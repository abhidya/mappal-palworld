// Day/night rig for the timelapse. Rendered ONLY when daylightStore.hour is
// non-null (see Scene.tsx); the editor's normal static ambient+directional pair
// is untouched otherwise, and unmounting this restores it exactly.
//
// TIME BASE (all real, none synthesised)
// --------------------------------------
// `hour` is the world's own clock: worldSaveData.GameTimeSaveData
// .GameDateTimeTicks, which is a .NET-style 100 ns tick count, so
//     864_000_000_000 ticks = one in-game day
//     hour = (ticks % 864e9) / 864e9 * 24
// Measured across 606 snapshots of this world, that clock advances 45.000
// in-game seconds per real second (p25..p75 = 44.995..45.003), i.e. one
// in-game day per 32 real minutes.
//
// DAWN/DUSK ANCHOR: one snapshot pair caught a bed-sleep — the clock jumped
// 18:18 -> 05:37 in 218 real seconds. Palworld only lets you sleep after dark
// and wakes you in the morning, so 18:18 is already dusk and 05:37 is already
// day. SUNRISE/SUNSET below bracket that observation.
//
// EXPOSURE POLICY (hard requirement, not a preference)
// ----------------------------------------------------
// The timelapse IS the deliverable, so a viewer must be able to read the base
// and see a piece appear in EVERY frame. Night is therefore a COLOUR shift,
// not an exposure drop: as the sun's directional contribution falls, the
// ambient and hemisphere terms rise to compensate, and the total light the
// scene receives stays within a narrow band all cycle (see EXPOSURE_* below,
// and daylightState()'s `total` field which the harness asserts on).
// Everything varies continuously through a smoothstep twilight — there is no
// instant at which the key light snaps off.
//
// No shadow maps: at these scene extents they cost more than they add, and
// hard shadows would eat exactly the night legibility this rig is protecting.
import { useMemo } from "react";
import * as THREE from "three";

const SUNRISE = 5;
const SUNSET = 19;

/** Total light the scene receives must stay inside this band, all cycle. */
export const EXPOSURE_MIN = 1.55;
export const EXPOSURE_MAX = 2.35;

function mix(a: THREE.ColorRepresentation, b: THREE.ColorRepresentation, t: number): THREE.Color {
  return new THREE.Color(a).lerp(new THREE.Color(b), THREE.MathUtils.clamp(t, 0, 1));
}
const lerp = THREE.MathUtils.lerp;
function smoothstep(a: number, b: number, x: number) {
  const t = THREE.MathUtils.clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
}

export interface DayNightState {
  /** Continuous solar elevation, -1 (deep night) .. +1 (solar noon). */
  elevation: number;
  /** 0 = full night, 1 = full day, smoothly blended through twilight. */
  dayness: number;
  keyDir: [number, number, number];
  fillDir: [number, number, number];
  keyColor: THREE.Color;
  keyIntensity: number;
  fillColor: THREE.Color;
  fillIntensity: number;
  ambientColor: THREE.Color;
  ambientIntensity: number;
  hemiSky: THREE.Color;
  hemiGround: THREE.Color;
  hemiIntensity: number;
  skyColor: THREE.Color;
  /** Sum of all light intensities — the exposure the band above constrains. */
  total: number;
}

export function daylightState(hour: number): DayNightState {
  const h = ((hour % 24) + 24) % 24;
  // Continuous elevation: positive between SUNRISE and SUNSET, negative
  // through the night, deepest around 02:00. One smooth curve, so nothing in
  // the rig has to branch on "is it day".
  const phase = (h - SUNRISE) / (SUNSET - SUNRISE);
  const elevation = Math.sin(Math.PI * phase);
  // Twilight blend. Wide enough that dusk and dawn are visible transitions
  // rather than a cut, which is what sells "time is passing".
  const dayness = smoothstep(-0.18, 0.18, elevation);

  // Key light travels a half-turn across the sky per day; the moon rides the
  // opposite arc. Never below the horizon — a key light coming from underneath
  // lights the wrong faces and reads as a bug.
  const az = Math.PI * phase + Math.PI * 0.15;
  const R = 40;
  const height = Math.max(0.22, Math.abs(elevation)) * R * 0.9;
  const keyDir: [number, number, number] = [Math.cos(az) * R, height, Math.sin(az) * R];
  const fillDir: [number, number, number] = [-keyDir[0], height * 0.75, -keyDir[2]];

  // Key: warm low sun -> neutral noon -> pale blue moon. The moon's own
  // contribution is deliberately substantial, not a token rim.
  const sunColor = mix("#ff9a52", "#fff4e2", Math.min(1, Math.max(0, elevation) * 1.8));
  const moonColor = new THREE.Color("#c2d6ff");
  const keyColor = mix(moonColor, sunColor, dayness);
  const sunI = 0.46 + 0.80 * Math.max(0, elevation);
  const moonI = 0.46 + 0.16 * Math.max(0, -elevation);
  const keyIntensity = lerp(moonI, sunI, dayness);

  // Fill from the opposite side: keeps the shaded face of every piece off
  // black. Stronger at night, because at night it is doing more of the work.
  const fillColor = mix("#7e9ed8", "#bcd4ff", dayness);
  const fillIntensity = lerp(0.30, 0.18, dayness);

  // Ambient + hemisphere are the compensating terms. They rise as the sun
  // falls, which is what holds total exposure inside the band.
  const ambientIntensity = lerp(0.62, 0.46, dayness);
  const ambientColor = mix("#a9bde0", mix("#ffd9b0", "#ffffff", Math.min(1, Math.max(0, elevation) * 1.5)), dayness);
  const hemiIntensity = lerp(0.60, 0.36, dayness);
  const hemiSky = mix("#8aa6d8", "#cfe3ff", dayness);
  const hemiGround = mix("#3f4a60", "#6b5f4e", dayness);

  // Sky is where the time of day is allowed to read strongly, because the
  // background carries no geometry a viewer needs to read.
  const daySky = mix("#432c34", "#1f3f63", Math.min(1, Math.max(0, elevation) * 1.4));
  const nightSky = mix("#101a2e", "#0a1120", Math.max(0, -elevation));
  const skyColor = mix(nightSky, daySky, dayness);

  const total = keyIntensity + fillIntensity + ambientIntensity + hemiIntensity;
  return { elevation, dayness, keyDir, fillDir, keyColor, keyIntensity,
           fillColor, fillIntensity, ambientColor, ambientIntensity,
           hemiSky, hemiGround, hemiIntensity, skyColor, total };
}

export function DayNightLights({ hour }: { hour: number }) {
  const s = useMemo(() => daylightState(hour), [hour]);
  return (
    <>
      {/* Sky tint only exists while this rig is mounted; R3F's attach restores
          the editor's transparent canvas on unmount. */}
      <color attach="background" args={[s.skyColor.r, s.skyColor.g, s.skyColor.b]} />
      <ambientLight intensity={s.ambientIntensity} color={s.ambientColor} />
      {/* Sky/ground wrap — this is what keeps a roof's UNDERSIDE and the
          pilings under a glass foundation readable. Flat ambient alone left
          overhangs unreadable at night. */}
      <hemisphereLight args={[s.hemiSky, s.hemiGround, s.hemiIntensity]} />
      <directionalLight position={s.keyDir} intensity={s.keyIntensity} color={s.keyColor} />
      <directionalLight position={s.fillDir} intensity={s.fillIntensity} color={s.fillColor} />
    </>
  );
}
