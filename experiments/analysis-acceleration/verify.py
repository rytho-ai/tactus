"""Measure shipped analysis paths in isolated processes, with fresh JIT caches.

uv run experiments/analysis-acceleration/verify.py AUDIO --out OUTPUT_DIRECTORY
Each worker includes package imports and audio decoding in parent wall time.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter


def worker(args):
    import numpy as np
    import soundfile as sf

    from tactus.analysis import _features, _qtransform, spectral

    audio, rate = sf.read(args.audio)
    audio = audio[: int(args.seconds * rate)]
    if args.backend == "native":
        _qtransform._JIT_MIN_WORK = float("inf")
        spectral._STFT_CHUNK_WORK = float("inf")
        _features.fft_workers = spectral.fft_workers = lambda work: 1
    fn = getattr(spectral, args.name)
    key = {"cqt": "magnitude", "vqt": "magnitude", "mel": "power", "stft": "level_db"}[args.name]
    t = perf_counter()
    result = fn(audio, rate)
    first = perf_counter() - t
    samples = []
    for _ in range(args.repeats):
        t = perf_counter()
        result = fn(audio, rate)
        samples.append(perf_counter() - t)
    np.save(args.out / f"{args.name}-{args.seconds}-{args.backend}.npy", result[key])
    print(
        json.dumps(
            {
                "first_call_s": first,
                "warm_median_s": float(np.median(samples)) if samples else None,
                "warm_total_s": sum(samples),
                "numba_loaded": "numba" in sys.modules,
                "shape": list(result[key].shape),
            }
        )
    )


def main(args):
    import numpy as np

    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
        "cases": [],
    }
    for seconds in (1, 149):
        for name in ("cqt", "vqt", "stft", "mel"):
            case = {"name": name, "seconds": seconds}
            with tempfile.TemporaryDirectory(prefix="tactus-analysis-jit-") as cache:
                for phase, backend in (("native", "native"), ("first", "auto"), ("cached", "auto")):
                    command = [
                        sys.executable,
                        __file__,
                        str(args.audio),
                        "--worker",
                        "--name",
                        name,
                        "--seconds",
                        str(seconds),
                        "--backend",
                        backend,
                        "--out",
                        str(args.out),
                        "--repeats",
                        "3" if phase != "cached" else "0",
                    ]
                    start = perf_counter()
                    run = subprocess.run(
                        command,
                        env={**os.environ, "NUMBA_CACHE_DIR": cache},
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    data = json.loads(run.stdout)
                    data["process_s"] = perf_counter() - start
                    data["startup_process_estimate_s"] = data["process_s"] - data["warm_total_s"]
                    case[phase] = data
                before = np.load(args.out / f"{name}-{float(seconds)}-native.npy")
                after = np.load(args.out / f"{name}-{float(seconds)}-auto.npy")
                np.testing.assert_allclose(after, before, rtol=1e-10, atol=2e-14)
                case["array_equal"] = bool(np.array_equal(after, before))
                case["max_absolute_error"] = float(np.max(np.abs(after - before)))
            report["cases"].append(case)
            print(json.dumps(case), flush=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--backend", choices=["native", "auto"])
    parser.add_argument("--name")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--repeats", type=int, default=0)
    args = parser.parse_args()
    worker(args) if args.worker else main(args)
