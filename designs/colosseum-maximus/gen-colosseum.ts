// Colosseum Maximus — generated blueprint.
//
// Builds a tiered amphitheatre on the verified 400 cm lattice with a central
// 28-storey spiral tower, then hands the placement list to MapPal's own
// reconcileExport() so every emitted object is a real donor bundle with fresh,
// mutually consistent GUIDs (src/model/writeback.ts).
//
// Skeleton file: fixtures/calibration_01.json — its PalBoxV2 is kept (moved to
// the arena centre, which is what the base_camp anchor follows); all its other
// objects are dropped by reconcileExport's deletion path.
//
// usage (from the repo root): npx tsx designs/colosseum-maximus/gen-colosseum.ts designs/colosseum-maximus/colosseum_base.json
import { readFileSync, writeFileSync } from "node:fs";
import { loadBlueprint, serializeBlueprint } from "../../src/parse/blueprint";
import { extractObjects } from "../../src/model/blueprintView";
import { mintGuid, reconcileExport, type DonorLibrary } from "../../src/model/writeback";
import { validateLinkage } from "../../src/model/validate";
import type { PlacedObject, Vec3 } from "../../src/model/types";
import donorsJson from "../../src/data/donors.json";
import objectsJson from "../../src/data/objects.json";

/* eslint-disable @typescript-eslint/no-explicit-any */
const OUT = process.argv[2] ?? "../colosseum_base.json";
const SKELETON = "fixtures/calibration_01.json";
const DONORS = (donorsJson as unknown as { donors: DonorLibrary }).donors;
const TYPES = (objectsJson as any).types as Record<string, unknown>;

const GRID = 400; // cm, horizontal pitch (docs/CALIBRATION.md)
const V = 325; // cm, vertical pitch per storey
const AREA_RANGE = 3500; // cm, base build radius
const TOP = 27; // storeys; the finial lands at 28 -> 91.0 m, matching the tallest verified real structure

// ---------------------------------------------------------------- placement
const placed: PlacedObject[] = [];
const used = new Set<string>(); // "type@x,y,z" dedup
let ORIGIN: Vec3 = { x: 0, y: 0, z: 0 };

const yawQuat = (deg: number) => {
  const a = (deg * Math.PI) / 180 / 2;
  return { x: 0, y: 0, z: Math.sin(a), w: Math.cos(a) };
};
/** Wall/stair convention (verified against calibration_01): a piece sitting on
 *  the tile edge in direction d has yaw = atan2(-dy, -dx) — its outward normal
 *  (and a stair's ascent) points along d. */
const facingYaw = (dx: number, dy: number) => (Math.atan2(-dy, -dx) * 180) / Math.PI;

function put(typeId: string, x: number, y: number, z: number, yawDeg = 0) {
  if (!TYPES[typeId]) throw new Error(`unknown MapObjectId ${typeId}`);
  if (!DONORS[typeId]) throw new Error(`no donor bundle for ${typeId}`);
  const key = `${typeId}@${Math.round(x)},${Math.round(y)},${Math.round(z)}`;
  if (used.has(key)) return;
  used.add(key);
  placed.push({
    id: mintGuid(),
    typeId,
    position: { x: ORIGIN.x + x, y: ORIGIN.y + y, z: ORIGIN.z + z },
    rotation: yawQuat(yawDeg),
    scale: { x: 1, y: 1, z: 1 },
    origin: "placed",
  });
}
const lvl = (l: number) => l * V;

// ------------------------------------------------------------------ lattice
type Cell = [number, number];
const cellR = (c: Cell) => Math.hypot(c[0], c[1]);
const ringOf = (c: Cell) => Math.round(cellR(c));
const key = (c: Cell) => `${c[0]},${c[1]}`;

const R = 9;
const allCells: Cell[] = [];
for (let i = -R; i <= R; i++) for (let j = -R; j <= R; j++) allCells.push([i, j]);

/** Radius guard: no piece may stick outside area_range. */
const fits = (c: Cell) =>
  Math.hypot(Math.abs(c[0]) * GRID + GRID / 2, Math.abs(c[1]) * GRID + GRID / 2) <= AREA_RANGE;

const ring = (k: number) => allCells.filter((c) => ringOf(c) === k && fits(c));

const TOWER = 2; // 5x5 tower footprint: max(|i|,|j|) <= 2
const inTower = (c: Cell) => Math.max(Math.abs(c[0]), Math.abs(c[1])) <= TOWER;

