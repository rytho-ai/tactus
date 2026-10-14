"""Thin local HTTP layer over serve.Service (needs the `serve` extra: FastAPI + uvicorn).

v1 routes: `POST /v1/render` (`{"params", "param_files", "key", "checkpoint", "deliver"}`)
answers with the request's document; `GET /v1/requests/{n}` is that document again;
`GET /v1/requests/{n}/files/{path}` serves a regular file of the request directory (no
`..`, no symlinks; HTTP Range); `GET /v1/requests/{n}/receipt` serves the receipt, also a
retired one's; `GET /v1/work` is the work card. `/docs` and `/openapi.json` describe them.
`static` (`--static DIR`) serves DIR at `/` after every API route; without it `/` is a
JSON index. The unversioned originals stay: `GET /status`, `POST /render` (no `deliver`,
answers `tactus run`'s result), `POST /cancel`, `POST /reload`.

Failures use the run error envelope with `invalid_request`/`invalid_parameters` → 400,
`not_found` → 404, `superseded`/`cancelled` → 409, everything else → 500. Local only: the
socket binds a loopback address, and a request whose `Host` or `Origin` is not loopback,
or a POST that is not `application/json` (which a foreign page could send without a CORS
preflight), is refused with 403/415 before it reaches the service or a static file.

Reads: serve (Service) · _contracts (RunError)
"""

from __future__ import annotations

import ipaddress
import json
import signal
import socket
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from ._contracts import RunError
from .serve import Service

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.concurrency import run_in_threadpool
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise RunError(
        "invalid_request",
        "request",
        "tactus serve needs the serve extra (FastAPI and uvicorn): uv add 'tactus[serve]'",
    ) from exc

_STATUS = {
    "invalid_request": 400,
    "invalid_parameters": 400,
    "not_found": 404,
    "superseded": 409,
    "cancelled": 409,
}
_FIELDS = {"params", "param_files", "key", "checkpoint"}
_V1_FIELDS = _FIELDS | {"deliver"}
_MEDIA = {
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".opus": "audio/ogg",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".npy": "application/octet-stream",
}
ROUTES = {
    "POST /v1/render": "render a request; {params, param_files, key, checkpoint, deliver}",
    "GET /v1/requests/{n}": "a kept request's document",
    "GET /v1/requests/{n}/files/{path}": "a file of a kept request's directory (Range)",
    "GET /v1/requests/{n}/receipt": "a request's receipt (kept or retired)",
    "GET /v1/work": "the work card: about, parameters, recent examples, map summary",
    "GET /status": "session, load, requests, bytes",
    "POST /render": "the unversioned original: tactus run's result",
    "POST /cancel": "cancel waiting requests and a running render",
    "POST /reload": "load the current source now",
    "GET /docs": "OpenAPI page (/openapi.json)",
}


def is_loopback(host: str) -> bool:
    host = host.strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _error(exc: RunError) -> JSONResponse:
    return JSONResponse(exc.to_dict(), status_code=_STATUS.get(exc.code, 500))


def _refuse(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        RunError("invalid_request", "request", message).to_dict(), status_code=status
    )


async def _body(request: Request, fields: set[str]) -> dict[str, Any]:
    body = json.loads(await request.body() or b"{}")
    if not isinstance(body, dict):
        raise TypeError("the request body must be a JSON object")
    unknown = body.keys() - fields
    if unknown:
        raise ValueError(f"unknown request fields: {', '.join(sorted(unknown))}")
    return body


def _request_file(directory: Path, path: str) -> Path:
    """A regular file under `directory` named by `path`: no `..`, no symlinked component."""
    parts = PurePosixPath(path).parts
    if path.startswith("/") or not parts or any(p in ("..", ".") or "\\" in p for p in parts):
        raise RunError("not_found", "request", f"no file {path!r} in this request")
    target = directory
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise RunError("not_found", "request", f"{path!r} is a symlink; it is not served")
    if not target.is_file():
        raise RunError("not_found", "request", f"no file {path!r} in this request")
    return target


