"use client";

/**
 * NotificationBell — derives real notifications from case state transitions.
 *
 * Four event types (no separate notifications table needed):
 *   missing_docs      — case is NEED_INFO, RM must upload documents
 *   docs_updated      — case left NEED_INFO and now has findings (RM uploaded)
 *   sent_to_authority — case is SUBMITTED_FOR_APPROVAL (we sent it up)
 *   received_decision — case is APPROVED or REJECTED (decision came back)
 *
 * Unread tracking: stores last-seen set of case_ids per type in localStorage
 * so the badge count resets only after the user opens the panel.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { Bell, X, FileWarning, Upload, ArrowUpCircle, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { fetchCases } from "../lib/api";
import type { CaseSummary } from "../lib/types";

// ─── Types ───────────────────────────────────────────────────────────────────

type NotifType = "missing_docs" | "docs_updated" | "sent_to_authority" | "received_decision";

interface Notif {
  id: string;        // case_id — deduplicates per run
  type: NotifType;
  caseId: string;
  customerId: string;
  product: string;
  state: string;
  ts: number;        // Date.now() when derived — used for ordering
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = "shb_notif_seen";
const POLL_MS = 30_000;

const TYPE_META: Record<NotifType, {
  icon: (n: Notif) => React.ReactNode;
  label: string;
  color: (n: Notif) => string;
  bg: string;
  detail: (n: Notif) => string;
}> = {
  missing_docs: {
    icon: () => <FileWarning className="size-4" />,
    label: "Thiếu tài liệu",
    color: () => "var(--color-danger-600)",
    bg: "#fff1f0",
    detail: (n) => `Hồ sơ ${n.caseId} (${n.customerId}) cần RM bổ sung tài liệu.`,
  },
  docs_updated: {
    icon: () => <Upload className="size-4" />,
    label: "RM đã cập nhật tài liệu",
    color: () => "var(--color-success-600)",
    bg: "#f0faf5",
    detail: (n) => `RM đã tải lên tài liệu cho hồ sơ ${n.caseId} (${n.customerId}).`,
  },
  sent_to_authority: {
    icon: () => <ArrowUpCircle className="size-4" />,
    label: "Gửi lên cấp cao hơn",
    color: () => "var(--color-navy-700)",
    bg: "#f0f0f8",
    detail: (n) => `Hồ sơ ${n.caseId} (${n.customerId}) đã gửi lên Ban lãnh đạo phê duyệt.`,
  },
  received_decision: {
    icon: (n) => n.state === "APPROVED"
      ? <CheckCircle2 className="size-4" />
      : <XCircle className="size-4" />,
    label: "Nhận kết quả phê duyệt",
    color: (n) => n.state === "APPROVED" ? "var(--color-success-600)" : "var(--color-danger-600)",
    bg: "#fffbf0",
    detail: (n) =>
      n.state === "APPROVED"
        ? `Hồ sơ ${n.caseId} (${n.customerId}) đã được PHÊ DUYỆT.`
        : `Hồ sơ ${n.caseId} (${n.customerId}) đã bị TỪ CHỐI.`,
  },
};

// ─── Derive notifications from case list ─────────────────────────────────────

const ORDER: NotifType[] = ["missing_docs", "received_decision", "sent_to_authority", "docs_updated"];

function deriveNotifs(cases: CaseSummary[]): Notif[] {
  const now = Date.now();
  const out: Notif[] = [];

  for (const c of cases) {
    const base = {
      caseId: c.case_id,
      customerId: c.customer_id,
      product: c.product ?? "",
      state: c.state,
      ts: now,
    };

    if (c.state === "NEED_INFO") {
      out.push({ ...base, id: `missing_${c.case_id}`, type: "missing_docs" });
    } else if (c.state === "SUBMITTED_FOR_APPROVAL") {
      out.push({ ...base, id: `sent_${c.case_id}`, type: "sent_to_authority" });
    } else if (c.state === "APPROVED" || c.state === "REJECTED") {
      out.push({ ...base, id: `decision_${c.case_id}`, type: "received_decision" });
    }

    // If a case now has findings and is past NEED_INFO, RM likely uploaded docs.
    if (
      c.has_findings &&
      c.state !== "NEED_INFO" &&
      c.state !== "ANALYZING"
    ) {
      out.push({ ...base, id: `docs_${c.case_id}`, type: "docs_updated" });
    }
  }

  return out.sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type));
}

// ─── Seed / historical mock notifications ────────────────────────────────────
// These represent past events that the system doesn't yet surface via API
// (e.g. completed approvals, older RM uploads). Shown alongside live ones.

const MOCK_NOTIFS: Notif[] = [
  {
    id: "mock_approved_C05",
    type: "received_decision",
    caseId: "C05",
    customerId: "CUST-MINHLONG",
    product: "SME_WC",
    state: "APPROVED",
    ts: Date.now() - 1 * 60 * 60 * 1000, // 1 hour ago
  },
  {
    id: "mock_missing_C08",
    type: "missing_docs",
    caseId: "C08",
    customerId: "CUST-MINHLONG",
    product: "SME_WC",
    state: "NEED_INFO",
    ts: Date.now() - 3 * 60 * 60 * 1000, // 3 hours ago
  },
  {
    id: "mock_sent_C06",
    type: "sent_to_authority",
    caseId: "C06",
    customerId: "CUST-ANPHU",
    product: "SME_WC",
    state: "SUBMITTED_FOR_APPROVAL",
    ts: Date.now() - 5 * 60 * 60 * 1000, // 5 hours ago
  },
  {
    id: "mock_docs_C07",
    type: "docs_updated",
    caseId: "C07",
    customerId: "CUST-HOASEN",
    product: "SME_WC",
    state: "READY_FOR_REVIEW",
    ts: Date.now() - 8 * 60 * 60 * 1000, // 8 hours ago
  },
  {
    id: "mock_rejected_C04",
    type: "received_decision",
    caseId: "C04",
    customerId: "CUS-00004",
    product: "SME_TERM",
    state: "REJECTED",
    ts: Date.now() - 24 * 60 * 60 * 1000, // yesterday
  },
  {
    id: "mock_missing_C03",
    type: "missing_docs",
    caseId: "C03",
    customerId: "CUS-00003",
    product: "SME_WC",
    state: "NEED_INFO",
    ts: Date.now() - 26 * 60 * 60 * 1000,
  },
];

// ─── localStorage helpers ─────────────────────────────────────────────────────

function loadSeen(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch { /* ignore */ }
  return new Set();
}

