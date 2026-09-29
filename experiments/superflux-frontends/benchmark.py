"""Measure public onset calls and fresh CLI startup/RSS; run before and after changes."""

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

import soundfile as sf

from tactus.analysis import rhythm

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--audio", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--filterbank", default=None)
a = p.parse_args()
x, sr = sf.read(a.audio)
params = {} if a.filterbank is None else {"filterbank": a.filterbank}
warm = []
for i in range(8):
    t = time.perf_counter()
    rhythm.onsets(x, sr, **params)
    elapsed = time.perf_counter() - t
    if i:
        warm.append(elapsed)
cold = []
for i in range(5):
    cmd = [
        "/usr/bin/time",
        "-f",
        "%M",
        "uv",
        "run",
        "tactus",
        "analyze",
        "rhythm",
        "onsets",
        str(a.audio),
    ]
    if a.filterbank is not None:
        cmd += ["--filterbank", a.filterbank]
    t = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    elapsed = time.perf_counter() - t
    json.loads(result.stdout)
    cold.append({"seconds": elapsed, "rss_kib": int(result.stderr.splitlines()[-1])})
report = {
    "audio": str(a.audio),
    "sample_rate": sr,
    "frames": len(x),
    "params": params,
    "warm_seconds": warm,
    "warm_median": statistics.median(warm),
    "cold": cold,
    "cold_median": statistics.median(r["seconds"] for r in cold),
    "rss_kib_median": statistics.median(r["rss_kib"] for r in cold),
}
a.out.write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if "median" in k}))
