"""Repeat native SFZ synthesis with optional CPU affinity; retain every result hash."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--sfz", type=Path, required=True)
    parser.add_argument("--midi", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--require-identical", action="store_true")
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.cpu is not None:
        os.sched_setaffinity(0, {args.cpu})
    result = []
    reference = sf.read(args.reference, dtype="float32")[0] if args.reference else None
    for index in range(args.runs):
        path = args.out / f"{index}.wav"
        command = [
            str(args.tool),
            "--sfz",
            str(args.sfz),
            "--midi",
            str(args.midi),
            "--wav",
            str(path),
            "--samplerate",
            "44100",
            "--use-eot",
        ]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        (args.out / f"{index}.log").write_text(proc.stdout + proc.stderr)
        proc.check_returncode()
        audio, rate = sf.read(path, dtype="float32")
        if reference is None:
            reference = audio
        entry = {
            "run": index,
            "sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
            "max_difference_from_first": float(np.max(np.abs(audio - reference))),
            "sample_rate": rate,
            "frames": len(audio),
        }
        result.append(entry)
        print(json.dumps(entry), flush=True)
    report = {"runs": result, "unique_outputs": len({r["sha256"] for r in result}), "cpu": args.cpu}
    report["matches_reference"] = all(r["max_difference_from_first"] == 0 for r in result)
    (args.out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.require_identical and (
        report["unique_outputs"] != 1 or not report["matches_reference"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
