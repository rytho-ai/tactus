"""Run all four real CLI commands, checking numeric arrays, images and hashes."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus.analysis import image, spectral


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    audio, rate = sf.read(args.audio)
    report = []
    for name in ("cqt", "vqt", "stft", "mel"):
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "tactus.cli",
                "analyze",
                "spectral",
                name,
                str(args.audio),
                "--out",
                str(args.out / name),
                "--image",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        (args.out / f"{name}.json").write_text(run.stdout)
        record = json.loads(run.stdout)
        direct = getattr(spectral, name)(audio, rate)
        for key, value in direct.items():
            if isinstance(value, np.ndarray):
                ref = record["result"][key]
                with np.load(ref["file"]) as arrays:
                    np.testing.assert_array_equal(arrays[ref["key"]], value)
        path = next((args.out / name).rglob("image.svg"))
        assert path.read_text() == image(direct, title=f"spectral.{name}")
        for file, artifact in record["artifacts"].items():
            assert (
                hashlib.sha256((path.parent / file).read_bytes()).hexdigest() == artifact["sha256"]
            )
        report.append(
            {
                "analysis": name,
                "arrays_equal": True,
                "image_equal": True,
                "artifact_hashes_verified": True,
            }
        )
    (args.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
