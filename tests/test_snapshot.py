"""Tests for groundcrew.snapshot."""

from __future__ import annotations

from unittest import mock

from groundcrew.snapshot import (
    FileState,
    StateSnapshot,
    diff_snapshots,
)


def _write(root, name, content):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_filestate_round_trip():
    fs = FileState(path="a.txt", size=3, sha256="deadbeef")
    d = fs.to_dict()
    assert d == {"path": "a.txt", "size": 3, "sha256": "deadbeef"}
    fs2 = FileState.from_dict(d)
    assert fs2 == fs


def test_capture_basic(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    _write(tmp_path, "sub/b.txt", "world")
    snap = StateSnapshot.capture(tmp_path)
    assert "a.txt" in snap.files
    assert "sub/b.txt" in snap.files
    assert snap.files["a.txt"].size == 5
    assert len(snap.id) == 16


def test_capture_deterministic_id(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    snap2 = StateSnapshot.capture(tmp_path)
    assert snap1.id == snap2.id


def test_capture_id_changes_on_change(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    _write(tmp_path, "a.txt", "changed")
    snap2 = StateSnapshot.capture(tmp_path)
    assert snap1.id != snap2.id


def test_snapshot_round_trip(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap = StateSnapshot.capture(tmp_path)
    d = snap.to_dict()
    snap2 = StateSnapshot.from_dict(d)
    assert snap2.id == snap.id
    assert snap2.files["a.txt"].sha256 == snap.files["a.txt"].sha256


def test_capture_skips_permission_error(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    _write(tmp_path, "b.txt", "world")
    original = type(tmp_path / "a.txt").read_bytes

    def fake_read_bytes(self):
        if self.name == "b.txt":
            raise PermissionError("nope")
        return original(self)

    with mock.patch("pathlib.Path.read_bytes", new=fake_read_bytes):
        snap = StateSnapshot.capture(tmp_path)
    assert "a.txt" in snap.files
    assert "b.txt" not in snap.files


def test_diff_no_changes(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    assert diff.added == []
    assert diff.removed == []
    assert diff.modified == []


def test_diff_added(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    _write(tmp_path, "b.txt", "new")
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    assert len(diff.added) == 1
    assert diff.added[0].path == "b.txt"


def test_diff_removed(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    _write(tmp_path, "b.txt", "bye")
    snap1 = StateSnapshot.capture(tmp_path)
    (tmp_path / "b.txt").unlink()
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    assert len(diff.removed) == 1
    assert diff.removed[0].path == "b.txt"


def test_diff_modified(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    _write(tmp_path, "a.txt", "modified")
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    assert len(diff.modified) == 1
    before, after = diff.modified[0]
    assert before.path == "a.txt"
    assert before.sha256 != after.sha256


def test_diff_none_baseline(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(None, snap2)
    assert diff.snapshot_a_id is None
    assert len(diff.added) == 1


def test_changed_paths_property(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    _write(tmp_path, "b.txt", "keep")
    snap1 = StateSnapshot.capture(tmp_path)
    _write(tmp_path, "a.txt", "changed")
    _write(tmp_path, "c.txt", "new")
    (tmp_path / "b.txt").unlink()
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    assert diff.changed_paths == {"a.txt", "b.txt", "c.txt"}


def test_diff_round_trip(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    snap1 = StateSnapshot.capture(tmp_path)
    _write(tmp_path, "a.txt", "changed")
    _write(tmp_path, "b.txt", "new")
    snap2 = StateSnapshot.capture(tmp_path)
    diff = diff_snapshots(snap1, snap2)
    d = diff.to_dict()
    diff2 = diff_snapshots(snap1, snap2)
    from groundcrew.snapshot import SnapshotDiff

    restored = SnapshotDiff.from_dict(d)
    assert restored.snapshot_b_id == diff2.snapshot_b_id
    assert restored.changed_paths == diff.changed_paths


def test_empty_directory(tmp_path):
    snap = StateSnapshot.capture(tmp_path)
    assert snap.files == {}
    assert len(snap.id) == 16
