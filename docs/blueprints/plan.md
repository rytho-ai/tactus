# Tactus — plan

> 2026-09-23 · Short status index. Design lives in `thoughts/`; implementation plans live in
> `plans/`; shipped behavior lives in Git. This is the sole active Tactus product, formerly
> `tactus-code`; `tactus-daw` is reference-only. See
> [`product succession`](thoughts/2026-09-23-tactus-product-succession.md).

## ✅ Shipped

- **Tactus product succession** — former `tactus-code` now owns the repository, Python import,
  distribution, and CLI name `tactus` at `0.1.0`. Legacy implementation and history are retained
  separately. See [`handoff plan`](plans/2026-09-23-tactus-product-handoff.md).
- **Independent repository bootstrap** — installable Python package, CLI, tests, and the
  code-as-source-of-truth hypothesis. See [`repository bootstrap`](plans/2026-09-16-repository-bootstrap.md).
- **Declared real-media inputs** — `Project.file` records non-audio sidecars, and
  `Project.asset_region` materializes only a requested audio segment. Source hashes and
  selected material identity enter the compiled inputs and receipt; the selected clip replays
  without the original files. See [`real media inputs`](plans/2026-09-16-real-media-inputs.md).

## 🚧 In progress

- **Code-first production vertical slice** — finish the real-source adaptation, including
  pitch-preserving warp, MIDI/groove, effects/routing, and a revision; compare it with the
  existing production path and ask Paul to listen. The synthetic graph-only render and
  bass-only revision already work, but musical parity is open. See
  [`vertical-slice plan`](plans/2026-09-16-code-first-production-slice.md).
- **Agent authoring boundary for that slice** — use Functional Python/NumPy, optional shared
  temporal helpers, and optional local Pattern functions; do not require Track/Bus,
  Session, or Project as the Agent's universal composition schema. See
  [`functional authoring`](thoughts/2026-09-21-functional-audio-authoring-core.md) and
  [`temporal/Pattern boundary`](thoughts/2026-09-22-python-pattern-authoring-boundary.md), with
  the [optional-clock clarification](thoughts/2026-09-23-optional-clock-temporal-abstraction.md).

## ▶ Next

- **Formal stateful and transactional audition** — after the production workflow exposes
  real audition requests, test range/stem correctness and temporary parameter candidates
  against an unchanged source, then promote one guarded source edit. See
  [`stateful audition`](thoughts/2026-09-21-stateful-audition-first.md) and
  [`transactional audition`](thoughts/2026-09-23-transactional-audition.md).
- **Effect integration where the slice needs it** — use Pedalboard + small helpers as the
  initial effect/VST3 path; keep external sidechain explicitly unsupported until a real
  production requires and validates a native extension. See
  [`effect-host boundary`](thoughts/2026-09-23-effect-hosting-boundary.md).

## ⏸ Future — evidence-gated

- **Selective computation reuse** — revisit only when a concrete runtime consumer demonstrates
  a need. Python remains the creative source of truth; a broader graph model is not a required
  roadmap item. See [`temporal conclusion`](thoughts/2026-09-23-optional-clock-temporal-abstraction.md).
- **Commercial VST and broader host compatibility** — no confirmed licensed commercial VST
  is available on this machine; test the actual target plugin when one is available. Dynamic
  latency, complex routing, and crash isolation remain open. See
  [`effect-host boundary`](thoughts/2026-09-23-effect-hosting-boundary.md).
- **Additional runtimes or languages** — only after Python-first workflows expose a concrete
  limitation that cannot be solved within the existing source model.
