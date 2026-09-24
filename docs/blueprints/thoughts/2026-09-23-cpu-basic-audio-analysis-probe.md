# CPU-only basic audio analysis probe

> 2026-09-23 · This evidence feeds the pending basic-analysis decision back to Paul. The probe tested observation behavior; it did not change Tactus product code.

## Question and verdict rule

Can ordinary NumPy, SoundFile, pyloudnorm, and librosa provide useful first observations without a GPU, model weights, or a Tactus analysis framework?

Before running the trial, the acceptance rule was: file facts and numeric measurements must match generated ground truth; onset candidates should identify the regular loop's attacks; tempo estimates must remain candidates, especially for free-time audio; unavailable LUFS must be reported as unavailable. A fabricated value, an unqualified free-time BPM, or a claim that detected beat positions are exact authoring positions would fail the interpretation boundary.

## Method

A disposable Python script generated and wrote three float WAV fixtures using SoundFile, then decoded each once for the three analysis paths:

| Fixture | Ground truth |
| --- | --- |
| `short_kick` | 0.18 s mono, one attack at file start, no meaningful BPM |
| `beat_loop` | 8 s stereo, 120 BPM, kick/hat attacks every 0.25 s beginning at 0 |
| `free_time` | 8 s mono tonal texture, irregular added attacks at 0.7, 1.9, 3.35, 5.1, and 7.4 s; no declared BPM |

SoundFile supplied rate, channel count, frame count, and `float32` arrays. NumPy measured sample peak, RMS, and finite values. `pyloudnorm.Meter(...).integrated_loudness` measured integrated LUFS. Librosa ran `onset_detect` and `beat_track` on the mono signal with a 120-sample hop at 24 kHz. No resampling, model inference, or cloud service was used.

The run used Linux x86-64, Python 3.13.5, NumPy 2.5.3, SoundFile 0.14.0, pyloudnorm 0.2.0, and librosa 1.0.0 in a scratch environment created with `uv run --no-project --with numpy --with soundfile --with pyloudnorm --with librosa`. The generated fixtures and harness stayed outside the product repository under `/tmp/tactus-basic-analysis-probe-VsdJSW/`; they are disposable and not a maintained source of truth.

## Observations

| Fixture | File and level facts | LUFS | Timing candidates |
| --- | --- | --- | --- |
| Short kick | Expected 4,320 frames, mono, 24 kHz; peak −2.81 dBFS; RMS −15.97 dBFS | Unavailable: `ValueError` because the audio is shorter than the meter's block | Onset at 0.045 s, 45 ms after the authored attack; no beat and 0 BPM returned |
| Beat loop | Expected 192,000 frames, stereo, 24 kHz; peak −2.81 dBFS; RMS −21.27 dBFS | −20.29 LUFS | 31 of 32 attacks detected within 5 ms; the attack at file start was omitted. Tempo candidate 120 BPM. Beat candidates began at 0.77 s instead of the known 0 s downbeat. |
| Free-time texture | Expected 192,000 frames, mono, 24 kHz; peak −11.23 dBFS; RMS −24.46 dBFS | −25.22 LUFS | All five authored attacks detected at their rounded positions. Beat tracker still returned 50 BPM and a candidate beat at 6.265 s without a corresponding authored attack. |

All decoded arrays were finite. File/NumPy checks took 0.0003–0.0056 s per fixture and loudness 0–0.0104 s. Librosa timing analysis took 0.2646–0.9824 s per fixture in this warmed local run. These timings are exploratory; they are not a cross-platform benchmark or a cold-start measurement.

## Verdict and product implication

The observed library behavior is sufficient to start a CPU-only basic observation workflow. Tactus can use the existing packages directly while making their interpretation boundaries clear in reports: analyzed file/range, units, settings, algorithm, and unavailable values. Sample peak and RMS are different measurements from integrated LUFS. An onset candidate may lag an attack or omit one at a file boundary; a beat grid may have an incorrect phase even when its BPM is correct. A numeric tempo estimate does not establish that a piece has a musical clock.

This probe was deliberately synthetic and small. It does not establish accuracy on real recordings, reliable downbeat detection, quality of Agent musical choices, availability on every operating system, or the best package combination for all analyses. Test a real source passage and the Agent's interpretation during the production vertical slice. The next independent selection question is pitch-preserving stretch and local warp of an actual chop, with both timing checks and listening.
