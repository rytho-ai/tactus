# Second production through `run` — plan

> Generated: 2026-09-24 · Source: Paul approved planning the first slice recommended from the
> [implementation inventory](../thoughts/2026-09-24-implementation-evidence-inventory.md)
> (B1 wiring, A2 minimal, A7 receipt extension, A8 first version) · Grounding: fresh reads of
> `src/tactus/run.py`, `src/tactus/material.py`, both real examples, and the reference
> `tactus-daw` asset/hosting modules. Status: implementation authorized by Paul on
> 2026-09-24; step 5 waits for the guide-carrier choice.

## Context

Only one real production runs through `tactus run` today. `examples/real-chop-flip/` pins its two
inputs itself: `materials.py:22-30` hashes a mutable path, with an environment-variable override.
`examples/phonon-ballad/song.py` is a separate argparse program. It hashes five drum one-shots
inline (`song.py:36-78`, `221-269`) and loads an unpinned 148 MB system soundfont through
`libfluidsynth` via ctypes (`soundfont.py:20`). It calls `sfizz_render` through `subprocess` for
the `sfz` palette and writes its own WAVs plus a hand-built `receipt.json` into `dist/`. The
second copy of the pin-a-file pattern is the trigger for a shared mechanism (positioning §5).

`run.py:219-240` inventories only `.py` files under the entry directory and that directory's own
`uv.lock`. Examples inherit the repository root lock, so their lock is never recorded. The receipt
records Python, Tactus, NumPy, and SoundFile versions only. It does not record input materials,
imported third-party packages (`pyrubberband`, SciPy), or external processors (`rubberband 3.3.0`,
`sfizz_render`, `libfluidsynth`). `sfizz_render` has no `--version`, so a version string cannot
serve as its identity.

Agents learn the `render`/`run` contract from `README.md` and `examples/functional/README.md`.
Neither states the functional authoring discipline or the manifest/receipt fields. The
[functional authoring](../thoughts/2026-09-21-functional-audio-authoring-core.md) evidence shows
that this discipline fixed a 48-track failure, but the rules lived in an experiment fixture.

Reusable prior art: `../tactus-daw/src/tactus_daw/assets/pool.py` (105 LOC). It is a machine-wide
store keyed by content hash under `~/.local/share/tactus/pool`, with `<digest[:2]>/<digest>`
fan-out, atomic `put`, and `path_for` that re-verifies the hash and treats missing and corrupt
separately. It has no coupling to the tactus-daw Project model. This machine already holds
149 entries there. `hosting/sfz_backend.py` supplies the executable-fingerprint pattern: hash the
binary itself and never fall back silently.

Compatibility boundary: `render(*, ...)`, `tactus.run`, the `tactus run` CLI, the manifest, and
`MaterialStore` output delivery stay unchanged. The receipt is a persisted format. It gains fields
and moves to `format_version: 2`; tests are its only consumers.

## Resolved questions

- **Inline digests.** Works reference materials as `material("sha256:…")` module constants; no
  material lock file (Paul, 2026-09-24).
- **No GitPython; no Git work in this slice.** A4 remains separate (Paul, 2026-09-24).
- **Input bytes live in the shared pool.** They go under `$XDG_DATA_HOME/tactus/pool`, with a
  `TACTUS_POOL` override. The layout is byte-compatible with the tactus-daw pool, so identical
  bytes share one entry and moving a work directory needs no re-import. The output
  `MaterialStore` stays per-run and unchanged.
- **Identity = SHA-256 of the raw file bytes.** Decoded, region, and resampled audio are derived
  by the work's own code; this slice defines no decoded-audio identity. This follows the
  [real-media plan](2026-09-16-real-media-inputs.md) evidence: hash the whole source, and let the
  work decide what it reads.
- **Resolution returns a verified path, not decoded audio.** The work keeps using SoundFile for
  bounded reads, rate/channel checks, and headroom. No shared read adapter is added until a
  second work repeats the same read logic.
- **Python package attribution is automatic.** After `render` returns, the worker maps imported
  top-level modules to installed distributions and records their versions. External executables
  and native libraries have to be declared, because Python cannot see which binary a subprocess
  or ctypes call used.
