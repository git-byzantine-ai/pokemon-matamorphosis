#ifndef GUARD_METAMORPHOSIS_H
#define GUARD_METAMORPHOSIS_H

#include "global.h"
#include "pokemon.h"

#define META_MAGIC 0x4D41544D
#define META_VERSION 6
#define META_ESSENCE_MULTIPLIER 3
#define META_EVENTS 128
#define META_CACHE 2
#define META_BANKS 3
#define META_BYTES 4128
#define META_BUILD 0xC75F3521

struct MetaCheckpoint {
    u32 magic, campaignLo, campaignHi, headLo, headHi, sequence, flags, reserved;
};

struct MetaEvent {
    u32 sequence, parentLo, parentHi, headLo, headHi, personality, otId;
    u16 species, donor;
    u8 level, kind, reason, reserved;
};

struct MetaIdentity {
    u32 personality, otId;
    u16 species;
    u8 level, valid;
};

struct MetaAsset {
    u32 valid, personality, otId;
    u16 species;
    u8 level, reserved;
    u32 assetId;
    u8 data[META_BYTES];
};

struct MetaSlot {
    u32 bank, assetId;
};

struct __attribute__((packed)) MetaEssenceRow { u16 species, available, used; };
struct MetaMenuBridge {
    u32 requestId, status;
    struct MetaIdentity mon;
    u16 offset, total, count, reserved;
    struct MetaEssenceRow rows[8];
    u32 artStatus, artId;
};

struct MetaBridge {
    u32 magic, version, build, checkpoint;
    u32 write, read, overflow, heartbeat;
    u32 incomingReady, incomingSlot, incomingChecksum, cacheEpoch;
    struct MetaIdentity party[6];
    struct MetaIdentity display;
    struct MetaEvent events[META_EVENTS];
    struct MetaSlot cache[META_CACHE];
    u32 incomingBank;
    struct MetaMenuBridge menu;
};

extern struct MetaBridge gMetaBridge;
extern volatile const struct MetaAsset gMetaAssetBanks[META_BANKS];
bool8 Meta_Tick(void);
void Meta_Record(struct Pokemon *mon, u8 kind, u16 donor, u8 reason);
void Meta_Defeat(u8 battler, u8 participants);
const struct MetaAsset *Meta_Find(u32 personality, u32 otId);
bool8 Meta_Load(struct Pokemon *mon, void *dest, bool8 front, u16 paletteOffset);
bool8 Meta_LoadPic(u32 personality, u32 otId, void *dest, bool8 front);
void Meta_RefreshPicSprites(void);
void Meta_RefreshStorage(void);
void Meta_EnsureEVs(struct Pokemon *mon);
u8 Meta_EssenceYield(u16 species, u8 stat);
void Meta_OpenEssenceMenu(u8 slot, void (*returnCallback)(void));

#endif
