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

## Case DB-WIPE — unattended destructive SQL/shell (Replit / AgentWard class)

**Source:** Public incidents + Track B research (`20260806T201216Z`):

| Incident | Link / note |
|----------|-------------|
| Replit AI deleted production DB | PUBLIC_FAILURE_CORPUS / HN class |
| Google Antigravity wipe | unattended destructive filesystem |
| HN: “An AI agent deleted our production database” | agent claimed success after wipe |
| AgentWard | post-incident firewall after AI file delete |
| Genesis Agent | self-destructive agent tools |

**What fails:**

1. Free-form SQL tools accept `DROP DATABASE` / `TRUNCATE` / `DELETE FROM` without
   naming inventory (tables/DBs/paths) first.
2. Production environment runs destructive verbs (`db_wipe`, `drop`, `rm -rf`)
   without a human approval token.
3. Success receipts are written after the wipe — filesystem `gate_receipts` alone
   cannot see DB schema loss.

**Product in this repo:**

| Control | API |
|---------|-----|
| SQL classifier | `sql_is_destructive(sql)` |
| Shell classifier | `shell_is_destructive(command)` |
| Verb/tool classifier | `is_destructive(verb, sql=..., command=..., params=...)` |
| Pre-exec gate | `gate_destructive(...)` — inventory + approval in prod |
| Receipt gate | `gate_destructive_receipt(receipt, ...)` |
| Raise form | `assert_not_destructive(...)` |
| Verb set | `DESTRUCTIVE_VERBS` |

**Rules (load-bearing):**

- Destructive + empty inventory → **FAIL_LOUD** (`human_required`)
- Destructive + strict env (`production`/`staging`/…) + no approval → **FAIL_LOUD**
- Non-destructive (e.g. `SELECT`) → **PASS** without token
- `dev`/`test` still require inventory for destructive ops; approval optional

**Tests:** `tests/test_closed_loop_destructive.py` — Replit fixture, inventory miss,
approval miss, authorised path, receipt path.

**Non-Ornament:** Integrators **must** call `gate_destructive` (or
`gate_destructive_receipt`) **before** executing SQL/shell tools. Pair with
`humanproof.gate_approval` for token issue/consume. Without the pre-exec call,
this library cannot stop the wipe.

---

## Case TOOL-MISUSE — PRISMS validity / over-calling / missing (arXiv 2608.00218)

**Source:** Track B research (`20260809T001229Z`) —
[A Few Neurons Reveal When LLMs Misuse Tools](https://arxiv.org/abs/2608.00218)
(PRISMS sparse detection of tool-use failures).

**What fails:**

1. **validity** — tool calls with missing/invalid arguments still execute.
2. **over-calling** — unnecessary tools on answer-only turns / past max calls.
3. **missing** — tools required by the task but none planned.

**Product in this repo:**

| Control | API |
|---------|-----|
| Schema / plan types | `ToolSchema`, `PlannedToolCall` |
| Classifier | `analyze_tool_misuse` → `ToolMisuseReport` |
| Validity helper | `call_is_valid` |
| Gate | `gate_tool_misuse(...)` |
| Raise form | `assert_tool_misuse_ok` |

**Rules (load-bearing):**

- Missing required tools / empty when `tools_required` → **FAIL_LOUD**
- Invalid/incomplete arguments → **FAIL**
- Over-calling (`tools_forbidden` or over `max_calls`) → **FAIL**
- Clean plan → **PASS**

**Tests:** `tests/test_tool_misuse.py`

**Non-Ornament:** Call `gate_tool_misuse` on the tool plan **before** execution.
Pair with `gate_destructive` for DROP/rm and `gate_receipts` after side effects.

## Related queue IDs

- **SILENT-SUCCESS** — assemble/exit 0 degraded (shared with notarize)
- **DB-WIPE** — this case (Replit / Antigravity / AgentWard)
- **TOOL-MISUSE** — PRISMS class (this section)
- Public: pair with humanproof `gate_approval` for token lifecycle
