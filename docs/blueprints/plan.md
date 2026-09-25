# Tactus — plan

> 2026-09-25 · Short status index. Principles live in `../positioning.md`; current approaches
> live in `../design.md`; design history lives in `thoughts/`; implementation plans live in
> `plans/`; shipped behavior lives in Git. This is the sole active Tactus product, formerly
> `tactus-code`; `tactus-daw` is a reference implementation. See
> [`product succession`](thoughts/2026-09-23-tactus-product-succession.md) and the current
> [`product responsibility`](thoughts/2026-09-24-product-responsibility.md).

For implementation decisions, read the
[product positioning and principles](../positioning.md), then the [current design](../design.md)
for chosen approaches and undecided interfaces. The dated
[implementation inventory](thoughts/2026-09-24-implementation-evidence-inventory.md) maps earlier
experiments to remaining work; it does not set the priorities on this board. Agents writing a
work use the [`tactus-authoring` skill](../../skills/tactus-authoring/SKILL.md).

## ✅ Shipped

- **Tactus product succession** — former `tactus-code` now owns the repository, Python import,
  distribution, and CLI name `tactus` at `0.1.0`. Legacy implementation and history are retained
  separately. See [`handoff plan`](plans/2026-09-23-tactus-product-handoff.md).
- **Independent repository bootstrap** — installable Python package, CLI, tests, and the
  code-as-source-of-truth hypothesis. See the [current README](../../README.md).
- **Default scientific stack** — NumPy, SciPy, SoundFile, pyloudnorm and librosa are base
  dependencies with a lock. See [foundation evidence](plans/2026-09-24-implementation-foundation.md)
  and [analysis dependencies](thoughts/2026-09-23-analysis-core-dependencies.md).
- **Functional entry and CLI** — `render(*, ...)` returns named audio; `tactus.run` /
  `tactus run` own isolated execution, parameter binding, PCM24 delivery and receipts. The
  Project/Track prototype and its commands were retired at Paul's request (`9feccdd`). See the
  [entry plan](plans/2026-09-24-functional-production-entry.md) and the
  [retirement plan](plans/2026-09-24-retire-arrangement-prototype.md). The authoring boundary
  (Functional Python, optional temporal and Pattern helpers, no mandatory Track/Session model)
  is recorded in [`functional authoring`](thoughts/2026-09-21-functional-audio-authoring-core.md)
  and [`optional clock`](thoughts/2026-09-23-optional-clock-temporal-abstraction.md).
- **Code-first vertical slice** — `examples/real-chop-flip/` produces a real-source eight-bar
  piece end to end: warp, authored drums/bass, effects, a bass-level candidate and Paul's pick
  (version A). It runs through `render()` with outputs sample-identical to the earlier path.
  Closed on 2026-09-25: its purpose, proving the code-first path, is met and exceeded by later
  work. Two remainders were folded elsewhere rather than pursued: sonic parity with the Music
  Agent OS version is no longer a target, and MIDI is exercised by phonon-ballad (SFZ) and the
  Pedalboard probes (VST3). See the [slice plan](plans/2026-09-16-code-first-production-slice.md)
  and the [real-source probe](thoughts/2026-09-24-real-source-warp-boundary-probe.md).
- **Second production, pinned inputs and the authoring skill** (`f2c7e4e`, `8c1e7fe`) —
  `material()`/`tool()`, the shared input pool, `tactus material add`, receipt v2, and
  phonon-ballad on `tactus run`. Six combinations are sample-identical to the pre-port
  baselines. The `tactus-authoring` skill is symlinked into `~/.claude/skills` and
  `~/.codex/skills`. Fresh-Agent trials passed; a 69-file pack probe found per-file pinning
  sufficient; a shared read/resample helper was declined. See the
  [plan](plans/2026-09-24-second-production-through-run.md), the
  [trial](thoughts/2026-09-24-fresh-agent-authoring-trial.md) and the
  [many-materials probe](thoughts/2026-09-24-many-materials-probe.md).
- **Git revision record and candidate keeping** (`d102e83`, `e8d4412`, `59ae34a`) — receipts
  record Git `HEAD`, dirty state, untracked sources, a restoring `source.patch` and
  `elapsed_seconds`. Agents keep a candidate by editing defaults and committing with Git, after
  checking the receipt against the current source. Approved mixes are archived in the pool.
  `tactus accept` was built and then shelved on `shelved/tactus-accept`, because clear guidance
  alone gave 6/6 correct disclosures. See the [plan](plans/2026-09-24-audition-acceptance.md),
  the [accept probe](thoughts/2026-09-24-accept-necessity-probe.md) and the
  [Git workflow probe](thoughts/2026-09-24-git-workflow-probe.md).
- **Readable outputs and range audition v1** (`0b342a0`, `6e938d4`) — outputs are named
  `<name>-<sha8>.wav`. Section listening started as `tactus run --range`, and
  `tactus excerpt` later replaced it (see below). A full-song dogfood showed an Agent's self-windowed preview differing
  from the song by up to 100% per bar. See the [naming probe](thoughts/2026-09-25-output-naming-probe.md),
  the [dogfood](thoughts/2026-09-25-full-song-dogfood.md) and the
  [range plan](plans/2026-09-25-range-audition.md).
- **Effects and VST3 via Pedalboard, A6 v1** (`3577f99`) — Pedalboard is a base dependency.
  `tactus.fx` provides `set_param`, `process_automated` and `render_instrument`, and the skill
  has an "Effects and plugins" section. A blind reverb test preferred Pedalboard over
  hand-written DSP. Four probe rounds cut mean Agent cost from about 183k to 137k tokens and
  removed hand-rolled loops and silent start transients. See the
  [blind A/B](thoughts/2026-09-25-reverb-blind-ab.md) and the
  [iterations](thoughts/2026-09-25-pedalboard-agent-iterations.md).

