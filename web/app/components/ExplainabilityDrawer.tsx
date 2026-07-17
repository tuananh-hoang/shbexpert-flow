"use client";

import { useEffect, useState } from "react";
import { fetchEvidence, fetchFindingHistory } from "../lib/api";
import type { EvidenceItem, Finding } from "../lib/types";
import { EvidenceViewer } from "./EvidenceViewer";

/**
 * Screen 2 + 3 from Explainable_AI_Interaction_Design.md: Agent
 * Explainability Drawer -> Evidence Viewer. The drill-down hierarchy is
 * Dashboard -> Agent Summary -> Evidence — this component IS that second
 * and third step, opened from any widget click on the dashboard.
 *
 * Phase 8: restyled onto the shared globals.css tokens (badge-{stance}
 * classes, --navy/--border/--text-muted vars) instead of a local
 * STANCE_COLOR map, so this component and page.tsx never drift on what
 * "SUPPORT" looks like. Added the Citations section (structured RAG
 * source — distinct from the Evidence section, which resolves
 * evidence_ids to document/page/bbox).
 */

function fmtValue(value: Record<string, unknown>): string {
  if ("amount_vnd" in value) return `${Number(value.amount_vnd).toLocaleString("vi-VN")} VND`;
  if ("date" in value) return String(value.date);
  if ("pct" in value) return `${value.pct}%`;
  return JSON.stringify(value);
}

export function ExplainabilityDrawer({
  caseId,
  finding,
  onClose,
}: {
  caseId: string;
  finding: Finding;
  onClose: () => void;
}) {
  const [evidence, setEvidence] = useState<EvidenceItem[] | null>(null);
  const [history, setHistory] = useState<Finding[] | null>(null);
  const [viewerEvidence, setViewerEvidence] = useState<EvidenceItem | null>(null);

  useEffect(() => {
    setEvidence(null);
    setHistory(null);
    fetchEvidence(caseId, finding.evidence_ids).then(setEvidence).catch(() => setEvidence([]));
    fetchFindingHistory(caseId, finding.finding_key)
      .then((r) => setHistory(r.versions))
      .catch(() => setHistory([finding]));
  }, [caseId, finding]);

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: "min(480px, 100vw)",
        background: "var(--surface)",
        boxShadow: "-4px 0 24px rgba(11, 37, 69, 0.18)",
        padding: 24,
        overflowY: "auto",
        zIndex: 1000,
      }}
    >
      <button
        onClick={onClose}
        style={{ float: "right", border: "none", background: "none", fontSize: 20, cursor: "pointer", color: "var(--text-muted)" }}
      >
        ×
      </button>

      <div className="muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 }}>
        {finding.agent_id}
      </div>
      <h2 style={{ margin: "4px 0 12px", color: "var(--navy-900)" }}>{finding.issue_key.replace(/_/g, " ")}</h2>

      <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
        <span className={`badge badge-${finding.stance}`}>{finding.stance}</span>
        <span className="muted" style={{ fontSize: 13 }}>Severity: {finding.severity}</span>
        <span className="muted" style={{ fontSize: 13 }}>Confidence: {Math.round(finding.confidence * 100)}%</span>
      </div>

      <section style={{ marginBottom: 20 }}>
        <h3 className="section-title" style={{ fontSize: 14 }}>Summary</h3>
        <p>{finding.claim}</p>
        {finding.recommended_action && (
          <p>
            <strong>Recommended action:</strong> {finding.recommended_action}
          </p>
        )}
      </section>

      {finding.citations.length > 0 && (
        <section style={{ marginBottom: 20 }}>
          <h3 className="section-title" style={{ fontSize: 14 }}>Citations</h3>
          {finding.citations.map((c, i) => (
            <div key={i} className="card" style={{ padding: 10, marginBottom: 8 }}>
              <div style={{ fontWeight: 600 }}>
                {c.source_id}
                {c.version && ` v${c.version}`}
                {c.section && ` — ${c.section}`}
              </div>
              {c.effective_date && <div className="muted" style={{ fontSize: 12 }}>hiệu lực {c.effective_date}</div>}
              <blockquote
                style={{
                  fontSize: 13,
                  margin: "6px 0 0",
                  paddingLeft: 10,
                  borderLeft: "3px solid var(--border)",
                  color: "var(--text)",
                }}
              >
                {c.text}
              </blockquote>
              <div className="muted" style={{ fontSize: 11, marginTop: 4, textAlign: "right" }}>
                match {Math.round(c.score * 100)}%
              </div>
            </div>
          ))}
        </section>
      )}

      <section style={{ marginBottom: 20 }}>
        <h3 className="section-title" style={{ fontSize: 14 }}>Evidence</h3>
        {evidence === null && <p className="muted">Đang tải...</p>}
        {evidence?.length === 0 && <p className="muted">Không có evidence.</p>}
        {evidence?.map((e) => (
          <div key={e.field_id} className="card" style={{ padding: 10, marginBottom: 8 }}>
            <div style={{ fontWeight: 600 }}>{e.field_key.replace(/_/g, " ")}</div>
            <div>{fmtValue(e.value)}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {e.doc_type} · trang {e.page} · confidence {Math.round(e.confidence * 100)}%
            </div>
            {e.viewer_url && (
              <button
                onClick={() => setViewerEvidence(e)}
                style={{
                  fontSize: 13,
                  color: "var(--accent)",
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                }}
              >
                Mở tài liệu gốc →
              </button>
            )}
          </div>
        ))}
      </section>

      {history && history.length > 1 && (
        <section>
          <h3 className="section-title" style={{ fontSize: 14 }}>Decision Trace — lịch sử version</h3>
          {history.map((h) => (
            <div key={h.version} style={{ borderLeft: "3px solid var(--border)", paddingLeft: 10, marginBottom: 10 }}>
              <div style={{ fontWeight: 600 }}>
                v{h.version} — <span className={`badge badge-${h.stance}`}>{h.stance}</span>
              </div>
              <div style={{ fontSize: 13, marginTop: 4 }}>{h.claim}</div>
              {h.change_reason && (
                <div className="muted" style={{ fontSize: 12, fontStyle: "italic" }}>{h.change_reason}</div>
              )}
            </div>
          ))}
        </section>
      )}

      {viewerEvidence && <EvidenceViewer evidence={viewerEvidence} onClose={() => setViewerEvidence(null)} />}
    </div>
  );
}
