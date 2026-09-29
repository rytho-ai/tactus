"""Check preserved Mel, log triangles, independent dense log and annotated onset results.

Requires the SHA-pinned upstream SuperFlux.py supplied with --reference (no runtime import).
See README for retrieval and corpus reconstruction. All audio stays outside Git.
"""

import argparse
import hashlib
import importlib.util
import inspect
import json
import statistics
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.fft import rfft

from tactus.analysis import _features, _onset, rhythm

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dense_projection(x, n_fft, hop, weights, *, power):
    # Same framing and precision as the optimized path, full matrix and dense weights.
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (n_fft // 2, n_fft // 2)), n_fft)[
        ::hop
    ]
    from scipy.signal import get_window

    magnitude = abs(rfft(frames * get_window("hann", n_fft), axis=1))
    if power:
        magnitude **= 2
    return np.einsum("mf,ft->mt", weights, magnitude.T, optimize=True)


def vibrato_observation():
    """One sustained FM tone: suppression of envelope motion is not perfect onset accuracy."""
    rate = 44100
    t = np.arange(rate * 3) / rate
    frequency = 440 + 20 * np.sin(2 * np.pi * 5 * t)
    x = 0.3 * np.sin(2 * np.pi * np.cumsum(frequency) / rate)
    x *= np.minimum(t / 0.02, 1) * np.minimum((3 - t) / 0.02, 1)
    result = {}
    for bank in ["mel", "log"]:
        result[bank] = {}
        for width in [1, 3]:
            strength = rhythm.onset_strength(x, rate, filterbank=bank, max_size=width)
            times = np.asarray(strength["times_s"])
            mean = np.mean(np.asarray(strength["strength"])[(times > 0.5) & (times < 2.5)])
            events = rhythm.onsets(x, rate, filterbank=bank, max_size=width)["onsets_s"]
            result[bank][str(width)] = {"steady_mean_strength": float(mean), "events_s": events}
        assert result[bank]["3"]["steady_mean_strength"] < result[bank]["1"]["steady_mean_strength"]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--audio", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    pinned = json.loads(Path(__file__).with_name("reference-source.json").read_text())
    source = a.reference.read_bytes()
    assert hashlib.sha256(source).hexdigest() == pinned["sha256"]
    # Execute only the original Filter class. Its sole compatibility edit replaces
    # the removed np.float alias with builtin float; formulas stay verbatim.
    code = source.decode().split("class Filter(object):", 1)[1].split("class Wav(object):", 1)[0]
    namespace = {"np": np}
    exec("class Filter(object):" + code.replace("np.float", "float"), namespace)  # noqa: S102 -- SHA-pinned reference class only
    Filter = namespace["Filter"]
    filter_checks = []
    for rate in [8000, 22050, 44100, 48000]:
        for n_fft in [1024, 2048, 4096]:
            for bands in [12, 24, 36]:
                upper = min(16000, rate / 2)
                original = Filter(n_fft // 2, rate, bands=bands, fmin=27.5, fmax=upper).filterbank.T
                # Tactus excludes any rounded center outside the requested bounds.
                centers = np.argmax(original, axis=1) * rate / n_fft
                original = original[(centers >= 27.5) & (centers <= upper)]
                original = np.pad(original, ((0, 0), (0, 1)))
                got = _features.log_frequency_weights(rate, n_fft, bands, 27.5, upper)
                np.testing.assert_array_equal(got, original)
                filter_checks.append(
                    {"rate": rate, "n_fft": n_fft, "bands_per_octave": bands, "count": len(got)}
                )
    ref = load_module("migration_reference", ROOT / "experiments/owned-analysis/check.py")
    score = load_module("onset_scoring", ROOT / "experiments/librosa-analysis/check.py")
    dense = load_module("dense_log_reference", ROOT / "tests/test_superflux_frontends.py").dense_log
    report = {
        "upstream": pinned,
        "original_filter_checks": filter_checks,
        "parity": [],
        "loops": {},
        "log_projection_benchmark": {},
    }
    corpus = json.loads((a.corpus / "truth_manifest.json").read_text())
    paths = [a.audio, *[a.corpus / "loops" / name for name in corpus]]
    for path in paths:
        x, rate = sf.read(path)
        expected = ref.reference(x, rate, "onset_strength")
        got = np.asarray(rhythm.onset_strength(x, rate)["strength"])
        np.testing.assert_allclose(got, expected, atol=1e-10, rtol=1e-10)
        for name, kw in [("onsets", {}), ("onsets_backtracked", {"backtrack": True})]:
            np.testing.assert_array_equal(
                rhythm.onsets(x, rate, **kw)["onsets_s"], ref.reference(x, rate, name)
            )
        log_expected = dense(x, rate)
        log_actual = np.asarray(rhythm.onset_strength(x, rate, filterbank="log")["strength"])
        np.testing.assert_allclose(log_actual, log_expected, atol=1e-10, rtol=1e-10)
        report["parity"].append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mel_max_error": float(abs(got - expected).max()),
                "log_max_error": float(abs(log_actual - log_expected).max()),
            }
        )
        if path.name in corpus:
            truth = np.array(corpus[path.name]["truth_frames"]) / rate
            results = {}
            for variant in ["mel", "log"]:
                for backtrack in [False, True]:
                    label = variant + ("_backtracked" if backtrack else "")
                    events = rhythm.onsets(x, rate, filterbank=variant, backtrack=backtrack)[
                        "onsets_s"
                    ]
                    results[label] = {
                        "events_s": events,
                        "scores": {
                            str(ms): score.metrics(truth, events, ms / 1000)
                            for ms in [2, 10, 25, 50]
                        },
                    }
            report["loops"][path.name] = results
    report["vibrato_observation"] = vibrato_observation()
    report["macro_f1"] = {
        name: {
            str(ms): float(
                np.mean([r[name]["scores"][str(ms)]["f1"] for r in report["loops"].values()])
            )
            for ms in [2, 10, 25, 50]
        }
        for name in ["mel", "mel_backtracked", "log", "log_backtracked"]
    }
    x, rate = sf.read(a.audio)
    projection = _features._project_bands
    for label, audio in [("short", x[: rate * 5]), ("full", x)]:
        timings = {}
        values = {}
        # Alternate implementations so one does not always receive the warm machine.
        for i in range(8):
            for mode in ["dense", "sparse"] if i % 2 else ["sparse", "dense"]:
                _features._project_bands = dense_projection if mode == "dense" else projection
                t = time.perf_counter()
                values[mode] = rhythm.onsets(audio, rate, filterbank="log")
                elapsed = time.perf_counter() - t
                if i:
                    timings.setdefault(mode, []).append(elapsed)
        assert values["dense"] == values["sparse"]
        report["log_projection_benchmark"][label] = {
            "seconds": timings,
            "medians": {k: statistics.median(v) for k, v in timings.items()},
        }
    _features._project_bands = projection
    report["sources"] = {
        str(Path(inspect.getfile(m)).relative_to(ROOT)): hashlib.sha256(
            Path(inspect.getfile(m)).read_bytes()
        ).hexdigest()
        for m in [_features, _onset, rhythm]
    }
    a.out.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "filter_checks": len(filter_checks),
                "files": len(paths),
                "macro_f1": report["macro_f1"],
                "log_projection_benchmark": {
                    k: v["medians"] for k, v in report["log_projection_benchmark"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
