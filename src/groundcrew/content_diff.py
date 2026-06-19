"""Content-level (line-by-line) diff between two snapshots."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from groundcrew.snapshot import StateSnapshot


@dataclass
class FileDiff:
    """Line-level diff for a single file.

    Attributes:
        path: Relative path to the file.
        before_lines: Number of lines in the before version (0 for new files).
        after_lines: Number of lines in the after version (0 for deleted files).
        added_lines: Number of lines added.
        removed_lines: Number of lines removed.
        unified_diff: Standard unified diff string.
        is_binary: True if the file was detected as binary.
    """

    path: str
    before_lines: int
    after_lines: int
    added_lines: int
    removed_lines: int
    unified_diff: str
    is_binary: bool = False


@dataclass
class ContentDiff:
    """Aggregated line-level diff across all changed files.

    Attributes:
        file_diffs: Per-file diff results.
        total_added: Sum of added lines across all files.
        total_removed: Sum of removed lines across all files.
    """

    file_diffs: list[FileDiff] = field(default_factory=list)
    total_added: int = 0
    total_removed: int = 0


def _is_binary(data: bytes) -> bool:
    """Heuristic: treat as binary if it contains a null byte in the first 8 KB."""
    return b"\x00" in data[:8192]


def _read_lines(path: Path) -> tuple[list[str], bool]:
    """Read a file and return (lines, is_binary)."""
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return [], False
    if _is_binary(data):
        return [], True
    try:
        text = data.decode("utf-8", errors="replace")
    except ValueError:
        return [], True
    return text.splitlines(keepends=True), False


def _make_file_diff(
    rel_path: str,
    root: Path,
    before_exists: bool,
    after_exists: bool,
) -> FileDiff:
    """Generate a FileDiff for a single file path."""
    abs_path = root / rel_path

    if before_exists and after_exists:
        # Modified — we re-read the current (after) version from disk.
        # For a true before/after we would need two root directories; since
        # StateSnapshot only stores hashes, we diff empty vs current for adds
        # and current vs empty for removes. For modifications we diff the
        # before snapshot hash info (not content) — so we produce a unified
        # diff of the current file against an empty baseline to represent "changed".
        after_lines, is_bin = _read_lines(abs_path)
        if is_bin:
            return FileDiff(
                path=rel_path,
                before_lines=0,
                after_lines=0,
                added_lines=0,
                removed_lines=0,
                unified_diff="(binary file)",
                is_binary=True,
            )
        # We don't have the before content (only its hash), so emit a +/= diff
        added = len(after_lines)
        diff_text = "".join(
            difflib.unified_diff(
                [],
                after_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
        )
        return FileDiff(
            path=rel_path,
            before_lines=0,
            after_lines=len(after_lines),
            added_lines=added,
            removed_lines=0,
            unified_diff=diff_text,
            is_binary=False,
        )

    if after_exists:
        # Added
        after_lines, is_bin = _read_lines(abs_path)
        if is_bin:
            return FileDiff(path=rel_path, before_lines=0, after_lines=0,
                            added_lines=0, removed_lines=0,
                            unified_diff="(binary file)", is_binary=True)
        diff_text = "".join(
            difflib.unified_diff([], after_lines,
                                 fromfile="/dev/null", tofile=f"b/{rel_path}")
        )
        return FileDiff(
            path=rel_path,
            before_lines=0,
            after_lines=len(after_lines),
            added_lines=len(after_lines),
            removed_lines=0,
            unified_diff=diff_text,
        )

    # Removed — file no longer on disk; we can only report it was removed
    return FileDiff(
        path=rel_path,
        before_lines=0,
        after_lines=0,
        added_lines=0,
        removed_lines=0,
        unified_diff=f"--- a/{rel_path}\n+++ /dev/null\n(file removed)",
    )


def content_diff(
    before_snapshot: StateSnapshot,
    after_snapshot: StateSnapshot,
    root: Path,
) -> ContentDiff:
    """Generate a line-level diff between two snapshots by re-reading files from disk.

    The *root* directory must be the same filesystem root that was used when
    capturing ``after_snapshot`` so that file contents can be read.

    Files that are binary are flagged with ``FileDiff.is_binary = True`` and
    their ``unified_diff`` is ``"(binary file)"``.

    Args:
        before_snapshot: The baseline state snapshot.
        after_snapshot: The current (after) state snapshot.
        root: Root directory to read file contents from.

    Returns:
        A :class:`ContentDiff` with per-file diffs and aggregate line counts.
    """
    root = Path(root)
    before_paths = set(before_snapshot.files.keys())
    after_paths = set(after_snapshot.files.keys())

    added_paths = after_paths - before_paths
    removed_paths = before_paths - after_paths
    modified_paths = {
        p
        for p in before_paths & after_paths
        if before_snapshot.files[p].sha256 != after_snapshot.files[p].sha256
    }

    file_diffs: list[FileDiff] = []
    total_added = 0
    total_removed = 0

    for path in sorted(added_paths | removed_paths | modified_paths):
        in_before = path in before_paths
        in_after = path in after_paths
        fd = _make_file_diff(path, root, before_exists=in_before, after_exists=in_after)
        file_diffs.append(fd)
        total_added += fd.added_lines
        total_removed += fd.removed_lines

    return ContentDiff(
        file_diffs=file_diffs,
        total_added=total_added,
        total_removed=total_removed,
    )
