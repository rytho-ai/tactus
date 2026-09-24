# Functional production entry and CLI — implementation plan

> Updated: 2026-09-24 · Paul approved implementing the minimal `render()` boundary after the entry-format probe and follow-up discussion. Status: implemented and verified. Completion evidence and remaining limits are recorded below.

> Compatibility supersession: Paul subsequently requested removing the old approach entirely.
> The [retirement plan](2026-09-24-retire-arrangement-prototype.md) supersedes every compatibility
> requirement below for Project/Track, format-v1 arrangements and build/render/inspect/diff.
> Earlier verification results remain historical evidence of the code tested at that time.

## Accepted scope after the probe

The [entry-format probe](../thoughts/2026-09-24-entry-output-format-necessity-probe.md)
showed that ordinary Python can deliver the audio without a universal work format.
It did not test the value of one caller executing different works and parameter candidates.
Paul chose a consistent execution/handoff boundary: `render(*, ...)` returns
`{sample_rate, outputs}`; the internal musical structure remains ordinary Python.
The name is `render`, because it generates audio; the runner owns file export.

Implement one public runner and one CLI adapter, with existing MaterialStore delivery.
Validate the shared-caller benefit on both a modular mix/stem work and a clip-bank work.
Candidate acceptance is an explicit source edit in the verification workflow; automatic
promotion, live sessions, arrangement schemas, registration and parameter UIs remain deferred.
No claim that all music production must use this interface follows from this decision.

## Context

`build.py` executes `build(project)` and requires `TRANSPORT` with BPM, bars, and sample rate.
`Project` requires tracks; `render.py` derives duration and placement from beats. Ordinary Python
can produce the intended audio, but handing it to this runtime requires extra musical structure.

`cli.py` exposes build/render/inspect/diff and prints JSON on successful operations. Source
printing can contaminate stdout; source exceptions do not have a common machine-readable
result. Existing tests cover format-v1 replay, material integrity, revision, and media inputs.

The first slice should accept completed audio from a plain function and provide a reliable run
boundary. Keep existing commands and format-v1 artifacts compatible. The existing real-source
production slice remains the musical acceptance gate; this slice establishes the runtime entry.

## Existence evidence and validation

### Assumptions to challenge

Paul asked how to check that the interface makes no unnecessary musical assumptions.
For each constraint, identify its consumer and the failure it prevents. Distinguish
caller coordination from temporary support limits; neither is a universal music model.

| Assumption | Consumer/reason | Evidence or remaining limitation |
| --- | --- | --- |
| One named entry, named parameters and named outputs | Generic runner and candidate caller | Exercise the same caller against a modular mix/stem work and a clip bank. |
| Keyword-only finite JSON parameters | CLI transport and effective-parameter receipts | Initial support limit; richer Python arguments are not inherently invalid music. |
| One sample rate per result | One existing MaterialStore per invocation | Initial support limit; mixed-rate deliverables remain unsupported, not disproven. |
| Mono/stereo PCM24 output within full scale | Existing WAV delivery and validation | Initial support limit; does not constrain intermediate DSP or establish other layouts unnecessary. |
| Finite arrays returned together | Offline delivery | Streaming/live execution is untested; no general claim follows. |
| No required BPM, tracks, mix or equal duration | Preserve author structure | Free-time mix/stems and unequal-length clips must pass without musical rewrites. |

Adapter work may describe the handoff, but must not force fabricated transport,
padding, regrouping or automatic mixing. Passing the two fixtures supports only
their tested scope; new works that require musical rewrites should reopen the boundary.

