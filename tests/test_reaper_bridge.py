"""Native bridge transport/export contracts; live Lua checks opt into an isolated REAPER."""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import run
from tactus.bridges import reaper
from tactus.commands import Command
from tactus.export import deliver


@pytest.fixture
def ipc(tmp_path):
    root = tmp_path / "tactus-bridge"
    (root / "requests").mkdir(parents=True)
    (root / "responses").mkdir()
    (root / "heartbeat.json").write_text(json.dumps({"protocol": 1, "time": time.time()}))
    return root


def respond(ipc, payload):
    """One fake peer exercises the actual client's file protocol, not REAPER behavior."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        pending = list((ipc / "requests").glob("*.lua"))
        if pending:
            request = pending[0]
            request.unlink()
            response = ipc / "responses" / f"{request.stem}.json"
            temporary = response.with_suffix(".tmp")
            temporary.write_text(payload)
            temporary.replace(response)
            return
        time.sleep(0.002)
    raise AssertionError("Client did not submit a request")


def test_return_print_and_remote_error(ipc, capsys):
    for payload, expected in [
        (
            {"ok": True, "result": [1, {"value": "聲音"}], "output": "diagnostic"},
            [1, {"value": "聲音"}],
        ),
        ({"ok": False, "error": "native failure", "output": "before failure"}, None),
    ]:
        with ThreadPoolExecutor() as peer:
            future = peer.submit(respond, ipc, json.dumps(payload))
            if expected is not None:
                assert reaper.execute("return {}", resource_path=ipc.parent) == expected
            else:
                with pytest.raises(reaper.BridgeError, match="native failure"):
                    reaper.execute("error('native failure')", resource_path=ipc.parent)
            future.result()
    output = capsys.readouterr()
    assert output.out == "" and "diagnostic" in output.err and "before failure" in output.err
    assert not list((ipc / "responses").iterdir())


def test_timeout_withdraws_queue_without_retry(ipc):
    with pytest.raises(reaper.BridgeTimeout, match="execution may have started"):
        reaper.execute("return 1", resource_path=ipc.parent, timeout=0.02)
    assert not list((ipc / "requests").iterdir())


def test_stale_missing_and_incompatible_bridge_fail_before_submission(ipc):
    for content in ['{"protocol":1,"time":0}', '{"protocol":2}', "[]", "not JSON"]:
        (ipc / "heartbeat.json").write_text(content)
        with pytest.raises(reaper.BridgeError):
            reaper.execute("return 1", resource_path=ipc.parent)
        assert not list((ipc / "requests").iterdir())
    (ipc / "heartbeat.json").unlink()
    with pytest.raises(reaper.BridgeError, match="run .* in REAPER"):
        reaper.execute("return 1", resource_path=ipc.parent)


@pytest.mark.parametrize("payload", ["not JSON", "{}", "[]", '{"ok":1}'])
def test_malformed_reply_is_visible(ipc, payload):
    with ThreadPoolExecutor() as peer:
        future = peer.submit(respond, ipc, payload)
        with pytest.raises(reaper.BridgeError, match="Invalid REAPER reply"):
            reaper.execute("return 1", resource_path=ipc.parent)
        future.result()


@pytest.mark.parametrize(
    "options",
    [
        {"timeout": 0},
        {"timeout": True},
        {"timeout": float("nan")},
        {"undo": ""},
        {"args": {"value": float("inf")}},
        {"args": {1: "bad key"}},
        {"args": 2**63},
    ],
)
def test_invalid_call_does_not_touch_daw(ipc, options):
    with pytest.raises((TypeError, ValueError)):
        reaper.execute("return args", resource_path=ipc.parent, **options)
    assert not list((ipc / "requests").iterdir())


def test_export_preserves_channels_lengths_headroom_and_uses_existing_export_flow(
    tmp_path, monkeypatch
):
    source = tmp_path / "song.py"
    source.write_text("""import numpy as np
def render():
    return {"sample_rate": 24000, "outputs": {"mix": np.ones(8),
        "mono": np.array([0.123456789,1.5,-1.5]), "stereo":np.ones((5,2))}}
