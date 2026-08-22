// World Partition streaming-cell reader.
//
// Cooked Palworld ships each World Partition cell as its own .umap under
// PL_MainWorld5/_Generated_/<Grid>_L<lod>_X<x>_Y<y>_DL<datalayer>.umap, with the
// cell's actors BAKED IN (there is no __ExternalActors__ directory in the pak —
// cooking folds them into the cell package). So every actor's real authored
// transform is recoverable straight from the package exports.
//
// Mode 1 (--survey): print the export class histogram of one or more cells.
// Mode 2 (--level):  dump every placed StaticMesh / foliage instance transform
//                    as JSON.
using System.Text.Json;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Objects;
using CUE4Parse.UE4.Objects.Core.Math;
using CUE4Parse.UE4.Objects.UObject;
using CUE4Parse.UE4.Versions;
using CUE4Parse.UE4.Assets;
using CUE4Parse.UE4.Assets.Exports.Component.StaticMesh;

namespace Palx;

public static class Level
{
    static string OutDir => Environment.GetEnvironmentVariable("PALX_OUT")
        ?? Program.BaseDir;

    public static DefaultFileProvider MakeProvider(string root)
    {
        var provider = new DefaultFileProvider(new DirectoryInfo(root), SearchOption.AllDirectories,
            new VersionContainer(EGame.GAME_UE5_1), StringComparer.OrdinalIgnoreCase);
        provider.Initialize();
        provider.Mount();   // unencrypted pak: required, else Files is empty
        provider.MappingsContainer = new FileUsmapTypeMappingsProvider(
            Program.UsmapPath);
        provider.ReadNaniteData = true;
        // Palworld subclasses UHierarchicalInstancedStaticMeshComponent for its
        // foliage. Without this the export falls back to plain UObject and the
        // PerInstanceSMData bulk array (which is serialized, not a UProperty) is
        // never read — every foliage component comes back with 0 instances.
        foreach (var n in new[] { "PalFoliageISMComponent", "PalFoliageISMComponentBase",
                                  "PalHierarchicalInstancedStaticMeshComponent" })
            ObjectTypeRegistry.RegisterClass(n, typeof(UHierarchicalInstancedStaticMeshComponent));
        return provider;
    }

