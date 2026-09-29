"""Compare owned spectral/onset analyses with optional librosa on supplied audio.

uv run --extra librosa python experiments/owned-analysis/check.py --audio FILE [FILE ...] --out REPORT
Librosa is installed through the optional librosa extra, not the default runtime. Loudness uses
frozen answers in tests/fixtures and the independent EBU check, not a live package.
"""

import argparse
import hashlib
import inspect
import json
import statistics
import time
from importlib.metadata import version
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from tactus import _biquad
from tactus.analysis import _features, _level, _onset, level, rhythm, spectral


def reference(audio, rate, name):
    x = audio.sum(axis=1) if audio.ndim == 2 else audio
    if name in ("mel", "mfcc", "chroma"):
        size = 4096 if name == "chroma" else 2048
        padded = np.pad(x, (0, max(0, size - len(x))))
        power = abs(librosa.stft(padded, n_fft=size, hop_length=512))[:, : 1 + len(x) // 512] ** 2
        if name == "chroma":
            return librosa.feature.chroma_stft(S=power, sr=rate, n_fft=size, tuning=0)
        mel = librosa.feature.melspectrogram(S=power, sr=rate, n_fft=size)
        if name == "mel":
            return mel
        return librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=20)
    x = audio.mean(axis=1) if audio.ndim == 2 else audio
    hop = max(1, round(rate * 0.005))
    padded = np.pad(x, (0, max(0, 1024 - len(x))))
    power = abs(librosa.stft(padded, n_fft=1024, hop_length=hop))[:, : 1 + len(x) // hop] ** 2
    mel = librosa.feature.melspectrogram(
        S=power, sr=rate, n_fft=1024, n_mels=138, fmin=27.5, fmax=min(16000, rate / 2)
    )
    if mel.shape[1] <= 2:
        strength = np.zeros(mel.shape[1])
    else:
        strength = librosa.onset.onset_strength(
            S=librosa.power_to_db(mel, ref=np.max),
            sr=rate,
            n_fft=1024,
            hop_length=hop,
            lag=2,
            max_size=3,
        )
    if name == "onset_strength":
        return strength
    frames = librosa.onset.onset_detect(
        onset_envelope=strength, sr=rate, hop_length=hop, delta=0.07, wait=int(0.03 * rate // hop)
    )
    if name == "onsets_backtracked" and len(frames):
        normalized = strength - strength.min()
        normalized /= normalized.max() + np.finfo(float).tiny
        frames = librosa.onset.onset_backtrack(frames, normalized)
    return np.unique(frames[frames * hop < len(x)]) * hop / rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checks = {
        "mel": (spectral.mel, "power", {}),
        "mfcc": (spectral.mfcc, "coefficients", {}),
        "chroma": (spectral.chroma, "chroma", {}),
        "onset_strength": (rhythm.onset_strength, "strength", {}),
        "onsets": (rhythm.onsets, "onsets_s", {}),
        "onsets_backtracked": (rhythm.onsets, "onsets_s", {"backtrack": True}),
    }
    report = {
        "versions": {p: version(p) for p in ["numpy", "scipy", "librosa"]},
        "sources": {
            str(Path(inspect.getfile(m)).relative_to(Path.cwd())): hashlib.sha256(
                Path(inspect.getfile(m)).read_bytes()
            ).hexdigest()
            for m in [_biquad, _features, _level, _onset, level, rhythm, spectral]
        },
        "inputs": [],
    }
    for path in args.audio:
        audio, rate = sf.read(path)
        item = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sample_rate": rate,
            "frames": len(audio),
            "checks": {},
        }
        for name, (fn, field, params) in checks.items():
            expected = reference(audio, rate, name)
            got = fn(audio, rate, **params)[field]
            if got is None:
                assert not np.isfinite(expected)
                error = None
            else:
                if name.startswith("onsets"):
                    np.testing.assert_array_equal(got, expected)
                else:
                    np.testing.assert_allclose(got, expected, atol=1e-8, rtol=1e-10)
                delta = np.abs(np.asarray(got) - expected)
                error = float(delta.max()) if delta.size else 0.0
            item["checks"][name] = {"passed": True, "max_abs_error": error}
        # Full public functions, warm median, no file loading or imports included.
        item["timings_s"] = {}
        for fn in [
            level.loudness,
            level.rms_curve,
            level.peak_curve,
            level.momentary_loudness,
            level.short_term_loudness,
            level.loudness_range,
            spectral.mel,
            spectral.mfcc,
            spectral.chroma,
            rhythm.onsets,
        ]:
            fn(audio, rate)
            samples = []
            for _ in range(5):
                start = time.perf_counter()
                fn(audio, rate)
                samples.append(time.perf_counter() - start)
            item["timings_s"][fn.__name__] = statistics.median(samples)
        report["inputs"].append(item)
        print(path.name, f"{len(checks)}/{len(checks)} parity checks passed", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
