"""Exercise compiled menu/EV functions in a disposable mGBA, never a user save.

Uses GDB for input injection and the same companion command/ACK protocol as Lua.
Captures actual BG0 VRAM for visual inspection. Does not test Lua networking.
Run: python -m scripts.essence_smoke
"""
import json
import os
import shutil
import struct
import subprocess
import time
from pathlib import Path
from PIL import Image
from companion.server import Application
from companion.history import unpack_event
from scripts.gdb_smoke import Remote

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/triple-update'
OUT=ROOT/'build/triple-tests/emulator'
CODE=0x08ff0000
PARAM=0x0203ff20


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # A new directory and filename on every run prevent accidental save reuse.
    session=OUT/str(time.time_ns());session.mkdir()
    rom=session/'disposable.gba';shutil.copy2(BUILD/'firered-metamorphosis.gba',rom)
    symbols={p[-1]:int(p[0],16) for line in (BUILD/'symbols.txt').read_text().splitlines() if len(p:=line.split())>=3}
    meta=json.loads((BUILD/'bridge.json').read_text());base=meta['bridge_address'];menu=base+4760
    mainptr=symbols['gMain'];party=symbols['gPlayerParty']
    asm=f'''.syntax unified
.cpu arm7tdmi
.thumb
.global rpc, keys, idle
.thumb_func
rpc:
 push {{r4,lr}}
 sub sp,#16
 ldr r4,={PARAM}
 ldr r0,[r4,#36]
 ldr r1,={mainptr+4}
 str r0,[r1]
 ldr r0,[r4,#16]
 str r0,[sp]
 ldr r0,[r4,#20]
 str r0,[sp,#4]
 ldr r0,[r4,#24]
 str r0,[sp,#8]
 ldr r0,[r4,#28]
 str r0,[sp,#12]
 ldr r0,[r4]
 ldr r1,[r4,#4]
 ldr r2,[r4,#8]
 ldr r3,[r4,#12]
 ldr r4,[r4,#40]
 bl call_r4
 ldr r4,={PARAM}
 str r0,[r4,#32]
 movs r0,#1
 str r0,[r4,#44]
 add sp,#16
 pop {{r4,pc}}
.thumb_func
keys:
 push {{r4,lr}}
 ldr r4,={PARAM}
 ldr r0,[r4]
 ldr r1,={mainptr+0x2e}
 strh r0,[r1]
 strh r0,[r1,#2]
 ldr r0,[r4,#36]
 ldr r1,={mainptr+4}
 str r0,[r1]
 movs r0,#1
 str r0,[r4,#44]
 ldr r4,[r4,#36]
 bl call_r4
 pop {{r4,pc}}
.thumb_func
idle:
 bx lr
.thumb_func
call_r4:
 bx r4
.pool
'''
    (session/'fixture.s').write_text(asm)
    tool=ROOT/'.tools/msys64/ucrt64/bin'
    env=dict(os.environ);env['PATH']=str(tool)+os.pathsep+env['PATH']
    def buildtool(name,*args):
        return subprocess.check_output([str(tool/(name+'.exe')),*map(str,args)],env=env,text=True)
    buildtool('arm-none-eabi-as','-mcpu=arm7tdmi','-o',session/'fixture.o',session/'fixture.s')
    buildtool('arm-none-eabi-ld','-Ttext',hex(CODE),'-o',session/'fixture.elf',session/'fixture.o')
    buildtool('arm-none-eabi-objcopy','-O','binary',session/'fixture.elf',session/'fixture.bin')
    entries={p[2]:int(p[0],16)|1 for line in buildtool('arm-none-eabi-nm',session/'fixture.elf').splitlines() if len(p:=line.split())==3}
    config=json.loads((ROOT/'config.example.json').read_text())
    config.update(database=str(session/'history.sqlite3'),cache=str(session/'sprites'))
    config['generator']['provider']='preview';app=Application(config)
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    proc=subprocess.Popen([str(ROOT/'.tools/mGBA-0.10.5-win64/mGBA.exe'),'-g',str(rom)],cwd=session,startupinfo=startup,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    remote=None
    try:
        time.sleep(2);remote=Remote();remote.cmd('?');remote.run(2)
        assert remote.mem(symbols['gPlayerPartyCount'],1)==b'\0','Disposable fixture must have an empty party'
        def u32(address):return struct.unpack('<I',remote.mem(address,4))[0]
        def write32(address,value):remote.write(address,struct.pack('<I',value))
        save=u32(symbols['gSaveBlock2Ptr']);remote.write(save,bytes.fromhex('cebfcdceffffffff'))
        remote.write(CODE,(session/'fixture.bin').read_bytes())
        write32(mainptr,0);write32(mainptr+4,entries['idle'])
        cp=u32(base+12);write32(cp+4,1);write32(cp+8,0xeeeeeeee)
        campaign='eeeeeeee00000001';events=[]
        def sync():
            write,read=struct.unpack('<II',remote.mem(base+16,8))
            for n in range(read,write):
                raw=remote.mem(base+132+n%128*36,36)
                event=unpack_event(raw);events.append(event)
                assert app.command(f'EVENT {campaign} {raw.hex()}')=='ACK '+event['head']
                write32(base+20,n+1)
        def pump():
            sync();remote.run(.08);sync()
        def invoke(entry,args=(),target=None):
            sync();values=list(args)+[0]*(8-len(args))
            remote.write(PARAM,struct.pack('<12I',*values,0,u32(mainptr+4),target or 0,0))
            write32(mainptr+4,entry)
            remote.run(.10);sync()
            if u32(PARAM+44)!=1:
                remote.run(.5);sync()
            assert u32(PARAM+44)==1, f'Injected callback did not finish: target={target}, registers={remote.cmd("g")}, callback={u32(mainptr+4):08x}'
            return u32(PARAM+32)
        def call(name,*args):return invoke(entries['rpc'],args,symbols[name]|1)
        def key(value):invoke(entries['keys'],[value]);pump()
        def evs():return [call('GetMonData3',party,26+i,0) for i in range(6)]
        for name in ('SetVBlankCallback','SetHBlankCallback'):call(name,0)
        for name in ('ScanlineEffect_Stop','ResetTasks','FreeAllWindowBuffers'):call(name)
        call('InitHeap',symbols['gHeap'],0x1b000)
        call('CreateMon',party,25,20,31,1,0x11223344,1,3)
        remote.write(symbols['gPlayerPartyCount'],b'\x01');pump()
        assert evs()==[0]*6
        # Mimic old EVs, then remove only the migration marker. Meta_Tick must
        # clear them exactly once while keeping level, moves and IVs intact.
        before=[call('GetMonData3',party,n,0) for n in (56,13,14,15,16,39,40,41,42,43,44)]
        remote.write(PARAM+64,b'\x21');call('SetMonData',party,29,PARAM+64)
        assert evs()[3]==33
        remote.write(party+30,b'\0\0');pump();assert evs()==[0]*6
        after=[call('GetMonData3',party,n,0) for n in (56,13,14,15,16,39,40,41,42,43,44)]
        assert before==after
        for _ in range(10):call('Meta_Record',party,1,16,0)
        call('MonGainEVs',party,16);assert evs()==[0]*6
        assert call('Meta_EssenceYield',16,3)==3
        assert call('Meta_EssenceYield',25,3)==6
        assert call('Meta_EssenceYield',6,4)==9
        assert call('Meta_EssenceYield',12,4)==6
        assert call('Meta_EssenceYield',12,5)==3
        # Seed an old applied build and saved marker; the new ROM refunds it
        # exactly once before 3x spending. Original user saves are never loaded.
        call('Meta_Record',party,6,0,0);call('Meta_Record',party,4,16,10);call('Meta_Record',party,5,0,0)
        remote.write(PARAM+64,b'\x0a');call('SetMonData',party,29,PARAM+64)
        remote.write(party+30,b'\x45\x4d');pump()
        assert evs()==[0]*6 and events[-1]['kind']==8
        current=f'{u32(cp+16):08x}{u32(cp+12):08x}'
        assert app.ledger_at(campaign,current,'00000003:11223344')['available']=={'16':10}
        call('Meta_EnsureEVs',party);pump()
        assert sum(e['kind']==8 for e in events)==1
        commits_before=sum(e['kind']==5 for e in events)
        def open_menu(direct=True):
            if direct:call('Meta_OpenEssenceMenu',0,entries['idle'])
            assert u32(menu+4)==1
            current=f'{u32(cp+16):08x}{u32(cp+12):08x}'
            pid,ot,species,level,_=struct.unpack('<IIHBB',remote.mem(menu+8,12))
            reply=app.command(f'MENU {campaign} {current} {ot:08x},{pid:08x},{species},{level} 0').split()
            rows=[] if reply[4]=='-' else [tuple(map(int,r.split(','))) for r in reply[4].split(';')]
            remote.write(menu+22,struct.pack('<HH',int(reply[3]),len(rows)))
            for i,row in enumerate(rows):remote.write(menu+28+i*6,struct.pack('<HHH',*row))
            write32(menu+4,2);pump()
        def capture(name):
            data=remote.mem(0x06000000,65536);pal=struct.unpack('<256H',remote.mem(0x05000000,512))
            control=struct.unpack('<H',remote.mem(0x04000008,2))[0]
            charbase=((control>>2)&3)*16384;mapbase=((control>>8)&31)*2048
            image=Image.new('RGB',(240,160));pixels=image.load()
            for y in range(160):
                for x in range(240):
                    entry=struct.unpack_from('<H',data,mapbase+((y//8)*32+x//8)*2)[0]
                    tx,ty=x%8,y%8
                    if entry&1024:tx=7-tx
                    if entry&2048:ty=7-ty
                    byte=data[charbase+(entry&1023)*32+ty*4+tx//2]
                    color=pal[(entry>>12)*16+(byte>>(4*(tx%2))&15)]
                    pixels[x,y]=tuple(((color>>shift)&31)*255//31 for shift in (0,5,10))
            image.resize((960,640),Image.Resampling.NEAREST).save(OUT/(name+'.png'))
        open_menu();capture('empty-selection')
        key(0x100) # R adds ten
        assert evs()==[0]*6
        capture('ten-selected')
        key(2) # B cancels
        assert evs()==[0]*6 and sum(e['kind']==5 for e in events)==commits_before
        open_menu();key(0x10) # right adds one
        key(8);capture('confirmation');key(1)
        for _ in range(6):pump()
        capture('committed')
        assert evs()==[0,0,0,3,0,0]
        assert [e['kind'] for e in events]==[1]*10+[6,4,5,8]+[6,4,5]
        current=f'{u32(cp+16):08x}{u32(cp+12):08x}'
        ledger=app.ledger_at(campaign,current,'00000003:11223344')
        assert ledger['available']=={'16':9} and ledger['spent']=={'16':1}
        call('Meta_EnsureEVs',party);assert evs()[3]==3
        key(2);open_menu();key(0x100);key(8);key(1)
        for _ in range(6):pump()
        assert evs()==[0,0,0,30,0,0]
        # Reopen applied quantities, refund all ten, then reapply without new defeats.
        key(2);open_menu();key(0x200);key(8);key(1)
        for _ in range(6):pump()
        assert evs()==[0]*6
        current=f'{u32(cp+16):08x}{u32(cp+12):08x}'
        assert app.ledger_at(campaign,current,'00000003:11223344')['available']=={'16':10}
        key(2);open_menu();key(0x100);key(8);key(1)
        for _ in range(6):pump()
        assert evs()[3]==30
        # Spinner moves while actual job status is pending, then confirms only
        # after the matching asset is resident in the ROM bank cache.
        write32(base+28,180);write32(menu+76,2);capture('generating-a')
        remote.run(.3);capture('generating-b')
        assert (OUT/'generating-a.png').read_bytes()!=(OUT/'generating-b.png').read_bytes()
        key(2)
        call('InitPartyMenu',0,0,0,0,0,symbols['Task_HandleChooseMonInput']|1,entries['idle'])
        remote.run(1);key(1);remote.run(.5);capture('party-action-menu')
        key(0x80);key(1);remote.run(.8)
        open_menu(direct=False);capture('party-menu-entry')
        key(2);remote.run(1)
        assert u32(mainptr+4)==symbols['CB2_UpdatePartyMenu']|1
        assert u32(symbols['sEssence'])==0
        report={'rom_sha256':meta['rom_sha256'],'reset_old_evs':True,'level_moves_ivs_preserved':True,
                'battle_evs_deferred':True,'cancel_spends_nothing':True,'partial_then_remaining_spend':True,
                'essence_multiplier':3,'legacy_applied_essence_refunded_once':True,'refund_and_reapply':True,'animated_generation_indicator':True,'migration_runs_once':True,'party_menu_entry_and_return':True,'final_evs':evs(),'event_kinds':[e['kind'] for e in events],
                'session':str(session),'transport':'GDB with real companion commands; Lua not exercised'}
        # Replay distinct historical pairs on a disposable clone. The user's
        # 12-, 20- and 35-EV exports are identical; 7 EVs provides a distinct pair.
        # Observe actual summary/front and battle/back OBJ VRAM after each
        # upload, rather than treating a cache acknowledgement as rendering.
        old_key='ea8a47f03ab231b152560e556cb074200445ad19a32e61fc22808b7b682bdf37'
        new_key='4980d58d8f190993bb3586c089a7800345cb56a625b6e68f9982403ae15be271'
        payloads=[(ROOT/'runtime/sprites'/k/'sprite.bin').read_bytes() for k in (old_key,new_key)]
        write32(mainptr,0);write32(mainptr+4,entries['idle'])
        call('SetVBlankCallback',0);call('ResetTasks');call('FreeAllWindowBuffers')
        call('ResetSpriteData');call('ResetAllPicSprites')
        call('InitHeap',symbols['gHeap'],0x1b000)
        call('CreateMon',party,1,12,31,1,0xae41f26a,1,0x9b1c965e)
        from companion.history import hash_bytes
        def upload(index):
            payload=payloads[index];ident=int((old_key,new_key)[index][:8],16)
            asset=struct.pack('<IIIHBBI',0x4d41544d,0xae41f26a,0x9b1c965e,1,12,0,ident)+payload
            remote.write(meta['asset_address']+index*4148,asset)
            write32(base+4756,index);write32(base+36,0);write32(base+40,hash_bytes(payload,2166136261))
            write32(base+32,1);pump()
        def sprite_bytes(sprite_id):
            assert sprite_id<64
            attr=struct.unpack('<H',remote.mem(symbols['gSprites']+sprite_id*68+4,2))[0]
            return remote.mem(0x06010000+(attr&1023)*32,2048)
        upload(0)
        call('ShowPokemonSummaryScreen',party,0,0,entries['idle'],0)
        remote.run(2)
        summary_sprite=None
        for i in range(8):
            pic=remote.mem(symbols['sSpritePics']+i*24,24)
            if pic[11] and struct.unpack_from('<I',pic,12)[0]==0xae41f26a:summary_sprite=pic[10];break
        assert summary_sprite is not None
        assert sprite_bytes(summary_sprite)==payloads[0][:2048],'Initial summary front mismatch'
        upload(1);remote.run(.5)
        assert sprite_bytes(summary_sprite)==payloads[1][:2048],'Refreshed summary front mismatch'
        assert payloads[0][:2048]!=payloads[1][:2048]
        print('PASS: existing Bulbasaur front changed in actual summary OBJ VRAM',flush=True)
        key(2);remote.run(1)
        call('CreateMon',symbols['gEnemyParty'],16,5,31,1,0x87654321,1,1)
        remote.write(symbols['gEnemyPartyCount'],b'\x01')
        upload(0);call('SetMainCallback2',symbols['CB2_InitBattle']|1)
        remote.run(4)
        def wait_back(payload):
            for attempt in range(35):
                sprite_id=remote.mem(symbols['gBattlerSpriteIds'],1)[0]
                if sprite_id<64:
                    flags=remote.mem(symbols['gSprites']+sprite_id*68+62,1)[0]
                    if flags&1 and not flags&4 and sprite_bytes(sprite_id)==payload[2048:4096]:return
                if attempt%6==5:key(1)
                remote.run(.2)
            raise AssertionError('Visible battle back sprite did not match uploaded payload')
        wait_back(payloads[0]);upload(1);wait_back(payloads[1])
        assert payloads[0][2048:4096]!=payloads[1][2048:4096]
        print('PASS: existing Bulbasaur back changed in actual visible battle OBJ VRAM',flush=True)
        report['user_sprite_rendering']={'before':old_key,'after':new_key,'summary_front_changed':True,'visible_battle_back_changed':True,'method':'Byte-for-byte OBJ VRAM comparison on isolated clone; original save not loaded'}
        (OUT/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    finally:
        if remote:remote.s.close()
        proc.terminate();proc.wait(timeout=10);app.history.close()


if __name__=='__main__':main()

