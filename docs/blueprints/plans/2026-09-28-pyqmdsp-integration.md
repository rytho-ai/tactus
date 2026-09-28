# pyqmdsp in Tactus — plan

> Generated: 2026-09-28 · Source: Paul requested integration and testing after pyqmdsp's
> upstream parity verification · Grounding: main `64091f7`, local `qmdsp-beats` prototype,
> pyqmdsp main `09b36d6` · Status: implemented and verified.

## Context

Main exposes level and spectral analyses through `tactus.analysis.CATEGORIES`; the CLI
generates commands and help from this registry. Beat tracking exists only in the local
prototype. The standalone `openmirlab/pyqmdsp` package now owns the native build and algorithms.
Its 72-file beat evaluation passed the original mean F-measure difference gate of 0.005.

## Resolved questions

- Adopt pyqmdsp at a full Git revision, following the existing pytimestretch dependency.
- Expose only `rhythm.beats` in Tactus. Broader pyqmdsp bindings remain available directly.
- Preserve prototype fields: `beats_s`, `bpm`, `tempo_curve`; return `bpm: null` for fewer
  than two beats. Convert package arrays to lists without recomputing beat times or tempo.
- Let pyqmdsp own framing, channel averaging, dtype conversion, algorithm parameters and
  sample-rate handling. No resampling, timing offsets or replacement estimator.
- Keep analysis outside `render`, freezing accepted results using the existing material flow.
- The prototype branch stays local. Implement on main's architecture without its ctypes/native
  build. Existing reference data is now preserved in the pyqmdsp repository.

## Approach

1. Add the pinned base dependency and lock; implement a small rhythm adapter and register it.
2. Exercise real native calls in tests: known clicks and a tempo change, exact package parity
   for mono/stereo at multiple rates, short/silent material, invalid input and JSON conversion.
   Verify generated help and CLI on saved audio and published run outputs.
3. Re-run the 72-file reference evaluation through Tactus. Store a reproducible script and
   numeric report under `experiments/pyqmdsp-integration/`, recording both package equality
   and the Vamp score gate. Keep audio outside Git.
4. Update README, authoring guidance, current design and board. Follow the handoff's fresh
   Agent usability check: give a new executor only the authoring skill and unseen audio task;
   the parent verifies its saved results. This checks use, not delegates review or judgment.
5. Run full pytest, Ruff and real installation/CLI checks. Record evidence and remaining limits.

## Critical files

| File | Role and planned change |
|---|---|
| `pyproject.toml`, `uv.lock` | Pin/install the standalone native package |
| `src/tactus/analysis/rhythm.py` | JSON-ready adapter, field definitions and limitations |
| `src/tactus/analysis/__init__.py` | Register the category for Python and CLI discovery |
| `tests/test_rhythm.py`, `tests/test_cli.py` | Numerical, input and CLI integration checks |
| `experiments/pyqmdsp-integration/` | Repeatable corpus check and measured results |
| `README.md`, `skills/tactus-authoring/` | Discoverability and frozen-analysis workflow |
| `docs/design.md`, `docs/blueprints/plan.md` | Actual shipped behavior and evidence |

## Verification

- `uv sync --locked`; direct installed package identity and pinned source inspection.
- Focused rhythm/CLI tests, then `uv run pytest` and `uv run ruff check .`.
- 72 audio files: exact equality with direct pyqmdsp for all three result fields (except the
  documented no-estimate sentinel); mean F differs from saved Vamp reference by at most 0.005.
- Real `uv run tactus analyze rhythm beats FILE`, all help levels, run-directory analysis,
  material freezing, and a new work's dependency resolution/install.
- Fresh Agent uses unseen material through the skill and CLI; parent reruns its commands.

## Out of scope

Downbeats, onsets, key, automatic warp/slicing, PyPI publication, and pushing or merging the
old prototype branch. Accuracy is measured on the stated corpus, not promised for all music.

## Outcome

- The adapter keeps revision 1 and all prototype fields. Native code and Vamp remain outside
  Tactus; the installed package owns numerical behavior. The existing generated CLI needed
  no special beat command implementation.
- `uv sync --locked` installed pyqmdsp from the pinned commit on Python 3.12.11 / Linux x86_64.
- Focused integration/analysis/CLI suite: **94 passed**. Full suite: **400 passed, 1 skipped**
  (203.27 s). The skipped opt-in new-work installation test passed separately with
  `TACTUS_SLOW=1 uv run pytest tests/test_init.py::test_init_then_uv_sync_then_run_uses_the_works_own_lock -q`.
- A separate actual `tactus init --tactus-path` work installed dependencies, analyzed a real
  drum loop (31 beats, 90.6661 BPM), and reported the exact pyqmdsp Git source in installation
  metadata. This exercises the consumer environment, not only Tactus's development venv.
- `uv run ruff check .`, `git diff --check`, and `uv build` passed. Ruff excludes the existing
  nested `.claude/worktrees` checkouts, which contain independent prototype code; no prototype
  files were modified.
- Corpus CLI parity: **72/72 exact**, all three fields; Vamp reference mean F **0.865342**,
  actual **0.864849**, difference **0.000492**, below **0.005**. Five individual score differences
  remain, listed in the [report](../../../experiments/pyqmdsp-integration/README.md).
- Fresh executor given only authoring guidance and two unseen recordings successfully discovered
  the CLI, saved analyses and pinned/read back identical JSON. Parent independently reran both
  analyses and material checks. One mistaken JSON selector exposed a documentation gap:
  README/reference now explain the `result` envelope. No quality claim is made for unannotated
  trial recordings. See [trial evidence](../../../experiments/pyqmdsp-integration/user-trial.json).
- The old `qmdsp-beats` branch remains local and unmodified. No PyPI release is involved.
