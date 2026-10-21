"""MCP is an optional protocol entry to the existing native bridge, not an agent host."""

import asyncio
import builtins
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CancelledNotification, CancelledNotificationParams, ClientNotification

from tactus import mcp as entry
from tactus.bridges import reaper

LIVE = os.environ.get("TACTUS_REAPER_RESOURCE_PATH")


@asynccontextmanager
async def client(resource, *, command=None, arguments=None):
    params = StdioServerParameters(
        command=command or sys.executable,
        args=arguments or ["-m", "tactus.mcp", "reaper", "--path", str(resource)],
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        assert init.serverInfo.name == "tactus"
        yield session


def content(result):
    if result.isError:
        return "\n".join(c.text for c in result.content if c.type == "text")
    assert result.structuredContent is not None
    return result.structuredContent


@pytest.fixture
def peer(tmp_path):
    root = tmp_path / "tactus-bridge"
    (root / "requests").mkdir(parents=True)
    (root / "responses").mkdir()
    (root / "heartbeat.json").write_text(json.dumps({"protocol": 1, "time": time.time()}))
    return root


def reply(peer, payload):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        pending = list((peer / "requests").glob("*.lua"))
        if pending:
            request = pending[0]
            source = request.read_text()
            request.unlink()
            output = peer / "responses" / f"{request.stem}.json"
            temporary = output.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload))
            temporary.replace(output)
            return source
        time.sleep(.005)
    raise AssertionError("MCP did not submit a bridge request")


def test_stdio_discovery_and_offline_status(tmp_path):
    async def trial():
        async with client(tmp_path) as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert set(tools) == {"reaper_status", "reaper_execute"}
            assert tools["reaper_status"].annotations.readOnlyHint
            assert not tools["reaper_execute"].annotations.readOnlyHint
            assert tools["reaper_execute"].annotations.destructiveHint
            assert not tools["reaper_execute"].annotations.idempotentHint
            assert tools["reaper_execute"].inputSchema["required"] == ["code"]
            assert tools["reaper_execute"].outputSchema["type"] == "object"
            status = content(await session.call_tool("reaper_status"))
            assert status["status"] == "unavailable"
            assert status["resource_path"] == str(tmp_path)
            assert Path(status["bridge_script"]).is_file()
            assert "run" in status["error"]["message"]
            failed = await session.call_tool("reaper_execute", {"code": "return true"})
            assert failed.isError and "BridgeError" in content(failed)
    asyncio.run(trial())
    assert not (tmp_path / "tactus-bridge").exists()


@pytest.mark.parametrize("value", [None, False, 17, "聲音\n\"\\", [1, {"音": True}], {}])
def test_stdio_native_json_result_and_explicit_args(peer, value):
    async def trial():
        async with client(peer.parent) as session:
            task = asyncio.create_task(asyncio.to_thread(
                reply, peer, {"ok": True, "result": value, "output": "native diagnostic"}
            ))
            result = await session.call_tool("reaper_execute", {
                "code": "return args", "args": {"聲音": "quotes'\"\n\\", "rows": [1, False]},
                "undo": "Tactus: 試驗", "timeout": 3,
            })
            assert content(result) == {"result": value}
            source = await task
            assert "undo=" in source and "Tactus: 試驗" in source
            assert "local args=" in source and "聲音" in source
    asyncio.run(trial())


@pytest.mark.parametrize("payload, expected", [
    ({"ok": False, "error": "partial native failure", "output": ""}, "partial native failure"),
    ({"wrong": True}, "Invalid REAPER reply"),
])
def test_stdio_native_errors_remain_errors_and_server_survives(peer, payload, expected):
    async def trial():
        async with client(peer.parent) as session:
            task = asyncio.create_task(asyncio.to_thread(reply, peer, payload))
            result = await session.call_tool("reaper_execute", {"code": "return true"})
            await task
            assert result.isError and expected in content(result)
            assert len((await session.list_tools()).tools) == 2
    asyncio.run(trial())


def test_stdio_timeout_has_late_reply_path_and_no_retry(peer):
    async def trial():
        async with client(peer.parent) as session:
            result = await session.call_tool("reaper_execute", {"code": "return 1", "timeout": .05})
            assert result.isError
            assert "execution may have started" in content(result)
            assert "late reply" in content(result)
    asyncio.run(trial())
    assert not list((peer / "requests").glob("*.lua"))


@pytest.mark.parametrize("arguments", [
    {"code": ""}, {"code": 42}, {"code": "return 1", "timeout": True},
    {"code": "return 1", "timeout": "3"}, {"code": "return 1", "timeout": 0},
    {"code": "return 1", "undo": ""},
])
def test_invalid_arguments_do_not_submit_native_work(peer, arguments):
    async def trial():
        async with client(peer.parent) as session:
            result = await session.call_tool("reaper_execute", arguments)
            assert result.isError
    asyncio.run(trial())
    assert not list((peer / "requests").glob("*.lua"))


