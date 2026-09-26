"""Setup and launch logic shared by the GUI and repeatable package checks."""
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from contextlib import closing
from pathlib import Path
from . import VERSION
from .downloads import DEPENDENCIES, HIDDEN, download, extract, import_model, sha256
from .rom import validate_base, apply_ips, extract_references


def resources():
    if getattr(sys,'frozen',False): return Path(sys._MEIPASS)/'release'
    return Path(__file__).resolve().parents[1]/'build/portable-resources'


def default_data():
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PokemonMetamorphosis'


def write_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp'); temporary.write_text(json.dumps(value,indent=2),encoding='utf-8'); os.replace(temporary,path)


def devices(executable):
    result=subprocess.run([str(executable),'--list-devices'],capture_output=True,text=True,errors='replace',timeout=30,creationflags=HIDDEN)
    if result.returncode: raise RuntimeError('Graphics detection failed. See setup.log; update your graphics driver and retry.\n'+result.stderr[-1500:])
    found=[]
    for line in result.stdout.splitlines():
        m=re.match(r'^(Vulkan\d+|CPU)\s+(.+)$',line)
        if m: found.append({'id':m[1],'name':m[2]})
    if not found: raise RuntimeError('No supported image-generation device was detected.')
    return found


def preferred_device(found):
    def score(d):
        name=d['name'].lower()
        return (d['id']!='CPU',any(x in name for x in ('nvidia','radeon rx','arc(')),d['id'])
    return max(found,key=score)['id']


class Installation:
    def __init__(self,data,assets=None):
        self.data=Path(data).resolve(); self.assets=Path(assets or resources()).resolve()
        self.manifest=json.loads((self.assets/'manifest.json').read_text())
        self.data.mkdir(parents=True,exist_ok=True)
        self.model=self.data/'tools/models/dreamshaper8.safetensors'
        self.sd=self.data/'tools/stable-diffusion/sd-cli.exe'
        self.emulator=self.data/'tools/mGBA-0.10.5-win64/mGBA.exe'
        self.game=self.data/'game/firered-metamorphosis.gba'

    def state(self):
        path=self.data/'installation.json'
        return json.loads(path.read_text()) if path.exists() else {}

    def ready(self):
        state=self.state()
        return state.get('release_rom')==self.manifest['rom_sha256'] and all(p.is_file() for p in (self.game,self.sd,self.emulator,self.model))

    def setup(self,rom_path=None,model_path=None,progress=lambda *_:None,cancel=None):
        progress('Checking your FireRed ROM',None)
        base_path=Path(rom_path) if rom_path else self.data/'game/base.gba'
        if not base_path.is_file(): raise ValueError('Select your original FireRed ROM to begin setup.')
        base=base_path.read_bytes(); validate_base(base)
        # Build a complete new game/reference version before touching the current one.
        for name,expected in self.manifest['files'].items():
            if sha256(self.assets/name)!=expected: raise ValueError(f'Package file {name} is damaged. Download and extract the ZIP again.')
        patched=apply_ips(base,(self.assets/'metamorphosis.ips').read_bytes())
        if hashlib.sha256(patched).hexdigest()!=self.manifest['rom_sha256']: raise ValueError('Patched ROM checksum mismatch')
        if shutil.disk_usage(self.data).free < (500*1024*1024 if self.model.exists() else 4*1024**3):
            raise RuntimeError('Not enough free disk space. Allow at least 4 GB for first-time setup.')
        refs=self.data/'references'/self.manifest['source_revision']
        extract_references(base,json.loads((self.assets/'references.json').read_text()),refs)
        tools=self.data/'tools'; downloads=self.data/'downloads'
        for kind,dest in (('emulator',tools),('runtime',tools/'stable-diffusion')):
            if cancel and cancel.is_set(): raise InterruptedError('Setup paused.')
            archive=download(DEPENDENCIES[kind],downloads/DEPENDENCIES[kind]['file'],progress,cancel)
            extract(archive,dest)
        if model_path: import_model(model_path,self.model,progress)
        else: download(DEPENDENCIES['model'],self.model,progress,cancel)
        progress('Detecting graphics devices',None); found=devices(self.sd)
        old=self.state(); selected=old.get('device')
        if selected not in [d['id'] for d in found]: selected=preferred_device(found)
        self.game.parent.mkdir(parents=True,exist_ok=True)
        if self.game.exists() and sha256(self.game)!=self.manifest['rom_sha256']:
            self.backup()
        for path,content in ((self.data/'game/base.gba',base),(self.game,patched)):
            if not path.exists() or path.read_bytes()!=content:
                temporary=path.with_suffix('.new'); temporary.write_bytes(content); os.replace(temporary,path)
        # An empty portable INI isolates mGBA from any existing user installation.
        ini=self.emulator.parent/'config.ini'
        if not ini.exists(): ini.write_text('[ports.qt]\nvolume=128\n')
        state={'version':VERSION,'release_rom':self.manifest['rom_sha256'],'device':selected,'devices':found,'references':str(refs)}
        if old.get('ai_check',{}).get('device')==selected and old.get('devices')==found: state['ai_check']=old['ai_check']
        write_json(self.data/'installation.json',state)
        progress('Setup complete. Run Test AI, then Play.',1)
        return state

    def config(self,port=0,dashboard_port=0):
        config=json.loads((self.assets/'config.json').read_text())
        state=self.state(); device=state['device']
        config.update(source=str(self.data/'references'/self.manifest['source_revision']),catalog=str(self.assets/'catalog.json'),traits=str(self.assets/'traits.tsv'),
                      database=str(self.data/'history.sqlite3'),cache=str(self.data/'sprites'),
                      port=port,dashboard_port=dashboard_port,installation=str(self.data))
        config['generator'].update(executable=str(self.sd),model=str(self.model),
            backend='cpu' if device=='CPU' else f'te=cpu,diffusion={device},vae={device}',timeout_seconds=3600)
        return config

    def select_device(self,device):
        state=self.state()
        if device not in [d['id'] for d in state['devices']]: raise ValueError('Unknown graphics device')
        if device!=state['device']: state.pop('ai_check',None)
        state['device']=device; write_json(self.data/'installation.json',state)

    def test_ai(self,progress=lambda *_:None):
        from companion.generator import Generator
        from companion.recipe import make_recipe
        if not self.ready(): raise ValueError('Complete setup first.')
        progress('Generating a real front/back pair. This can take several minutes.',None)
        config=self.config(); config['cache']=str(self.data/'checks/sprites')
        catalog=json.loads((self.assets/'catalog.json').read_text())
        gen=Generator(config,catalog)
        recipe=make_recipe('00000002:11223344',20,25,{'16':34},catalog)
        start=time.monotonic(); key,payload=gen.generate(recipe)
        state=self.state(); state['ai_check']={'device':state['device'],'seconds':round(time.monotonic()-start,2),'key':key}
        write_json(self.data/'installation.json',state)
        progress('AI test passed: both sprite views are ready.',1)
        return dict(state['ai_check'],folder=str(payload.parent))

    def backup(self):
        dest=self.data/'backups'/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())[-6:]); dest.mkdir(parents=True,exist_ok=False)
        for path in (self.data/'game').glob('*.sav'): shutil.copy2(path,dest/path.name)
        for path in (self.game,self.data/'installation.json'):
            if path.exists(): shutil.copy2(path,dest/path.name)
        db=self.data/'history.sqlite3'
        if db.exists():
            with closing(sqlite3.connect(db)) as src,closing(sqlite3.connect(dest/'history.sqlite3')) as target: src.backup(target)
        # Sprites are immutable and retained in the same data directory.
        return dest


