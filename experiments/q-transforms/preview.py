"""Rebuild the Chinese comparison page from check.py's report and artifacts."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus.analysis import image, rhythm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = json.loads(args.report.read_text())
    for record in report["cli"]:
        name = record["analysis"].split(".")[-1]
        source = Path(record["image"])
        for origin, extension in (
            (source, "svg"),
            (source.with_name("arrays.npz"), "npz"),
            (source.with_name("result.json"), "json"),
        ):
            shutil.copy2(origin, args.out / f"{name}.{extension}")
    audio, rate = sf.read(args.report.parent / "excerpt.wav")
    sf.write(args.out / "excerpt.wav", audio, rate, subtype="PCM_24")
    clicks = np.zeros(22050 * 16)
    times = np.r_[np.arange(0.5, 8, 1), np.arange(8.5, 16, 0.5)]
    clicks[(times * 22050).astype(int)] = 1
    svg = image(rhythm.tempogram(clicks, 22050), title="60 BPM → 120 BPM")
    (args.out / "tempo-reference.svg").write_text(svg, encoding="utf-8")
    shutil.copy2(Path(__file__).with_name("preview.html"), args.out / "index.html")


if __name__ == "__main__":
    main()
