"""Create a disposable RAM test harness for the compiled ROM, never for a user save.

Run at the title screen in a fresh emulator. Calls the real CreateMon,
Meta_Record and summary-screen functions; does not simulate their behavior.
The test does not exercise the battle XP/Rare Candy/Day Care hook call sites.
"""
import json
import re
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
parser = argparse.ArgumentParser()
parser.add_argument('--battle', action='store_true')
args = parser.parse_args()
symbols = {}
for line in (BUILD / 'symbols.txt').read_text().splitlines():
    m = re.match(r'([0-9a-f]+)\s+(?:[0-9a-f]+\s+)?\w\s+(\w+)$', line)
    if m:
        symbols[m[2]] = int(m[1], 16)

end = 0
for line in (BUILD / 'symbols.txt').read_text().splitlines():
    fields = line.split()
    if len(fields) == 4 and 0x02000000 <= int(fields[0],16) < 0x02040000:
        end = max(end, int(fields[0],16) + int(fields[1],16))
base = (end + 15) & ~15
asm = f'''.syntax unified
.cpu arm7tdmi
.thumb
.global _start
.thumb_func
_start:
 push {{r4, lr}}
 sub sp, #16
 movs r0, #0
 ldr r4, ={symbols['SetVBlankCallback'] | 1}
 bl call_r4
 movs r0, #0
 ldr r4, ={symbols['SetHBlankCallback'] | 1}
 bl call_r4
 ldr r4, ={symbols['ScanlineEffect_Stop'] | 1}
 bl call_r4
 ldr r4, ={symbols['ResetTasks'] | 1}
 bl call_r4
 ldr r4, ={symbols['FreeAllWindowBuffers'] | 1}
 bl call_r4
 ldr r0, ={symbols['gHeap']}
 ldr r1, =0x1B000
 ldr r4, ={symbols['InitHeap'] | 1}
 bl call_r4
 movs r0, #1
 str r0, [sp, #0]
 ldr r0, =0x12345678
 str r0, [sp, #4]
 movs r0, #1
 str r0, [sp, #8]
 str r0, [sp, #12]
 ldr r0, ={symbols['gPlayerParty']}
 movs r1, #4
 movs r2, #6
 movs r3, #31
 ldr r4, ={symbols['CreateMon'] | 1}
 bl call_r4
 ldr r0, ={symbols['gPlayerPartyCount']}
 movs r1, #1
 strb r1, [r0]
'''
for kind, donor in [(1, 16)] * 3 + [(2, 0)]:
    asm += f''' ldr r0, ={symbols['gPlayerParty']}
 movs r1, #{kind}
 movs r2, #{donor}
 movs r3, #0
 ldr r4, ={symbols['Meta_Record'] | 1}
 bl call_r4
'''
if args.battle:
    asm += f''' ldr r0, =0x87654321
 str r0, [sp, #4]
 ldr r0, ={symbols['gEnemyParty']}
 movs r1, #16
 movs r2, #5
 movs r3, #31
 ldr r4, ={symbols['CreateMon'] | 1}
 bl call_r4
 ldr r0, ={symbols['gEnemyPartyCount']}
 movs r1, #1
 strb r1, [r0]
 ldr r0, ={symbols['CB2_InitBattle'] | 1}
 ldr r4, ={symbols['SetMainCallback2'] | 1}
 bl call_r4
'''
else:
    asm += f''' movs r0, #0
 str r0, [sp]
 ldr r0, ={symbols['gPlayerParty']}
 movs r1, #0
 movs r2, #0
 ldr r3, =0x0203fff0
 ldr r3, [r3]
 ldr r4, ={symbols['ShowPokemonSummaryScreen'] | 1}
 bl call_r4
'''
asm += f'''
 add sp, #16
 pop {{r4, pc}}
.thumb_func
call_r4:
 bx r4
.pool
'''
(BUILD / 'smoke.s').write_text(asm)
tool = ROOT / '.tools/msys64/ucrt64/bin'
subprocess.run([str(tool / 'arm-none-eabi-as.exe'), '-mcpu=arm7tdmi', '-o', str(BUILD / 'smoke.o'), str(BUILD / 'smoke.s')], check=True)
subprocess.run([str(tool / 'arm-none-eabi-ld.exe'), '-Ttext', hex(base), '-o', str(BUILD / 'smoke.elf'), str(BUILD / 'smoke.o')], check=True)
subprocess.run([str(tool / 'arm-none-eabi-objcopy.exe'), '-O', 'binary', str(BUILD / 'smoke.elf'), str(BUILD / 'smoke.bin')], check=True)
code = (BUILD / 'smoke.bin').read_bytes()
assert base + len(code) <= 0x0203fff0, 'Insufficient unused EWRAM for the test fixture'
(BUILD / 'smoke-layout.json').write_text(json.dumps({'address':base, 'size':len(code)}))
bridge = json.loads((BUILD / 'bridge.json').read_text())['bridge_address']
lua = f'''-- Disposable integration fixture. Fresh title screen only; do not save.
assert(emu:read8({symbols['gPlayerPartyCount']}) == 0, 'Smoke test requires an empty party')
-- The title screen has not run NewGameInitData. Gen 3 strings terminate
-- with 0xff, not NUL; a zero-filled trainer name overruns summary buffers.
local save = emu:read32({symbols['gSaveBlock2Ptr']})
for i,v in ipairs({{0xce,0xbf,0xcd,0xce,0xff,0xff,0xff,0xff}}) do emu:write8(save+i-1,v) end
local code = '{code.hex()}'
for i=1,#code,2 do emu:write8({base}+(i-1)/2,tonumber(code:sub(i,i+1),16)) end
emu:write32(0x0203fff0, emu:read32({symbols['gMain'] + 4}))
emu:write32({symbols['gMain'] + 4}, {base | 1})
local n=0
local cb
cb=callbacks:add('frame',function()
 n=n+1
 if n==900 then
  console:log('SMOKE seq='..emu:read32(emu:read32({bridge + 12})+20)..' write='..emu:read32({bridge + 16})..' read='..emu:read32({bridge + 20})..' cacheEpoch='..emu:read32({bridge + 44}))
  callbacks:remove(cb)
 end
end)
console:log('Smoke: creating level 6 Charmander, recording three Pidgeys, opening summary')
'''
(BUILD / 'smoke.lua').write_text(lua, newline='\n')
(BUILD / 'smoke-mode.txt').write_text('battle' if args.battle else 'summary')
print(BUILD / 'smoke.lua')
