"""One-off smoke test for Phase 1 — shared/state.py write path. Run inside
the api container (has shared/, DATABASE_URL pointed at shbapp). Safe to
delete once Phase 2+ add real pytest coverage.
"""
from shared.db import get_session
from shared.models import Case
from shared.schemas import Actor, FindingIn
from shared.state import (
    EvidenceRequiredError,
    InvalidTransitionError,
    transition_state,
    write_finding,
)

CASE_ID = "C06"

with get_session() as session:
    # Clean slate if a prior run left the seed case behind.
    existing = session.get(Case, CASE_ID)
    if existing is None:
        session.add(
            Case(
                case_id=CASE_ID,
                customer_id="CUST-ANPHU",
                product="SME_WC",
                requested_facility={"amount_vnd": 8_000_000_000, "tenor_months": 12},
                owner="rm1",
                state="DRAFT",
                version=1,
            )
        )
        session.flush()
        print(f"seeded case {CASE_ID}")
    else:
        print(f"case {CASE_ID} already exists, state={existing.state}")

with get_session() as session:
    # 1. Financial Agent writes a fresh finding (v1, new lineage).
    f1 = write_finding(
        session,
        FindingIn(
            case_id=CASE_ID,
            agent_id="financial_analysis",
            issue_key="COLLATERAL_COVERAGE",
            claim_type="INFERENCE",
            claim="Coverage adequate based on declared collateral value.",
            stance="SUPPORT",
            severity="MEDIUM",
            evidence_ids=["EV-BCTC-2025-P12"],
            confidence=0.88,
        ),
        versions={"formula_version": "FIN-0.3-MOCK"},
    )
    print("wrote", f1.display_id, f1.stance)

    # 2. Collateral Agent revises the SAME lineage after a targeted question
    #    (Phase 4 will drive this automatically; here we just prove the
    #    version-append mechanics work).
    f2 = write_finding(
        session,
        FindingIn(
            case_id=CASE_ID,
            agent_id="financial_analysis",
            issue_key="COLLATERAL_COVERAGE",
            claim_type="INFERENCE",
            claim="Coverage adequate at 1.08x after excluding overdue AR.",
            stance="SUPPORT",
            severity="MEDIUM",
            evidence_ids=["EV-BCTC-2025-P12", "EV-AR-AGING"],
            confidence=0.9,
            change_reason="Recomputed excluding overdue receivables per Collateral Agent question.",
        ),
        finding_key=f1.finding_key,
    )
    print("wrote", f2.display_id, "change_reason:", f2.change_reason)
    assert f2.version == 2

    # 3. NFR-01 guard: a HIGH/CRITICAL finding with no evidence must be rejected.
    try:
        write_finding(
            session,
            FindingIn(
                case_id=CASE_ID,
                agent_id="policy_compliance",
                issue_key="KYC_MATCH",
                claim_type="INFERENCE",
                claim="Customer matches AML watchlist entry.",
                stance="OPPOSE",
                severity="CRITICAL",
                evidence_ids=[],
                confidence=0.5,
            ),
        )
        raise AssertionError("expected EvidenceRequiredError, none raised")
    except EvidenceRequiredError as exc:
        print("EvidenceRequiredError correctly raised:", exc)

    # 4. Valid state transition.
    case = transition_state(
        session, case_id=CASE_ID, new_state="INTAKE_VALIDATION", actor=Actor(type="SYSTEM", id="seed_script")
    )
    print("case state now:", case.state, "version:", case.version)

    # 5. Invalid transition must be rejected (DRAFT-skipping straight to
    #    READY_FOR_REVIEW isn't in the allowed graph from INTAKE_VALIDATION's
    #    current position — ANALYZING is required first).
    try:
        transition_state(
            session, case_id=CASE_ID, new_state="READY_FOR_REVIEW", actor=Actor(type="SYSTEM", id="seed_script")
        )
        raise AssertionError("expected InvalidTransitionError, none raised")
    except InvalidTransitionError as exc:
        print("InvalidTransitionError correctly raised:", exc)

print("\nALL STATE-LAYER SMOKE TESTS PASSED")
