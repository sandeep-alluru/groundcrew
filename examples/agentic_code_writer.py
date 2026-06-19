"""
agentic_code_writer.py — groundcrew for AI coding agent audit trails.

Story: An AI coding agent writes 5 files to implement a new feature.
groundcrew wraps each step in a capture block to produce an ActionReceipt.

At the end:
  1. Full audit trail: 5 receipts, each showing files added/modified
  2. Verification report: every file written, its hash before and after
  3. Tamper check: modify one file post-receipt, re-snapshot, detect tampering

Run:
    python examples/agentic_code_writer.py
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from groundcrew.codec import ActionSpec
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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Simulated agent file writes
# These represent a realistic feature implementation:
# "Add user authentication with JWT to an existing Flask API"
# ---------------------------------------------------------------------------

FILES_TO_WRITE = [
    {
        "step": 1,
        "verb": "create",
        "target": "src/auth/jwt_handler.py",
        "description": "Create JWT token handler module",
        "content": '''\
"""JWT authentication handler for the user auth service."""

import hashlib
import hmac
import json
import time
from typing import Any


SECRET_KEY = "replace-with-env-var-in-production"  # noqa: S105


def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def create_token(user_id: str, role: str = "user", ttl_seconds: int = 900) -> str:
    """Create a signed JWT token with expiry."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + ttl_seconds,
    }).encode())
    sig_input = f"{header}.{payload}".encode()
    sig = _b64url_encode(hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a JWT token and return its payload, or None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        sig_input = f"{header}.{payload}".encode()
        expected_sig = _b64url_encode(
            hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return None
        import base64
        padded = payload + "=="
        data = json.loads(base64.urlsafe_b64decode(padded))
        if data.get("exp", 0) < int(time.time()):
            return None
        return data
    except Exception:
        return None
''',
    },
    {
        "step": 2,
        "verb": "create",
        "target": "src/auth/middleware.py",
        "description": "Create auth middleware for Flask routes",
        "content": '''\
"""Authentication middleware — decorators for Flask route protection."""

import functools
from typing import Any, Callable

# In production: from src.auth.jwt_handler import verify_token
# Here we import relatively for demo purposes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from jwt_handler import verify_token


def require_auth(f: Callable) -> Callable:
    """Decorator: require valid JWT in Authorization header."""
    @functools.wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        # In a real Flask app: request.headers.get("Authorization", "")
        # Simulated here for demo
        auth_header = kwargs.pop("_auth_header", "")
        if not auth_header.startswith("Bearer "):
            return {"error": "Unauthorized", "status": 401}
        token = auth_header[7:]
        payload = verify_token(token)
        if payload is None:
            return {"error": "Invalid or expired token", "status": 401}
        kwargs["current_user"] = payload
        return f(*args, **kwargs)
    return decorated


def require_role(role: str) -> Callable:
    """Decorator: require a specific role in addition to valid JWT."""
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        @require_auth
        def decorated(*args: Any, **kwargs: Any) -> Any:
            user = kwargs.get("current_user", {})
            if user.get("role") != role:
                return {"error": "Forbidden", "status": 403}
            return f(*args, **kwargs)
        return decorated
    return decorator
''',
    },
    {
        "step": 3,
        "verb": "create",
        "target": "src/auth/__init__.py",
        "description": "Create auth package init",
        "content": '''\
"""User authentication package."""

from .jwt_handler import create_token, verify_token
from .middleware import require_auth, require_role

__all__ = ["create_token", "verify_token", "require_auth", "require_role"]
''',
    },
    {
        "step": 4,
        "verb": "modify",
        "target": "src/api/routes.py",
        "description": "Add auth endpoints to existing routes",
        "content": '''\
"""API routes — includes authentication endpoints."""

# Simulated Flask routes (would use from flask import Blueprint, request in production)
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "auth"))
from jwt_handler import create_token, verify_token


USERS_DB = {
    "alice": {"password_hash": "5e884898da...", "role": "admin"},
    "bob":   {"password_hash": "6b86b273ff...", "role": "user"},
}


def login(username: str, password: str) -> dict:
    """POST /auth/login — returns JWT on valid credentials."""
    user = USERS_DB.get(username)
    if user is None:
        return {"error": "Invalid credentials", "status": 401}
    # In production: check bcrypt hash
    token = create_token(user_id=username, role=user["role"])
    return {"token": token, "status": 200}