const ARENA = allCells.filter((c) => !inTower(c) && ringOf(c) >= 3 && ringOf(c) <= 4);
const TIER = [5, 6, 7].map((k) => ring(k));
const GALLERY = ring(8);
const gallerySet = new Set(GALLERY.map(key));

// -------------------------------------------------------- 1. arena + tower pad
// Tower ground pad (5x5) and the arena sand ring around it, all at level 0.
for (const c of allCells) {
  if (!inTower(c)) continue;
  put("Ancient_foundation", c[0] * GRID, c[1] * GRID, lvl(0));
}
const arenaStairCells = new Set<string>();
const DIRS: Cell[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];
// vomitoria: 4 radial aisles, arena -> tier1 -> tier2 -> tier3 -> gallery
for (const d of DIRS) {
  for (let k = 4; k <= 7; k++) {
    const c: Cell = [d[0] * k, d[1] * k];
    arenaStairCells.add(key(c));
    const level = k - 4; // ring4@0, ring5@1, ring6@2, ring7@3 -> gallery@4
    put("Stone_Stair", c[0] * GRID, c[1] * GRID, lvl(level), facingYaw(d[0], d[1]));
  }
}
for (const c of ARENA) {
  if (arenaStairCells.has(key(c))) continue;
  put("Stone_Foundation", c[0] * GRID, c[1] * GRID, lvl(0));
}

// ------------------------------------------------------- 2. cavea (seating tiers)
// Ring 5 @ L1, ring 6 @ L2, ring 7 @ L3, each carried by a radial pillar
// substructure — the colosseum's own load-bearing trick, visible through the
// outer arcade.
TIER.forEach((cells, idx) => {
  const level = idx + 1;
  for (const c of cells) {
    const x = c[0] * GRID;
    const y = c[1] * GRID;
    if (!arenaStairCells.has(key(c))) put("Stone_Foundation", x, y, lvl(level));
    for (let s = 0; s < level; s++) put("Stone_pillar", x, y, lvl(s));
    // railing on the inward-facing edges (the drop toward the arena)
    for (const d of DIRS) {
      const n: Cell = [c[0] + d[0], c[1] + d[1]];
      if (cellR(n) >= cellR(c)) continue;
      if (ringOf(n) === ringOf(c)) continue;
      if (arenaStairCells.has(key(c)) || arenaStairCells.has(key(n))) continue;
      put("Ancient_Fence", x + d[0] * (GRID / 2), y + d[1] * (GRID / 2), lvl(level), facingYaw(d[0], d[1]));
    }
  }
});

// ---------------------------------------------- 3. outer facade + top gallery
// Four superimposed arcade storeys (L0-L3) carrying the ring-8 gallery deck at
// L4, then an attic storey and a cornice — the Colosseum's elevation.
const ARCADE = ["Ancient_WallGate", "Ancient_WindowWall", "Ancient_WallGate", "Ancient_WindowWall"];
for (const c of GALLERY) {
  const x = c[0] * GRID;
  const y = c[1] * GRID;
  if (!arenaStairCells.has(key(c))) put("Ancient_foundation", x, y, lvl(4));
  for (const d of DIRS) {
    const n: Cell = [c[0] + d[0], c[1] + d[1]];
    if (gallerySet.has(key(n))) continue;
    if (cellR(n) <= cellR(c)) continue;
    const ex = x + d[0] * (GRID / 2);
    const ey = y + d[1] * (GRID / 2);
    const yw = facingYaw(d[0], d[1]);
    for (let s = 0; s <= 3; s++) put(ARCADE[s], ex, ey, lvl(s), yw);
    put("Ancient_wall", ex, ey, lvl(4), yw); // attic
    put("Ancient_SlantedRoof", ex, ey, lvl(5), yw); // cornice
  }
  // arcade piers between the bays
  for (const d of DIRS) {
    const n: Cell = [c[0] + d[0], c[1] + d[1]];
    if (!gallerySet.has(key(n))) continue;
    for (let s = 0; s <= 4; s++) {
      put("Ancient_Pillars", x + d[0] * (GRID / 2), y + d[1] * (GRID / 2), lvl(s));
    }
  }
}