def test_cancellation_keeps_native_worker_serialized(tmp_path, monkeypatch):
    active = 0
    maximum = 0
    finished = []
    started = threading.Event()

    def native(code, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        started.set()
        time.sleep(.12)
        finished.append(code)
        active -= 1
        return code

    monkeypatch.setattr(reaper, "execute", native)
    server = entry.create_server(resource_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            # initialize used request 0; the first tool call uses request 1.
            first = asyncio.create_task(session.call_tool("reaper_execute", {"code": "first"}))
            await anyio.to_thread.run_sync(started.wait)
            await session.send_notification(ClientNotification(CancelledNotification(
                method="notifications/cancelled",
                params=CancelledNotificationParams(requestId=1, reason="user cancelled"),
            )))
            result = await session.call_tool("reaper_execute", {"code": "second"})
            assert content(result) == {"result": "second"}
            try:
                await first
            except McpError:
                pass  # A cancelled reply is host/protocol state, not native rollback.
    anyio.run(trial)
    assert finished == ["first", "second"] and maximum == 1


def test_json_looking_strings_are_not_reinterpreted(tmp_path, monkeypatch):
    monkeypatch.setattr(reaper, "execute", lambda code, **kw: [kw.get("args"), kw.get("undo")])
    server = entry.create_server(resource_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            for value in ["null", "[]", "{}", "false", '["notes"]', {"x": 2}, [1], None]:
                result = await session.call_tool("reaper_execute", {
                    "code": "return args", "args": value, "undo": "null",
                })
                assert content(result) == {"result": [value, "null"]}
    anyio.run(trial)


def test_startup_failures_stay_off_protocol_stdout(tmp_path, monkeypatch, capsys):
    assert entry.main(["--resource-path", str(tmp_path / "missing")]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "does not exist" in captured.err
    original = builtins.__import__

    def without_sdk(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("SDK absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sdk)
    assert entry.main(["--resource-path", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "tactus[mcp]" in captured.err


def test_ordinary_import_and_cli_help_do_not_load_sdk(tmp_path):
    code = """
import builtins
original=builtins.__import__
def importing(name,*a,**kw):
    if name=='mcp' or name.startswith('mcp.'):
        raise AssertionError('Optional SDK must not be imported')
    return original(name,*a,**kw)
builtins.__import__=importing
from tactus.bridges import reaper
from tactus.cli import main
main(['mcp','--help'])
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "omit to expose both" in result.stdout


@pytest.mark.skipif(not LIVE, reason="Use isolated TACTUS_REAPER_RESOURCE_PATH")
def test_live_stdio_status_edit_readback_failure_and_undo(tmp_path):
    async def trial():
        async with client(LIVE) as session:
            async def execute(code, **kwargs):
                result = await session.call_tool("reaper_execute", {"code": code, **kwargs})
                assert not result.isError, content(result)
                return content(result)["result"]

            previous = await execute("return tostring(reaper.EnumProjects(-1,''))")
            try:
                await execute("""
reaper.Main_OnCommand(41929,0)
local p=reaper.EnumProjects(-1,'')
for i,name in ipairs({'MCP 聲音','Keep this track'}) do
 reaper.InsertTrackAtIndex(i-1,true)
 reaper.GetSetMediaTrackInfo_String(reaper.GetTrack(p,i-1),'P_NAME',name,true)
end
local t=reaper.GetTrack(p,0)
local item=reaper.CreateNewMIDIItemInProj(t,0,4,false)
reaper.SetOnlyTrackSelected(t)
reaper.SetMediaItemSelected(item,true)
reaper.SetTempoTimeSigMarker(p,-1,0,-1,-1,93,3,4,false)
reaper.SetTempoTimeSigMarker(p,-1,2,-1,-1,108,5,8,false)
reaper.SetEditCurPos2(p,3,false,false)
reaper.GetSet_LoopTimeRange2(p,true,false,1,2,false)
reaper.Main_SaveProjectEx(p,args.path,8)
reaper.Undo_OnStateChangeEx2(p,'MCP fixture baseline',-1,-1)
return true
""", args={"path": str(tmp_path / "MCP 聲音.rpp")})
                report = content(await session.call_tool("reaper_status"))
                assert report["status"] == "ready"
                project = report["project"]
                assert project["tracks"] == 2 and project["meter"] == [5, 8]
                assert project["tempo"] == 108 and project["cursor_s"] == 3
                assert project["time_selection_s"] == [1, 2]
                assert project["selected_tracks"][0]["name"] == "MCP 聲音"
                assert len(project["selected_items"]) == 1
                guid = project["selected_tracks"][0]["guid"]
                changed = await execute("""
local t=reaper.GetSelectedTrack(0,0)
assert(reaper.GetTrackGUID(t)==args.guid,'Target changed')
reaper.SetMediaTrackInfo_Value(t,'D_VOL',.73)
return reaper.GetMediaTrackInfo_Value(t,'D_VOL')
""", args={"guid": guid}, undo="Tactus MCP: fixture gain")
                assert changed == .73
                assert await execute("return reaper.Undo_CanUndo2(0)") == "Tactus MCP: fixture gain"
                assert await execute("""
reaper.Undo_DoUndo2(0)
return reaper.GetMediaTrackInfo_Value(reaper.GetSelectedTrack(0,0),'D_VOL')
""") == 1
                failed = await session.call_tool("reaper_execute", {"code": """
reaper.SetMediaTrackInfo_Value(reaper.GetSelectedTrack(0,0),'D_VOL',.62)
error('MCP partial mutation')
""", "undo": "Tactus MCP: deliberate failure"})
                assert failed.isError and "MCP partial mutation" in content(failed)
                assert await execute("""
return reaper.GetMediaTrackInfo_Value(reaper.GetSelectedTrack(0,0),'D_VOL')
""") == .62
                await execute("reaper.Undo_DoUndo2(0);return true")
                assert await execute("""
return reaper.GetMediaTrackInfo_Value(reaper.GetSelectedTrack(0,0),'D_VOL')
""") == 1
            finally:
                await execute("""
for i=0,100 do local p=reaper.EnumProjects(i,'');if not p then break end
 if tostring(p)==args.previous then reaper.SelectProjectInstance(p);return true end
end
error('Original tab no longer exists')
""", args={"previous": previous})
    asyncio.run(trial())
