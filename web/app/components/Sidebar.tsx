"use client";

/**
 * Fixed left sidebar — restyled per the dashmint_ai-trang prototype's
 * `Shell.tsx` (brand block + nav + user footer, violet/token-driven), but
 * routing logic is UNCHANGED from the original: only "Dashboard" (current
 * case, highlight-only) and "Applications" (the Queue, `/`) are real;
 * everything else stays a disabled "Sắp có" placeholder rather than a
 * prototype-style HashRouter with routes that don't exist here (this app
 * is Next.js App Router, not react-router — no router swap, just a
 * visual reskin of the same two real routes).
 *
 * Navy/orange palette + EN/VI LanguageToggle added per the FE_flow.jpeg
 * redesign — see globals.css's --sidebar-* / --logo-accent tokens.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { GitCompareArrows, LayoutGrid, UserCircle2 } from "lucide-react";
import { useI18n } from "../lib/i18n";
import { LanguageToggle } from "./LanguageToggle";

const DISABLED_KEYS = ["nav.tasks", "nav.documents", "nav.reports", "nav.auditTrail", "nav.settings"] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { t } = useI18n();
  const onCasePage = pathname?.startsWith("/cases/") ?? false;
  const onQueuePage = pathname === "/";

  return (
    <aside
      className="flex h-screen w-60 shrink-0 flex-col px-3 py-5"
      style={{
        background: "linear-gradient(180deg, var(--sidebar-bg), var(--sidebar-bg-2))",
        position: "sticky",
        top: 0,
      }}
    >
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-lg"
          style={{ background: "var(--logo-accent)", color: "#fff" }}
        >
          <GitCompareArrows size={16} />
        </span>
        <div>
          <div className="text-sm font-semibold" style={{ color: "var(--sidebar-fg)" }}>
            {t("nav.appName")}
          </div>
          <div className="text-xs" style={{ color: "var(--sidebar-fg-muted)" }}>
            {t("nav.tagline")}
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        <div
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium"
          style={
            onCasePage
              ? { background: "var(--sidebar-active-bg)", color: "#fff" }
              : { color: "var(--sidebar-fg-muted)" }
          }
        >
          <LayoutGrid size={16} />
          {t("nav.dashboard")}
        </div>
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium"
          style={
            onQueuePage
              ? { background: "var(--sidebar-active-bg)", color: "#fff" }
              : { color: "var(--sidebar-fg-muted)" }
          }
        >
          <LayoutGrid size={16} />
          {t("nav.applications")}
        </Link>
        {DISABLED_KEYS.map((key) => (
          <div
            key={key}
            className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm font-medium opacity-50"
            style={{ color: "var(--sidebar-fg-muted)" }}
            title={t("nav.comingSoonTitle")}
          >
            {t(key)}
            <span
              className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
              style={{ background: "rgba(255,255,255,0.14)", color: "var(--sidebar-fg-muted)" }}
            >
              {t("nav.comingSoon")}
            </span>
          </div>
        ))}
      </nav>

      <div className="px-2 pb-3">
        <LanguageToggle />
      </div>

      {/* Danh tính demo tĩnh — hệ thống chưa có auth thật, khớp
          Actor(type="USER", id="credit_officer_demo") backend đã dùng
          cho mọi hành động HITL (api/app/routers/cases.py). */}
      <div className="flex items-center gap-2.5 border-t px-2 pt-3" style={{ borderColor: "rgba(255,255,255,0.12)" }}>
        <UserCircle2 size={28} style={{ color: "var(--sidebar-fg-muted)" }} />
        <div>
          <div className="text-xs font-medium" style={{ color: "var(--sidebar-fg)" }}>
            {t("nav.officerName")}
          </div>
          <div className="text-xs" style={{ color: "var(--sidebar-fg-muted)" }}>
            {t("nav.officerRole")}
          </div>
        </div>
      </div>
    </aside>
  );
}
