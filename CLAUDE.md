# groundcrew — Session Anchor

**Research spec:** `../tech-research/07-Computer-and-Browser-Use/groundcrew-the-deterministic-state-oracle-for-computer/README.md`  
**One-liner:** Ground-truth state oracle for computer-use agents via OS-layer (a11y tree + FS + network)  
**Phase:** backlog  
**Stack:** Python, pyobjc-framework-Accessibility (macOS), watchdog  

## Key decisions
- macOS-only for v0.1 (AXUIElement/AXObserver is mature); Linux/Windows deferred
<!-- more decisions as sessions progress -->

## Next step
Read the research spec, then implement the macOS AXUIElement state snapshot daemon.

## MVP definition
- `pip install groundcrew` works
- Python daemon reading macOS AXUIElement + watchdog/FSEvents → structured JSON snapshots
- CLI: `groundcrew capture <script>` wraps any Python script and emits before/after "action receipt"
- Structured JSON diff showing: accessibility tree delta + filesystem change
- README with example action receipt output