| Capability | Why it belongs in this slice | Evidence and deciding check |
| --- | --- | --- |
| Function outputs without transport/tracks | Accept the chosen Python authoring approach, including free-time works | Current build explicitly rejects missing TRANSPORT and Project rejects missing tracks. A no-BPM function must complete unchanged through the new runner. |
| Shared output validation/storage and receipt | Remove repeated export and attribution work from production source | MaterialStore already owns these audio checks and storage. Compare plain Python delivery and Tactus delivery on identical musical code, including a failed run. The value beyond direct Python remains to be demonstrated. |
| Fresh process per invocation | Prevent prior imports and mutable DSP/module state from affecting a later run | A stateful module invoked twice through the Python runner must give independent runs. Process isolation does not imply isolation of arbitrary external services or files. |
| CLI JSON and separate diagnostics | Allow an agent to reliably consume results even when source or native libraries log | Print from Python and a native-style file-descriptor write, then parse exactly one command result. |
| New output directory per run | Prevent a failed candidate from appearing to return earlier audio | An existing destination is rejected before source execution; a failed new run has no completed manifest or success response. |
| Composition registration/discovery | No current acceptance task needs multiple registered works or metadata discovery | Deferred. Remotion is a design reference, not evidence that this capability is needed here. |

Validation can occur before or after implementation. Keep the shared-delivery value claim open
until the workflow comparison is complete; technical test success alone does not close it.

## Implemented contracts

### Production source

The entry is a Python file defining a synchronous `render` function. The first version accepts
only explicitly named keyword-only parameters; defaults and supplied values must be finite,
JSON-serializable data. No required annotations, decorator, registration object, Project, Track,
BPM, fixed directory layout, or __main__ block. Required keyword-only arguments are allowed;
missing and unknown arguments are rejected before invoking the function. Variadic and positional
parameters are outside this first entry contract. Do not coerce values using type annotations.

Imports and function definitions may run during loading, but loading must not call render or
export audio. Execute the module with a non-__main__ name. Author source follows this lifecycle
convention; Tactus does not sandbox arbitrary Python or prevent arbitrary import side effects.

The function returns exactly these two fields:

```python
import numpy as np


def render(*, bass_gain: float = 0.8):
    sample_rate = 48_000
    t = np.arange(sample_rate) / sample_rate
    bass = bass_gain * 0.2 * np.sin(2 * np.pi * 110 * t)
    texture = 0.05 * np.sin(2 * np.pi * 440 * t)
    return {
        "sample_rate": sample_rate,
        "outputs": {
            "mix": bass + texture,
            "stem:bass": bass,
        },
    }
```

- `sample_rate`: a positive integer, excluding bool; shared by all outputs in this result.
- `outputs`: a nonempty dictionary of nonempty string labels to NumPy arrays. Labels are
  metadata, never filesystem paths. No label, including mix, is mandatory; the example uses
  mix/stems to exercise the intended workflow. Tactus does not derive a mix by summing outputs.
- Arrays: real numeric, nonempty mono `(frames,)` or mono/stereo `(frames, channels)`, finite,
  and within [-1, 1]. Reject complex, object, and bool arrays rather than silently converting
  their meaning. Output lengths may differ; each duration follows its own frame count.
- Reuse the existing float32-to-PCM24 materialization boundary. Quantization is explicit;
  no normalization, limiting, resampling, padding, or trimming is introduced. This is a bounded
  delivery format, not a rule that every intermediate DSP signal must stay below full scale.

This example illustrates the contract, not musical acceptance. The actual acceptance example
will use separate part functions and a short free-time arrangement while preserving this shape.

### Python runner and CLI

Public Python operation: `tactus.run(source, *, out, params=None)`. Re-export it from `__init__.py`.
It always invokes a fresh child process, returns a success dictionary, or raises `RunError` with
code, phase, and message. It never prints the machine-readable result itself.

CLI adapter:

```bash
uv run tactus run examples/functional/song.py --out /tmp/tactus-take-a
uv run tactus run examples/functional/song.py --out /tmp/tactus-take-b \
  --params '{"bass_gain": 0.4}'
```

`--out` is required. `--params` is one JSON object, defaulting to `{}`; reject malformed JSON,
duplicate keys, NaN/Infinity, and a non-object top level. The Python API applies the same value
constraints and permits only string parameter keys. Bind the signature and capture effective
parameters, including defaults, before invocation. Parameter overrides do not rewrite source.
No additional --set, params-file, alternate entry-name, or overwrite modes in the first slice.

