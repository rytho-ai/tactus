# Owned CQT, VQT, tempogram and image verification

The public analyses use NumPy/SciPy; librosa is an optional test oracle. DTW is
excluded. The shared image renderer uses NumPy and Python's standard library,
producing a standalone SVG with a PNG heatmap, labeled axes and color bounds.

## Definitions and independent checks

- Q filters: geometric centers; periodic Hann, integer `ceil` lengths,
  `alpha=tanh(log(2)/bins_per_octave)`, length `filter_scale*sr/(alpha*f+gamma)`.
  L1 norm 2, centered zero padding, magnitude output. VQT's default gamma is
  `24.7*alpha/0.108`; gamma=0 exactly equals CQT. Filter bands crossing Nyquist
  are rejected using the documented Hann bandwidth guard. The formula follows
  the [librosa wavelet-length convention](https://librosa.org/doc/0.11.0/generated/librosa.filters.wavelet_lengths.html).
  Optional tests compare lengths, not recursive librosa CQT coefficients.
- `tests/test_q_transforms.py`: every-frame direct complex sums at three sample
  rates, three gammas, multiple hops/short lengths; bin-centered tone amplitude,
  octave index, summed/cancelled channels, invalid inputs, nonmutation and huge
  hop without huge padding. The direct transform has no resampling, frequency
  sparsification, phase output, inverse or tuning estimation.
- Tempogram: centered zero-padded Hann frames over the existing Mel SuperFlux
  envelope; FFT linear autocorrelation divided by zero-lag energy. Positive lags
  form ascending, irregular BPM rows. Direct sample correlations verify both
  boundaries and chunk transitions. Clicks at 60/120/180 BPM locate the expected
  period. Optional [librosa tempogram](https://librosa.org/doc/0.11.0/_modules/librosa/feature/rhythm.html)
  comparison uses explicit zero padding and center=False; upstream's ordinary
  centered mode uses ramp padding, so its edge values are not this contract.
- Image checks decode PNG bytes to verify low/high row orientation, check XML and
  escaped titles, labels, recorded bounds, block-mean reduction, nonmutation and
  silence. Existing Mel/chroma/MFCC adopt the same renderer. CLI tests verify
  numeric arrays exactly, SVG bytes, artifact hashes, saved/stdout record equality,
  no-overwrite behavior, cleanup on invalid bounds and custom `image` parameter
  compatibility. Display settings remain separate from numerical params.

**Not claimed:** bitwise equivalence to librosa CQT/VQT; a single correct tempo;
audio inversion; improved musical quality; general speed superiority to librosa.

## Current verification

See [verification.json](verification.json):

- Default suite: **972 passed, 83 skipped**. Skips are 82 optional external
  comparisons plus one existing opt-in installation test.
- Isolated reference group: **82 passed**, none skipped. Includes all three new
  external-oracle cases. Ordinary independent tests run without those packages.
- Ruff check, Python formatting and wheel/sdist build pass. Wheel implementation
  bytes match the checkout. Repository-wide formatting additionally reports old
  Markdown code-fence formatting in four unrelated documents; those were left alone.
- Actual CLI on 20 seconds of real stereo music: CQT, VQT and tempogram numeric
  roundtrips and all artifact hashes verified. All four preview images load; audio
  plays as a 20-second PCM24 view. The analysis itself uses a DOUBLE WAV excerpt.
- The shared checkout separately gained Numba for DSP during this work. These
  analysis functions still do not import it. No analysis dependency was added;
  the import-guard test explicitly rejects Numba/librosa/pyloudnorm on the Q path.

The real input is the 149.189-second, 44.1 kHz stereo production with SHA256
`32222836141353be4973175d26d2b7c600394d96dc68b89c2cf97362e486e4d1`.
Its 36–56 second excerpt supplies the visual trial; a separate synthetic
60→120 BPM click train checks visible tempo mapping. Large generated files live in
`dogfood/2026-09-29-q-transforms/`. The session preview is served by the existing
port 4187 server at `/q-analysis/`.

## Acceleration experiments

All methods implement the same double-precision Q-filter definition. No fastmath,
resampling or coefficient pruning. Timings include filter construction and output
allocation, medians of three warm trials on this machine; they are observations,
not test thresholds. Multithreaded results explicitly include their extra CPU use.

The adopted implementation uses **two real decimated FIR operations** in place of
one complex FIR: only requested hop samples are computed, without materializing
full-rate complex outputs or a three-dimensional frame/filter tensor. On 5 seconds
of real 44.1 kHz mono sum: 397→257 ms, 1.54×; maximum difference 5.6e-17.
On the full recording, current public calls measured CQT 5.13 s, VQT 2.09 s,
tempogram 0.292 s. These initial full-song timings overlapped the general test run;
use the separate long-JIT report for the later comparison. See [report.json](report.json).

### Same-definition alternatives, 22.05 kHz noise

[acceleration.json](acceleration.json), measured after the general suite completed:

| Method | 1 s input, warm | 30 s input, warm |
| --- | ---: | ---: |
| Complex decimated FIR baseline | 27.4 ms | 587.3 ms |
| **Two real decimated FIRs (adopted)** | **19.7 ms** | **268.9 ms** |
| NumPy bounded direct sums | 22.9 ms | 259.3 ms |
| FFT overlap-add, full-rate output | 47.1 ms | 1334.8 ms |
| Numba, 1 thread | 14.6 ms | 234.9 ms |
| Numba, 4 threads | 12.6 ms | 171.8 ms |
| Numba, 8 threads | 11.0 ms | 108.3 ms |

Every method's maximum absolute error is below 7.3e-16 on these inputs. FFT loses
here because it computes full-rate outputs that the hop-based transform discards.
The small NumPy/FIR difference on 30 seconds is insufficient to add a second backend.
Numba's 8-thread warm speedup is 2.48× over the adopted SciPy path; most of that gain
comes from parallelism, not JIT alone (one thread is only 1.14×).

### Startup matters

Fresh Python processes include imports, filter planning and allocation. Numba uses
four threads in this table. Separate fresh cache directories measure compilation;
subsequent fresh processes measure cached code loading.

| Input | SciPy process | Numba first process | Numba cached process |
| --- | ---: | ---: | ---: |
| 1 s | 0.584 s | 1.162 s | 0.741 s |
| 30 s | 0.835 s | 1.316 s | 0.892 s |

Therefore JIT is **not automatically a CLI improvement**. Numba remains a probe
for these analysis functions; the public CQT/VQT path is SciPy and has no compiler
startup. Tempogram already batches native FFTs. A future JIT adoption should be
motivated by repeated/long analyses and include cache/thread behavior in its contract.

### Full real recording: JIT pays off on long input

[long-jit.json](long-jit.json): same 149.189 s, 44.1 kHz mono sum, measured after
other verification commands finished. Three warm trials per method:

| Method | Warm CQT |
| --- | ---: |
| Adopted SciPy real FIR | 4.924 s |
| Numba 1 thread | 4.021 s |
| Numba 4 threads | 2.822 s |
| Numba 8 threads | 1.891 s |

Eight-thread JIT is **2.60× faster warm**, with maximum absolute difference
5.6e-16. Fresh processes, including decoding and mono summing, take SciPy 5.54 s
versus Numba 3.21 s with first compilation and 2.69 s with cached code (median of
2 subsequent processes). Long inputs amortize compilation/import overhead, unlike
the short CLI cases. This supports future explicit or workload-based acceleration,
not an unconditional claim that JIT is faster for every analysis. These are CQT
measurements; they do not establish equivalent gains for VQT, FFT tempogram or DSP.

## Reproduce

```bash
uv run pytest tests/test_q_transforms.py tests/test_tempogram.py tests/test_analysis_images.py
uv run --extra librosa pytest -m reference
uv run experiments/q-transforms/check.py /path/to/music.wav --out dogfood/q-check-new
uv run experiments/q-transforms/preview.py dogfood/q-check-new/report.json --out dogfood/q-preview
uv run --with numba experiments/q-transforms/acceleration.py --out dogfood/acceleration-new.json
uv run --with numba experiments/q-transforms/long_jit.py /path/to/music.wav --out dogfood/long-jit-new.json
```

Use fresh output/cache directories for startup trials; do not silently reuse the
recorded first-compilation caches. `numba_probe.py` retains the first narrower
experiment separately in [numba-first.json](numba-first.json).