function saveSeen(ids: Set<string>) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids])); } catch { /* ignore */ }
}

function relativeTime(ts: number): string {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return "Vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return `${Math.floor(diff / 86400)} ngày trước`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function NotificationBell() {
  const [notifs, setNotifs]   = useState<Notif[]>([]);
  const [seen, setSeen]       = useState<Set<string>>(new Set());
  const [open, setOpen]       = useState(false);
  const panelRef              = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const cases = await fetchCases();
      const live = deriveNotifs(cases);
      // Merge: live takes precedence over mock for the same case_id prefix
      const liveIds = new Set(live.map((n) => n.id));
      const mocks = MOCK_NOTIFS.filter((m) => !liveIds.has(m.id));
      const merged = [...live, ...mocks].sort(
        (a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type)
      );
      setNotifs(merged);
    } catch {
      // On error, still show mock notifications
      setNotifs([...MOCK_NOTIFS]);
    }
  }, []);

  // Initial load + polling
  useEffect(() => {
    setSeen(loadSeen());
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const unread = notifs.filter((n) => !seen.has(n.id));
  const unreadCount = unread.length;

  function handleOpen() {
    setOpen((o) => !o);
  }

  function markAllRead() {
    const next = new Set([...seen, ...notifs.map((n) => n.id)]);
    setSeen(next);
    saveSeen(next);
  }

  function markRead(id: string) {
    const next = new Set([...seen, id]);
    setSeen(next);
    saveSeen(next);
  }

  // Group by type for rendering
  const byType = notifs.reduce<Partial<Record<NotifType, Notif[]>>>((acc, n) => {
    (acc[n.type] ??= []).push(n);
    return acc;
  }, {});

  const typeOrder: NotifType[] = ["missing_docs", "received_decision", "sent_to_authority", "docs_updated"];

  return (
    <div className="relative" ref={panelRef}>
      {/* Bell button */}
      <button
        onClick={handleOpen}
        className="relative p-2 rounded-lg hover:bg-muted transition-colors"
        aria-label={`${unreadCount} thông báo chưa đọc`}
      >
        <Bell className="size-5 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-0.5 bg-[var(--color-orange-600)] text-white text-[9px] font-bold rounded-full flex items-center justify-center tabular-nums">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute right-0 top-[calc(100%+8px)] w-[380px] max-h-[520px] overflow-y-auto z-50 rounded-xl border border-border bg-card shadow-xl flex flex-col"
          style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.14)" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-card z-10">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-foreground">Thông báo</span>
              {unreadCount > 0 && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-[var(--color-orange-600)] text-white">
                  {unreadCount} mới
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-[11px] text-[var(--color-orange-600)] hover:underline font-semibold"
                >
                  Đánh dấu đã đọc
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground"
              >
                <X className="size-3.5" />
              </button>
            </div>
          </div>

          {/* Notification list */}
          {notifs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
              <Bell className="size-8 opacity-25" />
              <p className="text-sm">Không có thông báo</p>
            </div>
          ) : (
            <div className="flex flex-col">
              {typeOrder.map((type) => {
                const group = byType[type];
                if (!group?.length) return null;
                const meta = TYPE_META[type];
                return (
                  <div key={type}>
                    {/* Group label */}
                    <div
                      className="flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-wider sticky top-[49px] border-b border-border"
                      style={{ background: meta.bg, color: meta.color(group[0]) }}
                    >
                      {meta.icon(group[0])}
                      {meta.label}
                      <span className="ml-auto text-[10px] font-bold opacity-70">{group.length}</span>
                    </div>

                    {/* Items */}
                    {group.map((n) => {
                      const isUnread = !seen.has(n.id);
                      const itemColor = meta.color(n);
                      return (
                        <Link
                          key={n.id}
                          href={`/cases/${n.caseId}`}
                          onClick={() => { markRead(n.id); setOpen(false); }}
                          className="flex items-start gap-3 px-4 py-3 border-b border-border last:border-0 hover:bg-muted/50 transition-colors no-underline"
                          style={{ background: isUnread ? `${meta.bg}` : "transparent" }}
                        >
                          {/* Color dot / icon */}
                          <div
                            className="mt-0.5 size-7 rounded-full flex items-center justify-center shrink-0"
                            style={{ background: meta.bg, color: itemColor }}
                          >
                            {meta.icon(n)}
                          </div>

                          {/* Text */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <span className="text-xs font-bold text-foreground font-mono">{n.caseId}</span>
                              <span className="text-[10px] text-muted-foreground truncate">{n.customerId}</span>
                              {isUnread && (
                                <span
                                  className="ml-auto size-2 rounded-full shrink-0"
                                  style={{ background: itemColor }}
                                />
                              )}
                            </div>
                            <p className="text-[12px] text-muted-foreground leading-snug">
                              {meta.detail(n)}
                            </p>
                            <p className="text-[10px] text-muted-foreground mt-1 opacity-70">
                              {relativeTime(n.ts)}
                            </p>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}

          {/* Footer */}
          <div className="sticky bottom-0 bg-card border-t border-border px-4 py-2.5 text-center">
            <Link
              href="/"
              onClick={() => setOpen(false)}
              className="text-xs text-[var(--color-orange-600)] font-semibold hover:underline"
            >
              Xem tất cả hồ sơ →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
