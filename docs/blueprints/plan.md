# Tactus Code — plan

> 2026-09-16 · Short status index. Design lives in `thoughts/`; implementation plans live in
> `plans/`; shipped behavior lives in Git.

## ✅ Shipped

- **Independent repository bootstrap** — local Git repository, installable Python package,
  minimal CLI, tests, and documented code-as-source-of-truth hypothesis. See
  [`repository bootstrap`](plans/2026-09-16-repository-bootstrap.md).

## 🚧 In progress

- **Code-first production vertical slice** — a playable synthetic-source chop-flip example now
  compiles modular Python into a graph/material store and renders mix plus sample/drums/bass stems
  without source code. Tests verify exact graph-only replay, a bass-only revision, and an honest
  materialized-randomness boundary. It has not yet matched the private Music Agent OS source,
  pitch-preserving warp, effects/routing, groove MIDI, or human A/B acceptance. See
  [`vertical-slice plan`](plans/2026-09-16-code-first-production-slice.md).

## ▶ Next

- **Close the workflow gap** — replace the synthetic fixture with a locally usable, lawful source
  and compare the adapted output with the Music Agent OS production path. Add only the missing
  production seams the comparison actually requires, then ask Paul to listen to the A/B.

## ⏸ Future — evidence-gated

- **Arrangement Graph and replay contract** — only after the first workflow shows which musical
  structure must survive compilation and graph-only rendering.
- **Additional runtimes or languages** — only after Python-first workflows expose a concrete
  limitation that cannot be solved within the existing source model.
