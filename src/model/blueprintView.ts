// Read-only extraction of PlacedObject views from the raw blueprint blob.
// Every path accessed here was observed in fixtures/calibration_01.json and is
// documented in docs/SCHEMA.md. Anything missing fails loudly (CLAUDE.md §4) —
// we never guess a default for a field we expected to find.

import type { PaintColor, PlacedObject, Quat, Vec3 } from "./types";

// Minimal structural types for the paths we read. Everything else in these
// objects is deliberately untyped and untouched.
interface RawMapObject {
  MapObjectId?: { value?: unknown };
  Model?: {
    value?: {
      RawData?: { value?: RawModelData };
      Paint?: { value?: { RawData?: { value?: { values?: unknown } } } };
    };
  };
  // Per-type extras, dispatched on concrete_model_type. Signboards are the only
  // one we read: PalMapObjectSignboardModel carries the text the player typed
  // on the sign in game, as a plain FString the save tools parse natively.
  ConcreteModel?: {
    value?: {
      RawData?: { value?: { concrete_model_type?: unknown; signboard_text?: unknown } };
    };
  };
}
interface RawModelData {
  instance_id?: unknown;
  hp?: { current?: unknown; max?: unknown };
  initital_transform_cache?: {
    // sic — the game's own typo, see docs/SCHEMA.md
    rotation?: Partial<Quat>;
    translation?: Partial<Vec3>;
    scale3d?: Partial<Vec3>;
  };
}

function fail(index: number, what: string): never {
  throw new Error(
    `blueprintView: map_objects[${index}] is missing ${what} — schema drift vs docs/SCHEMA.md (calibrated 2026-07-16, PST v2.1.0). Refusing to guess.`
  );
}

function asVec3(v: Partial<Vec3> | undefined, index: number, what: string): Vec3 {
  if (
    !v ||
    typeof v.x !== "number" ||
    typeof v.y !== "number" ||
    typeof v.z !== "number"
  )
    fail(index, what);
  return { x: v.x, y: v.y, z: v.z };
}

function asQuat(q: Partial<Quat> | undefined, index: number, what: string): Quat {
  if (
    !q ||
    typeof q.x !== "number" ||
    typeof q.y !== "number" ||
    typeof q.z !== "number" ||
    typeof q.w !== "number"
  )
    fail(index, what);
  return { x: q.x, y: q.y, z: q.z, w: q.w };
}

export interface CampInfo {
  /** Camp anchor position (== palbox transform at load time). */
  position: Vec3;
  /** Build radius in Unreal units (fixture: 3500). Objects outside get warnings. */
  areaRange: number;
}

/** Camp anchor + radius, or null if the shape is unexpected (warn, don't guess). */
export function extractCampInfo(raw: unknown): CampInfo | null {
  const rd = (raw as any)?.base_camp?.value?.RawData?.value;
  const t = rd?.transform?.translation;
  const areaRange = rd?.area_range;
  if (
    typeof t?.x !== "number" ||
    typeof t?.y !== "number" ||
    typeof t?.z !== "number" ||
    typeof areaRange !== "number"
  ) {
    return null;
  }
  return { position: { x: t.x, y: t.y, z: t.z }, areaRange };
}

// --- Paint (Model.value.Paint) ---------------------------------------------
// docs/SCHEMA.md previously listed this as an opaque blob. It is a 24-byte
// PalMapObjectPaintSaveData RawData record. Layout verified by histogramming
// every map object in the four union blueprints under public/union plus a live
// single-base export (2026-08-21) — only four distinct blobs exist across the
// whole world, and they line up exactly with the paints applied in game:
//
//   bytes  0..15   4x little-endian float32 = FLinearColor R, G, B, A
//   bytes 16..19   uint32 "painted" flag — 0 = never painted, 1 = painted
//   bytes 20..23   zero in every observed record
//
// Pieces that predate the paint feature (or snapshots taken before the piece
// was first painted) carry a ZERO-LENGTH values array. That is normal, not
// schema drift, so an absent/short blob means "unpainted" and never fails.
const PAINT_BLOB_BYTES = 24;
const PAINTED_FLAG_OFFSET = 16;

