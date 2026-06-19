"""
deployment_gate.py — groundcrew as a deployment safety gate.

Story: A deployment pipeline uses groundcrew to verify that an AI agent
only modified files it was authorized to touch.

Two runs:
  Run 1 (PASS): Agent modifies src/api.py and src/routes.py — both authorized.
  Run 2 (FAIL): Agent also modifies config/secrets.yml — UNAUTHORIZED.

The gate logic: compare actual changed paths against the authorized path prefix.
Any unauthorized change blocks deployment.

Run:
    python examples/deployment_gate.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from groundcrew.codec import ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)
    print()


def section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")
    print()


# ---------------------------------------------------------------------------
# Deployment gate logic
# ---------------------------------------------------------------------------

def check_deployment_gate(
    receipt_id: str,
    changed_paths: set[str],
    authorized_prefixes: list[str],
) -> tuple[bool, list[str], list[str]]:
    """
    Check whether all changed paths fall within authorized prefixes.

    Returns:
        (gate_passed, authorized_changes, unauthorized_changes)
    """
    authorized_changes = []
    unauthorized_changes = []

    for path in sorted(changed_paths):
        is_authorized = any(
            path.startswith(prefix) for prefix in authorized_prefixes
        )
        if is_authorized:
            authorized_changes.append(path)
        else:
            unauthorized_changes.append(path)

    gate_passed = len(unauthorized_changes) == 0
    return gate_passed, authorized_changes, unauthorized_changes


def print_gate_result(
    run_num: int,
    gate_passed: bool,
    authorized_changes: list[str],
    unauthorized_changes: list[str],
    authorized_prefixes: list[str],
) -> None:
    status = "PASS" if gate_passed else "FAIL — DEPLOY BLOCKED"
    border = "=" if gate_passed else "!"
    print(f"  {border * 62}")
    print(f"  Deployment Gate: {status}")
    print(f"  {border * 62}")
    print()
    print(f"  Authorized scope: {authorized_prefixes}")
    print()

    if authorized_changes:
        print(f"  AUTHORIZED CHANGES ({len(authorized_changes)}):")
        for path in authorized_changes:
            print(f"    [OK]  {path}")
    else:
        print("  AUTHORIZED CHANGES: (none)")

    if unauthorized_changes:
        print()
        print(f"  UNAUTHORIZED CHANGES ({len(unauthorized_changes)}):")
        for path in unauthorized_changes:
            print(f"    [BLOCK]  {path}")
        print()
        print("  REASON: Agent modified files outside the authorized scope.")
        print("  ACTION: Deployment blocked. Investigate agent behavior.")
    else:
        print()
        print("  RESULT: All changes within authorized scope. Deployment approved.")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / ".groundcrew" / "deploy_gate.db"

        # Set up initial codebase structure
        (root / "src").mkdir()
        (root / "config").mkdir()
        (root / "tests").mkdir()

        # Pre-existing files
        (root / "src" / "api.py").write_text(
            '"""API module — v1.0"""\n\ndef get_users():\n    return []\n'
        )
        (root / "src" / "routes.py").write_text(
            '"""Routes — v1.0"""\n\nroutes = []\n'
        )
        (root / "src" / "models.py").write_text(
            '"""Data models"""\n\nclass User:\n    pass\n'
        )
        (root / "config" / "app.yml").write_text(
            "app:\n  name: myapp\n  debug: false\n"
        )
        (root / "config" / "secrets.yml").write_text(
            "secrets:\n  db_password: placeholder\n  jwt_secret: placeholder\n"
        )
        (root / "tests" / "test_api.py").write_text(
            '"""API tests"""\n\ndef test_placeholder():\n    pass\n'
        )

        store = ReceiptStore(str(db_path))
        overall_exit_code = 0

        banner("groundcrew — Deployment Safety Gate Demo")

        print("  Deployment gate policy:")
        print("  An AI agent is authorized to modify files under src/ only.")
        print("  Any change outside src/ blocks deployment.")
        print()
        print("  Two simulated deployment runs:")
        print("  Run 1: Agent modifies src/api.py + src/routes.py [expected: PASS]")
        print("  Run 2: Agent also modifies config/secrets.yml   [expected: FAIL]")

        # Authorized prefixes — only src/ files are allowed
        AUTHORIZED_PREFIXES = ["src/"]

        # -----------------------------------------------------------------------
        # RUN 1: Authorized changes only
        # -----------------------------------------------------------------------
        section("Run 1 — Agent: Update API v1.0 → v2.0 (authorized scope)")

        print("  Agent task: Refactor API to add pagination support.")
        print("  Expected changes: src/api.py, src/routes.py")
        print()

        spec_run1 = ActionSpec(
            verb="refactor",
            target="src/",
            params={
                "agent_id": "refactor-agent-v1",
                "pr": "feat/api-pagination",
                "authorized_scope": AUTHORIZED_PREFIXES,
            },
        )

        with Oracle(str(root), spec_run1) as oracle_run1:
            # Agent modifies only authorized files
            (root / "src" / "api.py").write_text(
                '"""API module — v2.0 with pagination"""\n\n'
                'def get_users(page: int = 1, per_page: int = 20):\n'
                '    """Return paginated users."""\n'
                '    return {"page": page, "per_page": per_page, "users": []}\n'
            )
            (root / "src" / "routes.py").write_text(
                '"""Routes — v2.0 with pagination support"""\n\n'
                'routes = [\n'
                '    ("/users", "get_users", {"methods": ["GET"]}),\n'
                '    ("/users/<int:page>", "get_users", {"methods": ["GET"]}),\n'
                ']\n'
            )

        receipt_run1 = oracle_run1.record(spec_run1)
        store.save(receipt_run1)

        changed_paths = receipt_run1.diff.changed_paths
        print(f"  Files changed: {sorted(changed_paths)}")
        print(f"  Receipt ID:    {receipt_run1.id}")
        print(f"  before_id:     {receipt_run1.before_id[:8]}")
        print(f"  after_id:      {receipt_run1.after_id[:8]}")
        print()

        gate_passed, authorized, unauthorized = check_deployment_gate(
            receipt_run1.id,
            changed_paths,
            AUTHORIZED_PREFIXES,
        )
        print_gate_result(1, gate_passed, authorized, unauthorized, AUTHORIZED_PREFIXES)

        if not gate_passed:
            overall_exit_code = 1

        # -----------------------------------------------------------------------
        # RUN 2: Agent touches unauthorized file
        # -----------------------------------------------------------------------
        section("Run 2 — Agent: Feature addition that leaks into config/ (unauthorized)")

        print("  Agent task: Add database connection pooling.")
        print("  Expected changes: src/api.py (update connection logic)")
        print("  Actual changes:   src/api.py + config/secrets.yml (UNAUTHORIZED)")
        print()
        print("  Note: the agent tried to 'helpfully' update secrets.yml")
        print("  with a new db_pool_size setting — but this is outside its scope.")
        print()

        spec_run2 = ActionSpec(
            verb="feature",
            target="src/",
            params={
                "agent_id": "feature-agent-v1",
                "pr": "feat/db-connection-pooling",
                "authorized_scope": AUTHORIZED_PREFIXES,
            },
        )

        with Oracle(str(root), spec_run2) as oracle_run2:
            # Agent modifies authorized file...
            (root / "src" / "api.py").write_text(
                '"""API module — v2.1 with connection pooling"""\n\n'
                'POOL_SIZE = 10\n\n'
                'def get_users(page: int = 1, per_page: int = 20):\n'
                '    """Return paginated users via connection pool."""\n'
                '    return {"page": page, "per_page": per_page, "users": [], "pool": POOL_SIZE}\n'
            )
            # ...AND an unauthorized file (the security violation)
            (root / "config" / "secrets.yml").write_text(
                "secrets:\n"
                "  db_password: placeholder\n"
                "  jwt_secret: placeholder\n"
                "  db_pool_size: 10  # added by agent — UNAUTHORIZED\n"
            )

        receipt_run2 = oracle_run2.record(spec_run2)
        store.save(receipt_run2)

        changed_paths2 = receipt_run2.diff.changed_paths
        print(f"  Files changed: {sorted(changed_paths2)}")
        print(f"  Receipt ID:    {receipt_run2.id}")
        print(f"  before_id:     {receipt_run2.before_id[:8]}")
        print(f"  after_id:      {receipt_run2.after_id[:8]}")
        print()

        gate_passed2, authorized2, unauthorized2 = check_deployment_gate(
            receipt_run2.id,
            changed_paths2,
            AUTHORIZED_PREFIXES,
        )
        print_gate_result(2, gate_passed2, authorized2, unauthorized2, AUTHORIZED_PREFIXES)

        if not gate_passed2:
            overall_exit_code = 1

        # -----------------------------------------------------------------------
        # RECEIPTS IN STORE
        # -----------------------------------------------------------------------
        section("Receipt Store — Immutable deployment audit log")

        all_receipts = store.list_receipts()
        print(f"  {len(all_receipts)} deployment receipt(s) on record:\n")
        for r in all_receipts:
            paths = sorted(r.diff.changed_paths)
            gate_ok, auth, unauth = check_deployment_gate(r.id, r.diff.changed_paths, AUTHORIZED_PREFIXES)
            result = "APPROVED" if gate_ok else "BLOCKED"
            print(f"  [{result}]  Receipt {r.id}  ({r.spec.verb} {r.spec.target})")
            for p in paths:
                mark = "OK" if any(p.startswith(pfx) for pfx in AUTHORIZED_PREFIXES) else "BLOCKED"
                print(f"             [{mark}]  {p}")
            print()

        # -----------------------------------------------------------------------
        # SUMMARY
        # -----------------------------------------------------------------------
        section("Gate Summary")

        print("  Run 1: AUTHORIZED CHANGES ONLY  — deployment APPROVED")
        print("         Files: src/api.py, src/routes.py (within src/ scope)")
        print()
        print("  Run 2: UNAUTHORIZED CHANGE DETECTED — deployment BLOCKED")
        print("         AUTHORIZED:   src/api.py")
        print("         UNAUTHORIZED: config/secrets.yml")
        print()
        print("  The groundcrew receipt provides cryptographic proof of exactly")
        print("  which files changed and when, enabling post-incident forensics")
        print("  in addition to the pre-deploy gate check.")

        store.close()

    print()
    print("=" * 68)
    exit_word = "PASSED" if overall_exit_code == 0 else "FAILED (unauthorized changes detected)"
    print(f"  Deployment gate overall: {exit_word}")
    print("=" * 68)
    print()

    return overall_exit_code


if __name__ == "__main__":
    # Exit with 0 because the demo intentionally shows both pass and fail paths —
    # the "fail" is expected behavior in this demonstration.
    # In a real CI pipeline, you would exit with the gate result.
    main()
    sys.exit(0)
