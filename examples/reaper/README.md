# REAPER as a library, and native project handoff

A Python work writes ordinary ReaScript Lua to use ReaSynth; a custom exporter
hands the saved stems to a native project. See the [bridge reference](../../skills/references/reaper.md)
for setup and exact behavior. No MCP or third-party REAPER extension is needed.

Create a work with `tactus init`, copy song.py and instrument.lua here into it, and
add the `[tool.tactus.export]` registration from pyproject.toml. Commit the work's
source and lock before rendering. Run the packaged bridge Lua inside your REAPER
instance, then pass its actual resource directory and REAPER binary/bundle:

```bash
tactus run song.py --out runs/a --params '{"resource_path":"/your/REAPER/resources","reaper_bundle":"/your/REAPER"}'
tactus run song.py --out runs/b --params '{"resource_path":"/your/REAPER/resources","reaper_bundle":"/your/REAPER","transpose":3}'
tactus export reaper runs/a --out exports/reaper --resource-path /your/REAPER/resources --tempo 120 --markers '[[0,"A"],[4,"B"]]'
```

The Lua creates a new tab, uses native MIDI calls and renders 8 seconds including
release. Each generated tab is left open and the previously selected tab is restored.
The temporary instrument project/audio is disposable; keep the accepted run audio.

Open exports/reaper/song.rpp to continue editing without Tactus. Its three stems
use relative paths; neither REAPER instruments nor Tactus are required to play them
inside REAPER. To choose different markers from a run's map, write a local exporter
wrapper that selects those entries and calls export_project with seconds.

For replay without the DAW, import the chosen lead WAV with `tactus material add`,
put its ref in source (or pass `lead_ref`), commit, then render another run. Audio
replay and regenerated instrument output are separate promises.
