"""Optional file-based Max host support; ordinary native Python still loads devices.

The adopted Max engine accepts authored object graphs, code, UI and values. This
module owns writable assets, command identity and completion, not musical choices.
Reads: adopted MIT Max builder/assets; shared finite JSON/atomic writer; local files.
"""

import json
import math
import time
import uuid
from pathlib import Path

from ..._contracts import json_copy, write_json
from ._assets import declare_device
from ._vendor import agent_m4l


class MaxError(RuntimeError):
    """The Max host reported a failed command."""


def build(out: str | Path, *, role: str, instance_id: str | None = None,
          title: str | None = None, width: int | None = None, height: int | None = None) -> dict:
    """Build a new unfrozen host directory. Load its AMXD through native browser code."""
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    identity = "tactus_" + agent_m4l.slugify(instance_id or uuid.uuid4().hex)
    config = agent_m4l.build_device(role, identity, title, install=False,
                                    device_width=width, device_height=height, output_dir=out)
    # File commands are the Tactus transport. Authored graphs may opt into UDP,
    # but the generated wrapper does not open an ambient command listener.
    patch_path = Path(config['patch_path'])
    patch = json.loads(patch_path.read_text(encoding='utf-8'))
    patcher = patch['patcher']
    removed = {r['box']['id'] for r in patcher['boxes']
               if r['box'].get('text', '').startswith('udpreceive ')}
    patcher['boxes'] = [r for r in patcher['boxes'] if r['box']['id'] not in removed]
    patcher['lines'] = [r for r in patcher['lines']
                        if r['patchline']['source'][0] not in removed
                        and r['patchline']['destination'][0] not in removed]
    write_json(patch_path, patch)
    agent_m4l.build_amxd(patch_path, Path(config['amxd_path']), config['role'])
    config['udp_port'] = None
    (out / "LICENSE").write_bytes(Path(agent_m4l.__file__).with_name("LICENSE").read_bytes())
    write_json(out / "device.json", config)
    return config


def _webui(identity, spec):
    if isinstance(spec, list):
        return [_webui(f"{identity}_{i}", item) for i, item in enumerate(spec)]
    if not isinstance(spec, dict):
        return spec
    if any(key in spec for key in ("html", "js", "css", "controls", "assets")):
        return {**spec, **agent_m4l.write_webui(identity, spec)}
    return spec


def command(config: dict, message: dict, *, timeout: float = 10) -> dict:
    """Submit one authored Max message and await its matching acknowledgment.

    Supports the reference host's full patch/value/WebUI protocol. Timeout is an
    unknown completion, not cancellation or permission to resend a mutation.
    """
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    declare_device(config)
    message = json_copy(message)
    if not isinstance(message, dict):
        raise TypeError("message must be a finite JSON object")
    identity = config["instance_id"]
    payload = {**message, "id": uuid.uuid4().hex, "instance_id": identity,
               "role": config["role"]}
    patch_key = "patch" if "patch" in payload else "spec"
    patch = payload.get(patch_key)
    for holder in (payload, patch):
        if isinstance(holder, dict):
            for key in ("webui", "webuis"):
                if key in holder:
                    holder[key] = _webui(identity, holder[key])
    path = Path(config["command_file"])
    status = Path(config["status_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if patch is not None and payload.get("command") not in ("web_reload", "reload_webui"):
        write_json(Path(str(path) + ".recovery.json"), {"patch": patch}, compact=True)
    write_json(path, payload, compact=True)
    expected = {"set": "set", "status": "status", "clear": "clear",
                "web_reload": "webui_reload", "reload_webui": "webui_reload"}.get(
                    payload.get("command"), "reload")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = json.loads(status.read_text(encoding="utf-8").rstrip("\0 \n\r\t"))
            if value.get("command_id") == payload["id"]:
                if value.get("event") == "error":
                    raise MaxError(json.dumps(value, ensure_ascii=False))
                if value.get("event") == expected or (
                    expected == "reload" and value.get("last_reload_command_id") == payload["id"]
                ):
                    return value
        except (OSError, ValueError):
            pass  # Max writes a live status file; incomplete writes are not replies.
        time.sleep(.02)
    raise TimeoutError(f"Max command {payload['id']} completion unknown; inspect {status}. "
                       "Do not automatically retry mutations.")
