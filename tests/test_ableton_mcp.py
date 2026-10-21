"""Ableton uses the existing optional MCP entry and exposes only status/execute."""

import asyncio
import os
import sys
import threading
import time

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CancelledNotification, CancelledNotificationParams, ClientNotification

from tactus import mcp as entry
from tactus.bridges import ableton, reaper


def test_real_stdio_discovery_and_offline_status(tmp_path):
    async def trial():
        params = StdioServerParameters(command=sys.executable, args=[
            "-m", "tactus.mcp", "live", "--path", str(tmp_path),
        ])
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert set(tools) == {"ableton_status", "ableton_execute"}
            assert tools["ableton_status"].annotations.readOnlyHint
            assert not tools["ableton_execute"].annotations.idempotentHint
            status = await session.call_tool("ableton_status")
            assert status.structuredContent["status"] == "unavailable"
            assert status.structuredContent["ableton_path"] == str(tmp_path)
            failed = await session.call_tool("ableton_execute", {"code": "result=1"})
            assert failed.isError
    asyncio.run(trial())
    assert not (tmp_path / "tactus-bridge").exists()


def test_native_args_and_status_share_execute(tmp_path, monkeypatch):
    calls = []

    def native(code, **kw):
        calls.append((code, kw))
        if code == 'result = state.read(**args)':
            return {"version": "fixture", **kw['args']}
        return kw.get("args")

    monkeypatch.setattr(ableton, "execute", native)
    server = entry.create_server(ableton_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            status = await session.call_tool("ableton_status")
            assert status.structuredContent["project"]["version"] == "fixture"
            assert status.structuredContent['project']['scope'] == 'summary'
            detail = await session.call_tool('ableton_status', {
                'scope': 'device', 'track_id': 'track-runtime-id', 'device_id': 'device-runtime-id',
            })
            assert detail.structuredContent['project'] == {
                'version': 'fixture', 'scope': 'device', 'track_id': 'track-runtime-id',
                'device_id': 'device-runtime-id',
            }
            for value in (None, False, "[]", {"音": [1, None]}):
                response = await session.call_tool("ableton_execute", {
                    "code": "result=args", "args": value, "undo": "Edit", "timeout": 2,
                })
                assert response.structuredContent == {"result": value}
            assert calls[-1][1] == {"bridge_path": tmp_path, "args": {"音": [1, None]},
                                     "undo": "Edit", "timeout": 2}
    anyio.run(trial)


def test_cancellation_keeps_running_python_serialized(tmp_path, monkeypatch):
    started = threading.Event()
    finished = []

    def native(code, **kwargs):
        started.set()
        time.sleep(.1)
        finished.append(code)
        return code

    monkeypatch.setattr(ableton, "execute", native)
    server = entry.create_server(ableton_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            first = asyncio.create_task(session.call_tool("ableton_execute", {"code": "first"}))
            await anyio.to_thread.run_sync(started.wait)
            await session.send_notification(ClientNotification(CancelledNotification(
                method="notifications/cancelled",
                params=CancelledNotificationParams(requestId=1, reason="cancelled"),
            )))
            second = await session.call_tool("ableton_execute", {"code": "second"})
            assert second.structuredContent == {"result": "second"}
            try:
                await first
            except McpError:
                pass
    anyio.run(trial)
    assert finished == ["first", "second"]


def test_one_or_both_daw_connections(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        entry.create_server()
    server = entry.create_server(resource_path=tmp_path, ableton_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"reaper_status", "reaper_execute",
                             "ableton_status", "ableton_execute"}
            for name in ("reaper_status", "ableton_status"):
                status = (await session.call_tool(name)).structuredContent
                assert status["status"] == "unavailable"
    anyio.run(trial)


def test_busy_reaper_does_not_block_live(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_reaper(code, **kwargs):
        started.set()
        assert release.wait(2)
        return "reaper done"

    monkeypatch.setattr(reaper, "execute", slow_reaper)
    monkeypatch.setattr(ableton, "execute", lambda code, **kwargs: "live done")
    server = entry.create_server(resource_path=tmp_path, ableton_path=tmp_path)

    async def trial():
        async with create_connected_server_and_client_session(server) as session:
            pending = asyncio.create_task(session.call_tool("reaper_execute", {"code": "wait"}))
            try:
                assert await anyio.to_thread.run_sync(started.wait, 1)
                live = await asyncio.wait_for(
                    session.call_tool("ableton_execute", {"code": "result=1"}), timeout=1)
                assert live.structuredContent == {"result": "live done"}
            finally:
                release.set()
            assert (await pending).structuredContent == {"result": "reaper done"}
    anyio.run(trial)


@pytest.mark.skipif(not os.environ.get("TACTUS_ABLETON_PATH"), reason="Use isolated Live Set")
def test_live_stdio_native_status_args_errors_and_recovery():
    async def trial():
        params = StdioServerParameters(command=sys.executable, args=[
            "-m", "tactus.mcp", "--ableton-path", os.environ["TACTUS_ABLETON_PATH"],
        ])
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            assert {t.name for t in (await session.list_tools()).tools} == {
                "ableton_status", "ableton_execute",
            }
            status = await session.call_tool("ableton_status")
            assert status.structuredContent["status"] == "ready"
            assert status.structuredContent["project"]["version"]
            assert status.structuredContent["project"]["python_version"]
            returned = await session.call_tool("ableton_execute", {
                "code": "print('native diagnostic')\nresult=args", "args": {"音": [False, None]},
            })
            assert returned.structuredContent == {"result": {"音": [False, None]}}
            failed = await session.call_tool("ableton_execute", {
                "code": "raise RuntimeError('native MCP failure')",
            })
            assert failed.isError
            recovered = await session.call_tool("ableton_execute", {"code": "result=1"})
            assert recovered.structuredContent == {"result": 1}
    asyncio.run(trial())
