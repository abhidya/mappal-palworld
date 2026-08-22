"""Physical cross-check: do foliage instances land ON the landscape surface?

Landscape verts (LandscapeMeshDto LOD0) are actor-local -> world = vert + proxy.loc.
Foliage instances are IFA-local  -> world = inst.T + IFA.RootComponent.RelativeLocation.
Neither offset is guessed: both are read off the cooked components.
If the two agree in Z, both frames are correct.
"""
import json, struct, os, sys, math
SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
from glbcheck import readglb

def verts_of(p):
    d = open(p, 'rb').read()
    o = 12; js = None; bin_ = None
    while o < len(d):
        ln, ty = struct.unpack('<II', d[o:o+8]); o += 8
        ch = d[o:o+ln]; o += ln
        if ty == 0x4E4F534A: js = json.loads(ch)
        elif ty == 0x004E4942: bin_ = ch
    pa = js['accessors'][0]; v = js['bufferViews'][pa['bufferView']]
    n = pa['count']
    f = struct.unpack('<%df' % (n*3), bin_[v['byteOffset']:v['byteOffset']+n*12])
    return [(f[i*3], f[i*3+1], f[i*3+2]) for i in range(n)]

idx = json.load(open(f"{SP}/terrain_index.json"))
land = []
for r in idx:
    lx, ly, lz = r['loc']
    for (x, y, z) in verts_of(os.path.join(SP, r['glb'])):
        land.append((x+lx, y+ly, z+lz))
print(f"landscape verts (world): {len(land)}")
xs = [p[0] for p in land]; ys = [p[1] for p in land]; zs = [p[2] for p in land]
print(f"  X {min(xs):.0f}..{max(xs):.0f}   Y {min(ys):.0f}..{max(ys):.0f}   Z {min(zs):.0f}..{max(zs):.0f}")

acts = json.load(open(f"{SP}/cellactors.json"))
ifa = next(r for r in acts if r['name'] == 'RootComponent0')
ox, oy, oz = ifa['loc']
print(f"IFA root offset: {ox} {oy} {oz}")

# bucket landscape verts on a 200cm grid for nearest lookup
grid = {}
for (x, y, z) in land:
    grid.setdefault((int(x//200), int(y//200)), []).append(z)

samp = []
for r in acts:
    for i in r['instances'][:20]:
        samp.append((i[0]+ox, i[1]+oy, i[2]+oz))
print(f"foliage instances sampled: {len(samp)}")
fx = [p[0] for p in samp]; fy = [p[1] for p in samp]; fz = [p[2] for p in samp]
print(f"  X {min(fx):.0f}..{max(fx):.0f}   Y {min(fy):.0f}..{max(fy):.0f}   Z {min(fz):.0f}..{max(fz):.0f}")

deltas = []
for (x, y, z) in samp:
    cands = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cands += grid.get((int(x//200)+dx, int(y//200)+dy), [])
    if cands:
        deltas.append(z - (sum(cands)/len(cands)))
if deltas:
    deltas.sort()
    print(f"foliage Z minus local landscape Z:  n={len(deltas)}  "
          f"median={deltas[len(deltas)//2]:.0f}  p10={deltas[len(deltas)//10]:.0f}  "
          f"p90={deltas[len(deltas)*9//10]:.0f}")
else:
    print("NO OVERLAP between foliage XY and landscape XY -> frames disagree")
