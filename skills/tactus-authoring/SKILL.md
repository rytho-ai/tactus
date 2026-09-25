---
name: tactus-authoring
description: Write, revise, or run a Tactus music production — a Python file defining `render(*, ...)` executed by `tactus run`. Use when composing or editing a work's audio code, pinning samples or instruments with `material()`/`tool()`, running parameter candidates, or reading a run's manifest/receipt.
---

# Writing a Tactus work

A Tactus work is ordinary Python and NumPy. You decide the material, notes, processing order,
routing, automation, and mix; this skill covers only how Tactus runs and records the work.
Tactus runs it in a fresh process, checks the audio it returns, writes PCM24 WAVs, and records
what produced them. Any structure you find helpful is allowed; none is required.

## Steps

1. **Pin every input.** Import each sample, soundfont, beat grid, or other file the sound
   depends on with `tactus material add FILE...`. Paste each printed `sha256:…` ref into source
   as a named constant, and resolve it with `material(REF)`. Declare each external executable or
   native library at its point of use with `tool(NAME_OR_PATH)`. Done when no file path or
   environment variable in source decides which bytes the work hears.
2. **Write the work as a pipeline of functions** (see Functional discipline). Done when
   `render` reads top to bottom as the processing order, and every stage is a named function
   whose inputs arrive as arguments and whose result is returned.
3. **Expose the choices you want to audition** as keyword-only parameters of `render`, with
   JSON-valued defaults. Done when each candidate you intend to compare differs only by
   `--params`.
4. **Run it**: `tactus run song.py --out NEW_DIR [--params '{"name": value}']`. Every run needs
   a directory that does not exist yet. Keep run directories out of Git, in one fixed place:
   the main checkout's ignored `runs/` or a folder outside the repository. Git holds the
   source, `uv.lock` and the `sha256:` refs; audio lives in run outputs and the pool. A file
   you hand to a listener stays at the path you gave until they are done with it. Done when
   stdout reports `"status": "ok"`. On failure, fix what `error.code` and `error.phase` point
   at (see Run results).
