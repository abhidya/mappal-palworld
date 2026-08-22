# Siting the Colosseum Maximus on natural quartz

**Verdict up front: no location in Palworld satisfies both hard constraints.**
The quartz is real and the coordinates below are real, but there is no flat
68.5 m building pad anywhere near it. What follows is the evidence, the
recommended compromise, and exactly what the compromise costs.

---

## 1. The chosen point

|                        | value |
|------------------------|-------|
| **Unreal world (cm)**  | **X = 8800.0, Y = 97900.0, Z = 4850.5** |
| **In-game map coords** | **(-131, 289)** |
| Quartz nodes in the 3,500 cm base radius | **8** — the global maximum anywhere in the game |
| Spare radius on the outermost node | 131.8 cm |
| Biome | northern snowfield (Astral Mountains / Land of Absolute Zero side) |
| Nearest dungeon entrance | 28,392 cm (284 m) — clear |
| Nearest existing base edge | 229,422 cm (2.29 km) — clear |
| Nearest settlement building | 5,116 cm (51 m) — outside the base radius |

Z is the real ground height at that exact XY, sampled off the cooked ground
meshes — i.e. where the Palbox will actually sit when you place it.

Everything else inside the radius: 1 copper node, 2 stone nodes, 1 log node.

The eight nodes, by distance from the Palbox:

| dist (cm) | world X, Y, Z | map |
|---|---|---|
| 2358 | 10633.5, 96416.7, 4190.7 | (-134.0, 292.8) |
| 2592 | 9741.7, 95485.7, 4232.3 | (-136.1, 290.9) |
| 2770 | 6613.9, 99600.7, 4831.3 | (-127.1, 284.1) |
| 2984 | 11422.6, 99324.0, 2488.9 | (-127.7, 294.5) |
| 3134 | 9723.5, 94905.3, 4130.8 | (-137.3, 290.8) |
| 3278 | 11703.3, 96377.9, 4222.6 | (-134.1, 295.1) |
| 3335 | 11853.4, 99240.8, 2465.4 | (-127.9, 295.5) |
| 3368 | 6206.9, 100049.6, 4814.5 | (-126.1, 283.2) |

Only 23 distinct centres in the whole world hold all eight; the node set's
minimum enclosing circle is 3,308 cm against a 3,500 cm base radius, so there is
just 192 cm of freedom in where the Palbox can go. **Place it accurately.**

---

## 2. World -> in-game map coordinates

    map_x = (world_y - 158000) / 459.42
    map_y = (world_x + 123888) / 459.42

**The axes swap.** The map's horizontal axis is driven by world **Y**, the
map's vertical axis by world **X**. The offsets are the midpoint of Palworld's
world box; 459.42 is world centimetres per map unit (the world box is 918,000 cm
across and the map spans -1000..+1000, so 918000/2000 = 459).

The constants are the published palworld-coord values. The part that had to be
established from the pak is the axis order and that the offsets actually land
things in the right place, because an axis swap or sign error is invisible in
the constants alone. Two independent checks, both against extracted data
(`tools/verify_mapcoords.py` re-runs them):

**Check 1 — the game's own quest anchor.** `DT_PalQuestLocationData` row
`Main_UnlockFastTravel` (the first fast-travel unlock, on the Plateau of
Beginnings) is at world (-358785, 267940).

| transform | gives | documented Plateau |
|---|---|---|
| swapped axes | (239, -511) | ~(233, -488) |
| plain axes | (-511, 239) | wrong quadrant entirely |

**Check 2 — published quartz spots must land on real quartz.** Five
independently published Pure-Quartz farming coordinates, converted to world and
checked against the 453 `BP_PalMapObjectSpawner_RockQuartz_C` actors extracted
from the pak:

| documented map | -> world | real quartz within 100 m |
|---|---|---|
| (-209, 250) | (-9033, 61981) | 8 |
| (-212, 249) | (-9492, 60603) | 8 |
| (-215, 253) | (-7655, 59225) | 8 |
| (-259, 394) | (57123, 39010) | 5 |
| (-415, 470) | (92039, -32659) | 3 |

Every one lands on real quartz. On the unswapped transform they land on empty
terrain, which is what makes this the discriminating test.

**Accuracy.** Check 1 leaves a ~23 map-unit (~105 m) residual, but it compares a
quest trigger against a community-recommended base spot, which are genuinely
different points, so that is an upper bound on the error rather than a measure
of it. I tried least-squares refitting the offsets against quartz-cluster
centroids; it diverged (the published spots are not cluster centroids, so the
estimator is biased) and made check 1 worse, so it was discarded rather than
kept for the appearance of precision. **Navigate to (-131, 289), then look for
the quartz outcrops** — do not trust the last digit.

---

## 3. The quartz is verified, not assumed

`BP_PalMapObjectSpawner_RockQuartz_C` — 453 actors across all 7,085
`MainGrid_L0_*` World Partition cells of `PL_MainWorld5`.

- Their `loc` values are **world** coordinates, not cell-relative: all 453 fall
  inside the 25,600 cm cell box implied by their own cell name. Cell-relative
  values could not do that.