// -------------------------------------------------------------- 4. the tower
// 5x5 shell, hollow 3x3 core, spiral staircase running the 16 perimeter tiles:
// three stair tiles per side, a landing at each corner -> 12 storeys per loop.
const ringTiles: Cell[] = [];
for (let i = -2; i <= 2; i++) ringTiles.push([i, -2]);
for (let j = -1; j <= 2; j++) ringTiles.push([2, j]);
for (let i = 1; i >= -2; i--) ringTiles.push([i, 2]);
for (let j = 1; j >= -1; j--) ringTiles.push([-2, j]);
const isCorner = (c: Cell) => Math.abs(c[0]) === 2 && Math.abs(c[1]) === 2;

let level = 0;
let k = 0;
let guard = 0;
const landingLevels: number[] = [];
while (level < TOP && guard++ < 400) {
  const c = ringTiles[k % ringTiles.length];
  const next = ringTiles[(k + 1) % ringTiles.length];
  if (isCorner(c)) {
    put("Ancient_roof", c[0] * GRID, c[1] * GRID, lvl(level));
    landingLevels.push(level);
  } else {
    const d: Cell = [next[0] - c[0], next[1] - c[1]];
    put("Ancient_stair", c[0] * GRID, c[1] * GRID, lvl(level), facingYaw(d[0], d[1]));
    level += 1;
  }
  k += 1;
}

const DECKS = [6, 12, 18, 24];
const DECK_SET = new Set(DECKS);

// tower shell: 20 wall segments per storey on the 5x5 boundary + a colonnade
const towerBoundary: Array<{ x: number; y: number; yaw: number; mid: boolean }> = [];
for (const c of ringTiles) {
  for (const d of DIRS) {
    const n: Cell = [c[0] + d[0], c[1] + d[1]];
    if (inTower(n)) continue;
    towerBoundary.push({
      x: c[0] * GRID + d[0] * (GRID / 2),
      y: c[1] * GRID + d[1] * (GRID / 2),
      yaw: facingYaw(d[0], d[1]),
      mid: !isCorner(c),
    });
  }
}
// boundary junction points: a pillar at every 4 m along the tower perimeter,
// giving the shaft a continuous colonnade instead of a flat panel grid
const towerPiers: Array<[number, number]> = [];
{
  const H = 2 * GRID + GRID / 2; // 1000 cm — half the 5x5 footprint
  for (let k = -2; k <= 2; k++) {
    towerPiers.push([k * GRID, -H], [k * GRID, H], [-H, k * GRID], [H, k * GRID]);
  }
}
for (let s = 0; s < TOP; s++) {
  for (const b of towerBoundary) {
    // ground storey and every deck storey open into loggias so Pals can walk in
    const t =
      (s === 0 || DECK_SET.has(s)) && b.mid
        ? "Ancient_WallGate"
        : s % 2 === 1
          ? "Ancient_WindowWall"
          : "Ancient_wall";
    put(t, b.x, b.y, lvl(s), b.yaw);
  }
  for (const [px, py] of towerPiers) put("Ancient_Pillars", px, py, lvl(s));
}
// interior decks every 6 storeys (all land on spiral landing levels)
for (const dl of DECKS) {
  for (let i = -1; i <= 1; i++)
    for (let j = -1; j <= 1; j++) put("Ancient_roof", i * GRID, j * GRID, lvl(dl));
}
// crown: full 5x5 observation deck at the top, parapet, pyramid finial
for (let i = -2; i <= 2; i++)
  for (let j = -2; j <= 2; j++) put("Ancient_roof", i * GRID, j * GRID, lvl(TOP));
for (const c of ringTiles) {
  for (const d of DIRS) {
    const n: Cell = [c[0] + d[0], c[1] + d[1]];
    if (inTower(n)) continue;
    put(
      "Ancient_Fence",
      c[0] * GRID + d[0] * (GRID / 2),
      c[1] * GRID + d[1] * (GRID / 2),
      lvl(TOP),
      facingYaw(d[0], d[1])
    );
  }
}
for (let i = -1; i <= 1; i++)
  for (let j = -1; j <= 1; j++) put("Ancient_PyramidRoof", i * GRID, j * GRID, lvl(TOP + 1));

// =========================================================== FACILITIES ====
// Level-80 endgame loadout. Benchmarked against the gallery's
// venom8698_Ultimate_Level80_Base_04 (845 pieces) and extended.
const FLOOR_EPS = 1; // furniture rests ~1 cm above its foundation (calibration)

interface Slot { c: Cell; x: number; y: number; z: number; yaw: number; level: number }
const occupied = new Set<string>();
const occKey = (level: number, c: Cell) => `${level}:${c[0]},${c[1]}`;

