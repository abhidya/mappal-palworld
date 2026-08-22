// Optional real-surroundings layer for the timelapse renderer. OFF BY DEFAULT
// (`props === null`), same contract as daylightStore / palStore / playerStore:
// nothing in the app's UI writes it, the only writer is CameraDevHook's dev-only
// setTerrain(), and it never touches the model or export.
//
// See TerrainLayer.tsx for where every number comes from (cooked World
// Partition cell packages in the client pak) and why the 25600 cm cell grid is
// evidence rather than a fit.
import { create } from "zustand";

export interface TerrainProp {
  /** Asset name, e.g. "SM_Cliff_Formation_5". */
  mesh: string;
  /** URL of the extracted GLB under public/terrain_meshes/. */
  url: string;
  /** Authored world RelativeLocation, Unreal cm. */
  x: number;
  y: number;
  z: number;
  /** Authored RelativeRotation, converted from FRotator to an Unreal-space quaternion. */
  qx: number;
  qy: number;
  qz: number;
  qw: number;
  /** Authored RelativeScale3D (Unreal axis order). */
  sx: number;
  sy: number;
  sz: number;

  // --- WATER SURFACES ONLY (ocean / ponds / river / waterfalls) -------------
  // Palworld's water has no base-colour map: the ocean and the ponds are
  // MSM_SingleLayerWater and the waterfalls are unlit translucent noise
  // shaders, so the shared "sample the albedo texture" path finds nothing and
  // falls through to TerrainLayer's flat rock-green. These optional fields
  // carry the material's OWN cooked parameter values instead — the colour
  // vectors, opacity and roughness that the MaterialInstanceConstant actually
  // ships — so a water surface renders with the game's numbers rather than a
  // stand-in. Every field is optional; a prop without them behaves exactly as
  // before. build_terrain.py records where each number came from in `water`.
  /** Linear-RGB tint multiplied into TEXTURED slots (e.g. a waterfall's Color01). */
  tint?: [number, number, number];
  /** Linear-RGB colour for slots with no base-colour map (the water body colour). */
  flat?: [number, number, number];
  /** Material opacity; only meaningful with `transparent`. */
  opacity?: number;
  /** True for BLEND_Translucent materials. */
  transparent?: boolean;
  /** The material's own Roughness scalar. */
  rough?: number;
  /** Provenance: which asset/parameter every number above was read from. */
  water?: { kind: string; material: string; source: string };

  // --- VEGETATION INSIDE THE BUILT FOOTPRINT ---------------------------------
  /**
   * `Model.RawData.instance_id` of every placed piece standing on this plant.
   *
   * In game, building CLEARS the foliage under the piece. The pak's foliage and
   * the save's buildings are two independent sources here, so nothing removed
   * the trees the player removed — at Wooden Camp, oaks grew up through an
   * elevated wooden deck. build_terrain.py tags each plant whose trunk falls
   * inside a placed piece's own oriented box (see its BUILT FOOTPRINT section
   * for the box, the axis order and why the test is XY-only), and TerrainLayer
   * hides the plant only while one of these pieces is in the frame's live
   * object set.
   *
   * That is what makes it TIME-AWARE rather than a static erase: at frame 0 the
   * forest is intact, a tree goes as the foundation over it is placed, and a
   * base that is later deleted from the save (Lost Camp) gives its trees back.
   * Undefined on everything that is not vegetation inside the footprint, and on
   * every prop of an older terrain_*.json — which therefore renders unchanged.
   */
  cullBy?: string[];
}

export interface TerrainState {
  /** null = surroundings layer off (default, and the only value the app's UI produces). */
  props: TerrainProp[] | null;
  setProps: (p: TerrainProp[] | null) => void;
}

export const useTerrainStore = create<TerrainState>((set) => ({
  props: null,
  setProps: (props) => set({ props }),
}));
