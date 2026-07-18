"use client";

import { useEffect, useRef, useState } from "react";
import {
  Send, Paperclip, Scale, ShieldCheck, CheckCircle2, XCircle,
  ChevronRight, RefreshCw, ArrowUpCircle, RotateCcw, Sparkles, User2,
} from "lucide-react";
import { fetchChatMessages, sendChatMessage, fetchCreditMemo } from "../../lib/api";
import type { CaseDetail, ChatMessageDto, CreditMemo } from "../../lib/types";
import { RichText } from "../../components/RichText";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Separator } from "../../components/ui/separator";
import { cn } from "../../lib/utils";

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtVnd(v: number | null | undefined) {
  if (v == null) return "—";
  return v.toLocaleString("vi-VN") + " VND";
}

// ─── Agent config ─────────────────────────────────────────────────────────────

const AGENTS = [
  { id: "legal",     label: "Legal Agent",    Icon: Scale,       color: "var(--color-navy-700)",    bg: "var(--color-navy-50)" },
  { id: "risk",      label: "Risk Agent",     Icon: ShieldCheck, color: "var(--color-danger-600)",  bg: "var(--color-danger-50)" },
];

// ─── Message bubble ──────────────────────────────────────────────────────────

function MessageBubble({ role, content, agentId, timestamp, streaming }: {
  role: "USER" | "ASSISTANT";
  content: string;
  agentId?: string;
  timestamp?: string;
  streaming?: boolean;
}) {
  const isUser = role === "USER";
  const agent = AGENTS.find((a) => a.id === agentId) ?? AGENTS[0];

  return (
    <div className={cn("flex items-start gap-2.5", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <span
        className="flex size-8 shrink-0 items-center justify-center rounded-full text-white text-xs font-bold"
        style={{ background: isUser ? "var(--color-navy-700)" : agent.color }}
      >
        {isUser ? <User2 className="size-4" /> : <agent.Icon className="size-4" />}
      </span>

      <div className={cn("flex flex-col gap-1 max-w-[78%]", isUser && "items-end")}>
        {!isUser && (
          <p className="text-xs font-semibold" style={{ color: agent.color }}>
            {agent.label}
            {timestamp && (
              <span className="ml-2 font-normal text-[var(--color-gray-400)]">
                {new Date(timestamp).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </p>
        )}
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-[var(--color-navy-700)] text-white"
              : "rounded-tl-sm border border-[var(--color-gray-200)] bg-white text-[var(--color-gray-900)]"
          )}
        >
          {isUser ? content : <RichText text={content} />}
          {streaming && <span className="ml-0.5 animate-pulse">▍</span>}
        </div>
        {isUser && timestamp && (
          <p className="text-[11px] text-[var(--color-gray-400)]">
            {new Date(timestamp).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Suggested questions ──────────────────────────────────────────────────────

const SUGGESTIONS = [
  "Điều kiện giải ngân là gì?",
  "Tài sản bảo đảm cần bổ sung gì?",
  "Covenant tài chính áp dụng thế nào?",
  "Xem lịch sử covenant",
];

// ─── Agent Chat Panel ─────────────────────────────────────────────────────────

function AgentChatPanel({ caseId }: { caseId: string }) {
  const [activeAgent, setActiveAgent] = useState(AGENTS[0].id);
  const [messages, setMessages] = useState<ChatMessageDto[] | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChatMessages(caseId).then(setMessages).catch(() => setMessages([]));
  }, [caseId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streaming]);

  const send = async (content: string) => {
    const text = content.trim();
    if (!text || sending) return;
    setSending(true);
    setDraft("");
    setStreaming("");
    try {
      await sendChatMessage(caseId, text, (chunk) => setStreaming((p) => (p ?? "") + chunk));
    } finally {
      const refreshed = await fetchChatMessages(caseId).catch(() => null);
      if (refreshed) setMessages(refreshed);
      setStreaming(null);
      setSending(false);
    }
  };

  const shown = (messages ?? []).filter((m) => m.role !== "SYSTEM");
  const isEmpty = messages !== null && shown.length === 0 && streaming === null;

  return (
    <Card className="py-0 gap-0 flex flex-col overflow-hidden" style={{ height: 640 }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-[var(--color-gray-100)]">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-bold text-[var(--color-navy-900)]">Chatbot Interaction</p>
          <span className="text-xs text-[var(--color-gray-400)]">ⓘ</span>
        </div>
        <button className="flex items-center gap-1 text-xs text-[var(--color-gray-500)] hover:text-[var(--color-navy-700)] transition-colors">
          Lịch sử hội thoại <RefreshCw className="size-3" />
        </button>
      </div>

      {/* Agent selector */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--color-gray-100)]">
        {AGENTS.map((a) => (
          <button
            key={a.id}
            onClick={() => setActiveAgent(a.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
              activeAgent === a.id
                ? "border-[var(--color-gray-300)] bg-white shadow-sm"
                : "border-transparent bg-transparent text-[var(--color-gray-500)] hover:bg-[var(--color-gray-50)]"
            )}
            style={activeAgent === a.id ? { color: a.color } : {}}
          >
            <a.Icon className="size-3.5" />
            {a.label}
            <span
              className="size-1.5 rounded-full"
              style={{ background: "var(--color-success-600)" }}
            />
          </button>
        ))}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages === null ? (
          <p className="text-sm text-center text-[var(--color-gray-400)] mt-8">Đang tải hội thoại…</p>
        ) : isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <Sparkles className="size-6 text-[var(--color-orange-400)]" />
            <p className="text-sm text-[var(--color-gray-500)] max-w-xs">
              Nhập câu hỏi cho Legal Agent hoặc Risk Agent để bắt đầu phân tích.
            </p>
          </div>
        ) : (
          <>
            {shown.map((m) => (
              <MessageBubble
                key={m.message_id}
                role={m.role as "USER" | "ASSISTANT"}
                content={m.content}
                agentId={activeAgent}
                timestamp={m.created_at}
              />
            ))}
            {streaming !== null && (
              <MessageBubble role="ASSISTANT" content={streaming} agentId={activeAgent} streaming />
            )}
          </>
        )}
      </div>

      {/* Suggestions */}
      {isEmpty && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2 pt-1 border-t border-[var(--color-gray-100)]">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="px-2.5 py-1 rounded-full border border-[var(--color-gray-200)] text-xs text-[var(--color-gray-600)] hover:border-[var(--color-orange-400)] hover:text-[var(--color-orange-600)] transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-[var(--color-gray-100)]">
        <button className="text-[var(--color-gray-400)] hover:text-[var(--color-gray-600)] transition-colors shrink-0">
          <Paperclip className="size-4" />
        </button>
        <input
          className="flex-1 text-sm bg-transparent outline-none text-[var(--color-gray-900)] placeholder:text-[var(--color-gray-400)]"
          placeholder={`Nhập câu hỏi cho ${AGENTS.find((a) => a.id === activeAgent)?.label ?? "Agent"}…`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); } }}
          disabled={sending}
        />
        <button
          onClick={() => send(draft)}
          disabled={!draft.trim() || sending}
          className="shrink-0 flex items-center justify-center size-8 rounded-full bg-[var(--color-orange-600)] text-white hover:bg-[var(--color-orange-700)] disabled:opacity-40 transition-colors"
        >
          <Send className="size-3.5" />
        </button>
      </div>
    </Card>
  );
}

// ─── Decision Summary Card ────────────────────────────────────────────────────

function DecisionSummaryCard({ caseDetail }: { caseDetail: CaseDetail }) {
  const d = caseDetail.decision;

  const STATE_LABEL: Record<string, { label: string; color: string; bg: string }> = {
    ANALYZING:              { label: "Đang thẩm định", color: "var(--color-warning-700)", bg: "var(--color-warning-100)" },
    READY_FOR_REVIEW:       { label: "Chờ phê duyệt",  color: "var(--color-success-700)", bg: "var(--color-success-100)" },
    SUBMITTED_FOR_APPROVAL: { label: "Đã trình duyệt", color: "var(--color-navy-700)",    bg: "var(--color-navy-50)" },
    APPROVED:               { label: "Đã phê duyệt",   color: "var(--color-success-700)", bg: "var(--color-success-100)" },
    REJECTED:               { label: "Từ chối",         color: "var(--color-danger-700)",  bg: "var(--color-danger-100)" },
  };
  const stateInfo = STATE_LABEL[caseDetail.state] ?? { label: caseDetail.state, color: "var(--color-gray-700)", bg: "var(--color-gray-100)" };

  const amountReq = caseDetail.requested_facility?.amount_vnd as number | undefined;
  const amountRec = d?.recommended_amount_vnd;

  const financialF = [...caseDetail.findings].reverse().find((f) => f.agent_id === "financial_analysis");
  const dscr = financialF?.metrics?.dscr;
  const icr  = financialF?.metrics?.icr ?? (dscr ? dscr * 1.48 : null);
  const ntt  = financialF?.metrics?.debt_ratio ? Math.round(financialF.metrics.debt_ratio * 100) : 48;

  const COVENANTS = [
    { label: "DSCR ≥ 1.20 lần", value: dscr ? `${dscr.toFixed(2)}` : "—", pass: dscr == null || dscr >= 1.2 },
    { label: "ICR ≥ 2.00 lần",  value: icr  ? `${icr.toFixed(2)}`  : "—", pass: icr  == null || icr  >= 2.0 },
    { label: "Nợ/TTS ≤ 60%",    value: `${ntt}%`,                          pass: ntt <= 60 },
    { label: "Báo cáo tài chính Q1/2025", value: "Đã nộp", pass: true },
    { label: "Không có nợ xấu tại TCTD",  value: "Đạt",    pass: true },
  ];

  const conditions = d?.conditions_precedent.slice(0, 4) ?? [
    "Tài sản bảo đảm hợp lệ",
    "Bảo hiểm tài sản",
    "Ký HD tín dụng & công chứng",
    "Phí & lãi trong hạn",
  ];
  const conditionPass = [true, true, false, true];

  return (
    <Card className="py-0 gap-0 overflow-hidden">
      <CardHeader className="pt-4 pb-3 px-5">
        <CardTitle className="text-sm">Tóm tắt quyết định</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="p-0">
        <div className="grid grid-cols-3 divide-x divide-[var(--color-gray-100)]">
          {/* Col 1: Status */}
          <div className="p-4 flex flex-col gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-1.5">Trạng thái hồ sơ</p>
              <span
                className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold"
                style={{ color: stateInfo.color, background: stateInfo.bg }}
              >
                {stateInfo.label}
              </span>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-0.5">SLA</p>
              <p className="text-sm font-bold text-[var(--color-danger-600)]">-1 ngày</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-0.5">Hạn mức đề nghị</p>
              <p className="text-xs font-semibold text-[var(--color-gray-900)] tabular-nums">{fmtVnd(amountReq)}</p>
            </div>
            {amountRec && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-0.5">Hạn mức đánh giá</p>
                <p className="text-xs font-semibold text-[var(--color-gray-900)] tabular-nums">{fmtVnd(amountRec)}</p>
              </div>
            )}
            {d && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-1">Xếp hạng tín dụng nội bộ</p>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-[var(--color-navy-50)] text-[var(--color-navy-700)] text-xs font-bold">
                  BB <span className="font-normal text-[var(--color-gray-500)]">Trung bình khá</span>
                </span>
              </div>
            )}
          </div>

          {/* Col 2: Covenants */}
          <div className="p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-2.5">Checklist covenant chính</p>
            <div className="flex flex-col gap-2">
              {COVENANTS.map((cv) => (
                <div key={cv.label} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {cv.pass
                      ? <CheckCircle2 className="size-3.5 shrink-0 text-[var(--color-success-600)]" />
                      : <XCircle className="size-3.5 shrink-0 text-[var(--color-danger-600)]" />
                    }
                    <span className="text-xs text-[var(--color-gray-700)] truncate">{cv.label}</span>
                  </div>
                  <span className="text-xs font-semibold text-[var(--color-gray-900)] shrink-0">{cv.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Col 3: Approval conditions */}
          <div className="p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-2.5">Điều kiện phê duyệt</p>
            <div className="flex flex-col gap-2">
              {conditions.map((c, i) => (
                <div key={i} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {conditionPass[i] !== false
                      ? <CheckCircle2 className="size-3.5 shrink-0 text-[var(--color-success-600)]" />
                      : <XCircle className="size-3.5 shrink-0 text-[var(--color-danger-600)]" />
                    }
                    <span className="text-xs text-[var(--color-gray-700)] truncate">{c}</span>
                  </div>
                  <span
                    className="text-xs font-semibold shrink-0"
                    style={{ color: conditionPass[i] !== false ? "var(--color-success-600)" : "var(--color-danger-600)" }}
                  >
                    {conditionPass[i] !== false ? "Đạt" : "Chưa"}
                  </span>
                </div>
              ))}
            </div>
            <button className="group mt-3 flex items-center gap-0.5 text-xs font-semibold text-[var(--color-orange-600)]">
              Xem chi tiết điều kiện
              <ChevronRight className="size-3 transition-transform duration-150 group-hover:translate-x-0.5" />
            </button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Routing flow ─────────────────────────────────────────────────────────────

const ROUTING_STEPS = ["CBTD (Bạn)", "GDPD", "HĐTD", "HĐTV"];

function RoutingFlow() {
  return (
    <Card className="py-0 gap-0">
      <CardContent className="px-5 py-4">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-gray-500)] mb-3">Định tuyến khuyến nghị</p>
        <div className="flex items-center gap-0">
          {ROUTING_STEPS.map((step, i) => (
            <div key={step} className="flex items-center">
              <div
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-semibold border",
                  i === 0
                    ? "border-[var(--color-orange-600)] text-[var(--color-orange-600)] bg-[var(--color-orange-50)]"
                    : "border-[var(--color-gray-200)] text-[var(--color-gray-600)] bg-white"
                )}
              >
                {step}
              </div>
              {i < ROUTING_STEPS.length - 1 && (
                <ChevronRight className="size-4 text-[var(--color-gray-300)] mx-1 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Action Center ────────────────────────────────────────────────────────────

type ActionKey = "return" | "reject" | "accept" | "escalate";

const ACTIONS: { key: ActionKey; label: string; sublabel: string; Icon: typeof CheckCircle2; color: string; bg: string }[] = [
  { key: "return",   label: "Trả lại RM bổ sung", sublabel: "Điều 4.3",  Icon: RotateCcw,     color: "var(--color-warning-600)", bg: "var(--color-warning-50)" },
  { key: "reject",   label: "Từ chối",             sublabel: "Mẫu 4.5",  Icon: XCircle,        color: "var(--color-danger-600)",  bg: "var(--color-danger-50)" },
  { key: "accept",   label: "Phê duyệt",           sublabel: "",          Icon: CheckCircle2,   color: "var(--color-success-600)", bg: "var(--color-success-50)" },
  { key: "escalate", label: "Trình cấp trên",      sublabel: "GDPD / HĐTD / HĐTV", Icon: ArrowUpCircle, color: "var(--color-navy-600)", bg: "var(--color-navy-50)" },
];

function ActionCenter({ caseId, canDecide, onAction }: {
  caseId: string;
  canDecide: boolean;
  onAction: (action: ActionKey, reason?: string) => void;
}) {
  const [memo, setMemo] = useState<CreditMemo | null>(null);
  const [loadingMemo, setLoadingMemo] = useState(false);
  const [memoError, setMemoError] = useState<string | null>(null);

  const generateMemo = async () => {
    setLoadingMemo(true);
    setMemoError(null);
    try {
      setMemo(await fetchCreditMemo(caseId));
    } catch (e) {
      setMemoError("Không thể tạo credit memo. Thử lại sau.");
    } finally {
      setLoadingMemo(false);
    }
  };

  return (
    <Card className="py-0 gap-0 overflow-hidden">
      <div className="grid grid-cols-[1fr_1fr] divide-x divide-[var(--color-gray-100)]">
        {/* Left: Actions */}
        <div className="p-4 flex flex-col gap-3">
          <div>
            <p className="text-sm font-bold text-[var(--color-navy-900)] mb-0.5">Action Center</p>
            <p className="text-xs text-[var(--color-gray-500)]">Xác nhận Credit Memo</p>
          </div>

          {/* Generate memo button */}
          <button
            onClick={generateMemo}
            disabled={loadingMemo}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border border-[var(--color-orange-300)] text-[var(--color-orange-600)] text-xs font-semibold hover:bg-[var(--color-orange-50)] transition-colors disabled:opacity-50"
          >
            {loadingMemo
              ? <RefreshCw className="size-3.5 animate-spin" />
              : <Sparkles className="size-3.5" />
            }
            Tự động tạo BC TDTD theo Mẫu 2 Phụ lục 03
          </button>
          {memoError && <p className="text-xs text-[var(--color-danger-600)]">{memoError}</p>}

          {/* Action buttons */}
          <div className="grid grid-cols-2 gap-2">
            {ACTIONS.map(({ key, label, sublabel, Icon, color, bg }) => (
              <button
                key={key}
                onClick={() => onAction(key)}
                disabled={!canDecide || (!memo && key === "accept")}
                className="flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl border border-[var(--color-gray-100)] hover:border-[var(--color-gray-200)] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: bg }}
              >
                <Icon className="size-5" style={{ color }} />
                <span className="text-[11px] font-semibold text-center leading-tight" style={{ color }}>
                  {label}
                </span>
                {sublabel && (
                  <span className="text-[10px] text-[var(--color-gray-400)]">{sublabel}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Memo preview */}
        <div className="p-4 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold text-[var(--color-navy-900)]">Xem trước Credit Memo (Mẫu 2 PL03)</p>
            {memo && (
              <span className="px-2 py-0.5 rounded text-[10px] font-bold text-[var(--color-success-700)] bg-[var(--color-success-50)]">
                Sẵn sàng
              </span>
            )}
          </div>

          {!memo ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center py-8 border border-dashed border-[var(--color-gray-200)] rounded-lg">
              <p className="text-xs text-[var(--color-gray-400)]">
                Tạo Credit Memo để xem trước tài liệu
              </p>
            </div>
          ) : (
            <div className="flex-1 border border-[var(--color-gray-200)] rounded-lg overflow-hidden">
              <div className="bg-[var(--color-gray-50)] px-3 py-2 border-b border-[var(--color-gray-200)]">
                <p className="text-[10px] text-center font-semibold text-[var(--color-gray-700)] uppercase tracking-wide">
                  BÁO CÁO THẨM ĐỊNH TÍN DỤNG
                </p>
                <p className="text-[10px] text-center text-[var(--color-gray-500)]">(Mẫu 2 – Phụ lục 03)</p>
              </div>
              <div className="p-3 space-y-1.5 max-h-[200px] overflow-y-auto">
                {memo.sections.slice(0, 3).map((s) => (
                  <div key={s.title}>
                    <p className="text-[10px] font-bold text-[var(--color-navy-700)]">{s.title}</p>
                    <p className="text-[10px] text-[var(--color-gray-600)] line-clamp-2">{s.content[0]}</p>
                  </div>
                ))}
              </div>
              <div className="px-3 py-2 border-t border-[var(--color-gray-100)] flex justify-end">
                <button className="group flex items-center gap-0.5 text-xs font-semibold text-[var(--color-orange-600)]">
                  Xem toàn bộ
                  <ChevronRight className="size-3 transition-transform duration-150 group-hover:translate-x-0.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function TraoDoiTab({
  caseId,
  caseDetail,
  canDecide,
  onAction,
}: {
  caseId: string;
  caseDetail: CaseDetail;
  canDecide: boolean;
  onAction: (action: "accept" | "rerun" | "return" | "override" | "reject" | "escalate", reason?: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_520px] gap-5 items-start">
      <AgentChatPanel caseId={caseId} />

      <div className="flex flex-col gap-4">
        <DecisionSummaryCard caseDetail={caseDetail} />
        <RoutingFlow />
        <ActionCenter
          caseId={caseId}
          canDecide={canDecide}
          onAction={(a) => onAction(a as any)}
        />
      </div>
    </div>
  );
}
