// Codec for the opaque ConcreteModel RawData blob — "shape 2b" (docs/SCHEMA.md).
//
// PST failed to decode the ConcreteModel RawData of 25 of the 453 harvested
// donor types, so it survives as `{"values": {"~b": "<base64>"}}` with none of
// shape 1's id fields — while Model.RawData.concrete_model_instance_id is
// still a real, non-zero GUID. The ids are inside the blob: verified across
// all 25 affected donors, bytes 0..15 are concrete_model_instance_id and
// bytes 16..31 are the model instance_id, each GUID stored as four
// little-endian uint32 groups (the FGuid A/B/C/D layout).
//
// Every function here is pure — callers do the assignment — so this file never
// mutates blueprint data (that stays writeback.ts's job).

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Where PST parks bytes it could not decode. */
export const OPAQUE_BLOB_KEY = "~b";
/** Both ids live in the first 32 bytes; shorter blobs carry neither. */
const IDS_BYTES = 32;

/** The blob of a shape-2b ConcreteModel RawData, or null for any other shape. */
export function opaqueConcreteBlob(concreteRawData: any): string | null {
  if (typeof concreteRawData?.instance_id === "string") return null; // shape 1: decoded
  const b64 = concreteRawData?.values?.[OPAQUE_BLOB_KEY];
  return typeof b64 === "string" ? b64 : null;
}

/** The two ids a shape-2b blob carries, or null if it is too short to hold them. */
export function decodeConcreteBlobIds(
  b64: string
): { concreteId: string; modelId: string } | null {
  const bytes = base64ToBytes(b64);
  if (bytes.length < IDS_BYTES) return null;
  return {
    concreteId: guidFromBytes(bytes, 0),
    modelId: guidFromBytes(bytes, 16),
  };
}

/** The same blob with its two ids replaced; every other byte is preserved. */
export function withConcreteBlobIds(b64: string, concreteId: string, modelId: string): string {
  const bytes = base64ToBytes(b64);
  if (bytes.length < IDS_BYTES) {
    throw new Error(`concreteBlob: blob is ${bytes.length} bytes, need ${IDS_BYTES}`);
  }
  bytes.set(guidToBytes(concreteId), 0);
  bytes.set(guidToBytes(modelId), 16);
  return bytesToBase64(bytes);
}

function guidToBytes(guid: string): Uint8Array {
  const hex = guid.replace(/-/g, "");
  if (!/^[0-9a-fA-F]{32}$/.test(hex)) throw new Error(`concreteBlob: not a GUID: ${guid}`);
  const bytes = new Uint8Array(16);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < 4; i++) {
    view.setUint32(i * 4, parseInt(hex.slice(i * 8, i * 8 + 8), 16) >>> 0, true);
  }
  return bytes;
}

function guidFromBytes(bytes: Uint8Array, offset: number): string {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let hex = "";
  for (let i = 0; i < 4; i++) {
    hex += view.getUint32(offset + i * 4, true).toString(16).padStart(8, "0");
  }
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
