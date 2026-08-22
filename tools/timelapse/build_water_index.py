"""Distil every WATER surface Palworld actually authors into one small index.

WHY THIS EXISTS AT ALL. Every earlier sweep of the cooked world read actors
through a `class name contains "StaticMeshComponent"` filter. Palworld's water
is not authored that way:

  * the OCEAN is a Blueprint actor, BP_SimpleWater_C, in the PERSISTENT level
    (PL_MainWorld5.umap) rather than in any World Partition cell. Its root is a
    HierarchicalInstancedStaticMeshComponent holding 1,681 tiled instances of
    one 10 m plane. The actor carries `bWorldOceanPlane = true`.
  * the RIVERS are SplineMeshComponents emitted by BP_UltimateRiverTool_C.
    "SplineMeshComponent" does not contain "StaticMeshComponent", so all 472 of
    them were dropped by name.
  * the PONDS are HierarchicalInstancedStaticMeshComponents under
    BP_SimpleWater_C actors inside the cells.

None of that is missing from the pak; it was missing from the filter. Nothing
here is generated: every location, scale, instance transform and colour below
is read out of the cooked package with Mappings.usmap applied (palxwater/).

COLOUR. Palworld's water ships no base-colour texture — the ocean and ponds
are MSM_SingleLayerWater and the waterfalls are unlit translucent noise shaders
— so there is nothing for the texture extractor to find and the surfaces fell
through to TerrainLayer's flat rock-green. The colours below are the
MaterialInstanceConstant's OWN cooked FLinearColor parameters, named per
material in `source`. They are linear-RGB, exactly as Unreal stores them.

Inputs (all produced by palxwater against pakroot/Pal-Windows.pak):
  waterout/persistent_exports2.json  every export of PL_MainWorld5.umap
  waterout/cellexports_water.json    every export of the 238 cells around the
                                     four bases (UNFILTERED, unlike terr/cellactors.json)
  waterout/water_splines.json        every SplineMeshComponent + its FSplineMeshParams
  waterout/water_matparams.json      every water material's parameters
Output: water_index.json
"""
import json, math, os

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
W = f"{SP}/waterout"

persistent = json.load(open(f"{W}/persistent_exports2.json"))
cells = json.load(open(f"{W}/cellexports_water.json"))
splines = json.load(open(f"{W}/water_splines.json"))
mats = {m["name"]: m for m in json.load(open(f"{W}/water_matparams.json"))}


def leaf(p):
    return (p or "").split("/")[-1].split(".")[-1]


# --------------------------------------------------------------- materials
# Each entry states which cooked parameter every number came from. Only
# parameters the material itself ships are used; nothing is averaged, guessed
# or "made to look right".
def single_layer_water(name, colour_param, kind):
    """MSM_SingleLayerWater: the body colour is the material's own scattering
    colour vector. In the M_Pal_Water / M_Pal_Water1 family that parameter is
    literally called `Deep Scattering`; in M_Pal_Water_Ver2 (the world ocean)
    the same quantity is split into a scalar magnitude and a colour, and the
    colour half is `ScatteringCoefficientsColor`. Either way it is the shipped
    FLinearColor the author set as "what colour is this water"."""
    m = mats[name]
    v = m["resolvedVectors"][colour_param]
    s = m.get("resolvedScalars") or {}
    rec = {"kind": kind, "flat": [round(v[0], 6), round(v[1], 6), round(v[2], 6)],
           "transparent": False, "opacity": 1.0,
           "source": f"{name}.{colour_param} = FLinearColor{tuple(round(x,6) for x in v[:3])}"
                     f" ({m['blend']}, {m['shadingModel']}) from {m['asset']}"}
    if "Roughness" in s:
        rec["rough"] = round(s["Roughness"], 4)
        rec["source"] += f"; Roughness={rec['rough']}"
    # UE's SingleLayerWater does not hide what is under it: it composites
    #   result = waterColour + behindWater * ColorScaleBehindWater
    # and MI_Pal_Water_Ver2 ships ColorScaleBehindWater = 0.35. Alpha-blending
    # the same surface at opacity 1 - 0.35 gives exactly that sum, so the sea
    # bed, the shore rocks and the reef read through the sea the way the game
    # shows them instead of the plane sealing the world off. Only materials
    # that actually ship this scalar get it (the M_Pal_Water family exposes
    # `Deep`/`Ford` variants that mean something else, so those stay opaque).
    if "ColorScaleBehindWater" in s:
        csbw = s["ColorScaleBehindWater"]
        rec["transparent"] = True
        rec["opacity"] = round(1.0 - csbw, 4)
        rec["source"] += (f"; ColorScaleBehindWater={csbw} -> alpha-blended at"
                          f" opacity {rec['opacity']} = the same composite")
    return rec


