"""Per-snapshot PLAYER index: who the four players were, and where the save says
they were, at every recorded moment of this world's history.

Everything here is read verbatim out of world/current/Players/<UID>.sav in each
snapshot:
  - PlayerCharacterMakeData: BodyMeshName / HeadMeshName / HairMeshName,
    EquipmentBodyMeshName / EquipmentHeadMeshName, OverrideEquipmentInfo
    (Head/Body skins), HairColor / BrowColor / BodyColor / BodySubsurfaceColor /
    EyeColor (LinearColor RGBA), EyeMaterialName, VoiceID.
  - LastTransform: the player's recorded world Transform (translation cm +
    rotation quaternion). NOTE this is "where the save last put this player",
    i.e. their position at logout / at the moment the snapshot was written — it
    is NOT a position at the moment any particular piece was built.

Speed trick: the .sav files are git-LFS tracked, so `git show <commit>:<path>`
returns a ~130-byte POINTER whose oid is the content hash. Snapshots where a
player did not change produce the identical oid, so we only smudge+decode each
DISTINCT blob once (1229 snapshots x 4 players collapses to a few hundred real
decodes). That is also the honest way to answer "did their appearance change?" —
a single oid across the whole history means the bytes never changed.

Output: player_index.json
  {"players": {uid: {"appearance": [{"from":ts,"to":ts, ...fields}],
                     "transform":  [{"from":ts,"to":ts,"x","y","z","qz","qw"}]}},
   "snapshots": [ts,...]}
"""
import json, os, subprocess, sys, time
from collections import defaultdict

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("PALTL_REPO") or os.path.expanduser("~/Palworld")
PLAYER_DIR = "world/current/Players"


def list_player_files():
    out = subprocess.run(["git", "-C", REPO, "ls-tree", "--name-only", "HEAD", PLAYER_DIR + "/"],
                         capture_output=True, text=True).stdout.split()
    return [p for p in out if p.endswith(".sav") and "_dps" not in p]