- The blueprint is a `PalMapObjectSpawnerSimple` with no mesh of its own; its
  cooked name table carries exactly one map-object row, **`DamagableRock0003`**.
  The sibling pattern corroborates it: RockStone->0001, RockCopper->0002,
  RockQuartz->0003, RockCoal->0004.
- `DT_MapObjectMasterDataTable` row `DamagableRock0003` ->
  `BP_MapObject_DamagableRock0003`, which references `SM_RockQuartz` +
  `MI_PalProp_RockQuartz`, carries a `PalMapObjectDropItemParameterComponent`,
  and contains the item FName **`Quartz`**.
- `DT_ItemDataTable` row `Quartz`: `EPalItemTypeA::Material`,
  `EPalItemTypeB::MaterialOre`, `BP_Item_Ore_Quartz`.

This is the natural ore node, not `QuartzPit` (which is the buildable base-camp
pit) and not `BP_PalMapObjectSpawner_Crystal_C` (349 actors, a different
resource in a different region — zero of them are within 50 m of any quartz).

Siting is exact rather than a heuristic: an optimal fixed-radius disc can always
be slid until two covered nodes lie on its boundary, so enumerating every node
plus both radius-R circle centres through every close pair is guaranteed to
contain an optimum. **8 nodes is provably the most that fit in one 3,500 cm base
radius anywhere in the game.**

---

## 4. Why no site clears the flatness gate

Palworld's ground is not a Landscape — it is placed static meshes — so ground
height was measured by rebuilding the real ground triangles in world space from
the cooked cells and casting rays down onto them.

**The measurement is trustworthy.** Raycasting under each real quartz actor,
node Z minus sampled ground Z comes out at or near **0.0** for essentially every
node. The game's own rocks sit exactly on the surface that was reconstructed.

**Two hard gates, both derived from the build itself, not from round numbers:**

1. **Coverage** — the full 3,423 cm build radius (the outermost piece) must be
   over real ground. A rim cutting the disc means pieces hanging over a void.
2. **Flatness** — ground relief across that disc must stay within **325 cm**,
   the design's storey pitch. 296 of the 2,776 pieces sit at arena-floor level,
   so more than one storey of relief buries or floats a floor piece.

**Result of a centre sweep over eight regions** (every centre on a 200 cm
lattice, ground sampled on a 200 cm lattice):

| | |
|---|---|
| centres whose full 3,423 cm disc is on real ground | **2,065** |
| ...of those, also within the 325 cm flatness cap | **0** |
| flattest fully-covered disc found anywhere | **4,860 cm** of relief (15x the cap) |
| most quartz on any fully-covered disc | **3** |

So the two gates are not merely hard to satisfy together — full coverage and
flatness are independently available but never coincide with quartz. Quartz in
Palworld sits on snow mountainside and sky islands; there is no quartz mesa big
enough to take a 68.5 m disc.

---

## 5. The compromise, named

Flatness is unattainable at every candidate, so it cannot be the deciding axis.
The recommendation therefore **maximises the stated primary objective — quartz —
and picks the centre that minimises void and relief among the 8-node options.**

Among the 23 centres that hold eight nodes, this one has the fewest floor pieces
off the ground and the flattest core (p10–p90 1,614 cm against 2,383 cm for the
alternatives); it gives up ~3 points of void coverage to get that.

**What you are accepting at (8800.0, 97900.0):**

| | |
|---|---|
| ground relief across the 3,423 cm build disc | 3,899 cm (39 m) |
| middle 80% of that relief | 1,614 cm (16 m) |
| disc area with no ground under it | 21.0% |
| arena-floor pieces (296 total) over void | 56 |
| ...buried more than 50 cm | 12 |
| ...floating more than 50 cm | 155 |

So roughly three quarters of the arena floor does not meet the ground: the
south-west sector overhangs a drop, and the hillside falls away far faster than
the single-level floor can follow. Palworld renders and keeps such pieces
(a PST-imported base writes absolute positions, terrain notwithstanding), so the
base works — it just stands partly on air and is partly cut into the slope.

Only 12 pieces end up buried, which is the number worth caring about: buried
pieces are the ones you cannot see or reach. This centre was chosen partly
because alternatives traded those 12 for 58–129 buried pieces.

**The honest summary: you are trading appearance for quartz.** Eight nodes is
the global maximum and cannot be had on flat ground, because flat ground with
quartz does not exist in this game. If the building looking right matters more
than the node count, take a runner-up below — but note that none of them is flat
either; they are merely less bad.

The void figure above is measured against a deliberately conservative ground
set (the classifier that names Palworld's ground meshes was written for
non-snow biomes and rejects snow piles, scree and rock formations, which are
walkable here). Real coverage is therefore somewhat better than 21% void, and
the relief numbers — which are what actually disqualify every site — are
unaffected.

---

## 6. Runners-up and why they lost

**Other centres that also hold eight nodes** (all within 200 m of the chosen
point — the eight-node set barely moves):

