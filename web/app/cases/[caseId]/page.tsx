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

type Tab = "overview" | "council" | "conflicts" | "audit";

function StanceBadge({ stance }: { stance: string }) {
  return <span className={`badge badge-${stance}`}>{stance}</span>;
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
  const [activeTab, setActiveTab] = useState<Tab>("overview");
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
      alert(String(err));
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

  const financialRepayment = caseDetail.findings.find((f) => f.issue_key === "REPAYMENT_CAPACITY");
  const financialCoverage = caseDetail.findings.find(
    (f) => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "financial_analysis"
  );
  const collateral = caseDetail.findings.find(
    (f) => f.issue_key === "COLLATERAL_COVERAGE" && f.agent_id === "collateral_legal"
  );
  const policy = caseDetail.findings.find((f) => f.issue_key === "REVENUE_RECONCILIATION");
  const openConflicts = caseDetail.conflicts.filter((c) => c.status !== "RESOLVED");
  const decision = caseDetail.decision;
  // No findings/decision yet and nothing currently running — the case is
  // sitting in the Application Queue's "chờ phân tích" state (frontend-
  // flow plan Phase 2). `busy` (set true by runAnalyze / rerun) drives
  // the AnalyzingView instead once a job is actually in flight.
  const isFresh = caseDetail.findings.length === 0 && !caseDetail.decision;

  return (
    <main className="app-shell">
      {/* Hero strip */}
      <div className="hero-strip">
        <div className="breadcrumb">
          SHBExpert AI · <Link href="/" style={{ color: "inherit" }}>Applications</Link> &gt; SME &gt; {caseDetail.customer_id}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <h1>Case {caseDetail.case_id}</h1>
          <span className="status-pill">{caseDetail.state}</span>
        </div>
        <div className="hero-metrics">
          <div>
            <div className="hero-metric-label">Requested</div>
            <div className="hero-metric-value">{formatVnd(caseDetail.requested_facility.amount_vnd as number)}</div>
          </div>
          <div>
            <div className="hero-metric-label">Recommended</div>
            <div className="hero-metric-value">{formatVnd(decision?.recommended_amount_vnd)}</div>
          </div>
          <div>
            <div className="hero-metric-label">Recommendation</div>
            <div className="hero-metric-value" style={{ color: decision ? RECOMMENDATION_COLOR[decision.recommendation] : undefined }}>
              {decision?.recommendation ?? "Chưa chạy"}
            </div>
          </div>
          <div>
            <div className="hero-metric-label">Documents</div>
            <div className="hero-metric-value">{caseDetail.findings.length > 0 ? "Đã trích xuất" : "—"}</div>
          </div>
          <div>
            <div className="hero-metric-label">Conflicts</div>
            <div className="hero-metric-value">{caseDetail.conflicts.length} Issues</div>
          </div>
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
      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
        <button className="btn btn-primary" onClick={runAnalyze} disabled={busy}>
          {busy ? "Đang phân tích..." : "Chạy lại phân tích"}
        </button>
        {log.length > 0 && <span className="muted" style={{ marginLeft: 12, fontSize: 12 }}>{log[log.length - 1]}</span>}
      </div>

      {/* Tab bar */}
      <div className="tab-bar">
        <button className={`tab${activeTab === "overview" ? " active" : ""}`} onClick={() => setActiveTab("overview")}>
          Overview
        </button>
        <button className={`tab${activeTab === "council" ? " active" : ""}`} onClick={() => setActiveTab("council")}>
          Expert Council
        </button>
        <button className={`tab${activeTab === "conflicts" ? " active" : ""}`} onClick={() => setActiveTab("conflicts")}>
          Conflicts
          {openConflicts.length > 0 && <span className="tab-badge">{openConflicts.length}</span>}
        </button>
        <button className={`tab${activeTab === "audit" ? " active" : ""}`} onClick={() => setActiveTab("audit")}>
          Audit
        </button>
      </div>

      {activeTab === "overview" && (
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
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
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
            <PlaceholderWidget title="Document Completeness" agent="Intake Agent" />
          </section>

          {decision && (
            <section className="card" style={{ marginBottom: 20 }}>
              <div className="card-title">
                Recommendation: <span style={{ color: RECOMMENDATION_COLOR[decision.recommendation] }}>{decision.recommendation}</span>
              </div>
              <div style={{ fontSize: 13, marginBottom: 8 }}>
                <strong>Hard gates:</strong>{" "}
                {decision.hard_gates.map((g) => (
                  <span key={g.gate_id} style={{ marginRight: 8 }}>
                    {g.gate_id}={g.status === "PASS" ? "✓" : "✗"}
                  </span>
                ))}
              </div>
              {decision.strengths.length > 0 && (
                <div style={{ fontSize: 13 }}>
                  <strong>Strengths:</strong>{" "}
                  {decision.strengths.map((id) => (
                    <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", marginRight: 8, color: "var(--accent)" }}>
                      {id}
                    </a>
                  ))}
                </div>
              )}
              {decision.risks.length > 0 && (
                <div style={{ fontSize: 13 }}>
                  <strong>Risks:</strong>{" "}
                  {decision.risks.map((id) => (
                    <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", marginRight: 8, color: "var(--accent)" }}>
                      {id}
                    </a>
                  ))}
                </div>
              )}
              {decision.dissent.length > 0 && (
                <div style={{ fontSize: 13, color: "var(--caution)" }}>
                  <strong>Dissent (chưa thống nhất):</strong>{" "}
                  {decision.dissent.map((id) => (
                    <a key={id} onClick={() => findingByDisplayId(id) && setSelectedFinding(findingByDisplayId(id)!)} style={{ cursor: "pointer", marginRight: 8, color: "var(--accent)" }}>
                      {id}
                    </a>
                  ))}
                </div>
              )}
              {decision.conditions_precedent.length > 0 && (
                <div style={{ fontSize: 13 }}>
                  <strong>Conditions:</strong> {decision.conditions_precedent.join("; ")}
                </div>
              )}
              {decision.policy_version && (
                <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                  policy_version={decision.policy_version} · decision_matrix_version={decision.decision_matrix_version}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {activeTab === "council" && (
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

      {/* Human-in-the-loop actions — case-level, visible regardless of tab */}
      <div className="action-bar">
        <button className="btn" onClick={() => doAction("accept")}>Accept</button>
        <button className="btn" onClick={doOverride}>Override</button>
        <button className="btn" onClick={() => doAction("return", "RM cần bổ sung giải trình chênh lệch doanh thu")}>Return to RM</button>
        <button className="btn" onClick={() => doAction("rerun")}>Rerun</button>
      </div>
        </>
      )}

      {selectedFinding && (
        <ExplainabilityDrawer caseId={caseId} finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
      )}
    </main>
  );
}