def batch_pointers(commits, paths):
    """One `git cat-file --batch` pass: (ts, path) -> lfs oid (or raw sha for
    non-pointer blobs). Cheap because LFS pointers are ~130 bytes."""
    req, keys = [], []
    for c, ts in commits:
        for p in paths:
            req.append(f"{c}:{p}")
            keys.append((ts, p))
    proc = subprocess.Popen(["git", "-C", REPO, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = proc.communicate(("\n".join(req) + "\n").encode())
    res = {}
    pos = 0
    for key in keys:
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].decode(errors="replace")
        pos = nl + 1
        if header.endswith("missing") or " " not in header:
            continue
        size = int(header.split()[-1])
        body = out[pos:pos + size]
        pos += size + 1
        oid = None
        for line in body.split(b"\n"):
            if line.startswith(b"oid sha256:"):
                oid = line.split(b":", 1)[1].decode()
                break
        res[key] = oid or ("raw:" + header.split()[0])
    return res


def smudge(commit, path):
    ptr = subprocess.run(["git", "-C", REPO, "show", f"{commit}:{path}"], capture_output=True).stdout
    return subprocess.run(["git", "-C", REPO, "lfs", "smudge"], input=ptr, capture_output=True).stdout


def parse(raw):
    import ooz  # noqa: F401
    from palworld_save_tools.gvas import GvasFile
    from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
    from palworld_save_tools.palsav import decompress_sav_to_gvas
    gvas, _ = decompress_sav_to_gvas(raw)
    sd = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
        .dump()["properties"]["SaveData"]["value"]
    mk = sd.get("PlayerCharacterMakeData", {}).get("value", {})

    def name(k):
        return mk.get(k, {}).get("value")

    def col(k):
        v = mk.get(k, {}).get("value")
        return None if v is None else [v["r"], v["g"], v["b"], v["a"]]

    ov = mk.get("OverrideEquipmentInfo", {}).get("value", {})
    appearance = {
        "body": name("BodyMeshName"), "head": name("HeadMeshName"), "hair": name("HairMeshName"),
        "eqBody": name("EquipmentBodyMeshName"), "eqHead": name("EquipmentHeadMeshName"),
        "ovHead": ov.get("Head", {}).get("value"), "ovBody": ov.get("Body", {}).get("value"),
        "eyeMat": name("EyeMaterialName"), "voice": name("VoiceID"),
        "hairColor": col("HairColor"), "browColor": col("BrowColor"),
        "bodyColor": col("BodyColor"), "bodySubsurface": col("BodySubsurfaceColor"),
        "eyeColor": col("EyeColor"),
    }
    # LastTransform is NOT always populated: some snapshots carry a
    # LastTransform struct with no Rotation/Translation at all (the player was
    # not resident in the world when the save was written). Those snapshots
    # yield transform=None and the player is simply not placed for them —
    # never back-filled from a neighbouring snapshot.
    transform = None
    try:
        lt = sd["LastTransform"]["value"]
        t = lt["Translation"]["value"]
        r = lt["Rotation"]["value"]
        transform = {"x": round(t["x"], 1), "y": round(t["y"], 1), "z": round(t["z"], 1),
                     "qx": round(r["x"], 6), "qy": round(r["y"], 6),
                     "qz": round(r["z"], 6), "qw": round(r["w"], 6)}
    except (KeyError, TypeError):
        transform = None
    return appearance, transform


def _decode(item):
    (p, oid), c = item
    try:
        return ((p, oid), parse(smudge(c, p)))
    except Exception:
        return ((p, oid), (None, None))


def runs(series):
    """[(ts, value)] sorted -> [{'from':ts,'to':ts, **value}] merging equal runs."""
    out = []
    for ts, v in series:
        if out and out[-1]["_v"] == v:
            out[-1]["to"] = ts
            continue
        out.append({"from": ts, "to": ts, "_v": v})
    return [{**r["_v"], "from": r["from"], "to": r["to"]} for r in out if r["_v"] is not None]


def main():
    commits = [l.split() for l in open(f"{SP}/commits.txt")]
    commits = sorted(((c, int(t)) for c, t in commits), key=lambda x: x[1])
    paths = list_player_files()
    print(f"players: {[p.split('/')[-1] for p in paths]}")
    print(f"snapshots: {len(commits)}", flush=True)

    t0 = time.time()
    ptr = batch_pointers(commits, paths)
    print(f"pointers read in {time.time()-t0:.0f}s; entries={len(ptr)}", flush=True)

    # commit that first exhibits each distinct (path, oid) — decode once each
    firstcommit = {}
    for c, ts in commits:
        for p in paths:
            oid = ptr.get((ts, p))
            if oid and (p, oid) not in firstcommit:
                firstcommit[(p, oid)] = c
    print(f"distinct player blobs to decode: {len(firstcommit)} "
          f"(vs {len(commits)*len(paths)} naive)", flush=True)

    from multiprocessing import Pool
    items = list(firstcommit.items())
    cache = {}
    with Pool(3) as pool:
        for i, (key, val) in enumerate(pool.imap(_decode, items, chunksize=8)):
            cache[key] = val
            if (i + 1) % 200 == 0:
                print(f"  decoded {i+1}/{len(items)} {time.time()-t0:.0f}s", flush=True)
    bad = sum(1 for v in cache.values() if v[0] is None)
    notrans = sum(1 for v in cache.values() if v[0] is not None and v[1] is None)
    print(f"  decode failures={bad}  blobs with NO LastTransform={notrans}", flush=True)

    players = {}
    for p in paths:
        uid = p.split("/")[-1][:-4].lower()
        uid8 = uid[:8]
        appear, trans = [], []
        for c, ts in commits:
            oid = ptr.get((ts, p))
            if not oid:
                continue
            a, t = cache.get((p, oid), (None, None))
            appear.append((ts, a))
            trans.append((ts, t))
        players[uid8] = {"uid": uid, "file": p.split("/")[-1],
                         "appearance": runs(appear), "transform": runs(trans),
                         "distinctBlobs": len({ptr.get((ts, p)) for _, ts in commits} - {None})}

    out = {"players": players, "snapshots": [ts for _, ts in commits]}
    json.dump(out, open(f"{SP}/player_index.json", "w"))
    print(f"\n-> player_index.json ({os.path.getsize(SP+'/player_index.json')//1024} KB) "
          f"in {time.time()-t0:.0f}s")
    for uid8, d in players.items():
        print(f"  {uid8}  blobs={d['distinctBlobs']:4d}  "
              f"appearance runs={len(d['appearance'])}  transform runs={len(d['transform'])}")
        if d["appearance"]:
            a = d["appearance"][0]
            print(f"      first look: body={a['body']} head={a['head']} hair={a['hair']} "
                  f"eqBody={a['eqBody']} eqHead={a['eqHead']} ov={a['ovBody']}/{a['ovHead']}")
            b = d["appearance"][-1]
            if len(d["appearance"]) > 1:
                print(f"      last  look: body={b['body']} head={b['head']} hair={b['hair']} "
                      f"eqBody={b['eqBody']} eqHead={b['eqHead']} ov={b['ovBody']}/{b['ovHead']}")


if __name__ == "__main__":
    main()
