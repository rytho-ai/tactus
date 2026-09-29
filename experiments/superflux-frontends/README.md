# Mel and log-frequency SuperFlux

Both built-in onset functions accept `filterbank="mel"` (default) or `"log"`.
This batch adds the log frontend and optimizes shared band projection without a new
runtime dependency. There are still 26 analyses, with two onset frontend choices.

```bash
uv run tactus analyze rhythm onsets loop.wav --filterbank mel
uv run tactus analyze rhythm onsets loop.wav --filterbank log --bands-per-octave 24
uv run tactus analyze rhythm onset_strength loop.wav --filterbank log --out measurements
```

## Definitions and compatibility

Both variants average channels, use centered zero-padded periodic Hann frames,
integer `round(hop_s * sample_rate)` hops, the same explicit lag and frequency
maximum filter, and the existing Tactus peak selection/backtracking. Defaults
remain n_fft=1024, hop_s=.005, fmin=27.5, fmax=min(16000, Nyquist), lag=2,
max_size=3, delta=.07 and min_interval_s=.03.

| Frontend | Bands | Spectrum and compression |
| --- | --- | --- |
| Mel | Slaney-area-normalized, `n_mels=138` | Power → relative dB, amin=1e-10, top_db=80 |
| Log | A440-aligned, unit-height, `bands_per_octave=24` | Magnitude → log10(1 + filtered magnitude) |

The unused density parameter has no effect but is still checked as a positive integer.
Log requires fmin>0. Its requested edges round to FFT bins; duplicates merge, Nyquist
is excluded, and only rounded centers inside the requested frequency bounds survive.
No resolvable triangle raises ValueError. It is not a CQT. Log compression is sensitive
to input gain; no input normalization or gain-invariance claim is made.

Strength is the mean positive compressed-band difference: Mel dB and log10-magnitude
units cannot be compared directly. Both are normalized to 0–1 by peak picking.
Result keys and revision 1 remain compatible; CLI params record the selected frontend.

