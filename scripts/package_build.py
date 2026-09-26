"""Publish ROM, ELF-derived bridge and a compact IPS patch for this revision."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ips(original, modified):
    if len(modified) > 0x1000000:
        raise ValueError('IPS maximum ROM size exceeded; use BPS for expanded ROMs')
    output = bytearray(b'PATCH')
    i = 0
    while i < len(modified):
        if i < len(original) and original[i] == modified[i]:
            i += 1
            continue
        start = i
        if start == 0x454f46:
            start -= 1
        i += 1
        while i < len(modified) and i - start < 65535 and (i >= len(original) or original[i] != modified[i]):
            i += 1
        # IPS reserves the offset bytes spelling EOF.
        data = modified[start:i]
        output += start.to_bytes(3, 'big') + len(data).to_bytes(2, 'big') + data
    output += b'EOF'
    return bytes(output)


def package(destination=None):
    source = ROOT / 'rom/pokefirered'
    build = Path(destination).resolve() if destination else ROOT / 'build'
    build.mkdir(parents=True, exist_ok=True)
    nm = ROOT / '.tools/msys64/ucrt64/bin/arm-none-eabi-nm.exe'
    symbols = subprocess.check_output([str(nm), '-S', str(source / 'pokefirered.elf')], text=True)
    match = re.search(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+\w\s+gMetaBridge$', symbols, re.M)
    if not match:
        raise RuntimeError('gMetaBridge missing from ELF')
    address, size = (int(v, 16) for v in match.groups())
    banks = re.search(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+\w\s+gMetaAssetBanks$', symbols, re.M)
    bank_address, bank_size = (int(v,16) for v in banks.groups())
    assert 0x08000000 <= bank_address < 0x09000000 and bank_size == 12444
    lua = (ROOT / 'bridge/metamorphosis.lua').read_text().replace('@BRIDGE_ADDRESS@', hex(address)).replace('@ASSET_ADDRESS@',hex(bank_address))
    (build / 'metamorphosis.lua').write_text(lua, newline='\n')
    rom = source / 'pokefirered.gba'
    assert size == 4844, 'Unexpected C bridge layout'
    manifest = {'protocol': 6, 'essence_multiplier': 3, 'build_id': 'c75f3521', 'source_revision': 'c75f352304d529f6ba92d4f74b9cf8b5c3810788',
                'rom_sha256': hashlib.sha256(rom.read_bytes()).hexdigest(), 'bridge_address': address,
                'bridge_size': size, 'event_size': 36, 'event_capacity': 128,
                'event_offset': 132, 'cache_offset': 4740, 'cache_slots': 2, 'slot_size': 8, 'asset_size': 4148,
                'asset_address': bank_address, 'asset_banks': 3, 'incoming_bank_offset': 4756, 'payload_size': 4128,
                'menu_offset':4760,'menu_size':84,'essence_page_size':8}
    (build / 'bridge.json').write_text(json.dumps(manifest, indent=2))
    (build / 'symbols.txt').write_text(symbols)
    shutil.copy2(rom, build / 'firered-metamorphosis.gba')
    baseline = ROOT / 'build/firered-baseline.gba'
    if baseline.exists():
        (build / 'firered-metamorphosis.ips').write_bytes(ips(baseline.read_bytes(), rom.read_bytes()))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', help='Stage a matching ROM/bridge bundle without replacing the running game')
    package(parser.parse_args().output)
