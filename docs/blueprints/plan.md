# Tactus — plan

> 2026-09-24 · Short status index. Principles live in `../positioning.md`; current approaches
> live in `../design.md`; design history lives in `thoughts/`; implementation plans live in
> `plans/`; shipped behavior lives in Git. This is the sole active Tactus product, formerly
> `tactus-code`; `tactus-daw` is a reference implementation. See
> [`product succession`](thoughts/2026-09-23-tactus-product-succession.md) and the current
> [`product responsibility`](thoughts/2026-09-24-product-responsibility.md).

For implementation decisions, read the
[product positioning and principles](../positioning.md), then the [current design](../design.md)
for chosen approaches and undecided interfaces. Implementation gaps live in the plans below.
The dated [implementation inventory and checklist](thoughts/2026-09-24-implementation-evidence-inventory.md)
maps the existing experiments to remaining work, completed foundations, and conditional directions;
it does not change the priorities on this board.

## ✅ Shipped

- **Tactus product succession** — former `tactus-code` now owns the repository, Python import,
  distribution, and CLI name `tactus` at `0.1.0`. Legacy implementation and history are retained
  separately. See [`handoff plan`](plans/2026-09-23-tactus-product-handoff.md).
- **Independent repository bootstrap** — installable Python package, CLI, tests, and the
  code-as-source-of-truth hypothesis. See the [current README](../../README.md) and Git history.

## 🚧 In progress

- **Code-first production vertical slice** — finish the real-source adaptation, including
  pitch-preserving warp, MIDI/groove, effects/routing, and a revision; compare it with the
  existing production path and ask Paul to listen. `examples/real-chop-flip/` now delivers a
  real-source eight-bar production through `render()`, including warp, authored drums/bass,
  local filtering/delay and a bass-level candidate. Unrelated outputs remain identical and
  direct Python export matches. Paul preferred version 1/A; the base is retained with its
  existing -5 dB bass default. A fresh run after removing legacy compatibility reproduced all
  selected WAV hashes without changing source. Full workflow/sonic parity and MIDI remain open.
  Dogfood exposed external comparison handoff and supplementary processor attribution needs.
  Run results and manifest/receipt are readable directly. See the
  ignored `dogfood/2026-09-24-functional-production/report.md`. See
  [`vertical-slice plan`](plans/2026-09-16-code-first-production-slice.md) and the
  [real-source probe](thoughts/2026-09-24-real-source-warp-boundary-probe.md).
- **Agent authoring boundary for that slice** — use Functional Python/NumPy, optional shared
  temporal helpers, and optional local Pattern functions; do not require Track/Bus,
  Session, or Project as the Agent's universal composition schema. See
  [`functional authoring`](thoughts/2026-09-21-functional-audio-authoring-core.md) and
  [`temporal/Pattern boundary`](thoughts/2026-09-22-python-pattern-authoring-boundary.md), with
  the [optional-clock clarification](thoughts/2026-09-23-optional-clock-temporal-abstraction.md)
  and [sampling affordance evidence](thoughts/2026-09-24-sampling-affordance-fresh-agent-probe.md).
  The [functional entry and CLI](plans/2026-09-24-functional-production-entry.md) is implemented
  and verified: `render(*, ...)` returns named audio; `tactus.run` / `tactus run` owns
  isolated execution, parameter binding, PCM24 delivery and receipts. The same caller handles
  mix/stems and unequal-length clips; a real-source production matches its plain-Python WAVs.
  The format is an execution/handoff agreement, with initial support limits explicitly listed
  in the plan. Automatic promotion and stateful range audition remain open.
  The earlier Project/Track arrangement prototype, media-import API and build/render/inspect/diff
  commands have been removed at Paul's request, together with their dedicated example/tests.
  Current verification: 53 tests, Ruff, package build and 9 installed CLI checks passed; selected
  A audio is unchanged. See the [retirement plan](plans/2026-09-24-retire-arrangement-prototype.md).
  The entry plan retains the original implementation and plain-Python comparison evidence.
- **Default scientific stack** — the decision to include NumPy, SciPy, SoundFile, pyloudnorm,
  and librosa is implemented and verified with the existing lock. Audio
  I/O, resampling, loudness, and STFT smoke checks passed; seven tests, Ruff, and CLI checks
  passed. The self-contained principles and supersession notice
  are ready for runtime work. See [foundation evidence](plans/2026-09-24-implementation-foundation.md)
  and [analysis dependencies](thoughts/2026-09-23-analysis-core-dependencies.md).

## ▶ Next

- **Second production through `run`** — port phonon-ballad to `render()`, add pinned input
  materials and declared tools to the receipt, and ship an Agent-facing authoring guide.
  Implementation authorized; in progress. See
  [`plan`](plans/2026-09-24-second-production-through-run.md).
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
