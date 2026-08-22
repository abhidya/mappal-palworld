# Siting the Colosseum Maximus on natural quartz

**Verdict up front: no location in Palworld satisfies the flatness constraint,
and none in this region satisfies the coverage constraint either.** The quartz
is real and the coordinates below are real, but there is no flat 68.5 m building
pad anywhere near quartz. Both gates are recorded below as **unmet**, not
quietly relaxed. What follows is the evidence, the recommended compromise, and
exactly what the compromise costs.

---

## 1. The chosen point

|                        | value |
|------------------------|-------|
| **Unreal world (cm)**  | **X = 9000.0, Y = 98100.0, Z = 4836.2** |
| **In-game map coords** | **(-130, 289)** |
| Quartz nodes in the 3,500 cm base radius | **8** — the global maximum anywhere in the game |
| Spare radius on the outermost node | **93.8 cm** |
| Biome | northern snowfield (Astral Mountains / Land of Absolute Zero side) |
| Nearest dungeon entrance | 28,314 cm (283 m) — clear |
| Nearest existing base edge | 229,629 cm (2.30 km) — clear |
| Nearest settlement building | 4,975 cm (50 m) — outside the base radius |

Z is the anchor height produced by the ground/flatness lane for this exact
centre, not derived independently here, so the two lanes cannot disagree.

Everything else inside the radius: 1 copper node, 2 stone nodes, 1 log node.

The eight nodes, by distance from the Palbox:

| dist (cm) | world X, Y, Z | map |
|---|---|---|
| 2346 | 10633.5, 96416.7, 4190.7 | (-134.0, 292.8) |
| 2714 | 11422.6, 99324.0, 2488.9 | (-127.7, 294.5) |
| 2718 | 9741.7, 95485.7, 4232.3 | (-136.1, 290.9) |
| 2819 | 6613.9, 99600.7, 4831.3 | (-127.1, 284.1) |
| 3073 | 11853.4, 99240.8, 2465.4 | (-127.9, 295.5) |
| 3205 | 11703.3, 96377.9, 4222.6 | (-134.1, 295.1) |
| 3276 | 9723.5, 94905.3, 4130.8 | (-137.3, 290.8) |
| 3406 | 6206.9, 100049.6, 4814.5 | (-126.1, 283.2) |

The eight-node set's minimum enclosing circle is 3,308 cm against a 3,500 cm
base radius, so only a small patch of centres holds all eight and this one
leaves **93.8 cm of slack** on the outermost node. **Place the Palbox
accurately** — a metre of drift costs you a node.

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
kept for the appearance of precision. **Navigate to (-130, 289), then look for
the quartz outcrops** — do not trust the last digit.

---

## 3. The quartz is verified, not assumed

`BP_PalMapObjectSpawner_RockQuartz_C` — 453 actors across all 7,085
`MainGrid_L0_*` World Partition cells of `PL_MainWorld5`.

- Their `loc` values are **world** coordinates, not cell-relative: all 453 fall
  inside the 25,600 cm cell box implied by their own cell name. Cell-relative
  values could not do that.
- The blueprint has no mesh of its own; its cooked name table carries exactly
  one map-object row, **`DamagableRock0003`**. The sibling pattern corroborates
  it: RockStone->0001, RockCopper->0002, RockQuartz->0003, RockCoal->0004.
- `DT_MapObjectMasterDataTable` row `DamagableRock0003` ->
  `BP_MapObject_DamagableRock0003`, which references `SM_RockQuartz` +
  `MI_PalProp_RockQuartz`, carries a `PalMapObjectDropItemParameterComponent`,
  and contains the item FName **`Quartz`**.
- `DT_ItemDataTable` row `Quartz`: `EPalItemTypeA::Material`,
  `EPalItemTypeB::MaterialOre`, `BP_Item_Ore_Quartz`.

This is the natural ore node, not `QuartzPit` (the buildable base-camp pit) and
not `BP_PalMapObjectSpawner_Crystal_C` (349 actors, a different resource in a
different region — zero within 50 m of any quartz).

