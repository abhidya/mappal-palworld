// Tests for src/parse/paint.ts — the decode of `PalMapObjectPaintSaveData`,
// which docs/SCHEMA.md used to carry as an opaque UNKNOWN.
//
// Two layers, deliberately:
//
//  1. Synthetic blobs pin the byte layout itself. Every literal below is a real
//     blob reproduced byte-for-byte, including the case that carries the whole
//     argument (same colour, different flag) and the single non-greyscale
//     sample that speaks to channel ordering.
//  2. A sweep over every committed fixture pins the claim SCHEMA.md now makes
//     about real files. If a future PST version changes the blob, this fails
//     loudly instead of letting the documentation quietly rot.
//
// The fixtures are all unpainted (nobody painted the calibration bases), so
// layer 2 can only confirm the default/empty rows of the table in paint.ts.
// The painted rows come from worlds that aren't ours to commit — the greyscale
// ones from an exported base, the chromatic one contributed from a whole-world
// scan of a live save (decode verified here, extraction not reproduced by this
// author). Layer 1 keeps all of them regression-tested regardless.

import { describe, test, expect } from "vitest";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { decodePaint } from "./paint";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixturesDir = path.resolve(here, "../../fixtures");

/** Wrap a byte array in the nesting decodePaint expects, as an int array. */
function asIntArray(bytes: number[]): unknown {
  return { Model: { value: { Paint: { value: { RawData: { value: { values: bytes } } } } } } };
}

/** Same, but with PST's `{"~b": base64}` byte tag. */
function asByteTag(bytes: number[]): unknown {
  const b64 = Buffer.from(bytes).toString("base64");
  return {
    Model: { value: { Paint: { value: { RawData: { value: { values: { "~b": b64 } } } } } } },
  };
}

// Real blobs, byte-for-byte, as observed. Named for what the game shows.
const UNPAINTED_DEFAULT = [
  0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 0, 0, 0, 0, 0, 0, 0, 0,
]; // rgba 1,1,1,1  flag 0
const PAINTED_BLACK = [
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x80, 0x3f, 1, 0, 0, 0, 0, 0, 0, 0,
]; // rgba 0,0,0,1  flag 1
const PAINTED_WHITE = [
  0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 1, 0, 0, 0, 0, 0, 0, 0,
]; // rgba 1,1,1,1  flag 1

// The only non-greyscale blob we have observed: four Wooden_foundation tiles in
// a 2x2 cluster (one deliberate paint job), from a whole-world scan of a live
// save — a contributed sample, decode verified here.
// Deliberately NOT named for a colour — see the ordering test below.
const PAINTED_CHROMATIC = [
  0xc3, 0x64, 0x4e, 0x3e, 0xf6, 0x62, 0x95, 0x3e, 0, 0, 0x80, 0x3f, 0, 0, 0x80, 0x3f, 1, 0, 0, 0, 0,
  0, 0, 0,
]; // ch0..ch3 = 0.2016, 0.2918, 1, 1  flag 1

