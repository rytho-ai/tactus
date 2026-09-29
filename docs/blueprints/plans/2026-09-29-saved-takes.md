# Saved takes — plan

> 2026-09-29 · Paul approved using original instruments and preserving chosen performances.
> Grounding: functional runner, input pool/tree, stage reuse, clean-handoff experiment.

## Context

`run.py` publishes PCM24 outputs; `@stage` stores disposable intermediate arrays. Neither
offers a durable, explicitly selected, unquantized performance with generation provenance.
The clean-handoff experiment manually promoted cached pads/bass arrays and copied source
and receipts. Native instrument patches proved causes but are not the product strategy.

## Resolved questions

- Use official instruments. Take playback requires audio and Tactus, not the generator.
- A take is a pinned folder material; source chooses its ref. No mutable take registry,
  automatic acceptance, regeneration fallback, or plugin modifications.
- Preserve original real numeric NumPy samples (dtype and shape) in `.npy`, without clipping,
  normalization, resampling or PCM quantization. Playback checks the requested sample rate.
- Generation remains ordinary `render()`. Optional `takes` names intermediate arrays from the
  same execution that produced the audition outputs. Existing works remain compatible.
- MIDI/patch edits require an explicit new generation run and selection. Old refs remain valid.

## Approach

1. Add `takes.py`, owning candidate publication, validation, save/export and `load_take`.
   Candidates contain audio, metadata, generation receipt, and a snapshot of inventoried
   Python source/nearest lock (plus local pyproject when present). Existing material/tree
   hashing owns storage and integrity. Declared generator assets/tools remain receipt refs;
   the take bundle is sufficient for playback, not a complete generator environment.
2. Extend `render` with optional nonempty `takes` mapping, sharing `sample_rate` with outputs.
   Complete run manifests with takes use version 3; old runs keep version 2. Publish only
   after validation, keep failure cleanup, and teach published-output readers version 3.
3. `tactus take save RUN NAME` verifies and imports the exact candidate into the pool.
   `load_take(REF, sample_rate=...)` resolves the immutable material and never invokes tools.
   `tactus take export REF --out DIR` copies a verified bundle for transfer; existing
   `tactus material add DIR` imports it elsewhere with the same ref.
4. Update authoring reference, README and current design/board. Keep take gain/effects in
   ordinary work code after loading. Source/Git owns choosing, comparing and reverting refs.
5. Exercise official OB-Xf/sfizz on a copy of the full-song work: save raw pads/bass, export,
   import into a fresh pool, rerender without tools/cache, revise bass gain and revert refs.

## Critical files

| File | Role |
|---|---|
| `src/tactus/takes.py` | Take bundle and immutable material lifecycle |
| `src/tactus/run.py` | Optional take validation/publication and source snapshot |
| `src/tactus/cli.py`, `__init__.py` | CLI and Python entry points |
| `src/tactus/excerpt.py` | Read version 3 run outputs |
| `tests/test_takes.py` | Exact playback, provenance, failure and transfer coverage |
| `skills/tactus-authoring/` | Generation, audition, selection, regeneration, transfer |
| `docs/design.md`, `docs/blueprints/plan.md`, `README.md` | Product decision and shipped use |

## Verification

- Round-trip float32/float64, mono/stereo, headroom; no generator on playback.
- Two nondeterministic candidates retained; explicit ref switches and rollback.
- Delete run/source/cache/original pool after transfer; playback and receipt still work.
- Reject missing/corrupt audio/provenance, invalid metadata/rate/name and malformed arrays.
- Failed generation publishes no candidate; existing run/excerpt/reuse contracts remain.
- Full pytest and Ruff; real CLI help/save/export/import plus official-instrument production.
- Verify audio equality and unchanged stems after gain revision. Human musical approval is
  separate; do not label newly generated performances as approved.

## Out of scope

Instrument forks/installation, cross-platform generator determinism, automatic MIDI change
detection, cloud storage, a take browser, and a complete generator dependency exporter.

## Outcome

Implemented on `feat/saved-takes`. The original-instrument full-song trial passed:
all six playback WAVs match the generating run, bass-only gain edits preserve the other
four stems, and selecting an alternative pad then restoring the original ref restores all
six WAVs exactly. Fresh offline containers have no generator tools or stage cache mounted.
See [trial evidence](../../../experiments/saved-takes/README.md).

The existing excerpt rejection test was updated to use unknown version 999 because version
3 is now supported. The initial trial harness used a symlinked plugin bundle, which existing
`tool()` rejects; copying the original bundle fixed the harness without changing runtime or
instrument behavior. No native patch was required and no new take is listener-approved.

Final gates: `uv run pytest -q` — 416 passed, 1 existing opt-in test skipped (236.72 s);
`uv run ruff check .` and `git diff --check` passed. CLI help/save/export/import/run paths
were exercised. Installed OB-Xf/sfizz hashes still match the unpatched originals.
