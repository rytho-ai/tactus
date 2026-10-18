"""Shared native reader contracts; these fixtures do not establish native Live support."""

import ast
import itertools
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tactus.bridges.TactusBridge.state import LiveState

_IDS = itertools.count(1)


class Native:
    def __init__(self, observable=(), **values):
        self._live_ptr = next(_IDS)
        self.observable = set(observable)
        self.listeners = {}
        self.__dict__.update(values)

    def __getattr__(self, name):
        for prefix in ('add_', 'remove_'):
            if name.startswith(prefix) and name.endswith('_listener'):
                prop = name[len(prefix):-len('_listener')]
                if prop in self.observable:
                    callbacks = self.listeners.setdefault(prop, [])
                    return callbacks.append if prefix == 'add_' else callbacks.remove
        raise AttributeError(name)

    def emit(self, prop):
        for callback in list(self.listeners.get(prop, [])):
            callback()


class Device(Native):
    def __init__(self, **values):
        super().__init__(observable=('name', 'parameters'), **values)
        self.parameter_reads = 0
        self._parameters = [Native(observable=('value',), name='Cutoff', value=.5,
                                   min=0, max=1, is_quantized=False)]

    @property
    def parameters(self):
        self.parameter_reads += 1
        return self._parameters


@pytest.fixture
def host():
    note = SimpleNamespace(note_id=7, pitch=60, start_time=.25, duration=.5, velocity=90,
                           mute=False, probability=1., velocity_deviation=0., release_velocity=64.)
    reads = []

    def notes():
        reads.append('all')
        return [note]

    clip = Native(observable=('notes', 'name', 'loop_start'), name='Clip', start_time=0,
                  end_time=4, looping=True, loop_start=0, loop_end=4, start_marker=0,
                  end_marker=4, is_midi_clip=True, length=4,
                  get_all_notes_extended=notes, get_selected_notes_extended=lambda: [note])
    device = Device(name='Instrument', class_name='Operator', can_have_chains=False)

    def track(name, clips):
        return Native(observable=('name', 'devices'), name=name, mute=False, solo=False,
                      mixer_device=SimpleNamespace(volume=SimpleNamespace(value=.8),
                                                   panning=SimpleNamespace(value=0)),
                      devices=[], arrangement_clips=[], clip_slots=clips,
                      view=Native(observable=('selected_device',), selected_device=None))

    lead = track('Lead', [SimpleNamespace(has_clip=True, clip=clip)])
    lead.devices = [device]
    lead.view.selected_device = device
    bass = track('Bass', [])
    master = track('Master', [])
    view = Native(observable=('selected_track', 'detail_clip'), selected_track=lead, detail_clip=clip)
    song = Native(observable=('tempo', 'tracks', 'is_playing', 'return_tracks'),
                  view=view, tracks=[lead, bass], return_tracks=[], master_track=master,
                  scenes=[1], file_path='/work/set.als', name='Set', is_playing=False,
                  current_song_time=0, tempo=120, signature_numerator=4, signature_denominator=4,
                  cue_points=[SimpleNamespace(time=0, name='A')])
    app = SimpleNamespace(get_major_version=lambda: 11, get_minor_version=lambda: 3,
                          get_bugfix_version=lambda: 43)
    state = LiveState(song, app, 'epoch')
    yield SimpleNamespace(state=state, song=song, clip=clip, device=device, lead=lead,
                          bass=bass, master=master, reads=reads, note=note, app=app)
    state.close()


def test_shallow_reads_list_targets_without_notes_or_device_parameters(host):
    summary = host.state.read()
    assert summary['tracks'] == 2
    assert summary['track_list'] == [{'id': str(host.lead._live_ptr), 'name': 'Lead'},
                                     {'id': str(host.bass._live_ptr), 'name': 'Bass'}]
    assert summary['detail_clip']['id'] == str(host.clip._live_ptr)
    detail = host.state.read('track')
    assert detail['session'][0]['id'] == str(host.clip._live_ptr)
    assert 'notes' not in detail['session'][0]
    assert 'parameters' not in detail['devices'][0]
    assert host.reads == [] and host.device.parameter_reads == 0


def test_notes_retain_exact_guard_shape_and_attributes(host):
    assert host.state.read('notes') == {
        'song': str(host.song._live_ptr), 'track': str(host.lead._live_ptr),
        'clip': str(host.clip._live_ptr), 'loop': [0, 4, True], 'markers': [0, 4],
        'notes': [vars(host.note)], 'selected': [7],
    }
    assert host.device.parameter_reads == 0


