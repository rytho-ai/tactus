"""Call native ReaScript Lua from Python; export rendered audio as a REAPER project.

Run script() inside REAPER once, then execute ordinary Lua with explicit args and
resource_path. Transport, data exchange and completion live here; reaper_support owns shared
selection/project/render mechanics. Notes, routing and instruments stay authored.
Live project state is external input: pin projects/audio and declare native tools
when provenance matters. Errors/timeouts never imply rollback or automatic retry.
Reads: stdlib file queue/time/JSON; inputs.tool; SciPy WAV writer for handoff only.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import uuid
from pathlib import Path

from ..inputs import tool

__all__ = ["BridgeError", "BridgeTimeout", "execute", "export_project", "script"]


class BridgeError(RuntimeError):
    """REAPER is unavailable, the transport failed, or Lua raised an error."""


class BridgeTimeout(TimeoutError):
    """Completion is unknown; inspect the DAW before retrying a mutation."""


def script() -> Path:
    """Path to the packaged Lua script; load/run it in REAPER's Actions window."""
    return Path(__file__).with_suffix(".lua")


def _literal(value) -> str:
    """Bind Python data using native Lua literals, never executable string interpolation."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError("Lua integer args must fit signed 64 bits")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Lua args must be finite")
        return repr(value)
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if isinstance(value, str):
        value.encode("utf-8")
        escaped = "".join(
            "\\\\"
            if c == "\\"
            else '\\"'
            if c == '"'
            else f"\\{ord(c):03d}"
            if ord(c) < 32 or ord(c) == 127
            else c
            for c in value
        )
        return '"' + escaped + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(_literal(v) for v in value) + "}"
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return "{" + ",".join(f"[{_literal(k)}]={_literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(
        "Lua args accept strings/paths, finite numbers, booleans, lists and string-key dicts"
    )


def execute(
    code: str,
    *,
    resource_path: str | Path,
    args=None,
    timeout: float = 30.0,
    undo: str | None = None,
):
    """Execute Lua synchronously on REAPER's main thread, returning its first result.

    `args` is available as native Lua data (lists are 1-based; None becomes nil).
    Return finite JSON values: tables are dense arrays or string-key objects; an
    empty table becomes {}. Convert REAPER handles to GUIDs/data before returning.
    `print` goes to Python stderr. An explicit undo label groups mutations but does
    not roll them back on error. Timeout cannot cancel code already executing;
    queued requests are withdrawn/expire. There is no automatic retry.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be nonempty Lua source")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be finite and positive")
    if undo is not None and (not isinstance(undo, str) or not undo):
        raise ValueError("undo must be a nonempty label or None")
    bindings = _literal(args)
    root = Path(resource_path).expanduser().resolve() / "tactus-bridge"
    try:
        heartbeat = json.loads((root / "heartbeat.json").read_text(encoding="utf-8"))
        if not isinstance(heartbeat, dict):
            raise TypeError("Invalid heartbeat")
        if heartbeat.get("protocol") != 1:
            raise BridgeError("Incompatible REAPER bridge; run the packaged script again")
        age = time.time() - heartbeat["time"]
        if not 0 <= age <= 10:
            raise BridgeError("REAPER bridge heartbeat is stale; run the script in REAPER")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BridgeError(
            f"REAPER bridge is unavailable at {root}; run {script()} in REAPER"
        ) from exc
    tool(str(script()))
    request_id = uuid.uuid4().hex
    request = root / "requests" / f"{request_id}.lua"
    response = root / "responses" / f"{request_id}.json"
    source = (
        f"return {{protocol=1, expires={math.ceil(time.time() + timeout)}, "
        f"undo={_literal(undo)}, run=function()\nlocal args={bindings}\n{code}\nend}}\n"
    )
    temporary = request.with_suffix(".tmp")
    temporary.write_text(source, encoding="utf-8", newline="\n")
    temporary.replace(request)
    deadline = time.monotonic() + timeout
    while True:
        try:
            raw = response.read_text(encoding="utf-8")
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                request.unlink(missing_ok=True)
                raise BridgeTimeout(
                    f"REAPER request {request_id} timed out; execution may have started. "
                    f"Inspect DAW state before retrying; a late reply may appear at {response}"
                ) from None
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
            continue
        response.unlink()
        try:
            reply = json.loads(raw)
            ok = reply["ok"]
            if not isinstance(ok, bool):
                raise TypeError("Invalid reply status")
        except (ValueError, KeyError, TypeError) as exc:
            raise BridgeError(f"Invalid REAPER reply for {request_id}") from exc
        if reply.get("output"):
            print(reply["output"], file=sys.stderr)
        if not ok:
            raise BridgeError(reply.get("error", "REAPER request failed"))
        return reply.get("result")


