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
  // Real numbers a deterministic tool computed (coverage_ratio, dscr,
  // ...) — see Citation's sibling comment in shared/schemas.py.
  metrics: Record<string, number>;
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
  created_at: string;
  updated_at: string;
  has_findings: boolean;
}

export interface DocumentSummary {
  document_id: string;
  doc_type: string;
}

// "Tổng quan" tab data (web redesign Phase 3) — additive, optional joins.
// `null` means the case's customer/collateral was never seeded into those
// domain tables (e.g. older case, or Customer 360/Collateral not run for
// it yet) — the tab must render an honest empty state, not crash.
export interface CustomerIdentity {
  customer_name: string;
  tax_code: string | null;
  industry_code: string | null;
  establish_date: string | null;
  representative_name: string | null;
  representative_role: string | null;
}

export interface CollateralSummary {
  collateral_type: string;
  owner_name: string;
  registration_number: string | null;
}

export interface IncomeEvidenceItem {
  field_key: string;
  value: Record<string, unknown>;
  evidence_id: string;
  confidence: number;
}

export interface CaseDetail {
  case_id: string;
  customer_id: string;
  product: string;
  state: string;
  version: number;
  requested_facility: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  documents: DocumentSummary[];
  required_doc_types: string[];
  findings: Finding[];
  conflicts: Conflict[];
  decision: Decision | null;
  identity: CustomerIdentity | null;
  collateral_summary: CollateralSummary | null;
  income_evidence: IncomeEvidenceItem[];
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

// Credit Memo — computed view (api/app/routers/memo.py), not persisted.
export interface CreditMemoSection {
  title: string;
  content: string[];
}

export interface CreditMemo {
  case_id: string;
  prepared_at: string;
  recommendation: "APPROVE" | "APPROVE_WITH_CONDITIONS" | "REFER" | "REJECT" | "NEED_INFO";
  sections: CreditMemoSection[];
}

// Chat — ai-architecture_v2.md §11.8. 1 case = 1 thread.
export interface ChatMessageDto {
  message_id: string;
  seq: number;
  role: "USER" | "ASSISTANT" | "SYSTEM";
  content: string;
  citations: unknown[] | null;
  created_at: string;
}

export interface AuditEvent {
  seq: number;
  event_type: string;
  actor: { type: string; id: string };
  timestamp: string;
  payload: Record<string, unknown>;
  versions: Record<string, unknown>;
}
