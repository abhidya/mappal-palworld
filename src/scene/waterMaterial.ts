// A DEPTH-AWARE water surface, reconstructed from MI_Pal_Water_Ver2's own
// cooked parameters.
//
// WHY THE OLD PATH RENDERED A SLAB. The ocean prop was drawn as a plain
// MeshStandardMaterial whose colour was `ScatteringCoefficientsColor` (0,1,0.6)
// at a CONSTANT opacity of 0.65. Two things are wrong with that, and the second
// is the one the eye actually complains about:
//
//   1. ScatteringCoefficientsColor is NOT a base colour. In UE's
//      MSM_SingleLayerWater it is a scattering COEFFICIENT — an attenuation per
//      unit distance travelled through the water volume, paired with
//      AbsorptionCoefficientsColor. Pasting it in as an albedo is a category
//      error, and because its green channel is pinned at 1.0 it produces a
//      fully-saturated teal.
//
//   2. A CONSTANT opacity has no depth term, so 40 cm of water over a sand bar
//      composites identically to 40 m of open ocean. Every depth cue is gone
//      and what is left is, correctly, read as a flat slab of paint. The
//      seabed was in fact showing through the whole time (the pale green/tan at
//      Glass Tower IS the submerged reef) — it just showed through by the same
//      35% everywhere, which reads as pattern printed ON the slab rather than
//      as something seen underwater.
//
// WHAT THIS DOES INSTEAD is UE's own composite, with UE's own numbers:
//
//     transmittance  T(d) = exp(-(sigmaA + sigmaS) * d)
//     result         = behind * T * ColorScaleBehindWater      (refracted seabed)
//                    + (sigmaS/sigmaE) * (1 - T) * lightEnergy (in-scattered)
//
// `d` is the real length of the water column along the view ray, taken from the
// depth buffer of a scene pass rendered WITHOUT the water (see WaterPass.tsx).
//
// The important consequence is that the coefficients are strongly per-channel:
// extinction is (1.0, 0.131, 0.104) per metre, so RED is gone within about a
// metre while blue-green survives tens of metres. That single fact is what
// turns a uniform teal sheet into a sea that is pale over the reef and deepens
// to blue offshore — and it is measured game data, not a painted gradient.
//
// PROVENANCE — every constant below is read verbatim off the cooked
// MaterialInstanceConstant (waterout/water_matparams.json, produced by
// palxwater --matparams against pakroot/Pal-Windows.pak with Mappings.usmap):
//   Pal/Content/Pal/Material/Water/MI_Pal_Water_Ver2.uasset
//     ScatteringCoefficients        0.00006     AbsorptionCoefficients   0.5
//     ScatteringCoefficientsColor   (0, 1, 0.6) AbsorptionCoefficientsColor
//                                               (0.02, 0.0025, 0.002)
//     ColorScaleBehindWater         0.35        Roughness                0.03
//     Specular                      0.04        Refraction               1.03
//     Wave1..4 tiling/speed/intensity + their normal maps (see WAVES)
//   parent M_Pal_Water_Ver2: BLEND_Masked, MSM_SingleLayerWater
import * as THREE from "three";

/** UE authors these per CENTIMETRE; the scene is metres (UNIT_SCALE = 0.01). */
const CM_PER_M = 100;

/** MI_Pal_Water_Ver2, verbatim. */
export const OCEAN_MATERIAL = {
  scatteringCoefficients: 0.00006,
  scatteringCoefficientsColor: [0, 1, 0.6] as const,
  absorptionCoefficients: 0.5,
  absorptionCoefficientsColor: [0.02, 0.0025, 0.002] as const,
  colorScaleBehindWater: 0.35,
  roughness: 0.03,
  specular: 0.04,
  refraction: 1.03,
};

/**
 * Extinction and single-scattering albedo, per METRE, from the material's own
 * scalar x colour pairs.
 *
 * sigmaS = ScatteringCoefficients * ScatteringCoefficientsColor
 * sigmaA = AbsorptionCoefficients * AbsorptionCoefficientsColor
 *
 * Worked out, per metre: sigmaE = (1.0, 0.131, 0.1036). Red therefore falls to
 * 37% after one metre and to essentially nothing after three, while blue is
 * still at 35% after ten metres — the ordinary physics of sea water, and here
 * it comes straight out of the shipped asset.
 */