5. **Listen and compare.** A passing run proves the technical contract only. Discarding a
   candidate needs no action.

   To hear part of the work, cut it from a run you already have:
   `tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` (seconds; `END` may
   be empty for the output's end), or `excerpt(run_dir, out=…, range=[start, end])` from
   Python. It slices that run's saved audio without rendering again, so the excerpt is exactly
   what the listener hears in that candidate. Do not window `render` yourself: reverb and
   compressor tails, a loop's phase, and whole-mix processing depend on material before the
   window, so a self-windowed render differs from the same span of the full song.
6. **Keep one candidate**: edit its parameter values into `render`'s defaults, run again, and
   commit the source with `git` once the result is the version you chose. Discard edits you do
   not keep with `git checkout`.

   Before keeping it, check that the source has not moved since the candidate was rendered:
   compare the candidate receipt's `git.commit` and `source_files` with the current source.
   If it moved, the version the listener chose no longer exists: tell the listener what
   changed, render the same parameters from the current source as a new candidate, and keep it
   only after they approve it. When you report a result, compare every output hash in the two
   manifests; matching one stem does not show the mix matches.

   Archive what the listener approved before committing: `tactus material add` the approved
   run's mix (and any stems you delivered). The pool keys files by the same SHA-256 the
   manifest records, so the hash stays retrievable with `material("sha256:…")` after run
   directories are cleaned up. The commit message names the approved run and its mix hash:

   ```
   Keep c2: bass -9 dB, pad 1800 Hz

   Approved from runs/c2-recheck (mix sha256 ff0b54d…)
   ```

Structural experiments, such as a new stage or reordered processing, cannot be expressed as
parameters. Make them on a Git branch or `git worktree`, run each, and keep one by merging.
Give runs made inside a worktree an `--out` in the main checkout's `runs/`, because removing
the worktree deletes everything inside it.

## Functional discipline

- **Inputs stay unchanged.** A function never writes into an array it received or into
  module-level state; it builds a fresh result it owns.
- **Data flows through arguments and return values.** Module-level values are constants:
  tempo, refs, `SEED`.
- **Stages have names**, so a revision can find and replace one stage.
- **Order is visible.** Processing that depends on order appears in that order in the code.
- **Compute once.** Bind a shared intermediate to a name and pass it to each consumer.
- **Randomness is explicit.** Create `np.random.default_rng(SEED)` inside `render` or a stage,
  and pass generators or derived seeds down.
- **Analysis results are frozen.** Analysis that yields a decision (tempo, onsets, slice points,
  beat grid, key) runs once, outside `render`. Freeze the result as a pinned material file or
  as constants in source, so re-analysing is an explicit revision and a library upgrade cannot
  move a slice point. Signal-following DSP (compressors, envelope followers) stays in `render`.

## Reference

### The `render` contract

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

### Inputs

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
  tree in place and returns that folder, ready for `pedalboard.load_plugin`. A missing tool
  fails the run with `tool_unavailable`.
- Imported Python distributions are recorded automatically; declare only non-Python
  executables and libraries. Installed with Tactus: NumPy, SciPy, SoundFile, pyloudnorm,
  librosa, Pedalboard (effects and VST3 hosting), pytimestretch (time stretch and pitch) and
  `mido` (MIDI files, for example for `sfizz_render --midi`). Their own documentation is the
  reference for using them.

### Helpers (`from tactus import fx`)

- `fx.describe(plugin, contains=None)` and `fx.format_table(rows)`: each parameter's current
  value, units, range and labels. Look before setting parameters: many plugins report no
  units, so read the range for the scale (on 0–100, `1.0` means 1%), and the current values
  show a plugin that starts with no usable sound.
- `fx.set_param(plugin, name, value, unit=None)` snaps a value with a unit (`"ms"`, `"s"`,
  `"Hz"`, `"kHz"`, `"cents"`, `"dB"`, `"%"`, or the labels' own unit) to a valid value,
  range-checks it, and returns the value actually set; record that one.
- `fx.render_instrument(plugin, messages, duration=seconds, sample_rate=rate)` renders a VST3
  instrument from `mido` messages or `(bytes, seconds)` tuples in absolute seconds, after a
  silent warm-up render that removes a start transient; returns `(frames, channels)`.
- `fx.process_automated(chain, audio, rate, update, block_seconds=0.02, tail_seconds=…)`
  processes in blocks, calling `update(t)` with each block's start time so you can set
  parameters over time; it handles reset, tail silence and reported latency.
- `fx.varispeed(audio, rate, speed)` plays audio at a per-output-frame speed (pitch follows
  speed; `0.0` holds, negative is not supported).

### Library behavior that affects Tactus results

- **Array layout.** Pedalboard effects and `fx.render_instrument` use Tactus's
  `(frames, channels)`; only a direct instrument call (`plugin(messages, ...)`) returns
  `(channels, frames)`.
- **Renders that change between runs.** Some VST3 instruments (OB-Xf, for one) render slightly
  different audio on every run, and `pytimestretch.extreme_stretch` is random with a
  per-process seed, so its result changes when calls are added before it or reordered. A
  re-render's hashes then do not match, even with unchanged source: archive approved audio,
  and pin a result you want to keep as a material.
- **Clipping the report cannot see.** `clipped_samples` counts only what the work returns
  outside ±1. Audio already clipped inside the work, by `np.clip` or by Pedalboard's `Limiter`
  (a loudness maximizer that hard-clips at 0 dBFS), reports 0.

### Run results

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

`receipt.json` (`format_version` 2) attributes the run:

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
- `runtime`, `reproducibility`, `attribution_scope`.

A receipt guarantees the saved outputs, not that re-running the source reproduces them. Say an
old version can be reproduced only after you re-render it and every output hash matches.

Errors print `{"status": "error", "error": {code, phase, message}}`. `phase` is one of
`request`, `load`, `bind`, `execute`, `validate`, or `publish`. The exit code is 2 for
request, load, and bind errors, 1 otherwise, and 130 when cancelled. A failed run leaves no
output directory.

### Worked examples

In the Tactus repository (`https://github.com/rytho-ai/tactus`, or the local checkout that
installed the package):

- `examples/real-chop-flip/`: a real sample with a beat grid, a `pytimestretch` warp to an
  exact length, and a bass-level candidate parameter.
- `examples/phonon-ballad/`: a full song with pinned drum samples, a soundfont through a
  declared native library, and palette/drum parameters.
