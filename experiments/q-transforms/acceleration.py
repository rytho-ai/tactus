"""Same-definition CQT acceleration probe: NumPy, FIR, FFT and Numba JIT.

uv run --with numba experiments/q-transforms/acceleration.py --out REPORT.json
No fastmath, reduced precision, resampling or sparse frequency approximation.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import numba
import numpy as np
from numba_probe import prepared
from scipy.signal import get_window, oaconvolve, upfirdn

from tactus.analysis import spectral
from tactus.analysis._qtransform import design


def alternative(x, rate, method):
    frequencies, sizes, _ = design(rate, 32.70319566257483, 84, 12, 1, 0)
    count = 1 + len(x) // 512
    out = np.empty((84, count))
    for row, (frequency, size) in enumerate(zip(frequencies, sizes, strict=True)):
        offsets = np.arange(size) - size // 2
        window = get_window("hann", size)
        kernel = window * np.exp(-2j * np.pi * frequency * offsets / rate) * (2 / window.sum())
        offset = size - 1 - size // 2
        if method == "fft":
            values = oaconvolve(x, kernel[::-1])
            out[row] = np.abs(values[offset : offset + count * 512 : 512])
        elif method == "complex_fir":
            prefix = int(-offset % 512)
            first = (offset + prefix) // 512
            values = upfirdn(kernel[::-1], np.pad(x, (prefix, 512)), down=512)
            out[row] = np.abs(values[first : first + count])
        else:
            signal = np.pad(x, (size // 2, size))
            frames = np.lib.stride_tricks.sliding_window_view(signal, size)[::512][:count]
            # Bounded direct sums; no Python loop over individual output frames.
            block = max(1, (1 << 19) // size)
            for first in range(0, count, block):
                out[row, first : first + block] = np.abs(
                    np.einsum("ij,j->i", frames[first : first + block], kernel, optimize=False)
                )
    return out


def timed(fn, trials=3):
    timings = []
    for _ in range(trials):
        start = perf_counter()
        value = fn()
        timings.append(perf_counter() - start)
    return value, float(np.median(timings))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rate = 22050
    report = {
        "numba": numba.__version__,
        "numpy": np.__version__,
        "fastmath": False,
        "precision": "float64",
        "trials": 3,
        "cases": [],
    }
    # Deliberately separate thread parallelism from JIT itself.
    numba.set_num_threads(1)
    prepared(np.zeros(rate), rate)
    for seconds in (1, 30):
        x = np.random.default_rng(37).normal(size=rate * seconds)
        reference = spectral.cqt(x, rate)["magnitude"]
        methods = {"scipy_real_fir": lambda x=x: spectral.cqt(x, rate)["magnitude"]}
        for method in ("numpy", "complex_fir", "fft"):
            methods[method] = lambda method=method, x=x: alternative(x, rate, method)
        for threads in (1, 4, 8):

            def jit(threads=threads, x=x):
                numba.set_num_threads(threads)
                return prepared(x, rate)

            methods[f"numba_{threads}_threads"] = jit
        case = {"audio_s": seconds, "rate": rate, "methods": {}}
        for method, fn in methods.items():
            values, elapsed = timed(fn)
            np.testing.assert_allclose(values, reference, rtol=1e-10, atol=2e-14)
            case["methods"][method] = {
                "median_s": elapsed,
                "max_error": float(np.max(np.abs(values - reference))),
            }
        report["cases"].append(case)
    # Fresh processes include import, planning/allocation and compilation/cache loads.
    root = Path(__file__).resolve().parent
    base = args.out.parent / "jit-process-cache"
    report["fresh_processes"] = []
    for seconds in (1, 30):
        for engine in ("scipy", "numba"):
            code = f"import sys;sys.path.insert(0,{str(root)!r});import numpy as np;x=np.random.default_rng(37).normal(size=22050*{seconds});"
            code += (
                "from tactus.analysis import spectral;spectral.cqt(x,22050)"
                if engine == "scipy"
                else "from numba_probe import prepared;import numba;numba.set_num_threads(4);prepared(x,22050)"
            )
            # Each duration receives a fresh cache; first includes JIT compilation.
            cache = base / f"{seconds}s-{engine}"
            cache.mkdir(parents=True, exist_ok=False)
            env = {**os.environ, "NUMBA_CACHE_DIR": str(cache.resolve())}

            def process(code=code, env=env):
                subprocess.run(
                    [sys.executable, "-c", code], check=True, capture_output=True, env=env
                )

            _, first = timed(process, trials=1)
            _, cached = timed(process)
            report["fresh_processes"].append(
                {
                    "audio_s": seconds,
                    "engine": engine,
                    "first_process_s": first,
                    "cached_process_median_s": cached,
                }
            )
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
