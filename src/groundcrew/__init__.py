"""groundcrew — Deterministic state oracle and semantic action codec for computer-use agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from groundcrew.chain import ChainVerification, build_chain_report, verify_chain
from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.content_diff import ContentDiff, FileDiff, content_diff
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.snapshot import FileState, SnapshotDiff, StateSnapshot
from groundcrew.watcher import DirectoryWatcher

__version__ = _version("groundcrew")

__all__ = [
    "ActionReceipt",
    "ActionSpec",
    "ChainVerification",
    "ContentDiff",
    "DirectoryWatcher",
    "FileDiff",
    "FileState",
    "Oracle",
    "ReceiptStore",
    "SnapshotDiff",
    "StateSnapshot",
    "__version__",
    "build_chain_report",
    "content_diff",
    "verify_chain",
]
