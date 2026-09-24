"""Exercise the public functional runner, publication and isolated candidate workflow."""

from __future__ import annotations

import json
import os
import py_compile
import runpy
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import AudioRef, RunError, run
from tactus.material import MaterialStore

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "functional"


def source(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "authoring"
    root.mkdir(exist_ok=True)
    path = root / "song.py"
    path.write_text(text, encoding="utf-8")
    return path


def read(path: str) -> dict:
    return json.loads(Path(path).read_text())


def test_production_candidates_acceptance_and_clip_bank(tmp_path, monkeypatch):
    project = tmp_path / "authoring"
    shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("__pycache__"))
    entry = project / "song.py"
    original = entry.read_bytes()
    cwd = Path.cwd()
    base = run(entry, out=tmp_path / "base")
    candidate = run(entry, out=tmp_path / "candidate", params={"bass_gain": 0.4})
    again = run(entry, out=tmp_path / "again")
    assert Path.cwd() == cwd
    assert entry.read_bytes() == original
    b, c, a = [read(result["manifest"]) for result in (base, candidate, again)]
    assert b == a
    assert b["outputs"]["stem:texture"] == c["outputs"]["stem:texture"]
    for name in ("mix", "stem:bass"):
        assert b["outputs"][name] != c["outputs"][name]
    assert read(base["receipt"])["parameters"] == {"bass_gain": 0.8}
    assert read(candidate["receipt"])["parameters"] == {"bass_gain": 0.4}
    assert "parts.py" in read(base["receipt"])["source_files"]

    # Compare exported audio with ordinary Python executing the same musical functions.
    monkeypatch.syspath_prepend(str(project))
    direct = runpy.run_path(str(entry))["render"]()
    for name, expected in direct["outputs"].items():
        actual, rate = sf.read(base["outputs"][name])
        assert rate == direct["sample_rate"]
        assert sf.info(base["outputs"][name]).subtype == "PCM_24"
        np.testing.assert_allclose(actual, expected, atol=2**-23, rtol=0)
    assert not np.allclose(
        direct["outputs"]["mix"],
        direct["outputs"]["stem:bass"][:, None] + direct["outputs"]["stem:texture"],
    )

    # Accept the candidate via an explicit source edit; no automatic promotion is claimed.
    entry.write_text(original.decode().replace("bass_gain=0.8", "bass_gain=0.4"))
    accepted = run(entry, out=tmp_path / "accepted")
    assert read(accepted["manifest"]) == c
    assert read(accepted["receipt"])["source_files"] != read(candidate["receipt"])["source_files"]

    clips = run(project / "clips.py", out=tmp_path / "clips", params={"gain": 0.3})
    outputs = read(clips["manifest"])["outputs"]
    assert outputs.keys() == {"short", "long"}
    assert {ref["frames"] for ref in outputs.values()} == {9600, 30000}

    # Saved outputs remain integrity-checkable with source removed.
    moved = tmp_path / "moved"
    shutil.move(tmp_path / "base", moved)
    shutil.rmtree(project)
    store = MaterialStore(moved / "materials", b["sample_rate"])
    for ref in b["outputs"].values():
        assert len(store.read(AudioRef(**ref))) == ref["frames"]
    ref = AudioRef(**b["outputs"]["mix"])
    wav = moved / "materials" / "audio" / f"{ref.sha256}.wav"
    payload = wav.read_bytes()
    wav.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    with pytest.raises(ValueError, match="hash mismatch"):
        store.read(ref)


