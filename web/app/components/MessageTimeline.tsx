"use client";

/**
 * Inter-agent coordination feed — ported from the prototype's
 * MessageTimeline.tsx, but real agents never chat with each other
 * (ai-architecture.md §3: blackboard pattern, no direct messaging). What
 * DOES exist and maps onto this exact UI shape is `ConflictRecord.
 * targeted_questions[]` — the Orchestrator's targeted question to the
 * specific agent whose finding conflicts with another (worker/app/graph/
 * build.py::_challenge_node). `from` is always "Orchestrator" here, which
 * is the honest source — not a fabricated agent-to-agent transcript.
 */
import { MessageSquareShare } from "lucide-react";
import type { Conflict } from "../lib/types";
import { agentMetaFor } from "../lib/agentMeta";
import { useI18n } from "../lib/i18n";
import { Card, SectionTitle } from "./ui";

export function MessageTimeline({ conflicts }: { conflicts: Conflict[] }) {
  const { t, lang } = useI18n();
  const rows = conflicts.flatMap((c) =>
    c.targeted_questions.map((q, i) => ({
      key: `${c.conflict_id}-${i}`,
      toAgent: q.to_agent,
      question: q.question,
      round: c.round,
    }))
  );

  return (
    <Card className="p-4">
      <SectionTitle>{t("messageTimeline.title")}</SectionTitle>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm" style={{ color: "var(--text-muted-2)" }}>
          {t("messageTimeline.empty")}
        </p>
      ) : (
        <div className="mt-2 space-y-2">
          {rows.map((r) => (
            <div key={r.key} className="rounded-lg p-2.5" style={{ background: "var(--status-warning-bg)" }}>
              <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: "var(--status-warning)" }}>
                <MessageSquareShare size={13} />
                Orchestrator → {agentMetaFor(r.toAgent, lang).shortLabel} ({t("messageTimeline.roundLabel")} {r.round})
              </div>
              <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
                {r.question}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
