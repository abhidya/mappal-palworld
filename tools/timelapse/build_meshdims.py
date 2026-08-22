"""Close MapPal's magenta-box gap with MEASURED dimensions.

INPUT
  bpbbox.json   produced by palxbb: for each buildable Blueprint, every mesh
                component, the referenced mesh's LOD0 vertex extents, the
                component's own RelativeLocation/Rotation/Scale3D, and the AABB
                each component occupies in blueprint-local space.
  mesh_manifest.json  typeId -> its blueprint, and the mesh path(s) that
                blueprint references.

WHAT GETS WRITTEN
  mappal/src/data/objects.json    size filled in for types that had null
                                  dimensions (the magenta ones), AND promoted
                                  over the previous estimate for the types whose
                                  manifest primary resolved to a Blueprint - see
                                  PROMOTION below. Every other type's existing
                                  size is left exactly as it was.
  c4all_report.json               rows appended for meshes measured here that
                                  the report did not already carry.
  mappal/src/data/meshRegistry.json   entries added only for types whose real
                                  mesh has an extracted GLB that exists on disk.
  mesh_manifest_bpfix.json        NEW: for each type whose manifest primary
                                  meshPath resolves to a Blueprint instead of a
                                  mesh, the mesh that blueprint's own component
                                  actually points at.
  meshdims_unresolved.json        NEW: everything still unmeasured, with why.

PROMOTION
  The 20 "resolves to a Blueprint" types were never magenta - they carried a
  "rough estimate" / "works bounds" guess. Those boxes feed the avatar's
  standing-height rule, and several of the guesses are badly wrong:
  Stool01_Stone 100x100x100 vs measured 39x39x54, TrafficCone02_Iron
  150x150x150 vs 105x105x129, AncientElectricGenerator 300x300x95 vs
  260x150x366. A 2.5x-too-tall box floats a character in mid-air above a stool,
  so the measurement replaces the guess. The previous value is preserved in
  `measured.existingSize` / `measured.existingSizeSource` and re-running never
  launders a measurement into that slot, so the change is auditable and
  reversible (plus objects.json.bak-prepromote).

AXIS CONVENTION  (the easy thing to get wrong)
  objects.json's size is [length, thickness, height], and per src/scene/
  coords.ts size[0] is placed along the object's LOCAL Y and size[1] along its
  LOCAL X - derived and numerically verified there against the calibration
  fixtures, and implemented in src/scene/proxyGeometry.ts (three-local
  X = size[1], three-local Z = size[0]). A blueprint-local AABB is (X, Y, Z), so

      size = [ extentY, extentX, extentZ ]

  The script re-checks this against every wall-kit blueprint it measured: a
  wall's long side must land in size[0], or it refuses to write anything.

WHAT IS EXCLUDED FROM THE UNION, AND WHY
  Some blueprints carry mesh components that are not the object's geometry:
  engine BasicShapes primitives used as gameplay volumes (BP_BuildObject_PalBoxV2
  has two `Cylinder`s scaled to 7001 x 7001 x 10001 cm - that is the camp's
  area_range, twice its 3500 cm radius, not the palbox), the UE third-person
  template's StopBox collision cube, and the PalSphereLight effect. Including
  them produces a box a hundred times too big, which is exactly the kind of
  fabricated number that puts an avatar in orbit. They are excluded BY ASSET
  PATH (objective, not by name or by size), listed per type in the output, and
  a type left with no components after the exclusion stays unresolved rather
  than being given the primitive's box.

  Cube_LowHeight is NOT excluded: in BP_BuildObject_DisplayCharacter it is the
  display cage's four visible walls, i.e. real geometry.

NOTHING IS INVENTED
  A type is written only if a real mesh component with real vertices measured.
  Anything else stays null - and so stays magenta - and is listed in
  meshdims_unresolved.json with the reason.
"""
import json, os, shutil, datetime

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
OBJECTS = f"{SP}/mappal/src/data/objects.json"
REPORT = f"{SP}/c4all_report.json"
REGISTRY = f"{SP}/mappal/src/data/meshRegistry.json"

# Excluded by asset path - gameplay volumes / template collision / effects.
PRIMITIVE_PATHS = (
    "Engine/Content/BasicShapes/",                                    # area-range cylinders, build plates
    "Pal/Content/Others/ThirdPerson/Meshes/StopBox_StaticMesh",       # UE template collision cube
    "Pal/Content/Pal/Model/Other/PalSphereLight/PalSphereLight",      # sphere-light effect
)
# The arrow component is a placement helper with no geometry at all; it is what
# made 20 manifest entries "resolve" to a blueprint in the first place.
ARROW = "BP_BuildObjectSimulateArrowComponent"


