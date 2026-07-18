"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { AnalyzingView } from "../../components/AnalyzingView";
import { ExplainabilityDrawer } from "../../components/ExplainabilityDrawer";
import { decisionAction, fetchAudit, fetchCase, triggerAnalyze } from "../../lib/api";
import type { AuditEvent, CaseDetail, Finding } from "../../lib/types";

// ── Agent display metadata ──────────────────────────────────────────
const AGENT_META: Record<string, { name: string; icon: string }> = {
  financial_analysis:  { name: "Financial Agent",   icon: "📈" },
  collateral_legal:    { name: "Collateral Agent",  icon: "🏛"  },
  policy_compliance:   { name: "Policy Agent",      icon: "📜" },
  legal_review:        { name: "Legal Agent",       icon: "⚖️" },
  cic_check:           { name: "CIC Agent",         icon: "🏦" },
  customer_360:        { name: "Customer Agent",    icon: "👤" },
};

// Display order: real agents first, then placeholders
const AGENT_ORDER = [
  "financial_analysis",
  "collateral_legal",
  "policy_compliance",
  "legal_review",
  "cic_check",
  "customer_360",
];

type Tab = "summary" | "consensus" | "conflicts" | "conditions" | "audit";

const REC_COLOR: Record<string, string> = {
  APPROVE:                 "var(--support)",
  APPROVE_WITH_CONDITIONS: "var(--caution)",
  REFER:                   "var(--caution)",
  NEED_INFO:               "var(--need-data)",
  REJECT:                  "var(--oppose)",
};

const REC_LABEL: Record<string, string> = {
  APPROVE:                 "Phê duyệt",
  APPROVE_WITH_CONDITIONS: "Approve với Điều kiện",
  REFER:                   "Chuyển chuyên gia",
  REJECT:                  "Từ chối",
  NEED_INFO:               "Cần thêm thông tin",
};

function formatVnd(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ VND`;
}

function StanceBadge({ stance }: { stance: string }) {
  return <span className={`badge badge-${stance}`}>{stance}</span>;
}

// ── LTV SVG donut ───────────────────────────────────────────────────
function LtvDonut({ ratio }: { ratio: number | undefined }) {
  if (ratio == null) {
    return (
      <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "8px 0" }}>
        Chưa có dữ liệu LTV — chạy lại phân tích.
      </div>
    );
  }
  const ltvPct  = Math.round((1 / ratio) * 100);
  const r       = 35;
  const circ    = 2 * Math.PI * r;
  const fillLen = Math.min(ltvPct / 100, 1) * circ;
  const color   = ltvPct < 70 ? "var(--support)" : ltvPct < 80 ? "var(--caution)" : "var(--oppose)";

  return (
    <div className="ltv-donut-wrap">
      <svg width="90" height="90" viewBox="0 0 90 90" aria-hidden="true">
        <circle cx="45" cy="45" r={r} fill="none" stroke="var(--border)" strokeWidth="11" />
        <circle
          cx="45" cy="45" r={r} fill="none"
          stroke={color} strokeWidth="11"
          strokeDasharray={`${fillLen} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 45 45)"
        />
      </svg>
      <div className="ltv-center">
        <span className="ltv-pct" style={{ color }}>{ltvPct}%</span>
        <span className="ltv-sub">LTV</span>
      </div>
    </div>
  );
}

// ── DSCR progress bar ───────────────────────────────────────────────
function DscrBar({ dscr }: { dscr: number | undefined }) {
  if (dscr == null) return null;
  const scale        = 2.0;
  const pct          = Math.min((dscr / scale) * 100, 100);
  const thresholdPct = (1.2 / scale) * 100;
  const color        = dscr >= 1.2 ? "var(--support)" : "var(--oppose)";

  return (
    <div className="dscr-section">
      <div className="dscr-header">
        <span className="dscr-label">DSCR (Khả năng trả nợ)</span>
        <span className="dscr-value" style={{ color }}>{dscr.toFixed(2)}</span>
      </div>
      <div className="dscr-track">
        <div className="dscr-fill" style={{ width: `${pct}%`, background: color }} />
        <div className="dscr-threshold" style={{ left: `${thresholdPct}%` }} />
      </div>
      <div className="dscr-note">Ngưỡng tối thiểu: 1.2 · Thang đo: 0 → {scale}</div>
    </div>
  );
}

// ── Workflow rail ───────────────────────────────────────────────────
const WF_LABELS = ["Tiếp nhận NCTD", "Thẩm định", "Rà soát rủi ro", "Phê duyệt"];

function getWfStep(state: string): number {
  if (state === "ANALYZING")               return 1;
  if (state === "READY_FOR_REVIEW")        return 2;
  if (state === "SUBMITTED_FOR_APPROVAL")  return 3;
  if (state === "APPROVED" || state === "REJECTED") return 4;
  return 0;
}

