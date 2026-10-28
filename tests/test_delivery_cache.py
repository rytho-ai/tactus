"""Cached lossless exports preserve audio/metadata and invalidate changed inputs."""
import json

import numpy as np
import pytest

from tactus._delivery import web
from tactus.analysis import level


def deliver(tmp_path, name, audio, **options):
    out = tmp_path / name
    out.mkdir()
    web(audio, 8000, out=out, codec='flac', peaks=9,
        cache=str(tmp_path / 'cache'), **options)
    return out, json.loads((out / 'bundle.json').read_text())


def test_identical_outputs_reuse_but_changed_track_recomputes(tmp_path, monkeypatch):
    x = np.sin(np.arange(8000) * .3) * .1
    audio = {'voice': x, 'drums': x * .5}
    a, first = deliver(tmp_path, 'a', audio)
    calls = []
    original = level.loudness
    def loudness(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(level, 'loudness', loudness)
    b, second = deliver(tmp_path, 'b', audio, run_identity={'run': '/another-run'})
    assert not calls
    assert first['outputs'] == second['outputs']
    assert second['source']['run'] == 'another-run'
    for entry in first['outputs'].values():
        assert (a / entry['file']).read_bytes() == (b / entry['file']).read_bytes()
    deliver(tmp_path, 'c', {**audio, 'voice': x * .75})
    assert len(calls) == 1
    # Export copies are independent: modifying a delivery cannot poison cache.
    (a / first['outputs']['voice']['file']).write_bytes(b'corrupt export')
    _, fourth = deliver(tmp_path, 'd', audio)
    assert len(calls) == 1 and fourth['outputs'] == second['outputs']


@pytest.mark.parametrize('artifact', ['audio', 'record.json', 'record.sha256'])
def test_corrupt_entry_is_recomputed(tmp_path, monkeypatch, artifact):
    audio = {'voice': np.ones(8000) * .1}
    _, first = deliver(tmp_path, 'a', audio)
    folder = next((tmp_path / 'cache').iterdir())
    (folder / artifact).write_bytes(b'corrupted')
    calls = []
    original = level.loudness
    def loudness(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(level, 'loudness', loudness)
    _, second = deliver(tmp_path, 'b', audio)
    assert len(calls) == 1 and first['outputs'] == second['outputs']


def test_options_and_implementation_invalidate(tmp_path, monkeypatch):
    from tactus import _delivery_cache
    audio = {'voice': np.ones(8000) * .1}
    deliver(tmp_path, 'a', audio)
    deliver(tmp_path, 'b', audio, bit_depth=16)
    assert len(list((tmp_path / 'cache').iterdir())) == 2
    monkeypatch.setattr(_delivery_cache, 'implementation', lambda: 'new-code')
    deliver(tmp_path, 'c', audio)
    assert len(list((tmp_path / 'cache').iterdir())) == 3


def test_headroom_and_analysis_use_original_samples_not_pcm_identity(tmp_path):
    # Both prints quantize to the same PCM24, but their original levels differ.
    x = np.full(8000, .1, dtype=np.float64)
    _, first = deliver(tmp_path, 'a', {'voice': x})
    _, second = deliver(tmp_path, 'b', {'voice': x + 1e-10})
    assert first['outputs']['voice']['source_sha256'] == second['outputs']['voice']['source_sha256']
    assert len(list((tmp_path / 'cache').iterdir())) == 2


def test_cache_cannot_be_inside_export(tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    with pytest.raises(ValueError, match='outside'):
        web({'voice': np.ones(8000) * .1}, 8000, out=out, codec='flac', cache=str(out / 'cache'))
    assert not (out / 'cache').exists()


def test_optional_loudness_skips_analysis_preserving_audio_and_peaks(tmp_path, monkeypatch):
    x = np.sin(np.arange(8000) * .3) * .1
    a, first = deliver(tmp_path, 'measured', {'voice': x})
    def unexpected(*_):
        raise AssertionError('Unrequested loudness analysis ran')
    monkeypatch.setattr(level, 'loudness', unexpected)
    b, second = deliver(tmp_path, 'live', {'voice': x}, loudness=False)
    left, right = first['outputs']['voice'], second['outputs']['voice']
    assert (a / left['file']).read_bytes() == (b / right['file']).read_bytes()
    assert left['peaks'] == right['peaks'] and left['peak_dbfs'] == right['peak_dbfs']
    assert right['integrated_lufs'] is None
    assert second['measurements']['integrated_lufs'] is False
    assert first['measurements']['integrated_lufs'] is True
    assert len(list((tmp_path / 'cache').iterdir())) == 2


def test_unmeasured_export_does_not_import_analysis(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'tactus.analysis', None)
    _, bundle = deliver(tmp_path, 'no-analysis', {'voice': np.zeros(8000)}, loudness=False)
    assert bundle['measurements']['integrated_lufs'] is False
