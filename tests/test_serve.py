"""Exercise the resident render service core (tactus.serve.Service) without an HTTP server."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import RunError
from tactus.cli import main as cli
from tactus.render_store import prune, read_published
from tactus.serve import Service

WORK = """import os
import numpy as np
import tactus
import tone

LOADED_BY = os.getpid()

def render(*, level=0.25, tape=None, wait=0.0, crash=False):
    if tape is not None and not isinstance(tape, list):
        raise tactus.InvalidParameters("tape must be a list of steps")
    if crash:
        raise RuntimeError("boom")
    if wait:
        import time
        time.sleep(wait)
    audio = np.full((800, 1), level * tone.GAIN, dtype=np.float32)
    marker = np.full((8, 1), LOADED_BY % 1000 / 1000, dtype=np.float32)
    return {"sample_rate": 8000, "outputs": {"a": audio, "pid": marker}}
"""


def make_work(tmp_path: Path, gain: str = "1.0") -> Path:
    root = tmp_path / "work"
    root.mkdir(exist_ok=True)
    (root / "tone.py").write_text(f"GAIN = {gain}\n")
    entry = root / "song.py"
    entry.write_text(WORK)
    return entry


def read(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


@pytest.fixture
def service(tmp_path):
    entry = make_work(tmp_path)
    with Service(entry, tmp_path / "serve") as running:
        yield running


def test_one_load_serves_many_requests_each_with_its_own_receipt(service):
    first = service.render({"level": 0.25})
    second = service.render({"level": 0.5})
    assert first["load"] == second["load"]
    assert first["load"]["id"] == "L1" and first["load"]["reason"] == "start"
    assert (first["request"], second["request"]) == (1, 2)
    assert Path(first["run"]).name == "0001" and Path(second["run"]).name == "0002"
    for result, level in ((first, 0.25), (second, 0.5)):
        receipt = read(result["receipt"])
        assert receipt["parameters"]["level"] == level
        assert receipt["service"]["load"]["id"] == "L1"
        assert receipt["service"]["load"]["pid"] == first["load"]["pid"]
        assert receipt["service"]["request"] == result["request"]
        assert receipt["service"]["session"] == service.session
        assert receipt["source_files"]["tone.py"] == hashlib.sha256(b"GAIN = 1.0\n").hexdigest()
        assert receipt["source_changed"] is None
        audio, rate = sf.read(result["outputs"]["a"])
        assert rate == 8000 and np.allclose(audio, level, atol=1e-6)
    # start() loaded the work once; neither request paid for a load.
    assert first["load"]["seconds"] > 0
    assert first["timings"]["load"] == second["timings"]["load"] == 0
    assert set(second["timings"]) == {"queue", "load", "render", "worker", "total"}
    log = [json.loads(line) for line in (service.directory / "session.jsonl").open()]
    assert [event["event"] for event in log] == ["session", "load", "request", "request"]
    assert (
        log[3]["receipt_sha256"] == hashlib.sha256(Path(second["receipt"]).read_bytes()).hexdigest()
    )


def test_request_directories_are_ordinary_runs(service, tmp_path, capsys):
    result = service.render()
    run_dir = Path(result["run"])
    published = read_published(run_dir)
    assert set(published.outputs) == {"a", "pid"}
    capsys.readouterr()
    assert cli(["export", "wav", str(run_dir), "--out", str(tmp_path / "wav")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert prune(run_dir)["freed_bytes"] > 0
    assert result["session_bytes"] > 0


def test_source_edit_between_requests_starts_a_new_load(service, tmp_path):
    before = service.render()
    (tmp_path / "work" / "tone.py").write_text("GAIN = 2.0\n")
    after = service.render()
    assert after["load"]["id"] == "L2" and after["load"]["reason"] == "source_changed"
    assert after["load"]["pid"] != before["load"]["pid"]
    receipt = read(after["receipt"])
    assert receipt["source_files"]["tone.py"] == hashlib.sha256(b"GAIN = 2.0\n").hexdigest()
    assert receipt["service"]["load"]["reason"] == "source_changed"
    audio, _ = sf.read(after["outputs"]["a"])
    assert np.allclose(audio, 0.5, atol=1e-6)
    assert after["timings"]["load"] > 0


def test_edit_during_a_request_is_certain_for_files_loaded_before_it(tmp_path):
    entry = make_work(tmp_path)
    text = entry.read_text().replace(
        "    if crash:",
        "    if level == 0.75:\n        open('tone.py', 'w').write('GAIN = 3.0\\n')\n    if crash:",
    )
    entry.write_text(text)
    with Service(entry, tmp_path / "serve") as service:
        result = service.render({"level": 0.75})
        changed = read(result["receipt"])["source_changed"]
        assert changed["certain"] is True
        [edit] = changed["files"]
        assert edit["path"] == "tone.py" and edit["imported_at_load"] is True
        assert "next request loads" in changed["message"]
        audio, _ = sf.read(result["outputs"]["a"])
        assert np.allclose(audio, 0.75, atol=1e-6)  # the loaded GAIN = 1.0
        assert service.render()["load"]["id"] == "L2"


def test_invalid_parameters_are_the_works_message_and_the_worker_survives(service):
    ok = service.render()
    with pytest.raises(RunError) as rejected:
        service.render(param_files={"tape": {"not": "a list"}})
    assert rejected.value.code == "invalid_parameters"
    assert str(rejected.value) == "tape must be a list of steps"
    assert rejected.value.exit_code == 2
    with pytest.raises(RunError) as crashed:
        service.render({"crash": True})
    assert crashed.value.code == "execution_failed" and "boom" in str(crashed.value)
    again = service.render()
    assert again["load"] == ok["load"]
    # Failed requests leave no directory behind; their numbers stay used.
    assert not (service.directory / "0002").exists() and not (service.directory / "0003").exists()
    assert again["request"] == 4


def test_param_files_are_recorded_and_copied(service):
    result = service.render(param_files={"tape": [{"step": 1}, {"step": 2}]})
    receipt = read(result["receipt"])
    payload = b'[{"step":1},{"step":2}]'
    assert receipt["parameters"]["tape"] == [{"step": 1}, {"step": 2}]
    assert receipt["parameter_files"]["tape"] == {
        "path": None,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "copy": "parameters/tape.json",
    }
    assert (Path(result["run"]) / "parameters" / "tape.json").read_bytes() == payload
    with pytest.raises(RunError) as both:
        service.render({"tape": []}, param_files={"tape": []})
    assert both.value.code == "invalid_request"


def test_path_param_file_reads_the_file(service, tmp_path):
    tape = tmp_path / "tape.json"
    tape.write_text("[1, 2]")
    receipt = read(service.render(param_files={"tape": tape})["receipt"])
    assert receipt["parameter_files"]["tape"]["path"] == str(tape)


def test_a_newer_request_with_the_same_key_supersedes_a_waiting_one(service):
    results: dict[str, object] = {}

    def submit(name, **kwargs):
        try:
            results[name] = service.render(**kwargs)
        except RunError as exc:
            results[name] = exc

    slow = threading.Thread(target=submit, args=("slow",), kwargs={"params": {"wait": 1.0}})
    slow.start()
    time.sleep(0.3)
    stale = threading.Thread(
        target=submit, args=("stale",), kwargs={"params": {"level": 0.1}, "key": "next"}
    )
    stale.start()
    time.sleep(0.2)
    fresh = threading.Thread(
        target=submit, args=("fresh",), kwargs={"params": {"level": 0.2}, "key": "next"}
    )
    fresh.start()
    for thread in (slow, stale, fresh):
        thread.join(timeout=30)
    assert isinstance(results["stale"], RunError) and results["stale"].code == "superseded"
    assert read(results["fresh"]["receipt"])["parameters"]["level"] == 0.2
    assert results["slow"]["request"] == 1 and results["fresh"]["request"] == 2


def test_cancel_kills_a_running_render_and_the_next_request_loads_again(service):
    outcome: dict[str, object] = {}

    def submit():
        try:
            outcome["result"] = service.render({"wait": 30.0})
        except RunError as exc:
            outcome["error"] = exc

    first = service.render()
    thread = threading.Thread(target=submit)
    thread.start()
    time.sleep(0.5)
    started = time.perf_counter()
    assert service.cancel()["cancelled_running"] is True
    thread.join(timeout=10)
    assert time.perf_counter() - started < 5
    assert outcome["error"].code == "cancelled"
    assert not (service.directory / "0002").exists()
    after = service.render()
    assert after["load"]["id"] == "L2" and after["load"]["reason"] == "cancelled"
    assert after["load"]["pid"] != first["load"]["pid"]


def test_a_worker_that_died_is_replaced(service):
    import os
    import signal

    first = service.render()
    os.kill(first["load"]["pid"], signal.SIGKILL)
    time.sleep(0.2)
    after = service.render()
    assert after["load"]["reason"] == "worker_exited" and after["load"]["id"] == "L2"


def test_retain_keeps_the_newest_requests_and_their_receipts(tmp_path):
    entry = make_work(tmp_path)
    with Service(entry, tmp_path / "serve", retain=2, checkpoint=False) as service:
        results = [service.render({"level": 0.1 * (i + 1)}) for i in range(4)]
        kept = sorted(p.name for p in service.directory.iterdir() if p.name.isdigit())
        assert kept == ["0003", "0004"]
        retired = service.directory / "retired"
        assert sorted(p.name for p in retired.iterdir()) == [
            "0001.receipt.json",
            "0002.receipt.json",
        ]
        assert read(retired / "0001.receipt.json")["parameters"]["level"] == 0.1
        assert results[2]["retired"] == [1] and results[3]["retired"] == [2]
        assert results[3]["render"] is None
        assert service.status()["kept_requests"] == 2
        sizes = sum(
            f.stat().st_size
            for run in ("0003", "0004")
            for f in (service.directory / run).rglob("*")
            if f.is_file()
        )
        assert results[3]["session_bytes"] == sizes


def test_a_work_that_fails_to_load_fails_start(tmp_path):
    entry = make_work(tmp_path)
    entry.write_text("raise SystemExit('not today')\n")
    service = Service(entry, tmp_path / "serve")
    with pytest.raises(RunError) as failed:
        service.start()
    assert failed.value.code == "load_failed"
    service.close()


def test_a_broken_edit_fails_the_request_and_a_fix_loads_again(service, tmp_path):
    service.render()
    tone = tmp_path / "work" / "tone.py"
    tone.write_text("GAIN = (\n")
    with pytest.raises(RunError) as broken:
        service.render()
    assert broken.value.code == "load_failed"
    tone.write_text("GAIN = 1.0\n")
    assert service.render()["load"]["id"] == "L3"


def test_import_time_materials_stay_in_every_receipt(tmp_path, monkeypatch):
    from tactus.inputs import pool

    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    root = tmp_path / "work"
    root.mkdir()
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"material bytes")
    ref = f"sha256:{pool.put(sample)}"
    (root / "song.py").write_text(
        "import numpy as np\nfrom tactus import material\n"
        f"PATH = material({ref!r})\n"
        "def render():\n"
        "    return {'sample_rate': 8000, 'outputs': {'a': np.zeros(8)}}\n"
    )
    with Service(root / "song.py", tmp_path / "serve") as service:
        for _ in range(2):
            receipt = read(service.render()["receipt"])
            assert [m["ref"] for m in receipt["materials"]] == [ref]


def test_invalid_requests_are_rejected_before_rendering(service):
    with pytest.raises(RunError) as nan:
        service.render({"level": float("nan")})
    assert nan.value.code == "invalid_request"
    with pytest.raises(RunError) as bad_key:
        service.render(key=3)
    assert bad_key.value.code == "invalid_request"
    assert service.status()["requests"] == 0


def test_output_cannot_contain_the_work(tmp_path):
    entry = make_work(tmp_path)
    with pytest.raises(RunError) as inside:
        Service(entry, tmp_path)
    assert inside.value.code == "invalid_request"
