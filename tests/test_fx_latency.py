"""Host-compensated buffering: stream boundaries, initialization and fixed latency."""

import numpy as np
import pytest

from tactus import fx


class BufferedHost:
    """A pure delay whose host strips startup delay and flushes reset=True calls.

    This models the observable Pedalboard contract, independent of Tactus framing.
    """

    def __init__(self, latency=7):
        self.reported_latency_samples = latency
        self.reset()

    def reset(self):
        self.pending = None
        self.skip = self.reported_latency_samples

    def __call__(self, audio, rate, *, reset):
        if reset:
            self.reset()
        if self.pending is None:
            self.pending = np.zeros((self.reported_latency_samples, *audio.shape[1:]), np.float32)
        joined = np.concatenate([self.pending, audio])
        result, self.pending = joined[: len(audio)], joined[len(audio) :]
        skip = min(self.skip, len(result))
        self.skip -= skip
        result = result[skip:]
        if reset and len(result) < len(audio):
            count = max(len(audio) - len(result), self.reported_latency_samples, 3)
            flushed = self(np.zeros((count, *audio.shape[1:]), np.float32), rate, reset=False)
            result = np.concatenate([result, flushed])[: len(audio)]
        return result


@pytest.mark.parametrize("frames", [1, 19, 52, 101])
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("latency", [0, 7, 80])
def test_stream_keeps_first_and_last_samples_and_explicit_tail(frames, channels, latency):
    x = np.linspace(0.1, 0.9, frames, dtype=np.float32)
    if channels == 2:
        x = np.column_stack([x, -x])
    before = x.copy()
    calls = []
    host = BufferedHost(latency)
    result = fx.process_automated(
        host, x, 1000, calls.append, block_seconds=0.02, tail_seconds=0.003
    )
    want = np.pad(x, (0, 3) if channels == 1 else ((0, 3), (0, 0)))
    np.testing.assert_array_equal(result, want)
    np.testing.assert_array_equal(x, before)
    assert calls == [start / 1000 for start, _ in fx._block_bounds(frames + 3, 20)]
    repeated = fx.process_automated(
        host, x, 1000, lambda t: None, block_seconds=0.02, tail_seconds=0.003
    )
    np.testing.assert_array_equal(repeated, want)


def test_late_initial_latency_is_settled_before_audio():
    class LateHost(BufferedHost):
        preparations = 0

        def __call__(self, audio, rate, *, reset):
            if reset:
                self.preparations += 1
                self.reported_latency_samples = 5 if self.preparations == 1 else 13
            return super().__call__(audio, rate, reset=reset)

    host = LateHost(0)
    x = np.arange(80, dtype=np.float32)
    np.testing.assert_array_equal(fx.process_automated(host, x, 1000, lambda t: None), x)
    assert host.preparations == 3


def test_unstable_initialization_fails_with_a_bound():
    class UnstableHost(BufferedHost):
        def __call__(self, audio, rate, *, reset):
            if reset:
                self.reported_latency_samples += 1
            return super().__call__(audio, rate, reset=reset)

    with pytest.raises(ValueError, match="did not stabilize"):
        fx.process_automated(UnstableHost(), np.ones(100), 1000, lambda t: None)


def test_latency_changing_automation_fails_instead_of_returning_misaligned_audio():
    host = BufferedHost()

    def update(t):
        if t > 0:
            host.reported_latency_samples = 11

    with pytest.raises(ValueError, match="latency changed"):
        fx.process_automated(host, np.ones(100), 1000, update)
