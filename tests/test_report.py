"""Tests for groundcrew.report."""

from __future__ import annotations

import builtins
import io
import json

from rich.console import Console

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.report import print_diff, print_receipt, to_json, to_markdown
from groundcrew.snapshot import FileState, SnapshotDiff


def _receipt():
    spec = ActionSpec(verb="write", target="a.txt", params={})
    diff = SnapshotDiff(
        snapshot_a_id="aaa",
        snapshot_b_id="bbb",
        added=[FileState(path="new.txt", size=1, sha256="x")],
        removed=[],
        modified=[],
    )
    return ActionReceipt(
        spec=spec, before_id="aaa", after_id="bbb", diff=diff, success=True, timestamp=1.0
    )


def test_to_json_receipt():
    r = _receipt()
    parsed = json.loads(to_json(r))
    assert parsed["id"] == r.id
    assert parsed["spec"]["verb"] == "write"


def test_to_json_diff():
    diff = SnapshotDiff(
        snapshot_a_id="a",
        snapshot_b_id="b",
        added=[FileState(path="n.txt", size=1, sha256="x")],
        removed=[],
        modified=[],
    )
    parsed = json.loads(to_json(None, diff=diff))
    assert parsed["snapshot_b_id"] == "b"


def test_to_json_none():
    assert to_json(None, None) == "{}"


def test_to_markdown_empty():
    md = to_markdown([])
    assert "Groundcrew Action Log" in md
    assert "| ID |" in md


def test_to_markdown_with_receipt():
    r = _receipt()
    md = to_markdown([r])
    assert r.id in md
    assert "write" in md


def test_print_receipt_runs():
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    print_receipt(_receipt(), console=con)
    out = buf.getvalue()
    assert "write" in out


def test_print_diff_runs():
    diff = SnapshotDiff(
        snapshot_a_id="a",
        snapshot_b_id="b",
        added=[FileState(path="n.txt", size=1, sha256="x")],
        removed=[FileState(path="g.txt", size=1, sha256="y")],
        modified=[
            (
                FileState(path="m.txt", size=1, sha256="p"),
                FileState(path="m.txt", size=2, sha256="q"),
            )
        ],
    )
    buf = io.StringIO()
    con = Console(file=buf, highlight=False)
    print_diff(diff, console=con)
    out = buf.getvalue()
    assert "n.txt" in out
    assert "g.txt" in out
    assert "m.txt" in out


def _no_rich(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("rich"):
            raise ImportError("rich unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_print_receipt_no_rich(monkeypatch, capsys):
    _no_rich(monkeypatch)
    print_receipt(_receipt())
    out = capsys.readouterr().out
    assert "write" in out


def test_print_diff_no_rich(monkeypatch, capsys):
    _no_rich(monkeypatch)
    diff = SnapshotDiff(
        snapshot_a_id="a",
        snapshot_b_id="b",
        added=[FileState(path="n.txt", size=1, sha256="x")],
        removed=[],
        modified=[],
    )
    print_diff(diff)
    out = capsys.readouterr().out
    assert "+1" in out
