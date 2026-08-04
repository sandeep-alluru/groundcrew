# Closed loop — `groundcrew`

**Status:** wired (eagle-eyes / 2026-08-04)  
**Owner loop:** L4 FS/computer-use · **Law:** L10 non-empty side effects

## Load-bearing job

Filesystem action receipts / before-after snapshots

## Reader (implemented)

```python
from groundcrew import gate_receipts, assert_side_effects

# Empty store / list → FAIL_LOUD (exit 2)
# success=True with changed_paths==0 → FAIL_LOUD (L10)
# all success=False → FAIL (exit 1)
# success + real changes → PASS (exit 0)
out = gate_receipts(path_or_store_or_list)
assert_side_effects([...])  # raises ClosedLoopError unless ok
```

Module: `groundcrew.closed_loop` · API: `gate_receipts`, `assert_side_effects`

## Who reads the output?

CI / eagle-eyes dogfood / integrators that must block “success” on empty receipts

## What outcome changes?

Block success on empty receipt or zero file changes (L10 / D-GCROOT class)

## When NOT to use (anti-ornament)

Never report success on 0 files / dead paths

## Non-Ornament checklist

- [x] Reader implemented in library (`closed_loop.gate_receipts`)
- [x] Empty/wrong output fails loudly (exit 2)
- [x] Not exposed as free MCP in product agents
- [ ] Linked gap IDs in mem0 when improving
- [ ] eagle-eyes dogfood exercises `gate_receipts` (optional next)

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory
- L10: groundcrew success requires non-empty side effects

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
