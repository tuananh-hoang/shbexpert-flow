"use client";

/**
 * Analyzing / "thinking" screen (frontend-flow plan Phase 2) — shown
 * between "Bắt đầu phân tích" and the Dashboard. Renders the REAL
 * execution trace published by worker/app/graph/build.py's
 * `_with_progress` wrapper (step_started/step_completed per LangGraph
 * node) over the same SSE stream the Dashboard already uses — steps
 * appear in whatever order/concurrency they actually happen in (the 3
 * expert agents genuinely run in parallel, so their entries appear
 * together), never a pre-scripted animation.
 */
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../lib/i18n";

type StepStatus = "in_progress" | "done" | "failed";

interface StepState {
  step: string;
  label: string;
  status: StepStatus;
}

function Spinner() {
  return <span className="spinner" />;
}

export function AnalyzingView({ caseId, onComplete }: { caseId: string; onComplete: () => void }) {
  const { t } = useI18n();
  const [steps, setSteps] = useState<StepState[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  // The parent (CasePage) passes a fresh `onComplete` closure on every
  // render (it also has its own SSE listener that re-renders on every
  // progress message) — depending on `onComplete` directly in the effect
  // below would tear down and reopen this EventSource on nearly every
  // message. Redis pub/sub doesn't buffer, so a reconnect thrashing loop
  // like that silently drops whatever fires while re-subscribing — this
  // is exactly the bug that caused zero steps to ever render. A ref
  // sidesteps it: the effect only depends on `caseId`, so the connection
  // stays open for the whole run.
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    // Deliberately NOT /api/* — see web/app/sse/cases/[caseId]/stream/route.ts
    // for why the SSE endpoint is served from its own path.
    const es = new EventSource(`/sse/cases/${caseId}/stream`);
    es.addEventListener("progress", (event) => {
      const payload = JSON.parse((event as MessageEvent).data);
      if (payload.type === "step_started") {
        setSteps((prev) =>
          prev.some((s) => s.step === payload.step)
            ? prev
            : [...prev, { step: payload.step, label: payload.label, status: "in_progress" as StepStatus }]
        );
      } else if (payload.type === "step_completed") {
        // "failed" is STICKY per step: a fan-out agent that errors now
        // publishes step_failed itself, then the outer node wrapper still
        // publishes its own step_completed right after (isolation fix,
        // worker/app/graph/build.py::_run_fanout_agent) — without this
        // guard the later step_completed would silently flip a genuinely
        // failed agent back to a green checkmark.
        setSteps((prev) => prev.map((s) => (s.step === payload.step && s.status !== "failed" ? { ...s, status: "done" } : s)));
      } else if (payload.type === "step_failed") {
        setSteps((prev) => prev.map((s) => (s.step === payload.step ? { ...s, status: "failed" } : s)));
      } else if (payload.type === "job_completed") {
        onCompleteRef.current();
      } else if (payload.type === "job_failed") {
        setFailed(payload.error ?? t("analyzing.unknownError"));
      }
    });
    return () => es.close();
  }, [caseId]);

  return (
    <div className="card" style={{ maxWidth: 520, margin: "60px auto" }}>
      <div className="card-title">{t("analyzing.title")}</div>
      {steps.length === 0 && <p className="muted">{t("analyzing.starting")}</p>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {steps.map((s) => (
          <li
            key={s.step}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 0",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <span style={{ width: 18, textAlign: "center" }}>
              {s.status === "done" && <span style={{ color: "var(--support)" }}>✓</span>}
              {s.status === "failed" && <span style={{ color: "var(--oppose)" }}>✗</span>}
              {s.status === "in_progress" && <Spinner />}
            </span>
            <span style={{ fontSize: 14 }}>{s.label}</span>
          </li>
        ))}
      </ul>
      {failed && (
        <p style={{ color: "var(--oppose)", marginTop: 12 }}>
          {t("analyzing.failed", { error: failed })}
        </p>
      )}
    </div>
  );
}
