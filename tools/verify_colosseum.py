import json,math,sys,collections
p=sys.argv[1] if len(sys.argv)>1 else None
d=json.load(open(p))
mo=d['map_objects']
def T(m): return m['Model']['value']['RawData']['value']['initital_transform_cache']['translation']
pb=[i for i,m in enumerate(mo) if m['MapObjectId']['value']=='PalBoxV2']
print(f"map_objects            : {len(mo)}")
print(f"distinct MapObjectId   : {len(set(m['MapObjectId']['value'] for m in mo))}")
print(f"PalBox count           : {len(pb)} (index {pb})")
ids=[m['Model']['value']['RawData']['value']['instance_id'] for m in mo]
cids=[m['Model']['value']['RawData']['value']['concrete_model_instance_id'] for m in mo]
print(f"unique instance_id     : {len(set(ids))} / {len(ids)}  {'OK' if len(set(ids))==len(ids) else 'DUPLICATES'}")
print(f"unique concrete_id     : {len(set(cids))} / {len(cids)}  {'OK' if len(set(cids))==len(cids) else 'DUPLICATES'}")
o=T(mo[pb[0]])
print(f"PalBox translation     : ({o['x']:.3f}, {o['y']:.3f}, {o['z']:.3f})")
r=[math.hypot(T(m)['x']-o['x'],T(m)['y']-o['y']) for m in mo]
zs=[T(m)['z']-o['z'] for m in mo]
print(f"max XY radius from PB  : {max(r):.1f} cm  ({'INSIDE' if max(r)<3500 else 'OUTSIDE'} area_range 3500)")
print(f"footprint diameter     : {2*max(r)/100:.1f} m")
print(f"Z range rel. PalBox    : {min(zs):.1f} .. {max(zs):.1f} cm  -> height {(max(zs)-min(zs))/100:.1f} m")
# camp anchor
bc=d['base_camp']['value']['RawData']['value']
ct=bc['transform']
print(f"camp anchor translation: ({ct['translation']['x']:.3f}, {ct['translation']['y']:.3f}, {ct['translation']['z']:.3f})")
same = all(abs(ct['translation'][k]-o[k])<1e-6 for k in 'xyz')
print(f"camp anchor == PalBox  : {'YES' if same else 'NO'}")
print(f"camp area_range        : {bc['area_range']}")
wd=d['base_camp']['value']['WorkerDirector']['value']['RawData']['value']['spawn_transform']['translation']
print(f"worker spawn transform : ({wd['x']:.3f}, {wd['y']:.3f}, {wd['z']:.3f})")
print(f"base_camp_level        : {d.get('base_camp_level')}")
print(f"item_containers/works  : {len(d['item_containers'])} / {len(d['works'])}")
