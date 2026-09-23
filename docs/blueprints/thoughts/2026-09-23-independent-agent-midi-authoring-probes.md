# Two independent-Agent MIDI authoring probes

> 2026-09-23 · This evidence feeds the pending Tactus MIDI authoring decisions back to Paul; it is not API approval.

## Question and locked design

Two forks were tested: whether an optional endpoint-warp helper helps Agents edit musical time, and whether Symusic helps Agents more than task-local Python records plus Mido for MIDI revisions. The user approved eight independent Agent attempts: two forks × two conditions × two tasks. Each attempt used a fresh `gpt-6-luna` context at max reasoning, saw one task and one condition, and saved its first completed source as `initial.py` before testing. Agents were told not to inspect other conditions or the root checker. The root independently reran every first and final submission.

The preregistration, stored with the disposable fixtures, fixed the verdict rule before dispatch: a positive signal required at least equal first-pass correctness, a concrete reduction in errors or repair work, and no regression on the exception task. Equal correctness and repair burden meant **no demonstrated benefit**, not equivalence. `revise()` line count was secondary. Product code was read-only.

## Method

For the time-helper fork, both arms received the same immutable Python `Note`/`Production` data and Mido export. Only arm H had access to a *small, optional* `warp_notes(notes, map_time, predicate)` helper that maps each selected note's original start and end, then recomputes duration. T1 applied a 5/4 piecewise warp to lead notes, including one crossing the anchor. T2 moved selected lead starts while one exceptional note had to keep its original end. The helper was optional in T2.

For the representation fork, both arms started from Python source that constructed semantically identical 480-PPQ material. Arm P used task-local immutable Python records with a shared Mido exporter; arm S used Symusic 0.6.0 Score/Track/event objects. R1 edited later notes, one CC64 pedal-off, and tempo; R2 edited pitch, velocity, two note ends, and one pitch-bend position. Both tasks required all unrelated events to remain unchanged. Before dispatch, the root verified that the two representation baselines had identical normalized MIDI events.

The root checker parsed exported MIDI with Mido 1.3.3, normalized zero-velocity note-on as note-off, and compared exact tick positions, note pitches/velocities, CC64, pitch bends, tempo, meter, and 480 ticks/quarter. It did not compare file bytes. All fixtures, run outputs, and the checker are disposable under `/tmp/tactus-agent-midi-probes.AN1ICV/`.

## Results

| Task | Plain Python arm | Helper / Symusic arm |
| --- | --- | --- |
| T1: piecewise time warp | Pass first try; `revise()` 13 LOC | Helper used; pass first try; 9 LOC |
| T2: exceptional note end | Pass first try; 16 LOC | Helper available but not used; pass first try; 14 LOC |
| R1: notes, pedal, tempo edit | Python records + Mido: pass first try; 26 LOC | Symusic: pass first try; 14 LOC |
| R2: pitch, duration, bend edit | Python records + Mido: pass first try; 22 LOC | Symusic: pass first try; 15 LOC |

All eight first submissions passed independently when rerun by the root. All eight final submissions were byte-identical to their own first submissions; every repair count was zero. The T1 helper solution centralized endpoint arithmetic; the T2 helper-arm Agent chose plain Python for the exception. Symusic edits were shorter on both representation tasks. These LOC values describe each Agent's `revise()` body only: they omit the shared helper, task-local dataclass/export adapter, and Symusic library implementation, so they are not total system-cost comparisons. Differences in individual coding style also affect LOC.

## Verdict and next evidence

**Neither fork met the preregistered positive rule.** Both conditions in both probes tied on first-pass correctness and repairs, so this pilot does not demonstrate an Agent reliability advantage for the time helper or Symusic. The narrower evidence is that the helper was usable and optional, Symusic can express these edits concisely, and plain Python + Mido handled all tested tasks correctly.

This was one fresh Agent per task/condition, with two small synthetic tasks per fork and no repeated runs for a task/condition. It did not evaluate creative quality, large productions, arbitrary third-party MIDI, channel/program fidelity, semantic interpretation of duplicate same-pitch notes, token cost, or wall-time latency. The checker compared event content but did not test every possible simultaneous-event ordering. A future reliability test should use harder, repeated cross-module edits or imported performances only if those are real Tactus target workloads; otherwise the simpler interpretation is that both paths are sufficient for the present task class.