def test_full_project_preserves_legacy_capture_shape(host):
    snapshot = host.state.read('project')
    assert snapshot == {
        'runtime_id': str(host.song._live_ptr), 'path': '/work/set.als', 'playing': False,
        'tempo': 120, 'meter': [4, 4], 'tracks': [
            {'name': 'Lead', 'mute': False, 'solo': False, 'gain': .8, 'pan': 0,
             'devices': [{'name': 'Instrument', 'class': 'Operator',
                          'parameters': [{'name': 'Cutoff', 'value': .5}]}],
             'arrangement': [], 'session': [
                 {'name': 'Clip', 'start': 0, 'end': 4, 'loop': [True, 0, 4],
                  'markers': [0, 4], 'midi': True,
                  'notes': [{k: v for k, v in vars(host.note).items() if k != 'note_id'}]}]},
            {'name': 'Bass', 'mute': False, 'solo': False, 'gain': .8, 'pan': 0,
             'devices': [], 'arrangement': [], 'session': []}],
        'master': {'name': 'Master', 'gain': .8, 'pan': 0, 'devices': []},
        'returns': [], 'cues': [[0, 'A']],
    }


def test_explicit_targets_do_not_change_selection_or_fall_back(host):
    assert host.state.read('track', track_id=str(host.bass._live_ptr))['name'] == 'Bass'
    assert host.song.view.selected_track == host.lead
    with pytest.raises(ValueError, match='no longer present'):
        host.state.read('track', track_id='deleted')
    with pytest.raises(ValueError, match='no longer in'):
        host.state.read('device', device_id='deleted')
    with pytest.raises(ValueError, match='mismatch'):
        host.state.read('notes', track_id=str(host.bass._live_ptr))
    with pytest.raises(ValueError, match='device_id requires'):
        host.state.read(device_id='irrelevant')


def test_device_detail_observes_values_and_detaches_deleted_target(host):
    detail = host.state.read('device')
    assert detail['parameters'][0]['value'] == .5
    parameter = host.device._parameters[0]
    parameter.value = .75
    parameter.emit('value')
    assert host.state.read('device')['parameters'][0]['value'] == .75
    assert host.state.changes()['versions']['parameters'] == 1
    host.lead.devices = []
    host.lead.view.selected_device = None
    host.lead.emit('devices')
    host.state.refresh()
    assert not parameter.listeners['value']
    assert not host.device.listeners['parameters']


@pytest.mark.parametrize('closing', [False, True], ids=['poll-after-delete', 'close'])
def test_invalidated_native_listeners_do_not_block_cleanup_or_queued_reads(
        host, tmp_path, monkeypatch, closing):
    import json
    import time

    from tactus.bridges.TactusBridge.bridge import RequestQueue

    class ArgumentError(TypeError):
        """Boost.Python rejects handles whose native target has been deleted."""

    host.state.read('device')
    invalidated = [s for s in host.state._subscriptions.values()
                   if s[0] is host.device or s[0] in host.device._parameters]
    attempted = []

    def deleted_handle(callback):
        attempted.append(callback)
        raise ArgumentError('Native object no longer matches the C++ signature')

    for obj, prop, _callback, _label in invalidated:
        monkeypatch.setattr(obj, 'remove_' + prop + '_listener', deleted_handle)

    host.lead.devices = []
    host.lead.view.selected_device = None
    host.lead.emit('devices')
    queue = RequestQueue(tmp_path)
    queue._state = host.state
    try:
        if closing:
            subscriptions = list(host.state._subscriptions.values())
            queue.close()
            assert not host.state._subscriptions
            for obj, prop, callback, _label in subscriptions:
                if obj is not host.device and obj not in host.device._parameters:
                    assert callback not in obj.listeners[prop]
        else:
            request = {'id': 'after-delete', 'protocol': 1, 'instance': queue.instance,
                       'expires': time.time() + 5, 'code': 'result=state.read()',
                       'args': None, 'undo': None}
            (queue.root / 'requests/after-delete.json').write_text(json.dumps(request))
            queue.poll(lambda: {'song': host.song, 'app': host.app})
            reply = json.loads((queue.root / 'responses/after-delete.json').read_text())
            assert reply['ok'], reply
            assert reply['result']['selected_device'] is None
            assert not host.state._refresh_needed
            assert all(s not in host.state._subscriptions.values() for s in invalidated)
            host.song.tempo = 123
            host.song.emit('tempo')
            assert host.state.read()['changes']['versions']['song'] == 1
        assert len(attempted) == len(invalidated)
    finally:
        queue.close()


def test_notifications_rebind_selection_without_reading_notes(host):
    first = host.state.read()['changes']
    assert 'Clip.notes' in first['observed']
    assert 'Clip.selected_notes' in first['unsupported']
    host.song.view.detail_clip = None
    host.song.view.selected_track = host.bass
    host.song.view.emit('selected_track')
    changed = host.state.read()
    assert changed['selected_track']['name'] == 'Bass'
    assert changed['changes']['revision'] > first['revision']
    assert not host.clip.listeners['notes']
    assert not host.lead.view.listeners['selected_device']
    assert host.bass.view.listeners['selected_device']
    assert host.reads == [] and host.device.parameter_reads == 0


