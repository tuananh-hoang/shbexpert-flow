"use client";

/**
 * AI Credit Intelligence Dashboard — per
 * AI_Credit_Intelligence_Dashboard_Design.md and
 * Explainable_AI_Interaction_Design.md: a widget grid where each card is
 * produced by one expert agent, every widget is clickable, and clicking
 * drills into Agent Summary -> Evidence (ExplainabilityDrawer).
 *
 * Data flows entirely through `/api/*` (web/app/lib/api.ts), which
 * next.config.mjs rewrites to `api` — this page never touches
 * postgres/redis directly (overview.md §4).
 *
 * Phase 8 (frontend-flow plan) moved this from the root route (`/`) to
 * `/cases/[caseId]` — the root route is now the Application Queue
 * (web/app/page.tsx). `caseId` comes from the dynamic route segment
 * instead of a hardcoded constant, so any seeded case (C06/C07/C08...)
 * opens at its own URL.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { AnalyzingView } from "../../components/AnalyzingView";
import { ExplainabilityDrawer } from "../../components/ExplainabilityDrawer";
import { decisionAction, fetchAudit, fetchCase, triggerAnalyze } from "../../lib/api";
import type { AuditEvent, CaseDetail, Finding } from "../../lib/types";

const RECOMMENDATION_COLOR: Record<string, string> = {
  APPROVE: "var(--support)",
  APPROVE_WITH_CONDITIONS: "var(--caution)",
  REFER: "var(--caution)",
  NEED_INFO: "var(--need-data)",
  REJECT: "var(--oppose)",
};

type Tab = "summary" | "consensus" | "conflicts" | "conditions" | "audit";

function StanceBadge({ stance }: { stance: string }) {
  return <span className={`badge badge-${stance}`}>{stance}</span>;
}

// 6-card KPI strip (AI_Credit_Intelligence_Dashboard_Design.md's proposed
// Confidence/Risk Score pair collapsed into ONE real "Điểm tổng hợp" — see
// plan doc: two overlapping fake-looking numbers vs one real one). `value`
// is pre-formatted by the caller so this stays a dumb presentational card;
// callers pass "—" (never 0%/NaN) when the underlying data doesn't exist
// yet (AS-01 — a case with no score should never look artificially bad).
function KpiCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
    </div>
  );
}

// Real gauge (recharts RadialBarChart) fed by Finding.metrics.coverage_ratio
// — the collateral_legal agent's stricter check (bank's own valuation +
// expiry rule), not financial_analysis's naive one. `ratio` is undefined
// whenever that finding hasn't been (re)computed since the metrics column
// was added — old rows default to {} (see migration 0005), so the gauge
// honestly falls back to a "chưa có dữ liệu" state instead of drawing 0%.
function CoverageGauge({ ratio }: { ratio: number | undefined }) {
  if (ratio == null) {
    return <p className="muted" style={{ fontSize: 13 }}>Chưa có dữ liệu định lượng — chạy lại phân tích để tính.</p>;
  }
  const pct = Math.round(ratio * 100);
  const domainMax = Math.max(150, pct + 20);
  const color = pct >= 100 ? "var(--support)" : "var(--oppose)";
  return (
    <div style={{ width: "100%", height: 110, position: "relative" }}>
      <ResponsiveContainer>
        <RadialBarChart
          cx="50%"
          cy="100%"
          innerRadius="70%"
          outerRadius="100%"
          barSize={14}
          startAngle={180}
          endAngle={0}
          data={[{ value: pct, fill: color }]}
        >
          <PolarAngleAxis type="number" domain={[0, domainMax]} angleAxisId={0} tick={false} />
          <RadialBar background dataKey="value" cornerRadius={8} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div style={{ position: "absolute", bottom: 2, left: 0, right: 0, textAlign: "center", fontSize: 20, fontWeight: 700, color }}>
        {pct}%
      </div>
    </div>
  );
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="progress-track">
      <div className="progress-fill" style={{ width: `${pct}%`, background: pct >= 100 ? "var(--support)" : "var(--caution)" }} />
    </div>
  );
}

function Widget({
  title,
  agent,
  onClick,
  children,
}: {
  title: string;
  agent: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className={`card${onClick ? " card-clickable" : ""}`} onClick={onClick}>
      <div className="card-title">{title}</div>
      {children}
      <div className="card-agent-label">[{agent}]</div>
    </div>
  );
}

// Widget slots from AI_Credit_Intelligence_Dashboard_Design.md that have
// no corresponding agent built yet (Customer 360, Industry, Transaction,
// Intake, CIC) — shown in the same grid position so the layout matches
// the design doc's widget set, but honestly labeled "Sắp có" rather than
// fabricating numbers no agent actually computed.
function PlaceholderWidget({ title, agent }: { title: string; agent: string }) {
  return (
    <div className="card card-placeholder">
      <div className="card-title">{title}</div>
      <span className="placeholder-badge">Sắp có</span>
      <p style={{ fontSize: 13, marginTop: 8 }}>Agent chưa triển khai — chưa có dữ liệu thật.</p>
      <div className="card-agent-label">[{agent}]</div>
    </div>
  );
}

function formatVnd(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ VND`;
}

export default function CasePage() {
  const params = useParams();
  const caseId = params.caseId as string;

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCaseDetail(await fetchCase(caseId));
    } catch {
      // case not seeded yet — dashboard shows the loading state
    }
  }, [caseId]);

  useEffect(() => {
    refresh();
    // Deliberately NOT /api/* — see web/app/sse/cases/[caseId]/stream/route.ts
    // for why the SSE endpoint is served from its own path.
    const es = new EventSource(`/sse/cases/${caseId}/stream`);
    eventSourceRef.current = es;
    es.addEventListener("progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      setLog((prev) => [...prev, `${payload.type}${payload.findings_written ? ": " + payload.findings_written.join(", ") : ""}`]);
      if (payload.type === "job_completed" || payload.type === "job_failed") {
        setBusy(false);
        refresh();
      }
    });
    return () => es.close();
  }, [caseId, refresh]);

  useEffect(() => {
    if (activeTab === "audit") {
      fetchAudit(caseId).then(setAuditEvents);
    }
  }, [activeTab, caseId]);

  const findingByDisplayId = (id: string) => caseDetail?.findings.find((f) => f.display_id === id);

  const runAnalyze = async () => {
    setBusy(true);
    setLog([]);
    await triggerAnalyze(caseId);
  };

  const doAction = async (action: "accept" | "rerun" | "return" | "override", reason?: string) => {
    try {
      await decisionAction(caseId, action, reason);
      await refresh();
      if (action === "rerun") {
        setBusy(true);
        setLog([]);
      }
    } catch (err) {
      // Buttons that call this are disabled whenever `canDecide` is false,
      // so this only fires on a genuine race (state changed between page
      // load and click) — rare enough that a refresh + plain message is
      // enough, no need for a full error-boundary treatment.
      alert(`Không thực hiện được — trạng thái hồ sơ vừa thay đổi, hãy tải lại trang. (${String(err)})`);
      await refresh();
    }
  };

  const doOverride = async () => {
    const reason = prompt("Override khuyến nghị hệ thống — bắt buộc nhập lý do (FR-11):");
    if (!reason) return;
    await doAction("override", reason);
  };

  const openEvidenceFor = (issueKey: string) => {
    const finding = caseDetail?.findings.find((f) => f.issue_key === issueKey);
    if (finding) setSelectedFinding(finding);
  };

  if (!caseDetail) {
    return (
      <main className="app-shell">
        <p style={{ paddingTop: 32 }}>Đang tải case {caseId}...</p>
      </main>
    );
  }

  // findLast, not find: api/app/routers/cases.py::_latest_findings sorts
  // ascending by created_at, and a full "Chạy lại phân tích" rerun starts a
  // BRAND NEW finding_key lineage per agent rather than versioning the old
  // one (versioning is only for the targeted-question challenge loop) — so
  // after a rerun there can be two lineages for the same issue_key+agent_id
  // sitting in this array, and the most recent one is always last.
  const financialRepayment = caseDetail.findings.findLast((f) => f.issue_key === "REPAYMENT_CAPACITY");
  const financialCoverage = caseDetail.findings.findLast(
    (f) => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "financial_analysis"
  );
  const collateral = caseDetail.findings.findLast(
    (f) => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "collateral_legal"
  );
  const policy = caseDetail.findings.findLast((f) => f.issue_key === "REVENUE_RECONCILIATION");
  const openConflicts = caseDetail.conflicts.filter((c) => c.status !== "RESOLVED");
  const decision = caseDetail.decision;
  // No findings/decision yet and nothing currently running — the case is
  // sitting in the Application Queue's "chờ phân tích" state (frontend-
  // flow plan Phase 2). `busy` (set true by runAnalyze / rerun) drives
  // the AnalyzingView instead once a job is actually in flight.
  const isFresh = caseDetail.findings.length === 0 && !caseDetail.decision;
  // Accept/Override only ever succeed from READY_FOR_REVIEW (the only
  // state ALLOWED_TRANSITIONS lets move to SUBMITTED_FOR_APPROVAL —
  // shared/state.py). Rerun is the same story via the "rerun" CO_ACTION
  // (transitions to ANALYZING first, only valid from READY_FOR_REVIEW in
  // this system's simplified flow). Gating on this up front means a
  // stale action reads as "disabled, here's why" instead of a cryptic
  // alert() after a 409.
  const canDecide = caseDetail.state === "READY_FOR_REVIEW";
  const staleTitle = `Chỉ dùng được khi hồ sơ đang ở trạng thái READY_FOR_REVIEW (hiện tại: ${caseDetail.state})`;

  // Điểm tổng hợp (KPI): Σscore/Σmax across decision.scores. Deliberately
  // "—" (not 0%) when scores is empty — the hard-gate short-circuit path
  // (worker/app/graph/decision.py::_check_hard_gates) leaves scores=[] on
  // purpose when G1/G4 fail early (AS-01: "hồ sơ thiếu nghị quyết không
  // nên có điểm số").
  const scores = decision?.scores ?? [];
  const scoreSum = scores.reduce((s, x) => s + x.score, 0);
  const scoreMax = scores.reduce((s, x) => s + x.max, 0);
  const compositePct = scores.length > 0 && scoreMax > 0 ? Math.round((scoreSum / scoreMax) * 100) : null;

  const hardGates = decision?.hard_gates ?? [];
  const hardGatesPass = hardGates.filter((g) => g.status === "PASS").length;

  const requiredDocTypes = caseDetail.required_doc_types;
  const presentDocTypes = new Set(caseDetail.documents.map((d) => d.doc_type));
  const missingDocTypes = requiredDocTypes.filter((t) => !presentDocTypes.has(t));
  const docsCompletePct =
    requiredDocTypes.length > 0
      ? Math.round(((requiredDocTypes.length - missingDocTypes.length) / requiredDocTypes.length) * 100)
      : null;

  return (
    <main className="app-shell">
      {/* Hero strip — identity only; KPI numbers moved to the strip below
          (a separate white section, not squeezed onto the navy background). */}
      <div className="hero-strip">
        <Link href="/" className="btn-ghost" style={{ marginBottom: 10 }}>
          ← Quay lại danh sách
        </Link>
        <div className="breadcrumb">
          SHBExpert AI · <Link href="/" style={{ color: "inherit" }}>Applications</Link> &gt; SME &gt; {caseDetail.customer_id}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1>Case {caseDetail.case_id}</h1>
            <div className="hero-subtitle">
              {caseDetail.product} · kỳ hạn {caseDetail.requested_facility.tenor_months as number ?? "—"} tháng · {formatVnd(caseDetail.requested_facility.amount_vnd as number)}
            </div>
          </div>
          <span className="status-pill">{caseDetail.state}</span>
        </div>
      </div>

      {busy ? (
        <AnalyzingView caseId={caseId} onComplete={() => setBusy(false)} />
      ) : isFresh ? (
        <div className="card" style={{ maxWidth: 480, margin: "60px auto", textAlign: "center" }}>
          <p style={{ marginBottom: 16 }}>Hồ sơ đã có đủ dữ liệu — chưa chạy phân tích AI.</p>
          <button className="btn btn-primary" onClick={runAnalyze}>
            Bắt đầu phân tích
          </button>
        </div>
      ) : (
        <>
      {/* KPI strip — 6 white cards, separate from the navy hero-strip.
          "Điểm tổng hợp" and "Hard gates" are two distinct real numbers
          (not the Confidence/Risk Score pair from the original proposal,
          which would have shown overlapping/fabricated-looking figures). */}
      <section className="kpi-strip">
        <KpiCard label="Requested" value={formatVnd(caseDetail.requested_facility.amount_vnd as number)} />
        <KpiCard label="Recommended" value={formatVnd(decision?.recommended_amount_vnd)} />
        <KpiCard
          label="Điểm tổng hợp"
          value={compositePct != null ? `${compositePct}%` : "—"}
          tone={decision ? RECOMMENDATION_COLOR[decision.recommendation] : undefined}
        />
        <KpiCard label="Hard gates" value={hardGates.length > 0 ? `${hardGatesPass}/${hardGates.length} PASS` : "—"} />
        <KpiCard label="Documents" value={docsCompletePct != null ? `${docsCompletePct}%` : "—"} />
        <KpiCard label="Conflicts" value={`${openConflicts.length} mở`} tone={openConflicts.length > 0 ? "var(--oppose)" : undefined} />
      </section>

      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
        <button
          className="btn btn-primary"
          onClick={() => doAction("rerun")}
          disabled={busy || !canDecide}
          title={canDecide ? undefined : staleTitle}
        >
          {busy ? "Đang phân tích..." : "Chạy lại phân tích"}
        </button>
        {log.length > 0 && <span className="muted" style={{ marginLeft: 12, fontSize: 12 }}>{log[log.length - 1]}</span>}
      </div>

      {/* Tab bar */}
      <div className="tab-bar">
        <button className={`tab${activeTab === "summary" ? " active" : ""}`} onClick={() => setActiveTab("summary")}>
          Executive Summary
        </button>
        <button className={`tab${activeTab === "consensus" ? " active" : ""}`} onClick={() => setActiveTab("consensus")}>
          Agent Consensus
        </button>
        <button className={`tab${activeTab === "conflicts" ? " active" : ""}`} onClick={() => setActiveTab("conflicts")}>
          Conflicts
          {openConflicts.length > 0 && <span className="tab-badge">{openConflicts.length}</span>}
        </button>
        <button className={`tab${activeTab === "conditions" ? " active" : ""}`} onClick={() => setActiveTab("conditions")}>
          Conditions
          {decision && decision.conditions_precedent.length > 0 && (
            <span className="tab-badge" style={{ background: "var(--need-data-bg)", color: "var(--need-data)" }}>
              {decision.conditions_precedent.length}
            </span>
          )}
        </button>
        <button className={`tab${activeTab === "audit" ? " active" : ""}`} onClick={() => setActiveTab("audit")}>
          Audit Trail
        </button>
      </div>

      {activeTab === "summary" && (
        <>
          <section className="widget-grid" style={{ marginBottom: 20 }}>
            <Widget title="Financial Health" agent="Financial Agent" onClick={() => openEvidenceFor("REPAYMENT_CAPACITY")}>
              {financialRepayment ? (
                <>
                  <StanceBadge stance={financialRepayment.stance} />
                  <p style={{ fontSize: 13, marginTop: 8 }}>{financialRepayment.claim}</p>
                </>
              ) : (
                <p className="muted">Chưa có finding</p>
              )}
            </Widget>

            <Widget title="Collateral Coverage" agent="Financial + Collateral Agent">
              {/* Gauge driven by the stricter collateral_legal finding's
                  metrics.coverage_ratio (bank's own valuation + expiry
                  rule) — financial_analysis's naive coverage stays as text
                  below it, same as before, since the two can legitimately
                  disagree (that's what feeds the conflict detector). */}
              <CoverageGauge ratio={collateral?.metrics.coverage_ratio} />
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {financialCoverage && (
                  <div onClick={() => setSelectedFinding(financialCoverage)} style={{ cursor: "pointer" }}>
                    <StanceBadge stance={financialCoverage.stance} /> <span style={{ fontSize: 12 }}>Financial (thô)</span>
                    <p style={{ fontSize: 13, margin: "4px 0" }}>{financialCoverage.claim}</p>
                  </div>
                )}
                {collateral && (
                  <div onClick={() => setSelectedFinding(collateral)} style={{ cursor: "pointer", borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                    <StanceBadge stance={collateral.stance} /> <span style={{ fontSize: 12 }}>Collateral (chặt chẽ, v{collateral.version})</span>
                    <p style={{ fontSize: 13, margin: "4px 0" }}>{collateral.claim}</p>
                  </div>
                )}
                {openConflicts.some((c) => c.issue_key === "COLLATERAL_COVERAGE") && (
                  <div style={{ fontSize: 12, color: "var(--oppose)", fontWeight: 700 }}>⚠ Mâu thuẫn chưa giải quyết</div>
                )}
              </div>
            </Widget>

            <Widget title="Policy Compliance" agent="Policy & Compliance Agent" onClick={() => openEvidenceFor("REVENUE_RECONCILIATION")}>
              {policy ? (
                <>
                  <StanceBadge stance={policy.stance} />
                  <p style={{ fontSize: 13, marginTop: 8 }}>{policy.claim}</p>
                </>
              ) : (
                <p className="muted">Chưa có finding</p>
              )}
            </Widget>

            {/* Widget slots from AI_Credit_Intelligence_Dashboard_Design.md
                with no agent built yet — honest "Sắp có" placeholders,
                same grid position, no fabricated numbers. */}
            <PlaceholderWidget title="Revenue Trend" agent="Financial Agent" />
            <PlaceholderWidget title="Cashflow Analytics" agent="Transaction Agent" />
            <PlaceholderWidget title="Customer Concentration" agent="Customer Agent" />
            <PlaceholderWidget title="Customer 360" agent="Customer Agent" />
            <PlaceholderWidget title="Credit History (CIC)" agent="CIC Agent" />
            <PlaceholderWidget title="Industry Outlook" agent="Industry Agent" />

            <Widget title="Document Completeness" agent="Intake">
              {requiredDocTypes.length === 0 ? (
                <p className="muted">—</p>
              ) : (
                <>
                  <ProgressBar pct={docsCompletePct ?? 0} />
                  <p style={{ fontSize: 13, marginTop: 8 }}>
                    {requiredDocTypes.length - missingDocTypes.length}/{requiredDocTypes.length} loại chứng từ bắt buộc đã có
                  </p>
                  {missingDocTypes.length > 0 && (
                    <p style={{ fontSize: 12, color: "var(--oppose)" }}>Thiếu: {missingDocTypes.join(", ")}</p>
                  )}
                </>
              )}
            </Widget>
          </section>

          {decision && (
            // Full-width, light-green background — this is the page's final
            // verdict card, so it gets the "support" tone regardless of the
            // actual recommendation color (matches the approved redesign:
            // "nền xanh nhạt (--support-bg)"). Conditions moved to its own
            // tab (real data, decision.conditions_precedent, deserved more
            // room than one truncated inline line). No "View Details" CTA —
            // this page already IS the detail view, nothing further to link to.
            <section className="card recommendation-card" style={{ marginBottom: 20 }}>
              <div className="card-title">
                Khuyến nghị: <span style={{ color: RECOMMENDATION_COLOR[decision.recommendation] }}>{decision.recommendation}</span>
              </div>
              <div style={{ fontSize: 13, marginBottom: 14 }}>
                <strong>Hard gates:</strong>{" "}
                {decision.hard_gates.map((g) => (
                  <span key={g.gate_id} style={{ marginRight: 8 }}>
                    {g.gate_id}={g.status === "PASS" ? "✓" : "✗"}
                  </span>
                ))}
              </div>
              <div className="recommendation-columns">
                <div>
                  <div className="recommendation-col-title" style={{ color: "var(--support)" }}>
                    Điểm mạnh
                  </div>
                  {decision.strengths.length === 0 ? (
                    <p className="muted" style={{ fontSize: 13 }}>—</p>
                  ) : (
                    decision.strengths.map((id) => (
                      <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", display: "block", fontSize: 13, marginBottom: 4, color: "var(--accent)" }}>
                        {id}
                      </a>
                    ))
                  )}
                </div>
                <div>
                  <div className="recommendation-col-title" style={{ color: "var(--oppose)" }}>
                    Rủi ro
                  </div>
                  {decision.risks.length === 0 ? (
                    <p className="muted" style={{ fontSize: 13 }}>—</p>
                  ) : (
                    decision.risks.map((id) => (
                      <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", display: "block", fontSize: 13, marginBottom: 4, color: "var(--accent)" }}>
                        {id}
                      </a>
                    ))
                  )}
                </div>
              </div>
              {decision.dissent.length > 0 && (
                <div style={{ fontSize: 13, color: "var(--caution)", marginTop: 12 }}>
                  <strong>Dissent (chưa thống nhất):</strong>{" "}
                  {decision.dissent.map((id) => (
                    <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", marginRight: 8, color: "var(--accent)" }}>
                      {id}
                    </a>
                  ))}
                </div>
              )}
              {decision.policy_version && (
                <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                  policy_version={decision.policy_version} · decision_matrix_version={decision.decision_matrix_version}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {activeTab === "consensus" && (
        <section style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
          {caseDetail.findings.map((f) => (
            <div key={f.display_id} className="card card-clickable" onClick={() => setSelectedFinding(f)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div className="card-title" style={{ marginBottom: 0 }}>
                  {f.agent_id} <span className="muted" style={{ fontWeight: 400 }}>· {f.issue_key.replace(/_/g, " ")}</span>
                </div>
                <StanceBadge stance={f.stance} />
              </div>
              <p style={{ fontSize: 13, margin: "8px 0" }}>{f.claim}</p>
              <div className="muted" style={{ fontSize: 12 }}>
                severity {f.severity} · confidence {Math.round(f.confidence * 100)}% · {f.display_id}
                {f.citations.length > 0 && ` · ${f.citations.length} citation${f.citations.length > 1 ? "s" : ""}`}
              </div>
            </div>
          ))}
        </section>
      )}

      {activeTab === "conflicts" && (
        <section className="card" style={{ marginBottom: 20 }}>
          {caseDetail.conflicts.length === 0 ? (
            <p className="muted">Không có xung đột.</p>
          ) : (
            caseDetail.conflicts.map((c) => (
              <div key={c.conflict_id} style={{ marginBottom: 10 }}>
                <div>
                  <strong>{c.issue_key}</strong> — round {c.round} —{" "}
                  <span style={{ color: c.status === "UNRESOLVED" ? "var(--oppose)" : "var(--support)", fontWeight: 700 }}>{c.status}</span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>findings: {c.source_findings.join(", ")}</div>
                {c.targeted_questions.map((q, i) => (
                  <div key={i} style={{ fontSize: 12, marginLeft: 12, marginTop: 4 }}>
                    → {q.to_agent}: &quot;{q.question}&quot;
                  </div>
                ))}
              </div>
            ))
          )}
        </section>
      )}

      {activeTab === "conditions" && (
        <section className="card">
          {!decision || decision.conditions_precedent.length === 0 ? (
            <p className="muted">Không có điều kiện tiên quyết.</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {decision.conditions_precedent.map((c, i) => (
                <li key={i} style={{ fontSize: 13, marginBottom: 8 }}>
                  {c}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "audit" && (
        <section className="card">
          <div className="section-title">Audit trail — timeline bất biến</div>
          <table className="audit-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Event</th>
                <th>Actor</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((e) => (
                <tr key={e.seq}>
                  <td>{e.seq}</td>
                  <td>{e.event_type}</td>
                  <td>{e.actor.type}:{e.actor.id}</td>
                  <td>{new Date(e.timestamp).toLocaleString("vi-VN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Human-in-the-loop actions — case-level, visible regardless of tab.
          Return to RM / Rerun removed: Return to RM parks the case in
          NEED_INFO, a state this simplified flow (no OCR/intake step) has
          no path back out of — a dead end with no RM inbox screen to
          receive it anyway. Rerun's logic (transition to ANALYZING, then
          enqueue) is preserved — it's what the toolbar's "Chạy lại phân
          tích" button now calls, just without a separate duplicate button. */}
      <div className="action-bar">
        <button className="btn" onClick={() => doAction("accept")} disabled={!canDecide} title={canDecide ? undefined : staleTitle}>
          Accept
        </button>
        <button className="btn" onClick={doOverride} disabled={!canDecide} title={canDecide ? undefined : staleTitle}>
          Override
        </button>
      </div>
        </>
      )}

      {selectedFinding && (
        <ExplainabilityDrawer caseId={caseId} finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
      )}
    </main>
  );
}
