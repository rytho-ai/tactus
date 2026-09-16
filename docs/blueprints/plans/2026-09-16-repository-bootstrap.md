# Tactus Code repository bootstrap — plan

> Generated: 2026-09-16 · Source: Paul’s request to set up an independent `tactus-code` Git repository · Grounding: fresh comparison with sibling `tactus` and `audion` repositories

## Context

The existing `tactus` repository is an operation-oriented DAW runtime. The proposed code-first production approach is a separate experiment and must not inherit that repository’s source tree, history model, or package identity. There is no `tactus-code` directory yet. Sibling projects use a `src/` Python package, `pyproject.toml`, pytest, and `docs/blueprints/` for project tracking.

## Resolved questions

| Question | Decision |
|---|---|
| Repository | New local Git repository at `rytho-workspace/tactus-code`; no remote is created by setup. |
| Distribution / import / command | `tactus-code` / `tactus_code` / `tactus-code`; these do not collide with the installed `tactus` package. |
| Authority | User-authored Python source plus declared assets and dependencies; generated production state is an output, not a second editable source. |
| Initial scope | Installable package, honest CLI shell, tests, and project conventions only. No speculative arrangement or render API. |
| Legacy boundary | Old `tactus` remains unchanged and serves as a reference for later measured reuse. |

## Approach

1. Create the independent repository and a minimal `src/tactus_code` package with a versioned CLI entry point. The CLI reports its version and explains the experimental status without claiming unsupported production features.
2. Add package metadata, a lean development dependency group, tests, and a `.gitignore` that keeps local environments and generated audio/build artifacts out of Git.
3. Add a README that records the name’s meaning, the code-as-source-of-truth hypothesis, and the boundary between this experiment and the existing Tactus repo. Seed `docs/blueprints/plan.md` using the sibling status-board convention.
4. Run install, tests, lint, CLI smoke checks, and Git isolation checks. Commit the verified bootstrap locally with Paul’s personal author identity.

## Critical files

| File | Role and planned change |
|---|---|
| `pyproject.toml` | Package metadata, CLI entry point, dev checks. |
| `src/tactus_code/__init__.py` | Small public package root. |
| `src/tactus_code/cli.py` | Honest executable entry point. |
| `tests/test_cli.py` | Bootstrap interface contract. |
| `README.md` | Experiment thesis and non-goals. |
| `docs/blueprints/plan.md` | Status index, following sibling repo convention. |
| `.gitignore` | Ignore environments, caches, and generated production artifacts. |

## Verification

- `uv sync --group dev` installs the package from this repository only.
- `uv run pytest` and `uv run ruff check .` pass.
- `uv run tactus-code --version` and `uv run tactus-code doctor` work from a clean checkout.
- `git rev-parse --show-toplevel` points at `tactus-code`, not the existing `tactus` repo.
- The existing `tactus` source and tests remain unchanged.

## Out of scope

- Creating a GitHub repository or remote, publishing to PyPI, copying legacy code, implementing an Arrangement Graph, audio rendering, or Music Agent OS adapters.
