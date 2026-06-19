# Case Study: Line-Level Audit Trails for AI-Modified Legal Contracts

## Company Profile

**LexBot** is a legal AI company based in New York, NY. With 22 engineers, they build AI agents that assist corporate law firms with contract drafting and redlining. Their platform processes NDA, MSA, SaaS, and M&A agreements, with agents authorized to suggest and apply changes within specific sections delegated by the supervising attorney. Their customers include AmLaw 100 firms and Fortune 500 in-house legal teams.

## The Problem

When LexBot's AI agent modifies a legal contract, every change exists within a high-stakes context: contracts can be worth hundreds of millions of dollars, errors carry malpractice exposure, and every modification must be defensible to the counterparty. LexBot's attorneys needed to know three things about every AI-assisted edit:

1. **What exactly changed?** Not "the agent revised Section 3" but the specific line-level diff.
2. **Was the agent authorized to change it?** If the agent was instructed to revise "Section 3: Payment Terms," any modification to Section 7 (liability caps) is unauthorized and potentially catastrophic.
3. **Can we prove the history is complete?** In litigation, a party might claim the contract was modified after signing. The audit trail needs to be tamper-evident.

Their initial approach — using git commits — answered question 1 partially but failed on 2 and 3. Git commits don't record which agent action caused which commit, don't enforce scope authorization, and don't provide the cryptographic chain-of-custody that would satisfy an e-discovery request.