def create_app(service: Service, *, static: str | Path | None = None) -> FastAPI:
    """The FastAPI app for a started service; the caller owns the service's lifetime.

    `static` is a directory served at `/` (index.html) after every API route.
    """
    if static is not None:
        static = Path(static).resolve()
        if not static.is_dir():
            raise RunError("invalid_request", "request", f"--static must be a directory: {static}")
    app = FastAPI(title="tactus serve", version="1", docs_url="/docs", redoc_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next: Callable[..., Any]) -> Any:
        host = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
        if not is_loopback(host):
            return _refuse(403, f"tactus serve answers only local requests, not Host {host!r}")
        origin = request.headers.get("origin")
        if origin is not None and not is_loopback(urlsplit(origin).hostname or ""):
            return _refuse(403, f"tactus serve refuses requests from origin {origin!r}")
        if request.method == "POST":
            kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind != "application/json":
                return _refuse(415, "POST bodies must be application/json")
        return await call_next(request)

    @app.get("/status")
    def status() -> dict[str, Any]:
        return service.status()

    @app.post("/v1/render")
    async def render_v1(request: Request) -> Any:
        """Render one request; the answer is its document (see GET /v1/requests/{n})."""
        try:
            body = await _body(request, _V1_FIELDS)
        except (ValueError, TypeError) as exc:
            return _error(RunError("invalid_request", "request", str(exc)))
        try:
            result = await run_in_threadpool(
                service.render,
                body.get("params"),
                param_files=body.get("param_files"),
                key=body.get("key"),
                checkpoint=body.get("checkpoint"),
                deliver=body.get("deliver"),
            )
            return service.document(result["request"])
        except RunError as exc:
            return _error(exc)

    @app.get("/v1/requests/{number}")
    def request_document(number: int) -> Any:
        """A kept request's document; 404 (with the receipt's url) once retired."""
        try:
            return service.document(number)
        except RunError as exc:
            response = exc.to_dict()
            if service.receipt_path(number) is not None:
                response["receipt"] = f"/v1/requests/{number}/receipt"
            return JSONResponse(response, status_code=_STATUS.get(exc.code, 500))

    @app.get("/v1/requests/{number}/receipt")
    def request_receipt(number: int) -> Any:
        path = service.receipt_path(number)
        if path is None or not path.is_file():
            return _error(RunError("not_found", "request", f"no receipt for request {number}"))
        return FileResponse(path, media_type="application/json")

    @app.get("/v1/requests/{number}/files/{path:path}")
    def request_file(number: int, path: str) -> Any:
        """A regular file of a kept request directory; Range requests are answered with 206."""
        directory = service.request_directory(number)
        try:
            if directory is None:
                raise RunError("not_found", "request", f"request {number} has no files here")
            target = _request_file(directory, path)
        except RunError as exc:
            return _error(exc)
        return FileResponse(target, media_type=_MEDIA.get(target.suffix.lower()))

    @app.get("/v1/work")
    def work() -> dict[str, Any]:
        """The work card, derived from the loaded code and its runs."""
        return service.work()

    @app.post("/render")
    async def render(request: Request) -> Any:
        try:
            body = await _body(request, _FIELDS)
        except (ValueError, TypeError) as exc:
            return _error(RunError("invalid_request", "request", str(exc)))
        try:
            return await run_in_threadpool(
                service.render,
                body.get("params"),
                param_files=body.get("param_files"),
                key=body.get("key"),
                checkpoint=body.get("checkpoint"),
            )
        except RunError as exc:
            return _error(exc)

    @app.post("/cancel")
    def cancel() -> dict[str, Any]:
        return service.cancel()

    @app.post("/reload")
    def reload() -> Any:
        try:
            return {"status": "ok", "load": service.reload()}
        except RunError as exc:
            return _error(exc)

    if static is None:

        @app.get("/")
        def index() -> dict[str, Any]:
            return {"status": "ok", "service": "tactus serve", "routes": ROUTES}

    else:
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app


def bind(host: str, port: int) -> socket.socket:
    """A listening loopback socket; a non-loopback host is `invalid_request`."""
    if not is_loopback(host):
        raise RunError(
            "invalid_request",
            "request",
            f"tactus serve binds only loopback addresses (127.0.0.1, ::1, localhost), not {host!r}",
        )
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host.strip("[]") if host != "localhost" else "127.0.0.1", port))
    except OSError as exc:
        sock.close()
        raise RunError("invalid_request", "request", f"cannot listen on {host}:{port}: {exc}")
    sock.listen(128)
    return sock


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def serve(
    service: Service,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    static: str | Path | None = None,
    announce: Callable[[str], None] = lambda url: None,
) -> dict[str, Any]:
    """Start the service, serve HTTP until SIGINT/SIGTERM, stop the worker; return a summary."""
    import uvicorn

    app = create_app(service, static=static)
    sock = bind(host, port)
    url = None
    # uvicorn shuts down gracefully on SIGINT/SIGTERM, then re-raises the signal to the
    # handler it found; this one ends serving (also while loading) so the worker stops too.
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        service.start()
        address = sock.getsockname()
        shown = f"[{address[0]}]" if ":" in address[0] else address[0]
        url = f"http://{shown}:{address[1]}"
        announce(url)
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="warning", access_log=False)
        )
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        if url is not None:
            # A terminal's Ctrl-C can arrive twice (the group's and uv's forwarded copy);
            # the second must not interrupt stopping the worker or printing the summary.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        service.close()
        sock.close()
    return {"url": url, **service.status()}
