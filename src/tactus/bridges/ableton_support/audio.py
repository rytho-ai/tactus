"""Build/control/record a namespaced Max audio tap without blocking Live's main thread.

An authored recipe chooses routing, playback, timing, trimming and adoption. Raw tap
audio reflects Live's real-time clock; this is not an offline/sample-exact renderer.
Reads: adopted MIT tap/Max builder, shared JSON and local acknowledgment files.
"""

import json
import math
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import soundfile as sf

from ..._contracts import write_json
from ._assets import declare_device
from ._lifecycle import cleanup
from ._vendor import agent_m4l

ASSETS = Path(__file__).with_name("m4l")


def build(out: str | Path) -> dict:
    """Build a new tap folder. Its command/status files are unique to this device."""
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    command_path = out / "command.json"
    status_path = out / "status.json"
    patch = json.loads((ASSETS / "AgentAudioTap.maxpat").read_text(encoding="utf-8"))
    for row in patch["patcher"]["boxes"]:
        box = row["box"]
        text = box.get("text", "")
        if text == "js agent_audio_tap.js":
            box["text"] = (f"js agent_audio_tap.js {agent_m4l.max_arg(str(command_path))} "
                           f"{agent_m4l.max_arg(str(status_path))}")
        elif text.startswith("s agent_audio_tap_status"):
            box["text"] = f"s tactus_audio_tap_{uuid.uuid4().hex}"
        elif box.get("id") == "obj-title":
            box["text"] = "Tactus Audio Tap"
        elif "Controlled by Ableton MCP" in text:
            box["text"] = "Tactus file commands; stereo audio passes through unchanged."
    # Only explicit file commands control this tap. An authored patch can add
    # MIDI/UDP control deliberately; ordinary played notes must not start recording.
    removed = {'obj-udp', 'obj-tosymbol', 'obj-notein', 'obj-stripnote', 'obj-midi-select',
               'obj-midi-start', 'obj-midi-stop'}
    patcher = patch['patcher']
    patcher['boxes'] = [r for r in patcher['boxes'] if r['box']['id'] not in removed]
    patcher['lines'] = [r for r in patcher['lines']
                        if r['patchline']['source'][0] not in removed
                        and r['patchline']['destination'][0] not in removed]
    source = out / "Tactus Audio Tap.maxpat"
    write_json(source, patch)
    device = out / "Tactus Audio Tap.amxd"
    agent_m4l.build_amxd(source, device, "audio_effect")
    (out / "agent_audio_tap.js").write_bytes((ASSETS / "agent_audio_tap.js").read_bytes())
    config = {"amxd_path": str(device), "command_file": str(command_path),
              "status_file": str(status_path), "udp_port": None}
    (out / "LICENSE").write_bytes(Path(agent_m4l.__file__).with_name("LICENSE").read_bytes())
    write_json(out / "device.json", config)
    return config


def command(config: dict, action: str, *, path: str | Path | None = None,
            timeout: float = 5) -> dict:
    """Open/start/stop/query one tap and wait for its explicit acknowledgment."""
    if action not in {"open", "start", "stop", "status"}:
        raise ValueError("Unknown tap command")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    payload = {"id": uuid.uuid4().hex, "command": action}
    if path is not None:
        destination = Path(path).expanduser().resolve()
        if destination.exists():
            raise FileExistsError(destination)
        payload["path"] = str(destination)
    if action == "open" and path is None:
        raise ValueError("open requires a new output path")
    write_json(Path(config["command_file"]), payload, compact=True)
    status = Path(config["status_file"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = json.loads(status.read_text(encoding="utf-8"))
            if result.get("command_id") == payload["id"] and result.get("event") == action:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.01)
    raise TimeoutError(f"Tap command {payload['id']} completion unknown; inspect {status}; "
                       "do not automatically repeat writes.")


@contextmanager
def record(config: dict, *, path: str | Path, timeout: float = 5):
    """Record to a new file around caller-owned playback, duration and routing.

    Use one caller per tap. Each command waits for its own acknowledgment. Once a
    start is attempted, stop is attempted once even on errors; commands are never
    retried. Preserve a primary error if stop also fails. The file must decode and
    contain frames; silence is valid. Timing, gain, trimming and adoption stay outside.
    """
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    declare_device(config)
    if command(config, 'status', timeout=timeout)['recording']:
        raise RuntimeError('Tap is already recording; inspect before starting another take')
    command(config, 'open', path=destination, timeout=timeout)
    with cleanup(lambda: command(config, 'stop', timeout=timeout),
                 f'Tap stop completion unknown; inspect {destination}'):
        command(config, 'start', timeout=timeout)
        yield destination
    info = sf.info(destination)
    if info.frames == 0:
        raise ValueError(f'Recording contains no frames; inspect {destination}')


def capture(config: dict, perform, *, timeout: float = 5):
    """Return raw (frames-first audio, sample_rate) around a caller-owned performance.

    Own scratch files, recording acknowledgments, decoding and successful cleanup.
    perform() owns playback/duration/routing. Preserve leading timing/tails/amplitude;
    silence is valid. Failures retain the raw scratch and annotate its location.
    """
    if not callable(perform):
        raise TypeError('Supply a performance callable')
    scratch = Path(tempfile.mkdtemp(prefix='tactus-live-capture-'))
    path = scratch / 'capture.wav'
    try:
        with record(config, path=path, timeout=timeout):
            perform()
        samples, rate = sf.read(path, always_2d=True)
        if not np.isfinite(samples).all():
            raise ValueError('Capture contains nonfinite samples')
    except BaseException as exc:
        exc.add_note(f'Live capture retained: {scratch}; inspect before retrying')
        raise
    path.unlink()
    scratch.rmdir()
    return samples, rate
