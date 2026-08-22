# Palworld asset extractors

CUE4Parse-based .NET console tools that pull meshes, textures, terrain, water,
spawners and equipment out of a local Palworld install — on macOS, with no
Windows machine and no UE editor.

**They ship the extractors, never the extractions.** Palworld's assets are
Pocketpair's copyrighted content; nothing extracted belongs in this repository.

Build prerequisites, the `PALX_*` environment, per-tool usage and the pose-baking
notes are all in [`docs/TIMELAPSE.md`](../../docs/TIMELAPSE.md#regenerating-the-assets).

Quick start:

```bash
git clone --recursive https://github.com/FabianFG/CUE4Parse.git cue4parse
(cd cue4parse && git checkout 83200c6)
export PALX_BASE=/path/to/work
export PALX_PAKS=".../steamapps/common/Palworld/Pal/Content/Paks"
dotnet build -c Release -p:CUE4PARSE_SKIP_NATIVE=true palxtex
```
