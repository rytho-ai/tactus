# Creative connections

Start with the sound or transformation you want. These are possible connections,
not a checklist to put into every work. Select, combine, simplify, or replace them.

## Find a useful starting point

| Intent | Starting points | What can connect |
|---|---|---|
| Change timing or make a texture from a phrase | `pytimestretch.time_stretch`, `time_warp`; NumPy slicing | Frozen event positions → source/output frame pairs; envelope → playback or effect controls |
| Turn measured movement into musical movement | `tactus analyze --help`, Python analysis, custom analysis | Level, spectral or rhythm observations → authored choice of range, interpolation and destination |
| Build an effect with a particular character | [builtin DSP](dsp.md) and its installed source, Pedalboard, SciPy | Audio → local function → more audio; exposed control curve → another voice or processor |
| Work in frequency bands | `dsp.crossover`, filters, SciPy STFT | Different treatment per band; LR4 branches sum with changed phase |
| Make repetition move | `dsp.delay`, `dsp.crossfade_delay`, authored taps | Moving delay changes pitch; head crossfades trade that glide for a transition that can interfere |
| Connect notes, instruments and audio | `mido`, `fx.render_instrument`, custom synthesis | Notes → instrument audio → exactly the same processing paths as recorded audio |
| Revisit an arrangement | NumPy, optional `tactus.timing`, ordinary Python structures | Clips, gestures, sections, voices or procedural rules; choose what makes the intended revision clear |

Read a callable's docstring for the exact API and [runtime reference](runtime.md) for
Tactus runtime contracts. Private kernel source is an implementation reference, not a
stable import surface. If you adapt an algorithm, own the adapted function and its tests.

## Analysis can become a control signal

An observation does not prescribe a musical decision. Choose what a value means in this
work: louder source regions might expand time, shorten echoes, or open a second layer.
Freeze adopted decisions outside `render`, together with source identity and units.
An envelope follower that is part of the sound itself can run inside `render`.

When time changes, distinguish **source time** from **output time**. `time_warp` uses
strictly increasing integer `(source_frame, output_frame)` pairs including both endpoints.
To carry source-time controls through that warp, map each output frame back to source
time, then sample the source control there. To synchronize an independent groove to the
output, generate that control in output time instead. Both are valid artistic choices.

Check each analysis's coordinates: RMS uses window-end timestamps; spectral features may
use frame centers; onsets are estimates. Explicitly choose interpolation, edge behavior,
and a meaning for missing/silent values. Features are not already sample-rate automation.

## Adaptable examples

- [`taps.py`](../examples/taps.py): a local finite-repeat effect, inspired by the wet-only
  boundary of builtin delay. Each repeat gets a different filter and stereo position.
  Change spacing, reverse a tap, or replace the per-repeat transformation.
- [`prepare.py`](../examples/prepare.py) and [`warp.py`](../examples/warp.py): measure a
  source once, freeze a level-to-time decision, warp audio, and map the source envelope
  to output-time filter movement. Change the observation or its musical interpretation.
- [`mixed.py`](../examples/mixed.py): one small render combines Tactus band splitting,
  Pedalboard chorus and local mid/side motion. Change the branch or processing order.

These demonstrations use synthetic sources to make reruns independent of downloads.
They illustrate connections, not required effects or a preferred sound.

## Make an experiment inspectable

Return an untreated and treated version when that helps hear the change. State intended
duration, dry/wet behavior, tail, channels and state lifetime. Check finite values and
unexpected clipping, then listen; numerical success is not musical acceptance.
For custom recurrences, test an impulse or boundary transition. Measure before accelerating:
NumPy/SciPy suit array operations; Numba suits sequential sample loops. Include first-call
compilation when it affects iteration time. Local DSP can remain work-local indefinitely.
