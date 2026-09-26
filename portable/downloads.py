"""Pinned downloads with resumable transfers and verified publication."""
import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

DEPENDENCIES = {
    'emulator': {'file':'mgba-0.10.5.7z', 'sha256':'b497a57c7d9093834dadc64f33a90f7c411439c21fdb8a0143255a45ea37563a',
                 'url':'https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64.7z'},
    'runtime': {'file':'sd-vulkan-28b454b.zip', 'sha256':'3a4e5a75f022e4c0cad3e5a28c5921683adcb1808c0dd8e8a3536493497c793b',
                'url':'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-899-28b454b/sd-master-28b454b-bin-win-vulkan-x64.zip'},
    'model': {'file':'dreamshaper8.safetensors', 'sha256':'879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd',
              'url':'https://huggingface.co/Lykon/DreamShaper/resolve/228d79cb20811466f5c5710aa91f05dabd0b8a14/DreamShaper_8_pruned.safetensors?download=true'}
}
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def download(spec, destination, progress=lambda *_:None, cancel=None):
    destination = Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    progress(f'Checking {destination.name}',None)
    if destination.exists() and sha256(destination)==spec['sha256']:
        return destination
    partial = destination.with_suffix(destination.suffix+'.partial')
    if partial.exists() and sha256(partial)==spec['sha256']:
        os.replace(partial,destination)
        return destination
    start = partial.stat().st_size if partial.exists() else 0
    headers = {'User-Agent':'Pokemon-Metamorphosis-Installer/0.1'}
    if start: headers['Range'] = f'bytes={start}-'
    request = urllib.request.Request(spec['url'],headers=headers)
    with urllib.request.urlopen(request,timeout=30) as response:
        append = response.status==206 and response.headers.get('Content-Range','').startswith(f'bytes {start}-')
        if response.status==206 and not append:
            raise ValueError('Server returned an unexpected download range')
        if not append: start=0
        total = start+int(response.headers.get('Content-Length','0'))
        done = start
        with partial.open('ab' if append else 'wb') as out:
            while chunk:=response.read(1024*1024):
                if cancel and cancel.is_set(): raise InterruptedError('Download paused. Run setup again to resume.')
                out.write(chunk); done+=len(chunk)
                progress(f'Downloading {destination.name}: {done/1048576:.0f} MB',done/total if total else None)
    progress(f'Verifying {destination.name}',None)
    if sha256(partial)!=spec['sha256']:
        partial.unlink()
        raise ValueError(f'{destination.name} checksum mismatch. Retry setup to download a fresh copy.')
    os.replace(partial,destination)
    return destination


def safe_member(name):
    name=name.replace('\\','/')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name:
        raise ValueError('Unsafe archive member')


def extract(archive,destination):
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist(): safe_member(entry.filename)
            z.extractall(destination)
    else:
        # Windows 10/11 includes bsdtar, including 7z reading support.
        tar=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tar.exe'
        if not tar.exists(): raise RuntimeError('Windows tar.exe is missing. Install Windows updates, then retry setup.')
        result=subprocess.run([str(tar),'-tf',str(archive)],capture_output=True,text=True,check=True,creationflags=HIDDEN)
        for name in result.stdout.splitlines(): safe_member(name)
        subprocess.run([str(tar),'-xf',str(archive),'-C',str(destination)],capture_output=True,check=True,creationflags=HIDDEN)


def import_model(source,destination,progress):
    progress('Verifying existing DreamShaper 8 model',None)
    if sha256(source)!=DEPENDENCIES['model']['sha256']:
        raise ValueError('That is not the supported DreamShaper 8 model. Leave the optional model field empty to download the correct file.')
    destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    if Path(source).resolve()!=destination.resolve():
        temporary=destination.with_suffix('.importing'); shutil.copyfile(source,temporary); os.replace(temporary,destination)
    return destination
