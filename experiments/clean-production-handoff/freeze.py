"""Pin two observed performances while retaining their generation source and receipt."""

import argparse
import json
import shutil
from pathlib import Path

from tactus.inputs import pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_trial", type=Path)
    parser.add_argument("frozen_trial", type=Path)
    args = parser.parse_args()
    original, frozen = args.original_trial.resolve(), args.frozen_trial.resolve()
    frozen.mkdir(exist_ok=False)
    transfer = frozen / "transfer"
    shutil.copytree(
        original / "transfer",
        transfer,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "trees", "stages"),
        symlinks=True,
    )
    # Keep all generators and their provenance outside the frozen work's source inventory.
    provenance = transfer / "generation-source"
    provenance.mkdir()
    for name in ["song.py", "uv.lock", "pyproject.toml"]:
        shutil.copy2(transfer / "work" / name, provenance / name)
    shutil.copy2(original / "host-baseline/receipt.json", provenance / "receipt.json")
    receipt = json.loads((provenance / "receipt.json").read_text())
    inventory = json.loads((transfer / "inventory.json").read_text())
    source = (transfer / "work/song.py").read_text()
    performances = {}
    for function, constant in [("pad_bed", "PAD_PERFORMANCE"), ("bass_bed", "BASS_PERFORMANCE")]:
        stage = next(s for s in receipt["stages"] if s["name"] == function)
        stage_dir = original / "host-stages" / stage["key"]
        arrays = list(stage_dir.glob("arr-*.npy"))
        assert len(arrays) == 1
        digest = pool.put(arrays[0], root=transfer / "pool")
        ref = "sha256:" + digest
        performances[function] = {
            "ref": ref,
            "stage_key": stage["key"],
            "generation_receipt_sha256": pool.hash_file(provenance / "receipt.json"),
        }
        source = source.replace(f"@stage\ndef {function}(", f"def synthesize_{function}(")
        source += f'\n\n{constant} = "{ref}"\n\n\n@stage\ndef {function}() -> np.ndarray:\n    """Replay the pinned pre-gain performance; regeneration is a source revision."""\n    return np.load(material({constant}), allow_pickle=False)\n'
        inventory["material_refs"].append(ref)
        inventory["blobs"].append(digest)
        inventory["blob_bytes"] += arrays[0].stat().st_size
    (transfer / "work/song.py").write_text(source)
    inventory.update(
        {
            "mode": "frozen-performances",
            "performances": performances,
            "portable_source_sha256": pool.hash_file(transfer / "work/song.py"),
            "render_material_refs": sorted(
                ref for ref in inventory["material_refs"] if not ref.startswith("tree:")
            ),
            "render_tools": {},
            "blob_count": len(inventory["blobs"]),
        }
    )
    (transfer / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    # Use the latest runner, but never modify the earlier trial's files.
    shutil.copy2(Path(__file__).with_name("run_isolated.py"), transfer / "run_isolated.py")
    print(json.dumps({"frozen_trial": str(frozen), "performances": performances}, indent=2))


if __name__ == "__main__":
    main()
