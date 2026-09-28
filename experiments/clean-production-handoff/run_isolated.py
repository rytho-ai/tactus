"""Restore a fresh pool, exercise failures and render both candidates without network."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tactus import material, tool
from tactus.inputs import MaterialError, ToolError, pool, tree

INCOMING = Path("/incoming")
TRIAL = Path("/trial")
WORK = Path("/project/work")


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    inventory = json.loads((INCOMING / "inventory.json").read_text())
    assert not (TRIAL / "pool").exists(), "The destination must be fresh"
    assert not (TRIAL / "tools").exists(), "The destination must be fresh"
    checks = []

    def rejected(name, callback):
        try:
            callback()
        except (MaterialError, ToolError, ValueError, FileNotFoundError, RuntimeError) as exc:
            checks.append({"name": name, "rejected": True, "error": str(exc)})
        else:
            raise AssertionError(f"{name}: should have failed")

    for ref in inventory["material_refs"]:
        rejected(f"missing {ref}", lambda ref=ref: material(ref))
    for name in inventory["tools"]:
        rejected(f"missing {name}", lambda name=name: tool(str(TRIAL / "tools" / name)))
    shutil.copytree(INCOMING / "pool", TRIAL / "pool")
    shutil.copytree(INCOMING / "tools", TRIAL / "tools")
    assert not (TRIAL / "pool/stages").exists()
    # Damage a disposable destination blob, verify refusal, then restore exact bytes.
    ref = next(ref for ref in inventory["material_refs"] if ref.startswith("sha256:"))
    digest = ref.split(":")[-1]
    target = pool.path_for(digest)
    target.write_bytes(b"intentional corruption for the acceptance trial")
    rejected("corrupt file", lambda: material(ref))
    shutil.copyfile(INCOMING / "pool" / digest[:2] / digest, target)
    tree_ref = next(ref for ref in inventory["material_refs"] if ref.startswith("tree:"))
    manifest = pool.path_for(tree_ref.split(":")[-1])
    leaf = tree.parse_manifest(manifest.read_bytes())[0][1]
    target_leaf = pool.path_for(leaf)
    target_leaf.unlink()
    rejected("missing tree member", lambda: material(tree_ref))
    shutil.copyfile(INCOMING / "pool" / leaf[:2] / leaf, target_leaf)
    for ref in inventory["material_refs"]:
        material(ref)
    for name, expected in inventory["tools"].items():
        path = tool(str(TRIAL / "tools" / name))
        actual = (
            tree.digest_of_tree(path)[0] if expected["kind"] == "tree" else pool.hash_file(path)
        )
        assert actual == expected["sha256"], name
    # Identity enforcement belongs to this trial preflight; tool() itself only records.
    executable = TRIAL / "tools/sfizz_render"
    actual = pool.hash_file(executable)
    assert actual == inventory["tools"]["sfizz_render"]["sha256"]
    dump(
        TRIAL / "preflight.json",
        {"checks": checks, "restored": True, "stage_cache_initially_empty": True},
    )
    shutil.copy2("/project/system-packages.txt", TRIAL / "system-packages.txt")
    for name, params in [("baseline", {}), ("bass-minus-3db", {"bass_gain_db": -6.0})]:
        cmd = [
            str(Path(sys.prefix) / "bin/tactus"),
            "run",
            "song.py",
            "--reuse",
            "--out",
            str(TRIAL / "runs" / name),
            "--params",
            json.dumps(params),
        ]
        proc = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, check=False)
        (TRIAL / f"{name}.stdout.json").write_text(proc.stdout)
        (TRIAL / f"{name}.stderr.log").write_text(proc.stderr)
        print(proc.stdout, flush=True)
        proc.check_returncode()
    dump(
        TRIAL / "isolation.json",
        {
            "python": sys.version,
            "prefix": sys.prefix,
            "pool": os.environ["TACTUS_POOL"],
            "routes": Path("/proc/net/route").read_text(),
        },
    )


if __name__ == "__main__":
    main()
