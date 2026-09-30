# Source regions and audio delivery

Read this when chopping a source loop, using stems as new inputs, or handing off a mix.
These are authoring patterns; Tactus does not infer loop bodies, enforce a track model or
choose the musical boundaries. [boundaries.py](../examples/boundaries.py) is a synthetic
example with an intentionally off-grid file tail.

For original outputs from an accepted Tactus render, use
[saved render loading](runtime.md#reuse-saved-render-outputs) to pin one render identity
and load selected named arrays with their sample rate. This preserves original headroom
and dtype; the published audition WAVs may have been clipped or quantized.

## Choose the musical source region

Pin the source and freeze the boundaries used by the work: sample rate, start/end frames
(exclusive end), any chosen beat grid and the evidence for those choices. Filename BPM
and key are claims; beat analysis is an observation. Listen/check the chosen boundaries
before using them as arrangement decisions. Record uncertainty in the work's notes.

Separate the loop body from intro silence, pickup and effect/release tails. If a two-bar
phrase must fit inside a body, require `start + phrase_frames <= body_end`. Choose from
valid beat-aligned start positions. Wrap the index into those positions rather than
wrapping a sample offset modulo the full file length: a tail of arbitrary length would
shift every subsequent phrase away from the source grid.

Calculate source beat positions from their absolute times with `timing.frame_of` at the
source rate. Repeated multiplication of one rounded beat length can accumulate error.
Choose output placement from its own grid; source and target tempos may differ. For
variable tempo, use chosen markers rather than extrapolating one BPM. Cropping on a grid
does not stretch audio or establish a downbeat. Preserve tails as separate audio when
wanted and author their placement explicitly. Check full context near section boundaries,
including a late passage: a short intro audition can hide cumulative drift.

Declare short-source behavior: reject, pad or repeat deliberately. A NumPy slice silently
shortens when its end exceeds the source. Own a copy before applying fades or in-place
DSP so one phrase does not change subsequent uses of the source.

## Explain the stem and master boundaries

Outputs are named arrays, not required Track or Bus objects. When delivering stems,
describe which processing each includes:

| Boundary | What the array contains |
| --- | --- |
| Source / pre-channel | Recorded or generated audio before channel mixing |
| Post-channel | Channel fader, EQ, dynamics and any explicitly included effect returns |
| Pre-master | The declared sum/bus before final processing |
| Final mix | The master result, including final dynamics, saturation or gain |

Choose descriptive output names such as `bass_post`, `pre_master`, `mix`, or document
equivalent names. State whether wet returns are separate or already included, whether
stems retain pan, and whether they share sample rate, alignment and tail duration.
The source owns these relationships; Tactus does not assume that all outputs sum to mix.

When channel stems are intended to sum to pre_master, verify that relationship on the
original arrays. PCM24 quantization means separately published WAVs can sum with a small
rounding difference. Export original arrays as DOUBLE when exact samples are needed.
Final nonlinear compression/saturation cannot generally be reconstructed by processing
each stem separately: include the pre-master bus and source/settings for master processing.
Do not list pre_master as another channel to add to its constituent stems.

For mixing from saved prints, pin their hashes, read their rates/lengths and confirm the
processing boundary. A raw channel print and a previously mastered mix have different
level relationships. Inspect peaks and loudness, then compare by listening. Keep the
accepted input WAVs intact; processing new outputs constitutes a separate revision.

## A valid entry and processing notes

Copy [minimal.py](../examples/minimal.py) into a work as `song.py`. Its `render` returns
only `sample_rate`, `outputs` and optionally `takes`, as defined in
[the render contract](runtime.md#the-render-contract). Keep commentary/settings in source,
stderr logs or a work note; additional top-level metadata keys are not supported.

For native extension callables, `inspect.signature` can be unavailable. Read their
installed `__doc__`, `help()` and package documentation from the work's uv environment.
Validate a small representative audio call before building the full signal chain.
