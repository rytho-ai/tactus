# Retire the arrangement prototype

> 2026-09-24 · Paul explicitly requested removing anything retained solely for compatibility with the old approach. Status: implemented and verified.

## Context

The functional `render()` runner is implemented and a real production has been auditioned.
The package still exports Project/Track and exposes build/inspect/render/diff solely to
preserve the earlier arrangement prototype. Those commands/modules are not required by
`run.py`, which calls MaterialStore directly. Paul has removed the compatibility requirement.

## Approach and critical files

1. Remove `src/tactus/{build,graph,project,render}.py`, the corresponding CLI commands,
   and Project/Track exports. Keep `run`, RunError and AudioRef; `doctor` and version remain
   current environment tooling. The source entry is still named `render()` and invoked by run.
2. Remove MaterialStore.import_file, whose only production caller is the retired Project.
   Keep add/read and integrity validation because functional output delivery consumes them.
3. Remove `examples/chop-flip/` source and `tests/test_production_slice.py`, both exclusively
   exercising the retired graph model. Keep functional/real-chop-flip and the independent
   ordinary-Python phonon-ballad study. Leave existing ignored audio/evidence in place.
4. Make README/current design/board describe only supported behavior. Add supersession notices
   to historical implementation plans; preserve experimental evidence as historical records.
   Do not add aliases, deprecation shims, migration commands or an alternative inspect command.
5. Record Paul's preference for the first listening version A. Its -5 dB bass default is already
   the current source, so no musical edit is needed. Verify a fresh post-removal run has the
   selected audio's hashes and source inventory before recording this bounded acceptance.

## Verification

- Full pytest and Ruff; `git diff --check`.
- Build the wheel and check that retired modules are absent. Install into a disposable target
  and exercise CLI help/version/doctor/run, named clips, parameter overrides, and rejection
  of the removed commands. Import the package from that installed target.
- Use the installed runner to render the real production without overrides and compare all
  outputs with A; preserve source defaults and record the acceptance result.
- Search current source/tests/examples/docs for dangling old API consumers. Historical thought
  and plan descriptions can retain old names behind retirement notices.

## Scope

This removes obsolete executable behavior, not useful mechanisms already used by the new
runtime. No changes to the sibling tactus-daw repository, new audition APIs, unrelated personal
records, commits or publication are included. Broader musical parity remains unproven.

## Completion evidence

- Removed the four prototype modules, Project/Track exports, four old CLI commands,
  MaterialStore.import_file, seven graph-example source/docs files and the five-test
  graph-production test module. Current shared storage and functional tests remain.
- Updated current documentation and historical-plan supersession notices. Doctor now reports
  the installed environment with status `ok`, rather than the obsolete bootstrap label.
- `uv run --locked --inexact pytest -q`: **53 passed**, 13.56 s; Ruff and whitespace checks passed.
- Built sdist/wheel. Verified the wheel omits all four retired modules and the installed package
  exports only run, RunError and AudioRef. Nine installed CLI checks passed: help/version/doctor,
  rejection of build/inspect/render/diff, a parameterized clip bank, and the selected real work.
- The post-removal real-source run preserved every A output hash, source inventory and -5 dB
  bass default. Paul's preference for take 1/A is recorded as the current selection, not a
  general musical-quality claim. No musical source change was necessary.
- Disposable package evidence: `/tmp/tactus-retirement-BzVvvy/verification.json`.
  Persistent local audition evidence: ignored `dogfood/2026-09-24-functional-production/final/`.
