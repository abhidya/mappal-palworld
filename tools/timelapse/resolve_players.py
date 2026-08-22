"""Resolve every player look that ever appears in player_index.json to the real
SK_Player_* assets, using the GAME'S OWN character-creation data tables
(datatables.json, dumped from the pak by `palx --datatable CharacteCreation`).
Nothing here guesses a name-to-mesh mapping:

  BodyMeshName  "TypeA"/"TypeB"  -> DT_CharacterCreationMeshPresetTable_Body
                                    .SkeletalMesh   (TypeA is the FEMALE rig,
                                    TypeB the MALE one — per the table, not per
                                    the name)
  HeadMeshName  "Type26"         -> ..._Head.SkeletalMesh (female) /
                                    .SkeletalMesh_MaleHead (male)
  HairMeshName  "Type18"         -> ..._Hair.SkeletalMesh
  Equipment / skin item ids      -> ..._Equipments.SkeletalMeshMap, which is
                                    keyed by the same TypeA/TypeB body id.

Display rule (the game's own): OverrideEquipmentInfo (the cosmetic SKIN) wins
over the actually-equipped item when it is set. "Naked_Head" is not a row in the
table — it means "no head equipment", i.e. show the hair.

Emits c4players.json (a palx target list) and player_parts.json (look -> part
list) for the scene builder.
"""
import json, os, sys
from collections import OrderedDict

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
DT = json.load(open(f"{SP}/datatables.json"))
BODY = DT["DT_CharacterCreationMeshPresetTable_Body.uasset"]
HEAD = DT["DT_CharacterCreationMeshPresetTable_Head.uasset"]
HAIR = DT["DT_CharacterCreationMeshPresetTable_Hair.uasset"]
EQUIP = DT["DT_CharacterCreationMeshPresetTable_Equipments.uasset"]


def objpath(v):
    """'/Game/A/B/SK_X.SK_X' -> '/Game/A/B/SK_X' (drop the object suffix)."""
    if not v:
        return None
    v = v.split(".")[0] if "." in v.split("/")[-1] else v
    return v or None


def ci(table, key):
    if key is None:
        return None
    for k in table:
        if k.lower() == str(key).lower():
            return table[k]
    return None


def mesh_map(row, bodyType):
    """SkeletalMeshMap flattened as 'TypeA=/Game/... | TypeB=/Game/...'."""
    if not row:
        return None
    raw = row.get("SkeletalMeshMap") or ""
    for part in raw.split(" | "):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip().lower() == str(bodyType).lower():
            return objpath(v.strip())
    return None


def resolve(look):
    """One PlayerCharacterMakeData -> ordered list of (slot, /Game path, colorKey)."""
    body_t = look.get("body") or "TypeA"
    is_male = str(body_t).lower() == "typeb"
    parts = OrderedDict()

    # torso: skin override > equipped armour > the bare body preset
    # A set OverrideEquipmentInfo (the cosmetic skin) REPLACES the equipped item
    # outright — including replacing it with nothing. "Naked_Head" is the save's
    # sentinel for that: it is not a row in the equipment table and has no asset
    # anywhere in the pak, so an override of Naked_Head means "no headgear, show
    # the hair", NOT "fall back to whatever is equipped".
    ov_body = look.get("ovBody")
    eq_body = look.get("eqBody")
    cand_body = ov_body if ov_body else eq_body
    torso = mesh_map(ci(EQUIP, cand_body), body_t) if cand_body else None
    if not torso:
        row = ci(BODY, body_t)
        torso = objpath(row.get("SkeletalMesh")) if row else None
    if torso:
        parts["body"] = (torso, "bodyColor")

    hrow = ci(HEAD, look.get("head"))
    if hrow:
        h = objpath(hrow.get("SkeletalMesh_MaleHead") if is_male else hrow.get("SkeletalMesh"))
        if not h:
            h = objpath(hrow.get("SkeletalMesh"))
        if h:
            parts["head"] = (h, "bodyColor")

    # head equipment: skin override > equipped. "Naked_Head" is not a table row
    # and means "nothing on the head", so the hair shows instead.
    ov_head, eq_head = look.get("ovHead"), look.get("eqHead")
    cand_head = ov_head if ov_head else eq_head
    helm = mesh_map(ci(EQUIP, cand_head), body_t) if cand_head else None
    if helm:
        parts["headEquip"] = (helm, None)
    else:
        arow = ci(HAIR, look.get("hair"))
        if arow:
            a = objpath(arow.get("SkeletalMesh"))
            if a:
                parts["hair"] = (a, "hairColor")
    return parts


# DELIBERATELY NOT TINTING. PlayerCharacterMakeData's HairColor / BodyColor /
# EyeColor / BrowColor / BodySubsurfaceColor are stored as LinearColors but they
# are NOT literal colours: across all four players the R channel sits at ~0
# (0.000, -0.004, -0.372) while G and B run above 1.0 (1.07, 1.29, 1.59). Those
# are out of range for an sRGB colour and exactly what a (hue-shift, saturation,
# value) parameter triple looks like — and the game's own character-creation
# tables name the matching field `ShiftUIDisplayEyeColor`, i.e. a SHIFT. Turning
# them into an RGB swatch would require the player material graph, which we do
# not have; clamping them (which is what a naive read does) produced flat cyan
# for every player, which is simply wrong. So the parts are rendered untinted and
# the raw recorded triple is carried through for provenance instead of being
# guessed at.
def shift_of(c):
    return None if not c else [round(v, 5) for v in c[:3]]


def main():
    idx = json.load(open(f"{SP}/player_index.json"))
    looks = {}
    for uid8, d in idx["players"].items():
        for a in d["appearance"]:
            key = json.dumps({k: a[k] for k in
                              ("body", "head", "hair", "eqBody", "eqHead", "ovHead", "ovBody")},
                             sort_keys=True)
            looks[key] = a
    print(f"distinct player looks across the whole history: {len(looks)}")

    targets, parts_out, missing = {}, {}, []
    for key, look in looks.items():
        p = resolve(look)
        entry = []
        for slot, (path, colorKey) in p.items():
            name = path.split("/")[-1]
            targets[name] = path
            entry.append({"slot": slot, "mesh": name,
                          "url": f"/player_meshes/{name}.glb",
                          "color": None,
                          "colorShift": shift_of(look.get(colorKey)) if colorKey else None})
        parts_out[key] = entry
        for slot in ("body", "head"):
            if slot not in p:
                missing.append((slot, key))
    if missing:
        print(f"WARNING unresolved slots: {missing[:5]} ({len(missing)} total)")

    json.dump([{"name": n, "meshPath": p, "kind": "SK", "outDir": "player_meshes"}
               for n, p in sorted(targets.items())],
              open(f"{SP}/c4players.json", "w"), indent=1)
    json.dump(parts_out, open(f"{SP}/player_parts.json", "w"))
    print(f"distinct meshes to extract: {len(targets)} -> c4players.json")
    for n, p in sorted(targets.items()):
        print(f"   {n:44s} {p}")


if __name__ == "__main__":
    main()
