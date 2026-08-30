"""Recover player appearance observations from historical NAS Player saves.

The git history does not contain every pre-history Player save.  The extracted
NAS backup sets do, beside their matching Level.sav files.  This pass reads only
PlayerCharacterMakeData and records the real body type and mirror equipment
override at the Level.sav timestamp.  It never fills gaps or extrapolates.
"""
import glob
import hashlib
import json
import os

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))


def parse(path):
    import ooz  # noqa: F401
    from palworld_save_tools.gvas import GvasFile
    from palworld_save_tools.paltypes import PALWORLD_CUSTOM_PROPERTIES, PALWORLD_TYPE_HINTS
    from palworld_save_tools.palsav import decompress_sav_to_gvas

    raw = open(path, "rb").read()
    gvas, _ = decompress_sav_to_gvas(raw)
    sd = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
        .dump()["properties"]["SaveData"]["value"]
    mk = sd.get("PlayerCharacterMakeData", {}).get("value", {})

    def name(key):
        return mk.get(key, {}).get("value")

    ov = mk.get("OverrideEquipmentInfo", {}).get("value", {})
    return {
        "body": name("BodyMeshName"),
        "head": name("HeadMeshName"),
        "hair": name("HairMeshName"),
        "eqBody": name("EquipmentBodyMeshName"),
        "eqHead": name("EquipmentHeadMeshName"),
        "ovBody": ov.get("Body", {}).get("value"),
        "ovHead": ov.get("Head", {}).get("value"),
    }


def main():
    # A Player save can be copied into more than one backup directory.  Decode
    # identical bytes once, while preserving every independently dated sample.
    cache = {}
    observations = {}
    failures = []
    level_paths = []
    for root in ("nas", "nasbk", "nasbk2", "nasbk3"):
        level_paths.extend(glob.glob(f"{SP}/{root}/**/Level.sav", recursive=True))
    for level in sorted(set(level_paths), key=lambda p: (int(os.path.getmtime(p)), p)):
        ts = int(os.path.getmtime(level))
        players_dir = os.path.join(os.path.dirname(level), "Players")
        for path in sorted(glob.glob(os.path.join(players_dir, "*.sav"))):
            name = os.path.basename(path)
            if name.endswith("_dps.sav"):
                continue
            uid8 = name[:-4].lower()[:8]
            raw = open(path, "rb").read()
            digest = hashlib.sha256(raw).hexdigest()
            if digest not in cache:
                try:
                    cache[digest] = parse(path)
                except Exception as exc:
                    cache[digest] = None
                    failures.append({"path": path, "error": str(exc)[:200]})
            if cache[digest] is not None:
                observations.setdefault(uid8, []).append({"ts": ts, **cache[digest]})

    # Exact duplicate timestamps can arise when current and backup/world point
    # at the same save.  Keep one observation per value at that timestamp.
    for uid8, rows in observations.items():
        uniq = {}
        for row in rows:
            key = (row["ts"], json.dumps({k: row[k] for k in row if k != "ts"}, sort_keys=True))
            uniq[key] = row
        observations[uid8] = sorted(uniq.values(), key=lambda r: r["ts"])

    out = {
        "source": "historical NAS Players/*.sav; values verbatim from PlayerCharacterMakeData",
        "players": observations,
        "levelSavesScanned": len(set(level_paths)),
        "distinctPlayerSavesDecoded": len(cache),
        "failures": failures,
    }
    target = f"{SP}/equipment_nas_appearance.json"
    json.dump(out, open(target, "w"), indent=1)
    print(f"wrote {target}")
    print(f"Level saves={out['levelSavesScanned']} distinct Player saves={len(cache)} failures={len(failures)}")
    for uid8, rows in sorted(observations.items()):
        print(f"  {uid8}: {len(rows)} observations, {rows[0]['ts']}..{rows[-1]['ts']}")


if __name__ == "__main__":
    main()