def test_unobserved_mutation_is_still_read_fresh(host):
    first = host.state.read()['changes']
    host.lead.mute = True  # This property is deliberately not subscribed.
    assert host.state.read('track')['mute'] is True
    assert host.state.changes()['revision'] == first['revision']


def test_close_detaches_every_subscription_and_new_epoch_starts_clean(host):
    host.state.read('device')
    saved = list(host.state._subscriptions.values())
    host.state.close()
    host.state.close()
    for obj, prop, callback, _ in saved:
        assert callback not in obj.listeners[prop]
    with pytest.raises(RuntimeError, match='closed'):
        host.state.read()
    replacement = LiveState(host.song, host.app, 'new-epoch')
    try:
        assert replacement.read()['changes']['instance'] == 'new-epoch'
        assert replacement.changes()['revision'] == 0
    finally:
        replacement.close()


def test_standalone_reader_and_executor_compile_for_embedded_python():
    root = Path(__file__).parents[1] / 'src/tactus/bridges/TactusBridge'
    for path in root.glob('*.py'):
        ast.parse(path.read_text(), feature_version=(3, 7))


def test_nested_device_removal_detaches_parameter_watch(host):
    chain = Native(observable=('devices',), name='Chain', devices=[host.device])
    rack = Device(name='Rack', class_name='InstrumentGroupDevice', can_have_chains=True,
                  chains=[chain])
    host.lead.devices = [rack]
    host.lead.view.selected_device = rack
    host.state.read('device', device_id=str(host.device._live_ptr))
    parameter = host.device._parameters[0]
    assert parameter.listeners['value']
    chain.devices = []
    chain.emit('devices')
    host.state.refresh()
    assert not parameter.listeners['value']
    assert not chain.listeners['devices']


def test_guarded_edit_reuses_fresh_reader_and_rejects_intervening_note_changes(host):
    recipe = (Path(__file__).parents[1] / 'examples/ableton/selection.py').read_text()

    def run(args):
        namespace = {'state': host.state, 'song': host.song, 'args': args}
        exec(compile(recipe, '<selected-note-recipe>', 'exec'), namespace)  # noqa: S102
        return namespace['result']

    snapshot = run({'mode': 'inspect'})
    host.note.velocity = 91
    with pytest.raises(AssertionError, match='changed'):
        run({'mode': 'apply', 'token': snapshot['token'], 'notes': snapshot['notes']})
    with pytest.raises(AssertionError, match='expired/consumed'):
        run({'mode': 'apply', 'token': snapshot['token'], 'notes': snapshot['notes']})


@pytest.mark.parametrize('edit_returned_row', [False, True])
def test_shared_selection_edits_all_fields_without_changing_other_notes(
        host, monkeypatch, edit_returned_row):
    import copy

    outside = copy.copy(host.note)
    outside.note_id = 8
    outside_before = vars(outside).copy()
    monkeypatch.setattr(host.clip, 'get_all_notes_extended', lambda: [host.note, outside])
    monkeypatch.setattr(host.clip, 'get_notes_by_id', lambda ids: [copy.copy(host.note)], raising=False)

    def apply(vector):
        assert [n.note_id for n in vector] == [host.note.note_id]
        host.note.__dict__.update(vars(vector[0]))

    monkeypatch.setattr(host.clip, 'apply_note_modifications', apply, raising=False)
    snapshot = host.state.selection.inspect()
    edits = [snapshot['notes'][0] if edit_returned_row else dict(snapshot['notes'][0])]
    edits[0].update(start_time=.319, duration=.193, probability=.72,
                    velocity_deviation=9, release_velocity=53, pitch=67, velocity=101)
    result = host.state.selection.update(snapshot['token'], edits)
    assert result['notes'][0] == edits[0]
    assert vars(outside) == outside_before
    assert snapshot['notes'][0]['pitch'] == (67 if edit_returned_row else 60)
    with pytest.raises(AssertionError, match='expired/consumed'):
        host.state.selection.update(snapshot['token'], edits)


@pytest.mark.parametrize('change', [{'pitch': True}, {'duration': 0}, {'probability': 1.1},
                                   {'velocity': float('nan')}, {'mute': 1}])
def test_native_selection_validation_precedes_vector_access_and_consumes_token(host, change):
    snapshot = host.state.selection.inspect()
    edits = [dict(snapshot['notes'][0], **change)]
    with pytest.raises(ValueError):
        host.state.selection.update(snapshot['token'], edits)
    with pytest.raises(AssertionError, match='expired/consumed'):
        host.state.selection.update(snapshot['token'], snapshot['notes'])


