"""Render an original, deterministic pop-ballad study from Python source.

The reference recording is never sampled, imported, or used by this renderer.
The ``sfz`` palette preserves a continuous MIDI piano performance and sends it
to a supplied multi-sampled instrument through ``sfizz_render``.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from soundfont import SoundFont

from tactus import material, tool

RATE = 32_000
BPM = 120
BEAT = 60.0 / BPM
BAR = 4 * BEAT
SEED = 41377

# Drum one-shots and soundfont are pinned by content: import once with
# `tactus material add <file>` (see README) before running the "sampled" palette or
# "one-shots"/"loop" drum modes.
SOUNDFONT = "sha256:74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0"
DRUM_MATERIALS = {
    "kick": ("sha256:1ce5adcf77763bdbd3ad9492e1d7bf1f16b8b77877d183d21804a0c6aae42b4e", 0.42),
    "snare": ("sha256:9c1e1e3d5f4a777204ff60b4f578498bd9662e44deb48caabbff1bda027d0fba", 0.055),
    "hat": ("sha256:c1af239d645c4f6a4e769e10bde768bd2395f7a29ed60d68838ee77b7b98c984", 0.06),
    "ride": ("sha256:1e8ded3118c6530655e07ad1d4472bfa2cc1f2472ec954f7d7c576d56ffe8888", 0.035),
}
LOFI_DRUM_LOOP = (
    "sha256:183d6ef248b28a41b7e2b795138052781bd325f37d6397bacf7016432e5b45c1",
    0.34,
)
LOFI_LOOP_EQ = {
    "sub_cut_hz": 110,
    "sub_cut_amount": 0.28,
    "presence_dip_hz": 3_200,
    "presence_dip_width_hz": 1_700,
    "presence_dip_amount": 0.34,
    "output_gain": 0.78,
}
PROGRAMS = {"piano": (0, 5.0), "guitar": (24, 1.7), "strings": (48, 1.2), "lead": (26, 3.2)}
MIDI_TICKS_PER_BEAT = 480

SECTIONS = [
    ("intro", 4),
    ("verse_1", 12),
    ("pre_1", 4),
    ("chorus_1", 8),
    ("interlude", 4),
    ("verse_2", 8),
    ("pre_2", 4),
    ("chorus_2", 8),
    ("bridge", 8),
    ("final_chorus", 8),
    ("outro", 8),
]

# Four-chord cycles are original to this piece. Chord tones are MIDI pitches.
VERSE = [
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Dadd9", 50, (57, 62, 66, 64)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
PRE = [
    ("Em7", 40, (52, 55, 59, 62)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("F#m7", 42, (54, 57, 61, 64)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
CHORUS = [
    ("Dadd9", 50, (57, 62, 66, 64)),
    ("A/C#", 49, (57, 61, 64, 69)),
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Em7", 40, (52, 55, 59, 62)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Asus4", 45, (57, 62, 64, 69)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
BRIDGE = [
    ("Em7", 40, (52, 55, 59, 62)),
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]


def hz(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    a = min(n, max(1, int(attack * RATE)))
    r = min(n, max(1, int(release * RATE)))
    env = np.ones(n, dtype=np.float32)
    env[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def piano(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.35) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    wave = np.zeros(n, dtype=np.float32)
    for partial in range(1, 7):
        detune = 1 + 0.00012 * partial * partial
        decay = np.exp(-t * (1.1 + 0.53 * partial))
        wave += np.sin(2 * np.pi * f * partial * detune * t) * decay / partial**1.35
    hammer = np.sin(2 * np.pi * f * 8 * t) * np.exp(-t * 85) * 0.07
    return (wave + hammer) * envelope(n, 0.006, 0.18) * 0.17


def guitar(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.15) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    wave = np.zeros(n, dtype=np.float32)
    for partial in range(1, 8):
        wave += (
            np.sin(2 * np.pi * f * partial * t + partial * 0.19)
            * np.exp(-t * (2.1 + partial * 0.74))
            / partial**1.1
        )
    return wave * envelope(n, 0.003, 0.10) * 0.10


def strings(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.6) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    vibrato = 0.0023 * np.sin(2 * np.pi * 5.1 * t)
    phase = 2 * np.pi * f * (t + vibrato)
    wave = np.sin(phase) + 0.35 * np.sin(2.003 * phase) + 0.15 * np.sin(3.001 * phase)
    return wave.astype(np.float32) * envelope(n, 0.45, 0.55) * 0.055


def lead(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.2) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    vibrato = 0.0018 * np.sin(2 * np.pi * 5.4 * t) * np.clip((t - 0.25) * 3, 0, 1)
    phase = 2 * np.pi * f * (t + vibrato)
    wave = np.sin(phase) + 0.38 * np.sin(2 * phase) + 0.19 * np.sin(3 * phase)
    wave += 0.07 * np.sin(4 * phase)
    return wave.astype(np.float32) * envelope(n, 0.06, 0.19) * 0.13


def bass(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.1) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    phase = 2 * np.pi * hz(midi) * t
    wave = np.sin(phase) + 0.29 * np.sin(2 * phase) * np.exp(-t * 4)
    return wave.astype(np.float32) * np.exp(-t * 0.9) * envelope(n, 0.007, 0.10) * 0.20


def drum(kind: str, rng: np.random.Generator) -> np.ndarray:
    duration = {"kick": 0.34, "snare": 0.26, "hat": 0.09, "ride": 0.65}[kind]
    n = int(duration * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    if kind == "kick":
        phase = 2 * np.pi * (57 * t + 70 * (1 - np.exp(-t * 36)) / 36)
        return np.sin(phase) * np.exp(-t * 20) * 0.43
    noise = rng.standard_normal(n).astype(np.float32)
    noise -= np.convolve(noise, np.ones(23, dtype=np.float32) / 23, mode="same")
    if kind == "snare":
        tone = np.sin(2 * np.pi * 178 * t) * np.exp(-t * 17)
        return (0.22 * noise * np.exp(-t * 24) + 0.12 * tone).astype(np.float32)
    if kind == "ride":
        return (noise * np.exp(-t * 7) * 0.038).astype(np.float32)
    return (noise * np.exp(-t * 45) * 0.055).astype(np.float32)


def sampled_drums() -> dict[str, np.ndarray]:
    """Read four pinned one-shots from the shared pool without changing their originals."""
    result = {}
    for kind, (ref, gain) in DRUM_MATERIALS.items():
        path = material(ref)
        signal, source_rate = sf.read(path, dtype="float32", always_2d=True)
        mono = signal.mean(axis=1)
        frames = int(len(mono) * RATE / source_rate)
        original = np.arange(len(mono), dtype=np.float32) / source_rate
        target = np.arange(frames, dtype=np.float32) / RATE
        resampled = np.interp(target, original, mono).astype(np.float32)
        resampled -= float(np.mean(resampled))
        tail = min(len(resampled), int(0.025 * RATE))
        resampled[-tail:] *= np.linspace(1, 0, tail, dtype=np.float32)
        result[kind] = resampled * gain
    return result


def sampled_drum_loop() -> np.ndarray:
    """Read the pinned 120 BPM stereo drum loop without changing its source bytes."""
    ref, gain = LOFI_DRUM_LOOP
    path = material(ref)
    signal, source_rate = sf.read(path, dtype="float32", always_2d=True)
    frames = int(len(signal) * RATE / source_rate)
    original = np.arange(len(signal), dtype=np.float32) / source_rate
    target = np.arange(frames, dtype=np.float32) / RATE
    resampled = np.column_stack(
        [np.interp(target, original, signal[:, channel]) for channel in range(signal.shape[1])]
    ).astype(np.float32)
    frequencies = np.fft.rfftfreq(len(resampled), 1 / RATE)
    sub_cut = 1 - LOFI_LOOP_EQ["sub_cut_amount"] * np.exp(
        -0.5 * (frequencies / LOFI_LOOP_EQ["sub_cut_hz"]) ** 2
    )
    presence_dip = 1 - LOFI_LOOP_EQ["presence_dip_amount"] * np.exp(
        -0.5
        * ((frequencies - LOFI_LOOP_EQ["presence_dip_hz"]) / LOFI_LOOP_EQ["presence_dip_width_hz"])
        ** 2
    )
    shaped = np.fft.irfft(
        np.fft.rfft(resampled, axis=0) * (sub_cut * presence_dip)[:, None], axis=0
    )
    return shaped.astype(np.float32) * gain * LOFI_LOOP_EQ["output_gain"]


def add(
    bus: np.ndarray, sound: np.ndarray, start: float, gain: float = 1.0, pan: float = 0
) -> None:
    position = max(0, round(start * RATE))
    end = min(position + len(sound), len(bus))
    if end <= position:
        return
    if sound.ndim == 2:
        bus[position:end] += sound[: end - position] * gain
        return
    angle = (pan + 1) * np.pi / 4
    bus[position:end, 0] += sound[: end - position] * gain * np.cos(angle)
    bus[position:end, 1] += sound[: end - position] * gain * np.sin(angle)


def section_at(bar: int) -> tuple[str, int, int]:
    cursor = 0
    for name, bars in SECTIONS:
        if cursor <= bar < cursor + bars:
            return name, bar - cursor, bars
        cursor += bars
    raise IndexError(bar)


def harmony(name: str, local_bar: int) -> tuple[str, int, tuple[int, ...]]:
    if name.startswith("pre"):
        return PRE[local_bar % len(PRE)]
    if "chorus" in name:
        return CHORUS[local_bar % len(CHORUS)]
    if name == "bridge":
        return BRIDGE[local_bar % len(BRIDGE)]
    return VERSE[local_bar % len(VERSE)]


VERSE_MELODY = [
    [(0.5, 1.0, 71), (2.0, 0.6, 69), (3.0, 0.8, 66)],
    [(0.2, 1.3, 67), (2.0, 0.7, 71), (3.0, 0.8, 69)],
    [(0.5, 0.8, 66), (1.5, 0.8, 69), (2.6, 1.0, 74)],
    [(0.0, 1.3, 73), (2.0, 1.7, 69)],
]
PRE_MELODY = [
    [(0, 1, 71), (1.5, 0.8, 74), (2.5, 1.1, 76)],
    [(0, 1.5, 74), (2, 1.6, 78)],
    [(0, 0.8, 76), (1, 0.8, 74), (2, 1.8, 73)],
    [(0, 1.5, 73), (2, 1.8, 76)],
]
CHORUS_MELODY = [
    [(0, 1.3, 74), (1.8, 0.8, 78), (2.9, 0.9, 76)],
    [(0, 1.9, 76), (2.3, 1.4, 73)],
    [(0, 1.8, 78), (2, 0.8, 76), (3, 0.8, 74)],
    [(0, 0.9, 71), (1.2, 2.3, 74)],
    [(0, 1.2, 76), (1.5, 0.8, 74), (2.5, 1.0, 71)],
    [(0.2, 1.5, 74), (2, 1.7, 79)],
    [(0, 1.1, 78), (1.5, 1.1, 76), (3, 0.7, 74)],
    [(0, 3.5, 73)],
]
BRIDGE_MELODY = [
    [(0, 1.8, 71), (2.2, 1.5, 74)],
    [(0, 1.5, 73), (2, 1.6, 71)],
    [(0, 1.2, 69), (1.6, 1.1, 71), (3, 0.8, 74)],
    [(0, 3.5, 76)],
]


def ambience(signal: np.ndarray, wet: float) -> np.ndarray:
    result = signal.copy()
    for seconds, gain, swap in [
        (0.093, 0.42, True),
        (0.167, 0.32, False),
        (0.293, 0.22, True),
        (0.419, 0.14, False),
    ]:
        offset = int(seconds * RATE)
        tail = signal[:-offset, ::-1] if swap else signal[:-offset]
        result[offset:] += tail * gain * wet
    return result


def midi_variable_length(value: int) -> bytes:
    """Encode a non-negative Standard MIDI variable-length quantity."""
    encoded = [value & 0x7F]
    value >>= 7
    while value:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(encoded))


def render_sfz_piano(
    notes: list[tuple[float, float, int, int]], total_seconds: float, sfz_path: Path
) -> np.ndarray:
    """Render one continuous MIDI piano performance through a pinned SFZ instrument."""
    if not sfz_path.is_file():
        raise FileNotFoundError(f"SFZ program was not found in the pinned instrument: {sfz_path}")
    sfizz = tool("sfizz_render")

    events: list[tuple[int, int, bytes]] = [
        (0, 0, bytes((0xC0, 0))),
        (0, 0, bytes((0xB0, 64, 127))),
    ]
    # Release the pedal just before each harmony change. Leaving it down for
    # the whole song makes adjacent chords accumulate beneath the melody.
    for bar in range(1, round(total_seconds / BAR)):
        change = bar * BAR
        off = round((change - 0.055) * BPM / 60 * MIDI_TICKS_PER_BEAT)
        on = round((change + 0.030) * BPM / 60 * MIDI_TICKS_PER_BEAT)
        events.extend(
            [
                (off, 0, bytes((0xB0, 64, 0))),
                (on, 0, bytes((0xB0, 64, 127))),
            ]
        )
    for start, duration, pitch, velocity in notes:
        on = max(0, round(start * BPM / 60 * MIDI_TICKS_PER_BEAT))
        off = max(on + 1, round((start + duration) * BPM / 60 * MIDI_TICKS_PER_BEAT))
        events.extend(
            [
                (on, 1, bytes((0x90, pitch, max(1, min(127, velocity))))),
                (off, 0, bytes((0x80, pitch, 0))),
            ]
        )
    pedal_off = round((total_seconds + 1.4) * BPM / 60 * MIDI_TICKS_PER_BEAT)
    events.append((pedal_off, 0, bytes((0xB0, 64, 0))))
    events.sort()

    track = bytearray(b"\x00\xff\x51\x03" + int(60_000_000 / BPM).to_bytes(3, "big"))
    previous_tick = 0
    for tick, _, message in events:
        track.extend(midi_variable_length(tick - previous_tick))
        track.extend(message)
        previous_tick = tick
    track.extend(b"\x00\xff\x2f\x00")
    header = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01" + MIDI_TICKS_PER_BEAT.to_bytes(2, "big")
    midi = header + b"MTrk" + len(track).to_bytes(4, "big") + track

    with tempfile.TemporaryDirectory(prefix="tactus-sfz-") as scratch:
        midi_path = Path(scratch) / "performance.mid"
        wav_path = Path(scratch) / "piano.wav"
        midi_path.write_bytes(midi)
        subprocess.run(
            [
                str(sfizz),
                "--sfz",
                str(sfz_path),
                "--midi",
                str(midi_path),
                "--wav",
                str(wav_path),
                "--samplerate",
                str(RATE),
                "--quality",
                "10",
                "--polyphony",
                "128",
                "--use-eot",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        rendered, source_rate = sf.read(wav_path, dtype="float32", always_2d=True)
    if source_rate != RATE:
        raise ValueError(f"sfizz rendered at {source_rate} Hz, expected {RATE} Hz")
    frames = int((total_seconds + 2) * RATE)
    result = np.zeros((frames, 2), dtype=np.float32)
    result[: min(frames, len(rendered))] = rendered[:frames]
    return result


def _render(
    palette: str,
    soundfont: SoundFont | None,
    sfz_path: Path | None,
    drum_mode: str,
) -> dict:
    rng = np.random.default_rng(SEED)
    drum_samples = (
        sampled_drums() if drum_mode == "one-shots" and palette in ("sampled", "sfz") else None
    )
    drum_loop = sampled_drum_loop() if drum_mode == "loop" else None
    piano_notes: list[tuple[float, float, int, int]] = []

    def tone(kind: str, pitch: int, seconds: float) -> np.ndarray:
        if soundfont is not None:
            program, gain = PROGRAMS[kind]
            return soundfont.note(program, pitch, seconds) * gain
        return {"piano": piano, "guitar": guitar, "strings": strings, "lead": lead}[kind](
            pitch, seconds
        )

    def hit(kind: str) -> np.ndarray:
        return drum_samples[kind] if drum_samples is not None else drum(kind, rng)

    total_bars = sum(bars for _, bars in SECTIONS)
    frames = int((total_bars * BAR + 2) * RATE)
    buses = {
        name: np.zeros((frames, 2), dtype=np.float32)
        for name in ("piano", "guitar", "strings", "lead", "bass", "drums")
    }
    timeline = []
    loop_bar = 0
    for bar in range(total_bars):
        name, local, section_bars = section_at(bar)
        chord_name, root, notes = harmony(name, local)
        start = bar * BAR
        is_chorus = "chorus" in name
        is_pre = name.startswith("pre")
        is_verse = name.startswith("verse")
        timeline.append({"bar": bar + 1, "section": name, "chord": chord_name})

        # Broken-chord piano stays present as the intimate center of the mix.
        pattern = [0, 2, 1, 3, 0, 2, 1, 3]
        for step, index in enumerate(pattern):
            velocity = 0.78 if step % 4 else 1.0
            if is_chorus:
                velocity *= 1.12
            if name == "outro":
                velocity *= 0.70 * (1 - local / (section_bars + 2))
            velocity *= float(rng.uniform(0.93, 1.07))
            note_start = start + step * BEAT / 2
            if sfz_path is not None:
                piano_notes.append((note_start, 0.58, notes[index], round(72 * velocity)))
            else:
                add(
                    buses["piano"],
                    tone("piano", notes[index], 0.58),
                    note_start,
                    velocity,
                    -0.24 + 0.48 * (step % 2),
                )

        if sfz_path is None and name not in ("intro", "outro"):
            for beat, index in [(0.5, 1), (1.5, 2), (2.5, 3), (3.5, 1)]:
                add(
                    buses["guitar"],
                    tone("guitar", notes[index] + 12, 0.38),
                    start + beat * BEAT,
                    0.67 if is_verse else 0.88,
                    0.46,
                )

        if sfz_path is None and (is_chorus or is_pre or name == "bridge" or name == "outro"):
            pad_gain = 0.68 if is_pre else 1.0 if is_chorus else 0.57
            for index in (0, 1, 2):
                add(
                    buses["strings"],
                    tone("strings", notes[index], BAR - 0.3),
                    start,
                    pad_gain,
                    [-0.65, 0.0, 0.65][index],
                )

        if name not in ("intro", "interlude", "outro"):
            if is_chorus:
                phrase = CHORUS_MELODY[local % 8]
            elif is_pre:
                phrase = PRE_MELODY[local % 4]
            elif name == "bridge":
                phrase = BRIDGE_MELODY[local % 4]
            else:
                phrase = VERSE_MELODY[local % 4]
            for beat, length, pitch in phrase:
                # Small first-verse restraint; the final chorus is the emotional peak.
                gain = 0.70 if name == "verse_1" else 1.22 if name == "final_chorus" else 1.0
                if sfz_path is not None:
                    piano_notes.append(
                        (start + beat * BEAT, length * BEAT, pitch, round(92 * gain))
                    )
                else:
                    add(
                        buses["lead"],
                        tone("lead", pitch, length * BEAT),
                        start + beat * BEAT,
                        gain,
                        -0.06,
                    )
            if sfz_path is None and name == "final_chorus" and local in (0, 4):
                add(
                    buses["guitar"],
                    tone("guitar", notes[2] + 12, 1.1 * BEAT),
                    start + 3 * BEAT,
                    0.95,
                    0.7,
                )

        if name not in ("intro", "outro"):
            for beat, pitch, length in [(0, root, 1.35), (2, root + 7, 1.25)]:
                if sfz_path is not None:
                    piano_notes.append(
                        (start + beat * BEAT, length * BEAT, pitch, 55 if is_verse else 64)
                    )
                else:
                    add(
                        buses["bass"],
                        bass(pitch, length * BEAT),
                        start + beat * BEAT,
                        0.7 if is_verse else 1.0,
                    )

        # Keep the source loop bar-aligned; the arrangement controls when it enters.
        if drum_loop is not None and name not in ("intro", "outro", "interlude"):
            bar_frames = round(BAR * RATE)
            if len(drum_loop) < bar_frames:
                raise ValueError("Pinned drum loop is shorter than one bar")
            loop_bars = len(drum_loop) // bar_frames
            loop_start = (loop_bar % loop_bars) * bar_frames
            add(buses["drums"], drum_loop[loop_start : loop_start + bar_frames], start)
            loop_bar += 1

        # Half-time verse, wider backbeat in the chorus; never four-on-the-floor.
        elif drum_mode == "one-shots" and name not in ("intro", "outro", "interlude"):
            kick_beats = (0, 2.5) if is_verse or is_pre else (0, 2, 3.5)
            snare_beats = (2,) if is_verse or is_pre else (1, 3)
            kick_accents = (1.0, 0.62) if is_verse or is_pre else (1.0, 0.76, 0.56)
            snare_accents = (0.70,) if is_verse or is_pre else (0.96, 0.84)
            section_gain = 0.82 if is_verse else 0.91 if is_pre else 1.0
            for beat, accent in zip(kick_beats, kick_accents, strict=True):
                add(
                    buses["drums"],
                    hit("kick"),
                    start + beat * BEAT,
                    accent * section_gain * float(rng.uniform(0.94, 1.04)),
                )
            for beat, accent in zip(snare_beats, snare_accents, strict=True):
                add(
                    buses["drums"],
                    hit("snare"),
                    start + beat * BEAT,
                    accent * section_gain * float(rng.uniform(0.93, 1.03)),
                )
            if is_verse and local % 2:
                add(buses["drums"], hit("snare"), start + 3.72 * BEAT, 0.13, 0.06)
            hat_steps = range(0, 8, 2) if is_verse else range(8)
            for step in hat_steps:
                hat_accents = (0.78, 0.46, 0.62, 0.44, 0.74, 0.45, 0.59, 0.42)
                strength = hat_accents[step] * float(rng.uniform(0.92, 1.06))
                add(
                    buses["drums"],
                    hit("hat"),
                    start + step * BEAT / 2,
                    (0.30 if is_verse else 0.44) * section_gain * strength,
                    0.35,
                )
            if is_chorus and local in (0, 4):
                add(buses["drums"], hit("ride"), start, 0.82, -0.47)
            if (is_pre or name == "bridge") and local == section_bars - 1:
                for beat, gain in [(2.5, 0.28), (3.0, 0.38), (3.5, 0.55)]:
                    add(
                        buses["drums"],
                        hit("snare"),
                        start + beat * BEAT,
                        gain * float(rng.uniform(0.92, 1.05)),
                        0.12,
                    )

    if sfz_path is not None:
        buses["piano"] = render_sfz_piano(piano_notes, total_bars * BAR, sfz_path)
    buses["piano"] = ambience(buses["piano"], 0.18 if sfz_path is not None else 0.36)
    buses["guitar"] = ambience(buses["guitar"], 0.28)
    buses["strings"] = ambience(buses["strings"], 0.44)
    buses["lead"] = ambience(buses["lead"], 0.62)
    outro_start = int((total_bars - SECTIONS[-1][1]) * BAR * RATE)
    outro_end = int(total_bars * BAR * RATE)
    fade = np.linspace(1, 0, outro_end - outro_start, dtype=np.float32)[:, None]
    for signal in buses.values():
        signal[outro_start:outro_end] *= fade

    # Source code, not a saved DAW state, defines every musical decision.
    mix = sum(buses.values())
    mix = np.tanh(mix * 1.25).astype(np.float32)
    mix *= 0.88 / max(float(np.max(np.abs(mix))), 1e-9)
    outputs = {"mix": mix}
    for name, signal in buses.items():
        outputs[name] = np.clip(signal, -1, 1).astype(np.float32)
    return {"sample_rate": RATE, "outputs": outputs}


def render(
    *,
    palette: str = "sampled",
    drums: str = "one-shots",
    sfz_piano: str | None = None,
    sfz_program: str | None = None,
) -> dict:
    if palette not in ("sampled", "synthetic", "sfz"):
        raise ValueError(f"Unknown palette: {palette!r}")
    if drums not in ("one-shots", "loop", "none"):
        raise ValueError(f"Unknown drums mode: {drums!r}")
    if palette == "sampled":
        with SoundFont(material(SOUNDFONT), RATE) as soundfont:
            return _render(palette, soundfont, None, drums)
    if palette == "synthetic":
        return _render(palette, None, None, drums)
    # palette == "sfz": sfz_piano is a `tree:sha256:` ref to a folder material (the
    # instrument's `.sfz` programs plus their sample folders); sfz_program names the
    # `.sfz` file inside that tree, relative to its root. This cannot be parity-checked
    # here — no SFZ piano is pinned on this machine.
    if sfz_piano is None or sfz_program is None:
        raise ValueError(
            "sfz_piano (a tree:sha256: ref) and sfz_program (the .sfz file's relative "
            "path) are both required when palette='sfz'"
        )
    sfz_root = material(sfz_piano)
    return _render(palette, None, sfz_root / sfz_program, drums)
