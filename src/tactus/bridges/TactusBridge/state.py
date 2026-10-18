"""Scoped native Live reads, observed changes and guarded selection; embedded Python 3.7.

All access/subscription changes run on Live's main thread. Reads fetch fresh values;
observed revisions are incomplete notification hints, never a cache or edit guard.
Project and selected-note rows retain the original work-recipe serialization.
"""

import sys

from .selection import Selection

NOTE_FIELDS = ('note_id', 'pitch', 'start_time', 'duration', 'velocity', 'mute',
               'probability', 'velocity_deviation', 'release_velocity')
SCOPES = ('summary', 'track', 'notes', 'device', 'project')


def identity(obj):
    return None if obj is None else str(getattr(obj, '_live_ptr', obj))


def note_rows(notes, include_ids=True):
    fields = NOTE_FIELDS if include_ids else NOTE_FIELDS[1:]
    return [{key: getattr(note, key) for key in fields} for note in notes]


def object_row(obj):
    return None if obj is None else {'id': identity(obj), 'name': obj.name}


def clip_row(clip, full=False):
    row = {'name': clip.name, 'start': clip.start_time, 'end': clip.end_time,
           'loop': [clip.looping, clip.loop_start, clip.loop_end],
           'markers': [clip.start_marker, clip.end_marker], 'midi': clip.is_midi_clip}
    if not full:
        row['id'] = identity(clip)
    if clip.is_midi_clip:
        if full:
            row['notes'] = note_rows(clip.get_all_notes_extended(), include_ids=False)
    else:
        row.update(file=clip.file_path, warping=clip.warping, gain=clip.gain)
    return row


def device_row(device, full=False):
    row = {'name': device.name, 'class': device.class_name}
    if full:
        row['parameters'] = [{'name': p.name, 'value': p.value} for p in device.parameters]
        if device.can_have_chains:
            row['chains'] = [{'name': c.name, 'devices': [device_row(d, True) for d in c.devices]}
                             for c in device.chains]
    else:
        row['id'] = identity(device)
    return row


def track_row(track, full=False):
    row = {'name': track.name, 'mute': track.mute, 'solo': track.solo,
           'gain': track.mixer_device.volume.value, 'pan': track.mixer_device.panning.value,
           'devices': [device_row(d, full) for d in track.devices],
           'arrangement': [clip_row(c, full) for c in track.arrangement_clips],
           'session': [clip_row(s.clip, full) if s.has_clip else None for s in track.clip_slots]}
    if not full:
        row['id'] = identity(track)
    return row