Siting is exact rather than a heuristic: an optimal fixed-radius disc can always
be slid until two covered nodes lie on its boundary, so enumerating every node
plus both radius-R circle centres through every close pair is guaranteed to
contain an optimum. **8 nodes is provably the most that fit in one 3,500 cm base
radius anywhere in the game.**

---

## 4. Both gates are UNMET — recorded, not relaxed

Palworld's ground is not a Landscape — it is placed static meshes — so ground
height was measured by rebuilding the real ground triangles in world space from
the cooked cells and casting rays down onto them. The measurement is
trustworthy: raycasting under each real quartz actor, node Z minus sampled
ground Z comes out at or near 0.0. The game's own rocks sit on the surface that
was reconstructed.

### Gate 1 — coverage. UNMET.

Target was a full 3,423 cm build disc (the outermost piece) over real ground.

- **12.28% void is the regional floor** in the snow biome; at 8 quartz the best
  achievable is **16.88%**. A <=5% void target is unachievable here.
- Every <=5% void site on the map sits in the eastern/Q4 clusters, at 4–5 quartz
  **and** 61–91 m of relief — worse terrain *and* fewer nodes. There is no
  version of this where chasing coverage improves the outcome.

### Gate 2 — flatness. UNMET, and not by a little.

The cap was **325 cm**, the design's own storey pitch (296 of the 2,776 pieces
sit at arena-floor level, so more than one storey of relief buries or floats a
floor piece).

- Best in the snow region: **2,581 cm**. Best at <=5% void: **6,062 cm**.
- That is **8–19x** the cap.
- An earlier sweep over eight regions found 2,065 centres whose full build disc
  sits on real ground and **zero** within the cap; the flattest fully-covered
  disc anywhere had 4,860 cm of relief and carried at most 3 quartz.

This is a property of Palworld's snow biome — overlapping cliff chunks, no 68.5 m
flat shelf anywhere — not a search failure. Flat ground and quartz never
coincide in this game, so flatness cannot be the deciding axis.

### Caveat on every void figure above

Void is measured against **LOD0 render geometry**. Palworld's collision is a
separate and more continuous representation, so these are **pessimistic lower
bounds** — real in-game coverage is better than the percentages say. The relief
figures, which are what actually disqualify every site, are unaffected.

---

## 5. The compromise, named

Flatness is unattainable everywhere, so the site maximises the stated primary
objective — quartz — and then minimises the damage.

**Terrain figures below are the ground/flatness lane's own**, on its convention:
360 floor pieces, +/-50 cm tolerance, anchor taken as ground at the Palbox cell.
They are quoted as its numbers and are not blended with any measured here.

| | (8800, 97900) previous pick | **(9000, 98100) chosen** |
|---|---|---|
| void | 20.26% | **17.37%** |
| spread | 4,002.2 cm | **3,769.5 cm** |
| buried floor pieces | 15 | **12** |
| floating floor pieces | 189 | 205 |
| p10–p90 | 1,553.2 cm | 2,381.7 cm |

The chosen centre **strictly beats the previous pick on void, spread and buried
pieces at once**, while holding the same eight nodes. It gives up floating
pieces and p10–p90 to do it, and that trade is deliberate: **buried pieces
cannot be placed at all, whereas floating pieces can be built and stilted.**
Buried is therefore the metric that decides, and 12 is the lowest available at 8
quartz.

**What you are accepting:** roughly 17% of the disc has no LOD0 ground under it,
the ground falls 37.7 m across the build, and 217 of 360 floor pieces do not sit
flush — 205 standing clear of the ground, 12 buried. The south-west sector
overhangs; the hillside falls away faster than a single-level arena floor can
follow. Palworld renders and keeps such pieces (a PST-imported base writes
absolute positions regardless of terrain), so the base works — it just stands
partly on air and is partly cut into the slope.

**The honest summary: you are trading appearance for quartz.** Eight nodes is
the global maximum and cannot be had on flat ground, because flat ground with
quartz does not exist in this game.

---

## 6. Runners-up (ground lane's numbers, same convention)

Kept here so the decision is auditable rather than asserted.

| world X, Y | map | quartz | void | spread | buried | floating | not flush |
|---|---|---|---|---|---|---|---|
| **9400, 96900** | (-133, 290) | 6 | 33.78% | 3,513.6 cm | **0** | 184 | 184/360 |
| **10300, 96100** | (-135, 292) | 6 | 36.19% | **2,581.1 cm** | 71 | 80 | **151/360** |

