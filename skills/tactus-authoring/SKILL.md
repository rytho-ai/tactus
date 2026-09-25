---
name: tactus-authoring
description: Write, revise, or run a Tactus music production — a Python file defining `render(*, ...)` executed by `tactus run`. Use when composing or editing a work's audio code, pinning samples or instruments with `material()`/`tool()`, running parameter candidates, or reading a run's manifest/receipt.
---

# Writing a Tactus work

A Tactus work is ordinary Python and NumPy. You decide the material, notes, processing order,
routing, automation, and mix. Tactus runs the work in a fresh process, checks the audio it
returns, writes PCM24 WAVs, and records what produced them. Any structure you find helpful is
allowed, including Track-like groupings; none is required.

## Steps

1. **Pin every input.** Import each sample, soundfont, beat grid, or other file the sound
   depends on with `tactus material add FILE...`. Paste each printed `sha256:…` ref into source
   as a named constant, and resolve it with `material(REF)`. Declare each external executable or
   native library at its point of use with `tool(NAME_OR_PATH)`. Done when no file path or
   environment variable in source decides which bytes the work hears.
2. **Write the work as a pipeline of functions.** Follow the discipline below; for effects and
   plugins see Effects and plugins (Pedalboard) under Reference. Done when
   `render` reads top to bottom as the processing order, and every stage is a named function
   whose inputs arrive as arguments and whose result is returned.
3. **Expose the choices you want to audition** as keyword-only parameters of `render`, with
   JSON-valued defaults. Done when each candidate you intend to compare differs only by
   `--params`.
4. **Run it**: `tactus run song.py --out NEW_DIR [--params '{"name": value}']`. Every run needs
   a directory that does not exist yet. Keep run directories out of Git, in one fixed place:
   the main checkout's ignored `runs/` (listed in `.gitignore`) or a folder outside the
   repository. Git holds the source, `uv.lock` and the `sha256:` refs; audio lives in run
   outputs and the pool. A file you hand to a listener stays at the path you gave until they
   are done with it. Done when stdout reports `"status": "ok"`. On failure, fix what
   `error.code` and `error.phase` point at (see Reference).
