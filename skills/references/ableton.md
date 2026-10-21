# Ableton bridge

Tactus sends ordinary Python to Live's native API through `execute`; `read` supplies
shared fresh snapshots for conversational inspection and work lifecycle checks.
Musical choices, Max patches and VST choices stay in the work; shared helpers own
repeated target checks, metadata queries and load/configure completion.
The optional MCP entry exposes `ableton_status`, `ableton_execute`, and shared
`tactus_connections` discovery.
No additional agent, musical model, API whitelist or plugin-specific tools are required.

## Install once

Install Tactus with the optional extra if using MCP. From the checkout:

```bash
uv tool install --python 3.12 --editable '.[mcp]'
uv run tactus connect
```

`tactus connect` installs the bundled **TactusMCP directory** into
`User Library/Remote Scripts/`. No separate download or manual copy is needed.
Use `--live-library DIR` when Live's User Library is elsewhere; use `--check` to
inspect without changing files.
The default macOS location is `~/Music/Ableton/User Library/Remote Scripts/TactusMCP`;
Windows uses `Documents/Ableton/User Library/Remote Scripts/TactusMCP`.
Use the actual User Library location if customized.

Restart Live, then select **TactusMCP** in an unused Control Surface slot under
Preferences → Link/Tempo/MIDI (Settings → MIDI in newer versions). Input and Output
can remain None; this bridge does not need MIDI ports. If upgrading from
`TactusBridge`, replace that slot with `TactusMCP`. Keep other controller scripts.
The previous `TactusBridge` folder remains available during migration; remove it
after the new script is verified. See [Ableton's installation instructions](https://help.ableton.com/hc/en-us/articles/209072009-Installing-third-party-remote-scripts).

`bridge_path` below is that **installed script directory**, not its `tactus-bridge`
subdirectory or the packaged source. Live and the caller must share the filesystem
and have write access there. The script creates its local queue when activated.
Treat this as full trusted Python/native/file access, just like a work's own code.
Setup does not save, launch or quit Live, or change its Control Surface selection.
It edits agent-host configuration only with `--host codex`. After updating Tactus,
rerun `tactus connect` and restart Live. Differing installed files are backed up.

## Ordinary Python

```python
from tactus.bridges import ableton

selected = ableton.execute(
    "result = {'name': song.view.selected_track.name, 'tempo': song.tempo}",
    bridge_path="/absolute/User Library/Remote Scripts/TactusMCP",
)
```

`execute(code, *, bridge_path, args=None, timeout=30, undo=None)` is synchronous.
Code executes on Live's main thread with `Live`, `song`, `app`, `state`, `args` and
`result=None`. Assign `result` to return finite JSON data; native objects, handles,
parameters and vectors must be converted to explicit data. Native list/tuple results
become JSON lists; dict keys must be strings. Results are not silently truncated.
`args` accepts finite JSON only and is bound as data, never interpolated as Python.
Diagnostic prints go to the caller's stderr, leaving protocol stdout clean.
The installed Remote Script source files are declared with `tool()` for run provenance;
declare the Live application/plugins and preserve accepted native state separately.

The host runs Tactus's Python; the code string runs **Live's embedded Python**.
For example, the verified Live 11 installation embeds Python 3.7.3, so code strings
cannot use Python 3.12 syntax or assume the work's packages are installed inside Live.
Inspect `sys.version`, `dir()` and actual object properties when discovering an API.
Use the version-matched [Max 8 Live API overview](https://docs.cycling74.com/legacy/max8/vignettes/live_api_overview)
and [Live Object Model](https://docs.cycling74.com/apiref/lom/) as starting points.
These describe Max-facing object relationships/access, **not a complete specification
of Python Remote Scripts**. Python access and available methods depend on Live's
installed version and must be probed. Python `_live_ptr` identities are not Max's
device-scoped `id N` values; never interchange the two.

Use short native operations. Long computation, sleeps or rendering in a code string
block Live's main thread. Generate note data or files in the work's Python first,
then pass explicit values or accessible paths to native Python.

## Shared reads and observed changes

```python
summary = ableton.read(bridge_path=connection)
track = ableton.read(bridge_path=connection, scope="track",
                     track_id=summary["track_list"][0]["id"])
notes = ableton.read(bridge_path=connection, scope="notes")
device = ableton.read(bridge_path=connection, scope="device")
```

`connection` is the installed Remote Script directory. `read` uses the same execute
transport, with optional `timeout=30`. It reads native state without selecting objects,
saving files or editing the music. Explicit runtime IDs must still exist in their
target track; a missing target raises an error instead of selecting a substitute.

| Scope | Native data read |
| --- | --- |
| `summary` (default) | Versions, project identity/path, tempo/transport, track names/IDs, selection and observed changes. No MIDI vectors or device parameter values. |
| `track` | Selected or explicit `track_id`: mixer, clip metadata/placement and device names/IDs. No MIDI vectors or device parameter values. |
| `notes` | The MIDI detail clip on the selected or explicit track: all extended notes/IDs, actual selected IDs, loop and markers. Same shape as the guarded-edit recipe. |
| `device` | Selected or explicit `device_id` within the selected/explicit track, including nested devices: exposed parameter values/ranges, shallow chain contents and observed changes. |
| `project` | Full lifecycle snapshot: all regular-track clips/notes and recursive devices/parameters, master/return mixer/devices and locators. Same shape as the original capture reader. |

Use `track_id` with track/notes/device and `device_id` with device. Omitted targets
use the current selection. Each scope is one short native request; a large explicit
project read can occupy Live's main thread. Ask for detail only when needed. The
project snapshot is a lifecycle comparison, not an inventory of all plugin-private
state, automation or dependencies; the native ALS and authored dependencies retain
those responsibilities.

Inside `execute`, use `result = state.read(scope='notes')` or combine a read with native
target checks/operations in the same request. This is the same reader used by MCP and
the project/selected-note examples; ordinary native Python remains available.

`summary` and `device` include `changes`: a reader `instance`, monotonic `revision`,
per-group `versions`, subscription count, `observed` properties and `unsupported`
listeners. Inside execute, `state.changes()` reads that metadata directly. Compare
revisions only within the same instance. Each read still fetches fresh values;
there is no cached musical-state snapshot and no comprehensive content revision.

Listeners follow the Set/selection, track names and the current MIDI detail clip.
After a device read, they also observe the most recently requested device's exposed
parameters and containing chain; another device read replaces that target. The
existing main-thread poll reconciles topology/selection changes and removes old or
deleted targets; disconnect removes the remaining subscriptions. Callbacks only
advance counters and request reconciliation. Live 11 does not expose the tested
`Clip.selected_notes` listener: this is reported as unsupported, and selection is
read directly whenever requested. Notifications never replace exact pre-edit checks.

## Existing conversation through MCP

Start one Tactus MCP server for both Live and REAPER:

```bash
tactus-mcp
```

For a checkout environment, `uv sync --extra mcp` then
`uv run python -m tactus.mcp` is equivalent.
`tactus mcp` also works through the work's selected environment. The command
finds both installed bridge directories; use
`--live-path /absolute/User Library/Remote Scripts/TactusMCP` for a custom Live
location. It exposes two native tools per DAW plus `tactus_connections`; either DAW
can be unavailable while the
other remains usable. `tactus-mcp live` and `tactus-mcp reaper` remain available
for single-DAW connections. The older `--ableton-path DIR` and REAPER
`--resource-path DIR` launch forms also work.

Example host configuration (use absolute executable/path values):

```json
{
  "mcpServers": {
    "tactus-mcp": {
      "command": "/absolute/path/to/tactus-mcp",
      "args": []
    }
  }
}
```

The server can start while Live is unavailable. `ableton_status` returns setup paths
and a reason; once the script is active, the same MCP connection can read the set.
Status uses the shared `summary` reader by default. Its optional `scope`, `track_id`
and `device_id` arguments request the same detail as ordinary Python. For example,
`{"scope":"notes"}` reads selected MIDI context, and
`{"scope":"device","track_id":"TRACK_RUNTIME_ID","device_id":"DEVICE_RUNTIME_ID"}`
reads one inspected device. The outer response remains `{"status":"ready", ...,
"project": SNAPSHOT}`. A no-argument call remains compatible and additionally lists
track names/IDs and observed change metadata.
Runtime IDs do not survive restarting/reopening Live and are not edit guards.
Status does not claim access to every GUI selection or an Arrangement time range.

One Live process has one active Set. `tactus_connections` lists each connected Live
process and that Set's runtime `project_id`. Pass its `connection_id` and `project_id`
to status/execute for guarded work: switching the Set or restarting Live makes the
old target fail before authored code runs. Multiple Live processes using the same
installed Remote Script now have separate queues. With more than one, an omitted
connection ID fails rather than choosing a process. After updating the installed
Remote Script, reload it in Live to activate this behavior. A legacy fixed queue
still serves omitted-target calls but cannot guard explicit targets.

`ableton_execute` accepts the same `code`, `args`, `timeout`, `undo` fields and returns
`{"result": ...}`. Native failures are tool errors. Native browser, parameter and
Max recipes live in `examples/ableton/` in the matching Tactus source distribution.
A plugin-cache copy contains this reference; executable examples come from the
runtime source, as with the REAPER examples.

## Completion, edits and Undo

Requests carry an instance ID and expiry. A main-thread poll claims one request at
a time, skips expired/old-instance work, and atomically writes its response. Offline,
stale, malformed and incompatible connections fail visibly. A stale heartbeat can
also mean Live is busy or blocked; it is not proof that Live exited.

On timeout, the caller withdraws any still-queued request and raises `BridgeTimeout`.
Already-running Python continues. The error identifies the retained late response
path; inspect it and native state before deciding what to do next. No automatic retry,
rollback, or automatic Undo occurs. Old running files may remain after a Live crash;
they are not re-executed at startup. Native exceptions retain partial mutations.

A nonempty `undo` label requests `song.begin_undo_step()` / `end_undo_step()` around
the operation, including errors and result-serialization failures. **Live supplies
the displayed Undo description**; the supplied label expresses caller intent and is
not an API for renaming Live's Undo menu. Not every native action is undoable. In the
Live 11 probe, grouped track gain/pan restored together, while a tempo/meter probe
left the changed meter after Undo. Check the specific operation; do not claim
transactional rollback.

MCP calls serialize per DAW. Cancellation waits for the native worker to
finish or time out before releasing that DAW's worker; it cannot stop running
Python. Other clients and human edits are not locked. Inspect the exact target and
relevant notes/parameters immediately before writing, and read back afterwards.
Track indexes, names, runtime IDs and the status snapshot alone are insufficient
for checking all intervening edits. Keep these checks in work-authored native code.

## Max for Live and VST

Use `app.browser` to discover and load devices, then inspect native `device.parameters`.
Set a specific selected track and inspect hotswap/selected-device state before loading:
depending on device type and browser context, loading can replace an instrument.
Live 11 does not provide the newer `track.insert_device` used by some other bridges.
Device loading and Max initialization/indexing may settle after the call returns;
read back in a later short call. Re-reading is safe; blindly repeating a load can
insert a second device.

For VST/VST3, Live remains the host. MIDI, routing and exposed parameters use the same
native interface as other devices. Some plugins initially expose only Device On;
publish desired controls through Live's Configure mode or a configured Rack/preset.
Internal sample browsers, private controls and proprietary preset systems have no
universal Live API. See [Ableton's Configure documentation](https://www.ableton.com/en/live-manual/12/using-plug-ins/#plug-in-configure-mode).

For Max, author ordinary `.maxpat`, JavaScript and device files, then load the `.amxd`
through the browser and control exposed parameters. The bridge is not a Max patching
language or a realtime DSP host. Optional Max receivers/audio taps can be authored as
devices when needed; their files/protocols remain explicit work inputs.
The included Max control recipe builds an unfrozen device using the user's own empty
template and verifies JS acknowledgment of an exposed parameter; it is not a frozen
dependency/externals packager. Live 11 requires Max 8-compatible objects;
[Max 9 is not supported inside Live 11](https://support.cycling74.com/hc/en-us/articles/360049845974-Common-questions-about-Max-for-Live).
Inside a Max patch, use `live.path`, `live.object`, `live.observer` or JS `LiveAPI`
when accessing Live itself. Initialize such access through `live.thisdevice` after
Live's API is ready; defer mutations originating from observer notifications using
`deferlow` or the appropriate deferred JS mechanism. These Max execution rules do not
turn the main bridge into a Max-hosted command service.

## Audio, handoff and accepted native work

Shared execution mechanics are available without copying example files:

- `ableton.inspect_selection/update_notes`: fresh one-use selected-note edits. Inside
  native MCP execute use `state.selection.inspect()` / `state.selection.update(token, notes)`;
  pass `undo` on the execute request when grouping edits. `state.track(id)` resolves an
  exact native track without changing selection. Musical note values remain explicit.
- `ableton_support.devices.append(browser_path, bridge_path=..., track_id=...,
  expected_chain=[device_ids], parameters=chosen_values)`: exact browser path and chain
  checks, one load, then optional explicit native settings and fresh compact completion
  readback. Omit `parameters` to retain the original `{id, name, class}` result; with
  settings or `metadata=True`, the result includes `snapshot`. Use `uri` to distinguish
  same-name final browser entries. Load and configure have separate Undo steps; no
  group spans the settling ticks. This appends to a track; arbitrary rack/insertion/replacement
  remains native Python. Unknown completion or a changed chain is never retried.
- `ableton_support.devices.inspect/configure/configure_many`: learn selected parameter
  names/IDs, ranges and enum choices once, then batch caller-chosen native values and
  use returned compact actual values as the next edit's snapshot. Every batch freshly
  checks the reader epoch, device identity/layout, all observed values, enabled state
  and ranges before any write. A stale snapshot rejects; native setter errors can
  leave partial changes. There is no automatic retry or rollback. Use `metadata=False`
  for value reads once descriptions are known. Native MCP code calls the same owner:
  `state.devices.inspect(track_id, device_id, parameters=[...])` and
  `state.devices.configure([{'snapshot': snapshot, 'values': chosen_values}])`, with
  an explicit execute `undo` label. Values use each parameter's native scale.
- `ableton_support.devices.browse`: reusable browser metadata by `root`, optional
  child `path`, `search`, `recursive`, `include_presets` and `refresh`. Native MCP uses
  `state.devices.browse(...)`. Loadable entries are not descended unless presets are
  requested; narrow queries exceeding the traversal limit. Catalogs clear on native
  browser full-refresh when available, explicit refresh or reader close/Set replacement.
  Names/URIs are inventory, not proof of authorization or tested audio; loading always
  resolves a fresh native item. Parameter descriptions are bounded per-reader caches;
  target handles only validate identity, and musical values are never cached.
- `ableton_support.transport.playing`: a context manager owning start/stop completion
  for an explicitly chosen Arrangement/Session performance. Supply `mode`, `start_beat`;
  Session also needs `track_id`, `clip_id`, `launch_quantization` (e.g. `q_no_q`).
  Use an owned stopped workspace; the context leaves transport stopped.
- `ableton_support.audio.record(config, path=...)`: recording around caller code,
  with correlated acknowledgments and one stop cleanup attempt after a start attempt.
  A file must decode and contain frames; silence is valid. One caller owns each tap.
- `ableton_support.audio.capture(config, perform)`: own temporary recording/decoding,
  return `(audio, rate)` with original timing/tails/amplitude, retain failures for
  inspection. `perform()` chooses playback, duration and routing. Known AMXD/JS
  companions are declared with `tool()` by tap recording and Max commands.
- `ableton_support.project.capture/rebuild/export_project`: save/collect/verify native
  state, rebuild a writable material copy, or hand off selected outputs. Declare the
  callable directly as `tactus.bridges.ableton_support.project:export_project` under
  `[tool.tactus.export]`; no project/macOS adapter source copies are needed.

For example, in the work's ordinary Python (not inside Live's embedded interpreter):

```python
import time
from tactus.bridges.ableton_support import audio, transport

def perform():
    with transport.playing(bridge_path=connection, mode='arrangement', start_beat=0):
        time.sleep(seconds)  # An authored duration.

captured, sample_rate = audio.capture(tap, perform)
# Choose alignment, excerpt, gain, DSP and adoption here.
```

The source distribution's `examples/ableton/` demonstrates authored sound/routing,
performance windows and replay. `cowork.py`, `selection.py` and the lifecycle exports
in `project.py` are compatibility adapters to these shared owners. `accepted.py`
continues a pinned project or saved audio. Use `tactus init`, commit source/lock/refs,
and render with `tactus run`; a native reply alone is not a render receipt.

Other optional modules provide `max.build/command`, `audio.build/command`,
`visual.capture/max_console` and read-only `similar.find`.
They reuse MIT mechanisms from [bschoepke/ableton-live-mcp](https://github.com/bschoepke/ableton-live-mcp)
at `89f3b4ef4663e33b40ee47bda75d16f9b0ade9a8`, with source/license/patch notes in the
runtime's `ableton_support/UPSTREAM.md`. No additional MCP tools are introduced.
Generated host/tap assets go to explicit new folders; state defaults to
`~/.tactus/ableton` (`TACTUS_ABLETON_STATE_DIR` can override it). The Tactus builders
use file commands without implicit UDP listeners or MIDI-note record triggers.
Max patches can still author any native objects, code, I/O and UI explicitly.

Tap audio is stereo float32 at Live's active sample rate. Real-time capture retains
its actual timing; alignment/trimming/resampling/tails belong to the work. A master
capture recipe records before its fader. Native regeneration can vary; pin the saved
run tree and use `load_render` for exact original-array replay. Published PCM WAVs
are useful materials but requantization can change subsequent DSP's lowest bits.

Handoff uses native track/clip operations, explicit tempo, seconds for placement and
markers, FLOAT media and disabled warping/fades. The copied ALS is reopened, checked
and retains relative media after export publication. A macOS file-dialog adapter
handles save/open because no usable native Python file-lifecycle API was found on
Live 11. It needs English menus, Accessibility and a Desktop sidebar entry; other
platforms/languages need their own adapter. It stages only a UUID-named copy, moves
that copy into the destination and retains incomplete state on failure.

Live has one active Set. Export/rebuild require an explicit dedicated workspace and
`replace_active_set=True`, save recovery before replacing it and keep writable copies
outside the material pool. Export restores its recovery Set before Tactus publishes
the destination; open the final delivered ALS afterwards. Capture leaves its verified
copy active. A native GUI Set is external input until the completed bundle is pinned
with `tactus material add` and its ref is adopted in the work.

The shared project capture collects audio SampleRefs and preserves the native ALS. For Max,
supply `device_bundles[absolute_amxd]=tree_ref`: a collected/frozen folder containing
the exact AMXD and all companions at their authored relative paths. The complete tree
is copied and rebound; pool assets are never saved by Live. Dynamic graph/value state,
patch-internal absolute paths, external Max packages, plugin binaries/libraries and
hardware need explicit authored dependency handling. Printing accepted audio remains
available without reverse-engineering those dependencies.

The shared selected-note API uses actual detail clip/selected IDs, clip-local beats and
full extended note attributes. One-use snapshots reject intervening note/selection
changes, preserve unselected notes and group successful edits for native Undo. It
does not infer an unavailable GUI Arrangement time selection. Broader edits remain
ordinary native Python with operation-specific guards.

## Verified scope

Live 11.3.43 / embedded Python 3.7.3 / Max 8.5.8 on macOS has real-host evidence for
native execution, MIDI/automation/warp/listeners, operation-specific Undo, Max/VST3
loading and exposed parameters, stereo audio return, WebUI page-to-DSP control and
reload, console/window capture, and the three native handoff/adoption/replay flows.
A bundled static Max device retained its edited frequency after native rebuild and
recorded 440 Hz audio. Original pinned bundles remained unchanged.

The 38 reference capabilities are mapped in the source distribution's
`examples/ableton/coverage.md`; ordinary native methods replace the RPC vocabulary.
Live 11 lacks the newer `track.insert_device`; browser insertion is the measured
fallback. Similarity search requires the reference's compatible analyzed database
schema; this machine's Live 11 database lacks required columns and fails clearly.
Supported-schema fixtures are not a claim of real Live 12 acceptance. Max 8 uses
`jweb` for the verified WebUI; newer `jweb~` DSP needs a compatible Max version.
Max status is an upstream bounded summary with explicit truncation flags, not a
complete accepted-state snapshot. Native Python JSON results are not truncated.

Other platforms/versions and arbitrary private plugin controls are not established.
One Max scheduler crash occurred during overlapping exploratory operations and did
not reproduce in isolated repeated reload tests. No uninterrupted-playback guarantee
is made; keep native operations short and serialize access to each Max host/tap.
