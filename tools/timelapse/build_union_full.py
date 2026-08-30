"""Recover authoritative geometry for every object in build_index.json.

The sampled union builder is fast enough for iteration but can miss objects
that appear between sampled saves. This pass visits each distinct first-seen
snapshot once and copies the complete map-object record from that snapshot.
"""

import glob
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from multiprocessing import Pool


WORK_ROOT = sys.argv[1]
REPO = os.environ.get("PALTL_REPO") or os.path.expanduser("~/Palworld")
rows = json.load(open(os.path.join(WORK_ROOT, "build_index.json")))
want = defaultdict(set)
base_for_instance = {}
for row in rows:
    want[row["first"]].add(row["id"])
    base_for_instance[row["id"]] = row["base"]

sources = {}
for commit, timestamp in (line.split() for line in open(os.path.join(WORK_ROOT, "commits.txt"))):
    sources.setdefault(int(timestamp), ("git", commit))
for tree in ("nas", "nasbk", "nasbk2", "nasbk3", "historical"):
    for path in glob.glob(
        os.path.join(WORK_ROOT, tree, "**", "Level.sav"), recursive=True
    ):
        sources.setdefault(int(os.path.getmtime(path)), ("file", path))

jobs = [
    (timestamp, sources[timestamp], sorted(instance_ids))
    for timestamp, instance_ids in sorted(want.items())
    if timestamp in sources
]


def recover(job):
    _, (kind, reference), instance_ids = job
    try:
        from palworld_save_tools.gvas import GvasFile
        from palworld_save_tools.palsav import decompress_sav_to_gvas
        from palworld_save_tools.paltypes import (
            PALWORLD_CUSTOM_PROPERTIES,
            PALWORLD_TYPE_HINTS,
        )

        if kind == "git":
            pointer = subprocess.run(
                ["git", "-C", REPO, "show", f"{reference}:world/current/Level.sav"],
                capture_output=True,
                check=True,
            ).stdout
            raw = subprocess.run(
                ["git", "-C", REPO, "lfs", "smudge"],
                input=pointer,
                capture_output=True,
                check=True,
            ).stdout
        else:
            raw = open(reference, "rb").read()
        gvas, _ = decompress_sav_to_gvas(raw)
        world = GvasFile.read(
            gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
        ).dump()["properties"]["worldSaveData"]["value"]
        wanted = set(instance_ids)
        recovered = {}
        for map_object in world["MapObjectSaveData"]["value"]["values"]:
            instance = str(
                map_object["Model"]["value"]["RawData"]["value"].get("instance_id")
            )
            if instance in wanted:
                recovered[instance] = map_object
        camps = {
            str(entry["key"])[:8]: entry
            for entry in world["BaseCampSaveData"]["value"]
        }
        return recovered, camps
    except Exception as exc:
        return {}, {}, str(exc)


def encode(value):
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    return str(value)


def main() -> None:
    print(
        f"objects={len(base_for_instance)} snapshots={len(jobs)} "
        f"of {len(want)} distinct first-seen times",
        flush=True,
    )
    found = {}
    camps = {}
    failures = []
    started = time.time()
    with Pool(5) as pool:
        for completed, result in enumerate(pool.imap_unordered(recover, jobs, chunksize=2), 1):
            if len(result) == 3:
                recovered, recovered_camps, error = result
                failures.append(error)
            else:
                recovered, recovered_camps = result
            found.update(recovered)
            camps.update(recovered_camps)
            if completed % 50 == 0:
                print(
                    f"  {completed}/{len(jobs)} geometry={len(found)} "
                    f"{time.time() - started:.0f}s",
                    flush=True,
                )
    if failures:
        raise RuntimeError(f"{len(failures)} snapshots failed; first: {failures[0]}")
    missing = set(base_for_instance) - set(found)
    if missing:
        raise RuntimeError(f"missing geometry for {len(missing)} indexed objects")
    print(f"recovered geometry for {len(found)}/{len(base_for_instance)} objects")

    by_base = defaultdict(list)
    for instance, map_object in found.items():
        by_base[base_for_instance[instance]].append(map_object)
    output_dir = os.path.join(WORK_ROOT, "mappal", "public", "union")
    os.makedirs(output_dir, exist_ok=True)
    for base, objects in by_base.items():
        output_path = os.path.join(output_dir, f"union_{base}.json")
        level = 1
        if os.path.exists(output_path):
            level = json.load(open(output_path)).get("base_camp_level", 1)
        output = {
            "base_camp": camps.get(base),
            "base_camp_level": level,
            "map_objects": objects,
            "characters": [],
            "item_containers": [],
            "char_containers": [],
            "works": [],
            "dynamic_items": [],
        }
        json.dump(output, open(output_path, "w"), default=encode)
        print(f"{base}: {len(objects)} objects -> {os.path.getsize(output_path) // 1024} KB")


if __name__ == "__main__":
    main()