export function oceanCoefficients() {
  const m = OCEAN_MATERIAL;
  const sigmaS = new THREE.Vector3(
    m.scatteringCoefficients * m.scatteringCoefficientsColor[0],
    m.scatteringCoefficients * m.scatteringCoefficientsColor[1],
    m.scatteringCoefficients * m.scatteringCoefficientsColor[2],
  ).multiplyScalar(CM_PER_M);
  const sigmaA = new THREE.Vector3(
    m.absorptionCoefficients * m.absorptionCoefficientsColor[0],
    m.absorptionCoefficients * m.absorptionCoefficientsColor[1],
    m.absorptionCoefficients * m.absorptionCoefficientsColor[2],
  ).multiplyScalar(CM_PER_M);
  const sigmaE = new THREE.Vector3().addVectors(sigmaS, sigmaA);
  // Single-scattering albedo sigmaS/sigmaE: the colour the volume scatters
  // back. Guard the divide — red's sigmaS is exactly 0.
  const albedo = new THREE.Vector3(
    sigmaE.x > 0 ? sigmaS.x / sigmaE.x : 0,
    sigmaE.y > 0 ? sigmaS.y / sigmaE.y : 0,
    sigmaE.z > 0 ? sigmaS.z / sigmaE.z : 0,
  );
  return { sigmaS, sigmaA, sigmaE, albedo };
}

/**
 * The four wave normal maps M_Pal_Water_Ver2 declares, with the instance's own
 * tiling / speed / intensity. These are the shipped BC5 tangent-space normal
 * maps, extracted from the pak by palxw --tex; nothing here is hand-authored.
 *
 * ONE THING IS A RENDER CHOICE, and it is called out rather than hidden: the
 * cooked instance gives the tiling NUMBERS but not the UV basis the material
 * graph feeds them (the graph itself is not readable from the cooked instance).
 * The surface is world-aligned here and the tiling is taken as repeats across
 * one ocean TILE — 540 m, which is the real S_WaterMesh tile pitch. That makes
 * the four layers 180 m / 10.8 m / 6.4 m / 2.7 m features, i.e. swell through
 * chop through ripple, and preserves the game's own RATIOS between the layers.
 */
export const WAVE_TILE_M = 540;

export const WAVES = [
  { tex: "T_Water_01_N", tiling: 85, speed: 0.01, intensity: 0.36, dir: [1, 0] },
  { tex: "T_Water_01_N", tiling: 200, speed: 0.005, intensity: 0.7, dir: [0, 1] },
  { tex: "T_Water_N_2", tiling: 50, speed: 0.02, intensity: 1.0, dir: [0.984808, -0.173648] },
  { tex: "T_Water_WaveIntense_N", tiling: 3, speed: 0.2, intensity: 0.5, dir: [0.7, 0.7] },
] as const;

export const WAVE_TEXTURE_URLS = Array.from(new Set(WAVES.map((w) => w.tex))).map(
  (n) => `/water_tex/${n}.png`,
);

const VERT = /* glsl */ `
varying vec3 vWorldPos;
varying vec3 vViewPos;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWorldPos = wp.xyz;
  vec4 mv = viewMatrix * wp;
  vViewPos = mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

const FRAG = /* glsl */ `
#include <packing>

uniform sampler2D tSceneColor;
uniform sampler2D tSceneDepth;
uniform vec2  uResolution;
uniform float uCameraNear;
uniform float uCameraFar;

uniform vec3  uSigmaE;       // extinction per metre, per channel
uniform vec3  uAlbedo;       // sigmaS / sigmaE
uniform float uColorScaleBehindWater;
uniform float uRefraction;
uniform float uSpecularF0;
uniform float uRoughness;

uniform vec3  uSunDir;       // world-space, normalised, toward the light
uniform vec3  uSunColor;     // colour * intensity
uniform vec3  uSkyColor;
uniform vec3  uAmbient;
uniform float uWaterLight;   // rig day/night scalar, 1.0 in full day

