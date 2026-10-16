"""Optional fixture regeneration against pinned DAWG; tests need neither Bun nor Git.

uv run python tests/fixtures/instruments/generate.py --dawg PATH --bun PATH
No download or installation is performed. Requires the exact revision recorded below.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

REVISION = "13263790ade044979b6268059ec91567d793e04f"


def cases():
    for name, rate, changes in [
        ("grand", 44100, {}),
        ("felt", 48000, {"family": "felt"}),
        ("high-undamped", 48000, {"pitch": 89}),
        ("half", 44100, {"pedal": [{"time": 0, "state": "half"}]}),
        ("sustain", 48000, {"pedal": [{"time": 0, "state": "down"}, {"time": 2, "state": "up"}]}),
        ("soft", 44100, {"softPedal": [{"time": 0, "state": "down"}]}),
    ]:
        changes = dict(changes)
        pitch = changes.pop("pitch", 60)
        spec = {
            "seconds": 3.0,
            "notes": [{"id": "n0", "pitch": pitch, "start": 0, "duration": 0.6, "velocity": 0.7}],
            **changes,
        }
        yield {"name": "piano-" + name, "kind": "piano", "rate": rate, "recipe": spec}
    for name, rate, changes in [
        ("plain", 44100, {}),
        ("cello", 48000, {"hz": 110.0, "body_size": 2.4, "spec": {"decay": 0.9, "pos": 0.1}}),
        ("high", 22050, {"hz": 3000.0, "vibrato_hz": 5.0, "vibrato_cents": 10.0}),
        ("slur", 48000, {"events": [{"time": 0.8, "kind": "slur", "hz": 660.0, "hold": 1.2}]}),
        ("tremolo", 44100, {"spec": {"tremhz": 8.0}}),
        (
            "curves",
            48000,
            {
                "cents": [[0, -20], [0.5, 30], [1.5, 0]],
                "controls": [
                    [0, 0.1, 0.2, 0, 0.2],
                    [0.8, 0.8, 0.9, 0.7, 1],
                    [1.5, 0.2, 0.3, 0.1, 0.5],
                ],
            },
        ),
    ]:
        spec = {"hz": 440.0, "hold": 1.5, "seconds": 3.0, "velocity": 0.7, "seed": 17, **changes}
        yield {"name": "bow-" + name, "kind": "bow", "rate": rate, "recipe": spec}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dawg", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(args.dawg), "rev-parse", "HEAD"], text=True
    ).strip()
    if (
        revision != REVISION
        or subprocess.check_output(
            ["git", "-C", str(args.dawg), "status", "--porcelain"], text=True
        ).strip()
    ):
        raise ValueError("Fixture oracle must be the clean pinned DAWG revision")
    root = Path(__file__).resolve().parent
    rows = []
    arrays = {}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        for case in cases():
            recipe = case["recipe"]
            rate = case["rate"]
            kind = case["kind"]
            (tmp / "input.json").write_text(json.dumps(recipe))
            bridge = root / f"{kind}-reference.ts"
            subprocess.run(
                [
                    str(args.bun.resolve()),
                    str(bridge),
                    str(args.dawg.resolve()),
                    str(tmp / "input.json"),
                    str(tmp / "audio.f64"),
                    str(rate),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            audio = np.fromfile(tmp / "audio.f64", dtype="<f8").reshape(
                -1, 2 if kind == "piano" else 1
            )
            starts = [
                round(t * rate) for t in (0, 0.1, 0.4, 0.58, 0.7, 0.81, 1.0, 1.4, 1.8, 2.01, 2.5)
            ]
            arrays[case["name"]] = np.stack([audio[i : i + 512] for i in starts])
            rows.append(
                {
                    **case,
                    "starts": starts,
                    "window_frames": 512,
                    "frames": len(audio),
                    "peak": float(np.max(abs(audio))),
                    "rms": float(np.sqrt(np.mean(audio**2))),
                }
            )
    np.savez_compressed(root / "reference.npz", **arrays)
    metadata = {
        "upstream": "https://github.com/hraness/dawg",
        "revision": REVISION,
        "license": "MIT; src/tactus/_instruments/LICENSE.dawg",
        "reference_npz_sha256": hashlib.sha256((root / "reference.npz").read_bytes()).hexdigest(),
        "comparison": "Raw float64 before gain or fades; eleven 512-frame windows and full-buffer peak/RMS.",
        "cases": rows,
    }
    (root / "reference.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        "Generated",
        len(rows),
        "original-engine fixtures;",
        (root / "reference.npz").stat().st_size,
        "bytes",
    )


if __name__ == "__main__":
    main()
