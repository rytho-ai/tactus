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
newest N request directories, moving older receipts to `retired/`. `session.jsonl` logs
every load and request. Plain Python: the HTTP layer is `_serve_http`.

Reads: run (_load/_render via the worker, _parameter_files, _clean_failed, _stop) ·
_source (inventory) · _contracts
"""

from __future__ import annotations

import hashlib
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
    ) -> dict[str, Any]:
        """Render one request of the loaded work into a new numbered run directory.

        `params` and `param_files` follow `tactus run`: each `param_files` value is a
        `Path` to read or a JSON value (a performance sent in the request), recorded with
        its sha256 and copied to `parameters/NAME.json`. A work's `InvalidParameters` is
        `invalid_parameters`. Returns the run result plus `request`, `run`, `load`,
        `timings` and `session_bytes`.
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
        except (ValueError, TypeError, OSError, RecursionError) as exc:
            raise RunError("invalid_request", "request", str(exc)) from exc
        for name, (value, _payload, _record) in files.items():
            params[name] = value

        queued = time.perf_counter()
        self._acquire(key)
        try:
            return self._render_now(
                params, files, self.checkpoint if checkpoint is None else checkpoint, queued
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
        return {
            **result,
            "request": number,
            "run": str(out),
            "load": load,
            "timings": timings,
            "session_bytes": sum(self._kept.values()),
            **({"retired": retired} if retired else {}),
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
            shutil.rmtree(run, ignore_errors=True)
            with self._cond:
                self._kept.pop(number, None)
            self._log(
                {
                    "event": "retired",
                    "request": number,
                    "receipt": f"retired/{number:04d}.receipt.json",
                }
            )
            retired.append(number)
        return retired
