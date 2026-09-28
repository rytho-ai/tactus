# pyqmdsp — handoff: why and how

> Update 2026-09-28: the package is now published at `openmirlab/pyqmdsp`, with the broader
> qm-dsp API, nanobind bindings and upstream parity checks. The current Tactus integration
> and verification are tracked in [the integration plan](2026-09-28-pyqmdsp-integration.md).
> The original proposal below is historical; the prototype branch remains local.

> Generated: 2026-09-28 · Paul, for handing the work to someone else: "幫我寫一個要如何做？為什麼要做跟要怎麼做
> pyqmdsp 的訊息，我們交接給別人做" · Status: **not started**. A working prototype binding lives on
> branch `qmdsp-beats` of this repo (commits `aeb485a`, `69afd4d`).

## Why

Tactus is a code-first music runtime. Its `tactus analyze` command reports measurements in
categories, currently `level` and `spectral`. Beat tracking, which a DAW needs for warp, slicing
and aligning loops, is missing. Only non-neural-network engines were considered.

We measured the candidates on 72 annotated files: 31 synthetic files built from real drum hits,
with exact truth, and 41 Ballroom tracks with human annotations. The scores are mir_eval beat
F-measure at ±70 ms.

| Engine | Hard subsets (tempo change, odd meter, syncopation) | Ballroom |
|---|---|---|
| librosa `beat_track` | 0.78 | 0.71 |
| **qm-dsp `TempoTrackV2`** (Queen Mary, Davies & Plumbley) | **0.92** | **0.80** |
| Essentia RhythmExtractor2013 multifeature | 0.92 | 0.77 |

Paul listened to metronome overlays and confirmed it: "qm-dsp essentia 明顯準很多", "librosa
非常不準". qm-dsp was chosen over Essentia because it is GPL-2.0-or-later and needs only a small
C++ build, while Essentia is AGPL-3.0 and has no Python 3.12 wheel. Mixxx uses qm-dsp directly in
the same way.

Other qm-dsp parts measured so far:

- **Onset detection lost.** At ±50 ms it scored F 0.75 against librosa's 0.79 and aubio's 0.79:
  it misses quiet ghosts and tight flams.
- **Downbeat (`DownBeat`) failed**, with F 0.48 on steady 4/4.
- **Key detection: no clear win.** The mir_eval weighted score was qm-dsp 0.70, Essentia 0.70 and librosa chroma + Krumhansl 0.67 over 68 files. On 40 GiantSteps tracks it was 0.49, 0.55 and 0.49.

Tactus will use only parts that win a measured comparison. The package itself may wrap more.

Evidence:

- `docs/blueprints/thoughts/2026-09-28-beat-engine-survey.md` (on main);
- fixtures and scripts under `experiments/beat-eval/` on branch `qmdsp-beats`.

## What to build

**pyqmdsp** is a standalone Python package, a pybind11 binding of qm-dsp. Tactus depends on it,
pinned by git revision, the way it pins `pytimestretch`.

- **v0.1 scope:** beat tracking only.

  ```python
  pyqmdsp.beats(mono: np.ndarray[float32], sample_rate: int) -> dict
  ```

  It returns:
  - `beats_s`: `np.ndarray[float64]`, the beat times in seconds;
  - `bpm`: `float`;
  - `tempo_curve`: `np.ndarray[float64]`, 60 / inter-beat interval at each beat.

  It also exposes `__version__`. The GIL is released during computation, and input errors are
  clear.
- **Later, each behind its own tests:** other qm-dsp functions (key, onset detection function,
  chroma) can be wrapped for the package's own users. Tactus will not use them: onsets and key
  did not beat the alternatives. Do not add downbeats without new evidence.
- **Not in scope:** Vamp, and any GPU or neural-network code.

## How

