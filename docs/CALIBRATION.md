# Calibration — derived ground truth

> Derived from `fixtures/calibration_01.json` on 2026-07-16 via `npm run inspect`
> and targeted delta analysis. Every number below was computed from the file,
> not assumed. Where something was *not* directly measured, it says so.

## Provenance

| Field | Value |
|---|---|
| Fixture | `fixtures/calibration_01.json` (247 KiB, 22 map objects) |
| PST version used for export | v2.1.0 |
| Save format version (as reported by PST UI) | 1.0.1 |
| Palworld game version | Win S v1.0.1.100619 (Steam, Windows; player runs mods incl. one id 178D…) |
| Export date | 2026-07-16 |

Calibration base contents: Palbox, 10 wooden foundations (row of 5 + L + a
separate 4-foundation starter platform), 3 walls, 2 stacked pillars + roof
(vertical reference), chest, workbench, Pal bed. The export also captured a
dropped-item bag (`CommonDropItem3D`) and a world rock (`DamagableRock0012`)
that happened to be inside the base radius — see "Surprises" below.

## Units and axes

- **Confirmed consistent with Unreal defaults: centimetres, Z-up.** All
  rotations in the file are pure yaw (quaternion x≈0, y≈0) and yaw rotates the
  X/Y plane; Z is elevation (~7100 = ground height at this base).
- Foundations ground-snap at arbitrary Z (two foundation clusters sit 18.18
  units apart vertically, following terrain).

## Grid pitch — 400 units (4 m), refuting the "2 m" folklore

Adjacent flush foundation centres differ by exactly **400.0 units**:
deltas along the row are (dx=384.72, dy=−109.51), √(384.72² + 109.51²) = 400.00.
The perpendicular (L) delta is (109.51, 384.72) — also 400.00. The second
foundation cluster independently confirms 400.00.

**The grid is NOT world-axis-aligned.** Each snap-group inherits an arbitrary
yaw from its first placed piece (row grid: yaw 164.11°; starter platform:
yaw 61.18°). One base can contain multiple independent grids. Editor snapping
must therefore be *per-connected-group in local frame*, not global-XY.

## Vertical pitch — 325 units per wall/pillar segment

Pillar stack: z = 7139.69 → 7464.69 → roof at 7789.69. **Δz = 325.0 per
segment.** (Wall height itself not directly measured — walls in the fixture
have nothing on top — but pillars and walls are the same building tier;
assume 325 until a wall-supported floor is observed.)

## Rotation encoding — quaternion, yaw-only, 90° steps for structures

- Stored as quaternion `{x, y, z, w}` in `transform.rotation`.
- The 3 walls sit at yaw 164.11°, −105.89°, −15.89° — exactly grid-yaw,
  grid−90°, grid+180°. **Structures snap in 90° steps relative to their grid.**
