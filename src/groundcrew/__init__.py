"""groundcrew — Deterministic state oracle and semantic action codec for computer-use agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.snapshot import FileState, SnapshotDiff, StateSnapshot

__version__ = _version("groundcrew")

__all__ = [
    "ActionReceipt",
    "ActionSpec",
    "FileState",
    "Oracle",
    "ReceiptStore",
    "SnapshotDiff",
    "StateSnapshot",
    "__version__",
]
