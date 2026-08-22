"""Read the real player NAMES out of the save's guild rosters and fold them into
union/avatars.json.

Source: worldSaveData.GroupSaveDataMap -> each group's RawData -> players[] ->
player_info.player_name, keyed by that entry's own player_uid. These are the
names the game itself stores; nothing is hardcoded.

THE 00000000 QUESTION, settled from the data rather than assumed.
`build_player_uid` uses an all-zero UID as its "no owner" sentinel, and
build_actor_scenes.py already maps that exact value to None (an unattributed
piece). But the guild roster ALSO lists a real member whose UID merely STARTS
with eight zeros:

    00000000-0000-0000-0000-000000000000   x440   sentinel -> unattributed
    00000000-0000-0000-0000-000000000001   x293   a real player

counted directly off the union map_objects. So the 293 pieces that survive into
builders_<b>.json under the short key "00000000" are NOT system-placed — they
are that real player's work, and they get an avatar and a name like anyone else.
The two are only ambiguous if you truncate to 8 characters before testing for
the sentinel, which is exactly the mistake this comment exists to prevent.

Names are taken from the LIVE world (the one whose Players/ directory holds the
four UIDs the history actually references). A player with no roster entry keeps
name=null and simply renders without a tag — never with an invented one.
"""
import glob
import json
import os
import sys
from collections import Counter

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
sys.path.insert(0, SP + "/pst/src")
# palworld_save_tools lives in whatever venv you installed it into; point
# PALTL_SITE_PACKAGES at it if it is not already on sys.path.
_extra = os.environ.get("PALTL_SITE_PACKAGES")
if _extra:
    sys.path.insert(0, _extra)

import ooz  # noqa: F401
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
from palworld_save_tools.palsav import decompress_sav_to_gvas

ZERO = "00000000-0000-0000-0000-000000000000"
OUT = f"{SP}/mappal/public/union"
LEVELS = sys.argv[1:] or [
    f"{SP}/nas/64EE4B2C4C81F4912BF109850820D9BA/Level.sav",   # live world first
    f"{SP}/nas/47270A4B4C8A1C9F91E242B00F36B2DA/Level.sav",
]


def roster(level):
    gvas, _ = decompress_sav_to_gvas(open(level, "rb").read())
    wsd = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
        .dump()["properties"]["worldSaveData"]["value"]
    out = {}
    for entry in wsd["GroupSaveDataMap"]["value"]:
        raw = entry["value"]["RawData"]["value"]
        if not isinstance(raw, dict):
            continue
        for p in raw.get("players", []) or []:
            nm = (p.get("player_info") or {}).get("player_name")
            if nm:
                out.setdefault(str(p.get("player_uid", "")).lower(), nm)
    return out


# Which FULL uids actually built anything, straight off the map objects.
built = Counter()
for f in sorted(glob.glob(f"{OUT}/union_*.json")):
    for m in json.load(open(f))["map_objects"]:
        built[str(m["Model"]["value"]["RawData"]["value"].get("build_player_uid")).lower()] += 1

print("full build_player_uid values across the four bases:")
for u, n in built.most_common():
    print(f"  {u}  x{n}{'   <- all-zero sentinel: unattributed' if u == ZERO else ''}")

# First roster wins (live world listed first).
names_by_full = {}
for lv in LEVELS:
    if not os.path.exists(lv):
        continue
    for u, nm in roster(lv).items():
        names_by_full.setdefault(u, (nm, os.path.basename(os.path.dirname(lv))))

print("\nroster names:")
for u, (nm, w) in sorted(names_by_full.items()):
    print(f"  {u}  {nm!r}  (from {w[:8]})")

# Short key must match build_actor_scenes.py: sentinel -> unattributed, else [:8].
short_names = {}
for u, n in built.items():
    if u == ZERO:
        continue
    hit = names_by_full.get(u)
    if hit:
        short_names[u[:8]] = hit[0]

AV = f"{OUT}/avatars.json"
doc = json.load(open(AV))
players = doc["players"]
for uid, v in list(players.items()):
    runs = v["runs"] if isinstance(v, dict) else v
    players[uid] = {"name": short_names.get(uid), "runs": runs}
doc["names"] = short_names
json.dump(doc, open(AV, "w"), indent=1)

print(f"\nwrote {AV}")
for uid, v in players.items():
    print(f"  {uid}: name={v['name']!r} runs={len(v['runs'])}")
missing = [u for u, v in players.items() if not v["name"]]
if missing:
    print(f"no roster name (render without a tag, never invented): {missing}")
