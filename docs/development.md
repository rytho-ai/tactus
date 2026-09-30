# Development

Run these commands from the Tactus checkout with Python 3.12 and
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run tactus --version
uv run tactus doctor
uv run pytest
uv run ruff check .
```

Default development adds pytest/Ruff; librosa is optional and pyloudnorm is removed.
Numba remains a runtime dependency for accelerated DSP and long CQT/VQT analyses.
Individual external-reference comparisons skip with an installation hint when their
reference package is absent; independent math, edge-case and CLI tests still run.
Run the reference comparisons explicitly, or include them with the full suite:

```bash
uv run --extra librosa pytest -m reference
uv run --extra librosa pytest
```

`uv sync --group dev` removes packages left by an earlier reference run; `uv run`
alone can retain extra packages. The optional references remain pinned in `uv.lock`.

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

The README's editable install follows this checkout, including source edits. For a portable
work with a pinned Git installation, follow
[Install and select a work](../skills/references/project-commands.md#install-and-select-a-work).
Use `uv tool install --force` when intentionally replacing an existing CLI installation.

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
claude plugin validate . --strict
claude plugin validate .claude-plugin/plugin.json
```

The first command validates the marketplace. The plugin check reports that root
`CLAUDE.md` is not loaded as plugin context: that file imports repository development
instructions, while installed guidance is carried by `skills/`. This expected warning
means `--strict` is reserved for the marketplace check here.

For installation and updates, see the [plugin guide](../skills/README.md).
