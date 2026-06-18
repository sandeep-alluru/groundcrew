"""Tests for groundcrew.oracle."""

from __future__ import annotations

import pytest

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore, capture
from groundcrew.snapshot import SnapshotDiff


def _spec():
    return ActionSpec(verb="write", target="a.txt", params={})


def _write(root, name, content):
    p = root / name
    p.write_text(content)
    return p


def test_oracle_captures_before_after(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    with Oracle(tmp_path, _spec()) as oracle:
        pass
    assert oracle._before is not None
    assert oracle._after is not None


def test_oracle_captures_added(tmp_path):
    with Oracle(tmp_path, _spec()) as oracle:
        _write(tmp_path, "new.txt", "data")
    receipt = oracle.record(_spec())
    assert "new.txt" in receipt.diff.changed_paths


def test_oracle_captures_removed(tmp_path):
    _write(tmp_path, "gone.txt", "data")
    with Oracle(tmp_path, _spec()) as oracle:
        (tmp_path / "gone.txt").unlink()
    receipt = oracle.record(_spec())
    assert "gone.txt" in receipt.diff.changed_paths


def test_oracle_captures_modified(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    with Oracle(tmp_path, _spec()) as oracle:
        _write(tmp_path, "a.txt", "changed")
    receipt = oracle.record(_spec())
    assert "a.txt" in receipt.diff.changed_paths


def test_oracle_record_returns_receipt(tmp_path):
    with Oracle(tmp_path, _spec()) as oracle:
        pass
    receipt = oracle.record(_spec())
    assert isinstance(receipt, ActionReceipt)


def test_oracle_success_false_on_exception(tmp_path):
    with pytest.raises(ValueError, match="boom"), Oracle(tmp_path, _spec()) as oracle:
        raise ValueError("boom")
    receipt = oracle.record(_spec())
    assert receipt.success is False


def test_receiptstore_save_get(tmp_path):
    store = ReceiptStore(tmp_path / "r.db")
    spec = _spec()
    diff = SnapshotDiff(snapshot_a_id="a", snapshot_b_id="b", added=[], removed=[], modified=[])
    receipt = ActionReceipt(
        spec=spec, before_id="a", after_id="b", diff=diff, success=True, timestamp=1.0
    )
    store.save(receipt)
    got = store.get(receipt.id)
    assert got is not None
    assert got.id == receipt.id
    store.close()


def test_receiptstore_list(tmp_path):
    store = ReceiptStore(tmp_path / "r.db")
    diff = SnapshotDiff(snapshot_a_id="a", snapshot_b_id="b", added=[], removed=[], modified=[])
    for i in range(3):
        r = ActionReceipt(
            spec=ActionSpec(verb="v", target=f"t{i}", params={}),
            before_id="a",
            after_id="b",
            diff=diff,
            success=True,
            timestamp=float(i),
        )
        store.save(r)
    assert len(store.list_receipts()) == 3
    store.close()


def test_receiptstore_get_missing(tmp_path):
    store = ReceiptStore(tmp_path / "r.db")
    assert store.get("nonexistent") is None
    store.close()


def test_receiptstore_close(tmp_path):
    store = ReceiptStore(tmp_path / "r.db")
    store.close()


def test_receiptstore_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "r.db"
    store = ReceiptStore(nested)
    assert nested.parent.exists()
    store.close()


def test_capture_context_manager(tmp_path):
    with capture(tmp_path, _spec()) as oracle:
        _write(tmp_path, "x.txt", "data")
    receipt = oracle.record(_spec())
    assert "x.txt" in receipt.diff.changed_paths


def test_capture_context_manager_exception(tmp_path):
    with pytest.raises(ValueError, match="boom"), capture(tmp_path, _spec()) as oracle:
        raise ValueError("boom")
    assert oracle._success is False
