"""Same-world base import test against a given PST checkout.

Reproduces the forensic signature recorded in MapPal's docs/CALIBRATION.md:
  (a) imported works keep base_camp_id_belong_to = the ORIGINAL camp id
  (b) the palbox model instance_id is reused, so the world ends up with
      two map objects carrying identical instance_ids
plus a third check we added while reading 2.2.8:
  (c) Connector.connect.any_place entries that reference instance_ids which
      do not exist in the world after import (dangling links).

Operates entirely on a COPY of the save. Never writes to the save folder.
Usage: python sameworld_test.py <pst_src_dir> <level.sav copy>
"""
import sys, os, json, collections

PST_SRC = os.path.abspath(sys.argv[1])
LEVEL = os.path.abspath(sys.argv[2])
sys.path.insert(0, PST_SRC)
sys.path.insert(0, os.path.join(PST_SRC, "palsav"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from palworld_aio.utils import sav_to_gvas_wrapper           # noqa: E402
from palworld_aio.managers import base_manager                # noqa: E402


def s(x):
    return str(x).replace("-", "").lower()


def world(level):
    return level["properties"]["worldSaveData"]["value"]


def model_raw(mo):
    try:
        return mo["Model"]["value"]["RawData"]["value"]
    except Exception:
        return None


def work_raw(we):
    try:
        return we["RawData"]["value"]
    except Exception:
        return None


def snapshot(level):
    """Instance-id multiset, per-camp work counts, and connector refs."""
    w = world(level)
    map_objs = w.get("MapObjectSaveData", {}).get("value", {}).get("values", [])
    works = w.get("WorkSaveData", {}).get("value", {}).get("values", [])

    inst = collections.Counter()
    palbox_inst = collections.Counter()
    conn_refs = []          # (owner instance_id, referenced id)
    for mo in map_objs:
        mr = model_raw(mo)
        if not isinstance(mr, dict):
            continue
        iid = s(mr.get("instance_id", ""))
        inst[iid] += 1
        if str(mo.get("MapObjectId", {}).get("value", "")) == "PalBoxV2":
            palbox_inst[iid] += 1
        try:
            cc = mo["Model"]["value"]["Connector"]["value"]["RawData"]["value"]["connect"]
            for entry in cc.get("any_place", []) or []:
                # any_place entries are dicts of connect info; pull every guid-ish leaf
                for ref in guids_in(entry):
                    conn_refs.append((iid, ref))
        except Exception:
            pass

    work_by_camp = collections.Counter()
    for we in works:
        wr = work_raw(we)
        if isinstance(wr, dict):
            work_by_camp[s(wr.get("base_camp_id_belong_to", ""))] += 1

    return {
        "inst": inst,
        "palbox_inst": palbox_inst,
        "conn_refs": conn_refs,
        "work_by_camp": work_by_camp,
        "n_map_objs": len(map_objs),
        "n_works": len(works),
    }


GUIDLEN = 32


def guids_in(node, out=None):
    """Collect every guid-looking string anywhere under a nested structure."""
    if out is None:
        out = []
    # Guids arrive as str OR as palsav UUID objects — stringify anything that
    # isn't a container before testing it.
    if not isinstance(node, (dict, list, tuple)):
        t = str(node).replace("-", "")
        if len(t) == GUIDLEN:
            try:
                int(t, 16)
                out.append(t.lower())
            except ValueError:
                pass
    elif isinstance(node, dict):
        for v in node.values():
            guids_in(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            guids_in(v, out)
    return out


def main():
    print(f"PST source : {PST_SRC}")
    print(f"Level.sav  : {LEVEL}\n")
    level = sav_to_gvas_wrapper(LEVEL)
    w = world(level)

    camps = w.get("BaseCampSaveData", {}).get("value", [])
    print(f"base camps in world: {len(camps)}")
    if not camps:
        print("no base camps — nothing to test")
        return 2

    before = snapshot(level)
    for c in camps:
        cid = s(c["key"])
        print(f"  camp {cid}  works={before['work_by_camp'].get(cid, 0)}")

    # Pick the camp with the most map objects, or the one named on argv[3].
    counts = collections.Counter()
    for mo in w.get("MapObjectSaveData", {}).get("value", {}).get("values", []):
        mr = model_raw(mo)
        if isinstance(mr, dict):
            counts[s(mr.get("base_camp_id_belong_to", ""))] += 1
    if len(sys.argv) > 3:
        want = sys.argv[3].replace("-", "").lower()
        target = next(c for c in camps if s(c["key"]).startswith(want))
    else:
        target = max(camps, key=lambda c: counts.get(s(c["key"]), 0))
    src_id = str(target["key"])
    guild_id = target["value"]["RawData"]["value"]["group_id_belong_to"]
    print(f"\nexporting camp {s(src_id)} ({counts.get(s(src_id), 0)} map objects)")

    exported = base_manager.export_base_json(level, src_id)
    if not exported:
        print("export failed")
        return 2
    print("exported keys:", ", ".join(sorted(exported.keys())))
    print(f"  map_objects={len(exported.get('map_objects', []))} "
          f"works={len(exported.get('works', []))} "
          f"item_containers={len(exported.get('item_containers', []))}")

    print("\n--- IMPORTING BACK INTO THE SAME WORLD ---")
    ok = base_manager.import_base_json(level, exported, guild_id)
    print(f"import_base_json returned: {ok}")
    if not ok:
        print("import refused (blueprint version gate?) — stopping")
        return 2

    after = snapshot(level)
    print(f"\nmap objects {before['n_map_objs']} -> {after['n_map_objs']}"
          f"   works {before['n_works']} -> {after['n_works']}")

    # (b) duplicate instance ids
    dupes = {k: v for k, v in after["inst"].items() if v > 1 and k}
    pdupes = {k: v for k, v in after["palbox_inst"].items() if v > 1 and k}
    print(f"\n(b) duplicate map-object instance_ids after import : {len(dupes)}")
    for k, v in list(dupes.items())[:10]:
        print(f"      {k} x{v}")
    print(f"    duplicate PALBOX instance_ids                    : {len(pdupes)}")
    for k, v in pdupes.items():
        print(f"      {k} x{v}")

    # (a) works still bound to the original camp
    src_key = s(src_id)
    print(f"\n(a) works bound to ORIGINAL camp {src_key}: "
          f"{before['work_by_camp'].get(src_key,0)} -> {after['work_by_camp'].get(src_key,0)}")
    new_camps = set(after["work_by_camp"]) - set(before["work_by_camp"])
    for nc in new_camps:
        print(f"    new camp {nc} owns {after['work_by_camp'][nc]} works")

    # (c) dangling connector references
    live = {k for k in after["inst"] if k}
    dangling = [(o, r) for (o, r) in after["conn_refs"] if r not in live]
    total_refs = len(after["conn_refs"])
    print(f"\n(c) connector any_place refs: {total_refs} total, "
          f"{len(dangling)} pointing at instance_ids absent from the world")
    for o, r in dangling[:8]:
        print(f"      object {o} -> missing {r}")

    # (d) Same-world specific: do the IMPORTED objects' connector links point at
    # their own imported siblings, or back at the ORIGINAL base's objects?
    # A ref that resolves is not automatically a correct ref.
    new_objs = {k for k in after["inst"] if k} - {k for k in before["inst"] if k}
    imported_refs = [(o, r) for (o, r) in after["conn_refs"] if o in new_objs]
    cross_linked = [(o, r) for (o, r) in imported_refs if r not in new_objs]
    print(f"\n(d) connector refs on imported objects: {len(imported_refs)}")
    print(f"    pointing back at the ORIGINAL base : {len(cross_linked)}")
    for o, r in cross_linked[:8]:
        print(f"      imported {o} -> original {r}")

    verdict_b = "PASS" if not dupes else "FAIL"
    verdict_a = ("PASS" if after["work_by_camp"].get(src_key, 0)
                 == before["work_by_camp"].get(src_key, 0) else "FAIL")
    print(f"\nSIGNATURE (a) works rebound to new camp : {verdict_a}")
    print(f"SIGNATURE (b) no id collisions          : {verdict_b}")
    print(f"SIGNATURE (c) dangling connector refs   : {len(dangling)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
