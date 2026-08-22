// ---------------------------------------------------------------------------
// Read-only decoder for map_objects[i].Model.value.Paint — the struct the game
// calls `PalMapObjectPaintSaveData`, which docs/SCHEMA.md previously carried as
// "opaque blob — UNKNOWN, preserve".
//
// This module only ever READS. Nothing here feeds writeback, and the blob stays
// in `_raw` untouched, so CLAUDE.md C5 (round-trip fidelity) is unaffected:
// decoding a field is not the same as owning it. If we ever want to *edit*
// paint, that is a separate decision with its own in-game verification.
//
// How the layout was derived (all counts reproducible from this repo's own
// fixtures plus one painted world — see paint.test.ts):
//
//   bytes  0-15  4x little-endian float32 — an Unreal FLinearColor
//   bytes 16-19  uint32 "has been painted" flag (0 = never painted, 1 = painted)
//   bytes 20-23  uint32, zero in all 3,530 non-empty blobs observed
//
// The evidence, by observed blob. Channels are written ch0..ch3 by byte offset
// rather than R,G,B,A on purpose — see the ordering caveat below.
//
//   count  ch0,ch1,ch2,ch3            flag  source
//    3363  1, 1, 1, 1                    0  repo fixtures + one exported base
//    1262  (zero-length blob)            -  repo fixtures + one exported base
//     151  0, 0, 0, 1                    1  one exported base
//      12  1, 1, 1, 1                    1  one exported base
//       4  0.2016, 0.2918, 1, 1          1  whole-world scan of a live save
//
// Three rows carry the argument:
//
//  - Row 4 vs row 1. A painted object and a never-painted object carry the SAME
//    four colour floats and differ only at byte 16 — which proves the flag is
//    an independent "painted" boolean rather than something derived from the
//    colour.
//  - Row 3. Black is ch0..ch2 = 0 with ch3 = 1, which strongly implies alpha is
//    LAST — a naive "all four are zero when black" reading would have missed
//    that. Strictly it shows only that the 4th float stays 1.0 while the first
//    three go to 0.0; calling it alpha additionally assumes a colour+alpha
//    layout and opaque paint. Both are very likely, neither is proven.
//  - Row 5. The only non-greyscale sample we have observed: four
//    Wooden_foundation tiles in a 2x2 cluster on one base, i.e. one deliberate
//    paint job. Its three colour channels are mutually distinct, which is what
//    makes it able to discriminate between channel orderings at all.
//    PROVENANCE: this sample was contributed from a whole-world scan of a live
//    save. The decode is verified here (the bytes are reproduced in
//    paint.test.ts); the extraction itself was not reproduced by this author.
//
// KNOWN LIMIT, stated plainly per CLAUDE.md §4: the byte LAYOUT above is
// established, but the SEMANTIC ORDER of the three colour channels is not.
// Greyscale samples are symmetric under any permutation of ch0..ch2, so rows
// 1-4 cannot speak to it. Row 5 breaks that symmetry — but it only tells us
// the channel values, not which colour the player actually picked in game.
// Read as canonical FLinearColor R,G,B,A it is a saturated BLUE; read reversed
// as B,G,R,A it is a saturated ORANGE. Both are consistent with the bytes.
//
// So the R-then-G-then-B naming below is inferred from the struct being a UE
// `FLinearColor` (canonically R,G,B,A float32 in memory) plus alpha-last being
// strongly implied. It is NOT proven. Resolving it takes exactly one
// observation: look at those four foundations in game and see what colour they
// are. Until then, do not build anything that would be silently wrong if ch0
// and ch2 turned out to be swapped.
// ---------------------------------------------------------------------------

/** A decoded `PalMapObjectPaintSaveData`. Linear (not sRGB) colour, 0..1. */
export interface PaintState {
  /** Colour components in FLinearColor order — see the ordering caveat above. */
  r: number;
  g: number;
  b: number;
  /** Alpha (assumed — see the layout caveat). 1.0 in every observed blob. */
  a: number;
  /**
   * The game's own "this object has been painted" flag (byte 16), NOT a
   * colour-derived guess. False means the object is showing its stock
   * material, whatever the colour floats happen to say.
   */
  painted: boolean;
}

/** Byte length of a populated Paint blob. Anything else is refused, not guessed. */
const PAINT_BLOB_BYTES = 24;

/**
 * PST writes byte blobs in two different shapes and both occur in the wild:
 * a `{"~b": "<base64>"}` tag (all of fixtures/*.json) or a plain array of byte
 * ints (an export we checked carried zero `~b` tags anywhere in the file).
 * PST's `json_tools.CustomEncoder` only applies the `~b` tag to Python
 * `bytes`/`bytearray`, so whether a given field arrives tagged depends on the
 * internal type its parser produced — i.e. it can vary by PST version. Readers
 * must accept both; docs/SCHEMA.md now says so.
 */
function toBytes(values: unknown): Uint8Array | null {
  if (Array.isArray(values)) {
    const out = new Uint8Array(values.length);
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (typeof v !== "number" || !Number.isInteger(v) || v < 0 || v > 255) return null;
      out[i] = v;
    }
    return out;
  }
  if (values && typeof values === "object" && "~b" in values) {
    const b64 = (values as { "~b": unknown })["~b"];
    if (typeof b64 !== "string") return null;
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  return null;
}

/** Structural view of just the path we read. Everything else stays untyped. */
interface RawPaintCarrier {
  Model?: {
    value?: {
      Paint?: { value?: { RawData?: { value?: { values?: unknown } } } };
    };
  };
}

/**
 * Decode one raw `map_objects[i]` entry's paint.
 *
 * Returns `null` — meaning "this object has no paint record", which is a
 * normal, common state — when the Paint struct is absent or carries a
 * zero-length blob. 1,262 of the objects we surveyed are zero-length,
 * including 1,024 across this repo's own fixtures, so an empty blob is
 * emphatically not corruption.
 *
 * Throws only on a blob that is present, non-empty, and NOT 24 bytes: that is
 * schema drift, and per CLAUDE.md §4 we fail loudly rather than guess at a
 * layout we have not seen.
 */
export function decodePaint(mapObject: unknown): PaintState | null {
  const values = (mapObject as RawPaintCarrier)?.Model?.value?.Paint?.value?.RawData?.value
    ?.values;
  if (values === undefined) return null;

  const bytes = toBytes(values);
  if (bytes === null) return null;
  if (bytes.length === 0) return null;

  if (bytes.length !== PAINT_BLOB_BYTES) {
    throw new Error(
      `decodePaint: Paint blob is ${bytes.length} bytes, expected ${PAINT_BLOB_BYTES} ` +
        `(PalMapObjectPaintSaveData, see docs/SCHEMA.md). Refusing to guess a layout.`
    );
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return {
    r: view.getFloat32(0, true),
    g: view.getFloat32(4, true),
    b: view.getFloat32(8, true),
    a: view.getFloat32(12, true),
    painted: view.getUint32(16, true) !== 0,
  };
}
