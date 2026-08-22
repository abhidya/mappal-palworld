# Extracting real building models from Palworld (for local use)

> Researched 2026-07-16 against game v1.0.1.100619. Assets extracted from your
> own install, loaded locally by MapPal — never committed to this repo and not
> part of any public deploy unless a deliberate decision is made later.
>
> Revised after a full extraction run: the id → mesh table, the usmap
> requirement, and the server-vs-client pak split are all new sections below,
> and they correct earlier guidance rather than just adding to it.

## The short version

FModel (the standard UE asset explorer) opens Palworld's pak unencrypted; you
need one community "mappings" file (`Mappings.usmap`) because it's UE5 — this
is **mandatory, not a nicety**, see "The usmap is mandatory" below. Building
pieces are defined as `BP_BuildObject_*` Blueprints whose names line up with
our `MapObjectId`s; each Blueprint references its StaticMesh. Export the meshes
as glTF and `tools/` can generate the `MapObjectId → mesh` manifest.

**You do not have to open blueprints one at a time to build that manifest.**
`DT_MapObjectMasterDataTable` maps ids to blueprint classes directly — see
"The id → mesh table" below. An earlier revision of this doc ruled out
`DT_MapObjectAssignData` (correctly) and concluded the per-blueprint route was
the only option; that conclusion was wrong.

