# Timelapse renderer and data pipeline

`timelapse.mjs` drives MapPal headlessly to render a base's recorded history to
PNG frames; the Python scripts here build the data it loads.

Full documentation — pipeline order, every environment knob, how to regenerate
assets, and the provenance rules this feature is bound by — is in
[`docs/TIMELAPSE.md`](../../docs/TIMELAPSE.md).

```bash
export PALTL_WORK=/path/to/work    # holds mappal/ + intermediate JSON
node timelapse.mjs <base8> [MINFRAMES] [TURNS]
bash encode.sh
```
