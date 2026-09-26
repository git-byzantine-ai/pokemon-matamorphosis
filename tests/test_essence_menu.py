"""Run the ROM's actual selection function against EV boundary scenarios."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class EssenceMenuTests(unittest.TestCase):
    def test_selection_respects_whole_yields_caps_and_available_stock(self):
        source=(ROOT/'rom/overlay/src/metamorphosis_menu.c').read_text()
        function='static void ChangeEssence(s8 delta)'+source.split('static void ChangeEssence(s8 delta)',1)[1].split('\nstatic void Task_Essence',1)[0]
        prelude=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef int8_t s8;
#define NUM_STATS 6
#define MAX_PER_STAT_EVS 255
#define MAX_TOTAL_EVS 510
#define TRUE 1
#define FALSE 0
#define SE_SELECT 0
struct EssenceChoice {u16 species,available,add;};
struct {struct EssenceChoice rows[2];u16 cursor,evs[6];u8 limited;} state,*sEssence=&state;
u8 yields[3][6]={{0},{0,0,0,1,0,0},{0,0,0,0,2,1}};
u8 Meta_EssenceYield(u16 s,u8 i){return 3*yields[s][i];}
u16 EssenceEVTotal(void){u16 n=0;for(int i=0;i<6;i++)n+=state.evs[i];return n;}
void PlaySE(int x){}
void DrawEssence(void){}
'''
        checks=r'''
int main(void){
 state.rows[0]=(struct EssenceChoice){1,10,0};
 ChangeEssence(10);assert(state.rows[0].add==10 && state.evs[3]==30);
 ChangeEssence(1);assert(state.rows[0].add==10 && state.evs[3]==30);
 ChangeEssence(-10);ChangeEssence(-1);assert(state.rows[0].add==0 && state.evs[3]==0);
 state.evs[3]=252;ChangeEssence(10);assert(state.rows[0].add==1 && state.evs[3]==255 && state.limited);
 ChangeEssence(-1);assert(state.evs[3]==252 && state.rows[0].add==0);
 memset(&state,0,sizeof(state));state.rows[0]=(struct EssenceChoice){2,10,0};
 state.evs[4]=254;ChangeEssence(1);assert(state.rows[0].add==0 && state.evs[4]==254 && state.evs[5]==0);
 state.evs[4]=249;ChangeEssence(1);assert(state.rows[0].add==1 && state.evs[4]==255 && state.evs[5]==3);
 ChangeEssence(-1);assert(state.evs[4]==249 && state.evs[5]==0);
 memset(&state,0,sizeof(state));state.rows[0]=(struct EssenceChoice){2,10,0};
 state.evs[0]=255;state.evs[1]=254;
 ChangeEssence(1);assert(state.rows[0].add==0 && EssenceEVTotal()==509); /* no clipped 1/9 package */
 state.evs[1]=246;ChangeEssence(10);assert(state.rows[0].add==1 && EssenceEVTotal()==510);
 ChangeEssence(-1);assert(EssenceEVTotal()==501);
 return 0;
}
'''
        compiler=ROOT/'.tools/msys64/ucrt64/bin/gcc.exe'
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'selection.c';exe=Path(temp)/'selection.exe';src.write_text(prelude+function+checks)
            env=dict(os.environ);env['PATH']=str(compiler.parent)+os.pathsep+env['PATH']
            result=subprocess.run([str(compiler),'-std=c99',str(src),'-o',str(exe)],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(exe)],env=env,check=True,capture_output=True,timeout=10)