/** Raw byte array for a Paint blob, or null when there is nothing stored. */
function paintBytes(values: unknown): Uint8Array | null {
  if (Array.isArray(values)) {
    return values.length === 0 ? null : Uint8Array.from(values as number[]);
  }
  // PST also emits ByteProperty arrays as {"~b": "<base64>"} — see
  // src/data/donors.json, which stores its map objects that way.
  const b64 = (values as { "~b"?: unknown } | null | undefined)?.["~b"];
  if (typeof b64 !== "string" || b64.length === 0) return null;
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * Decoded player paint for one raw map object, or undefined when the piece was
 * never painted. Read-only — the blob itself is still re-emitted verbatim by
 * writeback.ts, so this can never round-trip a colour back into the file.
 */
export function extractPaint(entry: unknown): PaintColor | undefined {
  const values = (entry as RawMapObject)?.Model?.value?.Paint?.value?.RawData?.value?.values;
  const bytes = paintBytes(values);
  if (!bytes || bytes.length < PAINT_BLOB_BYTES) return undefined;

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  // Flag first: an unpainted piece's RGBA is (1,1,1,1) filler, which would
  // otherwise repaint every default object bright white.
  if (view.getUint32(PAINTED_FLAG_OFFSET, true) !== 1) return undefined;

  return {
    r: view.getFloat32(0, true),
    g: view.getFloat32(4, true),
    b: view.getFloat32(8, true),
    a: view.getFloat32(12, true),
  };
}

/**
 * The text a player wrote on a signboard in game, or undefined for every other
 * object and for signs left blank.
 *
 * Lives at ConcreteModel.value.RawData.value.signboard_text, written whenever
 * concrete_model_type is PalMapObjectSignboardModel. Guarded on that type
 * rather than on the field alone, so an unrelated model that happens to grow a
 * same-named field can never be read as a sign.
 *
 * Blank is normal — a sign is placed before it is written on — so an empty
 * string returns undefined rather than rendering an empty label.
 */
export function extractSignText(entry: unknown): string | undefined {
  const rd = (entry as RawMapObject)?.ConcreteModel?.value?.RawData?.value;
  if (!rd || rd.concrete_model_type !== "PalMapObjectSignboardModel") return undefined;
  const text = rd.signboard_text;
  if (typeof text !== "string" || text.length === 0) return undefined;
  return text;
}

/** Returns raw.map_objects or throws loudly. */
export function getMapObjects(raw: unknown): unknown[] {
  const objs = (raw as { map_objects?: unknown })?.map_objects;
  if (!Array.isArray(objs)) {
    throw new Error("blueprintView: raw.map_objects is not an array");
  }
  return objs;
}

/** Extract editable views from every map object. Read-only: raw is not touched. */
export function extractObjects(raw: unknown): PlacedObject[] {
  return getMapObjects(raw).map((entry, i) => {
    const o = entry as RawMapObject;
    const typeId = o.MapObjectId?.value;
    if (typeof typeId !== "string") fail(i, "MapObjectId.value");

    const rd = o.Model?.value?.RawData?.value;
    if (!rd) fail(i, "Model.value.RawData.value");

    const id = rd.instance_id;
    if (typeof id !== "string") fail(i, "RawData.value.instance_id");

    const t = rd.initital_transform_cache;
    if (!t) fail(i, "initital_transform_cache");

    const hpCurrent = typeof rd.hp?.current === "number" ? rd.hp.current : undefined;
    const hpMax = typeof rd.hp?.max === "number" ? rd.hp.max : undefined;

    return {
      id,
      typeId,
      position: asVec3(t.translation, i, "translation"),
      rotation: asQuat(t.rotation, i, "rotation"),
      scale: asVec3(t.scale3d, i, "scale3d"),
      hpCurrent,
      hpMax,
      signText: extractSignText(entry),
      paint: extractPaint(entry),
      origin: "original" as const,
    };
  });
}
