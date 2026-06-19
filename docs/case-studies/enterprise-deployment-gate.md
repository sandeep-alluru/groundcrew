# Case Study: Cryptographic Deployment Receipts for SOC2-Compliant AI Agents

## Company Profile

**Nexus Cloud** is a cloud infrastructure SaaS company based in Denver, CO. With 120 engineers, they build managed Kubernetes and Terraform automation tools for mid-enterprise customers. Their platform processes roughly 15,000 automated deployments per month. In 2024, they began piloting AI agents to automate routine deployment tasks — applying Helm chart updates, rotating secrets, scaling node groups — with human-in-the-loop approval for higher-risk changes.

## The Problem

The deployment agents worked well in controlled tests, but two incidents in production revealed a fundamental audit gap.

In the first incident, a deployment agent was tasked with updating a Helm chart's resource limits. The agent correctly updated the target file — but also modified a `secrets.env.template` file in the same directory, apparently confused by a prompt injection in the chart's `NOTES.txt` file that instructed it to "also update the environment template." The unauthorized modification was discovered three days later during a routine security review, but by then it had been deployed to 23 customer clusters.

In the second incident, a SOC2 Type II auditor asked for evidence that automated changes in the previous quarter were limited to their declared scope. The security team could show git commits, but couldn't demonstrate which specific agent action caused which file change, or prove that the agent stayed within its authorized scope on any given deployment. The auditor required 5 days of manual log correlation to reconstruct the evidence trail.

The core problem: the team could tell *what* changed (git diffs), but couldn't prove *why* it changed (which agent action caused it) or *whether the agent stayed in bounds* (scope verification). The two questions an auditor — or a post-incident investigator — most needs to answer.

## Solution Architecture

