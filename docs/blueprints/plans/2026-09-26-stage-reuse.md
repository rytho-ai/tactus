# Stage reuse for parameter candidates — plan

> Generated: 2026-09-26 · Source: Paul, after the [necessity probe](../thoughts/2026-09-26-fast-audition-necessity.md)
> · Grounding: `src/tactus/run.py` (`_execute`, receipt), `src/tactus/inputs/__init__.py`
> (`_materials`/`_tools` record), `src/tactus/store.py`, the dogfood 3 work
> (`dogfood/2026-09-25-full-song-3/work/song.py`) and the
> [transactional audition design](../thoughts/2026-09-23-transactional-audition.md).

## Context

Transactional audition has everything except reuse: candidates never touch source, every run is
isolated, and keeping is Git with a base check. The necessity probe found that speed alone does
not justify reuse yet: render waiting was 1–10% of Agent sessions, and 32 tracks render in about 14 s.
It did find value that does not depend on speed:

- **Agents compare by numbers.** In the dogfood 3 work, two renders with identical parameters
  differ in the pad (OB-Xf) by up to 2.6 dB per bar. The mix spectrum then differs about as much as a
  1 dB bass change does, so an Agent cannot verify that "only the bass changed".
- **Approved parts should stay put.** When one part is revised, other parts that were already
  approved should not be re-rolled.

Reuse also cuts a one-parameter candidate to the cost of the changed stage, about 1.8 s at any
track count in the synthetic measurement.

## Resolved choices

- **Opt-in, per run.** `tactus run --reuse` (and `run(..., reuse=True)`). Without it, nothing
  changes. Scope is parameter candidates on unchanged source; any source edit recomputes everything.
- **Marking a stage.** `from tactus import stage`; `@stage` on a module-level function. Outside a
  `--reuse` run, it is a plain call.
- **Conservative key.** A stage result is reused only when all of these match; any doubt is a miss:
  - the stage's qualified name and source file;
  - the SHA-256 of every `.py` file under the entry directory (the receipt's `source_files`);
  - the dependency lock (`{path, sha256}`), or, when there is none, the installed distribution
    names and versions;
  - the Python and Tactus versions;
  - a canonical hash of the call's arguments. Supported values are NumPy arrays (dtype, shape,
    bytes), `None`, bool/int/float/str/bytes, `Path`, and lists/tuples/dicts of these. Any other
    argument (a random `Generator`, a plugin object, a callable) makes the call not reusable; it
    runs normally and the receipt says why.
- **Tools are re-checked.** Materials are content-addressed and cannot change under a ref. A
  `tool()` path can change (for example a VST update). A cache entry records the tools and
  materials its stage resolved; on lookup, every recorded tool is re-hashed, and any mismatch is
  a miss.
- **The receipt stays complete.** On a hit, the stage's recorded materials and tools are replayed
  into the run's input record, so `materials` and `tools` list the same entries as a full render.
- **Stored results.** A cache entry holds only NumPy arrays and the supported plain values
  above, nested in lists/tuples/dicts. A result of another type is not stored, and the receipt
  says so. Each load returns fresh arrays. Entries live in `$TACTUS_POOL/stages/<key>/`, next to
  the pool on the same machine; there is no garbage collection in v1.
- **Receipt.** A new `stages` list with one entry per stage call, in call order:
  `{name, key, reused, seconds, reason}`. `reason` is null or says why a call was not reusable
  or not stored. The receipt also records `reuse` (bool). The receipt `format_version` becomes 3.
- **Nested stages** are keyed independently; a hit on an outer stage skips its inner calls, and
  the replayed record covers them.
- **Nondeterministic stages** (OB-Xf, `extreme_stretch`) are reused as-is. That is the point: an
  unchanged part stays identical across candidates. The skill says so.

## Approach

1. `src/tactus/stage.py` (new): the decorator, the key, the argument and result codecs, and
   storage. Its header states that it owns the reuse key.
2. `inputs/__init__.py`: expose a way for `stage.py` to capture the record added during a stage
   call and to replay a stored one. Keep `_materials`/`_tools` owned by `inputs`.
3. `run.py`: the `reuse` request field and CLI flag; compute the run-level key parts once before
   `render`; `stages` and `reuse` in the receipt; receipt `format_version` 3. `excerpt.py` is
   unchanged.
4. Skill: one short section — mark main stages with `@stage`, run candidates with `--reuse`,
   unchanged stages keep identical output, what makes a call not reusable — plus the new receipt
   fields (the drift test checks them).
5. Tests:
   - a hit returns identical arrays and skips the body (use a counter in a file under the run);
   - a changed parameter misses only the stages that received it;
   - a source edit misses everything;
   - a changed tool file misses;
   - an unsupported argument runs uncached with a reason;
   - the receipt's `materials`/`tools` match a full render;
   - outputs with `--reuse` equal outputs without it for a deterministic work;
   - without `--reuse` nothing is cached.

## Verification

- pytest, Ruff, the skill drift test, and CLI runs of the dogfood 3 work with `--reuse`. Convert
  its five `*_bed` functions to stages in a scratch copy, run the default and `bass_gain_db -4`:
  - every stem except bass must be byte-identical;
  - time the candidate.
- A fresh-Agent probe, with its verdict written down before the trial: Agents asked to try a
  one-parameter change and confirm what else changed, with and without `--reuse`, on a work with
  an OB-Xf pad. Measure whether their claims about unchanged parts are correct.

## Out of scope

Structural-edit reuse, cache garbage collection, sharing caches across machines, region-only
computation (checkpoints), parallel stages.
