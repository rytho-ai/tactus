# Project commands

Register ordinary Python functions in the work's `pyproject.toml`. The global `tactus`
command uses this work's locked environment; local code and dependencies travel with the
work. This example uses an editable Tactus checkout, so its source follows that checkout.
For a portable production, use `tactus init` with a published Git revision instead.

From the repository root, install once, then run the example:

```bash
uv tool install --python 3.12 --editable .
cd examples/project-commands
uv sync --locked

tactus analyze stereo width --help
tactus run song.py --out runs/a
tactus analyze stereo width runs/a/mix-*.wav --window-ms 100 --curve --out measurements
tactus export my-delivery runs/a --out delivery/label --title "First candidate"
tactus export stems runs/a --out delivery/stems
```

Each run/export destination must be new. The scalar width is approximately 0.5 at the
source defaults. `--curve` also saves the ten-window NumPy array and `result.json`.
The exporter writes FLOAT WAV without regenerating the source. Inspect `export.json` for
input, callable, parameters, environment and delivered file hashes.

- [measurements.py](measurements.py): custom analysis, including optional arrays.
- [delivery.py](delivery.py): custom exporter receiving named original arrays.
- [pyproject.toml](pyproject.toml): name-to-function registration.
- [Project command contract](../../docs/project-commands.md): flags, output and provenance.
