"""Exercise tactus serve's HTTP layer against a real local uvicorn server, and the CLI."""

from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

import uvicorn

from tactus import RunError
from tactus._serve_http import bind, create_app, is_loopback
from tactus.serve import Service

WORK = """import numpy as np
import tactus

def render(*, level=0.25, tape=None):
    if tape is not None and not isinstance(tape, list):
        raise tactus.InvalidParameters("tape must be a list of steps")
    return {"sample_rate": 8000, "outputs": {"a": np.full((80, 1), level, dtype=np.float32)}}
"""


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "song.py").write_text(WORK)
    service = Service(root / "song.py", tmp_path / "serve")
    service.start()
    sock = bind("127.0.0.1", 0)
    instance = uvicorn.Server(
        uvicorn.Config(create_app(service), log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=instance.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not instance.started:
        time.sleep(0.01)
    yield sock.getsockname()[1], service
    instance.should_exit = True
    thread.join(timeout=10)
    service.close()
    sock.close()


def call(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    payload = None if body is None else (body if isinstance(body, bytes) else json.dumps(body))
    default = {"Content-Type": "application/json"} if method == "POST" else {}
    connection.request(method, path, body=payload, headers={**default, **(headers or {})})
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return response.status, data


def test_render_and_status(server):
    port, service = server
    status, result = call(port, "POST", "/render", {"params": {"level": 0.5}, "key": "next"})
    assert status == 200 and result["status"] == "ok" and result["request"] == 1
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["parameters"]["level"] == 0.5 and receipt["service"]["load"]["id"] == "L1"
    status, state = call(port, "GET", "/status")
    assert status == 200 and state["requests"] == 1 and state["load"]["id"] == "L1"
    assert state["session"] == service.session


def test_invalid_parameters_is_400_with_the_works_message(server):
    port, _ = server
    status, result = call(port, "POST", "/render", {"param_files": {"tape": {"x": 1}}})
    assert status == 400
    assert result["error"] == {
        "code": "invalid_parameters",
        "phase": "bind",
        "message": "tape must be a list of steps",
    }
    status, result = call(port, "POST", "/render", {"param_files": {"tape": [1]}})
    assert status == 200 and Path(result["run"], "parameters", "tape.json").read_bytes() == b"[1]"


def test_malformed_requests_are_400(server):
    port, _ = server
    for body in (b"not json", b"[1]", {"steps": []}, {"params": {"nope": 1}}):
        status, result = call(port, "POST", "/render", body)
        assert status == 400, body
        assert result["error"]["code"] in {"invalid_request", "invalid_parameters"}


def test_local_only_guards(server):
    port, _ = server
    status, result = call(port, "GET", "/status", headers={"Host": "evil.example"})
    assert status == 403 and result["error"]["code"] == "invalid_request"
    status, _ = call(port, "POST", "/render", {}, headers={"Origin": "https://evil.example"})
    assert status == 403
    status, _ = call(port, "POST", "/render", {}, headers={"Content-Type": "text/plain"})
    assert status == 415
    status, _ = call(port, "GET", "/status", headers={"Origin": "http://127.0.0.1:4197"})
    assert status == 200


def test_reload_and_cancel(server):
    port, _ = server
    status, result = call(port, "POST", "/reload", {})
    assert (
        status == 200 and result["load"]["id"] == "L2" and result["load"]["reason"] == "requested"
    )
    status, result = call(port, "POST", "/cancel", {})
    assert status == 200 and result["cancelled_running"] is False


def test_only_loopback_hosts_bind():
    assert is_loopback("127.0.0.1") and is_loopback("localhost") and is_loopback("[::1]")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.2")
    with pytest.raises(RunError) as refused:
        bind("0.0.0.0", 0)
    assert refused.value.code == "invalid_request"


@pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
def test_cli_serves_until_interrupted(tmp_path, stop):
    root = tmp_path / "work"
    root.mkdir()
    (root / "song.py").write_text(WORK)
    process = subprocess.Popen(
        [sys.executable, "-m", "tactus.cli", "serve", str(root / "song.py")]
        + ["--out", str(tmp_path / "serve"), "--no-checkpoint"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "TACTUS_PROJECT_ROOT": ""},
    )
    try:
        line = process.stderr.readline()
        assert line.startswith("tactus serve: http://127.0.0.1:"), line
        port = int(line.split()[2].rsplit(":", 1)[1])
        status, result = call(port, "POST", "/render", {"params": {"level": 0.1}})
        assert status == 200 and result["render"] is None
        process.send_signal(stop)
        out, _ = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    summary = json.loads(out)
    assert summary["status"] == "ok" and summary["requests"] == 1


def test_cli_refuses_a_non_loopback_host(tmp_path, capsys):
    from tactus.cli import main

    root = tmp_path / "work"
    root.mkdir()
    (root / "song.py").write_text(WORK)
    code = main(["serve", str(root / "song.py"), "--out", str(tmp_path / "s"), "--host", "0.0.0.0"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_request"


def test_launcher_forwards_sigterm_and_waits_for_the_work(tmp_path):
    script = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *a: sys.exit(7))\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    driver = (
        "import sys\n"
        "from tactus.launcher import _delegate\n"
        f"sys.exit(_delegate([sys.executable, '-c', {script!r}], dict(__import__('os').environ)))\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", driver], stdout=subprocess.PIPE, text=True, cwd=tmp_path
    )
    assert process.stdout.readline().strip() == "ready"
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=10) == 7
