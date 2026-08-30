"""Resolve every CharacterID actually present in this world's save history.

The broad Pal table manifest covers authored Pal ids, while captured human NPCs
are stored under weapon/loadout-specific save ids (for example Ninja_Bowgun)
that intentionally share a cooked NPC body.  Boss variants likewise often share
the normal species mesh.  This pass joins those real save ids to real cooked
assets and emits only the 249 species/characters this world actually contains.
"""
import collections
import json
import os
import re

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))

ALIASES = {
    "Hunter_Bat": "NPC_Hunter",
    "Hunter_Handgun": "NPC_Hunter",
    "Guard_Rifle": "NPC_Male_Soldier",
    "DeathPenalty_guide": "NPC_DeathPenalty_guide",
    "Negotiator": "NPC_Negotiator",
    "SalesPerson_Wander": "NPC_SalesPerson_Caravan_01",
    "Visitor_Recruiter": "NPC_Recruiter",
    "Male_DarkTrader01": "NPC_Male_DarkTrader",
    "Male_DarkTrader02": "NPC_MedalTrader",
    "PalDealer": "NPC_Male_Trader",
    "PalPassive_Doctor": "NPC_Doctor",
    "Believer_CrossBow": "NPC_Believer",
    "Ninja_Bowgun": "NPC_Male_Ninja01",
    "Female_Soldier01": "NPC_Female_Soldier",
    "BOSS_Male_Soldier04": "NPC_Male_Soldier04",
    "BOSS_Hunter_Fat_GatlingGun": "NPC_Hunter_Fat",
    "BOSS_Believer_Fat_GiantClub": "NPC_Believer_Fat",
    "GrassBoss": "NPC_GrassBoss",
    "FireCult_FlameThrower": "NPC_FireCult",
    "Escort_PalTamer01": "NPC_Escort_PalTamer01",
    "Male_NinjaElite01": "NPC_Male_NinjaElite01",
    "BountyTrader": "NPC_BountyTrader",
    "Male_Scientist01_LaserRifle": "NPC_Male_Scientist01",
    "GYM_ElecPanda_Otomo": "ElecPanda",
}

# A few common captured humans use save ids with no row in DT_PalBPClass.  These
# paths are not guesses: BP_NPC_PalDealer and the corresponding NPC blueprints
# were walked with palxtex --bpmesh, and these are their CharacterMesh0 assets.
DIRECT = {
    "PalDealer": "/Game/Pal/Model/Character/NPC/SK_NPC_Male_Trader01/SK_NPC_Male_Trader01",
    "Male_DarkTrader01": "/Game/Pal/Model/Character/NPC/SK_NPC_Male_DarkTrader01/SK_NPC_Male_DarkTrader01",
    "Male_DarkTrader02": "/Game/Pal/Model/Character/NPC/SK_NPC_Male_DarkTrader02/SK_NPC_Male_DarkTrader02",
    "MobuCitizen": "/Game/Pal/Model/Character/NPC/SK_NPC_Male_People01/SK_NPC_Male_People01",
    "BOSS_Hunter_Fat_GatlingGun": "/Game/Pal/Model/Character/NPC/SK_NPC_Male_HunterFat01/SK_NPC_Male_HunterFat01",
}


def main():
    index = json.load(open(f"{SP}/pal_index.json"))
    broad = json.load(open(f"{SP}/pal_manifest.json"))
    files = [line.strip() for line in open(f"{SP}/pak_character_files.txt")]
    monster = {}
    for path in files:
        if (not path.endswith(".uasset") or "/Model/Character/Monster/" not in path
                or "/Skeleton/" in path or "PhysicsAsset" in path):
            continue
        leaf = os.path.basename(path)[:-7]
        if leaf.startswith("SK_") and not leaf.endswith("_Skeleton"):
            monster.setdefault(leaf.lower(), []).append(path[:-7])

    counts = collections.Counter(p["char"] for p in index["pals"])
    out = {}
    for char, count in sorted(counts.items()):
        rec = None
        candidates = [char]
        alias = ALIASES.get(char)
        if alias:
            candidates.append(alias)
        stripped = re.sub(r"^(BOSS_|PREDATOR_|GYM_)", "", char, flags=re.I)
        candidates.append(stripped)
        # Dark boss variants can be a material-only variant of the base model.
        candidates.append(re.sub(r"_(Dark|Ice|Electric)$", "", stripped, flags=re.I))
        for key in candidates:
            hit = broad.get(key)
            if hit and hit.get("resolved") and hit.get("meshPath"):
                rec = dict(hit)
                rec["resolvedFrom"] = key
                rec["method"] = "shipped DT_PalBPClass blueprint -> visible CharacterMesh0"
                break
        if rec is None:
            for key in candidates:
                paths = monster.get(("SK_" + key).lower()) or []
                if len(paths) == 1:
                    path = paths[0]
                    rec = {"meshName": os.path.basename(path), "meshPath": path,
                           "resolved": True, "resolvedFrom": key,
                           "method": "exact SK_<CharacterID> cooked monster asset"}
                    break
        if rec is None and char in DIRECT:
            path = DIRECT[char]
            rec = {"meshName": path.rsplit("/", 1)[-1], "meshPath": path,
                   "resolved": True, "resolvedFrom": char,
                   "method": "palxtex blueprint CharacterMesh0 walk"}
        if rec is None:
            rec = {"meshName": None, "meshPath": None, "resolved": False,
                   "method": "no exact cooked character mesh found"}
        rec["characterId"] = char
        rec["instancesInHistory"] = count
        out[char] = rec

    target = f"{SP}/pal_actual_manifest.json"
    json.dump(out, open(target, "w"), indent=1)
    missing = [(k, v["instancesInHistory"]) for k, v in out.items() if not v["resolved"]]
    print(f"wrote {target}: {len(out)-len(missing)}/{len(out)} actual CharacterIDs resolved")
    print(f"unresolved instances={sum(n for _, n in missing)}: {missing}")


if __name__ == "__main__":
    main()
