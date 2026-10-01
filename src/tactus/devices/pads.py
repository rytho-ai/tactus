"""Pads: cut material into slices and trigger sounds from named pads (in the manner of an MPC).

Self-contained: copy this file into a work and change it freely. Pad sounds are mono
`(frames,)` or `(frames, channels)` arrays at the work's sample rate; a kit may mix
mono and stereo pads (mono is copied to every channel). Slices may carry a tail past
their cut; one tune or choke value applies to the whole kit.

Reads: numpy · tactus.timing.frame_of
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np

from tactus.timing import frame_of

__all__ = ["play", "slices"]


def slices(sample, sample_rate, *, count=None, at_s=None, tail_s=0.0):
    """Cut `sample` into consecutive pieces and return them as a list.

    `count` gives that many equal slices (boundaries rounded to frames). `at_s` cuts at
    the given source times instead (for example adopted onsets or beats), giving
    `len(at_s) + 1` slices from the start to the end. Supply exactly one of them.
    `tail_s` lets every slice run that much past its cut into the next one (up to the end
    of the sample), so a slice played on a slower or uneven grid rings until a choke stops it.
    """
    sample = np.asarray(sample, dtype=np.float64)
    if (count is None) == (at_s is None):
        raise ValueError("supply exactly one of count or at_s")
    if count is not None:
        if count < 1:
            raise ValueError("count must be at least 1")
        edges = np.floor(np.linspace(0, len(sample), count + 1) + 0.5).astype(int)
    else:
        cuts = [frame_of(t, sample_rate) for t in at_s]
        if any(c <= 0 or c >= len(sample) for c in cuts) or sorted(set(cuts)) != cuts:
            raise ValueError("at_s must be increasing times strictly inside the sample")
        edges = np.array([0, *cuts, len(sample)])
    if tail_s < 0:
        raise ValueError("tail_s must be 0 or more")
    tail = frame_of(tail_s, sample_rate)
    return [sample[a : min(len(sample), b + tail)].copy() for a, b in pairwise(edges)]


def _tuned(sound, semitones):
    if not semitones:
        return sound
    rate = 2.0 ** (semitones / 12.0)
    positions = np.arange(int(len(sound) / rate)) * rate
    index = np.arange(len(sound))
    if sound.ndim == 1:
        return np.interp(positions, index, sound)
    return np.stack([np.interp(positions, index, sound[:, c]) for c in range(sound.shape[1])], axis=1)


def play(hits, pads, sample_rate, *, frames, choke=None, tune=None, fade_s=0.005, per_pad=False):
    """Trigger pad sounds: `hits` are `(start_s, pad, velocity)`, `pads` maps a name to audio.

    Each hit adds its pad's sound, scaled by velocity, at `frame_of(start_s)`; sounds
    overlap and ring out unless choked. `choke` maps pad names to a group: a hit cuts any
    still-ringing earlier hit of the same group (itself included) with a linear fade of
    `fade_s`, the way a closed hat stops an open one. `tune` maps pad names to semitones
    (repitched by resampling). Either may be one value instead of a dict, applying to
    every pad: `tune=-4` repitches the whole kit, `choke=1` puts every pad in one group,
    as for chops of one record. Returns the summed audio, or with `per_pad=True` a dict
    of one stem per pad whose sum is that audio. Output is mono only if every pad is mono.
    """
    kit = {name: np.asarray(sound, dtype=np.float64) for name, sound in pads.items()}
    tune = tune if isinstance(tune, dict) else dict.fromkeys(kit, tune or 0.0)
    choke = choke if isinstance(choke, dict) else ({} if choke is None else dict.fromkeys(kit, choke))
    kit = {name: _tuned(sound, tune.get(name, 0.0)) for name, sound in kit.items()}
    channels = max((s.shape[1] for s in kit.values() if s.ndim == 2), default=0)
    if channels:
        kit = {n: (np.repeat(s[:, None], channels, axis=1) if s.ndim == 1 else s) for n, s in kit.items()}
        if any(s.shape[1] != channels for s in kit.values()):
            raise ValueError("stereo pads must share one channel count")
    shape = (frames, channels) if channels else (frames,)
    stems = {name: np.zeros(shape) for name in kit}
    ordered = sorted(hits, key=lambda hit: hit[0])
    starts = [frame_of(start_s, sample_rate) for start_s, _, _ in ordered]
    fade = max(1, frame_of(fade_s, sample_rate))
    for i, (_, pad, velocity) in enumerate(ordered):
        if pad not in kit:
            raise ValueError(f"unknown pad {pad!r}; pads are {sorted(kit)}")
        begin = starts[i]
        if begin < 0 or begin >= frames:
            continue
        sound = kit[pad] * velocity
        group = choke.get(pad)
        if group is not None:
            later = [starts[j] for j in range(i + 1, len(ordered))
                     if choke.get(ordered[j][1]) == group and starts[j] > begin]
            if later and later[0] - begin < len(sound):
                cut = later[0] - begin
                sound = sound[: cut + fade].copy()
                ramp = np.linspace(1.0, 0.0, len(sound) - cut, endpoint=False)
                sound[cut:] *= ramp[:, None] if sound.ndim == 2 else ramp
        end = min(frames, begin + len(sound))
        stems[pad][begin:end] += sound[: end - begin]
    return stems if per_pad else sum(stems.values(), np.zeros(shape))
