# Real media inputs — plan

> Generated: 2026-09-16 · Source: real-source chop-flip dogfood · Grounding: `Project.asset`, `MaterialStore.import_file`, build receipt, and the existing production-slice tests

> Retired 2026-09-24: `Project.file`, `Project.asset_region` and the arrangement prototype were
> removed at Paul's request. See the [retirement plan](2026-09-24-retire-arrangement-prototype.md).
> This plan retains the original problem and verification evidence, not supported APIs.
> The paths in the historical file table below use the former package name.

## Context

The current `Project.asset` imports an entire audio file into the material store, requires its
sample rate to match the project, and records an audio source hash. A one-bar extraction from the
265-second Music Agent OS source materialized 67 MB of unused source audio. The original
workflow also reads a beat-grid `.npy`: a scratch build proved that this sidecar influences a
computed start time but is absent from both the compiled input list and receipt.

The aim is to make these two source dependencies explicit without adding beat-grid, sampling
style, or DSP-specific authoring objects. The public `Project.asset(path)` behavior and graph
format version remain compatible.

## Resolved questions

| Question | Decision |
|---|---|
| Non-audio sidecars | Add a generic `Project.file(path)` that validates project-local ownership and records a source hash. The caller chooses how to parse it. |
| Audio extraction | Add `Project.asset_region` alongside unchanged `Project.asset`; decode/materialize only the requested region while hashing the source file. |
| Sample-rate mismatch | Keep the explicit error for now. No low-quality implicit resampling; an import-conversion policy needs a separate fidelity test. |
| Compiled replay | Continue embedding only the selected PCM region; graph-only rendering must not need the source or sidecar. |

## Approach

1. Reuse one project-local file validation and streaming SHA-256 helper in `Project.file` and
   `Project.asset`. Register non-audio files in the graph's `inputs` list with a `kind` marker and
   source hash, and echo declared inputs in the receipt. Retain existing audio input fields for
   compatibility.
2. Add `Project.asset_region` backed by `MaterialStore.import_file` start/duration seconds. Seek and read only
   the bounded frames through SoundFile; reject invalid/out-of-range/empty ranges. Store the
   selected PCM, not the whole audio. Put the selected bounds in the registered audio input.
3. Add focused tests: sidecar declaration/hash in graph, bounded-source material size and
   decoded content, invalid range, unchanged whole-file import, and graph-only replay after
   source quarantine. Run the actual local source/beat-grid scratch song through the CLI.

## Critical files

| File | Role and planned change |
|---|---|
| `src/tactus_code/project.py` | Own declared source paths, hashes, and the author-facing file/region API. |
| `src/tactus_code/material.py` | Decode and materialize only requested source frames. |
| `src/tactus_code/build.py` | Include the same declared-input inventory in the receipt. |
| `tests/test_production_slice.py` | Verify public API and replay contracts. |
| `README.md` | State the new input behavior and the still-explicit rate constraint. |

## Verification

- Run `uv run pytest`, `uv run ruff check .`, and `uv build`.
- Build scratch Music Agent OS clip with the actual beat grid via `Project.file` and a bounded
  `Project.asset`, inspect graph inputs/material sizes, and render after source quarantine.
- Confirm generated state remains non-authoritative and no source files enter Git.

## Out of scope

Pitch-preserving warp, source-rate conversion, drum-loop acquisition, custom 808 production,
mix effects, MIDI export, and the Python + Git versus Tactus Code A/B. Those remain in the parent
production-slice plan and require their own acceptance evidence.
