# Beat tracking with qm-dsp, prototyped inside Tactus — plan

> Generated: 2026-09-28 · Source: the [beat engine comparison](../thoughts/2026-09-28-beat-engine-survey.md)
> (QM's tempo tracker beat librosa on beats: hard subsets 0.92 vs 0.78 F, Ballroom 0.80 vs 0.71;
> downbeats unusable); Paul: "好，那就就用qm-dsp", then "你先在tactus裡測試看看之後再移植到套件上" ·
> Grounding: the local builds and adapters in scratchpad `beat-eval/engines/` (qm-dsp at commit
> `e34a3cc`, qm-vamp-plugins' `BeatTrack` plugin source), Mixxx's direct use of qm-dsp,
> `src/tactus/analysis/`, `src/tactus/cli.py`.

## Context

The comparison ran QM through its Vamp plugin. Paul wants it bound directly, as Mixxx does,
tried inside Tactus first and moved to a standalone package (working name `pyqmdsp`) once it
works. Only beat tracking is in scope; it is the only qm-dsp part that was validated.

## Resolved choices

- **Work on a branch,** `qmdsp-beats`; main is untouched until the prototype passes.
- **Native code:**
  - vendor the minimal qm-dsp sources needed for `DetectionFunction`, `TempoTrackV2` and their
    dependencies (FFT via its bundled kissfft, maths helpers) under `native/qmdsp/`, pinned to
    commit `e34a3cc`, with its GPL-2.0-or-later licence and a README naming the source;
  - add a thin C API in `native/qmdsp/tactus_beats.cpp`:
    `int qm_beats(const float *mono, long n, int rate, double **beats_out, long *n_beats, double *bpm_out)`
    plus a free function;
  - reproduce the qm-vamp-plugins `BeatTrack` defaults: detection function type complex
    spectral difference, step and block sizes from the plugin, `TempoTrackV2` with the plugin's
    whitening, default input tempo and constraint settings. Read them from the plugin source in
    `beat-eval/engines/`, do not guess.
- **Build:** `scripts/build_qmdsp.sh` compiles `native/qmdsp` into a shared library in a
  git-ignored build directory. Packaging is not changed in the prototype.
- **Python:** `tactus/analysis/rhythm.py`, a new category ("rhythm: pulse and tempo").
  - `beats(audio, sample_rate)` loads the library with ctypes, mixes to mono and returns
    `{beats_s, bpm, tempo_curve}`, where `tempo_curve` holds 60 / inter-beat interval at each beat.
  - The docstring states units, the algorithm (Davies and Plumbley; qm-dsp `TempoTrackV2`), and
    that downbeats are not provided and why.
  - If the library is not built, the call raises a clear error naming the build script, and the
    category's tests skip.
- **Not in scope:**
  - downbeats;
  - key, chroma and segmentation;
  - pybind11 and the standalone package, which are the next step once this passes.

## Approach

1. Vendor the sources, write the C API, and write the build script. Build locally.
2. `rhythm.py` with `ANALYSES = (beats,)`, registered in `CATEGORIES`; the generated CLI then
   gives `tactus analyze rhythm beats FILE`.
3. Tests, skipped without the library:
   - a steady click at several tempi;
   - a tempo change;
   - the consistency test covers the new category automatically.
4. **Parity gate:** run the new binding over all 72 files of `beat-eval` and compare with the
   stored `qm_tempo` Vamp results. It passes if every file's beat F-measure is within 0.01 of the
   Vamp result and the mean differs by less than 0.005. Report any file that differs.
5. `reference.md`'s Measuring audio line needs no change. Update design.md's 驗證與觀察 in one
   line.

## Verification

- pytest, Ruff, and the parity gate.
- A fresh sonnet Agent with the skill only, on a small brief: find the beats and BPM of three
  unseen drum loops (one with a tempo change) and place a marker at every beat. Pass: beat
  F-measure ≥ 0.9 against truth, and it uses `tactus analyze rhythm beats`.
