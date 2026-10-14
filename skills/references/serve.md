# Rendering on request: `tactus serve`

For a work that is played while it renders (an interactive piece that needs the next bars
just before they sound), keep the work loaded and send it requests instead of starting
`tactus run` each time. A cold `tactus run` pays for a new Python process, imports and the
source inventory on every request (about 2 s of Island's 4 s step); the service pays them
once per load.

The service is an optional extra; works that only render offline do not need it:

```bash
uv add 'tactus[serve]'            # in the work
tactus serve song.py --out runs/serve --port 4300 [--host 127.0.0.1] [--no-checkpoint] [--retain 40] [--reuse]
```

Without `--port` the system chooses a free port; the printed address names it.

It prints `tactus serve: http://127.0.0.1:4300 (session …)` on stderr and serves until
Ctrl-C, then prints a JSON summary on stdout. It binds only loopback addresses.

## Requests

`POST /render` with `Content-Type: application/json`:

```json
{"params": {"steps": [{"name": "t0", "state": {}, "target": "market"}]},
 "param_files": {"tape": [{"bar": 1, "choice": "left"}]},
 "key": "next-step",
 "checkpoint": false}
```

- `params` are `render`'s keyword parameters, parsed like `tactus run --params`.
- `param_files` maps a parameter to a JSON value sent as a file (a performance): the receipt
  records it under `parameter_files` with `path: null`, the sha256 and size of its compact
  JSON bytes, and the run keeps the bytes in `parameters/NAME.json`. A name may not appear
  in both.
- `key` (optional): a newer request with the same key replaces one still waiting with it
  (`superseded`). Requests are rendered one at a time, in order.
- `checkpoint` (optional) overrides `--no-checkpoint` for this request.

The response is `tactus run`'s result (`outputs`, `manifest`, `receipt`, `render`,
`levels`, optional `source_changed`, `takes`, `map`) plus:

| Field | Meaning |
|---|---|
| `request`, `run` | the request number and its directory, `OUT/<session>/NNNN` |
| `load` | `id` (`L1`, `L2`, …), `loaded_at`, `reason` (`start`, `source_changed`, `cancelled`, `worker_exited`, `requested`), worker `pid`, load `seconds` |
| `timings` | seconds: `queue` (waiting), `load` (a reload this request paid for), `render` (the receipt's `elapsed_seconds`), `worker` (render + receipt + WAVs), `total` |
| `session_bytes` | bytes the session's kept request directories hold |
| `retired` | request numbers whose directories `--retain` just removed |

Errors use the run envelope `{"status": "error", "error": {"code", "phase", "message"}}`:
`invalid_request` and `invalid_parameters` (the work raised `tactus.InvalidParameters`; the
message is the work's) are HTTP 400, `superseded` and `cancelled` 409, others 500
(`execution_failed`, `load_failed` after an edit broke the work, …). A failed request leaves
no directory; the worker keeps serving.

Other routes: `GET /status` (session, current load, request count, waiting, bytes),
`POST /cancel` (cancel waiting requests and kill a running render; the next request loads
again), `POST /reload` (load the current source now).

From Python, without HTTP:

```python
from tactus.serve import Service

with Service("song.py", "runs/serve", checkpoint=False) as service:
    result = service.render({"steps": steps}, key="next-step")
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
newest N stay and each removed request's receipt is kept as `retired/NNNN.receipt.json`.
`session.jsonl` logs every load (with its inventory and Git record) and request (load,
status, timings, receipt sha256, bytes). An interactive piece that renders ten 17-second
clips per step writes about 33 MB of PCM per step; a session left walking for hours grew to
12 GB before retention existed. `tactus prune OUT/<session>/[0-9]*/` removes checkpoints from
kept requests. The session directory is not deleted when the service stops.
