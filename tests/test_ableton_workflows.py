"""Work recipe invariants; native file lifecycle requires explicit owned-workspace opt-in."""

import ast
import gzip
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/ableton'


@pytest.fixture
def project():
    from tactus.bridges.ableton_support import project

    return project


def test_embedded_scripts_compile_for_live11_python():
    for name in ['inspect_set.py', 'selection.py']:
        ast.parse((EXAMPLES / name).read_text(), feature_version=(3, 7))


def test_existing_capture_never_contacts_host(project, tmp_path, monkeypatch):
    monkeypatch.setattr(project, 'inspect', lambda **_: pytest.fail('Existing destination'))
    with pytest.raises(FileExistsError):
        project.capture(bridge_path='offline', out=tmp_path)


def test_replacement_is_explicit_before_material_or_host(project, tmp_path, monkeypatch):
    monkeypatch.setattr(project, 'material', lambda _: pytest.fail('Not authorized'))
    with pytest.raises(ValueError, match='replace_active_set'):
        project.rebuild('tree:sha256:' + 'a'*64, bridge_path='offline', out=tmp_path/'copy')
    with pytest.raises(ValueError, match='replace_active_set'):
        project.export_project({}, 44100, out=tmp_path, bridge_path='offline', tempo=120)


def test_capture_collects_audio_not_historical_preset_paths(project, tmp_path):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'original audio bytes')
    out = tmp_path / 'copy'
    out.mkdir()
    path = out / 'session.als'
    root = ET.fromstring(f'''<Ableton><LiveSet><SourceContext><OriginalFileRef><FileRef>
      <Path Value="/Missing historical preset.adv"/></FileRef></OriginalFileRef></SourceContext>
      <SampleRef><FileRef><Path Value="{source}"/>
      <RelativePath Value="old"/><RelativePathType Value="1"/></FileRef></SampleRef>
      </LiveSet></Ableton>''')
    path.write_bytes(gzip.compress(ET.tostring(root)))
    files = project._collect(path)
    assert len(files) == 1 and source.read_bytes() == b'original audio bytes'
    rebound = ET.fromstring(gzip.decompress(path.read_bytes())).find('.//SampleRef/FileRef')
    assert rebound.find('Path').get('Value') == ''
    assert rebound.find('RelativePathType').get('Value') == '1'
    target = out / rebound.find('RelativePath').get('Value')
    assert target.is_relative_to(out) and target.read_bytes() == source.read_bytes()
    assert rebound.find('RelativePath').get('Value') in files


def test_missing_audio_does_not_become_a_complete_capture(project, tmp_path):
    path = tmp_path / 'session.als'
    path.write_bytes(gzip.compress(b'<Ableton><SampleRef><FileRef>'
                                  b'<Path Value="/missing.wav"/></FileRef></SampleRef></Ableton>'))
    with pytest.raises(ValueError, match='missing'):
        project._collect(path)
    assert not (tmp_path / 'capture.json').exists()


def test_unfrozen_max_dependencies_need_explicit_packaging(project, tmp_path):
    source = tmp_path / 'live.amxd'
    source.write_bytes(b'unfrozen host')
    path = tmp_path / 'session.als'
    path.write_bytes(gzip.compress(f'<Ableton><MxDPatchRef><FileRef><Path Value="{source}"/>'
                                  '</FileRef></MxDPatchRef></Ableton>'.encode()))
    with pytest.raises(ValueError, match='Max dependencies'):
        project._collect(path)


def test_incomplete_bundle_fails_before_gui(project, tmp_path, monkeypatch):
    (tmp_path/'capture.json').write_text(json.dumps({'project': '../outside.als', 'files': {}}))
    monkeypatch.setattr(project, 'material', lambda _: tmp_path)
    monkeypatch.setattr(project, 'inspect', lambda **_: pytest.fail('Incomplete bundle'))
    with pytest.raises(ValueError, match='completed native'):
        project.rebuild('tree:sha256:'+'a'*64, bridge_path='offline', out=tmp_path/'copy',
                       replace_active_set=True)