The original [CPJKU SuperFlux reference](https://github.com/CPJKU/SuperFlux/blob/0a85f898af69188324b649a4c640052a5443078e/SuperFlux.py)
provides the log filter construction and magnitude-compression reference. Its framing,
window, fractional hop, precision, aggregation and peak picking differ. This API does
**not** claim full numerical equivalence to that application. Attribution is retained
in `src/tactus/analysis/LICENSE.SuperFlux`, included in the wheel.
The [librosa tutorial](https://librosa.org/doc/latest/auto_tutorials/03-advanced/plot_superflux.html)
explains its Mel substitution for the paper's log-frequency representation.

## Optimization

- Project only nonzero triangular filter coefficients using SciPy sparse matrices.
- Transform and project bounded FFT chunks instead of materializing whole-file power.
- Pad only boundary chunks instead of copying the complete mono waveform.
- Reuse owned log/difference buffers; never mutate the caller's audio or spectrum.
- Keep original Mel float32 coefficient rounding, float64 arithmetic and global dB floor.

Warm timings include the public `onsets` function, validation, downmix, peak picking
and list construction; exclude audio read/imports. Cold timings include `uv run tactus`
startup, reading the file and stdout serialization. Peak RSS is the complete fresh CLI
process reported by `/usr/bin/time`, not just arrays. Seven warm and five fresh trials.
Linux/i5-13600K, Python 3.12, same 149.189 s / 44.1 kHz stereo production and its first 5 s.
Other machine/input combinations are not covered by the speed claim.

| Input / measure | Previous Mel | Optimized Mel | Optimized log |
| --- | ---: | ---: | ---: |
| Full warm onset call | 319.6 ms | 257.9 ms | 250.1 ms |
| Full fresh CLI | 1.545 s | 1.497 s | 1.442 s |
| Full CLI peak RSS | 499.2 MiB | 350.7 MiB | 334.4 MiB |
| 5 s warm onset call | 15.18 ms | 10.54 ms | 10.43 ms |
| 5 s fresh CLI | 1.191 s | 1.137 s | 1.125 s |

Mel saves about 19% warm time and 30% peak RSS on the full input. It meets the
predeclared **20% warm time OR 25% peak RSS** gate through memory reduction. The
small cold-time differences are not presented as a major CLI speedup.

Do not interpret Mel-vs-log timings as optimization gains: they compute different
features. A separate alternating-trial comparison holds log semantics fixed and
substitutes a dense full-matrix projection: full public call 296.3→245.7 ms (~17%
faster); 5 s 16.04→10.76 ms (~33%). Detected events match exactly. That dense path is
a same-contract oracle, not the original SuperFlux application's benchmark.

Raw measurements: `before-*.json`, `after-*.json`, and `report.json`. Initial prototype
measurements were exploratory; the saved final baseline/full trials ran without the
prototype. No Numba/JIT or reduced precision was adopted.

## Correctness and onset accuracy

- 36 original-filter comparisons across 8/22.05/44.1/48 kHz, three FFT sizes and three
  band densities: coefficients match exactly, after the documented range-center mask.
- A 149 s production and nine real-one-shot drum loops: Mel strength matches the
  pinned librosa configuration, including exactly identical ordinary/backtracked
  onset times; log strength matches independent dense FFT/filter/difference math.
- Unit tests cover known triangles, timestamps, low-resolution/custom settings,
  silence/short audio, channel cancellation, noncontiguous input, invalid choices,
  chunk boundaries, quiet tails, buffer nonmutation and CLI saved provenance.
- A sustained synthetic vibrato tone reduces steady-state envelope motion with the
  maximum filter enabled, for both frontends. False onsets remain; this does not
  establish perfect vibrato rejection. Details are in `vibrato_observation`.
- Eight actual CLI combinations (both functions × both frontends × short/full input)
  match Python and saved records, in a work environment with no librosa/pyloudnorm/numba.
  Invalid frontend fails with an explanatory error. See `cli-report.json`.

Macro F1 across the existing nine annotated drum loops:

| Frontend | ±2 ms | ±10 ms | ±25 ms | ±50 ms |
| --- | ---: | ---: | ---: | ---: |
| Mel | .086 | .525 | .818 | .818 |
| Mel + backtracking | .293 | .685 | .808 | .818 |
| Log | .072 | .501 | .827 | .837 |
| Log + backtracking | .198 | .642 | .827 | .837 |

No universal winner: log is slightly higher at wider tolerances, lower at strict ones.
The labels are first 1%-of-peak crossings of recorded one-shots before mixing/effects,
not human-perceptual onset annotations. Neither frontend promises sample-accurate cuts.
The synthetic and nine-loop cases are bounded evidence, not a general music benchmark.

## Repository checks

Full pytest: **866 passed, 1 skipped** in 258.83 s (41 new tests). Repository Ruff,
format checks and build pass. Wheel files match the checked source and include
`LICENSE.SuperFlux`. No new dependency, global reinstall, commit or push.

## Reproduction

Rebuild the corpus using [the existing instructions](../librosa-analysis/README.md).
Save the pinned upstream source from `reference-source.json` to a scratch file. The
checker verifies its SHA-256, executes only the Filter class, and replaces the removed
`np.float` alias with builtin float. No upstream command or peak picker is run.

```bash
uv run --extra librosa python experiments/superflux-frontends/check.py \
  --reference dogfood/2026-09-29-superflux-frontends/SuperFlux.py \
  --corpus dogfood/2026-09-29-librosa-analysis/corpus \
  --audio dogfood/2026-09-25-full-song-3/work/runs/c4/mix-32222836.wav \
  --out dogfood/superflux-check.json

uv run python experiments/superflux-frontends/benchmark.py \
  --audio path/to/audio.wav --filterbank log --out dogfood/log-benchmark.json

uv run python experiments/superflux-frontends/cli_check.py \
  --project path/to/runtime-only-work --audio path/to/audio.wav \
  --work dogfood/superflux-cli-new --out dogfood/superflux-cli-report.json
```

The original production audio is local, not redistributed. Its hash is in report.json;
a replacement file exercises the checker but will not reproduce those performance
numbers. `--work` must not exist. Baseline JSON was captured before this implementation;
rerunning benchmark.py now measures the current implementation.
