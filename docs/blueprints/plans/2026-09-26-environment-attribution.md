# Environment attribution for rebuilding a work elsewhere (A7) — plan

> Generated: 2026-09-26 · Source: the implementation inventory's A7 ("verify rebuilding in another
> directory", never done), agreed with Paul · Grounding: `src/tactus/run.py` (`_inventory`,
> `_find_lock`, `_python_packages`, receipt), receipts from dogfood 3 and the probes.

## Context

A receipt promises to show how an output was made, but it cannot identify the environment that
made it:

- **Wrong or missing lock.** `dependency_lock` is the nearest `uv.lock` above the entry file. Works
  usually live outside the Tactus checkout and run with `uv run --project <tactus>`, so every
  probe receipt has `dependency_lock: null`. The environment that actually ran is the interpreter's
  (`sys.prefix`, e.g. `<tactus>/.venv`), whose project lock is not recorded.
- **Git-installed packages look identical.** `python_packages` records version strings only.
  pytimestretch `e43cc6d` and `bc15497` are both `0.2.0.dev0`. The install metadata already holds
  the commit (PEP 610 `direct_url.json`, `vcs_info.commit_id`).
- **Tactus itself is unidentified.** Tactus is an editable install (`dir_info.editable`), always
  `0.1.0`. Rebuilding needs the Tactus revision, whose `uv.lock` pins everything else.

## Resolved choices

- **`environment`** (new receipt field):
  - `prefix`: the interpreter's `sys.prefix`;
  - `lock`: `{path, sha256}` of the `uv.lock` in the project that owns that environment (the
    parent directory of a `.venv` prefix), or null.
  - `dependency_lock` keeps its current meaning, the lock nearest the entry file, so a work that
    has its own project stays attributed. Both are recorded.
- **`package_sources`** (new receipt field): for every recorded distribution not installed from an
  index, what its `direct_url.json` says:
  - VCS: `{"url", "vcs", "commit"}`;
  - local directory: `{"url", "editable"}`, plus `git: {commit, dirty}` when that directory is a
    Git checkout (reuse `revision.py`'s Git reading, don't duplicate it);
  - archive: `{"url", "hash"}` when present.

  Index installs are omitted: the lock pins them.
- The receipt `format_version` becomes 4. The skill's receipt section documents both fields, and
  the drift test covers them.
- **Rebuild instructions** (skill, one short paragraph): to rebuild an old output, check out the
  work's `git.commit` and apply `source.patch`; check out the Tactus revision from
  `package_sources` and `uv sync --frozen` there (the `environment.lock` hash must match); restore
  materials into the pool by ref; run with the recorded `parameters`. Outputs from
  nondeterministic plugins will not match by hash (existing guidance).

## Approach

1. `run.py`: compute `environment` and `package_sources` next to `_python_packages()` (a small
   helper; read `direct_url.json` via `importlib.metadata`). Update the header.
2. Skill: the receipt fields plus the rebuild paragraph; `format_version` 4.
3. Tests:
   - `environment.lock` resolves for the running venv;
   - a fake distribution with a VCS `direct_url.json`, and one that is editable and in a Git
     directory, appear with the right fields;
   - index installs are absent;
   - skill drift.

## Verification

- pytest, Ruff, the CLI.
- **The A7 acceptance test:** rebuild in another directory.
  1. Take a receipt made by the new code for a work outside the repo (a copy of the dogfood 3 work).
  2. Following only the receipt and the skill's paragraph, a fresh sonnet Agent rebuilds it in a new
     directory: a clean Tactus checkout at the recorded revision, `uv sync --frozen`, materials
     from a pool, the work's commit plus patch.
  3. Pass: every deterministic output hash matches the original. The OB-Xf pad is exempt and is
     compared by level. The Agent needs no information outside the receipt.

## Out of scope

Non-Python tools' own dependencies, cross-platform bit-exactness, automatic rebuilds (a
`tactus rebuild` command), and materials missing from the pool.
