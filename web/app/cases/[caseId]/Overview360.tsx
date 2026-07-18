"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import {
  Scale, Banknote, BarChart3, CreditCard, Home, Clock,
  Building, Users, ClipboardList, CheckCircle2,
} from "lucide-react";
import type { CaseDetail } from "../../lib/types";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Separator } from "../../components/ui/separator";
import { cn } from "../../lib/utils";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtNum(n: number): string {
  return n.toLocaleString("vi-VN");
}

function fmtVnd(n: number): string {
  return `${(n / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 3 })} tỷ VND`;
}

function verdictVariant(v: string): "success" | "warning" | "danger" {
  if (v === "Tốt") return "success";
  if (v === "Trung bình") return "warning";
  return "danger";
}

// ─── Mock static data (replaced as API expands) ───────────────────────────────

const MOCK_COMPANY = {
  type:          "Công ty TNHH 2 thành viên",
  founded:       "12/08/2012",
  charter_vnd:   30_000_000_000,
  address:       "Số 56, Đường Phạm Hùng, P. Mỹ Đình 1, Q. Nam Từ Liêm, Hà Nội",
  phone:         "024 3798 1234",
  email:         "info@minhphat.com.vn",
};

const MOCK_PERSONS = [
  { role: "Giám đốc",       name: "Ông Trần Văn Nam",   dob: "15/05/1978", cccd: "001078012345" },
  { role: "Kế toán trưởng", name: "Bà Nguyễn Thị Lan",  dob: "22/09/1985", cccd: "001185022345" },
];

const MOCK_PROFILE = {
  industry:     "Sản xuất bao bì giấy",
  vsic:         "1721",
  employees:    128,
  relationship: "3 năm 2 tháng",
  avg_revenue:  "82,3 tỷ VND/năm",
};

const MOCK_FINANCIAL_TABLE = [
  { label: "Doanh thu thuần",    y22: 68_520_000_000, y23: 81_430_000_000, y24: 94_250_000_000, ttm: 36_120_000_000, isRatio: false },
  { label: "Lợi nhuận EBITDA",  y22:  6_820_000_000, y23:  8_410_000_000, y24: 10_320_000_000, ttm:  4_120_000_000, isRatio: false },
  { label: "Lợi nhuận sau thuế",y22:  3_860_000_000, y23:  4_590_000_000, y24:  5_610_000_000, ttm:  2_180_000_000, isRatio: false },
  { label: "DSCR (TB)",          y22: 1.42,           y23: 1.55,           y24: 1.68,           ttm: null,           isRatio: true  },
  { label: "Dòng tiền HĐKD ròng",y22:5_120_000_000,  y23:  6_430_000_000, y24:  7_980_000_000, ttm:  3_150_000_000, isRatio: false },
];

const MOCK_COLLATERAL = {
  type:         "Nhà xưởng, QSDD và máy móc thiết bị",
  value_vnd:    22_500_000_000,
  date:         "12/05/2025",
  proposed_pct: 60.0,
  haircut_vnd:  18_000_000_000,
};

const COLLATERAL_MIX = [
  { name: "Nhà xưởng & QSDD",     pct: 60, color: "var(--color-navy-700)" },
  { name: "Máy móc thiết bị",      pct: 30, color: "var(--color-success-600)" },
  { name: "Phương tiện vận tải",   pct: 10, color: "var(--color-warning-600)" },
];

const SCORE_DIMENSIONS = [
  { icon: <Scale className="size-3.5" />,      label: "Năng lực pháp lý",     score: 90 },
  { icon: <Banknote className="size-3.5" />,   label: "Năng lực tài chính",    score: 68 },
  { icon: <BarChart3 className="size-3.5" />,  label: "Hiệu quả kinh doanh",   score: 70 },
  { icon: <CreditCard className="size-3.5" />, label: "Dòng tiền & trả nợ",    score: 72 },
  { icon: <Home className="size-3.5" />,       label: "Tài sản bảo đảm",       score: 66 },
  { icon: <Clock className="size-3.5" />,      label: "Lịch sử quan hệ",       score: 80 },
];

function scoreVerdict(s: number): string {
  return s >= 75 ? "Tốt" : s >= 60 ? "Trung bình" : "Kém";
}

// ─── KYC Card ─────────────────────────────────────────────────────────────────

