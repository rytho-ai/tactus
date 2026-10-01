# Audio analysis

Tactus analyses report observations for a chosen signal. Use the CLI for saved audio and
Python functions for arrays; the author decides how the results affect the work.
Discover categories with `tactus analyze --help`, then use category/command `--help` for
available analyses, parameters and exact definitions in the installed version.

- [Beat analysis](#beat-analysis)
- [Level curves and loudness range](#level-curves-and-loudness-range)
- [Onsets and feature arrays](#onsets-and-feature-arrays)
- [Spectrograms, Q transforms, tempogram and images](#stft-mel-spectrogram-cqt-vqt-tempogram-and-images)
- [Dynamics and spectral distribution](#dynamics-and-spectral-distribution)

Add `--brief` to print only `path`, `output`, `analysis` and `result` when you need the
number and not the parameters and provenance.

To write an analysis or register a work-local command, read the
[measure skill](../skills/measure/SKILL.md) and
[project command contract](../skills/references/project-commands.md#analyze).

## Beat analysis

```bash
tactus analyze rhythm beats loop.wav > beats.json
tactus material add beats.json
```

Each stdout line is one JSON object; its `result` contains `beats_s` (seconds), `bpm` (median tempo), and `tempo_curve`
(BPM between consecutive beats). Python: `from tactus.analysis import rhythm`, then
`rhythm.beats(audio, sample_rate)` with `(frames,)` or `(frames, channels)` audio.
Channels are averaged to mono. Freeze accepted results as source constants or a pinned
material before using them for slicing or alignment inside `render`.

Beat tracking uses [pyqmdsp](https://github.com/openmirlab/pyqmdsp), pinned in the dependency
lock, with no Vamp installation or separate Tactus native build. Source installation needs
a C/C++ toolchain. Short material (roughly 7.45 seconds or less of active audio) or silence
returns empty arrays and `bpm: null`. Beat tracking does not identify meter or downbeats.
The integration was checked against 72 corpus files, with exact CLI/package output parity;
this does not guarantee accuracy on arbitrary music. API regressions live in the
[analysis tests](../tests/test_analysis.py).

## Level curves and loudness range

These optional analyses are implemented in Tactus with NumPy/SciPy. There is no pymixtool
dependency. The existing whole-file `loudness`, `rms`, `sample_peak`, `true_peak` and
`clipping` measurements remain available.

| Command after `tactus analyze level` | Measurement |
| --- | --- |
| `momentary_loudness` | Ungated 400 ms LUFS curve; default 10 ms hop |
| `short_term_loudness` | Ungated 3 s LUFS curve; default 100 ms hop |
| `loudness_range` | Gated short-term loudness spread (LRA), in LU |
| `rms_curve` | Windowed RMS in dBFS; default 50 ms window / 10 ms hop |
| `peak_curve` | Windowed sample peak in dBFS; same default window / hop |

```bash
uv run tactus analyze level momentary_loudness mix.wav --out measurements
uv run tactus analyze level short_term_loudness mix.wav --out measurements
uv run tactus analyze level loudness_range mix.wav
uv run tactus analyze level rms_curve mix.wav --window-s 0.1 --hop-s 0.02
uv run tactus analyze level peak_curve mix.wav
```

Python: `from tactus.analysis import level`, then `level.short_term_loudness(audio, sample_rate)`.
Curves return JSON-ready `times_s` plus `loudness_lufs`, `rms_dbfs` or `sample_peak_dbfs`.
Timestamps mark **window ends**. Only complete windows are measured; short inputs yield
empty curves, zero-energy windows yield null. LUFS sums weighted channel powers, RMS averages
powers and peaks take the maximum; none downmixes stereo before measuring. LUFS supports
1–5 ordered channels (L, R, C, Ls, Rs; no LFE) at integer sample rates of at least 8 kHz.

LRA alone appends 1.5 s silence for file-based measurement. It returns `lra_lu`, its two
percentile levels, gate and block count; inputs under 3 s or without gated blocks return null.
Durations under 60 s are marked `provisional`. Short clips and isolated events can give
misleadingly large LRA; it is not a transient or mix-quality score. New LUFS calculations use
De Man K-weighting; owned integrated LUFS retains the legacy RBJ filter, with small
response differences. See [curve regression tests](../tests/test_level_curves.py) and
[independent reference fixtures](../tests/fixtures/README.md).

## Onsets and feature arrays

Built-ins are an optional toolbox. Use the provided functions, call other libraries directly,
or register your own [analysis commands](project-commands.md). Owned NumPy/SciPy analyses include:

| Command after `tactus analyze` | Result |
| --- | --- |
| `rhythm onset_strength` | `times_s`, `strength`: Mel or log-frequency SuperFlux onset-strength curve |
| `rhythm onsets` | `onsets_s`: candidate onset times; configurable threshold/spacing/backtracking |
| `spectral mel` | `power`: Mel power matrix, with `times_s` and filter-center `freqs_hz` |
| `spectral chroma` | `chroma`: 12 pitch-class rows, C through B, plus `times_s` and `pitch_classes` |
| `spectral tuning` | `offset_cents`, `offset_semitones`, `concentration`, `peaks`: how far the material sits from A440 |
| `spectral mfcc` | `coefficients`: MFCC rows starting at coefficient 0, plus `times_s` |

```bash
uv run tactus analyze rhythm onsets loop.wav --delta 0.07 --out measurements
uv run tactus analyze rhythm onset_strength loop.wav > strength.json
uv run tactus analyze spectral chroma loop.wav --out features
uv run tactus analyze spectral mfcc loop.wav --n-mfcc 13 --out features
uv run tactus analyze spectral mel loop.wav --n-mels 64 --out features
```

Spectral feature matrices require CLI `--out`: each NumPy field becomes a descriptor with
`file`, `key`, `shape`, and `dtype`, pointing into the analysis directory's `arrays.npz`.
Load it with `np.load(descriptor["file"])[descriptor["key"]]`. The adjacent `result.json`
records parameters, provenance and artifact hashes. Python receives arrays directly:

```python
from tactus.analysis import rhythm, spectral

features = spectral.chroma(audio, sample_rate)
matrix = features["chroma"]  # (12, time_frames), usable directly in your code
times = features["times_s"]
candidate_times = rhythm.onsets(audio, sample_rate)["onsets_s"]
```

Spectral features sum channels, following the existing spectral category; rhythm averages
them. Opposite-phase channels can cancel. Matrices use centered zero-padded Hann frames with
features on rows and time on columns. Mel power and MFCC have their own feature units,
not the older spectral measurements' full-scale-sine dB reference. Chroma does not infer
chords or key. Read each command's `--help` for exact definitions, tuning and silence behavior.

Onsets offer **Mel and log-frequency SuperFlux variants**, without NN weights or madmom-infer.
Mel remains the default, preserving existing onset behavior. Select the frontend explicitly:

```bash
uv run tactus analyze rhythm onsets loop.wav --filterbank mel
uv run tactus analyze rhythm onsets loop.wav --filterbank log --bands-per-octave 24
uv run tactus analyze rhythm onset_strength loop.wav --filterbank log
```

```python
mel_events = rhythm.onsets(audio, sample_rate, filterbank="mel")["onsets_s"]
log_events = rhythm.onsets(audio, sample_rate, filterbank="log")["onsets_s"]
```

`n_mels` controls Mel density; `bands_per_octave` controls log density. The other density
parameter is inactive (both must be positive integers). Mel uses Slaney-normalized power
and dB; log uses A440-aligned unit-height triangles, FFT magnitude and `log10(1+x)`.
Log requires `fmin > 0`; FFT-bin rounding can merge requested bands. Only rounded centers
inside the requested frequency bounds survive, and Nyquist is excluded. This is not CQT.
Both use Tactus's centered periodic Hann, integer-hop timing and peak picker, so the log
option is not a claim of complete numerical equivalence to the original SuperFlux program.
Strength units differ between variants; neither is a probability or guaranteed more accurate.
Sparse projection and bounded FFT chunks reduce work and memory; see
[front-end reference checks](../tests/test_superflux_frontends.py).

Onsets are candidates, not sample-accurate cut points. `--backtrack` moves them to preceding
strength minima; it changes their meaning and does not guarantee better accuracy.
Difficult-loop experiments did not establish sample-accurate transient boundaries.
Freeze accepted markers before using them in a production.

## STFT, Mel spectrogram, CQT, VQT, tempogram and images

These built-ins use owned implementations and require no librosa:

| Analysis | Numeric result | Definition |
| --- | --- | --- |
| `spectral stft` | `level_db`, `times_s`, `freqs_hz` | Hann-window STFT on linear frequency bins; dB relative to a full-scale sine |
| `spectral mel` | `power`, `times_s`, `freqs_hz` | Slaney Mel power spectrogram; area-normalized filters, feature units |
| `spectral cqt` | `magnitude`, `times_s`, `freqs_hz`, `window_samples` | Geometric frequency grid with longer Hann windows at lower frequencies |
| `spectral vqt` | Same arrays, plus resolved `gamma_hz` | Positive gamma shortens low-frequency windows; `--gamma 0` equals CQT |
| `rhythm tempogram` | `tempogram`, `times_s`, `bpms`, `lags` | Local autocorrelation of Mel SuperFlux strength, normalized by zero-lag energy |

```bash
uv run tactus analyze spectral stft loop.wav --out analysis --image
uv run tactus analyze spectral mel loop.wav --n-mels 128 --out analysis --image
uv run tactus analyze spectral cqt loop.wav --out analysis --image
uv run tactus analyze spectral vqt loop.wav --gamma 13 --out analysis --image
uv run tactus analyze rhythm tempogram loop.wav --window-s 4 --out analysis --image
# Fix the color range when comparing Q-transform images:
uv run tactus analyze spectral cqt loop.wav --out comparisons --image --image-min -80 --image-max 0
```

CQT/VQT automatically use cached Numba kernels for large workloads (at least one
billion estimated filter taps, with packed filters capped at 64 MiB), using up to
eight threads without fastmath. Short calls retain SciPy FIRs and do not load Numba.
The first accelerated call compiles; later processes can load the disk cache.
STFT bounds FFT temporaries in chunks; STFT and Mel retain native SciPy FFTs,
using four workers for at least 2**20 frame
samples; an enclosing nondefault `scipy.fft.set_workers(...)` setting takes precedence.
Mel keeps sparse native projection. Thread settings are restored after calls; results,
frame conventions and units are preserved. See
[native/accelerated equality checks](../tests/test_analysis_acceleration.py).

`--out` saves the full numeric arrays as NPZ and the analysis/provenance record as JSON.
`--image` additionally saves a standalone labeled `image.svg` (with an embedded PNG
heatmap), covered by the same artifact hashes. The flag also supports existing
chroma and MFCC analyses. It needs no plotting package. Python can use either view:

```python
from pathlib import Path
from tactus.analysis import image, spectral

result = spectral.cqt(audio, sample_rate)
matrix = result["magnitude"]  # (frequency_bins, time_frames)
Path("cqt.svg").write_text(image(result, title="CQT", vmin=-80, vmax=0), encoding="utf-8")

stft = spectral.stft(audio, sample_rate)
levels = stft["level_db"]  # (frequency_bins, time_frames), silence remains -inf
Path("stft.svg").write_text(image(stft, title="STFT"), encoding="utf-8")
mel = spectral.mel(audio, sample_rate, n_mels=128)
power = mel["power"]  # (mel_bands, time_frames)
Path("mel.svg").write_text(image(mel, title="Mel spectrogram"), encoding="utf-8")
```

STFT revision 2 returns arrays directly, replacing its old summary/file-only result and
Python `out=` parameter. The CLI now requires `--out` like the other matrix analyses;
use the JSON array references to locate the NPZ arrays. Existing STFT scaling is retained,
with a fixed FFT grid for short inputs. `shape` is `(frequency_bins, time_frames)`;
`duration_s` describes the original signal, and the last padded frame may extend past it.

Q transforms sum channels, use centered zero padding and default to C1, 84 bins,
12 bins/octave and a 512-sample hop. Their L1-normalized complex filters have gain 2;
a resolved bin-centered real sine reads approximately its peak amplitude. These are
feature magnitudes, not librosa's length-scaled coefficients. VQT defaults to the
ERB-derived gamma and reports it. Filter bands crossing Nyquist are rejected: e.g.
8 kHz audio needs fewer than the default seven octaves (`--n-bins 72`). Window and
bin limits are listed in `--help`. There is no inverse or phase API.

`spectral tuning` reports one offset for the whole signal: the magnitude-weighted circular
mean of how far spectral peaks (150 Hz to 4 kHz, parabolic-interpolated, 8192-point frames)
sit from the nearest A440 equal-tempered semitone. Pass `offset_semitones` to `chroma`'s
`tuning`, or use it to decide a repitch. It is not a pitch, key or chord estimate. On
synthetic chords with known offsets it is within 4 cents, biased a few cents flat because
upper partials sit below the semitone grid; on four 1930s–40s record transfers it was within
7 cents of librosa's `estimate_tuning`. It deliberately does not copy that definition: when the same
records were repitched by known amounts, the circular mean followed the change within a cent,
while a histogram-mode estimate jumped by up to 12 cents. `concentration` runs from about 0.01 for noise to
0.15–0.25 for full-band recordings and above 0.8 for clean harmonic tones: read a low value
as "the offset means little", and compare sections when a transfer may drift.

Tempogram averages channels, uses a 10 ms onset hop and a 4 s autocorrelation window,
then retains positive integer lags corresponding to 30–300 BPM. Rows are ascending
but **not uniformly spaced in BPM**; no prior or single tempo/beat estimate is returned.
Short clips are zero-padded and may not provide useful periodicity evidence.

Images preserve row-index spacing and label exact Hz/BPM centers; only STFT rows are
linear in Hz. STFT displays its existing dB values with a default -80..0 range; silence
uses the lowest color without changing numeric `-inf`. Time reduction averages linear
power before returning to dB. Q images use `20*log10(magnitude)` relative to 1, default -80..0;
Mel uses power dB with an automatic 80 dB range, chroma/tempogram use 0..1, MFCC uses
symmetric coefficient bounds. Display settings live separately from analysis params.
Mel power dB and STFT full-scale-sine dB use different references, so matching their
color bounds does not make their levels interchangeable.
For readability, at most 1200 time columns are averaged before display conversion;
NPZ retains every frame. Image metadata records units, color bounds and display shape.
See [Q-transform checks](../tests/test_q_transforms.py) and
[image output checks](../tests/test_analysis_images.py).

## Dynamics and spectral distribution

Five additional owned NumPy/SciPy analyses describe peak contrast and spectral shape:

| Command after `tactus analyze` | Observation |
| --- | --- |
| `level crest_factor` | Whole-input sample peak / RMS ratio, in dB |
| `level crest_factor_curve` | The same ratio over complete windows (default 50 ms / 10 ms hop) |
| `spectral bandwidth` | Power-weighted standard deviation of frequency, in Hz |
| `spectral rolloff` | First frequency bin reaching a power fraction (default 85%) |
| `spectral flatness` | Geometric/arithmetic mean of spectral power, on a 0–1 scale |

```bash
uv run tactus analyze level crest_factor mix.wav
uv run tactus analyze level crest_factor_curve drums.wav --window-s 0.05 --out measurements
uv run tactus analyze spectral bandwidth mix.wav
uv run tactus analyze spectral rolloff mix.wav --roll-percent 0.95
uv run tactus analyze spectral flatness mix.wav --n-fft 4096 --hop 512
```

Use the same names through `tactus.analysis.level` or `tactus.analysis.spectral` in Python.
These one-dimensional curves return JSON lists; they do not require an NPZ attachment.

Crest factor uses the maximum **sample peak across channels** and RMS averaged across all
samples/channels, without downmixing. It is not true peak minus LUFS (PLR), LRA or a punch
score. Its curve uses window-end timestamps, discards partial windows and depends on the
chosen window size. Silence is null; short inputs yield empty curves.

Spectral descriptors sum channels and use the Mel/MFCC frontend's centered, zero-padded
Hann grid: default `n_fft=2048`, `hop=512`, final center at or before input duration. This is
independent of the legacy centroid's terminal-frame policy. Bandwidth and rolloff use
**power**, not librosa's default magnitude weighting. Flatness includes DC/Nyquist and floors
power at `floor_ratio=1e-12` of each frame's largest bin before both means, so an ordinary
change in gain does not change the descriptor. Uniform spectra approach 1; concentrated
spectra approach 0. Zero-power frames return null for all three. Opposite-phase channels
can cancel. These values describe distributions; they do not identify instruments or grade
mix quality. See [descriptor regression tests](../tests/test_analysis_descriptors.py).
