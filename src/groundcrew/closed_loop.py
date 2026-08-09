"""Closed-loop reader/gate for groundcrew (Non-Ornament L1 + L10 + D-GCROOT + DB-WIPE).

Who reads the output?
  CI / L6 / eagle-eyes: receipts that must prove non-empty filesystem side effects;
  agent runtimes that must block destructive SQL/shell before execution.

What outcome changes?
  Successful receipts with real file changes → PASS (exit 0).
  Failed action (success=False) → FAIL (exit 1).
  Empty store, empty receipt list, or success with zero changed paths → FAIL_LOUD
  (exit 2). L10: success requires non-empty side effects.
  D-GCROOT: success with phantom / dead paths (claimed changes not on disk when
  ``root`` is provided) → FAIL_LOUD - never treat a fabricated diff as work.
  DB-WIPE / Replit class: destructive verb/SQL/shell without inventory + approval
  → FAIL_LOUD (human_required). Never unattended DROP/TRUNCATE/DELETE/rm.

When NOT to use:
  Never treat a success flag alone as proof of work - gate on changed_paths and,
  when a workspace root is known, verify those paths against the live tree.
  Never treat a free-form SQL tool as safe without :func:`gate_destructive`.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.oracle import ReceiptStore
from groundcrew.snapshot import SnapshotDiff

# ---------------------------------------------------------------------------
# Destructive tool classification (Replit / Antigravity / AgentWard class)
# ---------------------------------------------------------------------------

DESTRUCTIVE_VERBS: frozenset[str] = frozenset(
    {
        "delete",
        "drop",
        "truncate",
        "wipe",
        "rm",
        "rmdir",
        "unlink",
        "purge",
        "destroy",
        "db_drop",
        "db_wipe",
        "drop_table",
        "drop_database",
        "drop_schema",
        "shell_rm",
        "force_push",
        "git_push_force",
    }
)

# SQL that irreversibly destroys data or schema (not mere UPDATE/INSERT).
_SQL_DESTRUCTIVE_RE = re.compile(
    r"\b("
    r"DROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|USER|ROLE)|"
    r"TRUNCATE(?:\s+TABLE)?|"
    r"DELETE\s+FROM|"
    r"ALTER\s+TABLE\s+\S+\s+DROP|"
    r"DROP\s+DATABASE\s+IF\s+EXISTS"
    r")\b",
    re.IGNORECASE,
)

# Shell that deletes files or overwrites disks.
_SHELL_DESTRUCTIVE_RE = re.compile(
    r"(?:^|\s)("
    r"rm\s+-[a-zA-Z]*f|"
    r"rm\s+-rf|"
    r"rmdir\b|"
    r"shred\b|"
    r"dd\s+if=|"
    r"mkfs\b|"
    r">\s*/dev/"
    r")",
    re.IGNORECASE,
)

# Environments that always require human approval for destructive ops.
_STRICT_ENVIRONMENTS: frozenset[str] = frozenset(
    {"production", "prod", "live", "staging", "stage", "main", "master"}
)


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty, unusable, or empty-effect receipts."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of groundcrew receipts or destructive gates.

    Attributes:
        ok: True only when a pipeline may continue (PASS).
        verdict: ``PASS``, ``FAIL``, or ``FAIL_LOUD``.
        reason: Human-readable explanation (always non-empty).
        exit_code: 0 PASS, 1 FAIL (action failed), 2 FAIL_LOUD (empty/no side effects).
        receipt_count: Number of receipts examined.
        total_changed_paths: Distinct changed paths across examined receipts.
        empty_effect_ids: Receipt IDs that claimed success with zero changes.
        dead_path_ids: Receipt IDs with success but paths that fail disk verify.
        dead_paths: Sample of claimed paths that are dead on disk.
        human_required: True when a human must approve before proceeding.
        risk: ``safe``, ``high_risk``, or None when not a destructive gate.
        inventory_count: Count of named targets that will be destroyed (if gated).
        action: Canonical action / verb that was gated (destructive path).
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    receipt_count: int = 0
    total_changed_paths: int = 0
    empty_effect_ids: tuple[str, ...] = ()
    dead_path_ids: tuple[str, ...] = ()
    dead_paths: tuple[str, ...] = ()
    human_required: bool = False
    risk: str | None = None
    inventory_count: int = 0
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON reports (eagle-eyes dogfood, CI artifacts)."""
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "receipt_count": self.receipt_count,
            "total_changed_paths": self.total_changed_paths,
            "empty_effect_ids": list(self.empty_effect_ids),
            "dead_path_ids": list(self.dead_path_ids),
            "dead_paths": list(self.dead_paths),
            "human_required": self.human_required,
            "risk": self.risk,
            "inventory_count": self.inventory_count,
            "action": self.action,
        }


