"""Full-recording SciPy/Numba comparison, including fresh-process startup."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import numba
import numpy as np
import soundfile as sf
from numba_probe import prepared

from tactus.analysis import spectral


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    audio, rate = sf.read(args.audio)
    x = audio.sum(axis=1) if audio.ndim == 2 else audio
    result = {
        "input": str(args.audio),
        "duration_s": len(x) / rate,
        "rate": rate,
        "trials": 3,
        "warm": {},
    }
    reference = spectral.cqt(x, rate)["magnitude"]
    for engine, threads in (("scipy", 1), ("numba", 1), ("numba", 4), ("numba", 8)):
        numba.set_num_threads(threads)
        fn = (
            (lambda: spectral.cqt(x, rate)["magnitude"])
            if engine == "scipy"
            else lambda: prepared(x, rate)
        )
        fn()
        elapsed = []
        for _ in range(3):
            start = perf_counter()
            value = fn()
            elapsed.append(perf_counter() - start)
        np.testing.assert_allclose(value, reference, rtol=1e-10, atol=2e-14)
        result["warm"][f"{engine}_{threads}_threads"] = {
            "median_s": float(np.median(elapsed)),
            "max_error": float(np.max(np.abs(value - reference))),
        }
    result["fresh"] = []
    root = str(Path(__file__).resolve().parent)
    for engine in ("scipy", "numba"):
        code = f"import sys;sys.path.insert(0,{root!r});import soundfile as sf;a,r=sf.read({str(args.audio.resolve())!r});x=a.sum(axis=1) if a.ndim==2 else a;"
        code += (
            "from tactus.analysis import spectral;spectral.cqt(x,r)"
            if engine == "scipy"
            else "from numba_probe import prepared;import numba;numba.set_num_threads(8);prepared(x,r)"
        )
        cache = args.out.parent / f"full-cache-{engine}"
        cache.mkdir(exist_ok=False)
        times = []
        for _ in range(3):
            start = perf_counter()
            subprocess.run(
                [sys.executable, "-c", code],
                check=True,
                capture_output=True,
                env={**os.environ, "NUMBA_CACHE_DIR": str(cache.resolve())},
            )
            times.append(perf_counter() - start)
        result["fresh"].append(
            {
                "engine": engine,
                "threads": 8 if engine == "numba" else 1,
                "first_s": times[0],
                "cached_median_s": float(np.median(times[1:])),
            }
        )
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
