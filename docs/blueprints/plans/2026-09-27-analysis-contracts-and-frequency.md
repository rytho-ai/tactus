# `tactus analyze` in categories, one subcommand per analysis, plus spectral analyses — plan

> Generated: 2026-09-27 · Source: the [frequency probes](../thoughts/2026-09-27-frequency-analysis-probes.md)
> (with no definitions in the brief, a shared CLI gave 0 errors vs 3 and identical numbers across
> Agents); Paul asked for a phonon-like structure so analyses stay queryable as they grow, then
> chose the simpler design below over phonon-style contracts ("我同意用這個簡單版本") ·
> Grounding: phonon's discover/inspect/run model, `src/tactus/analysis/__init__.py`,
> `src/tactus/cli.py`, the frozen prototype and its validation (scratchpad `probe-freq2/toolsrc/`,
> `freq-validation/`).

## Context

`tactus analyze PATH` shipped earlier the same day as one flat JSON of loudness numbers, which
does not scale. The frequency probes showed the value of unifying is the definitions: without a
shared one, two methods for the same question differed by about 11 dB (band reference) and about
0.5 s (amplitude- vs power-weighted centroid).

phonon solves "many analyses, one way to query them" with typed contracts, a registry and
discover/inspect/run verbs, which it needs across a network and many providers. Tactus is local:
a function's signature and docstring, surfaced through the `--help` every Agent already uses,
give the same self-description with less to build and nothing to keep in sync.

## Resolved choices

- **Categories with progressive disclosure** (Paul: "我覺得他應該要被分類欸，然後要有統一的分類（運用progressive disclosure", then "好啊，那就這樣"):
  - a category is one aspect of sound and one module in `tactus/analysis/`;
  - names inside a category carry no prefix;
  - three levels:
    1. `tactus analyze --help` lists categories;
    2. `tactus analyze CATEGORY --help` lists that category's analyses, one line each;
    3. `tactus analyze CATEGORY NAME --help` gives parameters, fields, units and definitions.

    Run with `tactus analyze CATEGORY NAME PATH...`. The library mirrors it:
    `from tactus.analysis import spectral; spectral.centroid(...)`, and `help(spectral)` lists
    the category.
  - Categories now:
    - `level`: `loudness` (integrated LUFS), `true_peak`, `sample_peak`, `rms`, `clipping` (flat
      runs);
    - `spectral`: `spectrum`, `band_levels`, `centroid` (power-weighted), `peaks`, `stft`.

    Later categories, such as `pitch`, `rhythm` and `stereo`, join the same structure.
- **Validation outcome** (scratchpad `freq-validation/`, unseen material, rules set first):
  - `peaks` passed: 30/30 partials within ±0.2%.
  - `fundamental` failed: 47.5% within ±50 cents. It is no worse than librosa pyin/yin or
    autocorrelation on any material kind; two SFZ bass patches carry a sub-octave layer louder
    than the fundamental and defeat every method.
  - `f0_over_time` failed: 62%, and 7% on FM tones, where it trails pyin/yin. Its flat-line bug
    was fixed: short-window frequency grid plus window length.

  So there is **no `pitch` category yet**. `spectrum`, `band_levels`, `centroid` and `stft` are
  computations of stated definitions, not estimators, so they carry no overfitting risk.
- **One analysis is one function in `tactus.analysis`:**
  - keyword parameters with type hints and defaults;
  - a docstring stating what it measures, each result field's unit, and the definition (for
    example, "centroid: power-weighted mean frequency of each 2048-sample Hann frame…", or
    "levels in dB, a full-scale sine = 0 dB");
  - an integer `revision` set with a one-line decorator and bumped only when a result's meaning
    changes;
  - returns a JSON-ready dict.

  `ANALYSES`, an explicit tuple, lists the public analyses.
- **CLI subcommands generated from each category module's `ANALYSES`** (the three levels above):
  - `tactus analyze --help` lists every analysis with the first docstring line (phonon's
    discover);
  - `tactus analyze NAME --help` shows its parameters with defaults and types, and the full
    docstring (inspect);
  - `tactus analyze NAME PATH... [--param-name value ...] [--out DIR]` runs it on WAV files or
    run/excerpt directories, read through `read_published`. It prints one JSON object per input:
    `{path, output?, sample_rate, analysis, revision, params, result}`, where `params` is every
    effective value, defaults included.
- **The same functions are the library.** `from tactus import analysis; analysis.spectrum(audio, rate,
  resolution_hz=0.5)` returns the CLI's `result` dict. Keyword names mirror the flags
  (`--resolution-hz` ↔ `resolution_hz`), `help(analysis.spectrum)` shows the same text as
  `--help`, and `analysis.spectrum.revision` gives the revision. Use it inside `render` when a
  decision depends on the signal. Use the CLI to check delivered files or to analyse material
  before freezing the result.
- **Large results** (the STFT) write `.npz` under `--out` and return `{file, shape, …}`. Without
  `--out` the result carries a summary only and says so.
- **Errors** use Tactus's existing `{status: "error", error: {code, phase, message}}`.
- **Consistency by test, not by a contract layer:** a test asserts that every entry in `ANALYSES`
  has a revision, a docstring naming a unit for each result field, and typed, defaulted
  parameters, and that its `--help` renders.
- **Not built:**
  - a contract or registry data model;
  - JSON schemas;
  - separate discover/inspect/validate verbs;
  - jobs, queues, an artifact store, routing, MCP.

  A `--json` form of help can be added later if an Agent needs machine-readable listings.
- **CLI break:** the flat `tactus analyze PATH` output is replaced; it is hours old and used only
  by probes. A path given without a subcommand is an error that points to `tactus analyze --help`.

## Approach

1. Package:
   - split `analysis` into `level.py` and `spectral.py` (spectral ported from the validated
     prototype, without the pitch functions);
   - add `_revision` and `ANALYSES` in `__init__.py`, re-exporting the plain functions;
   - update the header.
2. `cli.py`: build `analyze`'s subparsers from `ANALYSES`, flags from `inspect.signature` and
   type hints, help from docstrings.
3. Tests:
   - the consistency test above;
   - `--help` listing;
   - run on a file and on a run directory;
   - an unknown analysis or flag errors;
   - `.npz` delivery;
   - each frequency analysis against known signals (non-bin tones, strong-2nd-harmonic bass, a
     linear sweep's crossing, band shares vs analytic).
4. `reference.md`: "Measuring audio" becomes the three commands and "read definitions with
   `tactus analyze NAME --help`". Update README "Supported surface" and design.md's 驗證與觀察.

## Verification

- pytest, Ruff and the skill drift test.
- A fresh sonnet Agent on round 1 of the no-definition frequency brief (`probe-freq2`), with the
  skill only. Pass: 0 objective errors, it finds the analyses through `--help`, and its band dB and
  sweep time equal the analyses' own values.
