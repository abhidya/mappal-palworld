// Renders the Pals that the save says were in this base at the moment being
// shown. Timelapse-only: renders nothing at all unless palStore's `pals` has
// been set by CameraDevHook's dev-only setPals(), so the editor is untouched.
//
// EVERY NUMBER HERE IS RECORDED DATA OR EXTRACTED ASSET DATA.
//   position  = the Pal's own SaveParameter.LastJumpedLocation from the snapshot
//               at time t, used verbatim (see palStore.ts for what that field
//               actually means and why it is an approximation of "where the Pal
//               is"). No jitter, no scatter, no distribution, no palbox
//               fallback: a Pal without a recorded position is not drawn.
//   mesh      = the Pal's own recorded CharacterID resolved to its real
//               extracted SK_<Species>.glb, textured with the base-colour map
//               pulled from the same pak (glbMaterial.ts). Species identity is
//               carried by the texture, not the silhouette, so a flat-shaded
//               Pal is effectively an unidentifiable blob.
//   grounding = the species' OWN blueprint component transform
//               (characterXform.ts / palXform.json). LastJumpedLocation is an
//               ACTOR location, i.e. the capsule centre; the mesh belongs at
//               CharacterMesh0.RelativeLocation relative to it. That is read out
//               of BP_<Species>, not estimated — without it every Pal floats by
//               its own capsule half-height.
//
// THE ONE RENDERING CHOICE, stated plainly: the save records no FACING for a
// Pal, so no yaw of our own is applied — a Pal is drawn at the orientation its
// own blueprint gives the mesh, and nothing here invents a heading.
import { useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { ueVecToThree } from "./coords";
import { buildGlb, glbMaterials, WHITE } from "./glbMaterial";
import { charLocalMatrix, xformKey, IDENTITY_XFORM, type CharXform } from "./characterXform";
import { usePalStore, type PalInstance } from "./palStore";
import palXform from "../data/palXform.json";

const XFORMS = palXform as unknown as Record<string, CharXform>;
/** Slots with no usable base-colour map keep the old flat look rather than rendering blank. */
const FLAT = "#cbd5e1";

function PalMesh({ pal, centroidThree }: { pal: PalInstance; centroidThree: THREE.Vector3 }) {
  const { scene } = useGLTF(pal.url);
  const xf = XFORMS[pal.char] ?? IDENTITY_XFORM;
  const built = useMemo(
    () => buildGlb(scene, `${pal.url}|${xformKey(xf)}`, charLocalMatrix(xf)),
    [pal.url, scene, xf],
  );
  const materials = useMemo(() => (built ? glbMaterials(built, WHITE, FLAT) : null), [built]);
  const position = useMemo(
    () => ueVecToThree({ x: pal.x, y: pal.y, z: pal.z }).sub(centroidThree),
    [pal.x, pal.y, pal.z, centroidThree],
  );
  if (!built || !materials) return null;
  return <mesh position={position} geometry={built.geometry} material={materials} />;
}

export function PalLayer({ centroidThree }: { centroidThree: THREE.Vector3 }) {
  const pals = usePalStore((s) => s.pals);
  if (!pals) return null;
  return (
    <>
      {pals.map((p) => (
        <PalMesh key={p.id} pal={p} centroidThree={centroidThree} />
      ))}
    </>
  );
}
