"use client";

/**
 * Application Queue — redesigned per dashmint_ai-trang's Dashboard.tsx:
 * header -> StatsBar -> FilterBar -> QueueList (cards, not a table).
 * Priority is computed client-side (lib/priority.ts) since `Case` has no
 * priority column; everything else binds to real GET /cases data
 * (api/app/routers/cases.py::list_cases).
 */
import { useEffect, useMemo, useState } from "react";
import { fetchCases } from "./lib/api";
import type { CaseSummary } from "./lib/types";
import { StatsBar } from "./components/StatsBar";
import { FilterBar, applyFilters, type QueueFilters } from "./components/FilterBar";
import { QueueList } from "./components/QueueList";
import { averageApprovalHours, isPending, sortByPriority } from "./lib/priority";
import { useI18n } from "./lib/i18n";

export default function ApplicationQueue() {
  const { t } = useI18n();
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [filters, setFilters] = useState<QueueFilters>({ product: "all", amountBucket: "all" });

  useEffect(() => {
    fetchCases().then(setCases).catch(() => setCases([]));
  }, []);

  const pending = useMemo(() => (cases ?? []).filter(isPending), [cases]);
  const sorted = useMemo(() => sortByPriority(pending), [pending]);
  const filtered = useMemo(() => applyFilters(sorted, filters), [sorted, filters]);
  const urgentCount = useMemo(() => sorted.filter((c) => c.priority === "urgent").length, [sorted]);
  const avgApprovalHours = useMemo(() => averageApprovalHours(cases ?? []), [cases]);
  const products = useMemo(() => Array.from(new Set((cases ?? []).map((c) => c.product))).sort(), [cases]);

  return (
    <main className="mx-auto max-w-7xl px-8 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("queue.title")}
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          {t("queue.subtitle")}
        </p>
      </div>

      <div className="mb-5">
        <StatsBar pendingCount={pending.length} urgentCount={urgentCount} avgApprovalHours={avgApprovalHours} />
      </div>

      <div className="mb-4">
        <FilterBar products={products} filters={filters} onChange={setFilters} />
      </div>

      {cases === null ? (
        <p style={{ color: "var(--text-muted-2)" }}>{t("queue.loading")}</p>
      ) : (
        <QueueList cases={filtered} />
      )}
    </main>
  );
}
