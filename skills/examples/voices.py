"""Two synthesized voices built from tactus.synth blocks: a moving saw lead and an FM bell.

The waveforms, detune, pitch scoop, filter sweep and FM index are this example's
choices, not defaults. Change any of them; every block is an ordinary function.
"""

import numpy as np

from tactus import dsp, synth

SR = 48000
MOTIF = [(0.0, 74, 0.35), (0.5, 79, 0.35), (1.0, 76, 0.7), (2.0, 81, 0.35), (2.5, 79, 0.9)]


def hz(midi):
    return 440.0 * 2 ** ((np.asarray(midi, dtype=np.float64) - 69) / 12)


def lead_note(freq, seconds, *, detune_cents, scoop_semitones, brightness):
    frames = round(seconds * SR)
    scoop = synth.envelope(-scoop_semitones, [(0.06, 0.0, -4)], SR, frames=frames)
    vibrato = 0.12 * synth.sine(5.5, SR, frames=frames) * synth.envelope(
        0.0, [(0.25, 0.0, 0), (0.3, 1.0, 2)], SR, frames=frames
    )
    pitch = freq * 2 ** ((scoop + vibrato) / 12)
    voices = sum(
        synth.saw(pitch * 2 ** (cents / 1200), SR, frames=frames, phase=offset)
        for cents, offset in ((-detune_cents, 0.13), (0.0, 0.0), (detune_cents, 0.61))
    ) / 3
    voices += 0.3 * synth.pulse(pitch / 2, SR, frames=frames, width=0.3)
    cutoff = synth.envelope(900.0, [(0.02, 9000.0 * brightness, 3), (seconds, 1800.0, -2)], SR, frames=frames)
    filtered = dsp.svf(voices, SR, mode="lowpass", cutoff_hz=cutoff, q=2.5)
    amp = synth.envelope(0.0, [(0.005, 1.0, 0), (seconds - 0.035, 0.7, -2), (0.03, 0.0, 0)], SR, frames=frames)
    return dsp.saturate(filtered * amp, SR, drive_db=10, mix=0.4)


def bell_note(freq, seconds, *, ratio, index):
    """FM bell; `index` is the phase_mod depth in cycles (radian index = 2π·index)."""
    frames = round(seconds * SR)
    depth = synth.envelope(index, [(seconds, 0.0, -6)], SR, frames=frames)
    modulator = depth * synth.sine(freq * ratio, SR, frames=frames)
    carrier = synth.sine(freq, SR, frames=frames, phase_mod=modulator)
    return carrier * synth.envelope(1.0, [(seconds, 0.0, -5)], SR, frames=frames)


def render(*, detune_cents=14.0, scoop_semitones=2.0, brightness=0.8, bell_ratio=3.5, bell_index=1.2):
    total = round(4.0 * SR)
    lead = np.zeros(total)
    bell = np.zeros(total)
    for beat, midi, seconds in MOTIF:
        start = round(beat * 0.5 * SR)
        note = lead_note(
            float(hz(midi)), seconds, detune_cents=detune_cents,
            scoop_semitones=scoop_semitones, brightness=brightness,
        )
        lead[start : start + len(note)] += note
        chime = bell_note(float(hz(midi - 12)), 1.4, ratio=bell_ratio, index=bell_index)
        end = min(total, start + len(chime))
        bell[start:end] += chime[: end - start]
    lead_stereo = dsp.pan(lead * 0.35, -0.2)
    bell_stereo = dsp.pan(bell * 0.2, 0.3)
    return {
        "sample_rate": SR,
        "outputs": {"lead": lead_stereo, "bell": bell_stereo, "mix": lead_stereo + bell_stereo},
    }
