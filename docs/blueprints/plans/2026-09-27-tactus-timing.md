# `tactus.timing` from tclock v3 — plan

> Generated: 2026-09-27 · Source: the [design comparison](../thoughts/2026-09-27-temporal-design-comparison.md),
> approved by Paul · Grounding: the probe module `tclock_v3.py` (scratchpad `probe-feel/`), its
> numeric-integration truth (`truth.py`), `src/tactus/__init__.py`, the skill, and dogfood 3's time code.

## Context

Three probes on temporal helpers:

- **Exact timing tasks:** no need shown.
- **A full production under load:** no load reduction shown.
- **Common musical transforms, three designs compared:** v3 won with 0 errors, against 7 without a
  helper and 7 with v2, at similar tokens.

The errors v3 prevented were a 0/1-based beat confusion and approximated tempo shapes.

## Resolved choices

- **Module:** `tactus.timing`, an optional import. It is named to avoid shadowing stdlib `time`.
  Nothing in `run`/`render` requires it, and a work may keep its own time maths.
- **API** (from v3, unchanged unless noted):
  - `Clock(*, sample_rate, tempo, meter=4, start_seconds=0.0)`. Tempo points:
    - `(bar, bpm)` is a step;
    - `(bar, bpm, shape)` is a gradual change from the previous point, with shape `"ramp"`
      (linear in beats), `"ramp-time"` (linear in time) or `"smooth"` (cosine ease).

    `meter` is quarter beats per bar, from a bar on. Methods:
    - `frame`/`seconds(bar, beat=0, *, ms=0)` and `frame_at`/`at(beat, *, ms=0)`;
    - `beats(bar, beat)`, `beats_per_bar(bar)`;
    - `beat_of(seconds)` (scalar or array), `bpm_at(beat)`;
    - `bars(first, last)` yielding `Bar(number, start_beat, beats, start_frame, end_frame)`;
    - `span(first_bar, end_bar)`.
  - `swing(beat, amount, unit=0.5)`; `Groove(offsets_ms, velocities=None, grid=0.25)` with
    `.ms(beat)`, `.velocity(beat)`, `.frame(clock, bar, beat, *, ms=0)`.
  - `frame_of(seconds, sample_rate)`: the one rounding rule, `floor(s * rate + 0.5)`.
  - `place(buffer, clip, frame, gain=1.0)` returns a new buffer.
  - `envelope_beats(clock, points, length)`, `envelope_seconds(clock, points, length)`.
- **Precision:**
  - `smooth` uses Simpson integration. Test it against closed or quad values: at most 1e-6 s of error
    over 64 bars. Raise the step count if needed; don't loosen the test.
  - `beat_of` is accurate to 1e-9 beats.
  - Validate inputs with clear `ValueError`s: unknown shape, a ramp with no previous point,
    points out of order, a first meter not at bar 1, non-positive bpm.
- **Beats are 0-based quarter notes from the bar's start**, stated first in the module docstring
  and in the skill. Beat 2 of a bar in musicians' counting is `beat=1.0`. This is the error the
  probe found.
- **Out of scope:** tempo from MIDI files, rubato or nested clocks, groove extraction from audio,
  and a global clock requirement.

## Approach

1. `src/tactus/timing.py`:
   - port v3, with the header docstring as the user guide;
   - add type hints and the validation above;
   - keep one owner for the rounding rule.
2. Export the module as `tactus.timing` (`from tactus import timing` works). Don't re-export names
   at the top level.
3. `tests/test_timing.py`:
   - steps, all three shapes against independent computations: scipy `quad` for all shapes, plus
     closed forms for ramp and ramp-time;
   - meters, including 7/8, and fractional bars;
   - no drift over 10,000 bars;
   - the `beat_of` round trip, including arrays;
   - `swing` at 0.5, 0.58 and 2/3, and between grid points;
   - `Groove` slots and wrap-around;
   - `envelope_*` endpoints and midpoints;
   - `place` not mutating its input;
   - the validation errors;
   - `bars`/`span`;
   - `ms` offsets.
4. Skill: a short "Musical time (optional)" section.
   - `from tactus.timing import Clock, swing, Groove`;
   - beats are 0-based (beat 2 = `1.0`);
   - one example covering a step, a ramp, a smooth ritardando, swing and a groove offset;
   - it is optional.

   Keep the section short; the module docstring holds the details.
5. README "Supported surface" and design.md's time passage.
6. **Adoption check:**
   - in a scratch copy of the dogfood 3 work, replace its hand-written `bar_time`/`SECTION_T` maths
     with `tactus.timing`;
   - confirm the deterministic stems are byte-identical;
   - report any difference and why.

## Verification

- pytest, Ruff, and the skill drift test.
- A fresh-Agent check on the shipped module: re-run round 1 of the design probe's brief with two
  fresh sonnet Agents using the skill, and score with `probe-feel/check.py`. Pass: 0 time errors.
