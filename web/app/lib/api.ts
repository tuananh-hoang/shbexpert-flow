import type { AuditEvent, CaseDetail, CaseSummary, EvidenceItem } from "./types";

// Every call goes through /api/* — next.config.mjs rewrites this to
// `api`. `web` never talks to postgres/redis/qdrant directly
// (overview.md §4).

export async function fetchCases(): Promise<CaseSummary[]> {
  const res = await fetch(`/api/cases`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetchCases failed: ${res.status}`);
  const data = await res.json();
  return data.cases;
}

export async function fetchCase(caseId: string): Promise<CaseDetail> {
  const res = await fetch(`/api/cases/${caseId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetchCase failed: ${res.status}`);
  return res.json();
}

export async function fetchFindingHistory(caseId: string, findingKey: string) {
  const res = await fetch(`/api/cases/${caseId}/findings/${findingKey}/history`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetchFindingHistory failed: ${res.status}`);
  return res.json() as Promise<{ finding_key: string; versions: CaseDetail["findings"] }>;
}

export async function fetchEvidence(caseId: string, evidenceIds: string[]): Promise<EvidenceItem[]> {
  if (evidenceIds.length === 0) return [];
  const res = await fetch(`/api/cases/${caseId}/evidence?ids=${evidenceIds.join(",")}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetchEvidence failed: ${res.status}`);
  const data = await res.json();
  return data.evidence;
}

export async function fetchAudit(caseId: string): Promise<AuditEvent[]> {
  const res = await fetch(`/api/cases/${caseId}/audit`, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetchAudit failed: ${res.status}`);
  const data = await res.json();
  return data.events;
}

export async function triggerAnalyze(caseId: string): Promise<void> {
  const res = await fetch(`/api/cases/${caseId}/analyze`, { method: "POST" });
  if (!res.ok) throw new Error(`triggerAnalyze failed: ${res.status}`);
}

export async function decisionAction(
  caseId: string,
  action: "accept" | "edit" | "rerun" | "return" | "override",
  reason?: string
): Promise<{ state: string }> {
  const res = await fetch(`/api/cases/${caseId}/decision/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, reason }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `decisionAction failed: ${res.status}`);
  }
  return res.json();
}