def free_ports():
    sockets=[]
    try:
        for _ in range(2):
            s=socket.socket(); s.bind(('127.0.0.1',0)); sockets.append(s)
        return tuple(s.getsockname()[1] for s in sockets)
    finally:
        for s in sockets:s.close()


def command(*args):
    if getattr(sys,'frozen',False): return [sys.executable,*args]
    return [sys.executable,'-m','portable.entry',*args]


class Session:
    def __init__(self,installation):
        self.installation=installation; self.process=None; self.game=None; self.job=None
        self.port,self.dashboard_port=free_ports()

    def start(self):
        from .windows import ChildJob
        install=self.installation
        if not install.ready(): raise ValueError('Complete setup before playing.')
        if not install.state().get('ai_check'): raise ValueError('Run Test AI once for the selected graphics device before playing.')
        config=install.config(self.port,self.dashboard_port)
        path=install.data/'session.json'; write_json(path,config)
        lua=(install.assets/'metamorphosis.lua').read_text().replace("'127.0.0.1', 8765",f"'127.0.0.1', {self.port}")
        self.script=install.data/'game/metamorphosis.lua'; self.script.write_text(lua,encoding='utf-8')
        log=(install.data/'companion.log').open('a',encoding='utf-8')
        try:
            self.process=subprocess.Popen(command('--companion',str(path)),stdout=log,stderr=log,creationflags=HIDDEN)
            self.job=ChildJob(self.process)
        finally: log.close()
        try:
            for _ in range(100):
                if self.process.poll() is not None: raise RuntimeError('Companion could not start. Open the data folder and inspect companion.log.')
                try:
                    status=self.status()
                    if status.get('installation')==str(install.data) and status.get('protocol')==6: break
                except (OSError,ValueError): pass
                time.sleep(.1)
            else: raise RuntimeError('Companion startup timed out. Check companion.log.')
            self.game=subprocess.Popen([str(install.emulator),'-C',f'savegamePath={install.game.parent}',
                '-C',f'savestatePath={install.data / "states"}',str(install.game)],cwd=install.emulator.parent)
        except Exception:
            self.close(); raise

    def status(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.dashboard_port}/api/status',timeout=1) as r:return json.load(r)

    def close(self):
        if self.game and self.game.poll() is None: raise RuntimeError('Save your game and close mGBA first.')
        if self.job: self.job.close(); self.job=None
        elif self.process and self.process.poll() is None: self.process.terminate()
        if self.process: self.process.wait(timeout=10)
