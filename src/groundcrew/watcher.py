"""Directory watcher — poll a directory for unauthorized mutations."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from groundcrew.snapshot import StateSnapshot, diff_snapshots


class DirectoryWatcher:
    """Polls a directory for changes and fires callbacks on unexpected mutations.

    Typical usage::

        watcher = DirectoryWatcher(root="/path/to/dir", interval_seconds=5.0)
        watcher.take_baseline()
        changes = watcher.check()
        if changes:
            print("Unexpected changes:", changes)

    Attributes:
        root: The directory being watched.
        authorized_paths: If provided, changes to these paths are considered
            authorized and will not be reported.
        interval_seconds: Polling interval used by :meth:`watch`.
    """

    def __init__(
        self,
        root: Path,
        authorized_paths: list[str] | None = None,
        interval_seconds: float = 5.0,
    ) -> None:
        self.root = Path(root)
        self.authorized_paths: set[str] = set(authorized_paths or [])
        self.interval_seconds = interval_seconds
        self._baseline: StateSnapshot | None = None

    def take_baseline(self) -> StateSnapshot:
        """Capture the current state of the directory as the authorized baseline.

        Returns:
            The captured :class:`~groundcrew.snapshot.StateSnapshot`.
        """
        self._baseline = StateSnapshot.capture(self.root)
        return self._baseline

    def check(self) -> list[str]:
        """Check for changes since the baseline was taken.

        Compares the current directory state against the stored baseline and
        returns a list of human-readable change descriptions for all changes
        that are *not* in :attr:`authorized_paths`.

        Returns:
            List of change descriptions. Empty if no unauthorized changes.

        Raises:
            RuntimeError: If :meth:`take_baseline` has not been called yet.
        """
        if self._baseline is None:
            raise RuntimeError("Call take_baseline() before check().")

        current = StateSnapshot.capture(self.root)
        diff = diff_snapshots(self._baseline, current)

        changes: list[str] = []

        for f in diff.added:
            if f.path not in self.authorized_paths:
                changes.append(f"ADDED    {f.path} ({f.size} bytes)")

        for f in diff.removed:
            if f.path not in self.authorized_paths:
                changes.append(f"REMOVED  {f.path}")

        for before, after in diff.modified:
            if before.path not in self.authorized_paths:
                changes.append(
                    f"MODIFIED {before.path} "
                    f"({before.size} → {after.size} bytes)"
                )

        return changes

    def watch(
        self,
        callback: Callable[[list[str]], None],
        max_checks: int = 10,
    ) -> None:
        """Poll for changes and invoke *callback* on unexpected mutations.

        Polls up to *max_checks* times, sleeping :attr:`interval_seconds`
        between each poll. This is intentionally non-infinite so it remains
        testable and composable. Use a loop around :meth:`watch` for indefinite
        monitoring.

        Args:
            callback: Called with a list of change description strings whenever
                unauthorized changes are detected.
            max_checks: Maximum number of polls before returning.
        """
        if self._baseline is None:
            self.take_baseline()

        for _ in range(max_checks):
            changes = self.check()
            if changes:
                callback(changes)
            time.sleep(self.interval_seconds)
