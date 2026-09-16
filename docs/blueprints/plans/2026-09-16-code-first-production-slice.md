# Code-first production vertical slice — plan

> Generated: 2026-09-16 · Source: conversation on code-as-source-of-truth, modular music, and Music Agent OS coverage · Grounding: fresh `tactus-code` bootstrap plus `music-agent-os/lab/chop_flip.py`, `jam.py`, `beatlib.py`, and its older Tactus migration plan

## Context

`tactus-code` currently has only an installable package and a `doctor` CLI. It has no project API,
audio engine, or build artifacts. The sibling `tactus` package can independently replay a compiled
`SongState` and content-addressed audio bundle, but its existing operation/history model is not an
assumed foundation here. The 2026-09-16 graph-only probe also found a real limitation: Python DSP
results replay, while undeclared randomness and processor implementation identity are not honestly
captured for source rebuilds.

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
| `src/tactus_code/project.py` | Small author-facing project/track declarations consumed by example `song.py`. |
| `src/tactus_code/compute.py` | Generic Python media computation and explicit dependency/materialization boundary. |
| `src/tactus_code/material.py` | Content-addressed asset owner used by compute, compile, and render. |
| `src/tactus_code/graph.py` | Versioned compiled arrangement codec; only compiler writes it. |
| `src/tactus_code/build.py` | Executes source, validates declarations, and writes snapshot plus receipt. |
| `src/tactus_code/render.py` | Graph-only mix/stem render and ephemeral audition requests. |
| `src/tactus_code/cli.py` | Existing entry point gains `build`, `inspect`, and `render` without duplicating owners. |
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
