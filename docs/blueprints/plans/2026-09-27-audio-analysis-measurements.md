# Audio analysis, part 1: loudness and peaks — plan

> Generated: 2026-09-27 · Source: the [audio-analysis probe](../thoughts/2026-09-27-audio-analysis-probe.md)
> (CLI and function arms 0 errors at ~100k tokens vs 71 errors at ~230k without tools; CLI and
> functions tied) and the board's parked item, resumed by Paul ("接著處理") · Grounding: the
> probe prototype `tanalysis.py` / `tanalyze.py` and its tests (scratchpad `probe-analysis/`),
> `src/tactus/cli.py`, `src/tactus/store.py` (`levels`), `src/tactus/fx.py`.

## Context

The probe's tool arms used every measurement below. Without tools, Agents rebuilt them with
pyloudnorm and SciPy correctly but at twice the tokens. They also had no shared definitions for:

- a flat top;
- where a dropout starts;
- which stereo windows to skip.

Onsets (part 2) and beat tracking (part 3) are not in this plan:

- onsets wait on validation against unseen material, which is running;
- beat tracking has not been probed.

## Resolved choices

- **Scope (Paul, 2026-09-27: "我們analysis先以音量、頻率為主就好"):** loudness and peaks now;
  frequency measurements next, after a necessity probe. DC offset, stereo correlation and
  digital-silence runs are dropped from this plan.

- **A new package, `tactus.analysis`**, gives analysis its own room instead of another loose
  module at the package root; onsets and beats join it later. It reports values, never
  verdicts. Works apply their own thresholds, following "Tactus reports, not blocks".
- **Functions** take `(audio, sample_rate)`, with audio in Tactus's `(frames,)` or
  `(frames, channels)` float layout:
  - `integrated_lufs` (ITU-R BS.1770 via pyloudnorm; `None` for silence or audio too short to
    gate);
  - `true_peak_dbtp` (BS.1770-4, 4× oversampling);
  - `sample_peak_dbfs`;
  - `rms_dbfs` (all channels flattened);
  - `dc_offset` (per channel);
  - `flat_runs(audio, min_length=4, above=0.5)`: count, longest and first positions of runs of
    identical absolute value;
  - `correlation_windows(audio, rate, seconds=1.0, floor_db=-60.0)`: per-window left/right
    Pearson correlation and the minimum, skipping quiet windows;
  - `silent_runs(audio, rate, min_ms)`: exact-zero runs strictly between the first and last
    non-zero sample, which is the dropout definition the probe needed and Agents hand-filtered.

  `analyze(audio, rate)` returns all of them as one JSON-ready dict.
- **CLI:** `tactus analyze PATH... [--windows]`.
  - `PATH` is a WAV file or a run or excerpt directory, which analyzes every output in its
    manifest.
  - It prints one JSON object per file.
  - The CLI calls only `tactus.analysis`, so there is one implementation behind two doors.
- **Not in this plan:**
  - changing the manifest or `levels`: the full-scale reporting item stays in Future, as Paul
    deferred it;
  - onsets and beats;
  - key, chords and structure;
  - dB conversion helpers.
- **Skill:** SKILL.md is unchanged. `reference.md` gets a short "Measuring audio" section: the
  command, the function list, and that values are measured on what you pass or on the saved
  WAV.

## Approach

1. `src/tactus/analysis/__init__.py`:
   - port the prototype's measurements, keeping its dropout, flat-run and window definitions;
   - type hints and a header docstring;
   - export as `tactus.analysis`.
2. `cli.py`: the `analyze` subcommand, reading WAVs with SoundFile and resolving run or excerpt
   directories through their manifest.
3. Tests:
   - pyloudnorm agreement;
   - true peak of an fs/4 sine with phase offset (known inter-sample overshoot);
   - flat runs at and below `min_length`;
   - silent runs inside vs at the edges;
   - correlation with a polarity flip in part of the file and with quiet windows;
   - DC;
   - mono and stereo shapes;
   - CLI on a file and on a run directory.
4. `reference.md` section, README "Supported surface", and design.md's "驗證與觀察" passage.

## Verification

- pytest, Ruff and the skill drift test.
- A fresh sonnet Agent on Part A (the delivery audit) of both rounds of the audio-analysis probe
  brief, with the skill only (no prototype files). Score with `probe-analysis/check.py`'s report
  section. Pass: 0 report errors in both rounds and use of `tactus analyze` or
  `tactus.analysis`.
