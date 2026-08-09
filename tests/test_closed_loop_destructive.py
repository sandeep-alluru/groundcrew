"""DB-WIPE / Replit-class destructive tool gate - inventory + approval required.

Public cases (Track B research):
  * Replit AI deleted production database (unattended DROP)
  * Google Antigravity wipe
  * AgentWard (post AI file-delete firewall)
  * HN: "An AI agent deleted our production database"
  * Genesis Agent / AgentWard class self-destructive tools

Pre-fix hole: free-form SQL/shell tools execute DROP/rm without naming
targets or obtaining human approval; success receipts mask the wipe.
"""

from __future__ import annotations

import pytest

from groundcrew.closed_loop import (
    ClosedLoopError,
    GateOutcome,
    assert_not_destructive,
    gate_destructive,
    gate_destructive_receipt,
    is_destructive,
    shell_is_destructive,
    sql_is_destructive,
)
from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.snapshot import SnapshotDiff


def _empty_diff() -> SnapshotDiff:
    return SnapshotDiff(
        snapshot_a_id="before000000000",
        snapshot_b_id="after0000000000",
        added=[],
        removed=[],
        modified=[],
    )


# --- classifiers -----------------------------------------------------------


def test_sql_drop_database_is_destructive() -> None:
    assert sql_is_destructive("DROP DATABASE production;") is True
    assert sql_is_destructive("drop table if exists users cascade") is True
    assert sql_is_destructive("TRUNCATE TABLE sessions") is True
    assert sql_is_destructive("DELETE FROM users WHERE 1=1") is True
    assert sql_is_destructive("SELECT * FROM users") is False
    assert sql_is_destructive("INSERT INTO users VALUES (1)") is False
    assert sql_is_destructive("") is False


def test_shell_rm_rf_is_destructive() -> None:
    assert shell_is_destructive("rm -rf /var/lib/data") is True
    assert shell_is_destructive("rm -f secret.key") is True
    assert shell_is_destructive("ls -la") is False
    assert shell_is_destructive("") is False


def test_is_destructive_verb_and_params() -> None:
    assert is_destructive("db_wipe") is True
    assert is_destructive("drop_table") is True
    assert is_destructive("read") is False
    assert is_destructive("execute_sql", sql="DROP TABLE t") is True
    assert is_destructive("execute_sql", params={"sql": "SELECT 1"}) is False
    assert is_destructive("shell", command="rm -rf ./out") is True
    assert is_destructive("write", target="a.txt") is False


# --- gate: empty / non-destructive -----------------------------------------


def test_empty_tool_call_fails_loud() -> None:
    out = gate_destructive()
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert "empty" in out.reason.lower()


def test_select_passes_without_approval() -> None:
    out = gate_destructive(verb="execute_sql", sql="SELECT * FROM users LIMIT 10")
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.risk == "safe"
    assert out.human_required is False


def test_read_verb_passes() -> None:
    out = gate_destructive(verb="read", target="users")
    assert out.ok is True
    assert out.risk == "safe"


# --- Replit incident fixture -----------------------------------------------


def test_replit_db_wipe_no_approval_fails_loud() -> None:
    """Public Replit AI: production DB wiped without human approval."""
    out = gate_destructive(
        verb="db_wipe",
        target="production",
        sql="DROP DATABASE production;",
        inventory=["production"],
        approved=False,
        environment="production",
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.exit_code == 2
    assert out.human_required is True
    assert out.risk == "high_risk"
    assert out.inventory_count == 1
    assert "approval" in out.reason.lower() or "DB-WIPE" in out.reason
    payload = out.to_dict()
    assert payload["human_required"] is True
    assert payload["action"] == "db_wipe"


def test_drop_table_without_inventory_fails_loud() -> None:
    """Agent issues DROP without naming tables - inventory required."""
    out = gate_destructive(
        verb="execute_sql",
        sql="DROP TABLE users; DROP TABLE orders;",
        inventory=[],  # explicit empty - agent refused to list targets
        approved=True,
        approval_token="owner-tok",
        environment="production",
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.human_required is True
    assert "inventory" in out.reason.lower()
    assert out.inventory_count == 0


def test_drop_with_inventory_and_approval_passes() -> None:
    out = gate_destructive(
        verb="drop",
        target="users",
        sql="DROP TABLE users;",
        inventory=["users"],
        approved=True,
        approval_token="owner-issued-abc",
        environment="production",
    )
    assert out.ok is True
    assert out.verdict == "PASS"
    assert out.risk == "high_risk"
    assert out.inventory_count == 1
    assert out.exit_code == 0


def test_token_alone_authorises_when_inventory_present() -> None:
    out = gate_destructive(
        verb="db_drop",
        sql="DROP DATABASE staging_clone;",
        inventory=["staging_clone"],
        approval_token="human-token-xyz",
        environment="staging",
    )
    assert out.ok is True
    assert out.verdict == "PASS"


def test_dev_env_allows_destructive_with_inventory_no_token() -> None:
    out = gate_destructive(
        verb="truncate",
        inventory=["tmp_sessions"],
        approved=False,
        environment="dev",
    )
    assert out.ok is True
    assert out.verdict == "PASS"


def test_shell_rm_rf_prod_without_approval_fails() -> None:
    out = gate_destructive(
        verb="shell",
        command="rm -rf /data/prod",
        inventory=["/data/prod"],
        environment="production",
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.human_required is True


# --- receipt path ----------------------------------------------------------


def test_gate_destructive_receipt_db_wipe() -> None:
    r = ActionReceipt(
        spec=ActionSpec(
            verb="db_wipe",
            target="production",
            params={"sql": "DROP DATABASE production;"},
        ),
        before_id="b1",
        after_id="a1",
        diff=_empty_diff(),
        success=True,
        timestamp=1.0,
    )
    # No inventory of tables, no approval → FAIL_LOUD (target used as weak inv)
    out = gate_destructive_receipt(r, approved=False, environment="production")
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert out.human_required is True

    out_ok = gate_destructive_receipt(
        r,
        inventory=["production", "public.users", "public.orders"],
        approved=True,
        approval_token="owner",
        environment="production",
    )
    assert out_ok.ok is True
    assert out_ok.inventory_count == 3


def test_gate_destructive_receipt_non_destructive() -> None:
    r = ActionReceipt(
        spec=ActionSpec(verb="write", target="a.txt", params={}),
        before_id="b1",
        after_id="a1",
        diff=_empty_diff(),
        success=True,
        timestamp=1.0,
    )
    out = gate_destructive_receipt(r)
    assert out.ok is True
    assert out.risk == "safe"


def test_assert_not_destructive_raises() -> None:
    with pytest.raises(ClosedLoopError) as ei:
        assert_not_destructive(
            "db_wipe",
            inventory=["prod"],
            environment="production",
        )
    assert "DB-WIPE" in str(ei.value) or "FAIL_LOUD" in str(ei.value)


def test_assert_not_destructive_passes_select() -> None:
    out = assert_not_destructive(verb="query", sql="SELECT 1")
    assert isinstance(out, GateOutcome)
    assert out.ok is True


def test_implicit_target_as_inventory_still_needs_approval() -> None:
    """target= fills inventory when inventory is None, but prod still needs auth."""
    out = gate_destructive(
        verb="wipe",
        target="cache_bucket",
        inventory=None,
        environment="production",
    )
    assert out.inventory_count == 1  # target used
    assert out.ok is False
    assert out.human_required is True