Resolve source/out paths relative to the caller before starting the child. The source parent is
the child working directory and is placed on its import path, so sibling modules and relative
assets work consistently from different calling directories. Keep the parent cwd and imports
unchanged. Use the active Python interpreter and environment; do not install dependencies at run time.

For execution invocations, stdout contains exactly one JSON result. Source prints, native stdout,
tracebacks, and progress belong on stderr. Help remains ordinary CLI help.

Success response (paths are absolute):

```json
{
  "status": "ok",
  "outputs": {"mix": "/tmp/tactus-take-a/materials/audio/<digest>.wav"},
  "manifest": "/tmp/tactus-take-a/manifest.json",
  "receipt": "/tmp/tactus-take-a/receipt.json"
}
```

Each output path points to the materialized WAV; output names need no filename escaping or
second audio copy. Identical named outputs may refer to the same content-addressed file.

Failure response:

```json
{
  "status": "error",
  "error": {"code": "invalid_output", "phase": "validate", "message": "Output mix contains NaN"}
}
```

Use phases `request`, `load`, `bind`, `execute`, `validate`, and `publish`; stable codes identify
invalid_request, output_exists, load_failed, invalid_parameters, execution_failed, invalid_output,
publication_failed, worker_failed, source_changed, and cancelled. Exit 2 for request/load/bind
errors, 1 for execution/validation/publication/worker errors, and 130 for cancellation. Syntax
errors include file/line context; user tracebacks remain available on stderr. Existing commands
retain their current response contracts. Do not return success after source SystemExit or an
abrupt worker exit without a valid completion result.

### Artifacts and source attribution

One run directory contains `materials/audio/`, `receipt.json`, and `manifest.json`. This is a
separate result format from the format-v1 arrangement; do not pretend final arrays are tracks.

The manifest has `kind: "tactus.functional-run"`, `format_version: 1`, `sample_rate`, and
`outputs` mapping labels to AudioRef fields (`sha256`, `frames`, `channels`). The format defines
material paths using the existing store convention. The receipt uses the same kind/version and
records the entry path/name, effective parameters, source hashes, observed dependency-lock hash,
Python/Tactus/NumPy/SoundFile versions, and an explicit saved-output replay/source-rebuild limitation.
No new public replay command is required: these are playable WAV outputs; tests use MaterialStore
integrity verification to demonstrate replay without source.

Inventory Python files beneath the entry's parent, excluding generated output, .tactus,
.tactus-code, .venv, and __pycache__. Hash a uv.lock at that root when present. Capture before
loading and check the same inventory and lock before publication; if changed, fail with
source_changed rather than issue a misleading receipt. This is a scoped inventory, not a complete
Python dependency tracer or a concurrency lock. It does not establish media pinning, record all
files arbitrary Python may read, or roll back changes made by author code.

Reserve the requested output directory with exclusive creation before executing source. Reject
any existing directory, including an empty one, and leave it untouched. Write receipt/materials
inside the new directory and publish the manifest last using atomic file replacement; the final
manifest is the completion marker. Emit success only after publication. On handled failure or
cancellation, clean only this run's reserved artifacts and reap the worker; never remove a
pre-existing destination. After an uncatchable process/machine failure, an incomplete directory
may remain without a completion manifest and must not be mistaken for a successful run.

This deliberately avoids replacing old results and directory-swap claims. The generated directory
must not be the source root or an ancestor. Tactus itself does not modify source or Git history;
the unchanged-source acceptance check exercises that property for the supplied fixture.

## Approach and critical files

### 1. Land the boundary fixture and result contract

Add `examples/functional/song.py` and ordinary part modules with explicit seconds and no global
BPM. Include an authored nonlinear mix so tests detect accidental stem summation. Document the
entry contract and the two CLI invocations in its README. Define and validate the result/parameter
rules in `src/tactus/run.py`; reject bad output before publishing a completed result.

### 2. Implement the shared execution operation

`src/tactus/run.py` owns the public runner, RunError, request validation, process lifecycle,
result validation, artifact publication, and receipt/manifest contract. A small private
`src/tactus/_worker.py` module loads source and calls that shared execution code in the child.
Keep composition logic in the example, not in the runner.

