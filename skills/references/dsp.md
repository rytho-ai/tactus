# Builtin DSP

`analysis` reports observations; `dsp` transforms audio. Both are optional: ordinary Python,
custom analysis commands and VST effects remain supported. Built-in calculations use
NumPy/SciPy, with cached Numba kernels for the sequential duck, both delays and automated
lowpass loops; beat tracking and time stretching retain pyqmdsp and pytimestretch.
See [DSP regression tests](https://github.com/rytho-ai/tactus/blob/main/tests/test_dsp_effects.py).

```python
import numpy as np
from tactus import dsp

# mono is a one-dimensional audio array; sr is its integer sample rate.
x = dsp.gain(mono, -6)  # scalar or per-frame dB
x = dsp.fade(x, sr, in_s=0.01, out_s=0.1)  # linear fades on a complete clip
stereo = dsp.pan(x, np.linspace(-1, 1, len(x)))
filtered, state = dsp.biquad(
    stereo,
    sr,
    kind="lowpass",
    frequency_hz=3000,
)
# Continue the same filter on another block; state is an explicit (2, channels) array.
next_filtered, state = dsp.biquad(
    next_stereo_block,
    sr,
    kind="lowpass",
    frequency_hz=3000,
    state=state,
)
```

- `gain`: scalar or per-frame dB, shared across channels.
- `fade`: linear amplitude fades, including endpoints; overlapping fades multiply.
  Durations must fit the clip. It operates on a whole clip, not a streaming fade state.
- `pan`: mono to stereo, -1 left / 0 center / +1 right, equal power (-3.01 dB per side
  at center). Stereo balancing is a different operation; this function rejects stereo.
- `biquad`: `lowpass`, `highpass`, `peak`, `low_shelf`, `high_shelf`. Q is positive;
  frequency is between zero and Nyquist. Gain applies to peak/shelves. Uses the Q-based
  [RBJ Cookbook equations](https://www.w3.org/TR/audio-eq-cookbook/).
  Start with `state=None`, carry returned state between blocks, and process zeros for a
  tail. Parameter changes are not smoothed. Whole/block equality assumes fixed parameters.
- `varispeed` and `fit_rms` are implemented in `dsp`; existing `tactus.fx` imports
  resolve to those same functions. Their float32 behavior and signatures are preserved.

Reusable whole-clip effects also use ordinary arrays:

- `duck(audio, detector, sample_rate, *, threshold_db=-18, ratio=4, attack_ms=5,
  release_ms=100, return_gain=False)`: external peak detector, hard-knee compression,
  no makeup gain or lookahead. Detector and audio must have equal frame counts;
  multichannel detection takes the maximum absolute channel value and applies one gain
  to every audio channel. Attack/release are linear-amplitude envelope time constants;
  zero means immediate. `return_gain=True` returns `(audio, per_frame_linear_gain)` for
  reuse on other signals. Ratio must be at least one.
- `delay(audio, sample_rate, *, delay_seconds=0.15, feedback=0.35, tail_seconds=0)`:
  wet-only fractional feedback delay. Delay accepts scalar or per-input-frame seconds,
  at least one sample; feedback is strictly between -1 and 1. Output appends
  `round(tail_seconds * sample_rate)` frames, holding the last delay value through the
  tail. Moving delay time changes pitch. Add dry audio explicitly when mixing.
- `crossfade_delay(audio, sample_rate, *, delay_seconds=0.15, feedback=0.35,
  tail_seconds=0, crossfade_seconds=0.05)`: the same wet-only layout, feedback range,
  minimum delay and explicit tail convention, using two fixed fractional readheads.
  Both start at the first requested delay. A changed target starts a linear crossfade
  of `round(crossfade_seconds * sample_rate)` samples, which must be at least one.
  Its first sample uses new-head weight `1/N`, and its last uses weight 1. Head positions
  remain fixed during the transition; the latest request is considered on the following
  sample, so intermediate requests can be skipped. The blended wet signal feeds the
  feedback path. This avoids a moving-head pitch glide but can create interference,
  cancellation and amplitude changes; a one-sample transition can click. It adopts the
  Faust probe's dual-head principle with explicit fractional taps and startup semantics,
  rather than promising identical samples to Faust `sdelay`.
- `crossover(audio, sample_rate, *, cutoff_hz=1000)`: returns `(low, high)` from a
  two-way fourth-order Linkwitz–Riley crossover. Scalar cutoff must be strictly between
  zero and Nyquist. Each branch cascades two second-order Butterworth sections. Outputs
  retain input shape/length and are about -6.02 dB at cutoff. Their unprocessed sum has
  flat magnitude response but changes phase; it is not sample-identical to the input.
  Each branch may be processed separately before adding them back together.
- `lowpass(audio, sample_rate, *, cutoff_hz=1000, q=1/sqrt(2))`: two-pole lowpass,
  scalar or per-frame cutoff strictly between zero and Nyquist, positive scalar Q.
  Scalar cutoff uses biquad; varying cutoff uses a topology-preserving state-variable
  filter. Controls are not automatically smoothed.
- `saturate(audio, sample_rate, *, drive_db=12, mix=0.5, oversample=8)`:
  wet transfer `tanh(audio * 10**(drive_db/20))`, with scalar/per-frame drive and linear
  dry/wet mix in `[0, 1]`. Polyphase oversampling accepts 1, 2, 4, 8 or 16; 1 disables
  antialias filtering. Higher factors reduce aliasing, without a universal elimination
  guarantee. Gain is interpolated at the oversampled rate; mix applies at the original
  rate. Length/alignment are retained and mix=0 is an exact copy of the dry input.

These effects reset on each call. Process complete clips, including explicit delay
tails; separate calls are not equivalent to streaming one continuous signal. Saturation
resampling pads clip edges with zeros. For fixed-filter streaming, use `biquad` state.
See the runnable [DSP effects production](https://github.com/rytho-ai/tactus/tree/main/examples/dsp-effects).
The [band processing and delay comparison](https://github.com/rytho-ai/tactus/tree/main/examples/dsp-components) uses
`crossover` and `crossfade_delay` alongside the existing effects.

Numba acceleration is automatic and keeps the same public API. The first call for a
new kernel signature compiles code; later processes can load its on-disk cache. First
use therefore costs more than repeated processing. Fixed-cutoff filtering and saturation
continue to use NumPy/SciPy. No fast-math transformations are enabled in the DSP kernels.

Owned DSP functions allocate float64 output and do not mutate input or caller state.
They do not clip or normalize output automatically; saturation deliberately shapes
amplitude. Empty arrays are supported. Audio uses `(frames,)` or `(frames, channels)`.
Use these functions inside `render()`; no separate DSP CLI or mandatory processor chain is needed.
