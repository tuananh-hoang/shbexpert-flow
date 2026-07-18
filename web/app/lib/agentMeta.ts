// Per-agent display metadata for the 4 real expert agents (worker/app/
// agents/*.py) — ported from the dashmint_ai-trang prototype's
// lib/agentMeta.ts pattern (per-agent {label, shortLabel, icon} reused
// across TaskGraph/AgentTraceCard/MessageTimeline), rewired to this app's
// REAL agent_id values instead of the prototype's mock
// credit_scoring/financial/legal/collateral set.
//
// agent_id values match shared/state.py::AGENT_CODE keys exactly — keep
// this in sync if a new agent is added there.
import { Building2, CheckCircle2, LineChart, Scale, Users, Workflow } from "lucide-react";
import type { ComponentType } from "react";
import { translate, type Lang } from "./i18n";

export type RealAgentId = "financial_analysis" | "policy_compliance" | "collateral_legal" | "customer_360";

export interface AgentMeta {
  label: string;
  shortLabel: string;
  icon: ComponentType<{ size?: number; className?: string }>;
}

// Icons only — labels are resolved per-language via translate() below, so
// this plain module (no hook access) still reads from the same lib/i18n.tsx
// dictionary every hook-based component uses instead of a second copy.
const AGENT_ICON: Record<RealAgentId, AgentMeta["icon"]> = {
  financial_analysis: LineChart,
  policy_compliance: Scale,
  collateral_legal: Building2,
  customer_360: Users,
};

export const REAL_AGENT_IDS: RealAgentId[] = [
  "financial_analysis",
  "policy_compliance",
  "collateral_legal",
  "customer_360",
];

export function agentMetaFor(agentId: string, lang: Lang): AgentMeta {
  const icon = AGENT_ICON[agentId as RealAgentId];
  if (!icon) return { label: agentId, shortLabel: agentId, icon: Workflow };
  return {
    label: translate(lang, `agent.${agentId}.label`),
    shortLabel: translate(lang, `agent.${agentId}.short`),
    icon,
  };
}

// Orchestrator/synthesis "nodes" in the LangGraph fan-out (worker/app/
// graph/build.py::STEP_LABELS) that aren't one of the 4 domain agents —
// TaskGraph needs meta for these too (top/bottom nodes of the graph).
export function planMeta(lang: Lang): AgentMeta {
  return { label: translate(lang, "agent.plan.label"), shortLabel: translate(lang, "agent.plan.short"), icon: Workflow };
}

export function synthesizeMeta(lang: Lang): AgentMeta {
  return {
    label: translate(lang, "agent.synthesize.label"),
    shortLabel: translate(lang, "agent.synthesize.short"),
    icon: CheckCircle2,
  };
}