Use a private request/result file protocol between parent and child. Forward child stdout and
stderr to diagnostic stderr; do not use source-controllable stdout as the protocol channel.
Verify the child exit status and structured response, including abnormal exits. Avoid importing
production code in the parent. Reuse MaterialStore and AudioRef without changing their existing
wire format or relaxing their checks.

The new module must not depend on private build.py helpers. Keep its narrowly scoped inventory
and publication helpers local until a shared abstraction has two compatible consumers; do not
refactor the old build path just to save a few lines in this slice.

### 3. Add the CLI adapter and preserve existing consumers

Add `run` in `src/tactus/cli.py`; all execution uses `tactus.run`. Map RunError to the agreed JSON
and exit status, including run-argument failures. Re-export run and RunError in `__init__.py` while
preserving AudioRef/Project/Track exports. Existing build/render/inspect/diff and format-v1
examples stay compatible. No packaging dependency changes are needed.

### 4. Verify correctness and demonstrate value

Use `tests/test_functional_run.py` for Python/subprocess boundary checks and
`tests/test_cli.py` for the additive CLI contract. Keep the existing production tests intact.
Carry out the workflow comparison below and record observations under completion evidence in
this plan; do not prefill successful results or claim independent agent trials.

After verification, update README commands, docs/design.md with the implemented interface and
its limits, and the existing board with actual delivery status. Only implementation advances
those documents from proposed to supported behavior.

## Verification

### Correctness

1. Execute the modular no-BPM example through Python and CLI in separate output directories.
   Verify names, rate, per-output frames/channels, and PCM values within encoding tolerance.
   Compare the authored nonlinear mix with its direct-Python reference.
2. Change only bass_gain: source bytes remain unchanged, the intended outputs change, and an
   unrelated declared output remains identical. Repeated calls through the same parent process
   must not retain a deliberately mutated module global or imported helper state.
3. Test signature binding and effective defaults, nested JSON values, unknown/missing parameters,
   malformed JSON, invalid sample rate, nonfinite/complex output, empty output, differing output
   lengths, and full-scale rejection. Failures produce no complete manifest.
4. Test source prints and file-descriptor stdout writes; CLI stdout remains one parseable JSON
   value. Exercise import errors, render exceptions, source SystemExit, abrupt worker exit, and
   caller cancellation, with the intended exit status and diagnostic context.
5. Reject an existing output directory before loading source. Fail after at least one material
   is written and verify no success marker survives; preserve pre-existing data. Exercise an
   in-scope source/lock change before publication and report source_changed honestly.
6. Move a completed run away from the source project and read all outputs from its manifest
   using MaterialStore. Verify digest and metadata checks reject tampering.
7. Run full pytest, Ruff, `uv build`, installed CLI --help/version/doctor/run, and the existing
   build/inspect/render/diff regression path. Use the active uv environment. This is the required
   code-change/package interface gate, not a request to run it during planning.

### Value compared with plain Python

Use the same musical functions and two parameter candidates in both paths. The baseline is
ordinary Python plus SoundFile, with a reasonable small local helper allowed. First compare
basic delivery honestly; then request the same output names, validation, parameter/source
attribution, and failed-run handling from both paths. Do not cripple the baseline to favor Tactus.

Record source adapters/export plumbing required, manual steps to associate audio with a candidate,
error diagnosis, and accidental-source/stale-output risks. Record startup/run overhead separately.
Do not use line count alone or claim a general productivity benchmark from one example.

Accept the delivery-value claim only if production code can keep its musical functions while
Tactus removes concrete repeated handoff work and provides usable failure results. If the local
helper is equally sufficient and the runner adds unexplained ceremony, narrow or revise the
runtime contract before treating that value claim as established. Technical correctness and
musical quality are separate results; Paul's real-source listening gate remains ahead.

## Deferred decisions and scope

- Composition registration, metadata discovery, selectable entry names, and schema-driven
  parameter editors: require a concrete workflow beyond this single entry.
