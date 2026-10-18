# REAPER bridge

Use `tactus.bridges.reaper` to call REAPER's native ReaScript Lua from Python,
co-work in a live project, or hand completed audio to a native project. REAPER runs
separately; the bridge has no MCP dependency. Python remains the work's source, and ordinary Lua owns
DAW-specific decisions. The [ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html)
is the function reference; REAPER can generate documentation for its installed version.

## Choose the lifecycle path

Start from new MIDI, an existing live project or an accepted render:

1. Read project identity/selection and the user's intended scope. Author the native
   queries the task needs; the bridge accepts ordinary Lua.
2. Borrow instruments/effects or co-work through short scoped edits.
3. Read back actual state; keep the edit's Undo separate from later human actions.
4. Adopt accepted project/media, MIDI/FX data or audio as material refs in source.
5. Render/version in Tactus. Pin chosen audio for replay with REAPER stopped.
6. Hand off native editable state or printed outputs. Later DAW edits become new
   accepted inputs, continuing the cycle.

Shared Python modules under `tactus.bridges.reaper_support` own repeated mechanics:

- `selection.inspect_selection` / `selection.replace_notes`: fresh native scope checks,
  authored replacement notes and one Undo group.
- `devices.inspect` / `devices.configure` / `devices.configure_many`: reusable FX
  descriptions, fresh chosen values and preflight-all parameter batches in one Undo.
- `project.inspect` / `project.capture` / `project.render_project`: native copies,
  media collection/reopen checks and writable rebuilds from pinned materials.
- `audio.render`: execute authored setup Lua in a private tab, render, validate and
  return frames-first audio; preserve failure evidence and restore the previous tab.

The matching runtime source distribution/repository's `examples/reaper/README.md`
shows these APIs in ordinary Python works. Copy musical source such as instrument.lua
when useful; selection/project/render machinery ships in the runtime. A plugin-cache
copy contains this reference; examples come from the matching runtime source distribution.

### Quick parameter edits

Use the ordinary track FX chain (including Master), inspected track/FX GUIDs and
zero-based parameter indices. Values are explicitly **normalized 0..1**, not Hz/dB.
Use native Lua for other chains, containers, routing or unsupported plugin interfaces.

```python
from tactus.bridges.reaper_support import devices

snapshot = devices.inspect(resource_path=resource, track_guid=track_guid,
                           fx_guid=fx_guid, parameters=[0, 1])
# Choose values after reading the actual parameter descriptions/display.
snapshot = devices.configure(snapshot, {'0': chosen_value}, resource_path=resource)
```

The returned compact snapshot holds actual values and can guard the next edit. One
`configure_many([{'snapshot': s, 'values': values}, ...])` checks the active project,
exact GUIDs, current parameter names/count and all observed values before any write.
Only observed indices may be changed; duplicates, nonfinite/out-of-range values and
stale snapshots reject. Native setter failure can leave partial edits, with no retry
or rollback. Use native Undo deliberately after inspection.

Descriptions are bounded caches in the running Lua bridge, with fresh layout checks;
musical values are never cached. `metadata=False` omits known descriptions and
`refresh=True` rebuilds an inspection's schema, expiring older snapshots for that FX.
`devices.stats` exposes cache build/hit counts. A host/cache restart expires snapshots.
The edit returns its own readback: another full project query, render or capture is
unnecessary for a small audition. Accepted state/audio still follows the lifecycle
above; an edit reply is not a run receipt. See `examples/reaper/fx.py` in the source
distribution for inspect/apply JSON commands.

## Connect an existing conversation through MCP

The optional stdio server exposes `reaper_status` and `reaper_execute`; it runs no
model and starts no agent conversation. Native Lua uses the same bridge as Python.
The live RPP remains the user's project; accepted state/audio becomes a pinned input
only when the work explicitly adopts it. MCP tool replies are not render receipts.

Install the extra in the environment that will start the server. From a checkout:

```bash
uv sync --extra mcp
uv run --extra mcp python -c 'from tactus.bridges.reaper import script; print(script())'
```

In REAPER, use Options → Show REAPER resource path to find its resource directory.
Load the printed Lua path with Actions → ReaScript → Load and run that Action once.
REAPER and the MCP server must share the local filesystem. The script has full
native ReaScript/file access, just as through the ordinary Python bridge.

Configure the agent host to launch the server; use actual absolute paths:

