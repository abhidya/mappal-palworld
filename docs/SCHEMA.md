# Blueprint schema — annotated (observed in fixtures/calibration_01.json)

> Every field below was personally observed in the fixture (PST v2.1.0 export).
> The "Paint" section additionally draws on every `fixtures/*.json` in this repo
> and on one real painted world (not committed — see that section's evidence table).
> Fields marked `UNKNOWN` are preserved verbatim and never touched (CLAUDE.md §4).
> `docs/PST-EXPORT-HINTS.md` has the PST-source-side view; this file is the
> on-disk truth.

## Top level

```jsonc
{
  "base_camp":       { "key": "<guid>", "value": { /* BaseCampSaveData */ } },
  "base_camp_level": 1,                 // int
  "map_objects":     [ /* 22 entries, see below */ ],
  "characters":      [],                // working Pals (empty — none assigned)
  "item_containers": [ /* 3 entries */ ],
  "char_containers": [ /* 1 entry: worker slots */ ],
  "works":           [ /* 14 entries */ ],
  "dynamic_items":   []
}
```

PST's own version check: a file missing `dynamic_items` or `base_camp_level`
is rejected as "old blueprint". Our loader mirrors this exact check.

## GVAS property wrapper convention

Everything nests in typed property wrappers:
`{"id": null, "value": <payload>, "type": "NameProperty" | "StructProperty" | ...}`,
structs add `struct_type` / `struct_id`, arrays add `array_type`. Binary blobs
(`trailing_bytes`, `CustomVersionData`, `unknown_bytes`, `Paint.RawData`) —
**preserve byte-for-byte** whether or not we understand them.

**Two byte-blob encodings exist; a reader must accept both.** In every fixture
here a blob is `{"~b": "<base64>"}`, but that tag is not guaranteed: PST's
`json_tools.CustomEncoder` applies `~b` only to Python `bytes`/`bytearray`
values, so a field whose parser produced a plain `list[int]` is emitted as a
bare JSON array of byte ints instead. We have a real export (a different PST
version) that contains **zero** `~b` tags anywhere in the file and writes every
blob as an int array — including blobs that are `~b`-tagged in `calibration_01`.
Note `unknown_bytes` already shows the array form in the listing above. Code
that reads a blob must handle both shapes; `src/parse/paint.ts` does.

## map_objects[i]

```jsonc
{
  "MapObjectId": { "id": null, "value": "Wooden_foundation", "type": "NameProperty" },
  "Model": {                       // struct_type: PalMapObjectModelSaveData
    "value": {
      "BuildProcess": { /* state int + opaque blobs — UNKNOWN, preserve */ },
      "Connector": {               // struct_type: PalMapObjectConnectorSaveData
        "value": { "RawData": { "value": {
          "supported_level": -1,   // UNKNOWN meaning
          "connect": {
            "index": 254,          // UNKNOWN meaning
            "any_place": [ { "connect_to_model_instance_id": "<guid>", "index": 254 } ]
          },
          "unknown_bytes": [0,0,0,0]
        }}}
      },
      "EffectMap": { /* empty MapProperty in fixture — UNKNOWN, preserve */ },
      "Paint":     { /* PalMapObjectPaintSaveData — DECODED, see "Paint" below */ },
      "RawData": { "value": {      // ← the fields we understand
        "instance_id": "<guid>",
        "concrete_model_instance_id": "<guid>",
        "base_camp_id_belong_to": "<guid>",   // == base_camp.key
        "group_id_belong_to": "<guid>",       // guild
        "hp": { "current": 3993, "max": 4000 },
        "initital_transform_cache": {          // sic — game's typo, emit verbatim
          "rotation":    { "x": 0, "y": 0, "z": -0.794, "w": 0.608 },  // quat
          "translation": { "x": -353520.0, "y": 271455.7, "z": 7140.7 }, // cm
          "scale3d":     { "x": 1, "y": 1, "z": 1 }
        },
        "repair_work_id": "<guid>",           // → works[].RawData.value.id
        "owner_spawner_level_object_instance_id": "<guid, usually zero>",
        "owner_instance_id": "<guid, usually zero>",
        "build_player_uid": "<guid>",
        "interact_restrict_type": 1,          // UNKNOWN meaning
        "deterioration_damage": 0.0,
        "stage_instance_id_belong_to": { "id": "<guid>", "valid": 3610003712 }, // UNKNOWN
        "unknown_bytes": [ /* ints — preserve */ ]
      }},
      "CustomVersionData": { /* opaque, preserve */ }
    }
  },
  "ConcreteModel": {               // struct_type: PalMapObjectConcreteModelSaveData
    "value": {
      // TWO SHAPES EXIST (discovered 2026-07-16 via export lint):
      // 1. "Smart" objects (chest, workbench, palbox, …): RawData.value has
      //    instance_id / model_instance_id / concrete_model_type + extras,
      //    and Model.RawData.concrete_model_instance_id cross-references it.
      // 2. Plain structural pieces (foundations, walls, pillars, roofs, …):
      //    Model.RawData.concrete_model_instance_id is the ZERO GUID and
      //    RawData.value is just {"values": <opaque>} with NO id fields.
      //    Preserve verbatim; never mint concrete ids for these (C4).
      "RawData": { "value": {
        "instance_id": "<guid>",   // == concrete_model_instance_id above (shape 1 only)
        "model_instance_id": "<guid>",  // == Model instance_id (backref, shape 1 only)
        "concrete_model_type": "PalMapObjectBaseCampPoint" // etc. (shape 1 only)
        /* + type-specific fields — treat all as UNKNOWN except observed ones */
      }},
      "ModuleMap": { "value": [    // present on objects with behaviours
        { "key": "EPalMapObjectConcreteModelModuleType::ItemContainer",
          "value": { "RawData": { "value": {
            "target_container_id": "<guid>",  // → item_containers[].key.ID.value
            "slot_attribute_indexes": [ { "attribute": 2, "indexes": [0] } ]  // UNKNOWN
          }}}},
        // also observed: ...ModuleType::StatusObserver (opaque), ::Energy (on base_camp)
      ]}
    }
  }
}
```

## Paint — `map_objects[i].Model.value.Paint`

Struct type `PalMapObjectPaintSaveData`. Previously recorded here as an opaque
UNKNOWN; it is decoded. `RawData.value.values` is either **empty** or exactly
**24 bytes**:

```
bytes  0-15   4x little-endian float32 — an Unreal FLinearColor
bytes 16-19   uint32 "has been painted" flag (0 = never painted, 1 = painted)
bytes 20-23   uint32, zero in all 3,530 non-empty blobs observed
```

An **empty** blob means the object has no paint record at all. That is normal,
not corruption — 1,024 objects across the fixtures in this repo carry one.

Decoder + tests: `src/parse/paint.ts`, `src/parse/paint.test.ts`. **Read-only.**
The blob still round-trips verbatim through `_raw`; decoding a field is not the
same as owning it, and editing paint would need its own in-game verification
(CLAUDE.md C5).

### Evidence

Every distinct blob observed. Channels are labelled `ch0..ch3` by byte offset
rather than `R,G,B,A` deliberately — see the caveat below.

| count | ch0,ch1,ch2,ch3 | flag | source |
|--:|---|--:|---|
| 3363 | `1, 1, 1, 1` | 0 | repo fixtures + one exported base |
| 1262 | *(zero-length)* | — | repo fixtures + one exported base |
| 151 | `0, 0, 0, 1` | 1 | one exported base |
| 12 | `1, 1, 1, 1` | 1 | one exported base |
| 4 | `0.2016, 0.2918, 1, 1` | 1 | whole-world scan of a live save † |

† Contributed sample. Its decode is verified here and its bytes are pinned in
`paint.test.ts`; the extraction was not independently reproduced.

Three rows carry the argument:

- **Row 4 vs row 1** — a *painted* object and a *never-painted* object have
  identical colour floats and differ only at byte 16. That is what proves the
  flag is an independent boolean rather than something derived from colour.
- **Row 3** — black is `ch0..ch2 = 0` with `ch3 = 1`, which strongly implies
  alpha is the **last** component; a "the blob is all zeros when black" reading
  would have missed it. Strictly this shows only that the 4th float stays 1.0
  while the first three go to 0.0 — calling it alpha also assumes a colour+alpha
  layout and opaque paint. Both likely, neither proven.
- **Row 5** — the only non-greyscale blob we have observed: four
  `Wooden_foundation` tiles in a 2x2 cluster on one base, i.e. a single
  deliberate paint job. Its three colour channels are mutually distinct, which
  is what lets it speak to channel ordering at all.

The fixtures alone only demonstrate rows 1 and 2 (nobody painted the calibration
bases); `paint.test.ts` asserts exactly that, and reproduces rows 3-5 as byte
literals so they stay regression-tested. If a future fixture ever gains a
painted object, that test fails and this table should be revisited.

### UNKNOWN, stated plainly (CLAUDE.md §4)

The byte **layout** is established. The **semantic order of the three colour
channels is not**, and the two are worth keeping separate.

Greyscale blobs (rows 1-4) are symmetric under any permutation of `ch0..ch2`, so
they say nothing about ordering. Row 5 does break that symmetry — its three
channels are mutually distinct. But it still doesn't finish the job, because the
bytes don't record which colour the player chose:

- read as canonical `FLinearColor` **R,G,B,A** → a saturated **blue**
- read reversed as **B,G,R,A** → a saturated **orange**

Both are consistent with the data. The `r`/`g`/`b` naming in `paint.ts` is
therefore **inferred** from `FLinearColor`'s canonical layout plus alpha-last
being strongly implied — not proven.

**What would settle it:** one in-game look at those four `Wooden_foundation`
tiles. If they're blue, the canonical reading is confirmed; if they're orange,
the channel order is reversed. That is a single observation, not more parsing —
and note it changes only the channel *names*, never the layout above.

Also unknown: whether the colour is a free RGB value or an index-like snap to
the game's fixed paint palette, and what bytes 20-23 are reserved for.

## item_containers[i]

`key.ID.value` = the GUID that `target_container_id` points at.
`value`: `BelongInfo` (GroupId + bControllableOthers), `Slots` (array of
`PalItemSlotSaveData` — empty in fixture), `SlotNum` (int), `RawData.value`
(`permission` lists + `trailing_unparsed_data` — preserve), `CustomVersionData`.

## works[i]

`WorkableType` (enum, e.g. `EPalWorkableType::Repair`), `WorkAssignMap`
(empty in fixture), `RawData.value`:

- `id` — the GUID `repair_work_id` points at
- `workable_bounds.box_sphere_bounds.box_extent` — half-extents of the owner
  object (usable as proxy dimensions!)
- `base_camp_id_belong_to`, `owner_map_object_model_id`,
  `owner_map_object_concrete_model_id` — backrefs
- `transform`: `{ "type": 2, "map_object_instance_id": "<guid>", ... }` —
  relative-to-object; follows the object automatically on move
- `assign_define_data_id` (e.g. `"RepairBuildObject_0"`), plus ~10 more fields —
  meanings UNKNOWN, preserve verbatim

## char_containers[i]

`key.ID.value` GUID (worker-slot container for the base). Contents UNKNOWN —
preserve verbatim.

## base_camp

`key` = base GUID; `value` includes a `ModuleMap` keyed by
`EPalBaseCampModuleType::*` (9 modules, e.g. `::Energy`) — all UNKNOWN,
preserve verbatim.