def _fail_loud(
    reason: str,
    *,
    receipt_count: int = 0,
    total_changed_paths: int = 0,
    empty_effect_ids: tuple[str, ...] = (),
    dead_path_ids: tuple[str, ...] = (),
    dead_paths: tuple[str, ...] = (),
    human_required: bool = False,
    risk: str | None = None,
    inventory_count: int = 0,
    action: str | None = None,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        receipt_count=receipt_count,
        total_changed_paths=total_changed_paths,
        empty_effect_ids=empty_effect_ids,
        dead_path_ids=dead_path_ids,
        dead_paths=dead_paths,
        human_required=human_required,
        risk=risk,
        inventory_count=inventory_count,
        action=action,
    )


def _fail(
    reason: str,
    *,
    human_required: bool = False,
    risk: str | None = None,
    inventory_count: int = 0,
    action: str | None = None,
    receipt_count: int = 0,
    total_changed_paths: int = 0,
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL",
        reason=reason,
        exit_code=1,
        receipt_count=receipt_count,
        total_changed_paths=total_changed_paths,
        human_required=human_required,
        risk=risk,
        inventory_count=inventory_count,
        action=action,
    )


def _receipt_changed_count(receipt: ActionReceipt) -> int:
    return len(receipt.diff.changed_paths)


