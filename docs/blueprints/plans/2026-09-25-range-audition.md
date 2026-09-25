# Range audition v1 — plan

> Generated: 2026-09-25 · Source: the full-song dogfood (see Context) and Paul's request to make
> section-only listening a Tactus responsibility · Grounding: `src/tactus/run.py`,
> `src/tactus/store.py`, `src/tactus/cli.py`, the dogfood run directories. Status: implemented 2026-09-25; the
> real-chop-flip slice 5.25–9.5 s equals the full render's frames for mix and bass.

## Context

A fresh Agent producing a 2:35 song (dogfood `2026-09-25-full-song`, gitignored) was asked to let
the producer hear only the bridge into the final chorus. It built its own `bar_range` parameter
and threaded a window through every stage. That preview took 5 s against 46 s for a full render,
but it did not match the full song. Aligned at bar 35, gain-matched, and compared per bar
against the same frames of the full render:

- The first bar differed by 88%: the reverb and compressor started cold.
- Bars 4, 8 and 12 of the preview differed by 50–100%: the keys loop restarted at the window
  start instead of continuing its phase.
- Every other bar differed by about 15%: master normalisation and compression saw different
  material.

The Agent reported the preview as verified, based on its own RMS numbers.

This is the failure the [stateful audition](../thoughts/2026-09-21-stateful-audition-first.md)
thought predicted. Its minimal contract makes correctness first: a region audition must match
the full render, and checkpoints or partial computation come later.
[Design](../../design.md) lists range audition as deferred until a production asks for it. This
production asked.

## Resolved questions

- **Correctness over speed.** v1 renders the whole work, then slices. The slice is sample-identical
  to the full render's frames by construction. Partial computation waits for measured need plus
  a matching-output proof.
- **Range in seconds, not bars.** Tactus has no mandatory tempo (positioning §4), so the work or
  Agent converts musical positions to seconds. The runtime rounds each end to the nearest frame
  and records both the seconds and the frames.
- **Hard boundaries.** No fades, pre-roll or tail. The slice is exactly the requested frames.
  Adding a fade or letting a tail ring is a creative choice.
- **Output selection.** An optional output list publishes only named outputs. The default is all.
- **Same entry point.** The range is an option of `run` / `tactus run`, not a new command: a
  range run is still one isolated execution with the same receipt.

## Approach

1. **`run(source, *, out, params=None, range=None, outputs=None)`.**
   - `range` is `[start_seconds, end_seconds]`. Values are finite, `start >= 0` and
     `end > start`. `end` may be null to mean "to the end of each output".
   - `outputs` is a list of existing output names.
   - Both are validated in the request phase where possible; output names and lengths are
     checked after `render`, in the validate phase.
   - The CLI gains `--range START:END` (END may be empty) and `--outputs a,b`.
2. **Slicing in `_execute`, after `_validate`, before publishing.**
   - `start_frame = round(start * rate)`; `end_frame = round(end * rate)`, or the output's
     length when `end` is null. The end is clamped to each output's own length.
   - An output that has no frames inside the range is omitted and listed; if every requested
     output is empty, the run fails with `invalid_request`/`validate`.
   - The full render is computed exactly as without a range.
3. **Records.**
   - The manifest gains `range: {start_seconds, end_seconds, start_frame, end_frame, omitted}`,
     and each published output gains `source_frames` (its full-render length). It stays
     `format_version` 1, because the fields are additive.
   - The receipt records `range` and `outputs` next to `parameters`.
4. **Skill.**
   - Step 5 (listen and compare): to hear part of the work, use `--range`. Do not window
     `render` yourself: state, loop phase and whole-mix processing make a self-windowed render
     differ from the song.
   - Document the new manifest and receipt fields.
5. **Docs.**
   - `docs/design.md` 試聽 section: range audition v1 exists; faster partial computation stays
     deferred.
   - Update the board.
   - Record the dogfood findings in `docs/blueprints/thoughts/2026-09-25-full-song-dogfood.md`.

## Critical files

| File | Planned change |
|---|---|
| `src/tactus/run.py` | Request validation for `range`/`outputs`; slicing before publish; manifest/receipt fields |
| `src/tactus/cli.py` | `--range`, `--outputs` parsing into the same request |
| `skills/tactus-authoring/SKILL.md` | Section-listening guidance and field docs (drift test covers new keys) |
| `tests/test_range.py` (new), `tests/test_cli.py` | Behaviour tests |

## Verification

- **Identity.** A range run's outputs, decoded, equal `full[start_frame:end_frame]` of a
  no-range run of the same source, sample for sample, for mono and stereo outputs and for an
  output that must be clamped.
- **Stateful case.** A render with a feedback delay (long tail) and a loop whose phase depends on
  absolute position: the range slice still equals the full render's frames. This is the exact
  class of error the dogfood exposed.
- **Validation.** Negative, reversed, non-finite and zero-length ranges are rejected. An unknown
  output name is rejected. An output ending before `start` is omitted and listed; all outputs
  empty is rejected.
- **Records.** The manifest `range` and `source_frames` values are correct, and the receipt
  records `range` and `outputs`.
- **Real work.** A range run on real-chop-flip (e.g. `--range 4:8 --outputs mix`) equals the same
  frames of the known full mix (`bc36a2c6…`).
- **Gates.** pytest, Ruff check and format, and the skill drift test.

## Out of scope

Partial computation, checkpoints, caching, musical-unit ranges (A1), fades or tails, and a
listening page.
