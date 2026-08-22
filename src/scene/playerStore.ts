// Optional player-avatar layer for the timelapse renderer. OFF BY DEFAULT
// (`players === null`), same contract as daylightStore/palStore: nothing in the
// app's UI ever writes it, the only writer is CameraDevHook's dev-only
// setPlayers(), and it never touches the model or export.
//
// See PlayerLayer.tsx for what is recorded data (who, look, where — all from
// Players/<UID>.sav at the snapshot being shown) and for the honesty limit on
// what LastTransform does and does not mean.
import { create } from "zustand";

/**
 * Where a part that is NOT skinned to the player skeleton hangs off the
 * character, in UNREAL component space (cm, and Unreal's own quaternion
 * convention) — i.e. an attach socket.
 *
 * Almost every part needs nothing here. Armour, hair, heads and
 * SK_HeadEquip052 are all skinned to SK_PalHuman_Skeleton and are authored in
 * character space, so they are drawn at the character's own origin and the
 * baked animation frame already put their vertices in the right place.
 *
 * A RIGID prop is the exception. SK_HeadEquip034 (the plastic helmet) has ONE
 * bone, ten centimetres of geometry, and lives in socket-local space; the
 * cooked data says which socket by name
 * (HairAttachSocketNameMap -> Socket_HairAttach_HeadEquip_front03). Its place
 * on the character is therefore a socket transform, and it must be the socket
 * transform AT THE BAKED POSE, not at the bind pose — the bind-pose socket sits
 * at z 154 cm and the kneeling one at z 104 cm, so using the bind value would
 * leave the helmet hanging half a metre above a kneeling head.
 * union/equipment_sockets_posed.json carries the posed value, composed by plain
 * FK from the socket's own recorded relative transform and the same animation
 * frame the vertices were baked from (build_posed_sockets.py). Nothing here is
 * an estimate.
 */
export interface PartAttach {
  /** Socket translation in Unreal component space, cm. */
  t: [number, number, number];
  /** Socket rotation, Unreal quaternion (x, y, z, w). */
  q: [number, number, number, number];
  /** Provenance string, carried so a reader can see which socket this is. */
  socket?: string;
}

export interface PlayerPart {
  /** URL of an extracted SK_Player_* GLB (body / head / hair / outfit piece). */
  url: string;
  /** Tint from the save's own LinearColor for this part, "#rrggbb". Undefined = untinted. */
  color?: string;
  /** Socket placement for a rigid prop. Undefined for every skinned part. */
  attach?: PartAttach;
}

export interface PlayerInstance {
  /** Player UID, the first eight hex characters, e.g. "aaaaaaaa". */
  uid: string;
  /** Parts assembled from PlayerCharacterMakeData at this snapshot. */
  parts: PlayerPart[];
  /** LastTransform translation, Unreal cm. */
  x: number;
  y: number;
  z: number;
  /** LastTransform rotation quaternion, Unreal space. */
  qx: number;
  qy: number;
  qz: number;
  qw: number;
}

/**
 * The BUILDER AVATAR: the player the save says is responsible for the piece
 * that is being placed right now, drawn beside that piece.
 *
 * READ THE PROVENANCE SPLIT CAREFULLY — the two halves are not equally real.
 *
 *   WHO is recorded data. Every map object carries its own `build_player_uid`,
 *   so "player X placed this piece" comes straight out of the save. Counted on
 *   the FULL uid across the four bases (uids and names redacted here — they are
 *   real people's identifiers; the SHAPE is what matters):
 *
 *     00000000-0000-0000-0000-000000000000  x3163  the all-zero "no owner"
 *                                                  sentinel -> unattributed
 *     aaaaaaaa-0000-0000-0000-000000000000  x2237  player A
 *     bbbbbbbb-0000-0000-0000-000000000000  x1376  player B
 *     00000000-0000-0000-0000-000000000001   x304  player C
 *     cccccccc-0000-0000-0000-000000000000     x3  (no roster name)
 *
 *   Note the first and fourth rows: two DIFFERENT uids share the first eight
 *   characters, so the short key "00000000" that builders_<b>.json uses is
 *   ambiguous unless the sentinel is resolved before truncation — which
 *   build_actor_scenes.py does, emitting null for it. A piece whose builder is
 *   null draws no avatar and is never attributed to a guess; a piece keyed
 *   "00000000" is player C's real work and is drawn like anyone else's.
 *
 *   WHERE is a RENDERING CHOICE, and must never be presented as recorded.
 *   Palworld does record a player position — SaveData.LastTransform in
 *   Players/<UID>.sav is populated in every snapshot we hold (verified by
 *   decoding the raw .sav files, not inferred) — but it is a SNAPSHOT-GRANULARITY
 *   last-known/logout position. It says where the save last put that player, not
 *   where they were standing at the instant any one piece went down. Palworld
 *   stores no per-piece build position anywhere. So standing the avatar beside
 *   the piece is a presentational device justified by the real attribution
 *   above, and nothing more. `PlayerInstance` (the `players` field) is the
 *   separate, honest layer that draws players at their actually-recorded
 *   LastTransform; the two are deliberately kept apart so neither can be
 *   mistaken for the other.
 */
export interface BuilderAvatar {
  /** Recorded `build_player_uid` of the piece being placed. */
  uid: string;
  /**
   * The player's own name, read from the save's guild rosters
   * (worldSaveData.GroupSaveDataMap -> players[].player_info.player_name) and
   * folded into union/avatars.json by build_names.py. Recorded data, like the
   * uid itself. null for a uid no roster names — that avatar renders with no
   * tag rather than an invented one.
   */
  name: string | null;
  /** Appearance parts — see `appearanceExact` for whether they are contemporaneous. */
  parts: PlayerPart[];
  /** Where to DRAW the avatar, Unreal cm. A rendering choice, not a recorded position. */
  x: number;
  y: number;
  z: number;
  /** Facing, as an Unreal-space quaternion. Also a rendering choice (it faces the piece). */
  qx: number;
  qy: number;
  qz: number;
  qw: number;
  /**
   * true  = `parts` come from a Players/<uid>.sav run that actually covers this
   *         timestamp, i.e. contemporaneous recorded appearance.
   * false = this moment predates the earliest surviving Players/<uid>.sav
   *         (the player-save record spans 1786878184..1787268757, while three of
   *         the four bases start building before that), so the player's EARLIEST
   *         recorded look is used. That extrapolation is only defensible because
   *         each player's appearance is provably constant across the whole
   *         recorded window — player_index.py compares the git-LFS oid of the
   *         .sav blob, and players A / B / C each produce exactly ONE
   *         appearance run over 1,137 snapshots (the fourth player has two).
   */
  appearanceExact: boolean;
}

export interface PlayerState {
  /** null = player layer off (default, and the only value the app's UI produces). */
  players: PlayerInstance[] | null;
  setPlayers: (p: PlayerInstance[] | null) => void;
  /** null = no builder avatar this frame (unrecorded builder, system UID, or layer off). */
  builder: BuilderAvatar | null;
  setBuilder: (b: BuilderAvatar | null) => void;
}

export const usePlayerStore = create<PlayerState>((set) => ({
  players: null,
  setPlayers: (players) => set({ players }),
  builder: null,
  setBuilder: (builder) => set({ builder }),
}));
