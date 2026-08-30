"""Merge local historical Level.sav snapshots into build_index.json.

Only snapshots belonging to the Diva Booties guild lineage are accepted. The
world GUID changed during migration, so the stable guild id is the authority.
"""

import glob
import json
import os
import sys
import time

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_CUSTOM_PROPERTIES, PALWORLD_TYPE_HINTS


LINEAGE_GUILD = "017a45a0"


def main(work_root: str) -> None:
    index_path = os.path.join(work_root, "build_index.json")
    rows = json.load(open(index_path))
    first = {row["id"]: row["first"] for row in rows}
    last = {row["id"]: row["last"] for row in rows}
    meta = {
        row["id"]: (row["base"], row["type"], row["x"], row["y"], row["z"])
        for row in rows
    }
    before = len(first)

    candidates = []
    for tree in ("nas", "nasbk", "nasbk2", "nasbk3", "historical"):
        candidates.extend(
            glob.glob(os.path.join(work_root, tree, "**", "Level.sav"), recursive=True)
        )
    candidates = sorted(set(candidates), key=os.path.getmtime)
    print(f"candidate saves: {len(candidates)}", flush=True)

    seen = set()
    used = skipped = 0
    for path in candidates:
        timestamp = int(os.path.getmtime(path))
        if timestamp < time.mktime((2026, 1, 1, 0, 0, 0, 0, 0, -1)):
            skipped += 1
            continue
        try:
            raw = open(path, "rb").read()
            signature = (len(raw), raw[:64])
            if signature in seen:
                skipped += 1
                continue
            seen.add(signature)
            gvas, _ = decompress_sav_to_gvas(raw)
            world = GvasFile.read(
                gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
            ).dump()["properties"]["worldSaveData"]["value"]
            guilds = {
                str(group["value"]["RawData"]["value"].get("group_id"))[:8]
                for group in world["GroupSaveDataMap"]["value"]
                if group["value"]["RawData"]["value"].get("group_type")
                == "EPalGroupType::Guild"
            }
            if LINEAGE_GUILD not in guilds:
                skipped += 1
                continue
            used += 1
            for map_object in world["MapObjectSaveData"]["value"]["values"]:
                raw_model = map_object["Model"]["value"]["RawData"]["value"]
                base = str(raw_model.get("base_camp_id_belong_to"))[:8]
                if base == "00000000":
                    continue
                instance = str(raw_model.get("instance_id"))
                translation = raw_model.get("initital_transform_cache", {}).get(
                    "translation", {}
                )
                if instance not in first or timestamp < first[instance]:
                    first[instance] = timestamp
                    meta[instance] = (
                        base,
                        map_object["MapObjectId"]["value"],
                        round(translation.get("x", 0)),
                        round(translation.get("y", 0)),
                        round(translation.get("z", 0)),
                    )
                last[instance] = max(last.get(instance, timestamp), timestamp)
        except Exception as exc:
            skipped += 1
            print(f"skip {path}: {exc}", flush=True)

    merged = [
        {
            "id": instance,
            "base": meta[instance][0],
            "type": meta[instance][1],
            "x": meta[instance][2],
            "y": meta[instance][3],
            "z": meta[instance][4],
            "first": first[instance],
            "last": last[instance],
        }
        for instance in first
    ]
    json.dump(merged, open(index_path, "w"))
    print(f"saves used={used} skipped={skipped}")
    print(f"objects {before} -> {len(merged)}")
    per_base = {}
    for row in merged:
        per_base.setdefault(row["base"], []).append(row)
    for base, base_rows in sorted(per_base.items(), key=lambda item: -len(item[1])):
        print(
            f"  {base}: {len(base_rows)} objects, "
            f"{len({row['first'] for row in base_rows})} build steps"
        )


if __name__ == "__main__":
    main(sys.argv[1])
