import json, os, shutil, struct, collections, sys

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
# palxtex --extract writes the textured GLBs (POSITION+NORMAL+TEXCOORD_0 plus
# embedded materials) here, alongside a tex/ folder of the decoded base-colour
# maps the glTF images reference. The older UV-less `meshes/` dir is the
# pre-texture pipeline and must NOT be the source any more — copying it over
# public/meshes strips every texture.
MESHES = os.path.join(SP, 'meshes_uv')
TEXSRC = os.path.join(MESHES, 'tex')
PUB = os.path.join(SP, 'mappal/public/meshes')
SRC = os.path.join(SP, 'mappal/src/data/meshRegistry.json')

glbs = sorted(f for f in os.listdir(MESHES) if f.endswith('.glb'))
names = set(f[:-4] for f in glbs)

# --- 1. copy GLBs (+ their textures) into public/meshes (replace) ---
os.makedirs(PUB, exist_ok=True)
for f in os.listdir(PUB):
    if f.endswith('.glb'):
        os.remove(os.path.join(PUB, f))
for f in glbs:
    shutil.copy2(os.path.join(MESHES, f), os.path.join(PUB, f))
if os.path.isdir(TEXSRC):
    shutil.rmtree(os.path.join(PUB, 'tex'), ignore_errors=True)
    shutil.copytree(TEXSRC, os.path.join(PUB, 'tex'))

# --- 2. registry ---
man = json.load(open(os.path.join(SP, 'mesh_manifest.json')))
report = json.load(open(os.path.join(SP, 'uv_report.json')))
rep = {e['name']: e for e in report if e.get('ok')}


def rank(nm, idx):
    """Deterministic primary pick: available GLB first, then real static mesh,
    then manifest order."""
    return (
        0 if nm in names else 1,           # must be actually extractable
        1 if nm.startswith('BP_') else 0,  # blueprint helper (arrow comp) last
        1 if nm.startswith('SK_') else 0,  # skeletal mesh after static
        idx,                               # else manifest order
    )


registry = {}
unmapped_types = {}
for tid, v in sorted(man.items()):
    paths = v.get('meshPaths') or ([v['meshPath']] if v.get('meshPath') else [])
    cands = [p.rsplit('/', 1)[-1] for p in paths]
    if not cands:
        unmapped_types[tid] = 'no mesh path in manifest'
        continue
    best = min(range(len(cands)), key=lambda i: rank(cands[i], i))
    nm = cands[best]
    if nm not in names:
        unmapped_types[tid] = 'no extracted GLB for ' + nm
        continue
    registry[tid] = {"mesh": nm, "url": "/meshes/%s.glb" % nm}

reg_json = json.dumps(registry, indent=1) + "\n"
open(os.path.join(PUB, 'registry.json'), 'w').write(reg_json)
open(SRC, 'w').write(reg_json)

# --- 4. validation ---
broken = []
for tid, e in registry.items():
    p = os.path.join(PUB, e['url'].lstrip('/').split('/', 1)[1])
    if not os.path.exists(p):
        broken.append((tid, e['mesh'], 'file missing'))
        continue
    with open(p, 'rb') as fh:
        head = fh.read(12)
    if head[:4] != b'glTF':
        broken.append((tid, e['mesh'], 'bad magic'))
        continue
    ver, total = struct.unpack('<II', head[4:12])
    if total != os.path.getsize(p):
        broken.append((tid, e['mesh'], 'length mismatch %d vs %d' % (total, os.path.getsize(p))))
    r = rep.get(e['mesh'])
    if r is None:
        broken.append((tid, e['mesh'], 'no report entry'))
    elif not r.get('verts'):
        broken.append((tid, e['mesh'], 'zero verts'))

# --- 3. coverage ---
b = json.load(open(os.path.join(SP, 'build_index.json')))
cnt = collections.Counter(o['type'] for o in b)
DROP = 'CommonDropItem3D'
tot = sum(cnt.values())
drop_n = cnt.get(DROP, 0)
struct_n = tot - drop_n
struct_hit = sum(c for t, c in cnt.items() if t != DROP and t in registry)
old = json.load(open(os.path.join(SP, 'meshes_prev_registry.json'))) if os.path.exists(os.path.join(SP, 'meshes_prev_registry.json')) else {}
old_hit = sum(c for t, c in cnt.items() if t != DROP and t in old)

unmapped = collections.Counter({t: c for t, c in cnt.items() if t != DROP and t not in registry})

out = {
    'glbs_copied': len(glbs),
    'registry_types': len(registry),
    'distinct_meshes_used': len(set(e['mesh'] for e in registry.values())),
    'unmapped_manifest_types': unmapped_types,
    'broken': broken,
    'objects_total': tot,
    'drop_items': drop_n,
    'structures_total': struct_n,
    'structures_real_mesh_new': struct_hit,
    'structures_real_mesh_old': old_hit,
    'old_registry_types': len(old),
    'top_unmapped': unmapped.most_common(15),
    'distinct_types_in_world': len(cnt),
    'distinct_types_mapped': len([t for t in cnt if t in registry]),
}
print(json.dumps(out, indent=1))