/** Cells of a ring, ordered around the circle, minus the aisle stairs. */
function slots(cells: Cell[], level: number): Slot[] {
  return [...cells]
    .sort((p, q) => Math.atan2(p[1], p[0]) - Math.atan2(q[1], q[0]))
    .filter((c) => !arenaStairCells.has(key(c)))
    .map((c) => ({
      c,
      x: c[0] * GRID,
      y: c[1] * GRID,
      z: lvl(level) + FLOOR_EPS,
      yaw: (Math.atan2(-c[1], -c[0]) * 180) / Math.PI, // face the arena
      level,
    }));
}

function fill(label: string, avail: Slot[], list: string[]) {
  const wanted = list.filter((t) => TYPES[t] !== undefined);
  if (wanted.length > avail.length) {
    throw new Error(`${label}: ${wanted.length} facilities but only ${avail.length} slots`);
  }
  // scatter the list around the ring instead of laying it down in one arc, so
  // the bulky props (ore nodes, furnaces) don't pile into a single quadrant
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  let step = 7;
  while (gcd(step, avail.length) !== 1) step++;
  wanted.forEach((t, i) => {
    const s = avail[(i * step) % avail.length];
    occupied.add(occKey(s.level, s.c));
    put(t, s.x, s.y, s.z, s.yaw);
  });
  console.log(`  ${label}: ${wanted.length}/${avail.length} slots used`);
}

// --- arena floor (rings 3-4, L0): the works ---------------------------------
fill("arena/industry", slots(ARENA, 0), [
  "AncientBlastFurnace", "AncientBlastFurnace", "AncientBlastFurnace",
  "BlastFurnace4", "BlastFurnace4",
  "AncientWorkBench", "AncientWorkBench", "AncientWorkBench", "AncientWorkBench",
  "AncientMultiProduct", "AncientMultiProduct",
  "Factory_Hard_04", "Factory_Hard_04",
  "WeaponFactory_Dirty_04", "WeaponFactory_Dirty_04",
  "SphereFactory_Black_04", "SphereFactory_Black_04",
  "SkyIslandOrePit", "SkyIslandOrePit", "StonePit", "Stonepit", "CoalPit",
  "CopperPit", "QuartzPit", "SulfurPit", "CrystalPit", "OilPump02",
  "IceCrusher",
  "ElectricKitchen", "HugeKitchen", "AncientCookingStove", "AncientCookingStove",
  "Cauldron", "ElectricCooler", "Refrigerator",
  "AncientElectricGenerator", "AncientElectricGenerator",
  "ElectricGenerator_Large", "ElectricGenerator_Large",
  "TransmissionTower",
]);

// --- tier 1 (ring 5, L1): storage -------------------------------------------
fill("tier1/storage", slots(TIER[0], 1), [
  "GuildChest", "GlobalPalStorage", "DimensionPalStorage",
  ...Array.from({ length: 14 }, () => "ItemChest_04"),
  "Container01_Iron", "Container01_Iron",
  "CoolerBox", "CoolerPalFoodBox", "PalFoodBox", "PalMedicineBox", "ToolBoxV1",
]);

// --- palbox chamber (tower ground floor, L0): the guild's power + drop-off --
{
  const chamber: Cell[] = [];
  for (let i = -1; i <= 1; i++)
    for (let j = -1; j <= 1; j++) if (i !== 0 || j !== 0) chamber.push([i, j]);
  const kit = [
    "EnergyStorage_Electric", "ItemChest_04", "EnergyStorage_Electric", "ItemChest_04",
    "EnergyStorage_Electric", "ItemChest_04", "EnergyStorage_Electric", "ItemChest_04",
  ];
  chamber.forEach((c, i) =>
    put(kit[i], c[0] * GRID, c[1] * GRID, lvl(0) + FLOOR_EPS, (Math.atan2(-c[1], -c[0]) * 180) / Math.PI)
  );
}

