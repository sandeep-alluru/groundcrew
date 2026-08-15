"""Deterministic filesystem state snapshots and content-addressed diffs."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileState:
    """The recorded state of a single file: relative path, size, and digest."""

    path: str  # relative to root
    size: int
    sha256: str  # full hex digest

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> FileState:
        return cls(path=str(d["path"]), size=int(str(d["size"])), sha256=str(d["sha256"]))


@dataclass
class StateSnapshot:
    """A content-addressed snapshot of every file beneath a root directory."""

    id: str  # SHA-256[:16] of sorted file-state JSON
    timestamp: float
    root: str
    files: dict[str, FileState]

    @classmethod
    def capture(cls, root: str | Path) -> StateSnapshot:
        # Operator-supplied workspace root: normalize, reject "..", walk only that tree.
        root_s = os.path.expanduser(str(root))
        if ".." in Path(root_s).parts or chr(0) in root_s:
            raise ValueError("snapshot root must not contain '..' or NUL")
        root_real = os.path.realpath(root_s)
        if not os.path.isdir(root_real):
            raise ValueError(f"snapshot root is not a directory: {root_real}")
        root_prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
        files: dict[str, FileState] = {}
        for dirpath, _dirnames, filenames in os.walk(root_real):
            for fname in filenames:
                # dirpath comes from walk of root_real (not raw user join)
                candidate = os.path.join(dirpath, fname)
                f_real = os.path.realpath(candidate)
                # Positive guard at every file sink (CodeQL)
                if not (f_real == root_real or f_real.startswith(root_prefix)):
                    continue
                rel = os.path.relpath(f_real, root_real)
                try:
                    # open only after positive under-root check
                    with open(f_real, "rb") as fh:
                        data = fh.read()
                    h = hashlib.sha256(data).hexdigest()
                    files[rel] = FileState(path=rel, size=len(data), sha256=h)
                except (PermissionError, OSError):
                    pass
        # content-address: SHA-256[:16] of sorted JSON of file states
        payload = json.dumps({k: v.to_dict() for k, v in sorted(files.items())}, sort_keys=True)
        snap_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return cls(id=snap_id, timestamp=time.time(), root=root_real, files=files)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "root": self.root,
            "files": {k: v.to_dict() for k, v in self.files.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> StateSnapshot:
        raw_files = d.get("files", {})
        assert isinstance(raw_files, dict)
        files = {k: FileState.from_dict(v) for k, v in raw_files.items()}
        return cls(
            id=str(d["id"]), timestamp=float(str(d["timestamp"])), root=str(d["root"]), files=files
        )


@dataclass
class SnapshotDiff:
    """The structural delta between two snapshots: added, removed, modified files.

    Attributes:
        added:    ``list[FileState]`` - files present in *b* but not in *a*.
                  Each element is a :class:`FileState`; use ``.path`` to get the
                  relative path string.  Example::

                      for f in diff.added:
                          print(f.path)   # e.g. "subdir/new_file.txt"

        removed:  ``list[FileState]`` - files present in *a* but not in *b*.
                  Same type as ``added``; iterate with ``.path``.

        modified: ``list[tuple[FileState, FileState]]`` - files whose content
                  changed.  Each element is ``(before, after)``::

                      for before, after in diff.modified:
                          print(before.path, before.sha256, "->", after.sha256)
    """

    snapshot_a_id: str | None
    snapshot_b_id: str
    added: list[FileState]
    removed: list[FileState]
    modified: list[tuple[FileState, FileState]]

    @property
    def changed_paths(self) -> set[str]:
        paths: set[str] = set()
        for f in self.added:
            paths.add(f.path)
        for f in self.removed:
            paths.add(f.path)
        for before, _after in self.modified:
            paths.add(before.path)
        return paths

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_a_id": self.snapshot_a_id,
            "snapshot_b_id": self.snapshot_b_id,
            "added": [f.to_dict() for f in self.added],
            "removed": [f.to_dict() for f in self.removed],
            "modified": [[b.to_dict(), a.to_dict()] for b, a in self.modified],
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> SnapshotDiff:
        added_raw = d.get("added", [])
        removed_raw = d.get("removed", [])
        modified_raw = d.get("modified", [])
        assert isinstance(added_raw, list)
        assert isinstance(removed_raw, list)
        assert isinstance(modified_raw, list)
        return cls(
            snapshot_a_id=str(d["snapshot_a_id"]) if d.get("snapshot_a_id") else None,
            snapshot_b_id=str(d["snapshot_b_id"]),
            added=[FileState.from_dict(f) for f in added_raw],
            removed=[FileState.from_dict(f) for f in removed_raw],
            modified=[(FileState.from_dict(b), FileState.from_dict(a)) for b, a in modified_raw],
        )


def diff_snapshots(snap_a: StateSnapshot | None, snap_b: StateSnapshot) -> SnapshotDiff:
    """Compute the added/removed/modified delta from ``snap_a`` to ``snap_b``."""
    a_files = snap_a.files if snap_a else {}
    b_files = snap_b.files
    a_paths = set(a_files.keys())
    b_paths = set(b_files.keys())
    added = [b_files[p] for p in b_paths - a_paths]
    removed = [a_files[p] for p in a_paths - b_paths]
    modified = [
        (a_files[p], b_files[p])
        for p in a_paths & b_paths
        if a_files[p].sha256 != b_files[p].sha256
    ]
    return SnapshotDiff(
        snapshot_a_id=snap_a.id if snap_a else None,
        snapshot_b_id=snap_b.id,
        added=added,
        removed=removed,
        modified=modified,
    )
