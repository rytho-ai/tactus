# Project commands and independent export — plan

> 2026-09-29 · Paul authorized implementation after the export-boundary probe and agreed
> on a global uv-installed CLI with project-local Python registrations.

## Context

`cli.py` generates built-in analysis commands from Python signatures, but has no project
registry. `init.py` creates locked uv works; the current console entry does not dispatch to
their environments. `run.py` publishes PCM24 before durable takes; a publication failure
loses completed generation. The export-boundary probe supports a checkpoint before delivery,
with one-command audition retained. Existing `take export` transfers one performance bundle;
it is distinct from delivering a run's final outputs.

## Resolved questions

- Install the CLI once with uv; `tactus` in a work uses that work's locked Tactus/dependencies.
  `init` remains a launcher command. Unrelated/no-project directories use the global install.
  Explicit `--project DIR` supports use outside the work; file arguments remain relative to
  the invoking directory. Project errors never fall back to global execution.
- `[tool.tactus.analysis]` maps `category.name` to `module:function`.
  `[tool.tactus.export]` maps a command name to `module:function`. No entry-point ecosystem,
  mutable global registry or implicit code scanning. Conflicts with built-ins are errors.
- Custom functions use ordinary Python and remain directly callable. Load only the selected
  extension; unrelated commands and category help do not import project plugins.
- Analysis: `(audio, sample_rate, *, parameters...) -> dict`; JSON results plus optional NumPy
  attachments. Existing built-in CLI names/results remain, with additional provenance.
- Export: `(outputs, sample_rate, *, out, parameters...) -> dict`; outputs are verified named
  arrays, `out` is the new delivery directory. Runtime inventories delivered files and writes
  `export.json` last. Return relative artifact paths. Failure removes only that delivery.
- Built-in exporters: wav (PCM24/FLOAT/DOUBLE), flac (PCM24), stems (ZIP; named outputs, default
  excludes literal mix). Neither analysis nor export automatically changes creative settings.
- Every new run checkpoints original returned arrays, receipt and take refs in `render.json`
  before default PCM24 delivery. Existing output manifest versions and WAV names stay valid.
  Completed render survives a delivery error; `tactus export` retries from it. Pre-checkpoint
  failures retain existing cleanup. Old runs remain exportable from their saved PCM only.

## Approach

1. `project.py` owns nearest-project discovery/config; `launcher.py` dispatches via uv locked
   environment to the project's CLI without recursion. Change console entry in pyproject.
2. `commands.py` owns registry, callable loading/contract validation and generated flags;
   built-in/custom analysis and export adopt it. Named help and required/default/bool flags
   work consistently. Imported extension diagnostics go to stderr.
3. `render_store.py` owns original-array checkpoint and integrity; run and export consume it.
   Persist before delivery, preserve completed checkpoints on errors, keep default WAV outputs.
4. `export.py` owns verified input selection, built-in exporters, export records and cleanup.
   `analyze.py` owns common audio loading, result serialization/attachments and provenance.
   Provenance includes input and function/source/config/lock identity, effective params and
   actual environment. Bounded source tracking is documented; this is trusted Python.
5. Document in README, design/board and authoring skill; provide a runnable local-extension
   example. Verify via an isolated uv tool install and a separate locked work, then update
   the user's existing global installation to this checked local checkout.

## Critical files

| Files | Responsibility |
|---|---|
| `src/tactus/project.py`, `launcher.py`, `pyproject.toml` | Global/project execution boundary |
| `src/tactus/commands.py`, `cli.py` | Registry, help, parameter parsing and dispatch |
| `src/tactus/analyze.py`, `export.py` | Domain execution and artifact provenance |
| `src/tactus/render_store.py`, `run.py`, `takes.py` | Durable render and recovery |
| `tests/test_project_commands.py`, `test_export.py`, existing CLI/run/skill tests | Contracts and regressions |
| `examples/project-commands/`, README, design, authoring reference | Consumer-facing workflow |

## Verification

- Existing analysis fields/results, run WAV bytes, excerpt and takes remain compatible.
- Local functions appear in help, typed/default/required/bool params work; collisions,
  malformed registrations and callable errors are clear JSON failures. Unselected broken
  plugin cannot break ordinary commands. Work source/dependency changes are attributed.
- Custom analysis scalar + array attachment; custom exporter writes a deliverable with hashes.
- Float precision/headroom, PCM fallback, missing/corrupt input, output exists, partial failure
  and retry without regeneration. Validate checkpoint before accepting it as an input.
- Global tool install: commands in nested work directory use project-only dependency;
  commands outside a work use global version; locked version takes precedence; no recursion
  or silent fallback. Retain logs from actual CLI passes. Preserve prior global install source.
- Full pytest and Ruff, real console commands, and a full-song export comparison.

## Out of scope

Cross-project package discovery, cloud publication, automatic analysis decisions, other
command families, sandboxing arbitrary extension code, and sample-rate conversion policies.

## Outcome

Implemented on `feat/project-commands`. The installed global `~/.local/bin/tactus` now
points to this editable checkout at 0.1.0 via uv; daily commands select the work's environment.
The previous installation receipt is retained in ignored trial evidence. No remote publication
or branch merge is part of this implementation.

Actual isolated-console verification passed 12 checks: outside-project global environment,
work environment, lazy custom help, render, scalar/array analysis, a dependency installed only
in the work (`rich`), nested cwd-relative paths, explicit `--project`, custom and built-in
exports, a separately locked 9.9.9 runtime fixture, and refusal without a lock. The runtime
fixture proves dispatch/version selection; it is not a claim of compatibility with every
historical Tactus release. The real global executable also ran the checked-in example's
render, custom analysis with attachments, and custom delivery successfully.

The existing full-song performance (149.189 s, 44.1 kHz stereo; bass, drums, keys, mix, pads,
textures) passed through the new runner and exporters. All six default audition WAV hashes
match the previous run. All six independent PCM24 export hashes match those audition WAVs;
all six FLOAT exports match saved original arrays sample for sample. No native instruments
were modified and these checks do not imply new listener approval.

Failure tests preserve a completed random render and candidate take after encoder failure,
then remove the generator source and successfully export the exact saved samples. Other
coverage includes required/bool/JSON flags, lazy broken modules, reserved names, corruption,
source/input changes, partial-output cleanup, preserved existing destinations, float64
headroom/precision, float16/integer conversion and explicit legacy PCM fallback.

The first regression pass found two assertions for superseded contracts: deleting a completed
render after delivery failure, and a closed set of analysis envelope fields. Both were updated
to require the new preservation/provenance fields while retaining exact beat-result equality.
Review also caught FLOAT/DOUBLE export passing non-native NumPy dtypes directly to SoundFile;
explicit casts now implement the documented format conversion, with float16/uint8 coverage.

Trial commands, console logs and audio comparisons remain local under
`dogfood/2026-09-29-project-commands/`; the source-only example and this summary are tracked.

Final gates: `uv run pytest -q` — 436 passed, 1 existing opt-in test skipped (252.87 s).
After final dtype/annotation-error handling adjustments, the focused project-command/export
suite passed all 24 cases, including four additional numeric-dtype cases. `uv run ruff check .`
and `git diff --check` passed. The actual global CLI was also verified outside a work and in
the example's own locked environment.
