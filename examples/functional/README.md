# Functional productions

Define a synchronous `render()` with explicitly named keyword-only parameters.
Defaults and overrides must be finite JSON values. Required keyword-only parameters
are supported; unknown/missing parameters are errors. There is no type-annotation
coercion. Put production work inside the function; Tactus loads the file under a
non-`__main__` name before calling it.

Return `{"sample_rate": positive_integer, "outputs": {name: numpy_array}}`, optionally
with `takes: {name: numpy_array}` to preserve original intermediate samples. See
[Saved takes](../../skills/tactus-authoring/reference.md#saved-takes).
Each named output is nonempty mono `(frames,)` or mono/stereo `(frames, channels)`,
real numeric and finite. Outputs beyond [-1, 1] are clipped on PCM24 delivery and reported. All outputs share the rate; lengths can
differ and no name is mandatory. Tactus stores float32-to-PCM24 WAVs without
normalization, resampling, limiting or automatic mixing. Each name must match
`[A-Za-z0-9][A-Za-z0-9._-]*`, since it becomes part of the saved WAV's filename.

## Run and compare

Use a new output directory for each invocation:

```bash
uv run tactus run examples/functional/song.py --out /tmp/tactus-song-base
uv run tactus run examples/functional/song.py --out /tmp/tactus-song-candidate \
  --params '{"bass_gain": 0.4}'
uv run tactus run examples/functional/clips.py --out /tmp/tactus-clips
```

The same command executes a stereo mix with mono/stereo stems, or two clips of
different lengths without a mix. `song.py` uses an authored nonlinear mix; the
runtime never sums the declared outputs. `parts.py` uses seconds with no global BPM.
This synthetic study tests the execution boundary, not real-source musical quality.

CLI stdout is one JSON result with output WAV paths, `manifest`, `receipt` and `render`.
Author logs and tracebacks go to stderr. Failures return an error code/phase/message
and a nonzero exit status. Existing destinations are rejected before loading source.
Failures before `render.json` remove the new run directory. After that checkpoint, original
arrays and candidate takes survive a delivery failure; retry with
`tactus export wav RUN --out NEW_DIR`. A manifest marks completed audition delivery;
uncatchable crashes can leave an incomplete directory. Original arrays add storage alongside
WAVs. See [export and project commands](../../docs/project-commands.md).

The Python equivalent is:

```python
from tactus import run

candidate = run(
    "examples/functional/song.py", out="/tmp/tactus-python-candidate", params={"bass_gain": 0.4}
)
```

Each invocation uses a fresh process. Relative imports and assets resolve from the
entry's directory. A parameter candidate does not edit source. Listen to/compare
the returned files with your audio tools. To accept a candidate in this first
version, explicitly edit the source default and run again; automatic promotion
and stateful range audition are not implemented.

## Attribution and saved results

`manifest.json` has kind `tactus.functional-run`, format version 2 (3 with optional `takes`), sample rate and
named AudioRefs (`sha256`, `frames`, `channels`, `file`). WAVs live at
`<out>/<name>-<sha256[:8]>.wav`; identical output bytes under the same name share
the same file. Saved WAVs remain playable without the original source. This format
is separate from the retired prototype `arrangement.json`. `tactus run` executes
the source entry; saved WAVs can be played directly without a separate render or
inspect command.

`receipt.json` records effective parameters including defaults, Python files beneath
the entry's parent, a `uv.lock` in that directory if present, and core runtime
versions. An observed source/lock change during execution fails the run. This is
a bounded inventory: imported code outside that directory, media, hidden randomness
and external processors are not automatically traced or pinned. It does not promise
deterministic source rebuilds or sandbox arbitrary Python/file-system side effects.
