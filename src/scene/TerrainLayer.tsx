// The base's real SURROUNDINGS: the cliffs, rocks and ruins the game itself
// places around it. Timelapse-only, same opt-in contract as PalLayer /
// PlayerLayer / DayNightLights — renders nothing unless terrainStore's `props`
// has been set by CameraDevHook's dev-only setTerrain().
//
// ALL OF THIS IS THE GAME'S OWN LEVEL DATA, not a generated landscape.
// Palworld ships PL_MainWorld5 as a cooked UE5 World Partition map: every
// streaming cell is its own package under _Generated_/ with its actors BAKED IN
// (there is no __ExternalActors__ directory in the pak), so each placed prop's
// authored RelativeLocation / RelativeRotation / RelativeScale3D is readable
// straight off the cooked StaticMeshComponent, and the mesh it points at is
// extracted from the same pak. build_terrain.py reads the cells covering a
// base's own coordinates and keeps the props within a stated radius of it.
//
// The cell grid is 25600 cm (cellX = floor(ue.x / 25600), cellY likewise). That
// is not a fitted guess: the cooked InstancedFoliageActor in each cell is
// literally named `InstancedFoliageActor_25600_<x>_<y>_-1`, and every placed
// prop's world coordinate falls inside the box that name implies.
//
// Rotation arrives as a quaternion already converted from the asset's FRotator
// by build_terrain.py, so it goes through coords.ts's numerically-verified
// ueQuatToThree() unchanged. Scale is the prop's own RelativeScale3D, mapped
// three.(x,y,z) = ue.(x,z,y) to match the geometry's own axis swap.
import { useMemo } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import { ueVecToThree, ueQuatToThree } from "./coords";
import { buildGlb, glbMaterials, WHITE } from "./glbMaterial";
import { UNIT_SCALE } from "./coords";
import { useTerrainStore, type TerrainProp } from "./terrainStore";

const S = UNIT_SCALE;
const UE_TO_THREE = new THREE.Matrix4().set(S, 0, 0, 0, 0, 0, S, 0, 0, S, 0, 0, 0, 0, 0, 1);

function Prop({ prop, centroidThree }: { prop: TerrainProp; centroidThree: THREE.Vector3 }) {
  const { scene } = useGLTF(prop.url);
  // Terrain props are plain StaticMeshComponents whose transform the cooked
  // cell already gives in world space, so the only local transform baked into
  // the vertices is the UE->three axis swap itself.
  const built = useMemo(() => buildGlb(scene, prop.url, UE_TO_THREE), [prop.url, scene]);
  // WATER: Palworld's water surfaces ship no base-colour map, so without the
  // material's own parameters they land on the flat rock-green fallback and
  // read as a green slab. build_terrain.py attaches the cooked
  // MaterialInstanceConstant's real values (see terrainStore.TerrainProp) and
  // they are used verbatim here. UE stores colour parameters as FLinearColor,
  // so they are fed in through setRGB(..., LinearSRGBColorSpace) rather than
  // being pasted in as if they were sRGB hex.
  const tint = useMemo(
    () => (prop.tint ? new THREE.Color().setRGB(...prop.tint, THREE.LinearSRGBColorSpace) : WHITE),
    [prop.tint],
  );
  const flat = useMemo(
    () =>
      prop.flat
        ? new THREE.Color().setRGB(...prop.flat, THREE.LinearSRGBColorSpace)
        : new THREE.Color("#6b7f63"),
    [prop.flat],
  );
  const materials = useMemo(
    () =>
      built
        ? glbMaterials(built, tint, flat, prop.opacity ?? 1, prop.transparent ?? false,
                       prop.rough ?? 1)
        : null,
    [built, tint, flat, prop.opacity, prop.transparent, prop.rough],
  );
  const position = useMemo(
    () => ueVecToThree({ x: prop.x, y: prop.y, z: prop.z }).sub(centroidThree),
    [prop.x, prop.y, prop.z, centroidThree],
  );
  const quaternion = useMemo(
    () => ueQuatToThree({ x: prop.qx, y: prop.qy, z: prop.qz, w: prop.qw }),
    [prop.qx, prop.qy, prop.qz, prop.qw],
  );
  if (!built || !materials) return null;
  return (
    <mesh
      position={position}
      quaternion={quaternion}
      scale={[prop.sx, prop.sz, prop.sy]}
      geometry={built.geometry}
      material={materials}
      receiveShadow
      // Translucent water (the waterfalls) draws after the opaque world, so it
      // blends against the cliff behind it instead of against the sky.
      renderOrder={prop.transparent ? 1 : 0}
    />
  );
}

export function TerrainLayer({ centroidThree }: { centroidThree: THREE.Vector3 }) {
  const props = useTerrainStore((s) => s.props);
  if (!props) return null;
  return (
    <>
      {props.map((p, i) => (
        <Prop key={`${p.mesh}-${i}`} prop={p} centroidThree={centroidThree} />
      ))}
    </>
  );
}
