# Ableton: create, hand off, co-work and adopt

Use the [bridge setup](../../skills/references/ableton.md) first. The bridge exposes
native Python; the optional MCP server still has only `ableton_status` and
`ableton_execute`. Shared APIs own repeated mechanics; these examples retain authored music and usage.

| Intent | Route |
| --- | --- |
| Inspect actual native state | `project.inspect`, selected-device recipes, or authored native Python |
| Borrow Live/Max/VST sound | `song.py` with a generated Max host/tap; adapt native routing/MIDI for other devices |
| Hand off saved Tactus audio | `project.export_project`, registered as a custom exporter |
| Edit the selected MIDI notes | `ableton.inspect_selection/update_notes` |
| Adjust exposed device parameters | shared `devices.inspect/configure_many`, or `fx.py` |
| Adopt accepted native state/media | `project.capture`, then `tactus material add` |
| Rebuild a pinned native set | `project.rebuild` or `accepted.py` |
| Continue without Live | Pin the run and use `load_render`; `accepted.py` accepts `audio_ref` |
| Browser, automation, warp, listeners, cleanup | [Native recipes](native_recipes.md) |
| Full reference inventory and boundaries | [Reference coverage](coverage.md) |

All read routes share the installed Remote Script's native `state.read` implementation.
Use `ableton.read(bridge_path=connection)` for a shallow track/selection overview;
`scope='track'`, `'notes'` or `'device'` requests targeted detail, with optional runtime
`track_id` / `device_id`. MCP `ableton_status` accepts the same scopes/target IDs.
`project.inspect` uses the explicit full `project` scope, and the selected-note recipe
uses the shared `notes` scope before every guarded edit. Full project reads keep their
original comparison shape. Optional observed revisions are notification hints; every
read is fresh and exact edit guards remain necessary. Live 11's missing selected-note
listener is reported explicitly. See the bridge reference for subscription lifecycle.

Create a work with `tactus init`, copy only the authored musical examples you need, and commit
source/lock/refs before rendering. The included pyproject.toml demonstrates the
export registration; it does not replace work initialization. Use the actual Live
**executable** with `tool()`: the macOS app bundle contains symlinked framework
directories, which the ordinary material/tool tree scanner rejects.

## 1. Live as an audio package

The optional helpers build Max files at explicit new destinations. They do not
load devices, select tracks, change routing or launch a background service.
The Tactus builders use file commands, without the adopted UDP command listener;
the tap also removes MIDI-note record triggers. Authored Max graphs may add their
own I/O deliberately. Generated folders include the adopted MIT license.

```python
from pathlib import Path
from tactus.bridges.ableton_support import max, audio

presets = Path('/absolute/User Library/Presets/Audio Effects/Max Audio Effect')
host = max.build(presets / 'My Host', role='audio_effect')
tap = audio.build(presets / 'My Tap')
```

Each writes `device.json`. Load the AMXDs through `app.browser` on an explicitly
owned audio track: host first, tap second. Inspect the chain after initialization;
never repeat a load because its immediate readback is empty. For `song.py`, use
Monitor In, unmute the fixture and route it to Sends Only, with sends at zero.
The example checks the track ID and exact device names before using it.

```python
# In the work's Python, compose the explicit JSON parameters from these objects.
params = {'bridge_path': '/absolute/User Library/Remote Scripts/TactusMCP',
          'live_binary': '/Applications/Ableton Live 11 Suite.app/Contents/MacOS/Live',
          'track_id': inspected_runtime_track_id, 'host': host, 'tap': tap,
          'frequency': 220}
```

Use `--param-file host=/absolute/MyHost/device.json` and
`--param-file tap=/absolute/MyTap/device.json` to bind those generated objects, and
pass the remaining fields with `--params`. Compare another frequency in a separate run. The example takes four seconds of a continuous
Max oscillator and combines it with authored NumPy parts. This oscillator is example
music, not a bridge requirement: replace its graph, timing, routing and musical data
in the work to use other Max devices, Live instruments or configured VSTs.

`max.command(config, message)` accepts the full adopted object graph/value/WebUI
protocol. For Max 8 use `webui.object='jweb'`; `jweb~` requires a compatible newer Max.
`web_reload` accepts top-level `webui`/`webuis` source/assets. It acknowledges the
scheduled reload; inspect the actual ready/title/state afterward. A graph update
can be acknowledged through `last_reload_command_id` after a WebUI event replaced
the latest status. Inspect `connection_errors` and the resulting signal too.
Commands are synchronous in external Python; waits never sleep in Live's main thread.
Serialize commands for each host/tap. There is no cross-client musical-state lock.

