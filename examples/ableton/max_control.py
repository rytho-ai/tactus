"""Editable Max 8 control fixture, built from the user's own empty MIDI device template.

No Max/VST commands are added to the bridge. This ordinary file recipe creates an
exposed parameter and a JS acknowledgment so actual patch execution can be checked.
The unfrozen AMXD chunk layout is verified with Live 11; this is not a general packager.
"""

import argparse
import json
from pathlib import Path

from tactus.bridges.ableton_support._vendor.agent_m4l import replace_ptch_chunk


def build(template: Path, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    script = out / "control.js"
    status = out / "status.json"
    script.write_text('''autowatch = 1;
inlets = 1;
outlets = 0;
function msg_float(value) {
    var f = new File(jsarguments[1], "write", "TEXT");
    if (!f.isopen) { error("Cannot write control acknowledgment\\n"); return; }
    f.eof = 0;
    f.writestring(JSON.stringify({value: value}));
    f.close();
}
function msg_int(value) { msg_float(value); }
''', encoding="utf-8")
    patch = {"patcher": {
        "fileversion": 1, "appversion": {"major": 8, "minor": 5, "revision": 8,
                                         "architecture": "x64", "modernui": 1},
        "classnamespace": "box", "rect": [0, 0, 460, 220], "devicewidth": 180,
        "amxdtype": 1835887981,
        "boxes": [
            {"box": {"id": "in", "maxclass": "newobj", "text": "midiin",
                     "patching_rect": [20, 20, 50, 22]}},
            {"box": {"id": "out", "maxclass": "newobj", "text": "midiout",
                     "patching_rect": [20, 100, 50, 22]}},
            {"box": {"id": "amount", "maxclass": "live.dial", "varname": "amount",
                     "parameter_enable": 1, "patching_rect": [100, 20, 50, 50],
                     "saved_attribute_attributes": {"valueof": {
                         "parameter_longname": "Probe value", "parameter_shortname": "Value",
                         "parameter_type": 0, "parameter_mmin": 0.0, "parameter_mmax": 127.0,
                         "parameter_initial": [64.0], "parameter_initial_enable": 1,
                     }}}},
            {"box": {"id": "ack", "maxclass": "newobj",
                     "text": f"js {json.dumps(str(script))} {json.dumps(str(status))}",
                     "patching_rect": [100, 110, 320, 22]}},
        ],
        "lines": [
            {"patchline": {"source": ["in", 0], "destination": ["out", 0]}},
            {"patchline": {"source": ["amount", 0], "destination": ["ack", 0]}},
        ],
        "parameters": {"amount": ["Probe value", "Value", 0]},
    }}
    (out / "Tactus Control Probe.maxpat").write_text(json.dumps(patch, indent=2), encoding="utf-8")
    device = out / "Tactus Control Probe.amxd"
    payload = json.dumps(patch, ensure_ascii=False).encode("utf-8") + b"\0"
    device.write_bytes(replace_ptch_chunk(template.read_bytes(), payload))
    return device


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True, help="Empty Max MIDI Effect.amxd")
    parser.add_argument("--out", type=Path, required=True, help="New folder in the User Library")
    options = parser.parse_args()
    print(build(options.template.resolve(), options.out.resolve()))
