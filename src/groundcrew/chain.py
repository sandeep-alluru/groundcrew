"""Receipt chain verification — validate and report chain-of-custody integrity."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from groundcrew.codec import ActionReceipt


@dataclass
class ChainVerification:
    """Result of verifying a receipt chain.

    Attributes:
        is_valid: True if the chain is unbroken.
        chain_length: Number of receipts in the chain.
        broken_at: Index of the first broken link, or None if the chain is valid.
        errors: List of human-readable error descriptions.
        summary: One-line summary of the verification result.
    """

    is_valid: bool
    chain_length: int
    broken_at: int | None = None
    errors: list[str] = field(default_factory=list)
    summary: str = ""


def verify_chain(receipts: list[ActionReceipt]) -> ChainVerification:
    """Verify that a sequence of receipts forms an unbroken chain.

    The chain is valid if for every consecutive pair:
    ``receipts[n].after_id == receipts[n+1].before_id``

    An empty list is considered trivially valid (length 0).
    A single-receipt list is also valid (nothing to check).

    Args:
        receipts: Ordered list of :class:`~groundcrew.codec.ActionReceipt` objects.

    Returns:
        A :class:`ChainVerification` with validity, broken index, and errors.
    """
    n = len(receipts)

    if n <= 1:
        return ChainVerification(
            is_valid=True,
            chain_length=n,
            broken_at=None,
            errors=[],
            summary=f"Chain valid: {n} receipt(s), nothing to verify."
            if n == 0
            else "Chain valid: single receipt.",
        )

    errors: list[str] = []
    broken_at: int | None = None

    for i in range(n - 1):
        expected_before = receipts[i].after_id
        actual_before = receipts[i + 1].before_id
        if expected_before != actual_before:
            if broken_at is None:
                broken_at = i + 1
            errors.append(
                f"Link broken at index {i + 1}: "
                f"receipt[{i}].after_id={expected_before!r} "
                f"!= receipt[{i + 1}].before_id={actual_before!r}"
            )

    is_valid = len(errors) == 0
    summary = (
        f"Chain valid: {n} receipt(s) form an unbroken chain."
        if is_valid
        else f"Chain BROKEN at index {broken_at}: {len(errors)} error(s) found."
    )

    return ChainVerification(
        is_valid=is_valid,
        chain_length=n,
        broken_at=broken_at,
        errors=errors,
        summary=summary,
    )


def build_chain_report(receipts: list[ActionReceipt]) -> str:
    """Build a human-readable chain-of-custody report for a sequence of receipts.

    The report lists each receipt's action, state transition, outcome, and timestamp,
    followed by an overall chain verification result.

    Args:
        receipts: Ordered list of :class:`~groundcrew.codec.ActionReceipt` objects.

    Returns:
        A formatted multi-line string suitable for printing or logging.
    """
    lines: list[str] = [
        "Chain-of-Custody Report",
        "=" * 50,
        f"Receipts: {len(receipts)}",
        "",
    ]

    for i, receipt in enumerate(receipts):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(receipt.timestamp))
        status = "SUCCESS" if receipt.success else "FAILURE"
        lines += [
            f"[{i:03d}] {ts}  {status}",
            f"      Action : {receipt.spec.verb} → {receipt.spec.target}",
            f"      Before : {receipt.before_id}",
            f"      After  : {receipt.after_id}",
            f"      Receipt: {receipt.id}",
            f"      Changed: +{len(receipt.diff.added)} files, "
            f"-{len(receipt.diff.removed)} files, "
            f"~{len(receipt.diff.modified)} files",
            "",
        ]

    verification = verify_chain(receipts)
    lines += [
        "-" * 50,
        f"Verification: {verification.summary}",
    ]

    if not verification.is_valid:
        for err in verification.errors:
            lines.append(f"  ERROR: {err}")

    return "\n".join(lines)
