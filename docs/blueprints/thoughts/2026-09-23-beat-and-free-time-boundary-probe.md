# Beat-based and free-time boundary probe

> 2026-09-23 · This evidence feeds the pending time-model decision back to Paul. It tests the current authoring and compiled-render boundary, not a proposed `Composition` API.

## Question and pre-registered rule

Can the current time boundary represent both a beat-based work and a free-time work without invented musical metadata?

Both works must build and render using their own time semantics to support the current boundary. If free-time needs a fabricated BPM or bar grid, compiled replay may still work, but the authoring time contract is insufficient. A WAV file alone does not count as evidence that the time model fits.

## Method

- Build and render the existing eight-bar `examples/chop-flip/song.py` work as the beat-based case.
- Author an eight-second free-time sound miniature: seeded rain texture, two bell strikes, and a swell, placed at irregular absolute-second positions (0.73, 2.41, and 4.85 seconds). It has no musical beat grid.
- Attempt the free-time build without `TRANSPORT`, then encode the same sound at fictitious 60 BPM / two bars and 120 BPM / four bars. Keep sample rate, audio computations, audible placement, and duration fixed.
- Render both compiled variants, compare WAV hashes, rerender one compiled variant, and inspect `tactus-code diff`.

Product code was read-only. The disposable free-time source and all generated audio remained under `/tmp/tactus-time-probe-free/` and `/tmp/tactus-time-probe-*-build/` or `/tmp/tactus-time-probe-*-render/`.

## Results

| Case | Build/render | Observable result |
| --- | --- | --- |
| Beat-based `chop-flip` | Passed | 21.333-second stereo WAV at 48 kHz; three tracks and 41 events. |
| Free-time, no BPM | Build rejected | `song.py must define TRANSPORT with bpm, bars, and sample_rate`. |
| Free-time, fictitious 60 BPM | Passed | Non-silent, 8.0-second stereo WAV at 48 kHz; four tracks and four events. |
| Same free-time work, fictitious 120 BPM | Passed | WAV byte-identical to the 60 BPM version. |

The two free-time mixes and a repeat render of the 60 BPM compiled graph all had SHA-256 `404a291f36feee9b6eb906f880f6c07adfb464d7af21fcd7c552c77bab327a2b`. The free-time mix peaked at 0.267 and had RMS 0.041, so these were not matching empty files.

Although the two free-time renders were byte-identical, `tactus-code diff` reported `transport_changed: true` and all four events changed. The only reason was the alternate fake beat representation: each absolute-second event position had to be doubled when BPM doubled. This makes a non-musical implementation choice look like a musical revision.

## Verdict

**Compiled material replay works for free-time audio, but the current authoring and graph time contract cannot describe it honestly.** A fabricated BPM and 4/4 bar grid enter the graph, and semantically equivalent free-time works appear different in the current diff. The evidence supports separating an authored time model from the renderer's sample coordinate. It does not establish a particular `Composition` class or schema.

The beat-based path remains useful and should not be discarded. A future contract could let a work declare beat-based or absolute-time coordinates, then resolve either to sample positions for the renderer. That is a design hypothesis, not something this probe implemented or verified.

## Limits and next decision

The free-time work is a short original miniature, not a full production or a listening judgment. The beat and free-time pieces differ in content and complexity; the controlled comparison is between the two encodings of the *same* free-time work. No tempo map, rubato, range rendering, stateful effect, source-rebuild reproducibility, or cache behavior was tested. Identical replay hashes establish only this compiled-render case.

Before choosing a schema, test a real production that combines an authored time model with an export request. The next deciding question is whether `beat -> seconds -> sample` and `seconds -> sample` can share a small resolution boundary without forcing either work to change its source-level intent.
