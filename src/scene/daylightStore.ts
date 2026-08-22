// Optional day/night lighting for the timelapse renderer.
//
// OFF BY DEFAULT, deliberately. `hour === null` means "the editor's normal
// static lighting", and nothing in the app's UI ever sets it — the only writer
// is CameraDevHook's dev-only `setDaylight()`, which the offline timelapse
// pipeline drives. So the editor look is byte-identical to before unless a
// caller opts in, exactly like visibilityStore's viewport-only lens: a render
// concern that never touches the model or export.
//
// `hour` is the base's IN-GAME time of day, 0..24, derived from
// worldSaveData.GameTimeSaveData.GameDateTimeTicks (see the timelapse
// renderer's tick->hour conversion). It is real recorded world time, not a
// wall-clock time and not a synthesised animation parameter.
import { create } from "zustand";

export interface DaylightState {
  /** In-game hour of day, 0..24. null = static editor lighting (default). */
  hour: number | null;
  setHour: (h: number | null) => void;
}

export const useDaylightStore = create<DaylightState>((set) => ({
  hour: null,
  setHour: (hour) => set({ hour }),
}));
