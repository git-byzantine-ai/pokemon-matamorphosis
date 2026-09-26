"""Build a ROM-free Windows ZIP from a verified ROM/bridge build and baseline."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from portable import VERSION
from portable.downloads import sha256
from portable.rom import validate_base,decompress,apply_ips


def prepare(bundle):
    assets=ROOT/'build/portable-resources'; assets.mkdir(parents=True,exist_ok=True)
    source=ROOT/'rom/pokefirered'; base=(ROOT/'build/firered-baseline.gba').read_bytes(); validate_base(base)
    manifest=json.loads((bundle/'bridge.json').read_text())
    patched=apply_ips(base,(bundle/'firered-metamorphosis.ips').read_bytes())
    assert hashlib.sha256(patched).hexdigest()==manifest['rom_sha256']
    catalog=json.loads((ROOT/'build/catalog.json').read_text()); index={}
    for entry in catalog.values():
        relative=entry['path']
        if relative in index:continue
        folder=source/'graphics/pokemon'/relative
        if not (folder/'front.png').exists():folder=folder/'normal'
        offsets={}
        for view in ('front','back','normal','shiny'):
            suffix='4bpp.lz' if view in ('front','back') else 'gbapal.lz'
            candidate=folder/f'{view}.{suffix}'
            parent=folder
            while not candidate.exists() and parent!=source/'graphics/pokemon':
                parent=parent.parent;candidate=parent/f'{view}.{suffix}'
            compressed=candidate.read_bytes()
            # Some form palettes are built into a concatenated parent file.
            offset=base.find(compressed)
            if offset<0:raise ValueError(f'Cannot locate baseline sprite data: {relative}/{view}')
            decompress(base,offset);offsets[view]=offset
        index[relative]=offsets
    (assets/'references.json').write_text(json.dumps(index,sort_keys=True))
    for src,name in ((bundle/'firered-metamorphosis.ips','metamorphosis.ips'),(bundle/'metamorphosis.lua','metamorphosis.lua'),
                     (ROOT/'build/catalog.json','catalog.json'),(ROOT/'companion/data/traits.tsv','traits.tsv'),
                     (ROOT/'config.example.json','config.json'),(ROOT/'packaging/PLAYER_GUIDE.txt','PLAYER_GUIDE.txt')):
        shutil.copy2(src,assets/name)
    manifest.update(version=VERSION,files={p.name:sha256(p) for p in assets.iterdir() if p.is_file() and p.name!='manifest.json'})
    (assets/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return assets


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',default='build/triple-update');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    os.chdir(ROOT);assets=prepare(Path(args.bundle).resolve())
    if args.prepare_only:print(assets);return
    out=ROOT/'dist';work=ROOT/'build/pyinstaller'
    assert out.resolve().is_relative_to(ROOT) and work.resolve().is_relative_to(ROOT)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','Metamorphosis',
        '--distpath',str(out),'--workpath',str(work),'--specpath',str(work),
        '--paths',str(ROOT),'--add-data',f'{assets};release','--add-data',f'{ROOT / "companion/dashboard.html"};companion',
        str(ROOT/'portable/entry.py')],check=True)
    app=out/'Metamorphosis';licenses=app/'LICENSES';licenses.mkdir(exist_ok=True)
    for path in (ROOT/'packaging/licenses').glob('*'):shutil.copy2(path,licenses/path.name)
    for name in ('PLAYER_GUIDE.txt','THIRD_PARTY_NOTICES.txt'):shutil.copy2(ROOT/'packaging'/name,app/name)
    for distribution in ('pillow','pyinstaller'):
        meta=importlib.metadata.distribution(distribution)
        for f in meta.files or []:
            if any(s in str(f).lower() for s in ('license','copying','copyright')) and meta.locate_file(f).is_file():
                shutil.copy2(meta.locate_file(f),licenses/(distribution+'-'+Path(f).name))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.exists():raise ValueError('Python license not found')
    shutil.copy2(python_license,licenses/'Python.txt')
    for name in ('_tcl_data/license.terms','_tk_data/license.terms'):
        path=app/'_internal'/name
        if path.exists():shutil.copy2(path,licenses/(Path(name).parent.name+'.txt'))
    (app/'VERSION.txt').write_text(VERSION+'\n')
    zipped=out/f'Pokemon-Metamorphosis-{VERSION}-Windows-x64.zip'
    with zipfile.ZipFile(zipped,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(app.rglob('*')):
            if path.is_file():z.write(path,Path('Metamorphosis')/path.relative_to(app))
    forbidden=('.gba','.sav','.sqlite3','.safetensors')
    with zipfile.ZipFile(zipped) as z:
        assert not any(n.lower().endswith(forbidden) for n in z.namelist())
    (out/(zipped.name+'.sha256')).write_text(sha256(zipped)+'  '+zipped.name+'\n')
    print(json.dumps({'zip':str(zipped),'bytes':zipped.stat().st_size,'sha256':sha256(zipped)},indent=2))


if __name__=='__main__':main()
