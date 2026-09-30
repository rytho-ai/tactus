---
name: measure
description: Use or write objective audio analyses for Tactus. Use for loudness, peaks, spectra, rhythm estimates, custom descriptors, analysis-function validation, registering work-local tactus analyze commands, comparing renders or turning observations into creative control data.
---

# Measure audio and write analyses

Start with the question the observation should answer. Choose a builtin, a library or a
work-local analysis function. Measurements describe signals under stated definitions;
the author decides how they matter musically. An analysis can also be raw material for
composition or a processor, rather than only a final audit.
For installed/optional analysis packages and integration caveats, read
[Packages and integration notes](../references/packages.md).

## Use an existing analysis

Discover the installed runtime progressively: `tactus analyze --help`, then
`tactus analyze CATEGORY --help`, then `tactus analyze CATEGORY NAME --help` for parameters,
units, definitions and limitations. Call the Python function directly when composing
calculations; use the CLI for saved files or run/excerpt directories. See
[Measuring audio](../references/runtime.md#measuring-audio) for result envelopes and paths.

Choose the exact signal and interval: source, intermediate array, saved raw render or
published audition WAV. A run-directory analysis measures its WAVs. Keep rate, channels,
units, window/hop, timestamp convention and aggregation explicit. Beats and onsets are
estimates, not guaranteed boundaries; a spectral peak need not be a fundamental. Compare
like regions and report how playback level matching or alignment affects the comparison.
Choose the calculation dtype explicitly for precision-sensitive reductions; the
[project command contract](../references/project-commands.md#analyze) describes input decoding.

## Write an analysis when the question needs one

1. **Define the observation.** Specify its formula or algorithm, units, channel reduction,
   window alignment, edge/padding behavior and treatment of silence or undefined values.
   For an estimator, state what its output estimates and how confidence or failure appears.
2. **Implement a normal Python function:** `analyze(audio, sample_rate, *, ...) -> dict`.
   Keyword parameters should have useful type annotations and JSON-valued defaults for CLI
   use. Return measurements with clear field names; return time axes with curves. Preserve
   inputs. Use NumPy/SciPy, builtin analyses or another dependency as useful ingredients.
3. **Validate the claim.** Check signals with known answers and relevant invariants (for
   example, gain invariance of a normalized spectral descriptor). Include silence, short
   input and channels. Estimators need representative real material; distinguish agreement
   with another implementation from correctness. Use [dsp](../dsp/SKILL.md)'s acceleration
   guidance if profiling shows a costly loop, keeping a checked reference.
4. **Expose only what the work needs.** Direct Python use is sufficient. For a reusable CLI
   command, read the [project command contract](../references/project-commands.md#analyze)
   and register `"category.name" = "module:function"` in `[tool.tactus.analysis]` in the work's
   `pyproject.toml`. It then appears under `tactus analyze`; no core edit is necessary.
   That reference owns flags, revision/provenance and array attachments.

When explicitly contributing a new Tactus builtin, work in the Tactus repository's
`src/tactus/analysis/`, add the function to its category's `ANALYSES` and maintain its
definition, revision and independent tests. Follow that repo's development instructions.
A work-specific descriptor can remain local indefinitely.

## Turn observations into creative choices

Use [compose](../compose/SKILL.md) to decide what the observation means in the work and
[dsp](../dsp/SKILL.md) to realize it as processing. Preserve the distinction between the
measurement and the authored mapping: the same energy curve could open a filter, shorten
a delay or expand a phrase.

Freeze accepted decisions as constants or pinned data, recording source identity, analysis
parameters/revision, units and the chosen mapping. Reanalysis is then a visible revision.
For listening between adopted beat points, pass the saved beat result to
[`excerpt`](../references/runtime.md#listening-to-part-of-a-run). Confirm its timestamps
use the selected run's origin; map offsets explicitly when analyzing a different region.
An envelope follower that continuously shapes sound may instead run inside `render`.
For analysis → time-stretch → effect, read
[Creative connections](../references/connections.md): carry source-time observations
through the warp, or deliberately generate controls in output time. Treat timestamps,
interpolation and missing values as choices to make explicit.
