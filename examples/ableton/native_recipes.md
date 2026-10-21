# Native Live vocabulary

These snippets run **inside** `ableton.execute` / `ableton_execute`, with Live's
embedded Python. They are editable vocabulary, not new tools or a mandatory object
model. Inspect the exact selected target first and supply expectations through `args`.
Live 11 embeds Python 3.7; external Python packages are not automatically available.

## Browser search, preview and insertion

Read one level, then follow an explicit path. `root.children` and native objects
must be converted before returning JSON. A recursive search can use ordinary Python
with an explicit traversal budget; report budget exhaustion rather than silently
returning an incomplete set.

```python
root = app.browser.plugins
result = [{'name': c.name, 'loadable': c.is_loadable} for c in root.children]
```

For an inspected sample item, `app.browser.preview_item(item)` and
`app.browser.stop_preview()` use Live's browser preview bus. Preview is separate
from loading. `app.browser.hotswap_target` must be inspected before loading; loading
can replace an instrument. `track.insert_device` is version dependent. On the tested
Live 11, use `song.view.selected_track`, `song.view.select_device` and
`app.browser.load_item` with a known target/chain and verify the settled result.

## MIDI and Arrangement

```python
clip = song.view.detail_clip
assert clip is not None and clip.is_midi_clip
fields = ('note_id', 'pitch', 'start_time', 'duration', 'velocity', 'mute',
          'probability', 'velocity_deviation', 'release_velocity')
result = [{key: getattr(n, key) for key in fields}
          for n in clip.get_all_notes_extended()]
```

Create notes using `Live.Clip.MidiNoteSpecification`, then `clip.add_new_notes`.
For existing notes, retrieve the vector with `get_notes_by_id`, change its fields,
then `apply_note_modifications`. `cowork.py` / `selection.py` implements a guarded
selected-note example, including current selection, all note fields and one-use tokens.

`track.duplicate_clip_to_arrangement(clip, beat)` copies a Session clip into
Arrangement. `track.create_audio_clip(absolute_path, beat)` and
`slot.create_audio_clip(absolute_path)` create file-backed audio clips. Select the
exact intended resulting clip; do not assume the last track/clip is still yours.

## Automation, including an authored velocity mapping

A clip envelope controls an actual native parameter. The mapping below is an
explicit artistic choice; change the range, shape and timing in the work.

```python
track = song.view.selected_track
clip = song.view.detail_clip
parameter = track.mixer_device.volume
envelope = clip.automation_envelope(parameter)
if envelope is None:
    envelope = clip.create_automation_envelope(parameter)
for note in clip.get_all_notes_extended():
    value = note.velocity / 127.0
    envelope.insert_step(note.start_time, note.duration, value)
result = [envelope.value_at_time(n.start_time + n.duration / 2)
          for n in clip.get_all_notes_extended()]
```

Other native methods include `events_in_range`, `delete_events_in_range`,
`clip.clear_envelope(parameter)` and `clear_all_envelopes`. Preserve unrelated
ranges deliberately; an envelope's existence is not proof it contains the expected
points. Read actual event/value results after editing.

## Warp markers

```python
clip = song.view.detail_clip
assert clip is not None and clip.is_audio_clip
clip.warping = True
clip.add_warp_marker(Live.Clip.WarpMarker(args['sample_seconds'], args['beat']))
result = [{'sample_time': m.sample_time, 'beat_time': m.beat_time}
          for m in clip.warp_markers]
```

`move_warp_marker(beat_time, beat_time_distance)` and
`remove_warp_marker(beat_time)` operate on the inspected marker. Native
`warp_mode` / `available_warp_modes` expose available choices. Read back the result;
clip file time and musical beat time are different units.

## Observe, retrieve events, then detach

A listener remains a native Python callback; it is not a new polling service.
This example uses a namespaced `builtins` slot because each execute has a fresh
namespace. Limit stored events according to the work's needs and remove listeners
before deleting their targets. Reopening a Set invalidates its native objects.

```python
import builtins
assert not hasattr(builtins, '_tactus_tempo_watch'), 'Detach the previous watcher'
events = []
def changed():
    events.append(song.tempo)
builtins._tactus_tempo_watch = (song, changed, events)
song.add_tempo_listener(changed)
```

In a later call:

```python
import builtins
observed_song, callback, events = builtins._tactus_tempo_watch
result = list(events)
observed_song.remove_tempo_listener(callback)
del builtins._tactus_tempo_watch
```

Make mutations outside observer notifications or use the relevant deferred native
mechanism. In Max use `live.thisdevice` for initialization and defer observer-driven
writes with `deferlow`; Max object IDs and Python `_live_ptr` values differ.

## Transport, Undo and exact cleanup

`song.start_playing()` / `stop_playing()` request transport changes; read in a later
call because the immediate `is_playing` value can still be the old value. Native
`current_song_time` uses beats. `song.undo()` / `redo()` remain explicit operations,
with no universal rollback promise.

To remove an owned temporary device, inspect exact track/device identities and chain
before deleting. A prefix alone does not establish ownership:

```python
track = next(t for t in list(song.tracks) + [song.master_track]
             if str(t._live_ptr) == args['track_id'])
assert [str(d._live_ptr) for d in track.devices] == args['chain'], 'Chain changed'
index = args['device_index']
assert str(track.devices[index]._live_ptr) == args['device_id'], 'Device changed'
track.delete_device(index)
result = [d.name for d in track.devices]
```

The same principle applies to generated Max hosts/taps. Do not delete the user's
upstream devices, controller scripts or state directory as part of cleanup.