def is_primitive(c):
    p = c.get("meshPath") or ""
    return any(x in p for x in PRIMITIVE_PATHS)


def leaf(path):
    return (path or "").rsplit("/", 1)[-1]


def union(comps):
    mn = [min(c["world_min_cm"][i] for c in comps) for i in range(3)]
    mx = [max(c["world_max_cm"][i] for c in comps) for i in range(3)]
    return mn, mx


def main():
    bb = json.load(open(os.environ.get("BPBBOX", f"{SP}/bpbbox.json")))
    dry = os.environ.get("DRYRUN") == "1"
    man = json.load(open(f"{SP}/mesh_manifest.json"))
    objects = json.load(open(OBJECTS))
    types = objects["types"]
    report = json.load(open(REPORT))
    have_rows = {e["name"] for e in report}
    registry = json.load(open(REGISTRY))
    glbs = {f[:-4] for f in os.listdir(f"{SP}/mappal/public/meshes") if f.endswith(".glb")}

    nulls = [t for t, v in types.items() if any(x is None for x in v["size"])]
    bp_primary = [t for t, v in man.items() if "/Blueprint/" in (v.get("meshPath") or "")]

    def candidates(t):
        """Blueprints that could describe this type, best first.

        1. the type's own blueprint;
        2. any blueprint the manifest already records this type as referencing -
           that is exactly the "20 resolve to a Blueprint" case: a shared base
           class, or the launcher/factory child it carries. Both come out of the
           manifest, so this is data, not a guess. The placement arrow component
           is skipped; it has no geometry at all.
        """
        v = man.get(t, {})
        out = [leaf(v.get("blueprint")) or f"BP_BuildObject_{t}"]
        for p in [v.get("meshPath")] + (v.get("meshPaths") or []):
            if p and "/Blueprint/" in p:
                n = leaf(p)
                if n != ARROW and n not in out:
                    out.append(n)
        return out

    filled, promoted, unresolved, bpfix, new_rows, wall_check = {}, {}, {}, {}, [], []
    measured_meshes = {}

    for t in sorted(types):
        tried, chosen = [], None
        for bp in candidates(t):
            rec = bb.get(bp)
            if rec is None:
                tried.append((bp, "not measured in this run"))
                continue
            comps = [c for c in (rec.get("comps") or []) if c.get("world_min_cm")]
            kept = [c for c in comps if not is_primitive(c)]
            vis = [c for c in kept if c["visible"]] or kept
            if not vis:
                tried.append((bp, "no mesh components" if not comps else
                              "only engine primitives / gameplay volumes: "
                              + ", ".join(sorted({c["mesh"] for c in comps}))))
                continue
            chosen = (bp, rec, comps, vis)
            break

        if not chosen:
            if t in nulls or t in bp_primary:
                unresolved[t] = {"blueprint": candidates(t)[0],
                                 "triedBlueprints": [{"bp": b, "why": w} for b, w in tried],
                                 "reason": tried[0][1] if tried else "no candidate blueprint"}
            continue

        bp, rec, comps, vis = chosen
        mn, mx = union(vis)
        obj_size = [round(mx[1] - mn[1], 2), round(mx[0] - mn[0], 2), round(mx[2] - mn[2], 2)]
        dropped = sorted({c["mesh"] for c in comps if is_primitive(c)})
        chain = candidates(t)
        record = {
            "blueprint": bp,
            "viaBlueprintChain": chain[:chain.index(bp) + 1],
            "size": obj_size,
            "min_cm": [round(v, 2) for v in mn],
            "max_cm": [round(v, 2) for v in mx],
            "componentsUsed": [{"export": c["export"], "mesh": c["mesh"],
                                "meshPath": c["meshPath"], "kind": c["kind"],
                                "verts": c["verts"], "scale": c["scale"],
                                "loc_cm": c["loc_cm"], "rot_pyr": c["rot_pyr"]} for c in vis],
            "componentsExcludedAsPrimitives": dropped,
            "unmeasuredComponents": rec.get("unmeasured", 0),
        }
        entry = types[t]

        was_null = any(x is None for x in entry["size"])
        already = entry["sizeSource"].startswith("MEASURED")
        # PROMOTE: the blueprint-primary types were never magenta - they carried
        # a "rough estimate" / "works bounds" guess. Those guesses feed the
        # avatar's standing-height rule, and several are badly wrong
        # (Stool01_Stone guessed 100x100x100, measured 39x39x54 - a 2.5x-too-tall
        # box floats a character above a stool), so a measurement replaces them.
        promote = t in bp_primary and not already

        if was_null or promote:
            # Keep whatever pre-measurement value was recorded the FIRST time, so
            # re-running never launders a measurement into the "existing" slot
            # and the change stays auditable and reversible.
            prev = entry.get("measured") or {}
            if "existingSize" in prev:
                record["existingSize"] = prev["existingSize"]
                record["existingSizeSource"] = prev.get("existingSizeSource")
            elif not already:
                record["existingSize"] = entry["size"]
                record["existingSizeSource"] = entry["sizeSource"]
            entry["size"] = obj_size
            entry["sizeSource"] = (
                f"MEASURED from the pak: union AABB of {bp}'s {len(vis)} mesh "
                f"component(s) ({', '.join(sorted({c['mesh'] for c in vis}))}), each "
                f"component's LOD0 vertex extents pushed through its own "
                f"RelativeScale3D/Rotation/Location (palxbb)"
                + (f"; excluded as gameplay volumes/primitives: {', '.join(dropped)}"
                   if dropped else "")
                + ". Order is [local-Y, local-X, local-Z] per coords.ts."
                + (f" Replaces the previous estimate {record['existingSize']} "
                   f"({(record.get('existingSizeSource') or '')[:60]})."
                   if promote and "existingSize" in record else ""))
            entry["measured"] = record
            # The proxy stands on the object's own Z. Publish the AABB's true Z
            # range rather than baking an offset into `size`: Altar starts 41 cm
            # below its origin, Expedition 137 cm, FishingPond2 168 cm, and a
            # standing-height rule that used size[2] would bury a builder.
            entry["measuredBottomCm"] = round(mn[2], 2)
            entry["measuredTopCm"] = round(mx[2], 2)
            (filled if was_null else promoted)[t] = record
        elif not already:
            record["existingSize"] = entry["size"]
            record["existingSizeSource"] = entry["sizeSource"]
        if t in bp_primary:
            bpfix.setdefault(t, {})["measured"] = record

        if "wall" in t.lower() and "triangle" not in t.lower():
            wall_check.append((t, obj_size))

        if t in bp_primary:
            pick = max(vis, key=lambda c: c["verts"])
            bpfix.setdefault(t, {}).update({
                "manifestPrimary": man[t]["meshPath"],
                "manifestPrimaryIsBlueprint": True,
                "resolvedViaBlueprint": bp,
                "resolvedMesh": pick["mesh"],
                "resolvedMeshPath": pick["meshPath"],
                "resolvedKind": pick["kind"],
                "allComponentMeshes": sorted({c["mesh"] for c in vis}),
                "glbAvailable": pick["mesh"] in glbs,
            })

        for c in vis:
            measured_meshes.setdefault(c["mesh"], c)

    for m, c in sorted(measured_meshes.items()):
        if m in have_rows:
            continue
        have_rows.add(m)
        new_rows.append({
            "name": m, "meshPath": c["meshPath"], "kind": c["kind"],
            "outDir": None, "vpath": None, "ok": True, "err": None,
            "verts": c["verts"], "tris": None, "nanite": None, "lods": None,
            "glb": f"meshes/{m}.glb" if m in glbs else None,
            "bbox_cm": [round(c["mesh_max_cm"][i] - c["mesh_min_cm"][i], 4) for i in range(3)],
            "min_cm": [round(v, 4) for v in c["mesh_min_cm"]],
            "max_cm": [round(v, 4) for v in c["mesh_max_cm"]],
            "source": "palxbb blueprint-component walk (build_meshdims.py); bbox is "
                      "the mesh's own LOD0 vertex extents, unscaled",
        })

    # --- axis sanity check, measured, not assumed ---
    bad = [w for w in wall_check if w[1][0] < w[1][1]]
    print(f"axis check: {len(wall_check)} wall-kit blueprints measured; long side "
          f"landed in size[0] for {len(wall_check) - len(bad)}")
    for t, s in wall_check:
        print(f"    {t:34s} -> {s}")
    if bad:
        raise SystemExit(f"AXIS CHECK FAILED for {bad} - refusing to write boxes "
                         f"whose length/thickness may be swapped")

    for t in nulls:
        if any(x is None for x in types[t]["size"]):
            unresolved.setdefault(t, {"reason": "blueprint not measured in this run"})
        else:
            unresolved.pop(t, None)

    reg_added = {}
    for t, v in bpfix.items():
        m = v.get("resolvedMesh")
        if m and v.get("glbAvailable") and t not in registry:
            registry[t] = {"mesh": m, "url": f"/meshes/{m}.glb"}
            reg_added[t] = m

    if not dry:
        for f in (OBJECTS, REPORT, REGISTRY):
            if not os.path.exists(f + ".bak-premeshdims"):
                shutil.copy2(f, f + ".bak-premeshdims")
        # .bak-premeshdims is the true pre-anything baseline and is never
        # rewritten; this second snapshot makes THIS pass individually
        # reversible without losing the first one.
        if promoted and not os.path.exists(OBJECTS + ".bak-prepromote"):
            shutil.copy2(OBJECTS, OBJECTS + ".bak-prepromote")
        if reg_added and not os.path.exists(REGISTRY + ".bak-preadopt"):
            shutil.copy2(REGISTRY, REGISTRY + ".bak-preadopt")
        objects["_measuredDims"] = (
            "Types whose sizeSource starts with 'MEASURED from the pak' carry a "
            "`measured` block: the blueprint, the mesh components used, any "
            "components excluded as gameplay volumes, and the union AABB. size is "
            "[local-Y, local-X, local-Z] cm (coords.ts). measuredBottomCm / "
            "measuredTopCm are that AABB's Z range relative to the object's own "
            "origin - use measuredTopCm, not size[2], for a standing-height rule "
            "on a blueprint whose geometry does not start at Z=0.")
        open(OBJECTS, "w").write(json.dumps(objects, indent=2, ensure_ascii=False))
        report.extend(new_rows)
        # keep the report's original indent so the diff is the appended rows only
        open(REPORT, "w").write(json.dumps(report, indent=2))
        if reg_added:
            open(REGISTRY, "w").write(json.dumps(dict(sorted(registry.items())), indent=1) + "\n")
        json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "note": ("Corrections for mesh_manifest.json entries whose primary "
                            "meshPath resolves to a Blueprint (the placement arrow "
                            "component, or a shared base class) instead of a mesh. "
                            "resolvedMesh is the mesh that blueprint's own mesh "
                            "component actually references. Written as a separate file "
                            "because mesh_manifest.json is gen_registry.py's input and "
                            "is regenerated elsewhere. meshRegistry.json can only adopt "
                            "a resolvedMesh once a GLB exists for it - glbAvailable "
                            "says whether one does."),
                   "types": bpfix},
                  open(f"{SP}/mesh_manifest_bpfix.json", "w"), indent=1)
        json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "note": ("Types still without measured dimensions. They stay magenta "
                            "on purpose: a wrong box feeds the avatar's standing-height "
                            "rule and would put a character floating or buried, which is "
                            "worse than a visible gap."),
                   "types": unresolved},
                  open(f"{SP}/meshdims_unresolved.json", "w"), indent=1)
    else:
        report.extend(new_rows)
        print("\nDRYRUN: nothing written")

    still = [t for t in nulls if any(x is None for x in types[t]["size"])]
    print(f"\nobjects.json      magenta types before={len(nulls)}  filled={len(filled)}  "
          f"still magenta={len(still)}  promoted-over-estimate={len(promoted)}")
    print(f"c4all_report.json rows {len(report) - len(new_rows)} -> {len(report)}  "
          f"(+{len(new_rows)} meshes)")
    print(f"meshRegistry.json entries added: {len(reg_added)} {reg_added}")
    print(f"mesh_manifest_bpfix.json  {len(bpfix)} types; blueprint-primary resolved "
          f"{sum(1 for v in bpfix.values() if v.get('resolvedMesh'))}/{len(bp_primary)}, "
          f"GLB already extracted for "
          f"{sum(1 for v in bpfix.values() if v.get('glbAvailable'))}")
    print(f"meshdims_unresolved.json  {len(unresolved)} types")
    for t, v in sorted(unresolved.items()):
        print(f"    {t:26s} {v['reason']}")
    if promoted:
        print("\npromoted (measurement replaces a previous estimate):")
        for t, r in sorted(promoted.items()):
            old = r.get("existingSize")
            print(f"    {t:30s} {str(old):28s} -> {str(r['size']):28s} "
                  f"bottom={types[t]['measuredBottomCm']:>7} top={types[t]['measuredTopCm']:>7}"
                  f"  via {r['blueprint']}")
    print("\nfilled:")
    for t, r in sorted(filled.items()):
        print(f"    {t:38s} {str(r['size']):32s} bottom={types[t]['measuredBottomCm']:>8} "
              f"top={types[t]['measuredTopCm']:>8}  via {r['blueprint']}"
              + (f"  [dropped {','.join(r['componentsExcludedAsPrimitives'])}]"
                 if r["componentsExcludedAsPrimitives"] else ""))


if __name__ == "__main__":
    main()
