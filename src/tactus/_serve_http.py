"""Thin local HTTP layer over serve.Service (needs the `serve` extra: FastAPI + uvicorn).

Routes: `GET /status`, `POST /render` (`{"params", "param_files", "key", "checkpoint"}`),
`POST /cancel`, `POST /reload`. Responses are the service's JSON; failures use the run
error envelope with `invalid_request`/`invalid_parameters` → 400, `superseded`/`cancelled`
→ 409, everything else → 500. Local only: the socket binds a loopback address, and a
request whose `Host` or `Origin` is not loopback, or a POST that is not
`application/json` (which a foreign page could send without a CORS preflight), is refused
with 403/415 before it reaches the service.

Reads: serve (Service) · _contracts (RunError)
"""

from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from ._contracts import RunError
from .serve import Service

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
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
    "superseded": 409,
    "cancelled": 409,
}
_FIELDS = {"params", "param_files", "key", "checkpoint"}


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


def create_app(service: Service) -> FastAPI:
    """The FastAPI app for a started service; the caller owns the service's lifetime."""
    app = FastAPI(title="tactus serve", docs_url=None, redoc_url=None, openapi_url=None)

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

    @app.post("/render")
    async def render(request: Request) -> Any:
        try:
            body = json.loads(await request.body() or b"{}")
            if not isinstance(body, dict):
                raise TypeError("the request body must be a JSON object")
            unknown = body.keys() - _FIELDS
            if unknown:
                raise ValueError(f"unknown request fields: {', '.join(sorted(unknown))}")
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


def serve(
    service: Service,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    announce: Callable[[str], None] = lambda url: None,
) -> dict[str, Any]:
    """Start the service, serve HTTP until interrupted, stop the worker; return a summary."""
    import uvicorn

    sock = bind(host, port)
    try:
        service.start()
        address = sock.getsockname()
        shown = f"[{address[0]}]" if ":" in address[0] else address[0]
        url = f"http://{shown}:{address[1]}"
        announce(url)
        server = uvicorn.Server(
            uvicorn.Config(create_app(service), log_level="warning", access_log=False)
        )
        try:
            server.run(sockets=[sock])
        except KeyboardInterrupt:
            # uvicorn re-raises the Ctrl-C it handled once it has shut down.
            pass
        return {"url": url, **service.status()}
    finally:
        service.close()
        sock.close()
