# Code-first production vertical slice — plan

> Generated: 2026-09-16 · Source: conversation on code-as-source-of-truth, modular music, and Music Agent OS coverage · Grounding: fresh `tactus-code` bootstrap plus `music-agent-os/lab/chop_flip.py`, `jam.py`, `beatlib.py`, and its older Tactus migration plan

> Progress as of 2026-09-24: functional real-source production and A/B listening are complete;
> Paul prefers the first version A. Broader effect/MIDI integration and sonic parity remain open.
> The Project/Track arrangement prototype has been removed at Paul's request; see the
> [retirement plan](2026-09-24-retire-arrangement-prototype.md). Its descriptions below are historical.

> Authoring supersession (2026-09-24): the mandatory `Project`/`Track`, transport, and
> graph-expansion prescriptions below describe the early prototype, not the current target
> architecture. [Functional authoring](../thoughts/2026-09-21-functional-audio-authoring-core.md)
> and [optional clocks](../thoughts/2026-09-23-optional-clock-temporal-abstraction.md) supersede
> those prescriptions. Preserve this plan's real-production, revision, replay, and listening
> acceptance case; use the [product positioning and principles](../../positioning.md) and
> [current design](../../design.md) when planning the next runtime change. The original
> graph examples and format-v1 replay are historical behavior, no longer supported after
> the explicit prototype retirement.

## Context

### Current execution slice — 2026-09-24

Paul authorized using the completed functional entry for a real production and revision cycle.
Use the existing local Music Agent OS source `CErZvbcaOeE_inst.wav` and its beat-grid sidecar,
already present in ignored dogfood assets. Keep their identities pinned in production source.
The current interface is `render()`, executed through `tactus run`; the historical graph/Track
prescriptions below are superseded as noted above.

Create `examples/real-chop-flip/` as an ordinary Python production: four source bars near
54.1 seconds, pitch-preserving Rubber Band warp to 90 BPM, an eight-bar long-phrase rearrangement,
authored drums and bass, and explicit project-local filtering/delay. The original Music Agent OS
long-phrase approach is a reference; this is a bounded adaptation, not full algorithm/sonic parity.
No new Tactus core API or effect-host integration is required to author this production.

Use the same source to produce a base and a candidate with bass reduced by 4 dB. Record actual
CLI requests/responses under `dogfood/2026-09-24-functional-production/responses/`. Verify source
stability, unchanged sample/drum outputs, changed bass/mix, repeatability in this environment,
and finite, unclipped WAV delivery. Measure duration/peak/LUFS as observations, not taste gates.
Compare direct Python/SoundFile delivery with Tactus on the same musical functions.

Provide a localhost listening page with original source excerpt, base/candidate playback,
aligned A/B switching and optional level matching. Keep all media local and ignored. Record
actual authoring/delivery friction in the dogfood report. Human listening and the choice of
which version to accept remain pending until Paul responds; do not label a proposed candidate
as accepted. After feedback, make the chosen source edit and verify its output against that
candidate. Run pytest and Ruff after production-source changes.

Critical files: `examples/real-chop-flip/{song,chops,rhythm,materials}.py` and README;
the ignored dogfood folder owns captures, generated audio and the listening page. The plan board
records delivered work and the listening gate. Existing runtime source is not changed by dogfood.

#### Execution evidence

The production and bass-level candidate are complete. Both are 22.333-second stereo PCM24
at 44.1 kHz; source and grid identities are pinned. The same source produced a base at
`bass_gain_db=-5.0`, candidate at `-9.0`, and byte-identical base repeat. Sample/drum outputs
remained identical; bass/mix changed. Direct Python/SoundFile export matched every base WAV.
The authored master gain was explicitly raised from 0.85 to 1.5 after the first quiet draft;
final base/candidate measure -18.88/-20.02 LUFS and -3.26/-4.93 dBFS sample peak.

