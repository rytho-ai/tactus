# REAPER bridge

Use `tactus.bridges.reaper` to call REAPER's native ReaScript Lua from Python,
or hand completed audio to a native project. REAPER runs separately; the bridge
has no MCP dependency. Python remains the work's source, and ordinary Lua owns
DAW-specific decisions. The [ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html)
is the function reference; REAPER can generate documentation for its installed version.

## Start the connection

REAPER and Tactus must share the local filesystem. In the work's locked environment:

```bash
uv run python -c 'from tactus.bridges.reaper import script; print(script())'
```

In REAPER's Actions list, load that Lua file with ReaScript → Load, then run it.
Keep it running while using the bridge. This creates `tactus-bridge/` under REAPER's
resource directory. Find that directory through Options → Show REAPER resource path.
Use an isolated REAPER configuration for automated experiments. No startup script,
control surface, extension or account is installed automatically.

```python
from tactus.bridges import reaper

resource = "/your/REAPER/resource-directory"
info = reaper.execute("return {version=reaper.GetAppVersion(), tracks=reaper.CountTracks(0)}",
                      resource_path=resource)
```

The script has the same native/file access as a ReaScript you write yourself.
Load/run it once per REAPER instance; end its running action or quit REAPER to stop.

## Write ordinary Lua

`execute(code, *, resource_path, args=None, timeout=30, undo=None)` waits for native
execution and returns the first Lua result. Supply data through `args`, so paths,
quotes and Unicode are encoded correctly instead of interpolated into Lua source:

```python
result = reaper.execute('''
local track = reaper.GetTrack(0, args.index)
assert(track, 'Track does not exist')
reaper.SetMediaTrackInfo_Value(track, 'D_VOL', args.gain)
return {guid=reaper.GetTrackGUID(track), gain=reaper.GetMediaTrackInfo_Value(track, 'D_VOL')}
''', resource_path=resource, args={"index": 0, "gain": 0.5}, undo="Set track gain")
```

Args accept strings, paths, finite numbers, booleans, lists/tuples and string-key
dictionaries. Lists become 1-based Lua tables. `None` becomes native `nil`, which
removes table fields and can create array holes; use explicit flags/values when
positions must be retained. Integers must fit signed 64 bits.

Return finite JSON values: dense tables become lists, string-key tables become
dicts, an empty table becomes `{}`, and nil becomes None. Return GUIDs or inspected
data for native handles. Sparse/mixed tables, cycles, functions, userdata and
non-finite numbers raise `BridgeError`; values are never silently truncated.
`print` is forwarded to Python stderr. The interface does not wrap each reaper.*
function or impose notes, tracks, routing or session data types on the work.

## Use REAPER to make audio

Write the native MIDI/FX/render instructions in a work-local `.lua` file. Read it
from Python and call execute with explicit project inputs, notes and output paths;
read the resulting WAV with SoundFile and return it from `render` normally. Check
its sample rate, channel count, frame count and finite values. The
`examples/reaper/` example in the Tactus source distribution uses ReaSynth, revisions and
pinned replay. When using a cached plugin copy, open the installed runtime example
from its source distribution/repo; its instrument Lua can also be written directly.

Declare Lua files and REAPER/plugin binaries with `tool()`, and pin input projects,
samples and selected audio with `material()`. Preserve `.rpp`/media filenames when
copying verified material bytes into a DAW input directory. A receipt records work
source, lock, materials and declared tools; it does not snapshot every mutable DAW
setting, external file or project action. To replay an accepted result independently
of REAPER, pin its rendered audio. Regenerating instrument sound is a separate check.

## Hand completed audio to REAPER

Register the library function in the work:

```toml
[tool.tactus.export]
reaper = "tactus.bridges.reaper:export_project"
```

```bash
tactus export reaper runs/a --out exports/reaper --resource-path /your/REAPER/resources --names '["lead","drums"]' --markers '[[0,"start"],[4,"next"]]'
```

The exporter receives verified saved arrays; it does not rerun the source instrument.
It writes FLOAT WAV files and creates `song.rpp` in a fresh REAPER project tab,
using the native API. Media paths are relative, with zero origin, unity gain/rate,
no fades and each output's own length. The old selected tab is restored; the new
saved tab remains open. No existing project is loaded over or overwritten.

Default names are all outputs except literal `mix`; pass `names=["mix"]` for a
mix-only project. Outputs need not sum to mix. Markers are caller-selected
`[seconds, label]` pairs; `tempo` is optional and changes native tempo only when
explicitly supplied. Time map/run identity are preserved in source.json; no map
lane is automatically interpreted. Use a work-local exporter wrapper to select map
entries and convert their frames to seconds. Native default tempo remains when
none is supplied; stem positions stay in seconds, not inferred beats.

`export.json` inventories the completed handoff. Move/copy the whole directory,
then open song.rpp in REAPER to continue working without Tactus. The format preserves
rendered audio; editable MIDI, automation and instrument/routing state require
work-authored native Lua and explicit data. Arbitrary Python cannot be inverted
into a DAW arrangement.

## Completion and state

Calls run serially in REAPER's main-thread defer loop. Each synchronous Lua request
must finish before another runs; use short calls to query playback over time.
A modal dialog, blocked plugin or infinite Lua loop can stall the host. `undo` groups
one project's modifications, but neither errors nor timeouts roll back changes.

On `BridgeTimeout`, inspect the project before retrying: queued requests are withdrawn
or expire, but an already executing script continues. A late reply may remain at the
path named by the exception. There is no automatic retry. An exporter failure may
leave its newly created tab for inspection even if the CLI removes its failed output
directory. User-authored Lua must coordinate project selection and any manual edits.

The bridge does not launch/quit REAPER or infer which live project you meant. Query
project identity first when operating on existing work. Reconnecting to live state,
replaying saved audio and rebuilding a DAW project have different evidence requirements.
