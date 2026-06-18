"""groundcrew demo — end-to-end walkthrough.

Run from repo root:
    python examples/demo.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from groundcrew import ActionSpec, Oracle, ReceiptStore
from groundcrew.report import print_receipt, to_json, to_markdown


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / ".groundcrew" / "receipts.db"

        # ── 1. Capture a "write" action ──────────────────────────────────────
        spec = ActionSpec(verb="write", target="config.json", params={"key": "value"})

        with Oracle(str(root), spec) as oracle:
            # Simulate an agent writing a config file
            (root / "config.json").write_text(json.dumps({"key": "value"}))

        receipt = oracle.record(spec)

        print("ActionReceipt ID:", receipt.id[:8])
        print("Files changed:", receipt.diff.changed_paths)
        print("Success:", receipt.success)

        # ── 2. Persist to store ───────────────────────────────────────────────
        store = ReceiptStore(str(db_path))
        store.save(receipt)

        retrieved = store.get(receipt.id)
        assert retrieved is not None
        assert retrieved.id == receipt.id
        print("\nReceipt round-tripped from store:", retrieved.id[:8])

        # ── 3. Capture a second action ────────────────────────────────────────
        spec2 = ActionSpec(verb="run", target="process_data.py", params={})

        with Oracle(str(root), spec2) as oracle2:
            (root / "output.txt").write_text("processed\n")
            (root / "log.txt").write_text("done\n")

        receipt2 = oracle2.record(spec2)
        store.save(receipt2)

        # ── 4. Show rich terminal output ──────────────────────────────────────
        print("\n── Rich receipt summary ──")
        print_receipt(receipt)

        # ── 5. JSON output ────────────────────────────────────────────────────
        j = json.loads(to_json(receipt))
        assert j["id"] == receipt.id
        print("\n── JSON output (first 80 chars) ──")
        print(to_json(receipt)[:80] + "...")

        # ── 6. Markdown output ────────────────────────────────────────────────
        md = to_markdown([receipt, receipt2])
        assert "Groundcrew" in md or "groundcrew" in md.lower()
        print("\n── Markdown (first 3 lines) ──")
        print("\n".join(md.split("\n")[:3]))

        # ── 7. List all receipts ──────────────────────────────────────────────
        all_receipts = store.list_receipts()
        assert len(all_receipts) == 2
        print(f"\nTotal receipts in store: {len(all_receipts)}")

        store.close()

    print("\ngroundcrew demo complete.")


if __name__ == "__main__":
    main()
