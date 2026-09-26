"""Promote a verified ROM/bridge bundle before launch, retaining the old bundle.

The PowerShell launcher refuses promotion while mGBA is open. This function
touches only the listed build artifacts; save files and history stay in place.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

FILES = ('firered-metamorphosis.gba','firered-metamorphosis.ips','metamorphosis.lua','bridge.json','symbols.txt')


def apply(build):
    build = Path(build)
    pending = build/'pending-update'
    if not (pending/'READY').is_file():
        return False
    for name in FILES:
        if not (pending/name).is_file():
            raise ValueError(f'Incomplete pending update: {name}')
    manifest = json.loads((pending/'bridge.json').read_text())
    actual = hashlib.sha256((pending/'firered-metamorphosis.gba').read_bytes()).hexdigest()
    if actual != manifest['rom_sha256']:
        raise ValueError('Pending ROM checksum mismatch; current game was not changed')
    lua = (pending/'metamorphosis.lua').read_text()
    for address in ('bridge_address','asset_address'):
        if hex(manifest[address]) not in lua:
            raise ValueError('Pending Lua bridge does not match pending ROM')
    backup = build/'previous-builds'/str(time.time_ns())
    backup.mkdir(parents=True)
    for name in FILES:
        if (build/name).exists():
            shutil.copy2(build/name,backup/name)
    # The emulator is closed by the launcher precondition. SQLite's backup
    # API also captures committed WAL data if the old companion is still up.
    for save in build.glob('*.sav'):
        shutil.copy2(save,backup/save.name)
    project=build.parent
    config_path=project/'config.local.json'
    if not config_path.exists():config_path=project/'config.example.json'
    if config_path.exists():
        config=json.loads(config_path.read_text())
        database=Path(config['database'])
        if not database.is_absolute():database=project/database
        if database.exists():
            source=sqlite3.connect(database)
            destination=sqlite3.connect(backup/'history.sqlite3')
            try:source.backup(destination)
            finally:destination.close();source.close()
    try:
        for name in FILES:
            temporary = build/(name+'.update-tmp')
            shutil.copy2(pending/name,temporary)
            os.replace(temporary,build/name)
        os.replace(pending/'READY',pending/'APPLIED')
    except Exception:
        for name in FILES:
            if (backup/name).exists():
                shutil.copy2(backup/name,build/name)
        raise
    print(f'Applied game update. Previous ROM, saves, and available history backed up in {backup}.')
    return True


if __name__ == '__main__':
    apply(Path(__file__).resolve().parents[1]/'build')
