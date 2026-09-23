# Tactus development

This repository is the active Tactus product, formerly `tactus-code`. Start with
`docs/blueprints/plan.md` for current work. `../tactus-legacy` is a reference implementation;
reuse mechanisms only when the active product needs them. Keep its environment separate.

Python source, declared material identities, and dependency locks own creative intent;
Git owns revision history. Generated arrangements and audio are derived artifacts. A graph
authoring model is not required. See the temporal and functional-authoring thoughts before
changing that responsibility split.

Use the installed small-change skill for decided fixes and the planning skill for new
capabilities. Store grounded plans in `docs/blueprints/plans/`, decisions in `thoughts/`,
and current status in `docs/blueprints/plan.md`. Historical docs retain their original names;
follow supersession notices before treating them as current requirements.

Use `uv` for the Python environment. Run pytest and Ruff for code changes; verify CLI behavior
when commands or packaging change. Gamut is retired; no workflow should invoke or synchronize it.
