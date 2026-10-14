# Adaptable creative connections

These small synthetic examples demonstrate combinations, not a genre or required pipeline.
Read `render` first, then follow the function relevant to the idea you want to change.

Copy this directory to a writable location, then make it part of an existing Tactus work or
create a new one. For example, from the Tactus checkout (choose a new destination):

```bash
tactus init /tmp/tactus-connections --tactus-path "$PWD"
cp skills/examples/*.py /tmp/tactus-connections/
cd /tmp/tactus-connections
git add .
git commit -m "Start creative connection examples"
tactus run taps.py --out runs/taps
tactus run mixed.py --out runs/mixed
uv run python prepare.py
git add decisions.py
git commit -m "Freeze source analysis and warp decisions"
tactus run warp.py --out runs/warp
```

For an installed plugin, replace the `cp` source with its `examples/` directory and use the
runtime source appropriate to your work. Always copy before running `prepare.py`: it writes
`.artifacts/` and `decisions.py`. Keep `.artifacts/` ignored; keep `decisions.py` in the work's
Git history. It contains refs generated in your pool, so these examples carry no private refs.

- [taps.py](taps.py): a work-local wet-only finite echo. Each repeat has its own filter and
  stereo position. [phrase.py](phrase.py) supplies deterministic source material.
- [mixed.py](mixed.py): Tactus band splitting, Pedalboard chorus and locally written mid/side
  motion. Modify the branches, processing order or output-time gesture.
- [prepare.py](prepare.py) and [warp.py](warp.py): measure source RMS once, freeze a creative
  level-to-time choice and its source identity, time-warp the audio, then map the source
  envelope through the inverse warp to drive a filter. Change the descriptor, mapping or
  effect. Regenerating `decisions.py` is an explicit revision, not part of every render.
- [minimal.py](minimal.py): a small valid entry to copy as `song.py`; keyword controls and
  the exact render-result shape, without extra top-level metadata.
- [boundaries.py](boundaries.py): select full phrases inside an authored loop body while
  excluding an off-grid tail; deliver post-channel stems, their pre-master sum and a final
  gain stage. Read [Source regions and audio delivery](../references/production.md).

## Synthesis examples

Instruments assembled from [synthesis building blocks](../references/synth.md). Every
waveform, ratio, decay and grain choice is the example's own; rewrite them freely.

- [voices.py](voices.py): a detuned PolyBLEP saw lead with pitch scoop, vibrato, an
  enveloped SVF sweep and light saturation, plus an FM bell with a decaying index.
- [physical.py](physical.py): struck metal from noise bursts through a free-bar modal
  bank, and a plucked-string line with filtered-noise excitation.
- [textures.py](textures.py): a granular pad from a synthesized chord using a seeded grain
  list, and a riser from a `dsp.spectral` freeze with upward frequency drift.

Run them like the others, for example `tactus run voices.py --out runs/voices`.

## Devices example

- [devices.py](devices.py): a melody played on one sampled note with a sustain loop, a
  break cut into eight slices and re-triggered in a new order with each slice choking the
  last, and a swung hat line from the step sequencer. Sources are synthesized stand-ins;
  see [Devices](../references/devices.md) and [Ways of making music](../references/techniques.md).

Each render returns comparable named WAVs. Listen with your audio tools. For an objective
check of the heard output, try `tactus analyze level sample_peak runs/warp` or write your own
analysis using the [measure skill](../measure/SKILL.md) and
[project command contract](../references/project-commands.md#analyze).

The example `prepare` process calls `level.rms_curve` directly and records its revision and
parameters; registration is optional. A production can use a local descriptor the same way,
or register it under `[tool.tactus.analysis]` when a shared CLI entry is useful.

Change candidates with keyword parameters, such as
`tactus run warp.py --out runs/warp-b --params '{"brightness": 0.4}'`. The adopted measurements
and markers stay fixed while brightness changes. Outputs need not share a duration: the
source is six seconds and this example deliberately maps it to eight seconds.
