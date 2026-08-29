// DEV-ONLY camera hook. Exposes the R3F camera + OrbitControls on window so an
// automated screenshot pipeline can set a deterministic, repeatable framing
// (identical before/after shots for feature GIFs). Guarded by import.meta.env
// .DEV at the call site in Scene.tsx, so it is tree-shaken out of production
// builds and never ships. Not wired to any UI.
import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useVisibilityStore } from "./visibilityStore";
import { useDaylightStore } from "./daylightStore";
import { useSceneChromeStore } from "./sceneChromeStore";
import { usePalStore, type PalInstance } from "./palStore";
import { usePlayerStore, type PlayerInstance, type BuilderAvatar } from "./playerStore";
import { preloadPlayerMeshes } from "./PlayerLayer";
import { useTerrainStore, type TerrainProp } from "./terrainStore";
import { useEditorStore } from "../model/store";

interface OrbitLike {
  target: THREE.Vector3;
  update: () => void;
  enabled: boolean;
}

export function CameraDevHook() {
  const camera = useThree((s) => s.camera);
  const scene = useThree((s) => s.scene);
  const controls = useThree((s) => s.controls) as unknown as OrbitLike | null;

  useEffect(() => {
    const api = {
      camera,
      // Exposed so the timelapse harness can assert that turning the day/night
      // rig back off restores the editor's exact default lighting/background.
      scene,
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
      // Timelapse pipeline: swap the rendered object set in place, without
      // re-parsing a blueprint file (a full loadFile() per frame dominated
      // render time). Editor-store only — the loaded raw JSON is untouched,
      // so export/writeback still reflect the real file.
      getObjects() {
        return useEditorStore.getState().objects;
      },
      setObjects(objs: unknown[]) {
        useEditorStore.setState({ objects: objs as never, selection: [] });
      },
      // Timelapse day/night: `hour` is the base's real IN-GAME time of day
      // (GameTimeSaveData.GameDateTimeTicks -> 0..24). Pass null to hand the
      // scene back to its normal static editor lighting. Nothing in the app's
      // UI calls this; see daylightStore.ts.
      setDaylight(hour: number | null) {
        useDaylightStore.getState().setHour(hour);
      },
      // Timelapse scene chrome: turn the editor's non-diegetic aids off for a
      // render. setChrome({grid:false}) drops the drei <Grid> ground plane,
      // which real terrain has made both redundant and wrong (it is a flat
      // lattice cutting through hills) and which visually buries the small
      // figures this render is about. Nothing in the app's UI calls this — see
      // sceneChromeStore.ts.
      setChrome(c: { grid?: boolean }) {
        useSceneChromeStore.getState().setChrome(c);
      },
      // Timelapse Pal layer: the Pals the save recorded inside this base at the
      // snapshot being rendered, with their own LastJumpedLocation. Pass null to
      // turn the layer off again. Nothing in the app's UI calls this — see
      // palStore.ts / PalLayer.tsx.
      setPals(pals: PalInstance[] | null) {
        usePalStore.getState().setPals(pals);
      },
      // Timelapse player layer: the players the save recorded, assembled from
      // their PlayerCharacterMakeData and placed at their recorded
      // LastTransform, both read from the snapshot being rendered. Pass null to
      // turn the layer off. See playerStore.ts / PlayerLayer.tsx (including what
      // LastTransform does and does not claim).
      setPlayers(players: PlayerInstance[] | null) {
        usePlayerStore.getState().setPlayers(players);
      },
      // Timelapse builder avatar: the player whose recorded build_player_uid
      // owns the piece being placed this frame, drawn beside that piece. Pass
      // null for a piece with no recorded builder, a system-built piece, or to
      // turn the avatar off. WHO is recorded attribution; WHERE is a rendering
      // choice — see playerStore.ts's BuilderAvatar doc before changing this.
      setBuilder(builder: BuilderAvatar | null) {
        usePlayerStore.getState().setBuilder(builder);
      },
      // Parse every avatar GLB up front. The timelapse calls this once with all
      // the part URLs in avatars.json, so switching builder mid-render never
      // suspends — see preloadPlayerMeshes for what a suspension costs a frame.
      preloadPlayers(urls: string[]) {
        preloadPlayerMeshes(urls);
      },
      // Timelapse surroundings layer: the cliffs/rocks/ruins the game's own
      // World Partition cells place around this base. Static for the whole
      // render (the client pak is one version, not a per-snapshot record) — see
      // terrainStore.ts / TerrainLayer.tsx.
      setTerrain(props: TerrainProp[] | null) {
        useTerrainStore.getState().setProps(props);
        // THE HORIZON NEEDS THE FAR PLANE OPENED. Scene.tsx sets far = 5000 m,
        // which was ample while the terrain stopped at 600 m but silently
        // clips the far-field mesh (TerrainProp.horizon), and a far-plane cut
        // through the land reads as exactly the "world ends here" edge this
        // layer exists to remove. `reach` is that mesh's own furthest vertex
        // from the base centre, in Unreal cm.
        //
        // Only ever widens, only when a horizon prop is present, and only in
        // this dev-only hook — the editor, which never calls setTerrain, keeps
        // Scene.tsx's 5000 exactly. Depth precision is unaffected in any
        // practical sense: with near << far the resolution goes as
        // z^2/(near * 2^bits), so it depends on `near`, not on `far`.
        let reach = 0;
        for (const p of props ?? []) if (p.horizon && p.reach) reach = Math.max(reach, p.reach);
        if (reach > 0 && (camera as THREE.PerspectiveCamera).isPerspectiveCamera) {
          const want = reach * 0.01 * 1.25 + 200; // cm -> m (UNIT_SCALE), + headroom
          if (camera.far < want) {
            camera.far = want;
            camera.updateProjectionMatrix();
          }
        }
      },
    };
    (window as unknown as { __mappalCam?: typeof api }).__mappalCam = api;
    return () => {
      delete (window as unknown as { __mappalCam?: typeof api }).__mappalCam;
    };
  }, [camera, scene, controls]);

  return null;
}
