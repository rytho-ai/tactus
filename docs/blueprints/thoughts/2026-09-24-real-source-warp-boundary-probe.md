# Real-source warp through the current Tactus boundary

> 2026-09-24 · Bounded probe of the current `asset_region` → `compute` → placement → compiled render path. This is not a listening verdict, a full Music Agent OS parity test, or an API decision.

## Question and preregistered rule

Can a real-audio, pitch-preserving chop workflow be written as ordinary project-local Python without changing Tactus's core? The pass condition was: compile and render two stretched chops plus an independent percussion stem; change only one source-region choice; observe a changed sample stem and mix but an identical percussion stem; and replay the compiled build from a directory without the source. A failure caused by technical work that every production would repeat would count as evidence for a framework helper. The probe did not use perceived musical quality as a pass condition.

## Trial

- Local-only source: `phonon/demo/playground/sample/demo-song.mp3`, SHA-256 `1d2672dfc554128c67c5fcd2342e0a72d0a2f254b17502c619d9755ef6645a87`, 40 seconds, 48 kHz stereo. Its licensing was not established; neither source nor derivative audio was added to Tactus or published.
- Disposable project under `/tmp/tactus-real-warp-probe-k5sHL5`; no Tactus product code was edited. The project used two two-second source regions, at 8 s and initially 12 s, stretched with `pyrubberband.time_stretch` 0.4.0 / system Rubber Band 3.3.0 to 128,000 frames each: one four-beat bar at 90 BPM and 48 kHz. A project-local NumPy function padded or trimmed the backend output to that explicit length and applied a fixed gain. A separate NumPy pulse function made eight quiet percussion events over two bars.
- Revision: move only the second source-region start from 12 s to 14 s; retain its placement and target duration. Compile and render both builds using the Tactus CLI, then compare semantic diff and WAV hashes. Copy the second compiled build into a directory containing no source audio or `song.py` and render again.

## Observations

The first build failed **before stretch**: decoding this MP3 produced a peak of 1.09598, and `asset_region` rejected audio above full scale. A one-time, explicit preparation step scaled the decoded file by 0.866803 to a 0.95 peak and wrote local 24-bit PCM. Its SHA-256 was `1f5f6413120152f745a6a2e874de9f2b477e38c1cb48f47a8dbc451d0e6e97d7`. The build then succeeded without Tactus changes. This is real input-friction, not evidence that the Agent cannot write a stretch function.

Both stretched materials had exactly 128,000 frames. The rendered mix and stems had 256,000 frames each, with a mix peak of 0.6493. Changing the second source region changed the sample-stem hash (`d739906c…` → `64390831…`) and mix hash (`1ff3fa87…` → `25d4fb0e…`); the percussion-stem hash remained `a2f7b2d0…`. `tactus diff` identified `sample/chop-1` as the changed event and reported no transport change. Rendering from the isolated compiled copy gave the same complete mix SHA-256, `25d4fb0eb73500e50d50a48a366672cad64a52c2043cf1ea9370c8b6396ff8c0`.

Two limits are visible in the artifacts. The receipt records Python, Tactus, NumPy, and SoundFile versions, but neither `pyrubberband` nor the external Rubber Band executable that made these materials. This weakens **source-rebuild provenance**, not the verified compiled replay. Also, `compute` hashes the entire `song.py` file as its code identity: the one-line source-region edit changed `code_sha256` for all three computations, including the unchanged pulse and first chop. Their output material hashes stayed identical in this trial. Tactus does not yet offer selective computation caching, so this is a prospective invalidation concern, not a measured cache miss.

## Verdict and next boundary

The existing composition seam is sufficient for **this bounded real-source warp**, but the stretch itself came from `pyrubberband` calling the system Rubber Band executable. Tactus did not implement a time-stretch algorithm: ordinary project-local Python chose the chops, called Rubber Band, and fitted its output to the requested bar length; Tactus handled materialization, placement, semantic diff, stems, and compiled replay. This supports keeping Rubber Band as the working stretch backend and allowing the Agent to use it through `compute` for this simple fixed-ratio case. It does **not** establish that a Tactus `warp()` helper is never useful, or that each project should indefinitely reimplement backend invocation and length handling.

In particular, the trial does not demonstrate musical quality, marker-based warp, automation, effect integration, or reliable source rebuild across machines. A dedicated helper should be justified by repeated authoring friction or a technical responsibility that must be shared across productions, not by the mere fact that stretch was used once.

The immediate framework-level candidates are narrower: an explicit policy for valid but above-full-scale decoded input (for example, a declared import gain that preserves provenance) and complete recording of external transform identity in the build receipt. Test those separately before promoting them into core. Human audition and a broader real-song workflow are still needed to judge whether project-local stretch code remains pleasant to author and revise.