`audio.command(config, 'open', path=NEW_WAV)`, `'start'`, `'stop'`, `'status'` wait
for matching command acknowledgments. The tap writes stereo float32 WAV at Live's
active audio rate. Timeouts mean unknown completion: inspect status/host/files before
resending. An acknowledgment does not establish correct routing, signal or duration;
read/validate the audio, then let `tactus run` create its receipt.

These are real-time captures. Leading silence, scheduler latency, transport alignment,
trimming, resampling and tails remain explicit work decisions. No offline/sample-exact
native regeneration is promised. The chosen saved arrays are the exact replay path:

```bash
tactus material add runs/a
# Put the returned tree ref in source or pass it as voice_ref.
tactus run song.py --out runs/replay --params '{"voice_ref":"tree:sha256:..."}'
```

A WAV `voice_ref` is also accepted, but PCM24 decoding changes low bits before later
DSP. Use the original run tree for identical recomputed mix hashes. Retain its arrays
in the pool. A receipt records source, tools, inputs and parameters; a bridge reply alone
is not a receipt.

## 2. Hand a completed run to Live

Register the shared exporter directly; no lifecycle source copies are needed:

```toml
[tool.tactus.export]
ableton = "tactus.bridges.ableton_support.project:export_project"
```

Use a dedicated Live workspace. Live has one active Set; the exporter saves an
separate recovery Set before replacing it. Its explicit flag is part of the
work's request, not automatic permission to discard unrelated state.

```bash
tactus export ableton runs/a --out exports/live \
  --bridge-path '/absolute/User Library/Remote Scripts/TactusMCP' \
  --tempo 120 --replace-active-set --names '["lead","bass"]' \
  --positions '{"bass":1.5}' --markers '[[0,"A"],[1.5,"Entry"]]'
```

Positions and markers use seconds. Tempo is explicit; map lanes are not interpreted
implicitly. Selected original arrays become FLOAT WAVs without normalization.
Native track/clip creation uses the Live API; warping and fades are disabled and unity
gain is verified. Native save/open and unsupported locator naming use the file adapter
and copied ALS serialization. The native set is reopened and its media/placement checked.
The exporter restores a recovery copy outside the publication directory, because Tactus
publishes exports by moving a staging directory. The delivered ALS uses relative media.
`source.json` preserves the originating run identity/map.

Open `exports/live/native/session Project/session.als` after publication to continue
in Live. This final location has been reopened in the native acceptance probe. The
result also reports the retained recovery copy. Do not delete an active scratch/recovery
folder while Live uses it. This handoff prints selected outputs; it does not reverse
arbitrary Python DSP into editable Live synthesis/MIDI.

The supplied file adapter is verified on macOS / English Live 11. It needs Accessibility
access and the Desktop sidebar entry: it saves a UUID copy there and moves only that
invocation's copy into the requested folder. Close additional Live windows/dialogs first.
Other platforms/languages need an authored file adapter; native Python access remains
available. Interrupted operations retain their stage/scratch for inspection.

## 3. Co-work, adopt, rebuild and replay

Select MIDI notes in the actual detail clip:

```python
from tactus.bridges.ableton import inspect_selection, update_notes

snapshot = inspect_selection(bridge_path=connection)
selected = [dict(n) for n in snapshot['notes'] if n['note_id'] in snapshot['selected']]
# Make the intended pitch/timing/velocity/etc. edits here, preserving IDs/attributes.
changed = update_notes(snapshot, selected, bridge_path=connection)
```

Coordinates use clip-local beats. The native one-use snapshot checks the active
Set/track/detail clip, loop/markers, all notes and exact selected IDs immediately
before editing. A changed selection/note rejects the edit. Inspect again after any
apply/error/reconnect. Other notes/expressions/automation are not replaced. Successful
selected-note edits and their grouped Undo have been verified; not every Live operation
is undoable. No automatic rollback or Undo is performed.

For quick device edits, use `fx.py` or the shared API directly:

```python
from tactus.bridges.ableton_support import devices

snapshot = devices.inspect(bridge_path=connection, track_id=track_id,
                           device_id=device_id, parameters=chosen_names)
snapshot = devices.configure(snapshot, chosen_native_values, bridge_path=connection)
```

Each configure returns actual compact values for the next guarded edit; metadata is
not repeated. `configure_many` preflights all devices before any write. Learn ranges
and enum choices from inspection; values are native, not automatically normalized.
`devices.browse(bridge_path=connection, recursive=True, search='echo')` searches cached
browser descriptions. `devices.append(..., parameters=chosen_native_values)` loads
once, waits and configures after readiness; load/configure remain separate Undo steps.
The same owner is available to MCP native Python as `state.devices`; no new MCP tool
is needed. Refresh stale metadata explicitly and reinspect after a rejected edit.

