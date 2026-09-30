"""Cached Numba kernels for owned whole-clip DSP loops.

Callers own validation, layout adaptation and finite-output checks. Kernels use
float64 arrays and preserve the scalar recurrence order from dsp.py, without fastmath.
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def duck_envelope(peaks: np.ndarray, attack_weight: float, release_weight: float) -> np.ndarray:
    envelope = np.empty(len(peaks), dtype=np.float64)
    level = 0.0
    for i in range(len(peaks)):
        peak = peaks[i]
        weight = attack_weight if peak > level else release_weight
        level += weight * (peak - level)
        envelope[i] = level
    return envelope


@njit(cache=True)
def fractional_delay(
    frames: np.ndarray,
    delays: np.ndarray,
    feedback: float,
    total: int,
    capacity: int,
) -> np.ndarray:
    channels = frames.shape[1]
    result = np.zeros((total, channels), dtype=np.float64)
    history = np.zeros((capacity, channels), dtype=np.float64)
    input_frames = frames.shape[0]
    for i in range(total):
        distance = delays[0] if len(delays) == 1 else delays[min(i, input_frames - 1)]
        if distance < i + 1:
            integer = int(np.floor(distance))
            fraction = distance - integer
            newer = i - integer
            if newer >= 0:
                read_index = newer % capacity
                for channel in range(channels):
                    result[i, channel] += (1.0 - fraction) * history[read_index, channel]
            if newer >= 1:
                read_index = (newer - 1) % capacity
                for channel in range(channels):
                    result[i, channel] += fraction * history[read_index, channel]
        write_index = i % capacity
        for channel in range(channels):
            history[write_index, channel] = feedback * result[i, channel]
            if i < input_frames:
                history[write_index, channel] += frames[i, channel]
    return result


@njit(cache=True)
def crossfade_fractional_delay(
    frames: np.ndarray,
    delays: np.ndarray,
    feedback: float,
    total: int,
    capacity: int,
    crossfade_samples: int,
) -> np.ndarray:
    channels = frames.shape[1]
    result = np.zeros((total, channels), dtype=np.float64)
    history = np.zeros((capacity, channels), dtype=np.float64)
    input_frames = frames.shape[0]
    current_delay = delays[0]
    old_delay = current_delay
    new_delay = current_delay
    fade_index = 0
    fading = False

    for i in range(total):
        requested = delays[0] if len(delays) == 1 else delays[min(i, input_frames - 1)]
        if not fading and requested != current_delay:
            old_delay = current_delay
            new_delay = requested
            fade_index = 0
            fading = True

        if fading:
            fade_index += 1
            weight = fade_index / crossfade_samples
            for head in range(2):
                distance = old_delay if head == 0 else new_delay
                scale = 1.0 - weight if head == 0 else weight
                if distance < i + 1:
                    integer = int(np.floor(distance))
                    fraction = distance - integer
                    newer = i - integer
                    if newer >= 0:
                        read_index = newer % capacity
                        for channel in range(channels):
                            result[i, channel] += (
                                scale * (1.0 - fraction) * history[read_index, channel]
                            )
                    if newer >= 1:
                        read_index = (newer - 1) % capacity
                        for channel in range(channels):
                            result[i, channel] += scale * fraction * history[read_index, channel]
            if fade_index == crossfade_samples:
                current_delay = new_delay
                fading = False
        else:
            distance = current_delay
            if distance < i + 1:
                integer = int(np.floor(distance))
                fraction = distance - integer
                newer = i - integer
                if newer >= 0:
                    read_index = newer % capacity
                    for channel in range(channels):
                        result[i, channel] += (1.0 - fraction) * history[read_index, channel]
                if newer >= 1:
                    read_index = (newer - 1) % capacity
                    for channel in range(channels):
                        result[i, channel] += fraction * history[read_index, channel]

        write_index = i % capacity
        for channel in range(channels):
            history[write_index, channel] = feedback * result[i, channel]
            if i < input_frames:
                history[write_index, channel] += frames[i, channel]

        if not fading:
            current_delay = new_delay
    return result


@njit(cache=True)
def variable_svf(
    frames: np.ndarray,
    a1: np.ndarray,
    a2: np.ndarray,
    a3: np.ndarray,
    m0: np.ndarray,
    m1: np.ndarray,
    m2: np.ndarray,
) -> np.ndarray:
    """Simper TPT state-variable filter; output = m0*input + m1*band + m2*low per frame."""
    output = np.empty_like(frames)
    channels = frames.shape[1]
    state1 = np.zeros(channels, dtype=np.float64)
    state2 = np.zeros(channels, dtype=np.float64)
    for i in range(frames.shape[0]):
        for channel in range(channels):
            v0 = frames[i, channel]
            v3 = v0 - state2[channel]
            v1 = a1[i] * state1[channel] + a2[i] * v3
            v2 = state2[channel] + a2[i] * state1[channel] + a3[i] * v3
            state1[channel] = 2.0 * v1 - state1[channel]
            state2[channel] = 2.0 * v2 - state2[channel]
            output[i, channel] = m0[i] * v0 + m1[i] * v1 + m2[i] * v2
    return output
