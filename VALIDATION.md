# Triple essence EVs — September 25, 2026

Protocol 6 triples every native EV component when essence is applied or removed. The 255-per-stat / 510-total caps and the 100-EV artwork threshold are unchanged. One Pidgey gives 3 Speed; Pikachu gives 6 Speed; Charizard gives 9 Special Attack; Butterfree gives 6 Special Attack + 3 Special Defense. Whole essence packages must fit; the first reachable artwork total is 102 EVs.

- ROM SHA-256: `f91e1334623afd7c461cf206ee846b4a15609f904fe98174d32b3eff8bea77bd`. IPS round-trip matches the 16 MiB ROM exactly. Memory remains 261,892 bytes EWRAM, a 108 KiB heap and a 4,844-byte bridge.
- **35 automated tests pass**, including legacy 1x history replay, one-time refund migration, full old 255-EV builds, 3x split yields, stat/total caps, 99→102→99 threshold transitions, refunds and historical branch isolation. New protocol handshake prevents using the old managed companion with this ROM.
- Existing 1x builds are refunded once, retaining every earned essence in that individual's bank and clearing applied EVs. Migration is a durable kind-8 history event and saved per-Pokémon marker `0x4D46`. New transactions carry an explicit 3x rules marker. Old history is interpreted with its original multiplier, so valid old builds do not become invalid retroactively.
- The compiled emulator fixture seeded an old applied build and marker, verified all ten essence refunded exactly once, then applied one Pidgey for 3 Speed EVs and all ten for 30. Removing all ten cleared the EVs and restored the bank; reapplying restored 30 Speed EVs. It also verified the real yield function for 3-, 6-, 9- and split-yield packages, cancel behavior, party-menu entry/return, the generation animation, and both sprite rendering paths.

Evidence: [compiled emulator result](build/triple-tests/emulator/result.json), [ten essence selected for 30 EVs](build/triple-tests/emulator/ten-selected.png). Testing used a disposable ROM/save and separate database, with real companion commands transported through GDB. It did not load or edit the user's save. Lua transport is separately covered with mocked endpoints; no full protocol-6 live Lua/GPU playthrough is claimed. No new AI artwork was needed for this arithmetic change. Previous galleries retain their historical 1x quantities.

The matching bundle is staged in `build/pending-update/`; the launcher installs it and backs up the previous bundle/save/history after mGBA closes. Existing higher-EV artwork resets to canonical when the refunded build drops below 100 EVs, and new art is requested after a new qualifying essence confirmation.

Earlier validation follows.

---

# Essence editing and appearance threshold — September 25, 2026

Protocol 5 update, staged under `build/pending-update/` for the next launcher run. The previous normal save and active ROM remain untouched during testing.

- Built ROM SHA-256: `d98580c20174e39ebf02d3ffd2bf4663eaf64039f84dd96376c42c2784c74392`. New IPS reconstructs that 16 MiB ROM exactly from the verified baseline. EWRAM: 261,892 / 262,144 bytes; heap: 108 KiB; bridge: 4,844 bytes; menu mailbox: 84 bytes.
- **32 automated tests pass.** New coverage includes refunds, full-cap swaps with zero net essence quantity, preserved historical branches, 99→100→99 EV appearance transitions, reapplication from the refunded bank, per-individual canonical asset IDs, progress responses and stale/closed menu protection.
- Below 100 applied essence EVs, export copies the canonical front/back and bypasses the AI subprocess. At 100 EVs the anatomical generator becomes eligible. Both normal and shiny canonical pairs encode successfully for all 411 catalog entries; this does not establish all-species in-game visual fidelity.

## Why the old save looked unchanged

The companion's last recorded client cache contained the latest Bulbasaur asset `4980d58d`. Its recipe held 35 EVs (94.85% base influence). The complete 4,128-byte exports at **12, 20 and 35 EVs are identical**, including both views and palette; the 7-EV export differs. Different recipe/job IDs therefore did not guarantee new visible pixels. [Historical sprite comparison](build/refund-tests/your-bulbasaur-history.png). This update skips generation for all of those low-EV recipes and restores the original species artwork.

## Compiled game verification

