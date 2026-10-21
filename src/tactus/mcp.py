"""Optional stdio tools for an existing agent host; native execution stays in bridge.

The standalone entry uses its installed environment, independently of a song's
lock. One server can expose REAPER and Ableton connections together. The SDK is imported
only when creating a server; ordinary bridge/Python use needs no MCP dependency.
"""

import argparse
import asyncio
import sys
from functools import partial
from importlib.metadata import version
from pathlib import Path

from ._mcp_args import add_connection_arguments, connection_kwargs
from .bridges import ableton, reaper

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

_ABLETON_INSTRUCTIONS = """Use Ableton Live in this conversation; no agent session is started.
Call ableton_status (including Live's embedded Python version), then author short
native Python using Live, song, app, state, args and result.
Status accepts scope=summary/track/notes/device/project and explicit runtime target IDs.
Summary lists tracks without scanning MIDI/parameters; request detail only when needed.
state.read uses the same fresh native reader. Observed change counters are incomplete
hints, never edit guards; unsupported listeners are reported.
Only finite JSON data crosses the bridge; convert native objects to explicit
data. Runtime object identities are not persistent IDs or comprehensive stale guards.
Inspect the actual target and relevant values immediately before edits; read back results.
Use undo to request a native Undo group (Live owns its displayed name, not the label).
Errors/cancellation/timeouts never imply rollback or cancellation of running Python.
Never automatically retry a mutation or undo a later human edit. Inspect native state
and the late response file first. Calls to the same DAW serialize; the other DAW
runs independently. Other clients and GUI edits are not locked. Long Python blocks
Live's main thread; use short operations.
Max for Live and VST are native devices: load via native browser access, inspect exposed
parameters and use ordinary source files for custom Max patches. Plugin-private GUI
and unexposed parameters are not universally accessible. No API/musical whitelist.
Setup does not launch/quit/save Live. Live state is external input; a tool response is
not a Tactus render receipt. Use Tactus skills for creation/analysis/versioning.
Object model reference (Max-facing, not a complete Python specification):
https://docs.cycling74.com/legacy/max8/vignettes/live_api_overview
Probe native Python methods/version differences; Python runtime IDs are not Max device IDs.
"""


