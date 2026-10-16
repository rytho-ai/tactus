"""Seconds-based piano performance: pedals, voice state, tails and body filtering.

Adapted from DAWG (LICENSE.dawg, NOTICE.md). Inputs are validated ordinary tuples;
there is no score/tick grid, normalization, voice stealing or shared mutable state.
"""

import math

import numpy as np

from ..dsp import _scalar
from ..timing import frame_of
from .piano import PianoVoice, params_for
from .piano_dsp import body_eq


def _pedal_events(events, name):
    result = []
    previous = -1.0
    for event in events:
        if len(event) != 2:
            raise ValueError(f"{name} events must be (time_s, state)")
        time, state = _scalar(event[0], f"{name} time_s"), event[1]
        if time < 0 or time < previous or state not in ("up", "half", "down"):
            raise ValueError(f"{name} must be chronological with up/half/down states")
        result.append((time, state))
        previous = time
    return result


def _pedal_at(events, time):
    state = "up"
    for at, next_state in events:
        if at > time:
            break
        state = next_state
    return state


def _notes(notes, pedal, seconds, rate):
    validated = []
    for index, event in enumerate(notes):
        if len(event) != 4:
            raise ValueError("notes must be (start_s, pitch, duration_s, velocity)")
        start, pitch, duration, velocity = (
            _scalar(value, name)
            for value, name in zip(event, ("start_s", "pitch", "duration_s", "velocity"))
        )
        if start < 0 or duration <= 0 or not 21 <= pitch <= 108 or not 0 <= velocity <= 1:
            raise ValueError(
                "notes need start_s >= 0, duration_s > 0, pitch 21..108, velocity 0..1"
            )
        hz = 440 * 2 ** ((pitch - 69) / 12)
        if hz >= 0.45 * rate:
            raise ValueError("piano fundamental must be below 0.45 * sample_rate")
        validated.append(
            {
                "start": start,
                "pitch": pitch,
                "duration": duration,
                "velocity": velocity,
                "hz": hz,
                "index": index,
            }
        )
    ordered = sorted(validated, key=lambda n: (n["start"], n["index"]))
    performed = []
    for note in ordered:
        release = note["start"] + note["duration"]
        end, damp_from = release, None
        state = _pedal_at(pedal, release)
        if state != "up":
            lift = next((t for t, state in pedal if t > release and state == "up"), seconds)
            end = max(release, min(lift, seconds))
            half = (
                release
                if state == "half"
                else next((t for t, state in pedal if release < t < end and state == "half"), None)
            )
            if half is not None:
                end = min(end, half + 2.5)
                damp_from = half - note["start"]
            restrike = next(
                (
                    n
                    for n in ordered
                    if n["velocity"] > 0
                    and n["pitch"] == note["pitch"]
                    and note["start"] < n["start"] < end
                ),
                None,
            )
            if restrike is not None:
                end = max(release, restrike["start"])
        performed.append({**note, "off": end, "damp_from": damp_from})
    return performed


def render_piano(
    notes, rate, *, frames, seed, family, parameters, pedal, soft_pedal, tail_s, tail_fade_s
):
    if not isinstance(seed, str):
        raise TypeError("piano seed must be a string")
    parameters = {} if parameters is None else dict(parameters)
    parameters = {
        key: _scalar(value, f"piano parameter {key}") for key, value in parameters.items()
    }
    try:
        params = params_for(family, **parameters)
    except TypeError as exc:
        raise ValueError(f"Unknown piano parameter: {exc}") from exc
    pedal = _pedal_events(pedal, "pedal")
    soft_pedal = _pedal_events(soft_pedal, "soft_pedal")
    tail_s, tail_fade_s = _scalar(tail_s, "tail_s"), _scalar(tail_fade_s, "tail_fade_s")
    if tail_s <= 0 or not 0 <= tail_fade_s <= tail_s:
        raise ValueError("tail_s must be positive and tail_fade_s between zero and tail_s")
    performed = _notes(notes, pedal, frames / rate, rate)
    audio = np.zeros((frames, 2))
    for note in reversed(performed):
        start = frame_of(note["start"], rate)
        if start >= frames or note["velocity"] == 0:
            continue
        off = start + max(1, frame_of(note["off"] - note["start"], rate))
        soft = {"up": 0.0, "half": 0.5, "down": 1.0}[_pedal_at(soft_pedal, note["start"])]
        voice = PianoVoice(
            note["hz"], note["velocity"], f"{seed}:{note['index']}", params, rate, soft=soft
        )
        end, taper = off + frame_of(tail_s, rate), frame_of(tail_fade_s, rate)
        damped = False
        for at in range(start // 32 * 32, min(frames, end), 32):
            begin = max(at, start)
            count = min(32, frames - at) - (begin - at)
            time = (begin - start) / rate
            if note["damp_from"] is not None and not damped and time >= note["damp_from"]:
                voice.damp(0.5)
                damped = True
            if not voice.released and off < begin + count:
                voice.note_off()
            block = voice.process(count)
            remaining = end - np.arange(begin, begin + count)
            gain = np.ones(count)
            if taper:
                fading = (remaining > 0) & (remaining < taper)
                # Keep source math's scalar cosine order.
                gain[fading] = [
                    0.5 - 0.5 * math.cos(math.pi * left / taper) for left in remaining[fading]
                ]
            gain[remaining <= 0] = 0
            value = block * gain
            audio[begin : begin + count, 0] += value * voice.gl
            audio[begin : begin + count, 1] += value * voice.gr
            if not voice.alive:
                break
    return body_eq(audio, family, rate)