Actual CLI captures, measurements and the listening page are in ignored
`dogfood/2026-09-24-functional-production/final/`; the session's `report.md` records friction.
Confirmed: paired listening required an external page; external transform versions required
supplemental provenance. Applying legacy inspect to a functional manifest also failed, but
Paul clarified that the new workflow does not need to inherit inspect: the run response and
readable manifest/receipt already supply results. Its initial classification as a feature gap
was withdrawn; this is a legacy workflow distinction, not a new inspect requirement. No runtime fix
was made during dogfood. 58 tests, Ruff and whitespace checks passed. Browser transport/A-B
switching passed; that is not a musical listening verdict.

**Listening outcome:** Paul said “我好像喜歡1”, interpreted as a preference for the first
version A. Retain A for this study; its -5 dB bass default already matches production source,
so no musical source edit is needed. A fresh installed-wheel run after prototype retirement
reproduced every selected output hash and the same source inventory. Evidence:
`dogfood/2026-09-24-functional-production/final/responses/selected-a.json` and `selection.json`.
This records a preference between these two takes, not a broad musical-quality approval.
Original Music Agent OS sonic parity, its full effect/drum workflow and MIDI export remain open.

At the time of this plan, `tactus-code` had only an installable package and a `doctor` CLI. The
subsequent prototype implemented `Project`/`Track` authoring, `compute`, declared media inputs,
compiled arrangement/materials, graph-only mix/stem rendering, and diff; those APIs have since
been retired. The former sibling
implementation is now `tactus-daw` and remains a reference, not an assumed foundation. The
2026-09-16 graph-only probe found a limitation that still matters: Python DSP results replay,
while undeclared randomness and processor implementation identity are not honestly captured for
source rebuilds.

The first production case should be a bounded adaptation of Music Agent OS
`lab/chop_flip.py::make_beat`: select and chop a musical source, warp and rearrange it, add drums
and a custom 808 (`lab/jam.py`), process and mix stems (`lab/beatlib.py`), then revise one musical
part. This case exercises the proposed framework without copying its taste rules into the runtime.
The legacy `lab/PLAN_tactus_migration_20260724.md` describes the old API migration; it is evidence
of workflow requirements, not the new architecture.

## Resolved questions

| Question | Decision |
|---|---|
| Authoritative project | Python source tree, declared assets, and dependency lock. Git owns history. |
| Generated state | A derived, read-only arrangement snapshot and materialized assets. Never a second user-edited project. |
| Creative logic | Ordinary Python modules/functions, including NumPy and existing Music Agent OS algorithms. Taste rules stay outside the framework. |
| Framework-owned seams | Transport, named parts/tracks, placement, declared computation inputs/outputs, material identity, routing, render requests, and receipts. |
| First workflow | Bounded `chop_flip.make_beat` adaptation with source chop/warp, custom 808, drums, mix/stems, and one revision. |
| Delivery order | Correct full rebuild and inspectable artifacts first; incremental caching only after dependency identity is proven. |
| Legacy reuse | Consult old Tactus implementations when a specific seam is reached; do not import its package wholesale. |

## Open questions

- **Input fixture and redistribution** — select a locally available, legally usable source/drum
  fixture before recording permanent audio in this repo. This blocks checked-in media, not the
  API/runtime design or scratch-based verification.
- **Subjective A/B judgment** — Paul decides whether the adapted result preserves the production
  intent and remains musically workable. Mechanical correctness alone cannot settle this gate.

## Approach

### 1. Establish one real codebase as the acceptance fixture

Create a separate example music project, not a monolithic library test. Its `song.py` composes
`parts/chops.py`, `parts/drums.py`, `parts/bass.py`, and `mix.py`. Adapt the existing Music Agent OS
algorithms with their musical parameters and output behavior intact; do not replace them with
framework recipes. Record baseline inputs, requested edit, expected stems, output names, and
commands before optimizing the API. Keep large/private audio in a local fixture directory; small
synthetic fixtures may be checked in for deterministic tests.

### 2. Define the smallest authoring and materialization boundary

