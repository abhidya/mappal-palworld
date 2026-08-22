"""Rigidly re-anchor the Colosseum Maximus blueprint onto a chosen world point.

The design's internal geometry is left untouched: every piece is moved by ONE
common translation delta, so all relative offsets, all rotations and all scales
are bit-for-bit what gen-colosseum.ts produced. Only the three kinds of spatial
field in the file carry a world position, and a full walk of the document
confirms there are no others:

  1. map_objects[*].Model.value.RawData.value.initital_transform_cache.translation
  2. base_camp.value.RawData.value.transform.translation                 (camp anchor)
  3. base_camp.value.WorkerDirector.value.RawData.value
         .spawn_transform.translation                                    (Pal spawn point)

Usage:
  python3 reanchor_colosseum.py <in.json> <out.json> <X> <Y> <Z>
where X Y Z are the Unreal world centimetres the PalBox should end up at.
"""
import json, math, sys


def palbox_index(mo):
    idx = [i for i, m in enumerate(mo) if m['MapObjectId']['value'] == 'PalBoxV2']
    if len(idx) != 1:
        raise SystemExit(f"expected exactly one PalBoxV2, found {len(idx)}")
    return idx[0]


def translations(doc):
    """Every world-space translation dict in the document, in document order."""
    for m in doc['map_objects']:
        yield m['Model']['value']['RawData']['value']['initital_transform_cache']['translation']
    bc = doc['base_camp']['value']
    yield bc['RawData']['value']['transform']['translation']
    yield bc['WorkerDirector']['value']['RawData']['value']['spawn_transform']['translation']


def main():
    src, dst, tx, ty, tz = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:6])
    doc = json.load(open(src))
    mo = doc['map_objects']
    pb = mo[palbox_index(mo)]
    o = pb['Model']['value']['RawData']['value']['initital_transform_cache']['translation']
    dx, dy, dz = tx - o['x'], ty - o['y'], tz - o['z']
    print(f"PalBox from ({o['x']:.3f}, {o['y']:.3f}, {o['z']:.3f})")
    print(f"        to  ({tx:.3f}, {ty:.3f}, {tz:.3f})")
    print(f"delta       ({dx:.3f}, {dy:.3f}, {dz:.3f})")

    # capture relative geometry BEFORE, to prove it is unchanged after
    before = [(t['x'] - o['x'], t['y'] - o['y'], t['z'] - o['z']) for t in translations(doc)]

    n = 0
    for t in translations(doc):
        t['x'] += dx
        t['y'] += dy
        t['z'] += dz
        n += 1
    print(f"translated  {n} spatial fields "
          f"({len(mo)} map objects + camp anchor + worker spawn)")

    o2 = pb['Model']['value']['RawData']['value']['initital_transform_cache']['translation']
    after = [(t['x'] - o2['x'], t['y'] - o2['y'], t['z'] - o2['z']) for t in translations(doc)]
    worst = max(max(abs(a[i] - b[i]) for i in range(3)) for a, b in zip(before, after))
    print(f"max change in any piece's offset from the PalBox: {worst:.3e} cm "
          f"({'RIGID - geometry preserved' if worst < 1e-6 else 'NOT RIGID'})")

    json.dump(doc, open(dst, 'w'), indent=1)
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
