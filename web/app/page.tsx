"use client";

/**
 * Application Queue — Screen 0 of the frontend flow (FE_flow.jpeg): list
 * of customers waiting for credit review. Selecting a row navigates to
 * `/cases/{case_id}` (web/app/cases/[caseId]/page.tsx), which shows the
 * Analyzing/"thinking" view if the case hasn't been analyzed yet, or the
 * full Dashboard once findings/decision exist.
 *
 * Data flows through /api/* only (overview.md §4) — GET /cases
 * (api/app/routers/cases.py::list_cases).
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchCases } from "./lib/api";
import type { CaseSummary } from "./lib/types";

function formatVnd(amount: unknown): string {
  if (typeof amount !== "number") return "—";
  return `${(amount / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ VND`;
}

function statusLabel(c: CaseSummary): string {
  if (!c.has_findings) return "Chờ phân tích";
  if (c.state === "READY_FOR_REVIEW") return "Sẵn sàng duyệt";
  if (c.state === "NEED_INFO") return "Cần bổ sung";
  if (c.state === "ANALYZING") return "Đang phân tích";
  return c.state;
}

function statusDotColor(c: CaseSummary): string {
  if (!c.has_findings) return "#8b98a8"; // grey — nothing has run yet
  if (c.state === "NEED_INFO") return "#e0a000"; // amber — needs attention
  if (c.state === "READY_FOR_REVIEW") return "#4fd67a"; // green — ready
  return "#8b98a8";
}

export default function ApplicationQueue() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);

  useEffect(() => {
    fetchCases().then(setCases).catch(() => setCases([]));
  }, []);

  return (
    <main className="app-shell">
      <div className="hero-strip">
        <div className="breadcrumb">SHBExpert AI</div>
        <h1>Application Queue</h1>
        <div className="hero-metrics">
          <div>
            <div className="hero-metric-label">Hồ sơ chờ xử lý</div>
            <div className="hero-metric-value">{cases?.length ?? "—"}</div>
          </div>
        </div>
      </div>

      <section className="card">
        {cases === null && <p className="muted">Đang tải danh sách hồ sơ...</p>}
        {cases?.length === 0 && <p className="muted">Chưa có hồ sơ nào.</p>}
        {cases && cases.length > 0 && (
          <table className="audit-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Khách hàng</th>
                <th>Sản phẩm</th>
                <th>Số tiền đề nghị</th>
                <th>Trạng thái</th>
                <th>Cập nhật</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.case_id}>
                  <td style={{ fontWeight: 700 }}>{c.case_id}</td>
                  <td>{c.customer_id}</td>
                  <td>{c.product}</td>
                  <td>{formatVnd(c.requested_facility.amount_vnd)}</td>
                  <td>
                    <span
                      className="status-pill"
                      style={{
                        background: "var(--need-data-bg)",
                        color: "var(--text)",
                        ["--status-dot-color" as string]: statusDotColor(c),
                      }}
                    >
                      {statusLabel(c)}
                    </span>
                  </td>
                  <td className="muted">{new Date(c.updated_at).toLocaleString("vi-VN")}</td>
                  <td>
                    <Link href={`/cases/${c.case_id}`}>
                      <button className="btn btn-primary">{c.has_findings ? "Mở hồ sơ" : "Bắt đầu phân tích"}</button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
