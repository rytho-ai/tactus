"""Regression tests for the shipped examples: run each through `tactus.run` and compare
decoded PCM against baselines captured before the second-production-through-run port
(docs/blueprints/plans/2026-09-24-second-production-through-run.md, step 6).

Cases that need pinned materials skip, naming the missing digest, when this machine's
pool does not have them (`tactus.inputs.pool.has`); everything else always runs.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import soundfile as sf

from tactus import run
from tactus.inputs import pool

REPO_ROOT = Path(__file__).resolve().parents[1]
FUNCTIONAL = REPO_ROOT / "examples" / "functional"
PHONON_BALLAD = REPO_ROOT / "examples" / "phonon-ballad"
REAL_CHOP_FLIP = REPO_ROOT / "examples" / "real-chop-flip"

CHOP_SOURCE_DIGEST = "845406ed5823a0af0dc4eec0985a58398bda9b74310c7c9e76863e1b17db1497"
CHOP_GRID_DIGEST = "72aacde1e3184be72ef668f9f5ed67a606e7bf40b17bf05af7c9f02fd8de0b93"

PHONON_SOUNDFONT_DIGEST = "74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0"
PHONON_DRUM_DIGESTS = (
    "1ce5adcf77763bdbd3ad9492e1d7bf1f16b8b77877d183d21804a0c6aae42b4e",  # kick
    "9c1e1e3d5f4a777204ff60b4f578498bd9662e44deb48caabbff1bda027d0fba",  # snare
    "c1af239d645c4f6a4e769e10bde768bd2395f7a29ed60d68838ee77b7b98c984",  # hat
    "1e8ded3118c6530655e07ad1d4472bfa2cc1f2472ec954f7d7c576d56ffe8888",  # ride
)

# Expected decoded-PCM (int32) sha256 per output name, copied verbatim from the step-0
# baselines taken before this port, before any example code changed.
PHONON_SYNTHETIC_NONE = {
    "bass": "4946f61aae067810b94a6d780adaf5058e85b5a0bdf61a595df34bf0ae91ba44",
    "drums": "6f3d7da9ae1ef130b14da0a5b5867c72cd9bf4a3cb39aa028a174152180c7253",
    "guitar": "e5d6326d9796b089c11027e431bdb05c75c62bb0141c6db33e47c6a92f261558",
    "lead": "26f0951ee3276d977ebe07565b712df5e14bc7835476221075e364afa31af2dd",
    "mix": "76e1f6b5e5e6ce498e5afb2b674326c2d3f6aeb68756be4f406250fcd948f041",
    "piano": "5b89b7bc5a0c9f10bb0a8d8f60e0efcf03d15fcf474a3d2d1dfacd013fe4df97",
    "strings": "c56ed6530cbd4b0219d7c00adfd33331ad5d48f64a2a8f9270fb444035615a87",
}
PHONON_SAMPLED_ONE_SHOTS = {
    "bass": "4946f61aae067810b94a6d780adaf5058e85b5a0bdf61a595df34bf0ae91ba44",
    "drums": "fa079c475987af9aa0be14a7528999f25c8463ffb9183014d7f4d30c00b3eb21",
    "guitar": "34ed707983e23715e88826f1ecbe0f34fda731f83dec1c9e3ba9b883ce643c6d",
    "lead": "6ca5177d9a05e50d2cbcac202327e17e4852753d6d8f92e697383c98b5992416",
    "mix": "a4749aa7408a5bc4a3a007285da8e0f7ef8d47e072196e9cc56c17c8de1ba50b",
    "piano": "5f70c5070b265745fb20d355ce88531980c81ab5f63b8bd375ec03ff89482c70",
    "strings": "3f70ab066f1f5c6babcf59eaaecc7b0a96ec0d47874a747c10ee0aefd4689faa",
}
PHONON_SYNTHETIC_ONE_SHOTS = {
    "bass": "4946f61aae067810b94a6d780adaf5058e85b5a0bdf61a595df34bf0ae91ba44",
    "drums": "3190f5f945bf90a39e885a887c86b6a769ae1f317a3f10a84aeda621a3078d83",
    "guitar": "e5d6326d9796b089c11027e431bdb05c75c62bb0141c6db33e47c6a92f261558",
    "lead": "26f0951ee3276d977ebe07565b712df5e14bc7835476221075e364afa31af2dd",
    "mix": "9e71fe07ad635a1699048da2bc1dc9f89641ab43f04e12f9f624e0a1a159b635",
    "piano": "710aabb9cddc2a0e5b2e96da452399240593f7248c06156957869d881726e8fa",
    "strings": "c56ed6530cbd4b0219d7c00adfd33331ad5d48f64a2a8f9270fb444035615a87",
}
CHOP_FLIP_BASE = {
    "sample": "8a5cb7b798a5835e4500c5c2fe476832a0c489a122b39efa6e14d9fa316cbc0c",
    "drums": "8d67bcbdc913556fc27f71f2f118e812fe41bd049d542d324b83fcaff7503e29",
    "bass": "70a11d25af5f1d774c822772a71bb6de3286e879720dd140c39bcc5d531e326d",
    "mix": "1d5655182f341b8cf690d0d528a325e7636b960f2bac894c69deb6209e091052",
}

CHOP_FLIP_MATERIALS_PRESENT = pool.has(CHOP_SOURCE_DIGEST) and pool.has(CHOP_GRID_DIGEST)
PHONON_DRUMS_PRESENT = all(pool.has(digest) for digest in PHONON_DRUM_DIGESTS)
PHONON_SAMPLED_MATERIALS_PRESENT = PHONON_DRUMS_PRESENT and pool.has(PHONON_SOUNDFONT_DIGEST)


def decoded_pcm_sha256(path: Path) -> str:
    """sha256 of a WAV's decoded int32 PCM samples: content identity independent of encoding."""
    data, _rate = sf.read(path, dtype="int32", always_2d=True)
    return hashlib.sha256(data.tobytes()).hexdigest()


