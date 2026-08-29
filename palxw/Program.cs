// Export named TEXTURE assets from the cooked pak to PNG.
//
// Why this exists: the water pass needs the wave NORMAL MAPS that
// M_Pal_Water_Ver2 itself declares (Wave1..Wave4_Texture). The earlier water
// sweep (palxwater --matparams) recorded the parameter NAMES and asset paths
// but never exported the image data, and palxtex only walks a mesh manifest —
// water surfaces have no mesh manifest entry, so nothing ever pulled them.
//
// Mappings.usmap is mandatory: Palworld cooks PKG_UnversionedProperties, so
// without it every export deserialises to zero properties and the sweep comes
// back silently empty. The mount log prints whether they loaded.
//
//   --tex <outdir> <name...>   export every UTexture2D whose asset leaf name
//                              matches one of <name...>, as <Name>.png
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Versions;
using CUE4Parse_Conversion.Textures;
using SkiaSharp;

namespace Palxw;

public static class Program
{
    const string Base = "/private/tmp/claude-501/-Users-mannybhidya-Palworld/d95cfa7e-a30c-402b-9afc-cd5987f04ffe/scratchpad";

    public static int Main(string[] args)
    {
        if (args.Length < 2 || args[0] != "--tex")
        {
            Console.Error.WriteLine("usage: --tex <outdir> <texture-name>...");
            return 2;
        }

        var outDir = args[1];
        Directory.CreateDirectory(outDir);
        var wanted = args.Skip(2).ToArray();

        var root = Environment.GetEnvironmentVariable("PALX_ROOT") ?? Path.Combine(Base, "pakroot");
        var provider = new DefaultFileProvider(new DirectoryInfo(root), SearchOption.AllDirectories,
            new VersionContainer(EGame.GAME_UE5_1), StringComparer.OrdinalIgnoreCase);
        provider.Initialize();
        provider.Mount();
        var usmap = Environment.GetEnvironmentVariable("PALX_USMAP") ?? Path.Combine(Base, "Mappings.usmap");
        provider.MappingsContainer = new FileUsmapTypeMappingsProvider(usmap);
        Console.Error.WriteLine($"provider files: {provider.Files.Count}");
        // PROVE the mappings took — a zero-property sweep is otherwise silent.
        Console.Error.WriteLine($"mappings: {(provider.MappingsContainer?.MappingsForGame != null ? "LOADED" : "NULL")}");

        int wrote = 0;
        foreach (var vp in provider.Files.Keys.OrderBy(x => x))
        {
            if (!vp.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)) continue;
            var leaf = vp[(vp.LastIndexOf('/') + 1)..^".uasset".Length];
            if (!wanted.Any(w => leaf.Equals(w, StringComparison.OrdinalIgnoreCase))) continue;
            try
            {
                var pkg = provider.LoadPackage(vp);
                foreach (var ex in pkg.GetExports())
                {
                    if (ex is not UTexture2D tex) continue;
                    var dec = tex.Decode(ETexturePlatform.DesktopMobile);
                    if (dec == null) { Console.Error.WriteLine($"  DECODE-NULL {leaf}"); continue; }
                    using var bmp = dec.ToSkBitmap();
                    var fname = Path.Combine(outDir, $"{tex.Name}.png");
                    using var data = bmp.Encode(SKEncodedImageFormat.Png, 95);
                    using var fs = File.Create(fname);
                    data.SaveTo(fs);
                    Console.WriteLine($"{tex.Name}\t{bmp.Width}x{bmp.Height}\t{tex.Format}\t{vp}");
                    wrote++;
                }
            }
            catch (Exception e) { Console.Error.WriteLine($"  ERR {vp}: {e.Message}"); }
        }
        Console.Error.WriteLine($"wrote {wrote} textures -> {outDir}");
        return wrote > 0 ? 0 : 1;
    }
}
