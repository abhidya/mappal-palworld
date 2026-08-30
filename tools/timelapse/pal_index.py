"""Per-snapshot Pal index, built the same way build_index.json was built for
structures: walk every Level.sav we hold (git-LFS history of $PALTL_REPO
plus the NAS backup sets) and record, for each Pal, where the save says it
was at that moment.

WHAT IS REAL DATA HERE
  - instance id, CharacterID, Level, Gender, NickName: verbatim from
    CharacterSaveParameterMap[i].value.RawData.object.SaveParameter.
  - position: verbatim SaveParameter.LastJumpedLocation (a real recorded
    FVector, in Unreal cm). Palworld does NOT persist a live Pal transform;
    LastJumpedLocation is the only recorded world position on the record and
    means "where this Pal last jumped", not "where it is standing". It is used
    as-is. Nothing is jittered, scattered, or synthesised. A Pal with no
    LastJumpedLocation is simply absent from this index.
  - base assignment: the base camp whose BaseCampSaveData.transform.translation
    is within area_range (horizontal) of that recorded position, nearest wins.
    area_range comes from the save too.
  - first/last: real snapshot timestamps (git commit time / file mtime), same
    clock build_index.json uses.

Output: pal_index.json
  {"bases": {b8: {x,y,z,area_range,name}},
   "snapshots": [ts,...],                       # every snapshot successfully read
   "pals": [{"id","char","level","gender","nick","base",
             "first","last","track":[[ts,x,y,z],...]}]}
  `track` is de-duplicated: a sample is emitted only when the recorded position
  actually changed, so a Pal that never jumped again carries one sample.
"""
import json, os, sys, glob, time, subprocess, hashlib, gzip
from collections import defaultdict
from multiprocessing import Pool

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("PALTL_REPO") or os.path.expanduser("~/Palworld")
LINEAGE_GUILD = "017a45a0"   # same lineage filter merge_all.py uses
try:
    EQUIP_CONTAINERS = json.load(open(f"{SP}/equipment_containers.json"))
except FileNotFoundError:
    EQUIP_CONTAINERS = {}


def read_raw(kind, ref):
    if kind == "git":
        blob = subprocess.run(["git", "-C", REPO, "show", f"{ref}:world/current/Level.sav"],
                              capture_output=True).stdout
        return subprocess.run(["git", "-C", REPO, "lfs", "smudge"],
                              input=blob, capture_output=True).stdout
    return open(ref, "rb").read()


def work(job):
    content_id, kind, ref = job
    try:
        import ooz  # noqa: F401
        from palworld_save_tools.gvas import GvasFile
        from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
        from palworld_save_tools.palsav import decompress_sav_to_gvas
        raw = read_raw(kind, ref)
        if len(raw) < 100000:
            return (content_id, None, None, None)
        gvas, _ = decompress_sav_to_gvas(raw)
        w = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
            .dump()["properties"]["worldSaveData"]["value"]

        guilds = {str(g["value"]["RawData"]["value"].get("group_id"))[:8]
                  for g in w["GroupSaveDataMap"]["value"]
                  if g["value"]["RawData"]["value"].get("group_type") == "EPalGroupType::Guild"}
        if LINEAGE_GUILD not in guilds:
            return (content_id, None, None, None)  # a different playthrough in the backup set

        bases = {}
        for b in w["BaseCampSaveData"]["value"]:
            rd = b["value"]["RawData"]["value"]
            tr = rd["transform"]["translation"]
            bases[str(b["key"])[:8]] = (tr["x"], tr["y"], tr["z"], float(rd.get("area_range", 0)))

        pals = []
        for e in w["CharacterSaveParameterMap"]["value"]:
            sp = e["value"]["RawData"]["value"]["object"]["SaveParameter"]["value"]
            if sp.get("IsPlayer", {}).get("value"):
                continue
            loc = sp.get("LastJumpedLocation")
            if not loc:
                continue
            v = loc["value"]
            iid = str(e["key"]["InstanceId"]["value"])
            pals.append((
                iid,
                sp["CharacterID"]["value"],
                v["x"], v["y"], v["z"],
                (sp.get("Level") or {}).get("value", {}).get("value", 1),
                (sp.get("Gender") or {}).get("value", {}).get("value", ""),
                (sp.get("NickName") or {}).get("value", ""),
            ))
        equipment = {}
        if EQUIP_CONTAINERS:
            containers = {str(e["key"]["ID"]["value"]): e["value"]
                          for e in w["ItemContainerSaveData"]["value"]}
            for uid8, ids in EQUIP_CONTAINERS.items():
                rec = {}
                for slotname in ("armor", "weapon", "food"):
                    container = containers.get(ids[slotname])
                    if container is None:
                        continue
                    items = []
                    for slot in container["Slots"]["value"]["values"]:
                        rd = slot["RawData"]["value"]
                        static_id = rd["item"]["static_id"]
                        if not static_id or static_id == "None":
                            continue
                        items.append([
                            rd["slot_index"], static_id, rd["count"],
                            str(rd["item"]["dynamic_id"]["local_id_in_created_world"]),
                        ])
                    rec[slotname] = sorted(items)
                if rec:
                    equipment[uid8] = rec
        return (content_id, bases, pals, equipment)
    except Exception as e:
        return (content_id, None, str(e)[:120], None)


