"""Tests for openveritas.codec."""

from __future__ import annotations

from openveritas.codec import ActionReceipt, ActionSpec
from openveritas.snapshot import SnapshotDiff


def _diff():
    return SnapshotDiff(snapshot_a_id="a", snapshot_b_id="b", added=[], removed=[], modified=[])


def test_actionspec_content_addressing():
    s1 = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    s2 = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    assert s1.id == s2.id


def test_actionspec_different_params():
    s1 = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    s2 = ActionSpec(verb="write", target="a.txt", params={"x": 2})
    assert s1.id != s2.id


def test_actionspec_round_trip():
    s = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    d = s.to_dict()
    s2 = ActionSpec.from_dict(d)
    assert s2.id == s.id
    assert s2.verb == "write"


def test_actionreceipt_content_addressing():
    spec = ActionSpec(verb="write", target="a.txt", params={})
    r1 = ActionReceipt(
        spec=spec, before_id="aaa", after_id="bbb", diff=_diff(), success=True, timestamp=1.0
    )
    r2 = ActionReceipt(
        spec=spec, before_id="aaa", after_id="bbb", diff=_diff(), success=True, timestamp=1.0
    )
    assert r1.id == r2.id


def test_actionreceipt_round_trip():
    spec = ActionSpec(verb="write", target="a.txt", params={})
    r = ActionReceipt(
        spec=spec, before_id="aaa", after_id="bbb", diff=_diff(), success=True, timestamp=1.0
    )
    d = r.to_dict()
    r2 = ActionReceipt.from_dict(d)
    assert r2.id == r.id
    assert r2.spec.id == spec.id
    assert r2.success is True


def test_actionspec_id_length():
    s = ActionSpec(verb="write", target="a.txt", params={})
    assert len(s.id) == 16
    int(s.id, 16)  # is hex


def test_actionreceipt_id_length():
    spec = ActionSpec(verb="write", target="a.txt", params={})
    r = ActionReceipt(
        spec=spec, before_id="a", after_id="b", diff=_diff(), success=True, timestamp=1.0
    )
    assert len(r.id) == 16
    int(r.id, 16)


def test_actionspec_empty_params():
    s = ActionSpec(verb="noop", target="", params={})
    assert len(s.id) == 16
    assert s.params == {}
