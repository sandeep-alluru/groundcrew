"""Closed-loop reader — empty receipts and empty side effects fail loudly (L10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundcrew.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_side_effects,
    gate_receipts,
)
from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.snapshot import SnapshotDiff


def _spec(verb: str = "write", target: str = "a.txt") -> ActionSpec:
    return ActionSpec(verb=verb, target=target, params={})


def _empty_diff() -> SnapshotDiff:
    return SnapshotDiff(
        snapshot_a_id="before000000000",
        snapshot_b_id="after0000000000",
        added=[],
        removed=[],
        modified=[],
    )


def _write(root: Path, name: str, content: str) -> None:
    (root / name).write_text(content)


def test_empty_list_fails_loud() -> None:
    out = gate_receipts([])
    assert isinstance(out, GateOutcome)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "empty" in out.reason.lower()


def test_empty_store_fails_loud(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "receipts.db")
    try:
        out = gate_receipts(store)
        assert out.verdict == "FAIL_LOUD"
        assert out.exit_code == 2
    finally:
        store.close()


def test_missing_db_fails_loud(tmp_path: Path) -> None:
    out = gate_receipts(tmp_path / "nope.db")
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "not found" in out.reason.lower()


def test_success_with_zero_changes_fails_loud() -> None:
    r = ActionReceipt(
        spec=_spec(),
        before_id="b1",
        after_id="a1",
        diff=_empty_diff(),
        success=True,
        timestamp=1.0,
    )
    out = gate_receipts([r])
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert "L10" in out.reason
    assert r.id in out.empty_effect_ids
    payload = out.to_dict()
    assert payload["empty_effect_ids"] == [r.id]


def test_real_mutation_passes(tmp_path: Path) -> None:
    with Oracle(tmp_path, _spec()) as oracle:
        _write(tmp_path, "new.txt", "data")
    receipt = oracle.record(_spec())
    out = gate_receipts([receipt])
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.exit_code == 0
    assert out.total_changed_paths >= 1
    assert out.receipt_count == 1


def test_store_path_with_side_effects_passes(tmp_path: Path) -> None:
    db = tmp_path / "receipts.db"
    ws = tmp_path / "ws"
    ws.mkdir()
    with Oracle(ws, _spec()) as oracle:
        _write(ws, "y.txt", "side-effect")
    receipt = oracle.record(_spec())
    store = ReceiptStore(db)
    try:
        store.save(receipt)
    finally:
        store.close()

    out = gate_receipts(db)
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.total_changed_paths >= 1


def test_all_failed_receipts_fail() -> None:
    r = ActionReceipt(
        spec=_spec(verb="rm", target="missing"),
        before_id="b1",
        after_id="a1",
        diff=_empty_diff(),
        success=False,
        timestamp=1.0,
    )
    out = gate_receipts([r])
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert out.exit_code == 1


def test_assert_side_effects_raises_on_empty() -> None:
    with pytest.raises(ClosedLoopError, match="FAIL_LOUD"):
        assert_side_effects([])


def test_assert_side_effects_ok(tmp_path: Path) -> None:
    with Oracle(tmp_path, _spec()) as oracle:
        _write(tmp_path, "z.txt", "ok")
    receipt = oracle.record(_spec())
    out = assert_side_effects([receipt])
    assert out.ok is True
