"use client";

/**
 * LMS — Khởi tạo & Phân luồng Hồ sơ Tín dụng.
 *
 * Điểm bắt đầu chung cho cả hai kênh khởi tạo (ảnh nghiệp vụ
 * ~/Pictures/lms_router.jpeg). Phân luồng chạy ngay khi tiếp nhận:
 *
 *   Credit Application (RM) ─┐
 *                            ├─► classify ─┬─► đỏ  → checklist → Credit Officer
 *   Mobile Banking KHDN     ─┘             └─► xanh → ACAS-SLINK (tự động 100%)
 *
 * Luồng xanh KHÔNG sinh ra case nào và không qua Credit Officer — nên khi
 * ra luồng xanh, trang này dừng ở kết quả phân luồng chứ không mở phần
 * upload. Engine SLINK là lát (b), chưa có.
 *
 * Spec: docs/superpowers/specs/2026-07-19-intake-routing-design.md
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Briefcase,
  CheckCircle2,
  CircleDashed,
  FileUp,
  Loader2,
  Send,
  Smartphone,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";
import { Button, Card, SectionTitle } from "../components/ui";
import {
  CHANNELS,
  CHANNEL_LABEL_VI,
  DOC_TYPES,
  DOC_TYPE_LABEL_VI,
  PRODUCTS,
  PRODUCT_LABEL_VI,
  SEGMENTS,
  SLINK_AGENT_LABEL_VI,
  createSubmission,
  fetchIntakeStatus,
  fetchSlinkApplication,
  submitCase,
  uploadDocument,
  type Channel,
  type DocType,
  type IntakeStatus,
  type Product,
  type RoutingResult,
  type Segment,
  type SlinkApplication,
} from "../lib/intakeApi";

type UploadRow = {
  key: string;
  fileName: string;
  docType: DocType;
  status: "uploading" | "done" | "deduplicated" | "error";
  message?: string;
};

/** Điền sẵn theo kênh, khớp hai kịch bản trong ảnh nghiệp vụ. */
const CHANNEL_PRESET: Record<Channel, { customerId: string; segment: Segment; product: Product; amount: string; tenor: string }> = {
  RM_LMS: { customerId: "CUST-NTE", segment: "SME", product: "SME_WC", amount: "800000000", tenor: "36" },
  MOBILE_KHDN: { customerId: "CUST-SLINK", segment: "MICROSME", product: "MICRO_OD", amount: "150000000", tenor: "12" },
};

