"""The Oracle: captures before/after state around actions and persists receipts."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.snapshot import StateSnapshot, diff_snapshots


class Oracle:
    """Context manager that snapshots a root before and after a block of work."""

    def __init__(self, root, spec=None):
        self.root = Path(root)
        self.spec = spec
        self._before: StateSnapshot | None = None
        self._after: StateSnapshot | None = None
        self._success = True

    def __enter__(self):
        self._before = StateSnapshot.capture(self.root)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._after = StateSnapshot.capture(self.root)
        if exc_type is not None:
            self._success = False
        return False

    def record(self, spec: ActionSpec) -> ActionReceipt:
        """Build an ActionReceipt for ``spec`` from the captured before/after state."""
        if self._after is None:
            self._after = StateSnapshot.capture(self.root)
        diff = diff_snapshots(self._before, self._after)
        return ActionReceipt(
            spec=spec,
            before_id=self._before.id if self._before else "",
            after_id=self._after.id,
            diff=diff,
            success=self._success,
            timestamp=time.time(),
        )


@contextmanager
def capture(root, spec):
    """Convenience context manager wrapping :class:`Oracle`."""
    oracle = Oracle(root, spec)
    oracle.__enter__()
    try:
        yield oracle
    except Exception:
        oracle._success = False
        raise
    finally:
        oracle.__exit__(None, None, None)


class ReceiptStore:
    """A SQLite-backed store for persisting and retrieving action receipts."""

    def __init__(self, path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, data TEXT)")
        self._conn.commit()

    def save(self, receipt: ActionReceipt) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO receipts (id, data) VALUES (?, ?)",
            (receipt.id, json.dumps(receipt.to_dict())),
        )
        self._conn.commit()

    def get(self, receipt_id: str) -> ActionReceipt | None:
        row = self._conn.execute("SELECT data FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if row is None:
            return None
        return ActionReceipt.from_dict(json.loads(row[0]))

    def list_receipts(self) -> list:
        rows = self._conn.execute("SELECT data FROM receipts").fetchall()
        return [ActionReceipt.from_dict(json.loads(r[0])) for r in rows]

    def close(self) -> None:
        self._conn.close()
