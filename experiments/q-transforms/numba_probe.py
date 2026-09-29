"""Optional Numba comparison; run with uv run --with numba this-file.

The normal Q implementation uses SciPy. This experiment measures exact real/imag
accumulation and explicitly reports first-call compilation separately from warm work.
"""

import json
from pathlib import Path
from time import perf_counter

import numba
import numpy as np
from numba import njit, prange
from scipy.signal import get_window

from tactus.analysis import spectral
from tactus.analysis._qtransform import design


@njit(cache=True, parallel=True)
def correlations(x, real, imag, sizes, hop):
    count = 1 + len(x) // hop
    result = np.empty((len(sizes), count))
    for row in prange(len(sizes)):
        size = sizes[row]
        for frame in range(count):
            start = frame * hop - size // 2
            lower = max(0, -start)
            upper = min(size, len(x) - start)
            re = 0.0
            im = 0.0
            for k in range(lower, upper):
                sample = x[start + k]
                re += sample * real[row, k]
                im += sample * imag[row, k]
            result[row, frame] = np.hypot(re, im)
    return result


def prepared(x, rate):
    frequencies, sizes, _ = design(rate, 32.70319566257483, 84, 12, 1, 0)
    real = np.zeros((len(sizes), sizes.max()))
    imag = np.zeros_like(real)
    for row, (frequency, size) in enumerate(zip(frequencies, sizes, strict=True)):
        window = get_window("hann", size)
        phase = 2 * np.pi * frequency * (np.arange(size) - size // 2) / rate
        real[row, :size] = 2 * window * np.cos(phase) / window.sum()
        imag[row, :size] = -2 * window * np.sin(phase) / window.sum()
    return correlations(x, real, imag, sizes, 512)


def timed(fn):
    start = perf_counter()
    value = fn()
    return value, perf_counter() - start


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rate = 22050
    rng = np.random.default_rng(37)
    numba.set_num_threads(4)
    x = rng.normal(size=rate)
    _, first = timed(lambda x=x: prepared(x, rate))
    report = {
        "numba": numba.__version__,
        "threads": 4,
        "fastmath": False,
        "first_call_1s_including_compile_or_cache_s": first,
        "cases": [],
    }
    for seconds in (1, 30):
        x = rng.normal(size=rate * seconds)
        reference = spectral.cqt(x, rate)["magnitude"]
        case = {"duration_s": seconds, "sample_rate": rate}
        for name, fn in (
            ("scipy", lambda x=x: spectral.cqt(x, rate)["magnitude"]),
            ("numba", lambda x=x: prepared(x, rate)),
        ):
            trials = []
            for _ in range(3):
                values, elapsed = timed(fn)
                trials.append(elapsed)
            np.testing.assert_allclose(values, reference, rtol=1e-11, atol=2e-14)
            case[name + "_median_s"] = float(np.median(trials))
            case[name + "_max_error"] = float(np.max(np.abs(values - reference)))
        report["cases"].append(case)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
