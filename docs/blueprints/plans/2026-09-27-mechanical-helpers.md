# Mechanical helpers — plan

> Generated: 2026-09-27 · Source: the [mechanical-helpers probe](../thoughts/2026-09-27-mechanical-helpers-probe.md)
> (helpers cut tokens 21% with no extra errors; Paul: "沒問題之後再整合") · Grounding: the probe prototype
> `thelp.py` and its tests (scratchpad `probe-helpers/`), `src/tactus/timing.py`, `src/tactus/fx.py`,
> `src/tactus/inputs/`, the skill and its reference.

## Context

The same Agents wrote the same mechanical code in every work, each a little differently.
Examples:

- marker overlap semantics;
- placing a clip before frame 0;
- quantize ties;
- note values under a changing tempo;
- where to measure level, and how to stay under a ceiling.

With the prototype helpers, Agents wrote about a third less code and used 21% fewer tokens, and
they all handled levels the same way. Six helpers were used by at least 2 of 3 Agents.
`db_to_gain`/`gain_to_db` were unused and are dropped.

## Resolved choices

- **No new top-level module.** The package root already holds too many loose modules, so each
  helper joins the module that owns its concern:
  - `tactus.timing` (positions and frames):
    - `quantize(beat, grid=0.25, strength=1.0)`: exact ties go to the later grid point, with
      float noise guarded.
    - `note_seconds(clock, beat, value)`: `value` beats as seconds at `clock.bpm_at(beat)`.
    - `add_at(buffer, clip, frame, gain=1.0)`: an in-place add that returns `buffer`. A clip
      starting before 0 loses its head and one running past the end loses its tail; it never
      wraps. It **replaces `place`**, which copied the whole buffer on every call, so Agents
      avoided it and hand-wrote in-place versions, one of which wrapped negative frames.
      `place` shipped a day earlier and has no users outside probes.
    - `markers(frames, length, value=0.5, channels=1)`: one impulse per distinct in-range frame.
  - `tactus.fx`: `fit_rms(audio, target_dbfs, ceiling_dbfs=-1.0)`.
  - `tactus.inputs`, exported at the top level as `tactus.load_audio`:
    `load_audio(ref_or_path, sample_rate, channels=2, trim_db=None)`.
- **`load_audio`:**
  - It accepts a `sha256:` ref, resolved through `material()` so the receipt still records it, or
    a `Path` already returned by `material()`.
  - Channel conversion: mono is duplicated, stereo is mixed to mono by mean, and anything else
    raises.
  - Resampling is exact and rational (`resample_poly`).
  - The optional leading trim drops everything before the first sample reaching
    `peak * 10**(trim_db/20)`.
  - The docstring states that the trim point depends on the resampler by under 1 ms, as the
    probe found.
- **`fit_rms` must not flat-top.** The prototype relied on Pedalboard's `Limiter`, which hard-clips;
  delivered files had 675–2641 samples flat at the ceiling. The replacement is a NumPy
  look-ahead gain limiter:
  - the needed gain per sample is `min(1, ceiling / peak across channels)`;
  - take a centered running minimum over a window of about 2W, then a box average over W
    (W ≈ 5 ms), so the gain at every peak is at most what that peak needs and changes smoothly;
  - iterate the pre-gain until the output RMS (all channels flattened) is within 0.05 dB of the
    target.

  The result is always at or below the ceiling. If the target cannot be reached within 0.5 dB
  in 30 iterations, raise `ValueError` with the achieved RMS. The docstring says it measures the
  returned audio, and that heavy targets on peaky material mean heavy limiting.
- **Skill:** SKILL.md is unchanged, because it holds only high-level rules. `reference.md` gets
  one line per helper under its module's section, with the details in the docstrings.
- **Out of scope:** dB conversion helpers, true-peak (inter-sample) ceilings, loudness (LUFS)
  targets, and marker overlap modes other than "one impulse".

## Approach

1. `timing.py`:
   - add `quantize`, `note_seconds`, `add_at` and `markers`;
   - remove `place`;
   - update the module docstring and `__all__`.
2. `fx.py`: `fit_rms` with the limiter above, plus a docstring.
3. `inputs`: `load_audio`, exported from `tactus/__init__.py`.
4. Tests:
   - port the prototype's `test_thelp.py` edges (ties, the head and tail cut, coincident markers,
     channel conversions, resample pitch and length, the trim);
   - `fit_rms`: RMS within 0.05 dB, peak ≤ ceiling, and fewer than 0.01% of samples within
     0.01 dB of the ceiling (no flat top), on peaky drum-like material at −14 and −12 dBFS;
   - the unreachable-target error;
   - `load_audio` with a ref recorded in a run's receipt `materials`.
5. `reference.md`:
   - list the new helpers in the Helpers and Musical time sections;
   - replace the example's `place`;
   - add `load_audio` to Inputs.

   Also update the README surface and `docs/design.md`'s time passage.
6. **Adoption check:**
   - re-run the probe's helper reference solution (`ref/helper_work`) ported to the shipped names;
   - it must score all True in both rounds with `check.py`;
   - report the drums' flat-sample counts.

## Verification

- pytest, Ruff, and the skill drift test.
- The adoption check above.
- One fresh sonnet Agent on round 1 of the probe brief, using only the skill and reference with
  no `thelp.py`. Pass: all items True, and it finds and uses the shipped helpers.
