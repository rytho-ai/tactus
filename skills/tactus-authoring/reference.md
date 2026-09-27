# Tactus reference

Details behind the [`tactus-authoring` skill](SKILL.md). Read the section you need when you
reach it; the skill's steps and discipline are the rules.

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
- It returns exactly `sample_rate` and `outputs`:
  - `sample_rate` is a positive int shared by all outputs.
  - `outputs` maps names matching `[A-Za-z0-9][A-Za-z0-9._-]*` (the name becomes part of
    the saved WAV's filename) to real NumPy arrays of shape `(frames,)` or `(frames, 1|2)`.
  - Every value must be finite. Tactus never normalizes, mixes, or resamples. Nothing is
    refused for exceeding [-1, 1]: the saved WAV is clipped to full scale, and the run
    reports it (see Run results).
- Outputs may differ in length. A mix, stems, and clips can live side by side.
- Relative imports and relative files resolve from the entry file's directory. Author logs go
  to stderr; stdout carries one JSON result.

## Creating a work

`tactus init DIR` scaffolds `DIR` as its own uv project depending on a pinned Tactus (a
`pyproject.toml` with `[tool.uv.sources]` and its own `uv.lock`, inside a new Git repository
unless `DIR` is already in one); run it with whatever Tactus you already have, e.g.
`uv run --project TACTUS_CHECKOUT tactus init DIR`. `uv add PACKAGE` adds a package to the work
only; the work's Python is pinned to what `init` copied from the running Tactus, not chosen by
the work.

## Listening to part of a run

`tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` (seconds; `END` may be
empty for the output's end), or `excerpt(run_dir, out=…, range=[start, end])` from Python. It
slices that run's saved audio without rendering again.

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
- Imported Python distributions are recorded automatically; declare only non-Python
  executables and libraries. Installed with Tactus: NumPy, SciPy, SoundFile, pyloudnorm,
  librosa, Pedalboard (effects and VST3 hosting), pytimestretch (time stretch and pitch) and
  `mido` (MIDI files, for example for `sfizz_render --midi`). Their own documentation is the
  reference for using them.

## Reusing unchanged stages

Mark a main stage — a module-level function `render` calls — with `@stage` from `tactus`.
Run candidates with `tactus run song.py --out DIR --reuse` (or `run(..., reuse=True)`): a
stage call whose source, dependencies and arguments all match a prior call returns that
call's exact result, including a performance that would otherwise change between runs
(OB-Xf) — that is the point, so a part already approved does not re-roll while you audition
a different parameter. Without `--reuse`, `@stage` is a plain call.

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
- `fx.process_automated(chain, audio, rate, update, block_seconds=0.02, tail_seconds=…)`
  processes in blocks, calling `update(t)` with each block's start time so you can set
  parameters over time; it handles reset, tail silence and reported latency.
- `fx.varispeed(audio, rate, speed)` plays audio at a per-output-frame speed (pitch follows
  speed; `0.0` holds, negative is not supported).
- `fx.fit_rms(audio, rate, target_dbfs, ceiling_dbfs=-1.0)` returns audio at a target
  whole-signal RMS with no sample above the ceiling, measured on what it returns; it limits
  with a smooth gain envelope instead of clipping, and raises if the target is unreachable.

## Measuring audio

Start at `tactus analyze --help` to list categories (`level`, `spectral`), then
`tactus analyze CATEGORY --help` to list that category's analyses, then
`tactus analyze CATEGORY NAME --help` for its parameters, result fields, units and
definitions — read definitions there, not here. Run with
`tactus analyze CATEGORY NAME PATH... [--flags] [--out DIR]`; `PATH` is a WAV file or a
run/excerpt directory (every named output measured). The library mirrors the CLI:
`from tactus.analysis import spectral; spectral.centroid(audio, rate, threshold_hz=2000.0)`.
Every analysis reports values, never a verdict — apply your own thresholds.

Values are measured on whatever array you pass, or on the saved WAV for a resolved run/excerpt
output — not on some other stage of your signal chain.

## Musical time (optional)

`from tactus.timing import Clock, swing, Groove` resolves musical position to seconds and
frames under a tempo map; `frame_of(seconds, sample_rate)` is the one rounding rule
(`floor(seconds * sample_rate + 0.5)`) for free-time work that needs no clock at all. It is
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

- **Array layout.** Pedalboard effects and `fx.render_instrument` use Tactus's
  `(frames, channels)`; only a direct instrument call (`plugin(messages, ...)`) returns
  `(channels, frames)`.
- **Renders that change between runs.** Some VST3 instruments (OB-Xf, for one) render slightly
  different audio on every run; a re-render's hashes then do not match, even with unchanged
  source. `pytimestretch.extreme_stretch` is different: each run repeats the same result
  while the `extreme_stretch` calls before it stay the same, and changes when one is added,
  removed or moved. Keep an approved part with `@stage` and `--reuse`, or pin it as a
  material; archive approved audio.
- **Clipping the report cannot see.** `clipped_samples` counts only what the work returns
  outside ±1. Audio already clipped inside the work, by `np.clip` or by Pedalboard's `Limiter`
  (a loudness maximizer that hard-clips at 0 dBFS), reports 0.

## Run results

Success prints `{"status": "ok", "outputs": {name: wav_path}, "manifest": path, "receipt":
path, "levels": {name: {peak_dbfs, clipped_samples}}}`.

`manifest.json` (`format_version` 2) identifies the saved audio: `kind`, `sample_rate`, and
`outputs` as `{name: {sha256, frames, channels, file, peak_dbfs, clipped_samples}}`. Each
`file` is `<name>-<sha256[:8]>.wav`, written directly under `--out`; the full `sha256` in the
manifest is what verifies it. `peak_dbfs` is the peak of the audio the work returned, before
clipping (0.01 dB; above 0 when it overflowed; `null` for digital silence), and
`clipped_samples` counts the sample values (all channels) outside ±1 that were clipped before
the write. `levels` in the run result repeats both numbers per output.

An excerpt directory has no receipt; its `manifest.json` (`format_version` 2) has `kind`
`tactus.excerpt` and carries:
- `range`: `start_seconds`, `end_seconds`, `start_frame`, `end_frame` and `omitted`: the
  requested seconds and their rounded frames (`end_seconds` and `end_frame` are `null` for an
  open end), and the requested outputs that had no frames in range.
- `source`: `run` (the source run directory) and `manifest_sha256` (the hash of that run's
  manifest).
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
- `environment`: the interpreter that ran this, since a work usually runs with
  `uv run --project <tactus>` from outside that checkout, so `dependency_lock` above is
  usually null. `prefix` is the interpreter's `sys.prefix`; `lock` is `{path, sha256}` of the
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
differently each run (see below) will not match by hash even after an exact rebuild.

**An older work without its own `pyproject.toml`** instead ran borrowing Tactus's own
environment: check out `git.commit` and apply `source.patch` if present; for each
`package_sources` entry with a `commit`, check out that revision of the named distribution
(`environment.lock` names the `uv.lock` — for Tactus itself — to `uv sync --frozen` against;
its hash must match); then restore materials and run as above.

Errors print `{"status": "error", "error": {code, phase, message}}`. `phase` is one of
`request`, `load`, `bind`, `execute`, `validate`, or `publish`. The exit code is 2 for
request, load, and bind errors, 1 otherwise, and 130 when cancelled. A failed run leaves no
output directory.
