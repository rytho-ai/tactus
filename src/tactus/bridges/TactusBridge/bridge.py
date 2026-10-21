"""Live's main-thread Python executor and local request queue, without music wrappers.

This directory is copied into Live and must work without Tactus, NumPy or MCP.
All native object access happens in the scheduled poll, never a socket/worker thread.
Reads: stdlib JSON/files/time, Live and _Framework at control-surface creation only.
"""

import contextlib
import io
import json
import math
import os
import time
import traceback
import uuid
from pathlib import Path

from .state import LiveState, identity

PROTOCOL = 1


def _finite(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) in (list, tuple):
        return [_finite(item) for item in value]
    if type(value) is dict and all(isinstance(key, str) for key in value):
        return {key: _finite(item) for key, item in value.items()}
    raise ValueError("Return finite JSON data; convert native Live objects to explicit data")


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(_finite(value), ensure_ascii=False, allow_nan=False),
                         encoding="utf-8")
    temporary.replace(path)


class RequestQueue:
    """One main-thread poll claims one request; replies survive client timeouts."""

    def __init__(self, directory):
        self.instance = uuid.uuid4().hex
        self.root = Path(directory) / "tactus-bridge" / "instances" / self.instance
        for name in ("requests", "running", "responses"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.heartbeat()

    def heartbeat(self):
        _write(self.root / "heartbeat.json", {
            "protocol": PROTOCOL, "instance": self.instance, "time": time.time(),
        })

    def poll(self, environment):
        self.heartbeat()
        reader = getattr(self, '_state', None)
        if reader is not None:
            try:
                reader.refresh()
            except RuntimeError:
                reader.close()
                self._state = None  # A replaced Set can invalidate native objects first.
        pending = sorted((self.root / "requests").glob("*.json"),
                         key=lambda path: path.name)
        for request in pending:
            running = self.root / "running" / request.name
            try:
                request.replace(running)
            except FileNotFoundError:
                continue  # The waiting client withdrew the queued request.
            output = io.StringIO()
            reply = {"id": request.stem, "instance": self.instance, "ok": False}
            try:
                value = json.loads(running.read_text(encoding="utf-8"))
                _finite(value)
                if value["protocol"] != PROTOCOL or value["id"] != request.stem:
                    raise ValueError("Invalid request identity/protocol")
                if value["instance"] != self.instance:
                    raise ValueError("Live bridge instance changed; inspect the current set")
                if value["expires"] <= time.time():
                    raise TimeoutError("Queued request expired before execution")
                if not isinstance(value["code"], str) or not value["code"].strip():
                    raise ValueError("code must be nonempty native Python")
                if value["undo"] is not None and (
                        not isinstance(value["undo"], str) or not value["undo"]):
                    raise ValueError("undo must be a nonempty label or None")
                compiled = compile(value["code"], f"<tactus-ableton:{request.stem}>", "exec")
                env = environment()
                if 'app' in env:
                    reader = getattr(self, '_state', None)
                    if reader is None or reader.song_id != identity(env['song']):
                        if reader is not None:
                            reader.close()
                        reader = LiveState(env['song'], env['app'], uuid.uuid4().hex)
                        self._state = reader
                    env['state'] = reader
                env.update(args=value["args"], result=None)
                song = env["song"]
                if value.get("project_id") is not None and identity(song) != value["project_id"]:
                    raise ValueError("Live Set changed; inspect targets before retrying")
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    grouped = value["undo"] is not None
                    if grouped:
                        song.begin_undo_step()
                    try:
                        exec(compiled, env, env)  # noqa: S102 - trusted native execution is the contract
                        result = _finite(env["result"])
                    finally:
                        if grouped:
                            song.end_undo_step()
                reply.update(ok=True, result=result)
            except BaseException:  # noqa: BLE001 - isolate each trusted native request
                # Native Python is trusted, not sandboxed. Even SystemExit must
                # report a failed request rather than stop the polling bridge.
                reply["error"] = traceback.format_exc()
            reply["output"] = output.getvalue()
            _write(self.root / "responses" / request.name, reply)
            running.unlink()
            self.heartbeat()
            return

    def close(self):
        reader = getattr(self, '_state', None)
        if reader is not None:
            reader.close()
        path = self.root / "heartbeat.json"
        try:
            if json.loads(path.read_text(encoding="utf-8"))["instance"] == self.instance:
                path.unlink()
        except (OSError, ValueError, KeyError, TypeError):
            pass


def _control_surface():
    # Lazy imports also let transport tests exercise the actual executor outside
    # Live, without pretending a fake object implements the native API.
    import Live
    from _Framework.ControlSurface import ControlSurface

    class Surface(ControlSurface):
        def __init__(self, c_instance):
            super().__init__(c_instance)
            self._tactus_active = True
            self._tactus_queue = RequestQueue(os.path.dirname(__file__))
            self.schedule_message(1, self._tactus_poll)
            self.log_message(f"TactusBridge ready: {self._tactus_queue.root}")

        def _tactus_poll(self):
            if not self._tactus_active:
                return
            try:
                self._tactus_queue.poll(lambda: {
                    "Live": Live, "song": self.song(),
                    "app": Live.Application.get_application(),
                })
            except Exception:  # noqa: BLE001 - keep scheduling after a queue I/O failure
                self.log_message(f"TactusBridge queue error: {traceback.format_exc()}")
            finally:
                if self._tactus_active:
                    self.schedule_message(1, self._tactus_poll)

        def disconnect(self):
            self._tactus_active = False
            self._tactus_queue.close()
            super().disconnect()

    return Surface


def TactusBridge(c_instance):
    return _control_surface()(c_instance)