- **pytimestretch as the stretch base (B2)** — `pytimestretch` (git revision `ab6871a`,
  GPL-2.0-or-later, accepted by Paul) is a base dependency and replaces `pyrubberband` plus the
  system `rubberband` executable, so stretch needs no external tool. The skill documents
  `duration_ratio`, explicit `backend` choice and headroom; there is no `tactus.stretch`
  wrapper. real-chop-flip migrated: `drums`/`bass` unchanged, `sample` +1.8 LU and `mix`
  +0.7 LU (Rubber Band 3.3 → 4.0 R3); Paul re-listened to version A and accepted it. The evidence is a
  separate session's consumer probe (`thoughts/2026-09-25-pytimestretch-consumer-probe.md`):
  full-song lengths and beat/pitch control tests passed. An unexplained SFZ bass difference
  from that probe stays a known issue.

- **Folder material and tool identity** — `tree:sha256:` refs pin folders: SFZ instruments
  keep their relative `#include`/sample paths, and a VST3 bundle is one `tool()` call whose
  returned path loads directly. Version-control directories are ignored. The Karoryfer
  swagbass imported in 0.9 s and rendered a note from its materialized folder, and OB-Xf
  loaded from `tool()`. phonon-ballad's `sfz` palette now takes a pinned tree plus a program
  name; it is still unverified for lack of an SFZ piano. `fx.varispeed` and the
  pytimestretch guidance shipped alongside. See the [plan](plans/2026-09-25-folder-identity.md)
  and the [pytimestretch Agent probe](thoughts/2026-09-25-pytimestretch-agent-probe.md).

- **Full-song dogfood 2, excerpt and plugin discovery** — a fresh Agent built a 52-bar song
  with every new piece: a pinned SFZ tree, Pedalboard, OB-Xf, pytimestretch and section
  previews. A full render took 7.9 s (46 s before). Paul found v2 much better after a revision.
  Findings and fixes:
  - `run --range` re-rendered, so an OB-Xf work's preview correlated only 0.42 with its
    candidate. `tactus excerpt` now slices an existing run's saved audio.
  - OB-Xf parameter scales (%, dB, 0–1) and its missing default patch led to a pad about
    40 dB too quiet. `fx.describe`/`format_table` now list values, units and ranges, and
    `set_param` errors show the range. A survey found unit metadata is plugin-specific:
    OB-Xf 64%, Dexed 0%, Cardinal 1%.
  - The skill now asks for per-section levels instead of a peak check.
  See the dogfood in `dogfood/2026-09-25-full-song-2/` (ignored).

## 🚧 In progress

None.

## ▶ Next

1. **Verify `fx.describe` on plugins without unit metadata** — fresh Agents configure Dexed
   (no reported units) and OB-Xf (64% units) using `describe`, range-aware errors and the
   per-section level check, to confirm the scale mistakes from dogfood 2 do not recur.

## ⏸ Future — evidence-gated

- **Render speed at scale: stage caching and parallel stems** — Paul raised it on 2026-09-25:
  render time grows roughly with tracks × effects, and it will matter for works with many
  tracks and real VSTs. Today a 4-stem 2:35 song takes about 46 s, so this is deferred. Notes
  for when it returns:
  - Caching unchanged stages is the most effective lever for many tracks, because a revision
    usually touches one or two. The functional authoring discipline (named stages with
    explicit inputs) is what makes caching safe.
  - Rendering independent stems in parallel is the second lever.
  - Section-only computation helps least, because every track still needs its own warm-up.
  - Any faster path must be verified against a full render; range audition v1 is that
    reference.
  - **First step when it returns:** measure before building. A synthetic 8/16/32/64-track
    work with typical effects (no LLM cost) shows where render time crosses about 1 and
    3 minutes and which part dominates.
  - Trigger: a real production whose `elapsed_seconds` makes revision loops slow (minutes per
    render, or dozens of renders per session).
  Python remains the creative source of truth; a broader graph model is not a required roadmap
  item. See [`temporal conclusion`](thoughts/2026-09-23-optional-clock-temporal-abstraction.md)
  and the [range plan](plans/2026-09-25-range-audition.md).
- **Latency compensation on a real VST3 effect** — `process_automated` shifts out reported
  latency, but it was verified only with a stub chain. Trigger: a latency-reporting VST3 effect
  is available or a work needs one.
- **Temporal helpers (A1)** — time maths was repeated in Agent code (four functions in one
  trial), but no probe or dogfood produced a timing error. Trigger: a work with tempo changes or
  a real conversion error.
- **Commercial VST and broader host compatibility** — no confirmed licensed commercial VST
  is available on this machine; test the actual target plugin when one is available. Dynamic
  latency, complex routing, crash isolation and external sidechain remain open. See
  [`effect-host boundary`](thoughts/2026-09-23-effect-hosting-boundary.md).
- **Allow Python 3.13** — `requires-python` is `>=3.12,<3.13` because the pedalboard 0.9.24 and
  0.9.25 cp313 Linux wheels run AVX-512 code unguarded at import (`vinserti64x2`) and crash on
  CPUs without AVX-512 (this machine's i5-13600K). 0.9.23 cp313 and 0.9.25 cp312 work. The
  upstream fix (spotify/pedalboard PR #511) merged on 2026-09-23 but is unreleased. Trigger: a
  pedalboard release containing it; install it on 3.13 here, run `import pedalboard` and the
  test suite, then relax the pin.
- **Additional runtimes or languages** — only after Python-first workflows expose a concrete
  limitation that cannot be solved within the existing source model.
