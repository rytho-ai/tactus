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
  `tactus accept` was built and then shelved, because clear guidance alone gave 6/6 correct
  disclosures; after a 3/3 re-run on the trimmed skill its branch was deleted on 2026-09-26
  ([why](thoughts/2026-09-26-delete-tactus-accept.md)). See the [plan](plans/2026-09-24-audition-acceptance.md),
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
  - Verified afterwards: two fresh Agents configured Dexed (0% units) and OB-Xf on the right
    scales and hit their level targets within ±1 dB; see the
    [discovery probe](thoughts/2026-09-25-plugin-discovery-probe.md).
  See the dogfood in `dogfood/2026-09-25-full-song-2/` (ignored).

- **Value and excerpt probes** — pinned materials and receipts beat plain Python + Git when a
  sample was silently replaced; `tactus excerpt` is not needed for correctness (Agents without it
  sliced saved WAVs exactly, 9/9) and is kept for convenience and traceability. A1's 43-minute
  session was environment contention, not Tactus. See the
  [probe notes](thoughts/2026-09-25-value-and-excerpt-probes.md).
- **`extreme_stretch` (pytimestretch main `e43cc6d`)** — adopted with no Tactus code: the
  dependency rev moved and the skill documents fitting its approximate length, capping its
  peaky level and its per-process seeded randomness. Paul's listening verdict is pending. See
  the [listening note](thoughts/2026-09-25-extreme-stretch-listening.md).

- **Level reporting and `mido`** (`49a51d9`) — over-full-scale output is published clipped
  instead of refused; the manifest (`format_version` 2) and the run result's `levels` report
  `peak_dbfs` and `clipped_samples`. `mido` is a base dependency for `sfizz_render`'s `.mid`.
  Two fresh Agents acted on reported clipping without `np.clip` and wrote MIDI with `mido`; the
  skill's Limiter advice was corrected after the probe. See the
  [plan](plans/2026-09-25-levels-and-midi.md) and the
  [probe](thoughts/2026-09-25-levels-and-midi-probe.md).

- **Full-song dogfood 3, Paul as producer** — an ambient lo-fi work revised over three rounds of
  Paul's notes, relayed verbatim, until he approved v4. Each revision touched at most 2 of 5
  stems (renders 11–17 s). It led to the level-reporting change and `mido`. See the
  [dogfood notes](thoughts/2026-09-25-full-song-dogfood-3.md).

- **Skill scope: using Tactus only** — Paul (2026-09-25): the skill should not teach music-making.
  It dropped mixing advice and third-party how-to (355 → about 225 lines), keeping library
  behavior only where it changes Tactus results; the earlier per-section level snippet and the
  "Effects and plugins" guidance went with it. Recorded in positioning §1. A rerun of the
  plugin-discovery task on the trimmed skill passed (correct scales, levels on target). See the
  [discovery probe](thoughts/2026-09-25-plugin-discovery-probe.md).

- **Stage reuse for parameter candidates** (`4df3d25`) — completes transactional audition:
  `@stage` plus `tactus run --reuse` reuses a stage whose source, dependencies, runtime and
  arguments are unchanged, re-checking its tools and replaying its inputs into the receipt
  (`stages`, `reuse`; receipt `format_version` 3). The value is controlled comparison, not
  speed: with reuse, 3/3 fresh Agents delivered a bass-only candidate with every other stem
  byte-identical, versus 0/3 without, where the OB-Xf pad re-rolled; costs were equal. A
  one-parameter candidate on dogfood 3 took 2.6 s instead of 20.1 s. See the
  [plan](plans/2026-09-26-stage-reuse.md), the
  [necessity probe](thoughts/2026-09-26-fast-audition-necessity.md) and the
  [Agent probe](thoughts/2026-09-26-stage-reuse-probe.md).

- **Rebuilding a work elsewhere (A7)** (`16de3c4`) — receipts (`format_version` 4) record the
  running `environment` (prefix and its project's `uv.lock`) and `package_sources` (VCS commit, or
  an editable directory's Git commit and dirty state), which were missing for works outside the
  repo. Acceptance: a fresh Agent rebuilt the approved dogfood 3 work in a new directory from
  its receipt alone; every deterministic stem matched byte for byte, and the OB-Xf pad was
  within 0.7 dB. See the [plan](plans/2026-09-26-environment-attribution.md) and the
  [acceptance](thoughts/2026-09-26-rebuild-elsewhere.md).

- **Every work is a uv project** (`efa37e9`, `8953e90`) — `tactus init DIR` scaffolds a work with
  its own `pyproject.toml` pinning Tactus (running install's origin, `--tactus-path`, or
  `--tactus URL@REV`), Tactus's `requires-python` (uv did not enforce `<3.13` transitively and
  built a 3.13 env where Pedalboard crashes), a `.gitignore`, a `uv.lock` and a Git repository.
  Works then run and `uv add` packages inside their own environment. Two fresh Agents created
  and rendered a work with an extra package from the skill alone. See the
  [plan](plans/2026-09-26-work-as-uv-project.md) and the
  [probe](thoughts/2026-09-26-work-as-uv-project-probe.md).

