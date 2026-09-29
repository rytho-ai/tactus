"""Exercise both SuperFlux frontends using a work environment without dev references."""

import argparse
import json
import subprocess
from pathlib import Path

import soundfile as sf

from tactus.analysis import rhythm


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--audio", type=Path, nargs="+", required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    prefix = ["uv", "run", "--project", str(a.project.resolve())]
    probe = subprocess.run(
        [
            *prefix,
            "python",
            "-c",
            'import importlib.util,json; print(json.dumps({n:importlib.util.find_spec(n) is not None for n in ["librosa","pyloudnorm","numba"]}))',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    dependencies = json.loads(probe.stdout)
    assert not any(dependencies.values())
    report = {"reference_packages_present": dependencies, "commands": []}
    for path in a.audio:
        x, rate = sf.read(path)
        for name in ["onsets", "onset_strength"]:
            for variant in ["mel", "log"]:
                dest = a.work / f"{path.stem}-{name}-{variant}"
                cmd = [
                    *prefix,
                    "tactus",
                    "analyze",
                    "rhythm",
                    name,
                    str(path.resolve()),
                    "--filterbank",
                    variant,
                    "--out",
                    str(dest.resolve()),
                ]
                run = subprocess.run(cmd, capture_output=True, text=True, check=True)
                record = json.loads(run.stdout)
                assert record["result"] == getattr(rhythm, name)(x, rate, filterbank=variant)
                saved = json.loads(next(dest.rglob("result.json")).read_text())
                assert record == saved
                assert record["params"]["filterbank"] == variant
                capture = a.work / f"{dest.name}.json"
                capture.write_text(
                    json.dumps(
                        {"command": cmd, "stdout": run.stdout, "stderr": run.stderr}, indent=2
                    )
                )
                report["commands"].append(
                    {"command": cmd, "capture": str(capture), "result": "pass"}
                )
    invalid = subprocess.run(
        [
            *prefix,
            "tactus",
            "analyze",
            "rhythm",
            "onsets",
            str(a.audio[0].resolve()),
            "--filterbank",
            "invalid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode != 0 and "filterbank" in invalid.stdout
    report["invalid_selector"] = {"returncode": invalid.returncode, "stdout": invalid.stdout}
    a.out.write_text(json.dumps(report, indent=2))
    print(
        f"{len(report['commands'])} CLI parity/save checks and invalid selector passed; no dev reference packages"
    )


if __name__ == "__main__":
    main()
