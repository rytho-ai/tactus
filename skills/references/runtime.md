# Tactus reference

Shared execution contracts for the [compose](../compose/SKILL.md),
[dsp](../dsp/SKILL.md) and [measure](../measure/SKILL.md) skills.
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
  (`$TACTUS_POOL`, default `~/.local/share/tactus/pool`). Reading it, sample-rate conversion
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
`stages` entry says why. Editing any `.py` file under the entry directory recomputes every
stage on the next run; only unchanged source lets a changed parameter reuse the stages it
did not touch. The key sees only `.py` source, arguments, dependencies and the tools a stage
resolved: a stage that reads any other file directly (not through `material()`) or an
environment variable keeps its old result when that input changes, so read inputs through
`material()`.

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

Start at `tactus analyze --help` to list categories (`level`, `spectral`, `rhythm`), then
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
cosine ease). The module docstring (`python -c "import tactus.timing; help(tactus.timing)"`)
has the full API and precision notes.

## Library behavior that affects Tactus results

[Packages and integration notes](packages.md) owns layouts, plugin state/tails, MIDI time,
stretching and reproducibility caveats, including clipping that the run report cannot see.

## Run results

Success prints `{"status": "ok", "outputs": {name: wav_path}, "manifest": path, "receipt":
path, "render": render_checkpoint_path, "levels": {name: {peak_dbfs, clipped_samples}}}`.

`render.json` (`kind` `tactus.render`, `format_version` 1) is written before audition
encoding. It records `sample_rate`, original `outputs` (`file`, `sha256`, `shape`, `dtype`),
`receipt_sha256` and optional `takes`. The CLI result's `render` points to it. Keep it with
`render/` and `receipt.json`; exports verify them. Raw arrays add 4 bytes per float32 sample
value or 8 per float64 value, alongside the PCM24 files. Legacy runs without a checkpoint
export from their saved PCM only, explicitly recorded as `published-pcm`.

`manifest.json` (`format_version` 2) identifies the saved audio: `kind`, `sample_rate`, and
`outputs` as `{name: {sha256, frames, channels, file, peak_dbfs, clipped_samples}}`. Each
`file` is `<name>-<sha256[:8]>.wav`, written directly under `--out`; the full `sha256` in the
manifest is what verifies it. `peak_dbfs` is the peak of the audio the work returned, before
clipping (0.01 dB; above 0 when it overflowed; `null` for digital silence), and
`clipped_samples` counts the sample values (all channels) outside ±1 that were clipped before
the write. `levels` in the run result repeats both numbers per output.

Runs returning `takes` use manifest `format_version` 3 and add `takes: {name: tree_ref}`
to both manifest and CLI result. These are candidate identities; `take save` imports them
before `load_take` can use them. Runs without takes retain version 2. Excerpts and analyses
read all three run manifest versions and operate on the audition `outputs`.

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
- `dependency_lock`: the nearest `uv.lock`, as `{path, sha256}` or null.
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
- `stages`: one entry per `@stage` call, in call order: `name`, `key`, `reused`, `seconds` and
  `reason`. `key` is null when the call was not reusable. `reason` is null on an ordinary hit
  or miss, and otherwise says why a call was not reusable or its result was not cached.
- `reuse`: whether this run was started with `--reuse`.
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
