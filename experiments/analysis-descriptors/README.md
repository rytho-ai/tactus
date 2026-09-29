# Dynamics and spectral descriptor verification

This batch adds five optional owned NumPy/SciPy observations: whole-input sample crest
factor, its windowed curve, spectral bandwidth, rolloff and flatness. They supplement
existing level/spectral observations; no new dependency or automatic production decision.

## Why these five

Crest factor locates peak-to-average changes that whole-file loudness/LRA do not describe.
Bandwidth describes spread beyond a centroid; rolloff is a cumulative energy percentile;
flatness describes how evenly power is distributed. These can compare processing candidates
or help authors select material/sections. None infers punch, instruments or overall quality.
See the [candidate assessment and plan](../../docs/blueprints/plans/2026-09-29-analysis-descriptors.md)
for the explicitly deferred alternatives.

## Definitions

- Sample crest factor is `20*log10(max(abs(audio))/RMS(audio))`, with the maximum across
  channels and RMS averaged over all samples/channels. No downmix, DC removal or gating.
  Whole-input scaling avoids squaring overflow/underflow. Curves use the existing complete
  rectangular windows (default 50 ms / 10 ms), window-end timestamps and no partial tails.
  Squared-power overflow in curves is rejected; extremely quiet underflowed windows are
  recomputed relative to their local peak. Silence is null. This differs from PLR and LRA.
- Spectral descriptors sum channels and use centered periodic Hann frames with zero padding,
  `n_fft=2048`, `hop=512`; frame centers stop at input duration, as in Mel/MFCC. All FFT bins
  from DC to Nyquist are included. Opposite-phase channels may cancel; zero-power frames
  return null for all descriptors.
- Bandwidth is the power-weighted frequency standard deviation (Hz), not a -3 dB width.
- Rolloff selects the first bin reaching `roll_percent` of cumulative power (default .85).
- Flatness is geometric/arithmetic mean of power, after dividing each frame by its largest
  bin and flooring at `floor_ratio` (default 1e-12). This relative floor removes ordinary
  gain dependence. Uniform spectra approach 1; concentrated spectra approach 0.

The mathematical spectral definitions were compared with
[librosa's official implementation](https://librosa.org/doc/main/_modules/librosa/feature/spectral.html).
Reference calls explicitly receive a **power** matrix (bandwidth/rolloff normally use
magnitude), and flatness receives relative power, `power=1`, `amin=1e-12`. Silence handling
is deliberate Tactus behavior, not inherited reference output.

## Evidence

`tests/test_analysis_descriptors.py` covers analytical sine/square/impulse crest factors;
nonaligned and strided windows; quiet tails and gain scaling; known equal-tone spectral
spread; tone/noise/impulse flatness; independent reference calculations at 8, 22.05 and
48 kHz; silence, phase cancellation, short inputs, invalid inputs/parameters, nonmutation,
CLI discovery and strict JSON nulls.

`report.json` records a local 149.189 s stereo production (44.1 kHz, input hash included),
three controlled transformations and five actual `uv run tactus analyze` commands.
Each CLI output matches its Python result and saved record. Three spectral reference
checks pass: bandwidth maximum error 2.73e-12 Hz, rolloff/flatness exactly equal on this input.
All five descriptors remain equal within numerical tolerance after -24 dB gain.

| Observation | Original | Processed | Interpretation within this experiment |
| --- | ---: | ---: | --- |
| Whole-input crest factor | 10.69 dB | 3.28 dB after clipping | Reduced peak-to-RMS contrast |
| Median spectral bandwidth | 465.13 Hz | 329.83 Hz after 1.5 kHz lowpass | Reduced frequency spread |
| Median 85% rolloff | 990.53 Hz | 796.73 Hz after lowpass | Lower cumulative power percentile |
| Median spectral flatness | 9.52e-6 | 5.23e-8 after lowpass | Less even power distribution across the full frequency range |

These measurements establish sensitivity to the specified transformations, not a universal
perceptual ranking or a recommendation to clip/filter the production.

## Reproduce

```bash
uv run --extra librosa pytest -q tests/test_analysis_descriptors.py tests/test_analysis.py
uv run --extra librosa python experiments/analysis-descriptors/check.py \
  --audio dogfood/2026-09-25-full-song-3/work/runs/c4/mix-32222836.wav \
  --work dogfood/descriptor-check-new \
  --out experiments/analysis-descriptors/report.json
```

The source production is ignored session material; substitute another WAV to repeat the
checks. `--work` must be new. Reference packages are in the optional `librosa` extra. Known processing
assertions in the runner target this fixture and may not hold for every substitute (for
example, an already band-limited signal may retain the same rolloff). Audio is not copied
into this report or redistributed. Source hashes are recorded for reproducibility.

## Repository gates

- Focused new/registry tests: 103 passed. Full `uv run pytest -q`: 825 passed, 1 skipped
  (the existing opt-in installation test).
- Repository-wide Ruff, changed-file formatting, `git diff --check` and `uv build` pass.
- Source hashes in the real-audio report match the current implementation; the wheel
  contains those same level/spectral/frontend files.
- All five additions are in the existing generated analysis registry: 26 analyses total
  (12 level, 11 spectral, 3 rhythm). No dependency or CLI-routing changes this batch.
- No commit, publication or global installation performed.