""")
    rendered = tmp_path / "run"
    run(source, out=rendered)
    source.unlink()  # Handoff must read the checkpoint, not rerun music.
    calls = []

    def native(code, *, resource_path, args):
        calls.append(args)
        assert resource_path == str(tmp_path)
        Path(args["project"]).write_text("native project supplied by REAPER")
        return {"version": "test-peer", "tracks": ["guid-a", "guid-b"]}

    monkeypatch.setattr(reaper, "execute", native)
    result = deliver(
        rendered,
        out=tmp_path / "export",
        command=Command("reaper", "export", reaper.export_project),
        params={"resource_path": str(tmp_path), "markers": [[0, "start"]]},
    )
    assert calls[0]["tempo"] is None and calls[0]["markers"] == [[0, "start"]]
    assert [t["name"] for t in calls[0]["tracks"]] == ["mono", "stereo"]
    mono, rate = sf.read(result["files"]["media/mono.wav"])
    stereo, _ = sf.read(result["files"]["media/stereo.wav"])
    assert rate == 24000 and mono.shape == (3,) and stereo.shape == (5, 2)
    np.testing.assert_array_equal(mono, np.array([0.123456789, 1.5, -1.5], dtype=np.float32))
    record = json.loads(Path(result["manifest"]).read_text())
    assert record["source"]["kind"] == "original-render"
    assert record["exporter"]["callable"] == "tactus.bridges.reaper:export_project"
    assert record["result"]["project"] == "song.rpp"
    origin = json.loads(Path(result["files"]["source.json"]).read_text())
    assert origin["run"]["run"] == str(rendered)


@pytest.mark.parametrize(
    "options",
    [
        {"names": []},
        {"names": ["stem", "stem"]},
        {"names": ["../bad"]},
        {"markers": [[-1, "negative"]]},
        {"markers": [[1, "too late"]]},
        {"tempo": 0},
        {"tempo": float("inf")},
    ],
)
def test_bad_export_inputs_fail_before_writing_or_calling(tmp_path, monkeypatch, options):
    def unexpected(*args, **kwargs):
        raise AssertionError("DAW should not be touched")

    monkeypatch.setattr(reaper, "execute", unexpected)
    with pytest.raises((TypeError, ValueError)):
        reaper.export_project(
            {"stem": np.ones(8)},
            24000,
            out=tmp_path / "out",
            resource_path=str(tmp_path),
            **options,
        )
    assert not (tmp_path / "out").exists()


LIVE = os.environ.get("TACTUS_REAPER_RESOURCE_PATH")


@pytest.mark.skipif(not LIVE, reason="Opt in with isolated TACTUS_REAPER_RESOURCE_PATH")
def test_live_new_request_is_visible_in_first_poll_after_cached_directory_read():
    """Warm the native directory cache, then create a request immediately before poll.

    This checks visibility in the same poll, without asserting a wall-clock latency.
    The one-shot defer wrapper restores itself before invoking the actual bridge.
    """
    identity = uuid.uuid4().hex
    reaper.execute('''
local probe={complete=false,seen=false}
_G.tactus_queue_refresh_test=probe
local original=reaper.defer
reaper.defer=function(callback)
 reaper.defer=original
 return original(function()
  local root=reaper.GetResourcePath()..'/tactus-bridge'
  local request=root..'/requests/'..args.id..'.lua'
  local response=root..'/responses/'..args.id..'.json'
  local called=false
  local ok,message=xpcall(function()
   reaper.EnumerateFiles(root..'/requests',-1)
   reaper.EnumerateFiles(root..'/requests',0)
   local file=assert(io.open(request,'wb'))
   file:write('return {protocol=1,expires='..(os.time()+10)..
    ',run=function() _G.tactus_queue_refresh_test.seen=true;return true end}')
   file:close()
   called=true;callback()
  end,debug.traceback)
  if not called then callback() end -- Keep the bridge alive even if fixture I/O fails.
  probe.error=not ok and message or nil
  probe.first_poll_saw_request=probe.seen
  probe.complete=true
  os.remove(request);os.remove(response)
 end)
end
return true
''', resource_path=LIVE, args={'id': identity})
    try:
        for _ in range(5):
            state = reaper.execute('''
local p=_G.tactus_queue_refresh_test
return {complete=p.complete,seen=p.first_poll_saw_request,error=p.error}
''', resource_path=LIVE)
            if state['complete']:
                break
        assert state['complete'] and not state.get('error'), state
        assert state['seen'], 'A newly created request must be visible in the next poll'
    finally:
        reaper.execute('_G.tactus_queue_refresh_test=nil;return true', resource_path=LIVE)


@pytest.mark.skipif(not LIVE, reason="Opt in with isolated TACTUS_REAPER_RESOURCE_PATH")
def test_live_native_lua_data_errors_and_timeout():
    def execute(code, **kwargs):
        return reaper.execute(code, resource_path=LIVE, **kwargs)

    args = {
        "string": '音色\\path\n"\0é',
        "integer": 2**53 + 1,
        "precise": 0.12345678901234567,
        "list": [True, False, 1.5],
    }
    assert execute("print('native Lua'); return args", args=args) == args
    assert execute("return args", args=None) is None
    assert execute("return {}") == {}
    for code, error in [
        ("this is invalid Lua", "syntax|near"),
        ("error('intentional')", "intentional"),
        ("return function() end", "Return JSON values"),
        ("return 0/0", "Non-finite"),
        ("local t={};t.self=t;return t", "Cyclic"),
    ]:
        with pytest.raises(reaper.BridgeError, match=error):
            execute(code)
    with pytest.raises(reaper.BridgeTimeout):
        execute(
            "local t=reaper.time_precise()+.15; while reaper.time_precise()<t do end; return 'late'",
            timeout=0.03,
        )
    assert execute("return reaper.GetAppVersion()", timeout=2)


@pytest.mark.skipif(not LIVE, reason="Opt in with isolated TACTUS_REAPER_RESOURCE_PATH")
def test_live_native_handoff_reopens_and_renders_portable_media(tmp_path):
    rate = 24000
    mono = np.linspace(-0.08, 0.08, 4800)
    stereo = np.column_stack([np.full(2400, 0.02), np.full(2400, -0.02)])
    before = reaper.execute("return select(2,reaper.EnumProjects(-1,''))", resource_path=LIVE)
    out = tmp_path / "original"
    result = reaper.export_project(
        {"mono": mono, "stereo": stereo},
        rate,
        out=out,
        resource_path=LIVE,
        markers=[[0, "start"]],
        tempo=100,
    )
    assert result["project"] == "song.rpp" and len(result["reaper"]["tracks"]) == 2
    assert (
        reaper.execute("return select(2,reaper.EnumProjects(-1,''))", resource_path=LIVE) == before
    )
    # Rename, not just copy: the original media path is now unavailable.
    moved = tmp_path / "moved"
    out.rename(moved)
    state = reaper.execute(
        """
