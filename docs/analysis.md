# Audio analysis

Tactus analyses report observations for a chosen signal. Use the CLI for saved audio and
Python functions for arrays; the author decides how the results affect the work.
Discover categories with `tactus analyze --help`, then use category/command `--help` for
available analyses, parameters and exact definitions in the installed version.

- [Data schema](#data-schema)
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

## Data schema

Every builtin returns an additional `schema` object. In Python it is `result["schema"]`;
in CLI JSON it is `report["result"]["schema"]`, including with `--brief`. It describes
the data rather than how to draw it. Existing fields, parameter defaults, arrays and
numeric analysis revisions stay unchanged. `image(result)` and `--image` remain available.
Project-defined analyses can use the same public helpers below. They are not annotated
automatically: absent declarations are unknown.

For example:

```python
from tactus.analysis import level

result = level.rms_curve(audio, sample_rate, window_s=0.02)
field = result["schema"]["fields"]["rms_dbfs"]
times = result[field["x"]["key"]]
values = result["rms_dbfs"]
# Each value measures [times[i] - field["x"]["width"], times[i]).
# width is window_samples / sample_rate, after sample rounding.
```

At 48 kHz the field description is:

```json
{
  "shape": "series",
  "x": {
    "key": "times_s", "quantity": "time", "unit": "s", "spacing": "linear",
    "origin": "input_start", "at": "end", "width": 0.02,
    "hop": 0.01, "padding": "none", "end_exclusive": true
  },
  "y": {
    "quantity": "rms", "unit": "dBFS",
    "special_values": [{"python": "null", "json": "null", "meaning": "zero_energy"}]
  }
}
```

### Declare and consume custom data

`from tactus.analysis import schema` provides the same constructors used by builtins.
Field names and quantities belong to the analysis, with no builtin-name registry or
dependency on a downstream tool. For example, a work-local waveform analysis:

```python
import numpy as np
from tactus.analysis import schema

def waveform(audio, sample_rate):
    # Explicit channel policy: average channels for this particular observation.
    samples = audio if audio.ndim == 1 else audio.mean(axis=1)
    return schema.attach(
        {"clock": np.arange(len(samples)) / sample_rate, "samples": samples},
        sample_rate=sample_rate,
        frames=len(samples),
        coordinate_keys=["clock"],
        fields={
            "samples": schema.series(
                schema.axis("clock", quantity="time", unit="s", spacing="linear",
                            origin="input_start", at="point"),
                schema.value("sample_amplitude", "FS"),
            )
        },
    )

result = waveform(audio, sample_rate)
times = schema.coordinates(result, "samples")
schema.validate(result)
```

Register this normal Python function as a work-local analysis to use it through the
CLI; its NumPy arrays require `--out`. This declares waveform data; it does not add a
waveform renderer to `image()`.

| Helper | Behavior |
| --- | --- |
| `axis(key=None, quantity=None, unit=None, spacing=None, **extra)` | Select a root/record key, inline `values` or row `column`; omitted semantics remain undeclared |
| `value(quantity, unit, **extra)` | Describe values; `sentinel`, `meaning` and `array=True` can declare Python/JSON/NPZ encodings |
| `series(x, y, **extra)` | A coordinate vector with value semantics; structured layouts also select the y values |
| `grid(x, y, value, dimensions=("y", "x"))` | A matrix with declared axis order; `("x", "y")` is also supported |
| `events(x, **extra)` | Points or spans, optionally with record/row attributes |
| `summary(quantity, unit, **extra)` | A scalar without an axis |
| `attach(result, *, sample_rate, frames, fields, coordinate_keys=(), parameter_keys=(), auxiliary_keys=())` | Classify existing keys, attach fresh finite-JSON metadata and validate; return a shallow result copy |
| `validate(result)` | Check declarations against in-memory data; return None or raise ValueError naming the failing field |
| `coordinates(result, field, axis="x")` | Resolve declared selectors and factors into an independent NumPy vector; grid axes may be x or y |

Constructors return ordinary dictionaries. Handwritten declarations use the same contract;
unknown properties can be omitted. `attach` shares existing arrays and values without
modifying them, copies metadata, and replaces an existing schema only in the returned
result. When deriving new values or coordinates, redeclare their semantics explicitly.

Validation checks finite-JSON metadata, version, disjoint/exhaustive field roles,
selectors, matrix order, coordinate lengths, numeric coordinates and declared window
support. It does not prove the algorithm, physical units, timestamp alignment,
normalization or sentinel meanings are correct. Independent numeric tests still matter.
It does not impose a musical verdict or make schemas mandatory for legacy custom analyses.

These helpers operate on Python results. For CLI JSON containing NPZ references, load
the required arrays first and replace their references with the arrays before validating
or resolving coordinates. The helpers never open paths, infer undeclared coordinates,
map project positions, resample data or reconcile units between analyses. Other tools
can consume the plain JSON declaration without adopting the Python helpers.

### Structure and selectors

`schema.version` is `1`, independent of the analysis's numeric `revision`. Consumers
should check the schema version and treat omitted properties as undeclared. No guessing
from array length, field names or another analysis's conventions is necessary.

| Schema member | Meaning |
| --- | --- |
| `input` | Original input `sample_rate`, `frames` and `time_origin: "input_start"`; duration is frames/rate, excluding analysis padding |
| `fields` | Map from existing result key to a data description; enumerate this map to discover measurements |
| `coordinate_keys` | Existing top-level coordinate arrays used by the measurements, including alternative lag coordinates |
| `parameter_keys` | Existing top-level resolved calculation settings, such as `window_samples`, `hop_samples` and `gamma_hz` |
| `auxiliary_keys` | Existing structural metadata, currently STFT's `shape` |

These roles partition the old top-level result fields. Legacy settings remain in their
original locations for compatibility; they are not additional series. CLI `params`
continues to record requested arguments, separately from these resolved settings.

Descriptions have one of four shapes:

- `series`: `x` coordinates and `y` value semantics. With no `layout`, values are in the
  field's result array/list, and coordinate `key` selects another top-level result key.
- `grid`: `x`, `y` and `value`, with explicit `dimensions: ["y", "x"]` for current
  matrices. The field's numeric matrix keeps its full original resolution.
- `events`: `x` gives event points or starts and durations. An empty list is no detected
  events, not an invented time coordinate.
- `summary`: `value` describes a scalar over the analyzed input, without a plotting axis.

An axis supplies `quantity`, `unit` and either `key` or inline `values`. Inline values
are used for MFCC coefficient indices and the starts of beat intervals. `spacing`
describes the **coordinate sequence**, not a requested display scale: `linear` is
arithmetic spacing, `logarithmic` is geometric spacing, `nonuniform` makes no equal-spacing
claim, and `categorical` preserves label order. Read actual coordinates even for a
regular sequence. A renderer may choose its own linear/log/index presentation.

Structured legacy fields keep their layouts:

- `layout: "records"`: `key` selectors refer to members of each record. `spectral.peaks`
  uses `freq_hz` and `level_db`, ordered by descending level rather than frequency.
  `band_levels` uses `low_hz` and `end_key: "high_hz"`; `attributes.share_db` describes
  the additional measurement. Its `interval` declares right-open bands except the last.
- `layout: "rows"`: `column` is a zero-based tuple/list column. Clipping events retain
  `[channel, start_frame, length]`; `x.factor` converts the start column to seconds,
  and `x.width` independently selects/scales the length column. Attributes identify the
  zero-based channel. The list retains its existing maximum of ten reported positions.

### Time support, units and special values

Time axes use seconds relative to **this input's start**, with `at` equal to `centre`,
`start`, `end` or `point`. A scalar `width` is seconds; a list supplies one width per
time value, except `width_axis: "y"` denotes one width per grid row (CQT/VQT). Clipping's
row selector form is described above. `hop` is the analysis grid step in seconds, not
the distance between detected events. Window-end boundaries are exclusive. Padding,
where declared, describes the windowing stage, not all prior filtering support.

Centered timestamps denote the algorithm's frame center. Discrete windows can have
odd lengths, and Q filters have different lengths by frequency. Do not reinterpret
them as arbitrary exact crop boundaries. STFT may include a padded last frame past
the input duration; centered feature frames can also require audio outside the input,
filled by zeros. Use actual input frames when slicing audio.
Legacy centroid allows SciPy to shorten the window on short inputs while keeping its
requested overlap; its declared width and hop reflect that effective grid.

Onset strength declares **points on the compensated envelope grid**, not centers of a
single analysis window. Its `alignment` records the centered Hann frontend window,
the delay in frames and the difference lag. A plotted point is not sample-accurate
evidence of an onset. Tempogram widths describe windows over that envelope.

Value descriptors use `quantity` and `unit`; optional `range`, `normalization` and
`silence` clarify bounded features and defined silent values. `unit: "1"` means
dimensionless. Feature units are not calibrated dBFS. Chroma's 0–1 normalization is
per-frame maximum; tempogram uses zero-lag energy.

`special_values` records sentinel **encodings and meanings**. Encoding names are strings:
`"null"` means Python None or JSON null, `"NaN"` means NaN, and `"-inf"` means negative
infinity. A zero-energy level of -inf is different from an undefined pitch/frequency or
an unavailable estimate, even when both serialize as JSON null. `python` describes the
direct result; `json` describes inline CLI values. `npz`, when supplied, describes array
attachments, which preserve nonfinite floats. Do not apply the inline JSON rule to NPZ.
An empty `special_values` list declares no special sentinel; zero can be a valid value.

The schema contains finite JSON and no input paths, hashes, run offsets or inferred
musical position. CLI `path`, `input_sha256`, `analysis`, `params` and provenance retain
input identity. For excerpt input, time zero is the excerpt's start: follow the
existing manifest chain and actual start frames to map back to a render. A bare Python
array does not establish file identity. No original-song or bar mapping is inferred.

### Builtin declaration audit

The declarations are checked against the computation and serialization in
[schema tests](../tests/test_analysis_schema.py), alongside existing numeric tests.

| Analysis | Shape and coordinates | Value/silence contract |
| --- | --- | --- |
| `level.loudness` | Summary | LUFS; null for silence or insufficient gated audio |
| `level.rms`, `sample_peak`, `true_peak` | Summary | dBFS/dBTP; -inf for zero energy, JSON null |
| `level.crest_factor` | Summary | dB ratio; null for zero energy |
| `level.momentary_loudness`, `short_term_loudness` | Series, window ends; resolved window_samples/rate | LUFS; null for zero energy; only complete windows |
| `level.rms_curve`, `peak_curve`, `crest_factor_curve` | Series, window ends; resolved window_samples/rate | dBFS or dB; null for zero energy; only complete windows |
| `level.loudness_range` | Summaries, no curve axis | LU/LUFS plus block count, original duration and provisional flag; unavailable levels null |
| `level.clipping` | Event spans with sample-to-second selectors, plus count/length summaries | Per-channel flat-top runs; no waveform or audible-clipping verdict |
| `spectral.spectrum` | Series, linear FFT frequency coordinates; entire input | dB re full-scale sine; -inf becomes inline JSON null |
| `spectral.band_levels` | Record series over frequency intervals | dB re full-scale sine and dB share; zero energy/empty bands -inf |
| `spectral.peaks` | Record series of frequency/level pairs, descending level | dB re full-scale sine; empty list when no peaks |
| `spectral.centroid` | Series, centered legacy STFT; separate threshold-crossing summary | Hz; zero power NaN becomes JSON null; crossing absent null |
| `spectral.stft` | Grid [frequency, time], centers, n_fft/rate; last frame may pass input end | dB re full-scale sine; -inf preserved in NPZ |
| `spectral.mel` | Grid [frequency, time], centered n_fft/rate; nonuniform Hz centers | Squared FFT magnitude per Hz; silence zero |
| `spectral.chroma` | Grid [pitch class, time], centered n_fft/rate; categorical C-first rows | Per-frame max-normalized 0–1; silence zero |
| `spectral.mfcc` | Grid [coefficient index, time], centered n_fft/rate | Orthonormal DCT of log-Mel power; silence finite, not missing |
| `spectral.cqt`, `vqt` | Grid [frequency, time], centers; window_samples/rate per row; geometric Hz grid | Amplitude features; silence zero |
| `spectral.tuning` | Summaries | Cents/semitones relative to A440; no qualifying peaks gives null offsets; concentration/count retained |
| `spectral.bandwidth`, `rolloff`, `flatness` | Series, centered n_fft/rate | Hz or dimensionless ratio; zero power null |
| `rhythm.beats` | Beat-point events, interval-start tempo series with per-interval widths, median summary | BPM; fewer than two beats gives null median, empty tempo curve |
| `rhythm.onsets` | Estimated time-point events on envelope grid | Empty list if no estimates; no window-center claim |
| `rhythm.onset_strength` | Series of compensated grid points; frontend/delay/lag declared | Mean positive Mel dB difference or log10(1+magnitude) difference; silence zero |
| `rhythm.tempogram` | Grid [tempo, time], centered window_frames*hop_samples/rate; nonuniform BPM from integer lags | Relative periodicity 0–1; zero-lag normalization; silence zero |

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
