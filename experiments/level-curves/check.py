"""Validate native M/S/LRA against the EBU v05 audio files (stored outside Git).

uv run python experiments/level-curves/check.py --corpus DIR --archive ZIP --out JSON
The EBU files are for technical testing only. No generated or official audio is published.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
from importlib.metadata import version
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus import _biquad
from tactus.analysis import _level, level

ARCHIVE_SHA512 = (
    "60d022fdac47ad0be2688411be9daecbff85da994d6fa4921bba6cffab841b081d8b15d9c"
    "e284ad2253efb686463450a84a0d19cb0bad7a934546cc52dd73771"
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--integrated", action="store_true", help="Also check integrated LUFS cases 1-8"
    )
    args = parser.parse_args()
    archive_sha512 = hashlib.sha512(args.archive.read_bytes()).hexdigest()
    if archive_sha512 != ARCHIVE_SHA512:
        raise ValueError("Archive does not match the Gentoo Manifest for EBU v05")
    report = {
        "versions": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("numpy", "scipy", "soundfile")},
        },
        "source_sha256": {
            str(p): digest(p)
            for p in (
                Path(__file__),
                Path(inspect.getfile(_level)),
                Path(inspect.getfile(level)),
                Path(inspect.getfile(_biquad)),
            )
        },
        "archive_sha512": archive_sha512,
        "archive_sha256": digest(args.archive),
        "archive_origin": "https://tech.ebu.ch/publications/ebu_loudness_test_set",
        "download_mirror": "https://mirrors.mit.edu/gentoo-distfiles/distfiles/de/ebu-loudness-test-setv05.zip",
        "checksum_source": "https://github.com/gentoo/gentoo/blob/master/media-libs/libebur128/Manifest",
        "scope": "M/S/LRA and optional integrated cases 1-8; not full EBU meter certification.",
        "integrated": args.integrated,
        "inputs": {},
        "checks": [],
    }

    def read(pattern):
        paths = list(args.corpus.glob(pattern))
        if len(paths) != 1:
            raise ValueError(f"Expected exactly one file for {pattern}: {paths}")
        p = paths[0]
        x, sr = sf.read(p)
        report["inputs"][p.name] = {"sha256": digest(p), "rate": sr, "frames": len(x)}
        return x, sr, p.name

    def check(name, file, values, expected, tolerance, extra=None):
        v = np.asarray(values, dtype=float)
        error = float(np.max(np.abs(v - expected))) if v.size else None
        passed = bool(v.size and np.isfinite(v).all() and error <= tolerance)
        report["checks"].append(
            {
                "name": name,
                "file": file,
                "expected": expected,
                "tolerance": tolerance,
                "observed_min": float(np.min(v)) if v.size else None,
                "observed_max": float(np.max(v)) if v.size else None,
                "maximum_error": error,
                "passed": passed,
                **(extra or {}),
            }
        )

    if args.integrated:
        patterns = [f"seq-3341-{i}-*.wav*" for i in range(1, 6)] + [
            "seq-3341-6-5channels-16bit.wav",
            "seq-3341-7_seq-3342-5-24bit.wav",
            "seq-3341-2011-8_seq-3342-6-24bit-v02.wav",
        ]
        for i, pattern in enumerate(patterns, 1):
            x, sr, filename = read(pattern)
            expected = -33 if i == 2 else -23
            check(
                f"3341-{i}/integrated",
                filename,
                [level.loudness(x, sr)["integrated_lufs"]],
                expected,
                0.1,
            )

    # Static calibration and five-channel weighting.
    for num, expected in [(1, -23), (2, -33), (6, -23)]:
        pattern = f"seq-3341-{num}-16bit.wav" if num != 6 else "seq-3341-6-5channels-16bit.wav"
        x, sr, filename = read(pattern)
        for fn in (level.momentary_loudness, level.short_term_loudness):
            check(f"3341-{num}/{fn.__name__}", filename, fn(x, sr)["loudness_lufs"], expected, 0.1)

    # Alternating levels with a constant expected windowed loudness.
    for num, fn, start in [(9, level.short_term_loudness, 3), (12, level.momentary_loudness, 1)]:
        x, sr, filename = read(f"seq-3341-{num}-24bit.wav")
        curve = fn(x, sr)
        values = np.array(curve["loudness_lufs"])[np.array(curve["times_s"]) >= start]
        check(f"3341-{num}/constant", filename, values, -23, 0.1)

    # Separate offset files: each peak must be captured by the default grid.
    for num, fn in [(10, level.short_term_loudness), (13, level.momentary_loudness)]:
        for offset in range(1, 21):
            x, sr, filename = read(f"seq-3341-{num}-{offset}-24bit.wav*")
            finite = [v for v in fn(x, sr)["loudness_lufs"] if v is not None]
            check(f"3341-{num}-{offset}/maximum", filename, [max(finite)], -23, 0.1)

    # The "live" fixtures are evaluated offline; check each successive level plateau.
    for num, fn, period in [
        (11, level.short_term_loudness, 6),
        (14, level.momentary_loudness, 0.8),
    ]:
        x, sr, filename = read(f"seq-3341-{num}-24bit.wav*")
        curve = fn(x, sr)
        t = np.array(curve["times_s"])
        v = np.array([float("-inf") if val is None else val for val in curve["loudness_lufs"]])
        for i in range(20):
            values = v[(t > i * period) & (t <= (i + 1) * period + 1e-9)]
            check(f"3341-{num}/segment-{i + 1}", filename, [max(values)], -38 + i, 0.1)

    patterns = [f"seq-3342-{i}-16bit.wav" for i in range(1, 5)] + [
        "seq-3341-7_seq-3342-5-24bit.wav",
        "seq-3341-2011-8_seq-3342-6-24bit-v02.wav",
    ]
    for i, (pattern, expected) in enumerate(zip(patterns, [10, 5, 20, 15, 5, 15]), 1):
        x, sr, filename = read(pattern)
        result = level.loudness_range(x, sr)
        check(f"3342-{i}/LRA", filename, [result["lra_lu"]], expected, 1, {"result": result})

    report["passed"] = sum(c["passed"] for c in report["checks"])
    report["total"] = len(report["checks"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "total": report["total"],
                "failures": [c for c in report["checks"] if not c["passed"]],
            },
            indent=2,
        )
    )
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