// --- tier 2 (ring 6, L2): farms, ranch, breeding ----------------------------
fill("tier2/farms", slots(TIER[1], 2), [
  "FarmBlockV2_Berries", "FarmBlockV2_wheet", "FarmBlockV2_tomato",
  "FarmBlockV2_Lettuce", "FarmBlockV2_Onion", "FarmBlockV2_Potato",
  "FarmBlockV2_Carrot", "Farm_SkillFruits", "Farm_SkillFruits",
  "AncientFarmBlock", "AncientFarmBlock",
  "MonsterFarm", "MonsterFarm", "MonsterFarm",
  "MultiElectricHatchingPalEggWithBreed", "MultiElectricHatchingPalEggWithBreed",
  "MultiElectricHatchingPalEggWithBreed",
  "FishingPond2", "FishingPond1",
  "FarmBlockV2_Berries", "FarmBlockV2_wheet", "FarmBlockV2_tomato",
  "FarmBlockV2_Lettuce", "FarmBlockV2_Onion", "FarmBlockV2_Potato",
  "FarmBlockV2_Carrot",
  "FarmBlockV2_Berries", "FarmBlockV2_wheet", "FarmBlockV2_tomato",
  "FarmBlockV2_Lettuce", "FarmBlockV2_Onion", "FarmBlockV2_Potato",
  "FarmBlockV2_Carrot", "Farm_SkillFruits", "AncientFarmBlock", "MonsterFarm",
]);

// --- tier 3 (ring 7, L3): dormitory, clinic, spa ----------------------------
fill("tier3/dorm", slots(TIER[2], 3), [
  "Ancient_Clinic", "Clinic", "MedicineFacility_03", "MedicineFacility_03",
  "OperatingTable", "Lab",
  "Ancient_Spa", "Ancient_Spa", "Spa3", "Spa3",
  ...Array.from({ length: 10 }, () => "Ancient_MedicalPalBed"),
  ...Array.from({ length: 12 }, () => "MedicalPalBed_05"),
  "PlayerBed_03", "PlayerBed_03", "PlayerBed_03", "PlayerBed_03",
]);

// --- gallery (ring 8, L4): mining terrace, camp management, defences --------
fill("gallery/mining+defence", slots(GALLERY, 4), [
  "Factory_Money", "CompositeDesk", "RepairBench", "WorkBench_SkillUnlock",
  "DismantlingConveyor", "DismantlingConveyor",
  "AncientRelicRecycler", "AncientRelicRecycler", "Crusher", "FlourMill",
  "StationDeforest3", "StationDeforest3", "MiningTool",
  "BaseCampItemDispenser", "BaseCampWorkerExtraStation", "BaseCampWorkHard03",
  "WorkSpeedIncrease1", "SanityDecrease1", "BaseCampBattleDirector",
  "Expedition", "Expedition", "CharacterRankUp", "SkinChange", "Altar",
  "DefenseMachinegun", "DefenseMissile", "DefenseBowGun",
  "DefenseMachinegun", "DefenseMissile", "DefenseBowGun",
  "DefenseMachinegun", "DefenseMissile", "DefenseBowGun",
  "DefenseWait", "DefenseWait",
]);

// tower deck turrets
for (const dl of DECKS) {
  put("DefenseMachinegun", -2 * GRID, 0, lvl(dl) + FLOOR_EPS, 0);
  put("DefenseMissile", 2 * GRID, 0, lvl(dl) + FLOOR_EPS, 180);
}

// ============================================================= DECOR =======
const BANNERS = [
  "Believer_Banner", "DarkIsland_Banner", "FireCult_Banner", "Hunter_Banner",
  "Ninja_Banner", "Police_Banner", "Scientist_Banner", "SkyIsland_Banner",
];
const FLAGS = [
  "Believer_Flag", "DarkIsland_Flag", "FireCult_Flag",
  "Ninja_Flag", "Police_Flag", "Scientist_Flag", "SkyIsland_Flag",
];
const TREES = [
  "FurnitureTree01_Cherry", "FurnitureTree02_Cherry", "FurnitureTree03_Cherry",
  "FurnitureTree01_Green", "FurnitureTree03_Green", "FurnitureTree01_Tropical",
  "FurnitureTree02_Tropical", "FurnitureTree01_Yellow", "FurnitureTree02_Red",
  "FurnitureTree03_Bamboo", "FurnitureTree01_Bamboo",
];
const BUSHES = [
  "FurnitureBush01_Flower", "FurnitureBush01_Green", "FurnitureBush02_Flower",
  "FurnitureBush01_Yellow", "FurnitureBush01_Tropical",
];
const IVY = ["Ivy01", "Ivy02", "Ivy03"];
const LAMPS = [
  "Light_LightPole01", "Light_LightPole02", "Light_LightPole03", "Light_LightPole04",
];

