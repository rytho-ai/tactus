# Level curves and loudness range

Tactus owns the selected pymixtool-inspired measurements directly: momentary and short-term
loudness, LRA, and RMS/sample-peak curves. The new calculations use NumPy/SciPy only.
No pymixtool dependency, source package or analyzer class was added. Existing integrated
loudness still uses pyloudnorm; existing dependencies and numerical contracts are unchanged.

## Evidence

Full `uv run pytest -q`: **638 passed, 1 skipped** (existing opt-in install test).
Focused level/analysis tests: 140 passed. Repository-wide Ruff and `uv build` passed;
the wheel includes the native helper and its retained coefficient implementation license.

[`report.json`](report.json) records **94/94 checks passing on 53 EBU v05 audio files**:

- Tech 3341 calibration cases 1, 2 and the five-channel variant of 6: M/S curves.
- Cases 9 and 12: alternating levels with the expected constant S/M response.
- All 20 offset files for each of cases 10 and 13: maximum S/M values.
- Cases 11 and 14: all 20 successive level maxima, evaluated offline.
- All six Tech 3342 LRA cases, including the two recorded programme excerpts.

Largest M/S error: **0.0663 LU** (tolerance 0.1). Largest LRA error: **0.0234 LU**
(tolerance 1). LRA results: 10.0011, 4.9994, 19.9951, 14.9993, 4.9766, 14.9846 LU.
Expected values and tolerances come from
[EBU Tech 3341](https://tech.ebu.ch/docs/tech/tech3341.pdf) and
[EBU Tech 3342](https://tech.ebu.ch/docs/tech/tech3342.pdf).
This verifies the selected file-based measurements; it is not certification of a complete
EBU meter, live streaming implementation, or the existing true-peak function.

The regression tests additionally cover published 48 kHz filter coefficients, independent
library block powers at four sample rates, level calibration, stereo polarity and channel
weights, complete-window timing/tails, quiet passages after loud ones, silence, insufficient
duration, malformed inputs, no imports from pymixtool/pyloudnorm in new calculations, and
generated CLI help/results/provenance. Tests use synthetic signals without downloads.

## Contracts and implementation

Curves use complete rectangular windows with timestamps at the **exclusive window end**.
Sizes round to sample counts, and partial tails are discarded. Loudness filters run once
over the entire input with zero initial state. The two K-weighting biquads use De Man
coefficients, adapted from pyloudnorm's MIT-licensed coefficient implementation; the notice
is retained in `src/tactus/analysis/LICENSE.pyloudnorm`. No pyloudnorm code is called by the
new calculations. Existing integrated LUFS keeps its default filter and may differ slightly.

Momentary uses 400 ms / 10 ms window/hop, short-term 3 s / 100 ms. LUFS adds weighted channel
powers (L/R/C/Ls/Rs, no LFE); RMS averages powers; sample peak takes the maximum across
channels. Zero-energy curve values are null. Short inputs yield empty curves. Loudness
accepts 8 kHz or higher integer sample rates; its arbitrary-rate formula is numerically
compared at 22050/44100/48000/96000 Hz, not certified at every possible rate.

LRA uses a 3 s window, at least 10 Hz sampling, and 1.5 s trailing silence. It gates at
-70 LUFS and 20 LU below the absolute-gated energy mean, then subtracts the nearest ordered
10th percentile from the 95th (ties upward). Original durations under 3 s or no gated data
yield null; durations under 60 s are marked provisional. Silence/tails can inflate LRA for
short or isolated events; the flag does not guarantee stability beyond 60 s.

Each window reduces its own power values instead of subtracting large whole-file prefix
sums. This preserves very quiet windows after loud passages. It also avoids constructing
an overlapping frame matrix. No streaming state or real-time performance promise is made.

## Reproduce official-file verification

EBU's [test set page](https://tech.ebu.ch/publications/ebu_loudness_test_set) identifies v05.
Direct EBU download returned HTTP 403 on this machine. The identical archive was obtained
from the MIT Gentoo mirror and verified against the SHA-512 in Gentoo's
[libebur128 Manifest](https://github.com/gentoo/gentoo/blob/master/media-libs/libebur128/Manifest).
The runner checks this digest before evaluation and records every input's SHA-256.
No audio is committed; the archive's terms permit technical testing only.

```bash
mkdir -p dogfood/2026-09-29-level-curves
curl -L --fail \
  https://mirrors.mit.edu/gentoo-distfiles/distfiles/de/ebu-loudness-test-setv05.zip \
  -o dogfood/2026-09-29-level-curves/ebu-loudness-test-setv05.zip
uv run python -m zipfile -e dogfood/2026-09-29-level-curves/ebu-loudness-test-setv05.zip \
  dogfood/2026-09-29-level-curves/ebu
uv run python experiments/level-curves/check.py \
  --corpus dogfood/2026-09-29-level-curves/ebu \
  --archive dogfood/2026-09-29-level-curves/ebu-loudness-test-setv05.zip \
  --out experiments/level-curves/report.json
uv run --extra librosa pytest tests/test_level_curves.py tests/test_analysis.py -q
```

## Real CLI use

[`cli-report.json`](cli-report.json) records all five commands on the existing full-song
dogfood mix, including its hash, output sizes and LRA. Raw JSON/provenance records are kept
in ignored `dogfood/2026-09-29-level-curves/cli/`. The CLI smoke test verifies execution and
saved-result readback, not whether any particular mix decision improves the music.