def test_selection_snapshot_is_replaced_on_inspect_and_cleared_on_close(host):
    previous = host.state.selection.inspect()
    current = host.state.selection.inspect()
    with pytest.raises(AssertionError, match='expired/consumed'):
        host.state.selection.update(previous['token'], previous['notes'])
    host.state.close()
    with pytest.raises(AssertionError, match='expired/consumed'):
        host.state.selection.update(current['token'], current['notes'])


def test_queue_injects_shared_reader_and_replaces_epoch_on_song_change(host, tmp_path):
    import copy
    import json
    import time

    from tactus.bridges.TactusBridge.bridge import RequestQueue

    queue = RequestQueue(tmp_path)

    class DeletedSong(Native):
        def __getattribute__(self, name):
            if name == '_live_ptr':
                raise RuntimeError('Native object was deleted')
            return super().__getattribute__(name)

    def read():
        request = {'id': 'fixture', 'protocol': 1, 'instance': queue.instance,
                   'expires': time.time() + 5, 'code': 'result=state.read()',
                   'args': None, 'undo': None}
        (queue.root / 'requests/fixture.json').write_text(json.dumps(request))
        queue.poll(lambda: {'song': host.song, 'app': host.app})
        reply = json.loads((queue.root / 'responses/fixture.json').read_text())
        assert reply['ok'], reply
        return reply['result']

    try:
        first = read()['changes']
        original = queue._state
        old_song = host.song
        host.song = copy.copy(host.song)
        host.song._live_ptr = next(_IDS)
        old_song.__class__ = DeletedSong
        second = read()['changes']
        assert second['instance'] != first['instance']
        assert original._closed
        assert second['revision'] == 0
    finally:
        queue.close()
    assert queue._state._closed


@pytest.mark.skipif(not os.environ.get('TACTUS_ABLETON_PATH'),
                    reason='Use an isolated stopped Live Set')
def test_live_scoped_reads_observe_changes_and_detach_owned_clip():
    from tactus.bridges import ableton

    connection = os.environ['TACTUS_ABLETON_PATH']

    def call(code, **kwargs):
        return ableton.execute(code, bridge_path=connection, **kwargs)

    before = ableton.read(bridge_path=connection, scope='project')
    if before['playing']:
        pytest.skip('Stop transport before native scoped-read verification')
    previous = ableton.read(bridge_path=connection)
    fixture = call('''
song.create_midi_track(-1)
t=song.tracks[-1]; t.name='Tactus isolated read fixture'; t.mute=True
song.view.selected_track=t
t.clip_slots[0].create_clip(4)
c=t.clip_slots[0].clip
c.add_new_notes((Live.Clip.MidiNoteSpecification(pitch=60,start_time=.25,duration=.5,velocity=90),))
song.view.detail_clip=c
c.select_all_notes()
result={'track':str(t._live_ptr),'clip':str(c._live_ptr)}
''', undo='Owned native read fixture')
    try:
        summary = ableton.read(bridge_path=connection)
        assert summary['track_list'][-1]['id'] == fixture['track']
        shallow = ableton.read(bridge_path=connection, scope='track', track_id=fixture['track'])
        assert 'notes' not in shallow['session'][0]
        notes = ableton.read(bridge_path=connection, scope='notes')
        assert notes['selected'] == [notes['notes'][0]['note_id']]
        revision = summary['changes']['revision']
        call('''
t=next(t for t in song.tracks if str(t._live_ptr)==args['track'])
c=t.clip_slots[0].clip
vector=c.get_notes_by_id(args['selected'])
vector[0].velocity=91
c.apply_note_modifications(vector)
''', args={**fixture, 'selected': notes['selected']}, undo='Owned native note change')
        assert ableton.read(bridge_path=connection, scope='notes')['notes'][0]['velocity'] == 91
        assert ableton.read(bridge_path=connection)['changes']['revision'] > revision
    finally:
        call('''
for index,track in reversed(list(enumerate(song.tracks))):
    if str(track._live_ptr)==args['fixture']['track']:
        song.delete_track(index)
for track in list(song.tracks)+list(song.return_tracks)+[song.master_track]:
    if str(track._live_ptr)==args['previous']['selected_track']['id']:
        song.view.selected_track=track
clip=args['previous']['detail_clip']
if clip is not None:
    for track in song.tracks:
        for c in list(track.arrangement_clips)+[s.clip for s in track.clip_slots if s.has_clip]:
            if str(c._live_ptr)==clip['id']:
                song.view.detail_clip=c
''', args={'fixture': fixture, 'previous': previous})
    assert ableton.read(bridge_path=connection, scope='project') == before
    assert 'Clip.notes' not in ableton.read(bridge_path=connection)['changes']['observed'] or (
        previous['detail_clip'] is not None)
