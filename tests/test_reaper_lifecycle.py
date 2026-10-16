"""Accepted native state becomes pinned material, rebuildable audio and a handoff."""

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import material
from tactus.bridges import reaper
from tactus.inputs import tree

EXAMPLE = Path(__file__).parents[1] / 'examples/reaper/project.py'
spec = importlib.util.spec_from_file_location('reaper_project_example', EXAMPLE)
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)
LIVE = os.environ.get('TACTUS_REAPER_RESOURCE_PATH')
BUNDLE = os.environ.get('TACTUS_REAPER_BUNDLE')


def test_capture_existing_destination_does_not_touch_daw(tmp_path, monkeypatch):
    monkeypatch.setattr(recipe, 'inspect', lambda **_: pytest.fail('Must not contact DAW'))
    with pytest.raises(FileExistsError):
        recipe.capture(resource_path='unused', out=tmp_path)


@pytest.mark.parametrize('source', [
    {'file': '', 'kind': 'EMPTY', 'wrapped': False, 'inline_midi': False},
    {'file': '/missing.wav', 'kind': 'WAVE', 'wrapped': False, 'inline_midi': False},
    {'file': '/section.wav', 'kind': 'WAVE', 'wrapped': True, 'inline_midi': False},
    {'file': '/song.rpp', 'kind': 'RPP_PROJECT', 'wrapped': False, 'inline_midi': False},
])
def test_uncollected_sources_fail_before_writing(tmp_path, monkeypatch, source):
    monkeypatch.setattr(recipe, 'inspect', lambda **_: {'media': [source]})
    out = tmp_path / 'snapshot'
    with pytest.raises(ValueError):
        recipe.capture(resource_path='unused', out=out)
    assert not out.exists()


@pytest.mark.parametrize('options', [
    {'ref': 'not-pinned'}, {'seconds': 0}, {'seconds': float('inf')},
    {'sample_rate': True}, {'sample_rate': 0},
])
def test_bad_rebuild_does_not_resolve_material_or_touch_host(monkeypatch, options):
    monkeypatch.setattr(recipe, 'material', lambda _: pytest.fail('Invalid request'))
    params = {'ref': 'tree:sha256:' + 'a' * 64, 'resource_path': 'unused',
              'reaper_bundle': 'unused', **options}
    with pytest.raises(ValueError):
        recipe.render_project(**params)


def test_unknown_native_completion_retains_real_scratch_copy(tmp_path, monkeypatch):
    bundle = tmp_path / 'pinned'
    bundle.mkdir()
    (bundle / 'session.rpp').write_text('native project')
    (bundle / 'capture.json').write_text('{"project":"session.rpp"}')
    monkeypatch.setattr(recipe, 'material', lambda _: bundle)
    monkeypatch.setattr(recipe, 'tool', lambda _: 'declared')
    seen = []

    def native(resource_path, **args):
        seen.append(Path(args['project']))
        if args['mode'] == 'render':
            raise reaper.BridgeTimeout('Already executing, completion unknown')
        return {'media': {}}

    monkeypatch.setattr(recipe, '_native', native)
    with pytest.raises(reaper.BridgeTimeout) as error:
        recipe.render_project('tree:sha256:' + 'a' * 64,
                              resource_path='peer', reaper_bundle='declared')
    assert seen[0] != bundle / 'session.rpp'
    assert seen[0].read_bytes() == (bundle / 'session.rpp').read_bytes()
    assert 'scratch retained' in error.value.__notes__[0]
    # Test owns the retained scratch; the production error path must not delete it.
    import shutil

    shutil.rmtree(seen[0].parent.parent)


@pytest.mark.parametrize('marker', ['unfinished JSON', '{}'])
def test_incomplete_capture_marker_is_not_rebuilt(tmp_path, monkeypatch, marker):
    (tmp_path / 'session.rpp').write_text('native state')
    (tmp_path / 'capture.json').write_text(marker)
    monkeypatch.setattr(recipe, 'material', lambda _: tmp_path)
    monkeypatch.setattr(recipe, 'tool', lambda _: pytest.fail('No native operation'))
    with pytest.raises(ValueError):
        recipe.render_project('tree:sha256:' + 'a' * 64,
                              resource_path='unused', reaper_bundle='unused')


SETUP = """
reaper.Main_OnCommand(41929,0)
local p=reaper.EnumProjects(-1,'')
reaper.Main_SaveProjectEx(p,args.path,8)
reaper.InsertTrackAtIndex(0,false)
local track=reaper.GetTrack(p,0)
reaper.GetSetMediaTrackInfo_String(track,'P_NAME','Native MIDI',true)
reaper.SetMediaTrackInfo_Value(track,'D_VOL',.12)
assert(reaper.TrackFX_AddByName(track,'ReaSynth (Cockos)',false,-1)>=0)
local item=reaper.CreateNewMIDIItemInProj(track,0,.2,false)
local take=reaper.GetActiveTake(item)
assert(reaper.MIDI_InsertNote(take,false,false,0,
 reaper.MIDI_GetPPQPosFromProjTime(take,.1),0,64,80,false))
reaper.InsertTrackAtIndex(1,false)
local second=reaper.GetTrack(p,1)
local audio=reaper.AddMediaItemToTrack(second)
local audio_take=reaper.AddTakeToMediaItem(audio)
reaper.SetMediaItemTake_Source(audio_take,reaper.PCM_Source_CreateFromFile(args.audio))
reaper.SetMediaItemInfo_Value(audio,'D_LENGTH',.2)
reaper.SetMediaItemTakeInfo_Value(audio_take,'D_STARTOFFS',.01)
reaper.SetMediaTrackInfo_Value(second,'D_VOL',.17)
reaper.SetOnlyTrackSelected(track)
reaper.GetSet_LoopTimeRange2(p,true,false,.02,.15,false)
reaper.SetEditCurPos(.05,false,false)
reaper.AddProjectMarker2(p,false,.1,0,'Keep marker',1,0)
reaper.Main_SaveProjectEx(p,args.path,8)
return true
"""


