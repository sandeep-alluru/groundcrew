# Closed loop — `groundcrew`

**Status:** stub (eagle-eyes Phase 0 / 2026-08-04)  
**Owner loop:** L4 FS/computer-use

## Load-bearing job

Filesystem action receipts / before-after snapshots

## Who reads the output?

Gate or test asserts receipt.files_changed > 0 when mutation expected

## What outcome changes?

Block success on empty receipt (D-GCROOT class)

## When NOT to use (anti-ornament)

Never report success on 0 files / dead paths

## Non-Ornament checklist

- [ ] Reader implemented in CI, gate, or eagle-eyes script
- [ ] Empty/wrong output fails loudly
- [ ] Not exposed as free MCP in product agents
- [ ] Linked gap IDs in mem0 when improving

## Related failures (farm memory)

- 2026-07-22 MCP buffet trim: write-only tools removed from Foundry framework
- D-FOGHORN: misuse of append-only fact log as current state
- Dual-path mem0: never rely on MCP-only for critical memory

## Daily rotation note

This file exists so pillar **C (closed loop)** can rise with real wiring over time. Prefer small daily commits that move a checkbox toward done.

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