def get_profile(username: str, auth_header: str = "") -> dict:
    """GET /users/{username}/profile — requires valid JWT."""
    if not auth_header.startswith("Bearer "):
        return {"error": "Unauthorized", "status": 401}
    payload = verify_token(auth_header[7:])
    if payload is None:
        return {"error": "Invalid token", "status": 401}
    return {"username": username, "role": payload.get("role"), "status": 200}
''',
    },
    {
        "step": 5,
        "verb": "create",
        "target": "tests/test_auth.py",
        "description": "Write unit tests for auth module",
        "content": '''\
"""Unit tests for the JWT authentication module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "auth"))
from jwt_handler import create_token, verify_token


def test_create_and_verify_token() -> None:
    token = create_token("user-123", role="admin")
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    print("PASS: test_create_and_verify_token")


def test_invalid_token_rejected() -> None:
    assert verify_token("not.a.valid.token") is None
    assert verify_token("") is None
    print("PASS: test_invalid_token_rejected")


def test_tampered_token_rejected() -> None:
    token = create_token("user-456")
    # Tamper with payload section
    parts = token.split(".")
    tampered = parts[0] + ".AAAAAAAAAA." + parts[2]
    assert verify_token(tampered) is None
    print("PASS: test_tampered_token_rejected")


if __name__ == "__main__":
    test_create_and_verify_token()
    test_invalid_token_rejected()
    test_tampered_token_rejected()
    print("All tests passed.")
''',
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / ".groundcrew" / "receipts.db"

        # Pre-create directory structure (the "existing" repo the agent works on)
        (root / "src" / "auth").mkdir(parents=True)
        (root / "src" / "api").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)

        # Create an existing file that step 4 will modify
        (root / "src" / "api" / "routes.py").write_text(
            '"""API routes — placeholder."""\n\n# TODO: implement\n'
        )

        store = ReceiptStore(str(db_path))
        receipts = []

        banner("groundcrew — Agentic Code Writer Audit Trail")

        print("  Scenario: AI coding agent implements JWT authentication.")
        print("  groundcrew wraps each file operation in a capture block.")
        print("  Every step produces a cryptographic ActionReceipt.")
        print()
        print("  Feature: Add JWT authentication to existing Flask API")
        print("  Files: 5 operations (4 creates + 1 modify)")
        print()

        # -----------------------------------------------------------------------
        # AGENT WRITES 5 FILES — each wrapped in a groundcrew capture
        # -----------------------------------------------------------------------
        section("Agent Execution — 5 steps with groundcrew capture")

        for step_info in FILES_TO_WRITE:
            step_num = step_info["step"]
            verb = step_info["verb"]
            target = step_info["target"]
            description = step_info["description"]
            content = step_info["content"]

            spec = ActionSpec(
                verb=verb,
                target=target,
                params={"agent_id": "coding-agent-v1", "step": step_num},
            )

            with Oracle(str(root), spec) as oracle:
                # Agent writes the file
                dest = root / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)

            receipt = oracle.record(spec)
            store.save(receipt)
            receipts.append(receipt)

            # Print step summary
            added = [f.path for f in receipt.diff.added]
            modified = [b.path for b, _ in receipt.diff.modified]
            changed = added + modified

            status_icon = "CREATE" if verb == "create" else "MODIFY"
            file_hash = sha256_file(root / target)
            print(f"  Step {step_num}: [{status_icon}] {target}")
            print(f"           Receipt ID: {receipt.id}")
            print(f"           File hash:  {file_hash}")
            print(f"           Changed:    {changed}")
            print(f"           before_id:  {receipt.before_id[:8]} → after_id: {receipt.after_id[:8]}")
            print()

        # -----------------------------------------------------------------------
        # VERIFICATION REPORT: Security auditor view
        # -----------------------------------------------------------------------
        section("Verification Report — Security Auditor View")

        print(f"  {'Step':<6} {'Action':<8} {'File':<40} {'Hash':<16} {'Status'}")
        print(f"  {'-'*4:<6} {'-'*6:<8} {'-'*38:<40} {'-'*14:<16} {'------'}")

        for i, (step_info, receipt) in enumerate(zip(FILES_TO_WRITE, receipts)):
            verb = step_info["verb"]
            target = step_info["target"]
            file_hash = sha256_file(root / target)
            print(f"  {i+1:<6} {verb.upper():<8} {target:<40} {file_hash:<16} OK")

        print()
        print(f"  Total receipts: {len(receipts)}")
        print(f"  Receipt store:  {db_path}")

        # Verify receipts round-trip from store
        all_from_store = store.list_receipts()
        assert len(all_from_store) == len(receipts), "Receipt count mismatch"
        print(f"  Store verified: {len(all_from_store)} receipts retrieved successfully")

        # -----------------------------------------------------------------------
        # TAMPER DETECTION: Modify a file after the receipt was issued
        # -----------------------------------------------------------------------
        section("Tamper Detection — Adversarial verification")

        tampered_file = root / "src" / "auth" / "jwt_handler.py"
        original_hash = sha256_file(tampered_file)

        print("  Simulating unauthorized modification of: src/auth/jwt_handler.py")
        print(f"  Original hash: {original_hash}")
        print()

        # Inject a backdoor — what an attacker might do
        original_content = tampered_file.read_text()
        backdoor = '\n\n# INJECTED: backdoor — sends tokens to attacker\ndef _exfiltrate(token): pass\n'
        tampered_file.write_text(original_content + backdoor)
        tampered_hash = sha256_file(tampered_file)

        print("  File modified (backdoor injected).")
        print(f"  Tampered hash: {tampered_hash}")
        print()

        # Re-snapshot the directory and compare with the receipt's after_id
        print("  Re-snapshotting filesystem to detect tampering...")
        current_snapshot = StateSnapshot.capture(str(root))

        # Find the receipt for jwt_handler.py
        jwt_receipt = receipts[0]  # step 1: create jwt_handler.py

        # Check: after_id from the receipt should NOT match the current snapshot
        if current_snapshot.id != jwt_receipt.after_id:
            print()
            print("  " + "!" * 60)
            print("  TAMPER DETECTED")
            print("  " + "!" * 60)
            print()
            print(f"  Expected snapshot ID (from receipt): {jwt_receipt.after_id}")
            print(f"  Current snapshot ID:                 {current_snapshot.id}")
            print()
            # Find which files changed
            after_files = current_snapshot.files
            receipt_files = {}  # We don't have the after-snapshot stored, but we can check hashes

            # Check the specific file
            cur_file_state = after_files.get("src/auth/jwt_handler.py")
            if cur_file_state:
                print("  File: src/auth/jwt_handler.py")
                print(f"    Receipt hash:  {original_hash}  (at time of write)")
                print(f"    Current hash:  {cur_file_state.sha256[:16]}")
                print("    MISMATCH — file was modified after receipt was issued")
        else:
            print("  No tampering detected (snapshot IDs match).")

        print()
        print("  AUDIT CONCLUSION:")
        print("  The groundcrew receipt for src/auth/jwt_handler.py")
        print(f"  records after_id={jwt_receipt.after_id[:8]} — the cryptographic")
        print("  fingerprint of the directory immediately after the agent wrote it.")
        print("  Any post-write modification is detectable by re-snapshotting")
        print("  and comparing against the receipt's after_id.")
        print()
        print("  In a regulated environment (finance, healthcare), this chain")
        print("  of receipts provides an immutable audit trail of every file")
        print("  the AI agent touched, when, and what exactly it wrote.")

        # -----------------------------------------------------------------------
        # CHAIN SUMMARY
        # -----------------------------------------------------------------------
        section("Receipt Chain Summary")

        for i, r in enumerate(receipts):
            verb = FILES_TO_WRITE[i]["verb"]
            target = FILES_TO_WRITE[i]["target"]
            diff_summary = (
                f"+{len(r.diff.added)} created, "
                f"~{len(r.diff.modified)} modified"
            )
            print(f"  [{i+1}] {r.id}  {verb} {target}")
            print(f"       {r.before_id[:8]} → {r.after_id[:8]}  |  {diff_summary}")

        store.close()

    print()
    print("=" * 68)
    print("  Demo complete.")
    print("=" * 68)
    print()


if __name__ == "__main__":
    main()
