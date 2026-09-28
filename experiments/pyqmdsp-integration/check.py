"""Check Tactus CLI/package parity and the 72-file Vamp beat-score gate.

Reads: external audio, truth/reference from the pinned pyqmdsp checkout, installed Tactus.
Writes: a numeric JSON report; no audio is copied into the repository.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import mir_eval
import numpy as np
import pyqmdsp
import soundfile as sf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_root", type=Path)
    parser.add_argument("reference_root", type=Path, help="pyqmdsp/verification/beats directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audio = {p.stem: p for p in args.audio_root.rglob("*.wav")}
    truths = sorted((args.reference_root / "truth").glob("*.json"))
    if len(truths) != 72:
        parser.error(f"expected 72 truth files, found {len(truths)}")
    paths = [audio[p.stem] for p in truths]
    cli = subprocess.run(
        [sys.executable, "-m", "tactus.cli", "analyze", "rhythm", "beats", *map(str, paths)],
        check=True,
        capture_output=True,
        text=True,
    )
    reports = [json.loads(line) for line in cli.stdout.splitlines()]
    assert len(reports) == 72
    rows = []
    for truth_path, wav, report in zip(truths, paths, reports, strict=True):
        truth = json.loads(truth_path.read_text())
        reference = json.loads((args.reference_root / "reference" / truth_path.name).read_text())
        samples, rate = sf.read(wav, dtype="float64")
        expected = pyqmdsp.beats(samples, rate)
        actual = report["result"]
        assert report["analysis"] == "rhythm.beats" and report["revision"] == 1
        assert report["path"] == str(wav) and report["sample_rate"] == rate
        exact = (
            np.array_equal(actual["beats_s"], expected["beats_s"])
            and np.array_equal(actual["tempo_curve"], expected["tempo_curve"])
            and actual["bpm"] == (expected["bpm"] if len(expected["beats_s"]) >= 2 else None)
        )

        def score(events, truth_beats=truth["beats"]):
            return float(
                mir_eval.beat.f_measure(
                    np.asarray(truth_beats),
                    np.asarray(events),
                    f_measure_threshold=0.07,
                )
            )

        ref_f, actual_f = score(reference["beats"]), score(actual["beats_s"])
        rows.append(
            {
                "file": wav.stem,
                "audio_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                "package_exact": bool(exact),
                "reference_f": ref_f,
                "actual_f": actual_f,
                "delta": actual_f - ref_f,
                "beat_count": len(actual["beats_s"]),
                "bpm": actual["bpm"],
            }
        )
    ref_mean = float(np.mean([r["reference_f"] for r in rows]))
    actual_mean = float(np.mean([r["actual_f"] for r in rows]))
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pyqmdsp_source": json.loads(distribution("pyqmdsp").read_text("direct_url.json")),
        "engine": pyqmdsp.engine_info(),
        "files": len(rows),
        "package_exact_files": sum(r["package_exact"] for r in rows),
        "reference_mean_f": ref_mean,
        "actual_mean_f": actual_mean,
        "absolute_mean_difference": abs(actual_mean - ref_mean),
        "passed": all(r["package_exact"] for r in rows) and abs(actual_mean - ref_mean) <= 0.005,
        "results": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    for row in rows:
        if abs(row["delta"]) > 1e-12:
            print(row["file"], row["delta"])
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