def test_declared_max_bundle_copies_exact_device_and_companions(project, tmp_path, monkeypatch):
    loaded = tmp_path / 'original.amxd'
    loaded.write_bytes(b'exact max device')
    bundle = tmp_path / 'max-bundle'
    bundle.mkdir()
    (bundle / loaded.name).write_bytes(loaded.read_bytes())
    (bundle / 'voice.js').write_text('function bang() {}')
    monkeypatch.setattr(project, 'material', lambda _: bundle)
    out = tmp_path / 'copy'
    out.mkdir()
    path = out / 'session.als'
    path.write_bytes(gzip.compress(f'<Ableton><MxDPatchRef><FileRef><Path Value="{loaded}"/>'
                                  '<RelativePath/><RelativePathType Value="6"/>'
                                  '</FileRef></MxDPatchRef></Ableton>'.encode()))
    files = project._collect(path, {str(loaded): 'tree:sha256:'+'a'*64})
    assert len(files) == 2
    copied = out / next(n for n in files if n.endswith('.amxd'))
    assert copied.read_bytes() == loaded.read_bytes()
    copied.write_bytes(b'GUI edit of copy')
    assert (bundle / loaded.name).read_bytes() == b'exact max device'
    assert loaded.read_bytes() == b'exact max device'


@pytest.mark.skipif(os.environ.get('TACTUS_ABLETON_WORKSPACE') != '1',
                    reason='Explicitly opt into replacing a dedicated Live workspace')
def test_native_handoff_capture_rebuild_and_pool_immutability(project, tmp_path, monkeypatch):
    import tempfile

    import numpy as np

    from tactus import material
    from tactus.inputs import tree

    connection = os.environ['TACTUS_ABLETON_PATH']
    monkeypatch.setenv('TACTUS_POOL', str(tmp_path / 'pool'))
    before = project.inspect(bridge_path=connection)
    if before['playing']:
        pytest.skip('Stop transport before native lifecycle verification')
    # This recovery survives pytest temporary-directory cleanup.
    recovery = project.save_copy(Path(tempfile.mkdtemp(prefix='tactus-live-test-'))/'recovery')
    try:
        signal = .05 * np.sin(2*np.pi*440*np.arange(4410)/44100)
        delivered = project.export_project({'test-tone': signal}, 44100,
            out=tmp_path/'delivery', bridge_path=connection, tempo=97,
            names=['test-tone'], positions={'test-tone': .375}, markers=[[.375, 'Verify']],
            replace_active_set=True)
        published = tmp_path/'published'
        (tmp_path/'delivery').rename(published)  # The real exporter publishes by moving.
        path = published / delivered['project']
        project.open_set(path, discard_current=True)
        state = project._wait(path, connection)
        project._media_inside(state, path.parent)
        assert state['tracks'][0]['name'] == 'test-tone'
        assert state['tracks'][0]['arrangement'][0]['start'] == pytest.approx(.375*97/60)
        assert state['cues'] == [[.375*97/60, 'Verify']]
        project.native('''
song.create_midi_track(-1)
t = song.tracks[-1]; t.name = 'Owned native MIDI'
t.clip_slots[0].create_clip(4)
c = t.clip_slots[0].clip
c.add_new_notes((Live.Clip.MidiNoteSpecification(pitch=64,start_time=.25,duration=.5,velocity=90),))
''', connection, undo='Native lifecycle fixture')
        accepted = tmp_path / 'accepted'
        captured = project.capture(bridge_path=connection, out=accepted)
        ref = tree.add(accepted)
        pinned = material(ref)
        original = tree.digest_of_tree(pinned)[0]
        rebuilt = project.rebuild(ref, bridge_path=connection, out=tmp_path/'scratch',
                                  replace_active_set=True)
        assert project._content(rebuilt['state']) == project._content(captured['reopened'])
        assert tree.digest_of_tree(pinned)[0] == original == tree.digest_from_ref(ref)
        assert not Path(rebuilt['project']).is_relative_to(pinned)
    finally:
        project.open_set(recovery, discard_current=True)
        project._wait(recovery, connection)