def test_fresh_module_state_relative_assets_and_parameter_snapshot(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
import helper
from pathlib import Path

if __name__ == "__main__":
    raise RuntimeError("must not execute the main block")

def render(*, options={"levels": [0.1]}, required):
    helper.calls += 1
    options["levels"].append(0.9)
    value = float(Path("asset.txt").read_text()) * helper.calls
    return {"sample_rate": 8000, "outputs": {"../label:clip": np.full(8, value)}}
""",
    )
    (entry.parent / "helper.py").write_text("calls = 0\n")
    (entry.parent / "asset.txt").write_text("0.1")
    params = {"required": None}
    first = run(entry, out=entry.parent / "out-a", params=params)
    second = run(entry, out=entry.parent / "out-b", params=params)
    assert read(first["manifest"]) == read(second["manifest"])
    assert params == {"required": None}
    assert read(first["receipt"])["parameters"] == {
        "required": None,
        "options": {"levels": [0.1]},
    }
    assert all(Path(p).is_relative_to(entry.parent / "out-a") for p in first["outputs"].values())


def test_helper_revision_ignores_stale_timestamp_bytecode(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
from helper import GAIN
def render():
    return {"sample_rate": 8000, "outputs": {"clip": np.full(8, GAIN)}}
""",
    )
    helper = entry.parent / "helper.py"
    helper.write_text("GAIN = 0.1\n")
    original_stat = helper.stat()
    py_compile.compile(str(helper), doraise=True)
    helper.write_text("GAIN = 0.2\n")
    os.utime(helper, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    result = run(entry, out=tmp_path / "out")
    actual, _ = sf.read(result["outputs"]["clip"])
    np.testing.assert_allclose(actual, 0.2, atol=2**-23, rtol=0)


@pytest.mark.parametrize(
    "expression",
    [
        "None",
        "{'sample_rate': True, 'outputs': {'a': np.zeros(8)}}",
        "{'sample_rate': 0, 'outputs': {'a': np.zeros(8)}}",
        "{'sample_rate': 8000, 'outputs': {}}",
        "{'sample_rate': 8000, 'outputs': {'': np.zeros(8)}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.zeros(0)}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.zeros((8, 3))}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.array([np.nan])}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.array([1.000000001])}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.array([-2**63], dtype=np.int64)}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.array([1j])}}",
        "{'sample_rate': 8000, 'outputs': {'a': np.array([True])}}",
        "{'sample_rate': 8000, 'outputs': {'a': [0.1]}}",
    ],
)
def test_invalid_outputs_never_publish(tmp_path, expression):
    entry = source(tmp_path, f"import numpy as np\ndef render():\n    return {expression}\n")
    out = tmp_path / "out"
    with pytest.raises(RunError) as failure:
        run(entry, out=out)
    assert (failure.value.code, failure.value.phase) == ("invalid_output", "validate")
    assert not out.exists()


@pytest.mark.parametrize(
    "body,params",
    [
        ("def render(positional=1): pass", {}),
        ("def render(**kwargs): pass", {}),
        ("def render(*, required): pass", {}),
        ("def render(): pass", {"unknown": 1}),
        ("def render(*, value=float('nan')): pass", {}),
        ("async def render(): pass", {}),
        ("def render(): yield 1", {}),
        ("render = None", {}),
    ],
)
def test_binding_errors(tmp_path, body, params):
    entry = source(tmp_path, body)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", params=params)
    assert failure.value.code == "invalid_parameters"
    assert failure.value.exit_code == 2


@pytest.mark.parametrize("params", [{1: "bad"}, {"x": float("inf")}, {"x": (1, 2)}, []])
def test_python_request_validation(tmp_path, params):
    entry = source(tmp_path, "raise RuntimeError('must not execute')")
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", params=params)
    assert failure.value.code == "invalid_request"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "body,code,phase",
    [
        ("this is invalid syntax!", "load_failed", "load"),
        ("raise ImportError('missing instrument')", "load_failed", "load"),
        ("def render(): raise RuntimeError('processor broke')", "execution_failed", "execute"),
        ("def render(): raise SystemExit(0)", "execution_failed", "execute"),
        ("import os\ndef render(): os._exit(0)", "worker_failed", "execute"),
        ("import os\ndef render(): os._exit(9)", "worker_failed", "execute"),
    ],
)
def test_execution_failures(tmp_path, body, code, phase):
    entry = source(tmp_path, body)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert (failure.value.code, failure.value.phase) == (code, phase)
    assert not (tmp_path / "out").exists()


def test_existing_destination_is_untouched_before_source_loading(tmp_path):
    entry = source(tmp_path, "from pathlib import Path\nPath('executed').touch()\n")
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    with pytest.raises(RunError, match="already exists") as failure:
        run(entry, out=out)
    assert failure.value.code == "output_exists"
    assert (out / "keep.txt").read_text() == "keep"
    assert not (entry.parent / "executed").exists()


@pytest.mark.parametrize("target", ["song.py", "uv.lock"])
def test_changed_source_or_lock_fails_attribution(tmp_path, target):
    entry = source(
        tmp_path,
        f"""import numpy as np
from pathlib import Path
def render():
    with Path({target!r}).open('a') as file:
        file.write('\\n# changed\\n')
    return {{"sample_rate": 8000, "outputs": {{"a": np.zeros(8)}}}}
""",
    )
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert failure.value.code == "source_changed"
    assert not (tmp_path / "out").exists()


def test_partial_publication_is_cleaned(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
from tactus.material import MaterialStore
original = MaterialStore.add
calls = 0
def fail_second(self, audio):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("disk failure after first material")
    return original(self, audio)
MaterialStore.add = fail_second
def render():
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8), "b": np.ones(8) * 0.1}}
""",
    )
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert failure.value.code == "publication_failed"
    assert not (tmp_path / "out").exists()
