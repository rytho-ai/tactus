"""tactus serve's v1 API: requests as resources, their files, delivery, the page and the work card."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest
import soundfile as sf

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

import uvicorn

from tactus._serve_http import bind, create_app
from tactus.serve import Service

WORK = '''"""A test tone. `level` sets the loudness; `tape` is a list of steps."""
import numpy as np
import tactus

def render(*, level: float = 0.25, tape=None):
    if tape is not None and not isinstance(tape, list):
        raise tactus.InvalidParameters("tape must be a list of steps")
    audio = np.full((8000, 1), level, dtype=np.float32)
    return {"sample_rate": 8000, "outputs": {"a": audio, "b": audio[:4000] * 0.5},
            "map": {"outputs": {"a": {"grid": {"bars": [0, 4000], "end": 8000},
                                      "lanes": {"marks": {"kind": "points",
                                                          "items": [{"at": 2000, "text": "x"}]}}}},
                    "clock_hint": {"what": "one bar of tone, then half a bar"}}}
'''


def start(tmp_path: Path, *, static: Path | None = None, retain: int | None = None):
    root = tmp_path / "work"
    root.mkdir(exist_ok=True)
    (root / "song.py").write_text(WORK)
    service = Service(root / "song.py", tmp_path / "serve", retain=retain, checkpoint=False)
    service.start()
    sock = bind("127.0.0.1", 0)
    instance = uvicorn.Server(
        uvicorn.Config(create_app(service, static=static), log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=instance.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not instance.started:
        time.sleep(0.01)

    def stop():
        instance.should_exit = True
        thread.join(timeout=10)
        service.close()
        sock.close()

    return sock.getsockname()[1], service, stop


@pytest.fixture
def server(tmp_path):
    port, service, stop = start(tmp_path)
    yield port, service
    stop()


def fetch(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    payload = None if body is None else json.dumps(body)
    default = {"Content-Type": "application/json"} if method == "POST" else {}
    connection.request(method, path, body=payload, headers={**default, **(headers or {})})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), data


def call(port, method, path, body=None):
    status, _, data = fetch(port, method, path, body)
    return status, json.loads(data)


def test_render_answers_with_the_request_as_a_resource(server):
    port, _ = server
    status, doc = call(port, "POST", "/v1/render", {"params": {"level": 0.5}})
    assert status == 200 and doc["status"] == "ok"
    assert doc["request"] == 1 and doc["url"] == "/v1/requests/1"
    assert doc["sample_rate"] == 8000
    assert doc["outputs"]["a"]["frames"] == 8000 and doc["outputs"]["a"]["seconds"] == 1.0
    assert doc["outputs"]["b"]["frames"] == 4000 and doc["outputs"]["b"]["seconds"] == 0.5
    assert doc["outputs"]["a"]["url"].startswith("/v1/requests/1/files/a-")
    assert doc["map"]["outputs"]["a"]["grid"]["bars"] == [0, 4000]
    assert doc["map_seconds"]["outputs"]["a"]["grid"]["bars"] == [0.0, 0.5]
    assert doc["map"]["clock_hint"] == {"what": "one bar of tone, then half a bar"}
    assert doc["params"] == {"level": 0.5, "tape": None}  # as bound, defaults included
    assert doc["receipt"] == "/v1/requests/1/receipt"
    assert set(doc["timings"]) == {"queue", "load", "render", "worker", "total"}
    assert doc["load"]["id"] == "L1"
    assert Path(doc["paths"]["run"]).name == "0001" and Path(doc["paths"]["receipt"]).is_file()
    assert "bundle" not in doc and "deliver_error" not in doc
    status, again = call(port, "GET", "/v1/requests/1")
    assert status == 200 and again == doc
    status, receipt = call(port, "GET", doc["receipt"])
    assert status == 200 and receipt["service"]["request"] == 1
    status, missing = call(port, "GET", "/v1/requests/9")
    assert status == 404 and missing["error"]["code"] == "not_found"


def test_files_are_served_from_the_request_directory_only(server, tmp_path):
    port, _ = server
    _, doc = call(port, "POST", "/v1/render", {})
    status, headers, data = fetch(port, "GET", doc["outputs"]["a"]["url"])
    assert status == 200 and headers["content-type"] == "audio/wav"
    assert data == Path(doc["paths"]["outputs"]["a"]).read_bytes()
    status, headers, part = fetch(port, "GET", doc["outputs"]["a"]["url"], headers={"Range": "bytes=0-43"})
    assert status == 206 and part == data[:44] and headers["content-range"].startswith("bytes 0-43/")
    status, map_json = call(port, "GET", "/v1/requests/1/files/map.json")
    assert status == 200 and map_json == doc["map"]
    run = Path(doc["paths"]["run"])
    secret = tmp_path / "secret.txt"
    secret.write_text("no")
    os.symlink(secret, run / "link.txt")
    (run / "inner").mkdir()
    for path in ("link.txt", "../0001/manifest.json", "%2e%2e/0001/manifest.json", "inner",
                 "nothing.wav", "..%2Fsecret.txt"):
        status, error = call(port, "GET", f"/v1/requests/1/files/{path}")
        assert status == 404 and error["error"]["code"] == "not_found", path


@pytest.mark.parametrize(
    "deliver", [{"codec": "flac", "peaks": 0}, {"codec": "aac", "bitrate": "96k", "peaks": 0}]
)
def test_deliver_writes_a_bundle_whose_lengths_equal_the_frames(server, deliver):
    if deliver["codec"] == "aac" and shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    port, _ = server
    status, doc = call(port, "POST", "/v1/render", {"deliver": deliver})
    assert status == 200 and "deliver_error" not in doc
    assert doc["bundle"] == "/v1/requests/1/files/web/bundle.json"
    assert "deliver" in doc["timings"]
    status, bundle = call(port, "GET", doc["bundle"])
    assert status == 200 and bundle["sample_rate"] == 8000
    for name in ("a", "b"):
        entry = bundle["outputs"][name]
        assert entry["frames"] == doc["outputs"][name]["frames"]
        assert entry["decoded"]["frames"] == entry["frames"]
        assert doc["outputs"][name]["delivered"] == f"/v1/requests/1/files/web/{entry['file']}"
        status, headers, data = fetch(port, "GET", doc["outputs"][name]["delivered"])
        assert status == 200 and len(data) > 0
    if deliver["codec"] == "flac":
        status, _, data = fetch(port, "GET", doc["outputs"]["a"]["delivered"])
        assert headers["content-type"] == "audio/flac"
        path = Path(doc["paths"]["run"], "web", bundle["outputs"]["a"]["file"])
        assert sf.info(path).frames == 8000 and path.read_bytes() == data
    assert bundle["map_seconds"]["outputs"]["a"]["grid"]["bars"] == [0.0, 0.5]


def test_delivery_failure_is_reported_and_keeps_the_run(server):
    port, _ = server
    status, doc = call(port, "POST", "/v1/render", {"deliver": {"codec": "aac"}})  # no bitrate
    assert status == 200 and doc["deliver_error"]["code"] == "export_failed"
    assert "bitrate" in doc["deliver_error"]["message"] and "bundle" not in doc
    assert Path(doc["paths"]["receipt"]).is_file()
    assert not Path(doc["paths"]["run"], "web").exists()
    for body in ({"deliver": {"bitrate": "96k"}}, {"deliver": {"codec": "flac", "x": 1}},
                 {"deliver": "flac"}, {"steps": []}):
        status, error = call(port, "POST", "/v1/render", body)
        assert status == 400 and error["error"]["code"] == "invalid_request", body
    status, error = call(port, "POST", "/render", {"deliver": {"codec": "flac"}})
    assert status == 400, "the unversioned /render takes no deliver"


def test_retired_requests_keep_receipt_and_parameters(tmp_path):
    port, service, stop = start(tmp_path, retain=1)
    try:
        call(port, "POST", "/v1/render", {"param_files": {"tape": [1, 2]}})
        status, doc = call(port, "POST", "/v1/render", {"params": {"level": 0.1}})
        assert doc["retired"] == [1]
        status, gone = call(port, "GET", "/v1/requests/1")
        assert status == 404 and gone["receipt"] == "/v1/requests/1/receipt"
        status, receipt = call(port, "GET", gone["receipt"])
        assert status == 200 and receipt["parameters"]["tape"] == [1, 2]
        kept = service.directory / "retired" / "0001.parameters" / "tape.json"
        assert kept.read_bytes() == b"[1,2]"
        status, _ = call(port, "GET", "/v1/requests/1/files/receipt.json")
        assert status == 404
    finally:
        stop()


def test_work_card_is_derived_from_code_and_runs(server, tmp_path):
    port, service = server
    status, card = call(port, "GET", "/v1/work")
    assert status == 200
    assert card["about"].startswith("A test tone.")
    assert card["parameters"] == {
        "level": {"annotation": "float", "default": 0.25},
        "tape": {"annotation": None, "default": None},
    }
    assert card["examples"] == {} and card["requests_kept"] == 0
    for level in (0.1, 0.2, 0.1, 0.3, 0.4):
        call(port, "POST", "/v1/render", {"params": {"level": level}})
    status, card = call(port, "GET", "/v1/work")
    assert card["examples"]["level"] == [0.4, 0.3, 0.1]  # newest first, distinct, at most 3
    assert card["examples"]["tape"] == [None]
    assert card["sample_rate"] == 8000 and card["requests_kept"] == 5
    summary = card["map_summary"]
    assert summary["outputs"]["a"]["bars"] == 2
    assert summary["outputs"]["a"]["lanes"]["marks"] == {
        "kind": "points", "items": 1, "fields": ["at", "text"]
    }
    assert summary["clock_hint"] == {"what": "one bar of tone, then half a bar"}
    # A new service on the same --out finds the examples in the earlier session's receipts.
    with Service(service.source, service.out, checkpoint=False) as fresh:
        card = fresh.work()
    assert card["examples"]["level"] == [0.4, 0.3, 0.1]
    assert card["requests_kept"] == 0 and card["sample_rate"] == 8000


def test_static_page_shares_the_origin_and_api_routes_win(tmp_path):
    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<p>page</p>")
    (page / "status").write_text("shadow")
    (page / "app.js").write_text("1")
    port, _, stop = start(tmp_path, static=page)
    try:
        status, _, data = fetch(port, "GET", "/")
        assert status == 200 and data == b"<p>page</p>"
        status, _, data = fetch(port, "GET", "/app.js")
        assert status == 200 and data == b"1"
        status, state = call(port, "GET", "/status")
        assert status == 200 and state["status"] == "ok"
        status, _, _ = fetch(port, "GET", "/app.js", headers={"Host": "evil.example"})
        assert status == 403
        status, _, _ = fetch(port, "GET", "/missing.js")
        assert status == 404
    finally:
        stop()


def test_index_and_openapi_list_the_v1_routes(server):
    port, _ = server
    status, index = call(port, "GET", "/")
    assert status == 200 and "POST /v1/render" in index["routes"]
    status, spec = call(port, "GET", "/openapi.json")
    assert status == 200
    for path in ("/v1/render", "/v1/requests/{number}", "/v1/requests/{number}/files/{path}",
                 "/v1/requests/{number}/receipt", "/v1/work", "/render", "/status"):
        assert path in spec["paths"], path
    status, _, page = fetch(port, "GET", "/docs")
    assert status == 200 and b"swagger" in page.lower()
    status, _, _ = fetch(port, "GET", "/openapi.json", headers={"Origin": "https://evil.example"})
    assert status == 403


def test_old_render_route_answers_as_before(server):
    port, _ = server
    status, result = call(port, "POST", "/render", {"params": {"level": 0.5}})
    assert status == 200
    assert {"outputs", "manifest", "receipt", "render", "levels", "request", "run", "load",
            "timings", "session_bytes", "map", "status", "render_bytes"} == set(result)
    assert Path(result["outputs"]["a"]).is_file()
    # The same request is also a resource.
    status, doc = call(port, "GET", "/v1/requests/1")
    assert status == 200 and doc["paths"]["outputs"] == result["outputs"]
