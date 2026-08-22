"""Acceptance test for the unowned-object indexing fix.

1. Every painted object in paint_index.json must appear in build_index.json.
2. Report what the radius rule added, per base and per type.
3. Compare per-base structure/step counts against the pre-fix baseline.
"""
import json
import sys
from collections import Counter

SP = sys.argv[1] if len(sys.argv) > 1 else "."
NAMES = {'07f13218': 'Glass Tower', '16fca097': 'Wooden Camp',
         'de44d9f4': 'Stone Works', '5fed0024': 'Lost Camp'}
BASELINE = {'07f13218': (2136, 98), 'de44d9f4': (1007, 22),
            '16fca097': (979, 23), '5fed0024': (89, 16)}

new = json.load(open(f"{SP}/build_index.json"))
old = json.load(open(f"{SP}/build_index.json.bak-preradius"))
paint = json.load(open(f"{SP}/paint_index.json"))

have = {r['id'] for r in new}
had = {r['id'] for r in old}
painted = set(paint['changes'])

missing = painted - have
print(f"ACCEPTANCE  painted={len(painted)}  in build_index={len(painted & have)}  MISSING={len(missing)}")
if missing:
    print("  still missing:", sorted(i[:8] for i in missing))
print(f"{'PASS' if not missing else 'FAIL'}\n")

added = [r for r in new if r['id'] not in had]
dropped = had - have
print(f"objects {len(old)} -> {len(new)}   added={len(added)} dropped={len(dropped)}")
if dropped:
    lost = [r for r in old if r['id'] in dropped]
    print(f"  !! DROPPED {len(dropped)}: {Counter(r['type'] for r in lost).most_common(8)}")
print("\nADDED by base / type:")
bybase = {}
for r in added:
    bybase.setdefault(r['base'], []).append(r)
for b, rs in sorted(bybase.items()):
    print(f"  {NAMES.get(b, b):13s} +{len(rs):3d}  {dict(Counter(r['type'] for r in rs))}")
    for r in sorted(rs, key=lambda r: r['first']):
        tag = " <-PAINTED" if r['id'] in painted else ""
        print(f"       {r['id'][:8]} {r['type']:24s} first={r['first']} last={r['last']}{tag}")

print("\nPER-BASE structures / steps  (loot excluded, as downstream):")
per = {}
for r in new:
    per.setdefault(r['base'], []).append(r)
for b, rs in sorted(per.items(), key=lambda x: -len(x[1])):
    st = [r for r in rs if r['type'] != 'CommonDropItem3D']
    steps = len({r['first'] for r in st})
    ob, os_ = BASELINE.get(b, (0, 0))
    print(f"  {NAMES.get(b, b):13s} structures {ob:5d} -> {len(st):5d} ({len(st)-ob:+d})   "
          f"steps {os_:4d} -> {steps:4d} ({steps-os_:+d})   loot={len(rs)-len(st)}")
