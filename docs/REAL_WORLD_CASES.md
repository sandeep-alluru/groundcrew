# Real-world cases driving groundcrew

## Case D-GCROOT — success with 0 files / phantom side effects

**Source:** LOCKED_PLAN L10 + farm doctrine (eagle-eyes REAL_WORK_QUEUE);
class of failure seen when agents report “success” without load-bearing
filesystem effects (Foundry-class silent success / vacuous guards).

**What fails:**

1. **Empty effects:** `success=True` with `changed_paths == 0` — action claimed
   done, nothing on disk changed.
2. **Dead / phantom paths:** `success=True` with non-empty `changed_paths` that
   invent `FileState` rows for files never written (or “removed” files still
   present). A gate that only checks `len(changed_paths) > 0` **passes** and
   masks the lie.

**Product in this repo:**

| Control | API |
|---------|-----|
| Empty side effects | `gate_receipts` → FAIL_LOUD (L10) |
| Dead-path verify | `gate_receipts(..., root=workspace)` → FAIL_LOUD (D-GCROOT) |
| Helper | `dead_paths_for_receipt(receipt, root)` |
| Raise form | `assert_side_effects(..., root=...)` |

**Tests:** `tests/test_closed_loop_reader.py` — phantom added path, removed-still-present,
real Oracle write with disk verify.

**Non-Ornament:** Integrators with a workspace **must** pass `root=` (or
`verify_disk=True` with root). Without root, only the empty-effects check runs;
phantom paths remain a known gap (documented in tests).

## Related queue IDs

- **SILENT-SUCCESS** — assemble/exit 0 degraded (shared with notarize)
- Public: Replit DB wipe / Antigravity — approval + receipts for destructive ops
  (humanproof + groundcrew; approval not yet shipped)
