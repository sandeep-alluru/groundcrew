"""Tests for groundcrew.chain — verify_chain and build_chain_report."""

from __future__ import annotations

import time

import pytest

from groundcrew.chain import ChainVerification, build_chain_report, verify_chain
from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.snapshot import SnapshotDiff


def _make_receipt(
    verb: str,
    target: str,
    before_id: str,
    after_id: str,
    success: bool = True,
) -> ActionReceipt:
    spec = ActionSpec(verb=verb, target=target, params={})
    diff = SnapshotDiff(
        snapshot_a_id=before_id,
        snapshot_b_id=after_id,
        added=[],
        removed=[],
        modified=[],
    )
    return ActionReceipt(
        spec=spec,
        before_id=before_id,
        after_id=after_id,
        diff=diff,
        success=success,
        timestamp=time.time(),
    )


def _make_chain(n: int = 3) -> list[ActionReceipt]:
    """Build a valid chain of n receipts where after_id[i] == before_id[i+1]."""
    receipts = []
    state_ids = [f"state_{i:04d}" for i in range(n + 1)]
    for i in range(n):
        r = _make_receipt(
            verb="write",
            target=f"file{i}.txt",
            before_id=state_ids[i],
            after_id=state_ids[i + 1],
        )
        receipts.append(r)
    return receipts


# ── verify_chain ──────────────────────────────────────────────────────────────

def test_verify_empty_chain() -> None:
    """Empty list is trivially valid."""
    result = verify_chain([])
    assert isinstance(result, ChainVerification)
    assert result.is_valid is True
    assert result.chain_length == 0


def test_verify_single_receipt() -> None:
    """A single receipt has nothing to verify; it's always valid."""
    r = _make_receipt("read", "file.txt", "aaa", "bbb")
    result = verify_chain([r])
    assert result.is_valid is True
    assert result.chain_length == 1


def test_verify_valid_chain() -> None:
    """A properly chained sequence should be valid."""
    chain = _make_chain(4)
    result = verify_chain(chain)
    assert result.is_valid is True
    assert result.chain_length == 4
    assert result.broken_at is None
    assert result.errors == []


def test_verify_broken_chain() -> None:
    """Injecting a mismatching ID should break the chain."""
    chain = _make_chain(3)
    # Break the link between index 1 and 2
    chain[2] = _make_receipt("write", "bad.txt", before_id="WRONG_ID", after_id="state_0003")
    result = verify_chain(chain)
    assert result.is_valid is False
    assert result.broken_at == 2
    assert len(result.errors) >= 1


def test_verify_chain_summary_contains_verdict() -> None:
    """Verification summary should be a non-empty string."""
    chain = _make_chain(2)
    result = verify_chain(chain)
    assert isinstance(result.summary, str)
    assert len(result.summary) > 0


# ── build_chain_report ────────────────────────────────────────────────────────

def test_build_chain_report_returns_string() -> None:
    """build_chain_report should return a non-empty string."""
    chain = _make_chain(2)
    report = build_chain_report(chain)
    assert isinstance(report, str)
    assert len(report) > 0


def test_build_chain_report_contains_actions() -> None:
    """Report should mention the verb and target of each receipt."""
    r1 = _make_receipt("write", "foo.py", "aaa", "bbb")
    r2 = _make_receipt("delete", "bar.py", "bbb", "ccc")
    report = build_chain_report([r1, r2])
    assert "write" in report
    assert "foo.py" in report
    assert "delete" in report
    assert "bar.py" in report


def test_build_chain_report_broken_mentions_error() -> None:
    """A broken chain report should mention ERROR."""
    chain = _make_chain(3)
    chain[1] = _make_receipt("write", "x.txt", before_id="WRONG", after_id="state_0002")
    report = build_chain_report(chain)
    assert "ERROR" in report or "BROKEN" in report
