# Librosa value beyond basic onset detection

> 2026-09-23 · This evidence fed the analysis-dependency decision back to Paul. The probe used disposable audio and code; Tactus product code and dependencies were not changed. The later [core-dependency decision](2026-09-23-analysis-core-dependencies.md) supersedes this document's optional-dependency recommendation; the observations remain historical evidence.

## Question and pre-registered verdict

Does librosa add a capability that changes a Tactus production decision beyond NumPy/SciPy analysis?

Two production-shaped questions were tested. For harmonic sample selection, can an analyzer identify the three pitch classes present in each short chord segment of a drum-mixed progression? For retuning a monophonic lead, can it identify the intended fundamental when the second harmonic is louder and note starts contain percussion?

The verdict rule was set before the run. Librosa's `chroma_cqt` would show a concrete incremental benefit if it recovered at least three of four known triads while a fixed SciPy chroma baseline recovered at most two. Librosa pYIN would show a concrete incremental benefit if it recovered at least three of four note frequencies within 50 cents while a fixed SciPy autocorrelation baseline recovered at most two. Passing one task would support that specific feature, not automatically a mandatory core dependency.

## Method

A CPU-only script generated a six-second C–Am–F–G progression with chord harmonics, a stronger low bass, kick and hi-hat. For each 1.5-second section, it scored the top three measured pitch classes against the authored triad. The SciPy baseline combined a 4,096-sample STFT, FFT-bin-to-pitch-class mapping, and average energy; librosa used `feature.chroma_cqt`. Both read the same 16 kHz array and were scored on the same interior windows.

A separate four-note lead used known fundamental frequencies of 220.00, 246.94, 261.63, and 293.66 Hz. Its second harmonic was stronger than the fundamental, and a short noise click marked each new note. The SciPy baseline used windowed autocorrelation over 1,024-sample frames and an energy gate; librosa used `pyin` over the same range and frames. Scoring used each note's interior frames and the median estimated frequency.

After seeing the registered result, an **exploratory robustness check** changed only the SciPy chroma window from 4,096 to 8,192 samples. This follow-up tests whether the initial discrepancy was simply low-frequency resolution. It was not part of the original win criterion.

The harness lived outside the repository under `/tmp/tactus-librosa-value-k4anJ4/`. It ran on Linux x86-64 CPU with Python 3.13.5, NumPy 2.5.3, SciPy via `uv run --no-project`, and librosa 1.0.0. No source audio or test harness is retained as a product artifact.

## Results

| Harmonic method | Exact pitch-class triads | Interpretation |
| --- | ---: | --- |
| SciPy STFT chroma, 4,096-sample window | 2/4 | A minor and G major had one wrong pitch class each. |
| Librosa CQT chroma | 4/4 | Met the pre-registered incremental-benefit rule against the fixed baseline. |
| SciPy STFT chroma, 8,192-sample window | 4/4 | Exploratory resolution adjustment closed the observed gap. |

| Fundamental estimator | Notes within 50 cents | Absolute median error |
| --- | ---: | --- |
| SciPy autocorrelation | 4/4 | 4.4–15.5 cents |
| Librosa pYIN | 4/4 | About 1.3 cents on each note |

Both methods marked three frames in the silent tail as voiced under the script's simple counting check. The measured processing times were sensitive to first-call setup: CQT took about 2.29 s on the first run and 0.26 s on the next; pYIN took about 2.48 s and then 0.12 s. The corresponding SciPy operations took roughly 0.01–0.03 s. These figures describe this local run only and are not a fair cold-start or cross-platform benchmark.

## Verdict and limits

Librosa provides useful ready-made musical analysis, especially CQT chroma and pYIN. The first registered chord comparison showed a task-specific benefit. The resolution check then showed that this fixture can also be solved by a small SciPy implementation, and both fundamental estimators passed the registered retuning task. The evidence therefore **does not establish a mandatory librosa core dependency**. Use it directly when a production needs a specific feature; reconsider a shared optional analysis extra or helper after repeated real use.

The audio was controlled and synthetic. A longer FFT window can blur fast chord changes, which this six-second fixture did not test. Complex recorded music, detuned sources, changing harmony, polyphonic melody, and Agent authoring effort remain unmeasured. `chroma_cqt` returns pitch-class evidence, not an authoritative chord label; pYIN supplies pitch candidates, not a complete transcription. A real production task with accepted musical ground truth would be the next deciding test.
