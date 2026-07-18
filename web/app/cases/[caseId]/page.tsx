"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
} from "recharts";
import {
  Search, Bell, ChevronDown, Eye, RefreshCw, CheckCircle,
  ArrowLeft, Info, ChevronRight, Download, FileEdit, MoreVertical,
  Scale, BarChart3, Building2, ShieldCheck, Bot,
} from "lucide-react";

import { AnalyzingView } from "../../components/AnalyzingView";
import { ChatTab } from "../../components/ChatTab";
import type { ActionKey } from "../../components/ActionBar";
import { ExplainabilityDrawer } from "../../components/ExplainabilityDrawer";
import { decisionAction, fetchAudit, fetchCase, triggerAnalyze } from "../../lib/api";
import type { AuditEvent, CaseDetail, Finding } from "../../lib/types";
import { Overview360 } from "./Overview360";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Progress } from "../../components/ui/progress";
import { Separator } from "../../components/ui/separator";
import { Skeleton } from "../../components/ui/skeleton";
import { cn } from "../../lib/utils";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatVnd(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 3 })} tỷ VND`;
}

function getStanceLabel(s: string): string {
  if (s === "SUPPORT") return "Tốt";
  if (s === "CAUTION") return "Trung bình";
  if (s === "OPPOSE") return "Kém";
  return "Chưa có dữ liệu";
}

function getStanceDot(s: string): string {
  if (s === "SUPPORT") return "var(--color-success-600)";
  if (s === "CAUTION") return "var(--color-warning-600)";
  if (s === "OPPOSE") return "var(--color-danger-600)";
  return "var(--color-gray-400)";
}

function confidenceBar(pct: number): string {
  if (pct >= 80) return "bg-[var(--color-success-600)]";
  if (pct >= 60) return "bg-[var(--color-warning-600)]";
  return "bg-[var(--color-danger-600)]";
}

function deriveCreditRating(pct: number | null): string {
  if (pct === null) return "—";
  if (pct >= 90) return "AAA";
  if (pct >= 80) return "AA";
  if (pct >= 70) return "A";
  if (pct >= 60) return "BBB";
  if (pct >= 50) return "BB";
  return "B";
}

const REC_VI: Record<string, string> = {
  APPROVE: "Phê duyệt",
  APPROVE_WITH_CONDITIONS: "Phê duyệt có điều kiện",
  REFER: "Chuyển chuyên gia",
  REJECT: "Từ chối",
  NEED_INFO: "Cần thêm thông tin",
};

const REC_VERDICT: Record<string, { text: string; color: string; icon: string }> = {
  APPROVE:                 { text: "ĐỦ ĐIỀU KIỆN",         color: "var(--color-success-600)", icon: "✓" },
  APPROVE_WITH_CONDITIONS: { text: "ĐỦ ĐIỀU KIỆN (có ĐK)",  color: "var(--color-warning-600)", icon: "!" },
  REFER:                   { text: "CHUYỂN CHUYÊN GIA",     color: "var(--color-navy-600)",    icon: "→" },
  REJECT:                  { text: "KHÔNG ĐỦ ĐIỀU KIỆN",    color: "var(--color-danger-600)",  icon: "✗" },
  NEED_INFO:               { text: "CẦN THÊM THÔNG TIN",    color: "var(--color-warning-600)", icon: "?" },
};

// ─── Agent card config ────────────────────────────────────────────────────────

const AGENT_CARDS = [
  {
    id: "legal_review",
    name: "Legal Agent",
    desc: "Đánh giá tình pháp lý DN & DADT",
    bg: "var(--color-navy-50)",
    iconColor: "var(--color-navy-700)",
    icon: <Scale className="size-5" />,
  },
  {
    id: "financial_analysis",
    name: "Financial Agent",
    desc: "Phân tích BCTC, khả năng trả nợ & tính PD",
    bg: "var(--color-success-100)",
    iconColor: "var(--color-success-600)",
    icon: <BarChart3 className="size-5" />,
  },
  {
    id: "collateral_legal",
    name: "Collateral Agent",
    desc: "Định giá TSDB, LTV, tính thanh khoản",
    bg: "var(--color-warning-100)",
    iconColor: "var(--color-warning-700)",
    icon: <Building2 className="size-5" />,
  },
  {
    id: "cic_check",
    name: "Risk Agent",
    desc: "Nhận diện rủi ro & đối chiếu CIC",
    bg: "var(--color-danger-100)",
    iconColor: "var(--color-danger-600)",
    icon: <ShieldCheck className="size-5" />,
  },
];

function getPrimaryMetric(f: Finding, agentId: string): { label: string; value: string } {
  if (agentId === "financial_analysis") {
    const dscr = f.metrics?.dscr;
    if (dscr) return { label: "DSCR (Ước tính)", value: `${dscr.toFixed(2)}x` };
    const pd = f.metrics?.pd_estimate;
    if (pd) return { label: "PD (XHTD nội bộ)", value: `${(pd * 100).toFixed(2)}%` };
  }
  if (agentId === "collateral_legal") {
    const cr = f.metrics?.coverage_ratio;
    if (cr && cr > 0) return { label: "LTV dự kiến", value: `${Math.round((1 / cr) * 100)}%` };
  }
  const scorePct = Math.round(f.confidence * 100);
  return { label: "Điểm đánh giá", value: `${scorePct}/100` };
}

function getAgentBullets(f: Finding, agentId: string): string[] {
  const bullets: string[] = [f.claim];
  if (agentId === "collateral_legal") {
    const cr = f.metrics?.coverage_ratio;
    if (cr && cr > 0) {
      const ltv = Math.round((1 / cr) * 100);
      bullets.push(`LTV hiện tại ${ltv}% < ngưỡng 65%.`);
    }
  }
  if (agentId === "financial_analysis") {
    const dscr = f.metrics?.dscr;
    if (dscr) bullets.push(`Khả năng trả nợ tốt, DSCR = ${dscr.toFixed(2)}x.`);
  }
  if (f.recommended_action) bullets.push(f.recommended_action);
  return bullets.slice(0, 4);
}

// ─── Planner workflow ─────────────────────────────────────────────────────────

const WF_STEPS = [
  "Tiếp nhận & KYC",
  "Thu thập dữ liệu",
  "Phân tích bởi AI Agents",
  "Tổng hợp & Chấm điểm",
  "Trình phê duyệt",
];

function getActiveStep(state: string): number {
  if (state === "ANALYZING") return 2;
  if (state === "READY_FOR_REVIEW") return 3;
  if (state === "SUBMITTED_FOR_APPROVAL") return 4;
  if (state === "APPROVED" || state === "REJECTED") return 5;
  return 2;
}

// ─── Single Agent Card ────────────────────────────────────────────────────────

function AgentCard({
  config, finding, docs, onFindingClick,
}: {
  config: typeof AGENT_CARDS[number];
  finding: Finding | undefined;
  docs: { document_id: string; doc_type: string }[];
  onFindingClick: (f: Finding) => void;
}) {
  const hasFinding = Boolean(finding);
  const scorePct = finding ? Math.round(finding.confidence * 100) : null;
  const primary = finding ? getPrimaryMetric(finding, config.id) : null;
  const bullets = finding ? getAgentBullets(finding, config.id) : [];
  const stanceColor = finding ? getStanceDot(finding.stance) : "var(--color-gray-400)";

  return (
    <Card className="py-0 gap-0 overflow-hidden flex flex-col">
      {/* Card header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-3">
          <div
            className="size-10 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: config.bg, color: config.iconColor }}
          >
            {config.icon}
          </div>
          <div>
            <p className="text-sm font-bold text-[var(--color-navy-900)]">{config.name}</p>
            <p className="text-xs text-muted-foreground leading-snug mt-0.5 max-w-[200px]">{config.desc}</p>
          </div>
        </div>
        <Badge
          variant={hasFinding ? "success" : "warning"}
          className="rounded-sm text-[11px] shrink-0 mt-0.5"
        >
          {hasFinding ? "Hoàn tất" : "Đang xử lý"}
        </Badge>
      </div>

      <Separator />

      {/* Metrics row */}
      <div className="px-4 pt-3 pb-2">
        {hasFinding && primary ? (
          <div className="flex items-end justify-between gap-4">
            {/* Primary metric */}
            <div>
              <p className="text-[11px] text-muted-foreground font-semibold mb-0.5">{primary.label}</p>
              <p
                className="text-[26px] font-extrabold leading-none font-[var(--font-display)]"
                style={{ color: primary.label.includes("Điểm") ? "var(--color-navy-700)" : "var(--color-orange-600)" }}
              >
                {primary.value}
              </p>
            </div>

            {/* Quick verdict */}
            <div className="text-right">
              <p className="text-[11px] text-muted-foreground font-semibold mb-1">Kết luận nhanh</p>
              <div className="flex items-center justify-end gap-1.5">
                <div className="size-2 rounded-full shrink-0" style={{ background: stanceColor }} />
                <span className="text-sm font-bold" style={{ color: stanceColor }}>
                  {getStanceLabel(finding!.stance)}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground py-1">Đang phân tích…</p>
        )}

        {/* Score bar + confidence */}
        {scorePct !== null && (
          <div className="mt-3 flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <p className="text-[11px] text-muted-foreground">Điểm đánh giá</p>
              <p className="text-xs font-bold text-foreground ml-auto">{scorePct}%</p>
            </div>
            <Progress value={scorePct} indicatorClassName={confidenceBar(scorePct)} className="h-1.5" />
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-muted-foreground">Độ tin cậy</p>
              <p className="text-xs font-bold text-foreground">{scorePct}%</p>
            </div>
          </div>
        )}
      </div>

      <Separator />

      {/* Bullets */}
      {bullets.length > 0 && (
        <div className="px-4 py-3 flex-1">
          <ul className="space-y-1.5">
            {bullets.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-foreground">
                <CheckCircle className="size-3.5 text-[var(--color-success-600)] shrink-0 mt-0.5" />
                <span className="leading-snug">{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Documents */}
      {docs.length > 0 && (
        <>
          <Separator />
          <div className="px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Bảng chứng chính
            </p>
            <div className="flex flex-col gap-1.5">
              {docs.slice(0, 3).map((d) => (
                <div key={d.document_id} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-[11px] text-muted-foreground">📄</span>
                    <span className="text-xs text-foreground truncate font-mono">
                      {d.doc_type.replace(/_/g, "_")}.pdf
                    </span>
                  </div>
                  <button
                    className="text-muted-foreground hover:text-primary shrink-0 transition-colors"
                    onClick={() => finding && onFindingClick(finding)}
                  >
                    <Eye className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* View full detail */}
      {finding && (
        <>
          <Separator />
          <button
            className="group px-4 py-2.5 text-xs font-semibold text-primary hover:bg-muted/50 transition-colors text-left flex items-center gap-1 no-underline"
            onClick={() => onFindingClick(finding)}
          >
            Xem phân tích chi tiết <ChevronRight className="size-3 transition-transform duration-150 group-hover:translate-x-0.5" />
          </button>
        </>
      )}
    </Card>
  );
}

// ─── Planner workflow bar ─────────────────────────────────────────────────────

function PlannerWorkflow({ state, updatedAt }: { state: string; updatedAt?: string }) {
  const activeStep = getActiveStep(state);
  const stateLabel = state === "ANALYZING" ? "Đang thực hiện"
    : state === "READY_FOR_REVIEW" ? "Sẵn sàng phê duyệt"
    : state === "APPROVED" ? "Đã phê duyệt"
    : state === "REJECTED" ? "Đã từ chối"
    : "Đang xử lý";

  return (
    <Card className="py-0 gap-0">
      <CardContent className="flex items-center gap-4 px-5 py-4 flex-wrap">
        {/* Planner identity */}
        <div className="flex items-center gap-3 flex-none w-48 border-r border-border pr-5">
          <div className="size-10 rounded-lg bg-[var(--color-navy-50)] flex items-center justify-center shrink-0 text-[var(--color-navy-700)]">
            <Bot className="size-5" />
          </div>
          <div>
            <p className="text-sm font-bold text-[var(--color-navy-900)]">Planner Agent</p>
            <p className="text-[11px] text-muted-foreground leading-snug">
              Điều phối và giám sát luồng thẩm định theo Workflow 1.2.3
            </p>
          </div>
        </div>

        {/* Steps */}
        <div className="flex-1 flex items-center justify-between min-w-0 gap-1">
          {WF_STEPS.map((label, i) => {
            const isDone    = i < activeStep;
            const isActive  = i === activeStep;
            const isPending = i > activeStep;
            return (
              <div key={i} className="flex items-center gap-1 flex-1 min-w-0">
                <div className="flex flex-col items-center gap-1 flex-none">
                  <div className={cn(
                    "size-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 border-2",
                    isDone    && "bg-[var(--color-navy-700)] border-[var(--color-navy-700)] text-white",
                    isActive  && "bg-[var(--color-orange-600)] border-[var(--color-orange-600)] text-white",
                    isPending && "bg-card border-border text-muted-foreground",
                  )}>
                    {isDone ? "✓" : i + 1}
                  </div>
                  <p className={cn(
                    "text-[10px] leading-tight text-center max-w-[80px]",
                    isDone    && "text-[var(--color-navy-700)] font-semibold",
                    isActive  && "text-[var(--color-orange-600)] font-bold",
                    isPending && "text-muted-foreground",
                  )}>
                    {label}
                  </p>
                  <p className={cn(
                    "text-[9px] font-semibold",
                    isDone   && "text-[var(--color-success-600)]",
                    isActive && "text-[var(--color-orange-600)]",
                    isPending && "text-muted-foreground",
                  )}>
                    {isDone ? "✓ Hoàn tất" : isActive ? "⟳ Đang thực hiện" : "Chờ xử lý"}
                  </p>
                </div>
                {i < WF_STEPS.length - 1 && (
                  <div className={cn(
                    "h-0.5 flex-1 mx-1 mt-[-18px]",
                    isDone ? "bg-[var(--color-navy-700)]" : "bg-border"
                  )} />
                )}
              </div>
            );
          })}
        </div>

        {/* Status */}
        <div className="flex-none border-l border-border pl-5 text-right">
          <p className="text-[11px] text-muted-foreground font-semibold mb-1">Trạng thái luồng</p>
          <Badge
            variant={state === "ANALYZING" ? "navy" : state === "READY_FOR_REVIEW" ? "success" : "muted"}
            className="rounded-sm"
          >
            {stateLabel}
          </Badge>
          {updatedAt && (
            <p className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1 justify-end">
              Cập nhật lúc: {new Date(updatedAt).toLocaleString("vi-VN", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" })}
              <RefreshCw className="size-2.5" />
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Score summary (bottom left) ─────────────────────────────────────────────

function ScoreSummary({
  compositePct, ltvPct, dscrValue, hardGates, conditions,
}: {
  compositePct: number | null;
  ltvPct: number | null;
  dscrValue: number | undefined;
  hardGates: { gate_id: string; status: string; reason: string | null }[];
  conditions: string[];
}) {
  const gaugeData = [{ value: compositePct ?? 0, fill: "var(--color-success-600)" }];
  const creditRating = deriveCreditRating(compositePct);
  const covenantFlags = hardGates.filter((g) => g.status !== "PASS").length;

  const metrics = [
    {
      label: "LTV",
      value: ltvPct != null ? `${ltvPct}%` : "—",
      verdict: ltvPct != null && ltvPct < 65 ? "Tốt" : ltvPct != null && ltvPct < 80 ? "Trung bình" : "Kém",
      color: ltvPct != null && ltvPct < 65 ? "var(--color-success-600)" : ltvPct != null && ltvPct < 80 ? "var(--color-warning-600)" : "var(--color-danger-600)",
    },
    {
      label: "CIC trạng thái",
      value: "Nhóm 1",
      verdict: "Tốt",
      color: "var(--color-success-600)",
    },
    {
      label: "DSCR (Ước tính)",
      value: dscrValue != null ? `${dscrValue.toFixed(2)}x` : "—",
      verdict: dscrValue != null && dscrValue >= 1.2 ? "Tốt" : "Kém",
      color: dscrValue != null && dscrValue >= 1.2 ? "var(--color-success-600)" : "var(--color-danger-600)",
    },
    {
      label: "Covenant flags",
      value: `${covenantFlags}`,
      verdict: covenantFlags === 0 ? "Tốt" : "Cảnh báo",
      color: covenantFlags === 0 ? "var(--color-success-600)" : "var(--color-warning-600)",
    },
  ];

  return (
    <Card className="py-0 gap-0 flex flex-col">
      <CardHeader className="pt-4 pb-3 px-5">
        <CardTitle className="text-sm">Tổng hợp chấm điểm & chỉ số chính</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-5 flex flex-col gap-5 flex-1">
        {/* Metric pills */}
        <div className="grid grid-cols-2 gap-2">
          {metrics.map((m) => (
            <div key={m.label} className="flex flex-col gap-0.5 rounded-lg border border-border p-2.5">
              <p className="text-[10px] text-muted-foreground font-semibold">{m.label}</p>
              <p className="text-lg font-extrabold font-[var(--font-display)]" style={{ color: m.color }}>
                {m.value}
              </p>
              <p className="text-[10px] font-bold" style={{ color: m.color }}>{m.verdict}</p>
            </div>
          ))}
        </div>

        {/* Donut gauge */}
        {compositePct !== null && (
          <div className="flex items-center gap-4">
            <div className="relative size-24 flex-none">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  cx="50%" cy="50%"
                  innerRadius="60%" outerRadius="90%"
                  startAngle={90} endAngle={-270}
                  data={gaugeData}
                >
                  <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                  <RadialBar dataKey="value" angleAxisId={0} background={{ fill: "var(--color-gray-100)" }} />
                </RadialBarChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-lg font-extrabold text-[var(--color-success-600)]">{compositePct}/100</span>
                <span className="text-[10px] text-muted-foreground">Tốt</span>
              </div>
            </div>
            <div className="flex-1">
              <p className="text-xs text-muted-foreground font-semibold mb-1">Điểm tổng hợp</p>
              <p className="text-2xl font-extrabold text-[var(--color-success-600)] font-[var(--font-display)]">
                {compositePct}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">Dựa trên {4} chiều đánh giá</p>
            </div>
          </div>
        )}

        {/* Score bar */}
        <div>
          <p className="text-[11px] font-bold text-muted-foreground mb-1.5">Thang điểm khuyến nghị</p>
          <div className="relative h-3 rounded-full overflow-hidden" style={{
            background: "linear-gradient(to right, var(--color-danger-600), var(--color-warning-600), var(--color-success-600))",
          }}>
            {compositePct !== null && (
              <div
                className="absolute top-0 bottom-0 w-1 bg-white shadow-md rounded-full"
                style={{ left: `calc(${compositePct}% - 2px)` }}
              />
            )}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
            <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
          </div>
        </div>

        {/* Credit rating */}
        <div>
          <p className="text-[11px] font-bold text-muted-foreground mb-2">Xếp hạng nội bộ</p>
          <div className="inline-flex items-center justify-center px-5 py-2 border-2 border-[var(--color-navy-700)] rounded-lg">
            <span className="text-xl font-extrabold text-[var(--color-navy-700)] font-[var(--font-display)]">
              {creditRating}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Verdict card (bottom center) ────────────────────────────────────────────

function VerdictCard({
  decision, caseDetail, onAccept, onOverride, canDecide, staleTitle, findingByDisplayId, setSelectedFinding,
}: {
  decision: CaseDetail["decision"];
  caseDetail: CaseDetail;
  onAccept: () => void;
  onOverride: () => void;
  canDecide: boolean;
  staleTitle: string;
  findingByDisplayId: (id: string) => Finding | undefined;
  setSelectedFinding: (f: Finding) => void;
}) {
  if (!decision) {
    return (
      <Card className="py-0 gap-0 flex flex-col">
        <CardHeader className="pt-4 pb-3 px-5">
          <CardTitle className="text-sm flex items-center gap-1.5">
            🎯 Kết luận & khuyến nghị
          </CardTitle>
        </CardHeader>
        <Separator />
        <CardContent className="p-5 flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground text-center">
            Chưa có kết quả phân tích.<br />Chạy phân tích để xem kết luận.
          </p>
        </CardContent>
      </Card>
    );
  }

  const verdict = REC_VERDICT[decision.recommendation] ?? { text: decision.recommendation, color: "var(--color-gray-700)", icon: "?" };
  const strengths = decision.strengths.slice(0, 4);

  return (
    <Card className="py-0 gap-0 flex flex-col">
      <CardHeader className="pt-4 pb-3 px-5 flex flex-row items-center justify-between">
        <CardTitle className="text-sm flex items-center gap-1.5">
          🎯 Kết luận & khuyến nghị
        </CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-5 flex flex-col gap-4 flex-1">
        {/* Verdict */}
        <div>
          <p className="text-[11px] text-muted-foreground font-semibold mb-1.5">Kết luận</p>
          <div className="flex items-center gap-2">
            <div
              className="size-8 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0"
              style={{ background: verdict.color }}
            >
              {verdict.icon}
            </div>
            <p className="text-xl font-extrabold font-[var(--font-display)]" style={{ color: verdict.color }}>
              {verdict.text}
            </p>
          </div>
        </div>

        {/* Recommendation details */}
        <div>
          <p className="text-[11px] text-muted-foreground font-semibold mb-1.5">Khuyến nghị</p>
          <div className="flex flex-col gap-1 text-sm text-foreground">
            {decision.recommended_amount_vnd != null && (
              <p>Phê duyệt hạn mức <span className="font-bold">{formatVnd(decision.recommended_amount_vnd)}</span></p>
            )}
            {decision.recommended_tenor_months != null && (
              <p>Kỳ hạn <span className="font-bold">{decision.recommended_tenor_months} tháng</span></p>
            )}
          </div>
        </div>

        <Separator />

        {/* Strengths as reasons */}
        {strengths.length > 0 && (
          <div>
            <p className="text-[11px] text-muted-foreground font-semibold mb-2">Lý do chính</p>
            <ul className="flex flex-col gap-1.5">
              {strengths.map((id) => {
                const f = findingByDisplayId(id);
                return (
                  <li
                    key={id}
                    className="flex items-start gap-2 text-xs text-foreground cursor-pointer hover:text-primary"
                    onClick={() => f && setSelectedFinding(f)}
                  >
                    <CheckCircle className="size-3.5 text-[var(--color-success-600)] shrink-0 mt-0.5" />
                    <span>{f?.claim ?? id}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Conditions */}
        {decision.conditions_precedent.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="text-[11px] text-muted-foreground font-semibold mb-2">Điều kiện tiên quyết</p>
              <ol className="flex flex-col gap-1.5 list-decimal list-inside">
                {decision.conditions_precedent.slice(0, 3).map((c, i) => (
                  <li key={i} className="text-xs text-foreground">{c}</li>
                ))}
              </ol>
            </div>
          </>
        )}

        {/* Actions */}
        <div className="mt-auto flex flex-col gap-2 pt-2">
          <Button size="sm" onClick={onAccept} disabled={!canDecide} title={canDecide ? undefined : staleTitle}>
            ✓ Chấp nhận khuyến nghị
          </Button>
          <Button variant="outline" size="sm" onClick={onOverride} disabled={!canDecide} title={canDecide ? undefined : staleTitle}>
            ↑ Override
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── RAG Evidence (bottom right) ─────────────────────────────────────────────

function RAGEvidence({
  findings, onFindingClick,
}: {
  findings: Finding[];
  onFindingClick: (f: Finding) => void;
}) {
  // Collect citations across all findings
  const citations = findings.flatMap((f) =>
    f.citations.map((c) => ({ ...c, findingClaim: f.claim, finding: f }))
  );
  const topCitations = citations.slice(0, 4);

  return (
    <Card className="py-0 gap-0 flex flex-col">
      <CardHeader className="pt-4 pb-3 px-5 flex flex-row items-center justify-between">
        <CardTitle className="text-sm flex items-center gap-1.5">
          Cơ sở tri thức (RAG Evidence)
          <Info className="size-3.5 text-muted-foreground" />
        </CardTitle>
        <Button variant="ghost" size="sm" className="text-xs text-primary gap-0.5 -mr-2">
          Xem tất cả <ChevronRight className="size-3" />
        </Button>
      </CardHeader>
      <Separator />
      <CardContent className="p-5 flex flex-col gap-3 flex-1">
        {topCitations.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có dữ liệu tri thức.</p>
        ) : (
          topCitations.map((c, i) => (
            <div
              key={i}
              className="flex items-start gap-3 p-3 rounded-lg border border-border hover:border-[var(--color-navy-300)] hover:bg-muted/30 cursor-pointer transition-colors"
              onClick={() => onFindingClick(c.finding)}
            >
              <div className="size-7 rounded bg-[var(--color-navy-50)] flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[var(--color-navy-700)] text-sm">📄</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-foreground leading-snug mb-0.5">
                  {c.section ? `${c.section} –` : ""} {c.source_id}
                </p>
                <p className="text-xs text-muted-foreground leading-snug line-clamp-2">{c.text}</p>
                {c.source_type && (
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Nguồn: {c.source_id}
                    {c.version ? ` – Phiên bản ${c.version}` : ""}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

// ─── Tab types ────────────────────────────────────────────────────────────────

type Tab = "review" | "overview" | "decision" | "chat";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CasePage() {
  const params = useParams();
  const caseId = params.caseId as string;

  const [caseDetail,      setCaseDetail]      = useState<CaseDetail | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [activeTab,       setActiveTab]       = useState<Tab>("review");
  const [auditEvents,     setAuditEvents]     = useState<AuditEvent[]>([]);
  const [busy,            setBusy]            = useState(false);
  const [log,             setLog]             = useState<string[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try { setCaseDetail(await fetchCase(caseId)); } catch { /* no-op */ }
  }, [caseId]);

  useEffect(() => {
    refresh();
    const es = new EventSource(`/sse/cases/${caseId}/stream`);
    eventSourceRef.current = es;
    es.addEventListener("progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      setLog((prev) => [...prev, `${payload.type}${payload.findings_written ? ": " + payload.findings_written.join(", ") : ""}`]);
      if (payload.type === "job_completed" || payload.type === "job_failed") {
        setBusy(false); refresh();
      }
    });
    return () => es.close();
  }, [caseId, refresh]);

  useEffect(() => {
    if (activeTab === "decision") fetchAudit(caseId).then(setAuditEvents);
  }, [activeTab, caseId]);

  const runAnalyze = async () => { setBusy(true); setLog([]); await triggerAnalyze(caseId); };

  const doAction = async (action: "accept" | "rerun" | "return" | "override", reason?: string) => {
    try {
      await decisionAction(caseId, action, reason);
      await refresh();
      if (action === "rerun") { setBusy(true); setLog([]); }
    } catch (err) {
      alert(`Không thực hiện được — hãy tải lại trang. (${String(err)})`);
      await refresh();
    }
  };

  const doOverride = async () => {
    const reason = prompt("Override khuyến nghị hệ thống — bắt buộc nhập lý do (FR-11):");
    if (!reason) return;
    await doAction("override", reason);
  };

  // ── Loading state ──────────────────────────────────────────────────
  if (!caseDetail) {
    return (
      <main className="flex flex-col gap-4 p-5">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-64 w-full" />)}
        </div>
      </main>
    );
  }

  // ── Derived values ─────────────────────────────────────────────────
  const decision   = caseDetail.decision;
  const isFresh    = caseDetail.findings.length === 0 && !decision;
  const canDecide  = caseDetail.state === "READY_FOR_REVIEW";
  const staleTitle = `Chỉ dùng được khi hồ sơ READY_FOR_REVIEW (hiện tại: ${caseDetail.state})`;

  const scores       = decision?.scores ?? [];
  const scoreSum     = scores.reduce((s, x) => s + x.score, 0);
  const scoreMax     = scores.reduce((s, x) => s + x.max, 0);
  const compositePct = scores.length > 0 && scoreMax > 0 ? Math.round((scoreSum / scoreMax) * 100) : null;
  const hardGates    = decision?.hard_gates ?? [];

  const requiredDocTypes = caseDetail.required_doc_types;
  const presentDocTypes  = new Set(caseDetail.documents.map((d) => d.doc_type));
  const missingDocTypes  = requiredDocTypes.filter((t) => !presentDocTypes.has(t));

  const financialF  = [...caseDetail.findings].reverse().find((f) => f.agent_id === "financial_analysis");
  const collateralF = [...caseDetail.findings].reverse().find((f) => f.agent_id === "collateral_legal");

  const coverageRatio = collateralF?.metrics?.coverage_ratio ?? financialF?.metrics?.coverage_ratio;
  const ltvPct        = coverageRatio != null && coverageRatio > 0 ? Math.round((1 / coverageRatio) * 100) : null;
  const dscrValue     = financialF?.metrics?.dscr;

  const agentFindingMap = new Map<string, Finding>();
  for (const f of caseDetail.findings) agentFindingMap.set(f.agent_id, f);

  const findingByDisplayId = (id: string) => caseDetail.findings.find((f) => f.display_id === id);
  const openConflicts      = caseDetail.conflicts.filter((c) => c.status !== "RESOLVED");

  // Distribute documents across agent cards (round-robin)
  const docSlots = AGENT_CARDS.map((_, i) =>
    caseDetail.documents.filter((_, j) => j % 4 === i)
  );

  const amountVnd = caseDetail.requested_facility?.amount_vnd as number | undefined;

  // ── Tab labels ─────────────────────────────────────────────────────
  const TABS: { key: Tab; label: string }[] = [
    { key: "overview", label: "360° Overview" },
    { key: "review",   label: "AI Multi-Agent Review" },
    { key: "decision", label: "Decision Hub" },
    { key: "chat",     label: "Trao đổi & Kết luận" },
  ];

  return (
    <main className="flex flex-col gap-0 min-h-screen bg-background">

      {/* ── Top header ─────────────────────────────────────────────── */}
      <div className="sticky top-0 z-20 bg-card border-b border-border">
        {/* Main header row */}
        <div className="flex items-center gap-4 px-6 py-3">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground shrink-0">
            <span className="text-muted-foreground cursor-pointer hover:text-foreground">☰</span>
            <span>Chi tiết hồ sơ</span>
          </div>
          <div className="flex-1 max-w-lg mx-auto relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Tìm kiếm hồ sơ, khách hàng, mã hồ sơ…"
              className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-muted/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-[var(--color-navy-500)]"
            />
          </div>
          <div className="flex items-center gap-3 shrink-0 ml-auto">
            <button className="relative p-2 rounded-lg hover:bg-muted transition-colors">
              <Bell className="size-5 text-muted-foreground" />
              <span className="absolute top-1 right-1 size-4 bg-[var(--color-orange-600)] text-white text-[9px] font-bold rounded-full flex items-center justify-center">6</span>
            </button>
            <div className="flex items-center gap-2 text-sm">
              <div className="size-8 rounded-full bg-[var(--color-navy-700)] flex items-center justify-center text-white text-xs font-bold shrink-0">NA</div>
              <div className="hidden sm:block">
                <p className="font-semibold text-foreground text-xs leading-tight">Nguyễn Văn An</p>
                <p className="text-[11px] text-muted-foreground">CBTD</p>
              </div>
              <ChevronDown className="size-3.5 text-muted-foreground hidden sm:block" />
            </div>
          </div>
        </div>

        {/* Sub-header: back + action buttons */}
        <div className="flex items-center justify-between px-6 py-2 border-t border-border bg-muted/30">
          <Link href="/" className="group flex items-center gap-1.5 text-sm text-[var(--color-orange-600)] transition-colors no-underline">
            <ChevronRight className="size-4 rotate-180 transition-transform duration-150 group-hover:-translate-x-0.5" />
            Quay lại danh sách
          </Link>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="gap-1.5 text-xs">
              <Download className="size-3.5" /> Tải báo cáo
            </Button>
            <Button size="sm" className="gap-1.5 text-xs">
              <FileEdit className="size-3.5" /> Chỉnh sửa hồ sơ
            </Button>
            <button className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground">
              <MoreVertical className="size-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Tab navigation ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-6 py-0 bg-card border-b border-border">
        <div className="flex items-center gap-0">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={cn(
                "px-4 py-3.5 text-sm font-semibold border-b-2 transition-colors",
                activeTab === key
                  ? "border-[var(--color-navy-700)] text-[var(--color-navy-700)]"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">Mã hồ sơ:</span>
          <span className="font-mono font-bold text-foreground">{caseDetail.case_id}</span>
          <Badge
            variant={canDecide ? "warning" : caseDetail.state === "APPROVED" ? "success" : "navy"}
            className="rounded-sm"
          >
            {caseDetail.state === "ANALYZING" ? "Đang thẩm định"
              : caseDetail.state === "READY_FOR_REVIEW" ? "Sẵn sàng phê duyệt"
              : caseDetail.state === "APPROVED" ? "Đã phê duyệt"
              : caseDetail.state}
          </Badge>
        </div>
      </div>

      {/* ── Page content ───────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 p-5 max-w-[1600px]">

        {/* ── Case hero card ─────────────────────────────────────────── */}
        <Card className="py-0 gap-0">
          <CardContent className="p-0">
            {/* Top: case ID + company name + meta row */}
            <div className="flex items-start gap-6 px-5 pt-4 pb-3 flex-wrap">
              <div className="flex-1 min-w-[280px]">
                {/* Case ID + status inline */}
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-mono text-lg font-extrabold text-[var(--color-navy-900)]">
                    {caseDetail.case_id}
                  </span>
                  <Badge
                    variant={canDecide ? "warning" : caseDetail.state === "ANALYZING" ? "navy" : caseDetail.state === "APPROVED" ? "success" : "muted"}
                    className="rounded-full text-xs gap-1"
                  >
                    <span className="size-1.5 rounded-full bg-current opacity-70 inline-block" />
                    {caseDetail.state === "ANALYZING" ? "Đang thẩm định"
                      : caseDetail.state === "READY_FOR_REVIEW" ? "Sẵn sàng phê duyệt"
                      : caseDetail.state === "APPROVED" ? "Đã phê duyệt"
                      : caseDetail.state}
                  </Badge>
                </div>
                {/* Company name */}
                <p className="text-xl font-extrabold text-[var(--color-navy-900)] font-[var(--font-display)] leading-tight mb-2">
                  {caseDetail.customer_id}
                </p>
                {/* Meta row */}
                <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                  <span>Mã KH: <span className="font-semibold text-foreground">KH{caseDetail.case_id.slice(-6)}</span></span>
                  <span>MST: <span className="font-semibold text-foreground">0101234567</span></span>
                  <span>Ngày tạo hồ sơ: <span className="font-semibold text-foreground">16/05/2025</span></span>
                  <span>CBTD tạo: <span className="font-semibold text-foreground">Nguyễn Văn An</span></span>
                </div>
              </div>

              {/* Right metadata strip */}
              <div className="flex items-start gap-6 flex-wrap border-l border-border pl-6">
                {[
                  { label: "Khách hàng",      value: caseDetail.customer_id },
                  { label: "Hạn mức đề nghị", value: amountVnd != null ? `${(amountVnd / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 3 })} tỷ VND` : "—" },
                  { label: "Xếp loại sơ bộ",  value: null, isXepLoai: true },
                  { label: "Ngành",            value: "Sản xuất bao bì" },
                  { label: "RM phụ trách",     value: "Nguyễn Văn An", sub: "CBTD" },
                ].map(({ label, value, isXepLoai, sub }) => (
                  <div key={label} className="flex flex-col gap-0.5 min-w-[100px]">
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">{label}</p>
                    {isXepLoai ? (
                      <Badge variant="warning" className="rounded-sm w-fit mt-0.5">Trung bình</Badge>
                    ) : (
                      <>
                        <p className="text-sm font-bold text-foreground">{value}</p>
                        {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Busy / Fresh states */}
        {busy ? (
          <AnalyzingView caseId={caseId} onComplete={() => setBusy(false)} />
        ) : isFresh ? (
          <Card className="py-0 gap-0">
            <CardContent className="flex flex-col items-center justify-center py-16 gap-4">
              <div className="size-16 rounded-full bg-[var(--color-navy-50)] flex items-center justify-center text-3xl">🤖</div>
              <div className="text-center">
                <p className="text-base font-bold text-foreground mb-1">Hồ sơ đã có đủ dữ liệu</p>
                <p className="text-sm text-muted-foreground">Chưa chạy phân tích AI. Nhấn bên dưới để bắt đầu.</p>
              </div>
              <Button onClick={runAnalyze}>Bắt đầu phân tích AI</Button>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* ── AI Multi-Agent Review tab ── */}
            {activeTab === "review" && (
              <>
                {/* Planner workflow */}
                <PlannerWorkflow state={caseDetail.state} updatedAt={caseDetail.findings[caseDetail.findings.length - 1]?.created_at} />

                {/* 4 Agent cards grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                  {AGENT_CARDS.map((config, i) => (
                    <AgentCard
                      key={config.id}
                      config={config}
                      finding={agentFindingMap.get(config.id)}
                      docs={docSlots[i]}
                      onFindingClick={setSelectedFinding}
                    />
                  ))}
                </div>

                {/* Bottom 3-column section */}
                {(compositePct !== null || decision) && (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
                    <ScoreSummary
                      compositePct={compositePct}
                      ltvPct={ltvPct}
                      dscrValue={dscrValue}
                      hardGates={hardGates}
                      conditions={decision?.conditions_precedent ?? []}
                    />
                    <VerdictCard
                      decision={decision}
                      caseDetail={caseDetail}
                      onAccept={() => doAction("accept")}
                      onOverride={doOverride}
                      canDecide={canDecide}
                      staleTitle={staleTitle}
                      findingByDisplayId={findingByDisplayId}
                      setSelectedFinding={setSelectedFinding}
                    />
                    <RAGEvidence
                      findings={caseDetail.findings}
                      onFindingClick={setSelectedFinding}
                    />
                  </div>
                )}

                {/* Rerun toolbar */}
                <div className="flex items-center gap-3 py-1">
                  <Button
                    variant="outline" size="sm"
                    onClick={() => doAction("rerun")}
                    disabled={busy || !canDecide}
                    title={canDecide ? undefined : staleTitle}
                    className="gap-1.5"
                  >
                    <RefreshCw className="size-3.5" /> Chạy lại phân tích
                  </Button>
                  {log.length > 0 && (
                    <span className="text-xs text-muted-foreground">{log[log.length - 1]}</span>
                  )}
                  {openConflicts.length > 0 && (
                    <Badge variant="warning" className="rounded-sm">
                      {openConflicts.length} xung đột chưa giải quyết
                    </Badge>
                  )}
                </div>
              </>
            )}

            {/* ── 360° Overview tab ── */}
            {activeTab === "overview" && (
              <Overview360 caseDetail={caseDetail} />
            )}

            {/* ── Trao đổi & Kết luận tab ── */}
            {activeTab === "chat" && (
              <ChatTab
                caseId={caseId}
                requestedAmountVnd={(caseDetail.requested_facility?.amount_vnd as number | null) ?? null}
                canDecide={canDecide}
                caseState={caseDetail.state}
                hasDecision={Boolean(caseDetail.decision)}
                onAction={(action: ActionKey, reason?: string) =>
                  doAction(action as "accept" | "rerun" | "return" | "override", reason)
                }
              />
            )}

            {/* ── Decision Hub tab ── */}
            {activeTab === "decision" && (
              <div className="flex flex-col gap-4">
                {decision ? (
                  <VerdictCard
                    decision={decision}
                    caseDetail={caseDetail}
                    onAccept={() => doAction("accept")}
                    onOverride={doOverride}
                    canDecide={canDecide}
                    staleTitle={staleTitle}
                    findingByDisplayId={findingByDisplayId}
                    setSelectedFinding={setSelectedFinding}
                  />
                ) : (
                  <Card className="py-0 gap-0">
                    <CardContent className="p-8 text-center">
                      <p className="text-sm text-muted-foreground">Chưa có quyết định. Chạy phân tích trước.</p>
                    </CardContent>
                  </Card>
                )}
                {/* Audit trail */}
                {auditEvents.length > 0 && (
                  <Card className="py-0 gap-0">
                    <CardHeader className="pt-4 pb-3 px-5">
                      <CardTitle className="text-sm">Audit Trail</CardTitle>
                    </CardHeader>
                    <Separator />
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-muted">
                          <tr>
                            <th className="px-4 py-2 text-left font-bold text-muted-foreground">#</th>
                            <th className="px-4 py-2 text-left font-bold text-muted-foreground">Event</th>
                            <th className="px-4 py-2 text-left font-bold text-muted-foreground">Actor</th>
                            <th className="px-4 py-2 text-left font-bold text-muted-foreground">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditEvents.map((e) => (
                            <tr key={e.seq} className="border-t border-border">
                              <td className="px-4 py-2 tabular-nums">{e.seq}</td>
                              <td className="px-4 py-2">{e.event_type}</td>
                              <td className="px-4 py-2 font-mono">{e.actor.type}:{e.actor.id}</td>
                              <td className="px-4 py-2 tabular-nums">{new Date(e.timestamp).toLocaleString("vi-VN")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Explainability drawer */}
      {selectedFinding && (
        <ExplainabilityDrawer
          caseId={caseId}
          finding={selectedFinding}
          onClose={() => setSelectedFinding(null)}
        />
      )}
    </main>
  );
}
