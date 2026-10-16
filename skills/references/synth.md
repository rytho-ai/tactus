# Synthesis building blocks

`tactus.synth` provides synthesis building blocks and physical piano/bowed-string
models. For `piano` and `bowed_string`, read [instrument models](instruments.md) for
notes, pedals, continuous bow events, voicing and licensing. Waveform, detune,
envelope shape, decay, brightness and grain choices are yours;
every timbre-shaping value is an explicit argument. Combine the blocks with NumPy,
[builtin DSP](dsp.md), Pedalboard or your own functions. The
[instrument examples](../examples/README.md#synthesis-examples) show one way to assemble
them and are meant to be rewritten. The building-block implementations are short and oracle-checked; when
you need a variation, read one with `inspect.getsource(tactus.synth.saw)` and copy it into
the work as your own function.

```python
import numpy as np
from tactus import dsp, synth

sr, n = 48000, 48000
pitch = 220 * 2 ** (synth.envelope(-2, [(0.08, 0, -4)], sr, frames=n) / 12)   # scoop
tone = synth.saw(pitch, sr, frames=n) + 0.3 * synth.pulse(pitch / 2, sr, frames=n, width=0.3)
cutoff = synth.envelope(800, [(0.02, 8000, 3), (0.9, 1500, -2)], sr, frames=n)
voice = dsp.svf(tone, sr, mode="lowpass", cutoff_hz=cutoff, q=2.5)
bell = synth.sine(440, sr, frames=n, phase_mod=0.3 * synth.sine(1540, sr, frames=n))  # FM, β≈1.9
hit = synth.resonators(synth.noise(4800, seed=3), sr, freqs_hz=[310, 854, 1675], decays_s=[1.2, 0.7, 0.4])
```

## Conventions

- Generators return mono float64 `(frames,)`; pan with `dsp.pan` and mix with NumPy.
  `piano` and `grains` with per-grain `pan` return stereo `(frames, 2)`.
- Frequency, width and `phase_mod` accept a scalar or one value per frame.
- Phase is in cycles everywhere (`phase()` output, `phase=`, `phase_mod=`), never radians.
- Output is deterministic for identical arguments. `noise`, `piano` and `bowed_string`
  require explicit seeds; use different seeds for independent layers. NumPy does not
  guarantee identical random streams across its versions: noise is reproducible within the
  work's locked environment, and a NumPy upgrade can change it.
- Inputs are never modified. Outputs are not clipped or normalized.

## Functions

- `phase(freq_hz, sample_rate, *, frames, start=0.0)`: cumulative phase; frame i holds
  `start + sum(freq[:i]) / sample_rate`. Not wrapped, so glides stay continuous.
  |freq| must stay below Nyquist; negative frequency runs backwards.
- `sine(freq_hz, sample_rate, *, frames, phase=0.0, phase_mod=0.0)`: `sin(2π(phase + phase_mod))`.
  FM/PM is `phase_mod=D * sine(f_m, ...)` with depth `D` in cycles. It deviates frequency by
  `2π·D·f_m` Hz; a classic radian index β is `D = β / (2π)` (β = 2 → D ≈ 0.32). `sine` accepts
  any depth; sidebands above Nyquist fold back (alias) as in other FM implementations.
- `saw(...)`: rising -1..+1 sawtooth with PolyBLEP band limiting. The first frame of a
  cycle sits mid-jump. Aliasing is greatly reduced, not removed. Upper harmonics are
  slightly darker than an ideal band-limited saw (at 48 kHz about -1 dB at 9 kHz, -2 dB at
  12 kHz, compared with Csound `vco2`).
- `pulse(..., width=0.5)`: +1 for the first `width` of each cycle, -1 after; `0<width<1`,
  per-frame width for PWM. Average is `2*width-1`; no DC removal. Width 0.5 is square.
- `triangle(...)`: +1 at cycle start, -1 at mid-cycle, PolyBLAMP band limited.
- `saw`, `pulse` and `triangle` reject an instantaneous frequency (including `phase_mod`)
  at or above Nyquist, because band limiting fails there; the error names the frequency, the
  frame and the `2π·D·f_m` deviation. Use `sine` for deep FM, or modulate a band-limited
  oscillator gently.
- `noise(frames, *, seed, color="white")`: white is uniform in [-1, 1) from NumPy PCG64;
  pink is that noise through Paul Kellet's refined filter (about -3 dB/octave from ~10 Hz at
  44.1-48 kHz), scaled by 0.11 and not peak-bounded.
- `envelope(start, segments, sample_rate, *, frames=None)`: segments are
  `(seconds, target, curve)`. Boundaries are absolute, `frame_of(cumulative seconds)`; each
  segment reaches its target on its boundary frame. `curve=0` is linear; otherwise
  `a + (b-a)(1-e^(c·x))/(1-e^c)` (Csound `transeg`): positive starts slowly, negative starts
  quickly, defined through zero. Zero-length segments jump. Without `frames` the result ends
  on the final target (last boundary + 1 frames); `frames` cuts or holds the final value.
  Use it for amplitude, pitch (in semitones or Hz), cutoff or any control.
- `resonators(excitation, sample_rate, *, freqs_hz, decays_s, gains=None)`: parallel
  two-pole modes. A unit impulse rings each mode as `gain·r^n·sin(2π f (n+1)/sr)`, falling
  60 dB in its decay. Mono or multichannel excitation keeps its layout and length; pad
  with zeros to hear the full ring. Csound `mode` with `Q = π f T60 / ln 1000` matches its shape.
- `pluck(freq_hz, sample_rate, *, excitation, frames, decay_s, brightness=0.5)`:
  Karplus-Strong with a two-tap damping filter (weight `0.5·(1-brightness)`) and allpass
  tuning (within a few cents). The fundamental decays 60 dB in `decay_s`; with brightness
  below 1, upper partials decay faster. Frequency is fixed per call (20 Hz to sr/4).
  An excitation with DC offset leaves a decaying offset; remove the mean first.
- `grains(source, sample_rate, *, onsets_s, positions_s, durations_s, frames, rate=1.0,
  gain=1.0, pan=None, window="hann")`: overlap-adds an explicit grain list from mono
  `source`. Onsets/durations round with `frame_of`; `rate` is source frames per output frame
  (negative plays backwards) with linear interpolation; reads outside the source are silent.
  Per-grain arrays or scalars; the caller decides density and randomness. `window` is
  `"hann"` (sin² sampled at frame centres) or `"triangle"`.

## Performance

NumPy/SciPy vectorized except the Karplus-Strong loop and grain overlap-add, which use
cached Numba kernels (first use compiles or loads the cache). Measured on this development
machine for 60 s at 48 kHz: glide saw 0.10 s, PWM pulse 0.12 s, pink noise 0.08 s,
20 resonator modes 0.21 s, pluck 0.01 s, 20,000 grains of one length 0.09 s (0.36 s when
every grain length differs, since the window is recomputed per length).

## Sources

Implemented from published methods; no Csound or SuperCollider source was read or copied,
so no upstream license applies. Csound is the behavioral oracle in tests; SC/Csound unit
names identify comparable designs: PolyBLEP/PolyBLAMP (Välimäki et
al.; cf. `vco2`, `Saw`, `Pulse`, `LFTri`), Kellet pink filter, `transeg`-style segments,
two-pole modal resonators (`mode`, `Ringz`/`Klank`), Karplus-Strong with allpass tuning
(Jaffe-Smith; `pluck`, `Pluck`), and windowed grains (`partikkel`, `GrainBuf`).
Oracle checks: `tests/test_synth_oracles.py` (runs when `csound` is installed).
