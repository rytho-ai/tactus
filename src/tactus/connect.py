"""Install the bundled native DAW bridges and register an optional Codex MCP entry."""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from importlib.util import find_spec
from pathlib import Path

from ._mcp_args import LEGACY_LIVE_SCRIPT_NAME, LIVE_SCRIPT_NAME, _candidates
from .bridges import ableton, reaper
from .bridges._instances import available
from .bridges.ableton_support._vendor.ableton_paths import user_library_candidates

REAPER_SCRIPT_NAME = "TactusMCP.lua"
PREVIOUS_REAPER_SCRIPT_NAMES = ("tactus-mcp.lua", "Tactus MCP.lua")


def _existing(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if path.is_dir()), None)


def _files(source: Path, filename: str | None = None) -> dict[Path, Path]:
    if source.is_file():
        return {Path(filename or source.name): source}
    return {Path(path.name): path for path in source.glob("*.py") if path.is_file()}


def _install(source: Path, target: Path, *, check: bool, backup_root: Path,
             filename: str | None = None) -> dict:
    files = _files(source, filename)
    if not files:
        raise ValueError(f"No bundled bridge files found at {source}")
    differing = [name for name, path in files.items()
                 if (target / name).is_file() and (target / name).read_bytes() != path.read_bytes()]
    missing = [name for name in files if not (target / name).is_file()]
    if not differing and not missing:
        return {"state": "installed", "path": str(target), "files": len(files)}
    if check:
        return {"state": "update_available" if differing else "not_installed",
                "path": str(target), "files": len(files)}
    backup = None
    if differing:
        backup = backup_root / f"{target.name}-{uuid.uuid4().hex[:12]}"
        backup.mkdir(parents=True)
        for name in differing:
            shutil.copy2(target / name, backup / name)
    target.mkdir(parents=True, exist_ok=True)
    for name in (*differing, *missing):
        shutil.copy2(files[name], target / name)
    result = {"state": "installed", "path": str(target), "files": len(files)}
    if backup is not None:
        result["backup"] = str(backup)
    return result


def _codex_entry(*, check: bool) -> dict:
    if find_spec("mcp") is None:
        return {"state": "unavailable", "reason": "Install tactus[mcp] in this Tactus environment"}
    executable = shutil.which("codex")
    if executable is None:
        return {"state": "unavailable", "reason": "Codex CLI is not installed"}
    # Keep the virtualenv entrypoint: resolving its symlink points to a base Python
    # that cannot import the Tactus installation or its optional MCP dependency.
    expected_command = str(Path(sys.executable).absolute())
    existing = subprocess.run([executable, "mcp", "get", "tactus-mcp"],
                              capture_output=True, text=True, check=False)
    if existing.returncode == 0:
        settings = dict(line.strip().split(": ", 1) for line in existing.stdout.splitlines()
                        if ": " in line)
        if settings.get("command") == expected_command and settings.get("args") == "-m tactus.mcp":
            return {"state": "configured", "name": "tactus-mcp"}
        return {"state": "conflict", "name": "tactus-mcp",
                "reason": "An existing entry uses a different command; inspect it before replacing"}
    if "No MCP server named" not in existing.stderr:
        return {"state": "error", "name": "tactus-mcp",
                "reason": existing.stderr.strip() or "Could not inspect Codex MCP settings"}
    if check:
        return {"state": "not_configured", "name": "tactus-mcp"}
    added = subprocess.run([executable, "mcp", "add", "tactus-mcp", "--",
                            expected_command, "-m", "tactus.mcp"],
                           capture_output=True, text=True, check=False)
    if added.returncode:
        return {"state": "error", "reason": added.stderr.strip() or added.stdout.strip()}
    return {"state": "configured", "name": "tactus-mcp"}


def connect(*, host: str | None = None, reaper_path: Path | None = None,
            live_library: Path | None = None, check: bool = False) -> dict:
    """Set up bundled bridges without modifying DAW projects or activation preferences."""
    if host not in (None, "codex"):
        raise ValueError(f"Unsupported agent host: {host}")
    resource = reaper_path.expanduser() if reaper_path else _existing(_candidates("reaper"))
    library = live_library.expanduser() if live_library else _existing(user_library_candidates())
    report: dict = {"name": "Tactus MCP", "check_only": check}
    if resource is None or not resource.is_dir():
        report["reaper"] = {"state": "unavailable", "reason": "REAPER resource directory not found"}
    else:
        scripts = resource / "Scripts"
        report["reaper"] = _install(reaper.script(), resource / "Scripts",
                                    check=check, backup_root=resource / ".tactus-backups",
                                    filename=REAPER_SCRIPT_NAME)
        report["reaper"]["path"] = str(scripts / REAPER_SCRIPT_NAME)
        for name in PREVIOUS_REAPER_SCRIPT_NAMES:
            old_script = scripts / name
            if old_script.is_file():
                report["reaper"].setdefault("previous_names", []).append(str(old_script))
        step = "In REAPER, load this file in Actions > ReaScript: Load, then run the Action."
        if sys.platform == "darwin":
            step += f" With REAPER closed, `open -a REAPER \"{scripts / REAPER_SCRIPT_NAME}\"` starts both."
        if "previous_names" in report["reaper"]:
            step += " Stop and remove the previous Tactus Action before deleting its file."
        report["reaper"]["next_step"] = step
    if library is None or not library.is_dir():
        report["live"] = {"state": "unavailable", "reason": "Live User Library not found"}
    else:
        remote_scripts = library / "Remote Scripts"
        installed = remote_scripts / LIVE_SCRIPT_NAME
        previous = remote_scripts / LEGACY_LIVE_SCRIPT_NAME
        report["live"] = _install(ableton.script(), installed,
                                  check=check, backup_root=library / ".tactus-backups")
        if previous.is_dir():
            report["live"]["previous_name"] = str(previous)
        report["live"]["active_scripts"] = [name for name, path in
                                            ((LIVE_SCRIPT_NAME, installed),
                                             (LEGACY_LIVE_SCRIPT_NAME, previous))
                                            if available(path / "tactus-bridge")]
        report["live"]["next_step"] = (
            f"Restart Live and select {LIVE_SCRIPT_NAME} in Settings > MIDI > Control Surface "
            "(Input and Output: None)." if LIVE_SCRIPT_NAME not in report["live"]["active_scripts"]
            else "The TactusMCP Control Surface is active; reload the MCP host if it used an old path."
        )
    if host == "codex":
        report["host"] = _codex_entry(check=check)
        report["host"]["next_step"] = "Reload MCP connections or start a new Codex session."
    return report
