"use client";

/**
 * "Lập kế hoạch" section — the 4 parallel expert agents' real progress,
 * ported from the prototype's TaskGraph.tsx but simplified: this used to
 * render 3 tiers (a standalone "Lập kế hoạch" box -> the 4 agents -> a
 * standalone "Tổng hợp" box), which read as 6 sequential steps when the
 * Orchestrator's plan/synthesize nodes aren't agents doing separate
 * analysis work — they're bookends around the SAME fan-out shown below,
 * and "Tổng hợp"'s content duplicated ScoringResultPanel one scroll down.
 * Now "Lập kế hoạch" is just this section's heading over the 4 agent
 * cards (that fan-out IS the plan being carried out), and there's no
 * "Tổng hợp" box at all. Status still comes from the REAL SSE
 * `step_started`/`step_completed`/`step_failed` events (worker/app/graph/
 * build.py::STEP_LABELS), the same stream AnalyzingView.tsx already
 * consumes — not a `setTimeout` mock. `steps` is passed down from the
 * case-detail page's own SSE listener (case-detail-page.tsx), which
 * already opens one EventSource for refresh/log — this reuses that data
 * instead of opening a second connection.
 */
import { REAL_AGENT_IDS, planMeta, agentMetaFor } from "../lib/agentMeta";
import { useI18n } from "../lib/i18n";
import { Card, StatusChip, type Tone } from "./ui";

export type StepStatus = "pending" | "in_progress" | "done" | "failed";
export interface StepState {
  step: string;
  status: StepStatus;
}

// Maps worker/app/graph/build.py node ids to the 4 real agent_id values
// findings are actually written under (shared/state.py::AGENT_CODE) — the
// SSE step id and the Finding.agent_id happen to differ only for
// "customer360" (no underscore) vs "customer_360" (with underscore).
export const STEP_TO_AGENT_ID: Record<string, string> = {
  financial: "financial_analysis",
  policy: "policy_compliance",
  collateral: "collateral_legal",
  customer360: "customer_360",
};

function statusOf(steps: StepState[], stepId: string): StepStatus {
  return steps.find((s) => s.step === stepId)?.status ?? "pending";
}

const STATUS_TONE: Record<StepStatus, Tone> = {
  pending: "neutral",
  in_progress: "brand",
  done: "good",
  failed: "critical",
};

function AgentNode({ label, subtitle, status }: { label: string; subtitle?: string; status: StepStatus }) {
  const { t } = useI18n();
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {label}
        </span>
        <StatusChip tone={STATUS_TONE[status]}>{t(`taskGraph.status.${status}`)}</StatusChip>
      </div>
      {subtitle && (
        <div className="mt-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
          {subtitle}
        </div>
      )}
    </Card>
  );
}

export function TaskGraph({ steps }: { steps: StepState[] }) {
  const { t, lang } = useI18n();
  return (
    <div className="space-y-2.5">
      <div>
        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {planMeta(lang).shortLabel}
        </div>
        <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
          {t("taskGraph.parallelProgress")}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {REAL_AGENT_IDS.map((agentId) => {
          const stepId = Object.keys(STEP_TO_AGENT_ID).find((k) => STEP_TO_AGENT_ID[k] === agentId)!;
          const meta = agentMetaFor(agentId, lang);
          return <AgentNode key={agentId} label={meta.shortLabel} status={statusOf(steps, stepId)} />;
        })}
      </div>
    </div>
  );
}