Nexus Cloud wrapped every deployment agent action with groundcrew. Each action produces an `ActionReceipt` — a content-addressed, tamper-evident record binding the declared intent (`ActionSpec`) to the actual filesystem effect (before/after `StateSnapshot` and `SnapshotDiff`). Receipts are stored in a SQLite database and verified as a chain before each deployment is marked complete.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Nexus Cloud Deployment Agent                     │
│                                                                      │
│  Deployment task                                                     │
│  "Update chart X"    ┌────────────────────────────────────────────┐ │
│        │             │  ActionSpec                                │ │
│        │             │  verb="write", target="charts/X/values.yaml"│ │
│        │             └───────────────────┬────────────────────────┘ │
│        │                                 │                           │
│        ↓                                 ↓                           │
│  ┌─────────────┐          ┌──────────────────────────────────────┐  │
│  │   Oracle    │          │  StateSnapshot BEFORE                │  │
│  │  (context   │  ──────► │  SHA-256 of /deployment-root/*       │  │
│  │   manager)  │          └──────────────────────────────────────┘  │
│        │                                                             │
│        ↓ (agent runs)                                               │
│  ┌─────────────┐          ┌──────────────────────────────────────┐  │
│  │   Oracle    │          │  StateSnapshot AFTER                 │  │
│  │  __exit__   │  ──────► │  SHA-256 of /deployment-root/*       │  │
│  └─────────────┘          └──────────────────────────────────────┘  │
│        │                                                             │
│        ↓                                                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ActionReceipt                                               │   │
│  │  spec_id | before_id | after_id | diff (added/removed/mod)  │   │
│  │  → ReceiptStore (SQLite)                                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│        │                                                             │
│        ↓                                                             │
│  verify_chain(receipts) → is_valid? → mark deployment COMPLETE      │
└──────────────────────────────────────────────────────────────────────┘
```

The `verify_chain()` call at the end of each deployment confirms that `receipt[n].after_id == receipt[n+1].before_id` for every consecutive pair — proving the state transitioned exactly as recorded, with no gaps or substitutions.

## Implementation

```python
# nexus/deployment/audited_agent.py
from pathlib import Path
from groundcrew.oracle import Oracle, ReceiptStore
from groundcrew.codec import ActionSpec, ActionReceipt
from groundcrew.chain import verify_chain, build_chain_report
from groundcrew.content_diff import content_diff

DEPLOYMENT_ROOT = Path("/data/deployments")
RECEIPT_DB = Path("/data/groundcrew/receipts.db")
AUTHORIZED_PATHS = {
    "helm-update": ["charts/", "manifests/"],
    "secret-rotation": ["secrets/"],
    "scaling": ["node-groups/", "autoscaler-config/"],
}

def run_audited_deployment(
    deployment_id: str,
    task_type: str,
    agent_actions: list[dict],
) -> tuple[bool, str]:
    """Run a deployment with full groundcrew audit trail.

    Returns (success, report_text).
    """
    store = ReceiptStore(RECEIPT_DB)
    receipts: list[ActionReceipt] = []
    root = DEPLOYMENT_ROOT / deployment_id

    for action_def in agent_actions:
        spec = ActionSpec(
            verb=action_def["verb"],
            target=action_def["target"],
            params=action_def.get("params", {}),
        )

        # Scope check BEFORE executing
        authorized = AUTHORIZED_PATHS.get(task_type, [])
        if not any(action_def["target"].startswith(p) for p in authorized):
            print(f"  [BLOCKED] {spec.verb} → {spec.target} is out of scope for {task_type}")
            continue

        # Capture before/after state around the action
        with Oracle(root, spec=spec) as oracle:
            _execute_action(action_def, root)  # The actual agent file operation

        receipt = oracle.record(spec)
        store.save(receipt)
        receipts.append(receipt)

        # Log what actually changed
        before_snap = oracle._before
        after_snap = oracle._after
        if before_snap and after_snap:
            cdiff = content_diff(before_snap, after_snap, root)
            print(f"  Receipt {receipt.id}: "
                  f"+{cdiff.total_added} lines / -{cdiff.total_removed} lines "
                  f"across {len(cdiff.file_diffs)} file(s)")

            # Unauthorized file detection
            for fd in cdiff.file_diffs:
                if not any(fd.path.startswith(p) for p in authorized):
                    print(f"  [ALERT] Unauthorized file modified: {fd.path}")
                    # Page on-call, halt deployment

    # Verify the complete chain before marking deployment done
    verification = verify_chain(receipts)
    report = build_chain_report(receipts)

    return verification.is_valid, report


def audit_deployment(deployment_id: str) -> str:
    """Retrieve and verify the full receipt chain for a past deployment."""
    store = ReceiptStore(RECEIPT_DB)
    all_receipts = store.list_receipts()

    # Filter to this deployment (receipts tagged by spec.params["deployment_id"])
    receipts = [
        r for r in all_receipts
        if r.spec.params.get("deployment_id") == deployment_id
    ]

    verification = verify_chain(receipts)
    return build_chain_report(receipts)


def _execute_action(action_def: dict, root: Path) -> None:
    """Placeholder: the actual agent file operation."""
    target = root / action_def["target"]
    if action_def["verb"] == "write":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action_def.get("content", ""))
```

When the prompt injection incident was simulated retroactively with this system, `content_diff()` on the relevant receipt immediately showed `secrets.env.template` in the `modified` set — a file outside the `charts/` authorized path. The `[ALERT]` line would have triggered the on-call page and halted the deployment before it reached any customer cluster.

## Results

- **100% of deployment agent actions** now have cryptographic receipts stored in the SQLite receipt database, providing a tamper-evident audit trail from day one of deployment
- **SOC2 audit time reduced from 5 days to 4 hours**: Auditors can now query the receipt store by date range or deployment ID and get a complete chain-of-custody report with one CLI command (`groundcrew receipts --since 2025-01-01`)
- **3 unauthorized file modifications caught in the first month** — all were caught at the `content_diff()` scope-check step, before any modification reached production infrastructure
- **Chain verification adds under 10ms** to deployment completion time, making it viable to verify every deployment, not just sampled ones
- **Incident reconstruction time**: When the second incident (the audit gap) was replicated with groundcrew in place, the full evidence trail was assembled in under 15 minutes — compared to 5 days manually

## Key Takeaways

- You cannot audit what you cannot measure. Git diffs show what changed; `ActionReceipt` shows what the agent *intended* to change and what it *actually* changed — these are different things.
- `content_diff()` is the scope enforcement primitive. Comparing the actual `SnapshotDiff` against the declared authorized paths catches the class of "agent went out of bounds" failures that prompt-level guardrails miss.
- `verify_chain()` provides tamper evidence without cryptographic infrastructure. The chain integrity check is pure Python standard library — no PKI, no signing keys, no external services.
- Receipt stores make audits self-serve. When the SOC2 auditor can run `groundcrew receipts` themselves and get a structured chain-of-custody report, audit cycles compress dramatically.
- The `Oracle` context manager design makes adoption incremental. Existing agent code is wrapped, not rewritten.

## Try It Yourself

```bash
# Install groundcrew
pip install groundcrew

# Capture an action and inspect the receipt
git clone https://github.com/sandeep-alluru/groundcrew
cd groundcrew
pip install -e .

# Run the CLI capture command against the examples directory
groundcrew capture --root /tmp/test-root --verb write --target config.yaml \
  --run "python examples/write_config.py"

# List receipts and verify the chain
groundcrew receipts
groundcrew verify
```