The isolated emulator fixture created a fresh save, separate database and disposable Pokémon. It verified deferred battle EVs, cancel, partial application, refunding all applied essence to the bank, reapplying it without new defeats, migration running only once, and entering/returning through the ordinary party menu. The generation bar changed position in actual BG0 VRAM captures: [animation](build/refund-tests/emulator/generating.gif).

It then replayed the user's distinct 7- and 35-EV Bulbasaur pairs on a disposable clone. The actual summary front and visible player battle back **both changed**, and their OBJ VRAM matched each delivered payload byte for byte. These below-threshold historical pairs were deliberately injected to test rendering independently of the new threshold. The user's original save was never loaded or changed. [Machine-readable result](build/refund-tests/emulator/result.json).

The fixture transports real companion EVENT/MENU commands via GDB, not Lua TCP. The actual Lua bridge is separately tested under Lua with mocked memory/socket endpoints. A complete protocol-5 Lua-network-to-GPU-to-battle run has not been repeated. The completion label checks both backend readiness and the matching resident asset ID; the emulator animation test supplies a controlled running status.

## Five visual examples

[Gallery](build/ev-gallery/gallery.png), [recipes and cache paths](build/ev-gallery/recipes.json). The 5-EV Bulbasaur is original artwork. The 100-EV Charmander, 180-EV Squirtle, 340-EV Pikachu and 510-EV Gengar are real local DreamShaper 8 outputs from this task, using canonical-front conditioning followed by generated-front-conditioned back generation. Exports were visually inspected. The 100-EV pair took about 73 seconds; higher-EV pairs were reused from this task's first gallery pass. Some donor traits are weak or omitted, and the resulting proportions remain stylized; weights are design influence, not exact pixel fractions.

The earlier validation below is historical.

---

# Essence update validation — September 25, 2026

This section describes protocol 4; the older evidence below is historical.

- Built ROM SHA-256: `84e7a93a2e9a7d8d02b7d9ce037a3da3aec4fc11a13c8f8cbc9ba5f06405c79a` (16 MiB), staged with its matching Lua/IPS/manifest/symbols in `build/pending-update/`.
- 28 automated tests pass. Coverage includes EV-weighted shares, stat/total caps, whole-yield refusal, available stock, cancel/unfinished transactions, duplicate acknowledgments, individual isolation, branched histories, frozen artwork after leveling/evolution, canonical-front conditioning, generated-front-to-back conditioning, pixel exports, Lua menu response handling, and save/history backups including committed SQLite WAL data.
- Both the active and new IPS patches reconstruct their ROMs exactly from the verified baseline. Protocol 4 uses 261,868 / 262,144 EWRAM bytes and a 108 KiB heap. The additional menu state is heap allocated only while open.

## Compiled game acceptance check

`scripts/essence_smoke.py` launched a fresh disposable mGBA 0.10.5 process with an empty party and a separate history database. It called actual compiled ROM functions and injected game key presses at main-loop boundaries. The original game save was not loaded or modified.

1. Created level 20 Pikachu; seeded old EVs; verified automatic migration reset them while preserving level, four moves and six IVs.
2. Recorded ten Pidgey defeats. Calling the real `MonGainEVs` no longer granted EVs.
3. Loaded the menu using real companion inventory replies. Selected ten, canceled, and verified zero EVs and zero spend commits.
4. Selected one and confirmed: 1 Speed EV, one spent essence, nine available.
5. Reopened and confirmed the remaining nine: 10 Speed EVs total. Repeated migration calls did not reset committed EVs.
6. Opened the ordinary field party menu, selected the new Metamorphosis action, and returned successfully to the party screen with temporary menu memory released.

Evidence: [machine-readable result](build/essence-tests/emulator/result.json), [selection screen](build/essence-tests/emulator/ten-selected.png), and [confirmation screen](build/essence-tests/emulator/confirmation.png). Images decode the actual emulator BG0 VRAM, not UI mockups; they do not include other backgrounds or sprites. The fixture uses GDB to deliver real companion commands/ACKs, rather than mGBA's Lua TCP transport. The unmodified Lua bridge is separately executed under Lua with mocked memory/socket endpoints for paging, cancellation, stale request IDs and error responses. A full live Lua-network-to-GPU-to-battle run has not been repeated for protocol 4.

## Actual GPU generation

