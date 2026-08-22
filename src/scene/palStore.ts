// Optional Pal layer for the timelapse renderer.
//
// OFF BY DEFAULT, exactly like daylightStore. `pals === null` means "the editor
// as it always was" and nothing in the app's UI ever writes it — the only writer
// is CameraDevHook's dev-only `setPals()`, which the offline timelapse pipeline
// drives. Viewport-only: never touches the model, the loaded blueprint, or
// export/writeback.
//
// WHAT A PalInstance IS, DATA-WISE
//   x/y/z  Unreal cm, verbatim from the Pal's own
//          CharacterSaveParameterMap[..].SaveParameter.LastJumpedLocation in the
//          snapshot being shown. Palworld does not persist a live Pal transform;
//          LastJumpedLocation is the only world position on the record and means
//          "where this Pal last jumped", not "where it is standing right now".
//          It is used exactly as recorded — nothing is jittered, scattered,
//          distributed or invented, and a Pal with no recorded position is
//          simply never drawn.
//   url    the Pal's real extracted SK_<Species>.glb (public/pal_meshes/),
//          resolved from its recorded CharacterID via pal_manifest.json.
//   There is deliberately NO rotation: the save records no facing for a Pal, so
//   every Pal is drawn unrotated rather than given a made-up heading.
import { create } from "zustand";

export interface PalInstance {
  /** Pal instance GUID from the save (stable across snapshots). */
  id: string;
  /** Recorded CharacterID, e.g. "BerryGoat". */
  char: string;
  /** URL of the extracted skeletal mesh GLB. */
  url: string;
  /** Recorded LastJumpedLocation, Unreal cm. */
  x: number;
  y: number;
  z: number;
}

export interface PalState {
  /** null = Pal layer off (default, and the only value the app's UI produces). */
  pals: PalInstance[] | null;
  setPals: (p: PalInstance[] | null) => void;
}

export const usePalStore = create<PalState>((set) => ({
  pals: null,
  setPals: (pals) => set({ pals }),
}));
