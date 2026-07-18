"use client";

/**
 * Credit Memo panel — ported from the prototype's CreditMemoPanel.tsx.
 * The memo itself is a computed view (api/app/routers/memo.py::
 * get_credit_memo), not a persisted artifact — "Tạo Credit Memo" just
 * triggers the first fetch; there's no separate generation step to wait
 * on, so the button's loading state is really just the fetch's.
 */
import { useState } from "react";
import { ClipboardList, FileCheck2 } from "lucide-react";
import { fetchCreditMemo } from "../lib/api";
import type { CreditMemo } from "../lib/types";
import { useI18n } from "../lib/i18n";
import { RichText } from "./RichText";
import { Button, Card, RecommendationChip, SectionTitle, formatFullDateTime, type Recommendation } from "./ui";

export function CreditMemoPanel({
  caseId,
  canGenerate,
  onMemoReady,
}: {
  caseId: string;
  canGenerate: boolean;
  /** Fired once a memo has actually been fetched — DISTINCT from
   * `canGenerate` (whether the button is even clickable). ActionBar's
   * `memoReady` gate must track "memo actually exists", same as the
   * prototype's `memoReady = !!memo`. */
  onMemoReady?: (ready: boolean) => void;
}) {
  const { t, lang } = useI18n();
  const [memo, setMemo] = useState<CreditMemo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchCreditMemo(caseId);
      setMemo(result);
      onMemoReady?.(true);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-4">
      <SectionTitle action={memo && <RecommendationChip recommendation={memo.recommendation as Recommendation} />}>
        <span className="flex items-center gap-1.5">
          <FileCheck2 size={14} /> {t("creditMemo.title")}
        </span>
      </SectionTitle>

      {!memo ? (
        <div className="mt-4 flex flex-col items-center gap-3 py-4 text-center">
          <ClipboardList size={22} style={{ color: "var(--text-muted-2)" }} />
          <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
            {canGenerate ? t("creditMemo.canGenerate") : t("creditMemo.cannotGenerate")}
          </p>
          {error && (
            <p className="text-xs" style={{ color: "var(--status-critical)" }}>
              {error}
            </p>
          )}
          <Button variant="primary" onClick={generate} disabled={!canGenerate || loading}>
            {loading ? t("creditMemo.generating") : t("creditMemo.generate")}
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
            {t("creditMemo.preparedAt", { time: formatFullDateTime(memo.prepared_at, lang) })}
          </div>
          {memo.sections.map((section) => (
            <div key={section.title}>
              <div className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                {section.title}
              </div>
              <div className="mt-1 space-y-1" style={{ color: "var(--text-secondary)" }}>
                {/* Was a hard <ul><li> list of raw text — content items are
                    full LLM-generated markdown (bold, and sometimes a whole
                    table, e.g. the legal checklist finding), which doesn't
                    fit inside a single bullet <li>; RichText renders each
                    item as its own block instead. */}
                {section.content.map((line, i) => (
                  <div key={i} className="text-xs">
                    <RichText text={line} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
