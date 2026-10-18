"""Actual file/executor contracts; fake song tests do not establish native Live behavior."""

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from tactus.bridges import ableton
from tactus.bridges.TactusBridge import bridge as runtime
from tactus.bridges.TactusBridge.bridge import RequestQueue


@pytest.fixture
def peer(tmp_path):
    for source in ableton.script().glob("*.py"):
        shutil.copy2(source, tmp_path / source.name)
    queue = RequestQueue(tmp_path)
    song = SimpleNamespace(begin_undo_step=lambda: None, end_undo_step=lambda: None)
    return queue, song


def exchange(peer, code, **kwargs):
    queue, song = peer
    with ThreadPoolExecutor() as worker:
        future = worker.submit(ableton.execute, code, bridge_path=queue.root.parent, **kwargs)
        deadline = time.monotonic() + 3
        while not list((queue.root / "requests").glob("*.json")):
            assert time.monotonic() < deadline
            time.sleep(.002)
        queue.poll(lambda: {"song": song})
        return future.result()


def test_native_args_results_prints_and_no_method_blacklist(peer, capsys):
    value = {"聲音": ['quotes\'"\n\\', False, None, [1, 2.5]]}
    assert exchange(peer, 'print("diagnostic")\nresult = [args, "get_notes("]', args=value) == [
        value, "get_notes(",
    ]
    captured = capsys.readouterr()
    assert captured.out == "" and "diagnostic" in captured.err


def test_failure_closes_undo_group_without_rollback(peer):
    queue, song = peer
    groups = []
    song.begin_undo_step = lambda: groups.append("begin")
    song.end_undo_step = lambda: groups.append("end")
    with pytest.raises(ableton.BridgeError, match="partial mutation"):
        exchange(peer, 'song.value = 42\nraise RuntimeError("partial mutation")', undo="Edit")
    assert song.value == 42 and groups == ["begin", "end"]
    assert exchange(peer, "result = song.value") == 42
    assert not list((queue.root / "running").iterdir())


@pytest.mark.parametrize("code", ["result=float('nan')", "result=song", "raise SystemExit(1)"])
def test_unserializable_results_and_system_exit_remain_native_errors(peer, code):
    with pytest.raises(ableton.BridgeError):
        exchange(peer, code)
    assert exchange(peer, "result = 1") == 1


@pytest.mark.parametrize("kwargs", [
    {"timeout": True}, {"timeout": 0}, {"timeout": float("inf")}, {"undo": ""},
    {"args": {1: 2}}, {"args": float("nan")}, {"args": (1, 2)},
])
def test_invalid_args_do_not_submit(peer, kwargs):
    with pytest.raises(ValueError):
        ableton.execute("result=args", bridge_path=peer[0].root.parent, **kwargs)
    assert not list((peer[0].root / "requests").iterdir())


def test_timeout_withdraws_unstarted_request_without_retry(peer):
    queue, song = peer
    with pytest.raises(ableton.BridgeTimeout, match="late reply"):
        ableton.execute("song.changed=True", bridge_path=queue.root.parent, timeout=.02)
    queue.poll(lambda: {"song": song})
    assert not hasattr(song, "changed")
    assert not list((queue.root / "requests").iterdir())


def test_started_timeout_keeps_late_reply_and_runs_once(peer):
    queue, song = peer
    song.started = threading.Event()
    song.release = threading.Event()
    song.calls = 0
    with ThreadPoolExecutor(max_workers=2) as worker:
        future = worker.submit(ableton.execute,
                               "song.calls+=1\nsong.started.set()\nsong.release.wait(2)\nresult=42",
                               bridge_path=queue.root.parent, timeout=.1)
        deadline = time.monotonic() + 2
        while not list((queue.root / "requests").glob("*.json")):
            assert time.monotonic() < deadline
            time.sleep(.002)
        polling = worker.submit(queue.poll, lambda: {"song": song})
        assert song.started.wait(1)
        try:
            with pytest.raises(ableton.BridgeTimeout):
                future.result()
        finally:
            song.release.set()
        polling.result()
    replies = list((queue.root / "responses").glob("*.json"))
    assert len(replies) == song.calls == 1
    assert json.loads(replies[0].read_text())["result"] == 42


