# Fixed-ratio stretch helper necessity probe

> 2026-09-24 · Evidence returned to the pending Tactus helper decision. This is not a stretch-quality ranking or an Agent performance benchmark.

## Question and preregistered rule

Does fixed-ratio stretching require a Tactus core helper, or can ordinary project-local Python handle the repeated mechanics? Compare separate project-local functions, a thin shared helper, and one project-local shared function. A core helper is supported only if at least two scenarios require repeated noncreative steps that cannot be removed locally while preserving author choices. Merely saving a few lines is convenience, not necessity.

## Method

Use the same locally prepared 48 kHz music source, `pyrubberband` 0.4.0, and system Rubber Band 3.3.0 in all variants. At 90 BPM, render a stereo two-second excerpt to 128,000 frames and a mono 3.4-second excerpt to 64,000 frames. Keep source regions, gains, placements, and backend fixed. Build and render all three variants through Tactus; compare material and WAV identities. Separately request six irregular output lengths from the backend. All harness files and audio stayed under `/tmp/tactus-stretch-helper-probe-6FroVc`; product code was not edited.

## Observations

All three authoring variants produced identical material hashes for both chops and an identical rendered mix WAV. The backend returned the requested frame count for both composition cases and six irregular targets: 23,457; 48,001; 55,555; 111,111; 129,037; and 190,001 frames. The two separate project-local functions repeated rate calculation and backend invocation. A single project-local function removed that duplication without changing the audio or requiring a Tactus API. The tested padding/trimming path never had to correct a length mismatch.

## Verdict

The preregistered condition for a necessary core helper was not met. Keep fixed-ratio stretching expressible as ordinary Python calling Rubber Band through `compute`; do not add `stretch_to_duration()` to Tactus core on this evidence. A helper may still become worthwhile if repeated cross-project work reveals backend-specific errors, duration mismatches, or provenance needs that project-local code cannot handle well. This probe did not measure Agent performance across projects, listening quality, all ratios, other backends, or marker-based warp.