uniform sampler2D uWave0;
uniform sampler2D uWave1;
uniform sampler2D uWave2;
uniform vec4  uWaveTiling;    // per layer: repeats across one 540 m tile
uniform vec4  uWaveIntensity;
uniform float uTileMeters;
uniform float uTime;
uniform vec4  uWaveSpeed;
uniform vec2  uWaveDir0; uniform vec2 uWaveDir1; uniform vec2 uWaveDir2; uniform vec2 uWaveDir3;

varying vec3 vWorldPos;
varying vec3 vViewPos;

// Tangent-space normal from one shipped BC5 map. BC5 stores X and Y; Z is
// reconstructed, which is also what UE does with these assets.
vec3 sampleWaveNormal(sampler2D t, vec2 uv, float intensity) {
  vec3 n = texture2D(t, uv).xyz * 2.0 - 1.0;
  n.z = sqrt(max(1e-4, 1.0 - clamp(dot(n.xy, n.xy), 0.0, 1.0)));
  return vec3(n.xy * intensity, n.z);
}

void main() {
  vec2 screenUV = gl_FragCoord.xy / uResolution;

  // ---- surface normal: the four shipped wave layers, world-aligned --------
  vec2 base = vWorldPos.xz / uTileMeters;
  vec3 n0 = sampleWaveNormal(uWave0, base * uWaveTiling.x + uWaveDir0 * uTime * uWaveSpeed.x, uWaveIntensity.x);
  vec3 n1 = sampleWaveNormal(uWave0, base * uWaveTiling.y + uWaveDir1 * uTime * uWaveSpeed.y, uWaveIntensity.y);
  vec3 n2 = sampleWaveNormal(uWave1, base * uWaveTiling.z + uWaveDir2 * uTime * uWaveSpeed.z, uWaveIntensity.z);
  vec3 n3 = sampleWaveNormal(uWave2, base * uWaveTiling.w + uWaveDir3 * uTime * uWaveSpeed.w, uWaveIntensity.w);
  // Sum the tangent-space perturbations, keep +Y up (the surface is horizontal).
  vec2 slope = n0.xy + n1.xy + n2.xy + n3.xy;
  vec3 N = normalize(vec3(slope.x, 4.0, slope.y));

  vec3 V = normalize(cameraPosition - vWorldPos);

  // ---- how much water is between this surface and whatever is behind it ---
  // Refract the lookup slightly, by the material's own Refraction (1.03).
  vec2 refrOffset = N.xz * (uRefraction - 1.0) * 0.6;
  vec2 refrUV = clamp(screenUV + refrOffset, vec2(0.001), vec2(0.999));

  float sceneDepthRaw = texture2D(tSceneDepth, refrUV).x;
  float sceneViewZ = perspectiveDepthToViewZ(sceneDepthRaw, uCameraNear, uCameraFar);
  float waterViewZ = vViewPos.z;
  // Both are negative and the scene behind is farther, so this is >= 0. Convert
  // the view-Z difference into a distance along the actual view ray.
  float rayStretch = length(vViewPos) / max(1e-4, abs(vViewPos.z));
  float depthM = max(0.0, (waterViewZ - sceneViewZ)) * rayStretch;

  // If the refracted sample landed on something IN FRONT of the water, it is
  // a foreground object bleeding in — fall back to the unrefracted sample.
  if (depthM <= 0.0) {
    refrUV = screenUV;
    sceneDepthRaw = texture2D(tSceneDepth, refrUV).x;
    sceneViewZ = perspectiveDepthToViewZ(sceneDepthRaw, uCameraNear, uCameraFar);
    depthM = max(0.0, (waterViewZ - sceneViewZ)) * rayStretch;
  }

  vec3 behind = texture2D(tSceneColor, refrUV).rgb;

  // ---- UE's single-layer-water composite ---------------------------------
  vec3 T = exp(-uSigmaE * depthM);
  vec3 refracted = behind * T * uColorScaleBehindWater;

  // In-scattered light. The volume term is lit by the rig's own light energy,
  // which is where the brightness of shallow tropical water comes from.
  vec3 lightEnergy = uSunColor * max(0.15, uSunDir.y) + uAmbient + uSkyColor;
  vec3 scattered = uAlbedo * (vec3(1.0) - T) * lightEnergy;

  vec3 body = (refracted + scattered) * uWaterLight;

  // ---- surface: fresnel sky reflection + sun glint ------------------------
  float cosTheta = clamp(dot(N, V), 0.0, 1.0);
  float F = uSpecularF0 + (1.0 - uSpecularF0) * pow(1.0 - cosTheta, 5.0);

  vec3 H = normalize(uSunDir + V);
  // Roughness 0.03 is a near-mirror; with the wave normals above this is what
  // becomes glitter rather than one dot.
  float a = max(1e-3, uRoughness * uRoughness);
  float spec = pow(max(0.0, dot(N, H)), 2.0 / (a * a) - 2.0);
  spec = min(spec, 12.0);

  vec3 color = mix(body, uSkyColor * uWaterLight, F)
             + uSunColor * spec * F * uWaterLight;

  gl_FragColor = vec4(color, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

export type WaterUniforms = {
  sunDir: THREE.Vector3;
  sunColor: THREE.Color;
  skyColor: THREE.Color;
  ambient: THREE.Color;
  waterLight: number;
};

/**
 * The ocean surface material. Rendered OPAQUE: it does its own compositing
 * against the pre-pass colour buffer, exactly as UE's single-layer water does,
 * so there is no alpha blend to get the sort order wrong and nothing it can
 * incorrectly occlude.
 */
export function createOceanMaterial(waveTextures: THREE.Texture[]): THREE.ShaderMaterial {
  const { sigmaE, albedo } = oceanCoefficients();
  for (const t of waveTextures) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = THREE.NoColorSpace; // normal maps are data, not colour
  }
  const byName = new Map<string, THREE.Texture>();
  Array.from(new Set(WAVES.map((w) => w.tex))).forEach((n, i) => byName.set(n, waveTextures[i]));

  return new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: false,
    depthWrite: true,
    depthTest: true,
    side: THREE.DoubleSide,
    uniforms: {
      tSceneColor: { value: null },
      tSceneDepth: { value: null },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uCameraNear: { value: 0.05 },
      uCameraFar: { value: 5000 },
      uSigmaE: { value: sigmaE },
      uAlbedo: { value: albedo },
      uColorScaleBehindWater: { value: OCEAN_MATERIAL.colorScaleBehindWater },
      uRefraction: { value: OCEAN_MATERIAL.refraction },
      uSpecularF0: { value: OCEAN_MATERIAL.specular },
      uRoughness: { value: OCEAN_MATERIAL.roughness },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uSunColor: { value: new THREE.Color(1, 1, 1) },
      uSkyColor: { value: new THREE.Color(0.2, 0.4, 0.6) },
      uAmbient: { value: new THREE.Color(0.3, 0.3, 0.3) },
      uWaterLight: { value: 1 },
      uWave0: { value: byName.get("T_Water_01_N") ?? null },
      uWave1: { value: byName.get("T_Water_N_2") ?? null },
      uWave2: { value: byName.get("T_Water_WaveIntense_N") ?? null },
      uWaveTiling: {
        value: new THREE.Vector4(WAVES[0].tiling, WAVES[1].tiling, WAVES[2].tiling, WAVES[3].tiling),
      },
      uWaveIntensity: {
        value: new THREE.Vector4(
          WAVES[0].intensity, WAVES[1].intensity, WAVES[2].intensity, WAVES[3].intensity),
      },
      uWaveSpeed: {
        value: new THREE.Vector4(WAVES[0].speed, WAVES[1].speed, WAVES[2].speed, WAVES[3].speed),
      },
      uWaveDir0: { value: new THREE.Vector2(WAVES[0].dir[0], WAVES[0].dir[1]) },
      uWaveDir1: { value: new THREE.Vector2(WAVES[1].dir[0], WAVES[1].dir[1]) },
      uWaveDir2: { value: new THREE.Vector2(WAVES[2].dir[0], WAVES[2].dir[1]) },
      uWaveDir3: { value: new THREE.Vector2(WAVES[3].dir[0], WAVES[3].dir[1]) },
      uTileMeters: { value: WAVE_TILE_M },
      uTime: { value: 0 },
    },
  });
}

