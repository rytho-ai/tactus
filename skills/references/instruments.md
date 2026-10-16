# Piano and bowed-string synthesis

Use `tactus.synth.piano` for an acoustic piano part and `tactus.synth.bowed_string`
for a continuous bowed voice. Both use owned Python/NumPy/SciPy/Numba code adapted
from DAWG under MIT, with no samples, weights, VST or JavaScript installation.
They return fresh float64 arrays, retain headroom and do not normalize or add room
reverb. Choose gain, arrangement and further DSP in the work. An explicit seed is
required; locked dependencies and saved renders remain the reproducibility boundary.

```python
from tactus import synth

sr = 44100
piano = synth.piano(
    [(0, 60, 0.4, 0.6), (0.5, 67, 0.4, 0.8)], sr,
    frames=3 * sr, seed="piano-a", family="felt",
    pedal=[(0, "down"), (1.8, "up")],
)
violin = synth.bowed_string(
    440, sr, frames=3 * sr, hold_s=1.5, seed=17, body_size=1.0,
    vibrato_hz=5, vibrato_cents=12,
    events=[{"kind": "slur", "time_s": 0.8, "freq_hz": 660, "hold_s": 1.0}],
)
```

## Piano

`piano(notes, sample_rate, *, frames, seed, family="grand", parameters=None,
pedal=(), soft_pedal=(), tail_s=8.0, tail_fade_s=0.25)` returns `(frames, 2)`.
Sample rate is an integer >=8000. Notes are `(start_s, pitch, duration_s, velocity)`
tuples, as in `devices.sampler`: nonnegative start, positive duration, MIDI pitch
21..108 (fractions allowed), velocity 0..1. Velocity zero is silent. The fundamental
must lie below 0.45 * sample_rate. Onsets and durations round to nearest frames,
half up. Notes overlap without automatic stealing; frames cuts the delivery.

Seed is a string, combined with each note's original input index. Keep note ordering
and seed when comparing parameter choices. `family` selects grand or felt defaults;
parameters then override those values. The felt family sets felt=1, hardness=0.3,
noise=0.6; other defaults match grand.

| Parameter | Grand default | Range / meaning |
|---|---:|---|
| hardness | 0.5 | 0..1, hammer brightness |
| touch | 1 | 0..1, velocity sensitivity; zero uses hammer velocity 0.8 |
| inharm | 1 | 0..4, string stiffness multiplier |
| unison | 0.7 | 0..30 cents, low-partial aftersound detuning |
| decay | 1 | 0.1..4, free-string decay multiplier |
| release | 1 | 0.1..4, key-release damping multiplier |
| strike | 0.12 | 0.04..0.3, hammer position along string |
| after | 0.3 | 0..1, slow aftersound share (internally capped at 0.95) |
| knock | 0.5 | 0..1, hammer/board mechanical level |
| noise | 0.25 | 0..1, key-off mechanics (and felt thud) |
| felt | 0 | 0..1, felt-strip voicing |
| width | 0.6 | 0..1, keyboard stereo spread |
| stretch | 1 | 0..1, stiffness-derived octave stretch; zero keeps equal temperament |

Pedal and soft-pedal lanes contain chronological `(time_s, state)` tuples, with
`state` up/half/down. Sustain defers note-off to pedal-up or a same-pitch restrike;
a half pedal adds a 0.5 s decay constant after written release. Soft pedal is read
at onset and changes hammer excitation/aftersound. F6 (MIDI89) and above have no
key-release dampers. Controls update in32-frame blocks, so key-off can happen up to
31 frames early. Voices stop when below the model's mode-culling floor or their
explicit tail window; tail_s defaults8 s, with a final tail_fade_s=0.25 s taper.
A pedal held past the delivery rings to the delivery boundary. There is no hidden
bar grid, tempo, normalization, shared sympathetic bank or prepared-piano support.

## Bowed string

`bowed_string(freq_hz, sample_rate, *, frames, hold_s, seed, velocity=0.8,
parameters=None, body_size=None, controls=(), pitch_curve=(), vibrato_hz=0,
vibrato_cents=0, events=())` returns mono `(frames,)`. Rate is an integer >=8000;
20 <= freq_hz < 0.4 * sample_rate, velocity0..1, hold_s>=0. Frames includes the
release/body tail you want, or truncates a longer hold. Seed is uint32 (0..2**32-1).

| Parameter | Default | Range / meaning |
|---|---:|---|
| decay | 0.6 | >0..12 s, free-string T60 at C4 |
| track | 0.5 | 0..1, decay scaling with frequency |
| damp | 0.5 | 0..1, loop high-frequency loss |
| pos | 0.12 | 0.01..0.5, requested bow position; calibrated to a playable position |
| pressure | 0.5 | 0..1, force within calibrated friction window |
| speed | 0.6 | 0..1, bow speed |
| attack | 0.08 | >0..12 s, initial speed ramp |
| release | 0.15 | >0..12 s, bow lift |
| tremhz | 0 | 0..40, bow reversals per second with seeded small rate variation |
| sord | 0 | 0..1, mute |

body_size=None returns the string alone. A size>=0.05 applies scaled violin-body
modes: 1 is violin-sized and2.4 cello-sized. This is a resonance model, not a sample
library. Combine body size with frequency, decay and bow position for your voicing.

Controls are rows `(time_s, pressure, speed, sord, dyn)`, all values0..1; dyn multiplies
velocity. Pitch curves are `(time_s, cents)` within +/-100 cents. Times must increase
strictly, are nonnegative, interpolate linearly and hold endpoints. Controls and
pitch update every32 frames. Vibrato is a sine, vibrato_hz0..20 and depth0..100 cents.

Events are chronological dictionaries:

- `{"kind":"release", "time_s":...}` lifts the bow early; it cannot extend hold.
- `{"kind":"slur", "time_s":..., "freq_hz":..., "hold_s":..., "pitch_curve":...}`
  continues the bow and moves pitch over7 ms. The optional pitch curve's time zero
  is the event; vibrato and bow controls keep the original voice clock. Slurs within
  two octaves of the first pitch and the same internal rate are accepted. Crossing
  that range or the 2x-rate boundary raises ValueError; author a separate call to
  retrigger the bow. Events are rounded to nearest frames, half up.

First use compiles the waveguide class; warm synthesis timing excludes that per-process
cost. The implementation retains source pitch locking, Thiran delay tuning, friction
calibration and high-register2x decimation. Quiet detection uses128-frame calls split
at events. Each public call resets state; events continue a voice within that call.
No ensemble, sympathetic strings or automatic articulation/slur inference is added.

## Source and verification

The original revision is [DAWG13263790](https://github.com/hraness/dawg/tree/13263790ade044979b6268059ec91567d793e04f).
Installed source includes `_instruments/NOTICE.md` and the full MIT notice in
`_instruments/LICENSE.dawg`; preserve those when adapting code. The public functions
import private model implementations on demand. Original oscillator/pluck/grain
functions remain independently usable.

Clean-checkout tests use saved original-engine float64 windows and full-buffer
peak/RMS, with input recipes and regeneration bridges under tests/fixtures/instruments.
They need no Bun or network. This verifies the recorded model configurations;
it does not establish naturalness, every parameter combination or real-time startup.
[Runnable example](../examples/instruments.py).
