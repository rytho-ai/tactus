# Tactus development

This repository is the active Tactus product, formerly `tactus-code`. Start with README.md
for delivered behavior and examples. When a local `docs/blueprints/plan.md` exists, read it
for ongoing work. `../tactus-daw` is a reference implementation;
reuse mechanisms only when the active product needs them. Its package and CLI use distinct names.

Before implementation, design changes, or review, read `docs/positioning.md` for product principles
and `docs/design.md` for current approaches and undecided interfaces. Both are self-contained and
maintained independently of the historical thoughts; design choices do not imply shipped behavior.

Use the installed small-change skill for decided fixes and the planning skill for new
capabilities. Maintain principles in `docs/positioning.md`, current approaches in `docs/design.md`,
grounded plans for active work in `docs/blueprints/plans/`, decision rationale by topic in
`docs/blueprints/thoughts/`, and current status in `docs/blueprints/plan.md`.
Write `docs/design.md` as the current decision for each topic: approach, boundaries, a short
reason and open questions, in present tense. Record dated progress, measurements and attempts
that were tried and reverted in blueprints or `experiments/`; tracked documents link only to
tracked files.
Original experiments and retired plans are archived with checksums under
`experiments/documentation-history/`; consult them when original measurements or superseded
proposals are needed. Current contracts stay in the maintained product documents.
Experiments that render many candidates run `tactus prune` on their run directories once the
results are recorded: each run's original arrays can exceed a gigabyte.
Blueprints and `experiments/` are local, Git-ignored working material. Keep usage contracts
and verification needed by a clean checkout in tracked docs, examples and tests.

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
