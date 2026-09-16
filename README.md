# Tactus Code

Tactus Code is an independent experiment in maintaining music arrangements as code. The name
states the hypothesis being tested: ordinary source code should be the authority for a music
project, while the production runtime compiles inspectable state and renders deliverables.

This repository runs beside the existing [Tactus](https://github.com/rytho-ai/tactus) repository.
It is not a fork, a replacement announcement, or an API-compatible successor. The existing
implementation is a reference for proven mechanisms; both approaches should be compared on the
same real production workflows before deciding what survives.

## Current status

Bootstrap only. The package installs and the CLI reports its environment. Arrangement compilation,
audio rendering, and Music Agent OS workflow support are **not implemented yet**.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are recommended:

```bash
uv sync --group dev
uv run tactus-code --version
uv run tactus-code doctor
uv run pytest
uv run ruff check .
```

The distribution is `tactus-code`, its Python import is `tactus_code`, and its command is
`tactus-code`. These names intentionally do not collide with the existing `tactus` package.

## Working hypothesis

- People and agents edit Python source, declared assets, and dependency locks; Git versions them.
- Generated arrangement state is a build artifact, not a second editable project.
- The runtime should make production outputs inspectable and reproducible without dictating every
  musical algorithm.
- NumPy DSP, external tools, and specialized production code should remain usable as ordinary
  source, subject to an explicit execution and materialization boundary.

The first substantive milestone is one complete Music Agent OS production workflow, measured
against the existing Tactus implementation. Its scope belongs in a separate grounded plan, not in
this bootstrap.
