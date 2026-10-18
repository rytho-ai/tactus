"""Shared native capture, rebuild and printed-stem handoff for a Live workspace.

Live 11 has one active set and no verified Python file-lifecycle API. The macOS
adapter saves recovery copies before replacing it; imported copies remain active.
All music/placement and readback use the Live API. ALS XML is used only to collect
file references into the copied bundle. Max/plugin-owned assets stay explicit.
"""

import gzip
import hashlib
import json
import math
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import soundfile as sf

from ... import material
from ...store import validate_name
from .. import ableton
from ._mac_ui import new_set, open_set, save_copy


def native(code, bridge_path, **kwargs):
    return ableton.execute(code, bridge_path=bridge_path, **kwargs)


def inspect(*, bridge_path):
    return ableton.read(bridge_path=bridge_path, scope='project')


def _wait(path, bridge_path):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            state = inspect(bridge_path=bridge_path)
        except (ableton.BridgeError, ableton.BridgeTimeout):
            time.sleep(.1)
            continue  # Read-only inspection may cross a Control Surface reload.
        if Path(state['path']).resolve() == path.resolve():
            return state
        time.sleep(.1)
    raise TimeoutError(f'Live did not open {path}; inspect the host before retrying')


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _collect(path, device_bundles=None):
    """Rebind audio SampleRefs and Max patch references in the COPY. Never write into original sources."""
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    files = {}
    refs = root.findall('.//SampleRef/FileRef') + root.findall('.//MxDPatchRef/FileRef')
    for ref in refs:
        node = ref.find('Path')
        if node is None or not node.get('Value'):
            continue
        source = Path(node.get('Value'))
        if not source.is_absolute() or not source.is_file():
            raise ValueError(f'Collect missing/unresolved native file first: {source}')
        digest = _digest(source)
        if source.suffix.lower() == '.amxd':
            bundle_ref = (device_bundles or {}).get(str(source.resolve()))
            if not isinstance(bundle_ref, str) or not bundle_ref.startswith('tree:sha256:'):
                raise ValueError('Declare Max dependencies with device_bundles[amxd_path]=tree_ref')
            bundle = material(bundle_ref)
            if not (bundle / source.name).is_file() or _digest(bundle / source.name) != digest:
                raise ValueError('Max bundle does not contain the exact loaded AMXD')
            relative_dir = Path('devices') / bundle_ref.rsplit(':', 1)[1]
            destination = path.parent / relative_dir
            if not destination.exists():
                shutil.copytree(bundle, destination)  # Real copies, not pool hardlinks.
            for file in destination.rglob('*'):
                if file.is_file():
                    files[file.relative_to(path.parent).as_posix()] = _digest(file)
            relative = (relative_dir / source.name).as_posix()
        else:
            relative = f'media/{digest}{source.suffix.lower()}'
            target = path.parent / relative
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
            if _digest(target) != digest or _digest(source) != digest:
                raise ValueError('Media changed while copying')
            files[relative] = digest
        node.set('Value', '')  # Resolve collected media relative to this ALS after moving.
        relative_node, kind = ref.find('RelativePath'), ref.find('RelativePathType')
        if relative_node is not None:
            relative_node.set('Value', relative)
        if kind is not None:
            kind.set('Value', '1')  # Native Save a Copy uses set-relative FileRefs.
    path.write_bytes(gzip.compress(ET.tostring(root, encoding='utf-8', xml_declaration=True), mtime=0))
    return files


def _media_inside(state, directory):
    for track in state['tracks']:
        for clip in track['arrangement'] + [c for c in track['session'] if c is not None]:
            if not clip['midi']:
                if not clip['file']:
                    raise ValueError('Native set has missing media: ' + track['name'] + '/' + clip['name'])
                file = Path(clip['file']).resolve()
                if not file.is_relative_to(directory) or not file.is_file():
                    raise ValueError(f'Native set still references outside/missing media: {file}')



