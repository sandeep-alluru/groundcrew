"""Subprocess-based CLI tests for openveritas."""

from __future__ import annotations

import subprocess
import sys


def test_cli_help():
    r = subprocess.run(
        [sys.executable, "-m", "openveritas.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20


def test_cli_log(tmp_path):
    db = str(tmp_path / "r.db")
    r = subprocess.run(
        [sys.executable, "-m", "openveritas.cli", "--db", db, "log"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
