"""Exercise the public functional runner, publication and isolated candidate workflow."""

from __future__ import annotations

import hashlib
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
from tactus.store import OutputStore

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
    assert b["outputs"]["stem-texture"] == c["outputs"]["stem-texture"]
    for name in ("mix", "stem-bass"):
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
        direct["outputs"]["stem-bass"][:, None] + direct["outputs"]["stem-texture"],
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
    store = OutputStore(moved, b["sample_rate"])
    ref_fields = ("sha256", "frames", "channels", "file")
    for name, ref in b["outputs"].items():
        assert len(store.read(AudioRef(**{key: ref[key] for key in ref_fields}))) == ref["frames"]
        assert ref["file"] == f"{name}-{ref['sha256'][:8]}.wav"
        assert (moved / ref["file"]).exists()
    ref = AudioRef(**{key: b["outputs"]["mix"][key] for key in ref_fields})
    wav = moved / ref.file
    payload = wav.read_bytes()
    wav.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    with pytest.raises(ValueError, match="hash mismatch"):
        store.read(ref)
    for forged in ("../mix-" + ref.sha256[:8] + ".wav", "mix-00000000.wav"):
        with pytest.raises(ValueError, match="does not match its reference"):
            store.read(AudioRef(ref.sha256, ref.frames, ref.channels, forged))


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
    return {"sample_rate": 8000, "outputs": {"label-clip": np.full(8, value)}}
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
    "expression,diagnostic",
    [
        ("None", "got NoneType"),
        ("(8000, np.zeros(8))", "got tuple"),
        ("{'outputs': {'a': np.zeros(8)}}", "missing fields: sample_rate"),
        (
            "{'sample_rate': 8000, 'outputs': {'a': np.zeros(8)}, 'metadata': {}}",
            "unexpected fields: 'metadata'",
        ),
        ("{3: 'extra'}", "unexpected fields: 3"),
    ],
)
def test_invalid_result_explains_the_contract(tmp_path, expression, diagnostic):
    entry = source(tmp_path, f"import numpy as np\ndef render():\n    return {expression}\n")
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert (failure.value.code, failure.value.phase) == ("invalid_output", "validate")
    assert diagnostic in str(failure.value)
    assert '"sample_rate": 48000' in str(failure.value)
    assert '"outputs": {"mix": audio}' in str(failure.value)
    assert not (tmp_path / "out").exists()


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
def test_source_or_lock_edited_during_a_run_keeps_the_run_and_says_so(tmp_path, target):
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
    if target == "uv.lock":
        (entry.parent / "uv.lock").write_text("version = 1\n")
    start = hashlib.sha256((entry.parent / target).read_bytes()).hexdigest()
    result = run(entry, out=tmp_path / "out")
    receipt = read(result["receipt"])
    changed = receipt["source_changed"]
    assert result["source_changed"] == changed
    assert changed["certain"] is False and target in changed["message"]
    if target == "song.py":
        # The receipt keeps the start inventory: the bytes this run loaded.
        assert receipt["source_files"]["song.py"] == start
        [edit] = changed["files"]
        assert edit["path"] == "song.py" and edit["imported"] is True
        assert edit["start_sha256"] == start != edit["end_sha256"]
        assert changed["dependency_lock"] is None
    else:
        assert receipt["dependency_lock"]["sha256"] == start
        assert changed["files"] == []
        assert changed["dependency_lock"]["start"]["sha256"] == start
    assert Path(result["outputs"]["a"]).is_file()


