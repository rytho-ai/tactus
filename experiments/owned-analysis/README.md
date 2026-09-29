# Owned analysis and basic DSP verification

Tactus now owns all 20 NumPy/SciPy analysis implementations; beat tracking remains on
pyqmdsp. The migration preserves the established definitions, not an assertion that a
new onset detector is more accurate. `tactus.dsp` adds optional gain/fade/pan and five
RBJ filter/EQ types with explicit state. Runtime stopped requiring librosa and pyloudnorm
in this migration. **Current update:** Numba is now used by DSP;
only librosa remains in the optional `librosa` extra. Pyloudnorm has been removed.
Its loudness answers are preserved in [ordinary test fixtures](../../tests/fixtures/README.md).
The historical reports below retain the versions and counts actually measured.

## Reproduce

Use the repository's optional librosa extra for spectral/onset comparisons.
`check.py` now performs six live librosa checks per input; loudness uses the frozen
ordinary tests and the independent EBU check. Historical `report.json` retains its
original seven-check results (including then-live pyloudnorm); use a fresh report
path when rerunning the current script:

```bash
uv run --extra librosa pytest -q tests/test_analysis.py tests/test_analysis_features.py tests/test_level_curves.py tests/test_owned_analysis.py tests/test_dsp.py
uv run --extra librosa python experiments/owned-analysis/check.py \
  --audio dogfood/2026-09-25-full-song-3/work/runs/c4/mix-32222836.wav \
    dogfood/2026-09-29-librosa-analysis/corpus/loops/*.wav \
  --out dogfood/owned-analysis-current.json
uv run python experiments/level-curves/check.py \
  --corpus dogfood/2026-09-29-level-curves/ebu \
  --archive dogfood/2026-09-29-level-curves/ebu-loudness-test-setv05.zip \
  --integrated --out experiments/owned-analysis/ebu-report.json
```

Audio is local and ignored. The nine loops can be rebuilt with
[the original corpus instructions](../librosa-analysis/README.md); the complete production
is local session material. Substitute other files with `--audio` to repeat the comparison;
the report records their hashes and durations. EBU archive acquisition/checksums are in
[the level-curve instructions](../level-curves/README.md). Official files are used for
technical testing only and are not redistributed.

## Correctness evidence

- `report.json`: 77 reference comparisons on one 149 s stereo production, its first 5 seconds and nine drum
  loops. Mel/MFCC/chroma/onset strength/integrated LUFS compare with pinned librosa 1.0.0
  and pyloudnorm 0.2.0, with absolute tolerance 1e-8 and relative tolerance 1e-10.
  Ordinary and backtracked onset times must match exactly. This is equivalence evidence,
  not an onset-accuracy evaluation; the original difficult-loop accuracy limits remain.
- `before-parity.json`: all 20 analyses compared with captured pre-migration results on
  that production, including unchanged functions, metadata, timestamps and nulls.
- `ebu-report.json`: 102/102 checks pass on the official v05 fixtures: existing M/S/LRA
  regression plus integrated LUFS cases 1–8 at 0.1 LU tolerance. Not full meter certification.
  Expected values follow [EBU Tech 3341](https://tech.ebu.ch/docs/tech/tech3341.pdf).
- Tests cover quiet passages after loud passages, arbitrary window/hop sizes, strided arrays,
  finite-power overflow, short signals, centered framing, filter rounding, gates, layouts,
  nonmutation, onset boundary windows and zero spacing. Existing analytical tone properties
  and direct reference tests continue to run.
- An upstream empty-event backtracking exception is deliberately fixed: no detected onsets
  now returns an empty list with `backtrack=True`. Valid detected event locations are preserved.

## DSP and runtime evidence

`tests/test_dsp.py` checks equal-power pan, fade endpoints/overlap, gain/headroom, independent
Butterworth responses, EQ center/end gains, channel isolation, reset and exact whole/block
filter equality (including empty blocks), explicit tails and caller-state nonmutation.
It also runs a production through the CLI. This verifies basic DSP behavior, not subjective
sound quality or general time-varying filter smoothing.

`cli-report.json` records 14 actual `uv run --no-dev tactus` commands after
`uv sync --no-dev`. Import discovery confirmed librosa, pyloudnorm and numba were absent.
Twelve analyses (including pyqmdsp beats) ran on the full production; saved JSON matched
stdout and NPZ descriptors loaded with their reported shapes. A stereo gain/fade/pan/filter
production rendered and exported WAV successfully, and its whole/block arrays matched
exactly. `uv run` alone may leave extra installed packages; the preceding exact sync matters.

The wheel includes both adapted-code notices (`LICENSE.librosa`, `LICENSE.pyloudnorm`),
`dsp.py` and the shared biquad implementation. Production requirements contain seven
packages: NumPy, SciPy, SoundFile, Mido, Pedalboard, pyqmdsp and pytimestretch.

## Performance method

`before-profile.json` retains the pre-migration full-function timings (median of three warm
calls); `report.json` records current medians of five warm calls on each identical input.
File loading, CLI startup and imports are excluded. Same i5-13600K/Linux host and locked
NumPy/SciPy versions; measurements are sequential observations, not a randomized paired
benchmark. Compare the function names to avoid confusing prototype-only numbers with
integrated validation and result-conversion overhead. Ownership does not depend on speedups.

Aligned level windows reduce local hop bins once. Other grids retain direct reductions.
Neither path subtracts global prefix sums, preserving very quiet energy after loud signals.
FFT work is chunked to avoid a whole-file windowed-frame allocation. No Numba path is shipped.
The earlier startup probe found that compilation/import overhead could outweigh short
analysis runs. Later [Q-transform timings](../q-transforms/README.md#startup-matters)
separate startup from warm throughput; DSP now independently uses Numba where measured.

## Integrated performance results

Same 149.189 s / 44.1 kHz stereo production, milliseconds per public function:

| Function | Before | Owned implementation | Ratio |
| --- | ---: | ---: | ---: |
| `loudness` | 179.2 | 144.9 | 1.24x |
| `rms_curve` | 118.8 | 36.5 | 3.25x |
| `peak_curve` | 166.7 | 35.9 | 4.64x |
| `momentary_loudness` | 183.7 | 113.9 | 1.61x |
| `short_term_loudness` | 140.6 | 105.3 | 1.34x |
| `loudness_range` | 166.9 | 133.8 | 1.25x |
| `mel` | 236.7 | 214.5 | 1.10x |
| `mfcc` | 265.8 | 227.0 | 1.17x |
| `chroma` | 351.4 | 310.0 | 1.13x |
| `onsets` | 324.7 | 308.7 | 1.05x |

The large RMS/peak gains support the bin-reduction optimization; small differences in the
other rows should not be generalized beyond this host/input. The owned implementation
includes input validation and JSON/array result construction. Five-second RMS/peak calls
are 0.79/0.76 ms; no new-process speedup claim is inferred from these warm timings.

## Repository gates

- Full `uv run pytest -q`: 751 passed, 1 skipped (the existing opt-in install test).
- Final focused verification after the integration-reduction refinement and three added
  Mel-transition cases: 209 level/reference tests and 204 feature/owned/DSP tests passed.
  The current collection is 755 tests; three were added after full-suite collection.
- Repository-wide Ruff and formatting of changed Python files passed; `uv build` passed.
- No global installation, commit or publication performed.
