"use client";

/** Queue as clickable cards (not a table) — ported from the prototype's
 * QueueList.tsx. Each row navigates to /cases/{case_id}; priority/status
 * chips use the real Priority (client-computed, lib/priority.ts) and real
 * case `state` machine (ui.tsx::CaseStatusChip), not the prototype's mock
 * CaseStatus enum. */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { CaseSummary } from "../lib/types";
import type { Priority } from "./ui";
import { Card, CaseStatusChip, PriorityChip, formatHours, formatVnd } from "./ui";
import { ageHours } from "../lib/priority";
import { useI18n } from "../lib/i18n";

type Row = CaseSummary & { priority: Priority };

export function QueueList({ cases }: { cases: Row[] }) {
  const { t, lang } = useI18n();

  if (cases.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p style={{ color: "var(--text-muted-2)" }}>{t("queueList.empty")}</p>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {cases.map((c) => {
        const amount = typeof c.requested_facility.amount_vnd === "number" ? c.requested_facility.amount_vnd : null;
        const tenor = typeof c.requested_facility.tenor_months === "number" ? c.requested_facility.tenor_months : null;
        return (
          <Link key={c.case_id} href={`/cases/${c.case_id}`}>
            <Card className="cursor-pointer p-4 transition-shadow hover:shadow-sm">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <PriorityChip priority={c.priority} />
                    <CaseStatusChip state={c.has_findings ? c.state : "DRAFT"} />
                    <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                      {c.customer_id}
                    </span>
                  </div>
                  <div className="mt-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
                    {c.product} · {t("queueList.waitPrefix")} {formatHours(ageHours(c.updated_at), lang)}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="tabular-nums text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {formatVnd(amount, lang)}
                  </div>
                  {tenor != null && (
                    <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
                      {tenor} {t("queueList.tenorSuffix")}
                    </div>
                  )}
                </div>
                <ArrowRight size={18} style={{ color: "var(--text-muted-2)" }} />
              </div>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
