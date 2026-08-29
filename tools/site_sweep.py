"""Centre sweep: find a base centre whose FULL build disc sits on real ground.

Two hard gates, then maximise quartz. Both gates come from the build itself,
not from round numbers:

  GATE 1 - COVERAGE. Every sample inside the 3423 cm build radius (the
  outermost Colosseum piece) must land on real cooked ground. A rim cutting the
  disc is disqualifying: pieces beyond it would hang over a void.

  GATE 2 - FLATNESS. 296 of the 2776 pieces sit at the arena floor level (Z
  offset 0), and the design's storey pitch is 325 cm. So if ground relief across
  the disc exceeds 325 cm, some floor piece is more than a whole storey buried
  or hovering. Cap = 325 cm; 150 cm (the first sub-level above the floor) is
  reported as the stricter figure.

Only then is quartz count maximised, with coverage margin beyond 3423 cm as the
tiebreak so a winner is not sitting on a knife edge.
"""
import sys, os, math, json, collections, statistics

SP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_flatness as gf
import quartz_cluster as qc

BUILD_R = 3423.4
AREA_R = 3500.0
STOREY = 325.0
SUBLEVEL = 150.0
GRID = 200.0


def build_region(pl, rx, ry, rr):
    tris = []
    for rec in pl:
        w = gf.world_tris(rec)
        if w is None:
            continue
        W, idx = w
        xs = [p[0] for p in W]; ys = [p[1] for p in W]
        if max(xs) < rx - rr or min(xs) > rx + rr or max(ys) < ry - rr or min(ys) > ry + rr:
            continue
        for t in range(0, len(idx), 3):
            a, b, c = W[idx[t]], W[idx[t + 1]], W[idx[t + 2]]
            if (max(a[0], b[0], c[0]) < rx - rr or min(a[0], b[0], c[0]) > rx + rr or
                    max(a[1], b[1], c[1]) < ry - rr or min(a[1], b[1], c[1]) > ry + rr):
                continue
            tris.append((a, b, c))
    CELL = 500.0
    grid = collections.defaultdict(list)
    for tri in tris:
        a, b, c = tri
        i0 = int(math.floor(min(a[0], b[0], c[0]) / CELL)); i1 = int(math.floor(max(a[0], b[0], c[0]) / CELL))
        j0 = int(math.floor(min(a[1], b[1], c[1]) / CELL)); j1 = int(math.floor(max(a[1], b[1], c[1]) / CELL))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                grid[(i, j)].append(tri)

    def gz(px, py):
        best = None
        for a, b, c in grid.get((int(math.floor(px / CELL)), int(math.floor(py / CELL))), ()):
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            u = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
            v = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
            w = 1 - u - v
            if u < -1e-9 or v < -1e-9 or w < -1e-9:
                continue
            z = u * a[2] + v * b[2] + w * c[2]
            if best is None or z > best:
                best = z
        return best

    n = int(rr / GRID)
    Z = {}
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            Z[(i, j)] = gz(rx + i * GRID, ry + j * GRID)
    return Z, n, len(tris)


DISC = [(i, j) for i in range(-int(BUILD_R / GRID) - 1, int(BUILD_R / GRID) + 2)
        for j in range(-int(BUILD_R / GRID) - 1, int(BUILD_R / GRID) + 2)
        if math.hypot(i * GRID, j * GRID) <= BUILD_R]


def sweep(name, rx, ry, rr, Q, pl, out):
    Z, n, ntri = build_region(pl, rx, ry, rr)
    lim = n - int(BUILD_R / GRID) - 1
    best = []
    for ci in range(-lim, lim + 1):
        for cj in range(-lim, lim + 1):
            cx, cy = rx + ci * GRID, ry + cj * GRID
            zs = []
            ok = True
            for di, dj in DISC:
                z = Z.get((ci + di, cj + dj), 'OUT')
                if z is None or z == 'OUT':
                    ok = False
                    break
                zs.append(z)
            if not ok or len(zs) < 100:
                continue
            spread = max(zs) - min(zs)
            q = sum(1 for p in Q if math.hypot(p[0] - cx, p[1] - cy) <= AREA_R)
            best.append((q, spread, cx, cy, statistics.median(zs)))
    covered = len(best)
    passing = [b for b in best if b[1] <= STOREY]
    print(f"  {name:<22} tris={ntri:>7}  fully-covered centres={covered:<6} "
          f"also within {STOREY:.0f} cm={len(passing)}")
    if best:
        best.sort(key=lambda b: b[1])
        q, sp, cx, cy, md = best[0]
        print(f"      flattest fully-covered: spread={sp:7.0f} cm  quartz={q}  at ({cx:.1f}, {cy:.1f})")
        bq = sorted(best, key=lambda b: (-b[0], b[1]))[0]
        print(f"      most quartz fully-covered: quartz={bq[0]}  spread={bq[1]:7.0f} cm  at ({bq[2]:.1f}, {bq[3]:.1f})")
    for b in best:
        out.append({"region": name, "quartz": b[0], "spread": b[1], "cx": b[2], "cy": b[3], "medianZ": b[4]})


def main():
    pl = gf.load_placements()
    Q = qc.load_quartz()
    print(f"ground placements: {len(pl)}   quartz nodes: {len(Q)}")
    print(f"GATE 1 full coverage of r={BUILD_R:.0f} cm   GATE 2 spread <= {STOREY:.0f} cm\n")
    regions = [
        ("main quartz field", 10000.0, 96000.0, 16000.0),
        ("rank6 plateau", 82546.8, 36438.6, 9000.0),
        ("rank9", 205.3, 70306.1, 9000.0),
        ("B", 102409.5, -3700.8, 9000.0),
        ("rank11", 155111.2, 89816.5, 9000.0),
        ("rank5 shelf", 2275.4, 58878.7, 9000.0),
        ("site E", 2819.8, 15201.6, 9000.0),
        ("rank4", 13518.1, -2681.4, 9000.0),
    ]
    out = []
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for nm, x, y, r in regions:
        if only and nm not in only:
            continue
        sweep(nm, x, y, r, Q, pl, out)
    json.dump(out, open(f"{SP}/quartz_sweep.json", "w"))
    print(f"\ntotal fully-covered centres across swept regions: {len(out)}")


if __name__ == "__main__":
    main()
