"""Closed-loop reader/gate for groundcrew (Non-Ornament L1 + L10 + D-GCROOT).

Who reads the output?
  CI / L6 / eagle-eyes: receipts that must prove non-empty filesystem side effects.

What outcome changes?
  Successful receipts with real file changes → PASS (exit 0).
  Failed action (success=False) → FAIL (exit 1).
  Empty store, empty receipt list, or success with zero changed paths → FAIL_LOUD
  (exit 2). L10: success requires non-empty side effects.
  D-GCROOT: success with phantom / dead paths (claimed changes not on disk when
  ``root`` is provided) → FAIL_LOUD — never treat a fabricated diff as work.

When NOT to use:
  Never treat a success flag alone as proof of work — gate on changed_paths and,
  when a workspace root is known, verify those paths against the live tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from groundcrew.codec import ActionReceipt
from groundcrew.oracle import ReceiptStore
from groundcrew.snapshot import SnapshotDiff


class ClosedLoopError(ValueError):
    """Raised when the gate refuses empty, unusable, or empty-effect receipts."""


@dataclass(frozen=True)
class GateOutcome:
    """Result of a closed-loop read of groundcrew receipts.

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
        }


def _fail_loud(
    reason: str,
    *,
    receipt_count: int = 0,
    total_changed_paths: int = 0,
    empty_effect_ids: tuple[str, ...] = (),
    dead_path_ids: tuple[str, ...] = (),
    dead_paths: tuple[str, ...] = (),
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
            receipt has ``success=False`` is FAIL (not FAIL_LOUD — evidence of
            attempted work that failed).
        root: Workspace directory for D-GCROOT dead-path verification. When set
            (or when ``verify_disk`` is True with a root), success receipts whose
            claimed paths do not match the live tree are FAIL_LOUD.
        verify_disk: Force on/off disk verification. Default: True when ``root``
            is provided, False otherwise.

    Returns:
        :class:`GateOutcome` — callers should ``sys.exit(outcome.exit_code)``.
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
            except Exception as exc:  # noqa: BLE001
                return _fail_loud(f"open receipt store failed: {exc.__class__.__name__}: {exc}")
        else:
            receipts = list(source)

        if len(receipts) == 0:
            return _fail_loud(
                "empty receipts — no load-bearing filesystem side effects to gate "
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
                "L10: success with empty side effects — "
                f"receipt_ids={list(empty_effect)} "
                "(success requires non-empty changed_paths)",
                receipt_count=len(receipts),
                total_changed_paths=total_changed,
                empty_effect_ids=empty_ids,
            )

        if dead_effect:
            return _fail_loud(
                "D-GCROOT: success with dead/phantom paths — "
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
                reason=(
                    f"all receipts failed action (count={len(receipts)} "
                    f"failed_ids={failed})"
                ),
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
                f"changed_paths={total_changed}"
                + (f" disk_verified={root}" if do_disk else "")
            ),
            exit_code=0,
            receipt_count=len(receipts),
            total_changed_paths=total_changed,
            empty_effect_ids=(),
        )
    finally:
        if owns and store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass


def assert_side_effects(
    source: ReceiptStore | Sequence[ActionReceipt] | str | Path,
    **kwargs: Any,
) -> GateOutcome:
    """Gate receipts and raise :class:`ClosedLoopError` unless outcome is ok."""
    outcome = gate_receipts(source, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
