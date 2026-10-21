# Development

Run these commands from the Tactus checkout with Python 3.12 or newer and
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run tactus --version
uv run tactus doctor
uv run pytest
uv run ruff check .
```

The checkout's `.python-version` defaults to 3.12. Verify Python 3.13 in a
separate environment without replacing that default:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/tactus-py313 uv sync --python 3.13 --locked --group dev
UV_PROJECT_ENVIRONMENT=/tmp/tactus-py313 uv run --python 3.13 --locked pytest
```

Pedalboard 0.9.26 or newer is required for CPU-compatible Linux wheels.
For an existing work that needs Python 3.13, update its `requires-python` if it
still contains `<3.13`, deliberately upgrade its Tactus source to this version,
then run `uv python pin 3.13` and `uv lock`. Existing work locks are not upgraded
automatically. If a work adds a dependency requiring Python 3.13, set the work's
own `requires-python = ">=3.13"` so its declared minimum matches its dependencies.

Default development adds pytest/Ruff; librosa is optional and pyloudnorm is removed.
Numba remains a runtime dependency for accelerated DSP and long CQT/VQT analyses.
Individual external-reference comparisons skip with an installation hint when their
reference package is absent; independent math, edge-case and CLI tests still run.
Run the reference comparisons explicitly, or include them with the full suite:

```bash
uv run --extra librosa pytest -m reference
uv run --extra librosa pytest
```

Tests marked `oracle` compare `tactus.synth` with an installed `csound` binary and skip
when it is not on `PATH` (`uv run pytest -m oracle`).

`uv sync --group dev` removes packages left by an earlier reference run; `uv run`
alone can retain extra packages. The optional references remain pinned in `uv.lock`.

## Internal contract checks

Source inventories, callable identities, attribution and completed-audio readers have
typed internal records. Check these modules with the checkout's Python environment:

```bash
uv tool run --from pyright==1.1.414 pyright --pythonpath .venv/bin/python \
  src/tactus/_source.py src/tactus/commands.py \
  src/tactus/provenance.py src/tactus/render_store.py
```

This is a scoped check, not a claim that the whole codebase is type-checked. Pyright runs
as a separate development tool and adds no runtime dependency.

## Analysis contributions

Use the public `tactus.analysis.schema` helpers for coordinate declarations; the
[schema contract and builtin audit table](analysis.md#data-schema) describe the format.
Check declarations against the actual calculation: window rounding, frame position,
padding, channel policy, units and special values. `schema.validate` checks structure,
not whether a physical unit or timestamp convention is true. Keep numerical regression
tests alongside schema checks; new metadata must preserve existing result fields and
numeric revisions when the algorithm has not changed.

```bash
uv run pytest tests/test_analysis_schema.py tests/test_generic_analysis_schema.py
```

## Product and design

Read [positioning](positioning.md) for the product principles and [design](design.md) for
current approaches and undecided interfaces. Follow [AGENTS.md](../AGENTS.md) when changing
this repository. Blueprints and `experiments/` are local, Git-ignored working material.
Tracked docs, examples and tests hold the usage contracts and verification needed by a clean
checkout. Keep exploratory scripts, raw benchmark reports and temporary experiments locally;
promote required regression inputs into `tests/fixtures/` and maintained examples into `examples/`.

The previous [tactus-daw](https://github.com/rytho-ai/tactus-daw) implementation is a reference
for tested mechanisms. This repository is the active Tactus product, formerly `tactus-code`.

## Installation choices

The README installs from public `main` without `--editable` until a release tag is
available. In a development checkout, `uv run` uses the current source;
`uv tool install --python 3.12 --editable .` deliberately
follows later edits. Keep development and release checkouts separate so the global CLI
does not silently move with unfinished work. For a portable work with a pinned Git
installation, follow
[Install and select a work](../skills/references/project-commands.md#install-and-select-a-work).
Use `uv tool install --force` when intentionally replacing an existing CLI installation.

## Release channel

The public `main` branch and its tags are the release source. Ongoing work may live in a
separate private development repository, but it is still the same `tactus` Python
package and plugin. A public release pull request starts from public `main` and contains
only the reviewed feature, its tests and its usage contract. Never merge a whole
development branch merely to publish one capability. Sync public `main` back into the
development repository after a release.

The required `verify` check covers installation, lint, focused runtime/plugin tests,
CLI startup and package build. It is a minimum promotion gate. The current CLI analysis
suite has a recorded baseline import failure on macOS and Linux, so `verify`
does not claim that suite is green. Include relevant full tests and actual DAW or
plugin-host verification in a feature's pull request when its claims require them.
A green check alone does not establish musical or native-host quality. Tag the
reviewed public commit with the package version only after the pull request and
required checks pass.

## Building distributions

```bash
uv build
```

The source distribution has an explicit allowlist in `pyproject.toml`: runtime source,
tests, maintained examples, usage/design docs, shared skills, plugin manifests and adopted
brand assets. Local blueprints, experiments, dogfood, probes and worktrees stay outside it.
Nested example environments, input audio, run outputs and delivery directories are excluded
explicitly, independently of Git tracking. Keep selected audio and experiment evidence in
their local stores; package rebuilds do not need them.

When changing the package boundary, inspect the resulting archive and build a wheel from
the unpacked source distribution. A wheel-only build does not verify the source archive.

## Plugin verification

Both hosts use the same skills and references under `skills/`, with plugin manifests
at the repository root in `.claude-plugin/` and `.codex-plugin/`:

```bash
uv run pytest tests/test_plugin.py tests/test_skill.py
claude plugin validate .claude-plugin/marketplace.json --strict
claude plugin validate .claude-plugin/plugin.json
```

The second command validates the marketplace. The plugin check reports that root
`CLAUDE.md` is not loaded as plugin context: that file imports repository development
instructions, while installed guidance is carried by `skills/`. This expected warning
means `--strict` is reserved for the marketplace check here.

For installation and updates, see the [plugin guide](../skills/README.md).