The CLI accepts inspected IDs and authored JSON, without musical defaults:

```bash
uv run python fx.py --bridge-path /absolute/TactusMCP inspect --track-id TRACK_ID --device-id DEVICE_ID --out fx.json
uv run python fx.py --bridge-path /absolute/TactusMCP apply fx.json values.json
```

Small note/parameter edits return readback without recording or rendering. Audition
inside Live; preserve accepted inputs and run Tactus when delivering audio. The initial
inspection is still needed; a warm next edit reuses its immediately prior snapshot.
Native stale-target/value guards and Undo remain active; partial native errors have no
automatic rollback. Do not reuse a snapshot after an intervening change.

Stop transport and close additional windows, then adopt the accepted set:

```python
from tactus.bridges.ableton_support.project import capture
record = capture(bridge_path=connection, out='captures/chosen')
```

Capture saves a new native copy, collects SampleRef audio, reopens it, verifies media
resolves inside the bundle and compares the inspected MIDI/device/mixer/clip state.
`capture.json` is written last. The verified copy stays active. Native ALS retains
routing, automation and plugin state; the readback is not a lock against concurrent
human edits or every plugin's private state.

For Max, first freeze/collect the device's complete assets into a portable folder,
import it with `tactus material add`, then supply:

```python
record = capture(bridge_path=connection, out='captures/with-max', device_bundles={
    '/absolute/Loaded Device.amxd': 'tree:sha256:...'
})
```

The bundle must contain the exact AMXD at its root, with companions at their authored
relative paths. Capture copies the complete declared tree and rebinds the copy. A static
Max DSP device's edited frequency, bundled source, native reload and recorded 440 Hz
output have been verified. Dynamic hosts must additionally preserve/restore their
accepted graph, values and state; arbitrary patch-internal absolute paths, external
packages and plugin-owned sample libraries cannot be inferred by this collector.
Declare/package those dependencies in the work, or print the accepted audio.

```bash
tactus material add captures/chosen
# Commit the returned ref and source/lock before rendering.
tactus run accepted.py --out runs/chosen \
  --param-file tap=/absolute/MyTap/device.json \
  --params '{"project_ref":"tree:sha256:...","bridge_path":"/absolute/TactusMCP","live_binary":"/absolute/Live","tap_browser_path":["Presets","Audio Effects","Max Audio Effect","MyTap","Tactus Audio Tap"],"seconds":8,"replace_active_set":true}'
```

Native mode needs `project_ref`, `bridge_path`, `live_binary`, `tap`, its exact
`tap_browser_path`, `seconds`, and `replace_active_set=true`. It saves recovery,
opens a real writable copy of the pinned bundle and records through a master tap.
The pool is never opened/saved by Live. This example captures **before the master fader**
and retains leading timing/latency; adapt it for a different recording boundary.
The successful scratch/recovery remains active and its path is reported.

For host-free exact replay, pin the selected run and pass its tree ref as `audio_ref`
to `accepted.py`. Compare output hashes before claiming equality. Native regeneration,
accepted audio replay and musical approval are distinct claims.

## Verification and reference

The baseline is Live 11.3.43 / embedded Python 3.7.3 / Max 8.5.8 on macOS. Native
library audio, three-flow lifecycle, guarded MIDI, bundled static Max, WebUI reload,
console capture, preview and browser-loaded VST3 Device On have real-host evidence.
Live 12-only APIs/analysis schemas and other platforms remain conditional. One Max
scheduler crash occurred during overlapping exploratory operations and could not be
reproduced in isolated repeated reload tests; uninterrupted playback is not guaranteed.

Ordinary contract tests live in `tests/test_ableton_*.py`, adopted MIT tests in
`tests/ableton_reference/`, and the folder-import regression in `tests/test_tree.py`.
Opt into the existing small native fixture tests only on an isolated workspace using
`TACTUS_ABLETON_PATH`. Source-string/fake-platform tests are not native acceptance.

For a simple exposed Max parameter → JS acknowledgment, `max_control.py` remains an
editable MIDI-effect example. Build it with `--template EMPTY_MAX_MIDI_EFFECT.amxd
--out NEW_USER_LIBRARY_FOLDER`, browser-load it and change its inspected parameter.
VST private controls/preset browsers require the plugin's exposed/configured interface;
no universal private plugin API is assumed.
