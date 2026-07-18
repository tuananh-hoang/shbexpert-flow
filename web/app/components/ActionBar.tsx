"use client";

/**
 * Human-in-the-loop action bar — ported from the prototype's
 * ActionBar.tsx (4 buttons + inline confirm-with-note), mapped onto this
 * backend's REAL decision/action endpoint (api/app/routers/cases.py).
 *
 * `reject`/`escalate` are NEW actions added for this redesign — audit-only
 * (a CO_ACTION event, no state transition): the case state machine has no
 * REJECTED/ESCALATED terminal modeled, and ai-architecture_v2.md §1.2
 * explicitly lists "không suy đoán authority matrix/workflow" as a
 * non-goal, so this doesn't invent one. `override` (existing HITL
 * override-with-reason, FR-11/AS-05) is KEPT as a separate action below
 * the main 4 — the prototype has no equivalent, but this is real,
 * already-working functionality this redesign must not drop.
 *
 * `MOCK_APPROVAL_AUTHORITY_VND` mirrors the prototype's
 * APPROVAL_AUTHORITY_VND purely to exercise the "vượt thẩm quyền -> chỉ
 * escalate được" UX — a clearly-labeled demo threshold, not a real SHB
 * authority matrix (same "MOCK, not policy" convention as DSCR>=1.3,
 * coverage tiers, etc. elsewhere in this codebase).
 */
import { useState } from "react";
import { ArrowUpCircle, CheckCircle2, RotateCcw, ShieldAlert, XCircle } from "lucide-react";
import { useI18n } from "../lib/i18n";
import { Button, Card, formatVnd } from "./ui";

export const MOCK_APPROVAL_AUTHORITY_VND = 5_000_000_000;

export type ActionKey = "return" | "reject" | "accept" | "escalate" | "override";

const ACTIONS: { key: ActionKey; labelKey: string; icon: typeof RotateCcw; variant: "secondary" | "danger" | "primary" }[] = [
  { key: "return", labelKey: "actionBar.action.return", icon: RotateCcw, variant: "secondary" },
  { key: "reject", labelKey: "actionBar.action.reject", icon: XCircle, variant: "danger" },
  { key: "accept", labelKey: "actionBar.action.accept", icon: CheckCircle2, variant: "primary" },
  { key: "escalate", labelKey: "actionBar.action.escalate", icon: ArrowUpCircle, variant: "secondary" },
];

const NOTE_PLACEHOLDER_KEY: Record<ActionKey, string> = {
  return: "actionBar.note.return",
  reject: "actionBar.note.reject",
  accept: "actionBar.note.accept",
  escalate: "actionBar.note.escalate",
  override: "actionBar.note.override",
};

const REASON_REQUIRED: ActionKey[] = ["reject", "escalate", "override"];

export function ActionBar({
  requestedAmountVnd,
  canDecide,
  caseState,
  memoReady,
  onAction,
}: {
  requestedAmountVnd: number | null;
  canDecide: boolean;
  /** Real Case.state (shared/state.py) — shown in a banner when !canDecide
   * so "every button is greyed out" has a visible reason instead of
   * reading as broken. Without this, a case that has moved past
   * READY_FOR_REVIEW (or hasn't reached it yet) looked identical to a
   * genuinely broken ActionBar. */
  caseState: string;
  memoReady: boolean;
  onAction: (action: ActionKey, reason?: string) => void;
}) {
  const { t, lang } = useI18n();
  const [pending, setPending] = useState<ActionKey | null>(null);
  const [note, setNote] = useState("");

  const overAuthority = requestedAmountVnd != null && requestedAmountVnd > MOCK_APPROVAL_AUTHORITY_VND;

  const confirm = (key: ActionKey) => {
    if (REASON_REQUIRED.includes(key) && !note.trim()) return;
    onAction(key, note.trim() || undefined);
    setPending(null);
    setNote("");
  };

  return (
    <Card className="space-y-3 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted-2)" }}>
        {t("actionBar.title")}
      </div>

      {!canDecide && (
        <div
          className="flex items-start gap-1.5 rounded-lg p-2 text-xs"
          style={{ background: "var(--status-warning-bg)", color: "var(--status-warning)" }}
        >
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          {t("actionBar.wrongState", { state: caseState })}
        </div>
      )}
      {canDecide && !memoReady && (
        <div
          className="flex items-start gap-1.5 rounded-lg p-2 text-xs"
          style={{ background: "var(--status-warning-bg)", color: "var(--status-warning)" }}
        >
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          {t("actionBar.memoRequired")}
        </div>
      )}
      {overAuthority && (
        <div
          className="flex items-start gap-1.5 rounded-lg p-2 text-xs"
          style={{ background: "var(--status-warning-bg)", color: "var(--status-warning)" }}
        >
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          {t("actionBar.overAuthority", {
            amount: formatVnd(requestedAmountVnd, lang),
            limit: formatVnd(MOCK_APPROVAL_AUTHORITY_VND, lang),
          })}
        </div>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {ACTIONS.map(({ key, labelKey, icon: Icon, variant }) => (
          <Button
            key={key}
            variant={variant}
            disabled={!canDecide || !memoReady || (key === "accept" && overAuthority)}
            onClick={() => setPending(key)}
          >
            <span className="flex w-full items-center gap-2">
              <Icon size={15} /> {t(labelKey)}
            </span>
          </Button>
        ))}
      </div>

      <Button variant="ghost" size="sm" disabled={!canDecide} onClick={() => setPending("override")}>
        {t("actionBar.overrideButton")}
      </Button>

      {pending && (
        <div className="rounded-lg p-3" style={{ background: "var(--surface-1)" }}>
          <textarea
            className="w-full rounded-lg border p-2 text-sm"
            style={{ borderColor: "var(--border-hairline)", background: "var(--surface-raised)", color: "var(--text-primary)" }}
            rows={2}
            placeholder={t(NOTE_PLACEHOLDER_KEY[pending])}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-2 flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setPending(null);
                setNote("");
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={REASON_REQUIRED.includes(pending) && !note.trim()}
              onClick={() => confirm(pending)}
            >
              {t("common.confirm")}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
