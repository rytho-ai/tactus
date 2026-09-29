"""Reproduce Q timing, optional Numba process costs and actual CLI image artifacts.

uv run experiments/q-transforms/check.py AUDIO --out NEW_DIRECTORY
Runtime computations and CLI need no reference packages. Numba process checks run
only when it is installed. Large audio/artifacts belong under ignored dogfood/.
"""

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import soundfile as sf
from scipy.signal import get_window, upfirdn

from tactus.analysis import rhythm, spectral
from tactus.analysis._qtransform import design
from tactus.inputs.pool import hash_file


def complex_baseline(x, rate):
    frequencies, sizes, _ = design(rate, 32.70319566257483, 84, 12, 1, 0)
    count = 1 + len(x) // 512
    out = np.empty((84, count))
    for row, (frequency, size) in enumerate(zip(frequencies, sizes, strict=True)):
        offsets = np.arange(size) - size // 2
        window = get_window("hann", size)
        kernel = window * np.exp(-2j * np.pi * frequency * offsets / rate) * (2 / window.sum())
        offset = size - 1 - size // 2
        prefix = int(-offset % 512)
        first = (offset + prefix) // 512
        values = upfirdn(kernel[::-1], np.pad(x, (prefix, 512)), down=512)
        out[row] = np.abs(values[first : first + count])
    return out


def timed(fn, trials=3):
    elapsed = []
    for _ in range(trials):
        start = perf_counter()
        value = fn()
        elapsed.append(perf_counter() - start)
    return value, float(np.median(elapsed))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    x, rate = sf.read(args.audio, dtype="float64")
    report = {
        "input": str(args.audio),
        "sha256": hash_file(args.audio),
        "duration_s": len(x) / rate,
        "rate": rate,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "method": "3 warm trials; medians; timing assertions deliberately absent",
    }
    # Same input and exact filter definition, only convolution arithmetic changes.
    short = x[: 5 * rate]
    mono = short.sum(axis=1) if short.ndim == 2 else short
    old, old_s = timed(lambda: complex_baseline(mono, rate))
    new, new_s = timed(lambda: spectral.cqt(mono, rate)["magnitude"])
    np.testing.assert_allclose(new, old, rtol=1e-10, atol=2e-14)
    report["same_definition_cqt_5s"] = {
        "complex_s": old_s,
        "split_real_s": new_s,
        "speedup": old_s / new_s,
        "max_error": float(np.max(np.abs(new - old))),
    }
    report["full_music_s"] = {}
    for fn in (spectral.cqt, spectral.vqt, rhythm.tempogram):
        _, elapsed = timed(lambda fn=fn: fn(x, rate))
        report["full_music_s"][fn.__name__] = elapsed
        print(fn.__name__, elapsed, flush=True)
    clip = x[36 * rate : 56 * rate] if len(x) >= 56 * rate else x
    source = args.out / "excerpt.wav"
    sf.write(source, clip, rate, subtype="DOUBLE")
    report["cli"] = []
    for category, name in (("spectral", "cqt"), ("spectral", "vqt"), ("rhythm", "tempogram")):
        directory = args.out / name
        command = [
            "uv",
            "run",
            "tactus",
            "analyze",
            category,
            name,
            str(source),
            "--out",
            str(directory),
            "--image",
        ]
        start = perf_counter()
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        elapsed = perf_counter() - start
        record = json.loads(completed.stdout)
        (args.out / f"{name}-stdout.json").write_text(completed.stdout)
        artifact_dir = next(directory.iterdir())
        assert json.loads((artifact_dir / "result.json").read_text()) == record
        for filename, metadata in record["artifacts"].items():
            assert hash_file(artifact_dir / filename) == metadata["sha256"]
        result = getattr(spectral if category == "spectral" else rhythm, name)(clip, rate)
        for key, value in result.items():
            if isinstance(value, np.ndarray):
                ref = record["result"][key]
                with np.load(ref["file"]) as arrays:
                    np.testing.assert_array_equal(arrays[ref["key"]], value)
        report["cli"].append(
            {
                "analysis": record["analysis"],
                "elapsed_s": elapsed,
                "verified_numeric_and_hashes": True,
                "image": str(artifact_dir / "image.svg"),
            }
        )
    report["reference_packages"] = {
        name: importlib.util.find_spec(name) is not None
        for name in ("librosa", "pyloudnorm", "numba")
    }
    if report["reference_packages"]["numba"]:
        cases = []
        probe = str(Path(__file__).with_name("numba_probe.py").resolve())
        for seconds in (1, 30):
            for engine in ("scipy", "numba"):
                code = "import numpy as np; from tactus.analysis import spectral; "
                code += f"x=np.random.default_rng(7).normal(size=22050*{seconds}); "
                if engine == "numba":
                    code += f"import runpy; p=runpy.run_path({probe!r}); p['numba'].set_num_threads(4); p['prepared'](x,22050)"
                else:
                    code += "spectral.cqt(x,22050)"

                def process(code=code):
                    subprocess.run(
                        [sys.executable, "-c", code],
                        check=True,
                        capture_output=True,
                        env={
                            **os.environ,
                            "NUMBA_CACHE_DIR": str(
                                Path("dogfood/2026-09-29-q-transforms/numba-cache").resolve()
                            ),
                        },
                    )

                _, elapsed = timed(process)
                cases.append(
                    {"engine": engine, "audio_s": seconds, "cached_fresh_process_median_s": elapsed}
                )
        report["numba_processes"] = cases
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
