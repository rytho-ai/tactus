# Clean production handoff

A bounded acceptance trial using Paul's 46-bar, 74 BPM ambient work. It exercises a fresh
Linux environment, full input restoration, one-stem revision and aligned delivery.
No Tactus runtime API was added. Inputs, native binaries and rendered audio stay outside Git.

## Result

**Saved-performance handoff passed. Regenerating the instruments did not.**

- First fresh synthesis: drums, keys and textures matched; SFZ bass differed on four notes.
  OB-Xf outro RMS differed by 1.075 dB, exceeding the predeclared 1 dB section threshold.
- A raw SFZ probe, restricted to one CPU, produced different WAVs from identical inputs.
  No Tactus processing is involved in that probe. The engine's internal cause is unresolved.
- Second trial pinned the host baseline's pre-gain pads and bass arrays as materials. A new
  pool and stage cache, inside a network-disabled container, reproduced **all six WAVs exactly**.
  This preserves that host performance; it does not recreate the older accepted OB-Xf take.
- Changing bass gain from -3 to -6 dB changed only bass and mix. Four other stems matched
  byte-for-byte; measured bass change was -3.00000047 dB. All five stages were reused.
- Fourteen missing/corrupt input and missing-tool cases failed explicitly; restored inputs
  passed. Delivery ZIP was unpacked and all 231 files verified. The source records the frozen
  refs; the generation source and receipt remain included.

See [evidence.json](evidence.json) for measured values and the limitations below.

## Files

| File | Responsibility |
| --- | --- |
| `work/song.py` | Portable synthesis copy: explicit tool declarations and five opt-in stages |
| `work/pyproject.toml`, `work/uv.lock` | Independent work environment, relative archived Tactus dependency |
| `prepare.py` | Required blob closure, tool hashes, fixed Tactus source archive |
| `Dockerfile`, `.dockerignore` | Fresh Python/native build; no host environment or assets in image |
| `run_isolated.py` | Negative checks, restoration, baseline and bass candidate |
| `probe_sfizz.py` | Raw SFZ repeatability probe, independent of runtime and effects |
| `freeze.py` | Pin pre-gain performances with generation provenance; keep synthesis evidence |
| `evaluate.py` | Actual WAV, receipt, revision, isolation and delivery checks |
| `index.html` | Chinese listening/download page, served beside measured artifacts |

The original source remains untouched. Portable-source changes are tool paths/declarations,
`@stage` annotations, formatting and removal of an unused import. Notes, DSP and mix defaults
are preserved. `freeze.py` makes a second explicit source revision: the two stage functions
read pinned NumPy arrays with `allow_pickle=False`; their generators remain in source.

## Reproduce the trial

Run preparation/evaluation with this repository's `uv run python`. Preparation requires the
private original song/pool and exact native tools. It refuses an existing transfer destination.

```bash
uv run python experiments/clean-production-handoff/prepare.py "$TRIAL_ROOT/transfer" \
  --original dogfood/2026-09-25-full-song-3/work \
  --pool dogfood/2026-09-25-full-song-3/pool \
  --plugin /path/to/OB-Xf.vst3 --sfizz /path/to/sfizz_render
uv sync --frozen --project "$TRIAL_ROOT/transfer/work" --python 3.12.11
TACTUS_POOL="$TRIAL_ROOT/transfer/pool" uv run --frozen \
  --project "$TRIAL_ROOT/transfer/work" tactus run \
  "$TRIAL_ROOT/transfer/work/song.py" --reuse --out "$TRIAL_ROOT/host-baseline"
```

Set `TRIAL_ROOT` to a new **absolute** local directory. Preserve its generated `pool/stages`
as `$TRIAL_ROOT/host-stages` and `pool/trees` as `$TRIAL_ROOT/host-trees` before transport;
those are host caches and must not enter the destination pool. The checked-in work lock pins the versions used in this trial. Build with:

```bash
docker build -t tactus-clean-handoff:20260928 "$TRIAL_ROOT/transfer"
mkdir "$TRIAL_ROOT/isolated"
docker create --name tactus-handoff-trial --network none \
  --mount "type=bind,src=$TRIAL_ROOT/transfer/pool,dst=/incoming/pool,readonly" \
  --mount "type=bind,src=$TRIAL_ROOT/transfer/tools,dst=/incoming/tools,readonly" \
  --mount "type=bind,src=$TRIAL_ROOT/transfer/inventory.json,dst=/incoming/inventory.json,readonly" \
  --mount "type=bind,src=$TRIAL_ROOT/isolated,dst=/trial" \
  tactus-clean-handoff:20260928
docker inspect tactus-handoff-trial > "$TRIAL_ROOT/container-inspect.json"
docker start -a tactus-handoff-trial
uv run python experiments/clean-production-handoff/evaluate.py "$TRIAL_ROOT" \
  --approved-run dogfood/2026-09-25-full-song-3/work/runs/c7
```

Expect the synthesis evaluation to be capable of failing; do not retry until a favorable take
and discard failures. To make the saved-performance variant:

```bash
uv run python experiments/clean-production-handoff/freeze.py "$TRIAL_ROOT" "$FROZEN_ROOT"
```

Use a new absolute `FROZEN_ROOT`. Repeat host sync/render, move its host caches, build a
separate image/tag, and create a new container/destination using that root. Evaluate with
`--preserved-run "$TRIAL_ROOT/host-baseline"` and
`--synthesis-evidence "$TRIAL_ROOT/measurements.json"` in addition to `--approved-run`.
The evaluator requires the saved-performance baseline to equal the original host render.

## Restore the delivered private bundle

Artifacts from this run are under ignored
`dogfood/2026-09-28-clean-production-handoff-frozen/`:

- `delivery.zip`: two mixes, ten stems, source/lock, archived Tactus, receipts, sections,
  measurements and checksums. No source samples or native instruments are in this ZIP.
- `rebuild-inputs.tar.gz`: full declared blob closure, native tools and source, without a venv
  or stage cache. Includes the two pinned performances and original generation provenance.
- `runtime-image.tar`: installed environment, restorable with `docker load -i`. This avoids
  fetching dependencies when reproducing; a new Docker build requires network and apt packages
  can change. The recorded image and system package inventory identify the tested environment.
- `bundle-checksums.json`: hashes for the three packages and the restored blob verification.

Extract rebuild inputs to a new transfer directory, load the image, and follow the same four
mounts above, using `tactus-frozen-handoff:20260928`. The container restores into a new `/trial`;
never mount a developer home, original work, venv or stage cache. For source regeneration,
use `generation-source/song.py` and the inventoried tools; its stochastic behavior remains.

## Listening and limits

Serve `index.html` beside `measurements.json`, `delivery/` and `delivery.zip`. The current local
page reuses the session server at `http://localhost:4186/runs/portability/`. Browser checks cover
loading, position-preserving candidate/stem switches, playback, download and mobile width.
They do not establish audio quality; neither new candidate has Paul's acceptance.

The ZIP's stems start at frame zero, contain 6,579,243 frames at 44.1 kHz, and use stereo
PCM24. They include each stem's gain/effects before nonlinear master compression/limiting;
summing them is not the mastered mix. Source `np.clip` can hide saturation from runtime
`clipped_samples`; this experiment makes no unclipped-audio claim.

This is a same-CPU/kernel Linux trial, not cross-OS portability. `tool()` records identities;
this trial's preflight enforces expected native hashes. Input reuse/distribution rights are
not conferred by these files. The sample/tool packages stay private and local.
