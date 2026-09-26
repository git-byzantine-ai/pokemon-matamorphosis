#include "global.h"
#include "gflib.h"
#include "metamorphosis.h"
#include "battle.h"
#include "battle_anim.h"
#include "battle_controllers.h"
#include "battle_interface.h"
#include "constants/battle.h"
#include "constants/species.h"

EWRAM_DATA struct MetaBridge gMetaBridge = {0};
/* The emulator patches an inactive ROM bank. The cartridge CPU only reads it.
 * Volatile prevents the compiler folding the initially empty bank contents. */
__attribute__((section(".rodata"))) volatile const struct MetaAsset gMetaAssetBanks[META_BANKS] = {{0}};
static EWRAM_DATA bool8 sRefreshPending = FALSE;

STATIC_ASSERT(sizeof(struct MetaCheckpoint) == 32, MetaCheckpointSize);
STATIC_ASSERT(sizeof(struct MetaEvent) == 36, MetaEventSize);
STATIC_ASSERT(sizeof(struct MetaIdentity) == 12, MetaIdentitySize);
STATIC_ASSERT(sizeof(struct MetaAsset) == 4148, MetaAssetSize);
STATIC_ASSERT(sizeof(struct MetaMenuBridge) == 84, MetaMenuBridgeSize);
STATIC_ASSERT(sizeof(struct MetaEssenceRow) == 6, MetaEssenceRowSize);

/* BoxPokemon.unknown is an unused, saved header word. The structure size and
 * secure checksum layout stay unchanged. This marker prevents repeated EV
 * migration on withdrawal, reload or a later menu visit. */
void Meta_EnsureEVs(struct Pokemon *mon)
{
    u8 i, zero = 0;
    if (mon->box.unknown == 0x4D46 || GetMonData(mon, MON_DATA_IS_EGG)
     || GetMonData(mon, MON_DATA_SPECIES) == SPECIES_NONE)
        return;
    if (mon->box.unknown == 0x4D45)
    {
        /* Return legacy applied essence to its bank before adopting 3x yields.
         * A full queue must retry later without changing the saved marker. */
        if (gMetaBridge.write - gMetaBridge.read >= META_EVENTS)
            return;
        Meta_Record(mon, 8, 0, META_ESSENCE_MULTIPLIER);
    }
    for (i = 0; i < NUM_STATS; i++)
        SetMonData(mon, MON_DATA_HP_EV + i, &zero);
    mon->box.unknown = 0x4D46;
    CalculateMonStats(mon);
}

u8 Meta_EssenceYield(u16 species, u8 stat)
{
    switch (stat)
    {
    case STAT_HP: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_HP;
    case STAT_ATK: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_Attack;
    case STAT_DEF: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_Defense;
    case STAT_SPEED: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_Speed;
    case STAT_SPATK: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_SpAttack;
    case STAT_SPDEF: return META_ESSENCE_MULTIPLIER * gSpeciesInfo[species].evYield_SpDefense;
    }
    return 0;
}

static struct MetaCheckpoint *Checkpoint(void)
{
    return (struct MetaCheckpoint *)gSaveBlock2Ptr->filler_B20;
}

static u32 Hash(const void *data, u32 size, u32 seed)
{
    const u8 *bytes = data;
    while (size--)
        seed = (seed ^ *bytes++) * 16777619;
    return seed;
}

static void Identity(struct MetaIdentity *out, struct Pokemon *mon)
{
    out->personality = GetMonData(mon, MON_DATA_PERSONALITY);
    out->otId = GetMonData(mon, MON_DATA_OT_ID);
    out->species = GetMonData(mon, MON_DATA_SPECIES);
    out->level = GetMonData(mon, MON_DATA_LEVEL);
    out->valid = out->species != SPECIES_NONE && !GetMonData(mon, MON_DATA_IS_EGG);
}

