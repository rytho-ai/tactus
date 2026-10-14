"""Resident render service core: load a work once, render requests into receipted runs.

`Service(source, out)` keeps one warm worker process (`_serve_worker`) that imported the
work once; each `render(params=..., param_files=...)` is the same contract as `tactus run`
and lands in an ordinary run directory, `OUT/<session>/NNNN/`, with its own receipt,
manifest and WAVs (so `export`, `prune`, `analyze` and `excerpt` read it as a run).

Truthful receipts: the worker takes the source/lock inventory, Git record and take
snapshot once at load, before importing. Before every request the service inventories
again; any changed `.py` file or lock replaces the worker (a new load, `reason:
"source_changed"`), so a receipt's `source_files` are always the bytes its load imported.
Edits made while a request renders are reported by `run._source_changes`. Each receipt's
`service` block names the session, the request number and the load it came from.

One worker renders one request at a time (stage context and the input record are
process globals). Waiting requests are served in order; a request with a `key`
supersedes waiting requests with the same key (`superseded`). `cancel()` kills an
in-flight render (`cancelled`); the next request loads again. `retain=N` keeps only the
newest N request directories, moving older receipts (and `parameters/`) to `retired/`.
`session.jsonl` logs every load and request. Plain Python: the HTTP layer is `_serve_http`.

Requests as resources (the v1 API): every successful request also gets a document
(`document(n)`): sample rate, outputs with frames and seconds, the map in frames and
seconds, the bound parameters, relative URLs under `/v1/requests/N` and local `paths`.
`render(..., deliver={codec, ...})` runs the `web` exporter into `NNNN/web/` after the
render; a delivery failure is reported as `deliver_error` and keeps the run. `work()` is a
card derived from the loaded code and the runs: docstring, parameters, recent values.

Reads: run (_load/_render via the worker, _parameter_files, _clean_failed, _stop) ·
_source (inventory) · _contracts · export (_deliver, web) · timemap (to_seconds)
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from . import _source as source_info
from ._contracts import RunError, json_copy
from .run import _clean_failed, _parameter_files, _stop

__all__ = ["Service"]

DELIVER_FIELDS = ("codec", "bitrate", "bit_depth", "peaks")
EXAMPLES = 3  # distinct recent values per parameter on the work card
EXAMPLE_BYTES = 16_384  # values larger than this (as JSON) are left off the card


class _Ticket:
    __slots__ = ("cancelled", "key", "superseded")

    def __init__(self, key: str | None) -> None:
        self.key = key
        self.superseded = False
        self.cancelled = False


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _end(process: subprocess.Popen[str]) -> None:
    """Stop a worker (its process group on POSIX) and close its pipes."""
    _stop(process)
    for pipe in (process.stdin, process.stdout):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass


def _directory_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def map_summary(time_map: dict[str, Any] | None) -> dict[str, Any] | None:
    """A map's shape for the work card: bars, lanes (kind, count, item fields), segments."""
    if not isinstance(time_map, dict):
        return None
    segments = time_map.get("segments", {})
    outputs = {}
    for name, entry in time_map.get("outputs", {}).items():
        grid = entry.get("grid") or {}
        lanes = {
            lane: {
                "kind": data.get("kind"),
                "items": len(data.get("items", [])),
                "fields": sorted({key for item in data.get("items", []) for key in item}),
            }
            for lane, data in entry.get("lanes", {}).items()
        }
        outputs[name] = {
            "bars": len(grid.get("bars", [])) if grid else None,
            "lanes": lanes,
            "segments": sorted(s for s, seg in segments.items() if seg.get("output") == name),
        }
    return {
        "outputs": outputs,
        "segments": sorted(segments),
        **({"clock_hint": time_map["clock_hint"]} if "clock_hint" in time_map else {}),
    }


def _canonical(value: Any) -> bytes:
    """The bytes a JSON value sent as a parameter file is recorded and copied as."""
    return json.dumps(json_copy(value), ensure_ascii=False, separators=(",", ":")).encode()


