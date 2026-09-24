# Do pyloudnorm and librosa earn a core dependency?

> 2026-09-23 · This evidence fed the analysis-library decision back to Paul. The probe compared library behavior on fixed audio and did not modify Tactus product code. The later [core-dependency decision](2026-09-23-analysis-core-dependencies.md) supersedes this document's optional-dependency recommendation; the observations remain historical evidence.

## Question and pre-registered rule

Do pyloudnorm or librosa add enough to a NumPy/SciPy-based basic-analysis workflow to warrant a core dependency?

Before running, the decision rule was: a package earns a core place only if it changes a concrete production decision or provides a needed standard measurement that the baseline lacks. For loudness, compare equally peaked and equally RMS-matched signals, then check pyloudnorm against an independent FFmpeg measurement. For onset, compare a fixed SciPy baseline and librosa on identical audio, scoring candidates within 25 ms of known authored attacks. A similar result cannot establish a necessary dependency. The test does not infer that a different implementation could never do the same work.

## Method

The loudness arm generated three 8 s, 24 kHz float WAVs: a 60 Hz sine, a 1 kHz sine with the same peak and RMS, and a 1 kHz sine whose final six seconds were replaced by silence. NumPy measured whole-file peak and RMS. `pyloudnorm.Meter(...).integrated_loudness` measured the decoded array; FFmpeg `loudnorm=print_format=json` measured the encoded float WAV independently.

The timing arm used the three synthetic fixtures from the [CPU basic-analysis probe](2026-09-23-cpu-basic-audio-analysis-probe.md) and an existing 120 BPM click-track fixture at `../phonon/demo/playground/sample/beat-grid-demo.wav`. Its SciPy baseline used an STFT with 1,024-sample windows and a 120-sample hop, positive spectral flux, and `find_peaks` with fixed prominence and 80 ms spacing. Librosa used `onset_detect` with the same 120-sample hop. Settings were chosen before reading comparison results and were not tuned per fixture. Only the first three fixtures have explicit authored attack lists for quantitative scoring.

Both arms ran on Linux x86-64 CPU using disposable code and generated WAVs under `/tmp/tactus-analysis-necessity-pIALJp/`. No product source, dependency list, or lockfile was changed. FFmpeg 6.1.1 was available locally. The Python scratch environment used NumPy 2.5.3, SoundFile 0.14.0, pyloudnorm 0.2.0, librosa 1.0.0, and SciPy via `uv run --no-project`.

## Results

| Signal | Sample peak | Whole-file RMS | pyloudnorm | FFmpeg |
| --- | ---: | ---: | ---: | ---: |
| 60 Hz, 8 s | −16.99 dBFS | −20.00 dBFS | −23.62 LUFS | −23.65 LUFS |
| 1 kHz, 8 s | −16.99 dBFS | −20.00 dBFS | −20.05 LUFS | −20.05 LUFS |
| 1 kHz, 2 s then 6 s silence | −16.99 dBFS | −26.02 dBFS | −20.39 LUFS | −20.39 LUFS |

Equal RMS and sample peak did not imply equal integrated loudness; the 60 Hz and 1 kHz cases differed by 3.57 LU according to pyloudnorm. Replacing six seconds with silence lowered whole-file RMS by about 6 dB while gated integrated loudness changed by only about 0.34 LU. FFmpeg matched pyloudnorm to within 0.03 LU in these three cases. This demonstrates the value of a standardized loudness measurement for these level-comparison tasks, not a unique need for pyloudnorm's implementation.

| Known-attack fixture | SciPy matches / total; extra candidates | Librosa matches / total; extra candidates |
| --- | --- | --- |
| 0.18 s kick | 1/1; 0 | 0/1; 1 candidate 45 ms after the attack |
| 120 BPM loop | 32/32; 0 | 31/32; 0; the file-start attack was omitted |
| Free-time texture | 5/5; 0 | 5/5; 0 |

On the existing 120 BPM click fixture, SciPy reported 24 onset candidates and librosa 23; both followed the visible quarter-second event pattern, but this fixture was not independently annotated for exact scoring. Librosa returned a 119.84 BPM tempo candidate. Its first beat candidate was at 0.512 s even though the generated click pattern begins at the file boundary. Both algorithms have window- and hop-dependent timing; matching within 25 ms does not make a candidate sample-accurate.

## Verdict and limits

The probe supports **LUFS as a separate observation** when comparing sustained or delivered audio. It does **not** prove that pyloudnorm is a necessary core dependency: FFmpeg produced effectively the same results here. Pyloudnorm remains a useful in-memory tool if a production repeatedly measures NumPy arrays without first writing files. Delivery-file measurement can use FFmpeg when that tool is already part of the workflow. Very short sounds still need an unavailable-LUFS result rather than a fabricated number.

The probe found **no demonstrated basic-onset need for librosa**. A small SciPy implementation was at least as effective on these controlled signals. Librosa can remain an optional analysis tool for tasks that need its higher-level algorithms, but a real production task should show the incremental benefit before it becomes a Tactus default. The result does not establish that the fixed SciPy threshold generalizes to complex recorded music, nor that librosa performs worse overall. No Agent authoring-time study was run.