1. **Start from the prototype.** On branch `qmdsp-beats`:
   - `native/qmdsp/` is a minimal, **byte-identical** copy of qm-dsp at commit
     `e34a3cc188332ed7c33cd9257ef164de5b587191` (`DetectionFunction`, `PhaseVocoder`,
     `TempoTrackV2`, `FFT`, `MathUtilities`, `Window.h`, bundled kissfft), with a provenance
     README and licences;
   - `native/qmdsp/tactus_beats.cpp` is the C API whose defaults reproduce the QM Vamp plugin
     `qm-tempotracker` (`plugins/BeatTrack.cpp`, `beatTrackNew`);
   - `src/tactus/analysis/rhythm.py` is the ctypes loader;
   - `scripts/build_qmdsp.sh` is the build.
2. **Keep these details exactly.** They are what reproduce the reference:
   - **Detection function:** complex spectral difference, step = `rate * 0.01161` samples, block
     = 2 × step, dbRise 3, whitening off.
   - **Framing:** plain **uncentered** sliding windows (frame k = samples `[k·step, k·step +
     block)`, no leading padding). Mixxx-style centered framing shifted every beat by one frame;
     this was found by diffing the detection function against the plugin's own output.
   - **Tracking:** trim trailing zeros, drop the first 2 detection-function frames, then
     `TempoTrackV2::calculateBeatPeriod(df, bp, tempi, 120.0, false)` and
     `calculateBeats(df, bp, beats, 0.9, 4.0)`.
   - **Time conversion:** reproduce the plugin's time conversion as it is, `beats[i] * step /
     rate`, without the `+2` frame offset.
3. **Package:**
   - a new repo, working name `pyqmdsp`; `pyqmdsp`, `qmdsp` and `qm-dsp` were all free on PyPI
     on 2026-09-28;
   - scikit-build-core + CMake + pybind11 (nanobind also acceptable), Python >= 3.12;
   - move the vendored sources to `src/qm-dsp/`, keeping them byte-identical: patches go in
     `.patch` files, never hand edits;
   - build wheels with cibuildwheel (Linux first, macOS next).
4. **Tests:**
   - steady clicks at several tempi;
   - a tempo change;
   - silence;
   - input validation.
5. **Parity gate, required:** run `pyqmdsp.beats` over the 72 evaluation files (regenerate the
   audio per `experiments/beat-eval/README.md`) and compare with
   `experiments/beat-eval/results/qm_tempo/` (the Vamp reference):
   - the mean beat F must equal the reference within 0.005, as the prototype did (0.865 vs 0.865);
   - list per-file differences. The prototype had 5 of 72 files differ by up to 0.037, traced to
     float sensitivity in `TempoTrackV2`'s dynamic-programming decode across compiler flags.
     Report any such files; do not "fix" them by changing defaults.
6. **Switch Tactus:**
   - add `pyqmdsp` to `pyproject.toml`, pinned by git rev;
   - make `rhythm.beats` call `pyqmdsp` instead of ctypes;
   - delete `native/` and `scripts/build_qmdsp.sh`;
   - `tactus analyze rhythm beats FILE` must keep its output fields.
7. **Verify in Tactus:**
   - full pytest and Ruff;
   - a fresh Agent, given only the skill, finds the beats of unseen loops through
     `tactus analyze rhythm beats`;
   - merge `qmdsp-beats` into main, keeping `experiments/beat-eval/`.

## Licence

- **qm-dsp** is GPL-2.0-or-later; its bundled kissfft is BSD-3-Clause. pyqmdsp is therefore
  GPL-2.0-or-later. It can be published on GitHub and PyPI with its sources and licences.
  Closed-source redistribution is not possible; whether Queen Mary offers a commercial licence is
  unverified.
- **Tactus** already carries GPL through pedalboard (GPLv3) and pytimestretch (GPL-2.0). qm-dsp's
  "or later" is compatible with both. Tactus's existing pytimestretch/pedalboard conflict is a
  separate item in Future.

## Decisions still with Paul

- The GitHub owner and repo name (`rytho-ai/pyqmdsp`, `ChenPaulYu/pyqmdsp` or other), and
  whether to publish to PyPI.
- Which extra qm-dsp functions to wrap beyond beats.
