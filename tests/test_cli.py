"""Smoke checks for the independent package and command entry point."""

from __future__ import annotations

import json

import pytest

from tactus.cli import main


def test_doctor_reports_bootstrap_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["package"] == "tactus"
    assert report["version"] == "0.1.0"
    assert report["status"] == "bootstrap"
    assert report["python"]


def test_version_uses_distribution_metadata(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == "tactus 0.1.0"
