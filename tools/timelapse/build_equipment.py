"""Build per-base, time-aware player wardrobe files from real save data.

Armor containers come from equipment_scan.json, produced while decoding every
historical Level.sav.  Body type and the game's mirror appearance override come
from PlayerCharacterMakeData in player_index.json and the earlier NAS Player
saves.  The shipped equipment preset table resolves each item/body-type pair to
its real cooked mesh.  Weapons and food are audited but intentionally not drawn:
the save records the loadout, not the selected hand/slot.
"""
import json
import os

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
MAPPAL = os.environ.get("MAPPAL_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
PUB = os.path.join(MAPPAL, "public")
UNION = os.path.join(PUB, "union")


def load(name, default=None):
    try:
        return json.load(open(os.path.join(SP, name)))
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def normalized(value):
    return None if value in (None, "", "None") else value


def mesh_name(asset):
    if not asset or asset == "None":
        return None
    return asset.split(".", 1)[0].rsplit("/", 1)[-1]


def mesh_map(row):
    out = {}
    for pair in row.get("SkeletalMeshMap") or []:
        key = pair.get("k", pair.get("Key"))
        value = pair.get("v", pair.get("Value"))
        if isinstance(value, dict):
            value = value.get("AssetPathName") or value.get("assetPathName")
        name = mesh_name(value)
        if key and name:
            out[key] = name
    return out


def hair_socket(row, body_type):
    for pair in row.get("HairAttachSocketNameMap") or []:
        key = pair.get("k", pair.get("Key"))
        value = pair.get("v", pair.get("Value"))
        if isinstance(value, dict):
            value = value.get("value") or value.get("Name")
        if key == body_type:
            return normalized(value)
    return None


def field_at(intervals, observations, ts, key, allow_extrapolate):
    """Return (value, provenance) without inventing a change between saves."""
    hits = [r for r in intervals if r["from"] <= ts <= r["to"]]
    if hits:
        return normalized(hits[-1].get(key)), "recorded"
    rows = sorted((r["ts"], normalized(r.get(key))) for r in observations if key in r)
    if not rows:
        return None, "unknown"
    before = [r for r in rows if r[0] <= ts]
    after = [r for r in rows if r[0] >= ts]
    if before and after and before[-1][1] == after[0][1]:
        return before[-1][1], "bracketed"
    values = {v for _, v in rows}
    if allow_extrapolate and len(values) == 1:
        return rows[0][1], "extrapolated"
    return None, "unknown"


def source_join(*sources):
    # One unknown field makes the combined mirror state unknown.  Otherwise the
    # weakest evidence is reported; this is surfaced in the renderer audit.
    rank = {"recorded": 0, "bracketed": 1, "extrapolated": 2, "unknown": 3}
    return max(sources, key=lambda s: rank.get(s, 3))


def distinct_loadouts(samples, uid, slot, lo, hi):
    seen = set()
    for ts, players in samples:
        if not (lo <= ts <= hi):
            continue
        for item in (players.get(uid) or {}).get(slot) or []:
            if len(item) > 1 and normalized(item[1]):
                seen.add(item[1])
    return sorted(seen)


def main():
    scan = load("equipment_scan.json")
    samples = sorted((int(ts), players or {}) for ts, players in scan["samples"])
    players = load("player_index.json")["players"]
    nas = load("equipment_nas_appearance.json", {"players": {}}).get("players", {})
    manifest = json.load(open(os.path.join(UNION, "manifest.json")))
    avatars = json.load(open(os.path.join(UNION, "avatars.json"))).get("players", {})
    tables_doc = load("equipment_tables.json")
    rows = next(iter(tables_doc.values()))

    def look(uid, ts):
        intervals = players.get(uid, {}).get("appearance", [])
        observations = nas.get(uid, [])
        body, body_src = field_at(intervals, observations, ts, "body", True)
        ov_body, ov_body_src = field_at(intervals, observations, ts, "ovBody", False)
        ov_head, ov_head_src = field_at(intervals, observations, ts, "ovHead", False)
        eq_body, eq_body_src = field_at(intervals, observations, ts, "eqBody", False)
        eq_head, eq_head_src = field_at(intervals, observations, ts, "eqHead", False)
        return {
            "bodyType": body or "TypeA",
            "bodyTypeSource": body_src,
            "appearanceOverrideSource": source_join(ov_body_src, ov_head_src),
            "appearanceOverride": {
                "body": ov_body,
                "head": ov_head,
                "equipmentBodyMeshName": eq_body,
                "equipmentHeadMeshName": eq_head,
                "equipmentMeshNameSource": source_join(eq_body_src, eq_head_src),
            },
        }

    def equipped(items, body_type):
        out = []
        unresolved = []
        for slot_index, item_id, count, dynamic_id, *_ in items or []:
            # PlayerEquipArmorContainer has nine fixed slots.  Only 0=head and
            # 1=body are visible clothing.  Slots 2..8 are pendants, shields,
            # gliders and sphere modules; auditing them is useful, but trying to
            # resolve them through the clothing table creates false failures and
            # would put gameplay props on the avatar without an authored socket.
            if slot_index not in (0, 1):
                continue
            row = rows.get(item_id)
            if row is None:
                unresolved.append(item_id)
                continue
            mesh = mesh_map(row).get(body_type)
            if not mesh:
                unresolved.append(item_id + "/" + body_type)
                continue
            rec = {"itemId": item_id, "mesh": mesh, "containerSlot": slot_index,
                   "count": count, "dynamicId": dynamic_id}
            if mesh.startswith("SK_HeadEquip"):
                rec["slot"] = "head"
                if row.get("IsHairAttachAccessory"):
                    rec["attach"] = "socket"
                    rec["socket"] = hair_socket(row, body_type)
                    if not rec["socket"]:
                        unresolved.append(item_id + "/missing-socket")
                        continue
                else:
                    rec["attach"] = "skeleton"
            elif "_Outfit_" in mesh:
                rec["slot"] = "body"
                rec["attach"] = "bodyReplace"
            else:
                unresolved.append(item_id + "/unclassified:" + mesh)
                continue
            rec["haveGlb"] = os.path.exists(os.path.join(PUB, "equipment_meshes_posed", mesh + ".glb"))
            rec["haveStandingGlb"] = os.path.exists(os.path.join(PUB, "equipment_meshes_posed_standing", mesh + ".glb"))
            out.append(rec)
        return out, sorted(set(unresolved))

    uids = sorted(players)
    for base, meta in manifest.items():
        lo, hi = int(meta["t0"]), int(meta["t1"])
        doc_players = []
        for uid in uids:
            raw_states = []
            for index, (ts, snapshot_players) in enumerate(samples):
                if ts > hi or (index + 1 < len(samples) and samples[index + 1][0] <= lo):
                    continue
                period_from = max(lo, ts)
                period_to = min(hi, samples[index + 1][0] - 1 if index + 1 < len(samples) else hi)
                if period_from > period_to:
                    continue
                player_slots = snapshot_players.get(uid)
                if player_slots is None:
                    continue
                state = look(uid, ts)
                armor, unresolved = equipped(player_slots.get("armor") or [], state["bodyType"])
                state.update({"from": period_from, "to": period_to,
                              "equipped": armor, "unresolvedArmor": unresolved})
                raw_states.append(state)

            # Collapse adjacent identical visual/provenance states.  Weapon and
            # food churn are deliberately excluded because neither is rendered.
            runs = []
            for state in raw_states:
                value = {k: v for k, v in state.items() if k not in ("from", "to")}
                if runs and runs[-1]["to"] + 1 == state["from"] and runs[-1]["_value"] == value:
                    runs[-1]["to"] = state["to"]
                else:
                    runs.append({"from": state["from"], "to": state["to"],
                                 "_value": value})
            runs = [{"from": r["from"], "to": r["to"], **r["_value"]} for r in runs]
            if not runs:
                continue
            doc_players.append({
                "uid": uid,
                "name": (avatars.get(uid) or {}).get("name") or uid,
                "runs": runs,
                "weaponLoadoutSeen": distinct_loadouts(samples, uid, "weapon", lo, hi),
                "foodEquipSeen": distinct_loadouts(samples, uid, "food", lo, hi),
                "nonClothingArmorSlotsSeen": sorted({
                    item[1]
                    for ts, snapshot_players in samples if lo <= ts <= hi
                    for item in ((snapshot_players.get(uid) or {}).get("armor") or [])
                    if len(item) > 1 and item[0] not in (0, 1) and normalized(item[1])
                }),
            })

        doc = {
            "base": base,
            "name": meta["name"],
            "source": "Level.sav ItemContainerSaveData + PlayerCharacterMakeData + shipped equipment preset table",
            "note": __doc__.strip(),
            "players": doc_players,
            "snapshotsSkippedDuringDecode": scan.get("skipped", 0),
        }
        target = os.path.join(UNION, f"equipment_{base}.json")
        json.dump(doc, open(target, "w"), indent=1)
        run_count = sum(len(p["runs"]) for p in doc_players)
        missing = sorted({m for p in doc_players for r in p["runs"] for m in r["unresolvedArmor"]})
        print(f"{base} {meta['name']}: players={len(doc_players)} wardrobe runs={run_count} unresolved={missing}")


if __name__ == "__main__":
    main()
