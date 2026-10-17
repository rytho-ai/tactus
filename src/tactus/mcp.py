"""Optional stdio tools for an existing agent host; native execution stays in bridge.

The standalone entry uses its installed environment, independently of a song's
lock. Each server binds one explicit REAPER resource directory. The SDK is imported
only when creating a server; ordinary bridge/Python use needs no MCP dependency.
"""

import argparse
import asyncio
import sys
from functools import partial
from importlib.metadata import version
from pathlib import Path

from .bridges import reaper

_STATUS = """
local p,path=reaper.EnumProjects(-1,'')
local tracks,items={},{}
for i=0,reaper.CountSelectedTracks(p)-1 do
  local t=reaper.GetSelectedTrack(p,i)
  local _,name=reaper.GetTrackName(t)
  tracks[#tracks+1]={guid=reaper.GetTrackGUID(t),name=name}
end
for i=0,reaper.CountSelectedMediaItems(p)-1 do
  local item=reaper.GetSelectedMediaItem(p,i)
  items[#items+1]={guid=({reaper.GetSetMediaItemInfo_String(item,'GUID','',false)})[2],
    position_s=reaper.GetMediaItemInfo_Value(item,'D_POSITION'),
    length_s=reaper.GetMediaItemInfo_Value(item,'D_LENGTH')}
end
local first,last=reaper.GetSet_LoopTimeRange2(p,false,false,0,0,false)
local num,den,tempo=reaper.TimeMap_GetTimeSigAtTime(p,reaper.GetCursorPositionEx(p))
return {version=reaper.GetAppVersion(),project_instance=tostring(p),project_path=path,
  change_count=reaper.GetProjectStateChangeCount(p),tracks=reaper.CountTracks(p),
  play_state=reaper.GetPlayStateEx(p),cursor_s=reaper.GetCursorPositionEx(p),
  time_selection_s={first,last},tempo=tempo,meter={num,den},
  selected_tracks=tracks,selected_items=items}
"""

_INSTRUCTIONS = """Use REAPER in this existing conversation; no agent session is started.
Call reaper_status to identify the live project and selection, then author short native
ReaScript Lua with reaper.* and explicit args. Inspect the actual target/state immediately
before mutations, read back results, and use a meaningful undo label when appropriate.
The status change counter alone is not a stale-edit guard: native setters may not bump it.
Return finite JSON data, converting native handles to GUIDs/data; an empty Lua table is {}.
Errors, cancellation and timeouts do not imply rollback. Never automatically retry a
mutation or undo a later human edit; inspect native state/late reply first. Offline renders
occupy REAPER's main thread. Connection setup does not launch/quit REAPER or save its
project; authored Lua may do so when requested.
Use Tactus skills for creation/analysis/versioning and accepted-state capture/handoff.
The live RPP remains external input; a tool response is not a Tactus render receipt.
Native reference: https://www.reaper.fm/sdk/reascript/reascripthelp.html
"""


def create_server(*, resource_path: str | Path):
    """Create two tools bound to one resource directory, without contacting REAPER."""
    try:
        import anyio
        from mcp import types
        from mcp.server.lowlevel import Server
    except ImportError as exc:
        raise ImportError(
            'MCP requires the optional SDK: install "tactus[mcp]" in this command\'s '
            'environment (from a checkout: uv sync --extra mcp).'
        ) from exc

    resource = Path(resource_path).expanduser().resolve()
    if not resource.is_dir():
        raise ValueError(f"REAPER resource directory does not exist: {resource}")
    server = Server("tactus", version=version("tactus"), instructions=_INSTRUCTIONS)
    lock = anyio.Lock()

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="reaper_status",
                description="Read live project/selection. If unavailable, return setup paths "
                "and reason. Empty native lists are {}. Project instance is runtime-only; "
                "the change counter alone is not a stale-edit guard. Does not save/edit.",
                inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
                outputSchema={"type": "object"},
                annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=True),
            ),
            types.Tool(
                name="reaper_execute",
                description="Execute ordinary native ReaScript Lua with args; return "
                "{result: native JSON value}. Use an undo label to group mutations. "
                "Timeout is seconds. Errors/cancellation/timeouts never imply rollback; "
                "inspect native state/late reply before retry. Calls in this server are "
                "serialized; other clients and human edits are not locked.",
                inputSchema={
                    "type": "object", "required": ["code"], "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string", "minLength": 1},
                        "args": {"description": "Native args: finite JSON data; preserved as given"},
                        "timeout": {"type": "number", "exclusiveMinimum": 0, "default": 30},
                        "undo": {"type": ["string", "null"], "minLength": 1, "default": None},
                    },
                },
                outputSchema={"type": "object", "required": ["result"],
                              "properties": {"result": {}}},
                annotations=types.ToolAnnotations(
                    readOnlyHint=False, destructiveHint=True,
                    idempotentHint=False, openWorldHint=True,
                ),
            ),
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name not in {"reaper_status", "reaper_execute"}:
            raise ValueError(f"Unknown tool: {name}")
        status = name == "reaper_status"
        setup = {"resource_path": str(resource), "bridge_script": str(reaper.script())}
        try:
            # The SDK validates the schema without reinterpreting JSON-looking
            # string args/labels. Keep the worker/lock until completion or native
            # timeout even on MCP cancellation: running Lua cannot be cancelled.
            async with lock:
                try:
                    with anyio.CancelScope(shield=True):
                        value = await anyio.to_thread.run_sync(partial(
                            reaper.execute, _STATUS if status else arguments["code"],
                            resource_path=resource,
                            **({} if status else {k: v for k, v in arguments.items() if k != "code"}),
                        ))
                finally:
                    # Deliver deferred cancellation before the SDK attempts a
                    # normal reply to a request it already acknowledged cancelled.
                    await anyio.lowlevel.checkpoint_if_cancelled()
            return {"status": "ready", **setup, "project": value} if status else {"result": value}
        except (reaper.BridgeError, reaper.BridgeTimeout, ValueError, TypeError) as exc:
            if status:
                return {
                    "status": "completion_unknown" if isinstance(exc, reaper.BridgeTimeout)
                    else "unavailable",
                    **setup, "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            # An MCP tool error, preserving the bridge's native/late-reply details.
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

    return server


def serve(*, resource_path: str | Path) -> int:
    """Run stdio only; startup diagnostics go to stderr, never protocol stdout."""
    try:
        server = create_server(resource_path=resource_path)
    except (ImportError, ValueError, OSError) as exc:
        print(f"tactus MCP: {exc}", file=sys.stderr)
        return 2
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(run())
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-path", required=True, type=Path,
                        help="REAPER's Options > Show REAPER resource path directory")
    options = parser.parse_args(argv)
    return serve(resource_path=options.resource_path)


if __name__ == "__main__":
    raise SystemExit(main())