| world X, Y | void | p10–p90 | buried floor pieces | why it lost |
|---|---|---|---|---|
| 8900.0, 98200.0 | 17.9% | 2,381 cm | 12 | best coverage of any 8-node centre, but 47% more relief through the middle |
| 8900.0, 98000.0 | 19.2% | 2,370 cm | 11 | same trade, marginally worse coverage |
| 8800.0, 97700.0 | 23.9% | 1,503 cm | 11 | flattest core found, but the worst coverage of the group |

**Fewer-quartz alternatives:**

| world X, Y | map | quartz | why it lost |
|---|---|---|---|
| 11800.0, 95900.0 | (-135, 295) | 7 | flattest of the 7-node discs (p10–p90 1,098 cm) but 26.1% void and 129 buried floor pieces |
| 4656.0, 102318.9 | (-121, 280) | 6 | ~40% of the disc over void — worst coverage of the quartz-rich options |
| 11530.4, 95138.9 | (-137, 295) | 5 | flat core, but more void and gives up 3 quartz |
| 82546.8, 36438.6 | (-265, 449) | 4 | best-covered site found (96%), but only 4 quartz and 80 m of relief |
| 2819.8, 15201.6 | (-311, 276) | 3 | 98% covered — but a hillside, 117 m of relief, and only 3 quartz |

**Disqualified outright:**

| world X, Y | map | quartz | reason |
|---|---|---|---|
| 34538.4, 84966.6 | (-159, 345) | 5 | dungeon entrance lock 1,148 cm **inside** the base radius |
| 91308.9, 53900.5 | (-227, 468) | 4 | dungeon entrance lock 1,100 cm inside the radius |
| 61047.8, 197652.7 | (86, 403) | 4 | no cooked ground exists there at all |
| 30922.5, -16631.7 | (-380, 337) | 3 | no cooked ground |
| 90570.5, 54812.5 | (-225, 472) | 4 | no cooked ground |

The three "no cooked ground" regions are not an extraction failure: one cell
there holds 13 quartz spawners and exactly 2 static meshes in its entire 256 m
span, and a full two-cell ring finds the nearest ground 33 km away. The only
Landscape in reach is `FarMountain`, a yaw-160° backdrop rather than walkable
ground. Whatever renders in those places is not in the cooked geometry, so their
quartz counts cannot be trusted and the sites were dropped rather than guessed
at.

---

## 7. Getting there

The site is in the northern snowfield. Bring cold-resistance — this is the
biome with `snow_orange` / IceCrocodile spawn tables and a
`BP_PalSpawner_Quest_SnowBoss_KillEnemy_C` quest boss 39 m from the chosen
point (outside the base radius, but you will meet it).

Named fast-travel points in this region, from the pak's own text table: **Garden
Beneath the Astral Mountains**, **Pristine Snow Field**, **Snowy Mountain
Crossroads**, **Land of Absolute Zero**. Their exact statue positions are not in
the cooked level data (fast-travel points live in save data once discovered), so
they are named rather than given coordinates here.

From your existing bases:

| from | distance | bearing |
|---|---|---|
| Stone Works | 2.36 km | 088 deg (E) |
| Lost Camp | 2.45 km | 023 deg (NNE) |
| Wooden Camp | 4.01 km | 334 deg (NNW) |
| Glass Tower | 4.24 km | 325 deg (NW) |

---

## 8. Placing it

The re-anchored blueprint is `colosseum_base_sited.json` in this folder. It is
the same 2,776 pieces moved by one rigid translation — the internal geometry is
byte-identical.

1. Travel to map **(-131, 289)** — northern snowfield, cold gear on.
2. Find the quartz. Eight outcrops ring the spot at 24–34 m; stand in the middle
   of them, on the high ground on the north-east side of the hollow.
3. **Place the Palbox there yourself.** This is what guarantees all eight nodes
   fall inside the base radius — there is only 132 cm of slack on the outermost
   one, so a careless placement drops nodes.
4. Import the structure with PST (game fully closed, save in PST afterwards).

**Read this before step 4.** PST's *Import Base* creates a **new base offset
~80 m** (collision-avoided) rather than filling in the base you just founded.
80 m is far larger than the 1.3 m of spare radius the eight nodes leave, so
**an import will not land on the quartz** — the imported copy becomes its own
base somewhere nearby, with however many nodes happen to fall inside it. The
manually placed Palbox is the thing that secures the quartz; treat the import as
the structure and expect to reconcile the two. Also from the repo's own hard
rules: never import a base into the world it was exported from on PST older than
v2.2.8, and the game must be fully closed whenever PST saves.

---

## 9. Reproducing any of this

    tools/quartz_cluster.py      exact max-coverage siting over the real nodes
    tools/site_sweep.py          centre sweep with the two hard gates
    tools/ground_flatness.py     ground raycast from the cooked ground meshes
    tools/verify_mapcoords.py    the two coordinate-transform checks above
    tools/reanchor_colosseum.py  the rigid re-anchor
    tools/verify_colosseum.py    post-move invariant check
