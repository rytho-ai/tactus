# Tactus

Tactus is a Python-first music production runtime for people and agents. Write music as
code, render audio, listen, and revise. Tactus handles execution and records what produced
each result; the author makes the musical decisions.

## Core ideas

- **Code owns the work.** Python source, pinned materials and dependency locks capture
  creative choices; Git records revisions.
- **Compose freely.** Combine builtin DSP, existing libraries, VSTs and your own functions.
  Choose the timing, routing and arrangement that suit the music.
- **Maintain music as code.** Use functional, modular code with clear interfaces; reveal
  implementation details as needed when reading or revising a work.
- **Listen and iterate.** Render separate candidates, use measurements as observations,
  and preserve the performances you choose.

## Install

### CLI and dependencies

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git first.
Tactus uses Python **3.12**; uv can install it. Git-sourced native dependencies also need
C and C++20 compilers, such as GCC or Clang.

```bash
git clone https://github.com/rytho-ai/tactus.git
cd tactus
uv tool install --python 3.12 --editable .
tactus doctor
```

The editable install follows this checkout;
see [fixed-revision installation](skills/references/project-commands.md#install-and-select-a-work)
for a portable setup.

### Core dependencies

The CLI installation automatically installs these runtime packages:

| Package | Role |
|---|---|
| **NumPy** | Audio arrays, synthesis, mixing and numerical operations |
| **SciPy** | Filters, resampling, FFT and analysis algorithms |
| **SoundFile** | Audio file reading and writing |
| **Numba** | Accelerated numerical kernels for DSP and analysis |
| **Pedalboard** | Audio effects and VST3 hosting |
| **pytimestretch** | Time stretching, pitch shifting and marker-based warping |
| **pyqmdsp** | QM-DSP beat tracking |
| **Mido** | MIDI messages and files |

Each work has its own locked environment. Add further dependencies there with `uv add PACKAGE`;
librosa is optional via `uv add "tactus[librosa]"`. External instruments, VST plugins and
sample libraries are installed separately. See [package notes](skills/references/packages.md)
for integration details; [pyproject.toml](pyproject.toml) and `uv.lock` record dependency constraints and pins.

### Agent skills

The `tactus` plugin provides **compose** (write and revise works), **dsp** (use or build
effects) and **measure** (use or write analyses). Install it from this repository root
for your agent host.

**Codex:**

```bash
codex plugin marketplace add .
codex plugin add tactus@tactus-local
```

**Claude Code:**

```bash
claude plugin marketplace add "$PWD"
claude plugin install tactus@tactus-local
```

Start a new session to load the skills. Both hosts share the same content; see the
[plugin guide](skills/README.md) for skill details and updates.

## Your first audio

From the Tactus checkout, create a separate work:

```bash
tactus init ../my-work --tactus-path "$PWD"
cd ../my-work
```

Save this as `song.py`:

```python
import numpy as np
from tactus import dsp


def render(*, gain=0.2):
    sample_rate = 48_000
    t = np.arange(2 * sample_rate) / sample_rate
    tone = gain * np.sin(2 * np.pi * 220 * t)
    audio = dsp.fade(tone, sample_rate, in_s=0.01, out_s=0.1)
    return {"sample_rate": sample_rate, "outputs": {"mix": audio}}
```

Render it, then try a quieter candidate:

```bash
tactus run song.py --out runs/a
tactus run song.py --out runs/b --params '{"gain": 0.1}'
```

Each output directory must be new. The command returns WAV paths, levels and execution
records. Play the WAVs with your audio tools. Parameters let you compare candidates without
editing source; adopt the values you choose in the work's code.

## Go further

- [Creative examples](skills/examples/README.md): custom effects, library combinations and analysis-driven time warping.
- [Runtime reference](skills/references/runtime.md): materials, rendering, excerpts and saved takes.
- [DSP](skills/references/dsp.md), [analysis](docs/analysis.md) and [custom analysis/export](skills/references/project-commands.md).
- [Product principles](docs/positioning.md), [current design](docs/design.md) and [development setup](docs/development.md).
