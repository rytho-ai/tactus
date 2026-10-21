"""Render mechanics preserve raw sound, failure evidence and the caller's tab."""

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus.bridges import reaper
from tactus.bridges.reaper_support import audio


def call(**kwargs):
    return audio.render('return args', resource_path='unused', reaper_bundle='declared',
                        **{'seconds': .01, 'sample_rate': 24000, 'channels': 2, **kwargs})


@pytest.mark.parametrize('kwargs', [
    {'seconds': 0}, {'seconds': True}, {'seconds': float('inf')},
    {'sample_rate': True}, {'sample_rate': 0}, {'channels': 3},
    {'timeout': 0}, {'args': object()},
])
def test_invalid_requests_do_not_allocate_or_contact_daw(monkeypatch, kwargs):
    monkeypatch.setattr(audio.tempfile, 'mkdtemp', lambda **_: pytest.fail('allocated'))
    monkeypatch.setattr(reaper, 'execute', lambda *a, **k: pytest.fail('contacted'))
    with pytest.raises((TypeError, ValueError)):
        call(**kwargs)


def test_render_preserves_raw_silence_channels_and_cleans_only_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, 'tool', Path)
    paths = []
    def native(code, *, resource_path, timeout, args):
        assert args['setup'] == 'return args' and args['data'] == {'example': True}
        out = Path(args['out'])
        paths.append(out)
        sf.write(out / 'audio.wav', np.zeros((240, 2)), 24000, subtype='FLOAT')
    monkeypatch.setattr(reaper, 'execute', native)
    result = call(args={'example': True})
    np.testing.assert_array_equal(result, np.zeros((240, 2)))
    assert not paths[0].exists()


@pytest.mark.parametrize('failure', ['timeout', 'missing', 'wrong-rate', 'nonfinite'])
def test_uncertain_or_invalid_render_keeps_scratch_and_primary_error(monkeypatch, failure):
    monkeypatch.setattr(audio, 'tool', Path)
    paths = []
    def native(code, *, resource_path, timeout, args):
        out = Path(args['out'])
        paths.append(out)
        (out / 'render.rpp').write_text('evidence')
        if failure == 'timeout':
            raise reaper.BridgeTimeout('native still executing')
        if failure != 'missing':
            data = np.zeros((240, 2))
            if failure == 'nonfinite':
                data[0] = np.nan
            sf.write(out / 'audio.wav', data, 48000 if failure == 'wrong-rate' else 24000,
                     subtype='FLOAT')
    monkeypatch.setattr(reaper, 'execute', native)
    with pytest.raises((reaper.BridgeTimeout, ValueError, sf.LibsndfileError)) as error:
        call()
    assert paths[0].is_dir() and (paths[0] / 'render.rpp').read_text() == 'evidence'
    assert str(paths[0]) in error.value.__notes__[0]
    shutil.rmtree(paths[0])


LIVE = os.environ.get('TACTUS_REAPER_RESOURCE_PATH')
BUNDLE = os.environ.get('TACTUS_REAPER_BUNDLE')


@pytest.mark.skipif(not LIVE or not BUNDLE, reason='Opt in with isolated native REAPER')
def test_live_private_render_restores_tab_accepts_silence_and_retains_failed_setup():
    def native(code):
        return reaper.execute(code, resource_path=LIVE)
    before = native("return {tab=tostring(reaper.EnumProjects(-1,'')), tracks=reaper.CountTracks(0)}")
    for channels in (1, 2):
        rendered = audio.render('assert(args == nil)', resource_path=LIVE,
                                reaper_bundle=BUNDLE, seconds=.01, sample_rate=24000,
                                channels=channels)
        assert rendered.shape == (240, channels) and np.isfinite(rendered).all()
        assert native("return {tab=tostring(reaper.EnumProjects(-1,'')), tracks=reaper.CountTracks(0)}") == before
    with pytest.raises(reaper.BridgeError, match='authored failure') as error:
        audio.render("error('authored failure')", resource_path=LIVE,
                     reaper_bundle=BUNDLE, seconds=.01, sample_rate=24000, channels=2)
    assert native("return {tab=tostring(reaper.EnumProjects(-1,'')), tracks=reaper.CountTracks(0)}") == before
    scratch = Path(error.value.__notes__[0].split(' at ', 1)[1].split(';', 1)[0])
    assert scratch.is_dir()
    # No request remains executing on this synchronous setup error; this test owns scratch.
    shutil.rmtree(scratch)
