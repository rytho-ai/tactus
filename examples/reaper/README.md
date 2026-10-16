# REAPER: instruments, live MIDI co-working and handoff

A Python work writes ordinary ReaScript Lua to use ReaSynth; a custom exporter
hands the saved stems to a native project. See the [bridge reference](../../skills/references/reaper.md)
for setup and exact behavior. No MCP or third-party REAPER extension is needed.

Create a work with `tactus init`, copy song.py and instrument.lua from this folder
into it, and add the `[tool.tactus.export]` registration from pyproject.toml. Commit the work's
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

## Co-work on the current MIDI selection

Copy cowork.py and selection.lua into the work. Keep the bridge running, select one
MIDI item and set a time selection inside it in REAPER (for example four bars).
The example uses that selection, not track names, track indices or a fixed tempo.

```bash
uv run python cowork.py --resource-path /your/REAPER/resources inspect --out selection.json
```

Read selection.json, author a JSON list of replacement notes in notes.json, then:

```bash
uv run python cowork.py --resource-path /your/REAPER/resources apply selection.json notes.json
```

Each note has start_qn/end_qn (absolute project quarter notes), pitch and velocity;
channel defaults to 0, selected/muted to false. The inspected notes already include
all fields, so copying and editing them preserves those choices. An empty list removes
the inspected notes. Timing and note decisions belong to the author.

The guarded recipe preserves instrument settings, other items, notes crossing/outside
the range and CC/text. It accepts one inline single take with zero source offset,
playrate one and no repeated/shared source. See the
[live workflow](../../skills/references/reaper.md#co-work-in-the-live-project) for
stale-state behavior, Undo, source-pool checks and adopting GUI changes.
One inspection is outstanding per host; inspect again after applying or reconnecting.
Read/write selection commands do not render audio or create a run receipt.
