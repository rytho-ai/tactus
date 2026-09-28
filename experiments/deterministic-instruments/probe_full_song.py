"""Regenerate the full song in fresh offline containers with local patched instruments."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from tactus.inputs import pool, tree


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pool", type=Path, required=True)
    p.add_argument("--plugin", type=Path, required=True)
    p.add_argument("--sfizz", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--image", default="tactus-clean-handoff:20260928")
    args = p.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(
        args.pool,
        root / "pool",
        copy_function=os.link,
        ignore=shutil.ignore_patterns("stages", "trees"),
    )
    shutil.copytree(args.plugin, root / "tools/OB-Xf.vst3")
    shutil.copy2(args.sfizz, root / "tools/sfizz_render")
    records = []
    for index in range(3):
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={root},dst=/trial",
            args.image,
            "uv",
            "run",
            "--offline",
            "--frozen",
            "tactus",
            "run",
            "song.py",
            "--out",
            f"/trial/run-{index}",
        ]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        (root / f"run-{index}.stdout.json").write_text(proc.stdout)
        (root / f"run-{index}.stderr.log").write_text(proc.stderr)
        proc.check_returncode()
        run = root / f"run-{index}"
        receipt = json.loads((run / "receipt.json").read_text())
        manifest = json.loads((run / "manifest.json").read_text())
        assert not receipt["reuse"] and not receipt["stages"]
        for entry in manifest["outputs"].values():
            assert pool.hash_file(run / entry["file"]) == entry["sha256"]
        records.append(
            {
                "hashes": {n: v["sha256"] for n, v in manifest["outputs"].items()},
                "seconds": receipt["elapsed_seconds"],
                "reuse": receipt["reuse"],
                "source_files": receipt["source_files"],
                "tools": receipt["tools"],
            }
        )
        print(json.dumps({"run": index, **records[-1]}), flush=True)
    reference = json.loads((args.reference / "manifest.json").read_text())
    exact = all(r["hashes"] == records[0]["hashes"] for r in records)
    unchanged = {
        n: records[0]["hashes"][n] == reference["outputs"][n]["sha256"]
        for n in ["bass", "drums", "keys", "textures"]
    }
    report = {
        "runs": records,
        "all_six_outputs_exact": exact,
        "other_stems_match_prior_host": unchanged,
        "plugin_sha256": tree.digest_of_tree(args.plugin)[0],
        "sfizz_sha256": pool.hash_file(args.sfizz),
        "image": subprocess.check_output(
            ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"], text=True
        ).strip(),
        "scope": "Fresh full synthesis, no stage reuse or saved performances; same Linux CPU/kernel.",
    }
    (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    assert exact and all(unchanged.values()), report


if __name__ == "__main__":
    main()
