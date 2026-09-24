# Time-stretch algorithm listening probe

> 2026-09-24 · Evidence for the Tactus time-stretch backend decision. Paul prefers A and chooses to keep Rubber Band as the baseline. The specific listening cell is not yet identified, so this is not a universal quality ranking.

## Question and preregistered decision rule

Does a non-Rubber-Band algorithm offer a useful audible advantage at a concrete material/ratio pair? Compare only within a fixed source and output-duration ratio. If a challenger is clearly preferable in at least one musically relevant pair without a severe failure, retain it as a possible optional tool. If no stable advantage appears, keep Rubber Band as the baseline. A split result calls for use-case selection, not a universal winner. This rule was stated before rendering or listening.

## Materials and method

- Two six-second in-workspace mono sources: `../phonon/demo/playground/sample/beat-grid-demo.wav` (SHA-256 `b8506d0fdcb5bcf358cbf06dc755564300b9cdd9421aaf30753e30cc1e65b805`, 22,050 Hz) and `../rytho/app/docs/blueprints/mockups/2026-09-02-rytho-panel-v2/assets/soft-pad.wav` (SHA-256 `261eccabb42ddbebaf7f22cc891dad6f259aaf0cd06cc86cd8316037feb6a3d0`, 44,100 Hz). These are rhythm/transient and sustained/harmonic examples, not a representative music corpus.
- Output-duration ratios: `0.5×` (faster/shorter), `1.5×`, and `3×` (slower/longer). Pitch shifting is not requested. Each source/ratio is an independent listening cell.
- Engines: Rubber Band v4.0.0 R2 and R3 through `rubband` 0.3.1, plus Signalsmith Stretch through `python-stretch` 0.3.1. Rubber Band uses offline `study`/`process` with 4096-frame input blocks and explicit engine selection; Signalsmith's `timeFactor` is set to the inverse of the output-duration ratio. The packages were used in isolated probe environments, not added to Tactus dependencies. [Rubber Band API](https://breakfastquay.com/rubberband/code-doc/classRubberBand_1_1RubberBandStretcher.html), [Signalsmith Python binding](https://github.com/gregogiudici/python-stretch).
- In each cell, all three outputs are matched to a common RMS with gain only, constrained below a peak ceiling; no EQ, limiter, resampling, or pitch correction is applied. Encoded audition audio is lossless PCM-16 FLAC embedded in one standalone HTML file. The original is available separately at native length as a timbral reference.
- The HTML presents randomized A/B/C labels per cell, allows switching at approximately the same playback position, and records a preference or no-winner response in browser local storage. The names can be revealed after listening. This is a convenience blind, not a formal double-blind test.

## Technical result so far

All 18 processed outputs (2 sources × 3 ratios × 3 engines) were finite and had exactly the expected frame count for their source and ratio. The interactive page was opened and checked in a browser: source/ratio selection, A/B/C switching with playback-position carryover, and answer reveal worked, with no page errors. This verifies the audition is usable; it says nothing about which audio sounds better.

Audition: [`../mockups/2026-09-24-stretch-listening/index.html`](../mockups/2026-09-24-stretch-listening/index.html). The standalone file is about 3.75 MB because it embeds lossless FLAC audio. The disposable render harness is not product code.

## Listening decision and its limit

Paul reported that A sounded best and chose to retain Rubber Band as the Tactus baseline. Because A/B/C were randomized independently in each cell, the report does not yet identify one specific engine or settle R2 versus R3:

| Cell | A |
| --- | --- |
| Beat, 0.5× | Rubber Band R3 |
| Beat, 1.5× | Rubber Band R2 |
| Beat, 3× | Rubber Band R2 |
| Pad, 0.5× | Rubber Band R3 |
| Pad, 1.5× | Signalsmith |
| Pad, 3× | Rubber Band R3 |

Keep Rubber Band as the working choice; do not add Signalsmith as a required backend on this evidence. If the precise perceptual result matters later, first ask which source/ratio cells Paul listened to. A preference for A in the pad 1.5× cell would be evidence for Signalsmith in that particular case, not Rubber Band. No code dependency or default-engine change was made by this listening decision.