Nobody has built a public Palworld *building* renderer before (creature-model
extraction is routine, buildings aren't) — so MapPal's manifest is new ground.

## One-time setup (~10 min)

1. Download FModel (`dec-2025` release or newer): https://fmodel.app/ —
   that release matters: it added Nanite static-mesh export, which UE5 games use.
2. Download the mappings file `Mappings.usmap`:
   https://github.com/PalworldModding/UsefulFiles/raw/refs/heads/master/Mappings.usmap
   — verified updated **2026-07-10, "Update Mapping to 1.0"**, matching our
   game build. (Do NOT use elliotks/Palworld-FModel — archived, pre-1.0 only.
   Fallback if a future hotfix breaks it: self-dump via UE4SS Dumper tab.)
3. In FModel: Directory → Selector → "Add Undetected Game" → directory
   `...\steamapps\common\Palworld` (the folder containing `Engine` and `Pal`);
   UE Versions = `GAME_UE5_1`; Settings → General → enable **Local Mapping
   File** → point at the `.usmap`. Leave the AES field blank (not needed).
4. Settings → Models: Texture Format = **PNG**. Mesh Format — two routes:
   - **Quick:** `glTF2` directly. Works, but is the less battle-tested path.
   - **Robust (FModel devs' recommendation):** `UEFormat (uemodel)`, then the
     UEFormat Blender plugin (github.com/Buckminsterfullerene02/UEFormat) →
     Blender → export glTF Binary (.glb). Use this if a direct-glTF mesh
     looks wrong (UVs/materials).

## Per-export session (~20 min for all building pieces)

5. Browse to `Pal/Content/Pal/Blueprint/MapObject/BuildObject/` — this is the
   canonical list of every buildable (`BP_BuildObject_...`). Right-click the
   folder → batch-export the packages' **Properties (JSON)**. These JSONs
   contain each buildable's StaticMesh reference — MapPal's manifest generator
   consumes them.
6. Open one Blueprint's JSON, note the StaticMesh path it references — that
   reveals the real Model folder. Right-click that mesh folder → **Save
   Folder's Packages Models** (+ Textures) to export `.glb` files.
7. Optional palette icons: `Pal/Content/Pal/Texture/UI/InGame` →
   `T_icon_construction_tab_*` textures as PNG.
8. Put everything under `assets-local/` in this project (gitignored):
   `assets-local/blueprints/*.json`, `assets-local/models/*.glb`,
   `assets-local/icons/*.png`.

## Known pitfalls (from the modding community's own docs + Epic's glTF docs)

- Blender import of UE assets: scale 0.01, "Add Leaf Bones" off.
- UE materials only approximate to glTF PBR — expect some texture slot fixing;
  normal maps may need a green-channel flip. glTF keeps max 2 UV channels,
  needs full-precision UVs, exports no collision and a single LOD (all fine
  for viz). Runtime paint/weathering overlays won't survive — you get the
  clean material, not in-game decay.
- `DT_MapObjectAssignData` is Pal work-assignment data, NOT an ID→mesh table.
  That much stands. But see "The id → mesh table" below: a different DataTable
  *is* one, and going through it beats opening blueprints by hand.
- ID ↔ blueprint matching heuristic: `BP_BuildObject_<Name>` suffixes mirror
  item IDs (e.g. `BP_BuildObject_WorkBench_SkillUnlock` ↔ our
  `WorkBench_SkillUnlock` donor) — strong pattern, verify per piece.
- For a fully scripted alternative to manual FModel clicking:
  github.com/PalworldDataTools/PalworldDataExtractor is a CUE4Parse-based
  .NET CLI/library that already dumps Palworld DataTables to JSON — could be
  extended to dump `DT_ItemDataTable` + BuildObject blueprints headlessly.

## The id → mesh table

`DT_MapObjectMasterDataTable` (and its `_Common` sibling) is an id → blueprint
table, which closes the chain end-to-end:

```
MapObjectId
  -> DT_MapObjectMasterDataTable(_Common).BlueprintClassSoft
  -> BP_BuildObject_*.uasset   (read its name table)
  -> a mesh asset, usually /Game/Pal/Model/.../SM_* or SK_*
```

e.g. `Stone_Foundation -> BP_BuildObject_Stone_Foundation -> SM_Floor_Stone`.

The terminal step is deliberately loose: 6 legitimate meshes resolve outside
`/Game/Pal/Model/` entirely — `SM_Mine01` under `/Game/Others/MilitaryItems/`,
`SM_Brazier` under `/Game/Others/-Animations/`, `S_Dead_Tree_qlEtl_lod3` under
`/Game/Megascans/`, and `SM_Crystal_Plume` under `/Game/Pal/Blueprint/`. Do not
filter on the `Model` prefix.

### What actually resolves — the honest count

Run against MapPal's own 453 type ids:

| | count |
|---|--:|
| produce **a path** | 452 |
| of those, land on a **real mesh asset** | **432** |
| land on a `BP_*` Blueprint, not a mesh | **20** |
| produce no path at all | 1 |

The one id with no path is `CommonDropItem3D`, which has no fixed mesh — it is
dropped loot and picks its model at runtime per item.

**The 20 are a fallback misfire, not a resolution**, and worth stating because a
flat "452 of 453" flatters the method. 14 of them land on the same generic
`/Game/Pal/Blueprint/MapObject/Components/BP_BuildObjectSimulateArrowComponent`
— including every `JapaneseStyle_*` wall, plus `Light_FloorLamp02`,
`Stool01_Stone`, `TrafficCone02_Iron`, `Shishiodoshi` and
`AncientElectricGenerator`. The other 6 point at `*_Base` blueprints for the
defense turrets, the black sphere factory, the leg-hold trap and the weapon
factory.

These are exactly the entries that fail downstream: the 5 distinct `BP_*`
targets above are **precisely** the 5 assets that came back `no UStaticMesh or
USkeletalMesh export` in the 818-mesh run (see the usmap section). So they are a
known, bounded set needing per-piece follow-up — presumably assembled from
components rather than named by the blueprint's top-level mesh reference.

All 432 real mesh paths were confirmed to exist in the client pak.

Why prefer this over reading each blueprint by hand: **name-guessing the mesh
path from the id is not safe.** `Umihebi_Fire` resolves to
`/Game/Pal/Model/Character/Monster/Umihebi/SK_Umihebi_Fire` — the *directory* is
`Umihebi`, not `Umihebi_Fire`. Any heuristic that assumes the folder matches the
id silently misses cases like that. The table doesn't guess.

Both DataTables and Blueprints live in the **dedicated-server** pak, so the
whole manifest can be generated with no game client installed. The meshes
cannot — see below.

## The usmap is mandatory

Palworld's cooked packages do not carry enough version information to be parsed
without help, and skipping the mappings file does not fail loudly — it fails
*quietly*, which is worse.

Two separate things, both verified against real package headers:

- **No declared engine version.** In every package checked (both paks),
  `FileVersionUE4`, `FileVersionUE5` and `FileVersionLicenseeUE4` are all `0`
  with zero custom-version entries. The file never says which engine wrote it,
  so the tool has to be told (`GAME_UE5_1`).
- **Unversioned properties.** Client-pak packages set `PKG_UnversionedProperties`
  (`0x2000` — e.g. `SM_Wall_Wood` has flags `0x80002200`), meaning properties are
  serialized with no inline names or types. Without a `.usmap` there is nothing
  to resolve them against. (Server-pak packages are flagged `0x80000200` — the
  bit is not set there, which is part of why the DataTable route works so
  easily off the server pak.)

**The failure mode is false negatives.** Before we supplied a usmap, a
heuristic byte-scanner concluded that 19 of 54 building meshes were
"Nanite-only" and that 6 Pal skeletal meshes had an unreadable vertex layout
(`no FPositionVertexBuffer found`). Both conclusions were artifacts of parsing
blind. With a usmap in place, all 19 and all 6 extracted through the ordinary
classic LOD path, and no Nanite decoder was needed for any of them — across a
full run of 818 meshes, `nanite` came back false for every single one and
809/818 extracted (the 9 misses are 5 blueprints with no mesh export at all and
4 assets absent from the directory being scanned, not decode failures).

If a mesh looks Nanite-only or structurally unreadable, check the usmap before
believing it.

## Server pak vs client pak

They are not interchangeable, and the split is sharp:

| | dedicated-server pak | Windows client pak |
|---|--:|--:|
| `.uasset` / `.uexp` | 66,973 / 76,977 | 66,979 / 76,983 |
| `.ubulk` (bulk payload) | **0** | **21,056** |
| audio (`.wem` / `.bnk`) | 0 | 4,303 / 1,180 |
| texture `.uexp`, mean size | **217 bytes** (max 4,641) | full payloads |

The server cook runs with `AllowAudioVisualData()` false: the asset *headers*
are all there, but the renderable payload is stripped. Same asset, both paks:
`SM_Wall_Wood` is a 4,771-byte `.uexp` with no `.ubulk` on the server side, and
a 65,911-byte `.uexp` plus a 72,240-byte `.ubulk` on the client side.

So: **the server pak is enough to build the id → mesh manifest, and useless for
geometry.** Textures averaging 217 bytes are header stubs, not textures. If you
are running a dedicated server and hoped to skip the client install, you can
generate the manifest but you will still need the client pak for the models.

## What MapPal does with it (to be built)

- `tools/gen-mesh-manifest.ts`: parse `assets-local/blueprints/*.json` →
  `assets-local/manifest.json` (`MapObjectId → {mesh, icon, name}`).
- Scene: load `.glb` per manifest entry (drei useGLTF), fall back to the
  parametric proxy shapes for anything unmapped or when `assets-local/` is
  absent. Zero assets in the repo; the loader ships, the models don't.

Sources: pwmodding.wiki (FModel setup, export tutorial),
palworld.wiki.gg/wiki/Game_Files/Guide (pak paths), github.com/4sval/FModel
(releases/wiki), PalworldModding/UsefulFiles (mappings).