- **Processors are recorded, not pinned.** The receipt carries each declared tool's path and
  SHA-256. Refusing to run with a different binary is deferred to A7's rebuild work.
- **Lock discovery walks upward.** The runner uses the nearest `uv.lock` from the entry directory
  upward and records its path and hash.
- **Phonon-ballad's hand-built receipt and `dist/` writes are removed.** Its musical parameters
  (palette, drum mode) become keyword-only `render` parameters. Section/timeline metadata stays in
  source; non-audio outputs remain out of scope.

## Open questions

1. **Guide carrier: skill or `AGENTS.md`** (blocks step 5). Paul narrowed the carrier to an Agent
   skill or an `AGENTS.md`, rather than a CLI-printed document; the choice between them is open.
2. **SFZ piano on this machine** (blocks only the `sfz` palette's parity check). No
   `UprightPiano.sfz` exists here; only Karoryfer bass SFZs under `music-agent-os/sfz/`. Until one
   is provided, the `sfz` palette keeps an explicit, unpinned path parameter. It is recorded in
   receipt parameters and marked unpinned. Whole-directory SFZ identity (a tree digest over
   sorted `(relpath, sha256)` pairs, as in tactus-daw `bundle/sfz.py`) waits for a pinned
   instrument that can be verified.
3. **First-version completion definition** (blocks nothing here). Proposed: A1–A8 each have a
   minimal adopted form, one fresh Agent takes over and revises a real song through the guide, and
   Paul listens to the result. To be settled on the board, not in this plan.

## Approach

Each step leaves `pytest`, Ruff, and the existing CLI checks green.

**0. Baselines before touching examples.** Run the current phonon-ballad CLI for `synthetic` with
drums `none`/`one-shots`/`loop`, and for `sampled` with `one-shots`. Record the decoded-sample
hashes of every WAV. Record the selected real-chop-flip A output hashes from a fresh `tactus run`,
checked against the dogfood report (`bc36a2c6…` base mix).

**1. Input pool and resolver.** Add an `src/tactus/inputs/` package with its own header:
- `pool.py`: `put`, `path_for`, and `has`, adapted near-verbatim from tactus-daw `pool.py`, with
  the root taken from `TACTUS_POOL` or XDG.
- `__init__.py`: public `material(ref: str) -> Path`. It takes `"sha256:<hex>"`, re-verifies the
  entry, and raises `MaterialError` with a reason of `missing`, `corrupt`, or `invalid_ref`. The
  message names the digest and the import command. Each resolution is recorded in a
  process-local run log.
- `tool(name_or_path: str) -> Path`: resolve through `shutil.which` or a path, hash the file,
  record `{name, path, sha256}`, and raise if it is absent.

Export `material` and `tool` from `tactus`.

**2. Receipt v2 and the import CLI.**
- In `_execute`, map `MaterialError` to code `material_unavailable` and phase `execute`.
- Add `materials`, `tools`, and `python_packages` to the receipt, with `dependency_lock: {path,
  sha256}` from the upward search. Rewrite `attribution_scope` to state what is and is not traced.
- The source inventory scope (entry directory `.py` files) and the `source_changed` guard stay
  as they are.
- Add `tactus material add PATH...`. It puts the bytes into the pool and prints JSON
  `{path: "sha256:…"}` on stdout, so Agents can paste digests into source.

**3. real-chop-flip adopts `material`/`tool`.**
- Replace `checked_path` and its environment overrides with two digest constants resolved
  through `material()`.
- Declare `tool("rubberband")` in `chops.py` at the point of use.
- Import the two dogfood assets into the pool.
- Acceptance: base and candidate outputs are byte-identical to step 0, and the receipt lists
  both materials, `rubberband`, `pyrubberband`, SciPy, and the root lock.

**4. phonon-ballad through `run`.**
- Convert to `render(*, palette="sampled", drums="one-shots", sfz_piano=None)`, returning
  `mix` plus the six stems at 32 kHz.
- Drum files and the FluidR3 soundfont resolve through `material()`. `libfluidsynth` (via
  `ctypes.util.find_library`) and `sfizz_render` are declared with `tool()`.
- Remove argparse, the `RYTHO_LIBRARY_ROOT` resolution, and the hand-built receipt. The
  author-owned soft clip and peak normalisation stay as they are.
- Acceptance: decoded samples equal the step 0 baselines for every palette and drum mode run
  there. The new receipt attributes every sampled input. Update the README to show `tactus run`
  commands.

**5. Agent guide (A8 first version).** Write the guide in the carrier chosen in open question 1,
covering:
- the `render` contract and output limits;
- `run` and the CLI;
- manifest and receipt v2 fields;
- `material`/`tool`/`material add`;
- the functional discipline: never mutate inputs or shared state, explicit data flow, named
  stages, processing order made visible, `+=` on arrays the function owns allowed.

Point to the two real examples as references. A test runs a real `run` and
asserts that every receipt and manifest key appears in the guide, so the guide and `run.py`
cannot drift silently.

**6. Example regression.** `tests/test_examples.py` always runs `examples/functional` and
phonon-ballad `synthetic`/`none`, which need no external inputs, against the step 0 hashes. The
sampled phonon-ballad and real-chop-flip cases carry a marker and skip, naming the missing digest,
when their materials are not in the pool.

**7. Board and docs.**
- Add this plan under ▶ Next in `plan.md`.
- Update `docs/design.md` for material resolution, receipt v2, and the tools record.
- Tick the matching inventory items only with evidence.

## Critical files

| File | Role and planned change |
|---|---|
| `src/tactus/run.py` | Receipt v2, upward lock search, package attribution, `material_unavailable` mapping |
| `src/tactus/inputs/` (new) | Pool, `material`, `tool`, run-scoped record log; header required |
| `src/tactus/__init__.py` | Export `material`, `tool` |
| `src/tactus/cli.py` | `material add` subcommand |
| Guide (skill or `AGENTS.md`, open question 1) | Agent-facing contract and functional discipline |
| `examples/real-chop-flip/materials.py`, `chops.py` | Adopt `material`/`tool`; drop env overrides |
| `examples/phonon-ballad/song.py`, `soundfont.py`, `README.md` | Port to `render(*, ...)`; adopt `material`/`tool` |
| `tests/test_inputs.py`, `tests/test_examples.py` (new) | Resolver and receipt behavior; example regression |
| `docs/design.md`, `docs/blueprints/plan.md` | Current approach and board entry |
| `../tactus-daw/src/tactus_daw/assets/pool.py` | Read-only source for the adapted pool |

## Verification

- **Focused tests with a temporary `TACTUS_POOL`:**
  - `material` resolves after the file is moved or renamed (same bytes);
  - a replaced file yields `corrupt`;
  - a deleted entry yields `missing` with an actionable message, and the run fails with
    `material_unavailable` and leaves no output directory;
  - an invalid ref is rejected before any path is built;
  - `tool` records a hash and fails for absent names.
- **Receipt:** lists every resolved material in resolution order and every declared tool, lists
  imported third-party distributions but not the stdlib, and records the nearest lock for a
  nested entry.
- **Parity:** real-chop-flip and phonon-ballad outputs match the step 0 baselines exactly. A
  deliberate sample swap produces a one-line source diff and a changed output.
- **Relocation:** copy real-chop-flip to a scratch directory outside the repo and `tactus run`
  it. It resolves from the pool and produces identical output (its lock is then reported as
  absent, not guessed).
- **Gates:** `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, package build,
  and installed-CLI checks for `run` and `material add`.
- **A8 acceptance (paid, needs Paul's go-ahead):** one fresh sonnet Agent receives only
  the guide and writes then revises a small multi-stage piece. Record first-pass success,
  input mutation, ordering, and recomputation errors against the fixture-era evidence. A single
  trial is an observation, not proof.
- **Listening:** outputs are sample-identical to baselines, so no new listening verdict is
  required; the sampled phonon-ballad mix is offered to Paul only if parity fails.

## Out of scope

Git integration (A4), transactional or range audition (A3, A5), Pedalboard (A6), time helpers
(A1), directory/SFZ tree identity (pending open question 2), processor pinning or refusal on mismatch, pool
garbage collection or cloud sync, decoded-audio identity, headroom or import-gain policy, and
Mido adoption (phonon-ballad hand-encodes its SMF and keeps doing so).
