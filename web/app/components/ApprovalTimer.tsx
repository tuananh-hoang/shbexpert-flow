"use client";

/** Compact elapsed-time pill, ported from the prototype's
 * ApprovalTimer.tsx. The "faster than average" comparison pill only
 * appears when a historical average actually exists — this backend has no
 * resolved-case history table yet (see StatsBar.tsx's same honesty note),
 * so that half is omitted rather than showing a fabricated percentage. */
import { Clock } from "lucide-react";
import { formatHours } from "./ui";
import { useI18n } from "../lib/i18n";

export function ApprovalTimer({ elapsedHours, isResolved }: { elapsedHours: number; isResolved: boolean }) {
  const { t, lang } = useI18n();
  return (
    <div className="flex items-center gap-2">
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
        style={{ background: "var(--surface-1)", color: "var(--text-secondary)" }}
      >
        <Clock size={13} />
        {isResolved ? t("approvalTimer.resolved") : t("approvalTimer.inProgress")} · {formatHours(elapsedHours, lang)}
      </span>
    </div>
  );
}