- **Optional musical time, `tactus.timing` (A1)** (`943c9b2`) — tempo maps with steps and three
  gradual shapes (`ramp`, `ramp-time`, `smooth`), meters, `swing`, `Groove`, `place` and envelopes;
  beats are 0-based quarter notes. A three-way design probe found tclock v3 best (0 errors, against
  7 with no helper and 7 with v2). Two fresh Agents then used the shipped module from the skill
  alone with no time errors, and three more did quantize strength, note-value delays, seeded
  humanize and live-coding patterns with it plus plain Python, so no further time helpers were
  added. See the [plan](plans/2026-09-27-tactus-timing.md), the
  [comparison](thoughts/2026-09-27-temporal-design-comparison.md) and the
  [gaps probe](thoughts/2026-09-27-timing-gaps-and-repetition.md).

- **Mechanical helpers** — `tactus.load_audio` (read, channel conversion, exact resample,
  leading-silence trim), `timing.add_at` (in-place mix, head/tail cut, never wraps; replaces
  `place`), `timing.markers`, `timing.quantize` (ties go later), `timing.note_seconds` and
  `fx.fit_rms` (a smooth look-ahead gain envelope instead of a clipping limiter). A two-arm probe
  found both arms error-free but the helper arm used 21% fewer tokens and a third less code; a
  fresh Agent then found and used all six from the reference alone, all items correct. See the
  [plan](plans/2026-09-27-mechanical-helpers.md) and the
  [probe](thoughts/2026-09-27-mechanical-helpers-probe.md).

- **`timing.euclid` and `timing.cycle`** — Bjorklund hit steps with Tidal's left rotation, and a
  figure's hit steps run continuously across bar lines, both as step-index tuples. The only
  conventions two Pattern probes found worth owning; a fresh Agent passed all five rounds of the
  idioms brief using them and wrote no Bjorklund of its own. See the
  [plan](plans/2026-09-27-euclid-and-cycle.md).

- **MIDI performance acceptance (B1)** — measured `fx.render_instrument` with a real plugin:
  velocity, sustain pedal, raw tuples and over-length messages behave; pitch bend took effect at
  the start of Pedalboard's 8192-frame block, up to 170 ms early. Three fresh Agents delivered
  those early bends without noticing (4/6 errors each), so `render_instrument` now renders in
  64-frame blocks (`buffer_size`, the same idea DawDreamer uses, without its engine); three more
  Agents then scored 0/6. See the [acceptance](thoughts/2026-09-27-midi-acceptance.md).

- **Categorized analysis (`tactus analyze CATEGORY NAME`)** — one function per analysis, CLI
  subcommands generated from them, three-level `--help` (categories → analyses → definitions),
  results carrying `analysis`, `revision` and params. `level`: loudness, true peak, sample peak,
  RMS, clipping. `spectral`: spectrum, band levels, power-weighted centroid, interpolated peaks,
  STFT (`.npz`). From two frequency probes (with no definitions given, the shared CLI gave 0
  errors vs 3 and one set of numbers); a fresh Agent passed from the skill alone. See the
  [plan](plans/2026-09-27-analysis-contracts-and-frequency.md).
- **Loudness and peak analysis (`tactus.analysis`, `tactus analyze`)** — integrated LUFS
  (pyloudnorm), true peak (4× oversampled), sample peak, RMS and flat-top runs, as functions and
  as a command over WAVs or run/excerpt directories, reporting values only. From the audio-analysis
  probe (tools halved tokens); a fresh Agent passed both audit rounds from the skill alone. See the
  [plan](plans/2026-09-27-audio-analysis-measurements.md).

## 🚧 In progress

None.

## ▶ Next

