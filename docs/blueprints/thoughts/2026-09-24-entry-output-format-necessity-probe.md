# Entry and output format necessity probe

> 2026-09-24 · Evidence for the pending functional-entry decision. This probes feasibility, not Agent productivity. Product code was unchanged.

## Question and preregistered rule

Does bounded production and revision require a mandatory `render()` entry returning `{sample_rate, outputs}`?

Before trials, the rule was recorded in scratch: if ordinary Python meets the same delivery requirements and produces identical audio, necessity is unsupported for this scope. A failure supports the fixed contract only if attributable to entry/result semantics.

## Method

Compare executable Python calling a local WAV writer with a fixed `render()` result consumed by a runner. Both use identical musical functions, validation, receipts, PCM24 encoding, parameters, and fresh processes. Local helpers are allowed in both arms; their interfaces are not proposed universal work formats.

Use the local 48 kHz stereo `phonon/demo/playground/sample/demo-song.mp3`, pinned to SHA256 `1d2672dfc554128c67c5fcd2342e0a72d0a2f254b17502c619d9755ef6645a87`. Apply explicit gain and fades, stretch two excerpts into two bars at 90 BPM, and add deterministic percussion. Separately export unequal-length clips without a mix.

Run five successful cases and three rejection controls per arm: 16 subprocesses total. Environment: Python 3.12.11, NumPy 2.5.3, SoundFile 0.14.0, pyrubberband 0.4.0, Rubber Band 3.3.0.

## Results

| Case | Observed in both arms |
| --- | --- |
| Base production | Mix and two stems, each 256,000 frames |
| Gain candidate | Mix/sample changed; percussion, source, and saved base stayed unchanged |
| Base rerun | Identical to original base |
| Source revision: second excerpt at 12 → 14 seconds | Mix/sample changed; percussion unchanged |
| Clip bank | 96,000- and 72,000-frame clips; no mix |
| Nonfinite audio, wrong material identity, occupied destination | Each rejected; no success receipt |

All corresponding WAVs were byte-identical across arms. Receipts recorded explicit parameter overrides, source hashes, material identity, runtime versions, and output hashes. Base mix SHA256: `6c929379517e6fcb2471b70e783e5a2fd350d4db22297153ae8bba29dedb4f9f`.

## Verdict and limits

The preregistered necessity condition was not established. Defer making the proposed entry/result contract mandatory. Ordinary Python supported this bounded workflow; neither a required arrangement object nor a universal work format was needed.

Validation, receipts, and process isolation operated independently of the fixed entry. This demonstrates separability, not that these local helpers already deserve core APIs. A fixed entry could still help a generic caller; that benefit was not measured.

Both arms were authored together and share musical logic. This is not an independent Agent trial, usability comparison, listening evaluation, live-session test, or test of stateful range audition. Receipts are bounded inventories, not complete dependency discovery. Failure tests do not establish crash-safe transactions.

The existing functional-entry plan remains a proposal whose mandatory-contract premise needs reconsideration. This probe does not implement or approve that plan.

Scratch evidence: `/tmp/tactus-entry-format-probe-lXB2D6/` contains preregistration, scripts, results, receipts, and local audio. Scratch is disposable; audio was not published.
