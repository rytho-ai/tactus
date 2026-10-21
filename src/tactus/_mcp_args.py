"""Small, shared CLI surface for one MCP server and optional DAW targets."""

import argparse
import os
import platform
from pathlib import Path

from .bridges.ableton_support._vendor.ableton_paths import user_library_candidates


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Default to both DAWs while retaining targeted and legacy launch forms."""
    parser.add_argument("daw", nargs="?", choices=("reaper", "live"),
                        help="Optional single-DAW target; omit to expose both")
    parser.add_argument("--path", type=Path,
                        help="Override the directory for a single-DAW target")
    parser.add_argument("--reaper-path", type=Path,
                        help="Override REAPER's resource directory in dual-DAW mode")
    parser.add_argument("--live-path", type=Path,
                        help="Override Live's installed TactusBridge directory in dual-DAW mode")
    legacy = parser.add_mutually_exclusive_group()
    legacy.add_argument("--resource-path", type=Path, help=argparse.SUPPRESS)
    legacy.add_argument("--ableton-path", type=Path, help=argparse.SUPPRESS)


def _candidates(daw: str) -> list[Path]:
    if daw == "live":
        return [p / "Remote Scripts" / "TactusBridge" for p in user_library_candidates()]
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [home / "Library" / "Application Support" / "REAPER"]
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata) / "REAPER"] if appdata else [home / "AppData" / "Roaming" / "REAPER"]
    return [home / ".config" / "REAPER"]


def _detected_path(daw: str, *, required: bool) -> Path:
    candidates = _candidates(daw)
    path = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if path is not None:
        return path
    if not required:
        return candidates[0]
    checked = ", ".join(str(candidate) for candidate in candidates)
    if daw == "reaper":
        advice = "In REAPER choose Options > Show REAPER resource path"
    else:
        advice = "Install TactusBridge in Live's User Library/Remote Scripts"
    raise ValueError(f"Cannot find {daw} connection directory. Checked: {checked}. "
                     f"{advice}. Use --path DIR if needed.")


def connection_kwargs(*, daw: str | None = None, path: Path | None = None,
                      resource_path: Path | None = None, ableton_path: Path | None = None,
                      reaper_path: Path | None = None, live_path: Path | None = None) -> dict:
    """Resolve both DAWs by default, without launching or changing either host."""
    if daw is None:
        if path is not None:
            raise ValueError("Use --reaper-path or --live-path without a DAW selector")
        if resource_path is not None or ableton_path is not None:
            if reaper_path is not None or live_path is not None:
                raise ValueError("Do not combine legacy and dual-DAW path flags")
            return ({"resource_path": resource_path} if resource_path is not None
                    else {"ableton_path": ableton_path})
        return {"resource_path": reaper_path or _detected_path("reaper", required=False),
                "ableton_path": live_path or _detected_path("live", required=False),
                "allow_missing": True}
    if any(value is not None for value in (resource_path, ableton_path, reaper_path, live_path)):
        raise ValueError("Use --path with reaper/live; do not combine it with other path flags")
    if path is None:
        path = _detected_path(daw, required=True)
    return {"resource_path": path} if daw == "reaper" else {"ableton_path": path}
