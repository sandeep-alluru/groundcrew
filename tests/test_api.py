"""FastAPI TestClient tests for openveritas.api."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVERITAS_DB", str(tmp_path / "r.db"))
    import openveritas.api as api_mod

    importlib.reload(api_mod)
    return TestClient(api_mod.app), tmp_path


def test_health(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_capture(client):
    c, tmp_path = client
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    r = c.post(
        "/capture",
        json={"root": str(work), "verb": "write", "target": "out.txt", "params": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["spec"]["verb"] == "write"
    assert "id" in body


def test_get_receipt(client):
    c, tmp_path = client
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    cap = c.post(
        "/capture",
        json={"root": str(work), "verb": "write", "target": "out.txt", "params": {}},
    )
    receipt_id = cap.json()["id"]
    r = c.get(f"/receipt/{receipt_id}")
    assert r.status_code == 200
    assert r.json()["id"] == receipt_id


def test_get_receipt_404(client):
    c, _ = client
    r = c.get("/receipt/nonexistent")
    assert r.status_code == 404


def test_list_receipts(client):
    c, tmp_path = client
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    c.post("/capture", json={"root": str(work), "verb": "v", "target": "t", "params": {}})
    r = c.get("/receipts")
    assert r.status_code == 200
    assert "receipts" in r.json()
    assert len(r.json()["receipts"]) >= 1


def test_get_diff(client):
    c, tmp_path = client
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    cap = c.post(
        "/capture",
        json={"root": str(work), "verb": "write", "target": "out.txt", "params": {}},
    )
    receipt_id = cap.json()["id"]
    r = c.get(f"/diff/{receipt_id}")
    assert r.status_code == 200
    assert "snapshot_b_id" in r.json()


def test_get_diff_404(client):
    c, _ = client
    r = c.get("/diff/nonexistent")
    assert r.status_code == 404
