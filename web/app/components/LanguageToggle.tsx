"use client";

/** Segmented VI | EN switch — lives in the Sidebar footer. Flips
 * `useI18n().lang` immediately (no reload); the choice persists via
 * localStorage (see lib/i18n.tsx). */
import { useI18n, type Lang } from "../lib/i18n";

const OPTIONS: { value: Lang; label: string }[] = [
  { value: "vi", label: "VI" },
  { value: "en", label: "EN" },
];

export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();

  return (
    <div
      className="flex items-center gap-1 rounded-lg p-0.5"
      style={{ background: "rgba(255,255,255,0.08)" }}
      role="group"
      aria-label={t("nav.language")}
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === lang;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => setLang(opt.value)}
            className="rounded-md px-2 py-1 text-[11px] font-semibold transition-colors"
            style={
              active
                ? { background: "var(--logo-accent)", color: "#fff" }
                : { background: "transparent", color: "var(--sidebar-fg-muted)" }
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