```json
{
  "mcpServers": {
    "tactus": {
      "command": "/absolute/path/to/checkout/.venv/bin/python",
      "args": ["-m", "tactus.mcp", "--resource-path", "/absolute/REAPER/resources"]
    }
  }
}
```

On Windows use the environment's `Scripts/python.exe`. This executable belongs to
the installation with the extra, independently of any song's lock. Alternatively,
use an absolute `uv` executable with args `run --project /absolute/checkout --locked
--extra mcp python -m tactus.mcp --resource-path /absolute/REAPER/resources`.

For a global installation, from the checkout run
`uv tool install --python 3.12 --editable '.[mcp]'` and use the absolute path of
`tactus-mcp` as command, with args `--resource-path /absolute/REAPER/resources`.
`tactus mcp --resource-path ...` is also available, but the normal Tactus launcher
selects the current work's environment; that work must have the MCP extra too.

For Codex CLI, add the same executable and arguments:

```bash
codex mcp add tactus -- /absolute/path/to/checkout/.venv/bin/python -m tactus.mcp --resource-path /absolute/REAPER/resources
```

For Claude Code, from the intended project:

```bash
claude mcp add --transport stdio tactus -- /absolute/path/to/checkout/.venv/bin/python -m tactus.mcp --resource-path /absolute/REAPER/resources
```

