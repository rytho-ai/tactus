# Tactus

Tactus is the active, general-purpose Python-first music production framework, formerly
`tactus-code`.
Python production source, declared materials, and dependency locks own creative intent;
Git records accepted changes. The runtime renders and verifies the resulting audio.
Agents own musical decisions and listening judgment, using their own tools such as Phonon or an
audio model when useful. Tactus owns the production mechanics that make outputs comparable and
traceable; it does not require a DAW-style authoring schema or a built-in musical judge.

For implementation decisions, start with the
[product positioning and principles](docs/positioning.md):
the self-contained, current product and design constraints.
The [current design](docs/design.md) records chosen approaches, their reasons, and undecided
interfaces; it includes directions that are not yet implemented.
The [plan board](docs/blueprints/plan.md) owns current work and delivery status.

The previous implementation is preserved in
[tactus-daw](https://github.com/rytho-ai/tactus-daw) as a reference for tested mechanisms.
This product succession does not imply API compatibility or feature parity. The reference
implementation now installs as `tactus-daw`, imports as `tactus_daw`, and runs as `tactus-daw`.

The default scientific stack includes NumPy, SciPy, SoundFile, pyloudnorm, and librosa;
Pedalboard, pytimestretch, pyqmdsp and Mido are installed as well. Production source can use
these packages directly. `tactus.analysis` exposes level, spectral and beat measurements;
estimated beats and tempo remain observations for the author to evaluate.

## Current status

Functional `render()` productions can now run through a shared Python/CLI entry without a
required BPM, track model or arrangement. Each run saves original arrays, named PCM24 WAVs,
a manifest and an execution receipt. See [functional examples and contract](examples/functional/README.md).
The interface is an initial offline mono/stereo delivery boundary, not a universal work model.

The [real-source chop-flip study](examples/real-chop-flip/README.md) exercises sampling,
pitch-preserving stretch, authored drums/bass, local effects and a parameter comparison.
Production code owns its input identities and musical choices. The runner owns validated
content-addressed WAV delivery and execution records.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are recommended:

```bash
uv sync --group dev
uv run tactus --version
uv run tactus doctor
uv run pytest
uv run ruff check .
```

## Install the CLI once

From this checkout:

```bash
uv tool install --python 3.12 --editable .
tactus init my-work --tactus-path "$PWD"
cd my-work
tactus doctor
```

Use `tactus ...` directly inside the work. The launcher selects its locked uv environment;
`uv add PACKAGE` adds work-specific dependencies. For portable works, pin a published
revision with `tactus init DIR --tactus URL@REV`. See the
[project command contract](docs/project-commands.md) for environment selection.

## Functional production entry

```python
import numpy as np


def render(*, gain=0.2):
    rate = 48_000
    t = np.arange(rate) / rate
    return {
        "sample_rate": rate,
        "outputs": {"clip": gain * np.sin(2 * np.pi * 220 * t)},
    }
```

Use the included modular production or clip bank:

```bash
tactus run examples/functional/song.py --out /tmp/tactus-take-a
tactus run examples/functional/song.py --out /tmp/tactus-take-b \
  --params '{"bass_gain": 0.4}'
tactus run examples/functional/clips.py --out /tmp/tactus-clips
```

Each destination must be new. The command returns one JSON result containing playable WAV
paths, a manifest and a receipt; author logs go to stderr. `from tactus import run` exposes
the same operation as `run(source, out=..., params={...})`, raising `RunError` on failure.
Runs execute in fresh processes, with relative imports/assets resolved from the source directory.
Parameter overrides do not edit source; accepting a candidate currently means an explicit
source edit. No output name, mix, common duration or musical grouping is required.

The [entry contract](examples/functional/README.md) describes parameter/output validation,
failure behavior and attribution limits. Receipts record effective parameters, a bounded
source inventory, the nearest `uv.lock`, pinned input materials resolved with `material()`,
tools declared with `tool()`, and imported package versions. Undeclared files and executables
are not traced. Import input files once with `tactus material add FILE...` and paste the
printed `sha256:` refs into source.
Saved WAVs are replayable, but arbitrary source rebuilds are not guaranteed deterministic.
To hear part of a run, `tactus excerpt RUN_DIR --range START:END --out NEW_DIR` cuts it from the
saved audio without rendering again. Accepting a candidate is a source edit committed with Git.

## Your analysis and delivery commands

Keep custom Python in the work and register it in `pyproject.toml`:

```toml
[tool.tactus.analysis]
"stereo.width" = "measurements:width"

[tool.tactus.export]
"my-delivery" = "delivery:bundle"
```

```bash
tactus analyze stereo width mix.wav --window-ms 100
tactus export my-delivery runs/a --out delivery/label
tactus export wav runs/a --subtype DOUBLE --out delivery/original
tactus export stems runs/a --out delivery/stems
```

`run` saves original audio before its default audition delivery. `export` creates another
format from that saved render, including after an encoding failure, without regenerating
instruments. Built-ins are `wav`, `flac`, and `stems`; custom functions use the same parameter,
result and provenance machinery. Original arrays cost additional storage alongside audition
WAVs. See the [runnable example](examples/project-commands/README.md) and
[function contracts](docs/project-commands.md).

## Preserve an instrument performance

Use original VST3/SFZ instruments. When a performance should stay fixed, have `render()`
return its raw array in an optional `takes` mapping alongside the usual audition outputs:

```python
def render(*, gain=0.25):
    raw = synthesize()  # your generator, called once for this candidate
    return {"sample_rate": 44100, "outputs": {"mix": raw * gain}, "takes": {"pad": raw}}
```

After listening to that run, save the selected take:

```bash
tactus take save runs/take-a pad
```

Paste its printed ref into the work and use `load_take` before further processing:

```python
from tactus import load_take

PAD_TAKE = "tree:sha256:…"

def render(*, gain=0.25):
    raw = load_take(PAD_TAKE, sample_rate=44100)
    return {"sample_rate": 44100, "outputs": {"mix": raw * gain}}
```

Takes preserve the original samples, dtype, shape and headroom, with a source snapshot and
receipt. They live in the material pool independently of stage cache and run directories.
Changing MIDI or a patch means generating and selecting a new take; old refs remain usable.
Playback needs no generator instrument. Gain, effects and placement remain editable in code.

To move a take, use `tactus take export REF --out take-bundle`, copy the folder, then run
`tactus material add take-bundle` on the destination machine. It returns the same ref.
Also transfer the work's source/lock and other required materials. See
[Saved takes](skills/tactus-authoring/reference.md#saved-takes) for the full lifecycle and
provenance limits.

## Supported surface

The CLI provides `init` (with `--tactus-path`/`--tactus`), `run` (with `--reuse`), `excerpt`,
`analyze CATEGORY NAME` (categories `level`, `spectral` and `rhythm`; `tactus analyze --help` lists
categories, `tactus analyze CATEGORY --help` lists analyses, `tactus analyze CATEGORY NAME
--help` gives parameters and definitions), `export NAME`, `material add`, `take save`, `take export`, `doctor`, help and version.
The public Python exports are `run`, `excerpt`, `RunError`, `AudioRef`, `material`, `tool`,
`load_audio`, `load_take`, `MaterialError`, `ToolError`, `stage`, the `fx` module, the `timing` module and
the `analysis` module.
Agents writing a work should use the [`tactus-authoring` skill](skills/tactus-authoring/SKILL.md)
(high-level rules; details in its [`reference.md`](skills/tactus-authoring/reference.md)). The
production function is named `render()`; execute it
through `tactus run`. Read the returned paths and manifest/receipt directly, and play the WAVs
with your audio tools.

The earlier Project/Track arrangement prototype and its build/render/inspect/diff commands
have been removed. There are no compatibility aliases or arrangement-format loaders.
The distribution, Python import, and command are all `tactus` (version `0.1.0`).

### Beat analysis

```bash
tactus analyze rhythm beats loop.wav > beats.json
tactus material add beats.json
```

Each stdout line is one JSON object; its `result` contains `beats_s` (seconds), `bpm` (median tempo), and `tempo_curve`
(BPM between consecutive beats). Python: `from tactus.analysis import rhythm`, then
`rhythm.beats(audio, sample_rate)` with `(frames,)` or `(frames, channels)` audio.
Channels are averaged to mono. Freeze accepted results as source constants or a pinned
material before using them for slicing or alignment inside `render`.

Beat tracking uses [pyqmdsp](https://github.com/openmirlab/pyqmdsp), pinned in the dependency
lock, with no Vamp installation or separate Tactus native build. Source installation needs
a C/C++ toolchain. Short material (roughly 7.45 seconds or less of active audio) or silence
returns empty arrays and `bpm: null`. Beat tracking does not identify meter or downbeats.
The [integration check](experiments/pyqmdsp-integration/README.md) records corpus parity
and its accuracy limits.

## Working hypothesis

- People and agents edit Python source, declared assets, and dependency locks; Git versions them.
- Generated audio and execution records are derived artifacts, not a second editable project.
- The runtime should make production outputs inspectable and reproducible without dictating every
  musical algorithm.
- NumPy DSP, external tools, and specialized production code should remain usable as ordinary
  source, subject to an explicit execution and materialization boundary.

Ordinary Python can already use installed DSP/analysis libraries. Shared temporal/Pattern APIs,
MIDI file delivery and selective caching remain open directions, to be implemented when concrete production needs justify them. See the
[vertical-slice plan](docs/blueprints/plans/2026-09-16-code-first-production-slice.md).