`9400, 96900` is the only centre in the region with **zero buried pieces**.
`10300, 96100` has the **flattest terrain found in the region** and the **best
floor fit** (151/360 not flush, against 217 at the chosen point).

Both were declined because dropping 2 of 8 nodes for roughly double the void
defeats the point of siting on quartz at all — but the trade is real and you may
weigh it differently. If the building looking right matters more than the node
count, `10300, 96100` is the one to take.

**Disqualified outright** (not trade-offs — hard failures):

| world X, Y | map | quartz | reason |
|---|---|---|---|
| 34538.4, 84966.6 | (-159, 345) | 5 | dungeon entrance lock 1,148 cm **inside** the base radius |
| 91308.9, 53900.5 | (-227, 468) | 4 | dungeon entrance lock 1,100 cm inside the radius |
| 61047.8, 197652.7 | (86, 403) | 4 | no cooked ground exists there at all |
| 30922.5, -16631.7 | (-380, 337) | 3 | no cooked ground |
| 90570.5, 54812.5 | (-225, 472) | 4 | no cooked ground |

The "no cooked ground" regions are not an extraction failure: one cell there
holds 13 quartz spawners and exactly 2 static meshes across its whole 256 m
span, and a two-cell ring finds the nearest ground 33 km away. The only
Landscape in reach is `FarMountain`, a backdrop rather than walkable ground.
Those quartz counts cannot be trusted, so the sites were dropped rather than
guessed at.

---

## 7. Getting there

Northern snowfield — bring cold resistance. This is the biome with
`snow_orange` / IceCrocodile spawn tables, and there is a
`BP_PalSpawner_Quest_SnowBoss_KillEnemy_C` quest boss 4,179 cm (42 m) from the
chosen point — outside the base radius, but you will meet it.

Named fast-travel points in this region, from the pak's own text table: **Garden
Beneath the Astral Mountains**, **Pristine Snow Field**, **Snowy Mountain
Crossroads**, **Land of Absolute Zero**. Exact statue positions are not in the
cooked level data (fast-travel points live in save data once discovered), so
they are named rather than given coordinates.

From your existing bases:

| from | distance | bearing |
|---|---|---|
| Stone Works | 2.37 km | 088 deg (E) |
| Lost Camp | 2.45 km | 023 deg (NNE) |
| Wooden Camp | 4.01 km | 334 deg (NNW) |
| Glass Tower | 4.24 km | 325 deg (NW) |

---

## 8. Placing it

The re-anchored blueprint is `colosseum_base_sited.json` in this folder — the
same 2,776 pieces moved by one rigid translation, internal geometry untouched.

1. Travel to map **(-130, 289)** — northern snowfield, cold gear on.
2. Find the quartz. Eight outcrops ring the spot at 23–34 m.
3. **Place the Palbox there yourself.** This is what secures all eight nodes,
   and there is only **93.8 cm of slack** on the outermost one.
4. Import the structure with PST (game fully closed, save in PST afterwards).

### Read this before step 4

**PST's *Import Base* creates a new base offset ~80 m** (collision-avoided)
rather than filling in the base you just founded. 80 m is vastly more than the
93.8 cm of slack the eight nodes leave, so **an import will not land on the
quartz.** The imported copy becomes its own base somewhere nearby, with however
many nodes happen to fall inside it.

**The manually placed Palbox is what secures the quartz; the import only brings
the structure.** Expect to reconcile the two.

Also from the repo's own hard rules: never import a base into the world it was
exported from on PST older than v2.2.8, and the game must be fully closed
whenever PST saves.

---

## 9. Reproducing any of this

    tools/quartz_cluster.py      exact max-coverage siting over the real nodes
    tools/site_sweep.py          centre sweep with the two hard gates
    tools/ground_flatness.py     ground raycast from the cooked ground meshes
    tools/verify_mapcoords.py    the two coordinate-transform checks above
    tools/reanchor_colosseum.py  the rigid re-anchor
    tools/verify_colosseum.py    post-move invariant check