// banners + flags alternating around the facade attic, pulled just inside the
// wall line so they fly over the parapet
GALLERY.forEach((c, idx) => {
  const t = idx % 2 === 0 ? BANNERS[idx % BANNERS.length] : FLAGS[idx % FLAGS.length];
  put(t, c[0] * GRID * 0.9, c[1] * GRID * 0.9, lvl(5) + FLOOR_EPS, (Math.atan2(c[1], c[0]) * 180) / Math.PI);
});

// lamp posts along the arena rim
ARENA.filter((c) => ringOf(c) === 4).forEach((c, idx) => {
  if (arenaStairCells.has(key(c)) || occupied.has(occKey(0, c))) return;
  put(LAMPS[idx % LAMPS.length], c[0] * GRID, c[1] * GRID, lvl(0) + FLOOR_EPS, (Math.atan2(-c[1], -c[0]) * 180) / Math.PI);
});

// planting and lighting on the tiers — offset into the corner of each cell so
// it stands beside the facility rather than through it
TIER.forEach((cells, ti) => {
  const level = ti + 1;
  cells.forEach((c, idx) => {
    if (arenaStairCells.has(key(c))) return;
    const z = lvl(level) + FLOOR_EPS;
    const ox = c[0] * GRID + 140;
    const oy = c[1] * GRID + 140;
    const inward = (Math.atan2(-c[1], -c[0]) * 180) / Math.PI;
    if (idx % 3 === 0) put(TREES[(idx + ti) % TREES.length], ox, oy, z, inward);
    else if (idx % 3 === 1) put(BUSHES[(idx + ti) % BUSHES.length], ox, oy, z, inward);
    else put(IVY[idx % IVY.length], ox, oy, z, inward);
    if (idx % 4 === 2) put("CeilingLamp", c[0] * GRID - 140, c[1] * GRID - 140, z + 300, inward);
    if (idx % 6 === 5) put("Bench_Wood", c[0] * GRID - 140, c[1] * GRID + 140, z, inward);
  });
});

// ivy and candle sconces climbing the outer arcade piers
GALLERY.forEach((c, idx) => {
  if (idx % 2 !== 0) return;
  const x = c[0] * GRID * 0.93;
  const y = c[1] * GRID * 0.93;
  const inward = (Math.atan2(-c[1], -c[0]) * 180) / Math.PI;
  put(IVY[idx % IVY.length], x, y, lvl(2) + FLOOR_EPS, inward);
  put("Light_CandleSticks_Wall", x, y, lvl(1) + 150, inward + 180);
});

// torches climbing the tower's four corners, every second storey
for (let s = 1; s < TOP; s += 2) {
  for (const sx of [-1, 1])
    for (const sy of [-1, 1])
      put("Torch", sx * (2 * GRID + GRID / 2 - 30), sy * (2 * GRID + GRID / 2 - 30), lvl(s) + FLOOR_EPS, 0);
}
// wall torches inside the shell on every landing level
for (const ll of landingLevels) {
  for (const d of DIRS)
    put("WallTorch", d[0] * (2 * GRID - 40), d[1] * (2 * GRID - 40), lvl(ll) + 150, facingYaw(d[0], d[1]));
}

// the imperial box: a furnished pavilion carved out of tier 3, facing the arena
{
  const bx = -7 * GRID;
  const z = lvl(3) + FLOOR_EPS;
  put("Rug01_Stone", bx, 0, z, 0);
  put("Rug02_Stone", bx, GRID, z, 0);
  put("Rug03_Stone", bx, -GRID, z, 0);
  put("Sofa03_Stone", bx - 60, 0, z, 0);
  put("Sofa01_Stone", bx - 60, GRID, z, 0);
  put("Sofa02_Stone", bx - 60, -GRID, z, 0);
  put("TableCircular01_Stone", bx + 120, 0, z, 0);
  put("Chair01_Stone", bx + 120, GRID, z, 0);
  put("Chair02_Stone", bx + 120, -GRID, z, 0);
  put("Piano01_Stone", bx, 2 * GRID, z, 0);
  put("Globe01_Stone", bx + 120, 2 * GRID, z, 0);
  put("Clock01_Stone", bx - 120, 2 * GRID, z, 0);
  put("Light_FirePlace01", bx - 150, -2 * GRID, z, 0);
  put("LargeLamp", bx, -2 * GRID, z, 0);
  put("Signboard", bx + 200, 0, z, 0);
  put("JetDragonStatue", bx, 3 * GRID, z, 0);
  put("IceHorseStatue", bx, -3 * GRID, z, 0);
}

