# Beat analysis to aligned production — plan

> Generated: 2026-09-28 · Source: Paul requested the proposed real-performance alignment
> and listening comparison · Grounding: Tactus `ccb3cc8`, installed pytimestretch `e43cc6d`.

## Context

`rhythm.beats` is integrated and numerically verified. The next question is whether detected
beats help an actual production align variable-tempo audio to an authored grid. Installed
`pytimestretch.time_warp` already accepts monotonic integer `(source_frame, output_frame)`
markers with explicit endpoints. The board's implication that no binding has been chosen
is stale: first exercise this installed capability through ordinary production functions.

Use the US Army Strings performance of Brahms's Hungarian Dance No. 5, distributed as
librosa's high-quality `brahms` example (CC-PDM-1.0 in its supplied metadata). It is a real
variable-tempo performance, not a recording with synthetic timing drift added.

## Approach

1. Create `examples/beat-alignment` with `tactus init --tactus-path`, its own lock and ignored
   inputs/runs. Pin decoded source audio and analysis JSON using `material`. Keep provenance,
   selection parameters and numerical evidence in Git, audio in the pool and ignored folders.
2. Run the real beat CLI once; inspect beat intervals and select a contiguous phrase. Freeze
   the unedited estimator output as a provisional alignment map. Provide original audio with
   detected clicks for human review; no downbeats or ground-truth labels are inferred.
3. Render two candidates through one `render` source: global fixed-ratio stretch and marker
   warp, same backend, phrase, target BPM, output duration, gain and authored percussion.
   Use continuous whole-phrase engine calls; retain clean source stems for artifact listening.
4. Verify actual rendered timing with local source/output audio feature matches independent
   of the beat tracker. Report this separately from the intended mathematical mapping and
   optional re-detection. Inspect discontinuity statistics near markers and clipping, without
   presenting these as proof of inaudibility. Check identical percussion and exact lengths.
5. Deliver a Traditional Chinese listening page with synchronized A/B controls, source-click
   review, clean stems, waveform/timing evidence and downloads. Serve it on localhost for
   SSH/IDE forwarding. Human listening and adoption of the provisional grid remain pending.
6. Record results under `docs/blueprints/thoughts`, update the board and design to match the
   demonstrated boundary, and run required pytest/Ruff checks for committed Python changes.

## Critical files

| File | Responsibility |
|---|---|
| `examples/beat-alignment/prepare.py` | Source provenance, one-time analysis and frozen markers |
| `examples/beat-alignment/song.py` | Explicit phrase selection, stretch/warp, percussion and mix |
| `examples/beat-alignment/evaluate.py` | Saved-output measurements and listening artifact |
| `examples/beat-alignment/pyproject.toml`, `uv.lock` | Independent consumer environment |
| `examples/beat-alignment/README.md` | Reproduction, result interpretation and evidence limits |
| `docs/blueprints/thoughts/2026-09-28-beat-alignment-production.md` | Measured outcome and design implications |
| `docs/design.md`, `docs/blueprints/plan.md` | Current capability and remaining listening decision |

## Verification

- Source identity and analysis material hash match, and render reads the frozen map only.
- Both candidates use the same source phrase, target grid, output frame count and percussion.
- Report source timing variation, global-affine grid residuals, local audio correspondence
  residuals after rendering, clipping and marker-boundary discontinuities.
- Marker warp earns a timing claim only if actual audio measurements improve; mapping
  coordinates alone are not sufficient evidence. Feature-match ambiguity is reported.
- Production render, CLI analysis, saved WAVs, receipts and listening-page links work.
- Full Tactus pytest and Ruff; targeted experiment assertions in the evaluator.
- The agent has no available subjective audio-listening instrument in this session. Human
  listening of completed artifacts decides beat interpretation, audible artifacts and preference.

## Out of scope

Adding a Tactus warp API, automatic downbeat detection, a universal quality verdict, changing
pyqmdsp's estimator, publishing the production, or accepting a listening candidate for Paul.

## Outcome

- Implemented the production at `examples/beat-alignment` with its own uv lock, pinned source
  and frozen estimator report. Selected 72 intervals across 27.504 seconds; target 160 BPM,
  27 seconds. Source intervals range from 117.45 to 206.72 BPM.
- Actual saved-audio correspondence against the target grid: fixed ratio **600.49 ms** mean
  absolute error / **1569.73 ms** p95; marker warp **7.79 ms** / **17.66 ms**. The evaluator
  estimates alignment from audio features, independently of the intended markers.
- Same frame counts and identical percussion hashes; zero clipped samples and zero configured
  isolated boundary-step flags. This does not settle audible quality or beat interpretation.
- Re-rendered all three modes after finalizing Python source: all four outputs per mode were
  byte-identical. Final receipts match the current production Python source and pinned materials.
- Full Tactus pytest: **400 passed, 1 skipped** (the unchanged opt-in installation test),
  202.36 seconds. Ruff and `git diff --check` pass.
- Browser-tested the listening page on desktop and a 390 px viewport: no horizontal overflow,
  audio loads, full-duration seeking works, A/B preserves 17.000 s when paused and resumes the
  matching position during playback, stem selection and downloads work. Blob-backed playback
  avoids Python's simple HTTP server's lack of Range support.
- The page is served at `http://localhost:4186/`. Human review of original clicks, rendered
  audio quality and candidate preference is the remaining acceptance step. No candidate was
  selected and no new Tactus warp API was added.
