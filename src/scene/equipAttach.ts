// Composing an equipment part's SOCKET transform into the matrix PlayerLayer
// bakes into a character part's vertices.
//
// Kept out of PlayerLayer.tsx so the ORDER of the composition — which is the
// whole content of this file, and the only thing here that can be got wrong —
// is stated once, next to the reason for it.
//
//   vertices are in SOCKET-LOCAL Unreal space
//     -> socket : where that socket sits in the character's COMPONENT space, at
//                 the baked animation frame (union/equipment_sockets_posed.json)
//     -> comp   : CharacterMesh0's own RelativeLocation/Rotation/Scale, i.e.
//                 where the mesh hangs off the recorded ACTOR transform
//                 (characterXform.ts — the same correction every Pal gets)
//     -> swap   : Unreal (x, y, z) -> three (x, z, y) * UNIT_SCALE
//
// so the matrix is  UE_TO_THREE * comp * socket, and charLocalMatrix already
// returns UE_TO_THREE * comp. Composing the socket on the RIGHT is what makes
// it a transform in Unreal component space, which is the space it was measured
// in; putting it anywhere else in the product would rotate it about three.js
// axes instead and silently mis-place the prop.
//
// The socket quaternion is used with its Unreal components verbatim, exactly as
// characterXform.ts's rotatorToQuat does: it is composed in UNREAL space and
// only then handed to the axis swap, so no handedness conversion belongs here.
import * as THREE from "three";
import { charLocalMatrix, xformKey, type CharXform } from "./characterXform";
import type { PlayerPart } from "./playerStore";

/**
 * The local matrix to bake into `part`'s vertices: the character component
 * transform for a skinned part, and that with the part's socket composed in for
 * a rigid prop.
 */
export function partLocalMatrix(part: PlayerPart, xform: CharXform): THREE.Matrix4 {
  const base = charLocalMatrix(xform);
  const a = part.attach;
  if (!a) return base;
  const socket = new THREE.Matrix4().compose(
    new THREE.Vector3(a.t[0], a.t[1], a.t[2]),
    new THREE.Quaternion(a.q[0], a.q[1], a.q[2], a.q[3]),
    new THREE.Vector3(1, 1, 1),
  );
  return base.multiply(socket);
}

/**
 * Cache key for buildGlb. MUST vary with the socket as well as the URL and the
 * component transform — buildGlb caches geometry by this string, so two parts
 * that share a mesh but sit at different sockets would otherwise collide and
 * the second would silently render at the first one's place.
 */
export function partKey(part: PlayerPart, xform: CharXform): string {
  const a = part.attach;
  return `${part.url}|${xformKey(xform)}` + (a ? `|@${a.socket ?? ""}:${a.t.join(",")}:${a.q.join(",")}` : "");
}
