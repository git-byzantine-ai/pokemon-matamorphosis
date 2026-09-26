import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class LuaBridgeTests(unittest.TestCase):
    def test_menu_delivery_paging_cancel_stale_response_and_error(self):
        lua=ROOT/'.tools/msys64/usr/bin/lua.exe'
        self.assertTrue(lua.exists(),'Install the project build toolchain first')
        bridge=(ROOT/'bridge/metamorphosis.lua').read_text().replace('@BRIDGE_ADDRESS@','0x02000000').replace('@ASSET_ADDRESS@','0x08010000')
        prelude=r'''
local memory={}
emu={memory={cart0={}}}
function emu:read8(a) return memory[a] or 0 end
function emu:read16(a) return self:read8(a)+256*self:read8(a+1) end
function emu:read32(a) return self:read16(a)+65536*self:read16(a+2) end
function emu:write8(a,v) memory[a]=v%256 end
function emu:write16(a,v) self:write8(a,v);self:write8(a+1,math.floor(v/256)) end
function emu:write32(a,v) self:write16(a,v);self:write16(a+2,math.floor(v/65536)) end
function emu:readRange(a,n) local t={} for i=0,n-1 do t[#t+1]=string.char(self:read8(a+i)) end return table.concat(t) end
local B=0x02000000
local C=0x02008000
local M=B+4760
emu:write32(B,0x4d41544d);emu:write32(B+4,6);emu:write32(B+8,0xc75f3521);emu:write32(B+12,C)
emu:write32(C,0x4d41544d);emu:write32(C+4,1)
local frame
callbacks={add=function(_,_,fn) frame=fn end}
local errors={}
console={log=function()end,error=function(_,s)errors[#errors+1]=s end}
local queued=nil
local requests={}
local response='ESSENCE 0000000000000000 0 9 1,10,0;2,20,0;3,30,0;4,40,0;5,50,0;6,60,0;7,70,0;8,80,0'
local progress='PROGRESS 0000000000000000 abcdef01 2'
socket={ERRORS={AGAIN='again'}}
local sock={}
function sock:connect() return true end
function sock:close() end
function sock:send(line)
 requests[#requests+1]=line
 if line:match('^HELLO') then assert(line=='HELLO 6 c75f3521\n');queued='OK 6\n'
 elseif line:match('^MENU') then queued=response..'\n'
 elseif line:match('^PROGRESS') then queued=progress..'\n'
 else queued='WAIT\n' end
 return #line
end
function sock:receive() local value=queued;queued=nil;if value then return value end return nil,'again' end
function socket.tcp()return sock end
local function request(id,offset)
 emu:write32(M,id);emu:write32(M+4,1);emu:write32(M+8,123);emu:write32(M+12,456)
 emu:write16(M+16,25);emu:write8(M+18,20);emu:write16(M+20,offset)
end
'''
        checks=r'''
request(1,0)
for i=1,122 do frame() end
assert(emu:read32(M+4)==2)
assert(emu:read16(M+22)==9 and emu:read16(M+24)==8)
assert(emu:read16(M+28+7*6)==8 and emu:read16(M+30+7*6)==80)
assert(requests[2]=='MENU 0000000000000001 0000000000000000 000001c8,0000007b,25,20 0\n')
response='ESSENCE 0000000000000000 8 9 9,90,0';request(2,8);frame();frame()
assert(emu:read32(M+4)==2 and emu:read16(M+24)==1 and emu:read16(M+30)==90)
-- Cancellation must not publish the arriving page.
request(3,8);frame();emu:write32(M+4,0);frame();assert(emu:read32(M+4)==0)
-- An old request id cannot satisfy a newly opened menu.
request(4,8);frame();emu:write32(M,5);frame();assert(emu:read32(M+4)==1)
frame();assert(emu:read32(M+4)==2)
-- Progress belongs to the currently selected individual and history head.
emu:write32(M+4,0);emu:write8(M+19,1)
local function awaitProgress()
 local previous=#requests
 for i=1,31 do frame();if #requests>previous and requests[#requests]:match('^PROGRESS') then return end end
 error('Progress not requested')
end
awaitProgress();frame()
assert(emu:read32(M+76)==2 and emu:read32(M+80)==0xabcdef01)
progress='PROGRESS 0000000000000000 abcdef02 3'
-- Closing the menu before a reply prevents publication.
awaitProgress();emu:write8(M+19,0);frame()
assert(emu:read32(M+76)==2 and emu:read32(M+80)==0xabcdef01)
emu:write8(M+19,1);awaitProgress();emu:write32(M,77);frame()
assert(emu:read32(M+76)==2)
awaitProgress();frame();assert(emu:read32(M+76)==3 and emu:read32(M+80)==0xabcdef02)
progress='PROGRESS ffffffffffffffff abcdef03 4';awaitProgress();frame()
assert(emu:read32(M+76)==3)
emu:write8(M+19,0)
-- Malformed or failed responses leave an actionable error, not a false page.
response='ESSENCE 0000000000000000 8 9 9,0,0';request(6,8);frame();frame();assert(emu:read32(M+4)==3)
response='ERROR checkpoint missing';request(7,8);frame();frame();assert(emu:read32(M+4)==3)
assert(#errors==1 and errors[1]:match('checkpoint missing'))
print('Lua menu protocol passed')
'''
        with tempfile.TemporaryDirectory() as temp:
            script=Path(temp)/'check.lua';script.write_text(prelude+'\ndo\n'+bridge+'\nend\n'+checks)
            env=dict(os.environ);env['PATH']=str(lua.parent)+os.pathsep+env['PATH']
            result=subprocess.run([str(lua),str(script)],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Lua menu protocol passed',result.stdout)
