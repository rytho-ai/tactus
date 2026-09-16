# Tactus Code

Tactus Code is an independent experiment in maintaining music arrangements as code. The name
states the hypothesis being tested: ordinary source code should be the authority for a music
project, while the production runtime compiles inspectable state and renders deliverables.

This repository runs beside the existing [Tactus](https://github.com/rytho-ai/tactus) repository.
It is not a fork, a replacement announcement, or an API-compatible successor. The existing
implementation is a reference for proven mechanisms; both approaches should be compared on the
same real production workflows before deciding what survives.

## Current status

First playable prototype. A Python project can produce a versioned arrangement snapshot,
content-addressed PCM materials, a build receipt, and graph-only mix/stem renders. The example is
a synthetic-source adaptation of one Music Agent OS workflow, **not** full workflow coverage or
musical parity with its private-source production. The current transport is 4/4; audio is
materialized at the project sample rate and rendered as PCM24 WAV.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are recommended:

```bash
uv sync --group dev
uv run tactus-code --version
uv run tactus-code doctor
uv run pytest
uv run ruff check .
```

Try the modular example:

```bash
uv run tactus-code build examples/chop-flip/song.py
uv run tactus-code inspect examples/chop-flip/.tactus-code/build/arrangement.json
uv run tactus-code render examples/chop-flip/.tactus-code/build/arrangement.json \
  --out examples/chop-flip/.tactus-code/render
```

`song.py` combines ordinary `parts/` and `mix.py` modules. `build` evaluates that source and
materializes each audio computation. `render` reads only `arrangement.json` and its material
store, so it does not need the authoring source. `tactus-code diff BEFORE AFTER` reports which
named tracks/events changed between two compiled builds; Git remains the source-history owner.

The receipt deliberately says **compiled replay only**. Arbitrary Python may use hidden state;
this first version does not promise that rerunning the source creates the same sound. Material
hashes make a selected execution replayable, while dependency detection and reliable incremental
rebuild remain open work.

The distribution is `tactus-code`, its Python import is `tactus_code`, and its command is
`tactus-code`. These names intentionally do not collide with the existing `tactus` package.

## Working hypothesis

- People and agents edit Python source, declared assets, and dependency locks; Git versions them.
- Generated arrangement state is a build artifact, not a second editable project.
- The runtime should make production outputs inspectable and reproducible without dictating every
  musical algorithm.
- NumPy DSP, external tools, and specialized production code should remain usable as ordinary
  source, subject to an explicit execution and materialization boundary.

The first slice currently lacks pitch-preserving warp, real audio analysis, bus/effect routing,
MIDI or `groove.mid` export, selective caching, plugin hosting, and human A/B judgment. These
remain measured requirements, not silently claimed features. See the
[vertical-slice plan](docs/blueprints/plans/2026-09-16-code-first-production-slice.md).
