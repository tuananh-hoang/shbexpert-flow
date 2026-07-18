// Queue priority — NOT a backend field (Case has no priority column).
// Computed client-side from SLA aging (how long since last update) + deal
// size, independent of risk/findings — same intent as the
// dashmint_ai-trang prototype's priority.ts, but thresholds here are a
// clearly-labeled MOCK cutoff (no SHB SLA policy behind them), consistent
// with every other mock threshold already in this codebase (DSCR>=1.3,
// coverage tiers, etc. — see worker/app/agents/*.py comments).
import type { CaseSummary } from "./types";
import type { Priority } from "../components/ui";

const URGENT_AGE_HOURS = 48;
const URGENT_AMOUNT_VND = 10_000_000_000;
const HIGH_AGE_HOURS = 24;
const HIGH_AMOUNT_VND = 3_000_000_000;

export function ageHours(updatedAt: string): number {
  return (Date.now() - new Date(updatedAt).getTime()) / (1000 * 60 * 60);
}

export function computePriority(c: CaseSummary): Priority {
  const age = ageHours(c.updated_at);
  const amount = typeof c.requested_facility.amount_vnd === "number" ? c.requested_facility.amount_vnd : 0;

  if (age >= URGENT_AGE_HOURS || amount >= URGENT_AMOUNT_VND) return "urgent";
  if (age >= HIGH_AGE_HOURS || amount >= HIGH_AMOUNT_VND) return "high";
  return "normal";
}

const PRIORITY_RANK: Record<Priority, number> = { urgent: 0, high: 1, normal: 2 };

/** Sort by priority first, then by longest-waiting within the same tier —
 * matches the prototype's QueueList ordering intent. */
export function sortByPriority(cases: CaseSummary[]): (CaseSummary & { priority: Priority })[] {
  return cases
    .map((c) => ({ ...c, priority: computePriority(c) }))
    .sort((a, b) => {
      const rankDiff = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
      if (rankDiff !== 0) return rankDiff;
      return ageHours(b.updated_at) - ageHours(a.updated_at);
    });
}

/** "Pending" = anything not yet past the Credit Officer's review step
 * (shared/state.py::ALLOWED_TRANSITIONS — SUBMITTED_FOR_APPROVAL onward is
 * past the queue's concern). */
const PENDING_STATES = new Set([
  "DRAFT",
  "INTAKE_VALIDATION",
  "NEED_INFO",
  "ANALYZING",
  "CHALLENGE",
  "READY_FOR_REVIEW",
]);

export function isPending(c: CaseSummary): boolean {
  return PENDING_STATES.has(c.state);
}

/** Cases that have LEFT the Credit Officer's queue by moving forward
 * (not by being sent back to NEED_INFO) — `updated_at` at this point is
 * the timestamp of that forward transition, so `updated_at - created_at`
 * is a real elapsed processing-time sample, not a placeholder. Same
 * states ApprovalTimer.tsx's `isResolved` already treats as "done". */
const FORWARD_RESOLVED_STATES = new Set([
  "SUBMITTED_FOR_APPROVAL",
  "CONDITION_FULFILLMENT",
  "READY_FOR_DISBURSEMENT",
]);

/** Average real processing time (hours) across every case that has
 * reached a forward-resolved state — `null` when there isn't one yet
 * (honest "no data" instead of a fabricated number), never a hardcoded
 * "—" regardless of what's actually in the queue. */
export function averageApprovalHours(cases: CaseSummary[]): number | null {
  const samples = cases
    .filter((c) => FORWARD_RESOLVED_STATES.has(c.state))
    .map((c) => (new Date(c.updated_at).getTime() - new Date(c.created_at).getTime()) / (1000 * 60 * 60));
  if (samples.length === 0) return null;
  return samples.reduce((a, b) => a + b, 0) / samples.length;
}
