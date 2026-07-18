"use client";

/**
 * CreditMemoPanel — in-app preview of the credit memo with PDF export.
 *
 * Flow:
 *   1. "Tạo tờ trình" → fetchCreditMemo (GET /cases/:id/memo) → renders sections
 *   2. "Xuất PDF"      → window.open(/cases/:id/memo/pdf) → browser downloads A4
 *
 * The PDF is rendered server-side by reportlab with Vietnamese DejaVuSans font
 * (api/app/routers/memo.py). The in-app view mirrors the PDF structure so the
 * officer can review before downloading.
 */

import { useState } from "react";
import {
  ClipboardList, FileDown, FileCheck2, CheckCircle2, XCircle,
  AlertTriangle, RefreshCw, ChevronDown, ChevronUp,
} from "lucide-react";
import { fetchCreditMemo } from "../lib/api";
import type { CreditMemo } from "../lib/types";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtVnd(v: unknown): string {
  const n = Number(v);
  if (!v || isNaN(n)) return "—";
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ VND`;
  return `${(n / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} triệu VND`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const REC_META: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  APPROVE: {
    label: "PHÊ DUYỆT",
    color: "var(--color-success-600)",
    bg: "#f0faf5",
    icon: <CheckCircle2 className="size-5" />,
  },
  APPROVE_WITH_CONDITIONS: {
    label: "PHÊ DUYỆT CÓ ĐIỀU KIỆN",
    color: "var(--color-warning-600)",
    bg: "#fffbf0",
    icon: <AlertTriangle className="size-5" />,
  },
  REFER: {
    label: "CHUYỂN XEM XÉT",
    color: "var(--color-warning-600)",
    bg: "#fffbf0",
    icon: <AlertTriangle className="size-5" />,
  },
  REJECT: {
    label: "TỪ CHỐI",
    color: "var(--color-danger-600)",
    bg: "#fff1f0",
    icon: <XCircle className="size-5" />,
  },
  NEED_INFO: {
    label: "YÊU CẦU BỔ SUNG HỒ SƠ",
    color: "var(--color-warning-600)",
    bg: "#fffbf0",
    icon: <AlertTriangle className="size-5" />,
  },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-[var(--color-navy-800)] text-white text-xs font-bold uppercase tracking-wider text-left hover:bg-[var(--color-navy-700)] transition-colors"
      >
        {title}
        {open ? <ChevronUp className="size-3.5 opacity-60" /> : <ChevronDown className="size-3.5 opacity-60" />}
      </button>
      {open && <div className="p-4">{children}</div>}
    </div>
  );
}

function InfoGrid({ rows }: { rows: [string, string][] }) {
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-2">
      {rows.map(([label, value]) => (
        <div key={label}>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
          <p className="text-sm font-semibold text-foreground">{value}</p>
        </div>
      ))}
    </div>
  );
}

function StanceChip({ stance }: { stance: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    SUPPORT:  { label: "Hỗ trợ",    cls: "bg-[var(--color-success-50,#f0faf5)] text-[var(--color-success-600)] border-[var(--color-success-200,#a3d9bc)]" },
    OPPOSE:   { label: "Rủi ro",    cls: "bg-[#fff1f0] text-[var(--color-danger-600)] border-[#ffc9c9]" },
    CAUTION:  { label: "Thận trọng", cls: "bg-[#fffbf0] text-[var(--color-warning-600)] border-[#fde68a]" },
    NEED_DATA:{ label: "Thiếu dữ liệu", cls: "bg-muted text-muted-foreground border-border" },
  };
  const m = map[stance] ?? { label: stance, cls: "bg-muted text-muted-foreground border-border" };
  return (
    <span className={`inline-block text-[10px] font-bold px-1.5 py-0.5 rounded border ${m.cls}`}>
      {m.label}
    </span>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CreditMemoPanel({
  caseId,
  canGenerate,
  onMemoReady,
}: {
  caseId: string;
  canGenerate: boolean;
  onMemoReady?: (ready: boolean) => void;
}) {
  const [memo, setMemo]     = useState<CreditMemo | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchCreditMemo(caseId);
      setMemo(result);
      onMemoReady?.(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function downloadPdf() {
    setDownloading(true);
    try {
      const res = await fetch(`/api/cases/${caseId}/memo/pdf`, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `to-trinh-${caseId}-${new Date().toISOString().slice(0, 10)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloading(false);
    }
  }

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (!memo) {
    return (
      <div className="border border-border rounded-xl bg-card overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 px-5 py-4 border-b border-border">
          <FileCheck2 className="size-4 text-[var(--color-navy-700)]" />
          <h3 className="text-sm font-bold text-foreground">Tờ trình thẩm định tín dụng</h3>
        </div>

        <div className="flex flex-col items-center gap-4 py-10 px-6 text-center">
          <ClipboardList className="size-10 text-muted-foreground opacity-40" />
          <div>
            <p className="text-sm font-semibold text-foreground mb-1">
              {canGenerate ? "Sẵn sàng tạo tờ trình" : "Chưa thể tạo tờ trình"}
            </p>
            <p className="text-xs text-muted-foreground max-w-xs">
              {canGenerate
                ? "AI sẽ tổng hợp kết quả phân tích thành tờ trình thẩm định chuẩn ngân hàng."
                : "Hồ sơ cần hoàn tất phân tích AI trước khi tạo tờ trình."}
            </p>
          </div>
          {error && (
            <p className="text-xs text-[var(--color-danger-600)] bg-[#fff1f0] border border-[#ffc9c9] rounded-lg px-3 py-2 max-w-xs">
              {error}
            </p>
          )}
          <button
            onClick={generate}
            disabled={!canGenerate || loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-45 disabled:cursor-not-allowed"
            style={{ background: canGenerate ? "var(--color-orange-600)" : undefined }}
          >
            {loading
              ? <><RefreshCw className="size-4 animate-spin" /> Đang tạo…</>
              : <><FileCheck2 className="size-4" /> Tạo tờ trình</>}
          </button>
        </div>
      </div>
    );
  }

  // ── Memo preview ────────────────────────────────────────────────────────────
  const recMeta = REC_META[memo.recommendation] ?? REC_META.REFER;

  // Parse sections back into structured data
  // The JSON endpoint returns flat sections; reconstruct what we need
  const infoSection   = memo.sections.find(s => s.title.includes("Thông tin"));
  const agentSections = memo.sections.filter(s =>
    !s.title.includes("Thông tin") &&
    !s.title.includes("Kết luận") &&
    !s.title.includes("Điều kiện")
  );
  const conclusionSection = memo.sections.find(s => s.title.includes("Kết luận"));
  const conditionSection  = memo.sections.find(s => s.title.includes("Điều kiện"));

  return (
    <div className="border border-border rounded-xl bg-card overflow-hidden flex flex-col">

      {/* ── Document header ─────────────────────────────────────────────────── */}
      <div className="bg-[var(--color-navy-800)] text-white px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] text-[var(--color-navy-300)] uppercase tracking-widest mb-1">
              Ngân hàng TMCP Sài Gòn – Hà Nội (SHB)
            </p>
            <h2 className="text-base font-bold leading-tight mb-2">
              TỜ TRÌNH THẨM ĐỊNH TÍN DỤNG
            </h2>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--color-navy-300)]">
              <span>Hồ sơ: <span className="text-white font-mono font-semibold">{memo.case_id}</span></span>
              <span>Lập ngày: <span className="text-white">{fmtDate(memo.prepared_at)}</span></span>
            </div>
          </div>
          {/* Action buttons */}
          <div className="flex flex-col gap-2 shrink-0">
            <button
              onClick={downloadPdf}
              disabled={downloading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--color-orange-600)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {downloading
                ? <><RefreshCw className="size-3.5 animate-spin" /> Đang xuất…</>
                : <><FileDown className="size-3.5" /> Xuất PDF</>}
            </button>
            <button
              onClick={generate}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/10 text-white hover:bg-white/20 transition-colors disabled:opacity-50"
            >
              {loading
                ? <><RefreshCw className="size-3.5 animate-spin" /> Đang tạo…</>
                : <><RefreshCw className="size-3.5" /> Làm mới</>}
            </button>
          </div>
        </div>
      </div>

      {/* ── Recommendation banner ────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-6 py-3 border-b border-border"
        style={{ background: recMeta.bg }}
      >
        <span style={{ color: recMeta.color }}>{recMeta.icon}</span>
        <div>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Khuyến nghị AI</p>
          <p className="text-sm font-extrabold" style={{ color: recMeta.color }}>{recMeta.label}</p>
        </div>
      </div>

      {/* ── Body ─────────────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 p-5">

        {/* I. Thông tin khoản vay */}
        {infoSection && (
          <SectionBlock title="I. Thông tin khách hàng & khoản vay">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              {infoSection.content.map((line) => {
                const [label, ...rest] = line.split(": ");
                return (
                  <div key={label}>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
                    <p className="text-sm font-semibold text-foreground">{rest.join(": ") || "—"}</p>
                  </div>
                );
              })}
            </div>
          </SectionBlock>
        )}

        {/* Agent finding sections */}
        {agentSections.map((sec) => (
          <SectionBlock key={sec.title} title={sec.title}>
            <div className="flex flex-col gap-0 divide-y divide-border">
              {sec.content.map((line, i) => {
                // Format: [KEY] claim (STANCE, conf%)
                const match = line.match(/^\[(.+?)\] (.+?) \((.+?), (\d+)%\)$/);
                if (match) {
                  const [, key, claim, stance, conf] = match;
                  return (
                    <div key={i} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                      <span className="text-[10px] font-mono text-muted-foreground shrink-0 mt-0.5 w-28 truncate">{key}</span>
                      <p className="flex-1 text-xs text-foreground leading-snug">{claim}</p>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <StanceChip stance={stance} />
                        <span className="text-[10px] text-muted-foreground tabular-nums">{conf}%</span>
                      </div>
                    </div>
                  );
                }
                return (
                  <p key={i} className="py-2 text-xs text-foreground leading-snug first:pt-0">{line}</p>
                );
              })}
            </div>
          </SectionBlock>
        ))}

        {/* Conditions precedent */}
        {conditionSection && conditionSection.content.length > 0 && (
          <SectionBlock title="IX. Điều kiện tiên quyết giải ngân">
            <ol className="flex flex-col gap-2 list-decimal list-inside">
              {conditionSection.content.map((cond, i) => (
                <li key={i} className="text-xs text-foreground leading-snug">{cond}</li>
              ))}
            </ol>
          </SectionBlock>
        )}

        {/* Conclusion */}
        {conclusionSection && (
          <SectionBlock title="X. Kết luận & kiến nghị">
            <div className="flex flex-col gap-2">
              {conclusionSection.content.map((line, i) => {
                const [label, ...rest] = line.split(": ");
                return (
                  <div key={i} className="flex items-baseline gap-2">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-wide w-32 shrink-0">{label}:</span>
                    <span className="text-xs font-semibold text-foreground">{rest.join(": ") || "—"}</span>
                  </div>
                );
              })}
            </div>
          </SectionBlock>
        )}

        {/* Signature block */}
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="bg-[var(--color-navy-800)] text-white px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
            Chữ ký xác nhận
          </div>
          <div className="grid grid-cols-3 divide-x divide-border">
            {[
              { role: "Cán bộ thẩm định", name: "Nguyễn Văn An" },
              { role: "Trưởng phòng thẩm định", name: "" },
              { role: "Giám đốc phê duyệt", name: "" },
            ].map(({ role, name }) => (
              <div key={role} className="p-4 text-center">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-6">{role}</p>
                <div className="h-px bg-border mb-2" />
                <p className="text-xs text-muted-foreground italic">{name || "(Ký, ghi rõ họ tên)"}</p>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-xs text-[var(--color-danger-600)] bg-[#fff1f0] border border-[#ffc9c9] rounded-lg px-3 py-2">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