The local DreamShaper backend generated a level 20 Pikachu recipe with ten spent Pidgey essences (10 Speed EVs, 98.529% base, 1.471% donor). The front call used the canonical base front reference; the back call used that accepted generated front. Both completed and exported valid shared-palette 64×64 sprites. Reference canvases, masks, raw contexts and logs are retained under `runtime/sprites/0a274f8edd7c59cdcdbc6b0c394ecd8a8660f808556f90f0be48369a5b715596/`; [recipe record](build/essence-tests/pikachu-example.json).

The implementation is ready for playtesting, not an all-game compatibility claim. Extended battles, many-species inventories, real emulator save-state rollback, PC/Day Care migration edge cases, long histories and all-species visual fidelity still need broader testing. Generation can omit or alter features despite references. Automatic evolution mechanics persist; accepted custom artwork changes only after an essence commit. Before the first commit the sprite is canonical.

## Historical validation

# Prototype validation — September 23, 2026

This is a working experimental vertical slice, not a completed full-game compatibility release.

## Build and automated checks

- Upstream: `pret/pokefirered` revision `c75f352304d529f6ba92d4f74b9cf8b5c3810788`.
- The unmodified build matched FireRed's expected SHA-1: `41cb23d8dccc8ebd7c649cd8fbb58eeace6e2fdc`.
- Shipping protocol 3 ROM SHA-256: `f9d4922861c743031b1b88a12c161b1141c4ad7a54851e61e5b650471a51ec31`.
- Nine automated tests pass (`scripts/test.ps1`): weighting examples and invariants, lineage handling, history replay/rollback/branching, idempotent generation requests, initial appearance policy, sprite encoding/transparency, all 411 catalog references, IPS record edge cases, and exact reconstruction of the actual 16 MiB patched ROM.
- Build uses 261,804 of 262,144 EWRAM bytes, including a 108 KiB heap. Three sprite banks occupy ROM space and are patched only in emulator memory. Earlier RAM-payload designs failed battle allocation checks and were replaced.

## Actual emulator acceptance test

Tested with mGBA 0.10.5 and the shipping protocol 3 Lua bridge. A disposable C fixture created a level 6 Charmander and a wild level 5 Pidgey. The fixture seeded three historical Pidgey defeats and placed Charmander one experience point below level 7 using the game's own `SetMonData` function. Normal battle code handled the subsequent fight, experience award, and level-up.

1. The companion delivered the existing level 6 AI image through Lua's ROM-bank upload path. The rendered player back-sprite OBJ VRAM matched the generated payload byte for byte.
2. Charmander defeated Pidgey through ordinary attacks and reached level 7. The companion recorded four total Pidgey defeats and automatically queued the level 7 job, with 93.3348% lineage and 6.6652% Pidgey recipe weights.
3. Free local Stable Diffusion generated the next pair. The companion delivered it automatically. After the level-up message was dismissed, the game refreshed the displayed back sprite; OBJ VRAM again matched the new AI payload byte for byte.
4. The six emitted events were all acknowledged (`write=6`, `read=6`); the sprite cache advanced to epoch 3. The ROM file's SHA-256 remained unchanged by runtime uploads.

Evidence: `build/live-bridge-check.txt`, `build/live-level-check.txt`, `build/live-level-render.txt`, `build/in-game-ai-battle.png`, and `build/in-game-ai-level7.png`. A separate earlier rendering check also verified the summary front sprite against its payload; that check preceded the protocol 3 storage change and has not been repeated on this final build.

Developer reproduction: create the isolated battle fixture with `scripts/make_emulator_smoke.py --battle`; launch a fresh, empty-party emulator with its GDB server (`-g`); run `scripts/gdb_smoke.py`; generate `scripts/make_live_battle_check.py` and load `build/live-bridge-check.lua` in its scripting console. These fixtures change test RAM and must never be run against a real save. The live helper provides a three-minute window and pauses on the level-up stat panel. The completed test used an equivalent continuation script after the original 30-second input window proved too short.

## AI and access findings

No OpenAI API credential was configured, so account-specific API/model entitlement could not be verified. No paid provider was used. Stable Diffusion 1.5 runs through stable-diffusion.cpp Vulkan on this computer's RTX 4070 Laptop GPU. Example pairs took roughly a minute including model startup; the final level 7 sampling/decoding phase reported 34.33 seconds, excluding startup and export.

