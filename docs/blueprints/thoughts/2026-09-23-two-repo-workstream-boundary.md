# Tactus Code is the active code-first workstream, not yet a replacement release

> 2026-09-23 · Working repository boundary. New Agent-first, code-as-source-of-truth
> experiments and their first production slice proceed in `tactus-code`; the existing
> `tactus` repo remains a reference for proven mechanisms and an independent product.

## The call

Develop the new Python-first production direction in `tactus-code`. Reuse or study the old
`tactus` implementation when a concrete seam needs it, but do not make its `Session`/`Track`
facade, operation history, or real-time-oriented architecture mandatory in the new authoring
model. The old repository is not being deleted, renamed, or silently declared obsolete.

This is a **workstream choice**, not an announcement that `tactus-code` is already an
API-compatible successor or the production replacement. The comparison gate remains a real
musical workflow and Paul's listening judgment, as recorded in the
[`code-first production slice`](../plans/2026-09-16-code-first-production-slice.md).

## How the repositories relate

- `tactus-code` owns current experiments in Functional Python/NumPy authoring, derived
  production graphs, material identity, stateful and transactional audition, and effect-host
  integration. Its current capabilities and limits are described in its [README](../../../README.md).
- `tactus` supplies tested examples of musical time, routing, effects, source editing, and
  compiled replay. Consult or port a mechanism when the new workflow actually needs it;
  do not treat the old board as the new project's status index.
- Each repo keeps its own Git history and `docs/blueprints/plan.md`. The active status of the
  code-first experiment belongs in the [`tactus-code` board](../plan.md); the old board should
  not be rewritten to imply a migration that has not been accepted.

## Evidence and unresolved decision

The existing [`tactus-code` README](../../../README.md) already says the repos run side by side,
the old implementation is a reference, and replacement must be decided from the same real
production workflows. The recent [Functional Python](2026-09-21-functional-audio-authoring-core.md),
[Pattern/temporal](2026-09-22-python-pattern-authoring-boundary.md),
[audition](2026-09-21-stateful-audition-first.md), and
[effect-host](2026-09-23-effect-hosting-boundary.md) findings give the new workstream a
more specific direction. They do not close the real-production A/B or establish release
parity. A formal replacement, migration, or retirement decision is deferred until that gate.
