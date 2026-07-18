"use client";

/**
 * Fixed left sidebar (FE_Dashboard.jpeg mockup) — persistent across every
 * page via web/app/layout.tsx, not just the case Dashboard.
 *
 * Only "Dashboard" (the currently-open case, if any) and "Applications"
 * (the Queue, web/app/page.tsx) correspond to real pages. Tasks /
 * Documents / Reports / Settings / Audit Trail don't exist yet — shown
 * disabled with a "Sắp có" badge rather than linking to a 404, same
 * honesty convention as the PlaceholderWidget cards on the case
 * dashboard (web/app/cases/[caseId]/page.tsx).
 *
 * "Dashboard" itself isn't a clickable link: there's no page that means
 * "dashboard with no case selected" in this app's actual routing
 * (`/` is the Queue, `/cases/[id]` is a specific case) — it just
 * highlights when a case is open, showing where you are rather than
 * linking somewhere new.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

const DISABLED_ITEMS = ["Tasks", "Documents", "Reports", "Audit Trail", "Settings"];

export function Sidebar() {
  const pathname = usePathname();
  const onCasePage = pathname?.startsWith("/cases/") ?? false;
  const onQueuePage = pathname === "/";

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="sidebar-logo-mark">S</span>
        SHBExpert AI
      </div>

      <nav className="sidebar-nav">
        <div className={`sidebar-nav-item${onCasePage ? " active" : ""}`}>Dashboard</div>
        <Link href="/" className={`sidebar-nav-item${onQueuePage ? " active" : ""}`}>
          Applications
        </Link>
        {DISABLED_ITEMS.map((label) => (
          <div key={label} className="sidebar-nav-item disabled" title="Chưa có trang này">
            {label}
            <span className="sidebar-nav-badge">Sắp có</span>
          </div>
        ))}
      </nav>

      {/* Danh tính demo tĩnh — hệ thống chưa có auth thật, khớp
          Actor(type="USER", id="credit_officer_demo") backend đã dùng
          cho mọi hành động HITL (api/app/routers/cases.py). */}
      <div className="sidebar-footer">
        <div className="sidebar-avatar">NA</div>
        <div>
          <div className="sidebar-officer-name">Nguyễn Văn A</div>
          <div className="sidebar-officer-role">Credit Officer</div>
        </div>
      </div>
    </aside>
  );
}
