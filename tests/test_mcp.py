"""Tests for openveritas.mcp_server helper functions."""

from __future__ import annotations

import json

import openveritas.mcp_server as m


def test_mcp_importable():
    assert hasattr(m, "run_server")


def test_capture_state_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    args = json.dumps({"root": str(work), "verb": "write", "target": "out.txt"})
    out = m._capture_state(args)
    parsed = json.loads(out)
    assert parsed["spec"]["verb"] == "write"
    assert "id" in parsed


def test_capture_state_with_run_cmd(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    work = tmp_path / "work"
    work.mkdir()
    args = json.dumps(
        {"root": str(work), "verb": "create", "target": "new.txt", "run_cmd": "touch new.txt"}
    )
    out = m._capture_state(args)
    parsed = json.loads(out)
    assert "new.txt" in parsed["diff"]["added"][0]["path"]


def test_get_receipt_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    cap = json.loads(m._capture_state(json.dumps({"root": str(work), "verb": "v", "target": "t"})))
    got = json.loads(m._get_receipt(json.dumps({"receipt_id": cap["id"]})))
    assert got["id"] == cap["id"]


def test_get_receipt_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    got = json.loads(m._get_receipt(json.dumps({"receipt_id": "nope"})))
    assert "error" in got


def test_list_receipts_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    m._capture_state(json.dumps({"root": str(work), "verb": "v", "target": "t"}))
    out = json.loads(m._list_receipts("{}"))
    assert len(out["receipts"]) >= 1


def test_db_path_default(monkeypatch):
    monkeypatch.delenv("OPENVERITAS_DB", raising=False)
    assert m._db_path() == ".openveritas/receipts.db"


def test_db_path_env(tmp_path, monkeypatch):
    custom = str(tmp_path / "custom.db")
    monkeypatch.setenv("OPENVERITAS_DB", custom)
    assert m._db_path() == custom
