// The blueprint component transform that sits between a CHARACTER's recorded
// actor location and where its mesh actually belongs.
//
// This is the same class of bug meshXform.json fixes for build objects, and it
// bites Pals and players harder. A save records an ACTOR transform — for a Pal,
// SaveParameter.LastJumpedLocation; for a player, SaveData.LastTransform. But a
// UE Character's actor origin is the CAPSULE CENTRE, and the skeletal mesh hangs
// off it with its own RelativeLocation. Read straight out of the game's own
// blueprints (palx --assetprops), e.g. BP_BerryGoat:
//
//     [CapsuleComponent]        CollisionCylinder  CapsuleHalfHeight = 30
//     [PalSkeletalMeshComponent] CharacterMesh0    RelativeLocation Z = -30
//
// i.e. the mesh sits exactly one capsule half-height BELOW the recorded point,
// which is what puts the feet on the ground. Drawing the mesh at the recorded
// location directly leaves every Pal floating by its own capsule radius — small
// for a Lamball, over a metre for the big ones. The offset is per species and is
// EXTRACTED, never estimated: see build_char_xform.py.
//
// Boss variants additionally carry a RelativeScale3D (BP_BerryGoat_BOSS is
// 1.5x), which is why scale is part of the record rather than assumed to be 1.
import * as THREE from "three";
import { UNIT_SCALE } from "./coords";

export interface CharXform {
  /** CharacterMesh0 RelativeLocation, Unreal cm. */
  loc: [number, number, number];
  /** CharacterMesh0 RelativeRotation as FRotator degrees [pitch, yaw, roll]. */
  rot: [number, number, number];
  /** CharacterMesh0 RelativeScale3D. */
  scale: [number, number, number];
}

export const IDENTITY_XFORM: CharXform = { loc: [0, 0, 0], rot: [0, 0, 0], scale: [1, 1, 1] };

const S = UNIT_SCALE;
/** three.(x,y,z) = ue.(x,z,y) * UNIT_SCALE — the same swap coords.ts documents. */
const UE_TO_THREE = new THREE.Matrix4().set(
  S, 0, 0, 0,
  0, 0, S, 0,
  0, S, 0, 0,
  0, 0, 0, 1,
);

/** Unreal FRotator (degrees) -> quaternion, using Unreal's own sign convention. */
function rotatorToQuat(pitch: number, yaw: number, roll: number): THREE.Quaternion {
  const d = Math.PI / 360; // deg -> half-radians
  const sp = Math.sin(pitch * d), cp = Math.cos(pitch * d);
  const sy = Math.sin(yaw * d), cy = Math.cos(yaw * d);
  const sr = Math.sin(roll * d), cr = Math.cos(roll * d);
  return new THREE.Quaternion(
    cr * sp * sy - sr * cp * cy,
    -cr * sp * cy - sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
    cr * cp * cy + sr * sp * sy,
  );
}

/**
 * Local matrix to bake into a character GLB's vertices: apply the blueprint's
 * component transform in UNREAL space first (that is the space the component
 * transform is authored in), then the UE->three axis swap. Composing in the
 * other order would rotate about the wrong axes.
 */
export function charLocalMatrix(x: CharXform): THREE.Matrix4 {
  const comp = new THREE.Matrix4().compose(
    new THREE.Vector3(x.loc[0], x.loc[1], x.loc[2]),
    rotatorToQuat(x.rot[0], x.rot[1], x.rot[2]),
    new THREE.Vector3(x.scale[0], x.scale[1], x.scale[2]),
  );
  return new THREE.Matrix4().multiplyMatrices(UE_TO_THREE, comp);
}

/** Stable cache key for buildGlb: geometry differs per (mesh, component transform). */
export function xformKey(x: CharXform): string {
  return `${x.loc.join(",")}|${x.rot.join(",")}|${x.scale.join(",")}`;
}