def assert_outputs_match(outputs: dict[str, str], expected: dict[str, str]) -> None:
    for name, expected_digest in expected.items():
        actual = decoded_pcm_sha256(Path(outputs[name]))
        assert actual == expected_digest, f"{name}: expected {expected_digest}, got {actual}"


def test_functional_example_runs(tmp_path):
    """examples/functional needs no external materials; it must always succeed."""
    result = run(FUNCTIONAL / "song.py", out=tmp_path / "functional")
    assert result["status"] == "ok"
    assert result["outputs"]
    for path in result["outputs"].values():
        assert Path(path).is_file()


def test_phonon_ballad_synthetic_none_matches_baseline(tmp_path):
    """The synthetic palette with no drums needs no external materials either."""
    result = run(
        PHONON_BALLAD / "song.py",
        out=tmp_path / "phonon-synthetic-none",
        params={"palette": "synthetic", "drums": "none"},
    )
    assert_outputs_match(result["outputs"], PHONON_SYNTHETIC_NONE)


@pytest.mark.skipif(
    not CHOP_FLIP_MATERIALS_PRESENT,
    reason=f"missing pool materials sha256:{CHOP_SOURCE_DIGEST} / sha256:{CHOP_GRID_DIGEST}; "
    "import with: tactus material add <source.wav> <grid.npy>",
)
def test_real_chop_flip_base_matches_baseline(tmp_path):
    result = run(REAL_CHOP_FLIP / "song.py", out=tmp_path / "chop-flip-base")
    assert_outputs_match(result["outputs"], CHOP_FLIP_BASE)


@pytest.mark.skipif(
    not PHONON_SAMPLED_MATERIALS_PRESENT,
    reason=f"missing pool materials: soundfont sha256:{PHONON_SOUNDFONT_DIGEST} and/or one or "
    f"more drum one-shots {PHONON_DRUM_DIGESTS}; import with: tactus material add <files>",
)
def test_phonon_ballad_sampled_one_shots_matches_baseline(tmp_path):
    result = run(
        PHONON_BALLAD / "song.py",
        out=tmp_path / "phonon-sampled-one-shots",
        params={"palette": "sampled", "drums": "one-shots"},
    )
    assert_outputs_match(result["outputs"], PHONON_SAMPLED_ONE_SHOTS)


@pytest.mark.skipif(
    not PHONON_DRUMS_PRESENT,
    reason=f"missing pool materials for drum one-shots {PHONON_DRUM_DIGESTS}; "
    "import with: tactus material add <files>",
)
def test_phonon_ballad_synthetic_one_shots_matches_baseline(tmp_path):
    result = run(
        PHONON_BALLAD / "song.py",
        out=tmp_path / "phonon-synthetic-one-shots",
        params={"palette": "synthetic", "drums": "one-shots"},
    )
    assert_outputs_match(result["outputs"], PHONON_SYNTHETIC_ONE_SHOTS)


@pytest.mark.skipif(
    not CHOP_FLIP_MATERIALS_PRESENT,
    reason=f"missing pool materials sha256:{CHOP_SOURCE_DIGEST} / sha256:{CHOP_GRID_DIGEST}; "
    "import with: tactus material add <source.wav> <grid.npy>",
)
def test_real_chop_flip_relocated_outside_repo_matches_baseline(tmp_path):
    """Materials resolve from the machine-wide pool, so a copy outside the repo still
    renders identical output. The relocated tree's `uv.lock` search starts above
    `tmp_path`, outside this repository, so its receipt reports whatever lock (or none)
    it finds walking upward from there — never the repository's own lock.
    """
    relocated = tmp_path / "real-chop-flip-relocated"
    shutil.copytree(REAL_CHOP_FLIP, relocated, ignore=shutil.ignore_patterns("__pycache__"))
    result = run(relocated / "song.py", out=tmp_path / "chop-flip-relocated-out")
    assert_outputs_match(result["outputs"], CHOP_FLIP_BASE)
