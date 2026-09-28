"""Compare actual full renders and make a verified, aligned delivery for this trial."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus.inputs.pool import hash_file

SECTIONS = [
    ("intro", 1, 9),
    ("rise", 9, 17),
    ("core_a1", 17, 25),
    ("core_a2", 25, 33),
    ("core_b", 33, 41),
    ("outro", 41, 47),
]
RATE = 44100
FRAMES = round(46 * 4 * 60 / 74 * RATE)


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_run(path):
    manifest = json.loads((path / "manifest.json").read_text())
    receipt = json.loads((path / "receipt.json").read_text())
    assert manifest["sample_rate"] == RATE
    for item in manifest["outputs"].values():
        audio_path = path / item["file"]
        assert hash_file(audio_path) == item["sha256"]
        info = sf.info(audio_path)
        assert info.frames == item["frames"] == FRAMES
        assert info.channels == item["channels"] == 2
        assert info.samplerate == RATE and info.subtype == "PCM_24"
    return manifest, receipt


def read(run, manifest, name):
    return sf.read(run / manifest["outputs"][name]["file"], dtype="float64")[0]


def compare(a_path, a, b_path, b):
    result = {}
    for name in a["outputs"]:
        x, y = read(a_path, a, name), read(b_path, b, name)
        diff = y - x
        result[name] = {
            "byte_identical": a["outputs"][name]["sha256"] == b["outputs"][name]["sha256"],
            "max_abs_sample_difference": float(np.max(np.abs(diff))),
            "rms_difference": float(np.sqrt(np.mean(diff * diff))),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--approved-run", type=Path, required=True)
    parser.add_argument("--preserved-run", type=Path)
    parser.add_argument("--synthesis-evidence", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    host_path = root / "host-baseline"
    base_path = root / "isolated/runs/baseline"
    candidate_path = root / "isolated/runs/bass-minus-3db"
    host, host_r = load_run(host_path)
    base, base_r = load_run(base_path)
    candidate, cand_r = load_run(candidate_path)
    approved, _ = load_run(args.approved_run)
    reconstruction = compare(host_path, host, base_path, base)
    revision = compare(base_path, base, candidate_path, candidate)
    historical = compare(args.approved_run, approved, host_path, host)
    x, y = read(host_path, host, "pads"), read(base_path, base, "pads")
    pad_sections = []
    for name, first, end in SECTIONS:
        lo, hi = [round((bar - 1) * 4 * 60 / 74 * RATE) for bar in (first, end)]
        ratio = np.sqrt(np.mean(y[lo:hi] ** 2) / np.mean(x[lo:hi] ** 2))
        pad_sections.append({"section": name, "rms_change_db": float(20 * np.log10(ratio))})
    x, y = read(base_path, base, "bass"), read(candidate_path, candidate, "bass")
    factor = 10 ** (-3 / 20)
    bass_error = float(np.max(np.abs(y - x * factor)))
    bass_rms_change = float(20 * np.log10(np.sqrt(np.mean(y * y) / np.mean(x * x))))
    inv = json.loads((root / "transfer/inventory.json").read_text())
    expected_tools = sorted(
        item["sha256"] for item in inv.get("render_tools", inv["tools"]).values()
    )
    expected_materials = sorted(inv.get("render_material_refs", inv["material_refs"]))
    checks = {
        "deterministic_stems_exact": all(
            reconstruction[n]["byte_identical"] for n in ["bass", "keys", "drums", "textures"]
        ),
        "stochastic_pad_sections_within_1db": all(
            abs(row["rms_change_db"]) <= 1 for row in pad_sections
        ),
        "four_untouched_stems_exact": all(
            revision[n]["byte_identical"] for n in ["pads", "keys", "drums", "textures"]
        ),
        "bass_and_mix_changed": all(not revision[n]["byte_identical"] for n in ["bass", "mix"]),
        "bass_gain_within_two_pcm24_steps": bass_error <= 2 / 2**23,
        "fresh_baseline_computed_all_stages": len(base_r["stages"]) == 5
        and all(not s["reused"] for s in base_r["stages"]),
        "candidate_reused_all_stages": len(cand_r["stages"]) == 5
        and all(s["reused"] for s in cand_r["stages"]),
        "only_bass_parameter_changed": {
            k for k in base_r["parameters"] if base_r["parameters"][k] != cand_r["parameters"][k]
        }
        == {"bass_gain_db"},
        "source_and_lock_unchanged": host_r["source_files"]
        == base_r["source_files"]
        == cand_r["source_files"]
        and len({r["dependency_lock"]["sha256"] for r in [host_r, base_r, cand_r]}) == 1,
        "materials_and_tools_complete": all(
            sorted(t["sha256"] for t in r["tools"]) == expected_tools
            and sorted(m["ref"] for m in r["materials"]) == expected_materials
            for r in [host_r, base_r, cand_r]
        ),
        "same_imported_package_versions": host_r["python_packages"]
        == base_r["python_packages"]
        == cand_r["python_packages"],
    }
    if inv.get("mode") == "frozen-performances":
        checks["all_six_outputs_exact"] = all(
            item["byte_identical"] for item in reconstruction.values()
        )
    preservation = None
    if args.preserved_run:
        preserved_manifest, _ = load_run(args.preserved_run)
        preservation = compare(args.preserved_run, preserved_manifest, host_path, host)
        checks["original_host_performance_preserved"] = all(
            v["byte_identical"] for v in preservation.values()
        )
    inspection = json.loads((root / "container-inspect.json").read_text())[0]
    checks["network_disabled"] = inspection["HostConfig"]["NetworkMode"] == "none"
    checks["only_declared_mounts"] = {m["Destination"] for m in inspection["Mounts"]} == {
        "/incoming/pool",
        "/incoming/tools",
        "/incoming/inventory.json",
        "/trial",
    }
    preflight = json.loads((root / "isolated/preflight.json").read_text())
    checks["negative_checks_rejected"] = len(preflight["checks"]) == len(
        inv["material_refs"]
    ) + len(inv["tools"]) + 2 and all(c["rejected"] for c in preflight["checks"])
    report = {
        "mode": inv.get("mode", "regenerated-instruments"),
        "preservation": preservation,
        "checks": checks,
        "passed": all(checks.values()),
        "host_to_clean": reconstruction,
        "clean_baseline_to_candidate": revision,
        "approved_c7_to_current_host": historical,
        "pad_sections": pad_sections,
        "bass_change_db": bass_rms_change,
        "bass_gain_max_sample_error": bass_error,
        "elapsed_seconds": {
            "host": host_r["elapsed_seconds"],
            "clean_baseline": base_r["elapsed_seconds"],
            "candidate": cand_r["elapsed_seconds"],
        },
        "delivery": {
            "sample_rate": RATE,
            "frames": FRAMES,
            "duration_seconds": FRAMES / RATE,
            "channels": 2,
            "format": "PCM_24",
            "start_frame": 0,
        },
        "limits": [
            "Same CPU/kernel, separate Ubuntu filesystem and Python environment; no cross-OS claim.",
            "OB-Xf fresh performances are stochastic; 1 dB section RMS is a coarse gate, not proof of perceptual equivalence.",
            "Stems contain channel processing and output gains, before nonlinear master compression/limiting; their sum is not the delivered master.",
            "Bass candidate is an unaccepted edit for audition.",
        ],
    }
    dump(root / "measurements.json", report)
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit("Acceptance checks failed; preserve evidence and diagnose before delivery")
    delivery = root / "delivery"
    delivery.mkdir(exist_ok=False)
    for label, path, manifest in [
        ("baseline", base_path, base),
        ("bass-minus-3db", candidate_path, candidate),
    ]:
        out = delivery / label
        out.mkdir()
        for name, item in manifest["outputs"].items():
            shutil.copy2(path / item["file"], out / f"{name}.wav")
        for name in ["receipt.json", "manifest.json"]:
            shutil.copy2(path / name, out / name)
    source = delivery / "source"
    shutil.copytree(
        root / "transfer/work",
        source / "work",
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "tools"),
    )
    shutil.copytree(root / "transfer/vendor", source / "vendor")
    if (root / "transfer/generation-source").exists():
        shutil.copytree(root / "transfer/generation-source", source / "generation-source")
    for name in ["inventory.json", "Dockerfile", "run_isolated.py", ".dockerignore"]:
        shutil.copy2(root / "transfer" / name, source / name)
    for name in ["measurements.json", "container-inspect.json"]:
        shutil.copy2(root / name, delivery / name)
    for name in ["preflight.json", "system-packages.txt", "isolation.json"]:
        shutil.copy2(root / "isolated" / name, delivery / name)
    if args.synthesis_evidence:
        shutil.copy2(args.synthesis_evidence, delivery / "failed-synthesis-attempt.json")
    metadata = {
        **report["delivery"],
        "bpm": 74,
        "meter": [4, 4],
        "bars": 46,
        "sections": [
            {
                "name": n,
                "first_bar_1based": a,
                "end_bar_exclusive": b,
                "start_frame": round((a - 1) * 4 * 60 / 74 * RATE),
                "end_frame": round((b - 1) * 4 * 60 / 74 * RATE),
            }
            for n, a, b in SECTIONS
        ],
        "stem_processing": report["limits"][2],
        "accepted": False,
    }
    dump(delivery / "metadata.json", metadata)
    (delivery / "README.md").write_text("""# Private Tactus production delivery

