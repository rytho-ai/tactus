# Mixed clocks versus ordinary Python probe

> 2026-09-23 · This evidence feeds the pending Tactus time-model decision back to Paul. It tests whether a framework-owned clock model is needed for one mixed-time work; it does not decide the final authoring interface.

## Question and pre-registered rule

Does a work mixing global tempo changes, an independent local BPM, and absolute-time events require a framework-owned clock model, or can ordinary Python resolve the time relationships?

Before the trials, the movement rule was fixed: changing only the global tempo after beat 4 must move later global-beat events and local events anchored to those beats, but not earlier global events, seconds-anchored local events, or absolute events. Changing only the local BPM must move only events using that local clock. Removing the global tempo must still permit absolute events and a seconds-anchored local clock. If direct Python/NumPy and Tactus produce the same positions and audio, this probe cannot claim a framework clock is necessary. The Python/NumPy comparison was added before either variant was run.

## Method

A disposable eight-second miniature used five short, distinguishable tones at 48 kHz:

- `global_early`: global beat 2, before the tempo change.
- `global_late`: global beat 6, after global beat 4 changes from 120 BPM to 90 BPM.
- `local_fixed`: local beat 2 at 140 BPM, anchored to absolute second 1.5.
- `local_follow`: local beat 1 at 140 BPM, anchored to global beat 8.
- `absolute`: absolute second 4.85.

Ordinary Python functions resolved the piecewise global tempo and local clocks. NumPy generated and mixed the tones directly. The same source computations and resolved positions were also sent through current Tactus Code `Project`, `build`, and graph-only `render`, without editing product code. Because that interface still requires `TRANSPORT` and `at_beats`, the Tactus adapter declared fictitious `bpm=60, bars=2` and used one fake beat per resolved second.

Four conditions were run: baseline, post-beat-4 global BPM changed to 100, local BPM changed to 160, and no global clock (only `local_fixed` and `absolute`). The scratch sources and outputs remain under `/tmp/tactus-mixed-time-probe/` for this session.

## Results

Resolved onset positions in output samples:

| Event | Baseline | Global changed | Local changed | No global |
| --- | ---: | ---: | ---: | ---: |
| `global_early` | 48,000 | 48,000 | 48,000 | absent |
| `global_late` | 160,000 | 153,600 | 160,000 | absent |
| `local_fixed` | 113,143 | 113,143 | 108,000 | 113,143 |
| `local_follow` | 244,571 | 231,771 | 242,000 | absent |
| `absolute` | 232,800 | 232,800 | 232,800 | 232,800 |

The graph positions matched direct Python's expected sample positions in all four conditions. Against baseline, the global-only change moved exactly `global_late` and `local_follow`; the local-only change moved exactly `local_fixed` and `local_follow`. Those were also exactly the Tactus stems whose WAV hashes changed. `tactus-code diff` identified those event names but reported `transport_changed: false`, because the graph's transport remained the fictitious 60 BPM in every condition.

Direct Python/NumPy and Tactus rendered the same eight-second mix. The baseline, local-changed, and no-global WAVs were byte-identical between paths. In the global-changed case, overlapping tones differed by at most `1.1920928955078125e-07` in decoded sample value, consistent with Tactus's intermediate PCM24 material quantization; onset positions still matched exactly. The direct no-global path used no global BPM, while its Tactus encoding still contained the fake 60 BPM transport.

## Verdict

**Ordinary Python plus NumPy was sufficient for this work's global tempo map, local clocks, no-global case, and audio rendering.** This probe gives no evidence that Tactus must own tempo-map or local-clock creative logic.

The current Tactus contract does have a concrete defect: it cannot accept already-resolved seconds/sample placement and duration without fictitious BPM/bar metadata. That lie enters the compiled graph; the graph cannot explain whether a moved event followed a global tempo change or a local clock change. The smallest product question is therefore whether Tactus should accept absolute placement and duration while leaving the calculation in source code. A richer clock module should be evidence-gated by repeated authoring or maintenance failures, not inferred from this successful Python calculation.

## Limits and next decision

This is one short original miniature, not an agent-maintenance or listening study. The direct path emitted a mix but did not reproduce Tactus's material store, receipts, source-free replay, or stem-delivery workflow; the result addresses time calculation, not the whole production runtime. The fixture used one piecewise-constant global change and fixed-rate local clocks; it did not test rubato, gradual tempo curves, nested local clocks, stateful DSP, or cache invalidation.

Next, compare two minimal authoring conditions on a real revision: (A) Python-owned clock functions feeding an absolute-placement Tactus interface and (B) a framework-owned clock interface. Keep the work and edits identical, and measure whether B actually reduces Agent mistakes or source-maintenance effort. Until then, do not infer that a clock object is required.
