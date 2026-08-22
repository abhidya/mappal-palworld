// Shared "real game texture x per-instance tint" material path for every layer
// that draws an extracted GLB: build objects (GlbObject.tsx), Pals
// (PalLayer.tsx), player characters (PlayerLayer.tsx), terrain props
// (TerrainLayer.tsx).
//
// WHY THIS IS SHARED, not inlined per layer: the extracted GLBs under
// public/meshes, public/pal_meshes and public/player_meshes now carry their own
// glTF materials with a real base-colour texture pulled out of the game pak
// (palxtex/Extract.cs). A layer that hardcodes `<meshStandardMaterial
// color="#cbd5e1">` throws that away and renders the mesh as a flat blob —
// which for Pals is fatal, because species identity IS the texture: shape alone
// barely separates 241 species, so flat-shaded Pals all look the same.
//
// The tint is deliberately NOT paint-specific. Several different features all
// want "the real texture, modulated by a per-object colour":
//   - player paint on build objects (Model.value.Paint)
//   - PlayerCharacterMakeData hair/brow/body/eye colours
//   - IsRarePal variants
// meshStandardMaterial multiplies `color` into `map`, so passing a tint keeps
// the texture detail and shifts the hue. Pass WHITE (the default) to render a
// textured mesh at its true albedo.
import * as THREE from "three";

export const WHITE = new THREE.Color(0xffffff);

/**
 * One geometry per (mesh URL + whatever local transform the caller bakes in),
 * with UVs preserved and one geometry GROUP per source primitive so each
 * primitive keeps its own texture. Without this cache every one of the 517
 * glass pillars in a single base would build and hold its own copy of the same
 * vertex buffer.
 */
export type BuiltGlb = {
  geometry: THREE.BufferGeometry;
  /** Base-colour map per material slot; null where the mesh has no usable texture. */
  maps: (THREE.Texture | null)[];
};

const GEOM_CACHE = new Map<string, BuiltGlb | null>();

/**
 * Flatten a loaded GLB scene into one geometry in the caller's local space.
 *
 * @param cacheKey must vary with BOTH the mesh URL and `localMatrix` — two
 *   callers that bake different transforms into the same mesh must not share.
 * @param localMatrix applied to the flattened vertices, e.g. the UE->three axis
 *   swap composed with a blueprint component transform.
 */
export function buildGlb(
  scene: THREE.Object3D,
  cacheKey: string,
  localMatrix: THREE.Matrix4
): BuiltGlb | null {
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
    // A primitive with no UVs still has to contribute the right number of uv
    // entries, or the attribute desyncs from position.
    if (t && t.length >= vcount * 2) for (let i = 0; i < vcount * 2; i++) uvs.push(t[i]);
    else for (let i = 0; i < vcount * 2; i++) uvs.push(0);
    let slot = maps.indexOf(part.map);
    if (slot < 0) { maps.push(part.map); slot = maps.length - 1; }
    groups.push({ start, count: vcount, slot });
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.applyMatrix4(localMatrix);
  geometry.computeVertexNormals();
  for (const g of groups) geometry.addGroup(g.start, g.count, g.slot);

  const res: BuiltGlb = { geometry, maps };
  GEOM_CACHE.set(cacheKey, res);
  return res;
}

// Materials are shared for the same reason geometry is: a base can hold 3,600+
// objects and 900 Pals, and the overwhelming majority differ only by
// (texture, tint, opacity).
const MAT_CACHE = new Map<string, THREE.MeshStandardMaterial>();

export function getGlbMaterial(
  map: THREE.Texture | null,
  tint: string | THREE.Color,
  opacity = 1,
  transparent = false,
  /** Override the matte default. Only water passes this: the game's water
   *  materials ship an explicit Roughness scalar (0.03 for the ocean), and a
   *  mirror-smooth surface is most of what makes water read as water. */
  roughness = 1
): THREE.MeshStandardMaterial {
  const tintKey = typeof tint === "string" ? tint : tint.getHexString();
  const key = `${map ? map.uuid : "-"}|${tintKey}|${opacity}|${transparent}|${roughness}`;
  let m = MAT_CACHE.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({
      map: map ?? null,
      transparent,
      opacity,
      // The UE->three axis swap has determinant -1, so it mirrors and reverses
      // triangle winding. DoubleSide is cheaper than re-winding every index.
      side: THREE.DoubleSide,
      // Base-colour maps only — no metal/roughness maps are exported — so keep
      // the surface dielectric and matte rather than inventing a specular
      // response the game does not have. `roughness` is only ever moved off 1
      // by a caller that has the material's real Roughness scalar (water).
      metalness: 0,
      roughness,
    });
    m.color.set(tint as THREE.ColorRepresentation);
    MAT_CACHE.set(key, m);
  }
  return m;
}

/**
 * Materials for one built GLB. Decided PER SLOT, not per object: a mesh can
 * have some slots textured and some not (23 of 613 architecture slots and 76 of
 * 1,232 Pal slots resolve to no usable base-colour map). Tinting a map-less
 * slot white would render it blank, so it falls back to `flatColor` instead —
 * which is exactly the flat look those pieces had before textures existed.
 *
 * @param tint per-instance colour for TEXTURED slots (paint, rare-Pal variant,
 *   player appearance). Defaults to WHITE = show the real texture unmodified.
 * @param flatColor colour for slots with no texture.
 */
export function glbMaterials(
  built: BuiltGlb,
  tint: string | THREE.Color,
  flatColor: string | THREE.Color,
  opacity = 1,
  transparent = false,
  roughness = 1
): THREE.MeshStandardMaterial[] {
  return built.maps.map((map) =>
    getGlbMaterial(map, map ? tint : flatColor, opacity, transparent, roughness)
  );
}