@pytest.fixture
def live_project(tmp_path):
    if not LIVE:
        pytest.skip('Opt in with isolated TACTUS_REAPER_RESOURCE_PATH')
    previous = reaper.execute("return tostring(reaper.EnumProjects(-1,''))", resource_path=LIVE)
    directory = tmp_path / 'original'
    directory.mkdir()
    # Deliberately external media: capture must collect/rebase it, not retain its path.
    audio = tmp_path / 'external.wav'
    sf.write(audio, .08 * np.sin(np.arange(7200) * .13), 24000, subtype='FLOAT')
    reaper.execute(SETUP, resource_path=LIVE,
                   args={'path': str(directory / 'source.rpp'), 'audio': str(audio)})
    yield directory, audio, previous
    reaper.execute("""for i=0,100 do local p=reaper.EnumProjects(i,'')
if not p then break end
if tostring(p)==args.previous then reaper.SelectProjectInstance(p);return true end
end;error('Previous tab disappeared')""", resource_path=LIVE, args={'previous': previous})


def test_live_capture_relocates_external_media_preserves_native_state_and_rebuilds(
    live_project, tmp_path, monkeypatch
):
    original, audio, _ = live_project
    before = recipe.inspect(resource_path=LIVE)
    saved = (original / 'source.rpp').read_bytes()
    out = tmp_path / 'captured'
    captured = recipe.capture(resource_path=LIVE, out=out)
    assert before == recipe.inspect(resource_path=LIVE)
    assert (original / 'source.rpp').read_bytes() == saved
    assert captured['files'] and captured['reaper']['tracks'][0]['name'] == 'Native MIDI'
    assert captured['reaper']['tracks'][0]['fx'][0]['enabled']
    assert captured['reaper']['time_selection'] == before['time_selection']
    assert (out / 'capture.json').is_file()
    audio.rename(tmp_path / 'external-unavailable.wav')
    moved = tmp_path / 'relocated'
    out.rename(moved)
    state = recipe._native(LIVE, mode='verify', project=str(moved / 'session.rpp'))
    recipe._verify_media(state, moved)
    assert recipe.inspect(resource_path=LIVE) == before
    monkeypatch.setenv('TACTUS_POOL', str(tmp_path / 'pool'))
    ref = tree.add(moved)
    pinned = material(ref)
    digest, _ = tree.digest_of_tree(pinned)
    if BUNDLE:
        a = recipe.render_project(ref, resource_path=LIVE, reaper_bundle=BUNDLE, seconds=.2)
        b = recipe.render_project(ref, resource_path=LIVE, reaper_bundle=BUNDLE, seconds=.2)
        assert a.shape == (4800, 2) and np.max(np.abs(a)) > .001
        np.testing.assert_array_equal(a, b)
        assert digest == tree.digest_of_tree(pinned)[0]
        assert recipe.inspect(resource_path=LIVE) == before


def test_live_capture_rejects_intervening_edit_before_save(live_project, tmp_path, monkeypatch):
    original, _, _ = live_project
    before = (original / 'source.rpp').read_bytes()
    native = recipe._native

    def intervening(resource_path, **args):
        if args['mode'] == 'capture':
            reaper.execute("reaper.SetMediaTrackInfo_Value(reaper.GetTrack(0,0),'D_VOL',.2)",
                           resource_path=LIVE)
        return native(resource_path, **args)

    monkeypatch.setattr(recipe, '_native', intervening)
    out = tmp_path / 'stale'
    with pytest.raises(reaper.BridgeError, match='Project changed'):
        recipe.capture(resource_path=LIVE, out=out)
    assert not (out / 'capture.json').exists()
    assert not (out / 'session.rpp').exists()
    assert (original / 'source.rpp').read_bytes() == before


def test_captured_manifest_is_explicit_about_plugin_owned_dependencies(tmp_path, monkeypatch):
    before = {'media': {}}
    monkeypatch.setattr(recipe, 'inspect', lambda **_: before)

    def native(resource_path, **args):
        if args['mode'] == 'capture':
            Path(args['project']).write_text('native save in test peer')
        return {'media': {}}

    monkeypatch.setattr(recipe, '_native', native)
    out = tmp_path / 'snapshot'
    recipe.capture(resource_path='peer', out=out)
    manifest = json.loads((out / 'capture.json').read_text())
    assert manifest['project'] == 'session.rpp' and manifest['files'] == {}
    assert 'plugin-owned' in manifest['external_dependencies']
