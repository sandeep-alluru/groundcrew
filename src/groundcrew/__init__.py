"""groundcrew — Deterministic state oracle and semantic action codec for computer-use agents."""

from __future__ import annotations

from importlib.metadata import version as _version

from groundcrew.chain import ChainVerification, build_chain_report, verify_chain
from groundcrew.closed_loop import (
    DESTRUCTIVE_VERBS,
    ClosedLoopError,
    GateOutcome,
    assert_not_destructive,
    assert_side_effects,
    dead_paths_for_receipt,
    gate_destructive,
    gate_destructive_receipt,
    gate_receipts,
    is_destructive,
    shell_is_destructive,
    sql_is_destructive,
)
from groundcrew.codec import ActionReceipt, ActionSpec
from groundcrew.content_diff import ContentDiff, FileDiff, content_diff
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.snapshot import FileState, SnapshotDiff, StateSnapshot
from groundcrew.tool_misuse import (
    PlannedToolCall,
    ToolMisuseReport,
    ToolSchema,
    analyze_tool_misuse,
    assert_tool_misuse_ok,
    call_is_valid,
    gate_tool_misuse,
)
from groundcrew.watcher import DirectoryWatcher

__version__ = _version("groundcrew")

__all__ = [
    "ActionReceipt",
    "ActionSpec",
    "ChainVerification",
    "ClosedLoopError",
    "ContentDiff",
    "DESTRUCTIVE_VERBS",
    "DirectoryWatcher",
    "FileDiff",
    "FileState",
    "GateOutcome",
    "Oracle",
    "PlannedToolCall",
    "ReceiptStore",
    "SnapshotDiff",
    "StateSnapshot",
    "ToolMisuseReport",
    "ToolSchema",
    "__version__",
    "analyze_tool_misuse",
    "assert_not_destructive",
    "assert_side_effects",
    "assert_tool_misuse_ok",
    "build_chain_report",
    "call_is_valid",
    "content_diff",
    "dead_paths_for_receipt",
    "gate_destructive",
    "gate_destructive_receipt",
    "gate_receipts",
    "gate_tool_misuse",
    "is_destructive",
    "shell_is_destructive",
    "sql_is_destructive",
    "verify_chain",
]