void Meta_Record(struct Pokemon *mon, u8 kind, u16 donor, u8 reason)
{
    struct MetaCheckpoint *cp = Checkpoint();
    struct MetaEvent *event;
    u8 payload[20];
    u32 sequence;
    if (GetMonData(mon, MON_DATA_IS_EGG) || GetMonData(mon, MON_DATA_SPECIES) == SPECIES_NONE)
        return;
    if (gMetaBridge.write - gMetaBridge.read >= META_EVENTS)
    {
        gMetaBridge.overflow = 1;
        return;
    }
    sequence = cp->sequence + 1;
    event = &gMetaBridge.events[gMetaBridge.write % META_EVENTS];
    event->sequence = sequence;
    event->parentLo = cp->headLo;
    event->parentHi = cp->headHi;
    event->personality = GetMonData(mon, MON_DATA_PERSONALITY);
    event->otId = GetMonData(mon, MON_DATA_OT_ID);
    event->species = GetMonData(mon, MON_DATA_SPECIES);
    event->donor = donor;
    event->level = GetMonData(mon, MON_DATA_LEVEL);
    event->kind = kind;
    event->reason = reason;
    event->reserved = 0;
    memcpy(payload, &sequence, 4);
    memcpy(payload + 4, &event->personality, 16);
    event->headLo = Hash(payload, 20, cp->headLo ^ 2166136261u);
    event->headHi = Hash(payload, 20, cp->headHi ^ 0x9E3779B9);
    cp->headLo = event->headLo;
    cp->headHi = event->headHi;
    cp->sequence = sequence;
    gMetaBridge.write++;
}

void Meta_Defeat(u8 battler, u8 participants)
{
    u8 i;
    u16 donor;
    if (gBattleTypeFlags & BATTLE_TYPE_POKEDUDE)
        return;
    donor = GetMonData(&gEnemyParty[gBattlerPartyIndexes[battler]], MON_DATA_SPECIES);
    for (i = 0; i < PARTY_SIZE; i++)
        if ((participants & (1 << i)) && GetMonData(&gPlayerParty[i], MON_DATA_HP))
            Meta_Record(&gPlayerParty[i], 1, donor, 0);
}

const struct MetaAsset *Meta_Find(u32 personality, u32 otId)
{
    u8 i, bank;
    for (i = 0; i < META_CACHE; i++)
    {
        bank = gMetaBridge.cache[i].bank;
        if (!bank || bank > META_BANKS)
            continue;
        bank--;
        if (gMetaAssetBanks[bank].valid == META_MAGIC
         && gMetaAssetBanks[bank].assetId == gMetaBridge.cache[i].assetId
         && gMetaAssetBanks[bank].personality == personality
         && gMetaAssetBanks[bank].otId == otId)
            return (const struct MetaAsset *)&gMetaAssetBanks[bank];
    }
    return NULL;
}

bool8 Meta_LoadPic(u32 personality, u32 otId, void *dest, bool8 front)
{
    const struct MetaAsset *asset = Meta_Find(personality, otId);
    u8 i;
    if (asset == NULL)
        return FALSE;
    for (i = 0; i < 4; i++)
        memcpy((u8 *)dest + i * 0x800, asset->data + (front ? 0 : 0x800), 0x800);
    return TRUE;
}

bool8 Meta_Load(struct Pokemon *mon, void *dest, bool8 front, u16 paletteOffset)
{
    const struct MetaAsset *asset;
    u8 i;
    if (GetMonData(mon, MON_DATA_IS_EGG))
        return FALSE;
    asset = Meta_Find(GetMonData(mon, MON_DATA_PERSONALITY), GetMonData(mon, MON_DATA_OT_ID));
    if (asset == NULL)
        return FALSE;
    for (i = 0; i < 4; i++)
        memcpy((u8 *)dest + i * 0x800, asset->data + (front ? 0 : 0x800), 0x800);
    LoadPalette(asset->data + 0x1000, paletteOffset, 32);
    return TRUE;
}

