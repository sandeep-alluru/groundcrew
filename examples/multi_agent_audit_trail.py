"""
multi_agent_audit_trail.py — groundcrew chain-of-custody for multi-agent pipelines.

Story: 3 agents work sequentially on a codebase:
  PlannerAgent  → CoderAgent → ReviewerAgent

Each agent has a groundcrew ActionReceipt. At the end, verify that each
agent's after_id matches the next agent's before_id — an unbroken chain of
custody from initial state to final output.

This is the kind of audit required for regulated AI deployments in finance
and healthcare, where you must prove that no unauthorized modifications
occurred between agent handoffs.

Run:
    python examples/multi_agent_audit_trail.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.snapshot import StateSnapshot


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
# Agent runners
# ---------------------------------------------------------------------------

def run_planner_agent(root: Path) -> tuple[ActionReceipt, Oracle]:
    """
    PlannerAgent: Creates the project structure and specification files.
    Simulates: an LLM agent that plans the implementation of a new feature.
    """
    spec = ActionSpec(
        verb="plan",
        target="project-root",
        params={
            "agent_id": "planner-agent-v1",
            "model": "claude-3-5-sonnet-20241022",  # what a real integration would use
            "task": "plan JWT authentication feature",
        },
    )

    with Oracle(str(root), spec) as oracle:
        # PlannerAgent creates spec and skeleton files
        (root / "PLAN.md").write_text(
            "# JWT Authentication Implementation Plan\n\n"
            "## Scope\n"
            "Add stateless JWT authentication to the existing API.\n\n"
            "## Files to create\n"
            "- src/auth/token.py — JWT creation and verification\n"
            "- src/auth/guards.py — Route protection decorators\n"
            "- tests/test_auth.py — Unit tests\n\n"
            "## Files to modify\n"
            "- src/api/routes.py — Add /login endpoint\n\n"
            "## Acceptance criteria\n"
            "- All tests pass\n"
            "- No hardcoded secrets\n"
            "- Token expiry enforced\n"
        )
        (root / "src" / "auth").mkdir(parents=True, exist_ok=True)
        (root / "src" / "auth" / "__init__.py").write_text(
            '"""Authentication package — scaffolded by PlannerAgent."""\n'
        )

    receipt = oracle.record(spec)
    return receipt, oracle


def run_coder_agent(root: Path, before_id: str) -> tuple[ActionReceipt, Oracle]:
    """
    CoderAgent: Implements the plan created by PlannerAgent.
    before_id should equal PlannerAgent's after_id for chain integrity.
    """
    spec = ActionSpec(
        verb="implement",
        target="src/auth/",
        params={
            "agent_id": "coder-agent-v1",
            "model": "claude-3-5-sonnet-20241022",
            "task": "implement JWT auth per PLAN.md",
            "expected_before_id": before_id,  # passed explicitly for verification
        },
    )

    with Oracle(str(root), spec) as oracle:
        # Verify handoff: CoderAgent checks it's starting from the right state
        current_snapshot = StateSnapshot.capture(str(root))
        if current_snapshot.id != before_id:
            raise RuntimeError(
                f"CoderAgent handoff verification failed: "
                f"expected state {before_id[:8]}, got {current_snapshot.id[:8]}"
            )

        # CoderAgent implements the files
        (root / "src" / "auth" / "token.py").write_text(
            '"""JWT token creation and verification."""\n\n'
            'import hashlib, hmac, json, time\n\n'
            'SECRET = "change-me-via-env"  # noqa: S105\n\n'
            'def _b64(data: bytes) -> str:\n'
            '    import base64\n'
            '    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()\n\n'
            'def create(user_id: str, ttl: int = 900) -> str:\n'
            '    h = _b64(json.dumps({"alg": "HS256"}).encode())\n'
            '    p = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl}).encode())\n'
            '    s = _b64(hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())\n'
            '    return f"{h}.{p}.{s}"\n\n'
            'def verify(token: str) -> dict | None:\n'
            '    try:\n'
            '        h, p, s = token.split(".")\n'
            '        exp_s = _b64(hmac.new(SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())\n'
            '        if not hmac.compare_digest(s, exp_s): return None\n'
            '        import base64\n'
            '        data = json.loads(base64.urlsafe_b64decode(p + "=="))\n'
            '        return data if data["exp"] > int(time.time()) else None\n'
            '    except Exception:\n'
            '        return None\n'
        )
        (root / "src" / "auth" / "guards.py").write_text(
            '"""Route protection decorators."""\n\n'
            'import functools\n'
            'from .token import verify\n\n'
            'def require_auth(f):\n'
            '    @functools.wraps(f)\n'
            '    def wrapper(*args, auth_header="", **kw):\n'
            '        if not auth_header.startswith("Bearer "): return {"status": 401}\n'
            '        payload = verify(auth_header[7:])\n'
            '        if not payload: return {"status": 401}\n'
            '        kw["user"] = payload\n'
            '        return f(*args, **kw)\n'
            '    return wrapper\n'
        )
        (root / "src" / "api").mkdir(parents=True, exist_ok=True)
        (root / "src" / "api" / "routes.py").write_text(
            '"""API routes — implemented by CoderAgent."""\n\n'
            'from src.auth.token import create\n'
            'from src.auth.guards import require_auth\n\n'
            'USERS = {"alice": "hunter2", "bob": "swordfish"}\n\n'
            'def login(username: str, password: str) -> dict:\n'
            '    if USERS.get(username) != password:\n'
            '        return {"error": "Unauthorized", "status": 401}\n'
            '    return {"token": create(username), "status": 200}\n\n'
            '@require_auth\n'
            'def profile(user: dict = None) -> dict:\n'
            '    return {"user_id": user["sub"], "status": 200}\n'
        )
        (root / "tests").mkdir(exist_ok=True)
        (root / "tests" / "test_auth.py").write_text(
            '"""Auth tests — written by CoderAgent."""\n\n'
            'import sys, os\n'
            'sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n'
            'from src.auth.token import create, verify\n\n'
            'def test_roundtrip():\n'
            '    t = create("user-1")\n'
            '    p = verify(t)\n'
            '    assert p and p["sub"] == "user-1", f"Roundtrip failed: {p}"\n'
            '    print("PASS test_roundtrip")\n\n'
            'def test_tamper():\n'
            '    t = create("user-2")\n'
            '    tampered = t[:20] + "XXXXX" + t[25:]\n'
            '    assert verify(tampered) is None\n'
            '    print("PASS test_tamper")\n\n'
            'if __name__ == "__main__":\n'
            '    test_roundtrip()\n'
            '    test_tamper()\n'
            '    print("All tests passed.")\n'
        )

    receipt = oracle.record(spec)
    return receipt, oracle


def run_reviewer_agent(root: Path, before_id: str) -> tuple[ActionReceipt, Oracle]:
    """
    ReviewerAgent: Reviews the code and adds review annotations.
    before_id should equal CoderAgent's after_id for chain integrity.
    """
    spec = ActionSpec(
        verb="review",
        target="src/",
        params={
            "agent_id": "reviewer-agent-v1",
            "model": "claude-3-opus-20240229",
            "task": "security review of JWT auth implementation",
            "expected_before_id": before_id,
        },
    )

    with Oracle(str(root), spec) as oracle:
        # Verify handoff
        current_snapshot = StateSnapshot.capture(str(root))
        if current_snapshot.id != before_id:
            raise RuntimeError(
                f"ReviewerAgent handoff verification failed: "
                f"expected {before_id[:8]}, got {current_snapshot.id[:8]}"
            )

        # ReviewerAgent adds a review report
        (root / "REVIEW.md").write_text(
            "# Security Review Report\n\n"
            "**Reviewer:** ReviewerAgent (claude-3-opus-20240229)\n"
            "**Date:** 2026-06-19\n"
            "**Status:** APPROVED WITH NOTES\n\n"
            "## Findings\n\n"
            "### Critical\n"
            "- None\n\n"
            "### High\n"
            "- `SECRET = 'change-me-via-env'` hardcoded default. "
            "Must be overridden via environment variable in production.\n\n"
            "### Medium\n"
            "- No rate limiting on /login endpoint. Add before production.\n"
            "- Token payload does not include `iss` claim. Add for auditability.\n\n"
            "### Low\n"
            "- Missing type annotations on `guards.py` decorators.\n\n"
            "## Test Coverage\n"
            "- test_roundtrip: PASS\n"
            "- test_tamper: PASS\n"
            "- Coverage: 78% (acceptable for MVP)\n\n"
            "## Verdict\n"
            "Approved for staging deployment. Address High finding before production.\n"
        )
        # Reviewer also annotates the token file with an inline comment
        token_path = root / "src" / "auth" / "token.py"
        existing = token_path.read_text()
        token_path.write_text(
            existing.replace(
                'SECRET = "change-me-via-env"  # noqa: S105',
                'SECRET = "change-me-via-env"  # noqa: S105  # REVIEW: override via JWT_SECRET env var',
            )
        )

    receipt = oracle.record(spec)
    return receipt, oracle


# ---------------------------------------------------------------------------
# Chain of custody verifier
# ---------------------------------------------------------------------------

def verify_chain(receipts: list[ActionReceipt]) -> tuple[bool, list[str]]:
    """
    Verify that each receipt's after_id matches the next receipt's before_id.

    Returns:
        (chain_intact, list of findings)
    """
    findings = []
    chain_intact = True

    for i in range(len(receipts) - 1):
        curr = receipts[i]
        next_ = receipts[i + 1]

        agent_curr = curr.spec.params.get("agent_id", f"agent-{i}")
        agent_next = next_.spec.params.get("agent_id", f"agent-{i+1}")

        if curr.after_id == next_.before_id:
            findings.append(
                f"  [OK]  {agent_curr} → {agent_next}: "
                f"after_id={curr.after_id[:8]} matches before_id={next_.before_id[:8]}"
            )
        else:
            chain_intact = False
            findings.append(
                f"  [BREAK]  {agent_curr} → {agent_next}: "
                f"after_id={curr.after_id[:8]} != before_id={next_.before_id[:8]}"
            )

    return chain_intact, findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Project root: the directory the agents work in
        root = tmp_path / "project"
        root.mkdir()
        # Receipt store lives OUTSIDE the project root so it doesn't
        # appear in snapshots — same as how .git lives outside your src/
        db_path = tmp_path / "groundcrew-store" / "pipeline.db"

        # Initial project state (before any agent runs)
        (root / "src").mkdir()
        (root / "README.md").write_text(
            "# MyApp\n\nStatus: pre-implementation\n"
        )

        store = ReceiptStore(str(db_path))

        banner("groundcrew — Multi-Agent Chain of Custody Audit")

        print("  3-agent sequential pipeline:")
        print("  PlannerAgent → CoderAgent → ReviewerAgent")
        print()
        print("  Each agent's ActionReceipt records its before/after state.")
        print("  Chain integrity: after_id[n] must equal before_id[n+1].")
        print("  This proves no unauthorized modifications occurred between")
        print("  agent handoffs — required for regulated AI deployments.")
        print()

        receipts: list[ActionReceipt] = []
        agent_names = ["PlannerAgent", "CoderAgent", "ReviewerAgent"]

        # -----------------------------------------------------------------------
        # Run agents sequentially
        # -----------------------------------------------------------------------
        section("Agent Pipeline Execution")

        # Step 1: PlannerAgent
        print("  [1/3] PlannerAgent — planning implementation...")
        receipt_planner, _ = run_planner_agent(root)
        store.save(receipt_planner)
        receipts.append(receipt_planner)
        planner_changed = sorted(receipt_planner.diff.changed_paths)
        print(f"        Receipt: {receipt_planner.id}")
        print(f"        State:   {receipt_planner.before_id[:8]} → {receipt_planner.after_id[:8]}")
        print(f"        Created: {planner_changed}")
        print()

        # Step 2: CoderAgent (receives PlannerAgent's after_id as its expected before_id)
        print("  [2/3] CoderAgent — implementing plan...")
        receipt_coder, _ = run_coder_agent(root, before_id=receipt_planner.after_id)
        store.save(receipt_coder)
        receipts.append(receipt_coder)
        coder_changed = sorted(receipt_coder.diff.changed_paths)
        print(f"        Receipt: {receipt_coder.id}")
        print(f"        State:   {receipt_coder.before_id[:8]} → {receipt_coder.after_id[:8]}")
        print(f"        Created: {coder_changed}")
        print()

        # Step 3: ReviewerAgent (receives CoderAgent's after_id)
        print("  [3/3] ReviewerAgent — security review...")
        receipt_reviewer, _ = run_reviewer_agent(root, before_id=receipt_coder.after_id)
        store.save(receipt_reviewer)
        receipts.append(receipt_reviewer)
        reviewer_changed = sorted(receipt_reviewer.diff.changed_paths)
        print(f"        Receipt: {receipt_reviewer.id}")
        print(f"        State:   {receipt_reviewer.before_id[:8]} → {receipt_reviewer.after_id[:8]}")
        print(f"        Changed: {reviewer_changed}")
        print()

        # -----------------------------------------------------------------------
        # CHAIN OF CUSTODY VERIFICATION
        # -----------------------------------------------------------------------
        section("Chain of Custody Verification")

        chain_intact, findings = verify_chain(receipts)

        print("  Verifying handoff integrity:")
        print()
        for finding in findings:
            print(finding)

        print()
        if chain_intact:
            print("  " + "=" * 62)
            print("  Chain of Custody — VERIFIED")
            print("  PlannerAgent → CoderAgent → ReviewerAgent")
            print("  All before/after hashes match. No unauthorized")
            print("  modifications occurred between agent handoffs.")
            print("  " + "=" * 62)
        else:
            print("  " + "!" * 62)
            print("  Chain of Custody — BROKEN")
            print("  Hash mismatch detected between agent handoffs.")
            print("  Unauthorized modification may have occurred.")
            print("  " + "!" * 62)

        # -----------------------------------------------------------------------
        # CHAIN VISUALIZATION
        # -----------------------------------------------------------------------
        section("Chain Visualization")

        initial_snapshot = StateSnapshot.capture.__doc__  # just for reference
        snap_ids = [r.before_id[:8] for r in receipts] + [receipts[-1].after_id[:8]]

        print(f"  Initial state:     [{snap_ids[0]}]  (empty project)")
        print()

        for i, receipt in enumerate(receipts):
            agent = receipt.spec.params.get("agent_id", f"agent-{i}")
            arrow_width = 20
            print(f"       │")
            print(f"       │  {receipt.spec.verb.upper()} — {agent}")
            print(f"       │  Receipt: {receipt.id}")
            print(f"       ▼")
            n_changed = len(receipt.diff.changed_paths)
            label = "(final state)" if i == len(receipts) - 1 else ""
            print(f"  [{snap_ids[i+1]}]  ({n_changed} file(s) changed) {label}")
            if i < len(receipts) - 1:
                print()

        # -----------------------------------------------------------------------
        # FINAL AUDIT REPORT
        # -----------------------------------------------------------------------
        section("Final Audit Report")

        all_from_store = store.list_receipts()
        total_files_changed = set()
        for r in all_from_store:
            total_files_changed.update(r.diff.changed_paths)

        print(f"  Pipeline: PlannerAgent → CoderAgent → ReviewerAgent")
        print(f"  Receipts issued:       {len(all_from_store)}")
        print(f"  Total files touched:   {len(total_files_changed)}")
        print(f"  Chain of custody:      {'INTACT' if chain_intact else 'BROKEN'}")
        print()
        print(f"  Files in final delivery:")
        for fpath in sorted(total_files_changed):
            print(f"    {fpath}")
        print()
        print("  Each file's complete write history is recorded in the")
        print("  ReceiptStore and can be reconstructed by the audit team.")
        print()
        print("  For regulated deployments, attach the receipt store DB to")
        print("  the deployment record to prove AI agent chain of custody.")

        store.close()

    print()
    print("=" * 68)
    chain_word = "VERIFIED" if chain_intact else "BROKEN — DEPLOY BLOCKED"
    print(f"  Chain of custody: {chain_word}")
    print("=" * 68)
    print()

    return 0 if chain_intact else 1


if __name__ == "__main__":
    sys.exit(main())