def export_project(
    outputs,
    sample_rate,
    *,
    out: Path,
    resource_path: str,
    names: list[str] | None = None,
    markers: list | None = None,
    tempo: float | None = None,
    time_map=None,
    run_identity=None,
) -> dict:
    """Custom exporter: selected stems at zero origin in a new native REAPER tab.

    Defaults to outputs except literal mix; select names=["mix"] for a mix-only
    handoff. Lengths may differ; FLOAT WAV preserves headroom without normalization.
    Markers are explicit [seconds, label] pairs. No map lane is interpreted, and
    tempo is changed only when supplied. Saves song.rpp with relative media and
    restores the formerly selected tab, leaving the new saved tab open.
    """
    import numpy as np
    from scipy.io import wavfile

    names = [name for name in outputs if name != "mix"] if names is None else names
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("names must select distinct, existing outputs")
    if any(
        not isinstance(n, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", n)
        or n not in outputs
        for n in names
    ):
        raise ValueError("names must select existing outputs with safe filenames")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    if tempo is not None and (
        isinstance(tempo, bool)
        or not isinstance(tempo, (int, float))
        or not math.isfinite(tempo)
        or tempo <= 0
    ):
        raise ValueError("tempo must be finite and positive")
    arrays = {}
    for name in names:
        audio = np.asarray(outputs[name])
        if (
            audio.ndim not in (1, 2)
            or not len(audio)
            or (audio.ndim == 2 and audio.shape[1] not in (1, 2))
            or audio.dtype.kind not in "fiu"
        ):
            raise ValueError(f"{name} must be nonempty real mono/stereo audio")
        with np.errstate(over="ignore"):
            audio = audio.astype(np.float32)
        if not np.isfinite(audio).all():
            raise ValueError(f"{name} must fit finite float32 audio")
        arrays[name] = audio
    duration = max(len(a) for a in arrays.values()) / sample_rate
    markers = [] if markers is None else markers
    if not isinstance(markers, (list, tuple)):
        raise TypeError("markers must contain [seconds, label] pairs")
    for marker in markers:
        if (
            not isinstance(marker, (list, tuple))
            or len(marker) != 2
            or isinstance(marker[0], bool)
            or not isinstance(marker[0], (int, float))
            or not math.isfinite(marker[0])
            or not 0 <= marker[0] <= duration
            or not isinstance(marker[1], str)
            or "\0" in marker[1]
        ):
            raise ValueError("markers must contain finite in-range seconds and string labels")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    media = out / "media"
    if (out / "song.rpp").exists():
        raise FileExistsError(out / "song.rpp")
    media.mkdir()
    tracks = []
    for name, audio in arrays.items():
        wavfile.write(media / f"{name}.wav", sample_rate, audio)
        tracks.append(
            {"name": name, "file": str(media / f"{name}.wav"), "seconds": len(audio) / sample_rate}
        )
    result = execute(
        _HANDOFF,
        resource_path=resource_path,
        args={
            "project": str(out / "song.rpp"),
            "tracks": tracks,
            "rate": sample_rate,
            "markers": markers,
            "tempo": tempo,
        },
    )
    (out / "source.json").write_text(
        json.dumps({"run": run_identity, "map": time_map}, indent=2) + "\n", encoding="utf-8"
    )
    return {"project": "song.rpp", "media": [f"media/{n}.wav" for n in names], "reaper": result}


_HANDOFF = """
local previous = reaper.EnumProjects(-1, '')
reaper.Main_OnCommand(41929, 0) -- New project tab, ignore default template
local project = reaper.EnumProjects(-1, '')
assert(project ~= previous, 'Could not create a new project tab')
local ok, result = xpcall(function()
  assert(reaper.CountTracks(project) == 0, 'New project contains template tracks')
  reaper.GetSetProjectInfo(project, 'PROJECT_SRATE', args.rate, true)
  reaper.GetSetProjectInfo(project, 'PROJECT_SRATE_USE', 1, true)
  if args.tempo then reaper.SetCurrentBPM(project, args.tempo, false) end
  reaper.Main_SaveProjectEx(project, args.project, 8)
  local ids = {}
  for i, stem in ipairs(args.tracks) do
    reaper.InsertTrackAtIndex(i - 1, true)
    local track = reaper.GetTrack(project, i - 1)
    reaper.GetSetMediaTrackInfo_String(track, 'P_NAME', stem.name, true)
    reaper.SetMediaTrackInfo_Value(track, 'D_VOL', 1)
    reaper.SetMediaTrackInfo_Value(track, 'D_PANLAW', 1)
    local source = reaper.PCM_Source_CreateFromFile(stem.file)
    assert(source, 'Could not read ' .. stem.file)
    local item = reaper.AddMediaItemToTrack(track)
    local take = reaper.AddTakeToMediaItem(item)
    reaper.SetMediaItemTake_Source(take, source)
    reaper.SetMediaItemInfo_Value(item, 'D_POSITION', 0)
    reaper.SetMediaItemInfo_Value(item, 'D_LENGTH', stem.seconds)
    reaper.SetMediaItemInfo_Value(item, 'D_FADEINLEN', 0)
    reaper.SetMediaItemInfo_Value(item, 'D_FADEOUTLEN', 0)
    reaper.SetMediaItemTakeInfo_Value(take, 'D_PLAYRATE', 1)
    ids[#ids + 1] = reaper.GetTrackGUID(track)
  end
  for _, marker in ipairs(args.markers) do
    reaper.AddProjectMarker2(project, false, marker[1], 0, marker[2], -1, 0)
  end
  reaper.GetSetProjectInfo_String(project, 'RENDER_FILE', 'renders', true)
  reaper.Main_SaveProjectEx(project, args.project, 8)
  return {version = reaper.GetAppVersion(), tracks = ids}
end, debug.traceback)
reaper.SelectProjectInstance(previous)
assert(ok, result)
return result
"""
