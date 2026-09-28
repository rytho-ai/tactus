"""Atmospheric lo-fi / ambient full song.

Pads (OB-Xf VST3, slow chord bed) and blurred PaulStretch textures (pytimestretch
extreme_stretch, on a crate vocal one-shot and the crate keys loop) carry the
foreground. A soft SFZ bass and a lightly time-stretched crate keys loop fill the
middle register. Drums (crate one-shots) are sparse and mostly absent, entering only
for the fuller middle. Arc: quiet opening -> rising -> full middle -> fading end.

Key: A minor. Tempo: 74 BPM. ~46 bars / ~2:29.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pedalboard
import pytimestretch
import soundfile as sf

from tactus import fx, material, stage, tool

# ---------------------------------------------------------------------------
# Materials (pinned with `tactus material add`; refs are content-addressed).
# ---------------------------------------------------------------------------

KEYS_LOOP = "sha256:ddec6235c47ff8fcd7190eea487b298a3d5358d49988e03ed887d197fe22c42b"  # OS_RSV_73_piano_chords_3_u_never_call_Am.wav (73bpm, Am, 4 bars)
VOCAL_TEXTURE = "sha256:d32b5fc57cf97243437fa5d75bb89db1e4a68dda6e7e02559de9a9adcda362f1"  # MCB_one_shot_fx_vocal_memory_01_64_d_major.wav
WIND_AMBIENCE = "sha256:b5db7f54a51ff00369e3c851dfe83e7685d31841233458ae8c4af3f1efacfb43"  # MO_ELX_fx_ambience_wind_C#min.wav
VOCAL_ONE_SHOT = "sha256:6eef6609ce9e39adc01fa0e9ae77a428abb8cc100517a958cc0f3113d19409a5"  # JSB_VB_vox_one_shot_ahh.wav (intro gesture, un-stretched)
KICK = "sha256:052396c08773289c56dcea08568a4e3852613ec0679c14cc7d423ae2aa0856a3"  # Dark_Kick14.wav
HAT = "sha256:c2f856e4bcae32d57a199d0d10caebb779f03f57dd2a0549fc15732ceee8a0f5"  # RKU_LT001_Hihat_Closed_13.wav
SNARE = "sha256:15a617634f4c80634e71f3f1efe15cae7cbfcfa923de71f728e1deb91f13f24f"  # hbk_kit05_oneshot_snare02.wav
SFZ_BASS_PACK = "tree:sha256:5b0331d6c2d34aabd30b2098c19b4f39d4f2b57c01b2fe7cc64d00d5685b468a"  # karoryfer.black-and-blue-basses

TOOLS = Path(__file__).resolve().parent / "tools"
OB_XF = TOOLS / "OB-Xf.vst3"

# ---------------------------------------------------------------------------
# Timing. 74 BPM, 4/4. Bars are 1-indexed; `bar_time(n)` is the start of bar n.
# ---------------------------------------------------------------------------

SAMPLE_RATE = 44100
BPM = 74.0
BAR_SEC = 4 * 60.0 / BPM  # 3.24324... s


def bar_time(bar: int) -> float:
    return (bar - 1) * BAR_SEC


# (name, first_bar, bar_after_last)
SECTIONS = [
    ("intro", 1, 9),
    ("rise", 9, 17),
    ("core_a1", 17, 25),
    ("core_a2", 25, 33),
    ("core_b", 33, 41),
    ("outro", 41, 47),
]
SECTION_T = {name: (bar_time(a), bar_time(b)) for name, a, b in SECTIONS}
TOTAL_SEC = bar_time(47)
TOTAL_FRAMES = round(TOTAL_SEC * SAMPLE_RATE)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def load(ref: str, rate: int = SAMPLE_RATE) -> np.ndarray:
    """Read a pinned material as float32 (frames, channels) at the project rate."""
    audio, sr = sf.read(material(ref), dtype="float32", always_2d=True)
    if sr != rate:
        from fractions import Fraction

        frac = Fraction(rate, sr).limit_denominator(1000)
        audio = scipy_resample(audio, frac.numerator, frac.denominator)
    return audio


def scipy_resample(audio: np.ndarray, up: int, down: int) -> np.ndarray:
    from scipy.signal import resample_poly

    return resample_poly(audio, up, down, axis=0).astype(np.float32)


def to_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    return audio[:, :2]


def new_bus(frames: int = TOTAL_FRAMES) -> np.ndarray:
    return np.zeros((frames, 2), dtype=np.float32)


def place(bus: np.ndarray, clip: np.ndarray, start_sec: float, gain: float = 1.0) -> None:
    """Additively mix `clip` into `bus` at `start_sec`, clipped to the bus bounds."""
    start = round(start_sec * SAMPLE_RATE)
    end = start + clip.shape[0]
    b0, b1 = max(0, start), min(bus.shape[0], end)
    c0, c1 = b0 - start, b1 - start
    if b1 > b0:
        bus[b0:b1] += clip[c0:c1] * gain


def fit_length(audio: np.ndarray, frames: int) -> np.ndarray:
    """Trim or zero-pad to an exact frame count (for extreme_stretch's approximate length)."""
    if audio.shape[0] >= frames:
        return audio[:frames]
    pad = np.zeros((frames - audio.shape[0], audio.shape[1]), dtype=audio.dtype)
    return np.concatenate([audio, pad], axis=0)


def fade(
    audio: np.ndarray, in_sec: float = 0.0, out_sec: float = 0.0, rate: int = SAMPLE_RATE
) -> np.ndarray:
    out = audio.copy()
    n_in = round(in_sec * rate)
    n_out = round(out_sec * rate)
    if n_in > 0:
        out[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)[:, None]
    if n_out > 0:
        out[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)[:, None]
    return out


def section_envelope(
    points: list[tuple[float, float]], frames: int = TOTAL_FRAMES, rate: int = SAMPLE_RATE
) -> np.ndarray:
    """Piecewise-linear gain envelope from (time_seconds, gain) breakpoints."""
    times = np.array([p[0] for p in points])
    gains = np.array([p[1] for p in points])
    t = np.arange(frames) / rate
    return np.interp(t, times, gains).astype(np.float32)


def peak_normalize(audio: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 1e-9:
        return audio
    return audio * (target_peak / peak)


def rms_dbfs(audio: np.ndarray, rate: int, bounds: list[tuple[float, float]]) -> list[float]:
    out = []
    for a, b in bounds:
        seg = audio[round(a * rate) : round(b * rate)]
        r = float(np.sqrt(np.mean(seg**2))) if seg.size else 0.0
        out.append(20 * np.log10(max(r, 1e-9)))
    return out


# ---------------------------------------------------------------------------
# A hand-rolled Standard MIDI File writer (Type 0). No MIDI library is a
# dependency of the Tactus environment, and sfizz_render needs a real .mid file.
# ---------------------------------------------------------------------------


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def write_midi(
    path: Path,
    events: list[tuple[float, str, int, int]],
    bpm: float = BPM,
    ticks_per_beat: int = 480,
) -> None:
    """events: (time_seconds, 'on'|'off', note, velocity), absolute time from 0."""
    us_per_beat = round(60_000_000 / bpm)
    sec_per_tick = (us_per_beat / 1_000_000) / ticks_per_beat

    msgs: list[tuple[float, bytes]] = [(0.0, b"\xff\x51\x03" + us_per_beat.to_bytes(3, "big"))]
    for t, kind, note, vel in events:
        status = 0x90 if kind == "on" else 0x80
        msgs.append((t, bytes([status, note, vel])))
    end_t = max(t for t, *_ in events) + 3.0
    msgs.append((end_t, b"\xff\x2f\x00"))
    msgs.sort(key=lambda m: m[0])

    track_data = bytearray()
    last_tick = 0
    for t, payload in msgs:
        tick = round(t / sec_per_tick)
        delta = max(0, tick - last_tick)
        track_data += _vlq(delta)
        track_data += payload
        last_tick = tick

    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_beat)
    track = b"MTrk" + struct.pack(">I", len(track_data)) + bytes(track_data)
    path.write_bytes(header + track)


# ---------------------------------------------------------------------------
# Pads: OB-Xf slow chord bed, one voicing per section, filter breathing added
# after the plugin render.
# ---------------------------------------------------------------------------

# Round 2: velocities lowered from draft 1 (producer: pad was "too loud and jarring,
# covering the chords" i.e. the keys stem).
#
# Round 3: a chroma analysis of KEYS_LOOP (librosa.feature.chroma_cqt, one window per
# bar) showed it isn't a static "Am" pad at all -- it alternates E7 (E, G#, B, D) on
# bars 1/3 and Am7 (A, C, E, G) on bars 2/4, i.e. a V7-i7 vamp in A minor. Rewrote the
# pad's pitch classes to stay inside that same {A, B, C, D, E, G, G#} set -- fixed the
# note clash, but not the complaint that followed.
#
# Round 4: producer said it still feels like "two main threads that don't connect" --
# pad and keys were harmonically compatible by round 3 but still two independent
# layers: the pad held one static chord for a whole 8-bar section while the loop kept
# alternating E7/Am7 underneath it every single bar, so the two never met on the same
# clock. Fix: phase-lock the pad's chord to the loop's own bar-level alternation for
# every section where the loop plays (rise..core_b), so a new pad chord lands on every
# bar boundary the loop itself turns over on, in the same dominant/tonic order the
# chroma analysis measured. `intro`/`outro` (loop silent) keep a single static dyad --
# there's nothing there to lock onto.

TONIC = [57, 60, 64, 67]  # Am7: A3 C4 E4 G4 -- matches the loop's Am7 bars
DOMINANT = [64, 68, 71, 74]  # E7: E4 G#4 B4 D5 -- matches the loop's E7 bars

# (section, velocity, extra_shimmer_notes) for the bar-synced span. `extra` notes are
# always the chord's own low tones doubled an octave up, so brightening the voicing
# through the arc never introduces a pitch outside the current chord.
SYNCED_SECTIONS = [
    ("rise", 30, 0),
    ("core_a1", 38, 1),
    ("core_a2", 42, 1),
    ("core_b", 46, 2),
]
STAGGER = 0.15
NOTE_OVERLAP = 0.25  # legato: next bar's chord starts before this one's off, OB-Xf's
# long release blurs the seam instead of a hard chord-change click.

INTRO_OUTRO_CHORDS = [
    ("intro", [57, 64], 24, 0.8),  # A3 E4 dyad, sparse
    ("outro", [57, 60, 64], 24, 0.6),  # Am, fading
]


def _octave_up(notes: list[int], count: int) -> list[int]:
    return [notes[i % len(notes)] + 12 for i in range(count)]


def _synced_pad_events() -> list[tuple[bytes, float]]:
    """One chord per bar across rise..core_b, phase-locked to KEYS_LOOP's own 4-bar
    tile (see the round-4 note above): bar 0 and 2 of each tile get the loop's
    dominant (E7) color, bar 1 and 3 get its tonic (Am7) color."""
    events: list[tuple[bytes, float]] = []
    global_bar = 0
    for section, vel, extra_count in SYNCED_SECTIONS:
        t0, t1 = SECTION_T[section]
        bar = t0
        while bar < t1 - 1e-6:
            local_bar = global_bar % 4
            base = DOMINANT if local_bar in (0, 2) else TONIC
            notes = base + _octave_up(base, extra_count)
            for i, note in enumerate(notes):
                events.append((bytes([0x90, note, vel]), bar + i * STAGGER))
            off_t = min(bar + BAR_SEC + NOTE_OVERLAP, TOTAL_SEC)
            for note in notes:
                events.append((bytes([0x80, note, 0]), off_t))
            bar += BAR_SEC
            global_bar += 1
    return events


@stage
def pad_bed(release_tail_sec: float = 6.0) -> np.ndarray:
    synth = pedalboard.load_plugin(str(tool(str(OB_XF))))
    fx.set_param(synth, "amp_env_attack_ms", 1800, unit="ms")
    fx.set_param(synth, "amp_env_release_ms", 2600, unit="ms")
    fx.set_param(synth, "amp_env_sustain", 100, unit="%")
    fx.set_param(synth, "filter_cutoff_hz", 4000, unit="Hz")
    fx.set_param(synth, "filter_resonance", 8, unit="%")
    fx.set_param(synth, "osc_2_volume", -7, unit="dB")
    fx.set_param(synth, "osc_2_detune_cents", 6, unit="cents")
    fx.set_param(synth, "volume", 70, unit="%")
    # The bar-synced span holds two overlapping chords (up to 6 notes each) for
    # NOTE_OVERLAP seconds at every bar boundary; 8 voices (the default) would steal
    # notes there.
    fx.set_param(synth, "polyphony_voices", 16, unit="Voices")

    messages: list[tuple[bytes, float]] = []
    for section, notes, vel, stagger in INTRO_OUTRO_CHORDS:
        t0, t1 = SECTION_T[section]
        for i, note in enumerate(notes):
            messages.append((bytes([0x90, note, vel]), t0 + i * stagger))
        off_t = t1 - 0.15
        for note in notes:
            messages.append((bytes([0x80, note, 0]), off_t))
    messages += _synced_pad_events()

    duration = TOTAL_SEC + release_tail_sec
    audio = fx.render_instrument(synth, messages, duration=duration, sample_rate=SAMPLE_RATE)

    # Slow filter breathing (an evolving pad, not a static one), plus a touch of
    # chorus for width and reverb for the ambient wash.
    chain = pedalboard.Pedalboard(
        [
            pedalboard.LadderFilter(
                mode=pedalboard.LadderFilter.Mode.LPF12, cutoff_hz=1400, resonance=0.15
            ),
            pedalboard.Chorus(rate_hz=0.18, depth=0.2, mix=0.25),
            pedalboard.Reverb(
                room_size=0.75, damping=0.5, wet_level=0.28, dry_level=0.8, width=1.0
            ),
        ]
    )

    def update(t: float) -> None:
        # 90-second breathing cycle, lowered and narrowed (was 500-2600 Hz) so the pad
        # stays underneath the keys loop's register instead of competing with it.
        cutoff = 1100 + 700 * np.sin(2 * np.pi * t / 90.0)
        chain[0].cutoff_hz = float(max(250, cutoff))

    processed = fx.process_automated(chain, audio, SAMPLE_RATE, update, tail_seconds=2.0)
    return fit_length(processed, TOTAL_FRAMES)


# ---------------------------------------------------------------------------
# Keys: the Am crate loop, lightly stretched to the song tempo (73 -> 74 BPM,
# already 4 bars), tiled through the rise / core sections.
# ---------------------------------------------------------------------------


@stage
def keys_bed() -> np.ndarray:
    loop = to_stereo(load(KEYS_LOOP))
    loop_bars = 4
    target_frames = round(loop_bars * BAR_SEC * SAMPLE_RATE)
    ratio = target_frames / loop.shape[0]
    stretched = pytimestretch.time_stretch(
        loop, SAMPLE_RATE, duration_ratio=ratio, backend="rubberband"
    )
    stretched = fit_length(fade(stretched, in_sec=0.05, out_sec=0.05), target_frames)

    bus = new_bus()
    t = SECTION_T["rise"][0]
    end_t = SECTION_T["core_b"][1]
    loop_dur = target_frames / SAMPLE_RATE
    while t < end_t:
        place(bus, stretched, t)
        t += loop_dur

    envelope = section_envelope(
        [
            (0.0, 0.0),
            (SECTION_T["rise"][0], 0.0),
            (SECTION_T["rise"][0] + 4.0, 0.35),
            (SECTION_T["core_a1"][0], 0.55),
            (SECTION_T["core_b"][0], 0.75),
            (SECTION_T["core_b"][1] - 6.0, 0.75),
            (SECTION_T["core_b"][1], 0.0),
            (TOTAL_SEC, 0.0),
        ]
    )
    bus = bus * envelope[:, None]

    chain = pedalboard.Pedalboard(
        [
            pedalboard.LadderFilter(
                mode=pedalboard.LadderFilter.Mode.LPF12, cutoff_hz=2600, resonance=0.1
            ),
            pedalboard.Reverb(
                room_size=0.55, damping=0.6, wet_level=0.22, dry_level=0.85, width=1.0
            ),
        ]
    )
    return chain(bus.T, SAMPLE_RATE, reset=True).T.astype(np.float32)


# ---------------------------------------------------------------------------
# Textures: PaulStretch (extreme_stretch) on a crate vocal one-shot into a
# whole-song wash, plus a stretched slice of the keys loop for the core, plus
# a looped wind-ambience bed. This is the foreground layer of the mix.
# ---------------------------------------------------------------------------


@stage
def texture_bed() -> np.ndarray:
    bus = new_bus()

    # 1) Vocal memory -> a long, blurred wash across the whole song.
    vocal = to_stereo(load(VOCAL_TEXTURE))
    vocal_target = TOTAL_FRAMES
    vocal_ratio = vocal_target / vocal.shape[0]
    vocal_wash = pytimestretch.extreme_stretch(vocal, SAMPLE_RATE, duration_ratio=vocal_ratio)
    vocal_wash = fit_length(vocal_wash, TOTAL_FRAMES)
    vocal_wash = fade(vocal_wash, in_sec=10.0, out_sec=14.0)
    vocal_wash = peak_normalize(vocal_wash, target_peak=0.35)
    place(bus, vocal_wash, 0.0, gain=0.9)

    # 2) The Am keys loop, PaulStretched into a slow harmonic wash for the
    #    fuller middle (core_a1 through core_b).
    keys_src = to_stereo(load(KEYS_LOOP))
    core_start, core_end = SECTION_T["core_a1"][0], SECTION_T["core_b"][1]
    core_len_frames = round((core_end - core_start) * SAMPLE_RATE)
    keys_ratio = core_len_frames / keys_src.shape[0]
    keys_wash = pytimestretch.extreme_stretch(keys_src, SAMPLE_RATE, duration_ratio=keys_ratio)
    keys_wash = fit_length(keys_wash, core_len_frames)
    keys_wash = fade(keys_wash, in_sec=8.0, out_sec=10.0)
    keys_wash = peak_normalize(keys_wash, target_peak=0.3)
    place(bus, keys_wash, core_start, gain=0.8)

    # 3) Wind ambience, looped with a crossfade across the whole song, kept low.
    wind = to_stereo(load(WIND_AMBIENCE))
    wind_bus = new_bus()
    xfade = round(1.5 * SAMPLE_RATE)
    seg_len = wind.shape[0]
    t = 0
    prev_tail = None
    while t < TOTAL_FRAMES:
        seg = wind.copy()
        if prev_tail is not None:
            n = min(xfade, seg.shape[0])
            ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
            seg[:n] = seg[:n] * ramp + prev_tail[:n] * (1 - ramp)
        place(wind_bus, seg, t / SAMPLE_RATE)
        prev_tail = np.zeros_like(seg)
        prev_tail[: min(xfade, seg.shape[0])] = seg[-min(xfade, seg.shape[0]) :]
        t += seg_len - xfade
    wind_env = section_envelope(
        [
            (0.0, 0.12),
            (SECTION_T["core_b"][0], 0.12),
            (SECTION_T["core_b"][1], 0.22),
            (TOTAL_SEC - 5.0, 0.3),
            (TOTAL_SEC, 0.05),
        ]
    )
    place(bus, wind_bus[:TOTAL_FRAMES] * wind_env[:, None], 0.0, gain=1.0)

    # 4) A tiny un-stretched vocal gesture right at the open, for a human touch
    #    before the textures take over (too short for extreme_stretch itself).
    gesture = to_stereo(load(VOCAL_ONE_SHOT))
    gesture = fade(gesture, in_sec=0.05, out_sec=0.3) * 0.25
    place(bus, gesture, 1.5)

    chain = pedalboard.Pedalboard(
        [
            pedalboard.LadderFilter(
                mode=pedalboard.LadderFilter.Mode.LPF12, cutoff_hz=5200, resonance=0.05
            ),
            pedalboard.Reverb(
                room_size=0.85, damping=0.4, wet_level=0.2, dry_level=0.88, width=1.0
            ),
        ]
    )
    return chain(bus.T, SAMPLE_RATE, reset=True).T.astype(np.float32)


# ---------------------------------------------------------------------------
# Bass: SFZ (sfizz_render) playing a slow, sparse root-note line under the
# chord changes. Absent in the intro, drops out in the outro.
# ---------------------------------------------------------------------------

BASS_NOTES = [
    ("rise", 45),  # A2
    ("core_a1", 41),  # F2
    ("core_a2", 48),  # C3
    ("core_b", 43),  # G2
    ("outro", 45),  # A2
]


@stage
def bass_bed() -> np.ndarray:
    sfz_root = material(SFZ_BASS_PACK)
    sfz_program = sfz_root / "Programs" / "07-darkblack_ghost.sfz"
    sfizz_bin = tool(str(TOOLS / "sfizz_render"))

    events: list[tuple[float, str, int, int]] = []
    for section, note in BASS_NOTES:
        t0, t1 = SECTION_T[section]
        hit_t = t0
        while hit_t < t1 - 0.5:
            events.append((hit_t, "on", note, 58))
            events.append((hit_t + BAR_SEC * 1.8, "off", note, 0))
            hit_t += BAR_SEC * 2

    with tempfile.TemporaryDirectory(prefix="tactus-bass-") as tmp:
        midi_path = Path(tmp) / "bass.mid"
        write_midi(midi_path, events)
        wav_path = Path(tmp) / "bass_render.wav"
        subprocess.run(
            [
                str(sfizz_bin),
                "--sfz",
                str(sfz_program),
                "--midi",
                str(midi_path),
                "--wav",
                str(wav_path),
                "--samplerate",
                str(SAMPLE_RATE),
                "--use-eot",
            ],
            check=True,
            capture_output=True,
        )
        audio = to_stereo(load_wav(wav_path))
    audio = fit_length(audio, TOTAL_FRAMES)

    chain = pedalboard.Pedalboard(
        [
            pedalboard.LadderFilter(
                mode=pedalboard.LadderFilter.Mode.LPF12, cutoff_hz=650, resonance=0.1
            ),
            pedalboard.Compressor(threshold_db=-20, ratio=2.5, attack_ms=10, release_ms=200),
        ]
    )
    processed = chain(audio.T, SAMPLE_RATE, reset=True).T.astype(np.float32)
    return peak_normalize(processed, target_peak=0.55)


def load_wav(path: Path) -> np.ndarray:
    audio, _sr = sf.read(path, dtype="float32", always_2d=True)
    return audio


# ---------------------------------------------------------------------------
# Drums: sparse crate one-shots, present only in the fuller middle. Soft,
# filtered, mostly kick + hat with an occasional snare accent.
# ---------------------------------------------------------------------------


@stage
def drum_bed() -> np.ndarray:
    kick = to_stereo(load(KICK))
    hat = to_stereo(load(HAT))
    snare = to_stereo(load(SNARE))

    bus = new_bus()
    t0, t1 = SECTION_T["core_a2"][0], SECTION_T["core_b"][1]
    bar = t0
    bar_i = 0
    while bar < t1:
        place(bus, kick, bar, gain=0.5)
        place(bus, hat, bar + BAR_SEC * 0.5, gain=0.28)
        place(bus, hat, bar + BAR_SEC * 1.5, gain=0.22)
        if bar_i % 4 == 2:
            place(bus, snare, bar + BAR_SEC * 1.0, gain=0.32)
        bar += BAR_SEC * 2
        bar_i += 1

    envelope = section_envelope(
        [
            (0.0, 0.0),
            (SECTION_T["core_a2"][0], 0.0),
            (SECTION_T["core_a2"][0] + 3.0, 1.0),
            (SECTION_T["core_b"][1] - 6.0, 1.0),
            (SECTION_T["core_b"][1], 0.0),
            (TOTAL_SEC, 0.0),
        ]
    )
    bus = bus * envelope[:, None]

    chain = pedalboard.Pedalboard(
        [
            pedalboard.LadderFilter(
                mode=pedalboard.LadderFilter.Mode.LPF12, cutoff_hz=2200, resonance=0.15
            ),
            pedalboard.Compressor(threshold_db=-18, ratio=3.0, attack_ms=5, release_ms=120),
        ]
    )
    processed = chain(bus.T, SAMPLE_RATE, reset=True).T.astype(np.float32)
    return peak_normalize(processed, target_peak=0.45)


# ---------------------------------------------------------------------------
# Master bus
# ---------------------------------------------------------------------------


def master(mix: np.ndarray) -> np.ndarray:
    chain = pedalboard.Pedalboard(
        [
            pedalboard.Compressor(threshold_db=-14, ratio=2.2, attack_ms=20, release_ms=250),
            pedalboard.Limiter(threshold_db=-2.0, release_ms=150),
        ]
    )
    processed = chain(mix.T, SAMPLE_RATE, reset=True).T.astype(np.float32)
    return np.clip(processed, -1.0, 1.0)


def render(
    *,
    pads_gain_db: float = -7.5,
    textures_gain_db: float = -1.0,
    keys_gain_db: float = -1.5,
    bass_gain_db: float = -3.0,
    drums_gain_db: float = -9.0,
) -> dict:
    pads = pad_bed()
    textures = texture_bed()
    keys = keys_bed()
    bass = bass_bed()
    drums = drum_bed()

    def db(x: float) -> float:
        return float(10 ** (x / 20))

    mix = (
        pads * db(pads_gain_db)
        + textures * db(textures_gain_db)
        + keys * db(keys_gain_db)
        + bass * db(bass_gain_db)
        + drums * db(drums_gain_db)
    )
    mix = master(mix)

    return {
        "sample_rate": SAMPLE_RATE,
        "outputs": {
            "mix": mix,
            "pads": np.clip(pads * db(pads_gain_db), -1.0, 1.0),
            "textures": np.clip(textures * db(textures_gain_db), -1.0, 1.0),
            "drums": np.clip(drums * db(drums_gain_db), -1.0, 1.0),
            "bass": np.clip(bass * db(bass_gain_db), -1.0, 1.0),
            "keys": np.clip(keys * db(keys_gain_db), -1.0, 1.0),
        },
    }
