# Base timelapse

Renders the recorded history of a Palworld base as a video: every piece
appearing over time, on real extracted terrain, under the save's own in-game
clock, with the players and Pals the save actually recorded.

It works by driving the normal MapPal scene in Chrome. `tools/timelapse/timelapse.mjs`
launches Chrome against a running vite dev server, calls dev-only hooks on
`window.__mappalCam` to set the scene's contents once per frame, screenshots,
and hands the PNGs to ffmpeg. Nothing in the editor UI changes: every layer this
feature adds draws nothing until those hooks populate its store.

---

## Contents

- [What is real and what is a rendering choice](#what-is-real-and-what-is-a-rendering-choice)
- [What is NOT in this repository](#what-is-not-in-this-repository)
- [The pipeline, end to end](#the-pipeline-end-to-end)
- [Regenerating the assets](#regenerating-the-assets)
- [Running a render](#running-a-render)
- [Environment knobs](#environment-knobs)
- [Findings worth keeping](#findings-worth-keeping)
- [Verification tools](#verification-tools)

---

## What is real and what is a rendering choice

This is the project's standing rule and it is enforced in the code comments at
every boundary. Do not soften it, and never present the second group as recorded
fact.

**Real recorded data — straight out of the save:**

| | |
|---|---|
| Who built each piece | every map object carries `build_player_uid` |
| Player appearance | `PlayerCharacterMakeData` per snapshot: body/head/hair mesh names, equipment, and the `LinearColor` tints |
| Equipped items | from the players' own containers |
| In-game clock | `GameDateTimeTicks` per snapshot |
| All geometry | extracted from the game's own cooked assets |
| Pal positions | `LastJumpedLocation` per Pal per snapshot |
| Player positions | `SaveData.LastTransform` in `Players/<UID>.sav` |

**Rendering choices — labelled as such everywhere they appear:**

| | |
|---|---|
| Where the *builder avatar* stands | Palworld records no per-piece build position. The avatar is placed beside the piece it is credited with. `PlayerLayer`'s separate `players` layer is the honest one: it draws players at their actually-recorded `LastTransform`. The two are kept deliberately apart. |
| Build **order** | The save has no placement timestamps. Pieces that share a first-seen snapshot are ordered by `buildorder.js`, which reconstructs a plausible sequence from the build lattice (support DAG + walking-builder greedy cost). Plausible, not recorded. |
| Demolition attribution | The save records no destruction at all. `demolitions.py` *infers* a demolition by pairing a vanished piece with one that appeared in substantially the same volume within 2 snapshots (AABB IoU ≥ 0.30), and credits the replacement's builder. Inferred. |
| `BUILDOUT_HOUR` | The in-game hour held during the reconstructed build-out phase. Stylistic. |
| Avatar scale | The avatar mesh is the game's own at its real 1.47 m, which is ~13 px at the framing this renders at. It is scaled up for legibility — a stated choice, not a claim about anyone's size. |

One nuance that must not be flattened: `LastTransform` *is* populated in every
snapshot held (verified by decoding the raw `.sav` files, not inferred), but it is
a **snapshot-granularity last-known/logout position**. It says where the save last
put that player — not where they were standing when any one piece went down.

---

## What is NOT in this repository

**No game assets.** The extracted Palworld meshes and textures are Pocketpair's
copyrighted content. This repository ships the **extractors**, never the
**extractions**. Everything under these paths is a build output, generated
locally from your own copy of the game, and is deliberately absent:

```
public/meshes/                       ~147 MB   build-piece meshes
public/union/                        ~45 MB    per-base merged save data
public/terrain_meshes/               ~90 MB    ground, props, foliage
public/pal_meshes/  public/player_meshes/
public/equipment_meshes[_posed][_standing]/
```

Also absent, and for the same or adjacent reasons: `Mappings.usmap` (derived from
the game), any `.sav` files, rendered frames and videos, and the CUE4Parse clone
the extractors build against.

Do not commit any of them. See [Regenerating the assets](#regenerating-the-assets).

---

## The pipeline, end to end

Everything runs out of a **work directory** — call it `$WORK` — that holds the
intermediate JSON and a MapPal checkout at `$WORK/mappal`. Every script honours
`PALTL_WORK`; it defaults to the current directory.

```
export PALTL_WORK=/path/to/work        # holds mappal/ + intermediate JSON
export PALTL_REPO=~/Palworld           # git repo of save-history snapshots (git-LFS)
export PALX_PAKS=".../Palworld/Pal/Content/Paks"
export PALX_BASE="$PALTL_WORK"         # where the extractors read Mappings.usmap
```

The chain is **order-sensitive**. Each stage consumes the previous stage's output.

### 1 — Save history → per-base unions and indices

| Script | Reads | Writes |
|---|---|---|
| `build_union.py $WORK` | every `Level.sav` held (NAS backups + ~40 sampled git snapshots; optionally `PALTL_LIVE_SAVE`) | `mappal/public/union/union_<base>.json` |
| `build_index.py <commits> <out>` | git-LFS history of `world/current/Level.sav` | `build_index.json` — per object: type, position, first/last snapshot |
| `extract_gametime.py` | same history | `gametime_index.json` — `ts → (real ticks, game ticks)` |
| `pal_index.py` | same history + NAS sets | `pal_index.json` — per Pal: level, gender, nick, base, position track |
| `player_index.py` | `Players/<UID>.sav` per snapshot | `player_index.json` |
| `resolve_players.py` | `player_index.json` + the game's character-creation data table | `player_parts.json` |
| `eol_scan.py` | same history | `eol_scan.json` — per-snapshot base-camp census |
| `paint_index.py` | same history | `paint_index.json` — when each object got painted |

`build_index.py` imports `basecamp_attrib.py` (base-camp attribution) and `ooz`
(`ooz.py` + `oozshim.py`, the Oodle-Kraken decompressor for this world's
`b'PlM'`-magic saves). `JOBS` sets `pal_index.py`'s pool size (default 3).

### 2 — Indices → the per-base files the renderer loads

All of these write into `mappal/public/union/`:

| Script | Writes |
|---|---|
| `build_actor_scenes.py` | `pals_<b>.json`, `players_<b>.json`, `builders_<b>.json` |
| `build_avatars.py` | `avatars.json` — per-UID appearance runs |
| `build_names.py` | folds real player names from the guild rosters into `avatars.json` |
| `build_wildpals.py` | `wildpals_<b>.json` — wild spawn points near each base |
| `build_wildpals_draw.py` | `wildpals_draw_<b>.json` — the one weighted group the game would actually roll, day and night |
| `build_terrain.py <base8> [radius_cm]` | `terrain_<b>.json` + `public/terrain_meshes/*.glb` |
| `demolitions.py` | `demolitions_<b>.json` (inferred — see above) |
| `build_endoflife.py` | `endoflife_<b>.json` — when each camp's record last existed |
| `build_posed_sockets.py` | `equipment_sockets_posed.json` |
| `build_override_meshes.py` | `equipment_override_meshes.json` |

`build_wildpals_draw.py` is fully deterministic — no RNG, no wall clock. It
derives every roll from `sha256("<spawnerId>|<phase>|…")`, so two runs produce
identical output.

### 3 — Meshes and registries

| Script | Purpose |
|---|---|
| `build_manifest.py` / `build_pal_manifest.py` | build the extraction target lists (`mesh_manifest.json`, `pal_manifest.json`) |
| `build_meshdims.py` | fold measured AABBs from `palxbb` into the manifest, closing MapPal's grey-box gap |
| `gen_registry.py` | emit `src/data/meshRegistry.json` — type → mesh → URL |
| `build_char_xform.py` | emit `src/data/palXform.json` — the `CharacterMesh` component transform each species' own blueprint gives its skeletal mesh |
| `build_water_index.py` | `water_index.json` — every water surface the game authors |

`src/data/meshRegistry.json`, `meshXform.json` and `palXform.json` **are**
committed: they are metadata (asset names, offsets, dimensions), not geometry.

### 4 — Render and encode

```
tools/timelapse/timelapse.mjs   →  $WORK/frames/<base>/f_%04d.png
tools/timelapse/encode.sh       →  $WORK/video/<base>.mp4
```

---

## Regenerating the assets

The extractors are in `tools/palworld-extract/`. They are CUE4Parse-based .NET
console apps, and — this is the notable part — **they run on macOS against the
normal game install. No Windows, no UE editor, no third-party GUI tool.**

### Prerequisites

1. **.NET 10 SDK.**
2. **CUE4Parse**, cloned as a sibling of the tool projects (the `.csproj` files
   reference `../cue4parse/`):
   ```bash
   cd tools/palworld-extract
   git clone --recursive https://github.com/FabianFG/CUE4Parse.git cue4parse
   cd cue4parse && git checkout 83200c6      # the revision these were built against
   ```
3. **`Mappings.usmap`** for your Palworld version, placed at `$PALX_BASE/Mappings.usmap`
   (or pointed at by `PALX_USMAP`). **This is mandatory** — see the findings below.

### Building

```bash
export PALX_BASE=/path/to/work
export PALX_PAKS=".../steamapps/common/Palworld/Pal/Content/Paks"
dotnet build -c Release -p:CUE4PARSE_SKIP_NATIVE=true tools/palworld-extract/palxtex
```

`-p:CUE4PARSE_SKIP_NATIVE=true` skips CUE4Parse's native ACL build, which does
not compile on macOS and **is not needed**: Palworld's player animations are
`FUECompressedAnimData`, which CUE4Parse decodes in pure C#.

If the paks sit on an SMB/NFS mount, also export
`DOTNET_SYSTEM_IO_DISABLEFILELOCKING=1` or the provider will fail to open them.

### The tools

| Project | What it extracts |
|---|---|
| `palx` | batch mesh → GLB from a JSON target list; original World-Partition cell reader |
| `palxtex` | textured meshes: GLB with UVs, per-section materials, decoded base-colour textures; plus blueprint/datatable resolution and animation pose baking (`Pose.cs`) |
| `palxground` | the current World-Partition cell / landscape reader — terrain heightfields, foliage instances, raw pak dumps |
| `palxwater` | rivers, ocean and waterfalls: spline-mesh and material params, plus a water-specific textured extractor |
| `palxbb` | a buildable blueprint's true local-space AABB, by unioning each mesh component's transformed LOD0 extents |
| `palxeq` | equipment meshes and skeletons, out of its own asset root so it cannot contend with the others |
| `palspawn` | Pal spawner actors, spawner blueprint CDOs (`SpawnGroupList`) and spawn datatables |

Common environment: `PALX_BASE` (work dir, default cwd), `PALX_PAKS` (required
where a tool mounts the pak), `PALX_USMAP` (default `$PALX_BASE/Mappings.usmap`).
`palxground` and `palxwater` additionally read `PALX_ROOT`, `PALX_OUT`,
`PALX_DUMP`; `palxground` also `LAND_LOD` (default 0), `LAND_NOGLB=1` (index
only, skip GLB writes) and `ALLEXP_OUT`. `palspawn` reads `CLSFILTER` (default
`Spawn`) and `OUTFILE`.

### Poses are baked, not skinned

`palxtex/Pose.cs` evaluates one frame of a shipped `UAnimSequence` and produces
skinning matrices; `Extract.cs`'s `SkinPositions` applies classic linear-blend
skinning on the CPU. **The exported GLBs therefore carry no skin weights**
(`skins=0`, no `JOINTS_0`/`WEIGHTS_0`, no `animations`, one node) — the pose is
baked into vertex positions and normals are recomputed from the posed geometry.
This is deliberate: it keeps the output contract identical to every other mesh
the renderer loads, which only handles flat single-node GLBs.

`Pose.cs` composes with `FMatrix` rather than `FTransform` on purpose — this
skeleton stores thousands of zero-quaternion padding entries that trip
`FTransform`'s normalize assert.

`--posebones` is the complementary path: it writes bone transforms to JSON so
rigid props (helmets, weapons) can be placed on the posed avatar externally,
which is what `build_posed_sockets.py` consumes.

---

## Running a render

1. **Serve MapPal**, with `public/` fully populated *first*:
   ```bash
   npm run dev            # default port 5174
   ```
   Vite builds its `public/` file listing **at startup**. A dev server started
   before the mesh directories were populated serves every texture as the SPA
   HTML fallback, and Pals render as flat grey blobs. If that happens, restart
   the dev server before suspecting the material code.

2. **Render one base:**
   ```bash
   cd tools/timelapse
   PALTL_WORK=/path/to/work node timelapse.mjs <base8> [MINFRAMES=240] [TURNS=1.5]
   ```
   Frames land in `$PALTL_WORK/frames/<base8>/f_%04d.png`, alongside two audit
   files: `plan.json` (one row per frame: phase, snapshot, game day/hour, lit
   hour) and `sig.json` (a plan fingerprint). **If `sig.json` does not match the
   current plan, every `f_*.png` in the directory is deleted** rather than
   splicing frames from two different plans into one video. Matching runs resume
   by skipping frames that already exist.

3. **The full production run:**
   ```bash
   PALTL_WORK=/path/to/work bash final_render_all.sh
   ```
   Sets `PPF=1` (every piece its own frame), `BUILDOUT_HOUR=8`, unsets
   `MAXFRAMES`, opens headed Chrome for acceptance, renders the four recorded
   bases plus the proposed no-Palbox Colosseum smallest-first, then encodes.

4. **Encode only:** `bash encode.sh` → `$PALTL_WORK/video/<base>.mp4`
   (1600x1000, 30 fps, libx264 crf 20, faststart).

Requirements: Node with `puppeteer-core`, a Chrome binary (`CHROME`, defaults to
the macOS path), and `ffmpeg`.

---

## Environment knobs

### `timelapse.mjs`

| Var | Default | Effect |
|---|---|---|
| `PALTL_WORK` | cwd | Work directory; expects `<PALTL_WORK>/mappal` |
| `PORT` | `5174` | vite dev server port |
| `OUTDIR` | `$WORK/frames/<base>` | Frame output directory |
| `CHROME` | macOS Chrome path | Chrome binary |
| `HEADLESS` | off | `1` runs headless |
| `CHROME_PROFILE` | unset | Profile-dir suffix. **Required for concurrent renders** — two Chromes cannot share a profile dir |
| `PPF` | `1` | Pieces revealed per build-out frame. `PRE_FRAMES = max(48, ceil(pieces/PPF))` |
| `MAXFRAMES` | `0` (none) | Total frame budget for a smoke test. **Silently raises `PPF` and re-chunks the build-out** — which is why the production script unsets it |
| `ONLY_FRAMES` | unset | Comma-separated frame indices. The whole plan is still computed, so camera and lighting on a listed frame match a full render |
| `BUILDOUT_HOUR` | held at first snapshot's hour | `0..24` float. In-game hour held through the reconstructed build-out. A stylistic choice — the first snapshots land at 22:24 and 01:11 for two of the bases |
| `DAYNIGHT` | on | `0` disables in-game day/night lighting |
| `GAMEPACE` | on | `0` disables in-game-clock pacing; falls back to uniform |
| `ACTORS` | on | `0` skips Pals, wild Pals, players, builders and terrain — makes a run comparable with pre-Pal renders |
| `STANCE` | `kneel` | `standing` switches the baked animation frame. Moves player **and** equipment meshes together — they must match or armour misaligns |
| `WILDPVP` | off | `1` keeps PvP-arena spawn points in the wild-Pal draw |
| `BUILDORDER` | `buildorder.js` | Path to the injected build-order script; swap in an older revision to A/B the ordering |
| `NOENDING` | unset | Suppresses the end-of-life coda |
| `ENDING_HOLD` | `60` | Frames held on the camp as it last stood |
| `ENDING_GONE` | `90` | Frames held on the same ground in the next save, camp absent |
| `CLOSEUP` | unset | Metres; writes a second screenshot per frame from that distance off the builder avatar. Diagnostic |
| `WHO` | unset | Logs the avatar's name per frame. Diagnostic |
| `AVATAR_SHEET` | unset | `uid@ts` specs; renders an avatar contact sheet instead of a video |

### `build_terrain.py`

Radii are in centimetres.

| Var | Default | Effect |
|---|---|---|
| `GROUND_R` | `60000` (600 m) | Radius for big terrain chunks — cliff, ground, `*_TOP` |
| `PROP_R` | `30000` (300 m) | Radius for everything else placed: rocks, ruins, waterfalls, shoreline. Also gates lights and rivers |
| `FOLIAGE_R` | `30000` | Radius for per-instance trees and bushes |
| `LANDSCAPE_R` | `RADIUS` arg (`30000`) | Landscape-quad clip box |
| `HORIZON_R` | `800000` (8 km) | Far-field HLOD terrain and ocean reach |
| `HORIZON_INNER` | `LANDSCAPE_R` | Inner edge of the far-field ring, avoiding overlap with detailed terrain |
| `OCEAN_R` | `GROUND_R` | Ocean-tile radius. **Tied to `GROUND_R` on purpose** — the sea must not out-reach the land |
| `WATER_R` | `GROUND_R` | Water-body radius |
| `FOLIAGE_CAP` | `3000` | Max decorative foliage instances, nearest-first |
| `GROUND_FOLIAGE_CAP` | `2000` | Separate cap for ground cover — flowers outnumber grass ~40:1 near a base |
| `CELLACTORS` | `$WORK/cellactors_wide.json` | Input cell-actor dump |

Usage: `python3 build_terrain.py --manifest` writes the extraction manifest;
`python3 build_terrain.py <base8> [radius_cm]` writes the per-base terrain.
`python3 build_colosseum.py` regenerates the checked-in design's synthetic
2,775-piece inputs, deliberately omitting both its Palbox and base-camp record.

### Pipeline-wide

| Var | Default | Effect |
|---|---|---|
| `PALTL_WORK` | cwd | Work directory, for every Python script |
| `PALTL_REPO` | `~/Palworld` | Git repo of save-history snapshots |
| `PALTL_LIVE_SAVE` | unset | Optional live-server `Level.sav`, folded into the union |
| `PALTL_SITE_PACKAGES` | unset | Extra `sys.path` entry if `palworld_save_tools` is in a venv |
| `JOBS` | `3` | `pal_index.py` pool size |

---

## Findings worth keeping

These cost days to establish. They are counter-intuitive, and a future reader
will otherwise repeat the dead ends.

### Palworld's ground is placed static meshes, not one Landscape

The ground under three of the four bases is a `LandscapeStreamingProxy` set in
the **`FarMountain_L0`** runtime grid. Earlier sweeps missed it because they
enumerated only grids matching `*Grid*`. The pak actually contains:

```
MainGrid_L0      7085 cells
FarMountain_L0    115 cells      <- the one that matters
Foliage_L0
MainGrid_L15
oilrig_L0
CloseRange_L0
~40 HLOD grids
```

Verified to **0–27 cm** against the game's own foliage and spawner placements
(`terrain_verify.py` does this cross-check: do foliage instances land *on* the
landscape surface?).

### The ocean is an actor in the persistent level

It is a `BP_SimpleWater_C` in `PL_MainWorld5.umap` — the **persistent** level,
not any World Partition cell. 1,681 `PerInstanceSMData` tiles of `S_WaterMesh`,
`bWorldOceanPlane=true`, sea level **Z = −2102.615**. Rivers are 472
`SplineMeshComponent`s.

A filter of `class contains "StaticMeshComponent"` misses all of it. That is why
`palxwater` sweeps unfiltered.

### `Mappings.usmap` is mandatory

Palworld cooks with `PKG_UnversionedProperties`. Without mappings, every property
read comes back **silently empty** — no error, no warning. **A zero result means
the mappings were not applied, not that the asset is absent.** Every extractor
here now fails loudly instead (`Usmap()` throws if the file is missing).

### The strobing hazard — do not remove the clamp

Snapshot gaps imply a median **1.52 in-game days per frame** — one and a half
sunrises every 33 ms. Played back unclamped that is a photosensitive-seizure
pattern, not a timelapse.

The clamp lives in `tools/timelapse/timelapse.mjs` (`CYCLE_FRAMES` / `MAXSTEP` /
`HARD_MAXSTEP`, search for "FORWARD ONLY"):

- `CYCLE_FRAMES = 240` → **`MAXSTEP` = 0.1 h of sun movement per frame**, i.e. a
  full day/night takes at least 240 frames (8 s at 30 fps).
- **Forward only.** Chasing the true hour by the shortest route makes the sun run
  backwards whenever the next snapshot sits slightly earlier in the day.
- `HARD_MAXSTEP = 24/120` — **never faster than 1 cycle / 4 s**. Exceeding it is
  a fatal error: the renderer prints `Refusing to render a strobing video` and
  exits non-zero rather than producing the file.

It is applied last, to the final rendered hour, *after* all pacing logic, so that
no future change to pacing can reintroduce strobing. **Do not remove or loosen
it. It is a safety guard, not a style preference.**

`tools/timelapse/strobecheck.py` proves an actual rendered sequence does not
strobe. Note that `src/scene/dayNight.test.ts` covers a *different* property —
that the scene stays readable at every hour (exposure band, key light never
zero, continuity across dawn/dusk) — not the frame-rate clamp.

### `CommonDropItem3D` is ground loot, not construction

It is dropped loot on a despawn timer. It has corrupted **three** separate
analyses in this project: it inflated build statistics from 819/279 to
2322/1785, and it manufactured a "frantic teardown" narrative that was in fact
93 dropped bags expiring.

Every script that counts built pieces excludes it explicitly — see `NONBUILT` in
`demolitions.py` and `TRANSIENT_EXACT` in `build_endoflife.py`. If a number about
construction looks dramatic, check this first.

### Two smaller ones

- **The all-zero builder UID is a sentinel, not a player** — but a real player's
  UID can share its first eight characters, so the short key is ambiguous unless
  the sentinel is resolved *before* truncation. `build_actor_scenes.py` does
  this and emits `null`; a piece with a `null` builder draws no avatar rather
  than a guessed one.
- **The first screenshot of a Chrome process comes back as bare background**
  (mean luminance 35.0 vs ~71). `timelapse.mjs` warms up by screenshotting until
  two consecutive captures are byte-identical, then discards them all.

---

## Verification tools

| Script | Checks |
|---|---|
| `strobecheck.py` | that a rendered sequence does not strobe |
| `terrain_verify.py` | that foliage instances land on the landscape surface (the 0–27 cm result) |
| `validate_glbs.py` | structural validation of the textured GLBs |
| `verify_radius.py` | that every painted object appears in the build index; guards the unowned-object indexing fix against a known baseline |

Repo-level checks, from the root:

```bash
npx tsc --noEmit
npm test              # vitest
```