- **Unified basic audio analysis (level and spectral shipped; onsets, pitch, beats open)** — a three-arm probe found
  Agents with only the installed libraries (pyloudnorm, librosa, scipy — all three used them)
  made 71 errors, all in onset detection, at about 230k tokens; CLI and function arms made 0
  at about 100k. CLI and functions tied: one implementation, two doors (functions and a
  `tactus analyze` command), reporting values, not verdicts. Three parts, when resumed:
  1. Loudness and peaks: **shipped** as `tactus.analysis` and `tactus analyze` (see Shipped).
     Paul narrowed analysis to loudness and frequency; DC, correlation and dropout checks are
     dropped.
  1b. Frequency: **shipped** as the `spectral` category (see Shipped). Pitch (`fundamental`,
     f0 over time) failed unseen-material validation (47.5% within ±50 cents; sub-octave SFZ
     layers defeat every method) and is not shipped. See the
     [probes](thoughts/2026-09-27-frequency-analysis-probes.md). Flat-top counts could
     also go into `tactus run`'s `levels`, closing the full-scale item in Future.
  2. Onsets: **failed validation, not shipped.** On 9 unseen loops built from real one-shots the
     prototype scored F1 0.12 at 2 ms (librosa tuned 0.27, at 10 ms 0.76); it had overfit the two
     synthetic test loops, so the probe's accuracy gap was an artifact. Precise onset detection is a
     research problem; revisit only with a method that passes the same unseen-material test.
  3. Beat tracking (tempo, beats, downbeat, tempo changes): Paul flagged it as essential for a
     DAW (warp, slicing, aligning loops); not yet tested. Annotate material, compare librosa with
     dedicated trackers (check licence and install), then a two-arm Agent probe. The output
     would be a beat grid pinned as a material, per the frozen-analysis rule.
  Key, chords and structure stay out of scope. See the
  [probe](thoughts/2026-09-27-audio-analysis-probe.md).
## ⏸ Future — evidence-gated

- **Marker warp (B2 remainder)** — fixed-ratio stretch shipped; stretching between markers (warp
  like a DAW) has no chosen binding, map format or length-error policy (design.md lists it as
  undecided). It pairs with beat tracking in the parked analysis item, whose output would be the
  markers. Trigger: a work needs audio aligned to a beat grid or markers.
- **Comparison and delivery report (C3 remainder)** — beyond measurements: candidate IDs, regions,
  mapping playback position to source audio, playback-only level matching (design.md
  "驗證與觀察"). Trigger: a real revision flow where comparing candidates is the friction.
- **Own DSP productization (C2)** — Faust/Numba ports and AOT/WASM parity exist as probes;
  portable state/buffer conventions and a native export toolchain are undecided. Trigger: a work
  needs a processor no library provides.
- **Pattern helpers (C1), closed 2026-09-27, re-probed the same day** — a two-arm probe with a multi-part piece, layered
  periodic rules and two revision rounds found no gain: 0 errors in both arms, the Pattern arm
  used 5% more tokens and changed about as many lines per revision (74 vs 76); only final source
  was shorter (139 vs 195 lines). Plain Python with `tactus.timing` expresses Euclidean,
  rotation, every-n, cross-bar cycles and seeded probability. Trigger: repeated, divergent
  pattern code in a real production, or a situation the probe did not test (much longer works,
  hand-offs). See the [probe](thoughts/2026-09-27-pattern-helpers-probe.md).
  A second probe with idioms Agents already know (a NumPy grid and a Tidal/Strudel-style
  mini-notation, both our own, no packages) and Tidal-worded briefs over five live-coding rounds
  met the pre-registered bar narrowly: plain Python made 2 errors (one Agent reversed Tidal's
  rotation direction once), both idiom arms 0; tokens within 10%, revision lines -16% (Tidal)
  and +9% (NumPy). The value seen is owning conventions (Bjorklund with Tidal rotation, cycles
  across bars, extension-stable seeded probability), not a pattern system. Paul chose the
  minimal addition: `timing.euclid` and `timing.cycle` shipped (see Shipped); the pattern system
  stays closed. See the [idioms probe](thoughts/2026-09-27-pattern-idioms-probe.md).
- **License before any public release** — pytimestretch main is GPL-2.0-only (libpaulstretch is
  GPLv2) while pedalboard is GPLv3, and the two cannot be conveyed together; Tactus itself
  declares no license yet. No issue while the repo is private and internal. Preferred fix when a
  release is planned: split PaulStretch out of pytimestretch as an optional package so the core
  returns to GPL-2.0-or-later. Parked by Paul on 2026-09-25. Trigger: planning any public release.
- **Report samples sitting at full scale** — clipping inside a plugin (Pedalboard's `Limiter`
  hard-clips at 0 dBFS) or a work's own `np.clip` reads as 0 `clipped_samples`; the levels probe
  found 23–775 such samples. Deferred by Paul on 2026-09-25. The corrected Limiter wording in the
  skill is also untested. Trigger: an Agent ships audible clipping that the report missed. See
  the [levels probe](thoughts/2026-09-25-levels-and-midi-probe.md).
- **Region-only computation (stateful checkpoints)** — after stage reuse, computing only the
  auditioned region with correct state is the remaining audition speedup. The 2026-09-21 probe
  proved checkpoints sample-exact but found they lose on a single audition and when every edit
  invalidates them; render waiting is 1–10% of real sessions. Trigger: a changed stage itself
  takes over 60 s on a long work. See the
  [necessity probe](thoughts/2026-09-26-fast-audition-necessity.md).
- **Latency compensation on a real VST3 effect** — `process_automated` shifts out reported
  latency, but it was verified only with a stub chain. Trigger: a latency-reporting VST3 effect
  is available or a work needs one.
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