The generated images and provider metadata are retained under `runtime/sprites/`. `build/ai-examples.png` compares the two requested weight examples. Percentage arithmetic is exact; semantic anatomy and donor visibility are approximate. The high-influence example still favors the lineage silhouette more strongly than its numerical weight suggests. A trained adapter or a better image model would be the next art-quality improvement.

## Implemented but not fully playtested

Rare Candy, Day Care, evolution presentation/side effects, PC portraits, double battles, switching, Transform/Substitute, shiny handling, long histories, full-game heap pressure, disconnect recovery, and actual emulator save-state rollback need broader acceptance testing. Python history branching tests do not establish emulator rollback correctness. Ordinary PID/OT clones, link trades, imported saves, and cross-computer sidecar migration are not supported release workflows. Bootstrap scripts have not been repeated on a clean second computer.

The companion must remain running. AI work is asynchronous: gameplay uses the previous accepted artwork while generation is pending, and a busy battle controller can defer the visual refresh until its current dialogue/action completes. Keep the game saves, SQLite history, and sprite cache together.

## Anatomical renderer update

The current generator replaces the donor-pixel collage with 386 hand-authored species profiles, covering all 411 ROM catalog entries through explicit Unown aliases. An anatomical compiler reserves a lineage signature, gives substantial donors a trait-selection opportunity, resolves conflicting attachment regions, and creates a connected geometric sketch. The image prompts contain anatomical descriptions rather than donor Pokémon names or numerical percentages. Continuous palette/shape parameters and a fixed individual seed provide partial continuity; feature thresholds can still cause visible transitions.

The default local checkpoint is DreamShaper 8, revision `228d79cb20811466f5c5710aa91f05dabd0b8a14`, file SHA-256 `879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd`. Installation verified that hash. The previous SD1.5 file and historical sprite cache remain intact.

Seventeen tests now pass. Added checks cover complete trait lookup, attachment conflict resolution, low-weight contributors, no species names in prompts, removal of facial instructions from rear prompts, absence of donor-pixel access, content-sensitive cache keys, separate-view process invocation, atomic payload publication after successful generation, rejection of clipped/background-filled images, outdated pending/failed job handling, and avoiding regeneration of a Pokémon's entire history after an art-engine update.

Actual GPU generation compared text-only conditioning, paired sketches, and separately prompted views. The original SD1.5 examples were crude; text-only results often ignored the requested anatomy or background. DreamShaper with separate sketch-conditioned views gave the most useful results tested. Three final pairs—level 14 Bulbasaur line, level 34 Squirtle line, and level 80 Gengar—took about 20–22 seconds each. All three pairs also passed the final border/background validation. Evidence and raw outputs are in `build/anatomy-final/`; the before/after image uses the original and new Gengar exports at equal pixel scale.

The live companion was restarted with the new renderer. A POLL request for the existing disposable acceptance campaign's level 7 Charmander automatically queued one current appearance. The worker generated it with the real GPU backend; protocol 3 returned 4,128 bytes with a valid checksum, correct species/level, and correct suppression after the client acknowledged its asset ID. Evidence: `build/anatomy-tests/live-service-result.json`. The ROM and Lua bridge were not modified. A new in-emulator visual rendering check was not repeated for this art-only update.

The new images remove the superimposed-creature effect, but are not finished production artwork. The model still sometimes interprets ears as horns, omits features, changes wing shape between views, or invents details. There is no semantic anatomy validator, ControlNet, Pokémon adapter, or previous-image feedback loop. Native multi-headed/armed forms, canonical shiny palettes, and all-species visual fidelity remain unvalidated. The trait catalog is a reviewable artistic starting point rather than an authoritative anatomical database.

## Pixel-art refinement

Anatomical renderer version 8 adds pixel-art styling after the anatomical description. Exporter version 4 replaces nearest source-pixel sampling with area sampling, removes detached one/two-pixel debris, adds a one-pixel cardinal contour at native resolution, and reserves dark ink in the shared palette. Output remains 64×64 per view, binary transparency, at most 15 shared visible colors, and exactly 4,128 bytes. No donor pixels are overlaid. The dashboard displays sprites at integer scales.

