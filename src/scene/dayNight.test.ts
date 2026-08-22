// The timelapse videos are the deliverable, so "you can always see the base"
// is a hard requirement on the day/night rig, not a matter of taste. These
// tests pin it: total scene exposure stays inside a narrow band all cycle, the
// key light never switches off, and the cycle is continuous (no cut at dawn or
// dusk). Tuning the look is fine; dropping the night floor is a regression.
import { describe, it, expect } from "vitest";
import { daylightState, EXPOSURE_MIN, EXPOSURE_MAX, WATER_NIGHT } from "./DayNightLights";

const HOURS = Array.from({ length: 24 * 12 }, (_, i) => i / 12); // every 5 in-game minutes

describe("day/night rig", () => {
  it("keeps total exposure inside the readable band at every hour", () => {
    for (const h of HOURS) {
      const s = daylightState(h);
      expect(s.total, `hour ${h}`).toBeGreaterThanOrEqual(EXPOSURE_MIN);
      expect(s.total, `hour ${h}`).toBeLessThanOrEqual(EXPOSURE_MAX);
    }
  });

  it("never lets the key light reach zero", () => {
    for (const h of HOURS) expect(daylightState(h).keyIntensity, `hour ${h}`).toBeGreaterThan(0.3);
  });

  it("keeps the ambient+hemisphere floor high enough to read unlit faces", () => {
    for (const h of HOURS) {
      const s = daylightState(h);
      expect(s.ambientIntensity + s.hemiIntensity, `hour ${h}`).toBeGreaterThan(0.75);
    }
  });

  // Water is the one surface exempted from the exposure policy above: it ships
  // no base-colour map and a colour channel already at 1.0, so a night held at
  // daytime irradiance saturated it and the sea read the same bright teal at
  // midnight as at noon. Pinning both ends matters — a daytime factor that
  // drifts off 1.0 would silently restage every daylight frame.
  it("darkens water at night and leaves full day untouched", () => {
    expect(daylightState(12).waterLight).toBe(1);
    expect(daylightState(2).waterLight).toBeCloseTo(WATER_NIGHT, 6);
    expect(WATER_NIGHT).toBeLessThan(1);
    expect(WATER_NIGHT).toBeGreaterThan(0);
    for (const h of HOURS) {
      const w = daylightState(h).waterLight;
      expect(w, `hour ${h}`).toBeGreaterThanOrEqual(WATER_NIGHT);
      expect(w, `hour ${h}`).toBeLessThanOrEqual(1);
    }
  });

  it("is continuous — no cut at dawn or dusk", () => {
    let prev = daylightState(0);
    for (const h of HOURS.slice(1)) {
      const s = daylightState(h);
      expect(Math.abs(s.total - prev.total), `hour ${h}`).toBeLessThan(0.05);
      expect(Math.abs(s.keyIntensity - prev.keyIntensity), `hour ${h}`).toBeLessThan(0.05);
      prev = s;
    }
  });

  it("still visibly moves through the day: night is cooler and the key light travels", () => {
    const noon = daylightState(12);
    const midnight = daylightState(2);
    expect(noon.dayness).toBeGreaterThan(0.99);
    expect(midnight.dayness).toBeLessThan(0.01);
    // night key is bluer than day key
    expect(midnight.keyColor.b - midnight.keyColor.r).toBeGreaterThan(0.1);
    expect(noon.keyColor.r - noon.keyColor.b).toBeGreaterThan(0.02);
    // the key light is on the other side of the base at dawn vs dusk
    expect(Math.sign(daylightState(6).keyDir[0])).not.toBe(Math.sign(daylightState(18).keyDir[0]));
    // and it never comes from below the horizon
    for (const h of HOURS) expect(daylightState(h).keyDir[1], `hour ${h}`).toBeGreaterThan(0);
  });
});
