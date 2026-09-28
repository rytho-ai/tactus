"""Prepare only this song's declared input closure; never copy a venv or stage cache."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from tactus.inputs import pool, tree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME_COMMIT = "6f6ae20"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--sfizz", type=Path, required=True)
    args = parser.parse_args()
    dest = args.destination.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copytree(
        HERE / "work", dest / "work", ignore=shutil.ignore_patterns(".venv", "__pycache__", "tools")
    )
    vendor = dest / "vendor" / "tactus"
    vendor.mkdir(parents=True)
    archive = subprocess.check_output(["git", "archive", RUNTIME_COMMIT], cwd=REPO)
    subprocess.run(["tar", "-x", "-C", str(vendor)], input=archive, check=True)
    receipt = json.loads((args.original / "runs/c7/receipt.json").read_text())
    refs = sorted(item["ref"] for item in receipt["materials"])
    digests = set()
    for ref in refs:
        digest = ref.rsplit(":", 1)[-1]
        path = pool.path_for(digest, root=args.pool)
        if path is None:
            raise FileNotFoundError(ref)
        digests.add(digest)
        if ref.startswith("tree:"):
            digests.update(d for _, d in tree.parse_manifest(path.read_bytes()))
    total_bytes = 0
    for digest in sorted(digests):
        path = pool.path_for(digest, root=args.pool)
        if path is None:
            raise FileNotFoundError(digest)
        assert pool.put(path, root=dest / "pool") == digest
        total_bytes += path.stat().st_size
    (dest / "tools").mkdir()
    shutil.copytree(args.plugin, dest / "tools/OB-Xf.vst3")
    shutil.copy2(args.sfizz, dest / "tools/sfizz_render")
    (dest / "work/tools").symlink_to("../tools", target_is_directory=True)
    inventory = {
        "scope": "Private Linux x86_64 trial; input redistribution rights are not granted.",
        "tactus_commit": subprocess.check_output(
            ["git", "rev-parse", RUNTIME_COMMIT], cwd=REPO, text=True
        ).strip(),
        "original_source_sha256": pool.hash_file(args.original / "song.py"),
        "approved_mix_sha256": "f2403143b408a79d27d3a77322737665156122b9445d44d54b5c3c65f90f46f4",
        "portable_source_sha256": pool.hash_file(dest / "work/song.py"),
        "material_refs": refs,
        "blobs": sorted(digests),
        "blob_count": len(digests),
        "blob_bytes": total_bytes,
        "tools": {
            "OB-Xf.vst3": {"kind": "tree", "sha256": tree.digest_of_tree(args.plugin)[0]},
            "sfizz_render": {"kind": "file", "sha256": pool.hash_file(args.sfizz)},
        },
    }
    (dest / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    for name in ["Dockerfile", ".dockerignore", "run_isolated.py"]:
        shutil.copy2(HERE / name, dest / name)
    print(json.dumps({"destination": str(dest), "blobs": len(digests), "bytes": total_bytes}))


if __name__ == "__main__":
    main()
