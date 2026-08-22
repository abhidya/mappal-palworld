// Renders the PLAYERS the save recorded, as they looked at the moment being
// shown. Timelapse-only, same opt-in contract as PalLayer/DayNightLights: draws
// nothing unless playerStore's `players` has been set by CameraDevHook's
// dev-only setPlayers().
//
// WHAT IS RECORDED DATA
//   who      Players/<UID>.sav exists per snapshot for all four players, and
//            every map object carries `build_player_uid` — so "this player built
//            that piece" is real attribution straight out of the save.
//   look     PlayerCharacterMakeData in THAT snapshot's Players/<UID>.sav:
//            BodyMeshName / HeadMeshName / HairMeshName (+ equipment names) and
//            the HairColor / BodyColor / EyeColor LinearColors. The parts list
//            and the tint on each part come from those fields; the meshes are
//            the game's own SK_Player_* assets. Appearance is resolved per
//            snapshot, so a player who re-customised mid-history changes on
//            screen at the snapshot where the save changed.
//   where    LastTransform in that same file — a real recorded world Transform
//            (translation cm + rotation quaternion), verified present and
//            populated for all four players. Both position and facing are used
//            verbatim.
//
// THE HONESTY LIMIT, stated plainly: LastTransform is "where the save last put
// this player" — their position when that snapshot was written — NOT where they
// were standing at the instant any particular piece was placed. Palworld records
// no per-piece build position. So this layer shows a real player at a real
// recorded location at a real recorded time; it does NOT show them in the act of
// placing the piece next to them, and nothing here should be read that way.
// Snapshots whose LastTransform is empty (it does happen) simply produce no
// player — the position is never back-filled from a neighbouring snapshot.
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";
import { Html, useGLTF } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { ueVecToThree, ueQuatToThree } from "./coords";
import { buildGlb, glbMaterials, WHITE } from "./glbMaterial";
import { IDENTITY_XFORM, type CharXform } from "./characterXform";
import {
  usePlayerStore,
  type PlayerInstance,
  type PlayerPart,
  type BuilderAvatar,
} from "./playerStore";
import { partLocalMatrix, partKey } from "./equipAttach";
import palXform from "../data/palXform.json";

// Same capsule-centre correction as Pals: LastTransform is the player ACTOR's
// transform, and the character mesh hangs off it at CharacterMesh0's own
// RelativeLocation. Read from the player character blueprint, not estimated.
const PLAYER_XFORM: CharXform =
  ((palXform as unknown as Record<string, CharXform>)["__player__"]) ?? IDENTITY_XFORM;
const FLAT = "#d8dee9";

/**
 * LEGIBILITY SCALE — a stated rendering choice, not a claim about anyone's size.
 *
 * The avatar geometry is the game's own SK_Player_* mesh at its real extracted
 * dimensions: 1.47 m from sole to crown. That is correct and it is also, at the
 * scale this timelapse is framed at, invisible. The renderer frames the WHOLE
 * base, and Glass Tower is ~110 m across, so the camera sits ~114 m back; at the
 * 1600x1000 viewport that puts a real-size player at THIRTEEN PIXELS tall,
 * indistinguishable from the specks of hardware on the glass pillars around it.
 * That — not a broken store, a missing mesh or a bad transform — is why the
 * builder avatar read as "not rendering" for so long: it was drawing correctly
 * every single frame, at a size no one could see. (Verified by pointing the
 * camera 4 m at the avatar mid-render: fully textured character, correct feet,
 * correct name tag.)
 *
 * So the avatar is enlarged only as far as legibility requires, and no further:
 *
 *   - The scale is derived from the CAMERA, not fixed. It is whatever multiple
 *     makes the character MIN_AVATAR_PX tall on screen, so a close camera
 *     renders the player at TRUE SIZE (scale clamps to 1) and only a wide
 *     establishing shot enlarges them.
 *   - It is capped at MAX_AVATAR_SCALE so an extreme pull-back cannot inflate a
 *     person into a landmark.
 *   - It scales about the FEET, so the "stands on the piece just built" contract
 *     that __builderAt encodes still holds exactly — an enlarged avatar has its
 *     soles on the same surface as a true-size one, it is not lifted or sunk.
 *
 * This is the same class of device as a map pin that keeps its size as you zoom
 * out. It affects APPARENT SIZE ONLY: who the builder is (`build_player_uid`),
 * what they look like (PlayerCharacterMakeData), and which piece they stand on
 * (the emitted build order) are all untouched real data.
 */
