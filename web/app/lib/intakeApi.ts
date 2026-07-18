/**
 * Client cho 4 endpoint tiếp nhận hồ sơ RM (api/app/routers/intake.py).
 *
 * Tách khỏi lib/api.ts để phản chiếu đúng cách backend tách router: api.ts
 * là phía đọc của Credit Officer, file này là phía ghi của RM.
 *
 * Mọi lời gọi đi qua /api/* — next.config.mjs rewrite sang service `api`.
 * Browser chỉ nói chuyện với origin của `web`, nên không cần CORS
 * (overview.md §4).
 */

export const DOC_TYPES = [
  "financial_statement",
  "tax_filing",
  "valuation_certificate",
  "business_registration",
] as const;

export type DocType = (typeof DOC_TYPES)[number];

export const DOC_TYPE_LABEL_VI: Record<DocType, string> = {
  financial_statement: "Báo cáo tài chính",
  tax_filing: "Tờ khai thuế",
  valuation_certificate: "Chứng thư định giá",
  business_registration: "Giấy đăng ký kinh doanh",
};

/** Mã máy, không phải tên tiếng Việt — chuỗi có dấu làm khóa so sánh thì
 *  đổi chính tả là vỡ, mà lỗi lại im lặng (hồ sơ rơi nhầm luồng). Khớp
 *  shared/constants.py::PRODUCT_LABEL_VI. */
export const PRODUCTS = ["MICRO_OD", "SME_WC", "SME_TERM"] as const;
export type Product = (typeof PRODUCTS)[number];

export const PRODUCT_LABEL_VI: Record<Product, string> = {
  MICRO_OD: "Thấu chi doanh nghiệp",
  SME_WC: "Vay vốn lưu động SME",
  SME_TERM: "Vay đầu tư tài sản cố định",
};

export const CHANNELS = ["RM_LMS", "MOBILE_KHDN"] as const;
export type Channel = (typeof CHANNELS)[number];

export const CHANNEL_LABEL_VI: Record<Channel, { title: string; subtitle: string }> = {
  RM_LMS: { title: "Credit Application (RM)", subtitle: "Kênh RM khởi tạo trên LMS" },
  MOBILE_KHDN: { title: "Mobile Banking KHDN", subtitle: "Khách hàng doanh nghiệp tự khởi tạo" },
};

export const SEGMENTS = ["SME", "MICROSME"] as const;
export type Segment = (typeof SEGMENTS)[number];

export type Lane = "GREEN" | "RED";

export type SubmissionInput = {
  channel: Channel;
  customer_id: string;
  segment: Segment;
  product: Product;
  requested_facility: { amount_vnd: number; tenor_months: number };
  owner: string;
};

export type RoutingResult = {
  routing_decision_id: string;
  lane: Lane;
  reason: string;
  /** null ở luồng xanh — luồng xanh không sinh ra case nào. */
  case_id: string | null;
  /** null ở luồng đỏ. Loại trừ nhau với case_id: đúng một cái khác null. */
  slink_application_id: string | null;
  status?: string;
};

export type SlinkAgentDecision = {
  agent_id: string;
  summary: string;
  rationale: string[];
  metrics: Record<string, unknown>;
  seq: number;
};

export type SlinkApplication = {
  slink_application_id: string;
  customer_id: string;
  amount_requested_vnd: number;
  tenor_months: number;
  status: "QUEUED" | "SCORING" | "APPROVED" | "REJECTED" | "FAILED";
  recommended_limit_vnd: number | null;
  interest_rate_pct: number | null;
  decision_reason: string | null;
  agent_decisions: SlinkAgentDecision[];
};

export const SLINK_AGENT_LABEL_VI: Record<string, string> = {
  profile: "Hồ sơ merchant",
  cashflow: "Phân tích dòng tiền",
  behavioural: "Chấm điểm hành vi",
  sizing_pricing: "Hạn mức & định giá",
  risk_compliance: "Rủi ro & tuân thủ",
};

export async function fetchSlinkApplication(id: string): Promise<SlinkApplication> {
  const res = await fetch(`/api/slink/applications/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res, "Không đọc được kết quả chấm điểm"));
  return res.json();
}

export type CreateCaseInput = {
  customer_id: string;
  product: string;
  requested_facility: { amount_vnd: number; tenor_months: number };
  owner: string;
};

export type CreatedCase = { case_id: string; state: string };

export type UploadedDocument = {
  document_id: string;
  sha256: string;
  doc_type: DocType;
  /** true khi (case_id, sha256) đã tồn tại — backend trả lại document_id cũ. */
  deduplicated: boolean;
};

export type SubmittedDoc = {
  doc_type: DocType;
  document_id: string;
  uploaded_at: string;
};

export type IntakeStatus = {
  state: string;
  submitted: SubmittedDoc[];
  missing: DocType[];
  /**
   * Phản ánh ALLOWED_TRANSITIONS, KHÔNG phải checklist đủ hay thiếu — RM
   * vẫn nộp được hồ sơ thiếu và INTAKE_VALIDATION sẽ trả về NEED_INFO.
   * Gate checklist thuộc lát 3.
   */
  can_submit: boolean;
};

/** Rút `detail` từ body lỗi của FastAPI để hiện đúng lý do thay vì mã số trần. */
async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return `${fallback} (HTTP ${res.status})`;
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

/**
 * Cửa vào chung của cả hai kênh — phân luồng ngay khi tiếp nhận.
 * Luồng đỏ trả về case_id để đi tiếp sang upload; luồng xanh trả null.
 */
export async function createSubmission(input: SubmissionInput): Promise<RoutingResult> {
  const res = await fetch("/api/intake/submissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readError(res, "Tiếp nhận hồ sơ thất bại"));
  return res.json();
}

export async function createCase(input: CreateCaseInput): Promise<CreatedCase> {
  const res = await fetch("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await readError(res, "Tạo hồ sơ thất bại"));
  return res.json();
}

export async function uploadDocument(
  caseId: string,
  file: File,
  docType: DocType,
): Promise<UploadedDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", docType);

  const res = await fetch(`/api/cases/${caseId}/documents`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await readError(res, `Tải ${file.name} thất bại`));
  return res.json();
}

export async function fetchIntakeStatus(caseId: string): Promise<IntakeStatus> {
  const res = await fetch(`/api/cases/${caseId}/intake-status`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res, "Không đọc được trạng thái hồ sơ"));
  return res.json();
}

export async function submitCase(caseId: string): Promise<CreatedCase> {
  const res = await fetch(`/api/cases/${caseId}/submit`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res, "Nộp hồ sơ thất bại"));
  return res.json();
}