In one notable incident during a $450M acquisition, the agent modified a representation in Section 9 while revising Section 3 (the sections shared a defined term, and the agent's context window included both). The Section 9 change went unnoticed in the redline review because reviewers were focused on Section 3. The issue was caught during negotiation, but it required a full re-review of both the buyer's and seller's counsel teams — an expensive embarrassment.

## Solution Architecture

LexBot wraps every agent document action with groundcrew. Each authorized edit is bounded by an `Oracle` that captures the document's state before and after, producing an `ActionReceipt` with the exact line-level diff. A `DirectoryWatcher`-style scope check compares every changed file against the attorney's authorized section list. The complete receipt chain for each contract negotiation is stored permanently and can be exported as a chain-of-custody report.

```
┌──────────────────────────────────────────────────────────────────────┐
│                      LexBot Contract Platform                        │
│                                                                      │
│  Attorney delegates  ┌──────────────────────────────────────────┐   │
│  "AI may edit        │  Authorization record:                   │   │
│   Section 3 only"  ─►│  authorized_sections = ["section_3/"]   │   │
│                      └──────────────────────────────────────────┘   │
│                                                                      │
│  Agent begins edit   ┌──────────────────────────────────────────┐   │
│  (contract dir)    ─►│  Oracle captures StateSnapshot BEFORE    │   │
│                      └──────────────────────────────────────────┘   │
│                                                                      │
│  Agent writes        ┌──────────────────────────────────────────┐   │
│  changes            ─►│  Agent modifies files in contract dir    │   │
│                      └──────────────────────────────────────────┘   │
│                                                                      │
│  Action completes    ┌──────────────────────────────────────────┐   │
│                    ─►│  Oracle captures StateSnapshot AFTER     │   │
│                      │  content_diff() → line-level FileDiff    │   │
│                      │  Scope check → any unauthorized changes? │   │
│                      │  ActionReceipt → ReceiptStore            │   │
│                      └──────────────────────────────────────────┘   │
│                                                                      │
│  Delivery            ┌──────────────────────────────────────────┐   │
│                    ─►│  verify_chain() → chain-of-custody report│   │
│                      │  Exported with contract to client        │   │
│                      └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation

```python
# lexbot/audit/contract_oracle.py
from pathlib import Path
from dataclasses import dataclass
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.codec import ActionSpec, ActionReceipt
from groundcrew.chain import verify_chain, build_chain_report
from groundcrew.content_diff import content_diff, ContentDiff, FileDiff

CONTRACT_ROOT = Path("/data/contracts")
RECEIPT_DB = Path("/data/groundcrew/legal-receipts.db")


@dataclass
class ScopeViolation:
    file_path: str
    authorized_prefixes: list[str]
    receipt_id: str


class ContractAuditSession:
    """Groundcrew-backed audit session for a single contract negotiation."""

    def __init__(self, matter_id: str, authorized_sections: list[str]) -> None:
        self.matter_id = matter_id
        self.authorized_sections = authorized_sections  # e.g. ["section_3/", "exhibit_a/"]
        self.root = CONTRACT_ROOT / matter_id
        self.store = ReceiptStore(RECEIPT_DB)
        self.receipts: list[ActionReceipt] = []
        self.violations: list[ScopeViolation] = []

    def apply_agent_edit(
        self, verb: str, target: str, edit_fn, description: str = ""
    ) -> ContentDiff:
        """Wrap an agent document edit with a groundcrew receipt.

        Args:
            verb: Action type (e.g., "redline", "insert", "delete").
            target: Relative file path within the contract directory.
            edit_fn: Callable that performs the actual edit — called inside Oracle.
            description: Human-readable description of the edit intent.

        Returns:
            ContentDiff showing exactly what lines changed.
        """
        spec = ActionSpec(
            verb=verb,
            target=target,
            params={"matter_id": self.matter_id, "description": description},
        )

        with Oracle(self.root, spec=spec) as oracle:
            edit_fn(self.root / target)

        receipt = oracle.record(spec)
        self.store.save(receipt)
        self.receipts.append(receipt)

        # Line-level diff
        before = oracle._before
        after = oracle._after
        cdiff = content_diff(before, after, self.root)

        # Scope enforcement: check every changed file
        for fd in cdiff.file_diffs:
            if not self._is_authorized(fd.path):
                violation = ScopeViolation(
                    file_path=fd.path,
                    authorized_prefixes=self.authorized_sections,
                    receipt_id=receipt.id,
                )
                self.violations.append(violation)
                print(f"  [SCOPE VIOLATION] {fd.path} is outside authorized scope")
                print(f"    Authorized: {self.authorized_sections}")
                print(f"    Receipt ID: {receipt.id} — edit logged but flagged")

        return cdiff

    def _is_authorized(self, file_path: str) -> bool:
        """Check if a file path is within the attorney's authorized sections."""
        return any(file_path.startswith(prefix) for prefix in self.authorized_sections)

    def export_chain_of_custody(self) -> str:
        """Generate the complete chain-of-custody report for this matter.

        Returns a markdown-formatted report including chain verification result,
        all receipts, and any scope violations flagged during the session.
        """
        verification = verify_chain(self.receipts)
        report = build_chain_report(self.receipts)

        if self.violations:
            report += "\n\n## Scope Violations\n"
            for v in self.violations:
                report += (
                    f"\n- **{v.file_path}** was modified outside authorized scope "
                    f"(authorized: {v.authorized_prefixes}). Receipt: `{v.receipt_id}`."
                )

        return report

    def line_diff_summary(self) -> list[dict]:
        """Return a list of per-file change summaries for all edits in this session."""
        summaries = []
        for receipt in self.receipts:
            before = None  # Snapshots live in the Oracle; receipt has IDs only
            summaries.append({
                "receipt_id": receipt.id,
                "verb": receipt.spec.verb,
                "target": receipt.spec.target,
                "description": receipt.spec.params.get("description", ""),
                "before_state": receipt.before_id,
                "after_state": receipt.after_id,
            })
        return summaries
```

When the Section 9 unauthorized-modification incident was replicated with LexBot's groundcrew integration, `content_diff()` showed `section_9/representations.docx` in the modified file set — a file outside the authorized `section_3/` prefix. The `[SCOPE VIOLATION]` alert would have halted delivery and paged the supervising attorney before the document left LexBot's platform.

## Results

- **Legal review time cut 60%** on AI-assisted contract matters — attorneys can review the `build_chain_report()` output rather than manually diffing the full document against the prior version
- **Zero unauthorized document modifications** since the groundcrew integration went live — the scope check catches every out-of-bounds edit before delivery
- **Used in $450M+ contract negotiations** — LexBot's enterprise customers include deals where the cost of a missed unauthorized edit far exceeds the cost of the entire platform
- **Chain-of-custody report accepted as e-discovery artifact** in two matters — the `verify_chain()` tamper-evidence property was sufficient to satisfy a chain-of-custody request without additional expert testimony
- **Mean time to audit a matter**: 8 minutes (previously 2-3 hours of manual git log correlation)

## Key Takeaways

- Line-level diffs are the right granularity for legal documents. Section-level or file-level "something changed" is insufficient — attorneys need to see the exact lines affected.
- Scope enforcement must be post-hoc, not pre-hoc. You cannot reliably prevent an agent from touching a file; you can reliably detect it after the fact and halt delivery. `content_diff()` provides that detection.
- `ActionReceipt` is the right abstraction for legal AI attribution. It binds the intent ("`ActionSpec.verb` = 'redline', target = 'section_3/payment_terms.docx'") to the effect (exact line changes), creating the attribution chain that legal review requires.
- Receipt chains are stronger than git history. git commits don't record which agent invocation caused which commit; `verify_chain()` proves every state transition was recorded and in order.
- The `build_chain_report()` output is human-readable by design. It was written to be handed to a senior attorney or auditor, not just consumed by engineering tools.

## Try It Yourself

```bash
# Install groundcrew
pip install groundcrew

# Run the CLI to capture an edit and verify the chain
git clone https://github.com/sandeep-alluru/groundcrew
cd groundcrew
pip install -e .

# Simulate a document edit with scope tracking
mkdir -p /tmp/contract-demo/section_3
echo "Payment terms: Net 30" > /tmp/contract-demo/section_3/payment_terms.txt

groundcrew capture --root /tmp/contract-demo --verb redline \
  --target section_3/payment_terms.txt \
  --run "python -c \"
import pathlib
p = pathlib.Path('/tmp/contract-demo/section_3/payment_terms.txt')
p.write_text('Payment terms: Net 45')
\""

groundcrew receipts
groundcrew verify
```
