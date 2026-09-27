# Temporal abstraction (A1) — plan

> Generated: 2026-09-26 · Source: inventory A1, agreed with Paul as the next capability · Grounding:
> [optional clock](../thoughts/2026-09-23-optional-clock-temporal-abstraction.md),
> [Python/Pattern boundary](../thoughts/2026-09-22-python-pattern-authoring-boundary.md),
> [mixed clocks](../thoughts/2026-09-23-mixed-clocks-vs-python-probe.md),
> [independent Agent MIDI](../thoughts/2026-09-23-independent-agent-midi-authoring-probes.md),
> the tactus-daw Setloom tempo-ramp note, and a survey of 64 distinct Agent-written works on this
> machine (dogfoods, examples, probes). Status: step 1 ran on 2026-09-27 and did **not** justify helpers
> ([result](../thoughts/2026-09-27-temporal-helpers-necessity-probe.md)); step 2 is not scheduled.

## Evidence so far

- **Repetition is universal; errors are rare.** Every work re-implements time maths, and no shared
  utility exists:

  | Kind of time maths | Distinct files |
  |---|---|
  | unit conversion (`BAR_SEC = 4*60/BPM`, `bar_time`, frames) | about 45 |
  | placement and repetition | about 35 |
  | fitting to bars and sample rounding | about 30 |
  | automation curves over sections | about 25 |
  | tempo conversion for stretch or MIDI | about 20 |
  | section tables | 6 |

  One file recomputes `bar_frames` at four call sites.
- **The only defect found is harmless.** dogfood 3 advances bar positions by `bar += BAR_SEC` (float
  accumulation) instead of calling its own `bar_time()`. The drift is about 1e-13 s, inaudible.
- **Earlier probes found no reliability gain on simple timing.** On the hybrid helper set
  (`bar`, `bars`, `beats`, `place`, `repeat`, `scale_time`), Agents went 6/6 on first pass, but the
  plain-Python arms also passed. A MIDI warp helper showed no correctness advantage (8/8 either way).
- **The one real timing failure was a tempo change.** Setloom's renderer read only the first tempo,
  so notes, curves, pulse and length silently ignored a 121→128 BPM ramp. Tempo changes have not
  appeared in Tactus works yet.
- **Principles:** time handling is Tactus's job (positioning §1). A global BPM or clock stays
  optional (§4, optional-clock decision). Helpers must not decide rhythm or feel.

So repetition is proven; value is not. Paul requires proof before building. The evidence points to
where helpers could matter: cases that are easy to get subtly wrong, not simple 4/4 placement.

## What the earlier probes already answer (read again 2026-09-26)

- **First writes of simple timing are not where helpers help.** In the mixed-clocks probe, plain
  Python got a global tempo change, an independent local BPM and absolute events sample-exact;
  its verdict gave "no evidence that Tactus must own tempo-map or local-clock creative logic".
  The helper probes found equal first-pass correctness.
- **That probe named the next test itself:** compare Python-owned clock functions with a
  framework clock "on a real revision", and measure "whether B actually reduces Agent mistakes or
  source-maintenance effort". Hand-written time maths breaks when a work is revised (tempo,
  inserted bars, meter), because literal seconds and frames do not move.
- **The false-BPM defect it found no longer exists:** `render()` requires no BPM.

So step 1's primary outcome is the revision round, not the first write.

## Step 1 — necessity probe (before any product code)

- **Prototype.** A small prototype module in scratch, not in the product: a clock from a tempo map
  (constant or piecewise-linear ramps) plus beats per bar and sample rate. It converts
  bar/beat → seconds → frames absolutely (never by accumulation) and rounds once. It also has
  `place`/`repeat` onto a buffer, a section table, and a breakpoint envelope sampled on the clock.
- **Tasks,** each with a ground truth I compute independently:
  1. **Tempo ramp.** 16 bars, 90 BPM ramping linearly to 110 over bars 9–12. Place a kick on every
     beat and a clap on 2 and 4. Put a filter sweep across bars 9–12 that follows the beats.
     Output length exact.
  2. **Mixed meter and swing.** 4 bars of 7/8 then 4 bars of 4/4 at 100 BPM, 16th-note hats with
     60% swing, and a 3-beat loop fitted to each 7/8 bar.
  3. **Free-time intro.** A 12.5 s intro in seconds, then 8 bars at 84 BPM starting exactly at
     12.5 s, with a 2-bar fade into bar 1.
- **Arms.**
  - H: the prototype plus a one-screen doc.
  - P: plain Python, the current skill.

  3 fresh sonnet Agents per arm, the same prompts, the current Tactus.
- **Revision round (primary).** The same Agent then revises its own work. It moves the ramp to bars
  7–12, inserts one 4/4 bar before bar 1 of task 1, changes task 2's first section to 5/8, and
  shortens task 3's intro to 10.0 s. Every dependent event and curve must move correctly and
  nothing else may move.
- **Metrics** (from the rendered stems and source, not self-reports):
  - T1: every event onset within ±1 frame of the ground truth, and exact output length;
  - T2: the automation curve's breakpoints within ±1 frame, following the tempo map in task 1;
  - T3: tokens, time and repair attempts.
- **Verdict,** written into the probe folder before dispatch:
  - helpers justified if, in the revision round, P fails T1 or T2 in at least 2 of the 9 task-runs
    and H fails at most 1,
    or P needs at least 1.3× H's tokens at equal correctness;
  - not justified if P matches H.

  For the not-justified case, the fallback is to leave A1 in Future and move the tempo-change
  trigger into the skill's guidance instead.

## Step 2 — only if step 1 passes: product design

- **`tactus.time`** (optional import; no work is required to use it):
  - `Clock(tempo, beats_per_bar=4, sample_rate=…)`, where `tempo` is a number or a tempo map of
    `(bar, bpm)` points with a constant or linear segment;
  - `clock.seconds(bar, beat=0)` and `clock.frame(bar, beat=0)`, computed absolutely and rounded
    once, half away from zero;
  - `clock.length(bars)` in frames;
  - `place(buffer, clip, frame, gain=1.0)`, which returns a new buffer (functional discipline);
  - `repeat(...)` over a list of frames;
  - `envelope(points, clock_or_seconds, frames)`, piecewise-linear from `(time, value)` breakpoints.
- **Free time:** every helper also accepts plain seconds; a clock is never required.
- **Out of scope** unless the probe shows otherwise: swing/groove templates (creative choices),
  rubato, nested clocks, MIDI tempo maps (`mido` handles files), pattern algebra.
- **Adoption:** convert dogfood 3's time code as the first consumer and confirm byte-identical
  output. The skill gets one short section (how to use `tactus.time`; not how to write rhythm).

## Verification

Step 1's verdict decides whether step 2 happens. If it ships, verify with:
- pytest, including property tests (no accumulation drift over 10,000 bars, and a tempo-ramp
  integral against a closed form);
- the dogfood 3 conversion;
- a fresh-Agent re-run of task 1 on the shipped module.