class Service:
    """A warm, single-flight renderer of one work. See the module docstring."""

    def __init__(
        self,
        source: str | Path,
        out: str | Path,
        *,
        reuse: bool = False,
        checkpoint: bool = True,
        retain: int | None = None,
    ) -> None:
        try:
            self.source = Path(source).resolve()
            self.out = Path(out).resolve()
            if not self.source.is_file() or self.source.suffix != ".py":
                raise ValueError(f"source must be an existing Python file: {self.source}")
            root = self.source.parent
            if root == self.out or root.is_relative_to(self.out):
                raise ValueError("output cannot be the source directory or an ancestor")
            if retain is not None and (type(retain) is not int or retain < 1):
                raise ValueError("retain must be a positive number of requests")
        except (ValueError, TypeError, OSError) as exc:
            raise RunError("invalid_request", "request", str(exc)) from exc
        self.reuse = bool(reuse)
        self.checkpoint = bool(checkpoint)
        self.retain = retain
        self.session: str | None = None
        self.directory: Path | None = None
        self._cond = threading.Condition()
        self._waiting: list[_Ticket] = []
        self._busy = False
        self._process: subprocess.Popen[str] | None = None
        self._pycache: tempfile.TemporaryDirectory[str] | None = None
        self._load: dict[str, Any] | None = None
        self._loads = 0
        self._next_reason = "start"
        self._requests = 0
        self._kept: dict[int, int] = {}
        self._documents: dict[int, dict[str, Any]] = {}
        self._retired: set[int] = set()
        self._cancelling = False
        self._requests_in_flight = False

    # -- lifecycle -------------------------------------------------------------------

    def start(self) -> dict[str, Any]:
        """Create the session directory and load the work; a failed load raises RunError."""
        stamp = datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
        try:
            self.out.mkdir(parents=True, exist_ok=True)
            for _ in range(10):
                session = f"{stamp}-{secrets.token_hex(2)}"
                directory = self.out / session
                try:
                    directory.mkdir()
                    break
                except FileExistsError:
                    continue
            else:  # pragma: no cover - ten collisions of a random suffix
                raise OSError(f"could not create a session directory in {self.out}")
        except OSError as exc:
            raise RunError("publication_failed", "publish", str(exc)) from exc
        self.session, self.directory = session, directory
        self._log(
            {
                "event": "session",
                "session": session,
                "source": str(self.source),
                "started_at": _now(),
                "options": {
                    "reuse": self.reuse,
                    "checkpoint": self.checkpoint,
                    "retain": self.retain,
                },
            }
        )
        with self._cond:
            self._busy = True
        try:
            self._ensure_loaded()
        finally:
            self._release()
        return self.status()

    def close(self) -> None:
        """Stop the worker. Request directories and the session log stay."""
        with self._cond:
            process, self._process = self._process, None
            self._load = None
        if process is not None:
            _end(process)
        if self._pycache is not None:
            self._pycache.cleanup()
            self._pycache = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- requests --------------------------------------------------------------------

    def render(
        self,
        params: dict[str, Any] | None = None,
        *,
        param_files: dict[str, Any] | None = None,
        key: str | None = None,
        checkpoint: bool | None = None,
        deliver: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render one request of the loaded work into a new numbered run directory.

        `params` and `param_files` follow `tactus run`: each `param_files` value is a
        `Path` to read or a JSON value (a performance sent in the request), recorded with
        its sha256 and copied to `parameters/NAME.json`. A work's `InvalidParameters` is
        `invalid_parameters`. Returns the run result plus `request`, `run`, `load`,
        `timings` and `session_bytes`; `document(request)` is the same request as a
        resource. `deliver` (`codec`, optional `bitrate`, `bit_depth`, `peaks`) runs the
        `web` exporter into `NNNN/web/` before the answer; the result then carries
        `bundle` or `deliver_error`.
        """
        if self.directory is None:
            raise RunError("invalid_request", "request", "the service has not been started")
        try:
            params = json_copy({} if params is None else params)
            if not isinstance(params, dict):
                raise TypeError("params must be a JSON object")
            if param_files is not None and not isinstance(param_files, dict):
                raise TypeError("param_files must map parameter names to JSON values")
            given = {
                name: value if isinstance(value, Path) else _canonical(value)
                for name, value in (param_files or {}).items()
            }
            files = _parameter_files(given, params)
            if key is not None and not isinstance(key, str):
                raise TypeError("key must be a string")
            if checkpoint is not None and not isinstance(checkpoint, bool):
                raise TypeError("checkpoint must be true or false")
            if deliver is not None:
                deliver = json_copy(deliver)
                if not isinstance(deliver, dict) or "codec" not in deliver:
                    raise TypeError("deliver must be an object with a codec")
                unknown = deliver.keys() - set(DELIVER_FIELDS)
                if unknown:
                    raise ValueError(f"unknown deliver fields: {', '.join(sorted(unknown))}")
        except (ValueError, TypeError, OSError, RecursionError) as exc:
            raise RunError("invalid_request", "request", str(exc)) from exc
        for name, (value, _payload, _record) in files.items():
            params[name] = value

        queued = time.perf_counter()
        self._acquire(key)
        try:
            return self._render_now(
                params,
                files,
                self.checkpoint if checkpoint is None else checkpoint,
                queued,
                deliver,
            )
        finally:
            self._release()

    def reload(self) -> dict[str, Any]:
        """Replace the worker with a fresh load of the current source (`reason: "requested"`)."""
        self._acquire(None)
        try:
            self._replace("requested")
            started = time.perf_counter()
            self._ensure_loaded()
            return {**self._load_view(), "seconds": round(time.perf_counter() - started, 3)}
        finally:
            self._release()

    def cancel(self) -> dict[str, Any]:
        """Cancel every waiting request and kill an in-flight render."""
        with self._cond:
            waiting = len(self._waiting)
            for ticket in self._waiting:
                ticket.cancelled = True
            busy = self._busy and self._process is not None and self._requests_in_flight
            process = self._process if busy else None
            if process is not None:
                self._cancelling = True
            self._cond.notify_all()
        if process is not None:
            _stop(process)
        return {"status": "ok", "cancelled_waiting": waiting, "cancelled_running": bool(busy)}

    def document(self, number: int) -> dict[str, Any]:
        """The resource document of a kept request; `not_found` when unknown or retired."""
        with self._cond:
            found = self._documents.get(number)
            retired = number in self._retired
        if found is None:
            raise RunError(
                "not_found",
                "request",
                f"request {number} was retired by --retain; its receipt is kept"
                if retired
                else f"no request {number} in this session",
            )
        return json_copy(found)

    def request_directory(self, number: int) -> Path | None:
        """The directory of a kept request, or None."""
        with self._cond:
            kept = number in self._documents
        return self.directory / f"{number:04d}" if kept and self.directory else None

    def receipt_path(self, number: int) -> Path | None:
        """A kept request's receipt or a retired request's kept copy; None for neither."""
        if self.directory is None:
            return None
        with self._cond:
            kept, retired = number in self._documents, number in self._retired
        if kept:
            return self.directory / f"{number:04d}" / "receipt.json"
        if retired:
            return self.directory / "retired" / f"{number:04d}.receipt.json"
        return None

    def work(self) -> dict[str, Any]:
        """A card describing the work, derived from the loaded code and its runs only.

        `about` is the module docstring and `parameters` are `render`'s keyword parameters
        (default, annotation) as the current load sees them. `examples` holds up to three
        distinct recent values per parameter from this session's kept requests or, when it
        has none, from receipts under `out` (newest first). `sample_rate` and `map_summary`
        are the last kept request's (or the newest run's under `out`).
        """
        with self._cond:
            load = self._load
            documents = [self._documents[n] for n in sorted(self._documents, reverse=True)]
            kept = len(self._kept)
        parameters = None if load is None else load.get("parameters")
        if documents:
            recent = [doc["params"] for doc in documents]
            last = documents[0]
            sample_rate, summary = last["sample_rate"], map_summary(last.get("map"))
        else:
            receipts = self._receipts()
            recent = [r.get("parameters") for _, r in receipts]
            sample_rate, summary = None, None
            for path, _ in receipts:
                manifest = _read_json(path.parent / "manifest.json")
                if isinstance(manifest, dict):
                    sample_rate = manifest.get("sample_rate")
                    summary = map_summary(_read_json(path.parent / "map.json"))
                    break
        examples: dict[str, list[Any]] = {}
        for values in recent:
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                if parameters is not None and name not in parameters:
                    continue
                found = examples.setdefault(name, [])
                text = json.dumps(value, sort_keys=True)
                if (
                    len(found) < EXAMPLES
                    and len(text) <= EXAMPLE_BYTES
                    and all(json.dumps(v, sort_keys=True) != text for v in found)
                ):
                    found.append(value)
        about = None if load is None else load.get("about")
        return {
            "status": "ok",
            "source": str(self.source),
            "about": inspect.cleandoc(about) if isinstance(about, str) else None,
            "parameters": parameters,
            "examples": examples,
            "sample_rate": sample_rate,
            "map_summary": summary,
            "requests_kept": kept,
        }

    def _receipts(self, limit: int = 100) -> list[tuple[Path, dict[str, Any]]]:
        """Receipts of runs under `out` (kept requests and retired copies), newest first."""
        found = [
            *self.out.glob("*/[0-9]*/receipt.json"),
            *self.out.glob("*/retired/*.receipt.json"),
        ]
        dated = []
        for path in found:
            try:
                dated.append((path.stat().st_mtime, path))
            except OSError:
                continue
        receipts = []
        for _, path in sorted(dated, reverse=True)[:limit]:
            receipt = _read_json(path)
            if isinstance(receipt, dict):
                receipts.append((path, receipt))
        return receipts

    def status(self) -> dict[str, Any]:
        with self._cond:
            return {
                "status": "ok",
                "session": self.session,
                "session_dir": str(self.directory) if self.directory else None,
                "source": str(self.source),
                "load": self._load_view() if self._load else None,
                "requests": self._requests,
                "busy": self._busy,
                "waiting": len(self._waiting),
                "session_bytes": sum(self._kept.values()),
                "kept_requests": len(self._kept),
                "retain": self.retain,
                "checkpoint": self.checkpoint,
                "reuse": self.reuse,
            }

    # -- internals -------------------------------------------------------------------

    def _acquire(self, key: str | None) -> None:
        ticket = _Ticket(key)
        with self._cond:
            if key is not None:
                for other in self._waiting:
                    if other.key == key:
                        other.superseded = True
            self._waiting.append(ticket)
            self._cond.notify_all()
            while not (ticket.superseded or ticket.cancelled) and (
                self._busy or self._waiting[0] is not ticket
            ):
                self._cond.wait()
            self._waiting.remove(ticket)
            self._cond.notify_all()
            if ticket.superseded:
                raise RunError(
                    "superseded", "request", f"a newer request with key {key!r} replaced this one"
                )
            if ticket.cancelled:
                raise RunError("cancelled", "request", "request cancelled before it started")
            self._busy = True

    def _release(self) -> None:
        with self._cond:
            self._busy = False
            self._requests_in_flight = False
            self._cond.notify_all()

    def _log(self, event: dict[str, Any]) -> None:
        assert self.directory is not None
        with (self.directory / "session.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    def _load_view(self) -> dict[str, Any]:
        assert self._load is not None
        return {key: self._load[key] for key in ("id", "loaded_at", "reason", "pid", "seconds")}

    def _replace(self, reason: str) -> None:
        """Drop the current worker; the next request loads with `reason`."""
        process, self._process = self._process, None
        self._load = None
        self._next_reason = reason
        if process is not None:
            _end(process)

    def _ensure_loaded(self) -> float:
        """Load when no live worker holds the current source; return the seconds spent."""
        assert self.directory is not None
        if self._process is not None and self._process.poll() is not None:
            self._replace("worker_exited")
        if self._load is not None:
            current = source_info.inventory(self.source.parent, self.directory)
            if (
                current["source_files"] != self._load["source_files"]
                or current["dependency_lock"] != self._load["dependency_lock"]
            ):
                self._replace("source_changed")
        if self._load is not None:
            return 0.0
        started = time.perf_counter()
        if self._pycache is None:
            self._pycache = tempfile.TemporaryDirectory(prefix="tactus-serve-")
        config = {
            "source": str(self.source),
            "excluded": str(self.directory),
            "reuse": self.reuse,
        }
        bootstrap = (
            f"import sys; sys.path.insert(0, {str(Path(__file__).parent.parent)!r}); "
            "from tactus._serve_worker import main; raise SystemExit(main())"
        )
        self._loads += 1
        load_id = f"L{self._loads}"
        # Same interpreter flags as `run`'s worker: never execute stale bytecode.
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-X",
                f"pycache_prefix={self._pycache.name}/{load_id}",
                "-c",
                bootstrap,
                json.dumps(config),
            ],
            cwd=self.source.parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name == "posix",
        )
        assert process.stdout is not None
        line = process.stdout.readline()
        message = json.loads(line) if line.strip() else None
        if message is None or message.get("status") != "loaded":
            _end(process)
            error = (
                RunError(**message["error"])
                if message and message.get("status") == "error"
                else RunError(
                    "worker_failed", "load", f"worker exited with status {process.returncode}"
                )
            )
            self._log(
                {
                    "event": "load",
                    "load": load_id,
                    "reason": self._next_reason,
                    "status": "error",
                    "error": error.to_dict()["error"],
                }
            )
            raise error
        seconds = round(time.perf_counter() - started, 3)
        self._process = process
        self._load = {
            "id": load_id,
            "loaded_at": _now(),
            "reason": self._next_reason,
            "pid": message["pid"],
            "seconds": seconds,
            "source_files": message["source_files"],
            "dependency_lock": message["dependency_lock"],
            "about": message.get("about"),
            "parameters": message.get("parameters"),
        }
        self._log(
            {
                "event": "load",
                "status": "ok",
                **{k: self._load[k] for k in ("loaded_at", "reason", "pid", "seconds")},
                "load": load_id,
                "source_files": message["source_files"],
                "dependency_lock": message["dependency_lock"],
                "git": message["git"],
            }
        )
        self._next_reason = "start"
        return seconds

    def _render_now(
        self,
        params: dict[str, Any],
        files: dict[str, tuple[Any, bytes, dict[str, Any]]],
        checkpoint: bool,
        queued: float,
        deliver: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.directory is not None
        began = time.perf_counter()
        load_seconds = self._ensure_loaded()
        load = self._load_view()
        self._requests += 1
        number = self._requests
        out = self.directory / f"{number:04d}"
        try:
            out.mkdir()
            if files:
                (out / "parameters").mkdir()
                for name, (_value, payload, _record) in files.items():
                    (out / "parameters" / f"{name}.json").write_bytes(payload)
        except OSError as exc:
            shutil.rmtree(out, ignore_errors=True)
            raise RunError("publication_failed", "publish", str(exc)) from exc
        request = {
            "out": str(out),
            "params": params,
            "checkpoint": checkpoint,
            "parameter_files": {name: record for name, (_, _, record) in files.items()},
            "service": {
                "session": self.session,
                "request": number,
                "load": {k: load[k] for k in ("id", "loaded_at", "reason", "pid")},
            },
        }
        process = self._process
        assert process is not None and process.stdin is not None and process.stdout is not None
        sent = time.perf_counter()
        with self._cond:
            self._requests_in_flight = True
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
        except (OSError, ValueError):
            line = ""
        returned = time.perf_counter()
        with self._cond:
            self._requests_in_flight = False
            cancelled, self._cancelling = self._cancelling, False
        try:
            if not line.strip():
                self._replace("cancelled" if cancelled else "worker_exited")
                raise (
                    RunError("cancelled", "execute", "render cancelled")
                    if cancelled
                    else RunError("worker_failed", "execute", "the worker exited during the render")
                )
            result = json.loads(line)
            if result.get("status") != "ok":
                raise RunError(**result["error"])
        except RunError as exc:
            _clean_failed(out)
            self._log(
                {
                    "event": "request",
                    "request": number,
                    "load": load["id"],
                    "status": "error",
                    "error": exc.to_dict()["error"],
                    "run": out.name if out.exists() else None,
                }
            )
            raise
        delivery: dict[str, Any] = {}
        if deliver is not None:
            delivery = self._deliver(out, deliver)
        size = _directory_bytes(out)
        with self._cond:
            self._kept[number] = size
        retired = self._retire(number)
        finished = time.perf_counter()
        receipt_bytes = (out / "receipt.json").read_bytes()
        timings = {
            "queue": round(began - queued, 3),
            "load": load_seconds,
            "render": result.pop("elapsed_seconds"),
            "worker": round(returned - sent, 3),
            **({"deliver": delivery.pop("seconds")} if delivery else {}),
            "total": round(finished - queued, 3),
        }
        self._log(
            {
                "event": "request",
                "request": number,
                "load": load["id"],
                "status": "ok",
                "run": out.name,
                "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "bytes": size,
                "timings": timings,
                **({"source_changed": True} if "source_changed" in result else {}),
            }
        )
        answer = {
            **result,
            "request": number,
            "run": str(out),
            "load": load,
            "timings": timings,
            "session_bytes": sum(self._kept.values()),
            **({"retired": retired} if retired else {}),
            **({"bundle": delivery["bundle"]} if "bundle" in delivery else {}),
            **({"deliver_error": delivery["error"]} if "error" in delivery else {}),
        }
        document = self._document(number, out, answer, delivery.get("bundle"))
        with self._cond:
            self._documents[number] = document
        return answer

    def _deliver(self, out: Path, deliver: dict[str, Any]) -> dict[str, Any]:
        """Run the web exporter into `out/web`; report a failure instead of raising."""
        from ._delivery import web
        from .commands import Command
        from .export import _deliver

        started = time.perf_counter()
        try:
            done = _deliver(
                out,
                out=out / "web",
                command=Command("web", "export", function=web),
                params=deliver,
                nested=True,
            )
            outcome: dict[str, Any] = {"bundle": str(Path(done["directory"]) / "bundle.json")}
        except RunError as exc:
            outcome = {"error": exc.to_dict()["error"]}
        return {**outcome, "seconds": round(time.perf_counter() - started, 3)}

    def _document(
        self, number: int, out: Path, answer: dict[str, Any], bundle: str | None
    ) -> dict[str, Any]:
        """The request as a resource: rate, outputs in frames and seconds, map, params, URLs."""
        base = f"/v1/requests/{number}"
        manifest = _read_json(out / "manifest.json") or {}
        receipt = _read_json(out / "receipt.json") or {}
        rate = manifest.get("sample_rate")
        delivered = (_read_json(Path(bundle)) or {}).get("outputs", {}) if bundle else {}
        outputs = {}
        for name, ref in manifest.get("outputs", {}).items():
            entry = {k: v for k, v in ref.items() if k != "file"}
            outputs[name] = {
                "url": f"{base}/files/{ref['file']}",
                **entry,
                "seconds": ref["frames"] / rate,
            }
            if name in delivered:
                outputs[name]["delivered"] = f"{base}/files/web/{delivered[name]['file']}"
        time_map = _read_json(out / "map.json") if "map" in answer else None
        paths = {
            key: answer[key]
            for key in ("run", "outputs", "manifest", "receipt", "render", "map", "bundle")
            if key in answer
        }
        from . import timemap

        return {
            "status": "ok",
            "request": number,
            "url": base,
            "sample_rate": rate,
            "outputs": outputs,
            **(
                {"map": time_map, "map_seconds": timemap.to_seconds(time_map, rate)}
                if time_map is not None
                else {}
            ),
            "receipt": f"{base}/receipt",
            "params": receipt.get("parameters"),
            **({"takes": answer["takes"]} if "takes" in answer else {}),
            "load": answer["load"],
            "timings": answer["timings"],
            **({"source_changed": answer["source_changed"]} if "source_changed" in answer else {}),
            **({"retired": answer["retired"]} if "retired" in answer else {}),
            **({"bundle": f"{base}/files/web/bundle.json"} if bundle else {}),
            **({"deliver_error": answer["deliver_error"]} if "deliver_error" in answer else {}),
            "paths": paths,
        }

    def _retire(self, newest: int) -> list[int]:
        """Remove request directories beyond the newest `retain`, keeping their receipts."""
        if self.retain is None:
            return []
        assert self.directory is not None
        with self._cond:
            old = sorted(self._kept)[: max(0, len(self._kept) - self.retain)]
        retired = []
        for number in old:
            if number == newest:
                continue
            run = self.directory / f"{number:04d}"
            keep = self.directory / "retired"
            keep.mkdir(exist_ok=True)
            receipt = run / "receipt.json"
            if receipt.is_file():
                shutil.copyfile(receipt, keep / f"{number:04d}.receipt.json")
            # The performance stays beside its receipt, so a retired request renders again.
            if (run / "parameters").is_dir():
                shutil.copytree(run / "parameters", keep / f"{number:04d}.parameters")
            shutil.rmtree(run, ignore_errors=True)
            with self._cond:
                self._kept.pop(number, None)
                self._documents.pop(number, None)
                self._retired.add(number)
            self._log(
                {
                    "event": "retired",
                    "request": number,
                    "receipt": f"retired/{number:04d}.receipt.json",
                }
            )
            retired.append(number)
        return retired
