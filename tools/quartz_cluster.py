"""Site the Colosseum Maximus on real, extracted natural-quartz ground.

DATA PROVENANCE - everything here is read out of the cooked client pak, nothing
is invented:

  quartz nodes   BP_PalMapObjectSpawner_RockQuartz_C actors from every
                 MainGrid_L0_* World Partition cell of PL_MainWorld5
                 (allspawners_L0.json). Their `loc` is already WORLD centimetres:
                 all 453 fall inside the 25600 cm cell box implied by their own
                 cell name, which would be impossible for cell-relative values.

  dungeon locks  BP_LevelObject_TowerLockBarrier_C (66 world-wide,
                 quartz_landmarks.json). These mark dungeon entrances, which are
                 no-build ground.

  existing bases the player's four camps, read from union_<id>.json ->
                 base_camp.value.RawData.value (centre + area_range).

MAX-COVERAGE SITING IS EXACT, NOT A HEURISTIC.
An optimal fixed-radius disc can always be translated until its boundary touches
two of the points it covers, so enumerating every point plus both centres of the
radius-R circles through every pair closer than 2R is guaranteed to contain an
optimal centre. Coverage is compared on DISTANCES with a relative epsilon:
squared distances at R=3500 are ~1.2e7, where an absolute 1e-6 epsilon is below
float resolution and silently drops nodes lying exactly on the boundary (which,
by construction, the two generating points always do).

Once the best-covered node SET is known, the disc is placed at that set's
minimum enclosing circle rather than at the boundary-touching centre that found
it. The MEC minimises the worst-case node distance, which buys the largest
possible margin between the outermost quartz node and the base edge - a node
sitting exactly on the boundary could fall outside the base in-game.
"""
import json, math, itertools, os

SP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = 3500.0                       # base_camp area_range, cm
BUILD_R = 3423.4                 # outermost Colosseum piece, cm
SCALE = 459.42                   # world cm per in-game map unit
MAP_OX, MAP_OY = 158000.0, 123888.0

BASES = {"07f13218": "Glass Tower", "16fca097": "Wooden Camp",
         "de44d9f4": "Stone Works", "5fed0024": "Lost Camp"}


def world_to_map(x, y):
    """Unreal world cm -> the coordinate pair the in-game map shows."""
    return ((y - MAP_OX) / SCALE, (x + MAP_OY) / SCALE)


def map_to_world(mx, my):
    return (my * SCALE - MAP_OY, mx * SCALE + MAP_OX)


def load_quartz():
    d = json.load(open(f"{SP}/allspawners_L0.json"))
    return [(x['loc'][0], x['loc'][1], x['loc'][2])
            for x in d if x['cls'] == 'BP_PalMapObjectSpawner_RockQuartz_C']


def load_dungeon_locks():
    d = json.load(open(f"{SP}/quartz_landmarks.json"))
    return [(x['loc'][0], x['loc'][1], x['loc'][2])
            for x in d if x['cls'] == 'BP_LevelObject_TowerLockBarrier_C' and any(x['loc'])]


def load_bases():
    out = []
    for bid, name in BASES.items():
        rd = json.load(open(f"{SP}/mappal/public/union/union_{bid}.json"))
        rd = rd['base_camp']['value']['RawData']['value']
        t = rd['transform']['translation']
        out.append((bid, name, t['x'], t['y'], t['z'], rd['area_range']))
    return out


def cover(P, cx, cy, R):
    lim = R * (1 + 1e-9) + 1e-6
    return [p for p in P if math.hypot(p[0] - cx, p[1] - cy) <= lim]


def candidate_centres(P, R):
    C = [(p[0], p[1]) for p in P]
    for a, b in itertools.combinations(P, 2):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d2 = dx * dx + dy * dy
        if d2 == 0 or d2 > 4 * R * R:
            continue
        d = math.sqrt(d2)
        h = math.sqrt(max(R * R - d2 / 4, 0.0))
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        ux, uy = -dy / d, dx / d
        C.append((mx + ux * h, my + uy * h))
        C.append((mx - ux * h, my - uy * h))
    return C


