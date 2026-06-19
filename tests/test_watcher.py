"""Tests for groundcrew.watcher — DirectoryWatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from groundcrew.snapshot import StateSnapshot
from groundcrew.watcher import DirectoryWatcher


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_take_baseline_returns_snapshot(watch_dir: Path) -> None:
    """take_baseline() should return a StateSnapshot."""
    watcher = DirectoryWatcher(root=watch_dir)
    snap = watcher.take_baseline()
    assert isinstance(snap, StateSnapshot)


def test_check_no_changes(watch_dir: Path) -> None:
    """check() after take_baseline() with no changes should return empty list."""
    watcher = DirectoryWatcher(root=watch_dir)
    watcher.take_baseline()
    changes = watcher.check()
    assert changes == []


def test_check_detects_added_file(watch_dir: Path) -> None:
    """check() should detect a newly added file."""
    watcher = DirectoryWatcher(root=watch_dir)
    watcher.take_baseline()
    (watch_dir / "secret.txt").write_text("oops", encoding="utf-8")
    changes = watcher.check()
    assert len(changes) == 1
    assert "ADDED" in changes[0]
    assert "secret.txt" in changes[0]


def test_check_detects_modified_file(watch_dir: Path) -> None:
    """check() should detect a modified file."""
    f = watch_dir / "data.txt"
    f.write_text("original", encoding="utf-8")
    watcher = DirectoryWatcher(root=watch_dir)
    watcher.take_baseline()
    f.write_text("modified content", encoding="utf-8")
    changes = watcher.check()
    assert any("MODIFIED" in c for c in changes)


def test_check_authorized_path_ignored(watch_dir: Path) -> None:
    """Files in authorized_paths should not appear in changes."""
    watcher = DirectoryWatcher(root=watch_dir, authorized_paths=["allowed.txt"])
    watcher.take_baseline()
    (watch_dir / "allowed.txt").write_text("authorized", encoding="utf-8")
    (watch_dir / "intruder.txt").write_text("bad", encoding="utf-8")
    changes = watcher.check()
    paths = " ".join(changes)
    assert "allowed.txt" not in paths
    assert "intruder.txt" in paths


def test_check_raises_without_baseline(watch_dir: Path) -> None:
    """check() without a prior take_baseline() should raise RuntimeError."""
    watcher = DirectoryWatcher(root=watch_dir)
    with pytest.raises(RuntimeError, match="take_baseline"):
        watcher.check()


def test_watch_calls_callback_on_change(watch_dir: Path) -> None:
    """watch() should invoke the callback when changes are detected."""
    called_with: list[list[str]] = []

    watcher = DirectoryWatcher(root=watch_dir, interval_seconds=0.0)
    watcher.take_baseline()
    (watch_dir / "alert.txt").write_text("intruder!", encoding="utf-8")

    def _cb(changes: list[str]) -> None:
        called_with.append(changes)

    # max_checks=1 so it exits immediately
    watcher.watch(callback=_cb, max_checks=1)
    assert len(called_with) == 1
    assert any("alert.txt" in c for c in called_with[0])


def test_watch_no_callback_when_no_changes(watch_dir: Path) -> None:
    """watch() should not invoke the callback when nothing changes."""
    called: list[list[str]] = []

    watcher = DirectoryWatcher(root=watch_dir, interval_seconds=0.0)
    watcher.take_baseline()
    watcher.watch(callback=called.append, max_checks=2)
    assert called == []
