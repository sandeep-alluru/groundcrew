# groundcrew — Architecture

## Overview

groundcrew is a deterministic state oracle and semantic action codec for computer-use agents. It captures filesystem state before and after agent actions, produces structured diffs, and stores tamper-evident action receipts.

## Module map

```
src/groundcrew/
├── snapshot.py       # FileState, StateSnapshot, SnapshotDiff, diff_snapshots()
├── codec.py          # ActionSpec, ActionReceipt
├── oracle.py         # Oracle context manager, capture(), ReceiptStore
├── report.py         # Rich, JSON, Markdown formatters
├── cli.py            # Click CLI entry point
├── api.py            # FastAPI REST server
└── mcp_server.py     # MCP server (lazy import)
```

## Data model

### Content-addressing

All core objects are content-addressed using SHA-256[:16]:

- `FileState.sha256` — SHA-256 of file content
- `StateSnapshot.id` — SHA-256[:16] of sorted JSON of all FileStates
- `ActionSpec.id` — SHA-256[:16] of `f"{verb}|{target}|{json(params)}"`
- `ActionReceipt.id` — SHA-256[:16] of `f"{spec.id}|{before_id}|{after_id}"`

### Core dataclasses

```
FileState
  path: str          (relative to root)
  size: int
  sha256: str        (full SHA-256 of file content)

StateSnapshot
  id: str            (content-addressed)
  timestamp: float
  root: str
  files: dict[str, FileState]

  capture(root) → StateSnapshot

SnapshotDiff
  snapshot_a_id: str | None
  snapshot_b_id: str
  added: list[FileState]
  removed: list[FileState]
  modified: list[tuple[FileState, FileState]]

  changed_paths → set[str]

ActionSpec
  verb: str          ("click", "type", "run", "write", "navigate")
  target: str        (semantic target description)
  params: dict
  id: str            (content-addressed)

ActionReceipt
  spec: ActionSpec
  before_id: str
  after_id: str
  diff: SnapshotDiff
  success: bool
  timestamp: float
  id: str            (content-addressed)
```

## Oracle

`Oracle` is a context manager that captures filesystem state before and after an action:

```python
class Oracle:
    def __init__(self, root, spec=None)
    def __enter__(self) → Oracle        # captures before_snapshot
    def __exit__(...)                   # captures after_snapshot
    def record(spec) → ActionReceipt    # computes diff, returns receipt
```

The `capture()` helper provides a simpler one-liner:

```python
@contextmanager
def capture(root, spec) → Generator[Oracle, None, None]
```

## Storage (ReceiptStore)

`ReceiptStore` is a SQLite-backed store with three tables:

- `snapshots` — JSON-serialized StateSnapshot objects
- `receipts` — ActionReceipt metadata (id, spec_id, before_id, after_id, success, timestamp)
- `receipt_data` — Full JSON-serialized ActionReceipt (for retrieval)

Snapshots are stored by content-addressed ID, so capturing the same directory state twice is a no-op.

## CLI

The CLI uses Click with a top-level `--db` option:

- `capture` — wraps a shell command with Oracle context, stores receipt
- `diff RECEIPT_ID` — retrieves and displays a stored receipt's diff
- `log` — lists all receipts from the store
- `status` — shows store info

## API

FastAPI routes mirror the CLI commands:

- `GET /health` — liveness probe
- `POST /capture` — run a shell command and capture state
- `GET /receipt/{receipt_id}` — retrieve a stored receipt
- `GET /receipts` — list all receipts
- `GET /diff/{receipt_id}` — get SnapshotDiff for a receipt

## MCP Server

The MCP server lazily imports `mcp` to avoid hard-dependency issues. It exposes three tools:

- `capture_state` — capture a snapshot of a directory
- `get_receipt` — retrieve a stored receipt by ID
- `list_receipts` — list all stored receipts

## Design decisions

**Pure stdlib for hashing** — `hashlib.sha256` + `os.walk` + `pathlib.Path.stat()`. No third-party dependencies for the core snapshot engine.

**Append-only receipts** — Receipts are never modified or deleted. The audit trail is permanent by design.

**Graceful file errors** — `StateSnapshot.capture()` silently skips files it cannot read (PermissionError, IsADirectoryError). The snapshot reflects what the agent could actually observe.

**No diff beyond filesystem** — v0.1 covers filesystem state only. Accessibility-tree and network-layer capture are explicitly deferred to future versions to keep the library scope achievable and cross-platform.