def unlit_waterfall(name):
    """MSM_Unlit + BLEND_Translucent. `Color01` is the emissive tint and is
    authored HDR (its brightest channel is 2.0), which an LDR
    MeshStandardMaterial cannot express. Dividing by the vector's own brightest
    channel keeps the shipped HUE and RATIO exactly and only removes the
    over-range gain — no channel is re-balanced. `DayOpacity` is the material's
    own daytime opacity multiplier; the per-pixel alpha under it is the
    material's RGBMask curve, baked into the extracted texture's alpha channel
    by palxwater/WaterExtract.cs."""
    m = mats[name]
    c = m["resolvedVectors"]["Color01"][:3]
    mx = max(c)
    s = m["resolvedScalars"]
    return {"kind": "waterfall",
            "tint": [round(x / mx, 6) for x in c],
            "transparent": True,
            "opacity": round(s["DayOpacity"], 4),
            "source": f"{name}.Color01 = FLinearColor{tuple(round(x,6) for x in c)}"
                      f" / {mx} (own max channel, HDR->LDR); DayOpacity="
                      f"{s['DayOpacity']}; alpha = saturate((L-{s['RGBMaskMin']})/"
                      f"({s['RGBMaskMax']}-{s['RGBMaskMin']})) baked into T_Water04"
                      f" ({m['blend']}, {m['shadingModel']}) from {m['asset']}"}


materials = {
    "MI_Pal_Water_Ver2": single_layer_water("MI_Pal_Water_Ver2", "ScatteringCoefficientsColor", "ocean"),
    "MI_Water_Lake": single_layer_water("MI_Water_Lake", "Deep Scattering", "pond"),
    "MI_Water_3": single_layer_water("MI_Water_3", "Deep Scattering", "pond"),
    "MI_Water_Grean": single_layer_water("MI_Water_Grean", "Deep Scattering", "pond"),
    "MI_Water": single_layer_water("MI_Water", "Deep Scattering", "pond"),
    "MI_RIVER": single_layer_water("MI_RIVER", "Deep Scattering", "river"),
    "MI_VFX_Env_WaterFall01": unlit_waterfall("MI_VFX_Env_WaterFall01"),
    "MI_VFX_Env_WaterFall15": unlit_waterfall("MI_VFX_Env_WaterFall15"),
    "MI_VFX_Env_WaterFall": unlit_waterfall("MI_VFX_Env_WaterFall"),
    "MI_VFX_Env_WaterFall05": unlit_waterfall("MI_VFX_Env_WaterFall05"),
}

# ------------------------------------------------------------------- ocean
# The one actor in the whole world flagged bWorldOceanPlane. Its HISM root is
# the sea: 1,681 instances of the same 10 m S_WaterMesh plane, each scaled 54x
# (= 540 m) and stepped 54,000 cm apart, so the tiles abut exactly. The Z of
# every instance is identical, and that Z IS the sea level - it is read off the
# component, not fitted to anything.
oc = None
for r in persistent:
    if r["cls"] != "BP_SimpleWater_C" or not r.get("worldOceanPlane"):
        continue
    actor = r["name"]
    mat = leaf(r.get("waterMaterial")) or "MI_Pal_Water_Ver2"
    hism = next(h for h in persistent
                if h.get("mesh") == "S_WaterMesh" and h.get("instanceCount", 0) > 100
                and h["outer"]["PlainText"] == actor.rsplit("_", 1)[0])
    lx, ly, lz = hism["loc"]
    ins = hism["instances"]
    zs = {round(i[2] + lz, 3) for i in ins}
    assert len(zs) == 1, zs
    oc = {
        "actor": actor,
        "package": "Pal/Content/Pal/Maps/MainWorld_5/PL_MainWorld5.umap",
        "material": mat,
        "mesh": "water_S_WaterMesh",
        "extracted": True,
        "seaLevelZ": zs.pop(),
        "tileCount": r.get("tileCount"),
        "instances": [[round(i[0] + lx, 1), round(i[1] + ly, 1), round(i[2] + lz, 1),
                       round(i[7], 4), round(i[8], 4), round(i[9], 4)] for i in ins],
        "source": (f"PL_MainWorld5.umap :: {actor} (BP_SimpleWater_C, bWorldOceanPlane=true,"
                   f" TileCount={r.get('tileCount')}, WaterMaterial={mat}) -> its root"
                   f" HierarchicalInstancedStaticMesh at RelativeLocation {[round(v) for v in hism['loc']]}"
                   f" holding {len(ins)} PerInstanceSMData transforms of S_WaterMesh."
                   " Every number is the cooked instance transform; nothing is derived."),
    }
    break
