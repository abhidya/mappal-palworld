// Shared editor-model contract. UI and scene code depend on these types and on
// the store API in store.ts — nothing outside src/model reads the raw blob.

/** Unreal-space vector: centimetres, Z-up. Conversion to three.js space
 *  happens in src/scene, never here. */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** Quaternion as stored in the blueprint (x, y, z, w). */
export interface Quat {
  x: number;
  y: number;
  z: number;
  w: number;
}

/**
 * Player-applied paint colour, decoded from `Model.value.Paint` (docs/SCHEMA.md).
 *
 * The game stores an FLinearColor, so these components are LINEAR (working-space)
 * values in 0..1 — NOT sRGB. Anything handing them to three.js must therefore use
 * `Color.setRGB(r, g, b, THREE.LinearSRGBColorSpace)`, never `setStyle`/a hex
 * string (which would apply an sRGB->linear decode a second time).
 *
 * Only present when the blob's "painted" flag is 1: an object the player never
 * painted leaves this undefined and keeps its category/material colour.
 */
export interface PaintColor {
  r: number;
  g: number;
  b: number;
  a: number;
}

export type Category =
  | "structure"
  | "production"
  | "storage"
  | "decor"
  | "defense"
  | "world";

/**
 * Editable view over one map object (CLAUDE.md §4). Holds only the fields we
 * understand; everything else stays in the raw blob and is re-emitted verbatim
 * at export time by src/model/writeback.ts.
 */
export interface PlacedObject {
  /** Model.RawData.instance_id for originals; freshly minted GUID for duplicates. */
  id: string;
  /** MapObjectId.value, e.g. "Wooden_foundation". */
  typeId: string;
  position: Vec3;
  rotation: Quat;
  scale: Vec3;
  hpCurrent?: number;
  hpMax?: number;
  /**
   * Text the player wrote on a signboard in game (ConcreteModel.RawData
   * .signboard_text). Undefined for everything that is not a written-on sign.
   * Read-only, like paint: the raw blob stays the source of truth on export.
   */
  signText?: string;
  /**
   * Player paint, decoded from the object's Paint blob — undefined unless the
   * blob says this piece was actually painted. Read-only: the editor never
   * writes it back, the raw blob remains the source of truth at export time.
   */
  paint?: PaintColor;
  /**
   * originals came from the loaded file (id exists in raw); duplicates are
   * cloned at export time from their sourceId's raw entry with fresh GUIDs;
   * placed objects are cloned from the donor library (src/data/donors.json).
   */
  origin: "original" | "duplicate" | "placed";
  /** For duplicates: the original object's id to clone from. */
  sourceId?: string;
}

/** Derived per-object grid frame: objects sharing a yaw belong to one snap grid. */
export const GRID_PITCH = 400; // units (cm) between foundation centres — docs/CALIBRATION.md
export const VERTICAL_PITCH = 325; // units per wall/pillar segment
