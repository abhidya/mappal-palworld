// DEV-ONLY camera hook. Exposes the R3F camera + OrbitControls on window so an
// automated screenshot pipeline can set a deterministic, repeatable framing
// (identical before/after shots for feature GIFs), plus viewport-level
// visibility and an object-set swap so such a pipeline can shoot many frames of
// one base without reloading it. Guarded by import.meta.env
// .DEV at the call site in Scene.tsx, so it is tree-shaken out of production
// builds and never ships. Not wired to any UI.
import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useVisibilityStore } from "./visibilityStore";
import { useEditorStore } from "../model/store";
import type { PlacedObject } from "../model/types";

interface OrbitLike {
  target: THREE.Vector3;
  update: () => void;
  enabled: boolean;
}

export function CameraDevHook() {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as unknown as OrbitLike | null;

  useEffect(() => {
    const api = {
      camera,
      controls,
      // Point the camera at `target`, sitting `pos` away, and let OrbitControls
      // adopt that as its orbit target so subsequent drags behave.
      setView(pos: [number, number, number], target: [number, number, number]) {
        camera.position.set(pos[0], pos[1], pos[2]);
        if (controls) {
          controls.target.set(target[0], target[1], target[2]);
          controls.update();
        } else {
          camera.lookAt(target[0], target[1], target[2]);
        }
      },
      // Viewport-only level visibility (for peel/solo feature GIFs). Never
      // touches the model or export — same guarantee the eye toggles have.
      hideLevels(levels: number[]) {
        useVisibilityStore.setState({ hiddenLevels: new Set(levels) });
      },
      showAllLevels() {
        useVisibilityStore.getState().showAll();
      },
      // Swap the rendered object set in place, for a pipeline that shoots many
      // frames of the same base (e.g. a build-order timelapse). The point is to
      // avoid a full loadFile() per frame: re-parsing a multi-MB blueprint
      // dominated frame time, and this took our render loop from ~3.5s to
      // ~0.28s per frame.
      //
      // UNSAFE FOR EXPORT, and unlike hideLevels() this is NOT a viewport-only
      // lens. hideLevels() writes to visibilityStore, which is deliberately
      // separate from the model; this writes the editor store's `objects`, and
      // that array IS the export input — reconcileExport() treats any raw
      // map_object missing from it as deleted and strips its works, containers
      // and inbound connector links to match. Swapping in a subset (the whole
      // point of a timelapse) and then exporting would write a file with
      // everything else removed. It also bypasses the PalBoxV2 protection that
      // deleteSelection()/duplicateSelection() enforce.
      //
      // So the swap sets `devObjectsSwapped`, and exportBlueprint() hard-
      // refuses while it is set — reload a blueprint to clear it. Undo/redo are
      // cleared too, since these objects did not arrive through a command and
      // an undo across the swap would restore a mismatched state.
      //
      // Production is unaffected: Scene.tsx only mounts this hook under
      // import.meta.env.DEV, so the whole surface is tree-shaken out of a
      // production build and the flag is always false there.
      getObjects(): PlacedObject[] {
        return useEditorStore.getState().objects;
      },
      setObjects(objects: PlacedObject[]) {
        useEditorStore.setState({
          objects,
          selection: [],
          undoStack: [],
          redoStack: [],
          devObjectsSwapped: true,
        });
      },
    };
    (window as unknown as { __mappalCam?: typeof api }).__mappalCam = api;
    return () => {
      delete (window as unknown as { __mappalCam?: typeof api }).__mappalCam;
    };
  }, [camera, controls]);

  return null;
}