function WorkflowRail({ state }: { state: string }) {
  const active = getWfStep(state);
  return (
    <div className="wf-rail">
      {WF_LABELS.map((label, i) => (
        <div key={i} className="wf-step">
          <div className="wf-node">
            <div className={`wf-dot ${i < active ? "done" : i === active ? "active" : "pending"}`}>
              {i < active ? "✓" : i + 1}
            </div>
            <div className={`wf-label${i === active ? " active" : ""}`}>{label}</div>
          </div>
          {i < WF_LABELS.length - 1 && (
            <div className={`wf-connector${i < active ? " done" : ""}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────
export default function CasePage() {
  const params = useParams();
  const caseId = params.caseId as string;

  const [caseDetail,      setCaseDetail]      = useState<CaseDetail | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [activeTab,       setActiveTab]       = useState<Tab>("summary");
  const [auditEvents,     setAuditEvents]     = useState<AuditEvent[]>([]);
  const [busy,            setBusy]            = useState(false);
  const [log,             setLog]             = useState<string[]>([]);
  const [expandedAgents,  setExpandedAgents]  = useState<Set<string>>(new Set());
  const eventSourceRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try { setCaseDetail(await fetchCase(caseId)); } catch { /* case not seeded yet */ }
  }, [caseId]);

  useEffect(() => {
    refresh();
    const es = new EventSource(`/sse/cases/${caseId}/stream`);
    eventSourceRef.current = es;
    es.addEventListener("progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      setLog(prev => [
        ...prev,
        `${payload.type}${payload.findings_written ? ": " + payload.findings_written.join(", ") : ""}`,
      ]);
      if (payload.type === "job_completed" || payload.type === "job_failed") {
        setBusy(false);
        refresh();
      }
    });
    return () => es.close();
  }, [caseId, refresh]);

  useEffect(() => {
    if (activeTab === "audit") fetchAudit(caseId).then(setAuditEvents);
  }, [activeTab, caseId]);

  const toggleAgent = (agentId: string) => {
    setExpandedAgents(prev => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId); else next.add(agentId);
      return next;
    });
  };

  const runAnalyze = async () => { setBusy(true); setLog([]); await triggerAnalyze(caseId); };

  const doAction = async (action: "accept" | "rerun" | "return" | "override", reason?: string) => {
    try {
      await decisionAction(caseId, action, reason);
      await refresh();
      if (action === "rerun") { setBusy(true); setLog([]); }
    } catch (err) {
      alert(`Không thực hiện được — trạng thái hồ sơ vừa thay đổi, hãy tải lại trang. (${String(err)})`);
      await refresh();
    }
  };

  const doOverride = async () => {
    const reason = prompt("Override khuyến nghị hệ thống — bắt buộc nhập lý do (FR-11):");
    if (!reason) return;
    await doAction("override", reason);
  };

  if (!caseDetail) {
    return (
      <main className="app-shell">
        <p style={{ paddingTop: 32 }}>Đang tải case {caseId}...</p>
      </main>
    );
  }

  // ── Derived values (same logic as before) ──────────────────────────
  const financialRepayment = caseDetail.findings.findLast(f => f.issue_key === "REPAYMENT_CAPACITY");
  const financialCoverage  = caseDetail.findings.findLast(
    f => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "financial_analysis"
  );
  const collateral = caseDetail.findings.findLast(
    f => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "collateral_legal"
  );
  const policy         = caseDetail.findings.findLast(f => f.issue_key === "REVENUE_RECONCILIATION");
  const openConflicts  = caseDetail.conflicts.filter(c => c.status !== "RESOLVED");
  const decision       = caseDetail.decision;

  const isFresh   = caseDetail.findings.length === 0 && !caseDetail.decision;
  const canDecide = caseDetail.state === "READY_FOR_REVIEW";
  const staleTitle = `Chỉ dùng được khi hồ sơ READY_FOR_REVIEW (hiện tại: ${caseDetail.state})`;

  const scores       = decision?.scores ?? [];
  const scoreSum     = scores.reduce((s, x) => s + x.score, 0);
  const scoreMax     = scores.reduce((s, x) => s + x.max, 0);
  const compositePct = scores.length > 0 && scoreMax > 0 ? Math.round((scoreSum / scoreMax) * 100) : null;

  const hardGates     = decision?.hard_gates ?? [];
  const hardGatesPass = hardGates.filter(g => g.status === "PASS").length;

  const requiredDocTypes = caseDetail.required_doc_types;
  const presentDocTypes  = new Set(caseDetail.documents.map(d => d.doc_type));
  const missingDocTypes  = requiredDocTypes.filter(t => !presentDocTypes.has(t));
  const docsCompletePct  = requiredDocTypes.length > 0
    ? Math.round(((requiredDocTypes.length - missingDocTypes.length) / requiredDocTypes.length) * 100)
    : null;

  // coverage_ratio = collateral_value / loan → LTV = 1 / coverage_ratio
  const coverageRatio = collateral?.metrics.coverage_ratio ?? financialCoverage?.metrics.coverage_ratio;
  const ltvPct        = coverageRatio != null && coverageRatio > 0
    ? Math.round((1 / coverageRatio) * 100)
    : null;
  const dscrValue = financialRepayment?.metrics.dscr;

  // Latest finding per agent_id
  const agentFindings = new Map<string, Finding>();
  for (const f of caseDetail.findings) agentFindings.set(f.agent_id, f);

  const findingByDisplayId = (id: string) => caseDetail.findings.find(f => f.display_id === id);
  const openFinding        = (id: string) => { const f = findingByDisplayId(id); if (f) setSelectedFinding(f); };

  const recColor = decision ? (REC_COLOR[decision.recommendation] ?? "var(--text)") : "var(--text-muted)";
  const recLabel = decision ? (REC_LABEL[decision.recommendation] ?? decision.recommendation) : "—";

  // Stance → tone class helper
  const stanceTone = (s: string | undefined) =>
    s === "SUPPORT" ? "ok" : s === "CAUTION" ? "warn" : s === "OPPOSE" ? "bad" : "pending";

  return (
    <main className="app-shell">

      {/* ── Case Hero ─────────────────────────────────────────────── */}
      <div className="case-hero">
        <div className="case-hero-top">
          <Link href="/" className="btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }}>
            ← Quay lại
          </Link>
          <span className="case-breadcrumb">
            SHBExpert AI · <Link href="/" style={{ color: "var(--color-navy-300)" }}>Applications</Link>
            {" "}›{" "}SME{" "}›{" "}{caseDetail.customer_id}
          </span>
        </div>

        <div className="case-hero-main">
          <div>
            <div className="case-id-mono">{caseDetail.case_id}</div>
            <div className="case-customer">{caseDetail.customer_id}</div>
            <div className="case-meta-row">
              <span>{caseDetail.product}</span>
              <span className="dot-sep">·</span>
              <span>Kỳ hạn {(caseDetail.requested_facility.tenor_months as number) ?? "—"} tháng</span>
              <span className="dot-sep">·</span>
              <span>{formatVnd(caseDetail.requested_facility.amount_vnd as number)}</span>
            </div>
          </div>

          <div className="case-hero-badges">
            {decision && (
              <span
                className="rec-status-pill"
                style={{
                  background: `${recColor}22`,
                  border: `1px solid ${recColor}55`,
                  color: recColor,
                }}
              >
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: recColor, display: "inline-block", marginRight: 6, flexShrink: 0 }} />
                {recLabel}
              </span>
            )}
            <span className="state-chip">{caseDetail.state}</span>
          </div>
        </div>

        <WorkflowRail state={caseDetail.state} />
      </div>

      {/* ── Busy / Fresh states ────────────────────────────────────── */}
      {busy ? (
        <AnalyzingView caseId={caseId} onComplete={() => setBusy(false)} />
      ) : isFresh ? (
        <div className="card" style={{ maxWidth: 480, margin: "60px auto", textAlign: "center", padding: 32 }}>
          <p style={{ marginBottom: 16 }}>Hồ sơ đã có đủ dữ liệu — chưa chạy phân tích AI.</p>
          <button className="btn btn-primary" onClick={runAnalyze}>Bắt đầu phân tích</button>
        </div>
      ) : (
        <>
          {/* Toolbar */}
          <div className="page-toolbar">
            <button
              className="btn btn-primary"
              onClick={() => doAction("rerun")}
              disabled={busy || !canDecide}
              title={canDecide ? undefined : staleTitle}
            >
              {busy ? "Đang phân tích..." : "⟳ Chạy lại phân tích"}
            </button>
            {log.length > 0 && (
              <span className="muted" style={{ fontSize: 12 }}>{log[log.length - 1]}</span>
            )}
          </div>

          {/* Tab bar */}
          <div className="tab-bar">
            {(["summary", "consensus", "conflicts", "conditions", "audit"] as Tab[]).map(tab => (
              <button
                key={tab}
                className={`tab${activeTab === tab ? " active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab === "summary"   && "Executive Summary"}
                {tab === "consensus" && "Agent Consensus"}
                {tab === "conflicts" && (
                  <>Conflicts{openConflicts.length > 0 && <span className="tab-badge">{openConflicts.length}</span>}</>
                )}
                {tab === "conditions" && (
                  <>
                    Conditions
                    {decision && decision.conditions_precedent.length > 0 && (
                      <span className="tab-badge" style={{ background: "var(--caution-bg)", color: "var(--caution)" }}>
                        {decision.conditions_precedent.length}
                      </span>
                    )}
                  </>
                )}
                {tab === "audit" && "Audit Trail"}
              </button>
            ))}
          </div>

          {/* ══════════════════════════════════════════════════════════
              TAB: Executive Summary
          ══════════════════════════════════════════════════════════ */}
          {activeTab === "summary" && (
            <div className="summary-tab">

              {/* Section 2 — AI Brief */}
              {decision ? (
                <section className="card exec-brief">
                  <div className="exec-brief-header">
                    <div className="section-eyebrow">✦ AI Brief — Tóm tắt quyết định</div>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {missingDocTypes.length > 0 && `📋 Thiếu ${missingDocTypes.length} tài liệu`}
                    </span>
                  </div>

                  <div className="exec-brief-grid">
                    {/* Recommendation */}
                    <div className="brief-rec">
                      <div className="brief-rec-label">Khuyến nghị AI</div>
                      <div className="brief-rec-value" style={{ color: recColor }}>{recLabel}</div>
                      {compositePct != null && (
                        <div className="brief-score" style={{ color: recColor }}>{compositePct}%</div>
                      )}
                    </div>

                    {/* Meters */}
                    <div className="brief-meters">
                      {compositePct != null && (
                        <div className="meter-row">
                          <div className="meter-header">
                            <span className="meter-label">Điểm tổng hợp</span>
                            <span className="meter-val">{compositePct}%</span>
                          </div>
                          <div className="meter-track">
                            <div className="meter-fill" style={{ width: `${compositePct}%`, background: recColor }} />
                          </div>
                        </div>
                      )}
                      {hardGates.length > 0 && (
                        <div className="meter-row">
                          <div className="meter-header">
                            <span className="meter-label">Hard gates</span>
                            <span className="meter-val">{hardGatesPass}/{hardGates.length} PASS</span>
                          </div>
                          <div className="meter-track">
                            <div
                              className="meter-fill"
                              style={{
                                width: `${Math.round((hardGatesPass / hardGates.length) * 100)}%`,
                                background: hardGatesPass === hardGates.length ? "var(--support)" : "var(--oppose)",
                              }}
                            />
                          </div>
                        </div>
                      )}
                      {docsCompletePct != null && (
                        <div className="meter-row">
                          <div className="meter-header">
                            <span className="meter-label">Hồ sơ đầy đủ</span>
                            <span className="meter-val">{docsCompletePct}%</span>
                          </div>
                          <div className="meter-track">
                            <div
                              className="meter-fill"
                              style={{
                                width: `${docsCompletePct}%`,
                                background: docsCompletePct === 100 ? "var(--support)" : "var(--navy-500)",
                              }}
                            />
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Strengths */}
                    <div className="brief-col">
                      <div className="brief-col-title" style={{ color: "var(--support)" }}>✓ Điểm mạnh</div>
                      {decision.strengths.length === 0 ? (
                        <p className="muted" style={{ fontSize: 13 }}>—</p>
                      ) : decision.strengths.slice(0, 3).map(id => {
                        const f = findingByDisplayId(id);
                        return (
                          <div
                            key={id}
                            className="brief-item"
                            onClick={() => f && setSelectedFinding(f)}
                            style={{ cursor: f ? "pointer" : "default" }}
                          >
                            <span style={{ color: "var(--support)", flexShrink: 0 }}>✓</span>
                            <span>{f?.claim ?? id}</span>
                          </div>
                        );
                      })}
                    </div>

                    {/* Risks */}
                    <div className="brief-col">
                      <div className="brief-col-title" style={{ color: "var(--oppose)" }}>⚠ Rủi ro chú ý</div>
                      {decision.risks.length === 0 ? (
                        <p className="muted" style={{ fontSize: 13 }}>—</p>
                      ) : decision.risks.slice(0, 3).map(id => {
                        const f = findingByDisplayId(id);
                        return (
                          <div
                            key={id}
                            className="brief-item"
                            onClick={() => f && setSelectedFinding(f)}
                            style={{ cursor: f ? "pointer" : "default" }}
                          >
                            <span style={{ color: "var(--caution)", flexShrink: 0 }}>⚠</span>
                            <span>{f?.claim ?? id}</span>
                          </div>
                        );
                      })}
                    </div>

                    {/* Missing docs */}
                    <div className="brief-col">
                      {missingDocTypes.length > 0 ? (
                        <>
                          <div className="brief-col-title" style={{ color: "var(--text-muted)" }}>📋 Thiếu hồ sơ</div>
                          {missingDocTypes.slice(0, 3).map(t => (
                            <div key={t} className="brief-item">
                              <span style={{ color: "var(--oppose)", flexShrink: 0 }}>✗</span>
                              <span style={{ fontSize: 12 }}>{t.replace(/_/g, " ")}</span>
                            </div>
                          ))}
                          {missingDocTypes.length > 3 && (
                            <span className="muted" style={{ fontSize: 12 }}>+{missingDocTypes.length - 3} nữa</span>
                          )}
                        </>
                      ) : (
                        <div className="brief-col-title" style={{ color: "var(--support)" }}>✓ Đủ hồ sơ</div>
                      )}
                    </div>
                  </div>

                  {decision.dissent.length > 0 && (
                    <div className="exec-brief-footer">
                      <span style={{ color: "var(--caution)", fontWeight: 700 }}>⚠ Dissent (chưa thống nhất):</span>
                      {decision.dissent.map(id => (
                        <a key={id} onClick={() => openFinding(id)} style={{ cursor: "pointer", marginLeft: 8, color: "var(--accent)", fontSize: 13 }}>{id}</a>
                      ))}
                    </div>
                  )}
                </section>
              ) : (
                <div className="card" style={{ padding: 16, marginBottom: 16 }}>
                  <p className="muted">Chưa có kết quả phân tích. Nhấn "Chạy lại phân tích" để bắt đầu.</p>
                </div>
              )}

              {/* Sections 3 + 4 — Two columns */}
              <div className="detail-cols">

                {/* Credit Proposal */}
                <div className="card proposal-card">
                  <div className="card-title" style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", marginBottom: 0 }}>
                    📋 Chi tiết đề xuất cấp tín dụng
                  </div>

                  <div className="proposal-section-label">Thông số tài chính</div>

                  <div className="proposal-row-item">
                    <span className="pkey">Hạn mức đề nghị</span>
                    <span className="pval">{formatVnd(caseDetail.requested_facility.amount_vnd as number)}</span>
                  </div>
                  <div className="proposal-row-item">
                    <span className="pkey">Hạn mức AI đề xuất</span>
                    <span className="pval" style={{ color: decision ? "var(--navy-700)" : "var(--text-muted)" }}>
                      {formatVnd(decision?.recommended_amount_vnd)}
                    </span>
                  </div>
                  <div className="proposal-row-item">
                    <span className="pkey">Kỳ hạn</span>
                    <span className="pval">
                      {(caseDetail.requested_facility.tenor_months as number) ?? "—"} tháng
                      {decision?.recommended_tenor_months != null && decision.recommended_tenor_months !== (caseDetail.requested_facility.tenor_months as number) && (
                        <span style={{ color: "var(--caution)", fontWeight: 400, fontSize: 11, marginLeft: 6 }}>
                          (AI: {decision.recommended_tenor_months}th)
                        </span>
                      )}
                    </span>
                  </div>
                  {(caseDetail.requested_facility.interest_rate_pct as number | null) != null && (
                    <div className="proposal-row-item">
                      <span className="pkey">Lãi suất</span>
                      <span className="pval">{String(caseDetail.requested_facility.interest_rate_pct)}% / năm</span>
                    </div>
                  )}
                  {caseDetail.requested_facility.purpose != null && (
                    <div className="proposal-row-item">
                      <span className="pkey">Mục đích vốn</span>
                      <span className="pval" style={{ fontSize: 12 }}>{String(caseDetail.requested_facility.purpose)}</span>
                    </div>
                  )}

                  {/* LTV donut */}
                  <div className="ltv-section">
                    <LtvDonut ratio={coverageRatio} />
                    <div className="ltv-details">
                      {coverageRatio != null && (
                        <div className="ltv-row">
                          <span className="lk">Tỷ lệ phủ TSĐB</span>
                          <span className="lv">{Math.round(coverageRatio * 100)}%</span>
                        </div>
                      )}
                      {ltvPct != null && (
                        <div className="ltv-row">
                          <span className="lk">LTV ước tính</span>
                          <span className="lv" style={{ color: ltvPct >= 80 ? "var(--oppose)" : ltvPct >= 70 ? "var(--caution)" : "var(--support)" }}>
                            {ltvPct}%
                          </span>
                        </div>
                      )}
                      <div className="ltv-row">
                        <span className="lk">Ngưỡng chính sách</span>
                        <span className="lv" style={{ color: "var(--oppose)" }}>≤ 80%</span>
                      </div>
                      {openConflicts.some(c => c.issue_key === "COLLATERAL_COVERAGE") && (
                        <div style={{ fontSize: 11.5, color: "var(--oppose)", fontWeight: 700, marginTop: 2 }}>
                          ⚠ Xung đột FA vs Collateral Agent
                        </div>
                      )}
                      {coverageRatio == null && (
                        <span className="muted" style={{ fontSize: 12 }}>Chưa có dữ liệu — chạy lại phân tích.</span>
                      )}
                    </div>
                  </div>

                  {/* DSCR bar */}
                  <DscrBar dscr={dscrValue} />

                  {/* Hard gates chips */}
                  {hardGates.length > 0 && (
                    <div className="hard-gates-row">
                      {hardGates.map(g => (
                        <span
                          key={g.gate_id}
                          className={`gate-chip ${g.status === "PASS" ? "pass" : g.status === "REVIEW" ? "review" : "fail"}`}
                          title={g.reason ?? undefined}
                        >
                          {g.gate_id}: {g.status === "PASS" ? "✓" : g.status === "REVIEW" ? "~" : "✗"}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Policy version footer */}
                  {decision?.policy_version && (
                    <div className="muted" style={{ fontSize: 11, padding: "8px 16px", borderTop: "1px solid var(--border)" }}>
                      policy_version={decision.policy_version} · matrix={decision.decision_matrix_version}
                    </div>
                  )}
                </div>

                {/* Risk & Compliance panel */}
                <div className="risk-panel">
                  <div className="card-title risk-panel-header">🛡 Rủi ro &amp; Tuân thủ</div>

                  {/* Financial health */}
                  {financialRepayment ? (
                    <div
                      className={`risk-item ${stanceTone(financialRepayment.stance)}`}
                      onClick={() => setSelectedFinding(financialRepayment)}
                      style={{ cursor: "pointer" }}
                    >
                      <div className={`risk-icon ${stanceTone(financialRepayment.stance)}`}>📊</div>
                      <div className="risk-body">
                        <div className="risk-name">
                          Sức khỏe tài chính
                          <StanceBadge stance={financialRepayment.stance} />
                        </div>
                        <div className="risk-finding">{financialRepayment.claim}</div>
                      </div>
                    </div>
                  ) : (
                    <div className="risk-item pending">
                      <div className="risk-icon pending">📊</div>
                      <div className="risk-body">
                        <div className="risk-name">Sức khỏe tài chính <span className="badge badge-NEED_DATA">NEED DATA</span></div>
                        <div className="risk-finding">Chưa có finding từ Financial Agent.</div>
                      </div>
                    </div>
                  )}

                  {/* Collateral */}
                  {(collateral || financialCoverage) ? (() => {
                    const f = collateral ?? financialCoverage!;
                    const t = stanceTone(f.stance);
                    return (
                      <div className={`risk-item ${t}`} onClick={() => setSelectedFinding(f)} style={{ cursor: "pointer" }}>
                        <div className={`risk-icon ${t}`}>🏠</div>
                        <div className="risk-body">
                          <div className="risk-name">
                            Tài sản bảo đảm (LTV)
                            <StanceBadge stance={f.stance} />
                            {openConflicts.some(c => c.issue_key === "COLLATERAL_COVERAGE") && (
                              <span style={{ fontSize: 10, color: "var(--oppose)", fontWeight: 700 }}>conflict</span>
                            )}
                          </div>
                          <div className="risk-finding">{f.claim}</div>
                        </div>
                      </div>
                    );
                  })() : (
                    <div className="risk-item pending">
                      <div className="risk-icon pending">🏠</div>
                      <div className="risk-body">
                        <div className="risk-name">Tài sản bảo đảm <span className="badge badge-NEED_DATA">NEED DATA</span></div>
                        <div className="risk-finding">Chưa có dữ liệu định lượng.</div>
                      </div>
                    </div>
                  )}

                  {/* Policy compliance */}
                  {policy ? (
                    <div
                      className={`risk-item ${stanceTone(policy.stance)}`}
                      onClick={() => setSelectedFinding(policy)}
                      style={{ cursor: "pointer" }}
                    >
                      <div className={`risk-icon ${stanceTone(policy.stance)}`}>📜</div>
                      <div className="risk-body">
                        <div className="risk-name">
                          Tuân thủ chính sách
                          <StanceBadge stance={policy.stance} />
                        </div>
                        <div className="risk-finding">{policy.claim}</div>
                      </div>
                    </div>
                  ) : (
                    <div className="risk-item pending">
                      <div className="risk-icon pending">📜</div>
                      <div className="risk-body">
                        <div className="risk-name">Tuân thủ chính sách <span className="badge badge-NEED_DATA">NEED DATA</span></div>
                        <div className="risk-finding">Chưa có finding từ Policy Agent.</div>
                      </div>
                    </div>
                  )}

                  {/* Agent conflicts */}
                  <div className={`risk-item ${openConflicts.length > 0 ? "warn" : "ok"}`}>
                    <div className={`risk-icon ${openConflicts.length > 0 ? "warn" : "ok"}`}>⚔</div>
                    <div className="risk-body">
                      <div className="risk-name">
                        Xung đột agent
                        <span className={`badge ${openConflicts.length > 0 ? "badge-CAUTION" : "badge-SUPPORT"}`}>
                          {openConflicts.length > 0 ? `${openConflicts.length} mở` : "Sạch"}
                        </span>
                      </div>
                      <div className="risk-finding">
                        {openConflicts.length > 0
                          ? openConflicts.map(c => c.issue_key.replace(/_/g, " ")).join(", ")
                          : "Tất cả agents đồng thuận."}
                      </div>
                    </div>
                  </div>

                  {/* Documents */}
                  <div className={`risk-item ${missingDocTypes.length === 0 ? "ok" : "bad"}`}>
                    <div className={`risk-icon ${missingDocTypes.length === 0 ? "ok" : "bad"}`}>📄</div>
                    <div className="risk-body">
                      <div className="risk-name">
                        Hồ sơ chứng từ
                        <span className={`badge ${missingDocTypes.length === 0 ? "badge-SUPPORT" : "badge-OPPOSE"}`}>
                          {missingDocTypes.length === 0 ? "Đầy đủ" : `Thiếu ${missingDocTypes.length}`}
                        </span>
                      </div>
                      {docsCompletePct != null && (
                        <div className="risk-finding">
                          {requiredDocTypes.length - missingDocTypes.length}/{requiredDocTypes.length} loại đã có
                          {missingDocTypes.length > 0 && (
                            <span style={{ color: "var(--oppose)" }}> · Thiếu: {missingDocTypes.join(", ")}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Extra findings not covered by named cards above */}
                  {caseDetail.findings
                    .filter(f => !["REPAYMENT_CAPACITY", "COLLATERAL_COVERAGE", "REVENUE_RECONCILIATION"].includes(f.issue_key))
                    .filter((f, i, arr) => arr.findIndex(x => x.issue_key === f.issue_key && x.agent_id === f.agent_id) === i)
                    .slice(0, 4)
                    .map(f => (
                      <div
                        key={f.display_id}
                        className={`risk-item ${stanceTone(f.stance)}`}
                        onClick={() => setSelectedFinding(f)}
                        style={{ cursor: "pointer" }}
                      >
                        <div className={`risk-icon ${stanceTone(f.stance)}`}>🔍</div>
                        <div className="risk-body">
                          <div className="risk-name">
                            {f.issue_key.replace(/_/g, " ")}
                            <StanceBadge stance={f.stance} />
                          </div>
                          <div className="risk-finding">{f.claim}</div>
                        </div>
                      </div>
                    ))
                  }
                </div>
              </div>

              {/* Section 5 — Agent matrix */}
              <section className="card agent-matrix-card">
                <div className="agent-matrix-header">
                  <span className="card-title" style={{ margin: 0 }}>🤖 AI Multi-Agent Analysis</span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {agentFindings.size} agent(s) có kết quả · {openConflicts.length} xung đột
                  </span>
                </div>

                <div style={{ overflowX: "auto" }}>
                  <table className="agent-table">
                    <thead>
                      <tr>
                        <th style={{ width: 220 }}>Agent</th>
                        <th style={{ width: 130 }}>Confidence</th>
                        <th>Finding chính</th>
                        <th style={{ width: 130 }}>Stance</th>
                        <th style={{ width: 50 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {AGENT_ORDER.map(agentId => {
                        const f        = agentFindings.get(agentId);
                        const meta     = AGENT_META[agentId] ?? { name: agentId, icon: "🤖" };
                        const expanded = expandedAgents.has(agentId);
                        const tone     = stanceTone(f?.stance);
                        const confPct  = f != null ? Math.round(f.confidence * 100) : null;

                        return (
                          <Fragment key={agentId}>
                            <tr className="agent-row" onClick={() => f && toggleAgent(agentId)}>
                              <td>
                                <div className="agent-name-cell">
                                  <div className={`agent-dot ${tone}`}>{meta.icon}</div>
                                  <div>
                                    <div className="agent-name">{meta.name}</div>
                                    <div className="agent-id">{agentId}</div>
                                  </div>
                                </div>
                              </td>
                              <td className="conf-cell">
                                {confPct != null ? (
                                  <div className="conf-row">
                                    <span className="conf-num">{confPct}%</span>
                                    <div className="conf-bar">
                                      <div className={`conf-fill ${tone}`} style={{ width: `${confPct}%` }} />
                                    </div>
                                  </div>
                                ) : <span className="muted">—</span>}
                              </td>
                              <td>
                                {f ? (
                                  <div className="agent-finding">{f.claim}</div>
                                ) : (
                                  <span className="muted" style={{ fontSize: 12 }}>Agent chưa triển khai — sắp có</span>
                                )}
                              </td>
                              <td>
                                {f
                                  ? <StanceBadge stance={f.stance} />
                                  : <span className="badge badge-NEED_DATA">NEED DATA</span>
                                }
                              </td>
                              <td>
                                {f && (
                                  <button
                                    className="expand-btn"
                                    onClick={e => { e.stopPropagation(); toggleAgent(agentId); }}
                                  >
                                    {expanded ? "▲" : "▼"}
                                  </button>
                                )}
                              </td>
                            </tr>

                            {f && expanded && (
                              <tr className="agent-detail-row">
                                <td colSpan={5}>
                                  <div className="agent-detail-inner">
                                    <div className="detail-section">
                                      <div className="detail-label">Issue</div>
                                      <div>{f.issue_key.replace(/_/g, " ")} · severity {f.severity} · v{f.version} · {f.display_id}</div>
                                    </div>
                                    {f.citations.length > 0 && (
                                      <div className="detail-section">
                                        <div className="detail-label">Citations</div>
                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                                          {f.citations.map((c, i) => (
                                            <span key={i} className="citation-pill" title={c.text}>
                                              {c.source_id}{c.section ? ` §${c.section}` : ""}
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                    {f.recommended_action && (
                                      <div className="detail-section">
                                        <div className="detail-label">Recommended action</div>
                                        <div>{f.recommended_action}</div>
                                      </div>
                                    )}
                                    <button
                                      className="btn"
                                      style={{ marginTop: 8, fontSize: 12, padding: "5px 12px" }}
                                      onClick={() => setSelectedFinding(f)}
                                    >
                                      Xem đầy đủ (Evidence + Citations) →
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Section 6 — Decision Support */}
              {decision && (
                <section className="decision-support">
                  <div className="decision-support-hd">
                    <div>
                      <div className="decision-eyebrow">✦ Decision Support — Hỗ trợ quyết định cuối</div>
                      <div className="decision-rec-text" style={{ color: recColor }}>{recLabel}</div>
                    </div>
                    {compositePct != null && (
                      <div className="decision-score">
                        <div className="decision-score-num" style={{ color: recColor }}>{compositePct}%</div>
                        <div className="decision-score-label">Điểm tổng hợp</div>
                      </div>
                    )}
                  </div>

                  <div className="decision-body-cols">
                    {/* Evidence */}
                    <div>
                      <div className="decision-col-label">→ Bằng chứng hỗ trợ</div>
                      {decision.strengths.length === 0 ? (
                        <p className="muted" style={{ fontSize: 13 }}>—</p>
                      ) : decision.strengths.map(id => {
                        const f = findingByDisplayId(id);
                        return (
                          <div key={id} className="evidence-item" onClick={() => f && setSelectedFinding(f)}>
                            <span style={{ color: "var(--accent)", flexShrink: 0 }}>→</span>
                            <span>{f?.claim ?? id}</span>
                          </div>
                        );
                      })}
                    </div>

                    {/* Conditions */}
                    <div>
                      <div className="decision-col-label">⚠ Điều kiện tiên quyết</div>
                      {decision.conditions_precedent.length === 0 ? (
                        <p className="muted" style={{ fontSize: 13 }}>Không có điều kiện.</p>
                      ) : decision.conditions_precedent.map((c, i) => (
                        <div key={i} className="condition-item">
                          <span className="cond-num">{i + 1}</span>
                          <span>{c}</span>
                        </div>
                      ))}
                      {missingDocTypes.length > 0 && (
                        <div style={{ marginTop: 10, padding: "9px 12px", background: "var(--caution-bg)", borderRadius: "var(--radius)", fontSize: 12 }}>
                          <span style={{ fontWeight: 700, color: "var(--caution)" }}>📋 Bổ sung trước giải ngân:</span>{" "}
                          {missingDocTypes.join(", ")}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="decision-actions">
                      <button
                        className="btn btn-primary"
                        onClick={() => doAction("accept")}
                        disabled={!canDecide}
                        title={canDecide ? undefined : staleTitle}
                      >
                        ✓ Accept
                      </button>
                      <button
                        className="btn"
                        onClick={doOverride}
                        disabled={!canDecide}
                        title={canDecide ? undefined : staleTitle}
                      >
                        ↑ Override
                      </button>
                      <button className="btn" disabled style={{ opacity: 0.5 }}>
                        📋 Yêu cầu tài liệu
                      </button>
                      <button className="btn" disabled style={{ opacity: 0.5 }}>
                        📄 Xuất Credit Memo
                      </button>
                    </div>
                  </div>
                </section>
              )}

            </div>
          )}

          {/* ══════════════════════════════════════════════════════════
              TAB: Agent Consensus
          ══════════════════════════════════════════════════════════ */}
          {activeTab === "consensus" && (
            <section style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
              {caseDetail.findings.length === 0 && (
                <p className="muted">Chưa có findings. Chạy phân tích để xem kết quả.</p>
              )}
              {caseDetail.findings.map(f => (
                <div
                  key={f.display_id}
                  className="card card-clickable"
                  onClick={() => setSelectedFinding(f)}
                  style={{ padding: 14 }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div>
                      <span style={{ fontWeight: 700 }}>{AGENT_META[f.agent_id]?.name ?? f.agent_id}</span>
                      <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
                        · {f.issue_key.replace(/_/g, " ")}
                      </span>
                    </div>
                    <StanceBadge stance={f.stance} />
                  </div>
                  <p style={{ fontSize: 13, margin: "0 0 6px" }}>{f.claim}</p>
                  <div className="muted" style={{ fontSize: 12 }}>
                    severity {f.severity} · confidence {Math.round(f.confidence * 100)}% · {f.display_id}
                    {f.citations.length > 0 && ` · ${f.citations.length} citation(s)`}
                  </div>
                </div>
              ))}
            </section>
          )}

          {/* ══════════════════════════════════════════════════════════
              TAB: Conflicts
          ══════════════════════════════════════════════════════════ */}
          {activeTab === "conflicts" && (
            <section className="card" style={{ marginBottom: 20 }}>
              {caseDetail.conflicts.length === 0 ? (
                <p className="muted" style={{ padding: 16 }}>Không có xung đột.</p>
              ) : caseDetail.conflicts.map(c => (
                <div key={c.conflict_id} style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
                    <span className={`badge ${c.status === "UNRESOLVED" ? "badge-OPPOSE" : c.status === "OPEN" ? "badge-CAUTION" : "badge-SUPPORT"}`}>
                      {c.status}
                    </span>
                    <strong>{c.issue_key.replace(/_/g, " ")}</strong>
                    <span className="muted" style={{ fontSize: 12 }}>Round {c.round}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
                    findings: {c.source_findings.join(", ")}
                  </div>
                  {c.targeted_questions.map((q, i) => (
                    <div
                      key={i}
                      style={{ fontSize: 12, marginLeft: 12, marginTop: 4, padding: "6px 10px", background: "var(--caution-bg)", borderRadius: 4, color: "var(--caution)" }}
                    >
                      → {q.to_agent}: &quot;{q.question}&quot;
                    </div>
                  ))}
                </div>
              ))}
            </section>
          )}

          {/* ══════════════════════════════════════════════════════════
              TAB: Conditions
          ══════════════════════════════════════════════════════════ */}
          {activeTab === "conditions" && (
            <section className="card" style={{ marginBottom: 20 }}>
              {!decision || decision.conditions_precedent.length === 0 ? (
                <p className="muted" style={{ padding: 16 }}>Không có điều kiện tiên quyết.</p>
              ) : (
                <>
                  {decision.conditions_precedent.map((c, i) => (
                    <div
                      key={i}
                      style={{ display: "flex", gap: 12, padding: "12px 16px", borderBottom: "1px solid var(--border)", alignItems: "flex-start" }}
                    >
                      <span className="cond-num">{i + 1}</span>
                      <span style={{ fontSize: 13 }}>{c}</span>
                    </div>
                  ))}
                  {missingDocTypes.length > 0 && (
                    <div style={{ padding: "12px 16px", background: "var(--caution-bg)" }}>
                      <div style={{ fontWeight: 700, color: "var(--caution)", marginBottom: 6, fontSize: 12 }}>
                        📋 Tài liệu cần bổ sung trước giải ngân
                      </div>
                      {missingDocTypes.map(t => (
                        <div key={t} style={{ fontSize: 13, marginBottom: 4 }}>· {t.replace(/_/g, " ")}</div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {/* ══════════════════════════════════════════════════════════
              TAB: Audit Trail
          ══════════════════════════════════════════════════════════ */}
          {activeTab === "audit" && (
            <section className="card" style={{ marginBottom: 20, overflow: "hidden" }}>
              <div className="section-title" style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                Audit trail — timeline bất biến
              </div>
              <div style={{ overflowX: "auto" }}>
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
                    {auditEvents.map(e => (
                      <tr key={e.seq}>
                        <td>{e.seq}</td>
                        <td>{e.event_type}</td>
                        <td>{e.actor.type}:{e.actor.id}</td>
                        <td>{new Date(e.timestamp).toLocaleString("vi-VN")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

        </>
      )}

      {selectedFinding && (
        <ExplainabilityDrawer
          caseId={caseId}
          finding={selectedFinding}
          onClose={() => setSelectedFinding(null)}
        />
      )}
    </main>
  );
}
