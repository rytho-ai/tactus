"""Freeze an analysis-driven time decision before rendering; run explicitly to revise.

Synthesizes and pins source audio, measures it, authors a warp, and pins the full report.
Writes decisions.py with immutable refs. The CLI owns pool ingestion.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from phrase import phrase

from tactus.analysis import level


def pin(path):
    command = [sys.executable, "-m", "tactus.cli", "material", "add", str(path)]
    result = json.loads(subprocess.check_output(command, text=True))
    return result["materials"][str(path)]


def prepare():
    root = Path(__file__).resolve().parent
    artifacts = root / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    audio, rate = phrase()
    source = artifacts / "phrase.wav"
    sf.write(source, audio, rate, subtype="FLOAT")
    source_ref = pin(source)
    curve = level.rms_curve(audio, rate, window_s=0.05, hop_s=0.025)
    values = np.array([0 if x is None else 10 ** (x / 20) for x in curve["rms_dbfs"]])
    frames = np.rint(np.linspace(0, len(audio), 9)).astype(int)
    centers = (frames[:-1] + frames[1:]) / (2 * rate)
    energy = np.interp(centers, curve["times_s"], values)
    # A compositional choice: stronger phrases occupy more time; total length stays 8 s.
    weights = 0.5 + energy / max(float(energy.max()), 1e-12)
    target = np.rint(np.r_[0, np.cumsum(weights)] / weights.sum() * 8 * rate).astype(int)
    report = {
        "source_ref": source_ref,
        "source_frames": len(audio),
        "sample_rate": rate,
        "analysis": "tactus.analysis.level.rms_curve",
        "revision": level.rms_curve.revision,
        "params": {"window_s": 0.05, "hop_s": 0.025},
        "curve": curve,
        "markers": np.column_stack([frames, target]).tolist(),
        "choice": "Stronger phrases expand; interpolate window-end RMS, hold edges, null=0.",
    }
    report_path = artifacts / "decision.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    decision_ref = pin(report_path)
    (root / "decisions.py").write_text(
        '"""Frozen by prepare.py; regenerating is an explicit creative revision."""\n\n'
        f'SOURCE = "{source_ref}"\nDECISION = "{decision_ref}"\n'
    )
    print(json.dumps({"source": source_ref, "decision": decision_ref}))


if __name__ == "__main__":
    prepare()
