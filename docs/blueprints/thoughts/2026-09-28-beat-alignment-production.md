# Real-performance beat alignment through existing packages

> 2026-09-28 · Technical trial complete; Paul reports a modest listening improvement.
> Final grid/candidate acceptance remains open. This is not a general beat-accuracy or quality verdict.

## Question

Does pyqmdsp beat analysis help align a variable-tempo real performance to an authored grid,
and does Tactus need a new warp interface to use it? The approved comparison was a global
fixed-ratio stretch versus beat-by-beat marker warp, with the same added accompaniment.

## Production

The source is librosa's HQ Brahms Hungarian Dance No. 5 example, performed by US Army
Strings. Supplied metadata declares CC-PDM-1.0. The recording was decoded to 44.1 kHz stereo
PCM24 with no manufactured timing variation. Both recording and Tactus's one-time beat report
are pinned in the material pool; `render` never runs an estimator.

Detected beat indices 11–83 select 4.13315–31.63719 seconds of the recording. This avoids
unstable opening estimates and retains a major acceleration/slowing passage. Its 72 intervals
span 27.50404 seconds; their estimated instantaneous tempi range from 117.45 to 206.72 BPM.
No beats were manually moved or inserted, and bar/downbeat positions were not inferred.
The grid is provisional pending source-with-clicks listening.

The target is 160 BPM and 27 seconds. The work's `mode` selects `time_stretch` or `time_warp`
from already-installed pytimestretch (`e43cc6d`), using Rubber Band high quality in both cases.
The latter maps integer source frames to target frames in one continuous engine call, with
explicit endpoints. It does not reset the engine or concatenate independent per-beat slices.
Source phrase, gain, edge fades, output length and an authored half-time percussion part are
shared. Percussion grouping is a creative overlay, not source meter detection.

Code, source hashes, lock, frozen estimates and full measurements are in
[`examples/beat-alignment`](../../../examples/beat-alignment/README.md). Audio is kept in its
ignored `runs/` and the material pool. The Traditional Chinese listening page serves the
actual saved Tactus WAVs and offers source-grid review, same-position A/B switching, clean
music stems, click overlays and downloads.

## Timing measurements

The evaluator aligns the saved source and output music audio by 48-band log-mel features
plus positive spectral difference, using full-phrase DTW at 10 ms hops. The intended markers
are not supplied to DTW; the frozen source beat positions are queried on its resulting path.
The first and last two anchors are excluded from reported summaries.

| Actual audio correspondence relative to target grid | Fixed ratio | Marker warp |
|---|---:|---:|
| Mean absolute residual | 600.49 ms | 7.79 ms |
| 95th percentile absolute residual | 1569.73 ms | 17.66 ms |
| Maximum absolute residual | 1609.56 ms | 20.96 ms |

Calibration: source-to-itself correspondence is exact. The fixed-ratio output corresponds
to its independently known affine time map within 2.55 ms mean / 8.89 ms max. Thus the result
supports a large improvement in placement of the **chosen source positions**. It does not
establish correctness of those positions as musical beats or sub-10-ms measurement precision.

## Signal and reproducibility checks

- Both candidates contain exactly 1,190,700 frames; their percussion WAVs have the same SHA-256.
- Every output is finite and has zero reported clipped samples. Mix peaks are -7.59/-7.95 dBFS.
- Music RMS is -27.81/-27.70 dBFS, a 0.11 dB difference; neither candidate was normalized
  separately to win a loudness comparison.
- Marker-neighborhood sample derivatives triggered no isolated-step flags (>0.02 and >3x
  the local derivative p99). This is a discontinuity diagnostic, not proof of inaudibility.
- Final runs reproduce all four outputs of each initial run byte-for-byte. Their receipts
  resolve the two pinned input refs and their Python source hashes still match.
- Subjective listening is pending: no available instrument in this session could judge audio
  quality. The human review must check click interpretation, transient softness, flutter,
  phrase feel and whether losing the original rubato is desired for this work.

## Design implication

Existing Tactus + pyqmdsp + pytimestretch complete this bounded production with ordinary
functions. A new native warp implementation or Tactus wrapper is not justified by this trial.
The previous board entry saying there was no chosen marker-warp binding was stale: the
installed dependency already exposes a tested marker contract.

The useful boundary is an explicit, frozen source-to-target map owned by the work, followed
by the package's continuous warp. Acceptance of the estimated map remains a musical decision.
One work does not yet show repeated authoring friction that warrants a shared map helper.

## Listening feedback and remaining decision

Paul's first response to the A/B comparison: **「我覺得有好一點」** (2026-09-28).
In context this is preliminary positive feedback on B's beat-marker alignment. It supports
using B as the basis for further work on this production. It does not specify which passage
improved, validate every detected beat, or settle the audible-artifact trade-off.

The source grid and final candidate are still provisional. Next refinement, if requested,
should follow a specific audible problem rather than adding a shared warp API on this evidence.

## Completion checks

Full Tactus pytest: 400 passed, 1 skipped (unchanged opt-in installation test), 202.36 seconds.
Ruff and whitespace checks pass. The listening page was exercised in Chromium at desktop and
390 px mobile widths; no horizontal overflow, audio playback/seeking, same-position A/B switching,
stem selection and downloads pass. The player uses cached Blob URLs so seeking remains usable
with the standard Python HTTP server. The server binds only localhost at port 4186.