    public static int Run(string[] args)
    {
        var mode = args[0];
        var provider = MakeProvider(Environment.GetEnvironmentVariable("PALX_ROOT")
            ?? Path.Combine(Program.BaseDir, "rawassets"));
        Console.Error.WriteLine($"provider files: {provider.Files.Count}");

        var wanted = args.Skip(1).ToArray();
        var vpaths = new List<string>();
        foreach (var k in provider.Files.Keys)
        {
            if (!k.EndsWith(".umap", StringComparison.OrdinalIgnoreCase)) continue;
            var leaf = k[(k.LastIndexOf('/') + 1)..];
            if (wanted.Length == 0 || wanted.Any(w => leaf.Contains(w, StringComparison.OrdinalIgnoreCase)))
                vpaths.Add(k);
        }
        vpaths.Sort();
        Console.Error.WriteLine($"matched {vpaths.Count} umaps");

        if (mode == "--charxform")
        {
            // For every character blueprint, emit the SkeletalMeshComponent's own
            // RelativeLocation/Rotation/Scale3D (plus the collision capsule's half
            // height, which is what that offset is derived from in the first place).
            // This is the character equivalent of meshXform.json: a save records the
            // ACTOR transform, and the mesh hangs off it by this amount.
            var assets = provider.Files.Keys
                .Where(k => k.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)
                            && args.Skip(1).Any(w => k.Contains(w, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(k => k).ToList();
            Console.Error.WriteLine($"matched {assets.Count} blueprint assets");
            var outx = new Dictionary<string, object>();
            int hits = 0;
            foreach (var vp in assets)
            {
                try
                {
                    var pkg = provider.LoadPackage(vp);
                    float? capsule = null;
                    object rec = null;
                    foreach (var ex in pkg.GetExports())
                    {
                        var cls = ex.ExportType ?? "";
                        if (cls.Contains("Capsule", StringComparison.OrdinalIgnoreCase)
                            && ex.Properties.Any(pr => pr.Name.Text == "CapsuleHalfHeight"))
                            capsule ??= ex.GetOrDefault<float>("CapsuleHalfHeight");
                        if (!cls.Contains("SkeletalMeshComponent", StringComparison.OrdinalIgnoreCase)) continue;
                        if (!ex.Name.Contains("CharacterMesh", StringComparison.OrdinalIgnoreCase)) continue;
                        var loc = ex.GetOrDefault("RelativeLocation", FVector.ZeroVector);
                        var rot = ex.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
                        var scl = ex.GetOrDefault("RelativeScale3D", FVector.OneVector);
                        var skm = ex.GetOrDefault<FPackageIndex>("SkeletalMesh", null);
                        rec = new {
                            loc = new[] { loc.X, loc.Y, loc.Z },
                            rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                            scale = new[] { scl.X, scl.Y, scl.Z },
                            mesh = skm?.Name,
                        };
                    }
                    if (rec != null)
                    {
                        var name = vp[(vp.LastIndexOf('/') + 1)..^".uasset".Length];
                        outx[name] = new { xform = rec, capsuleHalfHeight = capsule };
                        hits++;
                    }
                }
                catch { }
            }
            File.WriteAllText(Path.Combine(Program.BaseDir, "charxform_raw.json"),
                JsonSerializer.Serialize(outx, new JsonSerializerOptions { WriteIndented = false }));
            Console.Error.WriteLine($"blueprints with a CharacterMesh component: {hits} -> charxform_raw.json");
            return 0;
        }

        if (mode == "--assetprops")
        {
            // Dump every export's properties for arbitrary assets (used to read
            // the SkeletalMeshComponent's own RelativeLocation/Rotation/Scale3D
            // out of a Pal / player character blueprint, rather than eyeballing
            // an offset).
            var assets = provider.Files.Keys
                .Where(k => k.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)
                            && args.Skip(1).Any(w => k.Contains(w, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(k => k).ToList();
            Console.Error.WriteLine($"matched {assets.Count} assets");
            foreach (var vp in assets)
            {
                try
                {
                    var pkg = provider.LoadPackage(vp);
                    Console.WriteLine($"\n### {vp}");
                    foreach (var ex in pkg.GetExports())
                    {
                        var interesting = ex.Properties.Where(pr =>
                            pr.Name.Text is "RelativeLocation" or "RelativeRotation"
                            or "RelativeScale3D" or "SkeletalMesh" or "CapsuleHalfHeight"
                            or "MeshComponentRelativeTransform").ToList();
                        if (interesting.Count == 0) continue;
                        Console.WriteLine($"  [{ex.ExportType}] {ex.Name}");
                        foreach (var pr in interesting)
                            Console.WriteLine($"      {pr.Name.Text} = {pr.Tag?.GenericValue}");
                    }
                }
                catch (Exception ex) { Console.WriteLine($"FAIL {vp}: {ex.Message}"); }
            }
            return 0;
        }

        if (mode == "--datatable")
        {
            // Dump UDataTable rows as JSON. Used to resolve the equipment/skin
            // ITEM ids the player save records (e.g. "CopperArmorCold") to the
            // actual SK_Player_*_Outfit_* mesh the game uses for them, rather
            // than guessing a mapping from the names.
            var tables = provider.Files.Keys
                .Where(k => k.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)
                            && args.Skip(1).Any(w => k.Contains(w, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(k => k).ToList();
            Console.Error.WriteLine($"matched {tables.Count} assets");
            var dump = new Dictionary<string, object>();
            foreach (var vp in tables)
            {
                try
                {
                    var pkg = provider.LoadPackage(vp);
                    foreach (var ex in pkg.GetExports())
                    {
                        if (ex is not CUE4Parse.UE4.Assets.Exports.Engine.UDataTable dt) continue;
                        var rows = new Dictionary<string, Dictionary<string, string>>();
                        foreach (var kv in dt.RowMap)
                        {
                            var cols = new Dictionary<string, string>();
                            foreach (var prop in kv.Value.Properties)
                            {
                                var g = prop.Tag?.GenericValue;
                                if (g is CUE4Parse.UE4.Assets.Objects.UScriptMap map)
                                {
                                    // e.g. SkeletalMeshMap is keyed by gender enum —
                                    // flatten so the real per-gender mesh path is visible.
                                    var parts = new List<string>();
                                    foreach (var e2 in map.Properties)
                                        parts.Add($"{e2.Key?.GenericValue}={e2.Value?.GenericValue}");
                                    cols[prop.Name.Text] = string.Join(" | ", parts);
                                }
                                else cols[prop.Name.Text] = g?.ToString() ?? "";
                            }
                            rows[kv.Key.Text] = cols;
                        }
                        dump[vp[(vp.LastIndexOf('/') + 1)..]] = rows;
                        Console.WriteLine($"{vp[(vp.LastIndexOf('/') + 1)..]}: {rows.Count} rows");
                    }
                }
                catch (Exception ex) { Console.WriteLine($"FAIL {vp}: {ex.Message}"); }
            }
            File.WriteAllText(Path.Combine(Program.BaseDir, "datatables.json"),
                JsonSerializer.Serialize(dump, new JsonSerializerOptions { WriteIndented = false }));
            return 0;
        }

        if (mode == "--landscape")
        {
            // Real terrain: every World Partition cell that covers land carries an
            // ALandscapeStreamingProxy whose ULandscapeComponents hold the authored
            // heightmap. CUE4Parse rebuilds the exact editor heightfield mesh from
            // them (LandscapeMeshDto), so this is the game's own terrain geometry,
            // not a reconstruction.
            var recs = new List<object>();
            foreach (var vp in vpaths)
            {
                var pkg = provider.LoadPackage(vp);
                var cell = vp[(vp.LastIndexOf('/') + 1)..];
                foreach (var e in pkg.GetExports())
                {
                    if (e is not CUE4Parse.UE4.Assets.Exports.Actor.ALandscapeProxy proxy) continue;
                    var rootIdx = proxy.GetOrDefault<FPackageIndex>("RootComponent", null);
                    var root = rootIdx?.ResolvedObject?.Load();
                    var loc = root?.GetOrDefault("RelativeLocation", FVector.ZeroVector) ?? FVector.ZeroVector;
                    var scl = root?.GetOrDefault("RelativeScale3D", FVector.OneVector) ?? FVector.OneVector;
                    var rot = root?.GetOrDefault("RelativeRotation", FRotator.ZeroRotator) ?? FRotator.ZeroRotator;
                    try
                    {
                        var dto = new CUE4Parse_Conversion.Dto.LandscapeMeshDto(proxy,
                            CUE4Parse_Conversion.Options.ELandscapeFlags.Mesh);
                        // LAND_LOD picks the heightfield's OWN LOD. LOD0 of this
                        // landscape is 1 quad per metre, so a 600 m disc of it is
                        // ~2.3 M triangles - more than the whole rest of a base
                        // scene. A coarser LOD is the game's own decimation of the
                        // same surface, not an invented simplification.
                        var want = int.TryParse(Environment.GetEnvironmentVariable("LAND_LOD"), out var wl) ? wl : 0;
                        var li = Math.Min(want, dto.LODs.Count - 1);
                        var lod = dto.LODs[li];
                        Console.Error.WriteLine($"   lods={dto.LODs.Count} using={li}");
                        var pos = new float[lod.Vertices.Length * 3];
                        for (int i = 0; i < lod.Vertices.Length; i++)
                        {
                            var v = lod.Vertices[i].Position;
                            pos[i * 3] = v.X; pos[i * 3 + 1] = v.Y; pos[i * 3 + 2] = v.Z;
                        }
                        var outDir = Path.Combine(OutDir, "terrain_meshes");
                        Directory.CreateDirectory(outDir);
                        var nm = $"{cell[..cell.LastIndexOf('.')]}__{proxy.Name}";
                        // LAND_NOGLB=1: transforms/extents only. FarMountain_L0 holds
                        // 939 proxies; writing every GLB just to find out WHERE they
                        // are is minutes of disk for a question answered by the index.
                        if (Environment.GetEnvironmentVariable("LAND_NOGLB") != "1")
                            Program.WriteGlbPublic(Path.Combine(outDir, nm + ".glb"), pos, lod.Indices, nm);
                        float mnx=float.MaxValue,mny=float.MaxValue,mnz=float.MaxValue,mxx=float.MinValue,mxy=float.MinValue,mxz=float.MinValue;
                        for (int i = 0; i < pos.Length; i += 3) {
                            if (pos[i]<mnx) mnx=pos[i]; if (pos[i]>mxx) mxx=pos[i];
                            if (pos[i+1]<mny) mny=pos[i+1]; if (pos[i+1]>mxy) mxy=pos[i+1];
                            if (pos[i+2]<mnz) mnz=pos[i+2]; if (pos[i+2]>mxz) mxz=pos[i+2];
                        }
                        recs.Add(new { cell, actor = proxy.Name, glb = "terrain_meshes/" + nm + ".glb",
                            verts = lod.Vertices.Length, tris = lod.Indices.Length / 3,
                            vmin = new[]{mnx,mny,mnz}, vmax = new[]{mxx,mxy,mxz},
                            loc = new[] { loc.X, loc.Y, loc.Z }, scale = new[] { scl.X, scl.Y, scl.Z },
                            rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                            componentSizeQuads = proxy.ComponentSizeQuads,
                            components = proxy.LandscapeComponents.Length });
                        Console.WriteLine($"OK  {nm}  {lod.Vertices.Length} v  loc={loc}  scale={scl}  rot={rot}");
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"FAIL {cell} {proxy.Name}: {ex.GetType().Name}: {ex.Message}");
                    }
                }
            }
            File.WriteAllText(Path.Combine(OutDir, "terrain_index.json"),
                JsonSerializer.Serialize(recs, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }

        if (mode == "--dump")
        {
            // Copy the raw cooked bytes of every file whose virtual path matches one
            // of the patterns into rawassets/, so later passes can run off loose
            // files without holding the 40 GB pak open (it is contended).
            var outRoot = Environment.GetEnvironmentVariable("PALX_DUMP")
                ?? Path.Combine(Program.BaseDir, "rawassets");
            var pats = args.Skip(1).ToArray();
            long tot = 0; int n = 0, fail = 0;
            foreach (var k in provider.Files.Keys.ToList())
            {
                if (!pats.Any(w => k.Contains(w, StringComparison.OrdinalIgnoreCase))) continue;
                var dst = Path.Combine(outRoot, k.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(dst)) { n++; continue; }
                try
                {
                    var bytes = provider.SaveAsset(k);
                    Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
                    File.WriteAllBytes(dst, bytes);
                    tot += bytes.Length; n++;
                }
                catch (Exception ex) { fail++; Console.Error.WriteLine($"  SKIP {k}: {ex.Message}"); }
            }
            Console.Error.WriteLine($"dumped {n} files ({tot:N0} bytes), {fail} failed -> {outRoot}");
            return 0;
        }

        if (mode == "--ls")
        {
            foreach (var vp in vpaths) Console.WriteLine(vp);
            return 0;
        }

        if (mode == "--allexp")
        {
            // EVERY export of the matched cells, with no class filter at all.
            // The --level dump only keeps *StaticMeshComponent* / *ISMComponent* /
            // SceneComponent / *Landscape*, so anything else that carries geometry
            // (SplineMeshComponent, a Blueprint actor whose meshes live in its own
            // class package, ...) is invisible in cellactors.json. This mode is the
            // ground truth to compare it against.
            var recs = new List<object>();
            foreach (var vp in vpaths)
            {
                var pkg = provider.LoadPackage(vp);
                var cell = vp[(vp.LastIndexOf('/') + 1)..];
                foreach (var e in pkg.GetExports())
                {
                    var loc = e.GetOrDefault("RelativeLocation", FVector.ZeroVector);
                    var rot = e.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
                    var scl = e.GetOrDefault("RelativeScale3D", FVector.OneVector);
                    var meshRef = e.GetOrDefault<FPackageIndex>("StaticMesh", null);
                    var rootRef = e.GetOrDefault<FPackageIndex>("RootComponent", null);
                    // the actor's own class: for a BP instance the export's class is
                    // the generated class, reachable through the export's template.
                    string ovr = null;
                    var om = e.GetOrDefault<FPackageIndex[]>("OverrideMaterials", null);
                    if (om != null) ovr = string.Join(",", om.Select(x => x?.Name ?? "null"));
                    recs.Add(new
                    {
                        cell,
                        cls = e.ExportType,
                        name = e.Name,
                        outer = e.Outer?.Name,
                        mesh = meshRef?.Name,
                        meshPath = meshRef?.ResolvedObject?.GetPathName(),
                        root = rootRef?.Name,
                        ovr,
                        loc = new[] { loc.X, loc.Y, loc.Z },
                        rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                        scale = new[] { scl.X, scl.Y, scl.Z },
                        props = e.Properties.Select(p => p.Name.Text).ToArray(),
                    });
                }
                Console.Error.WriteLine($"{cell}: {pkg.GetExports().Count()} exports");
            }
            var op = Path.Combine(OutDir, Environment.GetEnvironmentVariable("ALLEXP_OUT") ?? "allexp.json");
            File.WriteAllText(op, JsonSerializer.Serialize(recs,
                new JsonSerializerOptions { WriteIndented = false }));
            Console.Error.WriteLine($"wrote {recs.Count} exports -> {op}");
            return 0;
        }

        if (mode == "--survey")
        {
            foreach (var vp in vpaths)
            {
                var pkg = provider.LoadPackage(vp);
                var hist = new SortedDictionary<string, int>();
                foreach (var e in pkg.GetExports())
                {
                    var c = e.ExportType ?? e.GetType().Name;
                    hist[c] = hist.GetValueOrDefault(c) + 1;
                }
                Console.WriteLine($"\n### {vp[(vp.LastIndexOf('/') + 1)..]}  exports={pkg.GetExports().Count()}");
                foreach (var kv in hist.OrderByDescending(k => k.Value))
                    Console.WriteLine($"   {kv.Value,6}  {kv.Key}");
            }
            return 0;
        }

        var outActors = new List<object>();
        foreach (var vp in vpaths)
        {
            var pkg = provider.LoadPackage(vp);
            var cell = vp[(vp.LastIndexOf('/') + 1)..];
            foreach (var e in pkg.GetExports())
            {
                var cls = e.ExportType ?? "";
                // --- plain placed static meshes -------------------------------
                if (cls.Contains("StaticMeshComponent", StringComparison.OrdinalIgnoreCase)
                    || cls.Contains("ISMComponent", StringComparison.OrdinalIgnoreCase))
                {
                    var meshRef = e.GetOrDefault<FPackageIndex>("StaticMesh", null);
                    var meshName = meshRef?.Name ?? meshRef?.ResolvedObject?.Name.Text ?? null;
                    var mp = meshRef?.ResolvedObject?.GetPathName();
                    var loc = e.GetOrDefault("RelativeLocation", FVector.ZeroVector);
                    var rot = e.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
                    var scl = e.GetOrDefault("RelativeScale3D", FVector.OneVector);

                    // Instanced (foliage / grouped props): PerInstanceSMData holds
                    // every instance's own 4x4 transform, relative to the component.
                    var insts = new List<float[]>();
                    if (e is UInstancedStaticMeshComponent ism && ism.PerInstanceSMData != null)
                    {
                        foreach (var pi in ism.PerInstanceSMData)
                        {
                            var t = pi.TransformData;
                            insts.Add(new[]{ (float)t.Translation.X, (float)t.Translation.Y, (float)t.Translation.Z,
                                             (float)t.Rotation.X, (float)t.Rotation.Y, (float)t.Rotation.Z, (float)t.Rotation.W,
                                             (float)t.Scale3D.X, (float)t.Scale3D.Y, (float)t.Scale3D.Z });
                        }
                    }
                    // OverrideMaterials is a COMPONENT-level property, so the mesh's
                    // own material list does not mention it. Palworld uses it both for
                    // water (the waterfalls) and to turn an /Engine/BasicShapes/Cube
                    // into a LOCAL FOG VOLUME - geometry that must never be drawn as
                    // an opaque surface. Recording it here is what lets the terrain
                    // build tell those apart from real ground.
                    var om = e.GetOrDefault<FPackageIndex[]>("OverrideMaterials", null);
                    var ovr = om == null ? null
                        : string.Join(",", om.Select(x => x?.Name ?? ""));
                    // A mesh component that hangs off something other than the actor
                    // root carries a RelativeLocation in PARENT space, not world space.
                    var parent = e.GetOrDefault<FPackageIndex>("AttachParent", null);
                    outActors.Add(new
                    {
                        cell,
                        cls,
                        name = e.Name,
                        mesh = meshName,
                        meshPath = mp,
                        ovr,
                        attachParent = parent?.Name,
                        loc = new[] { loc.X, loc.Y, loc.Z },
                        rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                        scale = new[] { scl.X, scl.Y, scl.Z },
                        instanceCount = insts.Count,
                        instances = insts,
                    });
                }
                else if (cls == "SceneComponent" || cls == "InstancedFoliageActor")
                {
                    var loc = e.GetOrDefault("RelativeLocation", FVector.ZeroVector);
                    var rot = e.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
                    var scl = e.GetOrDefault("RelativeScale3D", FVector.OneVector);
                    var root = e.GetOrDefault<FPackageIndex>("RootComponent", null);
                    outActors.Add(new
                    {
                        cell, cls, name = e.Name,
                        mesh = (string?)null, meshPath = root?.Name,
                        loc = new[] { loc.X, loc.Y, loc.Z },
                        rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                        scale = new[] { scl.X, scl.Y, scl.Z },
                        instanceCount = 0,
                        instances = new List<float[]>(),
                    });
                }
                else if (cls.Contains("Landscape", StringComparison.OrdinalIgnoreCase))
                {
                    var loc = e.GetOrDefault("RelativeLocation", FVector.ZeroVector);
                    var scl = e.GetOrDefault("RelativeScale3D", FVector.OneVector);
                    var sectionBase = e.GetOrDefault("SectionBaseX", 0);
                    outActors.Add(new
                    {
                        cell, cls, name = e.Name,
                        mesh = (string?)null, meshPath = (string?)null,
                        loc = new[] { loc.X, loc.Y, loc.Z },
                        rot = new[] { 0f, 0f, 0f },
                        scale = new[] { scl.X, scl.Y, scl.Z },
                        instanceCount = 0,
                        instances = new List<float[]>(),
                        sectionBaseX = sectionBase,
                        props = e.Properties.Select(p => p.Name.Text).ToArray(),
                    });
                }
            }
        }
        var outPath = Path.Combine(OutDir, "cellactors.json");
        File.WriteAllText(outPath, JsonSerializer.Serialize(outActors,
            new JsonSerializerOptions { WriteIndented = false }));
        Console.Error.WriteLine($"wrote {outActors.Count} records -> {outPath}");
        return 0;
    }
}
