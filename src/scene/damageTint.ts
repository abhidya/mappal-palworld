// Structure damage as a per-instance tint, modulating whatever colour the
// object already had.
//
// Every map object carries Model.RawData.hp {current, max}; blueprintView.ts
// already lifts it onto PlacedObject as hpCurrent/hpMax (Sidebar.tsx prints it)
// but nothing drew it. This turns that number into the same kind of value paint
// already produces — a per-instance colour handed to glbMaterial's `tint`, which
// meshStandardMaterial multiplies into the real base-colour map. So a damaged
// piece keeps its texture and its paint and simply reads as charred, rather
// than being swapped for a flat "damage" material.
//
// Deliberately IDENTITY at full HP: damaged(c, hp, max) returns the input
// object unchanged unless the save actually says the piece is hurt. In this
// world that is the overwhelming majority of pieces, so nothing else moves.
//
// The other field, `deterioration_damage`, is NOT used, and that is a measured
// decision rather than an oversight: it reads 0.0 on all 8,103 objects of the
// live save and on all ~8,100 objects of every one of 167 historical snapshots
// sampled across 2026-07-27..08-22. The game expresses decay by lowering
// hp.current, not by that counter.
import * as THREE from "three";

/** Below this, a piece is drawn as damaged. At or above it, nothing changes. */
const FULL = 0.999;

/**
 * Quantise the ratio before it reaches a colour. glbMaterial.ts's MAT_CACHE is
 * keyed on the tint's hex, so a continuous ratio would mint a fresh material
 * per distinct HP value — and HP moves every snapshot. 24 steps is finer than
 * the eye resolves through a texture multiply and keeps the cache bounded.
 */
const STEPS = 24;

/** How dark a piece at 0 HP goes. Not 0: a black piece reads as a hole. */
const MAX_DARKEN = 0.72;
/** How much colour is drained at 0 HP, toward soot rather than toward grey. */
const MAX_DESAT = 0.55;

const CACHE = new Map<string, THREE.Color>();

/**
 * Damage ratio in [0,1], or null when this object has no usable HP bar.
 *
 * hpMax <= 0 is not "destroyed" — it is how the save marks things that never
 * had a bar (loot containers read 0, Pal eggs read -1; together 4,175 of the
 * live save's 8,103 objects). Those must render untouched, so they return null
 * rather than a ratio of 0, which would paint every treasure box black.
 */
export function damageRatio(hpCurrent?: number, hpMax?: number): number | null {
  if (typeof hpCurrent !== "number" || typeof hpMax !== "number") return null;
  if (!(hpMax > 0)) return null;
  const r = hpCurrent / hpMax;
  if (!Number.isFinite(r)) return null;
  return Math.min(1, Math.max(0, r));
}

/**
 * The object's existing colour, darkened and desaturated in proportion to how
 * much HP it is missing. Returns `base` itself — same reference — whenever the
 * piece is intact or has no HP bar, so callers can hand the result straight to
 * the existing material path with no behavioural change for undamaged objects.
 */
export function damagedColor(
  base: THREE.Color | string,
  hpCurrent?: number,
  hpMax?: number
): THREE.Color | string {
  const r = damageRatio(hpCurrent, hpMax);
  if (r === null || r >= FULL) return base;

  const step = Math.round(r * STEPS);
  const baseKey = typeof base === "string" ? base : base.getHexString();
  const key = `${baseKey}|${step}`;
  const hit = CACHE.get(key);
  if (hit) return hit;

  const d = 1 - step / STEPS;                       // 0 = intact, 1 = at 0 HP
  const c = (typeof base === "string" ? new THREE.Color(base) : base.clone());
  const hsl = { h: 0, s: 0, l: 0 };
  c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s * (1 - MAX_DESAT * d), hsl.l * (1 - MAX_DARKEN * d));
  CACHE.set(key, c);
  return c;
}