Two complete 46-bar candidates: baseline and bass-minus-3db. Both are unaccepted
fresh reconstructions. Bass gain changes from -3 to -6 dB; all four other stems
are byte-identical. Every WAV starts at frame zero and has the same length.
See metadata.json for tempo/sections and measurements.json for acceptance evidence.

Stems include their channel effects and gains BEFORE the nonlinear master bus.
Summing stems will not recreate the delivered mix. The original runtime manifests
retain their hashed WAV filenames; this delivery renames WAVs to role names.
SHA256SUMS.json verifies the delivery filenames; receipts retain run provenance.

source/work contains song.py, pyproject.toml and uv.lock; source/vendor contains
Tactus at the inventory commit. Original samples and native instruments are in
the separate private rebuild-inputs.tar.gz. They are not licensed for public
redistribution by this delivery. Extract that archive to rebuild the Docker image;
use README instructions in the experiment repository. The installed image can
also be restored from runtime-image.tar without fetching Python dependencies.

The source has explicit tool paths and @stage decorators. This delivery pins the
pads and bass pre-gain arrays as materials, preserving the host baseline performance.
The generation-source directory retains the original generators and provenance.
The original attempt to regenerate both instruments failed its reproduction gates;
this delivery proves portability of saved performances, not deterministic synthesis.
""")
    hashes = {
        str(p.relative_to(delivery)): hash_file(p)
        for p in sorted(delivery.rglob("*"))
        if p.is_file()
    }
    dump(delivery / "SHA256SUMS.json", hashes)
    archive = root / "delivery.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for path in sorted(delivery.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(delivery))
    unpacked = root / "delivery-unpacked"
    with zipfile.ZipFile(archive) as z:
        z.extractall(unpacked)
    restored = json.loads((unpacked / "SHA256SUMS.json").read_text())
    assert all(hash_file(unpacked / name) == digest for name, digest in restored.items())
    dump(
        root / "delivery-verification.json",
        {
            "files_verified": len(restored),
            "zip_sha256": hash_file(archive),
            "zip_bytes": archive.stat().st_size,
            "passed": True,
        },
    )


if __name__ == "__main__":
    main()
