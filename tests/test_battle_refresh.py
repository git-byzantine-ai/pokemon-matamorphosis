"""Execute the actual C refresh function against controlled battle timing states."""
import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GCC = ROOT/'.tools/msys64/ucrt64/bin/gcc.exe'


class BattleRefreshTests(unittest.TestCase):
    def test_delivery_during_hidden_sendout_is_retried(self):
        compiler = str(GCC) if GCC.exists() else shutil.which('gcc')
        if not compiler:
            self.skipTest('Host C compiler unavailable')
        source = (ROOT/'rom/overlay/src/metamorphosis.c').read_text()
        function = source.split('static bool8 RefreshBattle(void)',1)[1].split('\nbool8 Meta_Tick',1)[0]
        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
typedef uint8_t u8;
typedef int bool8;
#define TRUE 1
#define FALSE 0
#define B_SIDE_PLAYER 0
#define SPECIES_NONE 0
#define STATUS2_SUBSTITUTE 1
#define MAX_SPRITES 64
#define MON_DATA_PERSONALITY 0
#define MON_DATA_OT_ID 1
#define MON_DATA_HP 2
#define OBJ_PLTT_ID(n) (256+16*(n))
#define BG_PLTT_ID(n) (16*(n))
static u8 vram[0x8000];
#define OBJ_VRAM0 ((uintptr_t)vram)
struct Pokemon { int hp; };
struct Sprite { int inUse, invisible; struct { int tileNum; } oam; };
struct MetaAsset { u8 data[4128]; };
struct { int inBattle; } gMain;
struct { int active; } gPaletteFade;
struct { struct { int transformSpecies; } battlerData[4]; } battleData;
static __typeof__(battleData) *gBattleSpritesDataPtr=&battleData;
struct { void *sprites[4]; } gfx;
static __typeof__(gfx) *gMonSpritesGfxPtr=&gfx;
int gBattleControllerExecFlags, gBattlersCount=1, gAbsentBattlerFlags;
struct { int status2; } gBattleMons[4];
u8 gBattlerSpriteIds[4]={0,1,2,3},gBattlerPartyIndexes[4]={0,1,2,3};
struct Sprite gSprites[64];
struct Pokemon gPlayerParty[6];
struct MetaAsset asset;
int copies,haveAsset=1;
int GetBattlerSide(int b) { return b&1; }
int GetBattlerPosition(int b) { return b; }
int GetMonData(struct Pokemon *m,int field) { return field==MON_DATA_HP?m->hp:42; }
const struct MetaAsset *Meta_Find(int p,int o) { return haveAsset?&asset:NULL; }
int Meta_Load(struct Pokemon *m,void *b,int front,int palette) { assert(!front);return 1; }
void LoadPalette(const void *p,int offset,int size) { assert(size==32); }
void RequestSpriteCopy(void *src,void *dst,int size) { assert(size==2048);copies++; }
'''
        checks = r'''
int main(void) {
    gMain.inBattle=1;gPlayerParty[0].hp=20;
    gSprites[0].inUse=1;gSprites[0].invisible=1;
    assert(RefreshBattle()==FALSE && copies==0); /* delivery during send-out */
    gSprites[0].invisible=0;
    assert(RefreshBattle()==TRUE && copies==1); /* later visible frame retries */
    gBattleControllerExecFlags=1;
    assert(RefreshBattle()==FALSE && copies==1); /* active animation/dialogue */
    gBattleControllerExecFlags=0;gBattlerSpriteIds[0]=64;
    assert(RefreshBattle()==FALSE); /* not allocated yet */
    gBattlerSpriteIds[0]=0;gSprites[0].inUse=0;
    assert(RefreshBattle()==FALSE);
    gSprites[0].inUse=1;gBattlersCount=3;gPlayerParty[2].hp=20;
    gSprites[2].inUse=1;gSprites[2].invisible=1;
    assert(RefreshBattle()==FALSE); /* one double-battle member still hidden */
    gSprites[2].invisible=0;assert(RefreshBattle()==TRUE);
    gPlayerParty[0].hp=0;gPlayerParty[2].hp=0;
    gSprites[0].invisible=1;gSprites[2].invisible=1;
    assert(RefreshBattle()==TRUE); /* fainted battlers cannot block forever */
    gMain.inBattle=0;assert(RefreshBattle()==TRUE);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp)/'refresh.c';exe=Path(temp)/'refresh.exe'
            c.write_text(harness+'\nstatic bool8 RefreshBattle(void)'+function+checks)
            env=dict(os.environ)
            env['PATH']=str(Path(compiler).parent)+os.pathsep+env.get('PATH','')
            compiled=subprocess.run([compiler,'-std=gnu11','-O0',str(c),'-o',str(exe)],capture_output=True,text=True,env=env)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            subprocess.run([str(exe)],check=True,capture_output=True,env=env)