Add a `Project`/`Track` surface for musical time, named tracks, placements, note events, bus sends,
and output declarations. A part is an ordinary Python function returning reusable event/audio
material; the runtime needs stable identities at the placement/output boundary, not a class for
every musical technique. Add one generic `compute` boundary for arbitrary Python audio generation
or transformation. It accepts explicit media inputs and parameters, creates a content-addressed
result, and records whether the author claims deterministic rebuild or only materialized replay.
No feature-specific `make_808` or `sp1200` framework primitive is added.

### 3. Compile and render through one inspectable build artifact

Execute the project entry point and lower its observed production declarations to a versioned
arrangement snapshot. Record transport, tracks, event identities, placements, material references,
routing, named outputs, and a build receipt containing source/dependency/input hashes and every
computation's reproducibility status. The snapshot and assets are generated under an ignored build
directory; the authored source remains untouched. Render mix and isolated stems from the compiled
artifact in a fresh process, without importing the song source. MIDI and analysis/report outputs
use the same named-artifact mechanism when the selected fixture actually needs them.

### 4. Make revision and reuse observable

Build two versions from Git-owned source: the original and a change confined to one bass part.
Demonstrate that the drum/chop modules remain reusable, their compiled identities survive, and
the audio difference is attributable to the edited part. Provide `inspect` and a semantic
before/after report for tracks, events, material hashes, routing, and outputs. Audition mute/solo
must be ephemeral and must not modify source or compiled state. First rebuilds may recompute
everything; report that honestly. Add selective cache reuse only after unchanged-output evidence
and dependency accounting are sufficient to prevent stale audio.

### 5. Compare with the old path and decide the next abstraction

Run the same production intent using the current Tactus path or the existing Music Agent OS
pipeline. Compare completed musical operations, source-module size, project-specific adapters,
revisions, stems, failure recovery, and human A/B usability. A new framework abstraction is
eligible only when it removes repeated production work across at least two parts/workflows without
constraining their musical algorithms. A single successful demo does not establish universal
Music Agent OS coverage.

## Critical files

| File | Role and planned change |
|---|---|
| `src/tactus/project.py` | Small author-facing project/track declarations and the generic `compute` boundary. |
| `src/tactus/material.py` | Content-addressed asset owner used by compute, compile, and render. |
| `src/tactus/graph.py` | Versioned compiled arrangement codec; only compiler writes it. |
| `src/tactus/build.py` | Executes source, validates declarations, and writes snapshot plus receipt. |
| `src/tactus/render.py` | Graph-only mix/stem render; ephemeral audition requests remain planned. |
| `src/tactus/cli.py` | Entry point with `build`, `inspect`, `render`, and `diff`. |
| `examples/chop-flip/` | Modular acceptance project and commands, using local media inputs. |
| `tests/` | Focused API, codec, material, graph-only replay, and revision tests. |
| `README.md` | Replace bootstrap-only claim only when the vertical slice really works. |

## Verification

1. Run `uv run pytest`, `uv run ruff check .`, package build, and CLI smoke checks after each
   landed phase.
2. Build the same source/declared assets twice in clean processes. Compare the compiled semantic
   snapshot and decoded PCM for mix and every stem; confirm asset hashes and receipt facts.
3. Quarantine `song.py` and original assets, then render from the compiled snapshot and packed
   material store alone. Fail if source code is imported or the original paths are opened.
4. Change only the bass module in Git; verify source diff, semantic diff, unchanged drum/chop
   identities, and audible bass/mix change. No generated file may become authoritative.
5. Run an undeclared-randomness or hidden-file negative control. The build must materialize it
   with an explicit limitation, reject it, or mark it non-reproducible; silent reproducibility
   claims fail.
6. Compare the adapted workflow with its Music Agent OS baseline, including human listening.
   Record missing musical intent and adapter burden rather than declaring success from WAV output.

## Out of scope

- A GUI, source-code round-trip editor, new music DSL, cross-language frontends, universal plugin
  graph, semantic Git merge, custom version store, and a complete Music Agent OS migration.
- Automatic taste, bassline, groove, 808, or mastering decisions inside the runtime.
- Promising incremental rebuilds before dependency tracking proves them correct.