def _content(state):
    value = json.loads(json.dumps(state))
    value.pop('path', None)
    value.pop('runtime_id', None)
    for track in value['tracks']:
        for clip in track['arrangement'] + [c for c in track['session'] if c is not None]:
            if not clip['midi']:
                clip['file'] = _digest(clip['file'])
    return value


def capture(*, bridge_path, out, device_bundles=None):
    """Save/collect/reopen accepted native state; leaves the verified copy active.

    Stop transport and close dialogs first. Native MIDI/device/routing/automation
    stay in the ALS. Supply device_bundles[absolute_amxd]=tree_ref for collected/frozen
    Max files and companions; patch-internal absolute paths still need an authored packager.
    Plugin-owned libraries and hardware remain external; pin audio for host-free replay. capture.json is written last.
    """
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    before = inspect(bridge_path=bridge_path)
    if before['playing']:
        raise ValueError('Stop transport before native capture')
    path = save_copy(out)
    after = inspect(bridge_path=bridge_path)
    if before != after:
        raise ValueError('Live changed during capture; inspect before adopting')
    files = _collect(path, device_bundles=device_bundles)
    open_set(path, discard_current=True)
    reopened = _wait(path, bridge_path)
    _media_inside(reopened, path.parent)
    if _content(before) != _content(reopened):
        raise ValueError('Native content changed after reopening; capture not complete')
    record = {'project': str(path.relative_to(out)), 'files': files,
              'source': before, 'reopened': reopened,
              'device_bundles': device_bundles or {},
              'dependencies': 'Plugin binaries/libraries and hardware must be declared separately'}
    (out / 'capture.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def rebuild(ref, *, bridge_path, out, replace_active_set=False):
    """Open a real writable COPY of accepted native state; never open/save pool files."""
    if replace_active_set is not True:
        raise ValueError('Use replace_active_set=True for the dedicated Live workspace')
    if not isinstance(ref, str) or not ref.startswith('tree:sha256:'):
        raise ValueError('Use a pinned tree bundle')
    source = material(ref)
    record = json.loads((source / 'capture.json').read_text())
    project = record.get('project')
    if not isinstance(project, str) or not project.endswith('.als'):
        raise ValueError('Use a completed native capture bundle')
    project_path = (source / project).resolve()
    if (not project_path.is_relative_to(source.resolve()) or not project_path.is_file()
            or not isinstance(record.get('files'), dict) or 'reopened' not in record):
        raise ValueError('Use a completed native capture bundle')
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    before = inspect(bridge_path=bridge_path)
    if before['playing']:
        raise ValueError('Stop transport before rebuilding')
    out.mkdir(parents=True, exist_ok=False)
    recovery = save_copy(out / 'recovery')
    if inspect(bridge_path=bridge_path) != before:
        raise ValueError('Live changed while saving recovery')
    shutil.copytree(source, out / 'input')
    path = out / 'input' / record['project']
    # Rebase collected paths to the scratch copy, not the original capture/pool.
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    for file in root.findall('.//FileRef'):
        relative = file.find('RelativePath')
        node = file.find('Path')
        if relative is not None and node is not None and relative.get('Value') in record['files']:
            node.set('Value', str(path.parent / relative.get('Value')))
            kind = file.find('RelativePathType')
            if kind is not None:
                kind.set('Value', '1')
    path.write_bytes(gzip.compress(ET.tostring(root, encoding='utf-8', xml_declaration=True), mtime=0))
    open_set(path, discard_current=True)
    state = _wait(path, bridge_path)
    _media_inside(state, path.parent)
    return {"state": state, "project": str(path), "recovery": str(recovery)}



def _finish_handoff(path, markers, tempo):
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    for clip in root.findall('.//AudioClip'):
        fade = clip.find('Fade')
        if fade is not None:
            fade.set('Value', 'false')
        for node in clip.findall('./Fades/*'):
            if node.tag in {'FadeInLength', 'FadeOutLength'}:
                node.set('Value', '0')
            elif node.tag in {'IsDefaultFadeIn', 'IsDefaultFadeOut'}:
                node.set('Value', 'false')
    container = root.find('./LiveSet/Locators/Locators')
    if container is None:
        raise ValueError('Unrecognized Live locator schema; use a version-specific exporter')
    container.clear()
    for i, (seconds, label) in enumerate(markers):
        locator = ET.SubElement(container, 'Locator', Id=str(i))
        for key, value in [('LomId', '0'), ('Time', str(seconds * tempo / 60)),
                           ('Name', label), ('Annotation', ''), ('IsSongStart', 'false')]:
            ET.SubElement(locator, key, Value=value)
    path.write_bytes(gzip.compress(ET.tostring(root, encoding='utf-8', xml_declaration=True), mtime=0))


def export_project(outputs, sample_rate, *, out, bridge_path: str, tempo: float,
                   replace_active_set: bool = False, names: list[str] | None = None,
                   positions: dict | None = None, markers: list | None = None,
                   time_map=None, run_identity=None):
    """Hand selected printed stems to a NEW Live set, preserving a recovery copy.

    positions/markers use seconds, tempo is explicit, warping is disabled. This
    exporter replaces Live's single active set, so replace_active_set=True is required.
    It restores a recovery copy; open the published ALS afterwards. FLOAT media
    preserves source headroom. The delivery remains portable after export publication.
    """
    if replace_active_set is not True:
        raise ValueError('Set replace_active_set=True for this single-set Live workspace')
    if type(tempo) not in (int, float) or not math.isfinite(tempo) or tempo <= 0:
        raise ValueError('tempo must be finite and positive')
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('sample_rate must be positive integer')
    names = [n for n in outputs if n != 'mix'] if names is None else names
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError('Select distinct output names')
    positions, markers = positions or {}, markers or []
    arrays = {}
    for n in names:
        if not isinstance(n, str) or n not in outputs:
            raise ValueError('Select existing output names')
        validate_name(n)
        original = np.asarray(outputs[n])
        if original.dtype.kind not in 'fiu':
            raise ValueError('Outputs must be real audio arrays')
        a = original.astype(np.float32)
        if a.ndim not in (1, 2) or not len(a) or (a.ndim == 2 and a.shape[1] not in (1, 2)):
            raise ValueError('Outputs must be nonempty mono/stereo audio')
        if not np.isfinite(a).all():
            raise ValueError('Outputs must fit finite float32')
        pos = positions.get(n, 0)
        if type(pos) not in (int, float) or not math.isfinite(pos) or pos < 0:
            raise ValueError('positions use finite nonnegative seconds')
        arrays[n] = a
    for seconds, label in markers:
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0 or not isinstance(label, str):
            raise ValueError('markers use nonnegative seconds/string labels')
    before = inspect(bridge_path=bridge_path)
    if before['playing']:
        raise ValueError('Stop transport before handoff')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)  # The export runner owns this destination.
    recovery_root = Path(tempfile.mkdtemp(prefix='tactus-live-export-'))
    recovery = save_copy(recovery_root / 'recovery')
    if inspect(bridge_path=bridge_path) != before:
        raise ValueError('Live changed while saving recovery')
    media = out / 'media'
    media.mkdir()
    stems = []
    for name, a in arrays.items():
        path = media / f'{name}.wav'
        sf.write(path, a, sample_rate, subtype='FLOAT')
        stems.append({'name': name, 'file': str(path), 'seconds': len(a) / sample_rate,
                      'position': positions.get(name, 0)})
    new_set(discard_current=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            ready = inspect(bridge_path=bridge_path)
            if ready['runtime_id'] != before['runtime_id'] and not ready['path']:
                break
        except (ableton.BridgeError, ableton.BridgeTimeout):
            pass  # Only repeat inspection, never repeat a musical mutation.
        time.sleep(.1)
    else:
        raise TimeoutError('New set did not become ready; recovery copy is retained')
    created = native('''
assert not song.is_playing and not song.file_path, 'Expected a new unsaved set'
song.create_audio_track(-1)  # Live requires at least one regular track.
for i in reversed(range(len(song.tracks)-1)): song.delete_track(i)
song.tempo = args['tempo']
song.loop = False; song.metronome = False
for i in reversed(range(len(song.return_tracks))): song.delete_return_track(i)
for i in reversed(range(len(song.master_track.devices))): song.master_track.delete_device(i)
song.master_track.mixer_device.volume.value = .85
song.master_track.mixer_device.panning.value = 0
for i, stem in enumerate(args['stems']):
 if i: song.create_audio_track(-1)
 t = song.tracks[-1]; t.name = stem['name']
 for j in reversed(range(len(t.devices))): t.delete_device(j)
 t.mute = False; t.solo = False
 t.mixer_device.volume.value = 0.85
 t.mixer_device.panning.value = 0
 t.mixer_device.crossfade_assign = 1
 t.current_monitoring_state = 2
 for send in t.mixer_device.sends: send.value = 0
 t.create_audio_clip(stem['file'], stem['position'] * song.tempo / 60.)
 c = t.arrangement_clips[0]; c.warping = False
 c.looping = False; c.name = stem['name']; c.gain = .4
 c.start_marker = 0; c.end_marker = stem['seconds']
 c.pitch_coarse = 0; c.pitch_fine = 0
 assert c.gain_display_string == '0.00 dB', 'Verify unity clip gain on this Live version'
song.current_song_time = 0
result = {'song': str(song._live_ptr), 'tracks': [str(t._live_ptr) for t in song.tracks]}
''', bridge_path, args={'tempo': tempo, 'stems': stems, 'markers': markers},
           undo='Create printed handoff')
    # Live rebuilds routing choices after track creation returns to its event loop.
    # Do not retry creation or assume the new track's routing vector is ready inline.
    native('''
assert str(song._live_ptr) == args['song'], 'Handoff set changed'
assert [str(t._live_ptr) for t in song.tracks] == args['tracks'], 'Handoff tracks changed'
routes = [next(r for r in t.available_output_routing_types if r.display_name == 'Master')
          for t in song.tracks]
for t, route in zip(song.tracks, routes): t.output_routing_type = route
''', bridge_path, args=created, undo='Route printed handoff')
    intended = inspect(bridge_path=bridge_path)
    project = save_copy(out / 'native')
    if inspect(bridge_path=bridge_path) != intended:
        raise ValueError('Handoff changed while saving; recovery is retained')
    _collect(project)
    _finish_handoff(project, markers, tempo)
    open_set(project, discard_current=True)
    reopened = _wait(project, bridge_path)
    _media_inside(reopened, project.parent)
    tolerance = tempo / (60 * sample_rate)  # One authored audio frame in beats.
    if len(reopened['tracks']) != len(stems):
        raise ValueError('Native handoff track count differs after reopening')
    for track, stem in zip(reopened['tracks'], stems):
        clip = track['arrangement'][0]
        start, end = stem['position'] * tempo / 60, (stem['position'] + stem['seconds']) * tempo / 60
        if (track['name'] != stem['name'] or abs(clip['start'] - start) > tolerance
                or abs(clip['end'] - end) > tolerance):
            raise ValueError('Native handoff position/length/name differs after reopening')
    # Export publishes by moving this staging directory. Keep Live on a recovery
    # copy outside it and use relative media so the delivered ALS can move safely.
    open_set(recovery, discard_current=True)
    _wait(recovery, bridge_path)
    (out / 'source.json').write_text(json.dumps({'run': run_identity, 'map': time_map}, indent=2)+'\n')
    return {'project': str(project.relative_to(out)), 'recovery': str(recovery),
            'native': _content(reopened)}
