"""Validate the player's ROM, apply the release patch and extract local references."""
import hashlib
import struct
from pathlib import Path
from PIL import Image

BASE_SHA1 = '41cb23d8dccc8ebd7c649cd8fbb58eeace6e2fdc'
ROM_SIZE = 16 * 1024 * 1024


def validate_base(data):
    if len(data) != ROM_SIZE or hashlib.sha1(data).hexdigest() != BASE_SHA1:
        raise ValueError('Select an unmodified English FireRed v1.0 ROM (16 MiB). This file has a different version or checksum. Your original file was not changed.')


def apply_ips(original, patch):
    if patch[:5] != b'PATCH':
        raise ValueError('Invalid patch header')
    out = bytearray(original)
    position = 5
    while True:
        if position + 3 > len(patch):
            raise ValueError('Truncated patch')
        if patch[position:position+3] == b'EOF':
            if position + 3 != len(patch):
                raise ValueError('Unexpected patch trailer')
            return bytes(out)
        if position + 5 > len(patch):
            raise ValueError('Truncated patch record')
        offset = int.from_bytes(patch[position:position+3], 'big')
        count = int.from_bytes(patch[position+3:position+5], 'big')
        position += 5
        if count:
            value = patch[position:position+count]
            if len(value) != count:
                raise ValueError('Truncated patch data')
            position += count
        else:
            if position + 3 > len(patch):
                raise ValueError('Truncated patch run')
            count = int.from_bytes(patch[position:position+2], 'big')
            value = patch[position+2:position+3] * count
            position += 3
        if offset + count > ROM_SIZE:
            raise ValueError('Patch exceeds expected ROM size')
        out[offset:offset+count] = value


def decompress(rom, offset, maximum=32768):
    if offset < 0 or offset + 4 > len(rom) or rom[offset] != 0x10:
        raise ValueError('Invalid compressed sprite pointer')
    size = int.from_bytes(rom[offset+1:offset+4], 'little')
    if not 0 < size <= maximum:
        raise ValueError('Invalid decompressed sprite size')
    pos, out = offset + 4, bytearray()
    while len(out) < size:
        flags = rom[pos]; pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                a, b = rom[pos:pos+2]; pos += 2
                length, distance = (a >> 4) + 3, ((a & 15) << 8 | b) + 1
                if distance > len(out):
                    raise ValueError('Invalid sprite back reference')
                for _ in range(min(length, size-len(out))):
                    out.append(out[-distance])
            else:
                out.append(rom[pos]); pos += 1
    return bytes(out)


def untile(data):
    if len(data) < 2048:
        raise ValueError('Sprite tiles are incomplete')
    pixels = bytearray(4096)
    pos = 0
    for ty in range(0, 64, 8):
        for tx in range(0, 64, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    value = data[pos]; pos += 1
                    pixels[(ty+y)*64+tx+x] = value & 15
                    pixels[(ty+y)*64+tx+x+1] = value >> 4
    return bytes(pixels)


def extract_references(rom, index, destination):
    root = Path(destination).resolve()
    for relative, entry in index.items():
        folder = (root / 'graphics/pokemon' / relative).resolve()
        if not folder.is_relative_to(root):
            raise ValueError('Invalid sprite directory')
        folder.mkdir(parents=True, exist_ok=True)
        palettes = {}
        for kind in ('normal', 'shiny'):
            raw = decompress(rom, entry[kind], 128)[:32]
            palettes[kind] = [tuple(((n >> s) & 31)*255//31 for s in (0,5,10)) for n in struct.unpack('<16H',raw)]
            (folder/f'{kind}.pal').write_text('JASC-PAL\n0100\n16\n'+'\n'.join(' '.join(map(str,c)) for c in palettes[kind])+'\n')
        for view in ('front','back'):
            im = Image.frombytes('P',(64,64),untile(decompress(rom,entry[view])))
            im.putpalette([v for c in palettes['normal'] for v in c]); im.info['transparency'] = 0
            im.save(folder/f'{view}.png')