Quote each path containing spaces when using a shell. These commands write host
configuration; they do not start a replacement agent. Host configuration formats
vary: the JSON above is the common `mcpServers` form, while Codex uses TOML behind
its CLI. See [Codex MCP](https://developers.openai.com/codex/mcp/) and
[Claude Code MCP](https://code.claude.com/docs/en/mcp) for configuration/status UI.

Configure MCP once before the conversation. The server can start before REAPER or
the bridge: `reaper_status` reports `unavailable` with setup paths/reason. Later run
the bridge, and call status again from the same conversation/connection; `ready`
includes the active project, selected tracks/items, time selection and tempo/meter
at the edit cursor. No MCP reload is needed when only the DAW connection changes.
If adding the MCP configuration during an existing chat, use that host's supported
reload/reconnect mechanism; arbitrary hosts/sessions do not share one hot-load
contract. This is tool access from the original chat, not mirroring chat into REAPER.

Ask the agent to call `reaper_status`, then inspect the intended native scope before
an edit. For example, `reaper_execute` accepts:

```json
{
  "code": "return {version=reaper.GetAppVersion(), tracks=reaper.CountTracks(0)}",
  "args": null,
  "timeout": 30,
  "undo": null
}
```

It returns `{"result": ...}` in structured content and JSON text. `args` is finite
JSON data, preserved without interpreting JSON-looking strings; native values use
the ordinary bridge encoding. Exceptions are MCP tool errors (`isError`), including
native error text and timeout/late-reply paths. Status distinguishes `unavailable`
from `completion_unknown`. Empty native Lua tables become `{}`, including empty
selection lists. Project instance is runtime identity, not a persistent GUID.

Calls in each server are serialized. Once a native request starts, the server keeps
its worker until bridge completion/timeout even if the MCP caller has already received
a cancellation acknowledgement. Cancellation does not cancel Lua or roll back edits.
Other servers/human edits are not locked. Use
short operations, actual scope checks and explicit Undo; follow the recovery section
after errors/timeouts. Set the host's tool timeout above the requested native timeout
when needed. Stdout is protocol-only; diagnostics use stderr. Disconnecting MCP
leaves REAPER and its bridge Action running. Stop the Action separately to disconnect
the native side. This entry adds no HTTP listener, account or automatic DAW launch.

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

Use `audio.render` when you want a private native project for an instrument or FX
performance. The authored Lua creates the tracks, MIDI, plugins and routing; the
shared module owns the temporary tab, offline render settings, completion, WAV checks
and scratch cleanup. It renders exactly zero through the explicit duration, with no
extra tail, normalization or silence rejection. Include any desired release in duration.

```python
from tactus.bridges.reaper_support import audio

samples = audio.render(setup_lua, resource_path=resource,
                       reaper_bundle="/path/to/REAPER", args={"notes": notes},
                       seconds=8, sample_rate=24000, channels=2)
```

`setup_lua` sees ordinary `args` and `reaper.*` in a new empty project. It may open a
writable project copy, but must remain in that owned tab. Native setup executes once;
this is unrestricted Lua, not a sandbox. The native WAV uses PCM24, matching the existing recipe. Success closes the saved
temporary tab and returns decoded audio shaped `(frames, channels)`; mono has one column. Errors/timeouts
retain scratch and can leave the private tab open, while restoring the prior selected
tab when native execution returns. A timeout cannot cancel active rendering: inspect
its late reply before cleanup. Rendering occupies REAPER's main thread. The generic
`execute` path remains available for other native workflows.

Declare Lua files and REAPER/plugin binaries with `tool()`, and pin input projects,
samples and selected audio with `material()`. Preserve `.rpp`/media filenames when
copying verified material bytes into a DAW input directory. A receipt records work
source, lock, materials and declared tools; it does not snapshot every mutable DAW
setting, external file or project action. To replay an accepted result independently
of REAPER, pin its rendered audio. Regenerating instrument sound is a separate check.

## Co-work in the live project

Read the user's current selection and intended scope, then change only the accepted
part. Keep calls short while the user plays or edits: synchronous Lua and offline
rendering occupy REAPER's main thread. A playback cursor advancing is not evidence
of glitch-free audio. Keep long rendering separate from live editing.

The shared `selection` module reads one selected
MIDI item and the GUI time selection. It returns fully contained notes in absolute
project quarter notes; the agent authors the variation in ordinary Python/JSON:

```python
from tactus.bridges.reaper_support.selection import inspect_selection, replace_notes

snapshot = inspect_selection(resource_path=resource)
notes = [dict(note) for note in snapshot["notes"]]
# Compose the requested variation here, using snapshot["range_qn"] and these notes.
result = replace_notes(snapshot, notes, resource_path=resource)
```

Use a nonempty time selection inside a single-take inline MIDI item, with source
offset zero and playrate one. A nonrepeating first pass is supported even when
REAPER's source-loop checkbox is enabled. Repeated, shared pooled and file-backed
MIDI require their own recipe. The implementation recognizes inline pool identities from
native item state; verify that representation when adapting to another REAPER version.

The recipe binds the actual project/take in the running Lua host. One outstanding
inspection is retained; a new inspection replaces it, host restart loses it, and an
apply consumes it. Before writing it rechecks the selected item, time range, item
state and musical coordinates. Unrelated track FX changes can remain. A stale
response means inspect again and reconsider the variation against the new notes.

Only fully contained notes are replaced. Crossing/outside notes and CC/text events
remain; same-pitch overlaps with retained notes are rejected before writing. Proposed
notes are checked before deletion, including MIDI tick rounding. One native Undo
groups the edit. An execution error can still leave changes: inspect first, then
use that Undo if appropriate; never automatically undo a later human action.

After a result is accepted, save the required project/media as explicit materials
or capture the chosen MIDI, FX settings or rendered take in the work. Reference those
identities in source and commit them. Live state is an input to adopt, not automatic
two-way synchronization with the original generator. Preserve accepted audio through
the normal compose/run workflow; arbitrary GUI edits cannot be inverted into Python.

### Capture and rebuild accepted state

`project.capture(resource_path=resource, out=NEW_DIRECTORY)` saves a stopped live project
copy, collects/rebinds ordinary file-backed takes, verifies native reopening, checks
the live state is unchanged, then writes capture.json. Pin that directory with
`tactus material add`; use the tree ref as project_ref in accepted.py and commit
source/lock/refs before rendering. Native MIDI/FX/routing/automation remain in
the RPP. Inline MIDI and ordinary file takes are handled; wrapped sources,
subprojects/video or missing media require a work-authored recipe. Declare plugin
binaries and plugin-owned libraries/IRs separately; take-media collection cannot
discover every opaque plugin dependency. Saving a native copy may advance the live
change counter; after saving, capture compares actual native content and context rather
than treating that counter increment as a musical edit. Pre-save counter checks remain.

Rebuild from a real scratch copy, render the explicitly chosen range in a private
tab and restore the live tab. Material trees can use hardlinks: saving directly
inside material(ref) can corrupt the pool. The shared implementation retains scratch on failure
or timeout, since native execution can continue. Pin the chosen audio afterward;
accepted.py's audio_ref route needs no REAPER. Native capture and printed-stem
export support editable-state and preserved-sound handoffs respectively.

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

For work-authored mutations, compare actual target state as well as any native
change counter: setters do not always increment it. Native Undo also depends on
the preceding checkpoint. Record a programmatic fixture's complete baseline or
reopen its saved RPP before checking Undo; otherwise older unrelated state may
return. Choose Undo flags for the edited scope. Reconnect by ending the old bridge
action and running the packaged script again, then inspect the current project
and take fresh selection snapshots. Stop that action or quit REAPER to disconnect.