def test_edit_to_an_unimported_file_is_reported_as_not_affecting_the_audio(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
from pathlib import Path
def render():
    Path("scratch.py").write_text("print('changed')\\n")
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8)}}
""",
    )
    (entry.parent / "scratch.py").write_text("print('start')\n")
    result = run(entry, out=tmp_path / "out")
    changed = read(result["receipt"])["source_changed"]
    assert changed["certain"] is True
    assert [(f["path"], f["imported"]) for f in changed["files"]] == [("scratch.py", False)]


def test_unchanged_source_reports_no_change(tmp_path):
    entry = source(
        tmp_path,
        "import numpy as np\ndef render():\n"
        "    return {'sample_rate': 8000, 'outputs': {'a': np.zeros(8)}}\n",
    )
    result = run(entry, out=tmp_path / "out")
    assert read(result["receipt"])["source_changed"] is None
    assert "source_changed" not in result


def test_partial_delivery_is_cleaned_but_completed_render_survives(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
from tactus.store import OutputStore
original = OutputStore.add
calls = 0
def fail_second(self, name, audio):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("disk failure after first material")
    return original(self, name, audio)
OutputStore.add = fail_second
def render():
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8), "b": np.ones(8) * 0.1}}
""",
    )
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert failure.value.code == "publication_failed"
    assert (tmp_path / "out" / "render.json").is_file()
    assert not (tmp_path / "out" / "manifest.json").exists()
    assert not list((tmp_path / "out").glob("*.wav"))


def test_output_files_are_named_at_the_run_root(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
def render():
    return {"sample_rate": 8000, "outputs": {"drums-core": np.zeros(8)}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    manifest = read(result["manifest"])
    ref = manifest["outputs"]["drums-core"]
    expected = tmp_path / "out" / f"drums-core-{ref['sha256'][:8]}.wav"
    assert expected.is_file()
    assert result["outputs"]["drums-core"] == str(expected)
    assert hashlib.sha256(expected.read_bytes()).hexdigest() == ref["sha256"]
    # No materials/ subdirectory: outputs land directly at the top of --out.
    assert not (tmp_path / "out" / "materials").exists()


def test_over_full_scale_output_publishes_clipped_with_reported_peak_and_count(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
def render():
    audio = np.array([1.5, -1.5, 0.2, 2.0], dtype=np.float32)
    return {"sample_rate": 8000, "outputs": {"a": audio}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    manifest = read(result["manifest"])
    ref = manifest["outputs"]["a"]
    assert ref["clipped_samples"] == 3
    assert ref["peak_dbfs"] == pytest.approx(20 * np.log10(2.0), abs=0.01)
    assert result["levels"]["a"] == {"peak_dbfs": ref["peak_dbfs"], "clipped_samples": 3}
    audio, _ = sf.read(result["outputs"]["a"])
    assert np.max(np.abs(audio)) <= 1.0 + 1e-6
    np.testing.assert_allclose(audio, np.clip([1.5, -1.5, 0.2, 2.0], -1, 1), atol=2**-6)


def test_silent_output_reports_null_peak_dbfs(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
def render():
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8)}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    manifest = read(result["manifest"])
    assert manifest["outputs"]["a"]["peak_dbfs"] is None
    assert manifest["outputs"]["a"]["clipped_samples"] == 0
    assert result["levels"]["a"] == {"peak_dbfs": None, "clipped_samples": 0}


@pytest.mark.parametrize("name", ["a/b", "../x", ".hidden", ""])
def test_unsafe_output_names_are_rejected(tmp_path, name):
    entry = source(
        tmp_path,
        f"""import numpy as np
def render():
    return {{"sample_rate": 8000, "outputs": {{{name!r}: np.zeros(8)}}}}
""",
    )
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out")
    assert failure.value.code == "invalid_output"
    assert not (tmp_path / "out").exists()


def test_workspace_member_receipt_records_the_workspace_lock(tmp_path):
    workspace = tmp_path / "showcase"
    work = workspace / "works" / "dig"
    work.mkdir(parents=True)
    (workspace / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["works/*"]\n')
    lock = workspace / "uv.lock"
    lock.write_text("version = 1\n")
    (work / "pyproject.toml").write_text('[project]\nname="dig"\ndependencies=["tactus"]\n')
    entry = work / "song.py"
    entry.write_text(
        "import numpy as np\n"
        "def render():\n"
        "    return {'sample_rate': 8000, 'outputs': {'a': np.zeros(8)}}\n"
    )
    receipt = read(run(entry, out=work / "runs" / "a")["receipt"])
    assert receipt["dependency_lock"] == {
        "path": str(lock),
        "sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    }
