"""Compare fixed non-neural onset settings and smoke-test feature arrays on real audio.

Run with uv run --extra librosa python experiments/librosa-analysis/check.py --corpus CORPUS --out JSON.
CORPUS contains truth_manifest.json and loops/*.wav. Optional --audio files have no labels;
their outputs demonstrate successful computation only, never onset accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
from pathlib import Path

import librosa
import numpy as np
import scipy
import soundfile as sf

from tactus.analysis import rhythm, spectral


def metrics(truth, detected, tolerance):
    """Maximum-cardinality ordered matching in a fixed tolerance window, one-to-one.

    These sorted one-dimensional windows admit earliest-feasible greedy matching.
    Error statistics concern matched events only, at this tolerance; missed events remain
    in recall. Dense simultaneous reference notes remain separate, as in the saved corpus.
    """
    truth, detected = np.sort(truth), np.sort(detected)
    i = j = 0
    errors = []
    while i < len(truth) and j < len(detected):
        error = detected[j] - truth[i]
        if error < -tolerance:
            j += 1
        elif error > tolerance:
            i += 1
        else:
            errors.append(float(error * 1000))
            i += 1
            j += 1
    tp = len(errors)
    precision = tp / len(detected) if len(detected) else 0.0
    recall = tp / len(truth) if len(truth) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (len(truth) + len(detected)) if len(truth) + len(detected) else 1.0,
        "tp": tp,
        "fp": len(detected) - tp,
        "fn": len(truth) - tp,
        "matched_mean_absolute_error_ms": float(np.mean(np.abs(errors))) if errors else None,
        "matched_mean_signed_error_ms": float(np.mean(errors)) if errors else None,
    }


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def detect(audio, rate):
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    # Historical comparisons used float32, backtrack=True and the recorded tuned settings.
    baseline = mono.astype(np.float32)
    return {
        "librosa_default_backtracked": librosa.onset.onset_detect(
            y=baseline,
            sr=rate,
            backtrack=True,
            units="time",
        ).tolist(),
        "librosa_previous_tuned": librosa.onset.onset_detect(
            y=baseline,
            sr=rate,
            hop_length=64,
            delta=0.03,
            backtrack=True,
            units="time",
        ).tolist(),
        "tactus_superflux": rhythm.onsets(audio, rate)["onsets_s"],
        "tactus_superflux_backtracked": rhythm.onsets(audio, rate, backtrack=True)["onsets_s"],
    }


def synthetic_cases():
    rate = 48000
    events = np.array([0.25, 0.70, 1.15, 1.60, 2.05])
    for name, attack in (("pitched_hard_attack", 0.003), ("pitched_soft_attack", 0.08)):
        x = np.zeros(rate * 3)
        t = np.arange(round(rate * 0.4)) / rate
        for i, start in enumerate(events):
            f = 220 * 2 ** (i / 12)
            note = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)
            note *= np.minimum(1.0, t / attack) * np.exp(-t * 12) * 0.3
            # Avoid unlabelled click transients from abruptly truncating a sounding note.
            release = round(rate * 0.04)
            note[-release:] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, release)))
            offset = round(start * rate)
            x[offset : offset + len(note)] += note
        yield name, x, rate, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--audio", type=Path, nargs="*", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.corpus / "truth_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    report = {
        "versions": {
            "python": platform.python_version(),
            "librosa": librosa.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "source_sha256": {
            str(p): digest(p)
            for p in (
                Path(__file__),
                Path(inspect.getfile(rhythm)),
                Path(inspect.getfile(spectral)),
                Path(inspect.getfile(rhythm)).with_name("_features.py"),
                Path(inspect.getfile(rhythm)).with_name("_onset.py"),
            )
        },
        "corpus_manifest_sha256": digest(manifest_path),
        "onsets_params": {
            k: p.default
            for k, p in inspect.signature(rhythm.onsets).parameters.items()
            if k not in ("audio", "sample_rate")
        },
        "method_notes": {
            "librosa_previous_tuned": "hop_length=64, delta=0.03, backtrack=True, float32; "
            "previously tuned on loop_04, not an untouched baseline",
            "tactus_superflux_backtracked": "default Tactus parameters except backtrack=True",
        },
        "scoring": "One-to-one maximum-cardinality ordered matching at 2/10/25/50 ms; "
        "macro F1 across nine files. Earlier report used nearest greedy matching, "
        "so rerun baselines here instead of comparing headline scores directly.",
        "corpus_label_limits": "Recorded one-shots arranged into loops; reference marks each "
        "sample's first 1%-of-peak crossing before mixing/effects. "
        "Includes near-simultaneous notes; not a human-perceptual grid.",
        "loops": {},
        "synthetic": {},
        "unannotated_smoke": {},
    }
    for filename, meta in manifest.items():
        path = args.corpus / "loops" / filename
        audio, rate = sf.read(path)
        assert rate == meta["rate"] and len(audio) == meta["length"]
        truth = np.asarray(meta["truth_frames"]) / rate
        detections = detect(audio, rate)
        report["loops"][filename] = {
            "sha256": digest(path),
            "sample_rate": rate,
            "truth_s": truth.tolist(),
            "notes": meta["notes"],
            "detections_s": detections,
            "scores": {
                method: {str(ms): metrics(truth, values, ms / 1000) for ms in (2, 10, 25, 50)}
                for method, values in detections.items()
            },
        }
    report["macro_f1"] = {
        method: {
            str(ms): float(
                np.mean(
                    [item["scores"][method][str(ms)]["f1"] for item in report["loops"].values()]
                )
            )
            for ms in (2, 10, 25, 50)
        }
        for method in next(iter(report["loops"].values()))["scores"]
    }
    for name, audio, rate, truth in synthetic_cases():
        values = rhythm.onsets(audio, rate)["onsets_s"]
        report["synthetic"][name] = {
            "reference": "authored envelope start, not perceptual onset",
            "truth_s": truth.tolist(),
            "detected_s": values,
            "scores": {str(ms): metrics(truth, values, ms / 1000) for ms in (2, 10, 25, 50)},
        }
    for path in args.audio:
        audio, rate = sf.read(path)
        # Bound smoke computation to the first 15 seconds; hash records the original file.
        audio = audio[: rate * 15]
        features = {}
        for fn in (spectral.mel, spectral.chroma, spectral.mfcc):
            result = fn(audio, rate)
            arrays = {k: v for k, v in result.items() if isinstance(v, np.ndarray)}
            assert all(np.isfinite(a).all() for a in arrays.values())
            features[fn.__name__] = {k: list(v.shape) for k, v in arrays.items()}
        report["unannotated_smoke"][path.name] = {
            "sha256": digest(path),
            "sample_rate": rate,
            "analyzed_seconds": len(audio) / rate,
            "features": features,
            "onsets_s": rhythm.onsets(audio, rate)["onsets_s"],
            "accuracy": "not evaluated: no onset annotations",
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["macro_f1"], indent=2))


if __name__ == "__main__":
    main()
