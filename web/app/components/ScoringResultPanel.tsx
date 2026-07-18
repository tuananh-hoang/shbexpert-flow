"use client";

/**
 * "Khuyến nghị của AI" card — ported from the prototype's
 * ScoringResultPanel.tsx, but the prototype's XHTD score/rating-grade
 * (AA-CCC)/PD% don't exist in this backend and are NOT invented here
 * (ai-architecture_v2.md §18: no fabricated grades). The 3-metric stat
 * row keeps the same visual shape with real numbers instead:
 *   1. Điểm tổng hợp  — Σscore/Σmax over decision.scores (0-100)
 *   2. Khuyến nghị    — decision.recommendation (RecommendationChip)
 *   3. Hard gates     — X/Y PASS (decision.hard_gates)
 * `conditions_precedent[]` (already plain strings) is the
 * "requiredActions" list.
 *
 * Renamed from "Kết luận tổng hợp (Decision Synthesis)" — a Credit
 * Officer shouldn't need to know this is the LangGraph synthesize node's
 * output to understand the panel; a plain-language headline sentence
 * (below the title) states the recommendation in a full sentence before
 * the stat block, so the numbers aren't the first thing to interpret.
 */
import { ClipboardList, Gauge } from "lucide-react";
import type { Decision, Finding } from "../lib/types";
import { useI18n } from "../lib/i18n";
import { Card, RecommendationChip, SectionTitle, formatVnd, type Recommendation } from "./ui";

function FindingLinkList({
  ids,
  findings,
  onSelectFinding,
  emptyLabel,
}: {
  ids: string[];
  findings: Finding[];
  onSelectFinding: (finding: Finding) => void;
  emptyLabel: string;
}) {
  if (ids.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
        {emptyLabel}
      </p>
    );
  }
  return (
    <div className="space-y-1">
      {ids.map((id) => {
        const finding = findings.find((f) => f.display_id === id);
        return (
          <button
            key={id}
            className="block text-left text-sm underline"
            style={{ color: "var(--brand)" }}
            onClick={() => finding && onSelectFinding(finding)}
          >
            {id}
          </button>
        );
      })}
    </div>
  );
}

// Sentinel used to split the translated headline sentence around the
// {recommendation} placeholder so the recommendation text can render bold
// — t() only returns a plain string, not JSX. A word token (not a bare
// space) avoids ambiguity with real spaces elsewhere in the sentence.
const HEADLINE_SENTINEL = "@@REC@@";

export function ScoringResultPanel({
  decision,
  findings,
  onSelectFinding,
}: {
  decision: Decision | null;
  findings: Finding[];
  onSelectFinding: (finding: Finding) => void;
}) {
  const { t, lang } = useI18n();

  if (!decision) {
    return (
      <Card className="border-dashed p-6 text-center" style={{ borderColor: "var(--border-strong-2)" }}>
        <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
          {t("scoringResult.empty")}
        </p>
      </Card>
    );
  }

  const scoreSum = decision.scores.reduce((s, x) => s + x.score, 0);
  const scoreMax = decision.scores.reduce((s, x) => s + x.max, 0);
  const compositePct = decision.scores.length > 0 && scoreMax > 0 ? Math.round((scoreSum / scoreMax) * 100) : null;
  const gatesPass = decision.hard_gates.filter((g) => g.status === "PASS").length;
  const recommendationLabel = t(`rec.${decision.recommendation}`);
  const [headlinePre, headlinePost] = t("scoringResult.headline", { recommendation: HEADLINE_SENTINEL }).split(
    HEADLINE_SENTINEL
  );

  return (
    <Card className="space-y-4 p-4" style={{ borderColor: "var(--brand)" }}>
      <SectionTitle action={<RecommendationChip recommendation={decision.recommendation as Recommendation} />}>
        {t("scoringResult.title")}
      </SectionTitle>
      <p className="-mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        {headlinePre}
        <strong style={{ color: "var(--text-primary)" }}>{recommendationLabel}</strong>
        {headlinePost}
      </p>

      <div className="flex items-center gap-4 rounded-lg p-3" style={{ background: "var(--surface-1)" }}>
        <span
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
          style={{ background: "var(--brand-bg)", color: "var(--brand)" }}
        >
          <Gauge size={20} />
        </span>
        <div className="grid flex-1 grid-cols-3 text-center">
          <div>
            <div className="tabular-nums text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              {compositePct != null ? `${compositePct}` : "—"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
              {t("scoringResult.compositeScore")}
            </div>
          </div>
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {decision.hard_gates.length > 0 ? `${gatesPass}/${decision.hard_gates.length}` : "—"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
              {t("scoringResult.hardGatePass")}
            </div>
          </div>
          <div>
            <div className="tabular-nums text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {decision.recommended_amount_vnd != null ? formatVnd(decision.recommended_amount_vnd, lang) : "—"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
              {t("scoringResult.recommendedAmount")}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 border-t pt-3 sm:grid-cols-2" style={{ borderColor: "var(--border-hairline)" }}>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--status-good)" }}>
            {t("scoringResult.strengths")}
          </div>
          <FindingLinkList ids={decision.strengths} findings={findings} onSelectFinding={onSelectFinding} emptyLabel="—" />
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--status-critical)" }}>
            {t("scoringResult.risks")}
          </div>
          <FindingLinkList ids={decision.risks} findings={findings} onSelectFinding={onSelectFinding} emptyLabel="—" />
        </div>
      </div>

      {decision.dissent.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--status-warning)" }}>
            {t("scoringResult.dissent")}
          </div>
          <FindingLinkList ids={decision.dissent} findings={findings} onSelectFinding={onSelectFinding} emptyLabel="—" />
        </div>
      )}

      {decision.conditions_precedent.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium" style={{ color: "var(--text-muted-2)" }}>
            <ClipboardList size={13} /> {t("scoringResult.conditions")}
          </div>
          <ol className="list-inside list-decimal space-y-1">
            {decision.conditions_precedent.map((cond, i) => (
              <li
                key={i}
                className="rounded px-2 py-1 text-sm"
                style={{ background: "var(--status-warning-bg)", color: "var(--status-warning)" }}
              >
                {cond}
              </li>
            ))}
          </ol>
        </div>
      )}

      {decision.policy_version && (
        <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
          policy_version={decision.policy_version} · decision_matrix_version={decision.decision_matrix_version}
        </div>
      )}
    </Card>
  );
}
