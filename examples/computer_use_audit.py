"""
Healthcare RCM Computer-Use Audit Demo
=======================================
Demonstrates groundcrew + notarize + clickproof working together for a
healthcare Revenue Cycle Management (RCM) audit scenario.

An AI agent processes insurance claims in a web portal. Three tools create
an end-to-end, tamper-evident audit trail:

  1. clickproof  — Records GUI actions (clicks, form submissions) as
                   content-addressed UIFacts. Immutable record of what
                   the agent saw and clicked.

  2. groundcrew  — The Oracle captures deterministic ActionReceipts for
                   each significant action. StateSnapshot before/after
                   confirms the portal state transitioned correctly.

  3. notarize    — Assembles the full execution trace as a hash-chained
                   AgentTrace. PrivacyScrubber strips patient PII (SSN,
                   DOB) before storage. ConsistencyVerifier confirms the
                   trace has not been tampered with.

Run:
    pip install groundcrew notarize clickproof
    python 02_computer_use_audit.py
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

# groundcrew
from groundcrew.chain import build_chain_report, verify_chain
from groundcrew.codec import ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore

# notarize
from notarize.scrubber import PrivacyScrubber
from notarize.trace import AgentTrace, TraceStep
from notarize.verifier import ConsistencyVerifier

# clickproof
from clickproof.fact import FactObservation, UIFact
from clickproof.store import FactStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    """Print a bold section header."""
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def subsection(title: str) -> None:
    print(f"\n  -- {title} --")


# ── Phase 1: clickproof — record GUI actions ──────────────────────────────────

def phase_clickproof(store: FactStore, run_id: str) -> list[UIFact]:
    """Record GUI behavioral facts and observations for the RCM portal session."""
    section("PHASE 1: clickproof — GUI Action Recording")

    # The RCM portal is versioned so facts are tied to a specific UI release.
    portal_app = "rcm-portal"
    portal_ver = "2024.Q4"

    facts = [
        UIFact(
            app_name=portal_app,
            app_version=portal_ver,
            element="patient-id-verify-button",
            action="click",
            outcome="patient-identity-confirmed",
            context="claim-intake-form",
            confidence=1.0,
        ),
        UIFact(
            app_name=portal_app,
            app_version=portal_ver,
            element="claim-submit-button",
            action="click",
            outcome="claim-submitted-to-payer",
            context="claim-review-page",
            confidence=1.0,
        ),
        UIFact(
            app_name=portal_app,
            app_version=portal_ver,
            element="prior-auth-request-button",
            action="click",
            outcome="prior-auth-request-sent",
            context="authorization-page",
            confidence=0.95,
        ),
        UIFact(
            app_name=portal_app,
            app_version=portal_ver,
            element="denial-reason-dropdown",
            action="navigate",
            outcome="denial-codes-loaded",
            context="denial-management-page",
            confidence=1.0,
        ),
    ]

    for fact in facts:
        store.add_fact(fact)
        print(f"  [UIFact] {fact.element!r}  id={fact.id}")

    # Record observations confirming each click actually happened in this run.
    subsection("Recording click observations")
    now = time.time()
    observations = [
        FactObservation(
            fact_id=facts[0].id,
            observed_at=now,
            confirmed=True,
            agent_run_id=run_id,
        ),
        FactObservation(
            fact_id=facts[1].id,
            observed_at=now + 1.0,
            confirmed=True,
            agent_run_id=run_id,
        ),
        FactObservation(
            fact_id=facts[2].id,
            observed_at=now + 2.0,
            confirmed=True,
            agent_run_id=run_id,
        ),
        FactObservation(
            fact_id=facts[3].id,
            observed_at=now + 3.0,
            confirmed=True,
            agent_run_id=run_id,
        ),
    ]
    for obs in observations:
        store.add_observation(obs)
        print(f"  [Observation] fact={obs.fact_id}  confirmed={obs.confirmed}  run={obs.agent_run_id}")

    subsection("Summary")
    all_facts = store.list_facts(app_name=portal_app)
    print(f"  Total UIFacts stored for '{portal_app}': {len(all_facts)}")
    obs_count = sum(len(store.get_observations(f.id)) for f in all_facts)
    print(f"  Total observations stored: {obs_count}")

    return facts


# ── Phase 2: groundcrew — Oracle receipts and chain verification ───────────────

def phase_groundcrew(portal_root: Path, db_path: Path) -> list:
    """Use Oracle to capture before/after state for each claim action."""
    section("PHASE 2: groundcrew — Oracle Receipts & Chain Verification")

    store = ReceiptStore(str(db_path))
    receipts = []

    # ── Action 1: verify patient identity ────────────────────────────────────
    subsection("Action 1: verify_patient_identity")
    spec1 = ActionSpec(
        verb="verify",
        target="patient_identity",
        params={"claim_id": "CLM-2024-00891", "payer": "BlueCross"},
    )
    with Oracle(str(portal_root), spec1) as oracle1:
        # Simulate portal writing a verification record to the working directory.
        (portal_root / "verifications").mkdir(exist_ok=True)
        (portal_root / "verifications" / "CLM-2024-00891_identity.json").write_text(
            json.dumps({"claim_id": "CLM-2024-00891", "status": "verified", "method": "npi-lookup"})
        )
    receipt1 = oracle1.record(spec1)
    store.save(receipt1)
    print(f"  Receipt id : {receipt1.id}")
    print(f"  Success    : {receipt1.success}")
    print(f"  Files added: {[f.path for f in receipt1.diff.added]}")

    # ── Action 2: submit claim to payer ──────────────────────────────────────
    subsection("Action 2: submit_claim")
    spec2 = ActionSpec(
        verb="submit",
        target="claim",
        params={"claim_id": "CLM-2024-00891", "payer": "BlueCross", "amount_usd": 1_250.00},
    )
    with Oracle(str(portal_root), spec2) as oracle2:
        (portal_root / "claims").mkdir(exist_ok=True)
        (portal_root / "claims" / "CLM-2024-00891_submission.json").write_text(
            json.dumps({
                "claim_id": "CLM-2024-00891",
                "status": "submitted",
                "payer": "BlueCross",
                "amount_usd": 1250.00,
            })
        )
    receipt2 = oracle2.record(spec2)
    store.save(receipt2)
    print(f"  Receipt id : {receipt2.id}")
    print(f"  Success    : {receipt2.success}")
    print(f"  Files added: {[f.path for f in receipt2.diff.added]}")

    # ── Action 3: request prior authorization ────────────────────────────────
    subsection("Action 3: request_prior_auth")
    spec3 = ActionSpec(
        verb="request",
        target="prior_auth",
        params={"claim_id": "CLM-2024-00891", "procedure_code": "99213"},
    )
    with Oracle(str(portal_root), spec3) as oracle3:
        (portal_root / "authorizations").mkdir(exist_ok=True)
        (portal_root / "authorizations" / "CLM-2024-00891_auth.json").write_text(
            json.dumps({
                "claim_id": "CLM-2024-00891",
                "procedure_code": "99213",
                "auth_status": "pending",
            })
        )
    receipt3 = oracle3.record(spec3)
    store.save(receipt3)
    print(f"  Receipt id : {receipt3.id}")
    print(f"  Success    : {receipt3.success}")
    print(f"  Files added: {[f.path for f in receipt3.diff.added]}")

    receipts = [receipt1, receipt2, receipt3]

    # ── Chain verification ────────────────────────────────────────────────────
    subsection("Chain-of-Custody Verification")
    chain_result = verify_chain(receipts)
    print(f"  Chain length : {chain_result.chain_length}")
    print(f"  Is valid     : {chain_result.is_valid}")
    print(f"  Summary      : {chain_result.summary}")

    # ── Full chain-of-custody report ─────────────────────────────────────────
    subsection("Full Chain-of-Custody Report")
    report = build_chain_report(receipts)
    for line in report.split("\n"):
        print(f"  {line}")

    try:
        return receipts
    finally:
        store.close()


# ── Phase 3: notarize — trace assembly, PII scrub, and verification ────────────

def phase_notarize(run_id: str, facts: list[UIFact], receipts: list) -> None:
    """Assemble a hash-chained AgentTrace, scrub PII, then verify integrity."""
    section("PHASE 3: notarize — Trace Assembly, PII Scrub & Verification")

    # Build trace steps. Some observations intentionally contain raw PII strings
    # to demonstrate that PrivacyScrubber catches them before storage.
    steps = [
        TraceStep(
            step_index=0,
            action="gui:click patient-id-verify-button",
            observation=(
                f"Patient identity verification panel opened. "
                f"Patient SSN on file: 529-33-4918. DOB: 1972-08-14. "
                f"UIFact recorded: {facts[0].id}"
            ),
            result="success",
            tool_name="clickproof",
        ),
        TraceStep(
            step_index=1,
            action="oracle:verify patient_identity CLM-2024-00891",
            observation=(
                f"Oracle captured before/after state. "
                f"ActionReceipt id={receipts[0].id}. "
                f"Files added: verifications/CLM-2024-00891_identity.json"
            ),
            result="success",
            tool_name="groundcrew",
        ),
        TraceStep(
            step_index=2,
            action="gui:click claim-submit-button",
            observation=(
                f"Claim submission dialog confirmed. "
                f"Patient contact: billing@healthsystem.example.com. "
                f"UIFact recorded: {facts[1].id}"
            ),
            result="success",
            tool_name="clickproof",
        ),
        TraceStep(
            step_index=3,
            action="oracle:submit claim CLM-2024-00891",
            observation=(
                f"Oracle captured state transition for claim submission. "
                f"ActionReceipt id={receipts[1].id}. Amount: $1,250.00"
            ),
            result="success",
            tool_name="groundcrew",
        ),
        TraceStep(
            step_index=4,
            action="gui:click prior-auth-request-button",
            observation=(
                f"Prior auth request dispatched to BlueCross. "
                f"UIFact recorded: {facts[2].id}"
            ),
            result="success",
            tool_name="clickproof",
        ),
        TraceStep(
            step_index=5,
            action="oracle:request prior_auth CLM-2024-00891",
            observation=(
                f"Oracle captured prior auth state change. "
                f"ActionReceipt id={receipts[2].id}. Procedure code: 99213"
            ),
            result="success",
            tool_name="groundcrew",
        ),
        TraceStep(
            step_index=6,
            action="audit:finalize RCM session",
            observation=(
                "All claim actions completed successfully. "
                "Chain-of-custody verified. "
                f"Session run_id={run_id}"
            ),
            result="success",
            tool_name="notarize",
        ),
    ]

    trace = AgentTrace(
        trace_id=run_id,
        agent_name="rcm-audit-agent-v1",
        task="Process and audit insurance claim CLM-2024-00891 through RCM portal",
        steps=steps,
    )

    subsection("Assembled AgentTrace")
    print(f"  trace_id    : {trace.trace_id}")
    print(f"  agent_name  : {trace.agent_name}")
    print(f"  Steps       : {len(trace.steps)}")
    print(f"  Merkle root : {trace.merkle_root}")
    print(f"  Trace id    : {trace.id}")

    # ── PII scrubbing ─────────────────────────────────────────────────────────
    subsection("PII Scrub (SSN, email)")
    scrubber = PrivacyScrubber()
    scrub_result = scrubber.scrub(trace)

    print(f"  Replacements made  : {scrub_result.replacements_count}")
    print(f"  Patterns matched   : {scrub_result.patterns_matched}")

    # Show before/after for the step that had an SSN
    raw_obs = trace.steps[0].observation
    clean_obs = scrub_result.scrubbed_trace.steps[0].observation
    print(f"\n  Step 0 BEFORE scrub: {raw_obs}")
    print(f"  Step 0 AFTER  scrub: {clean_obs}")

    raw_obs2 = trace.steps[2].observation
    clean_obs2 = scrub_result.scrubbed_trace.steps[2].observation
    print(f"\n  Step 2 BEFORE scrub: {raw_obs2}")
    print(f"  Step 2 AFTER  scrub: {clean_obs2}")

    # ── Consistency verification of the scrubbed trace ────────────────────────
    subsection("Consistency Verification (scrubbed trace)")
    verifier = ConsistencyVerifier()
    vresult = verifier.verify(scrub_result.scrubbed_trace)

    print(f"  Verdict         : {vresult.verdict}")
    print(f"  Checks passed   : {vresult.checks_passed}")
    print(f"  Checks failed   : {vresult.checks_failed}")
    print(f"  Verification id : {vresult.id}")

    # ── Tamper detection demonstration ────────────────────────────────────────
    subsection("Tamper Detection Demo")
    tampered_trace = AgentTrace.from_dict(scrub_result.scrubbed_trace.to_dict())
    # Simulate an adversary altering a submission record in the trace.
    tampered_trace.steps[3].action = "oracle:submit claim CLM-2024-00891 [ALTERED-AMOUNT: $12500.00]"

    tampered_result = verifier.verify(tampered_trace)
    print(f"  Tampered trace verdict : {tampered_result.verdict}")
    print(f"  Failed checks          : {tampered_result.checks_failed}")
    assert tampered_result.verdict == "tampered", (
        f"Expected verdict='tampered' after mutation, got '{tampered_result.verdict}'"
    )
    print("  Tamper was correctly detected: YES")

    # ── Final audit summary ───────────────────────────────────────────────────
    subsection("Audit Summary")
    print(f"  Run ID               : {run_id}")
    print(f"  UIFacts recorded     : {len(facts)}")
    print(f"  ActionReceipts filed : {len(receipts)}")
    print(f"  Trace steps          : {len(scrub_result.scrubbed_trace.steps)}")
    print(f"  PII replacements     : {scrub_result.replacements_count}")
    print(f"  Trace integrity      : {vresult.verdict.upper()}")
    all_checks = vresult.checks_passed + vresult.checks_failed
    passed = len(vresult.checks_passed)
    total = len(all_checks)
    print(f"  Checks passed        : {passed}/{total}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the healthcare RCM computer-use audit demo."""
    print("\n" + "#" * 60)
    print("  Healthcare RCM Computer-Use Audit Demo")
    print("  groundcrew + notarize + clickproof")
    print("#" * 60)

    run_id = "rcm-audit-run-2024-00891"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Shared paths inside the temp workspace
        clickproof_db = tmp_path / "clickproof.db"
        groundcrew_db = tmp_path / ".groundcrew" / "receipts.db"
        portal_root = tmp_path / "portal_state"
        portal_root.mkdir()

        # Phase 1 — clickproof: record GUI actions
        with FactStore(str(clickproof_db)) as fact_store:
            ui_facts = phase_clickproof(fact_store, run_id)

        # Phase 2 — groundcrew: Oracle receipts and chain-of-custody report
        receipts = phase_groundcrew(portal_root, groundcrew_db)

        # Phase 3 — notarize: assemble trace, scrub PII, verify integrity
        phase_notarize(run_id, ui_facts, receipts)

    section("DEMO COMPLETE")
    print("  All three tools collaborated to produce a tamper-evident,")
    print("  PII-scrubbed audit trail for the RCM portal session.")
    print()


if __name__ == "__main__":
    main()