- **Free-placed furniture is NOT rotation-snapped**: chest −105.15°,
  bed 170.17°, workbench −16.72° — arbitrary player-aimed yaws. The editor
  must not force furniture onto 90° steps (offer snapping, don't require it).

## Wall placement — origin at foundation edge, base of wall

All 3 walls are exactly **200.0 units** (half a foundation) from their host
foundation's centre, at the foundation's own Z. So: foundation origin is at
its centre, top surface; wall origin is at the edge midpoint, bottom of wall.
Furniture rests ~1 unit above foundation Z (chest/bed/workbench at +1.05).

## Object type vocabulary (→ `src/data/objects.json`)

`MapObjectId.value` strings observed: `Wooden_foundation`, `Wooden_wall`,
`Wooden_pillar`, `Wooden_roof`, `PalBoxV2`, `ItemChest`, `Workbench`,
`MedicalPalBed_02`, `CommonDropItem3D`, `DamagableRock0012`.

**Free dimensions trick:** every object's repair `works` entry carries
`workable_bounds.box_sphere_bounds.box_extent` (half-extents) — e.g. chest
80×100×37 → 160×200×74 full size. Usable as gray-box proxy dimensions without
guessing.

## Linkage (the §0.2 highest-risk unknown) — mapped

Confirmed reference graph, all by GUID:

1. **Object → container:** objects with inventories carry a
   `ConcreteModel.ModuleMap` entry (`...ModuleType::ItemContainer`) whose
   `target_container_id` matches an `item_containers[].key.ID.value`.
   Chest, workbench, and even the dropped-item bag each have one.
2. **Object → work:** every object's `RawData.value.repair_work_id` points to a
   `works[]` entry (`EPalWorkableType::Repair`), which back-references the
   object via `owner_map_object_model_id` / `owner_map_object_concrete_model_id`
   and repeats `base_camp_id_belong_to`. The workbench has a second work entry
   (its crafting work). **Every placed object owns ≥1 work entry.**
3. **Object ↔ object (Connector):** furniture and the palbox link to their
   host foundation **bidirectionally** via
   `Model.Connector.RawData.value.connect.any_place[].connect_to_model_instance_id`.
   Structural pieces (walls/pillars/foundations between themselves) showed only
   `connect.index` in this fixture — grid adjacency appears implicit, not stored
   as explicit links between structure pieces.
4. **Object → base/guild:** `base_camp_id_belong_to` (= `base_camp.key`) and
   `group_id_belong_to` on every object.

### Editor consequences

- **Move/rotate (Phase 1):** edits `initital_transform_cache.translation` /
  `.rotation` only. No IDs change, so the linkage graph is untouched. The
  `works` entries carry a `transform` of `{type: 2, map_object_instance_id}`
  (relative-to-object), so they follow automatically. Low risk, as hoped.
- **Duplicate (Phase 1):** must mint fresh GUIDs for `instance_id` +
  `concrete_model_instance_id`, clone the repair `works` entry (fresh `id`,
  updated owner refs), clone any `item_containers` entry (+ fresh
  `target_container_id`), and rewrite/drop `Connector.any_place` links.
  Skipping the works-clone would give PST's importer a dangling
  `repair_work_id` — untested whether that's fatal; safest is to clone.
- **Delete (Phase 1):** should also remove the object's `works` entries and
  (for containers) its `item_containers` entry, or at minimum warn. PST's
  importer skips objects with dangling refs; orphaned works/containers ride
  along silently.

## Large-scale import verification (2026-07-18)

A ~450-piece editor-built tower (circle-filled platform, cloned pillar
column, vertically-stacked shaft walls, group-rotated stair wrap, palette-
placed SF/glass pieces) was imported cross-world and spawned **fully intact**:

- **The "~16-tile vertical build limit" community figure is refuted for
  imports on game v1.0.1** — the tower is ~47 wall-heights and every level
  spawned. (In-game *placement* may still enforce a limit; imports don't.)
- One editor defect found: the stair proxy geometry's ascent direction was
  mirrored versus the real game mesh, so stairs oriented by eye in the editor
  spawned backwards. Fixed in proxyGeometry (steps now rise toward −X);
  `tools/rotate-type.ts` repairs affected exports (rotate "stair" 180°).

## Surprises worth remembering

- The export includes **non-player-built objects** inside the radius: dropped
  item bags (`CommonDropItem3D`, with its own item container) and damageable
  world rocks (`DamagableRock0012`). The editor must preserve these verbatim
  and should render them distinctly (they are not on any grid).
- The game's own typo `initital_transform_cache` is real and must be emitted
  verbatim (C4/C5).
- `hp` shows live deterioration (chest at 3993/4000) — another reason never to
  regenerate values we don't understand.

## Round-trip gate

- [x] `roundtrip.test.ts` passes with zero semantic diffs *(activated 2026-07-16;
      first run caught JS silently rewriting Python's `-0.0` floats to `0` —
      fixed with a sign-preserving serializer)*
- [x] Round-tripped file re-imported via PST v2.1.0 into a save *(2026-07-16)*
- [x] Base verified intact in-game via **cross-world import** *(2026-07-16,
      second attempt — the first was invalidated by PST's same-world-import
      breakage, see "Phase 1 in-game verification" below)*: edited blueprint
      imported into a fresh world; full base spawned with the moved chest at
      its new position and the MapPal-duplicated chest beside it.

**GATE PASSED 2026-07-16 (cross-world). Phase 1 verified end-to-end — this is
the v0.1 definition of done (CLAUDE.md §10).**

## Phase 1 in-game verification (2026-07-16) — PARTIALLY INVALIDATED, see below

Initial reports of success were confounded. Forensics on the actual save
(decoded `.pstbase` re-exports of all three bases) established:

- **Same-world re-import is broken in PST v2.1.0 + game v1.0.1.** Importing a
  base back into the world it was exported from produces base camps whose
  structures the game deletes on first load. Two mechanisms observed:
  (a) imported works entries keep `base_camp_id_belong_to` = the ORIGINAL
  camp id (the original camp ended up owning 3× its works), and (b) PST
  deliberately reuses the palbox's model `instance_id` on import, so the world
  gets multiple palboxes with identical ids. The game's cleanup then deletes
  the import's entire connector-linked network. This hit the UNEDITED
  round-trip import identically — it is not caused by MapPal edits.
- **Deletion propagates along `Connector.any_place` links; link-free objects
  survive.** In the gutted import, exactly two objects survived, at their
  correct imported positions: the dropped-item bag and **MapPal's duplicated
  chest** (fresh GUID bundle, cleared connectors). The moved original chest —
  which kept its link to its host foundation — was purged with the network.
  This is strong evidence the duplicate writeback design is correct, and that
  `initital_transform_cache.translation` is authoritative for spawn position.
- The earlier §0.3 "verified intact in-game" and the first Phase 1 "success"
  were observations of the original base / the two surviving loose objects,
  made before the import-offset behaviour was understood.

**Consequence: all in-game verification must use cross-world import** —
export from world A, import into throwaway world B. Same-world import is a
PST limitation, not ours; for same-world duplication PST's own Clone Base is
the supported path. The round-trip gate's in-game legs must be re-run
cross-world before Phase 1 is declared verified.

## PST v2.2.8 re-test (2026-07-31) — collisions fixed, connectors still not remapped

PST's maintainer reported that v2.2.8 regenerates all base-related IDs on
import, so same-world import should no longer break. Re-tested here **at the
file level only** — no in-game load — by driving PST's real
`export_base_json` / `import_base_json` against copies of Alex's saves.
Harness and how to re-run: `tools/pst-compat/`.

Control first: the harness reproduces the original incident on v2.1.0.
Same-world import of a 17-object base produced **17 duplicate `instance_id`s,
including the palbox** (`9d3e77dc…` twice) — the signature recorded above.
The cause is literal identity mapping, confirmed by diffing the two versions:

```
v2.1.0:  instance_id_map[old_inst] = old_inst      # identity
v2.2.8:  instance_id_map[old_inst] = _new_uuid()
```

On v2.2.8 the same import yields **0 duplicate instance_ids, 0 duplicate
palbox ids**. Mechanism (b) is genuinely fixed.

**Correction to mechanism (a) above.** Works were never mis-bound: both
versions set `base_camp_id_belong_to = new_base_id` on every imported work
(`base_manager.py:280`), and the original camp's work count is unchanged by an
import on either version. The observed "original camp owns 3× its works" was
the *same* identity-mapping bug seen through the object graph — imported works
had their `owner_map_object_model_id` remapped through the identity map, so
they pointed at the **original** map objects. One root cause, not two.

**Remaining defect — `Connector.connect.any_place` is never remapped.**
Nothing in `import_base_json` touches it, on either version. Each entry is
`{connect_to_model_instance_id, index}` (`palsav/rawdata/connector.py:13`).
While IDs were identity-mapped this was invisible. Now that every ID is
regenerated it misfires two ways, both measured:

| Import | v2.1.0 | v2.2.8 |
|---|---|---|
| Cross-world (22-object MapPal export) | 0 dangling refs | **10 dangling** — point at IDs absent from the destination world |
| Same-world (17-object base) | n/a (collides instead) | **14 of 14** refs on imported objects point back at the **original** base's objects |

The same-world number is the concerning one: the imported copy is structurally
wired into the original base's connector network. Our own forensics established
that deletion propagates along `any_place` links — so the mechanism that gutted
the base in the original incident is still reachable, even though its trigger
(the ID collision) is gone. **Unverified either way in-game.**

A candidate one-block fix — remap `connect_to_model_instance_id` through the
existing `instance_id_map` inside the map-object loop — takes cross-world
dangling refs 10 → 0 and same-world cross-links 14 → 0, with collisions still
at 0 and all objects still imported. Patch: `tools/pst-compat/connector_remap.patch`.
Reported upstream 2026-07-31.

**The "never import into the world it came from" warning stays as-is** until
someone loads a same-world 2.2.8 import in-game and confirms the structures
survive. A file that no longer collides is not the same claim as a base the
game keeps — that distinction is exactly what CLAUDE.md §6 was written about.

Incidental v2.2.8 change worth knowing: objects whose `work_ids` don't resolve
are no longer dropped from the import. v2.1.0 set `has_invalid` and skipped the
whole object; v2.2.8 filters the bad IDs and keeps it. Fewer silent losses.

PST workflow gotchas (README must warn about all of these):
- Import Base creates a **new base copy offset ~80 m** (collision-avoided).
- After importing, you must **save in PST** (game fully closed) or nothing
  reaches disk.
- **Never import a base into the world it came from** (structures will be
  silently deleted on next load; see above).
- PST GUI base exports default to compressed `.pstbase`
  (`_version`-stamped cbor2→brotli→zstd); MapPal reads only the plain
  `.json` flavour.