describe("decodePaint byte layout", () => {
  test("decodes the unpainted default: white floats, painted flag clear", () => {
    expect(decodePaint(asIntArray(UNPAINTED_DEFAULT))).toEqual({
      r: 1,
      g: 1,
      b: 1,
      a: 1,
      painted: false,
    });
  });

  test("decodes painted black — the 4th float is the odd one out, not a fourth zero", () => {
    // This is what rules out "the blob is all zeros when black": the first
    // three floats are zero but the 4th is 1.0, which is what places alpha at
    // bytes 12-15 (strongly implied rather than proven — see paint.ts).
    expect(decodePaint(asIntArray(PAINTED_BLACK))).toEqual({
      r: 0,
      g: 0,
      b: 0,
      a: 1,
      painted: true,
    });
  });

  test("painted white and unpainted share a colour and differ only in the flag", () => {
    // The load-bearing case for reading byte 16 as an independent "has been
    // painted" boolean: identical colour floats, opposite flag.
    const unpainted = decodePaint(asIntArray(UNPAINTED_DEFAULT));
    const painted = decodePaint(asIntArray(PAINTED_WHITE));

    expect(painted).toEqual({ ...unpainted, painted: true });
    expect(unpainted!.painted).toBe(false);
    expect(painted!.painted).toBe(true);
  });

  test("pins the non-greyscale sample's layout without asserting a channel order", () => {
    // This sample is the only thing that can discriminate between channel
    // orderings, because its three colour channels are mutually distinct. But
    // the bytes alone do not say which colour a player picked: read as
    // FLinearColor R,G,B,A it is a saturated blue; read reversed as B,G,R,A it
    // is a saturated orange. Settling that needs one in-game observation, not
    // more parsing.
    //
    // So this test asserts what the bytes actually establish — the four floats
    // that are present, alpha's position, and the flag — and deliberately does
    // NOT assert which channel holds 0.2016. If the in-game check ever comes
    // back "orange", only the field NAMES in paint.ts change; the layout this
    // test pins, and this test, both stay correct.
    const p = decodePaint(asIntArray(PAINTED_CHROMATIC))!;

    const colourChannels = [p.r, p.g, p.b].map((v) => Number(v.toFixed(4))).sort((a, b) => a - b);
    expect(colourChannels).toEqual([0.2016, 0.2918, 1]);

    // The 4th float's role is settled well enough by the black sample to pin
    // by name here, unlike the three colour channels.
    expect(p.a).toBe(1);
    expect(p.painted).toBe(true);
  });

  test("reads PST's `~b` base64 byte tag and a plain int array identically", () => {
    // Both shapes occur in real exports — see the toBytes() comment in paint.ts.
    expect(decodePaint(asByteTag(PAINTED_BLACK))).toEqual(decodePaint(asIntArray(PAINTED_BLACK)));
  });

  test("treats an absent Paint struct and a zero-length blob as 'no paint record'", () => {
    expect(decodePaint({})).toBeNull();
    expect(decodePaint(asIntArray([]))).toBeNull();
  });

  test("refuses a blob of unexpected length rather than guessing (CLAUDE.md §4)", () => {
    expect(() => decodePaint(asIntArray([1, 2, 3]))).toThrow(/3 bytes, expected 24/);
  });
});

describe.skipIf(!existsSync(fixturesDir))("decodePaint against the committed fixtures", () => {
  const fixtures = existsSync(fixturesDir)
    ? readdirSync(fixturesDir).filter((f) => f.endsWith(".json"))
    : [];

  test("every Paint blob in every fixture decodes without throwing", () => {
    expect(fixtures.length).toBeGreaterThan(0);

    let decoded = 0;
    let empty = 0;
    for (const name of fixtures) {
      const parsed = JSON.parse(readFileSync(path.join(fixturesDir, name), "utf-8"));
      for (const obj of parsed.map_objects ?? []) {
        const paint = decodePaint(obj);
        if (paint === null) empty++;
        else decoded++;
      }
    }

    // Both states are well represented across the committed fixtures, so this
    // is a real exercise of both branches rather than a vacuous pass.
    expect(decoded).toBeGreaterThan(0);
    expect(empty).toBeGreaterThan(0);
  });

  test("every populated fixture blob is the unpainted default, as SCHEMA.md states", () => {
    // Nobody painted anything in the calibration/sampler bases. If this ever
    // fails, a fixture gained a painted object and SCHEMA.md's table (and the
    // note in paint.ts about greyscale-only samples) should be revisited —
    // a non-greyscale sample here would settle the channel-order caveat.
    for (const name of fixtures) {
      const parsed = JSON.parse(readFileSync(path.join(fixturesDir, name), "utf-8"));
      for (const obj of parsed.map_objects ?? []) {
        const paint = decodePaint(obj);
        if (paint === null) continue;
        expect(paint, name).toEqual({ r: 1, g: 1, b: 1, a: 1, painted: false });
      }
    }
  });
});