def mec(pts):
    """Minimum enclosing circle (Welzl, iterative-enough for these sizes)."""
    best = None
    n = len(pts)
    if n == 1:
        return (pts[0][0], pts[0][1], 0.0)
    # try all 2-point (diameter) and 3-point (circumcircle) determinations
    cands = []
    for a, b in itertools.combinations(pts, 2):
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        r = math.hypot(a[0] - cx, a[1] - cy)
        cands.append((cx, cy, r))
    for a, b, c in itertools.combinations(pts, 3):
        d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-9:
            continue
        ux = ((a[0]**2 + a[1]**2) * (b[1] - c[1]) + (b[0]**2 + b[1]**2) * (c[1] - a[1])
              + (c[0]**2 + c[1]**2) * (a[1] - b[1])) / d
        uy = ((a[0]**2 + a[1]**2) * (c[0] - b[0]) + (b[0]**2 + b[1]**2) * (a[0] - c[0])
              + (c[0]**2 + c[1]**2) * (b[0] - a[0])) / d
        cands.append((ux, uy, math.hypot(a[0] - ux, a[1] - uy)))
    for cx, cy, r in cands:
        if all(math.hypot(p[0] - cx, p[1] - cy) <= r * (1 + 1e-9) + 1e-6 for p in pts):
            if best is None or r < best[2]:
                best = (cx, cy, r)
    return best


def main():
    P = load_quartz()
    locks = load_dungeon_locks()
    bases = load_bases()
    print(f"quartz nodes   : {len(P)}  (BP_PalMapObjectSpawner_RockQuartz_C)")
    print(f"dungeon locks  : {len(locks)}  (BP_LevelObject_TowerLockBarrier_C)")
    print(f"existing bases : {len(bases)}")

    C = candidate_centres(P, R)
    print(f"exact candidate centres: {len(C)}")

    best_n = 0
    sets = {}
    for cx, cy in C:
        n = cover(P, cx, cy, R)
        if len(n) > best_n:
            best_n = len(n)
        key = tuple(sorted((round(p[0], 3), round(p[1], 3)) for p in n))
        if len(n) >= 4:
            sets[key] = n
    print(f"max quartz coverage achievable in one {R:.0f} cm base radius: {best_n}")

    # place each candidate node-set at its minimum enclosing circle
    placed = []
    for key, n in sets.items():
        m = mec(n)
        if m is None or m[2] > R:
            continue
        cx, cy, r = m
        placed.append((len(n), r, cx, cy, n))
    placed.sort(key=lambda t: (-t[0], t[1]))

    # distinct sites
    sites = []
    for cnt, r, cx, cy, n in placed:
        if all(math.hypot(cx - s[2], cy - s[3]) > R for s in sites):
            sites.append((cnt, r, cx, cy, n))
        if len(sites) >= 12:
            break

    print(f"\n{'#':<3}{'q':<3}{'world X':>11}{'world Y':>11}{'map X':>8}{'map Y':>8}"
          f"{'MECr':>7}{'margin':>8}{'lock d':>9}{'base d':>10}  verdict")
    out = []
    for i, (cnt, r, cx, cy, n) in enumerate(sites):
        mx, my = world_to_map(cx, cy)
        dlock = min(math.hypot(cx - l[0], cy - l[1]) for l in locks)
        dbase = min(math.hypot(cx - b[2], cy - b[3]) - (R + b[5]) for b in bases)
        bad = []
        if dlock < R:
            bad.append("DUNGEON-LOCK-INSIDE")
        if dbase < 0:
            bad.append("BASE-OVERLAP")
        verdict = ",".join(bad) if bad else "ok"
        print(f"{i+1:<3}{cnt:<3}{cx:>11.1f}{cy:>11.1f}{mx:>8.1f}{my:>8.1f}"
              f"{r:>7.0f}{R-r:>8.0f}{dlock:>9.0f}{dbase:>10.0f}  {verdict}")
        out.append({"rank": i + 1, "quartz": cnt, "cx": cx, "cy": cy,
                    "map_x": mx, "map_y": my, "mec_radius": r,
                    "margin": R - r, "dist_nearest_dungeon_lock": dlock,
                    "clearance_to_nearest_base": dbase,
                    "verdict": verdict, "nodes": n})
    json.dump(out, open(f"{SP}/quartz_sites.json", "w"), indent=1)
    print(f"\n-> {SP}/quartz_sites.json")


if __name__ == "__main__":
    main()
