# Piano synthesis

Use `tactus.synth.piano` for an acoustic piano part. It uses Python/NumPy/SciPy/Numba code adapted
from DAWG under MIT, with no samples, weights, VST or JavaScript installation.
It returns fresh float64 arrays, retains headroom and does not normalize or add room
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

## Source and verification

The original revision is [DAWG13263790](https://github.com/hraness/dawg/tree/13263790ade044979b6268059ec91567d793e04f).
Installed source includes `_instruments/NOTICE.md` and the full MIT notice in
`_instruments/LICENSE.dawg`; preserve those when adapting code. The public function
imports the private model implementation on demand. Original oscillator/pluck/grain
functions remain independently usable.

Clean-checkout tests use saved original-engine float64 windows and full-buffer
peak/RMS, with input recipes and regeneration bridges under tests/fixtures/instruments.
They need no Bun or network. This verifies the recorded model configurations;
it does not establish naturalness, every parameter combination or real-time startup.
[Runnable example](../examples/instruments.py).
