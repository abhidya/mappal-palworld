"""Write per-site first/last visibility clocks and update the site manifest."""

import json
import os
import sys


NAMES = {
    "07f13218": "Glass Tower",
    "16fca097": "Wooden Camp",
    "de44d9f4": "Stone Works",
    "5fed0024": "Lost Camp",
}


def main(work_root: str) -> None:
    rows = json.load(open(os.path.join(work_root, "build_index.json")))
    output_dir = os.path.join(work_root, "mappal", "public", "union")
    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    per_base = {}
    for row in rows:
        per_base.setdefault(row["base"], {})[row["id"]] = [row["first"], row["last"]]
    for base, times in per_base.items():
        json.dump(times, open(os.path.join(output_dir, f"times_{base}.json"), "w"))
        first_seen = sorted({clock[0] for clock in times.values()})
        manifest[base] = {
            "name": NAMES.get(base, base),
            "objects": len(times),
            "steps": len(first_seen),
            "t0": first_seen[0],
            "t1": max(clock[1] for clock in times.values()),
        }
        print(f"{base}: {len(times)} objects, {len(first_seen)} steps")
    json.dump(manifest, open(manifest_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
