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
//
// TWO THINGS HERE ARE NOT STATIC, and both are driven by state the timelapse
// harness already writes every frame — no new call into this layer, and no
// change to setTerrain()'s "set once for the whole render" contract:
//
//   VEGETATION INSIDE THE BUILT FOOTPRINT (`prop.cullBy`). In game, placing a
//   piece clears the foliage under it; the pak's foliage and the save's
//   buildings are independent sources here, so nothing did — at Wooden Camp,
//   oaks grew up through an elevated wooden deck. build_terrain.py tags each
//   plant with the instance_ids of the pieces standing on it and this layer
//   hides it while any of them is in the editor store's LIVE object set, which
//   setObjects() replaces per frame. So the forest is whole at frame 0, a tree
//   goes as the foundation over it lands, and a base later deleted from the save
//   (Lost Camp) gives its trees back.
//
//   WATER'S DAYLIGHT RESPONSE (`prop.water`). See DayNightLights' WATER_NIGHT
//   note: water ships no base-colour map and a colour channel already at 1.0, so
//   under the rig's deliberately flat exposure it read the same bright teal at
//   midnight as at noon. Its shipped colour is scaled by the rig's own
//   `waterLight` — luminance only, exactly 1.0 in full day.
//
// Everything else is genuinely static, so it is rendered through a memoized
// child that never re-renders however often the two above change.
import { memo, useMemo } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import { ueVecToThree, ueQuatToThree } from "./coords";
import { buildGlb, glbMaterials, WHITE } from "./glbMaterial";
import { UNIT_SCALE } from "./coords";
import { useTerrainStore, type TerrainProp } from "./terrainStore";
import { useDaylightStore } from "./daylightStore";
import { daylightState } from "./DayNightLights";
import { useEditorStore } from "../model/store";

const S = UNIT_SCALE;
const UE_TO_THREE = new THREE.Matrix4().set(S, 0, 0, 0, 0, 0, S, 0, 0, S, 0, 0, 0, 0, 0, 1);

function Prop({
  prop,
  centroidThree,
  hidden = false,
  waterLight = 1,
}: {
  prop: TerrainProp;
  centroidThree: THREE.Vector3;
  /** True while a placed piece is standing on this plant — see `cullBy`. */
  hidden?: boolean;
  /** Daylight scalar for water surfaces only; 1 everywhere else. */
  waterLight?: number;
}) {
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
  //
  // `waterLight` multiplies those same values and nothing else. It is applied in
  // LINEAR space, on the FLinearColor itself, which is where a light term
  // belongs — scaling the sRGB-encoded value instead would bend the ratios
  // between the channels and really would be a recolour.
  const tint = useMemo(
    () =>
      prop.tint
        ? new THREE.Color().setRGB(
            prop.tint[0] * waterLight,
            prop.tint[1] * waterLight,
            prop.tint[2] * waterLight,
            THREE.LinearSRGBColorSpace,
          )
        : WHITE,
    [prop.tint, waterLight],
  );
  const flat = useMemo(
    () =>
      prop.flat
        ? new THREE.Color().setRGB(
            prop.flat[0] * waterLight,
            prop.flat[1] * waterLight,
            prop.flat[2] * waterLight,
            THREE.LinearSRGBColorSpace,
          )
        : new THREE.Color("#6b7f63"),
    [prop.flat, waterLight],
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
      // `visible` rather than unmounting: the props array is what keys this
      // whole layer, so dropping an entry would renumber its neighbours and make
      // React tear down and re-load GLBs mid-render. Hiding costs one skipped
      // draw call and keeps every key stable.
      visible={!hidden}
      // Translucent water (the waterfalls) draws after the opaque world, so it
      // blends against the cliff behind it instead of against the sky.
      renderOrder={prop.transparent ? 1 : 0}
    />
  );
}

/** The props that never change for the whole render — the overwhelming majority. */
const StaticProps = memo(function StaticProps({
  props,
  centroidThree,
}: {
  props: TerrainProp[];
  centroidThree: THREE.Vector3;
}) {
  return (
    <>
      {props.map((p, i) => (
        <Prop key={`s-${p.mesh}-${i}`} prop={p} centroidThree={centroidThree} />
      ))}
    </>
  );
});

/** Memoized so a frame that changed neither `hidden` nor `waterLight` for this
 *  prop costs nothing, even though the parent re-renders every frame. */
const LiveProp = memo(Prop);

export function TerrainLayer({ centroidThree }: { centroidThree: THREE.Vector3 }) {
  const props = useTerrainStore((s) => s.props);
  const hour = useDaylightStore((s) => s.hour);
  // The frame's live object set. `objects` is what the timelapse replaces every
  // frame via setObjects(), so this is the piece list as of THIS frame — the
  // whole time-awareness of the footprint cull rests on reading it here rather
  // than baking the final footprint in at build time.
  const objects = useEditorStore((s) => s.objects);

  // Split once per terrain load, not per frame.
  const { statics, live } = useMemo(() => {
    const statics: TerrainProp[] = [];
    const live: TerrainProp[] = [];
    for (const p of props ?? []) (p.cullBy?.length || p.water ? live : statics).push(p);
    return { statics, live };
  }, [props]);

  const liveIds = useMemo(() => {
    if (!live.some((p) => p.cullBy?.length)) return null; // nothing to test against
    return new Set(objects.map((o) => o.id));
  }, [objects, live]);

  // `hour === null` is the editor's static lighting, where water keeps its
  // shipped colour exactly as it always has.
  const waterLight = useMemo(() => (hour === null ? 1 : daylightState(hour).waterLight), [hour]);

  if (!props) return null;
  return (
    <>
      <StaticProps props={statics} centroidThree={centroidThree} />
      {live.map((p, i) => (
        <LiveProp
          key={`l-${p.mesh}-${i}`}
          prop={p}
          centroidThree={centroidThree}
          hidden={!!liveIds && !!p.cullBy?.some((id) => liveIds.has(id))}
          waterLight={p.water ? waterLight : 1}
        />
      ))}
    </>
  );
}
