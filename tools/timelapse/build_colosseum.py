#!/usr/bin/env python3
"""Build the synthetic, no-Palbox Colosseum timelapse inputs.

The Colosseum is a proposed structure at surveyed world coordinates, not a
recorded camp.  Its geometry comes from the checked-in sited blueprint; every
piece therefore shares one render-clock timestamp and buildorder.js supplies
the geometry-derived animation order.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
from pathlib import Path


BASE = "c0105eum"
RENDER_CLOCK = 1787268757


def normalize(value):
    """Convert PST byte wrappers to the shape used by the render unions."""
    if isinstance(value, dict):
        if set(value) == {"~b"}:
            return list(base64.b64decode(value["~b"]))
        return {key: normalize(item) for key, item in value.items() if key != "__skip__"}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def write_json(path: Path, document, *, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=indent), encoding="utf-8")
    print(f"{path.name}: {path.stat().st_size:,} bytes")


def main():
    root = Path(os.environ.get("MAPPAL_ROOT", Path(__file__).resolve().parents[2]))
    source = root / "designs/colosseum-maximus/colosseum_base_sited.json"
    output = Path(os.environ.get("OUT_UNION", root / "public/union"))

    union = normalize(json.loads(source.read_text(encoding="utf-8")))
    pieces = union["map_objects"]
    palboxes = [piece for piece in pieces if piece["MapObjectId"]["value"] == "PalBoxV2"]
    if len(palboxes) != 1:
        raise SystemExit(f"expected exactly one PalBoxV2, found {len(palboxes)}")

    palbox = palboxes[0]
    palbox_id = palbox["Model"]["value"]["RawData"]["value"]["instance_id"]
    pieces = [piece for piece in pieces if piece is not palbox]
    union["map_objects"] = pieces
    union["base_camp"] = None

    # The one character container belongs only to the omitted camp's worker
    # director.  No structure references it, so retaining it would be dangling.
    union["char_containers"] = []

    encoded = json.dumps(union)
    if palbox_id in encoded:
        raise SystemExit("Palbox instance id remains referenced after removal")
    if len(pieces) != 2775:
        raise SystemExit(f"expected 2,775 structures, found {len(pieces)}")

    ids = [piece["Model"]["value"]["RawData"]["value"]["instance_id"] for piece in pieces]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate structure instance ids")

    write_json(output / f"union_{BASE}.json", union)
    write_json(output / f"times_{BASE}.json", {item_id: [RENDER_CLOCK, RENDER_CLOCK] for item_id in ids})

    site = (
        "Colosseum Maximus is a PROPOSED STRUCTURE at surveyed world coordinates "
        "(9000, 98100, 4836.24; in-game map -130, 289), with NO Palbox and NO base "
        "camp. It has never existed in a save, so no construction or actor history "
        "was recorded."
    )
    write_json(output / f"pals_{BASE}.json", {"base": BASE, "pals": [], "note": site})
    write_json(output / f"players_{BASE}.json", {"base": BASE, "players": [], "note": site})
    write_json(
        output / f"builders_{BASE}.json",
        {
            "base": BASE,
            "builders": {},
            "counts": {"attributed": 0, "unrecorded": len(ids)},
            "note": site + " No builder avatar is invented.",
        },
    )
    write_json(
        output / f"demolitions_{BASE}.json",
        {"base": BASE, "params": {}, "demolitions": [], "counts": {"pairs": 0}, "note": site},
    )
    write_json(
        output / f"wildpals_draw_{BASE}.json",
        {
            "base": BASE,
            "source": "not extracted",
            "kind": "wild-spawn-draw",
            "spawners": 0,
            "speciesCount": 0,
            "pvpSpawnerIds": [],
            "counts": {"day": 0, "night": 0},
            "day": [],
            "night": [],
            "note": site + " World spawn tables have not been swept for this proposed site.",
        },
    )
    write_json(
        output / f"equipment_{BASE}.json",
        {"base": BASE, "sockets": {}, "players": [], "counts": {"players": 0, "items": 0}, "note": site},
    )
    write_json(
        output / f"endoflife_{BASE}.json",
        {
            "base": BASE,
            "name": "Colosseum Maximus",
            "kind": "end-of-life",
            "source": "none — proposed structure, not a recorded camp",
            "snapshotsScanned": 0,
            "firstSnapshot": {"ts": None, "at": "no save contains this structure"},
            "finalSnapshot": {"ts": None, "at": "no save contains this structure"},
            "campRecord": {"present": False, "note": "Deliberately absent; no Palbox and no camp."},
            "pieces": {"indexedRows": len(ids), "builtPieces": len(ids), "transientRows": 0},
            "series": [],
            "pals": {"measure": "n/a", "count": 0},
            "timeline": [],
            "endOfLife": None,
            "note": site,
        },
    )

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    when = dt.datetime.fromtimestamp(RENDER_CLOCK, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    manifest[BASE] = {
        "name": "Colosseum Maximus",
        "objects": len(ids),
        "steps": 1,
        "t0": RENDER_CLOCK,
        "t1": RENDER_CLOCK,
        "synthetic": True,
        "note": f"Proposed structure with no Palbox/base camp; shared render clock {when}.",
    }
    write_json(manifest_path, manifest, indent=1)
    print(f"verified: {len(ids):,} unique structures, no Palbox, no base camp")


if __name__ == "__main__":
    main()
