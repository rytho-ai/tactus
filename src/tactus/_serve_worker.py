"""Private resident process for serve.py: load a work once, then render one request per line.

Protocol: argv[1] is a JSON config (`source`, `excluded`, `reuse`). The first line written
is the load (`{"status": "loaded", ...}`, with the module docstring as `about` and
`render`'s keyword parameters for the service's work card) or a run error envelope, after
which the process exits. Then each stdin line is a request for `run._render`, answered by
one line: the run result plus `elapsed_seconds`, or the error envelope. Protocol lines go to a private copy
of fd 1; fd 1 itself then points at stderr, so author `print` output (and C-level writes)
reaches the service's log rather than the protocol.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import time
import traceback
from pathlib import Path

from ._contracts import RunError, json_copy
from .run import _load, _render


def _send(channel, message: dict) -> None:
    channel.write(json.dumps(message, sort_keys=True) + "\n")
    channel.flush()


def _parameters(factory) -> dict:
    """`render`'s parameters as JSON: default (absent when required) and annotation text."""
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return {}
    described = {}
    for parameter in parameters:
        entry: dict = {"annotation": None}
        if parameter.annotation is not parameter.empty:
            entry["annotation"] = inspect.formatannotation(parameter.annotation)
        if parameter.default is parameter.empty:
            entry["required"] = True
        else:
            try:
                entry["default"] = json_copy(parameter.default)
            except (TypeError, ValueError, RecursionError):
                entry["default"] = repr(parameter.default)
        described[parameter.name] = entry
    return described


def main() -> int:
    channel = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    config = json.loads(sys.argv[1])
    source = Path(config["source"])
    started = time.perf_counter()
    try:
        loaded = _load(source, Path(config["excluded"]), reuse=bool(config.get("reuse")))
    except RunError as exc:
        traceback.print_exc(file=sys.stderr)
        _send(channel, exc.to_dict())
        return exc.exit_code
    _send(
        channel,
        {
            "status": "loaded",
            "pid": os.getpid(),
            "seconds": round(time.perf_counter() - started, 3),
            "source_files": loaded.before["source_files"],
            "dependency_lock": loaded.before["dependency_lock"],
            "git": loaded.git,
            "modules": sorted(loaded.modules),
            "about": getattr(loaded.factory, "__globals__", {}).get("__doc__"),
            "parameters": _parameters(loaded.factory),
        },
    )
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        out = Path(request["out"])
        try:
            result = _render(loaded, out, request, resident=True)
        except RunError as exc:
            if exc.code != "invalid_parameters":  # the work's own message says it all
                traceback.print_exc(file=sys.stderr)
            _send(channel, exc.to_dict())
            continue
        receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
        _send(channel, {**result, "elapsed_seconds": receipt["elapsed_seconds"]})
    return 0
