"""Image/data contract, color scales, real CLI artifacts and failure cleanup."""

import base64
import json
import struct
import xml.etree.ElementTree as ET
import zlib

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import image, rhythm, spectral
from tactus.cli import main
from tactus.inputs.pool import hash_file

NS = {"s": "http://www.w3.org/2000/svg"}


def parsed(svg):
    root = ET.fromstring(svg)
    return root, json.loads(root.find("s:metadata", NS).text)


@pytest.mark.parametrize(
    "fn",
    [spectral.cqt, spectral.vqt, spectral.mel, spectral.chroma, spectral.mfcc, rhythm.tempogram],
)
def test_image_metadata_axes_and_nonmutation(fn):
    result = fn(np.zeros(1000), 22050)
    before = {key: value.copy() for key, value in result.items() if isinstance(value, np.ndarray)}
    root, meta = parsed(image(result, title="<A&B>"))
    assert root.find("s:title", NS).text == "<A&B>"
    assert meta["vmin"] < meta["vmax"]
    assert meta["row_spacing"] == "matrix index"
    for key, value in before.items():
        np.testing.assert_array_equal(result[key], value)
    assert len(root.findall(".//s:image", NS)) == 2
    for node in root.findall(".//s:image", NS):
        raw = base64.b64decode(node.attrib["href"].split(",")[1])
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    _, fixed = parsed(image(result, vmin=-30, vmax=10))
    assert (fixed["vmin"], fixed["vmax"]) == (-30, 10)


def test_png_orientation_and_values():
    result = {
        "magnitude": np.array([[0.01, 0.01], [1, 1]]),
        "freqs_hz": np.array([110, 220]),
        "times_s": np.array([0, 1]),
    }
    root, _ = parsed(image(result, vmin=-40, vmax=0))
    raw = base64.b64decode(root.find(".//s:image", NS).attrib["href"].split(",")[1])
    pos = 8
    compressed = b""
    while pos < len(raw):
        size = struct.unpack("!I", raw[pos : pos + 4])[0]
        if raw[pos + 4 : pos + 8] == b"IDAT":
            compressed += raw[pos + 8 : pos + 8 + size]
        pos += size + 12
    pixels = zlib.decompress(compressed)
    # Higher-frequency row at top: palette's bright endpoint, low row dark.
    assert pixels[:7] == b"\0" + bytes([253, 225, 140]) * 2
    assert pixels[7:] == b"\0" + bytes([12, 10, 35]) * 2


def test_image_time_reduction_and_invalid_scaling():
    result = {
        "tempogram": np.ones((3, 3000)),
        "bpms": np.array([60, 120, 240]),
        "times_s": np.arange(3000) * 0.01,
    }
    _, meta = parsed(image(result))
    assert meta["shape"] == [3, 3000]
    assert meta["display_shape"] == [3, 1200]
    for kwargs in ({"vmin": 1, "vmax": 1}, {"vmin": float("nan")}, {"vmax": -1}):
        with pytest.raises(ValueError):
            image(result, **kwargs)


@pytest.mark.parametrize(
    "category,name",
    [
        ("spectral", "cqt"),
        ("spectral", "vqt"),
        ("spectral", "mel"),
        ("spectral", "chroma"),
        ("spectral", "mfcc"),
        ("rhythm", "tempogram"),
    ],
)
def test_cli_numeric_and_image_roundtrip(tmp_path, capsys, category, name):
    rate = 22050
    x = 0.2 * np.sin(2 * np.pi * 220 * np.arange(2205) / rate)
    wav = tmp_path / "input.wav"
    sf.write(wav, x, rate, subtype="DOUBLE")
    out = tmp_path / "analysis"
    args = ["analyze", category, name, str(wav), "--out", str(out), "--image"]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    module = spectral if category == "spectral" else rhythm
    direct = getattr(module, name)(x, rate)
    for key, value in direct.items():
        if isinstance(value, np.ndarray):
            ref = report["result"][key]
            with np.load(ref["file"]) as arrays:
                np.testing.assert_array_equal(arrays[ref["key"]], value)
    image_path = next(out.rglob("image.svg"))
    assert hash_file(image_path) == report["artifacts"]["image.svg"]["sha256"]
    assert json.loads(image_path.with_name("result.json").read_text()) == report
    assert "image" not in report["params"]
    assert image_path.read_text() == image(direct, title=f"{category}.{name}")
    # Different visualization settings coexist; same request retains no-overwrite behavior.
    assert main(args + ["--image-min", "-90", "--image-max", "10"]) == 0
    capsys.readouterr()
    assert len(list(out.rglob("image.svg"))) == 2
    assert main(args) != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "output_exists"


def test_bad_image_request_cleans_up_and_requires_out(tmp_path, capsys):
    wav = tmp_path / "input.wav"
    sf.write(wav, np.zeros(10), 22050)
    args = ["analyze", "spectral", "cqt", str(wav)]
    assert main(args + ["--image"]) != 0
    assert "requires --out" in capsys.readouterr().out
    assert main(args + ["--image-min", "-80"]) != 0
    assert "require --image" in capsys.readouterr().out
    out = tmp_path / "failed"
    assert main(args + ["--out", str(out), "--image", "--image-min", "10", "--image-max", "0"]) != 0
    capsys.readouterr()
    assert not list(out.iterdir())


def test_custom_image_named_parameter_is_not_a_builtin_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TACTUS_PROJECT_ROOT", raising=False)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="custom-image-test"\nversion="0.0.0"\n'
        '[tool.tactus.analysis]\n"custom.picture"="custom_picture:analyze"\n'
    )
    (tmp_path / "custom_picture.py").write_text(
        'def analyze(audio, sample_rate, *, image: str = "custom", image_min: float = 3):\n'
        '    return {"value": image, "minimum": image_min}\n'
    )
    sf.write(tmp_path / "input.wav", np.zeros(20), 22050)
    assert main(["analyze", "custom", "picture", "input.wav", "--image", "mine"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result"] == {"value": "mine", "minimum": 3}
    assert "visualization" not in report
