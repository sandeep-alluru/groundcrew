"""Tests for groundcrew.content_diff — FileDiff, ContentDiff, content_diff."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundcrew.content_diff import ContentDiff, FileDiff, content_diff
from groundcrew.snapshot import StateSnapshot


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_content_diff_empty_snapshots(tmp_dir: Path) -> None:
    """Two empty directories yield a ContentDiff with no file diffs."""
    snap_a = StateSnapshot.capture(tmp_dir)
    snap_b = StateSnapshot.capture(tmp_dir)
    result = content_diff(snap_a, snap_b, tmp_dir)
    assert isinstance(result, ContentDiff)
    assert result.file_diffs == []
    assert result.total_added == 0
    assert result.total_removed == 0


def test_content_diff_added_file(tmp_dir: Path) -> None:
    """A new file should appear as an added FileDiff with added_lines > 0."""
    snap_a = StateSnapshot.capture(tmp_dir)
    (tmp_dir / "new.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    snap_b = StateSnapshot.capture(tmp_dir)

    result = content_diff(snap_a, snap_b, tmp_dir)
    assert len(result.file_diffs) == 1
    fd = result.file_diffs[0]
    assert fd.path == "new.txt"
    assert fd.added_lines == 3
    assert fd.removed_lines == 0
    assert result.total_added == 3


def test_content_diff_removed_file(tmp_dir: Path) -> None:
    """A removed file should appear as a FileDiff and not cause an error."""
    (tmp_dir / "old.txt").write_text("hello\n", encoding="utf-8")
    snap_a = StateSnapshot.capture(tmp_dir)
    (tmp_dir / "old.txt").unlink()
    snap_b = StateSnapshot.capture(tmp_dir)

    result = content_diff(snap_a, snap_b, tmp_dir)
    assert any(fd.path == "old.txt" for fd in result.file_diffs)


def test_content_diff_unified_diff_present(tmp_dir: Path) -> None:
    """Added files should have non-empty unified_diff."""
    snap_a = StateSnapshot.capture(tmp_dir)
    (tmp_dir / "code.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    snap_b = StateSnapshot.capture(tmp_dir)

    result = content_diff(snap_a, snap_b, tmp_dir)
    fd = result.file_diffs[0]
    assert len(fd.unified_diff) > 0


def test_content_diff_no_change(tmp_dir: Path) -> None:
    """Unchanged files should not appear in file_diffs."""
    (tmp_dir / "stable.txt").write_text("no change\n", encoding="utf-8")
    snap_a = StateSnapshot.capture(tmp_dir)
    snap_b = StateSnapshot.capture(tmp_dir)

    result = content_diff(snap_a, snap_b, tmp_dir)
    assert result.file_diffs == []


def test_content_diff_multiple_files(tmp_dir: Path) -> None:
    """Multiple added files all appear in file_diffs."""
    snap_a = StateSnapshot.capture(tmp_dir)
    for i in range(3):
        (tmp_dir / f"file{i}.txt").write_text(f"content {i}\n", encoding="utf-8")
    snap_b = StateSnapshot.capture(tmp_dir)

    result = content_diff(snap_a, snap_b, tmp_dir)
    assert len(result.file_diffs) == 3
    assert result.total_added == 3