assert oc, "no bWorldOceanPlane actor found"

xs = sorted({i[0] for i in oc["instances"]})
ys = sorted({i[1] for i in oc["instances"]})
oc["gridX"] = [xs[0], xs[-1], round(xs[1] - xs[0], 1), len(xs)]
oc["gridY"] = [ys[0], ys[-1], round(ys[1] - ys[0], 1), len(ys)]

# --------------------------------------------------- placed water in cells
# Waterfall props, pond planes and the one bend-mesh, with the material each
# placement actually overrides to (the mesh's default material is NOT what the
# level uses for the waterfalls: every placed one overrides to MI_VFX_Env_
# WaterFall01 or 15).
MESH_URL = {"SM_Waterfall04": "water_SM_Waterfall04",
            "SM_Waterfall05": "water_SM_Waterfall05",
            "S_WaterMesh": "water_S_WaterMesh",
            "SM_BendWatermesh_001": "water_SM_BendWatermesh_001"}
DEFAULT_MAT = {"SM_Waterfall04": "MI_VFX_Env_WaterFall",
               "SM_Waterfall05": "MI_VFX_Env_WaterFall05",
               "SM_BendWatermesh_001": "MI_RIVER",
               "S_WaterMesh": None}

placed = []
for r in cells:
    m = r.get("mesh")
    if m not in MESH_URL:
        continue
    mat = leaf((r.get("overrideMaterials") or [None])[0]) or DEFAULT_MAT[m]
    if mat not in materials:
        print(f"  ! unmapped material {mat} on {m}; skipped")
        continue
    rec = {"mesh": MESH_URL[m], "asset": m, "cell": r["cell"], "material": mat,
           "loc": [round(v, 1) for v in r["loc"]],
           "rot": [round(v, 4) for v in r["rot"]],
           "scale": [round(v, 4) for v in r["scale"]],
           "instances": [[round(v, 4) for v in i] for i in r.get("instances", [])]}
    placed.append(rec)

# ------------------------------------------------------------------ rivers
rivers = [{"cell": r["cell"], "mesh": "water_SM_River_Plane",
           "material": leaf(r.get("matParent")) or "MI_RIVER",
           "startPos": r["startPos"], "startTangent": r["startTangent"],
           "endPos": r["endPos"], "endTangent": r["endTangent"],
           "startScale": r["startScale"], "endScale": r["endScale"],
           "startRoll": r["startRoll"], "endRoll": r["endRoll"],
           "startOffset": r["startOffset"], "endOffset": r["endOffset"],
           "up": r["splineUpDir"], "loc": r["loc"], "rot": r["rot"], "scale": r["scale"]}
          for r in splines if r.get("mesh") == "SM_River_Plane"]

out = {
    "note": __doc__.strip().splitlines()[0],
    "materials": materials,
    "ocean": oc,
    "placed": placed,
    "rivers": rivers,
}
json.dump(out, open(f"{SP}/water_index.json", "w"), indent=1)
print(f"water_index.json: ocean {len(oc['instances'])} tiles @ Z={oc['seaLevelZ']} "
      f"({oc['gridX'][3]}x{oc['gridY'][3]}, step {oc['gridX'][2]} cm), "
      f"{len(placed)} placed water components, {len(rivers)} river spline segments, "
      f"{len(materials)} materials")
for k, v in materials.items():
    print(f"  {k:24s} {v['kind']:9s} "
          f"{'tint' if 'tint' in v else 'flat'}="
          f"{v.get('tint') or v.get('flat')} op={v['opacity']} "
          f"transparent={v['transparent']} rough={v.get('rough')}")
