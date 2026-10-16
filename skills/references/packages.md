# Packages and integration notes

Use this map when choosing tools or connecting their outputs. The work's `uv.lock`, installed
signatures and package documentation own exact versions and APIs. Tactus's builtin source is
also available to inspect, adapt and learn from; choose tools for the work's intended sound.

## Available tools

Installed with the current Tactus runtime:

| Tool | Useful for | Read before connecting it |
|---|---|---|
| `tactus.dsp` | Gain, fades, pan, filters, ducking, delays, saturation and band splitting | [DSP contracts](dsp.md): whole-clip reset versus explicit biquad state; output shape and tails. |
| `tactus.fx` | Plugin parameters, MIDI instrument rendering, block automation, varispeed and RMS fitting | [Helpers](runtime.md#helpers-from-tactus-import-fx) and the MIDI/plugin notes below. |
| `tactus.timing` | Optional clocks, placement, envelopes, groove and rhythmic helpers; `Clock.grid` for a map, `fit_tempo`, `warp_markers` and `fold` to fit a recording to a grid | [Musical time](runtime.md#musical-time-optional): 0-based quarter-note beats, bar numbering and rounding. |
| `tactus.analysis` | Defined level/spectral observations, beat/onset estimates and curves, and `join` measurements at seams and loop wraps | [measure](../measure/SKILL.md); installed `tactus analyze ... --help` supplies definitions. |
| `tactus.synth`, `tactus.devices` | Synthesis blocks and a physical piano model; a sampler, pads and a step sequencer | [Synthesis](synth.md) and [Devices](devices.md). |
| `tactus.timemap` | Checking and converting a render's time map | [The time map](runtime.md#the-time-map-optional): frames of an output, validated at `run`. |
| NumPy | Audio arrays, synthesis, slicing, mixing, modulation and event data | Views can alias their source; preserve caller arrays. Align a per-frame curve with stereo as `curve[:, None]`. |
| SciPy | Filters, resampling, FFT/STFT, interpolation and numerical algorithms | Set the time axis explicitly for frames-first audio. Carry filter state for continuity; zero-phase filtering has different timing from a causal filter. |
| SoundFile (`soundfile`) | Read/write audio files | `sf.read` returns audio and rate, normally mono 1-D or frames-first multichannel; `always_2d=True` makes mono a column. Choose dtype/subtype deliberately; changing metadata alone does not resample. |
| Pedalboard (`pedalboard`) | Native effects and VST3 instrument/effect hosting | Channel layout, reset behavior, tails, plugin availability and parameter scales below. |
| pytimestretch | Pitch-preserving stretch, pitch shift, marker warps and spectral textures | Duration ratio, marker units, engine availability and extreme-stretch behavior below. |
| Mido (`mido`) | MIDI messages and files | MIDI track delta ticks versus absolute render seconds below. It does not synthesize sound. |
| pyqmdsp | QM-DSP beat analysis | Tactus exposes beat tracking through `analysis.rhythm.beats`. Beat estimates are not downbeats or exact transient boundaries. |
| Numba | Compile sequential numerical loops | [DSP acceleration](../dsp/SKILL.md#accelerate-measured-bottlenecks): compilation/cache cost, supported types and measured benefit. |

Other libraries are welcome. Add them with `uv add PACKAGE` in the work so its lock records
them. Librosa is optional via `uv add "tactus[librosa]"`; builtin Tactus analyses do not require
or call it. `uv add "tactus[serve]"` adds FastAPI and uvicorn for [`tactus serve`](serve.md). Pyloudnorm is not installed by Tactus; `uv add pyloudnorm` if your work needs it.
Librosa commonly uses the last axis for time, so inspect its callable before passing
frames-first stereo. Installed Python packages do not imply installed VSTs, SFZ instruments,
sample libraries or external executables: declare those with `material()` or `tool()` as
appropriate. Python package versions are recorded automatically.

Use `tactus doctor` to identify the selected environment. A package in the global CLI's
environment is not necessarily in the work's locked environment. Inspect a callable from
that work with `uv run python`, `help(...)`, `inspect.signature(...)` or `inspect.getsource(...)`.
Private Tactus kernels are references, not stable imports for a portable work.
Native extension callables may lack an inspectable signature: try their installed
`__doc__` or `help()` and a small validated call rather than treating introspection
failure as an unavailable processor. See [production notes](production.md#a-valid-entry-and-processing-notes).

## Writing audio files yourself

`tactus run` and `tactus export` write the work's audio. When your own code writes a float
WAV, `soundfile` (libsndfile) adds a PEAK chunk holding the time of writing, so identical
audio gives different file bytes and hashes on every run. Compare decoded samples, or
write with `scipy.io.wavfile.write(path, rate, array)`, which stores no timestamp.
PCM files from `soundfile` are stable.

## Pedalboard and instrument hosts

- **Layout:** Pedalboard audio effects accept frames-first arrays as used by Tactus, and can
  infer channels-first layout. Pass Tactus audio as it is; transposing it is unnecessary.
  For a whole clip through a built-in effect (Reverb, Chorus, Delay, Compressor) use
  `fx.process(chain, audio, rate, tail_seconds=...)`, which keeps the layout, resets the
  plugin and keeps the tail. Check the returned shape with very short blocks. A direct MIDI instrument call returns channels-first;
  `fx.render_instrument` returns frames-first. Avoid applying one blanket transpose rule to both.
- **State and tails:** create/reset instances for independent candidates. For continuous
  processing, reset explicitly before the stream and use `reset=False` on every audio block;
  `reset=True` makes Pedalboard flush that call as a complete input. Feed silence for the
  tail you want. Use [fx.process_automated](runtime.md#helpers-from-tactus-import-fx) for
  the supported block loop, fixed-latency negotiation and explicit tail.
- **Parameters:** use `fx.describe`/`format_table` before setting a plugin parameter and
  `fx.set_param` for units and supported values. A plugin's 0–100 range is not 0–1. Record
  the value actually set. VST hosting still depends on the particular installed plugin.
- **Performance timing:** read [Helpers](runtime.md#helpers-from-tactus-import-fx) for
  `render_instrument` warmup and its small block size; pitch bend/CC can take effect at
  block boundaries. Check the actual instrument when timing matters.
- **Reproducibility:** some instruments change across renders despite identical MIDI and
  settings. [Saved takes](runtime.md#saved-takes) preserve a selected performance. Temporary
  `@stage` reuse is not a durable performance archive.
- **Clipping:** a limiter or local `np.clip` can flatten peaks before the runner sees them.
  `clipped_samples` counts only returned values outside ±1; zero does not prove the earlier
  signal chain never clipped. Read the processor's behavior and inspect/listen as appropriate.

## Time and pitch engines

`pytimestretch` accepts mono `(frames,)` or frames-first `(frames, channels)` audio. For
`time_stretch`, `duration_ratio = output_duration / input_duration`; 2 makes it twice as long.
Specify the backend and its supported options deliberately. Use `available_backends()` and
the installed docstring to check availability and capability rather than guessing a fallback.

`time_warp` uses strictly increasing integer `(source_frame, output_frame)` markers with
explicit endpoints. Its last source coordinate is `len(audio)`, the exclusive end, not the
last sample's index. Observations in seconds must be converted to frames at the correct rate.
Read [Creative connections](connections.md#analysis-can-become-a-control-signal) when a
source-time envelope must travel through the warp. For tape-like coupled speed/pitch motion,
consider `fx.varispeed` or a local resampler instead of pitch-preserving stretching.

`extreme_stretch` creates a spectral texture: output length is approximate and phase is
randomized. The installed implementation requires at least 81,920 input frames and emits
whole FFT chunks. Do not infer its exact duration from the requested ratio. Earlier local
probes observed repeatability across fresh processes only with unchanged call order; use a
saved take when the exact waveform matters, rather than depending on that implementation detail.

## MIDI time

Mido message `time` has a context-dependent meaning. In a MIDI track it is a delta in ticks;
converting a file requires its tempo events and `ticks_per_beat`. Iterating a `MidiFile`
produces delta seconds, which still need accumulation for absolute event positions.
`fx.render_instrument` expects messages or `(bytes, seconds)` tuples at **absolute seconds**
from this render's start. Choose note ends, pedal release and render duration to include the
performance and release you intend; the helper returns the requested length. Use `mido` to
serialize events for an external SFZ renderer when that is the chosen instrument path.
