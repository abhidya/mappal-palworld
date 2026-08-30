"""Read each player's equipment-container GUIDs from their real Player save.

The GUIDs are the join keys from Player ``InventoryInfo`` into the world's
``ItemContainerSaveData``.  They are emitted separately so the expensive
Level.sav history walk can collect player equipment while it is already
decoding each world snapshot for Pal tracks.
"""
import glob
import json
import os

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES


SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
PLAYER_DIR = os.environ.get("PALTL_PLAYER_DIR") or \
    "/Users/mannybhidya/Palworld/world/current/Players"


def read_player(path):
    gvas, _ = decompress_sav_to_gvas(open(path, "rb").read())
    saved = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
        .dump()["properties"]["SaveData"]["value"]
    inv = saved["InventoryInfo"]["value"]

    def container_id(field):
        return str(inv[field]["value"]["ID"]["value"])

    return {
        "armor": container_id("PlayerEquipArmorContainerId"),
        "weapon": container_id("WeaponLoadOutContainerId"),
        "food": container_id("FoodEquipContainerId"),
    }


def main():
    out = {}
    for path in sorted(glob.glob(f"{PLAYER_DIR}/*.sav")):
        if path.endswith("_dps.sav"):
            continue
        uid = os.path.basename(path)[:-4].lower()
        out[uid[:8]] = {"uid": uid, **read_player(path)}
    if not out:
        raise SystemExit(f"no player saves found under {PLAYER_DIR}")
    dest = f"{SP}/equipment_containers.json"
    json.dump(out, open(dest, "w"), indent=1)
    print(f"wrote {dest}: {len(out)} players")
    for uid, row in out.items():
        print(f"  {uid}: armor={row['armor']} weapon={row['weapon']} food={row['food']}")


if __name__ == "__main__":
    main()
