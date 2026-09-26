# FireRed: Gradual Metamorphosis

An experimental FireRed ROM patch, mGBA Lua bridge, and free local Stable Diffusion companion. Metamorphosis is a player-selected action that spends defeated-Pokémon essence and grants EVs. Level-ups no longer generate artwork.

## Windows portable download

Download the **Windows x64 ZIP** from [GitHub Releases](https://github.com/git-byzantine-ai/pokemon-matamorphosis/releases), extract the entire folder, and open `Metamorphosis.exe`. Setup verifies your original English FireRed v1.0 ROM, applies the patch locally, downloads the emulator/runtime/model with checksum checks, detects your graphics devices, and tests real AI generation. Python, Git, Codex and the ROM build toolchain are not required on the player's computer.

Allow at least 4 GB free disk space and roughly 2.2 GB of first-run downloads. A Vulkan GPU is recommended; this alpha has been tested on an RTX 4070 Laptop GPU. At each launch, load the Lua bridge using the path provided by the launcher. Save/history/artwork live together in a separate persistent data folder, so replacing the application ZIP does not erase progress.

See the [player guide](packaging/PLAYER_GUIDE.txt) for setup, saves, controls and troubleshooting, and [portable build instructions](packaging/BUILD.md) for release maintainers. The ZIP contains a patch, not the original ROM or model weights. Existing development-checkout saves are not automatically imported into the portable app.

## Install the triple-EV essence update

1. Save through the **in-game Save menu**, then close mGBA.
2. From this project directory, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\play.ps1
```

3. The launcher installs `build/pending-update/` when its `READY` marker exists. It backs up the previous ROM bundle, normal save, and a consistent history snapshot under `build/previous-builds/`. It also upgrades an older managed companion.
4. Choose **Continue** from the normal save. Do not load a save state from the older ROM. In mGBA, load **Tools → Scripting → File → Load script → build/metamorphosis.lua** once per emulator session.
5. Choose **Start → Pokémon → your Pokémon → Metamorphosis**.

This update refunds previously applied 1x essence to the same Pokémon's bank **once**, clearing its old essence EVs. Reapply it through Metamorphosis to receive triple value. This preserves all collected essence and lets you choose a legal build under the existing caps. Level, moves, IVs, species and identity are retained. Boxed individuals migrate when they join the party. New 3x builds are not reset on later launches. Defeats that were never recorded cannot be reconstructed.

The companion must stay connected. Gameplay waits for durable event acknowledgments; if it pauses after a defeat or confirmation, check the Lua script and [local dashboard](http://127.0.0.1:8766). AI generation itself is asynchronous, retaining the previous accepted artwork until the new pair is ready. Logs are in `runtime/companion.stderr.log`.

## Essence controls and rules

| In-game control | Action | Default keyboard key here |
|---|---|---|
| Up / Down | Choose donor species | Arrow keys |
| Left / Right | Remove / add one essence | Arrow keys |
| L / R | Remove / add up to ten | A / S |
| A | Add one; confirm on the confirmation screen | X |
| Start | Review and apply selection | Enter |
| B | Cancel, return, or go back from confirmation | Z |

The screen shows the proposed EV totals and **USE / OWN** for each donor. USE starts at the amount already applied; OWN includes both applied and unspent essence. Decrease USE to remove essence and its EVs, or increase it to apply essence. Confirm with Start, then A. Removed essence returns to that individual's bank and can be reapplied later. Canceling leaves EVs and essence unchanged. Remove unwanted essence first when swapping at an EV cap.

After confirmation, a moving bar and “Shaping your Pokémon…” show that artwork is pending. “New sprite loaded!” appears only when the matching pair reaches the game's sprite cache. You can press A or B to continue playing during generation. If you stay on the result screen, it updates automatically; reopening the menu opens the essence editor.

Each surviving battle participant earns one essence of the defeated opponent's actual species. Trainer battles count; captures and passive Exp. Share recipients do not add essence. Banking continues beyond EV caps, so excess defeats remain recorded even when they cannot be spent. Level 100 Pokémon can use the menu.

One essence grants **three times** the species' native EV yield from the ROM table. FireRed's limits remain **255 EVs per stat and 510 total**. If any stat or the total would overflow, that whole essence is refused; partial essence is not consumed. Pidgey grants **3 Speed**, Pikachu **6 Speed**, and Charizard **9 Special Attack**. Split yields also triple: Butterfree gives **6 Special Attack and 3 Special Defense**. Removing an essence removes the same tripled EV package. Automatic battle and vitamin EV gains are disabled. Macho Brace and Pokérus do not multiply essence yields. Types, abilities, moves, and ordinary species progression remain.

## Composition algorithm

**Below 100 applied essence EVs, both views use the original sprite and skip AI generation.** At 100 or more, the formula below determines the design. Removing essence below 100 restores the original sprite, including for Pokémon that had custom artwork before this update. Only currently applied essence counts toward this threshold.

Let `n[s]` be the essence of species `s` currently applied to this individual and `y[s]` its total native EV yield:

```text
E = sum(n[s] * 3 * y[s])               # 0 to 510
base_share = 1 - 0.75 * E / 510
species_share[s] = 0.75 * n[s] * 3 * y[s] / 510
```

At zero spent EVs, the recipe is 100% base. At 510 spent EVs, it is 25% base and 75% essence. A native 3-EV species still weighs three times as much as a native 1-EV species: their essence packages now grant 9 and 3 EVs. Level has no effect on the weights. Each stat is checked separately: **85 Pidgey essence fills the 255 Speed cap**. Because all new contributions are multiples of three, the first reachable total above the 100-EV sprite threshold is **102 EVs** (34 Pidgey essence).

| Confirmed essence | EVs | Recipe |
|---|---|---|
| Pikachu + 10 Pidgey | 30 Speed | Original Pikachu sprite (below threshold) |
| Pikachu + 34 Pidgey | 102 Speed | 85% Pikachu, 15% Pidgey |
| Pikachu + 85 Pidgey + 85 Geodude | 255 Speed, 255 Defense | 25% Pikachu, 37.5% Pidgey, 37.5% Geodude |

At or above 100 EVs, the base is the individual's actual species at confirmation. The committed recipe and accepted art stay frozen through later level-ups and evolutions until another confirmation. Below the threshold, ordinary canonical sprites follow the current species. A donor matching the base contributes to that species' combined share.

Weights describe anatomical design influence, not exact percentages of image pixels. Small contributions may be hard to see at 64×64. The numerical base floor is enforced; no semantic image validator guarantees perceptual percentages.

## Image generation

The companion compiles a coherent creature from [386 editable trait profiles](companion/data/traits.tsv), covering all 411 FireRed catalog entries. It resolves incompatible attachment regions, preserves a base signature, and uses continuous palette/body proportions plus compatible donor traits. Donor Pokémon pictures are not superimposed.

The default `reference` pipeline uses two masked 1024×512 DreamShaper 8 calls:

1. **Front:** canonical base front sprite on the protected left half; the anatomical front guide on the editable right. The generated right half becomes the accepted front.
2. **Back:** that accepted generated front on the protected left; the rear guide on the editable right. Only the generated rear half is accepted. The second pass cannot replace the front.

Complex native body plans use canonical guides. Export removes white background, rejects clipping, fits each view to 64×64, removes tiny detached debris, adds a one-pixel contour, and quantizes both views to a shared 15-color palette plus transparency. The 4,128-byte GBA payload contains 2,048 front tiles, 2,048 back tiles and a 32-byte palette. Small party icons remain canonical; large summary/PC portraits and player battle backs use the custom pair.

Weights are at `.tools/models/dreamshaper8.safetensors` (about 2.13 GB). The runtime is `.tools/stable-diffusion/sd-cli.exe`, configured for Vulkan1 (this computer's RTX 4070 Laptop GPU). Each pass loads the model and exits, releasing GPU allocations. Cached pairs require no model execution. There are no API fees or cloud image uploads.

Recipes, reference canvases, masks, prompts, raw images, final front/back PNGs and logs stay in `runtime/sprites/<hash>/`. Keys include the recipe, traits, renderer/export versions, settings and canonical front reference pixels. Failed generation keeps previous art and does not grant EVs again. After fixing an error, run `python scripts/retry-failed.py` to retry artwork.

This backend is experimental: features may be omitted or reinterpreted and front/back details can differ. Canonical shiny palettes and all-species visual fidelity remain unvalidated. `scripts/run-companion.ps1 -Preview` is an explicitly non-AI diagnostic mode; stop an existing companion before changing providers.

The [five-example gallery](build/ev-gallery/README.md) is a historical **1x-yield** comparison: original at 5 EVs, then generated forms at 100, 180, 340 and 510 EVs. Its essence quantities predate triple yields. Recipe changes can produce identical exported pixels; numerical influence does not guarantee a visible change at every confirmation.

## Saves and validation

EVs and the migration marker live in normal Pokémon data. A 32-byte saved checkpoint points to the append-only history in `runtime/history.sqlite3`. Essence transactions record begin, selected quantities, then commit. Incomplete transactions do not spend banked essence. Replay is idempotent; saved history branches do not inherit future defeats or spending.

Back up the game save, history and `runtime/sprites` together. Stop the companion or use SQLite's backup API before copying its database; a live database copied without its WAL may omit recent events. Keep matching ROM/Lua versions together. RAM save states from older ROM builds are unsupported.

See [VALIDATION.md](VALIDATION.md) for evidence and remaining limits. The original source research is in [the design plan](GRADUAL_METAMORPHOSIS_PLAN.md). Link trading/imports, PID/OT clones, long histories and full-game heap stress need broader playtesting. Two individuals' sprites reside in the emulator cache; others stream from desktop storage.

## Build from source on Windows

Use Python 3.10+ with Pillow, PowerShell, network access and several GB of disk space. Scripts prefer the bundled Codex Python when available, otherwise `python` on PATH.

```powershell
./scripts/setup-build.ps1
./scripts/build.ps1 -Baseline
./scripts/build.ps1
./scripts/setup-local-ai.ps1
./scripts/setup-emulator.ps1
./scripts/test.ps1
```

The local MSYS2/agbcc toolchain builds pinned `pret/pokefirered` revision `c75f352304d529f6ba92d4f74b9cf8b5c3810788`. The baseline SHA-1 must be `41cb23d8dccc8ebd7c649cd8fbb58eeace6e2fdc`. A native Windows linker INCLUDE issue is handled by flattening linker scripts without changing their contents/order. MSYS2 package resolution is not a hermetic toolchain lock; a fresh bootstrap has not been repeated on a second computer.

`scripts/patch_rom.py` is the authoritative upstream edit set; `rom/overlay/` holds new C modules and headers. `rom/pokefirered` is a disposable prepared source tree. `rom/metamorphosis.patch` is regenerated for review. `scripts/build.ps1 -OutputDirectory build/essence-update` builds separately from the active game.

The bundle contains `firered-metamorphosis.gba`, an IPS patch, matching `metamorphosis.lua`, `bridge.json`, and ELF-derived `symbols.txt`. Always distribute the matching patch/bridge together; addresses can change after rebuilds.

Protocol 6 uses a 4,844-byte bridge: 128 queued events, two asset references, and an 84-byte menu mailbox containing owned/applied quantities and generation status. The heap retains 108 KiB. Three 4,148-byte banks live in emulator-patched ROM memory; Lua writes an inactive bank and publishes it after checksum verification. The ROM file stays unchanged. Asset IDs prevent stale RAM references from silently selecting another individual's artwork. Original hardware and other emulators are unsupported.

## Sources and ownership

- [pret/pokefirered](https://github.com/pret/pokefirered/tree/c75f352304d529f6ba92d4f74b9cf8b5c3810788): public matching decompilation, not Nintendo's official source release.
- [pret/agbcc](https://github.com/pret/agbcc/tree/da598c1d918402c42c0c0d7128ba14567f3175e9): matching compiler.
- [mGBA 0.10.5](https://github.com/mgba-emu/mgba/releases/tag/0.10.5): emulator and Lua API.
- [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp/releases/tag/master-899-28b454b): local Vulkan runtime.
- [DreamShaper 8](https://huggingface.co/Lykon/DreamShaper/blob/228d79cb20811466f5c5710aa91f05dabd0b8a14/DreamShaper_8_pruned.safetensors): current local model.

Upstream code, assets, tools and models retain their respective ownership and terms. Generated builds/tools/models are excluded from Git. Share source changes and patches rather than bundling the base game.
