"use client";

/** Queue filters — ported from the prototype's FilterBar.tsx. `branch` is
 * omitted: `Case` has no branch field in this backend (unlike the
 * prototype's mock CreditCase), so a branch dropdown would filter against
 * data that doesn't exist — left out rather than faked. */
import { useI18n } from "../lib/i18n";

export type AmountBucket = "all" | "lt1b" | "1to5b" | "gt5b";

export interface QueueFilters {
  product: string | "all";
  amountBucket: AmountBucket;
}

export function FilterBar({
  products,
  filters,
  onChange,
}: {
  products: string[];
  filters: QueueFilters;
  onChange: (next: QueueFilters) => void;
}) {
  const { t } = useI18n();
  const hasActiveFilter = filters.product !== "all" || filters.amountBucket !== "all";

  const selectStyle = {
    background: "var(--surface-raised)",
    borderColor: "var(--border-hairline)",
    color: "var(--text-primary)",
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className="rounded-lg border px-2.5 py-1.5 text-sm"
        style={selectStyle}
        value={filters.product}
        onChange={(e) => onChange({ ...filters, product: e.target.value })}
      >
        <option value="all">{t("filter.allProducts")}</option>
        {products.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>

      <select
        className="rounded-lg border px-2.5 py-1.5 text-sm"
        style={selectStyle}
        value={filters.amountBucket}
        onChange={(e) => onChange({ ...filters, amountBucket: e.target.value as AmountBucket })}
      >
        <option value="all">{t("filter.allAmounts")}</option>
        <option value="lt1b">{t("filter.lt1b")}</option>
        <option value="1to5b">{t("filter.1to5b")}</option>
        <option value="gt5b">{t("filter.gt5b")}</option>
      </select>

      {hasActiveFilter && (
        <button
          className="text-sm underline"
          style={{ color: "var(--text-muted-2)" }}
          onClick={() => onChange({ product: "all", amountBucket: "all" })}
        >
          {t("filter.clear")}
        </button>
      )}
    </div>
  );
}

export function applyFilters<T extends { product: string; requested_facility: Record<string, unknown> }>(
  cases: T[],
  filters: QueueFilters
): T[] {
  return cases.filter((c) => {
    if (filters.product !== "all" && c.product !== filters.product) return false;
    if (filters.amountBucket !== "all") {
      const amount = typeof c.requested_facility.amount_vnd === "number" ? c.requested_facility.amount_vnd : 0;
      if (filters.amountBucket === "lt1b" && amount >= 1_000_000_000) return false;
      if (filters.amountBucket === "1to5b" && (amount < 1_000_000_000 || amount > 5_000_000_000)) return false;
      if (filters.amountBucket === "gt5b" && amount <= 5_000_000_000) return false;
    }
    return true;
  });
}