class LiveState:
    """One bridge instance owns native listeners; native Python remains unrestricted."""

    note_fields = NOTE_FIELDS

    def __init__(self, song, app, instance):
        self.song, self.app, self.instance = song, app, instance
        self.song_id = identity(song)
        self.revision = 0
        self.versions = {}
        self._subscriptions = {}
        self._unsupported = []
        self._refresh_needed = True
        self._device_target = None
        self._closed = False
        self.selection = Selection(self)

    def _tracks(self):
        return list(self.song.tracks) + list(self.song.return_tracks) + [self.song.master_track]

    def track(self, track_id=None):
        """Resolve an exact runtime track ID to a native object, without changing selection."""
        if track_id is None:
            return self.song.view.selected_track
        for track in self._tracks():
            if identity(track) == track_id:
                return track
        raise ValueError('Track is no longer present; read the current summary')

    def _device_location(self, track, device_id):
        def find(devices, ancestors):
            for device in devices:
                if identity(device) == device_id:
                    return device, ancestors
                if device.can_have_chains:
                    for chain in device.chains:
                        found = find(chain.devices, ancestors + [
                            (device, 'Device', 'chains'), (chain, 'Chain', 'devices')])
                        if found is not None:
                            return found
            return None

        location = find(track.devices, [(track, 'Track', 'devices')])
        if location is None:
            raise ValueError('Device is no longer in the target track; inspect again')
        return location

    def _device(self, track, device_id=None):
        if device_id is None:
            return track.view.selected_device
        return self._device_location(track, device_id)[0]

    def _callback(self, group, topology):
        def changed(*unused):
            if not self._closed:
                self.revision += 1
                self.versions[group] = self.versions.get(group, 0) + 1
                if topology:
                    self._refresh_needed = True
        return changed

    @staticmethod
    def _detach(subscription):
        obj, prop, callback, _label = subscription
        try:
            getattr(obj, 'remove_' + prop + '_listener')(callback)
        except (AttributeError, RuntimeError, TypeError):
            # Deleted handles can raise Boost.Python.ArgumentError (a TypeError).
            # Finish cleanup in this poll so stale listeners cannot block requests.
            pass

    def refresh(self):
        """Reconcile changed targets in a later main-thread poll, never in callbacks."""
        if self._closed or not self._refresh_needed:
            return
        desired = {}

        def watch(obj, label, properties, group, topology=False):
            if obj is not None:
                for prop in properties:
                    desired[(identity(obj), prop)] = (obj, prop, label, group, topology)

        song = self.song
        watch(song, 'Song', ('tempo', 'signature_numerator', 'signature_denominator'), 'song')
        watch(song, 'Song', ('is_playing', 'current_song_time'), 'transport')
        watch(song, 'Song', ('tracks', 'return_tracks'), 'tracks', True)
        watch(song.view, 'Song.View', ('selected_track', 'detail_clip'), 'selection', True)
        for track in self._tracks():
            watch(track, 'Track', ('name',), 'tracks')
        track = song.view.selected_track
        if track is not None:
            watch(track, 'Track', ('devices',), 'devices', True)
            watch(track.view, 'Track.View', ('selected_device',), 'selection', True)
        clip = song.view.detail_clip
        watch(clip, 'Clip', ('name', 'looping', 'loop_start', 'loop_end', 'start_marker',
                             'end_marker'), 'clip')
        if clip is not None and clip.is_midi_clip:
            watch(clip, 'Clip', ('notes', 'selected_notes'), 'notes')
        if self._device_target is not None:
            try:
                target = self.track(self._device_target[0])
                device, ancestors = self._device_location(target, self._device_target[1])
            except (ValueError, RuntimeError):
                self._device_target = None
            else:
                for obj, label, prop in ancestors:
                    watch(obj, label, (prop,), 'devices', True)
                watch(device, 'Device', ('name', 'parameters'), 'devices', True)
                if device.can_have_chains:
                    watch(device, 'Device', ('chains',), 'devices', True)
                for parameter in device.parameters:
                    watch(parameter, 'DeviceParameter', ('value',), 'parameters')
        for key in list(self._subscriptions):
            if key not in desired:
                self._detach(self._subscriptions.pop(key))
        unsupported = []
        for key, (obj, prop, label, group, topology) in desired.items():
            if key in self._subscriptions:
                continue
            callback = self._callback(group, topology)
            try:
                getattr(obj, 'add_' + prop + '_listener')(callback)
            except (AttributeError, RuntimeError):
                unsupported.append(label + '.' + prop)
            else:
                self._subscriptions[key] = (obj, prop, callback, label)
        self._unsupported = sorted(set(unsupported))
        self._refresh_needed = False

    def changes(self):
        self.refresh()
        return {'instance': self.instance, 'revision': self.revision,
                'versions': dict(self.versions), 'subscriptions': len(self._subscriptions),
                'observed': sorted({s[3] + '.' + s[1] for s in self._subscriptions.values()}),
                'unsupported': list(self._unsupported)}

    def read(self, scope='summary', track_id=None, device_id=None):
        """Read fresh native state. Explicit runtime IDs never silently fall back."""
        if self._closed:
            raise RuntimeError('Live state reader is closed')
        if scope not in SCOPES:
            raise ValueError('Use a read scope: ' + ', '.join(SCOPES))
        if device_id is not None and scope != 'device':
            raise ValueError('device_id requires scope=device')
        if track_id is not None and scope not in ('track', 'device', 'notes'):
            raise ValueError('track_id requires scope=track, notes or device')
        self.refresh()
        song = self.song
        if scope == 'summary':
            track, clip = song.view.selected_track, song.view.detail_clip
            device = track.view.selected_device if track is not None else None
            return {
                'python_version': sys.version,
                'version': '.'.join(str(f()) for f in (self.app.get_major_version,
                    self.app.get_minor_version, self.app.get_bugfix_version)),
                'project_instance': identity(song), 'project_path': getattr(song, 'file_path', None),
                'name': getattr(song, 'name', None), 'tracks': len(song.tracks),
                'scenes': len(song.scenes), 'tempo': song.tempo,
                'meter': [song.signature_numerator, song.signature_denominator],
                'is_playing': song.is_playing, 'song_time_beats': song.current_song_time,
                'track_list': [object_row(t) for t in song.tracks],
                'return_tracks': [object_row(t) for t in song.return_tracks],
                'master_track': object_row(song.master_track),
                'selected_track': object_row(track), 'selected_device': object_row(device),
                'detail_clip': None if clip is None else dict(object_row(clip),
                    length_beats=clip.length, is_midi_clip=clip.is_midi_clip),
                'changes': self.changes(),
            }
        if scope == 'project':
            def mixer(track):
                return {'name': track.name, 'gain': track.mixer_device.volume.value,
                        'pan': track.mixer_device.panning.value,
                        'devices': [device_row(d, True) for d in track.devices]}
            return {
                'runtime_id': identity(song), 'path': song.file_path,
                'playing': song.is_playing, 'tempo': song.tempo,
                'meter': [song.signature_numerator, song.signature_denominator],
                'tracks': [track_row(t, True) for t in song.tracks],
                'master': mixer(song.master_track), 'returns': [mixer(t) for t in song.return_tracks],
                'cues': [[c.time, c.name] for c in song.cue_points],
            }
        track = self.track(track_id)
        if track is None:
            raise ValueError('Select a track or supply track_id')
        if scope == 'track':
            return track_row(track)
        if scope == 'notes':
            clip = song.view.detail_clip
            if clip is None or not clip.is_midi_clip:
                raise ValueError('Select a MIDI detail clip')
            if not (any(s.has_clip and s.clip == clip for s in track.clip_slots)
                    or any(c == clip for c in track.arrangement_clips)):
                raise ValueError('Clip/selected track mismatch')
            return {'song': identity(song), 'track': identity(track), 'clip': identity(clip),
                    'loop': [clip.loop_start, clip.loop_end, clip.looping],
                    'markers': [clip.start_marker, clip.end_marker],
                    'notes': note_rows(clip.get_all_notes_extended()),
                    'selected': [n.note_id for n in clip.get_selected_notes_extended()]}
        device = self._device(track, device_id)
        if device is None:
            raise ValueError('Select a device or supply device_id')
        self._device_target = (identity(track), identity(device))
        self._refresh_needed = True
        self.refresh()
        row = dict(device_row(device), track_id=identity(track))
        row['parameters'] = [dict(object_row(p), value=p.value, min=p.min, max=p.max,
                                  is_quantized=p.is_quantized) for p in device.parameters]
        row['chains'] = ([{'name': c.name, 'devices': [device_row(d) for d in c.devices]}
                          for c in device.chains] if device.can_have_chains else [])
        row['changes'] = self.changes()
        return row

    def close(self):
        self._closed = True
        self.selection.close()
        for subscription in self._subscriptions.values():
            self._detach(subscription)
        self._subscriptions.clear()