- Temporal helper APIs, Pattern, live playback, streaming, selective caching, and background jobs:
  excluded from the full-array delivery baseline.
- Source-pinned real media: choose inline digest versus tracked lockfile when connecting the
  real-source production slice; its absence must remain explicit in receipts/documentation.
- Stateful range audition, guarded candidate promotion, and arbitrary source-edit isolation:
  subsequent work; parameter overrides alone do not implement these contracts.
- Wider channels, alternate audio encodings, and high-headroom intermediate storage: revisit when
  a real output needs them; preserve the initial mono/stereo PCM24 contract in this slice.

## Completion evidence — 2026-09-24

Implemented `src/tactus/run.py`, the private `_worker.py` process entry, public exports,
the additive `run` CLI, and `examples/functional/` with shared musical functions and two
different work shapes. Existing build/render/inspect/diff contracts remain available.
README, the self-contained current design, and the board now describe actual support.

### Correctness and interface checks

- `uv run --locked --inexact pytest -q`: **58 passed** (16.39 seconds).
- `uv run --locked --inexact ruff check .`: passed. `git diff --check`: passed.
- `uv build`: sdist and wheel built; the wheel was installed into a disposable target.
  The package import was verified to resolve to that target, not the working-tree source.
- **15 installed CLI checks** covered help/version/doctor, functional mix/stem and clip-bank
  execution, gain candidates, invalid output, real-source outputs, and the existing
  build/inspect/render/diff workflow. All passed.
- Tests cover original/candidate/base-again, explicit source-default acceptance, nonlinear
  mix preservation, differing clip lengths, replay after source removal and hash tampering,
  local imports/assets, effective defaults and nested parameter mutation, source/lock changes,
  invalid signatures/JSON/audio, Python/native logs, partial publication, abnormal exits,
  occupied output preservation, and CLI cancellation with worker reaping and cleanup.
- A concrete freshness risk was found during review: an existing timestamp-based `.pyc`
  can survive a same-size source edit within its timestamp granularity. Workers now use
  a private bytecode lookup location with writes disabled. A stale-cache fixture verifies
  execution follows revised helper source, not the previous cached code.

### Shared-caller and plain-Python comparison

The same installed command executed `song.py` (a free-time nonlinear mix plus mono/stereo
stems) and `clips.py` (unequal-duration clips without a mix). No caller changes, fake transport,
padding or automatic grouping were needed. Changing only bass_gain preserved the texture output
and source bytes; explicitly accepting that gain in source reproduced the candidate manifest.

The real-source work from the earlier format probe also ran through this entry without changes
to its musical functions. Base, gain candidate and clip-bank WAV hashes exactly matched the
plain-Python/local-helper baseline. The base mix SHA256 remains
`6c929379517e6fcb2471b70e783e5a2fd350d4db22297153ae8bba29dedb4f9f`.

The direct baseline already had reusable WAV validation, identity checks and receipts; it was
not reduced to a deliberately weak `sf.write` call. Tactus supplies those delivery mechanics
through a common entry and additionally owns signature/default binding, structured error phases,
fresh-process execution and handled-failure cleanup. Production code hands off arrays rather
than implementing its own caller/export/receipt plumbing. Both paths can associate candidates
with audio; neither requires manual filename inference when its receipt is used.

One descriptive timing pair on the same real-source gain candidate: plain Python/local helper
**0.275 s**, installed Tactus **0.574 s**, including process startup and export. This is not a
performance benchmark; the additional process, fresh bytecode loading, inventory and publication
have a cost. No speed or independent Agent-productivity claim is made.

This validates the narrow coordination benefit requested by Paul: one caller can execute
different works and parameter candidates and consume a consistent result. It does not overturn
the probe's finding that ordinary Python is sufficient for producing these sounds, nor prove
all first-version support limits necessary. Musical listening quality, live/session behavior,
mixed-rate or multichannel delivery, full dependency attribution and stateful range audition
remain unverified or unsupported as listed above.

Disposable evidence, installed wheel, comparison audio and command results are under
`/tmp/tactus-functional-final-hZffFY/`; real source media and derivatives were not published.
