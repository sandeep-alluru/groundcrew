"""Closed-loop reader/gate for groundcrew (Non-Ornament L1 + L10).

Who reads the output?
  CI / L6 / eagle-eyes: receipts that must prove non-empty filesystem side effects.

What outcome changes?
  Successful receipts with real file changes → PASS (exit 0).
  Failed action (success=False) → FAIL (exit 1).
  Empty store, empty receipt list, or success with zero changed paths → FAIL_LOUD
  (exit 2). L10: success requires non-empty side effects.

When NOT to use:
  Never treat a success flag alone as proof of work — gate on changed_paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from groundcrew.codec import ActionReceipt
from groundcrew.oracle import ReceiptStore


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
    """

    ok: bool
    verdict: str
    reason: str
    exit_code: int
    receipt_count: int = 0
    total_changed_paths: int = 0
    empty_effect_ids: tuple[str, ...] = ()

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
        }


def _fail_loud(
    reason: str,
    *,
    receipt_count: int = 0,
    total_changed_paths: int = 0,
    empty_effect_ids: tuple[str, ...] = (),
) -> GateOutcome:
    return GateOutcome(
        ok=False,
        verdict="FAIL_LOUD",
        reason=reason,
        exit_code=2,
        receipt_count=receipt_count,
        total_changed_paths=total_changed_paths,
        empty_effect_ids=empty_effect_ids,
    )


def _receipt_changed_count(receipt: ActionReceipt) -> int:
    return len(receipt.diff.changed_paths)


def gate_receipts(
    source: ReceiptStore | Sequence[ActionReceipt] | str | Path,
    *,
    require_side_effects: bool = True,
    require_any_success: bool = True,
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

    Returns:
        :class:`GateOutcome` — callers should ``sys.exit(outcome.exit_code)``.
    """
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
            else:
                failed.append(r.id)

        total_changed = len(all_paths)
        empty_ids = tuple(empty_effect)

        if empty_effect:
            return _fail_loud(
                "L10: success with empty side effects — "
                f"receipt_ids={list(empty_effect)} "
                "(success requires non-empty changed_paths)",
                receipt_count=len(receipts),
                total_changed_paths=total_changed,
                empty_effect_ids=empty_ids,
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
