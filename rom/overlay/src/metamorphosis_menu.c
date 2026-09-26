#include "global.h"
#include "gflib.h"
#include "main.h"
#include "task.h"
#include "menu.h"
#include "data.h"
#include "metamorphosis.h"
#include "constants/pokemon.h"
#include "constants/species.h"
#include "constants/songs.h"

struct EssenceChoice { u16 species, available, add, used; };
struct EssenceMenu {
    struct EssenceChoice rows[NUM_SPECIES];
    u16 total, loaded, cursor, commitIndex, evs[NUM_STATS];
    u8 slot, stage, limited, commitPass, animation;
    void (*returnCallback)(void);
};
static EWRAM_DATA struct EssenceMenu *sEssence = NULL;
static const struct BgTemplate sEssenceBg[] = {{.bg=0, .charBaseIndex=0, .mapBaseIndex=31, .screenSize=0, .paletteMode=0, .priority=0}};
static const struct WindowTemplate sEssenceWindows[] = {{.bg=0, .tilemapLeft=1, .tilemapTop=1, .width=28, .height=19, .paletteNum=0, .baseBlock=1}, DUMMY_WIN_TEMPLATE};
static const u16 sEssencePalette[] = {RGB(4,8,10),RGB(28,30,27),RGB(3,7,10),RGB(20,23,21),RGB(31,31,31)};
static const u8 sEssenceColors[] = {1,2,3};
static const u8 sMaxTotal[] = _("/510");
static const u8 sArrow[] = _(">");
static const u8 sSlash[] = _("/");
static const u8 sTitle[] = _("METAMORPHOSIS");
static const u8 sLoading[] = _("Loading essence...\nKeep the companion connected.\n\nB: Return");
static const u8 sUnavailable[] = _("Essence history unavailable.\nCheck the companion.\n\nB: Return");
static const u8 sEmpty[] = _("No essence collected.\nDefeat Pokemon to collect some.\n\nB: Return");
static const u8 sConfirm[] = _("Apply these essence changes?\nRemoved essence returns to your bank.\n\nA: Confirm    B: Keep editing");
static const u8 sWorking[] = _("Applying metamorphosis...\nWaiting for history to be saved.");
static const u8 sDone[] = _("New sprite loaded!\nCheck SUMMARY or the next battle.\n\nA or B: Return");
static const u8 sGenerating[] = _("Shaping your Pokemon...\nThe companion is creating its sprite.\n\nA or B: Continue playing");
static const u8 sFailed[] = _("Sprite generation failed.\nPrevious artwork kept. Check companion.\n\nA or B: Return");
static const u8 sBelow[] = _("Essence and EVs updated.\nNormal sprite until 100 essence EVs.\n\nA or B: Return");
static const u8 sWaiting[] = _("Waiting for the companion...\nKeep its Lua script connected.\n\nA or B: Continue playing");
static const u8 sLimit[] = _("Stat or total EV limit reached.");
static const u8 sControls[] = _("Left/Right: -/+1  L/R: -/+10");
static const u8 sApply[] = _("START: Apply     B: Cancel");
static const u8 sColumns[] = _("ESSENCE       USE / OWN");
static const u8 sHP[] = _("HP ");
static const u8 sAtk[] = _("ATK ");
static const u8 sDef[] = _("DEF ");
static const u8 sSpe[] = _("SPE ");
static const u8 sSpa[] = _("SPA ");
static const u8 sSpd[] = _("SPD ");
static const u8 *const sStatLabels[] = {sHP,sAtk,sDef,sSpe,sSpa,sSpd};

