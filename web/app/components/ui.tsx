"use client";

/**
 * Shared UI primitives — ported from the `dashmint_ai-trang` prototype's
 * `ui.tsx` (design language: violet brand, hairline borders over shadows,
 * chip-driven status language), rewired to this app's REAL domain types
 * (`Stance`, `Decision.recommendation`, case `state` machine) instead of
 * the prototype's mock `Verdict`/`TaskStatus`/`Priority` enums.
 *
 * Every color comes from a CSS variable defined in globals.css (new
 * `--brand`/`--status-*`/`--surface-*` tokens) — never a hex literal here,
 * so light/dark mode (prefers-color-scheme) and any future palette change
 * happen in exactly one place.
 */
import type { ReactNode } from "react";
import type { Stance } from "../lib/types";
import { useI18n, translate, type Lang } from "../lib/i18n";

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------
export function Card({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={`rounded-xl border ${className}`}
      style={{ background: "var(--surface-raised)", borderColor: "var(--border-hairline)", ...style }}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h3
        className="text-sm font-semibold uppercase tracking-wide"
        style={{ color: "var(--text-muted-2)" }}
      >
        {children}
      </h3>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusChip — base chip; every domain-specific chip below maps its enum to
// {tone, label} and renders through this one component.
// ---------------------------------------------------------------------------
export type Tone = "good" | "warning" | "serious" | "critical" | "neutral" | "brand";

const TONE_COLORS: Record<Tone, { fg: string; bg: string }> = {
  good: { fg: "var(--status-good)", bg: "var(--status-good-bg)" },
  warning: { fg: "var(--status-warning)", bg: "var(--status-warning-bg)" },
  serious: { fg: "var(--status-serious)", bg: "var(--status-serious-bg)" },
  critical: { fg: "var(--status-critical)", bg: "var(--status-critical-bg)" },
  neutral: { fg: "var(--text-secondary)", bg: "var(--surface-1)" },
  brand: { fg: "var(--brand)", bg: "var(--brand-bg)" },
};

export function StatusChip({ tone, children }: { tone: Tone; children: ReactNode }) {
  const c = TONE_COLORS[tone];
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium"
      style={{ color: c.fg, background: c.bg }}
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Domain chip wrappers — real backend enums, not the prototype's mock ones.
// ---------------------------------------------------------------------------
const STANCE_TONE: Record<Stance, Tone> = {
  SUPPORT: "good",
  CAUTION: "warning",
  OPPOSE: "critical",
  NEED_DATA: "neutral",
};

export function StanceChip({ stance }: { stance: Stance }) {
  const { t } = useI18n();
  return <StatusChip tone={STANCE_TONE[stance]}>{t(`stance.${stance}`)}</StatusChip>;
}

/** Roll-up of several findings from one agent into a single chip — worst
 * stance wins (OPPOSE > NEED_DATA/CAUTION > SUPPORT), matching the same
 * "don't average away a real gap" posture used in decision.py's scorecard. */
export function rollupStance(stances: Stance[]): Stance {
  if (stances.some((s) => s === "OPPOSE")) return "OPPOSE";
  if (stances.some((s) => s === "NEED_DATA")) return "NEED_DATA";
  if (stances.some((s) => s === "CAUTION")) return "CAUTION";
  return "SUPPORT";
}

export type Recommendation = "APPROVE" | "APPROVE_WITH_CONDITIONS" | "REFER" | "REJECT" | "NEED_INFO";

const RECOMMENDATION_TONE: Record<Recommendation, Tone> = {
  APPROVE: "good",
  APPROVE_WITH_CONDITIONS: "warning",
  REFER: "serious",
  REJECT: "critical",
  NEED_INFO: "neutral",
};

export function RecommendationChip({ recommendation }: { recommendation: Recommendation }) {
  const { t } = useI18n();
  return <StatusChip tone={RECOMMENDATION_TONE[recommendation]}>{t(`rec.${recommendation}`)}</StatusChip>;
}

// Case state machine (shared/state.py::ALLOWED_TRANSITIONS) — every state
// the backend can actually report, not a prototype-invented queued/approved
// enum.
const CASE_STATE_TONE: Record<string, Tone> = {
  DRAFT: "neutral",
  INTAKE_VALIDATION: "neutral",
  NEED_INFO: "warning",
  ANALYZING: "brand",
  CHALLENGE: "brand",
  READY_FOR_REVIEW: "good",
  SUBMITTED_FOR_APPROVAL: "brand",
  CONDITION_FULFILLMENT: "warning",
  READY_FOR_DISBURSEMENT: "good",
};

export function CaseStatusChip({ state }: { state: string }) {
  const { t } = useI18n();
  const known = state in CASE_STATE_TONE;
  const tone = known ? CASE_STATE_TONE[state] : "neutral";
  return <StatusChip tone={tone}>{known ? t(`state.${state}`) : state}</StatusChip>;
}

// Priority is NOT a backend field (Case has no priority column) — computed
// client-side from SLA age + deal size, see lib/priority.ts. Kept here only
// as the rendering half of that concept.
export type Priority = "urgent" | "high" | "normal";

const PRIORITY_TONE: Record<Priority, Tone> = {
  urgent: "critical",
  high: "warning",
  normal: "neutral",
};

export function PriorityChip({ priority }: { priority: Priority }) {
  const { t } = useI18n();
  return <StatusChip tone={PRIORITY_TONE[priority]}>{t(`priority.${priority}`)}</StatusChip>;
}

// ---------------------------------------------------------------------------
// ConfidenceMeter
// ---------------------------------------------------------------------------
export function ConfidenceMeter({ value, label }: { value: number; label?: string }) {
  const { t } = useI18n();
  const resolvedLabel = label ?? t("confidence.label");
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "var(--status-good)" : pct >= 60 ? "var(--status-warning)" : "var(--status-serious)";
  return (
    <div>
      <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted-2)" }}>
        <span>{resolvedLabel}</span>
        <span className="tabular-nums font-medium" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="mt-1 h-[6px] w-full rounded-full" style={{ background: "var(--surface-1)" }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const VARIANT_STYLE: Record<ButtonVariant, React.CSSProperties> = {
  primary:   { background: "var(--color-orange-600)", color: "#fff" },
  danger:    { background: "var(--status-critical)", color: "#fff" },
  secondary: { background: "#fff", color: "var(--color-orange-600)", border: "1px solid var(--color-orange-600)" },
  ghost:     { background: "transparent", color: "var(--text-secondary)" },
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3.5 py-2 text-sm",
};

export function Button({
  children,
  onClick,
  variant = "secondary",
  size = "md",
  disabled = false,
  className = "",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-40 hover:opacity-90 ${SIZE_CLASS[size]} ${className}`}
      style={VARIANT_STYLE[variant]}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Formatters — locale-aware (vi-VN / en-US). `lang` defaults to "vi" so
// call sites that haven't been threaded through useI18n() yet keep the
// original behavior; components on the translated main screens pass the
// active `lang` from useI18n() explicitly.
// ---------------------------------------------------------------------------
const NUMBER_LOCALE: Record<Lang, string> = { vi: "vi-VN", en: "en-US" };

export function formatVnd(amount: number | null | undefined, lang: Lang = "vi"): string {
  if (amount == null) return "—";
  const locale = NUMBER_LOCALE[lang];
  if (amount >= 1_000_000_000) {
    const value = (amount / 1_000_000_000).toFixed(amount % 1_000_000_000 === 0 ? 0 : 1);
    return `${value} ${translate(lang, "fmt.billion")}`;
  }
  if (amount >= 1_000_000) {
    return `${(amount / 1_000_000).toFixed(0)} ${translate(lang, "fmt.million")}`;
  }
  return `${amount.toLocaleString(locale)} VND`;
}

export function formatDateTime(iso: string, lang: Lang = "vi"): string {
  return new Date(iso).toLocaleTimeString(NUMBER_LOCALE[lang], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatFullDateTime(iso: string, lang: Lang = "vi"): string {
  return new Date(iso).toLocaleString(NUMBER_LOCALE[lang], {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatHours(hours: number, lang: Lang = "vi"): string {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} ${translate(lang, "fmt.minute")}`;
  if (hours < 24) return `${hours.toFixed(1)} ${translate(lang, "fmt.hour")}`;
  return `${(hours / 24).toFixed(1)} ${translate(lang, "fmt.day")}`;
}
