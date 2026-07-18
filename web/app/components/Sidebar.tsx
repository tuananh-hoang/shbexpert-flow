"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, LayoutDashboard, FolderOpen, Bot, CheckSquare, BarChart2, Settings } from "lucide-react";
import { cn } from "../lib/utils";

interface NavItem {
  icon: React.ReactNode;
  label: string;
  href?: string;
  active?: boolean;
  disabled?: boolean;
  hasChildren?: boolean;
  children?: { label: string; href: string; active?: boolean }[];
}

export function Sidebar() {
  const pathname = usePathname();
  const onCasePage  = pathname?.startsWith("/cases/") ?? false;
  const onQueuePage = pathname === "/";

  const navItems: NavItem[] = [
    {
      icon: <LayoutDashboard className="size-4.5" />,
      label: "Dashboard",
      href: "/",
      active: onQueuePage,
    },
    {
      icon: <FolderOpen className="size-4.5" />,
      label: "Hồ sơ tín dụng",
      disabled: true,
      hasChildren: true,
    },
    {
      icon: <Bot className="size-4.5" />,
      label: "AI Review",
      active: onCasePage,
      hasChildren: true,
      children: onCasePage && pathname
        ? [{ label: pathname.split("/").pop() ?? "Hồ sơ", href: pathname, active: true }]
        : [],
    },
    {
      icon: <CheckSquare className="size-4.5" />,
      label: "Decision Hub",
      disabled: true,
    },
    {
      icon: <BarChart2 className="size-4.5" />,
      label: "Báo cáo",
      disabled: true,
      hasChildren: true,
    },
    {
      icon: <Settings className="size-4.5" />,
      label: "Cài đặt",
      disabled: true,
    },
  ];

  return (
    <aside className="sidebar flex flex-col" style={{ minHeight: "100vh" }}>
      {/* Logo */}
      <div className="sidebar-logo">
        <div
          className="size-8 rounded-lg flex items-center justify-center text-white font-extrabold text-sm shrink-0"
          style={{ background: "var(--color-orange-600)" }}
        >
          S
        </div>
        <div>
          <p className="text-sm font-bold leading-tight" style={{ color: "var(--text-on-brand)" }}>
            SHBExpert AI
          </p>
          <p className="text-[10px] leading-tight" style={{ color: "rgba(255,255,255,0.55)" }}>
            Nền tảng tín dụng doanh nghiệp
          </p>
        </div>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav flex-1 py-2">
        {navItems.map(({ icon, label, href, active, disabled, hasChildren, children }) => (
          <div key={label}>
            {/* Main item */}
            {href && !disabled ? (
              <Link
                href={href}
                className={cn(
                  "sidebar-nav-item flex items-center gap-3",
                  active && "active"
                )}
              >
                <span className="shrink-0">{icon}</span>
                <span className="flex-1">{label}</span>
                {hasChildren && <ChevronRight className="size-3.5 opacity-50" />}
              </Link>
            ) : (
              <div
                className={cn(
                  "sidebar-nav-item flex items-center gap-3",
                  active && "active",
                  disabled && "disabled"
                )}
                title={disabled ? "Sắp có" : undefined}
              >
                <span className="shrink-0">{icon}</span>
                <span className="flex-1">{label}</span>
                {hasChildren && <ChevronRight className={cn("size-3.5 opacity-50", active && "rotate-90")} />}
                {disabled && (
                  <span className="sidebar-nav-badge text-[9px] px-1.5 py-0.5 rounded-full font-bold">Sắp có</span>
                )}
              </div>
            )}

            {/* Child items (when active and has children) */}
            {active && children && children.length > 0 && (
              <div className="ml-8 mt-0.5 mb-1 flex flex-col gap-0.5">
                {children.map((c) => (
                  <Link
                    key={c.href}
                    href={c.href}
                    className={cn(
                      "text-xs px-3 py-1.5 rounded-md transition-colors truncate",
                      c.active
                        ? "bg-[var(--color-navy-800)] text-white font-semibold"
                        : "text-[rgba(255,255,255,0.6)] hover:text-white hover:bg-[var(--color-navy-800)]"
                    )}
                  >
                    {c.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
        <div className="sidebar-footer flex items-center gap-3 cursor-pointer hover:bg-[var(--color-navy-800)] transition-colors rounded-lg mx-2 mb-2 px-2 py-2">
          <div className="sidebar-avatar shrink-0">NA</div>
          <div className="flex-1 min-w-0">
            <div className="sidebar-officer-name text-xs font-semibold truncate">CBTD: Nguyễn Văn An</div>
            <div className="sidebar-officer-role text-[10px] truncate opacity-70">Phòng Khách hàng Doanh nghiệp</div>
            <div className="text-[10px] opacity-50 truncate">Chi nhánh Hà Nội</div>
          </div>
          <ChevronRight className="size-3.5 opacity-50 shrink-0" />
        </div>

        <button className="w-full flex items-center justify-center gap-2 py-2.5 text-xs opacity-50 hover:opacity-80 transition-opacity"
          style={{ color: "rgba(255,255,255,0.7)", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <ChevronRight className="size-3.5 rotate-180" />
          Thu gọn menu
        </button>
      </div>
    </aside>
  );
}
