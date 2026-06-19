"""Command-line interface for groundcrew."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from groundcrew.codec import ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.report import print_diff, print_receipt, to_markdown

_DEFAULT_DB = ".groundcrew/receipts.db"


@click.group()
@click.version_option(package_name="groundcrew")
@click.option(
    "--db",
    default=_DEFAULT_DB,
    show_default=True,
    help="Path to the groundcrew receipt store.",
    envvar="GROUNDCREW_DB",
)
@click.pass_context
def main(ctx: click.Context, db: str) -> None:
    """Deterministic state oracle and semantic action codec for computer-use agents.

    groundcrew captures the filesystem state before and after an action,
    and emits a verifiable, content-addressed receipt of what changed.
    """
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@main.command()
@click.option("--root", default=".", show_default=True, help="Directory to snapshot.")
@click.option("--verb", required=True, help="Semantic verb for the action.")
@click.option("--target", required=True, help="Target the action acts upon.")
@click.option("--run", "run_cmd", default=None, help="Shell command to execute and capture.")
@click.pass_context
def capture(ctx: click.Context, root: str, verb: str, target: str, run_cmd: str | None) -> None:
    """Capture before/after state around an action and store a receipt.

    \b
    Examples:
      groundcrew capture --root . --verb write --target out.txt --run "echo hi > out.txt"
    """
    spec = ActionSpec(verb=verb, target=target, params={"run": run_cmd} if run_cmd else {})
    with Oracle(root, spec) as oracle:
        if run_cmd:
            result = subprocess.run(run_cmd, shell=True, cwd=root)  # noqa: S602
            if result.returncode != 0:
                oracle._success = False
    receipt = oracle.record(spec)
    store = ReceiptStore(ctx.obj["db"])
    store.save(receipt)
    store.close()
    click.echo(f"Captured receipt {receipt.id}  {verb} -> {target}")
    print_receipt(receipt)


@main.command()
@click.argument("receipt_id")
@click.pass_context
def diff(ctx: click.Context, receipt_id: str) -> None:
    """Show the diff for a stored receipt.

    \b
    Examples:
      groundcrew diff abc123def456
    """
    store = ReceiptStore(ctx.obj["db"])
    receipt = store.get(receipt_id)
    store.close()
    if receipt is None:
        raise click.ClickException(f"Receipt not found: {receipt_id}")
    print_diff(receipt.diff)


@main.command()
@click.pass_context
def log(ctx: click.Context) -> None:
    """List all stored receipts.

    \b
    Examples:
      groundcrew log
    """
    store = ReceiptStore(ctx.obj["db"])
    receipts = store.list_receipts()
    store.close()
    click.echo(to_markdown(receipts))


@main.command()
@click.option("--root", default=".", show_default=True, help="Directory to inspect.")
@click.pass_context
def status(ctx: click.Context, root: str) -> None:
    """Show the current staging state (a live snapshot of the root)."""
    from groundcrew.snapshot import StateSnapshot

    snap = StateSnapshot.capture(root)
    store = ReceiptStore(ctx.obj["db"])
    count = len(store.list_receipts())
    store.close()
    click.echo(f"Root      {snap.root}")
    click.echo(f"Snapshot  {snap.id}  ({len(snap.files)} files)")
    click.echo(f"Receipts  {count} stored")


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--interval",
    type=float,
    default=5.0,
    show_default=True,
    help="Polling interval in seconds.",
)
@click.option(
    "--max-checks",
    type=int,
    default=10,
    show_default=True,
    help="Maximum number of polling iterations before exiting.",
)
@click.option(
    "--allow",
    "allowed",
    multiple=True,
    metavar="PATH",
    help="Relative path that is authorized to change. Repeat for multiple.",
)
def watch(directory: Path, interval: float, max_checks: int, allowed: tuple[str, ...]) -> None:
    """Watch a directory for unauthorized changes.

    Polls DIRECTORY every INTERVAL seconds. Reports any unexpected mutations
    to stdout. Exits after MAX_CHECKS iterations.

    \b
    Examples:
      groundcrew watch ./output --interval 2
      groundcrew watch . --allow build/output.txt --max-checks 5
    """
    from groundcrew.watcher import DirectoryWatcher

    watcher = DirectoryWatcher(
        root=directory,
        authorized_paths=list(allowed) if allowed else None,
        interval_seconds=interval,
    )
    baseline = watcher.take_baseline()
    click.echo(
        f"Watching  {directory}  snapshot={baseline.id}  "
        f"files={len(baseline.files)}  "
        f"interval={interval}s  max_checks={max_checks}"
    )

    def _on_change(changes: list[str]) -> None:
        click.echo(f"\n[ALERT] {len(changes)} unauthorized change(s) detected:")
        for ch in changes:
            click.echo(f"  {ch}")

    watcher.watch(callback=_on_change, max_checks=max_checks)
    click.echo("Watch complete.")


if __name__ == "__main__":
    main()
