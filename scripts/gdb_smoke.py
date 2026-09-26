"""Developer-only rendering check in an isolated mGBA process started with -g.

Requires the running companion. Uses real ROM functions and durable TCP event
acknowledgments. GDB transports the sprite for this rendering test; the separate
Lua bridge must also be smoke-tested in mGBA. Never run against an existing save.
"""
import socket
import struct
import time
from pathlib import Path

class Remote:
    def __init__(self):
        self.s = socket.create_connection(('127.0.0.1', 2345), timeout=5)
        self.s.settimeout(5)

    def send(self, value):
        data = value.encode()
        self.s.sendall(b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode())

    def recv(self):
        while True:
            first = self.s.recv(1)
            if not first:
                raise ConnectionError('Emulator debugger disconnected')
            if first == b'$':
                break
        data = bytearray()
        while True:
            c = self.s.recv(1)
            if c == b'#':
                break
            data.extend(c)
        checksum = self.s.recv(2)
        self.s.sendall(b'+')
        return data.decode()

    def cmd(self, value):
        self.send(value)
        response = self.recv()
        while value != '?' and response.startswith(('S', 'T')):
            response = self.recv()
        return response

    def mem(self, address, count):
        return b''.join(bytes.fromhex(self.cmd(f'm{address+i:x},{min(512,count-i):x}')) for i in range(0,count,512))

    def write(self, address, data):
        for i in range(0, len(data), 256):
            part = data[i:i+256]
            assert self.cmd(f'M{address+i:x},{len(part):x}:{part.hex()}') == 'OK'

    def run(self, seconds=.2):
        self.send('c')
        self.s.settimeout(seconds)
        try:
            return self.recv()
        except TimeoutError:
            self.s.settimeout(5)
            self.s.sendall(b'\x03')
            return self.recv()
        finally:
            self.s.settimeout(5)

if __name__ == '__main__':
    import json
    symbols = {p[-1]:int(p[0],16) for line in open('build/symbols.txt') if len(p := line.split()) >= 3}
    manifest = json.loads(Path('build/bridge.json').read_text())
    b = manifest['bridge_address']
    remote = Remote()
    print('status', remote.cmd('?'))
    print('run', remote.run(2))
    print('registers', remote.cmd('g'))
    print('main', remote.mem(0x030030f0, 16).hex())
    save = struct.unpack('<I',remote.mem(symbols['gSaveBlock2Ptr'],4))[0]
    remote.write(save, bytes.fromhex('cebfcdceffffffff'))
    assert remote.mem(symbols['gPlayerPartyCount'],1) == b'\0', 'Requires a fresh empty-party session'
    fixture_address = json.loads(Path('build/smoke-layout.json').read_text())['address']
    remote.write(fixture_address, Path('build/smoke.bin').read_bytes())
    remote.write(0x0203fff0, remote.mem(0x030030f4, 4))
    remote.write(0x030030f4, struct.pack('<I', fixture_address | 1))
    print('break assert', remote.cmd(f"Z1,{symbols['AGBAssert']:x},2"))
    print('fixture run', remote.run(.3))
    print('registers', remote.cmd('g'))
    print('main', remote.mem(0x030030f0, 16).hex())
    print('queue', remote.mem(b+16,12).hex())
    cp = struct.unpack('<I', remote.mem(b+12,4))[0]
    campaign = 'ffffffff00000001'
    remote.write(cp+4, struct.pack('<II',1,0xffffffff))
    channel = socket.create_connection(('127.0.0.1',8765), timeout=10)
    stream = channel.makefile('rwb')
    def request(line):
        stream.write((line+'\n').encode()); stream.flush()
        return stream.readline().decode().strip()
    assert request('HELLO 3 c75f3521') == 'OK 3'
    write, read = struct.unpack('<II',remote.mem(b+16,8))
    assert write-read == 4
    for number in range(read,write):
        raw = remote.mem(b+132+(number%128)*36,36)
        ack = request(f'EVENT {campaign} {raw.hex()}')
        assert ack.startswith('ACK '), ack
        remote.write(b+20,struct.pack('<I',number+1))
    print('Durable companion ACKs: four real ROM events')
    payload = Path('runtime/sprites/d3162e30d5425b5a4624cfa31ca2be3d39c61cb170cd0ad6160f0f5ead0e37fb/sprite.bin').read_bytes()
    checksum = 2166136261
    for byte in payload:
        checksum = ((checksum ^ byte) * 16777619) & 0xffffffff
    asset = struct.pack('<IIIHBBI',0x4d41544d,0x12345678,1,4,6,0,0xd3162e30)+payload
    remote.write(manifest['asset_address'],asset)
    assert remote.mem(manifest['asset_address'],len(asset)) == asset
    remote.write(b+4756,struct.pack('<I',0))
    remote.write(b+36,struct.pack('<II',0,checksum))
    remote.write(b+32,struct.pack('<I',1))
    print('ack run', remote.run(.5))
    regs = remote.cmd('g')
    print('registers', regs)
    values = struct.unpack('<17I',bytes.fromhex(regs))
    if abs(values[15] - symbols['AGBAssert']) < 8:
        print('ASSERT', remote.mem(values[0],100).split(b'\0')[0], values[1],remote.mem(values[2],100).split(b'\0')[0])
        addr=0x02000000
        blocks=[]
        while True:
            flag,magic,size,prev,nxt=struct.unpack('<HHIII',remote.mem(addr,16))
            blocks.append((hex(addr),flag,size))
            if nxt==0x02000000 or len(blocks)>200:break
            addr=nxt
        print('HEAP',blocks)
        raise RuntimeError('ROM allocation assertion')
    print('main', remote.mem(0x030030f0,16).hex())
    p = struct.unpack('<I',remote.mem(symbols['sMonSummaryScreen'],4))[0]
    print('summary', hex(p), remote.mem(p+0x3274,12).hex())
    print('irqvector', remote.mem(0x03007ffc,4).hex())
    print('intrtable', remote.mem(symbols['gIntrTable'],56).hex())
    print('settle',remote.run(2))
    print('settled registers',remote.cmd('g'))
    print('settled summary', remote.mem(p+0x3274,12).hex())
    print('asset run',remote.run(1))
    print('asset registers',remote.cmd('g'))
    print('cache epoch',remote.mem(b+44,4).hex())
    print('asset summary',remote.mem(p+0x3274,12).hex())
    assert remote.mem(b+44,4) == struct.pack('<I',1)
    battle = Path('build/smoke-mode.txt').read_text() == 'battle'
    found = False
    if battle:
        remote.run(5)
        print('Battle initialized; intro awaits input. Run make_live_battle_check.py and its Lua fixture for rendering and level-up checks.')
    for index in range(0 if battle else 8):
        pic = remote.mem(symbols['sSpritePics']+index*24,24)
        if pic[11] and struct.unpack_from('<I',pic,12)[0] == 0x12345678:
            sprite = remote.mem(symbols['gSprites']+pic[10]*68,8)
            attr2 = struct.unpack_from('<H',sprite,4)[0]
            tiles = remote.mem(0x06010000+(attr2&1023)*32,2048)
            assert tiles == payload[:2048], 'Displayed sprite tiles differ from AI payload'
            found = True
    if not battle:
        assert found, 'Generated individual not present in the rendered sprite table'
        print('PASS: rendered OBJ VRAM equals the AI front sprite byte for byte')
    Path('build/gdb-iwram.bin').write_bytes(remote.mem(0x03000000, 0x8000))
    remote.send('c')
    stream.close(); channel.close()
    remote.s.close()