@pytest.mark.parametrize("mutation", [{"instance": "old-instance"}, {"expires": 0}])
def test_old_instance_or_expired_request_cannot_edit(peer, mutation):
    queue, song = peer
    request = {"id": "fixture", "protocol": 1, "instance": queue.instance,
               "expires": time.time() + 5, "code": "song.changed=True", "args": None,
               "undo": None, **mutation}
    (queue.root / "requests/fixture.json").write_text(json.dumps(request))
    queue.poll(lambda: {"song": song})
    assert not hasattr(song, "changed")
    assert not json.loads((queue.root / "responses/fixture.json").read_text())["ok"]


def test_stale_heartbeat_fails_before_submission(peer):
    queue, _ = peer
    (queue.root / "heartbeat.json").write_text(json.dumps({
        "protocol": 1, "instance": queue.instance, "time": 0,
    }))
    with pytest.raises(ableton.BridgeError, match="stale heartbeat"):
        ableton.execute("result=1", bridge_path=queue.root.parent)
    assert not list((queue.root / "requests").iterdir())


@pytest.mark.parametrize('source', ['bridge.py', 'devices.py'])
def test_missing_installed_source_is_visible_before_submission(peer, source):
    queue, _ = peer
    (queue.root.parent / source).unlink()
    with pytest.raises(ableton.BridgeError, match="installed Ableton Remote Script sources"):
        ableton.execute("result=1", bridge_path=queue.root.parent)
    assert not list((queue.root / "requests").iterdir())


@pytest.mark.parametrize("field", ["id", "instance"])
def test_mismatched_reply_is_preserved_without_retry(peer, monkeypatch, field):
    original = runtime._write

    def write(path, value):
        if path.parent.name == "responses":
            value = {**value, field: "wrong-identity"}
        original(path, value)

    monkeypatch.setattr(runtime, "_write", write)
    queue, song = peer
    song.calls = 0
    with pytest.raises(ableton.BridgeError, match="Invalid Ableton reply"):
        exchange(peer, "song.calls+=1\nresult=1")
    assert song.calls == 1
    assert len(list((queue.root / "responses").glob("*.json"))) == 1


@pytest.mark.skipif(not os.environ.get("TACTUS_ABLETON_PATH"), reason="Use isolated Live Set")
def test_live_native_python_edit_failure_and_single_undo():
    path = os.environ["TACTUS_ABLETON_PATH"]

    def call(code, **kwargs):
        return ableton.execute(code, bridge_path=path, **kwargs)

    fixture = call("""
previous=str(song.view.selected_track._live_ptr)
song.create_midi_track(-1)
t=song.tracks[-1]
t.name='Tactus isolated Undo fixture'
t.mute=True
result={'id':str(t._live_ptr),'previous':previous,
        'gain':t.mixer_device.volume.value,'pan':t.mixer_device.panning.value}
""")
    target = "t=next(t for t in song.tracks if str(t._live_ptr)==args['id'])\n"
    try:
        changed = call(target + "t.mixer_device.volume.value=.5\n"
                       "t.mixer_device.panning.value=.25\nresult=True",
                       args=fixture, undo="Tactus fixture")
        assert changed
        call("song.undo()")
        readback = target + "result=[t.mixer_device.volume.value,t.mixer_device.panning.value]"
        assert call(readback, args=fixture) == [fixture["gain"], fixture["pan"]]
        with pytest.raises(ableton.BridgeError, match="deliberate native failure"):
            call(target + "t.mixer_device.volume.value=.4\n"
                 "raise RuntimeError('deliberate native failure')",
                 args=fixture, undo="Tactus partial failure")
        assert call(readback, args=fixture)[0] == pytest.approx(.4)
        call("song.undo()")
        assert call(readback, args=fixture) == [fixture["gain"], fixture["pan"]]
    finally:
        call("""
for i,t in reversed(list(enumerate(song.tracks))):
    if str(t._live_ptr)==args['id']:
        song.delete_track(i)
for t in list(song.tracks)+list(song.return_tracks)+[song.master_track]:
    if str(t._live_ptr)==args['previous']:
        song.view.selected_track=t
""", args=fixture)