def dead_paths_for_receipt(receipt: ActionReceipt, root: str | Path) -> list[str]:
    """Return claimed side-effect paths that do not match the live workspace.

    D-GCROOT / L10 harden: a success receipt can invent ``FileState`` rows so
    ``changed_paths`` is non-empty while nothing real happened. When a workspace
    ``root`` is known, every path in the structural diff must match disk:

    - **added** / **modified**: file must exist under ``root``
    - **removed**: file must *not* exist under ``root``

    Returns the list of dead (mismatch) relative paths (may be empty).
    """
    base = Path(root)
    dead: list[str] = []
    diff: SnapshotDiff = receipt.diff

    for f in diff.added:
        if not (base / f.path).is_file():
            dead.append(f.path)

    for before, after in diff.modified:
        # Prefer after.path (post-change); fall back to before.path
        path = after.path or before.path
        if not (base / path).is_file():
            dead.append(path)

    for f in diff.removed:
        if (base / f.path).is_file():
            # Claimed removed but still present → dead claim
            dead.append(f.path)

    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for p in dead:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def gate_receipts(
    source: ReceiptStore | Sequence[ActionReceipt] | str | Path,
    *,
    require_side_effects: bool = True,
    require_any_success: bool = True,
    root: str | Path | None = None,
    verify_disk: bool | None = None,
) -> GateOutcome:
    """Read receipts and fail loudly when success has no filesystem side effects.

    Args:
        source: Open :class:`ReceiptStore`, path to a receipts SQLite db, or an
            in-memory sequence of :class:`ActionReceipt`.
        require_side_effects: If True (L10 default), any receipt with
            ``success=True`` and zero ``changed_paths`` is FAIL_LOUD.
        require_any_success: If True, a non-empty set of receipts where every
            receipt has ``success=False`` is FAIL (not FAIL_LOUD - evidence of
            attempted work that failed).
        root: Workspace directory for D-GCROOT dead-path verification. When set
            (or when ``verify_disk`` is True with a root), success receipts whose
            claimed paths do not match the live tree are FAIL_LOUD.
        verify_disk: Force on/off disk verification. Default: True when ``root``
            is provided, False otherwise.

    Returns:
        :class:`GateOutcome` - callers should ``sys.exit(outcome.exit_code)``.
    """
    do_disk = verify_disk if verify_disk is not None else (root is not None)
    if do_disk and root is None:
        return _fail_loud(
            "D-GCROOT: verify_disk=True requires root= workspace path "
            "(cannot prove side effects without a tree)"
        )

    owns = False
    store: ReceiptStore | None = None
    try:
        if isinstance(source, ReceiptStore):
            receipts = list(source.list_receipts())
        elif isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                return _fail_loud(f"receipt store not found: {path}")
            try:
                store = ReceiptStore(path)
                owns = True
                receipts = list(store.list_receipts())
            except Exception as exc:
                return _fail_loud(f"open receipt store failed: {exc.__class__.__name__}: {exc}")
        else:
            receipts = list(source)

        if len(receipts) == 0:
            return _fail_loud(
                "empty receipts - no load-bearing filesystem side effects to gate "
                "(write-only ornament / L10)"
            )

        empty_effect: list[str] = []
        dead_effect: list[str] = []
        dead_path_samples: list[str] = []
        failed: list[str] = []
        all_paths: set[str] = set()
        success_count = 0

        for r in receipts:
            paths = set(r.diff.changed_paths)
            all_paths |= paths
            if r.success:
                success_count += 1
                if require_side_effects and len(paths) == 0:
                    empty_effect.append(r.id)
                elif do_disk and root is not None and require_side_effects:
                    dead = dead_paths_for_receipt(r, root)
                    if dead:
                        dead_effect.append(r.id)
                        for p in dead:
                            if p not in dead_path_samples:
                                dead_path_samples.append(p)
            else:
                failed.append(r.id)

        total_changed = len(all_paths)
        empty_ids = tuple(empty_effect)
        dead_ids = tuple(dead_effect)
        dead_paths_t = tuple(dead_path_samples[:20])

        if empty_effect:
            return _fail_loud(
                "L10: success with empty side effects - "
                f"receipt_ids={list(empty_effect)} "
                "(success requires non-empty changed_paths)",
                receipt_count=len(receipts),
                total_changed_paths=total_changed,
                empty_effect_ids=empty_ids,
            )

        if dead_effect:
            return _fail_loud(
                "D-GCROOT: success with dead/phantom paths - "
                f"receipt_ids={list(dead_effect)} "
                f"dead_paths={dead_path_samples[:10]} "
                "(claimed side effects do not match workspace root)",
                receipt_count=len(receipts),
                total_changed_paths=total_changed,
                empty_effect_ids=(),
                dead_path_ids=dead_ids,
                dead_paths=dead_paths_t,
            )

        if require_any_success and success_count == 0:
            return GateOutcome(
                ok=False,
                verdict="FAIL",
                reason=(f"all receipts failed action (count={len(receipts)} failed_ids={failed})"),
                exit_code=1,
                receipt_count=len(receipts),
                total_changed_paths=total_changed,
                empty_effect_ids=(),
            )

        if require_side_effects and total_changed == 0:
            return _fail_loud(
                "L10: no filesystem side effects across receipts "
                f"(count={len(receipts)} changed_paths=0)",
                receipt_count=len(receipts),
                total_changed_paths=0,
            )

        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason=(
                f"receipts ok: count={len(receipts)} success={success_count} "
                f"changed_paths={total_changed}" + (f" disk_verified={root}" if do_disk else "")
            ),
            exit_code=0,
            receipt_count=len(receipts),
            total_changed_paths=total_changed,
            empty_effect_ids=(),
        )
    finally:
        if owns and store is not None:
            with contextlib.suppress(Exception):
                store.close()


