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
grounded plans in `docs/blueprints/plans/`, decision rationale and experiments in
`docs/blueprints/thoughts/`,
and current status in `docs/blueprints/plan.md`. Historical docs retain their original names;
follow supersession notices before treating them as current requirements.
Blueprints and `experiments/` are local, Git-ignored working material. Keep usage contracts
and verification needed by a clean checkout in tracked docs, examples and tests.

The single Tactus plugin uses root `.claude-plugin/` and `.codex-plugin/` manifests.
Its shared skills, references and examples live under `skills/`; both marketplaces target `.`.

Use `uv` for the Python environment. Run pytest and Ruff for code changes; verify CLI behavior
when commands or packaging change. Gamut is retired; no workflow should invoke or synchronize it.
