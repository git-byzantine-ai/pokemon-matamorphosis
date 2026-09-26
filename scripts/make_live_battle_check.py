"""Prepare a Lua acceptance fixture for the already-running disposable test battle."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
symbols = {p[-1]:int(p[0],16) for line in (root/'build/symbols.txt').read_text().splitlines() if len(p:=line.split())>=3}
manifest = json.loads((root/'build/bridge.json').read_text())
base = manifest['bridge_address']
project = root.as_posix()
fixture = json.loads((root/'build/smoke-layout.json').read_text())['address']
asm = f'''.syntax unified
.cpu arm7tdmi
.thumb
.global _start
.thumb_func
_start:
 push {{r4, lr}}
 sub sp, #8
 movs r0, #235
 str r0, [sp]
 ldr r0, ={symbols['gPlayerParty']}
 movs r1, #25
 mov r2, sp
 ldr r4, ={symbols['SetMonData'] | 1}
 bl call_r4
 ldr r0, =0x0203fff0
 ldr r1, [r0]
 ldr r0, ={symbols['gMain'] + 4}
 str r1, [r0]
 add sp, #8
 pop {{r4, pc}}
.thumb_func
call_r4:
 bx r4
.pool
'''
(root/'build/live-exp.s').write_text(asm)
tool = root/'.tools/msys64/ucrt64/bin'
for command in [
    ['arm-none-eabi-as.exe','-mcpu=arm7tdmi','-o','build/live-exp.o','build/live-exp.s'],
    ['arm-none-eabi-ld.exe','-Ttext',hex(fixture),'-o','build/live-exp.elf','build/live-exp.o'],
    ['arm-none-eabi-objcopy.exe','-O','binary','build/live-exp.elf','build/live-exp.bin'],
]:
    subprocess.run([str(tool/command[0]),*command[1:]],cwd=root,check=True)
code=(root/'build/live-exp.bin').read_bytes()
assert fixture+len(code)<=0x0203fff0
lua = f'''
-- Only the disposable GDB-created Charmander battle. Never use with a real save.
local mon={symbols['gPlayerParty']}
assert(emu:read32(mon)==0x12345678 and emu:read32(mon+4)==1 and emu:read8(mon+84)==6, 'wrong test individual')
-- Schedule SetMonData at a main-loop boundary; a Lua callback can interrupt
-- the game while secure Pokemon data is temporarily decrypted.
local code='{code.hex()}'
for i=1,#code,2 do emu:write8({fixture}+(i-1)/2,tonumber(code:sub(i,i+1),16)) end
emu:write32(0x0203fff0,emu:read32({symbols['gMain']+4}))
emu:write32({symbols['gMain']+4},{fixture|1})
-- Force a fresh transfer through the shipping Lua ROM-bank protocol.
emu:write32({base+4740},0)
emu:write32({base+4748},0)
dofile('{project}/build/metamorphosis.lua')
local n=0
local result='not checked'
local dismissed=false
local complete=false
local cb
cb=callbacks:add('frame',function()
 n=n+1
 if n%30==1 and emu:read8(mon+84)<7 then emu:addKey(0) end
 if n%30==4 then emu:clearKey(0) end
 if n==300 then
  local id=emu:read8({symbols['gBattlerSpriteIds']})
  local attr=emu:read16({symbols['gSprites']}+id*68+4)
  local tiles=emu:readRange(0x06010000+(attr&1023)*32,2048)
  local file=assert(io.open('{project}/runtime/sprites/d3162e30d5425b5a4624cfa31ca2be3d39c61cb170cd0ad6160f0f5ead0e37fb/sprite.bin','rb'))
  local payload=file:read('*a'); file:close()
  result=(tiles==payload:sub(2049,4096)) and 'PASS: live Lua-delivered battle back sprite matches AI payload' or 'FAIL: battle sprite mismatch'
  console:log(result)
  emu:screenshot('{project}/build/in-game-ai-battle.png')
 end
 if n%60==0 and emu:read8(mon+84)>=7 then
  -- The normal controller waits for A on the level-up text. Allow one
  -- dismissal after delivery, then stay on the stat panel for inspection.
  if emu:read32({base+44})>=3 and not dismissed then
   emu:addKey(0); dismissed=true
  end
  local f=io.open('{project}/runtime/sprites/cc012fe3633ce71b530920badfc3007e0c0b33ae36549f67778f328805862fe7/sprite.bin','rb')
  if f then
   local payload=f:read('*a'); f:close()
   local id=emu:read8({symbols['gBattlerSpriteIds']})
   local attr=emu:read16({symbols['gSprites']}+id*68+4)
   if emu:readRange(0x06010000+(attr&1023)*32,2048)==payload:sub(2049,4096) then
    result=result..'\\nPASS: actual level 7 generated back sprite rendered byte-for-byte'
    complete=true
   end
  end
 end
 if complete or n==10800 then
  emu:clearKey(0)
  local line=result..'\\nlevel='..emu:read8(mon+84)..' write='..emu:read32({base+16})..' read='..emu:read32({base+20})..' cacheEpoch='..emu:read32({base+44})
  console:log(line)
  local file=assert(io.open('{project}/build/live-bridge-check.txt','w')); file:write(line); file:close()
  emu:screenshot('{project}/build/in-game-level-check.png')
  callbacks:remove(cb)
 end
end)
console:log('Live test: Lua upload, battle KO, actual level-up hook; stops inputs at level 7')
'''
(root/'build/live-bridge-check.lua').write_text(lua,newline='\n')
