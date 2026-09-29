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
this repository. Local blueprints are Git-ignored working documents; tracked docs, examples,
tests and experiments hold the usage contracts and verification needed by a clean checkout.

The previous [tactus-daw](https://github.com/rytho-ai/tactus-daw) implementation is a reference
for tested mechanisms. This repository is the active Tactus product, formerly `tactus-code`.

## Installation choices

The README's editable install follows this checkout, including source edits. For a portable
work with a pinned Git installation, follow
[Install and select a work](../plugins/tactus/references/project-commands.md#install-and-select-a-work).
Use `uv tool install --force` when intentionally replacing an existing CLI installation.

## Plugin verification

Both hosts use the same skills and references under `plugins/tactus/`:

```bash
uv run pytest tests/test_plugin.py tests/test_skill.py
claude plugin validate plugins/tactus --strict
```

For installation and updates, see the [plugin guide](../plugins/tactus/README.md).
