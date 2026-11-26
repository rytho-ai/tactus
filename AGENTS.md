# Tactus development

This repository is the active Tactus product, formerly `tactus-code`. Start with README.md
for delivered behavior and examples. Resolve the configured project workspace for
working plans, progress and retained development rationale. `../tactus-daw` is a reference implementation;
reuse mechanisms only when the active product needs them. Its package and CLI use distinct names.

Before implementation, design changes, or review, read `docs/positioning.md` for product principles
and `docs/design.md` for current approaches and undecided interfaces. Both are self-contained and
maintained independently of the historical thoughts; design choices do not imply shipped behavior.

Use the installed execution skill for decided fixes and plan new capabilities before
implementation. Keep working plans, ideas, progress and retained process artifacts in
the selected project workspace; report an unavailable connection instead of creating
another local work board. Machine-specific workspace paths stay in local configuration,
not committed repository instructions.

Maintain product principles in `docs/positioning.md` and current approaches in
`docs/design.md`: approach, boundaries, a short reason and open questions, in present
tense. Tracked docs, examples and tests own the contracts and verification needed by a
clean checkout. Keep dated process history and private rationale in the workspace;
exploratory scripts, renders and media remain in `experiments/` under its local
retention rules. Historical blueprints are retired sources, not a place for new work.

Original experiments and retired plans may remain with checksums under
`experiments/documentation-history/`; consult them when original measurements or
superseded proposals are needed. Experiments and historical local blueprints stay
Git-ignored and outside distributions. When experiments render many candidates, run
`tactus prune` on unneeded run arrays after recording results; each run can exceed a
gigabyte. Preserve selected performances and required evidence.

When a task in this repository is to make music (a song, beat, demo, probe piece or listening
example), work as a user of Tactus: invoke the compose skill (`skills/compose/SKILL.md`)
first, create the piece with `tactus init` under `experiments/`, render it with `tactus run`
and deliver audio from that run directory. Deliver or publish only audio that has a run
receipt. Friction met along the way is a finding to report, and the piece still goes through
the same flow.

The single Tactus plugin uses root `.claude-plugin/` and `.codex-plugin/` manifests.
Its shared skills, references and examples live under `skills/`; both marketplaces target `.`.
Name the agent connection **Tactus MCP** (config ID `tactus-mcp`) and the DAW-facing
scripts `TactusMCP.lua` (REAPER) and `TactusMCP` (Live) in setup and documentation.

Use `uv` for Python environments, dependencies, and command execution: `uv sync` to prepare
the environment, `uv add` to manage dependencies, and `uv run python ...` for scripts and
one-off Python commands. Run tests and lint with `uv run pytest` and `uv run ruff check`.
Use `uv tool install` for the global CLI. Run commands from the relevant repo or work directory.
Run pytest and Ruff for code changes; verify CLI behavior when commands or packaging change.
Gamut is retired; no workflow should invoke or synchronize it.
