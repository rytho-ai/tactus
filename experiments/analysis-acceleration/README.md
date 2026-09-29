# Adopted spectral acceleration

Tactus keeps the existing analysis definitions, units, frame grids and revisions.
Numba is already a runtime dependency for DSP; this change adds no dependency.

## Dispatch and resource policy

- CQT/VQT: use SciPy's two real decimated FIRs for small workloads. At one billion
  estimated taps (`frame_count * sum(min(window_length, input_length))`), use the
  same centered correlation in a cached Numba kernel, with no fastmath. Packed real
  and imaginary filters must fit in 64 MiB; otherwise keep the per-filter SciPy path.
  There is no frequency-by-frame-by-window tensor or padding to the longest filter.
- Numba uses up to eight threads, respecting a lower existing thread mask. The
  calling thread's mask is restored in a `finally` block, including kernel errors.
  First use compiles; another process can load the disk cache. Short calls do not
  import Numba, including a single-frame call with a huge hop.
- STFT: bound FFT temporaries to chunks of roughly 2**20 frame samples instead of
  allocating full-song intermediate FFT, magnitude and power matrices. Keep SciPy's
  periodic Hann, normalization, odd/even FFT handling and exact timestamp arithmetic.
  The returned matrix still requires memory proportional to the requested result.
- STFT/Mel: use four native FFT workers at 2**20 frame samples. Nondefault enclosing
  `scipy.fft.set_workers(...)` values take precedence; the ordinary value 1 selects
  the automatic policy. No lasting worker setting changes. Mel keeps its bounded
  FFT chunks, two float32 coefficient rounding steps and native sparse projection.

## Candidate evidence

[probe.json](probe.json) records the earlier candidates, on the mono sum of the
149.189-second, 44.1 kHz music recording. Q Numba kernels reproduce the native arrays
exactly on that recording. Four/eight FFT workers improve Mel. JIT Mel projection
is slower than the native projection with four FFT workers, so it was not adopted.
STFT threading alone has inconsistent full-song gains; the adopted STFT path also
bounds temporary allocations. Numba does not replace the existing native FFT.

These are machine-specific observations, not timing assertions or universal speedup
claims. Parallel paths use more CPU cores. No approximations, resampling, fastmath,
or altered analysis definitions were introduced.

## Shipped-path measurements

[report.json](report.json): separate processes on the original stereo recording,
using its first 149 seconds at 44.1 kHz; ordinary channel summing and validation
are included. Three warm trials per path. Every native/automatic matrix is exactly
equal on both the one-second and long cases (maximum absolute error zero).

| Analysis | Native warm | Automatic warm | Speedup | Automatic first call, fresh cache | Cached first call |
| --- | ---: | ---: | ---: | ---: | ---: |
| CQT | 4.979 s | 2.086 s | 2.39x | 2.595 s | 2.087 s |
| VQT | 2.264 s | 0.395 s | 5.72x | 0.895 s | 0.518 s |
| STFT | 1.166 s | 0.263 s | 4.43x | 0.267 s | 0.297 s |
| Mel | 0.450 s | 0.256 s | 1.75x | 0.296 s | 0.453 s |

The STFT improvement includes bounded allocation, not just threading. Mel's separate
cached-process call is slower than its warm trials: these small timings vary, and
we do not claim a consistent end-to-end CLI speedup for Mel. Q's cached full-process
times (including scientific imports, source decoding, output saving and shutdown)
are 2.724 s and 1.141 s. One-second calls do not load Numba or start parallel FFTs;
small timing differences there reflect ordinary process/measurement variation.

## Verification results

- Full default suite: **1089 passed, 54 skipped** (53 optional reference cases and
  one existing opt-in case). The test oracle's expected silence log warning was
  subsequently suppressed; the focused acceleration tests were rerun.
- Isolated optional librosa environment against current source: **53 passed**.
- Four full-song CLI commands: numeric arrays equal direct Python calls, SVGs equal
  the shared renderer and all artifact hashes verified; see
  [CLI verification](cli-verification.json).
- Ruff check/format and `git diff --check` pass. Blueprints remain local and untracked.

## Verification and reproduction

Run with a representative WAV; the checked recording is not distributed here:

```bash
uv run experiments/analysis-acceleration/probe.py --out dogfood/analysis-probe.json
uv run experiments/analysis-acceleration/verify.py /path/to/music.wav --out dogfood/analysis-timing
uv run experiments/analysis-acceleration/cli_check.py /path/to/music.wav --out dogfood/analysis-cli
uv run pytest tests/test_analysis_acceleration.py tests/test_q_transforms.py tests/test_analysis.py tests/test_analysis_features.py tests/test_analysis_images.py
uv run --extra librosa pytest -m reference
```

`probe.py` uses the original local music path. `verify.py` accepts another recording;
its long case uses up to 149 seconds, and the short case uses one second. It creates
fresh temporary JIT caches, compares native and auto arrays, and measures three warm
trials plus a separate cached process. First-call timings exclude scientific-stack
imports and decoding but include lazy Numba import/compilation or cache loading.
`process_s` includes startup, decoding the source, all measured calls and saving the
matrix; native/first phases include three additional warm calls. The separately
reported `startup_process_estimate_s` subtracts the measured warm calls; it is an
estimate. Cached processes make one call, so their process times are measured directly.

Independent direct-sum tests exercise both Q backends at multiple rates, gammas,
short lengths and hops. STFT tests compare every matrix value and axis against
SciPy, including odd FFTs and no overlap. Mel compares serial/parallel matrices and
retains optional librosa reference checks. Other regressions cover memory fallback,
thread-mask restoration on failure, strided/stereo inputs and CLI image/data hashes.