def create_server(*, resource_path: str | Path | None = None,
                  ableton_path: str | Path | None = None, allow_missing: bool = False):
    """Create tools for one or both DAWs, without contacting or launching them."""
    try:
        import anyio
        from mcp import types
        from mcp.server.lowlevel import Server
    except ImportError as exc:
        raise ImportError(
            'MCP requires the optional SDK: install "tactus[mcp]" in this command\'s '
            'environment (from a checkout: uv sync --extra mcp).'
        ) from exc

    if resource_path is None and ableton_path is None:
        raise ValueError("Choose at least one of resource_path or ableton_path")
    targets = {}
    for prefix, path, native in (("reaper", resource_path, reaper),
                                 ("ableton", ableton_path, ableton)):
        if path is None:
            continue
        resource = Path(path).expanduser().resolve()
        if not allow_missing and not resource.is_dir():
            raise ValueError(f"{prefix} connection directory does not exist: {resource}")
        is_ableton = prefix == "ableton"
        targets[prefix] = {
            "native": native,
            "connection": {"bridge_path" if is_ableton else "resource_path": resource},
            "setup": {"ableton_path" if is_ableton else "resource_path": str(resource),
                      "bridge_script": str(native.script())},
            "lock": anyio.Lock(),
        }
    instructions = "\n".join(_ABLETON_INSTRUCTIONS if prefix == "ableton" else _INSTRUCTIONS
                             for prefix in targets)
    server = Server("tactus", version=version("tactus"), instructions=instructions)

    @server.list_tools()
    async def list_tools():
        tools = []
        for prefix in targets:
            is_ableton = prefix == "ableton"
            tools.extend([
            types.Tool(
                name=f"{prefix}_status",
                description=("Read fresh Live state: shallow summary by default, or track/notes/device/project "
                "detail using scope and optional target IDs. Observed revisions are incomplete "
                "notification hints, never edit guards. Runtime IDs "
                "are not persistent; unsupported project path is null. Does not save/edit. "
                "If unavailable, return setup paths and reason." if is_ableton else
                "Read live project/selection. If unavailable, return setup paths "
                "and reason. Empty native lists are {}. Project instance is runtime-only; "
                "the change counter alone is not a stale-edit guard. Does not save/edit."),
                inputSchema={"type": "object", "properties": ({
                    "scope": {"type": "string", "enum": ["summary", "track", "notes", "device", "project"],
                              "default": "summary"},
                    "track_id": {"type": "string", "minLength": 1},
                    "device_id": {"type": "string", "minLength": 1},
                } if is_ableton else {}), "additionalProperties": False},
                outputSchema={"type": "object"},
                annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=True),
            ),
            types.Tool(
                name=f"{prefix}_execute",
                description=("Execute native Python using Live, song, app, state, args; assign result. "
                "Live owns the Undo description. " if is_ableton else
                "Execute ordinary native ReaScript Lua with args; ") + "return "
                "{result: native JSON value}. Use an undo label to group mutations. "
                "Timeout is seconds. Errors/cancellation/timeouts never imply rollback; "
                "inspect native state/late reply before retry. Calls to the same DAW are "
                "serialized; the other DAW proceeds independently. Other clients "
                "and human edits are not locked.",
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
            ])
        return tools

    @server.call_tool()
    async def call_tool(name, arguments):
        prefix, _, action = name.partition("_")
        if prefix not in targets or action not in {"status", "execute"}:
            raise ValueError(f"Unknown tool: {name}")
        target = targets[prefix]
        native = target["native"]
        connection = target["connection"]
        setup = target["setup"]
        status = action == "status"
        try:
            # The SDK validates the schema without reinterpreting JSON-looking
            # string args/labels. Keep the worker/lock until completion or native
            # timeout even on MCP cancellation: running native code cannot be cancelled.
            async with target["lock"]:
                try:
                    with anyio.CancelScope(shield=True):
                        operation = (partial(ableton.read, **connection, **arguments)
                            if status and prefix == "ableton" else partial(
                                native.execute, _STATUS if status else arguments["code"],
                                **connection,
                                **({} if status else {k: v for k, v in arguments.items()
                                                     if k != "code"}),
                            ))
                        value = await anyio.to_thread.run_sync(operation)
                finally:
                    # Deliver deferred cancellation before the SDK attempts a
                    # normal reply to a request it already acknowledged cancelled.
                    await anyio.lowlevel.checkpoint_if_cancelled()
            return {"status": "ready", **setup, "project": value} if status else {"result": value}
        except (native.BridgeError, native.BridgeTimeout, ValueError, TypeError) as exc:
            if status:
                return {
                    "status": "completion_unknown" if isinstance(exc, native.BridgeTimeout)
                    else "unavailable",
                    **setup, "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            # An MCP tool error, preserving the bridge's native/late-reply details.
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

    return server


def serve(*, resource_path: str | Path | None = None,
          ableton_path: str | Path | None = None, allow_missing: bool = False) -> int:
    """Run stdio only; startup diagnostics go to stderr, never protocol stdout."""
    try:
        server = create_server(resource_path=resource_path, ableton_path=ableton_path,
                               allow_missing=allow_missing)
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
    add_connection_arguments(parser)
    options = parser.parse_args(argv)
    try:
        connection = connection_kwargs(daw=options.daw, path=options.path,
                                       resource_path=options.resource_path,
                                       ableton_path=options.ableton_path,
                                       reaper_path=options.reaper_path,
                                       live_path=options.live_path)
    except ValueError as exc:
        parser.error(str(exc))
    return serve(**connection)


if __name__ == "__main__":
    raise SystemExit(main())
