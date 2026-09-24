# Implementation foundation — plan

> Generated: 2026-09-24 · Source: Paul's request to consolidate the past week's principles and prepare core dependencies before implementation · Grounding: current source, dependency declarations, design thoughts, and existing production-slice plan.

> Foundation work is complete. The subsequently implemented
> [functional entry](2026-09-24-functional-production-entry.md) and
> [prototype retirement](2026-09-24-retire-arrangement-prototype.md) supersede the
> preparation-time gaps and compatibility requirements below. Verification here records
> the earlier foundation pass; the board owns current delivery status.

## Context

Tactus already has a playable prototype, but its required `Project`/`Track` and
`TRANSPORT` interface predates the functional-authoring and optional-clock conclusions.
Design evidence is distributed across dated thoughts. The original production-slice plan
still contains authoring prescriptions superseded by those conclusions.

The working tree already declares and locks NumPy, SciPy, SoundFile, pyloudnorm, and librosa.
This foundation pass consolidates the implementation constraints and verifies that environment.
It does not implement the new runtime or select unresolved public interfaces.

## Resolved questions

- Preserve the existing thoughts as historical evidence. Maintain the principles independently,
  with all definitions and boundaries needed to apply them in the document itself.
- Maintain product positioning and principles in `docs/positioning.md`, following Paul's chosen
  location. Maintain current approaches and execution contracts independently in `docs/design.md`;
  keep historical evidence in thoughts and delivery work in plans.
- Keep current behavior distinct from intended contracts and experimental API candidates.
- Verify the five approved base dependencies without promoting every probed backend to a
  universal dependency. Preserve additional packages already used by local experiments.
- Preserve current source, CLI, and format-v1 artifact behavior during this preparation.

## Approach

1. Maintain self-contained core principles and decision criteria. Connect them from
   AGENTS.md, README, and the existing board. Consolidate current approaches in `docs/design.md`;
   keep implementation gaps and verification here.
2. Add a supersession notice to the original vertical-slice plan where its mandatory authoring
   model conflicts with newer decisions; retain its musical acceptance case.
3. Sync the existing lock with `uv sync --locked --inexact --group dev`. Check imports and
   exercise array processing, audio I/O, loudness measurement, and analysis in a temporary smoke
   check. Run existing pytest, Ruff, and CLI doctor/version checks.
4. Record completion evidence here. Keep runtime implementation status on the existing board.

## Critical files

| File | Role and planned change |
| --- | --- |
| `docs/positioning.md` | Independently maintained, self-contained product and design principles |
| `docs/design.md` | Current approaches, reasons, execution contracts, and undecided boundaries |
| `docs/blueprints/plans/2026-09-16-code-first-production-slice.md` | Explicit supersession of early authoring prescriptions |
| `AGENTS.md`, `docs/blueprints/plan.md`, `README.md` | Core navigation and verified environment status |
| `pyproject.toml`, `uv.lock` | Existing approved base dependencies; verify without reselecting |
| `src/tactus/build.py`, `project.py`, `render.py` | Ground current implementation gaps; no runtime changes in this pass |

## Verification

- Frozen dependency sync and successful operation checks for all five approved packages.
- Existing pytest and Ruff; real CLI version and doctor.
- Resolve new local Markdown links and inspect the diff for accidental edits to prior work.

## Next implementation decision

### Design owner

The [current design](../../design.md) owns dependency choices, authoring and temporal approaches,
material identity, execution, audition, and validation contracts. This plan tracks the
implementation gaps and verification work against that design.

### Implementation gaps

| Concern | Current implementation | Unresolved contract |
| --- | --- | --- |
| Function authoring | `build(project)` with `Project`/`Track` | Minimal function-output contract; probe names such as `render_all` remain candidates. |
| Free time | Required BPM/bars in `TRANSPORT`; beat placement only | Seconds/samples, total duration, and source compatibility. |
| Pinned materials | Hash mutable paths during build and record them in generated receipts | Inline source digests or a tracked material lockfile. |
| Reproducibility | Compiled replay | Source-rebuild randomness, external dependencies, and processor identity. |
| Audition | Compiled mix/stems and mute/solo | Stateful ranges, isolated candidates, guarded promotion, and stale-base conflicts. |

### Next scope

The production slice remains the musical acceptance case. Before changing its runtime,
use the [functional entry and CLI plan](2026-09-24-functional-production-entry.md), which now
specifies the proposed function-output contract and first CLI operation. Implementation has not
started. Temporal helper interfaces and source-pinned material form remain later decisions;
preserve existing examples and replay compatibility where promised. Stateful audition remains
the subsequent product gate recorded on the board.

## Completion evidence

- Maintained principles now live in `docs/positioning.md`, reached from AGENTS.md, README,
  and the board. Current approaches and dependency choices live in `docs/design.md`; implementation
  gaps remain in this plan. The original slice now
  explicitly identifies superseded authoring prescriptions while preserving musical acceptance.
- `uv sync --locked --inexact --group dev` succeeded. The five approved packages were already
  installed; no dependency declaration or lock changes were needed in this pass. Extra local
  experiment packages were preserved.
- NumPy 2.5.3, SciPy 1.18.1, SoundFile 0.14.0, pyloudnorm 0.2.0, and librosa 1.0.0 passed an
  in-memory check: stereo float-WAV roundtrip, 48-to-24 kHz resampling, finite integrated LUFS,
  and finite STFT output with the expected shape.
- Existing pytest: seven passed. Ruff passed. Real CLI version and doctor reported
  `tactus 0.1.0` and the existing bootstrap status.
- New navigation links resolved and `git diff --check` passed. No runtime source was changed.
  Existing overlapping working-tree edits remain preserved and uncommitted.
