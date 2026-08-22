// Real extracted Palworld StaticMesh rendering (opt-in per type).
//
// Geometry comes from the game's own SM_* assets, exported to GLB with
// vertices left in RAW UNREAL CENTIMETRES (no axis swap, no scale) — see
// scripts that produced public/meshes/. MapPal's world is metres, Y-up, with
// three.(x,y,z) = ue.(x,z,y) * UNIT_SCALE (coords.ts), and the object's
// position/quaternion are ALREADY converted by the caller. So all that is
// left here is the mesh's own local-space conversion: scale by UNIT_SCALE
// and swap local Y/Z. That swap has determinant -1 (it mirrors), which
// reverses triangle winding — hence DoubleSide below rather than fighting it.
import { useMemo } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import { UNIT_SCALE } from "./coords";
import meshXform from "../data/meshXform.json";
import { paintToColor } from "./objectTypes";
import type { PlacedObject } from "../model/types";

const S = UNIT_SCALE;
const UE_TO_THREE = new THREE.Matrix4().set(
  S, 0, 0, 0,
  0, 0, S, 0,
  0, S, 0, 0,
  0, 0, 0, 1
);

// --- Blueprint component-relative transform ---------------------------------
// A save file stores the transform of the ACTOR (BP_BuildObject_*), not of the
// mesh inside it. Inside the blueprint, the StaticMeshComponent that actually
// draws the piece carries its own RelativeLocation/Rotation/Scale3D, and for a
// lot of types that is NOT identity — the artists rotated the component so one
// shared placement rule could serve meshes authored on different axes.
//
// Extracted straight from the game's own blueprints with CUE4Parse (see
// palxtex/Bp.cs -> mesh_xform.json): 277 of 432 registry types have a
// non-identity component transform, covering 2,585 of the 6,997 placed objects
// in build_index.json. Dropping it is what made fences look wrong.
//
// Concretely, and this is the whole bug: placement puts UE-local +X along the
// foundation-edge NORMAL for every edge-snapped piece (verified numerically in
// coords.ts, and re-confirmed here — |localX . normal| = 1.000 over 33 walls
// and 0.997 over 4 edge-adjacent fences in base 16fca097). SM_Wall_Wood is
// authored to match, bbox [29, 401, 333] cm: local X really is its 29 cm
// thickness. SM_Fence_Wood is authored the other way round, bbox
// [400, 23, 109] cm — its long axis is local X. BP_BuildObject_Wood_Fence
// reconciles the two with RelativeRotation yaw -90 deg on the mesh component,
// which swings the fence's length onto local Y where the placement rule wants
// it. Ignore that yaw and every fence renders 90 deg out, jutting across the
// edge instead of running along it. Roofs are hit the same way (Glass_roof and
// Wooden_roof both carry yaw +90; their footprint is square so the error shows
// up as the slope facing the wrong way rather than as a wrong outline).
//
// The component transform lives in UNREAL space, so it has to be applied to
// the raw UE-centimetre vertices BEFORE the UE->three axis swap, never after.
type Xform = { rot: number[]; loc: number[]; scale: number[] };
const XFORMS = meshXform as Record<string, Xform>;

/**
 * UE FRotator (degrees, Pitch/Yaw/Roll) -> quaternion, using Unreal's own
 * FRotator::Quaternion() sign convention. The result is applied to vertices
 * that are still in UE space, where — exactly as coords.ts established for the
 * save's placement quaternion — the plain Hamilton rotate-vector formula is
 * the right one. Sanity check: yaw +90 gives (0,0,sin45,cos45), which takes
 * UE-local +X to +Y.
 */
function ueRotatorToQuat(pitch: number, yaw: number, roll: number): THREE.Quaternion {
  const h = Math.PI / 360; // deg -> rad, halved
  const sp = Math.sin(pitch * h), cp = Math.cos(pitch * h);
  const sy = Math.sin(yaw * h), cy = Math.cos(yaw * h);
  const sr = Math.sin(roll * h), cr = Math.cos(roll * h);
  return new THREE.Quaternion(
    cr * sp * sy - sr * cp * cy,
    -cr * sp * cy - sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
    cr * cp * cy + sr * sp * sy
  );
}

/** UE_TO_THREE composed with this type's UE-space component transform. */
function geometryMatrix(typeId: string): THREE.Matrix4 {
  const x = XFORMS[typeId];
  if (!x) return UE_TO_THREE;
  const rel = new THREE.Matrix4().compose(
    new THREE.Vector3(x.loc[0], x.loc[1], x.loc[2]),
    ueRotatorToQuat(x.rot[0], x.rot[1], x.rot[2]),
    new THREE.Vector3(x.scale[0], x.scale[1], x.scale[2])
  );
  return new THREE.Matrix4().multiplyMatrices(UE_TO_THREE, rel);
}

// One baked geometry per (mesh URL, component transform). Without this every
// one of the 517 glass pillars in a base builds and keeps its own copy of the
// same vertex buffer; the timelapse renders thousands of objects per frame.
type Built = { geometry: THREE.BufferGeometry; maps: (THREE.Texture | null)[] };
const GEOM_CACHE = new Map<string, Built | null>();

const WHITE = new THREE.Color(0xffffff);

// Materials are shared too, for the same reason: a base can hold 3,600+
// objects and the overwhelming majority differ only by (texture, tint,
// opacity). Keyed on exactly those, so a painted piece still gets its own.
const MAT_CACHE = new Map<string, THREE.MeshStandardMaterial>();

