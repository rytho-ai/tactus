# `timing.euclid` and `timing.cycle` — plan

> Generated: 2026-09-27 · Source: the [Pattern idioms probe](../thoughts/2026-09-27-pattern-idioms-probe.md);
> Paul: "照你建議" (minimal integration, no pattern system) · Grounding: `src/tactus/timing.py`, the
> probe prototypes `tgrid.euclid` / `tmini` (scratchpad `probe-pattern2/`), their tests, and the
> skill reference.

## Context

Across two Pattern probes a pattern system never cut tokens or revisions. What recurred was
conventions:

- all three plain-Python Agents hand-wrote Bjorklund, citing "as in TidalCycles `bd(k,n)`";
- one of them reversed Tidal's rotation direction;
- every work hand-wrote a figure repeating across bar lines.

These are small, conventional and easy to get subtly wrong, the same standard the mechanical
helpers met.

## Resolved choices

- **Add two functions to `tactus.timing`; no new module, no pattern type:**
  - `euclid(k, n, rotate=0) -> tuple[int, ...]`: the hit step indices (0-based, ascending) of
    Bjorklund's (k, n), as TidalCycles/Strudel produce them. `rotate` follows Tidal's
    `(k,n,r)`: it rotates **left**, so a hit at step s moves to `(s - r) mod n` and a negative
    `rotate` moves hits later. Raise `ValueError` for `n <= 0` or `k` outside `0..n`.
  - `cycle(figure, count, start=0) -> tuple[int, ...]`: the steps in `[start, start + count)`
    where `figure` hits when it repeats continuously from step 0.
    - `figure` is a string of `x`/`X` for hits and `.`/`~` for rests, whitespace ignored, or
      a sequence of bools.
    - It never restarts at bar lines. Callers map steps to bars and beats themselves.
- **Returning indices, not arrays or events,** keeps both plain loops and NumPy use (`grid[idx]`)
  one step away. Velocity, accents and placement stay with the work.
- **Not added:**
  - seeded probability, since Agents kept earlier bars stable on their own in both probes;
  - `every`/`lastOf` and mini-notation, since Strudel's `every` counts from the first bar,
    unlike "every n-th bar", which is a trap;
  - reverse and roll, since NumPy and slicing already cover them.
- **Skill:** SKILL.md is unchanged. `reference.md` gets one line in Musical time; the
  docstrings carry the details. Their examples use numbers unrelated to any probe brief.

## Approach

1. `timing.py`:
   - add `euclid` and `cycle`, ported from the prototype's Bjorklund;
   - update `__all__` and the module docstring example.
2. Tests:
   - the Tidal tables (3,8), (5,8), (7,16), (2,5) and (4,7);
   - rotation: (3,8,2) = steps 1, 4, 6; a negative rotation moves hits later;
   - edge k = 0 and k = n;
   - validation errors;
   - `cycle` continuity across a start offset, string forms (`x.xx.`, `x ~ x`) and a bool
     sequence, and an empty result.
3. `reference.md`: one line.

## Verification

- pytest, Ruff and the skill drift test.
- One fresh sonnet Agent on all five rounds of the idioms probe brief, with only the skill and
  reference and no prototype module. Pass: 0 errors in every round by `probe-pattern2/check.py`,
  and it uses `timing.euclid` rather than writing its own Bjorklund.