Nineteen automated tests pass. The additional tests verify preservation of a connected one-pixel appendage, removal of isolated debris, contour width, deterministic encoding, binary alpha, frame margins, shared palette limits, and the reserved RGB555 ink color. Existing history, weighting, orchestration, cache, and protocol checks still pass.

Three fresh local DreamShaper pairs were generated with the same recipes and individual seeds as the previous examples. Each pair took about 21 seconds. Visually inspected outputs are in `build/pixel-art-final/`. The comparison script also re-exports the exact previous raw images, isolating the deterministic export changes from prompt-induced design variation. An earlier more forceful style prompt made the turtle too mechanical; that experimental output is retained in `build/pixel-art-v1/` but is not the active prompt. The final examples have clearer contours, though attached ground-shadow remnants and front/back differences remain visible. This process does not guarantee hand-crafted FireRed style.

The companion was restarted with the final renderer. A real TCP POLL against the existing disposable acceptance fixture generated and delivered the new level-7 asset `a2195b54`, with 4,128 bytes, checksum `197bcb28`, and correct known-asset suppression. Evidence: `build/pixel-art-final/live-service-result.json`; reproduction: `python -m scripts.check_pixel_service` with the existing fixture. ROM SHA-256 remains `f9d4922861c743031b1b88a12c161b1141c4ad7a54851e61e5b650471a51ec31`. No new in-emulator visual check was performed for this renderer-only update.

## Back-sprite report and reference-guided views (September 24)

The playtester's saved level 6–8 Bulbasaur backs had different PNG/raw hashes but almost unchanged silhouettes, while the independently generated fronts varied substantially. This establishes a generation-consistency problem, but does not by itself prove which pixels were displayed in that particular battle.

Code inspection also found a refresh race: `RefreshBattle` skipped a hidden/unallocated player sprite and returned success, causing `sRefreshPending` to clear. The fix defers completion for a living player with a cached asset until its sprite is usable. Fainted, absent, transformed and substituted battlers remain excluded as appropriate. A host-compiled test executes the actual C function against hidden-then-visible send-out, active-controller, missing-sprite, double-battle and fainted states. This is a controlled unit test of the real function, not a new full emulator battle acceptance run.

The patched ROM compiles successfully with unchanged bridge/bank addresses and protocol 3. Its SHA-256 is `6bc9dabdac54afb0961c7f896de0424b3011526a6fd9a5eb8766fdf724575424`. The staged IPS reconstructs that ROM exactly from the baseline. `build/pending-update/` holds the matched bundle; the running ROM was left untouched. Launcher promotion validates the ROM hash and Lua addresses, backs up the previous build, refuses to run while mGBA is open, and preserves the existing save. The game must be saved normally and restarted to activate the ROM fix; old-build save states should not be restored into the new build.

Anatomical renderer version 10 corrects short-ear sizing, supplies a low quadruped pose, and draws a closed back bulb instead of a flower stalk. The default front pass is followed by a masked 1024×512 pass with the actual front as left-hand visual context and the rear guide on the right. Only the right half is accepted; the original front is preserved. Both strengths are 0.46. This is contextual inpainting using the existing DreamShaper model, not a trained identity adapter. Native complex multi-headed/armed species retain separate text-conditioned views. Coherence is improved in the reviewed examples but not guaranteed; e.g. small ears, bulb shape and facial details can still differ or be lost during palette reduction.

Twenty-three tests pass, including the C timing test, reference-mask/front-preservation checks, emulator-cache reporting, update checksum/address validation, and save/previous-build preservation. Three real GPU pairs were reviewed: the playtester's level-8 Bulbasaur and the existing level-34 turtle/level-80 Gengar examples. Generation takes approximately 45–60 seconds per pair, with no extra model download or API fee. Evidence: `build/back-sprite-investigation/comparison.png`, `provenance.json`, and `build-check.json`.

The revised companion was restarted. The real connected Lua bridge reported the new level-8 asset `3491638b` in its accepted ROM cache; the dashboard now distinguishes that from a merely completed generation. This confirms delivery into the running emulator, not a direct comparison of battle VRAM. The native UI diagnostic input could not be completed, and no read-only render probe was installed. The staged ROM timing fix still needs a post-restart battle playtest.
