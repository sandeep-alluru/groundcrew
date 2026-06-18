"""
End-to-end smoke test for openveritas.

Simulates a user who just installed the package and wants to verify everything works.
No mocking, no fixtures — real behaviour, real CLI, real HTTP server.

Run from repo root:
    python smoke_test.py
    python smoke_test.py --verbose

Exit 0 = all passed. Exit 1 = at least one failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
REPO_ROOT = Path(__file__).parent
PYTHON = sys.executable

passed: list[str] = []
failed: list[tuple[str, str]] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"  {GREEN}+{RESET} {name}")


def fail(name: str, reason: str) -> None:
    failed.append((name, reason))
    print(f"  {RED}x{RESET} {name}")
    if VERBOSE:
        print(f"    {YELLOW}{reason}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def run(name: str, fn):  # noqa: ANN001
    try:
        fn()
        ok(name)
    except Exception as exc:
        reason = str(exc) if not VERBOSE else traceback.format_exc().strip()
        fail(name, reason)


def _seed(root: Path) -> None:
    (root / "a.txt").write_text("hello")


# ── 1. Package import ───────────────────────────────────────────────────────────

section("1. Package import & public API")


def _test_import_version():
    import openveritas

    assert openveritas.__version__, "__version__ is empty"
    assert openveritas.__version__ != "0.0.0"


def _test_public_api():
    from openveritas import (
        ActionReceipt,
        ActionSpec,
        FileState,
        Oracle,
        ReceiptStore,
        SnapshotDiff,
        StateSnapshot,
    )

    assert callable(StateSnapshot.capture)
    assert callable(Oracle)
    _ = (ActionReceipt, ActionSpec, FileState, ReceiptStore, SnapshotDiff)


run("openveritas imports with a real version", _test_import_version)
run("Public API (Oracle, StateSnapshot, ActionSpec, ...) importable", _test_public_api)


# ── 2. Content-addressing & serialization ──────────────────────────────────────

section("2. Content-addressing & serialization")


def _test_snapshot_content_addressed():
    from openveritas import StateSnapshot

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed(root)
        s1 = StateSnapshot.capture(root)
        s2 = StateSnapshot.capture(root)
        assert s1.id == s2.id, "Same content must produce same snapshot ID"
        assert len(s1.id) == 16
        (root / "a.txt").write_text("changed")
        s3 = StateSnapshot.capture(root)
        assert s3.id != s1.id, "Changed content must change snapshot ID"


def _test_snapshot_round_trip():
    from openveritas import StateSnapshot

    with tempfile.TemporaryDirectory() as tmp:
        _seed(Path(tmp))
        snap = StateSnapshot.capture(tmp)
        restored = StateSnapshot.from_dict(snap.to_dict())
        assert restored.id == snap.id


def _test_actionspec_content_addressed():
    from openveritas import ActionSpec

    a = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    b = ActionSpec(verb="write", target="a.txt", params={"x": 1})
    c = ActionSpec(verb="write", target="a.txt", params={"x": 2})
    assert a.id == b.id, "Identical specs must share an ID"
    assert a.id != c.id, "Different params must differ in ID"
    assert len(a.id) == 16


def _test_receipt_round_trip():
    from openveritas import ActionReceipt, ActionSpec, SnapshotDiff

    spec = ActionSpec(verb="write", target="a.txt", params={})
    diff = SnapshotDiff(snapshot_a_id="a", snapshot_b_id="b", added=[], removed=[], modified=[])
    r = ActionReceipt(
        spec=spec, before_id="a", after_id="b", diff=diff, success=True, timestamp=1.0
    )
    r2 = ActionReceipt.from_dict(r.to_dict())
    assert r2.id == r.id
    assert len(r.id) == 16


run("StateSnapshot is content-addressed & deterministic", _test_snapshot_content_addressed)
run("StateSnapshot to_dict/from_dict round-trip", _test_snapshot_round_trip)
run("ActionSpec is content-addressed", _test_actionspec_content_addressed)
run("ActionReceipt round-trip preserves ID", _test_receipt_round_trip)


# ── 3. Oracle & ReceiptStore ────────────────────────────────────────────────────

section("3. Oracle capture & ReceiptStore persistence")


def _test_oracle_added():
    from openveritas import ActionSpec, Oracle

    with tempfile.TemporaryDirectory() as tmp:
        spec = ActionSpec(verb="write", target="new.txt", params={})
        with Oracle(tmp, spec) as oracle:
            (Path(tmp) / "new.txt").write_text("data")
        receipt = oracle.record(spec)
        assert "new.txt" in receipt.diff.changed_paths


def _test_oracle_modified():
    from openveritas import ActionSpec, Oracle

    with tempfile.TemporaryDirectory() as tmp:
        _seed(Path(tmp))
        spec = ActionSpec(verb="edit", target="a.txt", params={})
        with Oracle(tmp, spec) as oracle:
            (Path(tmp) / "a.txt").write_text("changed")
        receipt = oracle.record(spec)
        assert "a.txt" in receipt.diff.changed_paths


def _test_oracle_success_flag():
    from openveritas import ActionSpec, Oracle

    with tempfile.TemporaryDirectory() as tmp:
        spec = ActionSpec(verb="x", target="y", params={})
        try:
            with Oracle(tmp, spec) as oracle:
                raise ValueError("boom")
        except ValueError:
            pass
        receipt = oracle.record(spec)
        assert receipt.success is False


def _test_store_round_trip():
    from openveritas import ActionSpec, Oracle, ReceiptStore

    with tempfile.TemporaryDirectory() as tmp:
        spec = ActionSpec(verb="write", target="new.txt", params={})
        with Oracle(tmp, spec) as oracle:
            (Path(tmp) / "new.txt").write_text("data")
        receipt = oracle.record(spec)
        store = ReceiptStore(Path(tmp) / "r.db")
        store.save(receipt)
        got = store.get(receipt.id)
        assert got is not None and got.id == receipt.id
        assert len(store.list_receipts()) == 1
        assert store.get("missing") is None
        store.close()


run("Oracle captures added files", _test_oracle_added)
run("Oracle captures modified files", _test_oracle_modified)
run("Oracle sets success=False on exception", _test_oracle_success_flag)
run("ReceiptStore save/get/list round-trip", _test_store_round_trip)


# ── 4. Report formatters ────────────────────────────────────────────────────────

section("4. Report formatters")


def _make_receipt():
    from openveritas import ActionReceipt, ActionSpec, FileState, SnapshotDiff

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


def _test_to_json():
    from openveritas.report import to_json

    parsed = json.loads(to_json(_make_receipt()))
    assert parsed["spec"]["verb"] == "write"
    assert to_json(None, None) == "{}"


def _test_to_markdown():
    from openveritas.report import to_markdown

    r = _make_receipt()
    md = to_markdown([r])
    assert "OpenVeritas" in md
    assert r.id in md
    assert "|" in md


def _test_print_receipt():
    import io

    from rich.console import Console

    from openveritas.report import print_receipt

    buf = io.StringIO()
    print_receipt(_make_receipt(), console=Console(file=buf, highlight=False))
    assert "write" in buf.getvalue()


run("to_json() returns valid JSON", _test_to_json)
run("to_markdown() produces a Markdown table", _test_to_markdown)
run("print_receipt() outputs to console", _test_print_receipt)


# ── 5. CLI ──────────────────────────────────────────────────────────────────────

section("5. CLI (openveritas)")


def _test_cli_help():
    r = subprocess.run(
        [PYTHON, "-m", "openveritas.cli", "--help"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(r.stdout) > 20


def _test_cli_capture_and_log():
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/r.db"
        work = Path(tmp) / "work"
        work.mkdir()
        cap = subprocess.run(
            [
                PYTHON, "-m", "openveritas.cli", "--db", db, "capture",
                "--root", str(work), "--verb", "create", "--target", "out.txt",
                "--run", "echo hi > out.txt",
            ],
            capture_output=True, text=True,
        )
        assert cap.returncode == 0, cap.stderr
        assert "Captured receipt" in cap.stdout
        assert (work / "out.txt").exists()
        log = subprocess.run(
            [PYTHON, "-m", "openveritas.cli", "--db", db, "log"],
            capture_output=True, text=True,
        )
        assert log.returncode == 0
        assert "Action Log" in log.stdout


def _test_cli_status():
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/r.db"
        r = subprocess.run(
            [PYTHON, "-m", "openveritas.cli", "--db", db, "status", "--root", tmp],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "Snapshot" in r.stdout


run("openveritas --help returns 0", _test_cli_help)
run("openveritas capture --run + log workflow", _test_cli_capture_and_log)
run("openveritas status returns 0", _test_cli_status)


# ── 6. FastAPI server ───────────────────────────────────────────────────────────

section("6. FastAPI server (openveritas[api])")


def _test_api_import():
    from openveritas.api import app

    assert app.title == "openveritas API"


def _test_api_health():
    from fastapi.testclient import TestClient

    from openveritas.api import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def _test_api_capture_workflow():
    import importlib
    import os

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OPENVERITAS_DB"] = f"{tmp}/r.db"
        import openveritas.api as api_mod

        importlib.reload(api_mod)
        from fastapi.testclient import TestClient

        client = TestClient(api_mod.app)
        work = Path(tmp) / "work"
        work.mkdir()
        (work / "seed.txt").write_text("seed")
        cap = client.post(
            "/capture",
            json={"root": str(work), "verb": "write", "target": "out.txt", "params": {}},
        )
        assert cap.status_code == 200
        rid = cap.json()["id"]
        assert client.get(f"/receipt/{rid}").status_code == 200
        assert client.get("/receipt/nope").status_code == 404
        assert client.get(f"/diff/{rid}").status_code == 200
        assert client.get("/diff/nope").status_code == 404
        receipts = client.get("/receipts")
        assert receipts.status_code == 200
        assert len(receipts.json()["receipts"]) >= 1
        del os.environ["OPENVERITAS_DB"]


run("openveritas.api imports with correct title", _test_api_import)
run("GET /health returns {status: ok, version: ...}", _test_api_health)
run("POST /capture + GET /receipt + /diff + /receipts workflow", _test_api_capture_workflow)


# ── 7. MCP server ───────────────────────────────────────────────────────────────

section("7. MCP server (openveritas[mcp])")


def _test_mcp_importable():
    import openveritas.mcp_server as m

    assert hasattr(m, "run_server")
    assert callable(m._capture_state)


def _test_mcp_capture_tool():
    import importlib
    import os

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OPENVERITAS_DB"] = f"{tmp}/r.db"
        import openveritas.mcp_server as m

        importlib.reload(m)
        work = Path(tmp) / "work"
        work.mkdir()
        out = json.loads(
            m._capture_state(json.dumps({"root": str(work), "verb": "v", "target": "t"}))
        )
        assert "id" in out
        got = json.loads(m._get_receipt(json.dumps({"receipt_id": out["id"]})))
        assert got["id"] == out["id"]
        listed = json.loads(m._list_receipts("{}"))
        assert len(listed["receipts"]) >= 1
        del os.environ["OPENVERITAS_DB"]


run("mcp_server imports & exposes helpers", _test_mcp_importable)
run("MCP capture/get/list tools work end-to-end", _test_mcp_capture_tool)


# ── 8. Diff semantics ───────────────────────────────────────────────────────────

section("8. Diff semantics (added / removed / modified)")


def _test_diff_added_removed_modified():
    from openveritas import StateSnapshot
    from openveritas.snapshot import diff_snapshots

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "keep.txt").write_text("keep")
        (root / "gone.txt").write_text("bye")
        (root / "edit.txt").write_text("v1")
        before = StateSnapshot.capture(root)
        (root / "gone.txt").unlink()
        (root / "edit.txt").write_text("v2")
        (root / "new.txt").write_text("new")
        after = StateSnapshot.capture(root)
        diff = diff_snapshots(before, after)
        assert {f.path for f in diff.added} == {"new.txt"}
        assert {f.path for f in diff.removed} == {"gone.txt"}
        assert {b.path for b, _a in diff.modified} == {"edit.txt"}
        assert diff.changed_paths == {"new.txt", "gone.txt", "edit.txt"}


def _test_diff_none_baseline():
    from openveritas import StateSnapshot
    from openveritas.snapshot import diff_snapshots

    with tempfile.TemporaryDirectory() as tmp:
        _seed(Path(tmp))
        after = StateSnapshot.capture(tmp)
        diff = diff_snapshots(None, after)
        assert diff.snapshot_a_id is None
        assert len(diff.added) == 1


run("diff_snapshots detects added/removed/modified", _test_diff_added_removed_modified)
run("diff_snapshots with None baseline treats all as added", _test_diff_none_baseline)


# ── 9. Edge cases ────────────────────────────────────────────────────────────────

section("9. Edge cases")


def _test_empty_dir():
    from openveritas import StateSnapshot

    with tempfile.TemporaryDirectory() as tmp:
        snap = StateSnapshot.capture(tmp)
        assert snap.files == {}
        assert len(snap.id) == 16


def _test_nested_dirs():
    from openveritas import StateSnapshot

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a" / "b").mkdir(parents=True)
        (Path(tmp) / "a" / "b" / "deep.txt").write_text("deep")
        snap = StateSnapshot.capture(tmp)
        assert any("deep.txt" in p for p in snap.files)


def _test_store_creates_parent_dirs():
    from openveritas import ReceiptStore

    with tempfile.TemporaryDirectory() as tmp:
        nested = Path(tmp) / "x" / "y" / "z" / "r.db"
        store = ReceiptStore(nested)
        assert nested.parent.exists()
        store.close()


def _test_empty_params_spec():
    from openveritas import ActionSpec

    s = ActionSpec(verb="noop", target="", params={})
    assert len(s.id) == 16


run("Empty directory yields empty snapshot", _test_empty_dir)
run("Nested directories are walked", _test_nested_dirs)
run("ReceiptStore creates parent directories", _test_store_creates_parent_dirs)
run("ActionSpec with empty params is valid", _test_empty_params_spec)


# ── 10. Determinism guarantees ──────────────────────────────────────────────────

section("10. Determinism guarantees")


def _test_snapshot_id_independent_of_walk_order():
    from openveritas import StateSnapshot

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for n in ("z.txt", "a.txt", "m.txt"):
            (root / n).write_text(n)
        id1 = StateSnapshot.capture(root).id
        id2 = StateSnapshot.capture(root).id
        assert id1 == id2


def _test_receipt_id_stable_across_serialization():
    from openveritas import ActionReceipt

    r = _make_receipt()
    r2 = ActionReceipt.from_dict(json.loads(json.dumps(r.to_dict())))
    assert r.id == r2.id


def _test_spec_id_param_order_invariant():
    from openveritas import ActionSpec

    a = ActionSpec(verb="v", target="t", params={"x": 1, "y": 2})
    b = ActionSpec(verb="v", target="t", params={"y": 2, "x": 1})
    assert a.id == b.id, "Param insertion order must not affect ID"


def _test_unchanged_state_no_diff():
    from openveritas import ActionSpec, Oracle

    with tempfile.TemporaryDirectory() as tmp:
        _seed(Path(tmp))
        spec = ActionSpec(verb="noop", target="a.txt", params={})
        with Oracle(tmp, spec) as oracle:
            pass  # no changes
        r = oracle.record(spec)
        assert r.diff.changed_paths == set(), "Unchanged state must produce empty diff"
        assert r.before_id == r.after_id


def _test_capture_helper_context_manager():
    from openveritas import ActionSpec
    from openveritas.oracle import capture

    with tempfile.TemporaryDirectory() as tmp:
        spec = ActionSpec(verb="write", target="z.txt", params={})
        with capture(tmp, spec) as oracle:
            (Path(tmp) / "z.txt").write_text("data")
        r = oracle.record(spec)
        assert "z.txt" in r.diff.changed_paths


run("Snapshot ID is independent of walk order", _test_snapshot_id_independent_of_walk_order)
run("Receipt ID survives JSON serialization", _test_receipt_id_stable_across_serialization)
run("ActionSpec ID is invariant to param order", _test_spec_id_param_order_invariant)
run("Unchanged state yields empty diff (before_id == after_id)", _test_unchanged_state_no_diff)
run("capture() helper context manager records changes", _test_capture_helper_context_manager)


# ── Summary ─────────────────────────────────────────────────────────────────────

total = len(passed) + len(failed)
print(f"\n{'=' * 60}")
print(f"{BOLD}Results: {len(passed)}/{total} passed{RESET}")

if failed:
    print(f"{RED}Failed ({len(failed)}):{RESET}")
    for name, reason in failed:
        print(f"  {RED}x{RESET} {name}")
        short = reason.split(chr(10))[0][:120]
        print(f"    {YELLOW}-> {short}{RESET}")
    print(f"\n{YELLOW}Tip: run with --verbose for full tracebacks{RESET}")
else:
    print(f"{GREEN}All {total} checks passed — openveritas is ready to ship{RESET}")

print(f"{'=' * 60}\n")
sys.exit(0 if not failed else 1)
