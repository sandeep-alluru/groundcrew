"""Human- and machine-readable formatters for receipts and diffs."""

from __future__ import annotations

import json

from openveritas.codec import ActionReceipt
from openveritas.snapshot import SnapshotDiff


def print_receipt(receipt: ActionReceipt, console=None) -> None:
    """Pretty-print a receipt to the console (falls back to plain text)."""
    try:
        from rich.console import Console
        from rich.table import Table

        c = console or Console()
        t = Table(title=f"Receipt {receipt.id}")
        t.add_column("Field")
        t.add_column("Value")
        t.add_row("Action", f"{receipt.spec.verb} -> {receipt.spec.target}")
        t.add_row("Before", receipt.before_id)
        t.add_row("After", receipt.after_id)
        t.add_row("Success", str(receipt.success))
        t.add_row("Changes", str(len(receipt.diff.changed_paths)))
        c.print(t)
    except ImportError:
        print(f"Receipt {receipt.id}: {receipt.spec.verb} -> {receipt.spec.target}")


def print_diff(diff: SnapshotDiff, console=None) -> None:
    """Pretty-print a snapshot diff to the console (falls back to plain text)."""
    try:
        from rich.console import Console

        c = console or Console()
        c.print(f"[bold]Diff[/bold] {diff.snapshot_a_id} -> {diff.snapshot_b_id}")
        for f in diff.added:
            c.print(f"  [green]+[/green] {f.path}")
        for f in diff.removed:
            c.print(f"  [red]-[/red] {f.path}")
        for before, _after in diff.modified:
            c.print(f"  [yellow]~[/yellow] {before.path}")
    except ImportError:
        print(f"Diff: +{len(diff.added)} -{len(diff.removed)} ~{len(diff.modified)}")


def to_json(receipt: ActionReceipt | None, diff: SnapshotDiff | None = None) -> str:
    """Serialize a receipt or diff to a JSON string."""
    if receipt is not None:
        return json.dumps(receipt.to_dict(), indent=2)
    if diff is not None:
        return json.dumps(diff.to_dict(), indent=2)
    return "{}"


def to_markdown(receipts: list) -> str:
    """Render a list of receipts as a Markdown table."""
    lines = ["# OpenVeritas Action Log", ""]
    lines.append("| ID | Verb | Target | Success | Changes |")
    lines.append("|---|---|---|---|---|")
    for r in receipts:
        lines.append(
            f"| `{r.id}` | {r.spec.verb} | {r.spec.target} | "
            f"{r.success} | {len(r.diff.changed_paths)} |"
        )
    return "\n".join(lines)
