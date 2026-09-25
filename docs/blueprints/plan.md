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

- **Second production through `run`** — implemented: `tactus.material`/`tool`, the shared
  input pool, `tactus material add`, receipt v2 (materials, tools, imported packages, nearest
  lock), and the `tactus-authoring` skill. phonon-ballad and real-chop-flip both run through
  `tactus run`. Every output is sample-identical to the pre-port baselines across six
  palette/drum/candidate combinations. 83 tests and Ruff pass. A fresh sonnet Agent using only
  the skill composed and then revised a lo-fi groove on the first pass; see the
  [trial](thoughts/2026-09-24-fresh-agent-authoring-trial.md). A three-agent probe with a
  69-file drum pack found per-file pinning sufficient at 14–21 materials per work, so no ref
  generator or pack identity is needed. A shared read/resample helper was also declined:
  works legitimately choose different resampling methods, and SoundFile plus SciPy/librosa
  already cover the rest. See the
  [many-materials probe](thoughts/2026-09-24-many-materials-probe.md). Still open:
  - installing the skill for Claude Code and Codex;
  - the `sfz` palette's parity check, which needs an SFZ piano;
  - Paul's listening of the trial output.
  See the [`plan`](plans/2026-09-24-second-production-through-run.md).

## ▶ Next

- **Git revision record and candidate keeping** — shipped in `d102e83`: receipts record Git
  `HEAD`, dirty state, untracked sources, a restoring `source.patch` and `elapsed_seconds`. The
  skill tells Agents to keep a candidate by editing defaults and committing with Git, after
  checking the receipt against the current source and getting re-approval on a moved base.
  `tactus accept` was built and then shelved on `shelved/tactus-accept`: in a 12-Agent A/B
  probe, clear guidance alone produced 6/6 correct disclosures. See the
  [accept probe](thoughts/2026-09-24-accept-necessity-probe.md). A five-scenario Git probe found
  Git use sound but approved audio lost with removed worktrees; the skill now fixes run
  locations and archives approved mixes in the pool. See the
  [Git workflow probe](thoughts/2026-09-24-git-workflow-probe.md).
- **Full-song dogfood and range audition v1** — a fresh Agent produced a 2:35 sectioned song.
  Its self-made section preview differed from the song (88% at the cold-start bar, 50–100% at
  loop-phase bars), so `tactus run --range START:END [--outputs]` now slices a full render and
  is sample-identical to it. Receipts also restore untracked sources (`59ae34a`). Output files
  are named `<name>-<sha8>.wav`. See the
  [dogfood](thoughts/2026-09-25-full-song-dogfood.md) and the
  [range plan](plans/2026-09-25-range-audition.md).
- **Effect integration (A6), now evidence-backed** — the full-song dogfood hand-wrote reverb,
  compression and sidechain in NumPy (the first version was too slow, the first reverb
  sounded metallic, and the improved one doubled render time). Next build candidate;
  SFZ-folder material identity rides with it.
- **Effect integration where the slice needs it** — use Pedalboard + small helpers as the
  initial effect/VST3 path; keep external sidechain explicitly unsupported until a real
  production requires and validates a native extension. See
  [`effect-host boundary`](thoughts/2026-09-23-effect-hosting-boundary.md).

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
- **Commercial VST and broader host compatibility** — no confirmed licensed commercial VST
  is available on this machine; test the actual target plugin when one is available. Dynamic
  latency, complex routing, and crash isolation remain open. See
  [`effect-host boundary`](thoughts/2026-09-23-effect-hosting-boundary.md).
- **Additional runtimes or languages** — only after Python-first workflows expose a concrete
  limitation that cannot be solved within the existing source model.
