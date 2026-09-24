# Tactus

Tactus is the active Python-first music production framework, formerly `tactus-code`.
Python production source, declared materials, and dependency locks own creative intent;
Git records accepted changes. The runtime renders and verifies the resulting audio.

The previous implementation is preserved in
[tactus-daw](https://github.com/rytho-ai/tactus-daw) as a reference for tested mechanisms.
This product succession does not imply API compatibility or feature parity. The reference
implementation installs as `tactus-daw`, imports as `tactus_daw`, and runs as `tactus-daw`.

## Current status

First playable prototype. A Python project can produce a versioned arrangement snapshot,
content-addressed PCM materials, a build receipt, and graph-only mix/stem renders. The example is
a synthetic-source adaptation of one Music Agent OS workflow, **not** full workflow coverage or
musical parity with its private-source production. The current transport is 4/4; audio is
materialized at the project sample rate and rendered as PCM24 WAV.

For locally owned source media, `Project.asset(path)` imports a whole audio file, while
`Project.asset_region(path, start_seconds=..., duration_seconds=...)` imports only a selected
segment. `Project.file(path)` declares any project-local sidecar (such as a beat-grid `.npy`)
and returns its path for ordinary Python parsing. Both source files are hashed in the compiled
input list and build receipt; the selected PCM region is stored so rendering does not need the originals. Audio
imports currently require the source sample rate to match the project; no implicit resampling is
performed.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are recommended:

```bash
uv sync --group dev
uv run tactus --version
uv run tactus doctor
uv run pytest
uv run ruff check .
```

Try the modular example:

```bash
uv run tactus build examples/chop-flip/song.py
uv run tactus inspect examples/chop-flip/.tactus/build/arrangement.json
uv run tactus render examples/chop-flip/.tactus/build/arrangement.json \
  --out examples/chop-flip/.tactus/render
```

`song.py` combines ordinary `parts/` and `mix.py` modules. `build` evaluates that source and
materializes each audio computation. `render` reads only `arrangement.json` and its material
store, so it does not need the authoring source. `tactus diff BEFORE AFTER` reports which
named tracks/events changed between two compiled builds; Git remains the source-history owner.

The receipt deliberately says **compiled replay only**. Arbitrary Python may use hidden state;
this first version does not promise that rerunning the source creates the same sound. Material
hashes make a selected execution replayable, while dependency detection and reliable incremental
rebuild remain open work.

The distribution, Python import, and command are all `tactus` (version `0.1.0`).
Existing `tactus-code` imports and commands must be updated. Build output now defaults to
`.tactus/`; previously generated `.tactus-code/` directories remain ignored and existing
format-v1 arrangement files can still be rendered using an explicit path.

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