export default function LmsPage() {
  const [channel, setChannel] = useState<Channel>("RM_LMS");
  const [customerId, setCustomerId] = useState(CHANNEL_PRESET.RM_LMS.customerId);
  const [segment, setSegment] = useState<Segment>(CHANNEL_PRESET.RM_LMS.segment);
  const [product, setProduct] = useState<Product>(CHANNEL_PRESET.RM_LMS.product);
  const [amountVnd, setAmountVnd] = useState(CHANNEL_PRESET.RM_LMS.amount);
  const [tenorMonths, setTenorMonths] = useState(CHANNEL_PRESET.RM_LMS.tenor);

  const [routing, setRouting] = useState<RoutingResult | null>(null);
  const [status, setStatus] = useState<IntakeStatus | null>(null);
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [docType, setDocType] = useState<DocType>(DOC_TYPES[0]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [slinkApp, setSlinkApp] = useState<SlinkApplication | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const caseId = routing?.case_id ?? null;
  const slinkId = routing?.slink_application_id ?? null;

  const refreshStatus = useCallback(async (id: string) => {
    setStatus(await fetchIntakeStatus(id));
  }, []);

  // Chấm điểm chạy bất đồng bộ ở worker — poll cho tới khi có kết quả cuối.
  // Poll thay vì SSE cho gọn: engine tất định chạy vài trăm ms, không phải
  // tác vụ dài cần streaming từng bước.
  useEffect(() => {
    if (!slinkId) return;
    let cancelled = false;

    async function poll() {
      try {
        const app = await fetchSlinkApplication(slinkId!);
        if (cancelled) return;
        setSlinkApp(app);
        if (app.status === "QUEUED" || app.status === "SCORING") {
          setTimeout(poll, 700);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    poll();

    return () => {
      cancelled = true;
    };
  }, [slinkId]);

  function pickChannel(next: Channel) {
    if (routing) return; // đã tiếp nhận thì không đổi kênh giữa chừng
    const preset = CHANNEL_PRESET[next];
    setChannel(next);
    setCustomerId(preset.customerId);
    setSegment(preset.segment);
    setProduct(preset.product);
    setAmountVnd(preset.amount);
    setTenorMonths(preset.tenor);
  }

  function reset() {
    setRouting(null);
    setStatus(null);
    setUploads([]);
    setSlinkApp(null);
    setError(null);
  }

  async function handleSubmitApplication() {
    setError(null);
    setBusy(true);
    try {
      const result = await createSubmission({
        channel,
        customer_id: customerId.trim(),
        segment,
        product,
        requested_facility: { amount_vnd: Number(amountVnd), tenor_months: Number(tenorMonths) },
        owner: channel === "RM_LMS" ? "rm1" : "khdn",
      });
      setRouting(result);
      setUploads([]);
      if (result.case_id) await refreshStatus(result.case_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!files || !caseId) return;
    setError(null);

    // Upload từng file một, không Promise.all: lỗi một file không được làm
    // hỏng cả lô, và mỗi dòng phải hiện trạng thái riêng.
    for (const file of Array.from(files)) {
      const key = `${file.name}-${Date.now()}-${Math.random()}`;
      setUploads((prev) => [...prev, { key, fileName: file.name, docType, status: "uploading" }]);

      try {
        const result = await uploadDocument(caseId, file, docType);
        setUploads((prev) =>
          prev.map((row) =>
            row.key === key
              ? {
                  ...row,
                  status: result.deduplicated ? "deduplicated" : "done",
                  message: result.deduplicated ? "Đã nộp trước đó — bỏ qua bản trùng" : undefined,
                }
              : row,
          ),
        );
      } catch (e) {
        setUploads((prev) =>
          prev.map((row) =>
            row.key === key
              ? { ...row, status: "error", message: e instanceof Error ? e.message : String(e) }
              : row,
          ),
        );
      }
    }

    await refreshStatus(caseId);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmitForReview() {
    if (!caseId) return;
    setError(null);
    setBusy(true);
    try {
      await submitCase(caseId);
      await refreshStatus(caseId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const isGreen = routing?.lane === "GREEN";
  const isRed = routing?.lane === "RED";

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-5 p-8">
      <header>
        <h1 className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
          LMS — Khởi tạo &amp; Phân luồng Hồ sơ Tín dụng
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted-2)" }}>
          Điểm bắt đầu chung cho cả hai kênh khởi tạo — phân luồng ngay khi tiếp nhận.
        </p>
      </header>

      {error && (
        <Card className="p-3 text-sm" style={{ borderColor: "var(--status-critical)" }}>
          <span style={{ color: "var(--status-critical)" }}>{error}</span>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3">
        {CHANNELS.map((c) => {
          const active = channel === c;
          const Icon = c === "RM_LMS" ? Briefcase : Smartphone;
          return (
            <button
              key={c}
              type="button"
              onClick={() => pickChannel(c)}
              disabled={!!routing}
              className="rounded-xl border p-4 text-left transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
              style={{
                background: "var(--surface-raised)",
                borderColor: active ? "var(--brand)" : "var(--border-hairline)",
              }}
            >
              <div className="flex items-center gap-2">
                <Icon size={16} style={{ color: active ? "var(--brand)" : "var(--text-muted-2)" }} />
                <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                  {CHANNEL_LABEL_VI[c].title}
                </span>
              </div>
              <p className="mt-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
                {CHANNEL_LABEL_VI[c].subtitle}
              </p>
            </button>
          );
        })}
      </div>

      <Card className="flex flex-col gap-4 p-5">
        <SectionTitle>1 · Thông tin khoản vay</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Mã khách hàng">
            <input className="lms-input" value={customerId} onChange={(e) => setCustomerId(e.target.value)} disabled={!!routing} />
          </Field>
          <Field label="Phân khúc">
            <select className="lms-input" value={segment} onChange={(e) => setSegment(e.target.value as Segment)} disabled={!!routing}>
              {SEGMENTS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sản phẩm">
            <select className="lms-input" value={product} onChange={(e) => setProduct(e.target.value as Product)} disabled={!!routing}>
              {PRODUCTS.map((p) => (
                <option key={p} value={p}>
                  {PRODUCT_LABEL_VI[p]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Số tiền (VND)">
            <input className="lms-input" type="number" value={amountVnd} onChange={(e) => setAmountVnd(e.target.value)} disabled={!!routing} />
          </Field>
          <Field label="Kỳ hạn (tháng)">
            <input className="lms-input" type="number" value={tenorMonths} onChange={(e) => setTenorMonths(e.target.value)} disabled={!!routing} />
          </Field>
        </div>

        <div className="flex gap-2">
          {!routing ? (
            <Button variant="primary" onClick={handleSubmitApplication} disabled={busy || !customerId.trim()}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Workflow size={14} />}
              Tiếp nhận &amp; phân luồng
            </Button>
          ) : (
            <Button variant="secondary" onClick={reset}>
              Làm lại
            </Button>
          )}
        </div>
      </Card>

      {routing && (
        <Card className="flex flex-col gap-3 p-5">
          <SectionTitle>2 · Kết quả phân luồng</SectionTitle>
          <div className="flex items-start gap-2">
            {isGreen ? (
              <Zap size={16} style={{ color: "var(--status-good)", marginTop: 2 }} />
            ) : (
              <Workflow size={16} style={{ color: "var(--status-serious)", marginTop: 2 }} />
            )}
            <div>
              <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                {isGreen
                  ? "Luồng xanh → ACAS-SLINK (tự động 100%)"
                  : "Luồng đỏ → Rà soát hồ sơ & Checklist → Credit Officer"}
              </div>
              <p className="mt-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
                {routing.reason}
              </p>
              {isGreen && (
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted-2)" }}>
                  Thấu chi MicroSME trong hạn mức tự động — không qua Credit Officer và không
                  sinh hồ sơ tín dụng.
                </p>
              )}
              {isRed && (
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted-2)" }}>
                  Đã tạo hồ sơ <strong style={{ color: "var(--text-primary)" }}>{routing.case_id}</strong> ở
                  trạng thái <strong style={{ color: "var(--text-primary)" }}>{status?.state ?? "…"}</strong>.
                </p>
              )}
            </div>
          </div>
        </Card>
      )}

      {isGreen && slinkApp && (
        <Card className="flex flex-col gap-4 p-5">
          <SectionTitle>3 · Chấm điểm tự động ACAS-SLINK</SectionTitle>

          {slinkApp.status === "QUEUED" || slinkApp.status === "SCORING" ? (
            <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted-2)" }}>
              <Loader2 size={15} className="animate-spin" />
              Đang chấm điểm dòng tiền…
            </div>
          ) : (
            <>
              <div className="flex items-start gap-2">
                {slinkApp.status === "APPROVED" ? (
                  <CheckCircle2 size={16} style={{ color: "var(--status-good)", marginTop: 2 }} />
                ) : (
                  <XCircle size={16} style={{ color: "var(--status-critical)", marginTop: 2 }} />
                )}
                <div>
                  <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {slinkApp.status === "APPROVED" ? "Đủ điều kiện cấp hạn mức" : "Không đủ điều kiện"}
                  </div>
                  <p className="mt-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
                    {slinkApp.decision_reason}
                  </p>
                </div>
              </div>

              {slinkApp.status === "APPROVED" && slinkApp.recommended_limit_vnd !== null && (
                <div className="flex gap-6">
                  <Metric label="Hạn mức khuyến nghị" value={`${slinkApp.recommended_limit_vnd.toLocaleString("vi-VN")} VND`} />
                  <Metric label="Lãi suất" value={`${slinkApp.interest_rate_pct}%/năm`} />
                </div>
              )}

              <div className="flex flex-col gap-2">
                {slinkApp.agent_decisions.map((d) => (
                  <div key={d.agent_id} className="text-sm">
                    <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                      {SLINK_AGENT_LABEL_VI[d.agent_id] ?? d.agent_id}
                    </span>
                    <span style={{ color: "var(--text-muted-2)" }}> — {d.summary}</span>
                  </div>
                ))}
              </div>

              <p className="text-xs" style={{ color: "var(--text-muted-2)" }}>
                Đây là <strong>khuyến nghị</strong>. Việc thực sự cấp hạn mức qua core-banking
                thuộc lát sau, chưa triển khai.
              </p>
            </>
          )}
        </Card>
      )}

      {isRed && (
        <>
          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle>3 · Nộp tài liệu</SectionTitle>

            <div className="flex items-end gap-3">
              <Field label="Loại tài liệu">
                <select className="lms-input" value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
                  {DOC_TYPES.map((d) => (
                    <option key={d} value={d}>
                      {DOC_TYPE_LABEL_VI[d]}
                    </option>
                  ))}
                </select>
              </Field>

              <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
                <FileUp size={14} />
                Chọn file
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="application/pdf,image/png,image/jpeg"
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
            </div>

            <p className="text-xs" style={{ color: "var(--text-muted-2)" }}>
              Chấp nhận PDF, PNG, JPEG — tối đa 20 MB mỗi file. Loại tài liệu do RM chọn,
              hệ thống chưa tự phân loại.
            </p>

            {uploads.length > 0 && (
              <ul className="flex flex-col gap-1.5">
                {uploads.map((row) => (
                  <li key={row.key} className="flex items-center gap-2 text-sm">
                    <UploadIcon status={row.status} />
                    <span style={{ color: "var(--text-primary)" }}>{row.fileName}</span>
                    <span className="text-xs" style={{ color: "var(--text-muted-2)" }}>
                      {DOC_TYPE_LABEL_VI[row.docType]}
                      {row.message ? ` — ${row.message}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle>4 · Checklist hồ sơ</SectionTitle>

            <ul className="flex flex-col gap-1.5">
              {DOC_TYPES.map((d) => {
                const done = status?.submitted.some((s) => s.doc_type === d) ?? false;
                return (
                  <li key={d} className="flex items-center gap-2 text-sm">
                    {done ? (
                      <CheckCircle2 size={15} style={{ color: "var(--status-good)" }} />
                    ) : (
                      <CircleDashed size={15} style={{ color: "var(--text-muted-2)" }} />
                    )}
                    <span style={{ color: done ? "var(--text-primary)" : "var(--text-muted-2)" }}>
                      {DOC_TYPE_LABEL_VI[d]}
                    </span>
                  </li>
                );
              })}
            </ul>

            {status && status.missing.length > 0 && (
              <p className="text-xs" style={{ color: "var(--text-muted-2)" }}>
                Còn thiếu {status.missing.length} loại. Vẫn nộp được — hệ thống sẽ trả về
                NEED_INFO để bổ sung sau.
              </p>
            )}

            <div>
              <Button variant="primary" onClick={handleSubmitForReview} disabled={busy || !status?.can_submit}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Vào hàng chờ Credit Officer
              </Button>
            </div>
          </Card>
        </>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
        {label}
      </div>
      <div className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium" style={{ color: "var(--text-muted-2)" }}>
        {label}
      </span>
      {children}
    </label>
  );
}

function UploadIcon({ status }: { status: UploadRow["status"] }) {
  if (status === "uploading") return <Loader2 size={15} className="animate-spin" style={{ color: "var(--text-muted-2)" }} />;
  if (status === "error") return <XCircle size={15} style={{ color: "var(--status-critical)" }} />;
  if (status === "deduplicated") return <CheckCircle2 size={15} style={{ color: "var(--text-muted-2)" }} />;
  return <CheckCircle2 size={15} style={{ color: "var(--status-good)" }} />;
}
