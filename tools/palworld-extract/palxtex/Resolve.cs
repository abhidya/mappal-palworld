using System.Text.Json;
using CUE4Parse.UE4.Assets.Exports.Engine;
using CUE4Parse.UE4.Objects.Core.Math;
using CUE4Parse.UE4.Objects.UObject;

namespace Palxtex;

/// Resolution helpers for object ids that are NOT BP_BuildObject_* buildables
/// (Pal eggs, world DamagableRocks). Two modes:
///   --dt <substr>...        dump every UDataTable row of the matching assets
///   --bpmesh <bppath>...    list the mesh components (+ relative xform) of the
///                           given blueprint packages, following native parent
///                           classes and referenced child blueprints.
public static class Resolve
{
    public static int RunDt(string[] args)
    {
        var provider = P.Mount();
        Console.Error.WriteLine($"mounted files={provider.Files.Count}");
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
                foreach (var ex in provider.LoadPackage(vp).GetExports())
                {
                    if (ex is not UDataTable dt) continue;
                    var rows = new Dictionary<string, Dictionary<string, string>>();
                    foreach (var kv in dt.RowMap)
                    {
                        var cols = new Dictionary<string, string>();
                        foreach (var prop in kv.Value.Properties)
                            cols[prop.Name.Text] = prop.Tag?.GenericValue?.ToString() ?? "";
                        rows[kv.Key.Text] = cols;
                    }
                    dump[vp[(vp.LastIndexOf('/') + 1)..]] = rows;
                    Console.WriteLine($"{vp}: {rows.Count} rows");
                }
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {vp}: {ex.Message}"); }
        }
        File.WriteAllText(Path.Combine(P.Base, "dt_dump.json"),
            JsonSerializer.Serialize(dump, new JsonSerializerOptions { WriteIndented = false }));
        Console.Error.WriteLine("-> dt_dump.json");
        return 0;
    }

    public class Comp
    {
        public string export { get; set; }
        public string exportClass { get; set; }
        public string mesh { get; set; }
        public string meshPath { get; set; }
        public float[] rot_pyr { get; set; }
        public float[] loc_cm { get; set; }
        public float[] scale { get; set; }
        public bool visible { get; set; }
        public string via { get; set; }
        public string[] overrideMaterials { get; set; }
    }

    /// Walks a blueprint package: its own mesh components, then (one level) the
    /// mesh components of any blueprint it imports. Cooked BPs keep their
    /// component defaults as exports, so this is the authoritative source.
    public static List<Comp> Walk(CUE4Parse.FileProvider.DefaultFileProvider provider, string vpath,
                                  int depth = 0, HashSet<string> seen = null)
    {
        seen ??= new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var outl = new List<Comp>();
        if (vpath == null || !seen.Add(vpath)) return outl;
        CUE4Parse.UE4.Assets.IPackage pkg;
        try { pkg = provider.LoadPackage(vpath); } catch { return outl; }

        foreach (var ex in pkg.GetExports())
        {
            var cls = ex.ExportType ?? "";
            if (!cls.Contains("StaticMeshComponent") && !cls.Contains("SkeletalMeshComponent")) continue;
            var mp = ex.GetOrDefault<FPackageIndex>("StaticMesh", null)
                     ?? ex.GetOrDefault<FPackageIndex>("SkeletalMesh", null);
            if (mp?.Name == null) continue;
            var r = ex.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
            var l = ex.GetOrDefault("RelativeLocation", FVector.ZeroVector);
            var s = ex.GetOrDefault("RelativeScale3D", FVector.OneVector);
            outl.Add(new Comp
            {
                export = ex.Name, exportClass = cls, mesh = mp.Name,
                meshPath = mp.ResolvedObject?.GetPathName(),
                rot_pyr = new[] { r.Pitch, r.Yaw, r.Roll },
                loc_cm = new[] { l.X, l.Y, l.Z },
                scale = new[] { s.X, s.Y, s.Z },
                visible = ex.GetOrDefault("bVisible", true),
                overrideMaterials = ex.GetOrDefault<FPackageIndex[]>("OverrideMaterials", null)
                    ?.Select(x => x?.Name).Where(x => x != null).ToArray(),
                via = depth == 0 ? null : vpath,
            });
        }
        if (outl.Count > 0 || depth >= 4) return outl;

        // No mesh of its own: follow the cooked blueprint parent/import chain.
        // Many Pal variants (boss/predator/elemental forms) inherit through two
        // or three intermediate BPs before reaching the actor that owns the
        // SkeletalMeshComponent, so a one-level walk silently lost them.
        if (pkg is CUE4Parse.UE4.Assets.IoPackage io)
        {
            foreach (var dep in io.ImportedPackages.Value)
            {
                var op = dep?.Name;
                if (op == null || !op.StartsWith("/Game/")) continue;
                var n = op[(op.LastIndexOf('/') + 1)..];
                if (!n.StartsWith("BP_")) continue;
                var vp = "Pal/Content/" + op.Substring("/Game/".Length) + ".uasset";
                if (!provider.Files.ContainsKey(vp)) continue;
                outl.AddRange(Walk(provider, vp, depth + 1, seen));
                if (outl.Count > 0) break;
            }
        }
        return outl;
    }

    public static int RunBpMesh(string[] args)
    {
        var provider = P.Mount();
        Console.Error.WriteLine($"mounted files={provider.Files.Count}");
        var res = new Dictionary<string, List<Comp>>();
        foreach (var want in args.Skip(1))
        {
            var leaf = "/" + want + ".uasset";
            var vp = provider.Files.Keys.FirstOrDefault(k => k.EndsWith(leaf, StringComparison.OrdinalIgnoreCase))
                     ?? provider.Files.Keys.FirstOrDefault(k => k.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)
                                                                && k.Contains(want, StringComparison.OrdinalIgnoreCase));
            if (vp == null) { Console.WriteLine($"MISS {want}"); continue; }
            var comps = Walk(provider, vp);
            res[want] = comps;
            Console.WriteLine($"### {want}  -> {vp}  ({comps.Count} mesh comps)");
            foreach (var c in comps)
                Console.WriteLine($"    [{c.exportClass}] {c.export} mesh={c.mesh} vis={c.visible} loc={string.Join(",", c.loc_cm)} rot={string.Join(",", c.rot_pyr)} scale={string.Join(",", c.scale)} via={c.via}\n        {c.meshPath}");
        }
        File.WriteAllText(Path.Combine(P.Base, "bpmesh_dump.json"),
            JsonSerializer.Serialize(res, new JsonSerializerOptions { WriteIndented = true }));
        Console.Error.WriteLine("-> bpmesh_dump.json");
        return 0;
    }

    /// Dump the real socket declarations from SK_PalHuman_Skeleton.  Rigid
    /// equipment is authored in socket-local space, so these transforms are
    /// required before composing it onto an animated player pose.
    public static int RunSockets(string[] args)
    {
        var provider = P.Mount();
        Console.Error.WriteLine($"mounted files={provider.Files.Count}");
        var vpath = provider.Files.Keys.FirstOrDefault(k =>
            k.EndsWith("/SK_PalHuman_Skeleton.uasset", StringComparison.OrdinalIgnoreCase));
        if (vpath == null) throw new FileNotFoundException("SK_PalHuman_Skeleton not found in PAK");
        var pkg = provider.LoadPackage(vpath);
        var sockets = new Dictionary<string, object>();
        foreach (var ex in pkg.GetExports())
        {
            if (!(ex.ExportType ?? "").Contains("SkeletalMeshSocket", StringComparison.OrdinalIgnoreCase))
                continue;
            var socket = ex.GetOrDefault("SocketName", new FName("None")).Text;
            var bone = ex.GetOrDefault("BoneName", new FName("None")).Text;
            if (string.IsNullOrEmpty(socket) || socket == "None") continue;
            var t = ex.GetOrDefault("RelativeLocation", FVector.ZeroVector);
            var r = ex.GetOrDefault("RelativeRotation", FRotator.ZeroRotator);
            var s = ex.GetOrDefault("RelativeScale", FVector.OneVector);
            var q = r.Quaternion();
            sockets[socket] = new Dictionary<string, object>
            {
                ["bone"] = bone,
                ["relative"] = new Dictionary<string, object>
                {
                    ["t"] = new[] { t.X, t.Y, t.Z },
                    ["q"] = new[] { q.X, q.Y, q.Z, q.W },
                    ["s"] = new[] { s.X, s.Y, s.Z },
                },
            };
        }
        var outPath = args.Length > 1 ? args[1] : Path.Combine(P.Base, "equipment_sockets.json");
        File.WriteAllText(outPath, JsonSerializer.Serialize(sockets,
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"{vpath}: {sockets.Count} sockets -> {outPath}");
        return sockets.Count > 0 ? 0 : 1;
    }

    /// list every package path whose leaf name matches a substring
    public static int RunFind(string[] args)
    {
        var provider = P.Mount();
        Console.Error.WriteLine($"mounted files={provider.Files.Count}");
        foreach (var k in provider.Files.Keys.Where(k =>
                     args.Skip(1).Any(w => k.Contains(w, StringComparison.OrdinalIgnoreCase))).OrderBy(k => k))
            Console.WriteLine(k);
        return 0;
    }
}
