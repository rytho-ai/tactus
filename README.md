# Tactus

Tactus is the active, general-purpose Python-first music production framework, formerly
`tactus-code`.
Python production source, declared materials, and dependency locks own creative intent;
Git records accepted changes. The runtime renders and verifies the resulting audio.
Agents own musical decisions and listening judgment, using their own tools such as Phonon or an
audio model when useful. Tactus owns the production mechanics that make outputs comparable and
traceable; it does not require a DAW-style authoring schema or a built-in musical judge.

For implementation decisions, start with the
[product positioning and principles](docs/positioning.md):
the self-contained, current product and design constraints.
The [current design](docs/design.md) records chosen approaches, their reasons, and undecided
interfaces; it includes directions that are not yet implemented.
The supported commands below and the checked-in examples describe delivered behavior.

The previous implementation is preserved in
[tactus-daw](https://github.com/rytho-ai/tactus-daw) as a reference for tested mechanisms.
This product succession does not imply API compatibility or feature parity. The reference
implementation now installs as `tactus-daw`, imports as `tactus_daw`, and runs as `tactus-daw`.

The default scientific stack includes NumPy, SciPy and SoundFile;
Pedalboard, pytimestretch, pyqmdsp and Mido are installed as well. Production source can use
these packages directly. Librosa is available through the optional `tactus[librosa]` extra; default installs
do not include it and built-in analyses do not call it. Productions can opt in with
`uv add "tactus[librosa]"`. Pyloudnorm is not a
Tactus dependency, including development groups or extras; loudness regression tests
use [frozen independent answers](tests/fixtures/README.md) and EBU checks. `tactus.analysis` exposes level, spectral, beat/onset and feature analyses;
estimated beats and tempo remain observations for the author to evaluate.

## Current status

Functional `render()` productions can now run through a shared Python/CLI entry without a
required BPM, track model or arrangement. Each run saves original arrays, named PCM24 WAVs,
a manifest and an execution receipt. See [functional examples and contract](examples/functional/README.md).
The interface is an initial offline mono/stereo delivery boundary, not a universal work model.

The [real-source chop-flip study](examples/real-chop-flip/README.md) exercises sampling,
pitch-preserving stretch, authored drums/bass, local effects and a parameter comparison.
Production code owns its input identities and musical choices. The runner owns validated
content-addressed WAV delivery and execution records.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are recommended:

```bash
uv sync --group dev
uv run tactus --version
uv run tactus doctor
uv run pytest
uv run ruff check .
```

Default development adds pytest/Ruff; librosa is optional and pyloudnorm is removed.
Numba remains a runtime dependency for accelerated DSP.
Individual external-reference comparisons skip with an installation hint when their
reference package is absent; independent math, edge-case and CLI tests still run.
Run the reference comparisons explicitly, or include them with the full suite:

```bash
uv run --extra librosa pytest -m reference
uv run --extra librosa pytest
```

`uv sync --group dev` removes packages left by an earlier reference run; `uv run`
alone can retain extra packages. The optional references remain pinned in `uv.lock`.

## Install the CLI once

Install a fixed Git revision (replace `FULL_COMMIT` with the chosen commit SHA):

```bash
uv tool install --python 3.12 "tactus @ git+https://github.com/rytho-ai/tactus.git@FULL_COMMIT"
tactus init my-work
cd my-work
tactus doctor
```

`init` pins that same revision in the new work. To develop Tactus itself, install the
checkout with `uv tool install --python 3.12 --editable .` and create a work with
`tactus init my-work --tactus-path "$PWD"`. Use `--force` when replacing an existing tool install.

Use `tactus ...` directly inside the work. The launcher selects its locked uv environment;
`uv add PACKAGE` adds work-specific dependencies. For portable works, pin a published
revision with `tactus init DIR --tactus URL@REV`. See the
[project command contract](docs/project-commands.md) for environment selection.

### Optional librosa installation

Librosa is **not a default dependency**. Explicitly opt in when needed:

```bash
# Install the global CLI with librosa (use an existing commit that includes this extra):
uv tool install --python 3.12 "tactus[librosa] @ git+https://github.com/rytho-ai/tactus.git@FULL_COMMIT"
# Within a work, add the extra to that work's own environment:
uv add "tactus[librosa]"
# Within this checkout:
uv sync --extra librosa
```

A global tool's extra does not automatically carry into a work's separate environment;
select it in the work if its Python code needs librosa. The extra installs the library
for ordinary Python use and optional reference tests; it adds no built-in CLI analysis
and does not change existing algorithms. `uv sync` without the extra removes it from
this checkout's environment. Pyloudnorm is not installed by either choice.

## Functional production entry

```python
import numpy as np


def render(*, gain=0.2):
    rate = 48_000
    t = np.arange(rate) / rate
    return {
        "sample_rate": rate,
        "outputs": {"clip": gain * np.sin(2 * np.pi * 220 * t)},
    }
```

Use the included modular production or clip bank:

```bash
tactus run examples/functional/song.py --out /tmp/tactus-take-a
tactus run examples/functional/song.py --out /tmp/tactus-take-b \
  --params '{"bass_gain": 0.4}'
tactus run examples/functional/clips.py --out /tmp/tactus-clips
```

Each destination must be new. The command returns one JSON result containing playable WAV
paths, a manifest and a receipt; author logs go to stderr. `from tactus import run` exposes
the same operation as `run(source, out=..., params={...})`, raising `RunError` on failure.
Runs execute in fresh processes, with relative imports/assets resolved from the source directory.
Parameter overrides do not edit source; accepting a candidate currently means an explicit
source edit. No output name, mix, common duration or musical grouping is required.

The [entry contract](examples/functional/README.md) describes parameter/output validation,
failure behavior and attribution limits. Receipts record effective parameters, a bounded
source inventory, the nearest `uv.lock`, pinned input materials resolved with `material()`,
tools declared with `tool()`, and imported package versions. Undeclared files and executables
are not traced. Import input files once with `tactus material add FILE...` and paste the
printed `sha256:` refs into source.
Saved WAVs are replayable, but arbitrary source rebuilds are not guaranteed deterministic.
To hear part of a run, `tactus excerpt RUN_DIR --range START:END --out NEW_DIR` cuts it from the
saved audio without rendering again. Accepting a candidate is a source edit committed with Git.

## Your analysis and delivery commands

Keep custom Python in the work and register it in `pyproject.toml`:

```toml
[tool.tactus.analysis]
"stereo.width" = "measurements:width"

[tool.tactus.export]
"my-delivery" = "delivery:bundle"
```

```bash
tactus analyze stereo width mix.wav --window-ms 100
tactus export my-delivery runs/a --out delivery/label
tactus export wav runs/a --subtype DOUBLE --out delivery/original
tactus export stems runs/a --out delivery/stems
```

`run` saves original audio before its default audition delivery. `export` creates another
format from that saved render, including after an encoding failure, without regenerating
instruments. Built-ins are `wav`, `flac`, and `stems`; custom functions use the same parameter,
result and provenance machinery. Original arrays cost additional storage alongside audition
WAVs. See the [runnable example](examples/project-commands/README.md) and
[function contracts](docs/project-commands.md).

## Preserve an instrument performance

Use original VST3/SFZ instruments. When a performance should stay fixed, have `render()`
return its raw array in an optional `takes` mapping alongside the usual audition outputs:

```python
def render(*, gain=0.25):
    raw = synthesize()  # your generator, called once for this candidate
    return {"sample_rate": 44100, "outputs": {"mix": raw * gain}, "takes": {"pad": raw}}
```

After listening to that run, save the selected take:

```bash
tactus take save runs/take-a pad
```

Paste its printed ref into the work and use `load_take` before further processing:

```python
from tactus import load_take

PAD_TAKE = "tree:sha256:…"


def render(*, gain=0.25):
    raw = load_take(PAD_TAKE, sample_rate=44100)
    return {"sample_rate": 44100, "outputs": {"mix": raw * gain}}
```

Takes preserve the original samples, dtype, shape and headroom, with a source snapshot and
receipt. They live in the material pool independently of stage cache and run directories.
Changing MIDI or a patch means generating and selecting a new take; old refs remain usable.
Playback needs no generator instrument. Gain, effects and placement remain editable in code.

To move a take, use `tactus take export REF --out take-bundle`, copy the folder, then run
`tactus material add take-bundle` on the destination machine. It returns the same ref.
Also transfer the work's source/lock and other required materials. See
[Saved takes](skills/tactus-authoring/reference.md#saved-takes) for the full lifecycle and
provenance limits.

## Supported surface

The CLI provides `init` (with `--tactus-path`/`--tactus`), `run` (with `--reuse`), `excerpt`,
`analyze CATEGORY NAME` (categories `level`, `spectral` and `rhythm`; `tactus analyze --help` lists
categories, `tactus analyze CATEGORY --help` lists analyses, `tactus analyze CATEGORY NAME
--help` gives parameters and definitions), `export NAME`, `material add`, `take save`, `take export`, `doctor`, help and version.
The public Python exports are `run`, `excerpt`, `RunError`, `AudioRef`, `material`, `tool`,
`load_audio`, `load_take`, `MaterialError`, `ToolError`, `stage`, the `fx` module, the `timing` module and
the `analysis` module.
Agents writing a work should use the [`tactus-authoring` skill](skills/tactus-authoring/SKILL.md)
(high-level rules; details in its [`reference.md`](skills/tactus-authoring/reference.md)). The
production function is named `render()`; execute it
through `tactus run`. Read the returned paths and manifest/receipt directly, and play the WAVs
with your audio tools.

The earlier Project/Track arrangement prototype and its build/render/inspect/diff commands
have been removed. There are no compatibility aliases or arrangement-format loaders.
The distribution, Python import, and command are all `tactus` (version `0.1.0`).

### Beat analysis

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
The [integration check](experiments/pyqmdsp-integration/README.md) records corpus parity
and its accuracy limits.

### Level curves and loudness range

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
response differences. See [definitions and EBU verification](experiments/level-curves/README.md).

### Onsets and feature arrays

Built-ins are an optional toolbox. Use the provided functions, call other libraries directly,
or register your own [analysis commands](docs/project-commands.md). Owned NumPy/SciPy analyses include:

| Command after `tactus analyze` | Result |
| --- | --- |
| `rhythm onset_strength` | `times_s`, `strength`: Mel or log-frequency SuperFlux onset-strength curve |
| `rhythm onsets` | `onsets_s`: candidate onset times; configurable threshold/spacing/backtracking |
| `spectral mel` | `power`: Mel power matrix, with `times_s` and filter-center `freqs_hz` |
| `spectral chroma` | `chroma`: 12 pitch-class rows, C through B, plus `times_s` and `pitch_classes` |
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
[reference, accuracy and performance checks](experiments/superflux-frontends/README.md).

#### STFT, Mel spectrogram, CQT, VQT, tempogram and images

These built-ins use owned NumPy/SciPy implementations and require no librosa:

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
bin limits are listed in `--help`. There is no tuning estimation, inverse or phase API.

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
See [verification and acceleration evidence](experiments/q-transforms/README.md).


They are candidates, not sample-accurate cut points. `--backtrack` moves them to preceding
strength minima; it changes their meaning and does not guarantee better accuracy.
The [evaluation](experiments/librosa-analysis/README.md) retains the difficult-loop comparison
and timing limitations. Freeze accepted markers before using them in a production.

### Dynamics and spectral distribution

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
mix quality. See [definitions and verification](experiments/analysis-descriptors/README.md).

## Owned DSP

`analysis` reports observations; `dsp` transforms audio. Both are optional: ordinary Python,
custom analysis commands and VST effects remain supported. Built-in calculations use
NumPy/SciPy, with cached Numba kernels for the sequential duck, both delays and automated
lowpass loops; beat tracking and time stretching retain pyqmdsp and pytimestretch.
See [migration and verification](experiments/owned-analysis/README.md).

```python
import numpy as np
from tactus import dsp

# mono is a one-dimensional audio array; sr is its integer sample rate.
x = dsp.gain(mono, -6)  # scalar or per-frame dB
x = dsp.fade(x, sr, in_s=0.01, out_s=0.1)  # linear fades on a complete clip
stereo = dsp.pan(x, np.linspace(-1, 1, len(x)))
filtered, state = dsp.biquad(
    stereo,
    sr,
    kind="lowpass",
    frequency_hz=3000,
)
# Continue the same filter on another block; state is an explicit (2, channels) array.
next_filtered, state = dsp.biquad(
    next_stereo_block,
    sr,
    kind="lowpass",
    frequency_hz=3000,
    state=state,
)
```

- `gain`: scalar or per-frame dB, shared across channels.
- `fade`: linear amplitude fades, including endpoints; overlapping fades multiply.
  Durations must fit the clip. It operates on a whole clip, not a streaming fade state.
- `pan`: mono to stereo, -1 left / 0 center / +1 right, equal power (-3.01 dB per side
  at center). Stereo balancing is a different operation; this function rejects stereo.
- `biquad`: `lowpass`, `highpass`, `peak`, `low_shelf`, `high_shelf`. Q is positive;
  frequency is between zero and Nyquist. Gain applies to peak/shelves. Uses the Q-based
  [RBJ Cookbook equations](https://www.w3.org/TR/audio-eq-cookbook/).
  Start with `state=None`, carry returned state between blocks, and process zeros for a
  tail. Parameter changes are not smoothed. Whole/block equality assumes fixed parameters.
- Existing `varispeed` and `fit_rms` are also exposed through `dsp`; `tactus.fx` imports and
  plugin helpers continue to work with their existing contracts.

Reusable whole-clip effects also use ordinary arrays:

- `duck(audio, detector, sample_rate, *, threshold_db=-18, ratio=4, attack_ms=5,
  release_ms=100, return_gain=False)`: external peak detector, hard-knee compression,
  no makeup gain or lookahead. Detector and audio must have equal frame counts;
  multichannel detection takes the maximum absolute channel value and applies one gain
  to every audio channel. Attack/release are linear-amplitude envelope time constants;
  zero means immediate. `return_gain=True` returns `(audio, per_frame_linear_gain)` for
  reuse on other signals. Ratio must be at least one.
- `delay(audio, sample_rate, *, delay_seconds=0.15, feedback=0.35, tail_seconds=0)`:
  wet-only fractional feedback delay. Delay accepts scalar or per-input-frame seconds,
  at least one sample; feedback is strictly between -1 and 1. Output appends
  `round(tail_seconds * sample_rate)` frames, holding the last delay value through the
  tail. Moving delay time changes pitch. Add dry audio explicitly when mixing.
- `crossfade_delay(audio, sample_rate, *, delay_seconds=0.15, feedback=0.35,
  tail_seconds=0, crossfade_seconds=0.05)`: the same wet-only layout, feedback range,
  minimum delay and explicit tail convention, using two fixed fractional readheads.
  Both start at the first requested delay. A changed target starts a linear crossfade
  of `round(crossfade_seconds * sample_rate)` samples, which must be at least one.
  Its first sample uses new-head weight `1/N`, and its last uses weight 1. Head positions
  remain fixed during the transition; the latest request is considered on the following
  sample, so intermediate requests can be skipped. The blended wet signal feeds the
  feedback path. This avoids a moving-head pitch glide but can create interference,
  cancellation and amplitude changes; a one-sample transition can click. It adopts the
  Faust probe's dual-head principle with explicit fractional taps and startup semantics,
  rather than promising identical samples to Faust `sdelay`.
- `crossover(audio, sample_rate, *, cutoff_hz=1000)`: returns `(low, high)` from a
  two-way fourth-order Linkwitz–Riley crossover. Scalar cutoff must be strictly between
  zero and Nyquist. Each branch cascades two second-order Butterworth sections. Outputs
  retain input shape/length and are about -6.02 dB at cutoff. Their unprocessed sum has
  flat magnitude response but changes phase; it is not sample-identical to the input.
  Each branch may be processed separately before adding them back together.
- `lowpass(audio, sample_rate, *, cutoff_hz=1000, q=1/sqrt(2))`: two-pole lowpass,
  scalar or per-frame cutoff strictly between zero and Nyquist, positive scalar Q.
  Scalar cutoff uses biquad; varying cutoff uses a topology-preserving state-variable
  filter. Controls are not automatically smoothed.
- `saturate(audio, sample_rate, *, drive_db=12, mix=0.5, oversample=8)`:
  wet transfer `tanh(audio * 10**(drive_db/20))`, with scalar/per-frame drive and linear
  dry/wet mix in `[0, 1]`. Polyphase oversampling accepts 1, 2, 4, 8 or 16; 1 disables
  antialias filtering. Higher factors reduce aliasing, without a universal elimination
  guarantee. Gain is interpolated at the oversampled rate; mix applies at the original
  rate. Length/alignment are retained and mix=0 is an exact copy of the dry input.

These effects reset on each call. Process complete clips, including explicit delay
tails; separate calls are not equivalent to streaming one continuous signal. Saturation
resampling pads clip edges with zeros. For fixed-filter streaming, use `biquad` state.
See the runnable [DSP effects production](examples/dsp-effects/README.md).
The [band processing and delay comparison](examples/dsp-components/README.md) uses
`crossover` and `crossfade_delay` alongside the existing effects.

Numba acceleration is automatic and keeps the same public API. The first call for a
new kernel signature compiles code; later processes can load its on-disk cache. First
use therefore costs more than repeated processing. Fixed-cutoff filtering and saturation
continue to use NumPy/SciPy. No fast-math transformations are enabled in the DSP kernels.

Owned DSP functions allocate float64 output and do not mutate input or caller state.
They do not clip or normalize output automatically; saturation deliberately shapes
amplitude. Empty arrays are supported. Audio uses `(frames,)` or `(frames, channels)`.
Use these functions inside `render()`; no separate DSP CLI or mandatory processor chain is needed.

## Working hypothesis

- People and agents edit Python source, declared assets, and dependency locks; Git versions them.
- Generated audio and execution records are derived artifacts, not a second editable project.
- The runtime should make production outputs inspectable and reproducible without dictating every
  musical algorithm.
- NumPy DSP, external tools, and specialized production code should remain usable as ordinary
  source, subject to an explicit execution and materialization boundary.

Ordinary Python can use the installed DSP/analysis libraries, optional timing helpers,
and opt-in stage reuse. Broader Pattern APIs and built-in MIDI delivery remain directions
to revisit when concrete production needs justify them; custom export can already implement
work-specific delivery. See the [command contract](docs/project-commands.md).
