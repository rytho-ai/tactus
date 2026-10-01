# Devices

`tactus.devices` offers familiar ways of making music as plain functions: a **sampler**,
**pads** and a **step sequencer**. They are music devices, not audio hardware, and using
them is a choice. Import one, or copy its file into your work and change it: each module is
self-contained, needs only NumPy and public Tactus modules, and works on ordinary arrays,
tuples and dicts. A device has no sound of its own; the material and settings you pass make
the sound, and the **patch** you build from them is yours.

```python
from tactus.devices import pads, sampler, steps

notes = steps.notes("x..x ..x. x... x.x.", [57, 60, 64, 62], bpm=96, gate=2.5)
melody = sampler.play(note_audio, sr, notes, frames=n, root=57, loop=(0.30, 0.50))

kit = dict(zip("abcdefgh", pads.slices(break_audio, sr, count=8)))
hits = steps.hits("x.x. x..x", "a", bpm=96) + steps.hits("..x. ..x.", "c", bpm=96)
drums = pads.play(hits, kit, sr, frames=n, choke={"a": 1, "c": 1})
```

To copy one: `python -c "import tactus.devices.sampler as m; print(m.__file__)"`, then copy
that file beside your work and import it under your own name.

## Where a device ends

- A **device** works with note events: it plays them (sampler, pads) or makes them (steps).
- [`tactus.dsp`](dsp.md) processes audio and knows nothing about notes.
- [`tactus.synth`](synth.md) generates sound from parameters and knows nothing about notes.
- Sounds you design from synth blocks are placed by your own code, for example with
  `timing.add_at`.

## Events

Times are absolute seconds from the start of the output.

- Note: `(start_s, pitch, duration_s, velocity)`. Pitch is a MIDI number (60 = middle C,
  fractions allowed); velocity is 0..1 and scales amplitude linearly.
- Pad hit: `(start_s, pad, velocity)`.

## sampler: a recording as a pitched instrument

- `note(sample, sample_rate, pitch, duration_s, velocity=1.0, *, root=60.0, start_s=0.0,
  loop=None, xfade_s=0.02, attack_s=0.005, release_s=0.08)` returns one note lasting
  `duration_s + release_s`. The sample is mono or `(frames, channels)`.
- `play(sample, sample_rate, notes, *, frames, **settings)` renders a whole part.
- **root** is the pitch the recording really sounds at. Measure it: a file labelled with a
  note name can sit tens of cents off, and a wrong root detunes every note. Autocorrelation
  or an FFT peak over a steady stretch of the sample gives the frequency;
  `69 + 12 * log2(hz / 440)` converts it to a MIDI number.
- **start_s** skips into the source, for example past a noisy or off-pitch onset.
- **loop** `(start_s, end_s)` in source seconds sustains a note longer than the recording.
  Pick a steady stretch, begin it at least `xfade_s` into the source, and make its length a
  whole number of periods of the tone; every wrap is crossfaded.
- Repitching resamples with linear interpolation: higher notes are shorter and brighter, and
  large upward shifts alias. For pitch without length change use `pytimestretch` in the work.

## pads: slices and one-shots on named pads

- `slices(sample, sample_rate, *, count=None, at_s=None, tail_s=0.0)` returns a list of
  pieces: `count` equal slices, or cuts at the given source times (for example adopted
  onsets or beats). `tail_s` lets each slice run that far into the next one.
- `play(hits, pads, sample_rate, *, frames, choke=None, tune=None, fade_s=0.005,
  per_pad=False)` triggers `pads[name]` at each hit. Sounds overlap and ring out. Pads may
  be mono or `(frames, channels)`; with any stereo pad the output is stereo and mono pads go
  to every channel.
- **choke** maps pad names to a group; a hit stops any earlier ringing hit of its group,
  itself included, with a short fade (closed hat over open hat, or a chopped loop where each
  slice cuts the previous one).
- **tune** maps pad names to semitones. `per_pad=True` returns one stem per pad.
- `choke` and `tune` also take one value for the whole kit: `choke=1, tune=-4`.
- **Chopping a record to a new tempo.** Repitching by `12 * log2(bpm / source_bpm)` semitones
  makes a source beat last one beat of the work, and moves the key by the same amount.
  Old recordings drift, so cut one slice per beat with a small `tail_s`, put the whole kit
  in one choke group and trigger a slice on every beat: each rings until the next cuts it,
  and uneven source beats leave no gaps.
- **Keeping the pitch instead.** Stretch each slice to the work's beat before it goes on a
  pad; pads then need no `tune` and no tail:
  `pytimestretch.time_stretch(part, sr, duration_ratio=beat_frames / len(part), backend="rubberband")`.
  Very short slices stretch poorly; cut by beats or bars rather than by single onsets.

## steps: a step grid as events

- `events(pattern, *, bpm, steps_per_beat=4, start_s=0.0, repeats=1, swing=0.5, level=0.7,
  accent=1.0)` returns `(start_s, velocity)` for each active step.
- A pattern is a string (`x` hit at `level`, `X` accent, `.` rest; spaces and `|` only for
  reading) or a sequence of velocities where 0 rests.
- **swing** places every second step inside its pair as `timing.swing` does: 0.5 straight,
  0.58 light, 2/3 triplet.
- `hits(pattern, pad, *, bpm, ...)` and `notes(pattern, pitches, *, bpm, gate=0.5, ...)`
  take the same timing arguments as `events` and attach a pad name or pitches (one, or a
  sequence cycled over the active steps).
- `from_indices(indices, length, *, velocity=0.7)` turns `timing.euclid` or `timing.cycle`
  output into a pattern.

The [devices example](../examples/README.md#devices-example) uses all three;
[Ways of making music](techniques.md) describes when each helps.
