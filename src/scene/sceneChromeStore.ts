// Whether the scene draws its NON-DIEGETIC aids — the drei <Grid> ground plane
// and anything else that exists to help a person edit rather than to depict the
// world. Same opt-in contract as daylightStore/palStore/playerStore: the app's
// UI never writes it, the only writer is CameraDevHook's dev-only setChrome(),
// and the default leaves interactive MapPal exactly as it was.
//
// WHY THE TIMELAPSE TURNS IT OFF. The Grid is a 1 m/10 m reference lattice
// floating at y=0, and it earns its place in the editor: with no ground, it is
// the only thing telling you where the ground is. The timelapse no longer has
// that problem — TerrainLayer draws 600 m of the game's own real terrain — so
// the Grid is at best redundant and at worst actively wrong, because it is an
// infinite flat plane cutting straight THROUGH real hills that are not flat.
// It also costs legibility where it is needed most: the builder avatar is a
// small figure against the ground, and a high-contrast blue lattice drawn over
// the same pixels is exactly the kind of visual noise that hides it.
import { create } from "zustand";

export interface SceneChromeState {
  /** false = hide the editor's grid ground plane. Default true (editor behaviour). */
  grid: boolean;
  setChrome: (c: { grid?: boolean }) => void;
}

export const useSceneChromeStore = create<SceneChromeState>((set) => ({
  grid: true,
  setChrome: (c) => set((s) => ({ grid: c.grid ?? s.grid })),
}));
