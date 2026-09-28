"""Repeat the raw SFZ render, without any Tactus run/stage/effect processing."""

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus.inputs.pool import hash_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", type=Path, required=True)
    parser.add_argument("--sfz", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-identical", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location("song", args.song)
    song = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(song)
    events = []
    for section, note in song.BASS_NOTES:
        start, end = song.SECTION_T[section]
        while start < end - 0.5:
            events.extend([(start, "on", note, 58), (start + song.BAR_SEC * 1.8, "off", note, 0)])
            start += song.BAR_SEC * 2
    midi = args.out / "bass.mid"
    song.write_midi(midi, events)
    for index in range(2):
        command = [
            str(args.tool),
            "--sfz",
            str(args.sfz),
            "--midi",
            str(midi),
            "--wav",
            str(args.out / f"raw-{index}.wav"),
            "--samplerate",
            "44100",
            "--use-eot",
        ]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        (args.out / f"raw-{index}.log").write_text(proc.stdout + proc.stderr)
        proc.check_returncode()
    a, b = [sf.read(args.out / f"raw-{index}.wav")[0] for index in range(2)]
    result = {
        "identical": np.array_equal(a, b),
        "max_sample_difference": float(np.max(np.abs(a - b))),
        "sha256": [hash_file(args.out / f"raw-{index}.wav") for index in range(2)],
        "midi_sha256": hash_file(midi),
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if args.require_identical and not result["identical"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
