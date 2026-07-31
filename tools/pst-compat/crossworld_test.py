"""Cross-world import of a MapPal-exported blueprint through PST's importer.

This is the case that matters for MapPal: our own export JSON, imported into a
world it never came from, using PST's real load_base_file + import_base_json.

Checks:
  - does PST's blueprint version gate accept our file?
  - do all objects survive import (2.1.0 silently dropped objects whose
    work_ids didn't resolve)?
  - any instance_id collisions in the destination world?
  - Connector.any_place refs pointing at ids absent from the destination
    (only observable cross-world, where the source ids genuinely don't exist).

Usage: python crossworld_test.py <pst_src> <dest Level.sav copy> <blueprint.json>
"""
import sys, os, collections

PST_SRC = os.path.abspath(sys.argv[1])
DEST = os.path.abspath(sys.argv[2])
BP = os.path.abspath(sys.argv[3])
sys.path.insert(0, PST_SRC)
sys.path.insert(0, os.path.join(PST_SRC, "palsav"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from palworld_aio.utils import sav_to_gvas_wrapper          # noqa: E402
from palworld_aio.managers import base_manager               # noqa: E402
from palworld_aio.managers.base_manager import validate_blueprint_version  # noqa: E402

from sameworld_test import s, world, model_raw, snapshot     # noqa: E402

try:
    from palworld_aio.managers.backup_manager import load_base_file
except ImportError:
    from palworld_aio.utils import load_base_file


def main():
    print(f"PST source : {PST_SRC}")
    print(f"destination: {DEST}")
    print(f"blueprint  : {BP}\n")

    bp = load_base_file(BP)
    ok, msg = validate_blueprint_version(bp)
    print(f"blueprint version gate: {ok} — {msg}")
    n_src = len(bp.get("map_objects", []))
    print(f"blueprint map_objects={n_src} works={len(bp.get('works', []))} "
          f"item_containers={len(bp.get('item_containers', []))}")
    if not ok:
        return 2

    level = sav_to_gvas_wrapper(DEST)
    w = world(level)
    before = snapshot(level)

    # A guild to own the import: prefer one that already owns a base camp.
    camps = w.get("BaseCampSaveData", {}).get("value", [])
    if camps:
        guild_id = camps[0]["value"]["RawData"]["value"]["group_id_belong_to"]
        print(f"target guild (from existing camp): {s(guild_id)}")
    else:
        groups = w.get("GroupSaveDataMap", {}).get("value", [])
        guild_id = None
        for g in groups:
            gv = g.get("value", {}).get("RawData", {}).get("value", {})
            if gv.get("group_type") == "EPalGroupType::Guild" or "guild_name" in gv:
                guild_id = g["key"]
                break
        if guild_id is None:
            print("no guild found in destination world")
            return 2
        print(f"target guild (from GroupSaveDataMap): {s(guild_id)}")

    print(f"\ndestination before: map_objects={before['n_map_objs']} works={before['n_works']}")
    print("--- IMPORTING (cross-world) ---")
    res = base_manager.import_base_json(level, bp, guild_id)
    print(f"import_base_json returned: {res}")
    if not res:
        return 2

    after = snapshot(level)
    added = after["n_map_objs"] - before["n_map_objs"]
    print(f"destination after : map_objects={after['n_map_objs']} works={after['n_works']}")
    print(f"\nobjects added: {added} of {n_src} in the blueprint "
          f"({n_src - added} dropped)")

    dupes = {k: v for k, v in after["inst"].items() if v > 1 and k}
    print(f"instance_id collisions in destination: {len(dupes)}")

    # Dangling refs must be attributed: the destination world may already have
    # had some (from its own history) before we imported anything.
    live_before = {k for k in before["inst"] if k}
    live_after = {k for k in after["inst"] if k}
    dang_before = [(o, r) for (o, r) in before["conn_refs"] if r not in live_before]
    dang_after = [(o, r) for (o, r) in after["conn_refs"] if r not in live_after]
    new_objs = live_after - live_before
    dang_new = [(o, r) for (o, r) in dang_after if o in new_objs]

    print(f"connector any_place refs: {len(before['conn_refs'])} -> {len(after['conn_refs'])}")
    print(f"  dangling BEFORE import      : {len(dang_before)} (pre-existing in this world)")
    print(f"  dangling AFTER import       : {len(dang_after)}")
    print(f"  dangling ON IMPORTED objects: {len(dang_new)}  <-- caused by the import")
    for o, r in dang_new[:8]:
        print(f"    imported object {o} -> missing {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
