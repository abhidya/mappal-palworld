"""Build a TEMPORAL paint index: when each object actually got painted.

Object *existence* is already temporal (build_index.json's first/last, replayed
by timelapse.mjs). Paint was not: the union blueprints hold one snapshot's Paint
blob per object, so a piece painted days after it was placed would appear
already painted the instant it is built. This walks the same snapshot history
and records, per object, the timestamps at which its paint actually CHANGED.

Sources (identical to union_full.py / merge_all.py):
  * git LFS history of world/current/Level.sav in $PALTL_REPO
  * NAS backup trees nas/, nasbk/, nasbk2/, nasbk3/

Only the 24-byte Paint blob is read, via paint_scan.py's byte-level scan
(~0.65 s per snapshot instead of ~30 s for a full GVAS parse).

Output: paint_index.json
  {
    "scanned":   [ts, ...],            # every snapshot timestamp scanned, sorted
    "changes":   { instance_id: [[ts, [r,g,b,a]], ...] }
  }
An entry's colour is null when the object was observed UNPAINTED at that ts
(either before it was ever painted, or after the player stripped the paint).
The renderer resolves the colour at time t by taking the last change with
ts <= t; no change yet => no paint => normal material colour.
"""
import glob
import json
import os
import subprocess
import sys
import time
from multiprocessing import Pool

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("PALTL_REPO") or os.path.expanduser("~/Palworld")
sys.path.insert(0, SP)
sys.path.insert(0, SP + "/pst/src")


def sources():
    """(ts, kind, ref) for every snapshot we can read, de-duped by timestamp."""
    src = {}
    for line in open(f"{SP}/commits.txt"):
        c, t = line.split()
        src.setdefault(int(t), ("git", c))
    for pat in ("nas/**/Level.sav", "nasbk/**/Level.sav",
                "nasbk2/**/Level.sav", "nasbk3/**/Level.sav"):
        for p in glob.glob(f"{SP}/{pat}", recursive=True):
            src.setdefault(int(os.path.getmtime(p)), ("file", p))
    return sorted((ts, kind, ref) for ts, (kind, ref) in src.items())


_SRC = None


def src_label(ts):
    """Human-readable origin of a snapshot timestamp, for the audit output."""
    global _SRC
    if _SRC is None:
        _SRC = {t: (k, r) for t, k, r in sources()}
    kind, ref = _SRC.get(ts, ("?", "?"))
    return f"{kind}:{ref if kind == 'git' else os.path.relpath(ref, SP)}"


def work(job):
    ts, kind, ref = job
    try:
        import paint_scan
        if kind == "git":
            blob = subprocess.run(["git", "-C", REPO, "show", f"{ref}:world/current/Level.sav"],
                                  capture_output=True).stdout
            raw = subprocess.run(["git", "-C", REPO, "lfs", "smudge"],
                                 input=blob, capture_output=True).stdout
        else:
            raw = open(ref, "rb").read()
        if not raw:
            return (ts, None, None)
        gvas = paint_scan.decompress(raw)
        return (ts, paint_scan.painted_objects(gvas), paint_scan.game_clock(gvas))
    except Exception:
        return (ts, None, None)


CACHE = f"{SP}/paint_raw.json"

