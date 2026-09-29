"""Optional librosa oracle and frozen loudness answers, available without pyloudnorm."""

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def librosa():
    return pytest.importorskip(
        "librosa", reason="Reference comparison: run uv run --extra librosa pytest"
    )


@pytest.fixture(scope="session")
def loudness_reference():
    data = json.loads((Path(__file__).parent / "fixtures/loudness-reference.json").read_text())

    def lookup(case, audio, rate):
        record = data["cases"][case]
        assert record["sample_rate"] == rate
        assert record["shape"] == list(audio.shape)
        # Input hashes document the capture. Do not require bitwise libm/random
        # generation across platforms; numerical tolerances live in each test.
        return record["expected"]

    return lookup