def git_content_ids(commits):
    """Return commit -> Level.sav content id in one cheap cat-file pass.

    Git-LFS commits usually contain a ~130-byte pointer, so the pointer oid is
    the identity of the actual save.  Identical oids are decoded only once.
    """
    specs = [f"{c}:world/current/Level.sav" for c in commits]
    proc = subprocess.Popen(["git", "-C", REPO, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = proc.communicate(("\n".join(specs) + "\n").encode())
    ids, pos = {}, 0
    for commit in commits:
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
        oid = next((line.split(b":", 1)[1].decode()
                    for line in body.splitlines() if line.startswith(b"oid sha256:")), None)
        ids[commit] = "lfs:" + oid if oid else "git:" + header.split()[0]
    return ids


def file_content_id(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "file:" + h.hexdigest()


def main():
    src = {}
    commit_rows = [line.split() for line in open(f"{SP}/commits.txt")]
    commit_ids = git_content_ids([c for c, _ in commit_rows])
    for c, t in commit_rows:
        src.setdefault(int(t), ("git", c))
    for pat in ("nas", "nasbk", "nasbk2", "nasbk3"):
        for p in glob.glob(f"{SP}/{pat}/**/Level.sav", recursive=True):
            src.setdefault(int(os.path.getmtime(p)), ("file", p))
    timeline = []
    unique = {}
    for ts, (kind, ref) in sorted(src.items()):
        content_id = commit_ids.get(ref) if kind == "git" else file_content_id(ref)
        if not content_id:
            content_id = f"missing:{kind}:{ref}"
        timeline.append((ts, content_id))
        unique.setdefault(content_id, (kind, ref))
    all_jobs = [(content_id, kind, ref) for content_id, (kind, ref) in unique.items()]
    cache_dir = f"{SP}/cache/pal_index"
    os.makedirs(cache_dir, exist_ok=True)

    def cache_path(content_id):
        return f"{cache_dir}/{hashlib.sha256(content_id.encode()).hexdigest()}.json.gz"

    cache = {}
    jobs = []
    for content_id, kind, ref in all_jobs:
        path = cache_path(content_id)
        try:
            with gzip.open(path, "rt") as f:
                cache[content_id] = json.load(f)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            jobs.append((content_id, kind, ref))
    print(f"snapshots: {len(timeline)}; distinct saves: {len(all_jobs)}; "
          f"cached: {len(cache)}; to decode: {len(jobs)}", flush=True)

    t0 = time.time()
    with Pool(int(os.environ.get("JOBS", "3"))) as pool:
        for done, (content_id, bases, pals, equipment) in enumerate(
                pool.imap(work, jobs, chunksize=2), 1):
            value = [bases, pals, equipment]
            cache[content_id] = value
            with gzip.open(cache_path(content_id), "wt") as f:
                json.dump(value, f, separators=(",", ":"))
            if done % 25 == 0:
                print(f"  decoded {done}/{len(jobs)} distinct saves {time.time()-t0:.0f}s", flush=True)

    base_meta = {}
    first, last, meta = {}, {}, {}
    track = defaultdict(list)          # iid -> [(ts,x,y,z)] deduped
    lastpos = {}
    snapshots = []
    equipment_samples = []
    done = 0
    skipped = 0
    for ts, content_id in timeline:
        done += 1
        bases, pals, equipment = cache.get(content_id, (None, None, None))
        if bases is None:
            skipped += 1
            continue
        snapshots.append(ts)
        equipment_samples.append([ts, equipment or {}])
        for b, v in bases.items():
            base_meta[b] = v
        for iid, cid, x, y, z, lvl, gen, nick in pals:
            if iid not in first:
                first[iid] = ts
            last[iid] = ts
            meta[iid] = (cid, lvl, gen, nick)
            p = (round(x, 1), round(y, 1), round(z, 1))
            if lastpos.get(iid) != p:
                lastpos[iid] = p
                track[iid].append([ts, p[0], p[1], p[2]])

    snapshots.sort()
    NAMES = {"07f13218": "Glass Tower", "16fca097": "Wooden Camp",
             "de44d9f4": "Stone Works", "5fed0024": "Lost Camp"}

    def owner(x, y):
        """Nearest base whose recorded area_range (horizontal) contains (x,y).
        Both the base centre and area_range are read straight from
        BaseCampSaveData; nothing here is a guessed radius."""
        best, bd = None, None
        for b, (bx, by, bz, r) in base_meta.items():
            d = ((x - bx) ** 2 + (y - by) ** 2) ** 0.5
            if d <= r and (bd is None or d < bd):
                best, bd = b, d
        return best

    out_pals = []
    for iid, tr in track.items():
        cid, lvl, gen, nick = meta[iid]
        # A Pal's base is decided per sample; the record's `base` is the base it
        # was inside for the majority of its samples, and `track` keeps every
        # sample with the base it was inside at that moment (null = outside every
        # base, e.g. out on an expedition or carried by the player).
        cnt = defaultdict(int)
        tr2 = []
        for ts, x, y, z in tr:
            b = owner(x, y)
            if b:
                cnt[b] += 1
            tr2.append([ts, x, y, z, b])
        home = max(cnt, key=cnt.get) if cnt else None
        out_pals.append({"id": iid, "char": cid, "level": lvl, "gender": gen,
                         "nick": nick, "base": home,
                         "first": first[iid], "last": last[iid], "track": tr2})

    out = {"bases": {b: {"x": v[0], "y": v[1], "z": v[2], "area_range": v[3],
                         "name": NAMES.get(b, b)} for b, v in base_meta.items()},
           "snapshots": snapshots, "pals": out_pals}
    json.dump(out, open(f"{SP}/pal_index.json", "w"))
    json.dump({"samples": equipment_samples, "skipped": skipped,
               "source": "same decoded Level.sav snapshots as pal_index.json"},
              open(f"{SP}/equipment_scan.json", "w"))

    print(f"\nsnapshots used={len(snapshots)} skipped={skipped}")
    print(f"pals with a recorded position at some point: {len(out_pals)}")
    per = defaultdict(int)
    for p in out_pals:
        per[p["base"]] += 1
    for b, n in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {NAMES.get(b, b) if b else '(outside every base)':22s} {n:4d} pals")
    print(f"bases seen: {[(b, NAMES.get(b,b)) for b in base_meta]}")
    print(f"-> {SP}/pal_index.json  ({os.path.getsize(SP+'/pal_index.json')//1024} KB) "
          f"in {time.time()-t0:.0f}s")
    print(f"-> {SP}/equipment_scan.json  {len(equipment_samples)} snapshots")


if __name__ == "__main__":
    main()