// arena furniture: braziers, statues and floor lamps on the sand
{
  const z = lvl(0) + FLOOR_EPS;
  for (const [sx, sy] of [[1, 1], [-1, -1], [1, -1], [-1, 1]]) {
    put("OlympicCauldron", sx * 3 * GRID, sy * 3 * GRID, z, 0);
  }
  put("DisplayCharacter", 0, 3 * GRID, z, 180);
  put("DisplayCharacter", 0, -3 * GRID, z, 0);
  put("Headstone", 4 * GRID, GRID, z, 0);
  put("FurnitureStone01", 4 * GRID, -GRID, z, 0);
  for (const d of DIRS) {
    put("Light_FloorLamp01", d[0] * (3 * GRID) + d[1] * 150, d[1] * (3 * GRID) + d[0] * 150, z, 0);
    put("Light_FloorLamp02", d[0] * (3 * GRID) - d[1] * 150, d[1] * (3 * GRID) - d[0] * 150, z, 0);
  }
}

// tower decks: lounge on 6, library on 12, garden on 18, shrine on 24
{
  const deckKit: Record<number, string[]> = {
    6: ["Sofa01_Iron", "TableCircular01_Iron", "Stool01_Iron", "Television01_Iron", "ArcadeVideoGame", "MachineGame01_Iron", "Rug04_Stone", "LargeCeilingLamp"],
    12: ["TableSquare01_Iron", "Chair01_Iron", "Chair02_Iron", "Bonsai", "Byobu", "Andon", "Toro", "LargeCeilingLamp"],
    18: ["FurnitureTree02_Cherry", "FurnitureBush01_Flower", "Plant01_Plant", "Plant02_Plant", "Plant03_Plant", "Plant04_Plant", "Shishiodoshi", "LargeCeilingLamp"],
    24: ["BuildableGoddessStatue", "Altar", "Cauldron", "Light_CandleSticks_Top", "Zabuton", "Zaisu", "Irori", "LargeCeilingLamp"],
  };
  for (const dl of DECKS) {
    const kit = deckKit[dl];
    let n = 0;
    for (let i = -1; i <= 1; i++)
      for (let j = -1; j <= 1; j++) {
        if (i === 0 && j === 0) continue;
        put(kit[n++ % kit.length], i * GRID, j * GRID, lvl(dl) + FLOOR_EPS, (Math.atan2(-j, -i) * 180) / Math.PI);
      }
  }
}

// top observation deck: the crown. Decor rides the outer ring so the central
// 3x3 finial does not swallow it.
{
  const z = lvl(TOP) + FLOOR_EPS;
  ringTiles.forEach((c, i) => {
    const yw = (Math.atan2(-c[1], -c[0]) * 180) / Math.PI;
    if (i % 4 === 0) put("BuildableGoddessStatue", c[0] * GRID, c[1] * GRID, z, yw);
    else if (i % 4 === 1) put("LargeLamp", c[0] * GRID, c[1] * GRID, z, yw);
    else if (i % 4 === 2) put(BANNERS[i % BANNERS.length], c[0] * GRID, c[1] * GRID, z, yw + 180);
    else put(FLAGS[i % FLAGS.length], c[0] * GRID, c[1] * GRID, z, yw + 180);
  });
  put("WallSignboard", 0, 2 * GRID + GRID / 2 - 20, z + 100, -90);
}

// signboards over the four vomitoria arches
for (const d of DIRS) {
  put(
    "WallSignboard",
    d[0] * (8 * GRID + GRID / 2 - 20),
    d[1] * (8 * GRID + GRID / 2 - 20),
    lvl(0) + 200,
    facingYaw(d[0], d[1])
  );
}

// ================================================================= EMIT ====
const bp = loadBlueprint(readFileSync(SKELETON, "utf8"));
const objects = extractObjects(bp.raw);
const palbox = objects.find((o) => o.typeId === "PalBoxV2");
if (!palbox) throw new Error("skeleton has no PalBoxV2");
ORIGIN = { ...palbox.position };
// re-base every placement onto the palbox (they were accumulated with ORIGIN
// zeroed for the first pass, so add the origin in now)
for (const p of placed) {
  p.position = { x: p.position.x + ORIGIN.x, y: p.position.y + ORIGIN.y, z: p.position.z + ORIGIN.z };
}
const keptPalbox: PlacedObject = {
  ...palbox,
  position: { ...ORIGIN },
  rotation: { x: 0, y: 0, z: 0, w: 1 },
  origin: "original",
};

