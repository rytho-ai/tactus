# Tactus reference

Shared execution contracts for the [compose](../compose/SKILL.md),
[dsp](../dsp/SKILL.md), [measure](../measure/SKILL.md),
[interactive](../interactive/SKILL.md) and [visual](../visual/SKILL.md) skills.
Read the relevant section on demand; installed help describes the work's pinned version.
Use [version](../version/SKILL.md) when establishing Git history,
adopting a candidate or recovering a work revision.

## Contents

- [Render contract](#the-render-contract) and [creating a work](#creating-a-work)
- [Excerpts](#listening-to-part-of-a-run), [keeping candidates](#keeping-a-candidate) and [saved takes](#saved-takes)
- [Inputs](#inputs) and [stage reuse](#reusing-unchanged-stages)
- [Reuse saved render outputs](#reuse-saved-render-outputs)
- [Plugin helpers](#helpers-from-tactus-import-fx) and [musical time](#musical-time-optional)
- [Measurements](#measuring-audio) and [project commands/export](#project-commands-and-export)
- [Library behavior](#library-behavior-that-affects-tactus-results) and [run results](#run-results)
- Rendering on request while a piece plays: [`tactus serve`](serve.md)

## The `render` contract

```python
import soundfile as sf
from tactus import material

KICK = "sha256:…"  # printed by `tactus material add kick.wav`


def render(*, bass_gain_db: float = -5.0) -> dict:
    kick, rate = sf.read(material(KICK), dtype="float32", always_2d=True)
    bass = bass_line(rate, gain_db=bass_gain_db)
    mix = master(sum_stems(drum_bus(kick), bass))
    return {"sample_rate": rate, "outputs": {"mix": mix, "bass": bass}}
```

- `render` is a synchronous function, and every parameter is keyword-only. Defaults are JSON
  values: numbers, strings, booleans, null, lists, or objects.
- It returns `sample_rate` and `outputs`, with an optional `takes` mapping (see Saved takes):
  - `sample_rate` is a positive int shared by all outputs.
  - `outputs` maps names matching `[A-Za-z0-9][A-Za-z0-9._-]*` (the name becomes part of
    the saved WAV's filename) to real NumPy arrays of shape `(frames,)` or `(frames, 1|2)`.
  - Every value must be finite. Tactus never normalizes, mixes, or resamples. Nothing is
    refused for exceeding [-1, 1]: the saved WAV is clipped to full scale, and the run
    reports it (see Run results).
- Outputs may differ in length. A mix, stems, and clips can live side by side.
  For stem processing and summation boundaries, read [audio delivery](production.md#explain-the-stem-and-master-boundaries).
- Relative imports and relative files resolve from the entry file's directory. Author logs go
  to stderr; stdout carries one JSON result.
- A performance (a tape, a route, a list of moves) can be a JSON file instead of inline JSON:
  `tactus run song.py --out runs/t1 --param-file tape=tapes/demo.json` (repeatable;
  `run(..., param_files={"tape": path})` in Python) binds the file's JSON to `tape`. A name
  given both in `--params` and as a file is `invalid_request`. The run keeps the exact bytes as
  `parameters/tape.json`, so `--param-file tape=RUN/parameters/tape.json` renders it again.
  Tactus defines no performance format. To reject a value before the expensive part, raise
  `tactus.InvalidParameters("why")` in `render`: the run fails with `invalid_parameters`
  (phase `bind`, exit 2) instead of `execution_failed`.

### The time map (optional)

`render` may also return `"map"`: the piece's time structure, derived by the same code that
made the audio, for players, checks, picture work and delivery. Positions are integer frames
of a named output; Tactus validates the structure and references and saves it as `map.json`
(see Run results). It gives no lane name a meaning and does not judge whether a join sounds
right. A work without bars returns lanes only, or no map.

```python
from tactus.timing import Clock

clock = Clock(sample_rate=48000, tempo=110)        # 3/4: Clock(..., meter=3)
return {"sample_rate": 48000, "outputs": {"loop": loop, "mix": mix}, "map": {
    "outputs": {
        "mix": {"grid": clock.grid(1, 8),             # bars, end, beats_per_bar, first_bar
                "lanes": {"sections": {"kind": "spans", "items": [
                              {"start": 0, "end": 418909, "label": "intro"}]},
                          "kick": {"kind": "points", "items": [{"at": 0}, {"at": 26182}]}}},
        "loop": {"grid": clock.grid(1, 4)}},
    "segments": {"loop": {"output": "loop", "start": 0, "end": 418909, "tail_end": 460000,
                          "loop": True, "tags": ["a"],
                          "joins": [{"at": "bars", "to": {"tags": ["a"]}, "keep_phase": True}]}},
    "clock_hint": {"tempo": 110}}}
```

- `outputs.NAME.grid`: `bars` are the frames where bars start (non-decreasing), numbered from
  `first_bar` (default 1, as in `Clock`) and lying inside the output (0 to its length): when bar 1
  starts before 0 s (a recording whose first downbeat falls a few ms early, a pickup), start the
  grid at the first bar line at or after 0 and name it, e.g. `Clock.grid(2, last)` gives
  `first_bar` 2; `end` (optional) is the frame after the last bar and
  may exceed the output (a master that stops before its last bar line); `beats_per_bar` is one
  number or one per bar (quarter beats, 7/8 is 3.5); `beats` optionally lists beat frames.
  `Clock.grid(first, last, offset=0)` builds it through `frame_of` (nearest frame); any frame
  list works. If the work sizes its audio another way (e.g. rounding up), check that the
  grid's `end` and the output length agree where a loop must be exact.
- `outputs.NAME.lanes.LANE`: `{"kind": "spans" | "points", "items": [...]}`, sorted by
  position. Items carry `start`/`end` or `at`, plus any JSON fields (`label`, `text`, `status`).
- `segments.NAME`: a region a player can loop, enter or leave: `output`, `start <= end <=
  tail_end` (the tail overlaps what follows), `loop`, `tags`, `label`. `joins` record where one
  may leave: `at` is `"bars"` (every bar line of that output's grid) or frames relative to
  `start`, from 0 to `end - start` inclusive (the body's end is a valid exit). `to` is optional: `null` (the player decides), segment names, or
  `{"tags": [...]}` (Tactus checks each tag exists on some segment; whether a target needs
  any or all of them is the player's rule); `keep_phase` enters the target at the same offset. Rules that depend on
  state (an hour, what was played before) stay in the work. A segment names one output; for
  parallel stems that loop together, put the segment on one of them and name the others in
  the work's own data (or a `label`/`tags` convention), as 《門》 does with `<space>_<stem>`.
- `clock_hint` is any JSON, informational only. Unknown keys are rejected; every error names
  the field, e.g. `map.outputs.mix.grid.bars[3]: frames must not decrease`. The run fails
  with `invalid_output`. `tactus.timemap.validate(map, outputs)` is the same check for a
  work's tests; `timemap.to_seconds(map, rate)` converts every position to seconds, and
  `timemap.from_seconds(map, rate)` is its inverse for timing that arrives in seconds (subtitles,
  editor labels, onsets, cues): the same fields become frames by `frame_of`, other fields are kept,
  and nothing is sorted or clamped, so validation still reports a wrong input by its path.

## Creating a work

`tactus init DIR` scaffolds `DIR` as its own uv project depending on a pinned Tactus (a
`pyproject.toml` with `[tool.uv.sources]` and its own `uv.lock`, inside a Git repository
rooted at `DIR`, even when it is inside another checkout). Git must be installed and on
PATH; initialization failures are reported as `init_failed` with phase `git`.
Initialization creates no commit: write and commit the source before the first render.
Install once with
`uv tool install --python 3.12 --editable TACTUS_CHECKOUT`; use
`tactus init DIR --tactus-path TACTUS_CHECKOUT` during local development, or pin a published
revision with `--tactus URL@REV`. Inside the work, plain `tactus ...` uses its locked environment.
`tactus --project DIR ...` selects it explicitly; file arguments keep their cwd meaning. `uv add PACKAGE` adds a package to the work
only; the work's Python is pinned to what `init` copied from the running Tactus, not chosen by
the work.

When entering an existing work from another directory or running Python scratch scripts,
read [Selecting a work's environment](project-commands.md#selecting-a-works-environment).
It owns explicit commands, uv/cwd behavior and doctor diagnostics.

## Listening to part of a run

`tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` (seconds; `END` may be
empty for the output's end), or `excerpt(run_dir, out=…, range=[start, end])` from Python. It
slices that run's saved audio without rendering again. Start/end positions use
[the musical-time rounding rule](#musical-time-optional); the end frame is exclusive.
Since September 30, 2026, half-sample ties choose the later frame, replacing excerpt's
previous ties-to-even rounding. Existing saved excerpts remain unchanged.

`excerpt` is the public CLI/Python name. It provides a verified contiguous time range from
a saved run. For arbitrary array selection, rearrangement or processing, use ordinary
Python/NumPy in the work; a [custom export](project-commands.md#export-a-completed-render) can expose that code
through the CLI.

For adopted beat boundaries:

```bash
tactus excerpt runs/a --beat-grid beats.json --beats 9:17 --out excerpts/phrase
```

Beat points are **1-based**: `9:17` spans eight intervals, starting at point 9 and stopping
before point 17. Supply both flags instead of `--range`. The grid is a JSON seconds array
(e.g. `[0.1, 0.6, 1.12]`), an object with `beats_s`, or a saved analysis `result.json` with
`result.beats_s`. Times must be finite, nonnegative and strictly increasing, relative to
this source run. A grid measured on a different recording or on an offset excerpt must be
mapped to this run's timeline first. Excerpt does not infer offsets or verify that a grid
belongs to the chosen run.

From Python, use `excerpt(run_dir, out=…, beat_grid=times_s, beats=[9, 17])`; `beat_grid` also
accepts a NumPy array or JSON path. Variable tempo uses the actual point times, with no BPM
interpolation. Both boundary points must exist; there is no extrapolated last beat.
These are beat points, not bar or downbeat labels. Adopt the analysis explicitly before
cutting; excerpt never runs beat detection. The usual per-output end clamping still applies.

## Keeping a candidate

Check the source against the candidate: compare the candidate receipt's `git.commit` and
`source_files` with the current source. When you report a result, compare every output hash in
the two manifests; matching one stem does not show the mix matches.

Archive what the listener approved before committing: `tactus material add` the approved run's
mix (and any stems you delivered). The pool keys files by the same SHA-256 the manifest
records, so the hash stays retrievable with `material("sha256:…")` after run directories are
cleaned up. The commit message names the approved run and its mix hash:

```
Keep c2: bass -9 dB, pad 1800 Hz

Approved from runs/c2-recheck (mix sha256 ff0b54d…)
```

Give runs made inside a `git worktree` an `--out` in the main checkout's `runs/`, because
removing the worktree deletes everything inside it.

## Saved takes

Use a saved take when a performance must survive source edits, cache deletion or moving to
another machine. A take is an immutable folder material with original samples, sample rate,
and generation provenance. Playback uses the saved audio; it never calls the generator.

1. **Generate and audition once.** Return a nonempty `takes` mapping alongside `outputs`,
   using the same arrays that feed this run's mix. Names and audio validation match outputs;
   all takes share `sample_rate`. Keep processing you want to revise after the take boundary.

   ```python
   def render(*, gain=0.25):
       raw = synthesize()  # original instrument; declare tools inside this function's call path
       return {"sample_rate": 44100, "outputs": {"mix": raw * gain}, "takes": {"pad": raw}}
   ```

   `tactus run generate.py --out runs/take-a` publishes audition WAVs plus candidate bundles
   under `takes/NAME/`. `audio.npy` preserves the original numeric dtype, shape and headroom;
   it is neither clipped nor converted to PCM24. Mutating a returned array also changes what
   is captured, so keep the raw array unchanged while processing the mix.
2. **Save the chosen candidate.** `tactus take save runs/take-a pad` verifies the candidate
   against the completed manifest, imports it into the material pool and prints `ref`.
   Saving does not edit source or imply listener approval. Save before deleting the run.
3. **Adopt explicitly in source.** Keep the printed `tree:sha256:…` ref as a constant, load it
   with `from tactus import load_take; raw = load_take(PAD_TAKE, sample_rate=44100)`, then
   apply gain/effects/placement. This returns the exact saved dtype and mono/stereo shape.
   A rate mismatch fails; explicit resampling is a source decision. Generator `tool()` calls
   belong only on the generation path, so playback works without the instrument installed.
   Re-render and compare every delivered output hash with the chosen candidate before
   claiming the adoption preserved it; commit the ref change with Git.
4. **Revise or revert.** To change MIDI/patch settings, edit the generation source and create
   another run. Save its take, compare it, and switch the source ref only when selected.
   Editing generator code does not change a pinned take. Keep the old ref for rollback.
5. **Transfer.** `tactus take export REF --out take-bundle` copies audio and provenance to a
   new folder. On the other machine, `tactus material add take-bundle` returns the same ref.
   Carry the work's source/lock and other materials too. The pool is local storage: back it
   up or export chosen takes before removing it.

A take's `take.json` (`kind`: `tactus.take`, `format_version` 1) records `name`, `sample_rate`,
`shape`, `dtype`, `audio_sha256`, `receipt_sha256`, and `source_sha256`. The bundle includes
`receipt.json`, `source.zip` (inventoried Python under `source/`, nearest `uv.lock`, and local
`pyproject.toml` when present), and `source.patch` when the run recorded one. These describe
how it was generated; generator materials, binaries and the Python environment are not
bundled. The whole folder is content-addressed and checked on loading. Original run/source
paths in the receipt are historical; playback has no dependency on those paths.

`@stage`/`--reuse` remains temporary reuse under unchanged source. Saving a take makes it a
material independent of that cache. Load selected takes outside cached stages when you want
the material checked on every run (a cache hit otherwise replays its earlier input record).

## Inputs

- `material("sha256:<hex>") -> Path` returns a verified path into the machine's pool
  (`$TACTUS_POOL`, default `~/.local/share/tactus/pool`). The pool is shared by every work on
  the machine, so it lives outside the work; `tactus material add` prints the pool it wrote
  to. To keep a work's materials beside it (a hand-off, a sandbox), export `TACTUS_POOL` for
  both `material add` and `run`. Reading it, sample-rate conversion
  and channel layout are the work's job; a relabelled rate is not a conversion. A missing entry
  fails the run with `material_unavailable`. Changing a sample means changing its ref in
  source, which is a reviewable diff.
- **Folder materials.** An instrument that is a folder (an SFZ program with `#include` files
  and sample folders reached by relative path) pins with `tactus material add DIR`, which
  prints a `tree:sha256:<hex>` ref. `material("tree:sha256:…")` returns a verified folder whose
  relative paths work as the original did. Verification hashes every file, so it costs seconds
  for a multi-gigabyte instrument.
- `tool("sfizz_render")` or `tool("/abs/path/lib.so")` returns the resolved file and records its
  path and SHA-256. `tool("/abs/path/Some.vst3")` on a folder (a plugin bundle) hashes the whole
  tree in place and returns that folder as a `Path`; `load_plugin` needs a string:
  `pedalboard.load_plugin(str(tool(...)))`. A missing tool fails the run with `tool_unavailable`.
- `tactus.load_audio(ref_or_path, sample_rate, channels=2, trim_db=None)` reads a material into
  `(frames, channels)` float32: mono duplicates to stereo, stereo mixes to mono by mean, other
  combinations raise; resampling is exact (`resample_poly`); `trim_db` drops leading silence
  before the first sample reaching `peak * 10**(trim_db/20)`. Takes a `"sha256:…"` ref (recorded
  the same as any other material) or a `Path` `material()` already returned.
- Imported Python distributions are recorded automatically; declare external executables
  and native libraries with `tool()`. Read [Packages and integration notes](packages.md)
  when choosing tools or connecting their audio, MIDI, timing and state conventions.

## Reuse saved render outputs

To continue from an accepted render's mix, stems or clips, import the completed run once:

```bash
tactus material add runs/accepted
```

Pin the returned `tree:sha256:…` ref in the new source and select the outputs you need:

```python
from tactus import load_render

ACCEPTED = "tree:sha256:…"  # replace with the printed ref


def render(*, bass_gain=0.8):
    previous = load_render(ACCEPTED, outputs=["bass", "drums"])
    bass = previous.outputs["bass"] * bass_gain
    drums = previous.outputs["drums"]
    return {"sample_rate": previous.sample_rate, "outputs": {"bass": bass, "drums": drums}}
```

`load_render(ref, *, outputs=None) -> LoadedRender` returns `sample_rate`, an immutable
`outputs` mapping of readonly arrays, and an immutable `origin` mapping with `ref`,
`kind="original-render"` and the `render.json` SHA-256 (`sha256`). Omit `outputs` to load
all outputs, or pass a nonempty list/tuple of unique existing names; requested order is
preserved. Call `.copy()` on an array before editing in place, or `dict(previous.outputs)`
when a mutable mapping is needed. Arrays retain their original dtype, shape and headroom;
they can differ from the clipped/quantized audition WAVs. Loading neither regenerates
instruments nor resamples: use `previous.sample_rate` or explicitly check and convert rates.

The folder must contain an original `render.json`, `receipt.json` and the requested
`render/NAME.npy` files. A full run can be imported directly. To preserve fewer bytes,
copy those metadata files plus **all** `render/` arrays to a separate folder and import
that folder; its ref differs from the full-run ref. No PCM fallback exists for legacy
runs or excerpt folders. Historical generator paths/tools in the receipt are provenance,
not requirements for playback.

Each call verifies the fixed tree index, checkpoint, receipt and selected arrays, including
their hashes, dtype, shape and finite mono/stereo values. Unrequested arrays and published
WAVs are neither read nor verified; their absence/corruption does not prevent reading an
intact subset. Use `material(ref)` for existing whole-folder verification. Missing/corrupt
inputs raise `MaterialError` (`missing`/`corrupt`), invalid refs use `invalid_ref`, and
invalid selections raise `ValueError`. The original tree ref is recorded in run receipts
and stage captures, using the same input recording as other materials.

Keep the pinned ref in Git; the material pool remains local and must be backed up or
transferred separately. Import before removing the run folder. When verification on every
run matters, load outside a cached stage: a stage hit replays its earlier input record.
Inside a stage, return arrays or plain dictionaries rather than the `LoadedRender` object
if the result should be cacheable.

## Reusing unchanged stages

Mark a main stage — a module-level function `render` calls — with `@stage` from `tactus`.
Run candidates with `tactus run song.py --out DIR --reuse` (or `run(..., reuse=True)`): a
stage call whose source, dependencies and arguments all match a prior call returns that
call's exact result, including a performance that would otherwise change between runs
(OB-Xf) — that is the point, so a part already approved does not re-roll while you audition
a different parameter. Without `--reuse`, `@stage` is a plain call.

Cache entries carry a format version and SHA-256 checksums for their metadata and array
files. A missing entry is a normal miss. An existing entry with missing/corrupt files stops
with `cache_corrupt`; older, unversioned entries stop with `cache_incompatible`. Neither
silently regenerates that performance. The error names the affected directory. Restore it
from a known-good backup, or explicitly render to a new output directory without `--reuse`
(the sound may change). To rebuild the cache, move only the named entry aside before
retrying with `--reuse`. Preserve approved performances as saved takes, independently of cache.

A call is not reusable when any argument, or the return value, is something other than a
NumPy array, `None`, a bool/int/float/str/bytes, a `Path`, or a list/tuple/dict of these — a
random `Generator`, a plugin object, a callable. It then runs normally and the receipt's
`stages` entry says why.

A stage is keyed on the source it reaches, not the whole entry directory. Starting from the
stage function, Tactus follows the names its code uses through work functions, classes and
modules (for a module, the attributes the code names), so editing a `.py` file the stage
does not reach (the mixer, a scratch script, or the arrangement in `song.py` for a stage
defined in another file) keeps it reused;
editing a reached file recomputes it. Plain values the code reaches (constants, arrays,
lists/dicts of these) are hashed at call time, so a constant imported from another file
or a module global that `render` sets before the call (`stretch.LEVEL = level`) counts too.
The receipt's `stages` entry lists the keyed files in `source`. When the reach cannot be
attributed — an `import` inside a reached function body, `getattr`/`exec`/`eval`/
`__import__`/`globals`/`vars`/`importlib`, or a reached object that is not a plain value
(a random `Generator`, a plugin instance, an object of your own class) — the stage is keyed
on every `.py` file under the entry directory, as before, and `source_reason` says why: pass
such inputs as arguments, or create them inside the stage, to key it precisely. State
changed through a method call (`stretch.TABLE.append(...)`) before the stage is called is
seen only as the resulting value, and an object's attributes are not followed.

The key also sees arguments, dependencies and the tools a stage resolved: a stage that reads
any other file directly (not through `material()`) or an environment variable keeps its old
result when that input changes, so read inputs through `material()`.

## Helpers (`from tactus import fx`)

- `fx.describe(plugin, contains=None)` and `fx.format_table(rows)`: each parameter's current
  value, units, range and labels. Look before setting parameters: many plugins report no
  units, so read the range for the scale (on 0–100, `1.0` means 1%), and the current values
  show a plugin that starts with no usable sound.
- `fx.set_param(plugin, name, value, unit=None)` snaps a value with a unit (`"ms"`, `"s"`,
  `"Hz"`, `"kHz"`, `"cents"`, `"dB"`, `"%"`, or the labels' own unit) to a valid value,
  range-checks it, and returns the value actually set; record that one.
- `fx.render_instrument(plugin, messages, duration=seconds, sample_rate=rate)` renders a VST3
  instrument from `mido` messages or `(bytes, seconds)` tuples in absolute seconds, after a
  silent warm-up render that removes a start transient; returns `(frames, channels)`. It renders
  in 64-frame blocks (`buffer_size`) because plugins apply pitch bend and CC at block starts.
- `fx.process(chain, audio, rate, tail_seconds=0.0)` runs a Pedalboard plugin or chain once
  over a complete clip in Tactus layout: no transpose, plugin reset first, float32 out.
  `tail_seconds` appends silence so reverb and delay tails are kept; without it the tail is cut.
- `fx.process_automated(chain, audio, rate, update, block_seconds=0.02, tail_seconds=…)`
  processes in blocks, calling `update(t)` with each block's start time so you can set
  parameters over time. It settles external-plugin latency on silence, resets once, streams
  all production blocks continuously and flushes buffered output at the end. Keep lookahead,
  oversampling and other latency-changing settings fixed during the call; a changed report
  raises ValueError. Plugin compatibility still requires testing the actual plugin.
- `fx.varispeed(audio, rate, speed)` plays audio at a per-output-frame speed (pitch follows
  speed; `0.0` holds, negative is not supported).
- `fx.fit_rms(audio, rate, target_dbfs, ceiling_dbfs=-1.0)` returns audio at a target
  whole-signal RMS with no sample above the ceiling, measured on what it returns; it limits
  with a smooth gain envelope instead of clipping, and raises if the target is unreachable.
  For a target integrated loudness use `dsp.fit_loudness` ([Builtin DSP](dsp.md)).

## Measuring audio

Start at `tactus analyze --help` to list categories (`join`, `level`, `rhythm`, `spectral`), then
`tactus analyze CATEGORY --help` to list that category's analyses, then
`tactus analyze CATEGORY NAME --help` for its parameters, result fields, units and
definitions — read definitions there, not here. Run with
`tactus analyze CATEGORY NAME PATH... [--flags] [--out DIR]`; `PATH` is a WAV file or a
run/excerpt directory (every named output measured). Each stdout line is one JSON object
with `path`, `analysis`, `revision`, `params` and a `result` object holding the measurements;
run/excerpt outputs also have `output`. Add `--brief` to print only `path`, `output`,
`analysis` and `result`. For example, read beat times at `.result.beats_s`.
The library returns the measurements directly and mirrors the CLI:
`from tactus.analysis import spectral; spectral.centroid(audio, rate, threshold_hz=2000.0)`.
Every analysis reports values, never a verdict — apply your own thresholds.

For beat times and tempo, use `tactus analyze rhythm beats FILE > beats.json` outside
`render`. Inspect the result, then pin the accepted JSON with `tactus material add beats.json`
or copy the chosen values into source constants. Read `tactus analyze rhythm beats --help` for duration
limits and the distinction between estimated beats and bar/downbeat positions.

Values are measured on whatever array you pass, or on the saved WAV for a resolved run/excerpt
output — not on some other stage of your signal chain.

**Balance by section.** Whole-run numbers hide a part that is too loud in one section and
absent in another. Cut the section from the saved run, then measure every output in it:

```bash
tactus excerpt runs/a --range 11.16:33.49 --out excerpts/hook1
tactus analyze level rms excerpts/hook1 --brief
```

One line per output. Compare the stems against each other and against the same stems in
another section. Use `rms` here, not `loudness`: gated loudness ignores the quiet blocks,
so a part that sounds only for a moment (a ringing tail, two pickup hits) reads as loud as
if it played throughout. This says which part dominates, not whether the balance is right.

### Analysis coordinates and images

Current builtins return `result["schema"]` in Python, or `report["result"]["schema"]`
in CLI JSON, also with `--brief`. Check `schema.version` (1, or 2 when a selector uses
`slice` or `end`, today only `rhythm.beats`); older runtimes
and project-defined analyses may omit it. Missing declarations remain unknown: consult
the selected implementation before making a coordinate-dependent decision.

- Enumerate `schema.fields` for measurements: `series`, `grid`, `events` or `summary`.
  `coordinate_keys`, `parameter_keys` and `auxiliary_keys` identify the other existing
  result fields; window/hop settings are not additional measurement curves.
- Read axis `quantity`, `unit` and `key` (or inline `values`); a `slice` takes part of
  that key, so beat intervals point to `beats_s` instead of repeating it. Grid `dimensions` gives
  matrix order. `spacing` describes coordinate spacing, not a required display scale;
  use the actual coordinates for Mel, Q transforms and BPM axes.
- Time axes declare `origin: "input_start"` and `at: "centre"`, `"start"`, `"end"` or
  `"point"`. `width` and `hop` use seconds after sample rounding. Width lists follow
  time points unless `width_axis: "y"` assigns one width per frequency row. Read
  `padding` and `alignment` when present; padded frames can extend beyond the input.
- Value descriptors supply units, normalization and `special_values`: Python `-inf`
  or NaN can become inline JSON null while NPZ preserves the float. Read the declared
  meaning before treating silence as missing data or converting null to zero.
- For structured results, `layout: "records"` selects keys inside each record;
  `end_key` (or an `end` selector) supplies an interval end; `schema.ends(result, field)`
  resolves ends from either, or from `width` and `at`. `layout: "rows"` selects tuple columns, with
  `factor` converting units and `width` selecting/scaling the span independently.

For example, `level.rms_curve(...)` describes `schema.fields.rms_dbfs.x` with
`at: "end"`: a value at time `t` measures `[t - width, t)`. Read the resolved width;
the requested duration can round to a different number of samples.

In Python, `from tactus.analysis import schema; x = schema.coordinates(result, field)`
resolves declared root/record/column/inline selectors and explicit factors; grids also
accept `axis="y"`. It returns a separate array without inferring origins or converting
units beyond the declared factor. Use `schema.validate(result)` to check structural
consistency. Both operate on in-memory results: materialize NPZ references first.
For declaring custom data with the same helpers, see
[Project analyses](project-commands.md#analyze).

`schema.input` gives sample rate and original frame count, not file identity or project
position. Preserve CLI `path`, `input_sha256`, `analysis` and `params` from the full
report when passing data downstream. For excerpt input, follow the source manifest
chain and add each saved `range.start_frame` to the local frame position; sum recorded
frames rather than re-rounding requested seconds. A bare array establishes no lineage.

For supported matrices, `tactus analyze spectral stft PATH --out NEW_DIR --image`
writes an SVG alongside the numerical result and NPZ arrays. In Python,
`from tactus.analysis import image; svg = image(result)` renders the direct result.
The same entry point supports Mel, chroma, MFCC, CQT, VQT and tempogram. A narrowed
excerpt can reveal features hidden in an overview. Read axis labels and the full
numerical coordinates: image downsampling does not provide sample-accurate positions.

## Project commands and export

Register work-owned Python callables in `pyproject.toml`:
`[tool.tactus.analysis]` maps `"category.name"` to `"module:function"`;
`[tool.tactus.export]` maps `"delivery-name"` to `"module:function"`.
They appear as `tactus analyze category name` and `tactus export delivery-name`.
Read [the project command contract](project-commands.md) before writing one: it
owns signatures, flags, array attachments, provenance and trusted-code limits.

`tactus export wav RUN --subtype DOUBLE --out NEW_DIR` delivers original float64 audio;
`FLOAT` casts to float32, the default `PCM_24` matches run's audition conversion.
`flac` writes PCM24 FLAC; `stems` writes a ZIP of named outputs (default excludes `mix`,
`--names '["bass", "drums"]'` selects explicitly). `wav` and `flac` take the same `--names`
to write only some outputs, for example `--names '["mix"]'`. All export from saved audio without
rerunning instruments. Custom exporters receive verified named arrays, sample rate and an
`out` Path, write files there, and return a JSON dict. `export.json` inventories those files.
A failed export removes only its new directory, so retrying leaves the render intact.
`--replace` rewrites an existing `--out` only when it is an earlier export (it holds a
`tactus.export` `export.json`): the new export is written beside it and swapped in after it
succeeds, so a failure keeps the earlier one. `--brief` prints the status, directory, record,
file count and a short result instead of every file path. `bundle.json` and `curves.json` are
compact JSON (no indentation); `export.json` stays indented.
Three built-ins deliver a run with its map: `web --codec aac|opus|flac|wav [--bitrate 224k]`
(browser audio plus `bundle.json`: lengths in frames and seconds, levels, waveform peaks, the
map in frames and in seconds, the run's hashes), `srt --output mix --lane lyrics` (a spans
lane as subtitles) and `curves --fps 30` (level curves, map events, bars and spans per video
frame). See [Export a completed render](project-commands.md#export-a-completed-render).

## Musical time (optional)

`from tactus.timing import Clock, swing, Groove` resolves musical position to seconds and
frames under a tempo map; `frame_of(seconds, sample_rate)` maps absolute seconds to
frames using `floor(seconds * sample_rate + 0.5)`. Musical placement and excerpt
boundaries share this rule: exact half-sample ties choose the later frame. Analysis
windows and DSP duration parameters keep their own documented discretization. It is
optional: nothing in `render`/`run` requires it, and a work may keep its own time maths.
Beats are 0-based quarter notes from the start of a bar — a musician's "beat 2" is `beat=1.0`.
`timing.quantize(beat, grid=0.25, strength=1.0)` moves a performed beat toward a grid (exact
ties go to the later grid point); `timing.note_seconds(clock, beat, value)` is a note `value`
in beats (e.g. `0.75` dotted eighth) as seconds at the tempo sounding at `beat`;
`timing.add_at(buffer, clip, frame, gain=1.0)` mixes a clip into a buffer in place, cutting a
head before frame 0 or a tail past the end, never wrapping; `timing.markers(frames, length,
value=0.5, channels=1)` makes one impulse per distinct in-range frame;
`timing.euclid(k, n, rotate=0)` and `timing.cycle(figure, count, start=0)` return the hit step
indices of a Euclidean rhythm and of a repeating figure run continuously across bar lines.

```python
clock = Clock(sample_rate=rate, tempo=[(1, 92), (9, 92), (13, 108, "ramp"), (17, 80)],
              meter=[(1, 4), (5, 3.5), (6, 4)])  # bar 5 is 7/8
clock.frame(9, 1.5)            # bar 9, beat 1.5; (9, 92) marks where the ramp starts
clock.frame(13, 0.0)           # the ramp arrives at 108 bpm here
clock.frame(17, 0.0)           # (17, 80) is a step: 80 bpm from bar 17
ritard = Clock(sample_rate=rate, tempo=[(1, 130), (17, 130), (21, 70, "smooth")])
ritard.frame(21, 0.0)                             # eased ritardando lands here
clock.frame(9, swing(1.75, 0.58))                 # swung sixteenth
groove = Groove(offsets_ms=[0.0, 8.0, -4.0, 6.0], grid=0.25)
groove.frame(clock, 9, 1.75)                      # a groove template's offset applied
```

Tempo points are `(bar, bpm)` (a step) or `(bar, bpm, shape)`, a gradual change from the
previous point: `"ramp"` (linear in beats), `"ramp-time"` (linear in time) or `"smooth"` (a
cosine ease). The module docstring (`uv run python -c "import tactus.timing; help(tactus.timing)"`)
has the full API and precision notes. `clock.grid(1, 8)` is the `grid` of a render map for
bars 1–8 (`bars`, `end` = bar 9, `beats_per_bar`); `offset=` shifts it to where the clock's
frame 0 sits in the output.

### Fitting a recording to a constant grid

To cut a recording by bars or stretch it onto another tempo, fit its adopted beat times once,
outside `render`, and freeze the result. `fit_tempo` fits the numbers it is given; it never
listens to audio, and it never picks the felt tempo or the downbeat.

```bash
tactus analyze rhythm beats master.wav > beats.json   # or another tracker, or taps
tactus material add beats.json
```

```python
from tactus.timing import Clock, fit_tempo, fold, frame_of, segment, warp_markers

fits = fit_tempo(report["result"]["beats_s"], bpm_range=(60, 100))  # range is required
for f in fits:  # best first; nothing is chosen for you
    print(f.bpm, f.origin_s, f.inliers, f.coverage, f.drift_ms_per_min, f.free_bpm)
```

Every tempo that is a multiple of `step` (default `1.0`: whole-number BPM) in `bpm_range` is
tried, and candidates are sorted by `inliers`, the fraction of beats within `tolerance_s`
(default 0.03 s) of the grid. A grid at twice a tempo contains every beat of the slower one,
so it never scores fewer inliers: compare `coverage`, the fraction of grid points that have a
beat (about 1.0 at 85 and 0.5 at 170 for a tracker that counted 85). A tracker that itself
counted double gives coverage near 1.0 at both; choose from the music, or narrow
`bpm_range`. `drift_ms_per_min` well away from 0 and `free_bpm` away from `bpm` mean the
recording follows a nearby tempo, not this one: try `step=0.1`. Low `inliers` for every
candidate means the recording has no constant tempo (rubato, ramps); write a tempo map
instead.

`origin_s` is a beat near 0 s, not a downbeat. The work picks which beat is bar 1 (kick and
snare placement, sections, listening), then freezes the choice as source constants with a
comment naming the beats material, the candidate's numbers and the date:

```python
GRID = {"08": (88, 0.003)}  # bpm, bar 1 s; fit_tempo on beats ref …, inliers 0.98, 2026-10-14
bpm, bar1 = GRID["08"]      # bar1 = f.origin_s + k * 60 / f.bpm for the k you chose
source = Clock(sample_rate=rate, tempo=bpm, meter=4, start_seconds=bar1)
```

The origin inherits the tracker's placement bias. qm-dsp beats sat 11–19 ms earlier than a
madmom-derived grid on the same masters, and about 25–30 ms before synthetic click onsets in
the integration test; Tactus reports this and does not correct it. Anchor `bar1` on drum
onsets in the work if the offset matters.

Bar numbers in recipes are `Clock`'s, 1-based. A 0-based bar count (index `n` in a list of
bars) is `Clock` bar `n + 1`. A bar line before 0 s is valid: `source.frame(1)` may be
negative, and bar 0 is a pickup bar.

Inside `render`, `segment(audio, *source.span(9, 17))` returns exactly those frames, zero-filled
where the range runs before 0 or past the end. Two ways to stretch onto a target tempo
(`pytimestretch` calls stay in the work):

```python
target = Clock(sample_rate=rate, tempo=88)
lead = frame_of(60 / bpm, rate)                 # one beat of engine context on each side
seg = segment(audio, source.frame(9) - lead, source.frame(17) + lead)
pairs = warp_markers(source, target, 9, 17, lead_frames=lead, tail_frames=lead)
out = pytimestretch.time_warp(seg, rate, markers=pairs, semitones=0)
body = out[pairs[1][1] : pairs[-2][1]]           # target bars 1..8, exactly

uniform = pytimestretch.time_stretch(segment(audio, *source.span(9, 17)), rate,
                                     duration_ratio=bpm / 88)
```

`warp_markers` pins every source bar line to its target bar line, so lengths are exact by
construction and the lead and tail map by the neighbouring bar's tempo ratio (`frame_of`).
Without lead or tail, the first pair is the first bar line and the last is the end bar. One
`duration_ratio` gives the same mapping inside the bars for a constant source tempo; its
length is `floor(frames * ratio + 0.5)`, so slice and pad it yourself. Whether the two sound
different on real masters is not yet compared.

`fold(onsets_s, period_s=4 * 60 / bpm, origin_s=bar1, steps=16)` counts onsets (or averages
`weights`) per sixteenth of the bar; use it to check a downbeat choice. Scoring the result is
the work's.

To excerpt by bars, write bar-line seconds as a beat grid. Excerpt rejects negative times, so
drop bar lines before 0 s, and then positions shift: if bar 1 starts before 0 s, position 1
of the array is bar 2.

```python
lines = [s for s in (source.seconds(b) for b in range(1, 41)) if s >= 0]
json.dump(lines, open("bars.json", "w"))  # then: tactus excerpt RUN --beat-grid bars.json --beats A:B
```

## Library behavior that affects Tactus results

[Packages and integration notes](packages.md) owns layouts, plugin state/tails, MIDI time,
stretching and reproducibility caveats, including clipping that the run report cannot see.

## Run results

`tactus run --brief` prints `{status, run, manifest, receipt, outputs: count, peak_dbfs (the
loudest output), clipped: [names], render_bytes}` plus `map`, `takes` and `source_changed`
when present, for works with many outputs. Without it, success prints `{"status": "ok", "outputs": {name: wav_path}, "manifest": path, "receipt":
path, "render": render_checkpoint_path, "render_bytes": int, "levels": {name: {peak_dbfs,
clipped_samples}}}`. `render_bytes` is the size of the saved original arrays; read it, because
it is usually the largest part of the run. With `--no-checkpoint`, `render` is `null` and
`render_bytes` is 0. A run whose `render` returned a map adds `"map": path_to_map.json`.
A request served by [`tactus serve`](serve.md) is the same run directory; its receipt adds a
`service` block naming the session, request and load.

`render.json` (`kind` `tactus.render`, `format_version` 1) is written before audition
encoding. It records `sample_rate`, original `outputs` (`file`, `sha256`, `shape`, `dtype`),
`receipt_sha256`, optional `takes` and optional `map` (`{file: "map.json", sha256}`). The CLI result's `render` points to it. Keep it with
`render/` and `receipt.json`; exports verify them. Raw arrays add 4 bytes per float32 sample
value or 8 per float64 value, alongside the PCM24 files. Legacy runs without a checkpoint
export from their saved PCM only, explicitly recorded as `published-pcm`.

That checkpoint is the largest part of a run: sixteen 92-second stereo float64 outputs take
about 1.1 GB per run, so a session that renders dozens of candidates fills tens of gigabytes.
When a run's original precision is no longer needed, `tactus prune RUN_DIR...` removes
`render.json` and `render/` after verifying the published audio, and reports the bytes
freed. A pruned run keeps its WAVs, manifest, receipt and take candidates; `analyze`,
`excerpt`, `take save` and PCM export still work, and the run reads as `published-pcm`.
It can no longer export the original float precision or be imported for `load_render`.
For candidates known in advance to be throwaway (a parameter sweep, a probe that renders
many variants), `tactus run ... --no-checkpoint` never writes the arrays; the run is then in
the same PCM-only state. The default keeps them, because which candidate will be adopted is
only known afterwards and arrays cannot be recovered once skipped.
Remove these files only through `prune`: `render/` gone with `render.json` left behind
reads as a corrupt checkpoint and blocks export. Keep the checkpoint of any run you may
continue from or deliver at full precision.

`manifest.json` (`format_version` 2) identifies the saved audio: `kind`, `sample_rate`, and
`outputs` as `{name: {sha256, frames, channels, file, peak_dbfs, clipped_samples}}`. Each
`file` is `<name>-<sha256[:8]>.wav`, written directly under `--out`; the full `sha256` in the
manifest is what verifies it. `peak_dbfs` is the peak of the audio the work returned, before
clipping (0.01 dB; above 0 when it overflowed; `null` for digital silence), and
`clipped_samples` counts the sample values (all channels) outside ±1 that were clipped before
the write. `levels` in the run result repeats both numbers per output.

Runs returning `takes` use manifest `format_version` 3 and add `takes: {name: tree_ref}`
to both manifest and CLI result. These are candidate identities; `take save` imports them
before `load_take` can use them. Runs without takes retain version 2. Runs returning a map
use `format_version` 4 (takes optional) and add `map: {file: "map.json", sha256}`; `map.json`
is the validated map with defaults filled (`first_bar`, `tail_end`, `loop`, `tags`, `joins`,
`to`, `keep_phase`). Receipt, `render.json` and manifest record the same hash, and every
reader verifies it: export (with or without a checkpoint), `load_render` (`.map`), and
`render_store.read_published`. `prune` keeps `map.json`. Excerpts and analyses read all four
run manifest versions and operate on the audition `outputs`; an excerpt does not carry the map.

An excerpt directory has no receipt; its `manifest.json` (`format_version` 2) has `kind`
`tactus.excerpt` and carries:
- `range`: `start_seconds`, `end_seconds`, `start_frame`, `end_frame` and `omitted`: the
  requested seconds and their rounded frames (`end_seconds` and `end_frame` are `null` for an
  open end), and the requested outputs that had no frames in range.
- `source`: `run` (the source run directory) and `manifest_sha256` (the hash of that run's
  manifest).
- `beat_selection` (beat requests only): 1-based `start_index` and `end_index`,
  `index_base: 1`, the full adopted `beats_s` grid, and `source` (file path/SHA-256 for a
  JSON file, or null for an in-memory array). The resolved seconds/frames remain in `range`.
- A `source_frames` entry on each output: that output's length in the source run.

`receipt.json` (`format_version` 4) attributes the run:

- `entry`, `parameters`: effective values, defaults included.
- `source_files`: the SHA-256 of each `.py` file under the entry directory, including scratch
  scripts that `render` never imports.
- `dependency_lock`: the nearest `uv.lock`, as `{path, sha256}` or null. In a uv workspace
  member without its own lock, this is the workspace root's `uv.lock`.
- `source_changed`: null when no inventoried `.py` file and not the lock changed while the
  run executed. Otherwise the run is still kept, `source_files`/`dependency_lock` keep their
  start-of-run hashes, and this lists `files` (`path`, `start_sha256`, `end_sha256`, null for
  an added or removed file, and `imported`: whether this run imported it), `dependency_lock`
  (`{start, end}` or null), `certain`, `stage_entries_discarded` and a `message`, which is also
  printed to stderr. `certain` is true when only files this run never imported changed (a
  scratch script): the receipt still names the source of the audio. It is false when an
  imported file or the lock changed: a file edited before it was imported ran its new bytes,
  which hashes cannot tell apart, so re-render before relying on the attribution. Stage cache
  entries this run wrote whose key used a changed file are removed. The CLI/Python run result
  repeats the object under `source_changed` only when something changed.
- `git`: null outside a repository, or `{commit, dirty, untracked, patch}`. `patch` names
  `source.patch` in the run directory when tracked files changed or untracked `.py` files
  existed; `commit` plus that patch restores the source that actually ran.
- `elapsed_seconds`: the wall time of the `render` call.
- `materials`: the refs resolved, in order.
- `tools`: `{name, path, sha256, kind}` for each declared tool; `kind` is `"file"` or `"tree"`.
- `python_packages`: each imported distribution name and its version.
- `environment`: the interpreter that ran this. The global launcher selects the work's
  locked environment; older works that borrowed the Tactus checkout may have a null
  `dependency_lock`. `prefix` is the interpreter's `sys.prefix`; `lock` is `{path, sha256}` of the
  `uv.lock` in the project that owns that environment (a `.venv` prefix's parent directory),
  or null.
- `package_sources`: for every `python_packages` distribution not installed from an index
  (the lock already pins those), what its install metadata says it came from: `{url, vcs,
  commit}` for a VCS install; `{url, editable}` plus `git: {commit, dirty}` when it is also a
  local Git checkout, for a directory install (an editable Tactus checkout looks like this);
  `{url, hash}` for an archive.
- `stages`: one entry per `@stage` call, in call order: `name`, `key`, `reused`, `seconds`,
  `reason`, `source` and `source_reason`. `key` is null when the call was not reusable.
  `reason` is null on an ordinary hit or miss, and otherwise says why a call was not reusable
  or its result was not cached. `source` lists the `.py` files (relative to the entry
  directory) the key used; `source_reason` is null when that is the source the stage reaches,
  and otherwise says why every file was used (see Reusing unchanged stages).
- `reuse`: whether this run was started with `--reuse`.
- `map` (only when `render` returned one): `{file: "map.json", sha256}`.
- `parameter_files` (only with `--param-file`): `{name: {path, sha256, bytes, copy}}`, the
  file as given, its hash and size, and `copy` (`parameters/NAME.json`, the same bytes in the
  run). `parameters` still holds the parsed value.
- `runtime`, `reproducibility`, `attribution_scope`.

A receipt guarantees the saved outputs, not that re-running the source reproduces them. Say an
old version can be reproduced only after you re-render it and every output hash matches.

**Rebuilding a receipt's run elsewhere, for a work created with `tactus init`:** check out
`git.commit` and apply `source.patch` if present, `uv sync --frozen` (the work's own
`dependency_lock` pins Tactus and every package), restore each `materials` ref into the pool
(`tactus material add`), and run with the recorded `parameters`. A plugin that renders
differently each run (see Library behavior above) will not match by hash even after an exact rebuild.

**An older work without its own `pyproject.toml`** instead ran borrowing Tactus's own
environment: check out `git.commit` and apply `source.patch` if present; for each
`package_sources` entry with a `commit`, check out that revision of the named distribution
(`environment.lock` names the `uv.lock` — for Tactus itself — to `uv sync --frozen` against;
its hash must match); then restore materials and run as above.

Errors print `{"status": "error", "error": {code, phase, message}}`. `phase` is one of
`request`, `load`, `bind`, `execute`, `validate`, or `publish`. The exit code is 2 for
request, load, and bind errors, 1 otherwise, and 130 when cancelled. A failure before
`render.json` removes the new run directory. After that checkpoint, the original render and
candidate takes survive while partial audition WAVs are removed. Retry delivery with
`tactus export wav RUN --out NEW_DIR`; `take save` also accepts these completed checkpoints.
