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

0. **Create the work** once, before writing source: `tactus init DIR` makes it its own uv
   project and Git repository. From then on, run everything from inside `DIR` with
   `uv run tactus ...`.
1. **Pin every input.** Add each sample, soundfont or other file the sound depends on with
   `tactus material add FILE...` and resolve its printed `sha256:…` ref, kept as a named
   constant, with `material(REF)`. Declare each external executable or native library with
   `tool(NAME_OR_PATH)`. Done when no file path or environment variable in source decides which
   bytes the work hears.
2. **Write the work as a pipeline of functions** (see Functional discipline). Done when
   `render` reads top to bottom as the processing order, and every stage is a named function
   whose inputs arrive as arguments and whose result is returned.
3. **Expose the choices you want to audition** as keyword-only parameters of `render`, with
   JSON-valued defaults. Done when each candidate you intend to compare differs only by
   `--params`.
4. **Run it**: `tactus run song.py --out NEW_DIR [--params '{"name": value}']`, into a directory
   that does not exist yet. Keep run directories out of Git in one fixed place (the work's
   ignored `runs/`); Git holds source, `uv.lock` and refs. A file you hand to a listener stays
   at its path until they are done with it. Done when stdout reports `"status": "ok"`; on
   failure, fix what `error.code` and `error.phase` point at.
5. **Listen and compare.** A passing run proves the technical contract only. To hear part of
   the work, cut it from a run you already have with `tactus excerpt`; never window `render`
   yourself — tails, loop phase and whole-mix processing depend on what came before, so a
   self-windowed render differs from the same span of the full song.
6. **Keep one candidate**: for instruments that change on each render, first follow
   **Saved takes** in the reference to preserve and adopt the exact performance. Then edit
   its parameter values into `render`'s defaults, run again, and
   commit once the result is the version you chose; discard the rest with `git checkout`. If
   the source moved since the candidate was rendered, the version the listener chose no longer
   exists: tell them what changed, render it again as a new candidate, and keep it only after
   they approve it. Archive the approved audio in the pool and name its run and mix hash in the
   commit message.

Structural experiments (a new stage, reordered processing) go on a Git branch or worktree; keep
one by merging.

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

[`reference.md`](reference.md) holds the details. Read the section you need when you reach it:

- **The `render` contract**: exact return shape, output names, value rules.
- **Creating a work**, **Listening to part of a run**, **Keeping a candidate**: the full
  commands and checks behind steps 0, 5 and 6.
- **Inputs**: folder materials, `tool()` on plugin bundles, and the packages installed with
  Tactus (NumPy, SciPy, SoundFile, pyloudnorm, librosa, Pedalboard, pytimestretch, pyqmdsp, `mido`).
- **Measuring audio**: discover level, spectral and rhythm analyses through `tactus analyze`,
  including beat times and tempo; freeze accepted estimates before using them in `render`.
- **Saved takes**: retain a chosen performance across source edits, cache deletion or machine
  changes; regenerate explicitly when MIDI or patch settings change.
- **Reusing unchanged stages**: `@stage` with `--reuse`, so an approved part does not re-roll
  while you audition another parameter.
- **Helpers** (`tactus.fx`) for plugin parameters, VST3 instruments and automation, and
  **Musical time** (`tactus.timing`, optional) for tempo maps, swing and groove. Beats there are
  0-based: a musician's "beat 2" is `beat=1.0`.
- **Library behavior that affects Tactus results**: array layouts, renders that change between
  runs, clipping the report cannot see.
- **Run results**: the manifest, receipt and error fields, and rebuilding a run elsewhere.

Worked examples live in the Tactus repository (`https://github.com/rytho-ai/tactus`, or the
local checkout that installed the package): `examples/real-chop-flip/` and
`examples/phonon-ballad/`.