function KYCCard({ caseDetail }: { caseDetail: CaseDetail }) {
  return (
    <Card className="py-0 gap-0 flex-1 min-w-0 overflow-hidden">
      <CardHeader className="pt-4 pb-3 px-5">
        <CardTitle className="text-sm">1. KYC &amp; Chân dung</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-0">
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">

          {/* Legal info */}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Building className="size-3.5 text-muted-foreground shrink-0" />
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Thông tin pháp lý</p>
            </div>
            <dl className="flex flex-col gap-2">
              {[
                { k: "Loại hình",       v: MOCK_COMPANY.type },
                { k: "Ngày thành lập",  v: MOCK_COMPANY.founded },
                { k: "Vốn điều lệ",     v: fmtVnd(MOCK_COMPANY.charter_vnd) },
                { k: "Địa chỉ trụ sở",  v: MOCK_COMPANY.address },
                { k: "Điện thoại",      v: MOCK_COMPANY.phone },
                { k: "Email",           v: MOCK_COMPANY.email },
              ].map(({ k, v }) => (
                <div key={k} className="grid grid-cols-[auto_1fr] gap-x-2">
                  <dt className="text-[11px] text-muted-foreground font-medium whitespace-nowrap">{k}</dt>
                  <dd className="text-[11px] text-foreground font-semibold text-right break-words">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Legal representatives */}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users className="size-3.5 text-muted-foreground shrink-0" />
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Đại diện pháp luật</p>
            </div>
            <div className="flex flex-col gap-4">
              {MOCK_PERSONS.map((person) => (
                <div key={person.name} className="flex items-start gap-3">
                  <div className="size-10 rounded-full bg-[var(--color-navy-100)] flex items-center justify-center text-sm font-bold text-[var(--color-navy-700)] shrink-0">
                    {person.name.split(" ").pop()?.charAt(0) ?? "?"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-foreground">{person.name}</p>
                    <p className="text-[11px] text-muted-foreground">Chức vụ: {person.role}</p>
                    <p className="text-[11px] text-muted-foreground">Sinh ngày: {person.dob}</p>
                    <p className="text-[11px] text-muted-foreground">CCCD: {person.cccd}</p>
                    <div className="flex items-center gap-1 mt-1.5">
                      <CheckCircle2 className="size-3 text-[var(--color-success-600)] shrink-0" />
                      <span className="text-[11px] font-semibold text-[var(--color-success-600)]">Đã xác thực eKYC</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Company profile */}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <ClipboardList className="size-3.5 text-muted-foreground shrink-0" />
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Chân dung doanh nghiệp</p>
            </div>
            <dl className="flex flex-col gap-2">
              {[
                { k: "Ngành nghề chính",   v: MOCK_PROFILE.industry },
                { k: "Mã ngành (VSIC)",    v: MOCK_PROFILE.vsic },
                { k: "Quy mô lao động",    v: `${MOCK_PROFILE.employees} người` },
                { k: "Thời gian quan hệ",  v: MOCK_PROFILE.relationship },
                { k: "Doanh số bình quân", v: MOCK_PROFILE.avg_revenue },
              ].map(({ k, v }) => (
                <div key={k} className="grid grid-cols-[auto_1fr] gap-x-2">
                  <dt className="text-[11px] text-muted-foreground font-medium whitespace-nowrap">{k}</dt>
                  <dd className="text-[11px] text-foreground font-semibold text-right">{v}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between mt-1">
                <span className="text-[11px] text-muted-foreground font-medium">CIC</span>
                <Badge variant="success" className="rounded-full text-[10px]">Tốt</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground font-medium">KYC</span>
                <Badge variant="success" className="rounded-full text-[10px]">Đã hoàn tất</Badge>
              </div>
            </dl>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Credit Request + Timeline ────────────────────────────────────────────────

const TIMELINE_STEPS = [
  "Tạo hồ sơ",
  "Đang thẩm định",
  "Trình phê duyệt",
  "Phê duyệt",
  "Giải ngân",
];

function getTimelineActive(state: string): number {
  if (state === "ANALYZING")               return 1;
  if (state === "READY_FOR_REVIEW")        return 2;
  if (state === "SUBMITTED_FOR_APPROVAL")  return 3;
  if (state === "APPROVED")               return 4;
  if (state === "REJECTED")               return 4;
  return 1;
}

function CreditRequestCard({ caseDetail }: { caseDetail: CaseDetail }) {
  const amountVnd = caseDetail.requested_facility?.amount_vnd as number | undefined;
  const tenorMonths = caseDetail.requested_facility?.tenor_months as number | undefined;
  const purpose = caseDetail.requested_facility?.purpose as string | undefined;
  const activeStep = getTimelineActive(caseDetail.state);

  const mockTimestamps: Record<number, string> = {
    0: "16/05/2025 09:30",
    1: "16/05/2025 10:15",
  };

  return (
    <Card className="py-0 gap-0 w-[300px] shrink-0">
      <CardHeader className="pt-4 pb-3 px-5">
        <CardTitle className="text-sm">2. Credit Request</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-4 flex flex-col gap-4">
        {/* Loan details */}
        <div>
          <p className="text-[11px] text-muted-foreground font-semibold mb-1">Mục đích vay</p>
          <p className="text-xs text-foreground leading-snug mb-3">
            {purpose ?? "Bổ sung vốn lưu động phục vụ sản xuất kinh doanh và mua nguyên vật liệu."}
          </p>

          <p className="text-[11px] text-muted-foreground font-semibold mb-1">Số tiền đề nghị cấp tín dụng</p>
          {amountVnd != null ? (
            <>
              <p className="text-xl font-extrabold text-[var(--color-navy-700)] font-[var(--font-display)] leading-tight">
                {fmtNum(amountVnd)} VND
              </p>
              <p className="text-[11px] text-[var(--color-navy-600)] mt-0.5">
                ({amountVnd === 15_000_000_000 ? "Mười lăm tỷ đồng" : fmtVnd(amountVnd)})
              </p>
            </>
          ) : (
            <p className="text-base font-bold text-muted-foreground">—</p>
          )}

          <div className="flex flex-col gap-1.5 mt-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Thời hạn vay</span>
              <span className="font-bold text-foreground">{tenorMonths ?? 24} tháng</span>
            </div>
            <div className="flex items-start justify-between text-xs gap-2">
              <span className="text-muted-foreground whitespace-nowrap">Loại sản phẩm</span>
              <span className="font-semibold text-[var(--color-navy-600)] text-right leading-snug">
                {caseDetail.product ?? "Cho vay bổ sung vốn lưu động"}
              </span>
            </div>
          </div>
        </div>

        <Separator />

        {/* Vertical timeline */}
        <div>
          <p className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider mb-3">Tiến trình hồ sơ</p>
          <div className="flex flex-col">
            {TIMELINE_STEPS.map((step, i) => {
              const isDone    = i < activeStep;
              const isActive  = i === activeStep;
              const isPending = i > activeStep;
              const isLast    = i === TIMELINE_STEPS.length - 1;
              return (
                <div key={step} className="flex items-start gap-3">
                  {/* Left: circle + connector */}
                  <div className="flex flex-col items-center shrink-0">
                    <div className={cn(
                      "size-5 rounded-full flex items-center justify-center text-[10px] font-bold border-2 shrink-0",
                      isDone    && "bg-[var(--color-success-600)] border-[var(--color-success-600)] text-white",
                      isActive  && "bg-[var(--color-navy-700)] border-[var(--color-navy-700)] text-white",
                      isPending && "bg-card border-border text-muted-foreground",
                    )}>
                      {isDone ? "✓" : isActive ? "" : ""}
                      {isActive && <span className="size-2 rounded-full bg-white" />}
                    </div>
                    {!isLast && (
                      <div className={cn(
                        "w-0.5 h-8 mt-0.5",
                        isDone ? "bg-[var(--color-success-600)]" : "bg-border"
                      )} />
                    )}
                  </div>

                  {/* Right: content */}
                  <div className="flex-1 min-w-0 pb-2">
                    <p className={cn(
                      "text-xs font-semibold leading-tight",
                      isDone   && "text-foreground",
                      isActive && "text-[var(--color-navy-700)] font-bold",
                      isPending && "text-muted-foreground",
                    )}>
                      {step}
                    </p>
                    {mockTimestamps[i] && (
                      <p className="text-[10px] text-muted-foreground mt-0.5">{mockTimestamps[i]}</p>
                    )}
                    {mockTimestamps[i] && (
                      <p className="text-[10px] text-muted-foreground">Nguyễn Văn An</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Financial table ──────────────────────────────────────────────────────────

function FinancialTable({ dscrReal }: { dscrReal: number | undefined }) {
  // Inject real DSCR value if available
  const rows = MOCK_FINANCIAL_TABLE.map((r) =>
    r.label === "DSCR (TB)" && dscrReal != null
      ? { ...r, ttm: dscrReal }
      : r
  );

  function cell(v: number, isRatio: boolean): string {
    if (isRatio) return v.toFixed(2);
    return fmtNum(v);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-bold text-foreground">Hiệu quả kinh doanh</p>
        <p className="text-[10px] text-muted-foreground">Số liệu BCTC kiểm toán &nbsp;·&nbsp; Đơn vị: VND</p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted">
              <th className="px-3 py-2 text-left font-bold text-muted-foreground whitespace-nowrap">Chỉ tiêu</th>
              {["2022", "2023", "2024", "TTM 04/2025"].map((y) => (
                <th key={y} className="px-3 py-2 text-right font-bold text-muted-foreground whitespace-nowrap">{y}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.label} className={cn("border-t border-border", i % 2 === 1 && "bg-muted/30")}>
                <td className="px-3 py-2 font-medium text-foreground whitespace-nowrap">{r.label}</td>
                <td className="px-3 py-2 text-right tabular-nums text-foreground">{cell(r.y22, r.isRatio)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-foreground">{cell(r.y23, r.isRatio)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-foreground font-semibold">{cell(r.y24, r.isRatio)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-[var(--color-navy-700)] font-bold">
                  {r.ttm != null ? cell(r.ttm, r.isRatio) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-muted-foreground mt-1.5 italic">
        Ghi chú: TTM 04/2025 là số liệu lũy kế 12 tháng đến 30/04/2025
      </p>
    </div>
  );
}

// ─── Collateral section ───────────────────────────────────────────────────────

function CollateralSection({ ltvPct }: { ltvPct: number | null }) {
  const ltv = ltvPct ?? Math.round((1 / (MOCK_COLLATERAL.value_vnd / MOCK_COLLATERAL.value_vnd)) * 100);
  const displayLtv = ltvPct != null ? `${ltvPct}%` : "66,7%";
  const ltvColor = (ltvPct ?? 67) < 65
    ? "var(--color-success-600)"
    : (ltvPct ?? 67) < 80
    ? "var(--color-warning-600)"
    : "var(--color-danger-600)";

  const pieData = COLLATERAL_MIX.map((m) => ({
    name: m.name,
    value: m.pct,
    fill: m.color,
  }));
  const totalVnd = MOCK_COLLATERAL.value_vnd;

  return (
    <div className="flex gap-4 flex-wrap">
      {/* Collateral details */}
      <div className="flex-1 min-w-[200px]">
        <p className="text-xs font-bold text-foreground mb-2">Tài sản bảo đảm</p>
        <dl className="flex flex-col gap-2">
          {[
            { k: "Loại tài sản",             v: MOCK_COLLATERAL.type, normal: true },
            { k: "Giá trị định giá (BC TĐG)", v: fmtNum(totalVnd) + " VND", normal: true },
            { k: "Ngày định giá",             v: MOCK_COLLATERAL.date, normal: true },
            { k: "LTV snapshot",              v: displayLtv, colored: ltvColor },
            { k: "Tỷ lệ cho vay đề xuất",    v: `${MOCK_COLLATERAL.proposed_pct.toFixed(1)}%`, normal: true },
            { k: "Giá trị TSBD sau haircut",  v: fmtNum(MOCK_COLLATERAL.haircut_vnd) + " VND", normal: true },
          ].map(({ k, v, colored, normal }) => (
            <div key={k} className="flex items-start justify-between gap-3">
              <dt className="text-[11px] text-muted-foreground font-medium whitespace-nowrap shrink-0">{k}</dt>
              <dd className="text-[11px] font-bold text-right" style={{ color: colored ?? "inherit" }}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Donut chart */}
      <div className="flex-none w-[200px]">
        <p className="text-xs font-bold text-foreground mb-2">Cơ cấu tài sản bảo đảm</p>
        <div className="relative h-[140px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="40%" cy="50%"
                innerRadius={40} outerRadius={58}
                paddingAngle={2}
                dataKey="value"
              >
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 11, borderRadius: 6, border: "none", background: "var(--color-gray-900)", color: "#fff" }}
                formatter={(v: number, n: string) => [`${v}%`, n]}
              />
            </PieChart>
          </ResponsiveContainer>
          {/* Center label */}
          <div className="absolute top-1/2 -translate-y-1/2" style={{ left: "calc(40% - 40px)", width: 80 }}>
            <p className="text-center text-xs font-extrabold text-foreground">
              {(totalVnd / 1_000_000_000).toFixed(1)}
            </p>
            <p className="text-center text-[10px] text-muted-foreground">tỷ VND</p>
          </div>
        </div>
        {/* Legend */}
        <div className="flex flex-col gap-1.5 mt-1">
          {COLLATERAL_MIX.map((m) => (
            <div key={m.name} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <div className="size-2 rounded-full shrink-0" style={{ background: m.color }} />
                <span className="text-[10px] text-muted-foreground">{m.name}</span>
              </div>
              <span className="text-[10px] font-bold text-foreground">{m.pct}%</span>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground mt-2">
          Tổng giá trị định giá: {fmtNum(totalVnd)} VND
        </p>
      </div>
    </div>
  );
}

// ─── Score summary sidebar ────────────────────────────────────────────────────

function ScoreSidebar({ compositePct }: { compositePct: number | null }) {
  const scores = SCORE_DIMENSIONS;
  const composite = compositePct ?? Math.round(scores.reduce((s, d) => s + d.score, 0) / scores.length);
  const overall = scoreVerdict(composite);

  return (
    <Card className="py-0 gap-0 w-full">
      <CardHeader className="pt-4 pb-3 px-4">
        <CardTitle className="text-sm">Tóm tắt đánh giá sơ bộ</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-4 flex flex-col gap-2.5">
        {scores.map((d) => {
          const v = scoreVerdict(d.score);
          return (
            <div key={d.label} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-muted-foreground shrink-0">{d.icon}</span>
                <span className="text-[11px] text-muted-foreground font-medium truncate">{d.label}</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="text-xs font-bold text-foreground tabular-nums">{d.score}/100</span>
                <Badge variant={verdictVariant(v)} className="rounded-sm text-[10px] px-1.5 py-0">
                  {v}
                </Badge>
              </div>
            </div>
          );
        })}

        <Separator className="my-1" />

        {/* Summary footer */}
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-0.5">
            <p className="text-[10px] text-muted-foreground font-semibold">Xếp loại sơ bộ</p>
            <p
              className="text-lg font-extrabold font-[var(--font-display)]"
              style={{ color: overall === "Tốt" ? "var(--color-success-600)" : overall === "Trung bình" ? "var(--color-warning-600)" : "var(--color-danger-600)" }}
            >
              {overall}
            </p>
          </div>
          <div className="flex flex-col gap-0.5 text-right">
            <p className="text-[10px] text-muted-foreground font-semibold">Điểm tổng hợp</p>
            <p className="text-lg font-extrabold text-[var(--color-navy-700)] font-[var(--font-display)]">
              {composite}<span className="text-sm font-bold text-muted-foreground">/100</span>
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function Overview360({ caseDetail }: { caseDetail: CaseDetail }) {
  // Derive real metrics from findings
  const financialF  = [...caseDetail.findings].reverse().find((f) => f.agent_id === "financial_analysis");
  const collateralF = [...caseDetail.findings].reverse().find((f) => f.agent_id === "collateral_legal");

  const coverageRatio = collateralF?.metrics?.coverage_ratio ?? financialF?.metrics?.coverage_ratio;
  const ltvPct = coverageRatio != null && coverageRatio > 0
    ? Math.round((1 / coverageRatio) * 100)
    : null;
  const dscrReal = financialF?.metrics?.dscr;

  const scores    = caseDetail.decision?.scores ?? [];
  const scoreMax  = scores.reduce((s, x) => s + x.max, 0);
  const scoreSum  = scores.reduce((s, x) => s + x.score, 0);
  const compositePct = scores.length > 0 && scoreMax > 0
    ? Math.round((scoreSum / scoreMax) * 100)
    : null;

  return (
    <div className="flex gap-4 items-start flex-wrap xl:flex-nowrap">

      {/* Left column: KYC + Financial stacked */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">
        <KYCCard caseDetail={caseDetail} />

        <Card className="py-0 gap-0 overflow-hidden">
          <CardHeader className="pt-4 pb-3 px-5">
            <CardTitle className="text-sm">3. Financial &amp; Collateral</CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="p-5 flex flex-col gap-6">
            <FinancialTable dscrReal={dscrReal} />
            <Separator />
            <CollateralSection ltvPct={ltvPct} />
          </CardContent>
        </Card>
      </div>

      {/* Right column: Credit Request + Score sidebar stacked */}
      <div className="flex flex-col gap-4 w-[300px] shrink-0">
        <CreditRequestCard caseDetail={caseDetail} />
        <ScoreSidebar compositePct={compositePct} />
      </div>

    </div>
  );
}
