# Rendering on request: `tactus serve`

For a work that is played while it renders (an interactive piece that needs the next bars
just before they sound), keep the work loaded and send it requests instead of starting
`tactus run` each time. A cold `tactus run` pays for a new Python process, imports and the
source inventory on every request (about 2 s of Island's 4 s step); the service pays them
once per load.

The service is an optional extra; works that only render offline do not need it:

```bash
uv add 'tactus[serve]'            # in the work
tactus serve song.py --out runs/serve --port 4300 [--static player] [--host 127.0.0.1] [--no-checkpoint] [--retain 40] [--reuse]
```

Without `--port` the system chooses a free port; the printed address names it. `--static DIR`
serves the work's page from DIR at `/` (`index.html`), so the page and the API share one
origin and the work needs no server of its own.

It prints `tactus serve: http://127.0.0.1:4300 (session …)` on stderr and serves until
Ctrl-C, then prints a JSON summary on stdout. It binds only loopback addresses.

## The v1 API

`POST /v1/render` with `Content-Type: application/json`:

```json
{"params": {"whole": false},
 "param_files": {"touch": {"calls": ["plain", "bob"]}},
 "key": "next",
 "checkpoint": false,
 "deliver": {"codec": "aac", "bitrate": "256k", "peaks": 0}}
```

- `params` are `render`'s keyword parameters, parsed like `tactus run --params`.
- `param_files` maps a parameter to a JSON value sent as a file (a performance): the receipt
  records it under `parameter_files` with `path: null`, the sha256 and size of its compact
  JSON bytes, and the run keeps the bytes in `parameters/NAME.json`. A name may not appear
  in both.
- `key` (optional): a newer request with the same key replaces one still waiting with it
  (`superseded`). Requests are rendered one at a time, in order.
- `checkpoint` (optional) overrides `--no-checkpoint` for this request.
- `deliver` (optional): `codec` (`wav`, `flac`, `aac`, `opus`), `bitrate` for aac/opus,
  `bit_depth` for flac, `peaks` (0 leaves the waveform outline out). After the render, the
  `web` exporter of [`tactus export web`](project-commands.md#delivering-with-the-map-web-srt-curves)
  writes `NNNN/web/` (browser audio, `bundle.json`, `export.json`) before the answer. A
  delivery failure is `deliver_error` in the answer; the run is kept.

The answer is the request as a resource; `GET /v1/requests/{n}` returns it again while the
request is kept:

| Field | Meaning |
|---|---|
| `request`, `url` | the request number and its resource, `/v1/requests/N` |
| `sample_rate` | the run's rate: every frame position below is in it |
| `outputs` | per output: `url` (the run's PCM24 WAV), `frames`, `seconds`, `channels`, `peak_dbfs`, `clipped_samples`, `sha256`; with `deliver`, `delivered` (the browser file) |
| `map`, `map_seconds` | the work's map in frames and in seconds, when `render` returned one; `clock_hint` is copied unchanged |
| `params` | the parameters as bound, defaults included (the receipt's `parameters`) |
| `receipt` | `/v1/requests/N/receipt` |
| `bundle` | with `deliver`: `/v1/requests/N/files/web/bundle.json` (lengths, levels, the decoded length of each file) |
| `deliver_error` | `{code, phase, message}` when delivery failed |
| `load`, `timings` | as below; `timings.deliver` is the delivery's seconds |
| `source_changed`, `retired`, `takes` | when present, as below |
| `paths` | the local paths (`run`, `outputs`, `manifest`, `receipt`, `render`, `map`, `bundle`) for Python callers on the same machine |

Other v1 routes:

- `GET /v1/requests/{n}/files/{path}` serves a regular file of that request directory
  (`manifest.json`, `map.json`, WAVs, `web/...`) with HTTP Range. Paths with `..`, symlinks
  and directories are refused (404); a retired request has no files.
- `GET /v1/requests/{n}/receipt` serves the receipt, a retired request's kept copy included.
  `GET /v1/requests/{n}` of a retired request is 404 with that `receipt` url.
- `GET /v1/work` is a card derived from the code and the runs, with nothing written by the
  author: `about` (the module docstring), `parameters` (`render`'s, with `default` or
  `required` and `annotation`), `examples` (up to three distinct recent values per parameter
  from this session's kept requests, or from receipts under `--out` when it has none),
  `sample_rate` and `map_summary` (bars, lane kinds, item counts and fields, segments,
  `clock_hint`) of the last request, `requests_kept`. An outside agent drives a work from it;
  the recent examples are the part it relies on most.
- `GET /docs` and `/openapi.json` describe the routes; `/` is a JSON index of them unless
  `--static` serves a page there. API routes take precedence over files in `--static`.

A page served with `--static` fetches `/v1/render`, then `bundle` and each output's
`delivered` url, and schedules from `map` or `map_seconds`. Say in the map's `clock_hint`
(or a lane) what each output represents, e.g. "the three possible next leads"; Tactus copies
it and gives it no meaning.

Errors use the run envelope `{"status": "error", "error": {"code", "phase", "message"}}`:
`invalid_request` and `invalid_parameters` (the work raised `tactus.InvalidParameters`; the
message is the work's) are HTTP 400, `not_found` 404, `superseded` and `cancelled` 409,
others 500 (`execution_failed`, `load_failed` after an edit broke the work, …). A failed
request leaves no directory; the worker keeps serving.

## The unversioned routes

The original routes stay as they were; existing pages use them.

`POST /render` takes `params`, `param_files`, `key` and `checkpoint` (no `deliver`) and
answers with `tactus run`'s result (absolute paths in `outputs`, `manifest`, `receipt`,
`render`, `map`; `levels`, optional `source_changed`, `takes`) plus:

| Field | Meaning |
|---|---|
| `request`, `run` | the request number and its directory, `OUT/<session>/NNNN` |
| `load` | `id` (`L1`, `L2`, …), `loaded_at`, `reason` (`start`, `source_changed`, `cancelled`, `worker_exited`, `requested`), worker `pid`, load `seconds` |
| `timings` | seconds: `queue` (waiting), `load` (a reload this request paid for), `render` (the receipt's `elapsed_seconds`), `worker` (render + receipt + WAVs), `total` |
| `session_bytes` | bytes the session's kept request directories hold |
| `retired` | request numbers whose directories `--retain` just removed |

A request sent this way is a resource too: `GET /v1/requests/{n}` and its files work for it.

Other routes: `GET /status` (session, current load, request count, waiting, bytes),
`POST /cancel` (cancel waiting requests and kill a running render; the next request loads
again), `POST /reload` (load the current source now).

From Python, without HTTP:

```python
from tactus.serve import Service

with Service("song.py", "runs/serve", checkpoint=False) as service:
    result = service.render({"steps": steps}, key="next-step", deliver={"codec": "flac"})
    document = service.document(result["request"])
    card = service.work()
```

## Receipts and source edits

Every request directory is an ordinary run: `receipt.json`, `manifest.json`, WAVs, and
`render/` unless checkpoints are off, so `tactus export`, `analyze`, `excerpt` and `prune`
read it. The receipt adds `service: {session, request, load: {id, loaded_at, reason, pid}}`.

The source inventory, Git record and take snapshot are taken once per load, before the
import; the receipt's `source_files` and `dependency_lock` are that load's. Before each
request the service inventories the work again; if any `.py` file or the lock changed, it
starts a new worker and the request runs on a new load (`reason: "source_changed"`), so a
warm process never renders old code under a new receipt or the reverse. A file edited while
a request renders is reported in `source_changed` as for `tactus run`; files the load had
already imported carry `imported_at_load: true` and are certain (the request ran the loaded
bytes), and the next request loads the edit. Committing unchanged bytes does not reload: the
`git` record still describes those bytes as a diff against the load's `HEAD`.

## Disk

Each session keeps every request directory unless `--retain N` is given; then only the
newest N stay and each removed request's receipt is kept as `retired/NNNN.receipt.json`,
with its `parameters/` as `retired/NNNN.parameters/`, so the request can be rendered again
from those bytes.
`session.jsonl` logs every load (with its inventory and Git record) and request (load,
status, timings, receipt sha256, bytes). An interactive piece that renders ten 17-second
clips per step writes about 33 MB of PCM per step; a session left walking for hours grew to
12 GB before retention existed. A request directory holds its outputs as PCM24 WAV
(about 17 MB per stereo minute at 48 kHz), the map, the receipt, `render/` unless
checkpoints are off, and `web/` when delivered (256 kbit/s AAC adds about 1.9 MB per stereo
minute). Size `--retain` as the number of requests a player may still reach back to, times
the bytes of one request. `tactus prune OUT/<session>/[0-9]*/` removes checkpoints from
kept requests. The session directory is not deleted when the service stops.
