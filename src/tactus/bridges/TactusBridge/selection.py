"""Guard selected MIDI edits without choosing note values; embedded Python 3.7.

One reader epoch owns one pending snapshot. Consume it before native validation;
fresh selection/content checks and full-note validation precede all vector writes.
Reads: shared native reader/note fields, selected clip, stdlib math and UUIDs.
"""

import copy
import math
import uuid


def validate_notes(snapshot, notes):
    """Validate complete selected-note rows without changing or clamping values."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('token'), str):
        raise TypeError('Use inspect_selection before updating')
    selected = set(snapshot['selected'])
    originals = {n['note_id']: n for n in snapshot['notes'] if n['note_id'] in selected}
    if not isinstance(notes, list) or len(notes) != len(originals):
        raise ValueError('Supply one full note for every selected ID')
    if {n.get('note_id') for n in notes} != selected:
        raise ValueError('Edit exactly the selected note IDs')
    bounds = {'pitch': (0, 127), 'velocity': (1, 127), 'probability': (0, 1),
              'velocity_deviation': (-127, 127), 'release_velocity': (0, 127)}
    for note in notes:
        if note.keys() != originals[note['note_id']].keys() or type(note['mute']) is not bool:
            raise ValueError('Keep the full inspected note attributes')
        if type(note['pitch']) is not int:
            raise ValueError('pitch must be an integer')
        for key in ('start_time', 'duration'):
            value = note[key]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{key} must be finite')
        if note['duration'] <= 0:
            raise ValueError('duration must be positive')
        for key, (low, high) in bounds.items():
            value = note[key]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not low <= value <= high):
                raise ValueError(f'{key} must be finite and in {low}..{high}')


class Selection:
    """One-use edits of the current selection; arbitrary native Python remains available."""

    def __init__(self, state):
        self._state = state
        self._pending = {}

    def inspect(self):
        snapshot = self._state.read(scope='notes')
        assert snapshot['selected'], 'Select notes in the MIDI editor'
        token = uuid.uuid4().hex
        self._pending.clear()
        self._pending[token] = snapshot
        return dict(copy.deepcopy(snapshot), token=token)

    def update(self, token, notes):
        snapshot = self._pending.pop(token, None)
        assert snapshot is not None, 'Snapshot expired/consumed; inspect again'
        assert self._state.read(scope='notes') == snapshot, 'Selection or clip changed; inspect again'
        validate_notes(dict(snapshot, token=token), notes)
        clip = self._state.song.view.detail_clip
        vector = clip.get_notes_by_id(snapshot['selected'])
        by_id = {n['note_id']: n for n in notes}
        for note in vector:
            for key in self._state.note_fields[1:]:
                setattr(note, key, by_id[note.note_id][key])
        clip.apply_note_modifications(vector)
        return self._state.read(scope='notes')

    def close(self):
        self._pending.clear()