const MIN_AVATAR_PX = 64;
const MAX_AVATAR_SCALE = 6;

/**
 * Multiple to draw a character of `worldHeight` metres at so it is at least
 * MIN_AVATAR_PX tall on screen. 1 whenever it already is.
 */
function legibilityScale(
  camera: THREE.Camera,
  at: THREE.Vector3,
  worldHeight: number,
  viewportPx: number,
): number {
  const persp = camera as THREE.PerspectiveCamera;
  if (!persp.isPerspectiveCamera || !worldHeight || !viewportPx) return 1;
  const dist = camera.position.distanceTo(at);
  // World units spanned by one pixel at that distance, straight off the frustum.
  const worldPerPx = (2 * dist * Math.tan((persp.fov * Math.PI) / 360)) / viewportPx;
  if (!(worldPerPx > 0)) return 1;
  const naturalPx = worldHeight / worldPerPx;
  if (!(naturalPx > 0)) return 1;
  return Math.min(MAX_AVATAR_SCALE, Math.max(1, MIN_AVATAR_PX / naturalPx));
}

function PartMesh({ part }: { part: PlayerPart }) {
  const { scene } = useGLTF(part.url);
  const built = useMemo(
    () => buildGlb(scene, partKey(part, PLAYER_XFORM), partLocalMatrix(part, PLAYER_XFORM)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [partKey(part, PLAYER_XFORM), scene],
  );
  // Textured slots render at true albedo. `part.color` stays undefined on
  // purpose: PlayerCharacterMakeData's colour fields are hue/sat/value SHIFT
  // parameters, not literal colours (see resolve_players.py) — tinting by them
  // would be an invention, so the raw triple is carried as provenance instead.
  const materials = useMemo(
    () => (built ? glbMaterials(built, part.color ?? WHITE, FLAT) : null),
    [built, part.color],
  );
  if (!built || !materials) return null;
  // Placed at the parent group's origin: the group carries position, facing and
  // the legibility scale, so every part of one character transforms together.
  return <mesh name="__avatarPart" geometry={built.geometry} material={materials} />;
}

/**
 * Where to hang this character's name tag, in three.js units above the avatar's
 * own origin, measured off the SAME built geometry the meshes render from
 * (buildGlb is cached per url+transform, so this re-uses the existing buffers
 * rather than loading anything twice).
 *
 * Both numbers come from the parts' combined bounding box rather than a
 * constant, because the parts genuinely differ in size: hair meshes vary in
 * height between players, and the body's origin sits one capsule half-height
 * (90 cm) below the feet, so "top of the head" is not a fixed distance from the
 * origin. The clearance is a fraction of the character's OWN height, which
 * keeps the gap looking the same on a tall and a short avatar.
 */
interface AvatarBounds {
  /** Crown, in avatar-local units above the mesh origin. */
  top: number;
  /** Soles, in avatar-local units (negative — the origin is the capsule centre). */
  bottom: number;
  /** Full sole-to-crown height. */
  height: number;
  /** Where the name tag hangs, local units above the origin. */
  labelY: number;
}

const EMPTY_BOUNDS: AvatarBounds = { top: 0, bottom: 0, height: 0, labelY: 0 };

function useAvatarBounds(parts: PlayerPart[]): AvatarBounds {
  const urls = useMemo(() => parts.map((p) => p.url), [parts]);
  // drei's array form resolves to one array of GLTFs, so the hook count stays
  // fixed however many parts a look has.
  const gltfs = useGLTF(urls) as unknown as { scene: THREE.Object3D }[];
  return useMemo(() => {
    let top = -Infinity;
    let bottom = Infinity;
    for (let i = 0; i < gltfs.length; i++) {
      // Same transform PartMesh bakes, socket included — a helmet placed on a
      // socket must contribute its PLACED bounds, not its 10 cm local ones, or
      // the name tag would sit at the wrong height whenever one is worn.
      const built = buildGlb(
        gltfs[i].scene,
        partKey(parts[i], PLAYER_XFORM),
        partLocalMatrix(parts[i], PLAYER_XFORM),
      );
      if (!built) continue;
      if (!built.geometry.boundingBox) built.geometry.computeBoundingBox();
      const bb = built.geometry.boundingBox;
      if (!bb) continue;
      top = Math.max(top, bb.max.y);
      bottom = Math.min(bottom, bb.min.y);
    }
    if (!Number.isFinite(top)) return EMPTY_BOUNDS;
    const height = Number.isFinite(bottom) ? top - bottom : top;
    return { top, bottom: Number.isFinite(bottom) ? bottom : 0, height, labelY: top + height * 0.18 };
  }, [gltfs, urls, parts]);
}

/**
 * Billboarded name tag over a player's head. Same mechanism ObjectBox.tsx uses
 * for its own floating labels — drei's <Html center>, which is screen-space, so
 * it stays upright and legible whatever the orbit does. Players only; Pals are
 * identified by their real texture and are deliberately left untagged.
 */
function NameTag({ name, labelY }: { name: string; labelY: number }) {
  return (
    <Html center pointerEvents="none" position={[0, labelY, 0]} style={{ zIndex: 1 }}>
      <div className="player-label">{name}</div>
    </Html>
  );
}

/**
 * One character: parts + optional tag, positioned, yawed, and scaled for
 * legibility about its own feet.
 *
 * THE SCALE IS COMPUTED DURING REACT RENDER, NOT ONLY IN useFrame, and that
 * distinction cost a while to find, so it is worth writing down. A useFrame-only
 * version is correct but only from the NEXT animation tick onward — and this
 * scene does not get one on demand. A full base is 1,900+ objects plus terrain,
 * and the loop runs at roughly FOUR frames per second; the offline renderer
 * waits 55 ms between pushing a frame's state and screenshotting it, which is
 * frequently less than a single tick. The observable result was a builder avatar
 * that came out at its unscaled 18 px on some frames and correct on others, with
 * nothing in the data differing between them. Deriving the scale in render makes
 * the very first drawn frame after a state change already correct, and the
 * useFrame below then keeps it live while a person orbits interactively.
 *
 * Reading `camera` during render is sound here rather than stale: the renderer
 * moves the camera and then pushes the frame's state in that order inside one
 * page.evaluate, so the render this triggers already sees the new camera.
 */
function AvatarGroup({
  parts, name, position, quaternion,
}: {
  parts: PlayerPart[];
  name: string | null;
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
}) {
  const ref = useRef<THREE.Group>(null);
  const bounds = useAvatarBounds(parts);
  const camera = useThree((s) => s.camera);
  const viewportPx = useThree((s) => s.size.height);
  const scale = legibilityScale(camera, position, bounds.height, viewportPx);
  // Pin the soles: the group's origin is the capsule centre, `bounds.bottom`
  // below it, so scaling by s would drop the feet to bottom*s. Lifting the
  // origin by bottom*(1-s) puts them back exactly where they were.
  const footY = position.y + bounds.bottom * (1 - scale);
  useFrame((state) => {
    const g = ref.current;
    if (!g) return;
    const s = legibilityScale(state.camera, position, bounds.height, state.size.height);
    g.scale.setScalar(s);
    g.position.set(position.x, position.y + bounds.bottom * (1 - s), position.z);
  });
  return (
    <group
      ref={ref}
      position={[position.x, footY, position.z]}
      quaternion={quaternion}
      scale={scale}
    >
      {parts.map((p) => (
        <PartMesh key={partKey(p, PLAYER_XFORM)} part={p} />
      ))}
      {/* Inside the group, so the tag rides the same scale and stays over the
          head. drei's <Html> is screen-space, so the tag itself keeps its size
          and legibility however far out the camera is — which is also why it,
          unlike the mesh, needed no help to be readable. */}
      {name && <NameTag name={name} labelY={bounds.labelY} />}
    </group>
  );
}

function PlayerAvatar({ player, centroidThree }: { player: PlayerInstance; centroidThree: THREE.Vector3 }) {
  const position = useMemo(
    () => ueVecToThree({ x: player.x, y: player.y, z: player.z }).sub(centroidThree),
    [player.x, player.y, player.z, centroidThree],
  );
  const quaternion = useMemo(
    () => ueQuatToThree({ x: player.qx, y: player.qy, z: player.qz, w: player.qw }),
    [player.qx, player.qy, player.qz, player.qw],
  );
  // No tag on this layer: it draws whoever the save happened to record a
  // LastTransform for, which is not a statement about who built anything.
  return <AvatarGroup parts={player.parts} name={null} position={position} quaternion={quaternion} />;
}

/**
 * The builder avatar: the player whose recorded `build_player_uid` owns the
 * piece being placed this frame, drawn BESIDE that piece.
 *
 * This is the one place in the scene where a character's POSITION is not read
 * from the save. See playerStore.ts's BuilderAvatar doc for the full provenance
 * split; the short version is that WHO built the piece is real recorded
 * attribution, while WHERE the avatar stands is a rendering choice, because
 * Palworld records no per-piece build position (the position it does record,
 * LastTransform, is a snapshot-granularity last-known position, and is drawn
 * honestly by the separate `players` layer above). Nothing here should be read
 * as "the player was standing there".
 */
function BuilderMesh({
  builder, centroidThree,
}: {
  builder: BuilderAvatar;
  centroidThree: THREE.Vector3;
}) {
  const position = useMemo(
    () => ueVecToThree({ x: builder.x, y: builder.y, z: builder.z }).sub(centroidThree),
    [builder.x, builder.y, builder.z, centroidThree],
  );
  const quaternion = useMemo(
    () => ueQuatToThree({ x: builder.qx, y: builder.qy, z: builder.qz, w: builder.qw }),
    [builder.qx, builder.qy, builder.qz, builder.qw],
  );
  // A player the guild rosters do not name passes name=null and renders with no
  // tag — never an invented one. See playerStore.ts's BuilderAvatar.name.
  return (
    <AvatarGroup
      parts={builder.parts}
      name={builder.name}
      position={position}
      quaternion={quaternion}
    />
  );
}

/**
 * Warm the GLB cache for a set of part URLs so the meshes are parsed BEFORE the
 * first frame that needs them.
 *
 * This matters specifically for the offline timelapse. The builder avatar swaps
 * meshes whenever the recorded builder changes, and an un-cached useGLTF
 * suspends — which, without a boundary nearer than the Canvas, unmounts the
 * WHOLE scene for that frame and writes out a flat background-coloured PNG.
 * That is exactly what happened when the avatars first started resolving: three
 * of the forty-eight build-out frames came out blank. Preloading removes the
 * suspension; the <Suspense> boundary below is the belt-and-braces half, so a
 * mesh that still is not ready costs the avatar for one frame instead of the
 * entire render.
 */
export function preloadPlayerMeshes(urls: string[]) {
  for (const u of urls) useGLTF.preload(u);
}

export function PlayerLayer({ centroidThree }: { centroidThree: THREE.Vector3 }) {
  const players = usePlayerStore((s) => s.players);
  const builder = usePlayerStore((s) => s.builder);
  if (!players && !builder) return null;
  return (
    <Suspense fallback={null}>
      {(players ?? []).map((p) => (
        <PlayerAvatar key={p.uid} player={p} centroidThree={centroidThree} />
      ))}
      {builder && (
        <BuilderMesh key={`builder-${builder.uid}`} builder={builder} centroidThree={centroidThree} />
      )}
    </Suspense>
  );
}
