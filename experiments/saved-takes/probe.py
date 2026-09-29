"""Exercise take selection and transfer on the private full-song work, using official tools."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from tactus.inputs import pool, tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--sfizz", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image", default="tactus-clean-handoff:20260928")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    generation = root / "generation"
    generation.mkdir()
    (generation / "tools").mkdir()
    shutil.copytree(args.plugin.resolve(), generation / "tools/OB-Xf.vst3")
    (generation / "tools/sfizz_render").symlink_to(args.sfizz.resolve())
    source = args.source.read_text()
    source = source.replace(
        '"outputs": {\n            "mix": mix,',
        '"takes": {"pads": pads, "bass": bass},\n        "outputs": {\n            "mix": mix,',
    )
    assert '"takes":' in source
    (generation / "song.py").write_text(source)
    # Keep this trial's source inventory and lock independent of the parent Tactus project.
    shutil.copy2(repo / "uv.lock", generation / "uv.lock")
    environment = {**os.environ, "TACTUS_POOL": str(root / "generation-pool")}
    shutil.copytree(
        args.pool,
        root / "generation-pool",
        copy_function=os.link,
        ignore=shutil.ignore_patterns("trees", "stages"),
    )

    def cli(*arguments):
        command = ["uv", "run", "--project", str(repo), "tactus", *map(str, arguments)]
        result = subprocess.run(
            command, env=environment, capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result.stdout)

    generations = []
    for index in range(2):
        result = cli("run", generation / "song.py", "--out", root / f"generated-{index}")
        generations.append(json.loads(Path(result["manifest"]).read_text()))
        print(f"Official instruments: generated candidate {index}", flush=True)
    assert (
        generations[0]["outputs"]["pads"]["sha256"] != generations[1]["outputs"]["pads"]["sha256"]
    )

    refs = {}
    transfer = root / "transfer"
    transfer.mkdir()
    for name in ("pads", "bass"):
        refs[name] = cli("take", "save", root / "generated-0", name)["ref"]
        cli("take", "export", refs[name], "--out", transfer / name)
    alternative = cli("take", "save", root / "generated-1", "pads")["ref"]
    cli("take", "export", alternative, "--out", transfer / "alternative-pads")

    # Only preserved takes and deterministic source samples enter the playback environment.
    playback_pool = transfer / "pool"
    original_receipt = json.loads((root / "generated-0/receipt.json").read_text())
    for item in original_receipt["materials"]:
        if item["ref"].startswith("sha256:"):
            blob = pool.path_for(item["ref"].split(":")[1], root=args.pool)
            pool.put(blob, root=playback_pool)
    for name, expected in [*refs.items(), ("alternative-pads", alternative)]:
        assert tree.add(transfer / name, pool_root=playback_pool) == expected
        shutil.rmtree(transfer / name)
    replay = source.replace(
        "from tactus import fx, material, stage, tool",
        "from tactus import fx, load_take, material, stage, tool",
    )
    replay = replay.replace(
        "    pads_gain_db: float = -7.5,",
        f"    pad_take: str = {refs['pads']!r},\n    pads_gain_db: float = -7.5,",
    )
    replay = replay.replace(
        "    pads = pad_bed()", "    pads = load_take(pad_take, sample_rate=SAMPLE_RATE)"
    )
    replay = replay.replace(
        "    bass = bass_bed()", f"    bass = load_take({refs['bass']!r}, sample_rate=SAMPLE_RATE)"
    )
    replay = replay.replace('        "takes": {"pads": pads, "bass": bass},\n', "")
    (transfer / "song.py").write_text(replay)
    # Independently copy blobs: no links to the generating pool, no stages, no instruments.
    assert not (playback_pool / "stages").exists()
    cases = {
        "baseline": {},
        "bass-minus-3db": {"bass_gain_db": -6.0},
        "alternative": {"pad_take": alternative},
        "restored": {},
    }
    reports = {}
    for name, params in cases.items():
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={transfer},dst=/trial",
            "--mount",
            f"type=bind,src={repo / 'src'},dst=/project/vendor/tactus/src,readonly",
            "-e",
            "TACTUS_POOL=/trial/pool",
            args.image,
            "/project/work/.venv/bin/python",
            "-m",
            "tactus.cli",
            "run",
            "/trial/song.py",
            "--out",
            f"/trial/{name}",
            "--params",
            json.dumps(params),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        (root / f"{name}.stdout.json").write_text(result.stdout)
        (root / f"{name}.stderr.log").write_text(result.stderr)
        result.check_returncode()
        manifest = json.loads((transfer / name / "manifest.json").read_text())
        receipt = json.loads((transfer / name / "receipt.json").read_text())
        assert receipt["tools"] == [] and receipt["reuse"] is False and receipt["stages"] == []
        hashes = {key: item["sha256"] for key, item in manifest["outputs"].items()}
        assert all(
            pool.hash_file(transfer / name / item["file"]) == item["sha256"]
            for item in manifest["outputs"].values()
        )
        reports[name] = {
            "hashes": hashes,
            "seconds": receipt["elapsed_seconds"],
            "tools": receipt["tools"],
            "reuse": receipt["reuse"],
        }
        print(f"Fresh offline container: {name}", flush=True)
    expected = {name: item["sha256"] for name, item in generations[0]["outputs"].items()}
    assert reports["baseline"]["hashes"] == expected == reports["restored"]["hashes"]
    for name in ("pads", "drums", "keys", "textures"):
        assert reports["bass-minus-3db"]["hashes"][name] == expected[name]
    assert reports["bass-minus-3db"]["hashes"]["bass"] != expected["bass"]
    assert reports["alternative"]["hashes"]["pads"] == generations[1]["outputs"]["pads"]["sha256"]
    assert reports["alternative"]["hashes"]["pads"] != expected["pads"]
    evidence = {
        "refs": refs,
        "alternative_pad": alternative,
        "runs": reports,
        "all_six_outputs_match_generation": True,
        "rollback_exact": True,
        "bass_edit_preserves_other_four_stems": True,
        "official_plugin_sha256": tree.digest_of_tree(args.plugin)[0],
        "official_sfizz_sha256": pool.hash_file(args.sfizz),
        "scope": "Same Linux CPU/kernel, fresh offline containers; no native instruments or stage cache mounted. New takes not listener-approved.",
    }
    (root / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
