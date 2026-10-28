"""The fast outline preserves integer bucket boundaries and all-channel maxima."""
from itertools import pairwise

import numpy as np
import pytest

from tactus._delivery import waveform_peaks


@pytest.mark.parametrize('frames,buckets', [(1, 8), (13, 4), (13, 13), (1003, 160)])
@pytest.mark.parametrize('channels', [None, 1, 2, 5])
@pytest.mark.parametrize('strided', [False, True])
def test_outline_matches_direct_bucket_definition(frames, buckets, channels, strided):
    shape = (frames * 2,) if channels is None else (frames * 2, channels)
    audio = np.random.default_rng(7).standard_normal(shape)
    audio = audio[::2] if strided else audio[:frames]
    edges = np.linspace(0, frames, min(buckets, frames) + 1).astype(int)
    expected = [round(float(np.max(np.abs(audio[a:b]))), 4) for a, b in pairwise(edges)]
    assert waveform_peaks(audio, buckets) == expected
