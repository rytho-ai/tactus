"""Verify real LSP VST3 latency against transparent impulses and seeded noise.

Run with uv run experiments/vst-latency/probe.py BUNDLE --out REPORT.json.
Uses an unmodified externally supplied LSP 1.2.35 bundle, never a runtime dependency.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pedalboard

from tactus import fx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    binary = args.bundle / "Contents/x86_64-linux/lsp-plugins.so"
    report = {
        "plugin": "LSP Limiter 1.2.35",
        "pedalboard": pedalboard.__version__,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "cases": [],
    }
    for rate, channels, count, hop, tail in (
        (44100, 1, 1, 0.02, 0),
        (48000, 2, 1, 0.02, 0.03),
        (48000, 2, 2, 0.01, 0),
        (44100, 2, 1, 0.003, 0),
    ):
        plugins = []
        for i in range(count):
            plugin = pedalboard.load_plugin(
                str(args.bundle), plugin_name=f"Limiter {'Mono' if channels == 1 else 'Stereo'}"
            )
            plugin.lookahead_ms = 10 if i == 0 else 5
            plugin.gain_boost = False
            plugin.automatic_level_regulation = False
            plugins.append(plugin)
        chain = plugins[0] if count == 1 else pedalboard.Pedalboard(plugins)
        shape = (rate,) if channels == 1 else (rate, channels)
        audio = np.random.default_rng(91).uniform(-0.02, 0.02, shape).astype(np.float32)
        audio[[0, rate // 4, rate - 1]] = 0.1
        before = audio.copy()
        calls = []
        actual = fx.process_automated(
            chain, audio, rate, calls.append, block_seconds=hop, tail_seconds=tail
        )
        expected = np.pad(
            audio, (0, round(tail * rate)) if channels == 1 else ((0, round(tail * rate)), (0, 0))
        )
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(audio, before)
        assert all(p.reported_latency_samples > 0 for p in plugins)
        # A second call starts fresh even when the plugin objects are reused.
        repeated = fx.process_automated(
            chain, audio, rate, lambda t: None, block_seconds=hop, tail_seconds=tail
        )
        np.testing.assert_array_equal(repeated, expected)
        case = {
            "sample_rate": rate,
            "channels": channels,
            "plugins": count,
            "block_seconds": hop,
            "tail_seconds": tail,
            "latencies": [p.reported_latency_samples for p in plugins],
            "frames": len(actual),
            "array_equal": True,
            "repeat_equal": True,
            "max_error": float(np.max(abs(actual - expected))),
            "update_calls": len(calls),
        }
        report["cases"].append(case)
        print(json.dumps(case), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