static void EssenceText(u8 x, u8 y, const u8 *text)
{
    AddTextPrinterParameterized3(0, FONT_SMALL, x, y, sEssenceColors, TEXT_SKIP_DRAW, text);
}
static void EssenceNumber(u8 x, u8 y, u16 n)
{
    u8 text[8];
    ConvertIntToDecimalStringN(text,n,STR_CONV_MODE_LEFT_ALIGN,5);
    EssenceText(x,y,text);
}
static u16 EssenceEVTotal(void)
{
    u8 i; u16 total=0;
    for (i=0;i<NUM_STATS;i++) total+=sEssence->evs[i];
    return total;
}
static void DrawEssence(void)
{
    u16 row,first; u8 i;
    FillWindowPixelBuffer(0,PIXEL_FILL(1));
    EssenceText(0,0,sTitle);
    EssenceNumber(150,0,EssenceEVTotal());
    EssenceText(176,0,sMaxTotal);
    for (i=0;i<NUM_STATS;i++)
    {
        EssenceText((i%3)*74,14+(i/3)*12,sStatLabels[i]);
        EssenceNumber((i%3)*74+28,14+(i/3)*12,sEssence->evs[i]);
    }
    if (sEssence->stage==0)
        EssenceText(0,50,gMetaBridge.menu.status==3?sUnavailable:sLoading);
    else if (sEssence->stage==2)
        EssenceText(0,50,sConfirm);
    else if (sEssence->stage==3)
        EssenceText(0,50,sWorking);
    else if (sEssence->stage==4)
    {
        const struct MetaAsset *asset=Meta_Find(GetMonData(&gPlayerParty[sEssence->slot],MON_DATA_PERSONALITY),GetMonData(&gPlayerParty[sEssence->slot],MON_DATA_OT_ID));
        bool8 ready=gMetaBridge.menu.artStatus==3 && asset && asset->assetId==gMetaBridge.menu.artId;
        if (ready) EssenceText(0,50,EssenceEVTotal()<100?sBelow:sDone);
        else if (gMetaBridge.menu.artStatus==4) EssenceText(0,50,sFailed);
        else
        {
            EssenceText(0,50,gMetaBridge.heartbeat?sGenerating:sWaiting);
            FillWindowPixelRect(0,PIXEL_FILL(3),8,122,200,6);
            FillWindowPixelRect(0,PIXEL_FILL(2),8+(sEssence->animation/8%10)*18,122,20,6);
        }
    }
    else if (!sEssence->total)
        EssenceText(0,50,sEmpty);
    else
    {
        EssenceText(0,38,sColumns);
        first=(sEssence->cursor/6)*6;
        for (row=first;row<sEssence->total && row<first+6;row++)
        {
            u8 y=50+(row-first)*12;
            if (row==sEssence->cursor) EssenceText(0,y,sArrow);
            EssenceText(10,y,gSpeciesNames[sEssence->rows[row].species]);
            EssenceNumber(106,y,sEssence->rows[row].add);
            EssenceText(128,y,sSlash);
            EssenceNumber(140,y,sEssence->rows[row].available);
        }
        EssenceText(0,124,sApply);
        EssenceText(0,136,sEssence->limited?sLimit:sControls);
    }
    CopyWindowToVram(0,COPYWIN_FULL);
}
static void RequestEssencePage(void)
{
    struct Pokemon *mon=&gPlayerParty[sEssence->slot];
    struct MetaMenuBridge *request=&gMetaBridge.menu;
    request->requestId++;
    request->mon.personality=GetMonData(mon,MON_DATA_PERSONALITY);
    request->mon.otId=GetMonData(mon,MON_DATA_OT_ID);
    request->mon.species=GetMonData(mon,MON_DATA_SPECIES);
    request->mon.level=GetMonData(mon,MON_DATA_LEVEL);
    request->mon.valid=TRUE;
    request->offset=sEssence->loaded;
    gMetaBridge.display=request->mon;
    request->status=1;
}
static void CloseEssence(u8 taskId)
{
    void (*callback)(void)=sEssence->returnCallback;
    gMetaBridge.menu.status=0;
    gMetaBridge.menu.mon.valid=FALSE;
    gMetaBridge.display.valid=FALSE;
    SetVBlankCallback(NULL);
    FreeAllWindowBuffers();
    Free(sEssence);sEssence=NULL;
    DestroyTask(taskId);
    SetMainCallback2(callback);
}
static void ChangeEssence(s8 delta)
{
    struct EssenceChoice *choice=&sEssence->rows[sEssence->cursor];
    u8 i,step,count=delta<0?-delta:delta;
    sEssence->limited=FALSE;
    for (step=0;step<count;step++)
    {
        if (delta<0)
        {
            if (!choice->add) break;
            choice->add--;
            for (i=0;i<NUM_STATS;i++) sEssence->evs[i]-=Meta_EssenceYield(choice->species,i);
        }
        else
        {
            u16 total=EssenceEVTotal();
            if (choice->add>=choice->available || choice->add>=255) break;
            for (i=0;i<NUM_STATS;i++)
            {
                u8 yield=Meta_EssenceYield(choice->species,i);
                total+=yield;
                if (sEssence->evs[i]+yield>MAX_PER_STAT_EVS) break;
            }
            if (i<NUM_STATS || total>MAX_TOTAL_EVS)
            {
                sEssence->limited=TRUE;
                break;
            }
            choice->add++;
            for (i=0;i<NUM_STATS;i++) sEssence->evs[i]+=Meta_EssenceYield(choice->species,i);
        }
    }
    PlaySE(SE_SELECT);
    DrawEssence();
}
static void Task_Essence(u8 taskId)
{
    struct Pokemon *mon=&gPlayerParty[sEssence->slot];
    u16 i;
    if (sEssence->stage==3)
    {
        /* One event per frame: Meta_Tick waits for its durable acknowledgement.
         * A batch can contain all species without overflowing the event ring. */
        /* Refunds precede additions, allowing swaps even at the EV cap. */
        while (sEssence->commitPass<2)
        {
            while (sEssence->commitIndex<sEssence->total)
            {
                struct EssenceChoice *row=&sEssence->rows[sEssence->commitIndex++];
                s16 change=row->add-row->used;
                if ((sEssence->commitPass==0 && change<0) || (sEssence->commitPass==1 && change>0))
                {
                    Meta_Record(mon,change<0?7:4,row->species,change<0?-change:change);
                    return;
                }
            }
            sEssence->commitPass++;sEssence->commitIndex=0;
        }
        for (i=0;i<NUM_STATS;i++)
        {
            u8 ev=sEssence->evs[i];
            SetMonData(mon,MON_DATA_HP_EV+i,&ev);
        }
        CalculateMonStats(mon);
        Meta_Record(mon,5,0,0);
        gMetaBridge.menu.artStatus=0;gMetaBridge.menu.artId=0;
        sEssence->stage=4;
        DrawEssence();
        return;
    }
    if (sEssence->stage==4)
    {
        sEssence->animation++;
        if (!(sEssence->animation%8)) DrawEssence();
    }
    if (JOY_NEW(B_BUTTON) || (sEssence->stage==4 && JOY_NEW(A_BUTTON)))
    {
        if (sEssence->stage==2) {sEssence->stage=1;DrawEssence();}
        else CloseEssence(taskId);
        return;
    }
    if (sEssence->stage==0)
    {
        struct MetaMenuBridge *response=&gMetaBridge.menu;
        if (response->status==3) {DrawEssence();return;}
        if (response->status!=2) return;
        if (response->offset!=sEssence->loaded || response->total>NUM_SPECIES
         || response->count>8 || sEssence->loaded+response->count>response->total
         || (!response->count && sEssence->loaded<response->total))
        {response->status=3;DrawEssence();return;}
        sEssence->total=response->total;
        for (i=0;i<response->count;i++)
        {
            struct MetaEssenceRow *row=&response->rows[i];
            if (!row->species || row->species>=NUM_SPECIES) {response->status=3;DrawEssence();return;}
            sEssence->rows[sEssence->loaded].species=row->species;
            sEssence->rows[sEssence->loaded].used=row->used;
            sEssence->rows[sEssence->loaded].add=row->used;
            sEssence->rows[sEssence->loaded++].available=row->available;
        }
        if (sEssence->loaded<sEssence->total) RequestEssencePage();
        else {response->status=0;sEssence->stage=1;DrawEssence();}
        return;
    }
    if (sEssence->stage==2 && JOY_NEW(A_BUTTON))
    {
        Meta_Record(mon,6,0,META_ESSENCE_MULTIPLIER);
        sEssence->stage=3;sEssence->commitIndex=0;sEssence->commitPass=0;DrawEssence();return;
    }
    if (sEssence->stage!=1 || !sEssence->total) return;
    if (JOY_REPT(DPAD_UP))
    {sEssence->cursor=(sEssence->cursor+sEssence->total-1)%sEssence->total;DrawEssence();}
    else if (JOY_REPT(DPAD_DOWN))
    {sEssence->cursor=(sEssence->cursor+1)%sEssence->total;DrawEssence();}
    else if (JOY_REPT(DPAD_LEFT)) ChangeEssence(-1);
    else if (JOY_REPT(DPAD_RIGHT) || JOY_NEW(A_BUTTON)) ChangeEssence(1);
    else if (JOY_NEW(L_BUTTON)) ChangeEssence(-10);
    else if (JOY_NEW(R_BUTTON)) ChangeEssence(10);
    else if (JOY_NEW(START_BUTTON))
    {
        for (i=0;i<sEssence->total;i++) if (sEssence->rows[i].add!=sEssence->rows[i].used) break;
        if (i<sEssence->total) {sEssence->stage=2;DrawEssence();}
    }
}
static void EssenceVBlank(void)
{
    TransferPlttBuffer();
}
static void EssenceMain(void)
{
    RunTasks();
    RunTextPrinters();
    UpdatePaletteFade();
}
void Meta_OpenEssenceMenu(u8 slot, void (*returnCallback)(void))
{
    u8 i;
    SetVBlankCallback(NULL);
    SetGpuReg(REG_OFFSET_DISPCNT,0);
    DmaClearLarge16(3,(void *)VRAM,VRAM_SIZE,0x1000);
    ResetTasks();
    ResetSpriteData();
    ResetPaletteFade();
    ResetBgsAndClearDma3BusyFlags(0);
    InitBgsFromTemplates(0,sEssenceBg,1);
    ChangeBgX(0,0,0);ChangeBgY(0,0,0);
    if (!InitWindows(sEssenceWindows)) {FreeAllWindowBuffers();SetMainCallback2(returnCallback);return;}
    DeactivateAllTextPrinters();
    sEssence=AllocZeroed(sizeof(*sEssence));
    if (sEssence==NULL) {FreeAllWindowBuffers();SetMainCallback2(returnCallback);return;}
    sEssence->slot=slot;sEssence->returnCallback=returnCallback;
    gMetaBridge.menu.artStatus=0;gMetaBridge.menu.artId=0;
    Meta_EnsureEVs(&gPlayerParty[slot]);
    for (i=0;i<NUM_STATS;i++) sEssence->evs[i]=GetMonData(&gPlayerParty[slot],MON_DATA_HP_EV+i);
    LoadPalette(sEssencePalette,0,sizeof(sEssencePalette));
    PutWindowTilemap(0);
    DrawEssence();
    RequestEssencePage();
    CreateTask(Task_Essence,0);
    ShowBg(0);
    SetVBlankCallback(EssenceVBlank);
    SetMainCallback2(EssenceMain);
}
