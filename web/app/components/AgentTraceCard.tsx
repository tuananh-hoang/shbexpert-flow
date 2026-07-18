"use client";

/**
 * One card per real expert agent — ported from the prototype's
 * AgentTraceCard.tsx (1 card = 1 AgentDecision), but a real agent writes
 * MANY findings (Financial alone writes 7 — DSCR/coverage/4 ratio groups/
 * cashflow), not one. This groups the agent's latest findings into a
 * single card: `rationale` = each finding's claim (prefixed by
 * issue_key), `confidence` = their average, the header chip = the
 * worst-case stance roll-up (ui.tsx::rollupStance — same "don't average
 * away a real gap" rule decision.py's scorecard uses).
 *
 * "Chỉ số đã tính" (was mislabeled "Tool calls (n)") is the REAL
 * deterministic-tool OUTPUT already on each finding (`metrics` — dscr,
 * coverage_ratio, ...), not a count of tool invocations — the old label
 * made a metric count (e.g. "32") read like a broken call counter.
 * Grouped per-finding (not flattened into one bag) with Vietnamese labels
 * (METRIC_LABELS) so a bare "0" is legible in context (e.g.
 * cross_guarantee_total_vnd=0 when there's genuinely no cross-guarantee),
 * instead of an unlabeled snake_case key next to a number.
 *
 * "Căn cứ chính sách/pháp lý" (was "Trích dẫn (RAG)") — same citations,
 * renamed because "RAG" is retrieval-augmented-generation engineering
 * jargon a Credit Officer has no reason to know; what it actually shows
 * is which policy/legal-checklist clause backs the claim.
 */
import { Wrench, BookOpen } from "lucide-react";
import type { Finding } from "../lib/types";
import { agentMetaFor } from "../lib/agentMeta";
import { useI18n } from "../lib/i18n";
import { Card, ConfidenceMeter, SectionTitle, StanceChip, rollupStance } from "./ui";

// Metric labels come from the shared i18n dictionary (`metric.*` keys,
// lib/i18n.tsx) — one definition per language instead of a second
// Vietnamese-only copy here. Falls back to a humanized version of the raw
// key (via t()'s built-in fallback-to-key behavior) for anything not
// listed, so an unmapped key never renders blank.
function metricLabel(key: string, t: (k: string) => string): string {
  const translated = t(`metric.${key}`);
  return translated === `metric.${key}` ? key.replace(/_/g, " ") : translated;
}

export function AgentTraceCard({
  agentId,
  findings,
  onSelectFinding,
}: {
  agentId: string;
  findings: Finding[];
  onSelectFinding: (finding: Finding) => void;
}) {
  const { t, lang } = useI18n();
  const meta = agentMetaFor(agentId, lang);
  const Icon = meta.icon;

  if (findings.length === 0) {
    return (
      <Card className="p-4">
        <SectionTitle>
          <span className="flex items-center gap-1.5">
            <Icon size={14} /> {meta.shortLabel}
          </span>
        </SectionTitle>
        <p className="mt-6 text-center text-sm" style={{ color: "var(--text-muted-2)" }}>
          {t("agentTrace.waiting")}
        </p>
      </Card>
    );
  }

  const stance = rollupStance(findings.map((f) => f.stance));
  const avgConfidence = findings.reduce((s, f) => s + f.confidence, 0) / findings.length;
  const allCitations = findings.flatMap((f) => f.citations.map((c) => ({ ...c, findingId: f.display_id })));
  const metricsByFinding = findings
    .map((f) => ({ finding: f, entries: Object.entries(f.metrics) }))
    .filter((g) => g.entries.length > 0);
  const totalMetrics = metricsByFinding.reduce((s, g) => s + g.entries.length, 0);

  return (
    <Card className="space-y-3 p-4">
      <SectionTitle
        action={<StanceChip stance={stance} />}
      >
        <span className="flex items-center gap-1.5">
          <Icon size={14} /> {meta.shortLabel}
        </span>
      </SectionTitle>

      <ConfidenceMeter value={avgConfidence} />

      <ul className="space-y-1.5">
        {findings.map((f) => (
          <li key={f.display_id}>
            <button className="text-left text-sm" onClick={() => onSelectFinding(f)} style={{ color: "var(--text-secondary)" }}>
              <span style={{ color: "var(--brand)" }}>•</span> [{f.issue_key.replace(/_/g, " ")}] {f.claim}
            </button>
          </li>
        ))}
      </ul>

      {metricsByFinding.length > 0 && (
        <div className="border-t pt-2" style={{ borderColor: "var(--border-hairline)" }}>
          <div className="mb-1 flex items-center gap-1 text-xs font-medium" style={{ color: "var(--text-muted-2)" }}>
            <Wrench size={12} /> {t("agentTrace.metricsComputed", { n: totalMetrics })}
          </div>
          <div className="space-y-1.5">
            {metricsByFinding.map(({ finding, entries }) => (
              <div key={finding.display_id}>
                <div className="text-[11px]" style={{ color: "var(--text-muted-2)" }}>
                  [{finding.issue_key.replace(/_/g, " ")}]
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {entries.map(([key, value]) => (
                    <span
                      key={key}
                      className="rounded px-1.5 py-0.5 font-mono text-xs"
                      style={{ background: "var(--surface-1)", color: "var(--brand)" }}
                    >
                      {metricLabel(key, t)}: {typeof value === "number" ? value.toLocaleString(lang === "en" ? "en-US" : "vi-VN") : String(value)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {allCitations.length > 0 && (
        <div className="border-t pt-2" style={{ borderColor: "var(--border-hairline)" }}>
          <div className="mb-1 flex items-center gap-1 text-xs font-medium" style={{ color: "var(--text-muted-2)" }}>
            <BookOpen size={12} /> {t("agentTrace.policyBasis")}
          </div>
          <div className="space-y-1">
            {allCitations.map((c, i) => (
              <div
                key={i}
                className="rounded px-1.5 py-1 text-xs"
                style={{ background: "var(--surface-1)", color: "var(--text-secondary)" }}
                title={c.text}
              >
                {c.source_id}
                {c.version && ` v${c.version}`} — {Math.round(c.score * 100)}%
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
