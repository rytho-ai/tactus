"""Measure saved candidate audio; estimate temporal correspondence independently of beats.

Reads: three Tactus manifests/WAVs, frozen source beat map. DTW uses spectral audio features,
not the marker positions; markers are queried only after obtaining the full alignment path.
Writes: tracked measurements.json and ignored data for the listening page. A DTW correspondence
is not manually annotated beat truth and boundary statistics do not establish inaudibility.
"""

from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from song import BACKEND, load_phrase

ROOT = Path(__file__).resolve().parent
HOP = 441


def read_run(name):
    directory = ROOT / "runs" / "final" / name
    manifest = json.loads((directory / "manifest.json").read_text())
    audio = {}
    for stem, entry in manifest["outputs"].items():
        audio[stem], rate = sf.read(directory / entry["file"], always_2d=True)
        assert rate == manifest["sample_rate"]
    return manifest, audio


def features(audio, rate):
    spectrum = librosa.feature.melspectrogram(
        y=audio.mean(axis=1),
        sr=rate,
        n_fft=2048,
        hop_length=HOP,
        n_mels=48,
        fmin=80,
        fmax=12000,
        power=1.0,
    )
    compressed = np.log1p(spectrum / 0.01)
    change = np.maximum(np.diff(compressed, prepend=compressed[:, :1], axis=1), 0)
    return np.concatenate([compressed, change * 2], axis=0) + 1e-8


def correspondence(source_features, target_features, rate):
    _, path = librosa.sequence.dtw(
        X=source_features,
        Y=target_features,
        metric="cosine",
        step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
        weights_mul=np.array([1.0, 1.5, 1.5]),
        global_constraints=True,
        band_rad=0.25,
    )
    path = path[::-1]
    source_indices = np.unique(path[:, 0])
    target_indices = np.array([np.median(path[path[:, 0] == i, 1]) for i in source_indices])
    return source_indices * HOP / rate, target_indices * HOP / rate


def error_summary(error_seconds):
    absolute = np.abs(error_seconds) * 1000
    return {
        "mean_abs_ms": float(absolute.mean()),
        "median_abs_ms": float(np.median(absolute)),
        "p95_abs_ms": float(np.percentile(absolute, 95)),
        "max_abs_ms": float(absolute.max()),
    }


def boundaries(audio, positions, rate):
    derivative = np.max(np.abs(np.diff(audio, axis=0)), axis=1)
    rows = []
    for frame in positions[2:-2]:
        n = int(frame)
        local = derivative[max(0, n - rate // 10) : n + rate // 10]
        near = derivative[max(0, n - rate // 1000) : n + rate // 1000]
        baseline = float(np.percentile(local, 99))
        jump = float(near.max())
        rows.append(
            {"frame": n, "peak_step": jump, "relative_to_local_p99": jump / max(baseline, 1e-12)}
        )
    return {
        "largest_marker_step": max(r["peak_step"] for r in rows),
        "largest_relative_step": max(r["relative_to_local_p99"] for r in rows),
        "isolated_step_flags": sum(
            r["peak_step"] > 0.02 and r["relative_to_local_p99"] > 3 for r in rows
        ),
        "definition": "Peak sample difference within 1 ms of each marker vs local 100 ms p99; flag >0.02 and >3x. Diagnostic, not audibility test.",
    }


def main():
    phrase, rate, source_frames = load_phrase()
    source_times = source_frames / rate
    target_times = np.arange(len(source_frames)) * 60 / 160
    target_frames = np.floor(target_times * rate + 0.5).astype(int)
    runs = {name: read_run(name) for name in ("source", "fixed", "warp")}
    reference = features(runs["source"][1]["music"], rate)
    fixed_drums = runs["fixed"][0]["outputs"]["drums"]["sha256"]
    assert fixed_drums == runs["warp"][0]["outputs"]["drums"]["sha256"]
    assert source_frames[0] == 0 and source_frames[-1] == len(phrase)
    assert np.all(np.diff(source_frames) > 0) and np.all(np.diff(target_frames) > 0)
    interior = slice(2, -2)
    global_mapping = source_times * target_times[-1] / source_times[-1]
    report = {
        "sample_rate": rate,
        "backend": BACKEND,
        "target_bpm": 160,
        "source_duration_s": len(phrase) / rate,
        "target_duration_s": float(target_times[-1]),
        "beat_intervals": len(source_times) - 1,
        "source_interval_bpm_range": [
            float(np.min(60 / np.diff(source_times))),
            float(np.max(60 / np.diff(source_times))),
        ],
        "fixed_affine_marker_error": error_summary((global_mapping - target_times)[interior]),
        "identical_percussion_sha256": fixed_drums,
        "measurement": "48-band log-mel plus positive spectral difference; unconstrained-by-markers full-phrase DTW, 10 ms hops, +/-25% global band, steps (1,1)/(1,2)/(2,1); query frozen source beat times afterwards. Exclude first/last two anchors.",
        "candidates": {},
    }
    plot = {
        "source_times": source_times.tolist(),
        "target_times": target_times.tolist(),
        "source_bpm": (60 / np.diff(source_times)).tolist(),
    }
    for name in ("fixed", "warp"):
        manifest, audio = runs[name]
        assert all(len(x) == target_frames[-1] for x in audio.values())
        assert all(np.isfinite(x).all() for x in audio.values())
        assert all(entry["clipped_samples"] == 0 for entry in manifest["outputs"].values())
        x, y = correspondence(reference, features(audio["music"], rate), rate)
        actual = np.interp(source_times, x, y)
        intended = global_mapping if name == "fixed" else target_times
        report["candidates"][name] = {
            "audio_correspondence_grid_error": error_summary((actual - target_times)[interior]),
            "audio_correspondence_mapping_error": error_summary((actual - intended)[interior]),
            "boundaries": boundaries(audio["music"], target_frames, rate),
            "music_rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(audio["music"] ** 2)))),
            "mix_peak_dbfs": manifest["outputs"]["mix"]["peak_dbfs"],
            "clipped_samples": sum(e["clipped_samples"] for e in manifest["outputs"].values()),
            "frames": len(audio["music"]),
        }
        plot[name + "_residual_ms"] = ((actual - target_times) * 1000).tolist()
    # Identity is a calibration of the feature alignment method, not a musical accuracy claim.
    x, y = correspondence(reference, reference, rate)
    identity_error = float(np.max(np.abs(x - y)))
    assert identity_error == 0
    report["dtw_identity_max_error_s"] = identity_error
    report["listening_status"] = "Human assessment of grid, artifacts and preference pending."
    (ROOT / "measurements.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "runs" / "plot.json").write_text(json.dumps(plot) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
