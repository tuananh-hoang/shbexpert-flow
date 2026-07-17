# Explainable AI Interaction Design
## SHB Expert - Credit Officer Dashboard UX

## Goal

Every dashboard widget is drillable.

Interaction hierarchy:

```
Dashboard
    ↓
Agent Summary
    ↓
Evidence & Citations
```

This combines:
- RAG
- Multi-agent reasoning
- Explainable AI
- Human-in-the-loop

---

# Screen 1 — Dashboard Overview

```text
Dashboard
├─ KPI Cards
├─ Financial Health
├─ Revenue Trend
├─ Customer
├─ Collateral
├─ Policy
└─ Recommendation

User clicks: Revenue Growth
```

Purpose:
- 5-second overview
- No long AI explanations
- Every card represents one expert agent.

---

# Screen 2 — Agent Explainability Drawer

```text
Financial Agent

Revenue Growth: +18%
Confidence: 96%

Summary
Revenue has increased steadily for three consecutive years.

Business Impact
✓ Positive repayment capacity
✓ Stable operations

Calculation
2024 Revenue: 9.5B
2025 Revenue: 11.2B
Growth: 18%

Evidence
Annual Report 2025
Page 12

[Open Evidence]
```

Purpose:
- Explain why
- Show confidence
- Show calculation
- Link to evidence

---

# Screen 3 — Evidence Viewer

```text
Annual_Report_2025.pdf
Page 12

Income Statement

Revenue
11,243,000,000 VND

Citation

Financial Agent used this value
to compute Revenue Growth.

Confidence: 96%
```

Purpose:
- Highlight exact supporting evidence
- Build trust
- Enable auditability

---

# Standard Interaction Pattern

```
Dashboard
      ↓
Agent Summary
      ↓
Evidence
```

Every widget follows this exact UX.

---

# Decision Trace (Recommended)

```text
Revenue Growth

▲ 18%

Source
Financial Agent

↓

Input
Financial Statements

↓

Tool
Financial Ratio Calculator

↓

Evidence
Annual Report 2025
Page 12

↓

Impact
+2.5 points to Overall Risk Score
```

This exposes a decision trace instead of chain-of-thought.

---

# Design Principles

1. Dashboard first.
2. Every widget is clickable.
3. Every recommendation is traceable.
4. Evidence links to original documents.
5. The Credit Officer remains the final decision-maker.

---

# Core Message

Data → Expert Agent → Calculation → Evidence → Decision

This demonstrates:
- RAG
- Multi-agent collaboration
- Explainable AI
- Human-in-the-loop governance
