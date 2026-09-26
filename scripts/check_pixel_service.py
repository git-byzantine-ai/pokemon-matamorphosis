"""Read-only replay of the existing disposable level-7 acceptance fixture.

No new gameplay events or emulator memory changes are made. POLL may enqueue
the current appearance with the updated renderer, as a reconnect would.
"""
import json
import socket
import sqlite3
import time
from pathlib import Path
from companion.generator import Generator
from companion.history import hash_bytes
from companion.sprites import validate


def main():
    config_path = Path('config.local.json')
    config = json.loads((config_path if config_path.exists() else Path('config.example.json')).read_text())
    fixture = json.loads(Path('build/anatomy-tests/service-request.json').read_text())
    campaign, head = fixture['campaign'], fixture['head']
    # Read the recorded job recipe so this probe cannot invent defeat counts.
    db = sqlite3.connect(f'file:{Path(config["database"]).resolve().as_posix()}?mode=ro',uri=True)
    row = db.execute('SELECT recipe FROM jobs WHERE campaign=? AND head=? AND level=7 ORDER BY rowid DESC LIMIT 1',
                     (campaign,head)).fetchone()
    db.close()
    if not row:
        raise RuntimeError('Disposable level-7 fixture is missing')
    recipe = json.loads(row[0])
    catalog = json.loads(Path(config['catalog']).read_text())
    expected = Generator(config,catalog).key(recipe)[:8]
    ot,pid = recipe['identity'].split(':')
    descriptor = f'{ot},{pid},4,7'
    def command(message):
        with socket.create_connection(('127.0.0.1',config['port']),timeout=5) as sock:
            stream = sock.makefile('rwb')
            stream.write(b'HELLO 3 c75f3521\n');stream.flush()
            assert stream.readline().decode().strip() == 'OK 3'
            stream.write((message+'\n').encode());stream.flush()
            return stream.readline().decode().strip()
    deadline = time.monotonic()+120
    while time.monotonic()<deadline:
        response = command(f'POLL {campaign} {head} - {descriptor}')
        fields = response.split()
        if fields[0]=='ASSET' and fields[6]==expected:
            payload = bytes.fromhex(fields[-1]);validate(payload)
            assert fields[4:6]==['4','7']
            assert hash_bytes(payload,2166136261)==int(fields[7],16)
            assert command(f'POLL {campaign} {head} {expected} {descriptor}')=='WAIT'
            result = {'status':'PASS','protocol':3,'species':4,'level':7,'bytes':len(payload),
                      'asset_id':expected,'checksum':fields[7],'known_asset_suppression':True}
            destination = Path('build/pixel-art-final/live-service-result.json')
            destination.write_text(json.dumps(result,indent=2))
            print(json.dumps(result),flush=True)
            return
        if response.startswith('ERROR'):
            raise RuntimeError(response)
        time.sleep(1)
    raise TimeoutError(f'Current pixel renderer asset {expected} was not delivered')


if __name__ == '__main__':
    main()
