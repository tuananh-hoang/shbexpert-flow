// Mirrors api/app/routers/cases.py response shapes exactly — kept as a
// single source of truth here rather than re-deriving from JSON shape
// guesses at each call site.

export type Stance = "SUPPORT" | "CAUTION" | "OPPOSE" | "NEED_DATA";
export type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

// A structured pointer into RAG-retrieved knowledge (policy clause / legal
// checklist item) that grounded a finding's claim — distinct from
// evidence_ids, which point at ExtractedField/document evidence.
export interface Citation {
  source_type: "POLICY" | "LEGAL_CHECKLIST";
  source_id: string;
  version: string | null;
  section: string | null;
  effective_date: string | null;
  text: string;
  score: number;
}

export interface Finding {
  display_id: string;
  finding_key: string;
  agent_id: string;
  issue_key: string;
  claim_type: "FACT" | "INFERENCE";
  claim: string;
  stance: Stance;
  severity: Severity;
  confidence: number;
  evidence_ids: string[];
  citations: Citation[];
  recommended_action: string | null;
  version: number;
  change_reason: string | null;
  created_at: string;
}

export interface Conflict {
  conflict_id: string;
  issue_key: string;
  round: number;
  status: "OPEN" | "RESOLVED" | "UNRESOLVED";
  source_findings: string[];
  targeted_questions: { to_agent: string; question: string; required_evidence: string[] }[];
}

export interface HardGate {
  gate_id: string;
  status: "PASS" | "FAIL" | "REVIEW";
  reason: string | null;
}

export interface ScoreEntry {
  dimension: string;
  score: number;
  max: number;
}

export interface Decision {
  decision_id: string;
  recommendation: "APPROVE" | "APPROVE_WITH_CONDITIONS" | "REFER" | "REJECT" | "NEED_INFO";
  requested_amount_vnd: number | null;
  recommended_amount_vnd: number | null;
  recommended_tenor_months: number | null;
  hard_gates: HardGate[];
  scores: ScoreEntry[];
  strengths: string[];
  risks: string[];
  conditions_precedent: string[];
  dissent: string[];
  policy_version: string | null;
  decision_matrix_version: string | null;
}

// Application Queue row (GET /cases) — deliberately lighter than
// CaseDetail: just enough to render a queue list + status badge without
// pulling findings/conflicts/decision for every case up front.
export interface CaseSummary {
  case_id: string;
  customer_id: string;
  product: string;
  state: string;
  requested_facility: Record<string, unknown>;
  updated_at: string;
  has_findings: boolean;
}

export interface CaseDetail {
  case_id: string;
  customer_id: string;
  product: string;
  state: string;
  version: number;
  requested_facility: Record<string, unknown>;
  findings: Finding[];
  conflicts: Conflict[];
  decision: Decision | null;
}

export interface EvidenceItem {
  field_id: string;
  field_key: string;
  value: Record<string, unknown>;
  confidence: number;
  page: number | null;
  // PDF point space (origin bottom-left) — matches what scripts/pdf_utils.py
  // actually drew, converted to CSS pixels at render time via pdf.js's own
  // page viewport transform (see EvidenceViewer.tsx).
  bbox: { x0: number; y0: number; x1: number; y1: number } | null;
  document_id: string | null;
  doc_type: string | null;
  document_url: string | null;
  // Same-origin PDF stream (api proxy) — what EvidenceViewer opens.
  // document_url (presigned, direct-to-MinIO) stays the "mở tài liệu gốc"
  // new-tab download fallback.
  viewer_url: string | null;
}

export interface AuditEvent {
  seq: number;
  event_type: string;
  actor: { type: string; id: string };
  timestamp: string;
  payload: Record<string, unknown>;
  versions: Record<string, unknown>;
}
