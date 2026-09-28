# Deterministic instrument regeneration — investigation

## Context

Paul asks whether OB-Xf and SFZ regeneration can be made repeatable, following the clean
handoff trial. Saved-performance replay already works; this investigation must execute the
actual synthesis and compare samples without importing saved stages. Preserve the existing
accepted work, handoff candidates, installed plugins and installed sfizz binary.

## Approach

1. Use small repeated fresh-process renders as failure signals. OB-Xf: compare default state
   against zero slop controls and fixed C RNG initialization. SFZ: reuse the raw MIDI probe,
   increase the failure rate through one-CPU scheduling, and preserve every outcome.
2. Distinguish exposed settings from internal state. Inspect the installed OB-Xf revision
   `1223e6f7b209b9affa91331c26f39d4095a4088e`; the sfizz source candidate is
   `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`. Do not attribute differences between builds to
   a patch without comparing unpatched and patched builds from the same source/toolchain.
3. If settings cannot fix the symptom, test narrowly scoped local native patches: explicit
   repeatable initialization for OB-Xf; a complete background-loading barrier or synchronous
   preload for sfizz. Keep variants and patches isolated; record any sonic trade-offs.
4. Validate successful candidates on the complete production generators and fresh processes,
   including one-CPU SFZ stress. No cache or pinned performance can satisfy this gate.
5. Record findings and exact scope. A successful native prototype is not a shipped Tactus API
   or an automatic replacement of the user's instrument. No external publishing is authorized.

## Critical files

- `experiments/deterministic-instruments/`: probes, native patches, build instructions, evidence.
- `dogfood/2026-09-28-deterministic-instruments/` (ignored): source/build trees and test outputs.
- `docs/blueprints/thoughts/2026-09-28-deterministic-instruments.md`: conclusions and limits.
- `docs/design.md`, `docs/blueprints/plan.md`: update only the verified behavior boundary.

## Verification

- Identical settings and MIDI in independent processes; actual output hashes/sample differences.
- Baseline must reproduce the observed problem; compare the same native revision before/after.
- A passing default/no-slop test alone does not establish general determinism.
- Full-song synthesis repeats must match; preserve parameter/timbre changes explicitly.
- Repository pytest and Ruff for tracked Python changes, plus real native/CLI tests.

## Outcome

Both native prototypes passed. Existing OB-Xf controls failed, while the local initialization
patch gave five identical fresh-process results. sfizz's dispatcher-delay regression failed
before the loading-barrier patch and matched the healthy reference after it, for single-note
and full-bass inputs. Ten production-patch full-bass repetitions also matched. Three new offline
containers regenerated all six full-song outputs identically, without cache/frozen materials.
Bass/drums/keys/textures also matched the previous host baseline. 400 pytest tests passed,
1 opt-in test skipped; Ruff passed. Installed tools and runtime APIs were not changed.
See the [findings](../thoughts/2026-09-28-deterministic-instruments.md) for productization limits.
