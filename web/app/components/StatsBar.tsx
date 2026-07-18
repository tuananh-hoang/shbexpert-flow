"use client";

/** KPI tile strip — ported from the prototype's StatsBar.tsx.
 * "Thời gian phê duyệt trung bình" is real: computed from every case that
 * has reached a forward-resolved state (`updated_at - created_at`,
 * lib/priority.ts::averageApprovalHours) — "—" only appears when there
 * truly are zero such cases yet, not as a permanent placeholder.
 * "Chất lượng phê duyệt" (NPL) stays "—" always — there is no
 * post-disbursement loan-performance table anywhere in this schema, a
 * real and permanent data gap (not a bug), so the explanatory note below
 * it is load-bearing, not decorative. */
import { Clock, FileStack, ShieldCheck, Siren } from "lucide-react";
import type { ReactNode } from "react";
import { Card, formatHours } from "./ui";
import { useI18n } from "../lib/i18n";

function Tile({
  icon,
  label,
  value,
  valueColor,
  note,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  valueColor?: string;
  note?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full"
          style={{ background: "var(--surface-1)", color: "var(--text-muted-2)" }}
        >
          {icon}
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted-2)" }}>
          {label}
        </span>
      </div>
      <div className="tabular-nums mt-1 text-xl font-semibold" style={{ color: valueColor ?? "var(--text-primary)" }}>
        {value}
      </div>
      {note && (
        <div className="mt-0.5 text-xs" style={{ color: "var(--text-muted-2)" }} title={note}>
          {note}
        </div>
      )}
    </Card>
  );
}

export function StatsBar({
  pendingCount,
  urgentCount,
  avgApprovalHours,
}: {
  pendingCount: number;
  urgentCount: number;
  avgApprovalHours: number | null;
}) {
  const { t, lang } = useI18n();
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Tile icon={<FileStack size={16} />} label={t("stats.pending")} value={String(pendingCount)} />
      <Tile
        icon={<Siren size={16} />}
        label={t("stats.urgent")}
        value={String(urgentCount)}
        valueColor={urgentCount > 0 ? "var(--status-critical)" : "var(--status-good)"}
      />
      <Tile
        icon={<Clock size={16} />}
        label={t("stats.avgApproval")}
        value={avgApprovalHours != null ? formatHours(avgApprovalHours, lang) : "—"}
        note={avgApprovalHours == null ? t("stats.avgApprovalNote") : undefined}
      />
      <Tile icon={<ShieldCheck size={16} />} label={t("stats.quality")} value="—" note={t("stats.qualityNote")} />
    </div>
  );
}
