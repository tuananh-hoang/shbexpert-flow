"use client";

/**
 * Case detail — redesigned per dashmint_ai-trang's CaseDetail.tsx: 3 tabs
 * (Tổng quan / Đánh giá sơ bộ & Chấm điểm / Trao đổi & Kết luận) instead
 * of the previous 5 flat tabs (Summary/Consensus/Conflicts/Conditions/
 * Audit — Conflicts folded into the Scoring tab's MessageTimeline,
 * Conditions folded into ScoringResultPanel, Audit trail dropped from
 * this page for now per the redesign plan's "việc không làm" note).
 *
 * Data flows entirely through `/api/*` (web/app/lib/api.ts) — unchanged.
 * ExplainabilityDrawer/EvidenceViewer are reused verbatim (redesign plan:
 * "không đổi lại" — they were already better than the prototype's
 * equivalent, real PDF+bbox vs none). They're also NOT translated in this
 * EN/VI pass (out of scope — see lib/i18n.tsx's docstring).
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { AnalyzingView } from "../../components/AnalyzingView";
import type { ActionKey } from "../../components/ActionBar";
import { ApprovalTimer } from "../../components/ApprovalTimer";
import { ChatTab } from "../../components/ChatTab";
import { EvidenceViewer } from "../../components/EvidenceViewer";
import { ExplainabilityDrawer } from "../../components/ExplainabilityDrawer";
import { OverviewTab } from "../../components/OverviewTab";
import { ScoringTab } from "../../components/ScoringTab";
import { STEP_TO_AGENT_ID, type StepState } from "../../components/TaskGraph";
import { Button, CaseStatusChip, formatVnd } from "../../components/ui";
import { decisionAction, fetchEvidence, fetchCase, triggerAnalyze } from "../../lib/api";
import type { CaseDetail, EvidenceItem, Finding } from "../../lib/types";
import { ageHours } from "../../lib/priority";
import { useI18n } from "../../lib/i18n";

type Tab = "overview" | "scoring" | "chat";

const TAB_IDS: Tab[] = ["overview", "scoring", "chat"];
const TAB_KEY: Record<Tab, string> = {
  overview: "case.tab.overview",
  scoring: "case.tab.scoring",
  chat: "case.tab.chat",
};

export default function CasePage() {
  const params = useParams();
  const caseId = params.caseId as string;
  const { t, lang } = useI18n();

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [viewerEvidence, setViewerEvidence] = useState<EvidenceItem | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<StepState[]>([]);

  const refresh = useCallback(async () => {
    try {
      const detail = await fetchCase(caseId);
      setCaseDetail(detail);
      // Reloading an already-analyzed case used to show every agent stuck
      // on "Chờ xử lý" (steps started life as `useState([])`, only ever
      // populated by THIS browser session's own SSE stream) — derive the
      // real state from persisted data instead: an agent with >=1 finding
      // has run (Task 34's fan-out isolation fix means every agent now
      // always writes at least a fallback finding, so this is reliable).
      // Live SSE (below, while busy) only ADDS to this baseline (including
      // "plan"/"synthesize" step events TaskGraph no longer renders as
      // their own boxes, but the generic handler still tracks generically),
      // never replaces it wholesale.
      const agentIdsWithFindings = new Set(detail.findings.map((f) => f.agent_id));
      const derived: StepState[] = Object.entries(STEP_TO_AGENT_ID).map(([step, agentId]) => ({
        step,
        status: (agentIdsWithFindings.has(agentId) ? "done" : "pending") as StepState["status"],
      }));
      setSteps((prev) => (prev.length > 0 ? prev : derived));
    } catch {
      // case not seeded yet — page shows the loading state
    }
  }, [caseId]);

  useEffect(() => {
    refresh();
    // Deliberately NOT /api/* — see web/app/sse/cases/[caseId]/stream/route.ts
    // for why the SSE endpoint is served from its own path. This single
    // connection drives BOTH the live refresh-on-completion behavior AND
    // the TaskGraph's step states (ScoringTab) — no second EventSource.
    const es = new EventSource(`/sse/cases/${caseId}/stream`);
    es.addEventListener("progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      if (payload.type === "step_started") {
        setSteps((prev) =>
          prev.some((s) => s.step === payload.step)
            ? prev.map((s) => (s.step === payload.step ? { ...s, status: "in_progress" } : s))
            : [...prev, { step: payload.step, status: "in_progress" }]
        );
      } else if (payload.type === "step_completed") {
        // "failed" is sticky — see AnalyzingView.tsx's identical guard for
        // why (_run_fanout_agent publishes step_failed then the outer
        // wrapper still publishes its own step_completed right after).
        setSteps((prev) => prev.map((s) => (s.step === payload.step && s.status !== "failed" ? { ...s, status: "done" } : s)));
      } else if (payload.type === "step_failed") {
        setSteps((prev) => prev.map((s) => (s.step === payload.step ? { ...s, status: "failed" } : s)));
      } else if (payload.type === "job_completed" || payload.type === "job_failed") {
        setBusy(false);
        refresh();
      }
    });
    return () => es.close();
  }, [caseId, refresh]);

  const runAnalyze = async () => {
    setBusy(true);
    setSteps([]);
    await triggerAnalyze(caseId);
  };

  const doAction = async (action: "accept" | "return" | "override" | "reject" | "escalate", reason?: string) => {
    try {
      await decisionAction(caseId, action, reason);
      await refresh();
    } catch (err) {
      alert(t("case.actionFailed", { err: String(err) }));
      await refresh();
    }
  };

  // ActionBar (rendered inside ChatTab) already collects a mandatory note
  // via its own inline confirm UI for reject/escalate/override — no
  // separate prompt()-based flow needed here anymore.
  const handleActionBarAction = (action: ActionKey, reason?: string) => doAction(action, reason);

  const openEvidenceById = async (evidenceId: string) => {
    const [item] = await fetchEvidence(caseId, [evidenceId]);
    if (item) setViewerEvidence(item);
  };

  if (!caseDetail) {
    return (
      <main className="mx-auto max-w-7xl px-8 py-8">
        <p style={{ color: "var(--text-muted-2)" }}>{t("case.loading", { id: caseId })}</p>
      </main>
    );
  }

  const isFresh = caseDetail.findings.length === 0 && !caseDetail.decision;
  const canDecide = caseDetail.state === "READY_FOR_REVIEW";
  const isResolved = caseDetail.state === "SUBMITTED_FOR_APPROVAL" || caseDetail.state === "READY_FOR_DISBURSEMENT";

  return (
    <main className="mx-auto max-w-7xl px-8 py-8">
      <Link
        href="/"
        className="mb-3 inline-flex items-center gap-1.5 text-sm"
        style={{ color: "var(--text-muted-2)" }}
      >
        <ArrowLeft size={14} /> {t("case.back")}
      </Link>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <CaseStatusChip state={caseDetail.state} />
            <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
              {caseDetail.customer_id}
            </h1>
          </div>
          <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            {caseDetail.product} · {formatVnd(caseDetail.requested_facility.amount_vnd as number, lang)} ·{" "}
            {t("case.tenorLabel")} {(caseDetail.requested_facility.tenor_months as number) ?? "—"} {t("case.tenorMonths")}
          </div>
        </div>
        <ApprovalTimer elapsedHours={ageHours(caseDetail.created_at)} isResolved={isResolved} />
      </div>

      {busy ? (
        <AnalyzingView caseId={caseId} onComplete={() => setBusy(false)} />
      ) : isFresh ? (
        <div className="mx-auto max-w-md rounded-xl border border-dashed p-10 text-center" style={{ borderColor: "var(--border-strong-2)" }}>
          <p className="mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>
            {t("case.freshNotice")}
          </p>
          <Button variant="primary" onClick={runAnalyze}>
            {t("case.startAnalyze")}
          </Button>
        </div>
      ) : (
        <>
          <div className="mb-5 flex gap-1.5 border-b" style={{ borderColor: "var(--border-hairline)" }}>
            {TAB_IDS.map((tabId) => (
              <button
                key={tabId}
                onClick={() => setActiveTab(tabId)}
                className="-mb-px border-b-2 px-3.5 py-2 text-sm font-medium"
                style={
                  activeTab === tabId
                    ? { borderColor: "var(--brand)", color: "var(--brand)" }
                    : { borderColor: "transparent", color: "var(--text-secondary)" }
                }
              >
                {t(TAB_KEY[tabId])}
              </button>
            ))}
          </div>

          {activeTab === "overview" && <OverviewTab caseDetail={caseDetail} onOpenEvidence={openEvidenceById} />}
          {activeTab === "scoring" && (
            <ScoringTab caseDetail={caseDetail} steps={steps} onSelectFinding={setSelectedFinding} />
          )}
          {activeTab === "chat" && (
            <ChatTab
              caseId={caseId}
              requestedAmountVnd={(caseDetail.requested_facility.amount_vnd as number) ?? null}
              canDecide={canDecide}
              hasDecision={caseDetail.decision != null}
              onAction={handleActionBarAction}
            />
          )}
        </>
      )}

      {selectedFinding && (
        <ExplainabilityDrawer caseId={caseId} finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
      )}
      {viewerEvidence && <EvidenceViewer evidence={viewerEvidence} onClose={() => setViewerEvidence(null)} />}
    </main>
  );
}