5. **Listen and compare.** A passing run proves the technical contract only. Judge the music by
   listening and comparing candidates. Discarding a candidate needs no action.

   To hear part of the work, cut it from a run you already have:
   `tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` (seconds; `END` may
   be empty for the output's end), or `excerpt(run_dir, out=…, range=[start, end])` from
   Python. It verifies and slices that run's saved audio without
   rendering again, so the excerpt is exactly what the listener hears in that candidate, even
   with plugins that render differently every time. Do not window `render` yourself: processing state (reverb and compressor tails), a loop's
   phase, and whole-mix processing (normalization, master compression) all depend on material
   before the window, so a self-windowed render differs from the same span of the full song.
6. **Keep one candidate**: edit its parameter values into `render`'s defaults, run again, and
   commit the source with `git` once the result is the version you chose. Discard edits you do
   not keep with `git checkout`.

   Before keeping it, check that the source has not moved since the candidate was rendered:
   compare the candidate receipt's `git.commit` and `source_files` with the current source.
   If it moved, the version the listener chose no longer exists. Tell the listener the source
   changed and what changed (`git log`, `git diff` against that commit). Render the same
   parameters from the current source as a new candidate, and keep it only after the listener
   approves that new render. When you report a result, compare every output hash in the two
   manifests; matching one stem does not show the mix matches.

   Archive what the listener approved before committing: `tactus material add` the approved
   run's mix (and any stems you delivered). The pool keys files by the same SHA-256 the
   manifest records, so the hash in the commit message stays retrievable with
   `material("sha256:…")` after run directories are cleaned up. The commit message names the
   approved run and its mix hash, so the revision points to what the listener heard:

   ```
   Keep c2: bass -9 dB, pad 1800 Hz

   Approved from runs/c2-recheck (mix sha256 ff0b54d…)
   ```

Structural experiments, such as a new stage or reordered processing, cannot be expressed as
parameters. Make them on a Git branch or `git worktree`, run each, and keep one by merging
with Git. Give runs made inside a worktree an `--out` in the main checkout's `runs/`, because
removing the worktree deletes everything inside it.

## Functional discipline

- **Inputs stay unchanged.** A function never writes into an array it received or into
  module-level state. It builds a fresh result, for example `out = np.zeros_like(x)`, then
  `out += …` or slice assignment into `out`, which it owns.
- **Data flows through arguments and return values.** Stages receive what they need and return
  what they make. Module-level values are constants: tempo, refs, `SEED`.
- **Stages have names.** `drums = drum_bus(hits, grid)` rather than an anonymous chain, so a
  revision can find and replace one stage.
- **Order is visible.** Processing that depends on order, such as effects after summing or
  stateful filters, appears in that order in the code that calls it.
- **Compute once.** Bind a shared intermediate to a name and pass it to each consumer, instead
  of recomputing it per consumer.
- **Randomness is explicit.** Create `np.random.default_rng(SEED)` inside `render` or a stage,
  and pass generators or derived seeds down.
- **Analysis results are frozen.** Analysis that yields a decision (tempo, onsets, slice points,
  beat grid, key) runs once, outside `render`. Freeze the result as a pinned material file
  (for example a `.npy` grid) or as constants in source, and have `render` read only the frozen
  result. Re-analysing is then an explicit revision, and a library upgrade cannot move a slice
  point. Signal-following processing (compressors, sidechain ducking, envelope followers) is
  DSP, not analysis, and stays in `render`.

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
  - Every value must be finite and within [-1, 1]. Tactus never normalizes, mixes, or
    resamples, so set the gain yourself.
- Outputs may differ in length. A mix, stems, and clips can live side by side, and no output
  name is required.
- Relative imports and relative files resolve from the entry file's directory. Author logs go
  to stderr; stdout carries one JSON result.

### Inputs

- `material("sha256:<hex>") -> Path` returns a verified path into the machine's pool
  (`$TACTUS_POOL`, default `~/.local/share/tactus/pool`). Read it with SoundFile or NumPy as
  the work requires. Handle bounded reads, sample-rate checks, and headroom in the work itself.
  Files in one pack often differ in sample rate and channel count. Converting them to the
  work's rate and layout is the work's job, done explicitly, for example with
  `scipy.signal.resample_poly`. Tactus never resamples, and a relabelled rate is not a
  conversion.
  - A missing entry fails the run with `material_unavailable`; import the file with
    `tactus material add`.
  - Changing a sample means changing its ref in source. That is a reviewable diff.
- **Folder materials.** An instrument that is itself a folder — an SFZ program with sibling
  `#include` files and sample folders it reaches by relative path, for instance — pins with
  `tactus material add DIR`, which prints a `tree:sha256:<hex>` ref instead of a plain
  `sha256:<hex>` one. `material("tree:sha256:…") -> Path` resolves it the same way: a verified
  path, but a folder whose relative paths work exactly as the original did, so
  `material(ref) / "programs/piano.sfz"` opens correctly. Verification hashes every file in the
  folder, so its cost scales with the folder's size (seconds for a multi-gigabyte instrument),
  same as a file material's re-verified read. A missing or corrupt entry fails the run with
  `material_unavailable`, same as a file material.
- `tool("sfizz_render")` or `tool("/abs/path/lib.so")` returns the resolved file and records its
  path and SHA-256. `tool("/abs/path/Some.vst3")` on a folder (a plugin bundle) hashes the whole
  tree in place, without storing it, and returns that same folder path. A missing tool fails the
  run with `tool_unavailable`.
- Imported Python distributions (for example `pytimestretch` or `scipy`) are recorded
  automatically; declare only non-Python executables and libraries.

### Time stretch and pitch shift (pytimestretch)

`pytimestretch` is installed with Tactus. It takes and returns NumPy audio:

```python
import pytimestretch

stretched = pytimestretch.time_stretch(
    audio, rate, duration_ratio=target_frames / len(audio), backend="rubberband"
)
```

- `duration_ratio` is output length over input length (above 1 is longer). To hit an exact
  length, use `target_frames / len(audio)`, and check the returned length.
- Choose `backend` explicitly (`"rubberband"` or `"signalsmith"`). The engines sound
  different, so the choice belongs to the work. `pytimestretch.pitch_shift` works the same way.
- Nothing is limited. A stretch can exceed the input's peak (1.145 measured on a full song),
  so set gain before delivery.
- For vocals, pass `formants="preserve"` when you shift pitch, especially together with a
  stretch; the default `"shift"` moves the formants with the pitch.
- `pytimestretch.time_warp(audio, rate, markers=…)` pins source frames to output frames, for
  example to put a loop's beats on the grid. Markers are integer `(source, output)` pairs
  that both strictly increase. The first pair is exactly `(0, 0)`, and the last is
  `(len(audio), output_length)`. When the first beat is not at frame 0, map frame 0 to
  output 0 and place each later beat at its target. Beat positions come from analysis, so
  freeze them (see Functional discipline).
- These engines preserve pitch. When pitch should follow speed, as in a tape stop, spin-down
  or record slow-down, use `fx.varispeed(audio, rate, speed)`. `speed` holds one playback
  rate per output frame (1.0 normal, 0.0 hold), and you shape the curve.

### Effects and plugins (Pedalboard)

`pedalboard` is installed with Tactus. It provides built-in effects, such as `Reverb`,
`Compressor`, `Delay`, `LadderFilter`, `Limiter`, `Chorus` and `Convolution`. For audible
filter sweeps use `LadderFilter`; `LowpassFilter` is a gentle 6 dB/octave slope. Pedalboard
also hosts VST3 effects and instruments. Reach for these before writing effect DSP by hand:
in a blind test the built-in reverb beat hand-written ones, and it ran about 9 times faster.

- **Layout.** Effects accept Tactus's `(frames, channels)` arrays and return the same layout.
  `fx.render_instrument` also returns `(frames, channels)`. Only a direct instrument call
  (`plugin(messages, ...)`) returns `(channels, frames)`.
- **One pass per stem.** Build one `Pedalboard([...])` per chain and process the whole stem in
  one call. The default `reset=True` starts from a clean state and compensates latency the
  plugin reports. A fresh instance per independent render keeps state from leaking between
  renders.
- **Tails.** Processing stops at the input's last frame, which cuts reverb and delay tails.
  `fx.process_automated(..., tail_seconds=…)` appends that much silence for you. For a
  direct chain call, append it yourself
  (`np.vstack([stem, np.zeros((tail_frames, channels))])`). The tail length is your choice.
- **Automation (parameters changing over time).** Use
  `fx.process_automated(chain, stem, rate, update, block_seconds=0.02, tail_seconds=…)`
  (`from tactus import fx`). It calls your `update(t)` with each block's start time in
  seconds, before processing that block through the same instance. In `update`, set the
  curve's value for time `t` (`lpf.cutoff_hz = …`, or `fx.set_param(...)`). The curve itself
  (shape, start, end) is yours; the helper handles block order, `reset` and tail silence, and
  it shifts out latency a plugin reports. Changes land on block boundaries, not
  sample-accurately.
- **VST3 plugins.** A VST3 plugin is a folder (`Name.vst3/Contents/...`); `tool()` on that
  folder hashes the whole bundle in place and returns the folder itself, so it is one step
  into `load_plugin`:

  ```python
  synth = pedalboard.load_plugin(str(tool(str(Path.home() / ".vst3/OB-Xf.vst3"))))
  ```

  - Set every parameter in source; the settings are part of the work. Use
    `fx.set_param(plugin, name, value, unit=None)`. It snaps a number with a unit (`"ms"`,
    `"s"`, `"Hz"`, `"kHz"`, `"cents"`, `"dB"`, `"%"`) to the nearest valid label of a
    discrete parameter, range-checks continuous ones, and suggests names on a typo. Other
    units work when they match the labels' own unit (`"semitones"`, `"voices"`). It
    returns the value actually set: record that value, not the one you requested.
    Before setting a plugin's parameters, look at them:
    `print(fx.format_table(fx.describe(synth, "env")))` lists each parameter's current value,
    units, range and labels. Units are often missing (Dexed reports none, and Cardinal's
    parameters are mostly 0–127), so read the range for the scale: 0–100 is a percentage, so
    `1.0` means 1%. Some plugins start with no usable sound (OB-Xf's oscillators are off by
    default), and the current values show it.
  - Render an instrument with
    `fx.render_instrument(synth, messages, duration=seconds, sample_rate=rate)`. Messages are
    `mido` messages or `(bytes, seconds)` tuples, timed in absolute seconds from the start of
    the render, and `duration` should include release time. It returns Tactus
    `(frames, channels)` audio. Changing parameters can make the first render sound before
    any note, so it runs a silent warm-up render first; calling the plugin directly skips
    that step and can leave that start transient in your stem.
- **Check levels per section, not just a peak.** A plugin with missing samples renders
  silence without raising, and a parameter on the wrong scale can leave a part about 40 dB
  too quiet without being silent. A peak above zero catches neither reliably. Measure each
  plugin's output per section, compare it with what you intended, and raise on a part that
  is far off:

  ```python
  def section_dbfs(audio, rate, bounds):  # bounds: [(start_s, end_s), ...]
      rms = [np.sqrt(np.mean(audio[round(a * rate) : round(b * rate)] ** 2)) for a, b in bounds]
      return [20 * np.log10(max(r, 1e-9)) for r in rms]
  ```
- **Not every plugin is deterministic.** Some VST3 instruments (OB-Xf, for one) render
  slightly different audio from identical input on every run. For works using them, a
  re-render's hashes will not match, even with unchanged source. Archive the approved audio,
  and compare re-renders by ear or by level, not by hash.
- **Not supported.** External sidechain into a VST3 effect. Duck from known hit times instead.

### Run results

Success prints `{"status": "ok", "outputs": {name: wav_path}, "manifest": path, "receipt":
path}`.

`manifest.json` (`format_version` 1) identifies the saved audio: `kind`, `sample_rate`, and
`outputs` as `{name: {sha256, frames, channels, file}}`. Each `file` is
`<name>-<sha256[:8]>.wav`, written directly under `--out` (`wav_path` above is that file's
absolute path); the full `sha256` in the manifest is what verifies it.

An excerpt directory has no receipt; its `manifest.json` has `kind` `tactus.excerpt` and
carries:
- `range`: `start_seconds`, `end_seconds`, `start_frame`, `end_frame` and `omitted`. These
  are the requested seconds and their rounded frames (`end_seconds` and `end_frame` are
  `null` for an open end), plus the requested outputs that had no frames in range and so
  were not published.
- `source`: `run` (the source run directory) and `manifest_sha256` (the hash of that run's
  manifest), so the excerpt traces back to the run and its receipt.
- A `source_frames` entry on each output: that output's length in the source run.

`receipt.json` (`format_version` 2) attributes the run:

- `entry`, `parameters`: effective values, defaults included.
- `source_files`: the SHA-256 of each `.py` file under the entry directory. Scratch scripts
  placed there are recorded as well, even when `render` never imports them.
- `dependency_lock`: the nearest `uv.lock`, as `{path, sha256}` or null.
- `git`: null outside a repository, or `{commit, dirty, untracked, patch}`. `patch` names
  `source.patch` in the run directory when tracked files changed or untracked `.py` files
  existed. `commit` plus that patch restores the source that actually ran.
- `elapsed_seconds`: the wall time of the `render` call.
- `materials`: the refs resolved, in order.
- `tools`: `{name, path, sha256, kind}` for each declared tool. `kind` is `"file"` for a single
  resolved file, or `"tree"` for a hashed folder (a plugin bundle).
- `python_packages`: an object mapping each imported distribution name to its version.
- `runtime`, `reproducibility`, `attribution_scope`.

A receipt guarantees the saved outputs. It does not guarantee that re-running the source
reproduces them. Say an old version can be reproduced only after you re-render it and every
output hash matches; until then, say it is expected but unverified, and point to the archived
file if there is one.

Errors print `{"status": "error", "error": {code, phase, message}}`. `phase` is one of
`request`, `load`, `bind`, `execute`, `validate`, or `publish`. The exit code is 2 for
request, load, and bind errors, 1 otherwise, and 130 when cancelled. A failed run leaves no
output directory.

### Worked examples

Both examples live in the Tactus repository
(`https://github.com/rytho-ai/tactus`, or the local checkout that installed the package):

- `examples/real-chop-flip/`: a real sample with a beat grid, bounded reads, a
  `pytimestretch` warp to an exact length, and a bass-level candidate parameter.
- `examples/phonon-ballad/`: a full song with pinned drum samples, a soundfont through a
  declared native library, and palette/drum parameters.
