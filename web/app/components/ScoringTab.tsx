"use client";

/**
 * "Đánh giá sơ bộ & Chấm điểm" tab — TaskGraph's "Lập kế hoạch" progress
 * strip full-width on top, then agent trace cards + message timeline +
 * scoring result below. Used to be a 300px-sidebar/1fr two-column layout
 * (ported from the prototype as-is) — but that fit a TALL 3-tier TaskGraph
 * (plan box -> 4 agents -> synthesize box); now that TaskGraph is just a
 * heading + one row of 4 compact cards, a tall empty sidebar next to a
 * much longer right column looked broken, so this is a single top-to-
 * bottom stack instead. All data is real (caseDetail.findings/conflicts/
 * decision) — see TaskGraph.tsx/AgentTraceCard.tsx/MessageTimeline.tsx/
 * ScoringResultPanel.tsx docstrings for the exact prototype->real-field
 * mapping.
 */
import type { CaseDetail, Finding } from "../lib/types";
import { REAL_AGENT_IDS } from "../lib/agentMeta";
import { AgentTraceCard } from "./AgentTraceCard";
import { MessageTimeline } from "./MessageTimeline";
import { ScoringResultPanel } from "./ScoringResultPanel";
import { TaskGraph, type StepState } from "./TaskGraph";

export function ScoringTab({
  caseDetail,
  steps,
  onSelectFinding,
}: {
  caseDetail: CaseDetail;
  steps: StepState[];
  onSelectFinding: (finding: Finding) => void;
}) {
  const findingsByAgent = new Map<string, Finding[]>();
  for (const agentId of REAL_AGENT_IDS) findingsByAgent.set(agentId, []);
  for (const f of caseDetail.findings) {
    if (!findingsByAgent.has(f.agent_id)) findingsByAgent.set(f.agent_id, []);
    findingsByAgent.get(f.agent_id)!.push(f);
  }

  return (
    <div className="space-y-5">
      <TaskGraph steps={steps} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {REAL_AGENT_IDS.map((agentId) => (
          <AgentTraceCard
            key={agentId}
            agentId={agentId}
            findings={findingsByAgent.get(agentId) ?? []}
            onSelectFinding={onSelectFinding}
          />
        ))}
      </div>

      <MessageTimeline conflicts={caseDetail.conflicts} />
      <ScoringResultPanel decision={caseDetail.decision} findings={caseDetail.findings} onSelectFinding={onSelectFinding} />
    </div>
  );
}
