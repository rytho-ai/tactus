# Level reporting and MIDI files — plan

> Generated: 2026-09-25 · Source: board ▶ Next 1–2, agreed with Paul after full-song dogfood 3 ·
> Grounding: `src/tactus/store.py` (`OutputStore.add`), `src/tactus/run.py` (`_validate`,
> manifest and result), `src/tactus/excerpt.py`, `skills/tactus-authoring/SKILL.md`,
> `tests/test_skill.py`.

## Context

- **Full scale.** `run._validate` and `OutputStore.add` both reject any sample outside ±1 with
  "exceeds full scale; set gain explicitly". Paul (2026-09-25): Tactus should not restrict this;
  the Agent should be aware of it. Evidence: the dogfood 3 Agent passed every output through
  `np.clip` from its first draft, so the check never fired and 26 samples of the v4 mix were
  hard-clipped. The skill never mentions the check.
- **MIDI files.** All three full-song dogfoods hand-wrote a ~40-line Standard MIDI File writer
  for `sfizz_render`, because no MIDI library is installed. The skill already says
  `fx.render_instrument` accepts `mido` messages, yet `mido` is not a dependency.

## Resolved choices

- **Over-full-scale output is published, not refused.** `OutputStore.add` clips to ±1 before the
  PCM24 write (soundfile already clips; clipping explicitly makes it the store's stated
  behavior) and measures the audio as the work returned it.
- **Each manifest output entry gains two keys:**
  - `peak_dbfs`: the peak of the returned audio before clipping, rounded to 0.01 dB (above 0
    when it overflowed); `null` for digital silence;
  - `clipped_samples`: the number of sample values (all channels) outside ±1.
- **The run result JSON gains `levels`:** `{name: {"peak_dbfs", "clipped_samples"}}`, so the
  Agent sees it in the command output without opening the manifest.
- **Manifest `format_version` becomes 2**, because the output-entry shape changed. Excerpt
  accepts version 1 and 2 source manifests. Excerpt outputs report the levels of the slice they
  publish (already clipped audio, so `clipped_samples` is 0 there).
- `AudioRef` stays the identity of saved audio (`sha256`, `frames`, `channels`, `file`); level
  information travels next to it rather than inside it, so `read()` verification is unchanged.
- **Skill.** State that nothing is refused for level, what `peak_dbfs` / `clipped_samples`
  mean, and the usual remedies (lower gain, a limiter such as Pedalboard's `Limiter`), and that
  hard-clipping with `np.clip` only hides the same distortion. It is guidance, not a rule.
- **`mido` becomes a base dependency** (MIT). The skill's SFZ/`sfizz_render` guidance says to
  write the `.mid` file with `mido`.

## Approach

1. `store.py`: remove the full-scale error; clip before writing; return level info from `add`
   alongside the `AudioRef` (for example `add()` returning the ref plus a small levels dict, or
   a separate function; pick the smallest change).
2. `run.py`: remove the full-scale check from `_validate`; put `peak_dbfs` and
   `clipped_samples` into each manifest output entry; add `levels` to the result; manifest
   `format_version` 2; update the module header.
3. `excerpt.py`: accept source manifest versions 1 and 2; write the level keys for its outputs;
   its manifest version follows the run manifest.
4. `pyproject.toml`/`uv.lock`: add `mido`.
5. Skill: level section in "Run results" (and a pointer from "Check levels per section"); SFZ
   guidance names `mido`; manifest `format_version` 2.
6. Tests:
   - an over-full-scale output publishes, with a correct peak and count, and the WAV is clipped;
   - silence gives `peak_dbfs` `null`;
   - the old rejection tests change accordingly;
   - excerpt reads a v1 manifest and a v2 manifest;
   - `test_skill` covers the new keys (it already checks every manifest and result key).

## Verification

- pytest, Ruff, the skill drift test, and the CLI on a loud source.
- A fresh-Agent probe, with its verdict written down before the trial: a task whose natural sum
  overflows and that needs an SFZ `.mid` file. Pass means the Agent notices the reported
  clipping and fixes the gain, without `np.clip`, and writes the MIDI with `mido`.

## Out of scope

- Loudness or true-peak metering, and warnings about levels.
- Detecting flat-topped (already clipped) audio that a work returns.