function getMaterial(
  map: THREE.Texture | null,
  tint: string | THREE.Color,
  opacity: number,
  transparent: boolean
): THREE.MeshStandardMaterial {
  const tintKey = typeof tint === "string" ? tint : tint.getHexString();
  const key = `${map ? map.uuid : "-"}|${tintKey}|${opacity}|${transparent}`;
  let m = MAT_CACHE.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({
      map: map ?? null,
      transparent,
      opacity,
      side: THREE.DoubleSide,
      // The extracted base-colour maps are albedo only — no metal/roughness
      // maps are exported — so keep the surface fully dielectric and matte
      // rather than inventing a specular response the game does not have.
      metalness: 0,
      roughness: 1,
    });
    m.color.set(tint as THREE.ColorRepresentation);
    MAT_CACHE.set(key, m);
  }
  return m;
}

export function GlbObject({
  url, position, quaternion, color, opacity, transparent, object,
}: {
  url: string;
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  /**
   * Base colour for the material. A CSS/hex string for the type's normal
   * category/material colour, or a THREE.Color when the piece carries player
   * paint (already converted out of the save's linear FLinearColor space by
   * objectTypes.ts's paintToColor — do NOT re-encode it as a hex string here,
   * that would push it back through three's sRGB decode a second time).
   * meshStandardMaterial multiplies `color` into `map`, so once a texture is
   * present the paint modulates it rather than replacing it.
   */
  color: string | THREE.Color;
  opacity: number;
  transparent: boolean;
  object: PlacedObject;
}) {
  const { scene } = useGLTF(url);
  // Merge every primitive in the GLB into one geometry in three-space local
  // coords, keeping UVs and one geometry GROUP per source primitive so each
  // one can keep its own base-colour texture.
  const cacheKey = `${url}|${object.typeId}`;
  const built = useMemo(() => {
    const hit = GEOM_CACHE.get(cacheKey);
    if (hit !== undefined) return hit;

    const parts: { geom: THREE.BufferGeometry; map: THREE.Texture | null }[] = [];
    scene.traverse((n) => {
      const m = n as THREE.Mesh;
      if (!m.isMesh || !m.geometry) return;
      const g = m.geometry.clone();
      g.applyMatrix4(m.matrixWorld);
      const src = (Array.isArray(m.material) ? m.material[0] : m.material) as
        | THREE.MeshStandardMaterial
        | undefined;
      parts.push({ geom: g, map: src?.map ?? null });
    });
    if (!parts.length) {
      GEOM_CACHE.set(cacheKey, null);
      return null;
    }

    const positions: number[] = [];
    const uvs: number[] = [];
    const maps: (THREE.Texture | null)[] = [];
    const groups: { start: number; count: number; slot: number }[] = [];
    for (const part of parts) {
      const g = part.geom.index ? part.geom.toNonIndexed() : part.geom;
      const p = g.attributes.position.array as ArrayLike<number>;
      const t = g.attributes.uv?.array as ArrayLike<number> | undefined;
      const start = positions.length / 3;
      for (let i = 0; i < p.length; i++) positions.push(p[i]);
      const vcount = p.length / 3;
      // A primitive with no UVs still has to contribute the right number of
      // uv entries or the attribute would desync from position.
      if (t && t.length >= vcount * 2) for (let i = 0; i < vcount * 2; i++) uvs.push(t[i]);
      else for (let i = 0; i < vcount * 2; i++) uvs.push(0);
      // One material slot per distinct texture — the untextured case collapses
      // to a single shared slot rather than one per primitive.
      let slot = maps.indexOf(part.map);
      if (slot < 0) { maps.push(part.map); slot = maps.length - 1; }
      groups.push({ start, count: vcount, slot });
    }

    const out = new THREE.BufferGeometry();
    out.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    out.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    // UE-space component transform first, then the UE->three axis swap — both
    // folded into one matrix by geometryMatrix().
    out.applyMatrix4(geometryMatrix(object.typeId));
    out.computeVertexNormals();
    for (const g of groups) out.addGroup(g.start, g.count, g.slot);

    const res = { geometry: out, maps };
    GEOM_CACHE.set(cacheKey, res);
    return res;
  }, [scene, cacheKey, object.typeId]);

  // Per-instance tint. A textured piece must render at its true albedo, so an
  // UNPAINTED one tints white (meshStandardMaterial multiplies color into map,
  // so anything else would stain the real texture with the category colour).
  // A painted piece tints with its actual paint, which is the whole point of
  // the paint feature — texture detail survives, the hue changes. Untextured
  // pieces keep the flat category/material colour they have always had.
  //
  // This same "base texture x per-instance tint" shape is what Pal species
  // textures, rare-Pal variants and player appearance colours need, so it is
  // deliberately not paint-specific.
  // Decided PER SLOT, not per object: a mesh can have some slots textured and
  // some not (23 of 613 architecture slots and 76 of 1,232 Pal slots resolve to
  // no usable base-colour map). Tinting a map-less slot white would render it
  // blank; it keeps the flat colour it had before instead.
  const paintTint = object.paint ? paintToColor(object.paint) : null;
  const materials = useMemo(() => {
    if (!built) return null;
    return built.maps.map((map) =>
      getMaterial(map, map ? (paintTint ?? WHITE) : color, opacity, transparent)
    );
  }, [built, paintTint, color, opacity, transparent]);

  if (!built || !materials) return null;
  return (
    <mesh
      position={position}
      quaternion={quaternion}
      geometry={built.geometry}
      material={materials.length === 1 ? materials[0] : materials}
      userData={{ isPlacedObject: true, placedObject: object }}
    />
  );
}