const { raw, notes } = reconcileExport(bp.raw, [keptPalbox, ...placed], DONORS);
(raw as any).base_camp_level = 23; // observed on the reference endgame camp

// ---- concrete-id de-collision --------------------------------------------
// 25 donor types carry a ConcreteModel whose RawData PST could not decode:
// an opaque `{values: {"~b": <base64>}}` blob. writeback.ts only remints
// concrete ids when the decoded `instance_id` field exists, so every clone of
// those types would ship the DONOR's concrete_model_instance_id — N copies,
// one id. PST's importer maps ids old->new through a dict keyed by the old id,
// so the copies would collapse onto a single mapping (the collision mode that
// gutted a base in docs/CALIBRATION.md).
//
// The blob's layout is not guessed: verified across 5 donors, bytes 0..15 are
// concrete_model_instance_id and bytes 16..31 are the model instance_id, each
// GUID stored as four little-endian uint32 groups. Both are rewritten here so
// the blob, the Model cross-ref and the works entry all agree.
const ZERO_GUID = "00000000-0000-0000-0000-000000000000";
function guidBytes(g: string): Buffer {
  const h = g.replace(/-/g, "");
  const b = Buffer.alloc(16);
  for (let i = 0; i < 4; i++) b.writeUInt32LE(parseInt(h.slice(i * 8, i * 8 + 8), 16) >>> 0, i * 4);
  return b;
}
{
  const worksByOwner = new Map<string, any[]>();
  for (const w of (raw as any).works) {
    const o = w?.RawData?.value?.owner_map_object_model_id;
    if (typeof o !== "string") continue;
    if (!worksByOwner.has(o)) worksByOwner.set(o, []);
    worksByOwner.get(o)!.push(w);
  }
  let fixed = 0;
  for (const mo of (raw as any).map_objects) {
    const rd = mo?.Model?.value?.RawData?.value;
    const crdv = mo?.ConcreteModel?.value?.RawData?.value;
    if (!rd || !crdv) continue;
    if (typeof crdv.instance_id === "string") continue; // decoded shape: writeback handled it
    const b64 = crdv?.values?.["~b"];
    if (typeof b64 !== "string") continue;
    if (typeof rd.concrete_model_instance_id !== "string" || rd.concrete_model_instance_id === ZERO_GUID)
      continue;
    const buf = Buffer.from(b64, "base64");
    if (buf.length < 32) continue;
    if (!buf.subarray(0, 16).equals(guidBytes(rd.concrete_model_instance_id))) {
      throw new Error(`concrete blob head != concrete_model_instance_id on ${mo.MapObjectId.value}`);
    }
    const oldC = rd.concrete_model_instance_id;
    const newC = mintGuid();
    guidBytes(newC).copy(buf, 0);
    guidBytes(rd.instance_id).copy(buf, 16);
    crdv.values["~b"] = buf.toString("base64");
    rd.concrete_model_instance_id = newC;
    for (const w of worksByOwner.get(rd.instance_id) ?? []) {
      if (w.RawData.value.owner_map_object_concrete_model_id === oldC)
        w.RawData.value.owner_map_object_concrete_model_id = newC;
    }
    fixed++;
  }
  console.log(`concrete-id de-collision: reminted ${fixed} opaque ConcreteModel blob(s)`);
}
const lint = validateLinkage(raw);

// report
const counts = new Map<string, number>();
for (const p of placed) counts.set(p.typeId, (counts.get(p.typeId) ?? 0) + 1);
const maxR = Math.max(
  ...placed.map((p) => Math.hypot(p.position.x - ORIGIN.x, p.position.y - ORIGIN.y))
);
const maxZ = Math.max(...placed.map((p) => p.position.z - ORIGIN.z));
console.log(`pieces: ${placed.length + 1} (incl. palbox), distinct types: ${counts.size}`);
console.log(`max radius: ${maxR.toFixed(0)} cm (area_range ${AREA_RANGE})`);
console.log(`height: ${(maxZ / 100).toFixed(1)} m / ${(maxZ / V).toFixed(1)} storeys`);
console.log("lint:", lint.length === 0 ? "clean" : lint.slice(0, 6));
for (const n of notes) console.log("note:", n);
writeFileSync(OUT, serializeBlueprint({ raw, warnings: [] }));
console.log("wrote", OUT);
