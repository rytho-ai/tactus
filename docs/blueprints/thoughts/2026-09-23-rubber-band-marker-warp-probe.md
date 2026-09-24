# Rubber Band marker-warp probe

> 2026-09-23 · Evidence for the pending Tactus time-stretch integration decision, returned to the user. This is a behavior probe, not an engine-quality ranking or a product API decision.

## Question and verdict rule

Can Tactus express DawDreamer-like warp markers without adopting DawDreamer's render engine, using a source-sample to target-sample map through Rubber Band? Before rendering, the probe set a ±20 ms tolerance for each known transient, plus no obvious digital silence at the map boundaries. A separate integration check asked whether `rubband` exposes the same key-frame map. A pass here would establish a usable first path, not perceptual quality or frame-perfect marker placement.

## Method

- Engine: system Rubber Band CLI/library 3.3.0 at 48 kHz; `pyrubberband` 0.4.0. Compare R2 and R3, keeping the same source, key-frame map, and output duration.
- Controlled source: five seconds, stereo. Channel 1 contains isolated Gaussian transients at source times 0.7, 1.6, 2.8, and 4.1 s. Channel 2 is a continuous 220 Hz tone to expose complete dropouts around markers.
- Map, in source seconds → output seconds: `0→0`, `0.7→0.7`, `1.6→1.3`, `2.8→3.25`, `4.1→3.9`, `5→5`, rounded to integer samples. The map includes both compressing and expanding intervals.
- Locate each output transient's peak within ±120 ms of its target. Report signed peak error; this measurement is **not** a complete psychoacoustic or onset-quality judgment.
- Also run a six-second in-workspace music excerpt through the same kind of nonuniform map, solely to create an audition and check output length. It is not a controlled timing fixture.
- Install `rubband` in an isolated temporary environment and inspect its published native binding for marker support. No Tactus product code was changed.

## Observations

| Path and input representation | Peak errors, ordered by marker (ms) | Result against ±20 ms rule |
| --- | --- | --- |
| Direct Rubber Band R2, float WAV | +3.375, +6.146, −14.625, +1.458 | Passes this fixture |
| `pyrubberband.timemap_stretch`, default R2, default temporary PCM-16 WAV | +1.792, +20.396, −14.500, +12.750 | Near miss: one marker exceeds rule by 0.396 ms |
| `pyrubberband.timemap_stretch`, explicit R3, temporary PCM-16 WAV | −0.042, +5.958, −8.563, +25.458 | Fails one marker |

The direct CLI R2 run with PCM-16 input reproduced the `pyrubberband` R2 errors, isolating the observed difference from float input to temporary WAV quantization rather than to the Python wrapper's time-map conversion. These numbers are deterministic on this fixture but not a universal precision bound. Four 10 ms tone-RMS windows spanning each boundary stayed nonzero; that only rules out a gross dropout, **not** audible clicks or other warp artifacts.

Direct CLI R3 printed a NaN/Inf time-ratio warning when the explicit `0→0` map point was supplied. Omitting that redundant origin point removed the warning but did not fix the +25 ms transient error. `pyrubberband` suppresses CLI stderr, so the same warning is not normally visible through its API.

For the six-second music excerpt, R2 produced 132,300 frames (6.000 s at 22,050 Hz), while R3 produced 131,460 frames (about 5.962 s) despite a six-second endpoint in the map. This output-length mismatch is a compatibility issue to investigate before treating R3's endpoint as exact; the excerpt has not received a human listening verdict.

`rubband` is **not missing the marker API**: its C++ binding exposes `Stretcher.set_key_frame_map(dict)` and forwards it to Rubber Band's `setKeyFrameMap`. Initially, no usable wheel was available for this Linux/Python 3.12 environment, and a source build failed because the installed Rubber Band was 3.3.0 whereas `rubband` requires 4.x. [Binding implementation](https://github.com/rec/rubband/blob/main/rubband/_rubband.cpp), [package requirements](https://github.com/rec/rubband).

### Follow-up: isolated Rubber Band 4.0 build

At the user's request, Rubber Band v4.0.0 was built and installed under `/tmp/tactus-warp-probe.aW3F9v/rb4`, **without replacing system 3.3.0**. `rubband` 0.3.1 was then built in an isolated Python 3.12 environment against that 4.0 library. The binding imported successfully and executed the same sample map through `Stretcher.set_key_frame_map`. The origin `0→0` was omitted from the binding map because it is implicit and triggered a warning in the earlier R3 CLI path. The binding used contiguous float32 NumPy input, offline `study` and `process` in 4096-frame blocks, and drained each available output block.

| Rubber Band 4.0 via `rubband` | Peak errors (ms) | Output length |
| --- | --- | --- |
| R2 (`EngineOption.faster`) | +3.396, +12.917, −9.875, +1.354 | 240,000 / 240,000 frames; passes ±20 ms on this fixture |
| R3 (`EngineOption.finer`) | 0.000, +12.437, −59.542, +15.729 | 240,000 / 240,000 frames; one marker fails ±20 ms |

On the six-second music excerpt, both 4.0 binding modes returned exactly 132,300 frames. This removes the **observed output-length mismatch on this path**, but does not isolate whether the difference came from the library version, the wrapper, or option defaults. The earlier 3.3 CLI results should not be treated as a controlled version-only comparison. The isolated build is an experiment fixture, not a durable Tactus dependency installation or packaging decision.

## Verdict and next decision

Marker-driven warp does **not** require DawDreamer: `pyrubberband.timemap_stretch`, `rubband.Stretcher.set_key_frame_map`, and Rubber Band's own key-frame map expose the needed mechanism. This fixture does **not** clear the pre-registered ±20 ms rule through `pyrubberband` in either R2 or R3; the isolated 4.0 `rubband` path clears it in R2 but not R3. Do not promise sample-accurate or always-within-20-ms transients. Keep Rubber Band as the known-good baseline and express source→target marker intent independently of a wrapper. A project-level packaging decision and a real listening check are still needed before making `rubband` a Tactus dependency.