local previous = reaper.EnumProjects(-1,'')
reaper.Main_OnCommand(41929,0)
local ok,result=xpcall(function()
 reaper.Main_openProject(args.project)
 local first=reaper.GetTrack(0,0)
 local take=reaper.GetActiveTake(reaper.GetTrackMediaItem(first,0))
 local file=reaper.GetMediaSourceFileName(reaper.GetMediaItemTake_Source(take),'')
 reaper.GetSetProjectInfo(0,'RENDER_SRATE',24000,true)
 reaper.GetSetProjectInfo(0,'RENDER_CHANNELS',2,true)
 reaper.GetSetProjectInfo(0,'RENDER_BOUNDSFLAG',0,true)
 reaper.GetSetProjectInfo(0,'RENDER_STARTPOS',0,true)
 reaper.GetSetProjectInfo(0,'RENDER_ENDPOS',.2,true)
 reaper.GetSetProjectInfo(0,'RENDER_SETTINGS',0,true)
 reaper.GetSetProjectInfo(0,'RENDER_TAILFLAG',0,true)
 reaper.GetSetProjectInfo(0,'RENDER_NORMALIZE',0,true)
 reaper.GetSetProjectInfo(0,'RENDER_DITHER',0,true)
 reaper.GetSetProjectInfo_String(0,'RENDER_FORMAT','ZXZhdxgAAQ==',true)
 reaper.GetSetProjectInfo_String(0,'RENDER_FILE',args.out,true)
 reaper.GetSetProjectInfo_String(0,'RENDER_PATTERN','verified',true)
 reaper.Main_OnCommand(42230,0)
 return {file=file,tempo=reaper.Master_GetTempo(),count=reaper.CountTracks(0)}
end,debug.traceback)
reaper.SelectProjectInstance(previous)
assert(ok,result)
return result
""",
        resource_path=LIVE,
        args={"project": moved / "song.rpp", "out": tmp_path},
    )
    assert Path(state["file"]).is_relative_to(moved / "media")
    assert state["count"] == 2 and state["tempo"] == 100
    actual, sr = sf.read(tmp_path / "verified.wav", always_2d=True)
    expected = np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)
    expected[: len(stereo)] += stereo.astype(np.float32)
    assert sr == rate and actual.shape == (4800, 2)
    np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
