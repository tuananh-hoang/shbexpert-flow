# AI Credit Intelligence Dashboard

### SHB Expert -- Credit Officer Dashboard (Lo-Fi Design Proposal)

## Vision

Instead of another ChatGPT interface, the product should feel like
**Power BI + Palantir + Perplexity**.

The dashboard visualizes **what the AI computes**, not simply **what the
AI says**.

Each dashboard widget corresponds to one expert agent. Clicking any
widget opens an explainability panel showing: - Agent reasoning -
Confidence - Supporting evidence - PDF citations - Highlighted document
snippets

The Credit Officer always remains the final decision maker.

------------------------------------------------------------------------

# User Flow

``` text
Application Queue
        │
        ▼
Select Credit Application
        │
        ▼
AI Credit Intelligence Dashboard
        │
        ├── Click Widget
        │       │
        │       ▼
        │  Agent Explainability Panel
        │
        ▼
Approve / Reject / Request Documents / Escalate
```

------------------------------------------------------------------------

# Lo-Fi Dashboard

``` text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ SHB Expert AI                                                                 CO Dashboard           │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Applications > SME > ABC Manufacturing Ltd                                    Status: Pending Review │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Executive Summary                                                                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Requested      Recommended      Confidence      Risk Score      Documents       Conflicts            │
│ 8.0B VND       7.0B VND         91%             82/100          94% Complete    2 Issues            │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────┬─────────────────────────────┬──────────────────────────────────────────┐
│ Financial Health            │ Revenue Trend              │ AI Recommendation                        │
│ Revenue ▲18%               │      /‾\                   │ APPROVE WITH CONDITIONS                  │
│ Net Margin 12.4%           │     /  \                  │ Confidence: 91%                          │
│ DSCR 1.72                  │ ___/    \____             │ ✓ Strong repayment capacity              │
│ Debt Ratio 0.46            │ 2023 2024 2025            │ ✓ Strong collateral                      │
│ Current Ratio 1.81         │                           │ ⚠ Customer concentration                 │
│ [Financial Agent]          │ [Financial Agent]         │ ⚠ Revenue mismatch                       │
└─────────────────────────────┴─────────────────────────────┴──────────────────────────────────────────┘

┌─────────────────────────────┬─────────────────────────────┬──────────────────────────────────────────┐
│ Cashflow                    │ Customer Concentration      │ Collateral                               │
│ ↑ Incoming                  │ Buyer A 42%                │ Coverage: 136%                           │
│ ↓ Outgoing                  │ Buyer B 18%                │ Haircut: 20%                             │
│ [Transaction Agent]         │ [Customer Agent]           │ [Collateral Agent]                       │
└─────────────────────────────┴─────────────────────────────┴──────────────────────────────────────────┘

┌─────────────────────────────┬─────────────────────────────┬──────────────────────────────────────────┐
│ Policy Compliance           │ Document Completeness       │ Industry Outlook                         │
│ ✓ AML                       │ 92% Complete               │ Medium Risk                              │
│ ✓ KYC                       │ Missing: Tax Report        │ Margin 12% vs Industry 9%                │
│ ✓ SME                       │ [Intake Agent]             │ [Industry Agent]                         │
│ ⚠ Collateral Review         │                            │                                          │
└─────────────────────────────┴─────────────────────────────┴──────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Agent Consensus                                                                                    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Financial ✓ | Collateral ✓ | Customer ⚠ | Policy ✓ | Industry ✓                                    │
│ Final Coordinator → APPROVE WITH CONDITIONS                                                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [ Approve ]   [ Reject ]   [ Request More Documents ]   [ Escalate ]                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# Dashboard Modules

## 1. Executive Summary

**Widgets** - Requested Loan Amount - AI Recommended Amount - Approval
Confidence - Overall Risk Score - Document Completeness - Agent Conflict
Count

------------------------------------------------------------------------

## 2. Financial Health (Financial Agent)

**Metrics** - Revenue Growth - Net Profit Margin - Current Ratio - Debt
Ratio - DSCR

**Charts** - Revenue Trend - Profit Trend

------------------------------------------------------------------------

## 3. Cashflow Analytics (Transaction Agent)

**Charts** - Monthly Cash In vs Cash Out - Operating Cashflow Trend -
Largest Transactions - Top Counterparties

Purpose: \> Can the customer consistently repay?

------------------------------------------------------------------------

## 4. Customer Concentration (Customer Agent)

**Charts** - Revenue by Customer (Pie) - Top Buyers (Bar)

Highlight: \> Buyer A contributes 42% of total revenue.

------------------------------------------------------------------------

## 5. Collateral (Collateral Agent)

**Widgets** - Coverage Gauge - Haircut - Eligible Value - Expiry Date

------------------------------------------------------------------------

## 6. Customer 360

-   Years with SHB
-   Products Owned
-   Existing Loans
-   Late Payments
-   RM Notes

------------------------------------------------------------------------

## 7. Credit History

-   Outstanding Debt
-   Credit Lines
-   Past Due Accounts
-   Credit Timeline

------------------------------------------------------------------------

## 8. Industry Analysis

-   Industry Risk
-   Growth
-   ESG
-   Customer vs Industry Benchmark

------------------------------------------------------------------------

## 9. Policy Compliance

Checklist: - AML - KYC - SME Eligibility - Lending Policy - Collateral
Policy

------------------------------------------------------------------------

## 10. Document Completeness

-   Completeness %
-   Missing Documents
-   Document Quality

------------------------------------------------------------------------

## 11. Agent Consensus

  Agent        Decision
  ------------ ------------
  Financial    ✅ Approve
  Collateral   ✅ Approve
  Customer     ⚠ Review
  Policy       ✅ Approve
  Industry     ✅ Approve

Coordinator synthesizes all agent outputs.

------------------------------------------------------------------------

## 12. Final Recommendation

Display: - Recommendation - Confidence - Strengths - Risks - Suggested
Conditions

------------------------------------------------------------------------

# Widget Interaction

Every widget is clickable.

The side panel should display: - Agent Name - Summary - Confidence -
Reasoning - Evidence - PDF Citations - Highlighted Snippets - "Explain
this metric"

------------------------------------------------------------------------

# Demo Narrative

1.  Open application queue.
2.  Select an application.
3.  AI has already completed parallel agent analysis.
4.  Dashboard presents synthesized insights.
5.  Click widgets to inspect explainability.
6.  Credit Officer makes the final decision.

------------------------------------------------------------------------

# Core Message

The UI should naturally communicate:

-   Every widget is produced by a specialized expert agent.
-   Every metric is backed by traceable evidence.
-   The Credit Officer remains in the loop while AI accelerates
    analysis.
