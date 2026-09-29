"""Native FFT workers and packed Numba Q/projection candidates; no fastmath."""

import json
from pathlib import Path
from time import perf_counter

import numba
import numpy as np
import soundfile as sf
from numba import njit, prange
from scipy.fft import get_workers, set_workers
from scipy.signal import get_window

from tactus.analysis import _features, _qtransform, spectral


@njit(cache=True, parallel=True)
def correlate(x, real, imag, starts, hop):
    count = 1 + len(x) // hop
    result = np.empty((len(starts) - 1, count))
    for row in prange(len(starts) - 1):
        base = starts[row]
        size = starts[row + 1] - base
        for frame in range(count):
            start = frame * hop - size // 2
            re = 0.0
            im = 0.0
            for k in range(max(0, -start), min(size, len(x) - start)):
                re += x[start + k] * real[base + k]
                im += x[start + k] * imag[base + k]
            result[row, frame] = np.hypot(re, im)
    return result


def q(x, rate, gamma):
    freqs, sizes, _ = _qtransform.design(rate, 32.70319566257483, 84, 12, 1, gamma)
    starts = np.r_[0, np.cumsum(sizes)]
    real = np.empty(starts[-1])
    imag = np.empty_like(real)
    for i, (f, n) in enumerate(zip(freqs, sizes, strict=True)):
        window = get_window("hann", n)
        kernel = window * np.exp(-2j * np.pi * f * (np.arange(n) - n // 2) / rate)
        kernel *= 2 / window.sum()
        real[starts[i] : starts[i + 1]] = kernel.real
        imag[starts[i] : starts[i + 1]] = kernel.imag
    return correlate(x, real, imag, starts, 512)


@njit(cache=True)
def projection(data, indices, indptr, values):
    result = np.zeros((len(indptr) - 1, values.shape[1]))
    for row in range(len(indptr) - 1):
        for k in range(indptr[row], indptr[row + 1]):
            for frame in range(values.shape[1]):
                result[row, frame] += data[k] * values[indices[k], frame]
    return result


def timed(fn, repeats=3):
    values = []
    for _ in range(repeats):
        t = perf_counter()
        out = fn()
        values.append(perf_counter() - t)
    return out, float(np.median(values))


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    x, rate = sf.read("dogfood/2026-09-25-full-song-3/work/runs/c4/mix-32222836.wav")
    x = x.sum(axis=1)
    # Disable shipped auto acceleration to reproduce the original native baseline.
    _qtransform._JIT_MIN_WORK = float("inf")
    spectral._STFT_CHUNK_WORK = float("inf")
    spectral.fft_workers = _features.fft_workers = lambda work: get_workers()
    numba.set_num_threads(min(8, numba.get_num_threads()))
    _, first = timed(lambda: q(x[:rate], rate, 0), 1)
    report = {"first_jit_call_s": first, "cases": []}
    for seconds in (1, 20, len(x) / rate):
        audio = x[: int(seconds * rate)]
        for name in ("cqt", "vqt", "stft", "mel"):
            fn = getattr(spectral, name)
            key = (
                "magnitude" if name in ("cqt", "vqt") else "level_db" if name == "stft" else "power"
            )
            reference, baseline = timed(lambda fn=fn, audio=audio, key=key: fn(audio, rate)[key])
            case = {"name": name, "seconds": seconds, "native_s": baseline}
            if name in ("cqt", "vqt"):
                result, elapsed = timed(
                    lambda audio=audio, name=name: q(audio, rate, 0 if name == "cqt" else None)
                )
                np.testing.assert_allclose(result, reference, atol=2e-14, rtol=1e-10)
                case["numba8_s"] = elapsed
                case["max_error"] = float(np.max(np.abs(result - reference)))
            else:
                for workers in (2, 4, 8):
                    with set_workers(workers):
                        result, elapsed = timed(
                            lambda fn=fn, audio=audio, key=key: fn(audio, rate)[key]
                        )
                    np.testing.assert_array_equal(result, reference)
                    case[f"fft{workers}_s"] = elapsed
                if name == "mel":
                    original = _features.csr_matrix

                    class Project:
                        def __init__(self, weights, factory=original):
                            self.s = factory(weights)

                        def __matmul__(self, values):
                            return projection(self.s.data, self.s.indices, self.s.indptr, values)

                    _features.csr_matrix = Project
                    fn(audio[:rate], rate)  # compile outside warm measurement
                    result, elapsed = timed(
                        lambda fn=fn, audio=audio, key=key: fn(audio, rate)[key]
                    )
                    _features.csr_matrix = original
                    np.testing.assert_array_equal(result, reference)
                    case["numba_projection_s"] = elapsed
            report["cases"].append(case)
            print(json.dumps(case), flush=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
