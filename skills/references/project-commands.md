# Project analysis and export commands

Install the CLI once with uv. Inside a work, `tactus` runs with that work's locked Tactus
version and dependencies. Register the work's Python functions by name; use the same CLI
for built-in and custom operations.

## Contents

- [Install and select a work](#install-and-select-a-work)
- [Test and lint a work](#test-and-lint-a-work)
- [Register local functions](#register-local-functions)
- [Analyze](#analyze)
- [Export a completed render](#export-a-completed-render)
- [Attribution boundary](#attribution-boundary)

## Install and select a work

For a fixed installation, replace `FULL_COMMIT` with the chosen published commit SHA:

```bash
uv tool install --python 3.12 "tactus @ git+https://github.com/rytho-ai/tactus.git@FULL_COMMIT"
tactus init my-work
cd my-work
```

The tool is installed from Git, so editing or switching a development checkout cannot
change it. `init` pins the same commit in the work. Use `--force` when replacing an existing
tool installation. This fixes the Tactus source revision; the work's `uv.lock` fixes its
full dependency environment.

For a development checkout:

```bash
uv tool install --python 3.12 --editable /path/to/tactus
tactus init my-work --tactus-path /path/to/tactus
cd my-work
uv add PACKAGE  # only when the work needs another dependency
```

For a portable work, `tactus init DIR --tactus URL@REV` pins a published revision instead.
An editable path follows local source changes; it does not freeze the checkout.

From then on, use `tactus ...` directly. The launcher selects an explicit `--project`,
a work passed by its parent launcher, or a recognizable current uv work environment;
otherwise it discovers the nearest `pyproject.toml` from cwd, including parents.
An unrelated nearest Python project ends discovery. In a Tactus work it runs
`uv run --project DIR --locked -- python -m
tactus.cli ...`. This installs/syncs the locked environment as needed. Missing or outdated
locks fail with no fallback to the global installation; use `uv lock` when intentionally
changing dependencies. `tactus doctor` reports the selected project, interpreter and version.
`init` uses the launcher installation; outside a work commands use the global environment.

Use `tactus --project /path/to/work ...` to select a work from elsewhere. Put `--project`
before the subcommand. File arguments remain relative to your invoking directory. A work
pinned to an older Tactus exposes that version's commands; update its dependency deliberately
to adopt new commands. `uv run tactus ...` remains usable but is unnecessary for daily use.

## Selecting a work's environment

From another directory, choose the work explicitly and keep file paths unambiguous:

```bash
tactus --project /path/to/work doctor
tactus --project /path/to/work run /path/to/work/song.py --out /path/to/work/runs/a
```

`--project` selects dependencies and custom command registrations; it preserves the
caller's cwd. Source/input/output arguments still refer to the caller's directory.
The render entry then resolves its own relative imports/files from its source directory.

For work-local Python scratch scripts, use its locked uv environment:

```bash
uv run --project /path/to/work --locked -- python /path/to/work/check.py
```

`uv run --project WORK` selects an environment while keeping cwd. Current Tactus recognizes
uv's running context when activation matches the interpreter and its default `.venv`
belongs to a Tactus work, so `uv run --project WORK --locked tactus doctor` keeps that work.
An activated environment by itself does not override project discovery. For custom/shared
environment locations, use explicit `tactus --project WORK`; automatic uv recognition is
limited to a work's default `.venv`. Older pinned launchers may still rediscover cwd:
use explicit selection or deliberately upgrade the work before relying on this behavior.

`doctor` retains its existing project/version/environment fields and also reports
`interpreter`, `lock` (path/hash or null), `package_source` (installation provenance or null),
and `environment_matches_project` (default `.venv` match, or null without a work).
Check the project, interpreter and package source together: different revisions can share
the same package version. A false match can reveal that a directly invoked module is using
another environment; retry through the installed launcher with explicit `--project`.
This diagnostic compares the default `.venv`, not arbitrary workspace/custom layouts.
Locks control versions; updating the global CLI does not upgrade a work's pinned Tactus.

## Test and lint a work

Run from the work root so both tools use its configuration:

```bash
uv run --locked --with pytest pytest
uv run --locked --with ruff ruff check .
```

`--with` supplies development tools for this invocation without adding runtime
requirements or changing the work lock. To lock tool versions for repeated checks,
use `uv add --group dev pytest ruff`, then `uv run --group dev pytest` and
`uv run --group dev ruff check .`.

New `tactus init` works include local pytest and Ruff settings. Tests can live at the
work root or under `tests/`; generated `runs/`, `pool/`, `analyses/` and `exports/`
directories are excluded from recursive checks. Pytest retains its usual excluded
build/hidden directories. Ruff uses explicit error, unused-name and import-order rules,
with work-local modules treated as first-party and Tactus as a third-party dependency.
The work does not inherit an enclosing product repository's lint policy.
These are editable defaults, not a runtime restriction.

For an older work, merge the following sections into its `pyproject.toml`, preserving
any deliberate existing tool settings. This updates tooling only; it does not upgrade
its locked Tactus or other dependencies.

```toml
[tool.pytest.ini_options]
norecursedirs = [
    "*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}",
    "runs", "pool", "analyses", "exports",
]

[tool.ruff]
line-length = 100
src = ["."]
extend-exclude = ["runs", "pool", "analyses", "exports"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]

[tool.ruff.lint.isort]
known-third-party = ["tactus"]
```

Recovery worktrees can remain under ignored `runs/`; recursive tests and lint skip
them. To check a recovery worktree deliberately, run these commands from that worktree's
own root. Explicit paths or command-line overrides can opt into excluded content; the
exclusions are discovery defaults, not a sandbox.

## Register local functions

```toml
[tool.tactus.analysis]
"stereo.width" = "measurements:width"

[tool.tactus.export]
"my-delivery" = "delivery:bundle"
```

Modules are imported from the work root or installed dependencies. Use distinctive module
names that do not shadow Python or dependency packages. Only the selected custom function is
imported; listing commands does not import all plugins. Built-in name conflicts are errors.
Functions must be synchronous, with the first two arguments as shown below and additional
parameters keyword-only. They remain directly callable from Python.

Parameters become flags: `window_ms: float = 100` becomes `--window-ms 100`. Parameters
without defaults are required. `bool` becomes `--flag` / `--no-flag`; `str`, `int`, `float`
use those types; lists/dicts and other annotations parse JSON. An unannotated flag takes a
string. Use annotations and JSON-valued defaults. `out`, help and dispatch fields are
reserved. Type parsing does not replace validation inside your function.

## Analyze

```python
import numpy as np


def width(audio, sample_rate, *, window_ms: float = 100.0):
    """Measure the first window's stereo side/mid RMS ratio (linear)."""
    if audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError("stereo required")
    frames = round(window_ms * sample_rate / 1000)
    if frames < 1:
        raise ValueError("window too short")
    audio = audio[:frames]
    mid = (audio[:, 0] + audio[:, 1]) / 2
    side = (audio[:, 0] - audio[:, 1]) / 2
    denominator = np.sqrt(np.mean(mid ** 2))
    return {"ratio": float(np.sqrt(np.mean(side ** 2)) / denominator) if denominator else None}
```

The runnable [example](https://github.com/rytho-ai/tactus/tree/main/examples/project-commands) implements windowed values
and an optional array curve.

```bash
tactus analyze --help
tactus analyze stereo width --help
tactus analyze stereo width mix.wav --window-ms 100 --out measurements
```

The function receives decoded audio (mono `(frames,)` or frames-first channels) and its
sample rate. Standalone files decode as float64; run/excerpt directories use the published
WAV loader's float32 arrays. Choose your calculation dtype explicitly when precision matters,
for example `audio = np.asarray(audio, dtype=np.float64)` before squaring/reducing.
It returns a dict. Each input produces one JSON line with `path`, `analysis`,
`revision` (optional function attribute, otherwise null), effective `params`, `sample_rate`,
`result`, `input_sha256` and `provenance`. A run directory measures its published audition
WAVs and adds each output name. It does not substitute original arrays for the heard audio.
Non-finite scalar measurements become null.

Builtin results also include the data declarations described in
[Analysis coordinates and images](runtime.md#analysis-coordinates-and-images).
Custom functions own their returned metadata; the runtime does not infer or attach a
schema for them. If reusing a builtin result while changing its values or coordinates,
update its declarations to describe the new result.

Use `from tactus.analysis import schema` to declare custom data with the same public
helpers as builtins. For example, a signed mono waveform observation (channels averaged):

```python
import numpy as np
from tactus.analysis import schema

def waveform(audio, sample_rate):
    samples = audio if audio.ndim == 1 else audio.mean(axis=1)
    return schema.attach(
        {"clock": np.arange(len(samples)) / sample_rate, "samples": samples},
        sample_rate=sample_rate, frames=len(samples), coordinate_keys=["clock"],
        fields={"samples": schema.series(
            schema.axis("clock", "time", "s", "linear", origin="input_start", at="point"),
            schema.value("sample_amplitude", "FS"),
        )},
    )
```

`attach` returns a shallow result copy with fresh metadata and validates field roles,
selectors, dimensions and window support. Existing arrays stay unchanged. Use `grid`
with explicit `dimensions`, `events` for points/spans, or `summary` for a scalar;
constructors return plain dictionaries. Classify other existing keys using
`coordinate_keys`, `parameter_keys` or `auxiliary_keys`. Unknown semantics can be omitted
in handwritten descriptors. `schema.validate(result)` also checks handwritten schemas;
it does not verify algorithmic correctness, units or estimator accuracy. Legacy custom
results without schema remain supported. This example needs `--out` for arrays and
does not add waveform image support.

`--out DIR` saves each result under its own input/command identity directory, along with
`result.json`. Nested NumPy arrays become attachments in `arrays.npz`; their JSON references
include `file`, `key`, `shape` and `dtype`. Arrays require `--out`; object arrays are rejected.
Existing result directories are preserved and rejected on repeat; choose a new destination
for a fresh execution. A callable may reserve keyword-only `out` to receive a runtime-owned
NPZ file path (or None); returning arrays is simpler for new code, including current STFT.
Logs go to stderr. Freeze accepted analysis results as materials or constants before using
them for creative decisions in `render`.

## Export a completed render

```bash
tactus export wav runs/a --out delivery/pcm
tactus export wav runs/a --subtype DOUBLE --out delivery/original
tactus export flac runs/a --out delivery/flac
tactus export stems runs/a --names '["drums", "bass"]' --out delivery/stems
tactus export my-delivery runs/a --out delivery/label --title "Chosen candidate"
```

`run` saves original returned arrays plus their receipt in `render/` and `render.json` before
writing the default PCM24 audition WAVs. It still renders and delivers in one command. If
that delivery fails after the checkpoint, the original arrays and candidate takes survive;
retry with `tactus export`, without rerunning instruments. Failures before completion remove
the new run directory. Keep `render.json`, `render/` and `receipt.json` together.

This adds storage: float32 arrays use about 4 bytes per sample value, float64 about 8, in
addition to 3 bytes for PCM24 audition audio (plus headers and provenance). There is no
automatic cleanup. Saved takes separately preserve selected intermediate performances as
reusable materials; `take export` transfers one of those bundles.

Export verifies the checkpoint's array and receipt hashes. `wav` defaults to the identical
PCM24 conversion and filenames used by `run`; FLOAT casts to float32 and DOUBLE to float64,
preserving headroom. `flac` and `stems` encode PCM24 with clipping counts. `stems` defaults to
every named output except literal `mix`; explicit `--names` selects a JSON list. `wav` and
`flac` default to every output and accept the same `--names`. No exporter
resamples, aligns, normalizes or assumes stems sum to the master. Older runs/excerpts without
`render.json` use verified saved WAVs; the record labels this `published-pcm`, whose lost
precision/headroom cannot be recovered. A corrupt checkpoint fails instead of using PCM.

A custom exporter receives verified, read-only named arrays and the sample rate:

```python
import soundfile as sf


def bundle(outputs, sample_rate, *, out, title: str = "Demo"):
    """Deliver the chosen mix as FLOAT WAV."""
    sf.write(out / "mix.wav", outputs["mix"], sample_rate, subtype="FLOAT")
    return {"title": title, "mix": "mix.wav"}
```

`out` is a newly created `pathlib.Path` directory, outside the source run. Write artifacts
there and return a finite JSON dict, using relative paths for your files. The runtime hashes
all files and writes `export.json` last, with source identity, callable, effective parameters,
result and provenance. This filename is reserved; symlinks and special files are rejected.
On failure only the newly created delivery directory is removed. Existing output locations
are rejected before calling your exporter. Exporting never invokes the original render code.

## Attribution boundary

Records include input hashes, callable source identity, local Python source inventory,
pyproject hash, dependency lock, actual environment/packages, and declared materials/tools.
Changes to observed input or project source during analysis/export fail the operation.
The source inventory covers local `.py` files, not every external file Python might read.
These are trusted Python functions: external I/O, network, randomness and side effects are
not sandboxed or exhaustively traced. Commit custom code, registration and the work's lock
with the work; pin any additional inputs with `material()` / `tool()`.
