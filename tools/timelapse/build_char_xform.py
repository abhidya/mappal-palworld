"""Species -> the CharacterMesh component transform its OWN blueprint gives the
skeletal mesh, plus the same record for the player character.

Why this exists: a Palworld save records an ACTOR transform
(SaveParameter.LastJumpedLocation for a Pal, SaveData.LastTransform for a
player), and a UE Character's actor origin is the CAPSULE CENTRE. The mesh is a
child component with its own RelativeLocation — for BP_BerryGoat that is
Z = -30 against a CapsuleHalfHeight of 30, i.e. exactly one half-height down,
which is what puts the feet on the ground. Drawing the mesh at the recorded
point leaves the Pal floating.

Every value is read out of the game's own blueprints (palx --charxform ->
charxform_raw.json). Nothing is estimated. Species whose blueprint carries no
explicit RelativeLocation inherit their parent BP's value where one exists
(cooked blueprints only serialise properties that differ from the parent), and
otherwise fall back to -CapsuleHalfHeight when the capsule is known, which is
the same number by construction.
"""
import json, os
SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(f"{SP}/charxform_raw.json"))
RAW_CI = {k.lower(): v for k, v in raw.items()}
man = json.load(open(f"{SP}/pal_manifest.json"))

def rec(bpname):
    # blueprint filenames are not case-consistent with CharacterIDs in the save
    # (save says "Sheepball", the asset is BP_SheepBall), so match case-insensitively.
    return raw.get(bpname) or RAW_CI.get(bpname.lower())

# Resolve every CharacterID the save actually uses, not just the manifest's own
# keys: the save spells some species differently from the asset ("Sheepball" vs
# BP_SheepBall) and carries BOSS_/Boss_ variants the manifest has no row for.
import glob
seen = dict(man)
for f in glob.glob(f"{SP}/mappal/public/union/pals_*.json"):
    for pl in json.load(open(f))["pals"]:
        seen.setdefault(pl["char"], {})

out, stats = {}, {"explicit": 0, "parent": 0, "capsule": 0, "none": 0}
for cid, e in seen.items():
    bp = (e.get("blueprint") or "").split("/")[-1]
    cands = [bp]
    # cooked child BPs only serialise what differs from the parent, so fall back
    # to the species' base blueprint (BP_<Species>) when the variant is silent.
    if bp.startswith("BP_"):
        base = "BP_" + bp[3:].split("_")[0]
        cands.append(base)
    cands.append("BP_" + cid)
    cands.append("BP_" + cid.split("_")[0])
    # BOSS_/Boss_/PREDATOR_ variants share their base species' rig
    stem = cid
    for pre in ("BOSS_", "Boss_", "PREDATOR_", "RAID_", "GYM_"):
        if stem.startswith(pre):
            stem = stem[len(pre):]
    cands += ["BP_" + stem, "BP_" + stem.split("_")[0], "BP_" + stem + "_Normal"]
    xf, cap, why = None, None, "none"
    for c in cands:
        r = rec(c)
        if not r:
            continue
        if cap is None and r.get("capsuleHalfHeight") is not None:
            cap = r["capsuleHalfHeight"]
        x = r["xform"]
        if xf is None and (any(x["loc"]) or any(x["rot"]) or x["scale"] != [1, 1, 1]):
            xf = x
            why = "explicit" if c == bp else "parent"
    if xf is None and cap:
        xf = {"loc": [0, 0, -cap], "rot": [0, 0, 0], "scale": [1, 1, 1]}
        why = "capsule"
    if xf is None:
        stats["none"] += 1
        continue
    stats[why] += 1
    out[cid] = {"loc": [round(v, 3) for v in xf["loc"]],
                "rot": [round(v, 4) for v in xf["rot"]],
                "scale": [round(v, 4) for v in xf["scale"]]}

# player character: BP_Player_Female / BP_Player_Male share the rig
pl = None
for c in ("BP_Player_Female", "BP_Player_Male", "BP_PalPlayerCharacter", "BP_Player"):
    if c in raw:
        pl = raw[c]
        break
if pl:
    x = pl["xform"]
    if not any(x["loc"]) and pl.get("capsuleHalfHeight"):
        x = {"loc": [0, 0, -pl["capsuleHalfHeight"]], "rot": x["rot"], "scale": x["scale"]}
    out["__player__"] = {"loc": [round(v, 3) for v in x["loc"]],
                         "rot": [round(v, 4) for v in x["rot"]],
                         "scale": [round(v, 4) for v in x["scale"]]}
    print(f"player xform: {out['__player__']} (capsuleHalfHeight={pl.get('capsuleHalfHeight')})")
else:
    print("WARNING: no player character blueprint found; player mesh left unoffset")

json.dump(out, open(f"{SP}/mappal/src/data/palXform.json", "w"), indent=0, sort_keys=True)
print(f"species with a component transform: {len(out)}  sources={stats}")
zs = sorted({tuple(v['loc']) for v in out.values()})
print(f"distinct Z offsets: {len({v['loc'][2] for v in out.values()})}, "
      f"range {min(v['loc'][2] for v in out.values())}..{max(v['loc'][2] for v in out.values())} cm")
nonzero_rot = [k for k, v in out.items() if any(v['rot'])]
print(f"species with a non-identity mesh rotation: {len(nonzero_rot)} {nonzero_rot[:5]}")