if __name__ == "__main__":
    if "--rollup" in sys.argv and os.path.exists(CACHE):
        # Re-run only the analysis over an existing walk.
        raw = json.load(open(CACHE))
        seen = {int(k): {i: tuple(c) for i, c in v.items()} for k, v in raw["seen"].items()}
        clocks = {int(k): v for k, v in raw["clocks"].items()}
        print(f"loaded cached walk: {len(seen)} snapshots", flush=True)
    else:
        todo = sources()
        print(f"snapshots: {len(todo)}", flush=True)
        seen = {}
        clocks = {}
        t0 = time.time()
        done = 0
        with Pool(6) as pool:
            for ts, painted, clock in pool.imap_unordered(work, todo, chunksize=4):
                done += 1
                if painted is not None:
                    seen[ts] = painted
                    clocks[ts] = clock
                if done % 100 == 0:
                    print(f"  {done}/{len(todo)} ok={len(seen)} {time.time() - t0:.0f}s", flush=True)
        json.dump({"seen": {str(k): v for k, v in seen.items()},
                   "clocks": {str(k): v for k, v in clocks.items()}}, open(CACHE, "w"))
        print(f"scanned {len(seen)} snapshots in {time.time() - t0:.0f}s", flush=True)
    scanned = sorted(seen)
    print(f"  with a world clock: {sum(1 for t in scanned if clocks.get(t) is not None)}", flush=True)

    # --- drop STALE / FOREIGN snapshots --------------------------------------
    # Backup trees are keyed by file mtime, but a "pre-restore" backup written
    # today can contain a world from ten days ago, and the NAS also holds saves
    # from entirely DIFFERENT worlds (other save-game GUIDs) whose clocks are
    # unrelated. Treated as newer, either kind makes every paint applied in
    # between look like the player stripped it and then re-applied it — pure
    # fabrication.
    #
    # The world's own clock is the authority: within one continuous world
    # GameDateTimeTicks never runs backwards. So keep the LONGEST chain of
    # snapshots whose clock is non-decreasing in real-time order (a longest
    # non-decreasing subsequence) and drop everything off it. That is robust to
    # a single wild outlier at either end, which a running-maximum rule is not.
    # Snapshots with no readable clock are kept — there is nothing to judge them
    # by — and are simply not part of the chain.
    import bisect
    timed = [(ts, clocks[ts]) for ts in scanned if clocks.get(ts) is not None]
    tails, back, idxs = [], [None] * len(timed), []
    for i, (_, c) in enumerate(timed):
        j = bisect.bisect_right(tails, c)
        back[i] = idxs[j - 1] if j else None
        if j == len(tails):
            tails.append(c); idxs.append(i)
        else:
            tails[j] = c; idxs[j] = i
    keep, i = set(), (idxs[len(tails) - 1] if tails else None)
    while i is not None:
        keep.add(timed[i][0]); i = back[i]
    stale = [(ts, c) for ts, c in timed if ts not in keep]
    order = [ts for ts in scanned if clocks.get(ts) is None or ts in keep]
    print(f"kept {len(order)} snapshots; dropped {len(stale)} whose world clock "
          f"is out of order (stale backups / other worlds):", flush=True)
    for ts, c in stale[:15]:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))} "
              f"game {c / 1e7 / 86400:.2f}d  {src_label(ts)}", flush=True)

    # Roll the per-snapshot painted sets into per-object change lists. An object
    # counts as "observed unpainted" only in snapshots where it EXISTS, which we
    # take from build_index.json's first/last — otherwise every object would get
    # a spurious null change at the very first snapshot in the record.
    life = {}
    for r in json.load(open(f"{SP}/build_index.json")):
        life[r["id"]] = (r["first"], r["last"], r["base"])
    ever = sorted({iid for p in seen.values() for iid in p})
    print(f"objects ever painted: {len(ever)}", flush=True)

    changes = {}
    for iid in ever:
        first, last, _ = life.get(iid, (order[0], order[-1], None))
        prev = "?"
        seq = []
        for ts in order:
            if ts < first or ts > last:
                continue
            cur = seen[ts].get(iid)
            cur = list(cur) if cur else None
            if cur != prev:
                seq.append([ts, cur])
                prev = cur
        # Drop a leading "unpainted" entry: absence of a change already means
        # unpainted, so it carries no information and only bloats the file.
        if seq and seq[0][1] is None:
            seq.pop(0)
        if seq:
            changes[iid] = seq

    out = {"scanned": order, "changes": changes}
    for path in (f"{SP}/paint_index.json",
                 f"{SP}/mappal/public/union/paint_index.json"):
        json.dump(out, open(path, "w"))
    print(f"paint_index.json: {len(changes)} objects, "
          f"{os.path.getsize(f'{SP}/paint_index.json') // 1024} KB", flush=True)

    # Timeline summary, per base.
    bybase = {}
    for iid, seq in changes.items():
        b = life.get(iid, (0, 0, "?"))[2]
        for ts, col in seq:
            bybase.setdefault(b, []).append((ts, iid, col))
    for b, evs in sorted(bybase.items()):
        evs.sort()
        print(f"\nbase {b}: {len(evs)} paint events, "
              f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(evs[0][0]))} .. "
              f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(evs[-1][0]))}")
        buckets = {}
        for ts, iid, col in evs:
            buckets.setdefault(time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)), []).append(col)
        for k in sorted(buckets):
            cols = buckets[k]
            n_un = sum(1 for c in cols if c is None)
            print(f"  {k}  +{len(cols) - n_un} painted"
                  + (f", {n_un} unpainted" if n_un else ""))
