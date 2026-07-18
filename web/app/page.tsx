"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Line,
  LineChart,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  RefreshCw,
  Info,
  ChevronRight,
  SlidersHorizontal,
  TrendingDown,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Search,
  Clock,
} from "lucide-react";

import { fetchCases } from "./lib/api";
import type { CaseSummary } from "./lib/types";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Progress } from "./components/ui/progress";
import { Separator } from "./components/ui/separator";
import { Skeleton } from "./components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./components/ui/table";
import { cn } from "./lib/utils";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatVnd(amount: number | null | undefined): string {
  if (amount == null) return "—";
  if (amount >= 1_000_000_000)
    return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ`;
  return `${(amount / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} tr`;
}

function timeStr(iso: string) {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}
function dateStr(iso: string) {
  return new Date(iso).toLocaleDateString("vi-VN");
}

// ─── Domain types & enrichment ────────────────────────────────────────────────

type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
type Recommendation =
  | "APPROVE" | "ESCALATE_LEGAL" | "REQUEST_DOCS"
  | "MANUAL_INVESTIGATION" | "WAIT_DATA" | "ANALYZING";
type Route =
  | "Credit Officer" | "Legal Expert" | "Financial Expert"
  | "Relationship Manager" | "System";

interface EnrichedCase {
  raw: CaseSummary;
  priority: Priority;
  priorityScore: number;
  recommendation: Recommendation;
  route: Route;
  routeIsYou: boolean;
  aiConfidence: number | null;
  amountVnd: number | null;
}

function derivePriority(c: CaseSummary, amt: number | null): Priority {
  const hi = amt !== null && amt >= 20_000_000_000;
  if (hi && c.state === "READY_FOR_REVIEW") return "CRITICAL";
  if (hi || c.state === "NEED_INFO") return "HIGH";
  if (c.state === "READY_FOR_REVIEW") return "MEDIUM";
  return "LOW";
}

function deriveRecommendation(c: CaseSummary): Recommendation {
  if (!c.has_findings || c.state === "ANALYZING") return "ANALYZING";
  if (c.state === "READY_FOR_REVIEW") return "APPROVE";
  if (c.state === "NEED_INFO") return "REQUEST_DOCS";
  return "MANUAL_INVESTIGATION";
}

function deriveRoute(rec: Recommendation): { route: Route; routeIsYou: boolean } {
  if (rec === "APPROVE" || rec === "MANUAL_INVESTIGATION")
    return { route: "Credit Officer", routeIsYou: true };
  if (rec === "ESCALATE_LEGAL") return { route: "Legal Expert", routeIsYou: false };
  if (rec === "REQUEST_DOCS") return { route: "Relationship Manager", routeIsYou: false };
  return { route: "System", routeIsYou: false };
}

const CONFIDENCE_MAP: Partial<Record<Recommendation, number>> = {
  APPROVE: 91, REQUEST_DOCS: 74, MANUAL_INVESTIGATION: 68, ESCALATE_LEGAL: 82,
};
const PRIORITY_SCORE: Record<Priority, number> = {
  CRITICAL: 92, HIGH: 72, MEDIUM: 55, LOW: 35,
};

function enrich(c: CaseSummary): EnrichedCase {
  const amountVnd = (c.requested_facility?.amount_vnd as number | undefined) ?? null;
  const recommendation = deriveRecommendation(c);
  const priority = derivePriority(c, amountVnd);
  const { route, routeIsYou } = deriveRoute(recommendation);
  return {
    raw: c, priority, priorityScore: PRIORITY_SCORE[priority],
    recommendation, route, routeIsYou,
    aiConfidence: CONFIDENCE_MAP[recommendation] ?? null, amountVnd,
  };
}

// Vietnamese priority labels
const VI_PRIORITY: Record<Priority, { label: string; variant: "danger" | "warning" | "navy" | "success" }> = {
  CRITICAL: { label: "Cao",        variant: "danger" },
  HIGH:     { label: "Cao",        variant: "danger" },
  MEDIUM:   { label: "Trung bình", variant: "warning" },
  LOW:      { label: "Thấp",       variant: "success" },
};

const RECO_META: Record<Recommendation, {
  label: string; detail: string; icon: React.ReactNode;
  variant: "success" | "warning" | "orange" | "navy" | "muted";
}> = {
  APPROVE:              { label: "Approve",              icon: <CheckCircle2 className="size-3" />, detail: "AI đề xuất phê duyệt. Sẵn sàng cho quyết định.", variant: "success" },
  ESCALATE_LEGAL:       { label: "Escalate to Legal",    icon: <AlertTriangle className="size-3" />, detail: "Phát hiện vấn đề pháp lý. Cần chuyên gia xem xét.", variant: "warning" },
  REQUEST_DOCS:         { label: "Request Documents",    icon: <FileText className="size-3" />, detail: "Thiếu tài liệu cần thiết để hoàn tất phân tích.", variant: "orange" },
  MANUAL_INVESTIGATION: { label: "Manual Investigation", icon: <Search className="size-3" />, detail: "Phát hiện mẫu bất thường. Cần cán bộ xem xét.", variant: "navy" },
  WAIT_DATA:            { label: "Wait for Data",        icon: <Clock className="size-3" />, detail: "Đang chờ điểm CIC từ hệ thống bên ngoài.", variant: "muted" },
  ANALYZING:            { label: "Đang phân tích…",      icon: <RefreshCw className="size-3 animate-spin" />, detail: "Các AI agent đang xử lý hồ sơ.", variant: "muted" },
};

const RECO_VARIANT_MAP = {
  success: "success", warning: "warning", orange: "orange", navy: "navy", muted: "muted",
} as const;

const REASONING_FACTORS: Partial<Record<Recommendation, string[]>> = {
  APPROVE:              ["Dòng tiền ổn định, đủ năng lực trả nợ", "Lịch sử tín dụng tốt", "Tài sản đảm bảo đủ điều kiện"],
  REQUEST_DOCS:         ["Thiếu báo cáo tài chính 2024", "Chưa có tờ khai thuế gần nhất"],
  MANUAL_INVESTIGATION: ["Mẫu giao dịch bất thường", "Cần xác minh thông tin thêm"],
  ESCALATE_LEGAL:       ["Phát hiện vấn đề pháp lý tiềm ẩn", "Cần chuyên gia pháp lý xem xét"],
  ANALYZING:            ["Đang chờ dữ liệu hoàn chỉnh từ hệ thống"],
  WAIT_DATA:            ["Đang chờ dữ liệu hoàn chỉnh từ hệ thống"],
};

// Mock SLA days per row (positive = days remaining, negative = overdue)
const SLA_PATTERN = [-2, 1, 3, -1, 2, -3, 4, 1, -1, 2];

// ─── Static chart data ────────────────────────────────────────────────────────

const SLA_TREND = [
  { d: "T2", v: 2.8 }, { d: "T3", v: 2.5 }, { d: "T4", v: 2.3 },
  { d: "T5", v: 2.1 }, { d: "T6", v: 1.9 }, { d: "T7", v: 1.7 },
  { d: "CN", v: 1.6 },
];

const DONUT_COLORS = [
  "var(--color-navy-700)",
  "var(--color-success-600)",
  "var(--color-warning-600)",
  "var(--color-orange-600)",
];

// ─── KPI Card 1: SLA Approval ────────────────────────────────────────────────

function SLACard({ loading }: { loading: boolean }) {
  return (
    <Card className="py-0 gap-0 flex-1 min-w-[280px]">
      <CardContent className="flex gap-0 p-5">
        {/* Left: text */}
        <div className="flex-1 min-w-0 pr-4">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--color-navy-900)] mb-0.5">
            SLA Approval <Info className="size-3.5 text-muted-foreground shrink-0" />
          </div>
          <p className="text-xs text-muted-foreground mb-3">Thời gian phê duyệt trung bình</p>
          {loading ? (
            <Skeleton className="h-8 w-28 mb-2" />
          ) : (
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-[28px] font-extrabold text-[var(--color-success-600)] font-[var(--font-display)] leading-none whitespace-nowrap">
                1.6 ngày
              </span>
              <span className="text-sm font-bold text-[var(--color-success-600)] flex items-center gap-0.5 whitespace-nowrap">
                <TrendingDown className="size-3.5" /> 42%
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-2 whitespace-nowrap">
            So với thủ công: <span className="font-semibold text-foreground">2.8 ngày</span>
          </p>
          <p className="text-[10px] text-muted-foreground mt-2 italic">* Ước tính — cần API created_at</p>
        </div>
        {/* Right: sparkline — hidden when card is narrow */}
        <div className="flex flex-col items-end justify-between flex-none w-[110px] hidden sm:flex">
          {!loading && (
            <ResponsiveContainer width="100%" height={56}>
              <LineChart data={SLA_TREND} margin={{ top: 4, right: 2, left: 2, bottom: 4 }}>
                <Line
                  type="monotone" dataKey="v"
                  stroke="var(--color-success-600)" strokeWidth={2} dot={false}
                />
                <Tooltip
                  contentStyle={{ fontSize: 11, padding: "3px 8px", borderRadius: 4, border: "none", background: "var(--color-gray-900)", color: "#fff" }}
                  formatter={(v: number) => [`${v} ngày`, ""]}
                  labelFormatter={(l: string) => l}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
          <p className="text-[10px] text-muted-foreground text-right leading-tight">
            Cải thiện trong<br />30 ngày qua
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── KPI Card 2: Portfolio Quality ───────────────────────────────────────────

function PortfolioCard({ loading }: { loading: boolean }) {
  const gaugeData = [{ value: 100, fill: "var(--color-success-600)" }];
  return (
    <Card className="py-0 gap-0 flex-1 min-w-[280px]">
      <CardContent className="flex gap-0 p-5">
        {/* Left: text */}
        <div className="flex-1 min-w-0 pr-4">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--color-navy-900)] mb-0.5">
            Portfolio Quality <Info className="size-3.5 text-muted-foreground shrink-0" />
          </div>
          <p className="text-xs text-muted-foreground mb-3">Chất lượng danh mục tín dụng</p>
          {loading ? (
            <Skeleton className="h-8 w-20 mb-2" />
          ) : (
            <div className="flex items-baseline gap-1.5 flex-wrap">
              <span className="text-xs text-muted-foreground font-semibold whitespace-nowrap">NPL</span>
              <span className="text-[28px] font-extrabold text-foreground font-[var(--font-display)] leading-none">0</span>
              <span className="text-lg font-bold text-muted-foreground">%</span>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-2">
            Chất lượng: <span className="font-bold text-[var(--color-success-600)]">Tốt</span>
          </p>
          <p className="text-[10px] text-muted-foreground mt-2 italic">* Dữ liệu chỉ mang tính minh hoạ</p>
        </div>
        {/* Right: gauge — hidden when card is narrow */}
        <div className="hidden sm:flex flex-col items-center justify-center flex-none">
          {!loading && (
            <div className="relative size-20">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  cx="50%" cy="50%"
                  innerRadius="65%" outerRadius="90%"
                  startAngle={90} endAngle={-270}
                  data={gaugeData}
                >
                  <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                  <RadialBar
                    dataKey="value"
                    angleAxisId={0}
                    background={{ fill: "var(--color-gray-100)" }}
                  />
                </RadialBarChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-sm font-extrabold text-[var(--color-success-600)]">100%</span>
                <span className="text-[9px] text-muted-foreground">Tốt</span>
              </div>
            </div>
          )}
          {loading && <Skeleton className="size-20 rounded-full flex-none" />}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── KPI Card 3: Queue Summary ────────────────────────────────────────────────

function QueueCard({
  total, cao, trungBinh, thap, loading,
}: {
  total: number; cao: number; trungBinh: number; thap: number; loading: boolean;
}) {
  return (
    <Card className="py-0 gap-0 flex-1 min-w-[220px]">
      <CardContent className="p-5">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-[var(--color-navy-900)] mb-0.5">
          Hồ sơ chờ rà soát <Info className="size-3.5 text-muted-foreground shrink-0" />
        </div>
        <p className="text-xs text-muted-foreground mb-2">Liên quan hạn mức lớn hoặc chờ giải ngân lâu</p>
        {loading ? (
          <Skeleton className="h-9 w-32 mb-3" />
        ) : (
          <p className="text-[32px] font-extrabold text-[var(--color-orange-600)] font-[var(--font-display)] leading-none mb-3">
            {total} hồ sơ
          </p>
        )}
        <div className="flex flex-col gap-1.5">
          <LegendRow color="var(--color-danger-600)"  label="Cao"        count={cao}       loading={loading} />
          <LegendRow color="var(--color-warning-600)" label="Trung bình" count={trungBinh}  loading={loading} />
          <LegendRow color="var(--color-success-600)" label="Thấp"       count={thap}       loading={loading} />
        </div>
      </CardContent>
    </Card>
  );
}

function LegendRow({ color, label, count, loading }: {
  color: string; label: string; count: number; loading: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <div className="size-2 rounded-full shrink-0" style={{ background: color }} />
        <span className="text-muted-foreground">{label}</span>
      </div>
      {loading ? <Skeleton className="h-4 w-5" /> : <span className="font-bold text-foreground">{count}</span>}
    </div>
  );
}

// ─── Filter bar ───────────────────────────────────────────────────────────────

function FilterBar({
  products, selectedProducts, onProductToggle,
  maxAmountB, onMaxAmountChange, onReset,
}: {
  products: string[];
  selectedProducts: Set<string>;
  onProductToggle: (p: string) => void;
  maxAmountB: number;
  onMaxAmountChange: (val: number) => void;
  onReset: () => void;
}) {
  const displayMax = maxAmountB >= 100 ? "100 Tỷ+" : `${maxAmountB} Tỷ`;
  return (
    <Card className="py-0 gap-0">
      <CardContent className="flex flex-wrap items-end gap-x-6 gap-y-3 px-5 py-3">
        {/* Sản phẩm */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Sản phẩm</label>
          <div className="flex items-center gap-1.5 flex-wrap">
            {products.map((p) => (
              <button
                key={p}
                onClick={() => onProductToggle(p)}
                className={cn(
                  "inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold border transition-colors cursor-pointer",
                  selectedProducts.has(p)
                    ? "bg-[var(--color-navy-700)] text-white border-[var(--color-navy-700)]"
                    : "bg-card border-border text-muted-foreground hover:border-[var(--color-navy-500)] hover:text-[var(--color-navy-700)]"
                )}
              >
                {p}
                {selectedProducts.has(p) && (
                  <span className="opacity-70 ml-0.5 text-sm leading-none">×</span>
                )}
              </button>
            ))}
            <button className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold border border-dashed border-border text-muted-foreground hover:border-[var(--color-navy-500)] cursor-pointer transition-colors">
              + Thêm
            </button>
          </div>
        </div>

        <div className="hidden sm:block self-stretch w-px bg-border" />

        {/* Đơn vị */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Đơn vị</label>
          <select className="text-sm font-medium border border-border rounded-md px-3 py-1.5 bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--color-navy-500)] min-w-[180px]">
            <option>Tất cả chi nhánh/PGD</option>
            <option>CN Hà Nội</option>
            <option>CN TP. Hồ Chí Minh</option>
            <option>CN Đà Nẵng</option>
          </select>
        </div>

        <div className="hidden sm:block self-stretch w-px bg-border" />

        {/* Hạn mức slider */}
        <div className="flex flex-col gap-1.5 flex-1 min-w-[180px] max-w-[260px]">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Hạn mức</label>
            <span className="text-xs text-muted-foreground tabular-nums">0 VND — {displayMax}</span>
          </div>
          <input
            type="range" min={0} max={100} step={5}
            value={maxAmountB}
            onChange={(e) => onMaxAmountChange(Number(e.target.value))}
            className="w-full h-1.5 rounded-full cursor-pointer"
            style={{ accentColor: "var(--color-navy-700)" }}
          />
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>0</span><span>100 Tỷ+</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-end gap-2 ml-auto">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs">
            <SlidersHorizontal className="size-3.5" /> Bộ lọc khác
          </Button>
          <Button variant="ghost" size="sm" className="gap-1.5 text-xs text-muted-foreground" onClick={onReset}>
            <RefreshCw className="size-3.5" /> Làm mới
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Case table ───────────────────────────────────────────────────────────────

function CaseTable({ cases, loading }: {
  cases: EnrichedCase[];
  loading: boolean;
}) {
  return (
    <Card className="py-0 gap-0 overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between pt-4 pb-3 px-5 gap-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm">Hồ sơ chờ xử lý</CardTitle>
          {!loading && (
            <Badge variant="muted" className="rounded-full font-bold tabular-nums">{cases.length}</Badge>
          )}
        </div>
        <Button variant="ghost" size="sm" className="text-xs text-primary gap-0.5 -mr-2">
          Xem tất cả <ChevronRight className="size-3" />
        </Button>
      </CardHeader>
      <Separator />
      {loading ? (
        <div className="p-4 flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <p className="p-8 text-sm text-muted-foreground text-center">
          Không có hồ sơ nào phù hợp với bộ lọc.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mã hồ sơ</TableHead>
              <TableHead>Khách hàng</TableHead>
              <TableHead>Sản phẩm</TableHead>
              <TableHead>Hạn mức</TableHead>
              <TableHead>Độ ưu tiên</TableHead>
              <TableHead>SLA</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead className="w-[130px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.map((c, i) => {
              const pm = VI_PRIORITY[c.priority];
              const sla = SLA_PATTERN[i % SLA_PATTERN.length];

              let statusLabel: string;
              let statusVariant: "warning" | "navy" | "success" | "muted";
              if (c.recommendation === "ANALYZING") {
                statusLabel = "Đang rà soát"; statusVariant = "navy";
              } else if (c.recommendation === "APPROVE") {
                statusLabel = "Chờ phê duyệt"; statusVariant = "success";
              } else if (c.recommendation === "REQUEST_DOCS") {
                statusLabel = "Chờ rà soát"; statusVariant = "warning";
              } else {
                statusLabel = "AI chấm điểm"; statusVariant = "muted";
              }

              return (
                <TableRow key={c.raw.case_id}>
                  <TableCell>
                    <Link
                      href={`/cases/${c.raw.case_id}`}
                      className="font-bold text-primary text-sm"
                    >
                      {c.raw.case_id}
                    </Link>
                  </TableCell>
                  <TableCell className="font-medium text-foreground max-w-[160px] truncate">
                    {c.raw.customer_id}
                  </TableCell>
                  <TableCell>
                    <Badge variant="muted" className="font-mono text-[11px] rounded-sm">{c.raw.product}</Badge>
                  </TableCell>
                  <TableCell className="tabular-nums font-semibold text-foreground whitespace-nowrap">
                    {formatVnd(c.amountVnd)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={pm.variant} className="rounded-sm">{pm.label}</Badge>
                  </TableCell>
                  <TableCell className={cn(
                    "font-semibold text-sm tabular-nums whitespace-nowrap",
                    sla < 0
                      ? "text-[var(--color-danger-600)]"
                      : "text-muted-foreground"
                  )}>
                    {sla < 0 ? `${sla} ngày` : `+${sla} ngày`}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant} className="rounded-full text-xs whitespace-nowrap">
                      {statusLabel}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button asChild variant="outline" size="sm" className="text-xs h-7 px-3 whitespace-nowrap">
                      <Link href={`/cases/${c.raw.case_id}`}>Mở hồ sơ</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}

// ─── Processing funnel ────────────────────────────────────────────────────────

const FUNNEL_STAGES = [
  { label: "Mới nhận",      color: "var(--color-navy-700)" },
  { label: "Đang rà soát",  color: "var(--color-navy-600)" },
  { label: "AI chấm điểm",  color: "var(--color-navy-500)" },
  { label: "Chờ phê duyệt", color: "var(--color-gray-500)" },
  { label: "Hoàn tất",      color: "var(--color-success-600)" },
];

const FUNNEL_DELTAS = ["+12%", "+5%", "+8%", "−7%", "+18%"];
const FUNNEL_POSITIVE = [true, true, true, false, true];

function ProcessingFunnel({ counts }: { counts: number[] }) {
  return (
    <Card className="py-0 gap-0">
      <CardHeader className="pb-0 pt-4 px-5">
        <CardTitle className="text-sm">Phễu xử lý hồ sơ</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pt-3 pb-4">
        <div className="flex items-stretch">
          {FUNNEL_STAGES.map((stage, i) => {
            const isFirst = i === 0;
            const isLast = i === FUNNEL_STAGES.length - 1;
            const arrowDepth = 14;
            const clip = isFirst
              ? `polygon(0 0, calc(100% - ${arrowDepth}px) 0, 100% 50%, calc(100% - ${arrowDepth}px) 100%, 0 100%)`
              : isLast
              ? `polygon(0 0, 100% 0, 100% 100%, 0 100%, ${arrowDepth}px 50%)`
              : `polygon(0 0, calc(100% - ${arrowDepth}px) 0, 100% 50%, calc(100% - ${arrowDepth}px) 100%, 0 100%, ${arrowDepth}px 50%)`;

            return (
              <div
                key={stage.label}
                className="flex-1 flex flex-col items-center justify-center py-4 text-white text-center relative"
                style={{
                  background: stage.color,
                  clipPath: clip,
                  marginLeft: isFirst ? 0 : `-${arrowDepth}px`,
                  zIndex: FUNNEL_STAGES.length - i,
                  paddingLeft: isFirst ? 12 : arrowDepth + 8,
                  paddingRight: isLast ? 12 : arrowDepth + 8,
                  minWidth: 0,
                }}
              >
                <p className="text-[10px] font-semibold opacity-80 mb-0.5 leading-tight">{stage.label}</p>
                <p className="text-xl font-extrabold leading-none">{counts[i]}</p>
                <p className={cn(
                  "text-[10px] font-bold mt-0.5",
                  FUNNEL_POSITIVE[i] ? "text-green-200" : "text-red-200"
                )}>
                  {FUNNEL_POSITIVE[i] ? "↑" : "↓"} {FUNNEL_DELTAS[i]}
                </p>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted-foreground mt-2">* So với 7 ngày trước</p>
      </CardContent>
    </Card>
  );
}

// ─── Product distribution donut ───────────────────────────────────────────────

function ProductDonutChart({ distribution }: { distribution: { name: string; value: number }[] }) {
  const total = distribution.reduce((s, d) => s + d.value, 0);

  if (distribution.length === 0) return null;

  return (
    <Card className="py-0 gap-0">
      <CardHeader className="flex flex-row items-center justify-between pt-4 pb-0 px-5">
        <CardTitle className="text-sm">Phân bổ hồ sơ theo sản phẩm</CardTitle>
        <select className="text-xs border border-border rounded px-2 py-1 bg-card text-muted-foreground focus:outline-none">
          <option>7 ngày qua</option>
          <option>30 ngày qua</option>
          <option>Tất cả</option>
        </select>
      </CardHeader>
      <CardContent className="px-5 pb-4 pt-3">
        <div className="flex items-center gap-4">
          <div className="w-[120px] h-[120px] flex-none">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={distribution}
                  cx="50%" cy="50%"
                  innerRadius={34} outerRadius={54}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {distribution.map((_, i) => (
                    <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ fontSize: 11, borderRadius: 6, border: "none", background: "var(--color-gray-900)", color: "#fff" }}
                  formatter={(v: number, n: string) => [`${v} hồ sơ`, n]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex-1 flex flex-col gap-2 min-w-0">
            {distribution.map((d, i) => (
              <div key={d.name} className="flex items-center justify-between gap-2 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="size-2.5 rounded-sm shrink-0"
                    style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }}
                  />
                  <span className="text-muted-foreground font-mono text-xs truncate">{d.name}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="font-bold text-foreground tabular-nums">{d.value}</span>
                  <span className="text-xs text-muted-foreground">
                    ({total ? Math.round((d.value / total) * 100) : 0}%)
                  </span>
                </div>
              </div>
            ))}
            <Separator className="my-0.5" />
            <div className="flex items-center justify-between text-sm font-bold">
              <span className="text-muted-foreground">Tổng</span>
              <span className="text-foreground tabular-nums">{total} hồ sơ</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── High priority list ───────────────────────────────────────────────────────

function HighPriorityList({ cases }: { cases: EnrichedCase[] }) {
  if (cases.length === 0) return null;
  const top3 = cases.slice(0, 3);

  return (
    <Card className="py-0 gap-0">
      <CardHeader className="flex flex-row items-center justify-between pt-4 pb-0 px-5">
        <CardTitle className="text-sm">Hồ sơ ưu tiên cao</CardTitle>
        <Button variant="ghost" size="sm" className="text-xs text-primary gap-0.5 -mr-2">
          Xem tất cả <ChevronRight className="size-3" />
        </Button>
      </CardHeader>
      <CardContent className="px-5 pb-4 pt-3 flex flex-col gap-3">
        {top3.map((c, i) => (
          <Link
            key={c.raw.case_id}
            href={`/cases/${c.raw.case_id}`}
            className="flex items-start justify-between gap-3 border border-border rounded-lg p-3 hover:bg-muted/40 hover:border-[var(--color-navy-300)] transition-colors group"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-primary truncate">{c.raw.case_id}</p>
              <p className="text-xs text-muted-foreground truncate mt-0.5">{c.raw.customer_id}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Hạn mức: <span className="font-semibold text-foreground">{formatVnd(c.amountVnd)}</span>
              </p>
              <p className="text-xs font-semibold text-[var(--color-danger-600)] mt-0.5">
                Quá hạn SLA: −{i + 1} ngày
              </p>
            </div>
            <Badge variant="danger" className="rounded-sm shrink-0 mt-0.5">Cao</Badge>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

// ─── AI Reasoning panel ───────────────────────────────────────────────────────

function ConfidenceBar({ value }: { value: number }) {
  const indicatorClass =
    value >= 85 ? "bg-[var(--color-success-600)]"
    : value >= 70 ? "bg-[var(--color-warning-600)]"
    : "bg-[var(--color-gray-400)]";
  return (
    <div className="flex flex-col gap-1 min-w-[68px]">
      <span className="text-xs font-bold tabular-nums text-foreground">{value}%</span>
      <Progress value={value} indicatorClassName={indicatorClass} className="h-1" />
    </div>
  );
}

function ReasoningPanel({ c }: { c: EnrichedCase }) {
  const reco = RECO_META[c.recommendation];
  const agents = [
    { name: "Financial Analysis", done: c.raw.has_findings },
    { name: "Risk Assessment",    done: c.priority !== "CRITICAL" },
    { name: "Document Check",     done: c.recommendation !== "REQUEST_DOCS" },
    { name: "Legal Check",        done: c.recommendation !== "ESCALATE_LEGAL" },
  ];
  const factors = REASONING_FACTORS[c.recommendation] ?? [];

  return (
    <Card className="gap-0 py-0 overflow-hidden">
      <div className="flex flex-wrap items-center gap-4 px-5 py-3 bg-muted border-b border-border">
        <span className="text-sm font-bold text-[var(--color-navy-900)] whitespace-nowrap">
          AI Reasoning — {c.raw.case_id}
        </span>
        <div className="flex flex-wrap gap-4">
          {agents.map((a) => (
            <div key={a.name} className="flex items-center gap-1.5">
              <span className={cn(
                "inline-flex size-[18px] items-center justify-center rounded-full text-[10px] font-extrabold",
                a.done
                  ? "bg-[var(--status-success-bg)] text-[var(--status-success-fg)]"
                  : "bg-[var(--status-warning-bg)] text-[var(--status-warning-fg)]"
              )}>
                {a.done ? "✓" : "!"}
              </span>
              <span className="text-xs font-medium text-foreground">{a.name}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-start gap-8 px-5 py-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Đề xuất AI</p>
          <Badge variant={RECO_VARIANT_MAP[reco.variant]} className="text-xs gap-1.5 px-3 py-1 rounded-md">
            {reco.icon}{reco.label}
          </Badge>
        </div>
        <Separator orientation="vertical" className="self-stretch hidden sm:block" />
        <div className="flex-1 min-w-[160px]">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Yếu tố chính</p>
          <ul className="text-sm text-foreground space-y-1 list-disc pl-4">
            {factors.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </div>
        <Separator orientation="vertical" className="self-stretch hidden sm:block" />
        <div className="flex flex-col gap-3 min-w-[120px]">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1">Số tiền</p>
            <p className="text-sm font-semibold text-foreground tabular-nums">{formatVnd(c.amountVnd)}</p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1">Sản phẩm</p>
            <p className="text-sm font-semibold text-foreground font-mono">{c.raw.product}</p>
          </div>
          {c.aiConfidence !== null && (
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1">Độ tin cậy</p>
              <ConfidenceBar value={c.aiConfidence} />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2 self-center ml-auto">
          <Button asChild size="sm">
            <Link href={`/cases/${c.raw.case_id}`}>
              {c.raw.has_findings ? "Mở hồ sơ" : "Bắt đầu"}
            </Link>
          </Button>
          <Button variant="outline" size="sm">Xem chi tiết</Button>
        </div>
      </div>
    </Card>
  );
}

// ─── Status bar ───────────────────────────────────────────────────────────────

function StatusBar({ lastUpdated }: { lastUpdated: string | null }) {
  return (
    <div className="flex items-center justify-between px-1 py-2 text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>
          Dữ liệu cập nhật:{" "}
          {lastUpdated
            ? new Date(lastUpdated).toLocaleString("vi-VN", {
                day: "2-digit", month: "2-digit", year: "numeric",
                hour: "2-digit", minute: "2-digit",
              })
            : "—"
          }
        </span>
        <RefreshCw className="size-3 opacity-50 hover:opacity-100 cursor-pointer transition-opacity" />
      </div>
      <div className="flex items-center gap-1">
        <Info className="size-3" />
        <span>Tất cả thời gian hiển thị theo GMT+7</span>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ApplicationQueue() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [selectedProducts, setSelectedProducts] = useState<Set<string>>(new Set());
  const [maxAmountB, setMaxAmountB] = useState(100); // in tỷ VND, 100 = no filter

  useEffect(() => {
    fetchCases().then(setCases).catch(() => setCases([]));
  }, []);

  const loading = cases === null;
  const enriched = useMemo(() => (cases ?? []).map(enrich), [cases]);

  // Priority counts
  const cao = useMemo(
    () => enriched.filter((c) => c.priority === "CRITICAL" || c.priority === "HIGH").length,
    [enriched]
  );
  const trungBinh = useMemo(
    () => enriched.filter((c) => c.priority === "MEDIUM").length,
    [enriched]
  );
  const thap = enriched.length - cao - trungBinh;

  // Product distribution for donut
  const productDistribution = useMemo(() => {
    const map: Record<string, number> = {};
    enriched.forEach((c) => { map[c.raw.product] = (map[c.raw.product] ?? 0) + 1; });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  }, [enriched]);

  const products = useMemo(() => productDistribution.map((d) => d.name), [productDistribution]);

  // Processing funnel counts
  const funnelCounts = useMemo(() => [
    Math.max(enriched.length, 1),                                          // Mới nhận
    enriched.filter((c) => c.recommendation === "ANALYZING").length,      // Đang rà soát
    enriched.filter((c) => c.raw.has_findings).length,                    // AI chấm điểm
    enriched.filter((c) => c.recommendation === "APPROVE").length,        // Chờ phê duyệt
    0,                                                                     // Hoàn tất (not in API)
  ], [enriched]);

  // Filtered cases
  const filteredCases = useMemo(() => {
    let result = enriched;
    if (selectedProducts.size > 0)
      result = result.filter((c) => selectedProducts.has(c.raw.product));
    if (maxAmountB < 100)
      result = result.filter((c) => (c.amountVnd ?? 0) <= maxAmountB * 1_000_000_000);
    return result;
  }, [enriched, selectedProducts, maxAmountB]);

  // Top priority cases for the list
  const highPriorityCases = useMemo(
    () => enriched.filter((c) => c.priority === "CRITICAL" || c.priority === "HIGH"),
    [enriched]
  );

  // Last updated timestamp
  const lastUpdated = useMemo(
    () => enriched.length
      ? enriched.reduce((latest, c) => c.raw.updated_at > latest ? c.raw.updated_at : latest, enriched[0].raw.updated_at)
      : null,
    [enriched]
  );

  function toggleProduct(p: string) {
    setSelectedProducts((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p); else next.add(p);
      return next;
    });
  }

  function resetFilters() {
    setSelectedProducts(new Set());
    setMaxAmountB(100);
  }

  return (
    <main className="flex flex-col gap-4 p-5 max-w-[1600px]">

      {/* ── KPI Strip ─────────────────────────────────────────── */}
      <div className="flex gap-4 flex-wrap">
        <SLACard loading={loading} />
        <PortfolioCard loading={loading} />
        <QueueCard total={enriched.length} cao={cao} trungBinh={trungBinh} thap={thap} loading={loading} />
      </div>

      {/* ── Filter bar ────────────────────────────────────────── */}
      {!loading && (
        <FilterBar
          products={products}
          selectedProducts={selectedProducts}
          onProductToggle={toggleProduct}
          maxAmountB={maxAmountB}
          onMaxAmountChange={setMaxAmountB}
          onReset={resetFilters}
        />
      )}

      {/* ── Main 2-column content ─────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4 items-start">

        {/* Left column */}
        <div className="flex flex-col gap-4">
          <CaseTable
            cases={filteredCases}
            loading={loading}
          />
          {!loading && <ProcessingFunnel counts={funnelCounts} />}
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          {!loading && <ProductDonutChart distribution={productDistribution} />}
          <HighPriorityList cases={highPriorityCases} />
        </div>
      </div>

      {/* ── Status bar ────────────────────────────────────────── */}
      <StatusBar lastUpdated={lastUpdated} />

    </main>
  );
}
