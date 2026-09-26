"""Small, audited edits applied against a pinned pristine source snapshot."""
import difflib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(source, target):
    changes = {}

    def edit(path, old, new, count=1):
        text = changes.get(path, (source / path).read_text())
        if text.count(old) != count:
            raise RuntimeError(f'Patch drift in {path}: expected {count} matches, got {text.count(old)} for {old[:80]!r}')
        changes[path] = text.replace(old, new)

    def include(path):
        edit(path, '#include "global.h"', '#include "global.h"\n#include "metamorphosis.h"')

    for path in ('src/main.c', 'src/battle_script_commands.c', 'src/party_menu.c', 'src/daycare.c',
                 'src/battle_gfx_sfx_util.c', 'src/trainer_pokemon_sprites.c', 'src/evolution_scene.c',
                 'src/pokemon_summary_screen.c', 'src/pokemon_storage_system_tasks.c', 'src/pokemon_storage_system_data.c', 'src/pokemon.c'):
        include(path)

    edit('include/malloc.h', '#define HEAP_SIZE 0x1C000', '#define HEAP_SIZE 0x1B000 // Reserve 4 KiB; sprite payloads live in emulator-patched ROM banks.')
    edit('ld_script.ld', '. = 0x1C000;', '. = 0x1B000;')
    edit('ld_script.ld', '        src/main.o(.text);', '        src/main.o(.text);\n        src/metamorphosis.o(.text);\n        src/metamorphosis_menu.o(.text);')
    # EVs come exclusively from confirmed essence spending. Disable vitamins
    # and all item EV mutations (including custom Enigma effects) consistently
    # in both the actual item-use path and its usability preview.
    pokemon_source = changes['src/pokemon.c']
    ev_start = pokemon_source.index('void MonGainEVs(struct Pokemon *mon, u16 defeatedSpecies)')
    ev_end = pokemon_source.index('u16 GetMonEVCount',ev_start)
    edit('src/pokemon.c',pokemon_source[ev_start:ev_end],
         'void MonGainEVs(struct Pokemon *mon, u16 defeatedSpecies)\n{\n    // Banked by Meta_Defeat. Only confirmed essence spending grants EVs.\n}\n\n')
    edit('src/pokemon.c', '        itemEffect = gItemEffectTable[item - ITEM_POTION];\n    }',
         '''        itemEffect = gItemEffectTable[item - ITEM_POTION];
    }
    if ((itemEffect[4] & (ITEM4_EV_HP | ITEM4_EV_ATK))
     || (itemEffect[5] & (ITEM5_EV_DEF | ITEM5_EV_SPEED | ITEM5_EV_SPDEF | ITEM5_EV_SPATK)))
        return TRUE; // No effect: essence is the only EV source.''', count=2)
    edit('src/party_menu.c', 'static void CursorCB_Summary(u8 taskId);',
         'static void CursorCB_Summary(u8 taskId);\nstatic void CursorCB_Metamorphosis(u8 taskId);\nstatic void CB2_OpenMetamorphosis(void);\nstatic void CB2_ReturnFromMetamorphosis(void);')
    edit('src/party_menu.c', '    u8 actions[8];', '    u8 actions[9];')
    edit('src/party_menu.c', 'SetWindowTemplateFields(2, 19, 19 - (sPartyMenuInternal->numActions * 2), 10,',
         'SetWindowTemplateFields(2, 16, 19 - (sPartyMenuInternal->numActions * 2), 13,')
    edit('src/party_menu.c', '    AppendToList(sPartyMenuInternal->actions, &sPartyMenuInternal->numActions, CURSOR_OPTION_SUMMARY);',
         '    AppendToList(sPartyMenuInternal->actions, &sPartyMenuInternal->numActions, CURSOR_OPTION_SUMMARY);\n    AppendToList(sPartyMenuInternal->actions, &sPartyMenuInternal->numActions, CURSOR_OPTION_METAMORPHOSIS);')
    edit('src/data/party_menu.h', '    CURSOR_OPTION_FIELD_MOVES,', '    CURSOR_OPTION_METAMORPHOSIS,\n    CURSOR_OPTION_FIELD_MOVES,')
    edit('src/data/party_menu.h', 'static struct\n{\n    const u8 *text;\n    TaskFunc func;',
         'static const u8 sMetamorphosisLabel[] = _("METAMORPHOSIS");\n\nstatic struct\n{\n    const u8 *text;\n    TaskFunc func;')
    edit('src/data/party_menu.h', '    [CURSOR_OPTION_SUMMARY]', '    [CURSOR_OPTION_METAMORPHOSIS] = {sMetamorphosisLabel, CursorCB_Metamorphosis},\n    [CURSOR_OPTION_SUMMARY]')
    # Reopen the same individual; the summary-screen last-viewed slot is not
    # meaningful when returning from the new custom screen.
    changes['src/party_menu.c'] += '''
static void CursorCB_Metamorphosis(u8 taskId)
{
    PlaySE(SE_SELECT);
    sPartyMenuInternal->exitCallback = CB2_OpenMetamorphosis;
    Task_ClosePartyMenu(taskId);
}
static void CB2_OpenMetamorphosis(void)
{
    Meta_OpenEssenceMenu(gPartyMenu.slotId, CB2_ReturnFromMetamorphosis);
}
static void CB2_ReturnFromMetamorphosis(void)
{
    gPaletteFade.bufferTransferDisabled = TRUE;
    InitPartyMenu(gPartyMenu.menuType, KEEP_PARTY_LAYOUT, gPartyMenu.action, TRUE,
                 PARTY_MSG_DO_WHAT_WITH_MON, Task_TryCreateSelectionWindow, gPartyMenu.exitCallback);
}
'''
    edit('src/pokemon_summary_screen.c', '    FREE_AND_SET_NULL_IF_SET(sMonSummaryScreen);', '    gMetaBridge.display.valid = FALSE;\n    FREE_AND_SET_NULL_IF_SET(sMonSummaryScreen);')
    edit('src/main.c', '        ReadKeys();', '''        ReadKeys();
        if (!Meta_Tick())
        {
            MapMusicMain();
            WaitForVBlank();
            continue;
        }''')
    edit('src/battle_script_commands.c', '            gBattleScripting.getexpState++;\n            gBattleStruct->givenExpMons',
         '            Meta_Defeat(gBattlerFainted, sentIn);\n            gBattleScripting.getexpState++;\n            gBattleStruct->givenExpMons')
    edit('src/battle_script_commands.c', '                BattleScriptPushCursor();\n                gLeveledUpInBattle',
         '                Meta_Record(&gPlayerParty[gBattleStruct->expGetterMonId], 2, 0, 0);\n                BattleScriptPushCursor();\n                gLeveledUpInBattle')
    edit('src/party_menu.c', '    ExecuteTableBasedItemEffect_(gPartyMenu.slotId, gSpecialVar_ItemId, 0);\n    GetMonLevelUpWindowStats',
         '    ExecuteTableBasedItemEffect_(gPartyMenu.slotId, gSpecialVar_ItemId, 0);\n    Meta_Record(mon, 2, 0, 1);\n    GetMonLevelUpWindowStats')
    edit('src/daycare.c', "        if (TryIncrementMonLevel(mon))\n        {\n            // Teach", "        if (TryIncrementMonLevel(mon))\n        {\n            Meta_Record(mon, 2, 0, 2);\n            // Teach")

    # Only the player loader gets a new early return; enemies remain canonical.
    edit('src/battle_gfx_sfx_util.c', '''    position = GetBattlerPosition(battlerId);
    if (ShouldIgnoreDeoxysForm''', '''    position = GetBattlerPosition(battlerId);
    if (gBattleSpritesDataPtr->battlerData[battlerId].transformSpecies == SPECIES_NONE
     && Meta_Load(mon, gMonSpritesGfxPtr->sprites[position], FALSE, OBJ_PLTT_ID(battlerId)))
    {
        const struct MetaAsset *asset = Meta_Find(monsPersonality, otId);
        LoadPalette(asset->data + 0x1000, BG_PLTT_ID(8) + BG_PLTT_ID(battlerId), PLTT_SIZE_4BPP);
        return;
    }
    if (ShouldIgnoreDeoxysForm''')

    edit('src/trainer_pokemon_sprites.c', '    u8 active;\n};', '    u8 active;\n    u32 personality, otId;\n    bool8 isFrontPic, isTrainer;\n};')
    edit('src/trainer_pokemon_sprites.c', '    for (j = 0; j < 4; j ++)', '''    if (!isTrainer)
        Meta_LoadPic(personality, otId, framePics, isFrontPic);
    for (j = 0; j < 4; j ++)''')
    edit('src/trainer_pokemon_sprites.c', '    sSpritePics[i].active = TRUE;', '''    sSpritePics[i].active = TRUE;
    sSpritePics[i].personality = personality;
    sSpritePics[i].otId = otId;
    sSpritePics[i].isFrontPic = isFrontPic;
    sSpritePics[i].isTrainer = isTrainer;
    Meta_RefreshPicSprites();''')
    changes['src/trainer_pokemon_sprites.c'] += '''
void Meta_RefreshPicSprites(void)
{
    u8 i;
    const struct MetaAsset *asset;
    struct Sprite *sprite;
    for (i = 0; i < PICS_COUNT; i++)
    {
        if (!sSpritePics[i].active || sSpritePics[i].isTrainer || sSpritePics[i].spriteId >= MAX_SPRITES)
            continue;
        sprite = &gSprites[sSpritePics[i].spriteId];
        if (!sprite->inUse || sprite->images != sSpritePics[i].images)
            continue;
        asset = Meta_Find(sSpritePics[i].personality, sSpritePics[i].otId);
        if (asset == NULL)
            continue;
        Meta_LoadPic(sSpritePics[i].personality, sSpritePics[i].otId, sSpritePics[i].frames, sSpritePics[i].isFrontPic);
        LoadPalette(asset->data + 0x1000, OBJ_PLTT_ID(sprite->oam.paletteNum), 32);
        RequestSpriteCopy(sSpritePics[i].frames, (u8 *)(OBJ_VRAM0 + sprite->oam.tileNum * 32), 0x800);
    }
}
'''
    edit('src/pokemon_summary_screen.c', '    sMonPicBounceState = AllocZeroed(sizeof(struct MonPicBounceState));', '''    sMonPicBounceState = AllocZeroed(sizeof(struct MonPicBounceState));
    gMetaBridge.display.personality = GetMonData(&sMonSummaryScreen->currentMon, MON_DATA_PERSONALITY);
    gMetaBridge.display.otId = GetMonData(&sMonSummaryScreen->currentMon, MON_DATA_OT_ID);
    gMetaBridge.display.species = GetMonData(&sMonSummaryScreen->currentMon, MON_DATA_SPECIES);
    gMetaBridge.display.level = GetMonData(&sMonSummaryScreen->currentMon, MON_DATA_LEVEL);
    gMetaBridge.display.valid = !GetMonData(&sMonSummaryScreen->currentMon, MON_DATA_IS_EGG);''')

    # Keep evolution side effects/move learning; replace the visual-only states.
    edit('src/evolution_scene.c', 'static void Task_EvolutionScene(u8 taskId);', 'static const u8 sMetaGrowthText[] = _("Metamorphosis continues!\\nHold B to pause this growth.");\nstatic void Task_EvolutionScene(u8 taskId);')
    edit('src/evolution_scene.c', '''            StringExpandPlaceholders(gStringVar4, gText_PkmnIsEvolving);
            BattlePutTextOnWindow(gStringVar4, B_WIN_MSG);
            gTasks[taskId].tState++;''', '''            StringExpandPlaceholders(gStringVar4, sMetaGrowthText);
            BattlePutTextOnWindow(gStringVar4, B_WIN_MSG);
            sEvoStructPtr->delayTimer = 90;
            gTasks[taskId].tState++;''')
    edit('src/evolution_scene.c', '''    case EVOSTATE_INTRO_MON_ANIM:
        if (!IsTextPrinterActive(0))
        {
            PlayCry_Normal(gTasks[taskId].tPreEvoSpecies, 0);
            gTasks[taskId].tState++;
        }
        break;''', '''    case EVOSTATE_INTRO_MON_ANIM:
        if (!IsTextPrinterActive(0))
        {
            if ((gMain.heldKeys & B_BUTTON) && (gTasks[taskId].tBits & TASK_BIT_CAN_STOP))
            {
                gTasks[taskId].tEvoWasStopped = TRUE;
                gTasks[taskId].tState = EVOSTATE_TRY_LEARN_MOVE;
            }
            else if (--sEvoStructPtr->delayTimer == 0)
            {
                if (!IsNationalPokedexEnabled() && gTasks[taskId].tPostEvoSpecies > SPECIES_MEW)
                {
                    gTasks[taskId].tEvoWasStopped = TRUE;
                    gTasks[taskId].tState = EVOSTATE_TRY_LEARN_MOVE;
                }
                else
                    gTasks[taskId].tState = EVOSTATE_SET_MON_EVOLVED;
            }
        }
        break;''')
    edit('src/evolution_scene.c', '            StringExpandPlaceholders(gStringVar4, gText_CongratsPkmnEvolved);', '            StringExpandPlaceholders(gStringVar4, sMetaGrowthText);', count=2)
    edit('src/evolution_scene.c', '            IncrementGameStat(GAME_STAT_EVOLVED_POKEMON);', '            IncrementGameStat(GAME_STAT_EVOLVED_POKEMON);\n            Meta_Record(mon, 3, 0, 3);', count=2)
    edit('src/evolution_scene.c', '''    LoadCompressedPalette(pokePal->data, OBJ_PLTT_ID(1), PLTT_SIZE_4BPP);

    SetMultiuseSpriteTemplateToPokemon(currSpecies''', '''    LoadCompressedPalette(pokePal->data, OBJ_PLTT_ID(1), PLTT_SIZE_4BPP);
    Meta_Load(mon, gMonSpritesGfxPtr->sprites[B_POSITION_OPPONENT_LEFT], TRUE, OBJ_PLTT_ID(1));

    SetMultiuseSpriteTemplateToPokemon(currSpecies''')

    edit('src/pokemon_storage_system_data.c', '    gStorage->displayMonItemId = ITEM_NONE;\n    gender = MON_MALE;', '    gMetaBridge.display.valid = FALSE;\n    gStorage->displayMonItemId = ITEM_NONE;\n    gender = MON_MALE;')
    edit('src/pokemon_storage_system_data.c', '            gStorage->displayMonPalette = GetMonFrontSpritePal(mon);', '''            gStorage->displayMonPalette = GetMonFrontSpritePal(mon);
            gMetaBridge.display.personality = gStorage->displayMonPersonality;
            gMetaBridge.display.otId = GetMonData(mon, MON_DATA_OT_ID);
            gMetaBridge.display.species = gStorage->displayMonSpecies;
            gMetaBridge.display.level = gStorage->displayMonLevel;
            gMetaBridge.display.valid = !gStorage->displayMonIsEgg;''')
    edit('src/pokemon_storage_system_data.c', '            gStorage->displayMonPalette = GetMonSpritePalFromSpeciesAndPersonality(gStorage->displayMonSpecies, otId, gStorage->displayMonPersonality);', '''            gStorage->displayMonPalette = GetMonSpritePalFromSpeciesAndPersonality(gStorage->displayMonSpecies, otId, gStorage->displayMonPersonality);
            gMetaBridge.display.personality = gStorage->displayMonPersonality;
            gMetaBridge.display.otId = otId;
            gMetaBridge.display.species = gStorage->displayMonSpecies;
            gMetaBridge.display.level = gStorage->displayMonLevel;
            gMetaBridge.display.valid = !gStorage->displayMonIsEgg;''')
    edit('src/pokemon_storage_system_tasks.c', '    FREE_AND_SET_NULL(gStorage);', '    gMetaBridge.display.valid = FALSE;\n    FREE_AND_SET_NULL(gStorage);')
    edit('src/pokemon_storage_system_tasks.c', '        gStorage->displayMonSprite->invisible = FALSE;', '        gStorage->displayMonSprite->invisible = FALSE;\n        Meta_RefreshStorage();')
    changes['src/pokemon_storage_system_tasks.c'] += '''
void Meta_RefreshStorage(void)
{
    const struct MetaAsset *asset;
    if (gStorage == NULL || !gMetaBridge.display.valid || gStorage->displayMonSprite == NULL
     || gStorage->displayMonIsEgg || gStorage->displayMonSpecies == SPECIES_NONE)
        return;
    asset = Meta_Find(gMetaBridge.display.personality, gMetaBridge.display.otId);
    if (asset == NULL)
        return;
    memcpy(gStorage->tileBuffer, asset->data, 0x800);
    CpuCopy32(gStorage->tileBuffer, gStorage->displayMonTilePtr, 0x800);
    LoadPalette(asset->data + 0x1000, gStorage->displayMonPalOffset, 32);
}
'''

    patch = []
    for path, text in changes.items():
        if not (target / path).exists() or (target / path).read_text() != text:
            (target / path).write_text(text, newline='\n')
        patch.extend(difflib.unified_diff((source / path).read_text().splitlines(True), text.splitlines(True), 'a/' + path, 'b/' + path))
    overlay = ROOT / 'rom/overlay'
    for file in overlay.rglob('*'):
        if file.is_file():
            relative = file.relative_to(overlay)
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            if not (target / relative).exists() or (target / relative).read_bytes() != file.read_bytes():
                shutil.copy2(file, target / relative)
            patch.extend(difflib.unified_diff([], file.read_text().splitlines(True), '/dev/null', 'b/' + relative.as_posix()))
    (ROOT / 'rom/metamorphosis.patch').write_text(''.join(patch), newline='\n')
