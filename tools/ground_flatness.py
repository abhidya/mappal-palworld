"""Sample REAL ground height across a base disc, from the game's own meshes.

Palworld's ground is not a Landscape - it is placed static meshes - so the only
honest way to ask "is this flat enough to build a 68.5 m arena on" is to rebuild
the ground triangles in world space and cast rays down onto them.

THE SELECTION BUG THIS EXISTS TO AVOID
Picking the ground chunks by "origin inside the disc" is wrong. Palworld's
ground chunks are large and their origin is not their centre, so a chunk whose
origin sits well outside the disc still covers ground inside it. Selecting that
way leaves systematic holes, and because the origins are offset consistently the
holes land in the same quadrant at every site - a give-away that they are an
artifact and not a cliff. Here every ground placement is transformed into world
space FIRST and kept if its world-space AABB overlaps the disc, which is the
selection that actually answers the question.

Transform convention is build_terrain.py's, unchanged: world = loc + R(rot) *
(vert * scale), with R built from the Unreal FRotator via the same
FRotator::Quaternion() sign convention.
"""
import json, math, os, struct, sys, collections

SP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MESHDIR = f"{SP}/terrq/meshes"
GROUND_KEYS = ("ground", "_top", "top_", "flat_horizontal", "rockyground",
               "hugecliff", "cliff", "terrain", "field")


def is_ground(name):
    n = name.lower()
    return any(k in n for k in GROUND_KEYS)


def read_glb_prim(path):
    d = open(path, "rb").read()
    o, js, bin_ = 12, None, None
    while o < len(d):
        ln, ty = struct.unpack("<II", d[o:o + 8]); o += 8
        ch = d[o:o + ln]; o += ln
        if ty == 0x4E4F534A: js = json.loads(ch)
        elif ty == 0x004E4942: bin_ = ch
    prim = js["meshes"][0]["primitives"][0]
    pa = js["accessors"][prim["attributes"]["POSITION"]]
    ia = js["accessors"][prim["indices"]]
    bv = js["bufferViews"]
    v = bv[pa["bufferView"]]; n = pa["count"]
    off = v.get("byteOffset", 0) + pa.get("byteOffset", 0)
    f = struct.unpack("<%df" % (n * 3), bin_[off:off + n * 12])
    iv = bv[ia["bufferView"]]
    w = 4 if ia["componentType"] == 5125 else 2
    ioff = iv.get("byteOffset", 0) + ia.get("byteOffset", 0)
    idx = struct.unpack("<%d%s" % (ia["count"], "I" if w == 4 else "H"),
                        bin_[ioff:ioff + ia["count"] * w])
    return [(f[i * 3], f[i * 3 + 1], f[i * 3 + 2]) for i in range(n)], list(idx)


def rot_matrix(pitch, yaw, roll):
    hp, hy, hr = (math.radians(v) * 0.5 for v in (pitch, yaw, roll))
    sp, cp = math.sin(hp), math.cos(hp)
    sy, cy = math.sin(hy), math.cos(hy)
    sr, cr = math.sin(hr), math.cos(hr)
    x = cr * sp * sy - sr * cp * cy
    y = -cr * sp * cy - sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    w = cr * cp * cy + sr * sp * sy
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))


_cache = {}


def mesh_of(name):
    if name not in _cache:
        p = f"{MESHDIR}/{name}.glb"
        _cache[name] = read_glb_prim(p) if os.path.exists(p) else None
    return _cache[name]


def load_placements():
    recs, seen = [], set()
    for f in ("cellactors_quartz.json", "cellactors_quartz_ring2.json",
              "cellactors_persistent.json"):
        p = f"{SP}/terrq/{f}"
        if not os.path.exists(p):
            continue
        for x in json.load(open(p)):
            if x.get("cls") != "StaticMeshComponent" or not x.get("mesh"):
                continue
            if not any(x["loc"]) or not is_ground(x["mesh"]):
                continue
            k = (x["mesh"], round(x["loc"][0], 1), round(x["loc"][1], 1), round(x["loc"][2], 1))
            if k in seen:
                continue
            seen.add(k)
            recs.append(x)
    return recs


def world_tris(rec):
    """Ground triangles of one placement, in world centimetres."""
    m = mesh_of(rec["mesh"])
    if m is None:
        return None
    verts, idx = m
    R = rot_matrix(*rec["rot"])
    sx, sy, sz = rec["scale"]
    lx, ly, lz = rec["loc"]
    W = []
    for vx, vy, vz in verts:
        px, py, pz = vx * sx, vy * sy, vz * sz
        W.append((lx + R[0][0] * px + R[0][1] * py + R[0][2] * pz,
                  ly + R[1][0] * px + R[1][1] * py + R[1][2] * pz,
                  lz + R[2][0] * px + R[2][1] * py + R[2][2] * pz))
    return W, idx


def sample_site(cx, cy, R, placements, step=200.0):
    # ---- select by world-space AABB overlap, NOT by origin distance ----
    chosen, tris = [], []
    for rec in placements:
        w = world_tris(rec)
        if w is None:
            continue
        W, idx = w
        xs = [p[0] for p in W]; ys = [p[1] for p in W]
        if max(xs) < cx - R or min(xs) > cx + R or max(ys) < cy - R or min(ys) > cy + R:
            continue
        chosen.append(rec["mesh"])
        for t in range(0, len(idx), 3):
            a, b, c = W[idx[t]], W[idx[t + 1]], W[idx[t + 2]]
            if (max(a[0], b[0], c[0]) < cx - R or min(a[0], b[0], c[0]) > cx + R or
                    max(a[1], b[1], c[1]) < cy - R or min(a[1], b[1], c[1]) > cy + R):
                continue
            tris.append((a, b, c))

    # ---- bucket triangles into a grid so each ray tests few of them ----
    CELL = 500.0
    grid = collections.defaultdict(list)
    for tri in tris:
        a, b, c = tri
        i0 = int(math.floor(min(a[0], b[0], c[0]) / CELL)); i1 = int(math.floor(max(a[0], b[0], c[0]) / CELL))
        j0 = int(math.floor(min(a[1], b[1], c[1]) / CELL)); j1 = int(math.floor(max(a[1], b[1], c[1]) / CELL))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                grid[(i, j)].append(tri)

    def ground_z(px, py):
        best = None
        for tri in grid.get((int(math.floor(px / CELL)), int(math.floor(py / CELL))), ()):
            a, b, c = tri
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

    zs, miss, quad = [], [], collections.Counter()
    n = int(R / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            px, py = cx + i * step, cy + j * step
            if math.hypot(px - cx, py - cy) > R:
                continue
            z = ground_z(px, py)
            q = ("N" if px >= cx else "S") + ("E" if py >= cy else "W")
            if z is None:
                miss.append((px, py)); quad[q + "_miss"] += 1
            else:
                zs.append(z)
            quad[q + "_all"] += 1
    return zs, miss, quad, len(chosen), len(tris)
