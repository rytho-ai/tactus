# Tactus Code — plan

> 2026-09-16 · Short status index. Design lives in `thoughts/`; implementation plans live in
> `plans/`; shipped behavior lives in Git.

## ✅ Shipped

- **Independent repository bootstrap** — local Git repository, installable Python package,
  minimal CLI, tests, and documented code-as-source-of-truth hypothesis. See
  [`repository bootstrap`](plans/2026-09-16-repository-bootstrap.md).

## ▶ Next

- **Choose and pre-register one Music Agent OS vertical slice** — the first build should cover a
  real analysis → arrangement → custom DSP → mix/stems/MIDI → revision workflow. Compare it with
  the existing Tactus path before promoting shared abstractions. No production model has been
  selected by the bootstrap.

## ⏸ Future — evidence-gated

- **Arrangement Graph and replay contract** — only after the first workflow shows which musical
  structure must survive compilation and graph-only rendering.
- **Additional runtimes or languages** — only after Python-first workflows expose a concrete
  limitation that cannot be solved within the existing source model.
