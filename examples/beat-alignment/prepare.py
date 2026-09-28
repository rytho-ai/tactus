"""Download and pin the recording, run Tactus once, and preserve its unedited beat report.

Reads: librosa's attributed brahms example, Tactus CLI and the local material pool.
Writes: ignored input WAV and tracked provenance/analysis JSON; never runs inside render.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import librosa
import soundfile as sf

ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args):
    completed = subprocess.run(
        [sys.executable, "-m", "tactus.cli", *map(str, args)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main():
    original = Path(librosa.ex("brahms", hq=True))
    audio, rate = sf.read(original, dtype="float64", always_2d=True)
    inputs = ROOT / "inputs"
    inputs.mkdir(exist_ok=True)
    source = inputs / "source.wav"
    sf.write(source, audio, rate, subtype="PCM_24")
    pinned = cli("material", "add", source)["materials"][str(source)]
    report = cli("analyze", "rhythm", "beats", source)
    # Stable identity rather than a machine-specific input path in the frozen report.
    report["path"] = pinned
    beat_file = ROOT / "detected-beats.json"
    beat_file.write_text(json.dumps(report, indent=2) + "\n")
    beat_ref = cli("material", "add", beat_file)["materials"][str(beat_file)]
    provenance = {
        "title": "Hungarian Dance No. 5 (string orchestra)",
        "composer": "Johannes Brahms",
        "performer": "US Army Strings",
        "license": "CC-PDM-1.0 (librosa supplied attribution metadata)",
        "source_url": "https://musopen.org/music/43805-hungarian-dance-no-5-in-f-sharp-minor-woo-1-string-orch",
        "download_url": "https://librosa.org/data/audio/" + original.name,
        "original_sha256": sha256(original),
        "source_ref": pinned,
        "analysis_ref": beat_ref,
        "sample_rate": rate,
        "frames": len(audio),
        "preparation": "Decode HQ Ogg to stereo PCM24 WAV at original sample rate; no timing edits.",
        "grid_status": "Unedited estimator output, frozen provisionally for comparison; human review pending.",
    }
    (ROOT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))
    print("Beat times:", report["result"]["beats_s"])
    print("Tempo curve:", report["result"]["tempo_curve"])


if __name__ == "__main__":
    main()