def assert_side_effects(
    source: ReceiptStore | Sequence[ActionReceipt] | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate receipts and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_receipts(source, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome


# ---------------------------------------------------------------------------
# DB-WIPE / Replit-class destructive tool gate
# ---------------------------------------------------------------------------


def sql_is_destructive(sql: str) -> bool:
    """Return True if *sql* contains irreversible DROP/TRUNCATE/DELETE-class ops.

    Public incidents (Replit AI production DB wipe, AgentWard file wipe) start
    with free-form SQL tools that accept any string. Classifiers must refuse
    before execution - not after a success receipt is written.
    """
    if not sql or not str(sql).strip():
        return False
    return _SQL_DESTRUCTIVE_RE.search(str(sql)) is not None


def shell_is_destructive(command: str) -> bool:
    """Return True if *command* looks like rm -rf / shred / dd overwrite class."""
    if not command or not str(command).strip():
        return False
    return _SHELL_DESTRUCTIVE_RE.search(str(command)) is not None


def _canonical_verb(verb: str) -> str:
    return (verb or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_destructive(
    verb: str = "",
    *,
    target: str = "",
    sql: str | None = None,
    command: str | None = None,
    params: dict[str, Any] | None = None,
) -> bool:
    """Classify a tool call as destructive (irreversible data/schema/file loss).

    Checks (any match → destructive):
      1. Verb in :data:`DESTRUCTIVE_VERBS` (exact or prefix ``verb:scope``)
      2. SQL payload via :func:`sql_is_destructive`
      3. Shell command via :func:`shell_is_destructive`
      4. ``params['sql']`` / ``params['command']`` / ``params['query']``
    """
    v = _canonical_verb(verb)
    if v:
        # Allow "drop:table", "db_wipe:prod", "delete:users"
        base = v.split(":", 1)[0]
        if base in DESTRUCTIVE_VERBS or v in DESTRUCTIVE_VERBS:
            return True

    p = params or {}
    sql_blob = sql if sql is not None else p.get("sql") or p.get("query")
    if sql_blob and sql_is_destructive(str(sql_blob)):
        return True

    cmd_blob = command if command is not None else p.get("command") or p.get("shell")
    if cmd_blob and shell_is_destructive(str(cmd_blob)):
        return True

    # Target alone is not enough (e.g. verb=read target=users) - only when
    # combined with destructive verb, already handled above.
    _ = target
    return False


def _inventory_list(inventory: Sequence[str] | None) -> list[str]:
    if inventory is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in inventory:
        s = str(item).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _has_approval(*, approved: bool, approval_token: str | None) -> bool:
    if approved and approval_token and str(approval_token).strip():
        return True
    if approved and approval_token is None:
        # Explicit approved=True without token is accepted only when caller
        # already verified a humanproof token out-of-band.
        return True
    return bool(approval_token and str(approval_token).strip())


def gate_destructive(
    verb: str = "",
    *,
    target: str = "",
    sql: str | None = None,
    command: str | None = None,
    params: dict[str, Any] | None = None,
    inventory: Sequence[str] | None = None,
    approved: bool = False,
    approval_token: str | None = None,
    environment: str = "production",
    require_inventory: bool = True,
) -> GateOutcome:
    """Block unattended destructive tools (Replit DB wipe / Antigravity / AgentWard).

    Load-bearing controls (all required for destructive ops in strict envs):

    1. **Classify** - verb / SQL / shell must be detected as destructive.
    2. **Inventory** - named targets that will be destroyed (tables, paths, DBs).
       Empty inventory = agent does not know what it is wiping → FAIL_LOUD.
    3. **Approval** - human token / approved flag. Missing → FAIL_LOUD
       (``human_required=True``).

    Non-destructive calls PASS without inventory or approval.

    Args:
        verb: Tool verb (e.g. ``db_wipe``, ``drop``, ``execute_sql``).
        target: Logical target name (db, table, path).
        sql: Free-form SQL if the tool accepts queries.
        command: Shell command string if applicable.
        params: Extra tool params (may embed ``sql`` / ``command`` / ``query``).
        inventory: Explicit list of objects that will be destroyed.
        approved: True when a human (or humanproof session) already approved.
        approval_token: Opaque owner-issued token id/secret handle.
        environment: ``production``/``staging`` always require approval;
            ``dev``/``test`` still require inventory for destructive ops.
        require_inventory: If True (default), destructive ops need non-empty
            inventory even when approved.

    Returns:
        :class:`GateOutcome` - callers must not execute the tool unless ``ok``.
    """
    v = _canonical_verb(verb)
    action = v or (f"sql:{sql[:40]}" if sql else (f"cmd:{command[:40]}" if command else ""))
    env = (environment or "production").strip().lower()
    strict = env in _STRICT_ENVIRONMENTS or env == ""

    # Completely empty call - nothing to gate.
    if not v and not (sql and str(sql).strip()) and not (command and str(command).strip()):
        p = params or {}
        if not p.get("sql") and not p.get("query") and not p.get("command") and not p.get("shell"):
            return _fail_loud(
                "DB-WIPE: empty tool call - no verb/sql/command to classify "
                "(cannot gate a phantom destructive action)",
                human_required=True,
                risk="high_risk",
                action=action or None,
            )

    destructive = is_destructive(verb, target=target, sql=sql, command=command, params=params)
    inv = _inventory_list(inventory)
    # Implicit inventory from target only when inventory was omitted (None),
    # not when the caller explicitly passed an empty list (declared no targets).
    if inventory is None and not inv and target and str(target).strip():
        inv = [str(target).strip()]

    if not destructive:
        return GateOutcome(
            ok=True,
            verdict="PASS",
            reason=f"non-destructive tool call action={action!r} env={env}",
            exit_code=0,
            human_required=False,
            risk="safe",
            inventory_count=len(inv),
            action=action or None,
        )

    # --- Destructive path ---
    if require_inventory and len(inv) == 0:
        return _fail_loud(
            "DB-WIPE: destructive action without inventory - "
            f"action={action!r} env={env} "
            "(Replit/AgentWard class: agent must name tables/paths/DBs before wipe)",
            human_required=True,
            risk="high_risk",
            inventory_count=0,
            action=action or None,
        )

    needs_approval = strict or env not in {"dev", "development", "test", "local", "ci"}
    has_auth = _has_approval(approved=approved, approval_token=approval_token)
    if needs_approval and not has_auth:
        return _fail_loud(
            "DB-WIPE: destructive action without human approval - "
            f"action={action!r} env={env} inventory={inv[:10]} "
            "(public: Replit AI production DB deletion; Antigravity wipe; "
            "AgentWard post-incident). Call humanproof.gate_approval first.",
            human_required=True,
            risk="high_risk",
            inventory_count=len(inv),
            action=action or None,
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"destructive action authorised: action={action!r} env={env} "
            f"inventory_count={len(inv)} approved={has_auth}"
        ),
        exit_code=0,
        human_required=False,
        risk="high_risk",
        inventory_count=len(inv),
        action=action or None,
    )


def gate_destructive_receipt(
    receipt: ActionReceipt,
    *,
    inventory: Sequence[str] | None = None,
    approved: bool = False,
    approval_token: str | None = None,
    environment: str = "production",
    require_inventory: bool = True,
) -> GateOutcome:
    """Gate an :class:`ActionReceipt` for destructive verbs (pre- or post-exec).

    Uses ``receipt.spec.verb/target/params`` plus optional explicit inventory.
    When inventory is omitted, falls back to ``receipt.diff.changed_paths``
    (filesystem-class wipes) then ``spec.target``.
    """
    if not isinstance(receipt, ActionReceipt):
        return _fail_loud(
            "DB-WIPE: gate_destructive_receipt requires ActionReceipt",
            human_required=True,
            risk="high_risk",
        )
    spec: ActionSpec = receipt.spec
    inv = inventory
    if inv is None:
        paths = list(receipt.diff.changed_paths)
        inv = paths if paths else None
    return gate_destructive(
        spec.verb,
        target=spec.target,
        params=spec.params,
        sql=spec.params.get("sql") if isinstance(spec.params, dict) else None,
        command=spec.params.get("command") if isinstance(spec.params, dict) else None,
        inventory=inv,
        approved=approved,
        approval_token=approval_token,
        environment=environment,
        require_inventory=require_inventory,
    )


def assert_not_destructive(
    verb: str = "",
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_destructive` is ok."""
    outcome = gate_destructive(verb, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
