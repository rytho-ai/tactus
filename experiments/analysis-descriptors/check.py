"""Check descriptors on real audio and known transformations, including actual CLI.

uv run python experiments/analysis-descriptors/check.py --audio FILE --work NEW_DIR --out REPORT
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from tactus import dsp
from tactus.analysis import _features, level, spectral

FUNCTIONS = [
    ("level", level.crest_factor, "crest_factor_db"),
    ("level", level.crest_factor_curve, "crest_factor_db"),
    ("spectral", spectral.bandwidth, "bandwidth_hz"),
    ("spectral", spectral.rolloff, "rolloff_hz"),
    ("spectral", spectral.flatness, "flatness"),
]


def summary(value):
    if isinstance(value, list):
        values = np.array([x for x in value if x is not None])
        return {
            "count": len(value),
            "nulls": len(value) - len(values),
            "median": float(np.median(values)) if len(values) else None,
        }
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    x, rate = sf.read(args.audio)
    lowpass, _ = dsp.biquad(x, rate, kind="lowpass", frequency_hz=1500)
    ceiling = float(np.max(np.abs(x)) / 3)
    variants = {
        "original": x,
        "gain_minus_24db": dsp.gain(x, -24),
        "lowpass_1500": lowpass,
        "clipped": np.clip(x, -ceiling, ceiling),
    }
    report = {
        "input": {
            "path": str(args.audio),
            "sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
            "sample_rate": rate,
            "frames": len(x),
        },
        "clip_ceiling": ceiling,
        "variants": {},
        "reference": {},
        "cli": [],
    }
    original = {}
    for variant, audio in variants.items():
        record = {}
        for category, fn, field in FUNCTIONS:
            result = fn(audio, rate)
            record[fn.__name__] = summary(result[field])
            if variant == "original":
                original[fn.__name__] = result
            if variant == "gain_minus_24db":
                np.testing.assert_allclose(
                    np.asarray(result[field], dtype=float),
                    np.asarray(original[fn.__name__][field], dtype=float),
                    rtol=1e-10,
                    atol=1e-8,
                    equal_nan=True,
                )
        report["variants"][variant] = record
    # Known processing should move the intended observation, not classify quality.
    assert (
        report["variants"]["clipped"]["crest_factor"]
        < report["variants"]["original"]["crest_factor"]
    )
    assert (
        report["variants"]["lowpass_1500"]["rolloff"]["median"]
        < report["variants"]["original"]["rolloff"]["median"]
    )
    assert (
        report["variants"]["lowpass_1500"]["bandwidth"]["median"]
        < report["variants"]["original"]["bandwidth"]["median"]
    )
    mono = x.sum(axis=1) if x.ndim == 2 else x
    power = abs(librosa.stft(mono, n_fft=2048, hop_length=512)) ** 2
    maximum = power.max(axis=0)
    valid = maximum > 0
    relative = np.divide(power, maximum, out=np.zeros_like(power), where=valid)
    references = {
        "bandwidth": librosa.feature.spectral_bandwidth(S=relative, sr=rate, n_fft=2048, p=2)[0],
        "rolloff": librosa.feature.spectral_rolloff(
            S=relative, sr=rate, n_fft=2048, roll_percent=0.85
        )[0],
        "flatness": librosa.feature.spectral_flatness(S=relative, power=1, amin=1e-12)[0],
    }
    for category, fn, field in FUNCTIONS:
        if category == "spectral":
            got = np.array(original[fn.__name__][field], dtype=float)[valid]
            expected = references[fn.__name__][valid]
            np.testing.assert_allclose(got, expected, atol=1e-8, rtol=1e-10)
            report["reference"][fn.__name__] = {
                "passed": True,
                "max_abs_error": float(np.max(abs(got - expected))),
            }
        cmd = [
            "uv",
            "run",
            "tactus",
            "analyze",
            category,
            fn.__name__,
            str(args.audio),
            "--out",
            str(args.work / fn.__name__),
        ]
        run = subprocess.run(cmd, capture_output=True, text=True, check=True)
        result = json.loads(run.stdout)
        assert result["result"] == original[fn.__name__]
        saved = json.loads(next((args.work / fn.__name__).glob("*/result.json")).read_text())
        assert saved == result
        report["cli"].append({"command": cmd, "returncode": run.returncode, "matches_python": True})
    report["gain_invariant"] = True
    report["source_sha256"] = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            Path(__file__),
            Path(level.__file__),
            Path(spectral.__file__),
            Path(_features.__file__),
        ]
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ["variants", "reference", "gain_invariant"]}, indent=2))


if __name__ == "__main__":
    main()
