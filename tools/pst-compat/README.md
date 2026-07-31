# PST compatibility harness

Drives PalworldSaveTools' **real** `export_base_json` / `import_base_json`
against copies of a save, so we can check what a new PST release does to a base
without loading the game. Written for the v2.2.8 re-test; see the
"PST v2.2.8 re-test" section of [../../docs/CALIBRATION.md](../../docs/CALIBRATION.md).

**This does not replace in-game verification.** It measures the *file* after
import. Whether the game keeps those structures on load is a separate claim and
only Alex loading the game can settle it. Every conclusion drawn from these
scripts must say which of the two it is.

Nothing here writes to `%LOCALAPPDATA%\Pal\Saved\SaveGames` — copy the save out
first and point the scripts at the copy.

## Setup

```bash
git clone --depth 1 --branch v2.2.8 \
  https://github.com/deafdudecomputers/PalworldSaveTools.git pst
python -m venv venv
./venv/Scripts/python -m pip install orjson packaging Pillow brotli cbor2 \
    msgpack zstandard py7zr pyside6-essentials nerdfont
./venv/Scripts/python -m pip install ./pst/src/palsav/palooz   # Oodle codec, builds from source
mkdir saves && cp "$LOCALAPPDATA/Pal/Saved/SaveGames/<steamid>/<world>/Level.sav" saves/
```

`palooz` is the Oodle decompressor. It ships as C++ source only — the wheel
builds locally and needs a C++ toolchain. Without it `load_sav` fails with
`module 'palooz' has no attribute 'decompress'`.

To compare against an older PST, add a worktree and pass its `src` instead:

```bash
git -C pst fetch --depth 1 origin tag v2.1.0
git -C pst worktree add ../pst210 v2.1.0
```

## Same-world import

```bash
./venv/Scripts/python sameworld_test.py pst/src saves/Level.sav [camp-id-prefix]
```

Exports a base and re-imports it into the world it came from, then reports:

- **(a)** works still bound to the original camp (should be unchanged)
- **(b)** duplicate `instance_id`s, and duplicate palbox ids specifically —
  this is the original incident's signature
- **(c)** `any_place` refs pointing at ids absent from the world
- **(d)** refs on imported objects that point back at the **original** base —
  a ref that resolves is not automatically a correct ref, and this is the check
  that caught the remaining 2.2.8 defect

## Cross-world import of a MapPal blueprint

```bash
./venv/Scripts/python crossworld_test.py pst/src saves/DestLevel.sav ../../fixtures/calibration_01.json
```

Loads one of our own exports through PST's `load_base_file` and imports it into
a world it never came from. Reports whether PST's blueprint version gate accepts
our file, how many objects survived the import, collisions, and dangling
connector refs attributed to the import (the destination's own pre-existing
dangling refs are subtracted).

## `connector_remap.patch`

Candidate upstream fix: remaps `connect_to_model_instance_id` through PST's
existing `instance_id_map`. Apply to a PST checkout with
`git -C pst apply ../connector_remap.patch` to reproduce the 10 → 0 and
14 → 0 results. Not ours to ship — it belongs in PST.

## Gotchas

- Connector ids come back as `PalUUID` objects, not `str`. Stringify before
  comparing or every check silently matches nothing (this bit us once).
- `import_base_json` pulls in PST's Qt editor modules; `QT_QPA_PLATFORM=offscreen`
  is set by the scripts so it runs headless.
- The scripts mutate the loaded level in memory only. They never write a `.sav`.
