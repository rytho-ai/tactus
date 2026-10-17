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

The matching runtime source distribution/repository's `examples/reaper/README.md`
walks through these routes. `project.py`/`project.lua` capture/rebuild accepted native
state; `accepted.py` renders the pinned project or audio. Copy these recipes into
the work, or author ordinary Lua directly. A plugin-cache copy contains this
reference; executable examples come from the matching runtime source distribution.

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

## Co-work in the live project

Read the user's current selection and intended scope, then change only the accepted
part. Keep calls short while the user plays or edits: synchronous Lua and offline
rendering occupy REAPER's main thread. A playback cursor advancing is not evidence
of glitch-free audio. Keep long rendering separate from live editing.

The copyable `examples/reaper/cowork.py` and `selection.lua` recipe reads one selected
MIDI item and the GUI time selection. It returns fully contained notes in absolute
project quarter notes; the agent authors the variation in ordinary Python/JSON:

```python
from cowork import inspect_selection, replace_notes  # copied into this work

snapshot = inspect_selection(resource_path=resource)
notes = [dict(note) for note in snapshot["notes"]]
# Compose the requested variation here, using snapshot["range_qn"] and these notes.
result = replace_notes(snapshot, notes, resource_path=resource)
```

Use a nonempty time selection inside a single-take inline MIDI item, with source
offset zero and playrate one. A nonrepeating first pass is supported even when
REAPER's source-loop checkbox is enabled. Repeated, shared pooled and file-backed
MIDI require their own recipe. The example recognizes inline pool identities from
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

The example's `project.py capture --out NEW_DIRECTORY` saves a stopped live project
copy, collects/rebinds ordinary file-backed takes, verifies native reopening, checks
the live state is unchanged, then writes capture.json. Pin that directory with
`tactus material add`; use the tree ref as project_ref in accepted.py and commit
source/Lua/lock/refs before rendering. Native MIDI/FX/routing/automation remain in
the RPP. Inline MIDI and ordinary file takes are handled; wrapped sources,
subprojects/video or missing media require a work-authored recipe. Declare plugin
binaries and plugin-owned libraries/IRs separately; take-media collection cannot
discover every opaque plugin dependency.

Rebuild from a real scratch copy, render the explicitly chosen range in a private
tab and restore the live tab. Material trees can use hardlinks: saving directly
inside material(ref) can corrupt the pool. The recipe retains scratch on failure
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
