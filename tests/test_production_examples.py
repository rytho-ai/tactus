"""Protect loop-tail exclusion and the documented channel/master handoff patterns."""

from __future__ import annotations

import runpy
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import run

EXAMPLES = Path(__file__).parents[1] / "skills" / "examples"


def test_phrases_wrap_between_valid_starts_without_tail_or_source_mutation():
    phrase = runpy.run_path(str(EXAMPLES / "boundaries.py"))["phrase"]
    # The source body is an authored grid; the trailing five frames are not loopable.
    body = np.arange(24, dtype=np.float64)
    source = np.concatenate((body, np.full(5, 999.0)))
    original = source.copy()
    for index in range(17):
        cut = phrase(source, body_end=24, starts=(0, 8, 16), frames=8, index=index)
        np.testing.assert_array_equal(cut, body[(index % 3) * 8 : (index % 3 + 1) * 8])
        assert len(cut) == 8
        cut[:] = 0  # A phrase owns its data, even when the processor changes it in place.
    np.testing.assert_array_equal(source, original)
    with pytest.raises(ValueError, match="fit completely"):
        phrase(source, body_end=24, starts=(0, 20), frames=8, index=0)


def test_stem_example_sums_before_master_and_keeps_master_separate(tmp_path):
    render = runpy.run_path(str(EXAMPLES / "boundaries.py"))["render"]
    outputs = render(master_gain_db=-6.0)["outputs"]
    np.testing.assert_array_equal(
        outputs["pre_master"], outputs["channel_a_post"] + outputs["channel_b_post"]
    )
    np.testing.assert_allclose(outputs["mix"], outputs["pre_master"] * 10 ** (-6 / 20))
    result = run(EXAMPLES / "boundaries.py", out=tmp_path / "printed")
    assert set(result["outputs"]) == {
        "channel_a_post", "channel_b_post", "pre_master", "mix"
    }
    for path in result["outputs"].values():
        audio, rate = sf.read(path, always_2d=True)
        assert rate == 8000
        assert audio.shape == (64000, 2)
        assert np.isfinite(audio).all() and np.max(np.abs(audio)) < 1


def test_minimal_entry_runs_without_materials(tmp_path):
    result = run(EXAMPLES / "minimal.py", out=tmp_path / "minimal")
    audio, rate = sf.read(result["outputs"]["mix"])
    assert rate == 48000 and audio.shape == (48000,)
    assert np.isfinite(audio).all() and np.max(np.abs(audio)) <= 0.2 + 2**-23
