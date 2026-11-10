"""Native probes must survive loader errors, process crashes and hangs."""

import json
import subprocess
import sys

import pytest

from tactus import _native_health as health
from tactus.cli import main


def test_real_native_engines_compute():
    report = health.check_native_dependencies()
    assert all(item["status"] == "ok" for item in report.values()), report
    assert set(report) == {
        "pyqmdsp", "pytimestretch.rubberband",
        "pytimestretch.signalsmith", "pytimestretch.paulstretch",
    }


@pytest.mark.parametrize("script, message", [
    ("raise ImportError('incompatible architecture: x86_64')", "incompatible architecture"),
    ("import os; os._exit(7)", "7"),
])
def test_probe_reports_child_failures(script, message):
    result = health._probe(script)
    assert result["status"] == "error"
    assert message in result["error"]


def test_probe_times_out(monkeypatch):
    monkeypatch.setattr(health, "_TIMEOUT", 0.1)
    result = health._probe("import time; time.sleep(10)")
    assert result["status"] == "error"
    assert "timed out" in result["error"]


def test_probe_uses_running_python_and_ignores_pythonpath(monkeypatch):
    def run(command, **kwargs):
        assert command[:3] == [sys.executable, "-I", "-c"]
        assert kwargs["timeout"] > 0
        return subprocess.CompletedProcess(command, 0, "native output", "native warning")
    monkeypatch.setattr(health.subprocess, "run", run)
    assert health._probe("pass") == {"status": "ok"}


def test_doctor_reports_failure_without_losing_environment(monkeypatch, capsys):
    monkeypatch.setattr(health, "check_native_dependencies", lambda: {
        "pyqmdsp": {"status": "error", "error": "incompatible architecture"},
        "pytimestretch.rubberband": {"status": "ok"},
    })
    assert main(["doctor"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert report["architecture"]
    assert report["interpreter"] == sys.executable
    assert report["native_dependencies"]["pyqmdsp"]["status"] == "error"
