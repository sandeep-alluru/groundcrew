# Closed loop — `groundcrew`

**Status:** wired + D-GCROOT + DB-WIPE (eagle-eyes / 2026-08-06)  
**Owner loop:** L4 FS/computer-use · **Law:** L10 non-empty side effects

## Load-bearing job

Filesystem action receipts / before-after snapshots + pre-exec destructive tool gate

## Reader (implemented)

```python
from groundcrew import (
    gate_receipts,
    assert_side_effects,
    dead_paths_for_receipt,
    gate_destructive,
    gate_destructive_receipt,
    sql_is_destructive,
)

# Empty store / list → FAIL_LOUD (exit 2)
# success=True with changed_paths==0 → FAIL_LOUD (L10)
# success + phantom paths not on disk → FAIL_LOUD (D-GCROOT, requires root=)
# all success=False → FAIL (exit 1)
# success + real changes (+ optional disk verify) → PASS (exit 0)
out = gate_receipts(path_or_store_or_list)
out = gate_receipts(receipts, root="/path/to/workspace")  # D-GCROOT
assert_side_effects([...], root=ws)  # raises ClosedLoopError unless ok

# DB-WIPE / Replit class — call BEFORE executing SQL/shell tools
out = gate_destructive(
    verb="db_wipe",
    sql="DROP DATABASE production;",
    inventory=["production"],
    approved=True,
    approval_token="owner-token",
    environment="production",
)
# destructive + no inventory → FAIL_LOUD
# destructive + prod + no approval → FAIL_LOUD (human_required)
# SELECT / non-destructive → PASS
```

Module: `groundcrew.closed_loop` · API: `gate_receipts`, `assert_side_effects`,
`dead_paths_for_receipt`, `gate_destructive`, `gate_destructive_receipt`,
`sql_is_destructive`, `shell_is_destructive`, `is_destructive`

See `docs/REAL_WORLD_CASES.md` (D-GCROOT, DB-WIPE).

## Who reads the output?

CI / eagle-eyes dogfood / integrators that must block “success” on empty receipts
and block unattended DROP/rm before execution

## What outcome changes?

Block success on empty receipt, zero file changes, or dead/phantom paths (L10 / D-GCROOT).
Block destructive SQL/shell without inventory + human approval (DB-WIPE).

## When NOT to use (anti-ornament)

Never report success on 0 files / dead paths. Always pass `root=` when the
workspace is known. Never execute free-form SQL without `gate_destructive`.

## Non-Ornament checklist

- [x] Reader implemented in library (`closed_loop.gate_receipts`)
- [x] Empty/wrong output fails loudly (exit 2)
- [x] Dead-path verify when `root=` provided (D-GCROOT)
- [x] Destructive pre-exec gate (`gate_destructive` / DB-WIPE)
- [x] Not exposed as free MCP in product agents
- [x] Named cases in `docs/REAL_WORLD_CASES.md`
- [ ] Linked gap IDs in mem0 when improving
- [x] eagle-eyes dogfood exercises empty `gate_receipts` (empty list/effect)

## Related failures (farm memory)

- D-GCROOT: success with 0 files / phantom changed_paths
- L10: groundcrew success requires non-empty side effects
- DB-WIPE: Replit AI / AgentWard / Antigravity unattended destructive tools
- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

Prefer small daily commits that keep the gate covered and used by readers.

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-04
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-05
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-06
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-06
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-06
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-06
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-07
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-07
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-07
- pytest_rc: 0
- node: clawer-samurai-2

## Auto-run 2026-08-07
- pytest_rc: 0
- node: clawer-samurai-2
