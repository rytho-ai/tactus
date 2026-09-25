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
2. **Write the work as a pipeline of functions.** Follow the discipline below. Done when
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

   To hear part of the work, use `--range START:END` (seconds, `END` may be empty for the
   output's end) and optionally `--outputs a,b` to publish only those outputs. The slice is cut
   from a full render, after Tactus validates it, so it sounds exactly as it does in the song.
   Do not window `render` yourself: processing state (reverb and compressor tails), a loop's
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
- `tool("rubberband")` or `tool("/abs/path/lib.so")` returns the resolved file and records its
  path and SHA-256. A missing tool fails the run with `tool_unavailable`.
- Imported Python distributions (for example `pyrubberband` or `scipy`) are recorded
  automatically; declare only non-Python executables and libraries.

### Run results

Success prints `{"status": "ok", "outputs": {name: wav_path}, "manifest": path, "receipt":
path}`.

`manifest.json` (`format_version` 1) identifies the saved audio: `kind`, `sample_rate`, and
`outputs` as `{name: {sha256, frames, channels, file}}`. Each `file` is
`<name>-<sha256[:8]>.wav`, written directly under `--out` (`wav_path` above is that file's
absolute path); the full `sha256` in the manifest is what verifies it.

Given `--range`, the manifest also carries `range`: `start_seconds`, `end_seconds`,
`start_frame`, `end_frame`, `omitted` — the requested seconds and their rounded frames
(`end_seconds` and `end_frame` are `null` for an open end), and the list of requested output
names that had no frames in range and so were not published. Each published output's entry also
gains `source_frames`: that output's full-render length, so a clamped or short slice is visible
next to its own (now shorter) `frames`.

`receipt.json` (`format_version` 2) attributes the run:

- `entry`, `parameters`: effective values, defaults included.
- `range`: the same `start_seconds`/`end_seconds`/`start_frame`/`end_frame`/`omitted` fields as
  the manifest, or `null` without `--range`. `outputs`: the requested output names from
  `--outputs`, or `null` without it.
- `source_files`: the SHA-256 of each `.py` file under the entry directory. Scratch scripts
  placed there are recorded as well, even when `render` never imports them.
- `dependency_lock`: the nearest `uv.lock`, as `{path, sha256}` or null.
- `git`: null outside a repository, or `{commit, dirty, untracked, patch}`. `patch` names
  `source.patch` in the run directory when tracked files changed or untracked `.py` files
  existed. `commit` plus that patch restores the source that actually ran.
- `elapsed_seconds`: the wall time of the `render` call.
- `materials`: the refs resolved, in order.
- `tools`: `{name, path, sha256}` for each declared tool.
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

- `examples/real-chop-flip/`: a real sample with a beat grid, bounded reads, a Rubber Band
  warp declared with `tool`, and a bass-level candidate parameter.
- `examples/phonon-ballad/`: a full song with pinned drum samples, a soundfont through a
  declared native library, and palette/drum parameters.
