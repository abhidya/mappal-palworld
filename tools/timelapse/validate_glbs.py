"""Structural validation for the textured GLBs in mappal/public/meshes.

glbcheck.py predates the UV/material pipeline: it hard-codes accessor 0 =
POSITION and accessor 2 = indices, which only holds for the old single-primitive
POSITION+NORMAL exports. This walks every primitive of every mesh instead, and
additionally checks that every registry url resolves and that both registry
copies agree.
"""
import json, os, struct, sys, collections

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(SP, 'mappal/public/meshes')

CT = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2),
      5125: ('I', 4), 5126: ('f', 4)}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def load(p):
    d = open(p, 'rb').read()
    assert d[:4] == b'glTF', 'bad magic'
    ver, tot = struct.unpack('<II', d[4:12])
    assert tot == len(d), 'length %d != file %d' % (tot, len(d))
    o, js, bin_ = 12, None, b''
    while o < len(d):
        ln, ty = struct.unpack('<II', d[o:o + 8]); o += 8
        ch = d[o:o + ln]; o += ln
        if ty == 0x4E4F534A: js = json.loads(ch)
        elif ty == 0x004E4942: bin_ = ch
    return js, bin_


def read(g, bin_, ai):
    a = g['accessors'][ai]
    bv = g['bufferViews'][a['bufferView']]
    fmt, sz = CT[a['componentType']]
    n = NC[a['type']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    cnt = a['count'] * n
    assert off + cnt * sz <= len(bin_), 'accessor %d overruns BIN' % ai
    return struct.unpack_from('<%d%s' % (cnt, fmt), bin_, off)


def check(p):
    g, bin_ = load(p)
    tv = tt = 0
    lo = [1e18] * 3; hi = [-1e18] * 3
    imgs = len(g.get('images', []))
    for m in g['meshes']:
        for pr in m['primitives']:
            assert 'POSITION' in pr['attributes'], 'no POSITION'
            pos = read(g, bin_, pr['attributes']['POSITION'])
            nv = len(pos) // 3
            assert nv > 0, 'zero vertices'
            idx = read(g, bin_, pr['indices'])
            assert len(idx) % 3 == 0, 'index count not a multiple of 3'
            assert max(idx) < nv, 'index %d out of range (%d verts)' % (max(idx), nv)
            assert all(v == v and abs(v) < 1e9 for v in pos), 'NaN/absurd vertex'
            for k in range(3):
                lo[k] = min(lo[k], min(pos[k::3])); hi[k] = max(hi[k], max(pos[k::3]))
            if 'TEXCOORD_0' in pr['attributes']:
                uv = read(g, bin_, pr['attributes']['TEXCOORD_0'])
                assert len(uv) // 2 == nv, 'UV count != vertex count'
            tv += nv; tt += len(idx) // 3
    bbox = [round(hi[k] - lo[k], 2) for k in range(3)]
    assert max(bbox) > 0, 'degenerate bbox'
    return tv, tt, bbox, imgs


pub = json.load(open(os.path.join(PUB, 'registry.json')))
src = json.load(open(os.path.join(SP, 'mappal/src/data/meshRegistry.json')))
assert pub == src, 'public/meshes/registry.json and src/data/meshRegistry.json differ'

want = sys.argv[1:]
fails = []
files = sorted(f for f in os.listdir(PUB) if f.endswith('.glb'))
for f in files:
    try:
        tv, tt, bbox, imgs = check(os.path.join(PUB, f))
        if want and any(w in f for w in want):
            print('  %-52s %7dv %7dt bbox_cm=%s imgs=%d' % (f[:-4], tv, tt, bbox, imgs))
    except AssertionError as e:
        fails.append((f, str(e)))
print('GLBs validated: %d, failures: %d' % (len(files), len(fails)))
for f, e in fails:
    print('  FAIL', f, e)

# every registry url must resolve
missing = [(t, e['url']) for t, e in pub.items()
           if not os.path.exists(os.path.join(PUB, e['url'].lstrip('/').split('/', 1)[1]))]
print('registry types: %d, urls that do not resolve: %d' % (len(pub), len(missing)))
for m in missing:
    print('  MISSING', m)

# every glTF image referenced by a GLB must exist in tex/
tex = set(os.listdir(os.path.join(PUB, 'tex'))) if os.path.isdir(os.path.join(PUB, 'tex')) else set()
badtex = []
for f in files:
    g, _ = load(os.path.join(PUB, f))
    for im in g.get('images', []):
        u = im.get('uri')
        if u and not u.startswith('data:'):
            n = u.split('/')[-1]
            if n not in tex:
                badtex.append((f, u))
print('texture files in tex/: %d, GLB image refs missing: %d' % (len(tex), len(badtex)))
for b in badtex[:10]:
    print('  MISSINGTEX', b)
sys.exit(1 if (fails or missing or badtex) else 0)