static bool8 RefreshBattle(void)
{
    u8 battler;
    bool8 complete = TRUE;
    struct Pokemon *mon;
    struct Sprite *sprite;
    const struct MetaAsset *asset;
    void *buffer;
    if (!gMain.inBattle)
        return TRUE;
    if (gBattleSpritesDataPtr == NULL || gMonSpritesGfxPtr == NULL
     || gBattleControllerExecFlags || gPaletteFade.active)
        return FALSE;
    for (battler = 0; battler < gBattlersCount; battler++)
    {
        if (GetBattlerSide(battler) != B_SIDE_PLAYER || gAbsentBattlerFlags & (1 << battler)
         || gBattleSpritesDataPtr->battlerData[battler].transformSpecies != SPECIES_NONE
         || gBattleMons[battler].status2 & STATUS2_SUBSTITUTE)
            continue;
        mon = &gPlayerParty[gBattlerPartyIndexes[battler]];
        asset = Meta_Find(GetMonData(mon, MON_DATA_PERSONALITY), GetMonData(mon, MON_DATA_OT_ID));
        if (asset == NULL || !GetMonData(mon, MON_DATA_HP))
            continue;
        /* Delivery can land between decompression and the send-out animation.
         * Keep the refresh pending until the live player's sprite is visible;
         * otherwise that battle retains its previously decompressed artwork. */
        if (gBattlerSpriteIds[battler] >= MAX_SPRITES)
        {
            complete = FALSE;
            continue;
        }
        sprite = &gSprites[gBattlerSpriteIds[battler]];
        if (!sprite->inUse || sprite->invisible)
        {
            complete = FALSE;
            continue;
        }
        buffer = gMonSpritesGfxPtr->sprites[GetBattlerPosition(battler)];
        if (Meta_Load(mon, buffer, FALSE, OBJ_PLTT_ID(battler)))
        {
            LoadPalette(asset->data + 0x1000, BG_PLTT_ID(8) + BG_PLTT_ID(battler), 32);
            RequestSpriteCopy(buffer, (u8 *)(OBJ_VRAM0 + sprite->oam.tileNum * 32), 0x800);
        }
    }
    return complete;
}

bool8 Meta_Tick(void)
{
    struct MetaCheckpoint *cp;
    const struct MetaAsset *incoming;
    u8 i, active, bank;
    if (gSaveBlock2Ptr == NULL)
        return TRUE;
    cp = Checkpoint();
    if (gMetaBridge.magic != META_MAGIC)
    {
        gMetaBridge.magic = META_MAGIC;
        gMetaBridge.version = META_VERSION;
        gMetaBridge.build = META_BUILD;
    }
    gMetaBridge.checkpoint = (u32)cp;
    if (cp->magic != META_MAGIC)
    {
        memset(cp, 0, sizeof(*cp));
        cp->magic = META_MAGIC;
        gMetaBridge.write = gMetaBridge.read = 0;
        for (i = 0; i < META_CACHE; i++)
            gMetaBridge.cache[i].bank = 0;
    }
    for (i = 0; i < PARTY_SIZE; i++)
    {
        Meta_EnsureEVs(&gPlayerParty[i]);
        Identity(&gMetaBridge.party[i], &gPlayerParty[i]);
    }
    if (gMain.inBattle && gBattlersCount)
    {
        for (i = 0; i < PARTY_SIZE; i++)
            gMetaBridge.party[i].valid = FALSE;
        active = 0;
        for (i = 0; i < gBattlersCount && active < META_CACHE; i++)
            if (GetBattlerSide(i) == B_SIDE_PLAYER && !(gAbsentBattlerFlags & (1 << i)))
                Identity(&gMetaBridge.party[active++], &gPlayerParty[gBattlerPartyIndexes[i]]);
    }
    if (gMetaBridge.heartbeat)
        gMetaBridge.heartbeat--;
    if (gMetaBridge.incomingReady && !gPaletteFade.active)
    {
        bank = gMetaBridge.incomingBank;
        if (bank < META_BANKS && gMetaBridge.incomingSlot < META_CACHE)
        {
            incoming = (const struct MetaAsset *)&gMetaAssetBanks[bank];
            if (gMetaAssetBanks[bank].valid == META_MAGIC
             && Hash(incoming->data, META_BYTES, 2166136261u) == gMetaBridge.incomingChecksum)
            {
                gMetaBridge.cache[gMetaBridge.incomingSlot].bank = bank + 1;
                gMetaBridge.cache[gMetaBridge.incomingSlot].assetId = gMetaAssetBanks[bank].assetId;
                gMetaBridge.cacheEpoch++;
                sRefreshPending = TRUE;
            }
        }
        gMetaBridge.incomingReady = 0;
    }
    if (sRefreshPending && !gPaletteFade.active)
    {
        Meta_RefreshPicSprites();
        Meta_RefreshStorage();
        if (RefreshBattle())
            sRefreshPending = FALSE;
    }
    /* All emitted history must reach durable storage before another game callback.
     * A single Day Care callback can produce up to 99 events; the ring holds 128.
     * This also prevents ordinary saves from getting ahead of their sidecar. */
    return gMetaBridge.write == gMetaBridge.read && !gMetaBridge.overflow;
}
