# Tactus / pyqmdsp integration verification

The Tactus CLI matched direct `pyqmdsp.beats()` exactly on all 72 evaluation files for
beat times, BPM and tempo curve. The adapter changes only serialization (arrays to lists)
and the no-estimate BPM sentinel (`0.0` to `null`). No algorithm parameters are changed.

## Corpus result

- Python 3.12.11, Linux x86_64; pyqmdsp `09b36d656b347425ba36c1c38ca372b337f0b527`.
- 31 synthetic files made from real drum hits and 41 annotated Ballroom recordings.
- F-measure uses a ±70 ms tolerance, averaged per file.
- Saved Vamp reference mean: **0.8653417145098259**.
- Tactus mean: **0.8648494122221307**.
- Absolute mean difference: **0.0004923022876951455**, below the **0.005** gate.
- Exact Tactus CLI/direct-package equality: **72/72**, all three fields.

Per-file values, audio hashes, engine revision, compiler and installation provenance are in
[`report.json`](report.json). These are bounded corpus results, not universal beat accuracy
or cross-platform bit-identity claims. The package's separate
[original qm-dsp comparison](https://github.com/openmirlab/pyqmdsp/tree/09b36d656b347425ba36c1c38ca372b337f0b527/verification/upstream)
checks direct original C++ outputs; this check tests Tactus's integration and the Vamp score gate.

Five files have different F-measures from the saved Vamp build, as in the package evaluation:

| File | Tactus F minus Vamp F |
|---|---:|
| Quickstep_Media-105122 | -0.03658536585365857 |
| VienneseWaltz_Media-103308 | -0.022727272727272707 |
| Waltz_Media-104202 | +0.030769230769230715 |
| Waltz_Media-104401 | +0.022727272727272707 |
| Waltz_Media-104801 | -0.02962962962962956 |

The original prototype investigated toolchain floating-point sensitivity in the tracker.
Passing the score gate does not make individual Vamp beat arrays identical.

## Reproduce

Use the Tactus checkout with its committed lock and a source checkout of pyqmdsp at the
revision above. Truth and Vamp reference JSON live in that package's `verification/beats/`;
its [SOURCES.md](https://github.com/openmirlab/pyqmdsp/blob/09b36d656b347425ba36c1c38ca372b337f0b527/verification/beats/SOURCES.md)
documents audio provenance and reconstruction. Audio is external; no recordings are stored here.
Synthetic reconstruction currently also needs the local prototype scripts and original sample
libraries noted there. The hashes in the report identify the exact audio used for this run.

```bash
uv sync --locked
uv run --with mir_eval python experiments/pyqmdsp-integration/check.py \
  AUDIO_ROOT PYQMDSP_CHECKOUT/verification/beats \
  --output /tmp/tactus-beat-report.json
```

The script calls the real CLI for every file, compares every returned field with direct
package calls, then scores against the saved annotations. A failure in either comparison
exits nonzero. `mir_eval` is an evaluation-only dependency.

## Consumer checks

The full Tactus suite passed: **400 passed, 1 skipped** (the opt-in installation test).
That installation test also passed when enabled explicitly. Ruff and sdist/wheel builds
passed. A fresh work created with `tactus init --tactus-path` installed the pinned package
and analyzed a real recording successfully in its own environment.

A fresh Agent, given only the authoring skill and two recordings outside the 72-file corpus,
discovered the CLI, saved both results, imported them into an isolated material pool and read
them back byte-for-byte. The parent independently repeated the analysis and material calls;
[`user-trial.json`](user-trial.json) records audio hashes and results. It initially assumed
an incorrect JSON shape in a `jq` selector, then recovered by inspecting output. README and
authoring reference now explicitly document `.result.beats_s`. These recordings have no
provided ground truth, so this trial establishes usability and persistence only.
