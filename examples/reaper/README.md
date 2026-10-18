# REAPER: read, create, co-work, adopt and hand off

A Python work writes ordinary ReaScript Lua to use ReaSynth; a custom exporter
hands the saved stems to a native project. See the [bridge reference](../../skills/references/reaper.md)
for setup and exact behavior. No MCP or third-party REAPER extension is needed.

| Intent | Route |
| --- | --- |
| Read existing state | `project.py inspect`, or author the required native query |
| Borrow instruments/effects | `song.py` + `instrument.lua` |
| Co-work on selected MIDI | shared `selection` API, or `cowork.py` CLI |
| Adopt current GUI/MIDI/FX state | `project.py capture`, then `tactus material add` |
| Rebuild accepted native state | `accepted.py` + shared `project.render_project` |
| Continue with REAPER stopped | Pin the chosen WAV; use `accepted.py` with `audio_ref` |
| Hand off and return later | Deliver native capture or export printed outputs; capture subsequent DAW edits into a new ref |

Create a work with `tactus init`, copy song.py and instrument.lua from this folder
into it, and add the `[tool.tactus.export]` registration from pyproject.toml. Commit the work's
source and lock before rendering. Run the packaged bridge Lua inside your REAPER
instance, then pass its actual resource directory and REAPER binary/bundle:

```bash
tactus run song.py --out runs/a --params '{"resource_path":"/your/REAPER/resources","reaper_bundle":"/your/REAPER"}'
tactus run song.py --out runs/b --params '{"resource_path":"/your/REAPER/resources","reaper_bundle":"/your/REAPER","transpose":3}'
tactus export reaper runs/a --out exports/reaper --resource-path /your/REAPER/resources --tempo 120 --markers '[[0,"A"],[4,"B"]]'
```

The Lua authors MIDI and sound; shared `audio.render` creates a private tab and
renders 8 seconds including release. It closes the successful private tab and restores
the previous tab. On failure/timeout it retains scratch for inspection. Keep the
accepted run audio.

Open exports/reaper/song.rpp to continue editing without Tactus. Its three stems
use relative paths; neither REAPER instruments nor Tactus are required to play them
inside REAPER. To choose different markers from a run's map, write a local exporter
wrapper that selects those entries and calls export_project with seconds.

For replay without the DAW, import the chosen lead WAV with `tactus material add`,
put its ref in source (or pass `lead_ref`), commit, then render another run. Audio
replay and regenerated instrument output are separate promises.

## Co-work on the current MIDI selection

Use `tactus.bridges.reaper_support.selection` directly, or copy cowork.py for its CLI. Keep the bridge running, select one
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

## Adopt the live project and continue in Tactus

Copy accepted.py for the musical entry and optionally project.py for its CLI. Shared
project/render Lua ships in Tactus; it is not copied into each work. Stop transport, select
the intended tab, inspect it and save its accepted state to a new directory:

```bash
uv run python project.py --resource-path /your/REAPER/resources inspect
uv run python project.py --resource-path /your/REAPER/resources capture --out captures/chosen
tactus material add captures/chosen
```

Set the returned tree ref as project_ref in source. Declare REAPER/plugin binaries
with `tool()` and required plugin libraries/IRs as explicit materials. Commit the
source, refs and lock, then render (or pass the choices as parameters):

Keep `captures/` in the work's .gitignore; Git records the material ref, while the
pool/native bundle retains the media. Retain or back up that pool when sharing a work.

```bash
tactus run accepted.py --out runs/chosen --params '{"project_ref":"tree:sha256:...","resource_path":"/your/REAPER/resources","reaper_bundle":"/your/REAPER","seconds":8,"sample_rate":24000}'
```

Capture saves a native copy, collects each file-backed take into content-named
media, rebinds only the copy, and reopens it to verify media resolves inside the
bundle. It checks actual native state before saving and the live state afterward,
then writes capture.json last. Existing destinations are refused. An incomplete
capture has no completion record; inspect it before retrying to a new path.

Native MIDI, FX, routing, automation and item/take settings stay in the RPP. This
recipe handles inline MIDI and ordinary file-backed takes, including external
files. Section/reversed sources, subprojects, video and missing sources need an
adapted native recipe. Plugin-owned samples/IRs and external hardware remain
separate dependencies. This is not an atomic lock against external media writers.

Rebuild makes a real scratch copy of the pinned bundle, renders zero through the
requested seconds in a private tab, then closes the successful private tab and
restores the selected live tab. Pool files are never saved into. Rendering occupies
REAPER's main thread; keep it separate from live edits. On failure/timeout the
scratch path is retained and reported on the exception; a failed private tab can
remain for inspection. Inspect the host and late reply before cleaning those files.

To preserve the chosen sound independently of the host and instruments:

```bash
tactus material add runs/chosen/mix-ACTUAL_HASH.wav
tactus run accepted.py --out runs/replay --params '{"audio_ref":"sha256:...","seconds":8,"sample_rate":24000}'
```

Use the actual WAV filename printed by run. Put the chosen audio_ref in source,
commit, and render with REAPER stopped. Compare hashes before claiming exact replay.
`gain` is an explicit Tactus-side revision; new MIDI/FX choices instead produce
another capture/ref and candidate. Technical selection is distinct from a
listener's musical approval.

For an editable native handoff deliver the entire capture directory and open
session.rpp with the required plugins/assets installed. For audio-preserving
handoff use `tactus export reaper` on the saved run. Register the exporter in the
work's existing pyproject.toml; keep its generated dependency source and lock:

```toml
[tool.tactus.export]
reaper = "tactus.bridges.reaper:export_project"
```

The example pyproject.toml uses a checkout-relative dependency and is not a
replacement for `tactus init`. After further edits in REAPER, capture to a new
directory/ref to start another cycle; arbitrary GUI changes are not inverted into
the original Python generator.

## Recover and disconnect

Read-only requests use no undo label. Before authored mutations check the actual
target/state; native setters do not always advance a change counter. Read back
results. Group edits with native Undo flags matching the item/track/all-state
scope. For programmatically created fixtures, record the complete baseline in
Undo history or reopen its saved RPP first; an older checkpoint can restore older
unrelated settings. Never automatically undo a later human action.

Errors/timeouts can leave changes. Inspect state and the late reply before deciding
to Undo or retry; an executing request continues after timeout. Keep its scratch
and output available until completion is known. Reconnect by stopping the old
bridge action and running the packaged script again, then inspect project identity
and take a fresh selection snapshot. Stop the bridge through Actions or quit
REAPER to disconnect; stop preview servers separately if you started any.
