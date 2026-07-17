"use client";

/**
 * Screen 3 — Evidence Viewer (FE_flow.jpeg / Explainable_AI_Interaction_Design.md):
 * renders the actual cited PDF page with a highlight box over the exact
 * cited value, a page thumbnail rail, zoom controls, and a "Citation
 * Details" panel. Opened from ExplainabilityDrawer when an evidence item
 * is clicked.
 *
 * bbox (EvidenceItem.bbox) is in PDF POINT space, origin bottom-left —
 * exactly what scripts/pdf_utils.py drew (see that file's docstring).
 * Converting to CSS pixels needs the real page height in points, read
 * from the loaded PDF itself (page.view, from pdf.js) rather than
 * assumed — our seed docs happen to all be A4, but this doesn't hardcode
 * that.
 */
import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { EvidenceItem } from "../lib/types";

// Standard react-pdf/pdfjs-dist bundler setup (see react-pdf README) —
// webpack resolves this to a static asset URL at build time, no manual
// copy into public/ needed, and nothing is fetched from a CDN (keeps the
// offline-safety principle already applied to fastembed in mcp-rag).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

function fmtValue(value: Record<string, unknown>): string {
  if ("amount_vnd" in value) return `${Number(value.amount_vnd).toLocaleString("vi-VN")} VND`;
  if ("date" in value) return String(value.date);
  if ("pct" in value) return `${value.pct}%`;
  return JSON.stringify(value);
}

export function EvidenceViewer({ evidence, onClose }: { evidence: EvidenceItem; onClose: () => void }) {
  const [numPages, setNumPages] = useState(1);
  const [pageNumber, setPageNumber] = useState(evidence.page ?? 1);
  const [scale, setScale] = useState(1.3);
  const [pageHeightPt, setPageHeightPt] = useState<number | null>(null);

  if (!evidence.viewer_url) {
    return null;
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(11, 37, 69, 0.55)",
        zIndex: 2000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--surface)",
          borderRadius: "var(--radius)",
          width: "min(1000px, 95vw)",
          height: "min(720px, 90vh)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "var(--shadow-md)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "12px 16px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div>
            <div style={{ fontWeight: 700 }}>{evidence.doc_type?.replace(/_/g, " ") ?? "Tài liệu"}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              Trang {pageNumber} / {numPages}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button className="btn" onClick={() => setScale((s) => Math.max(0.5, s - 0.2))}>
              −
            </button>
            <span className="muted" style={{ fontSize: 12, width: 40, textAlign: "center" }}>
              {Math.round(scale * 100)}%
            </span>
            <button className="btn" onClick={() => setScale((s) => Math.min(3, s + 0.2))}>
              +
            </button>
            <button className="btn" onClick={onClose}>
              ×
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {/* Thumbnail rail */}
          {numPages > 1 && (
            <div
              style={{
                width: 90,
                borderRight: "1px solid var(--border)",
                overflowY: "auto",
                padding: 8,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <Document file={evidence.viewer_url}>
                {Array.from({ length: numPages }, (_, i) => i + 1).map((n) => (
                  <div
                    key={n}
                    onClick={() => setPageNumber(n)}
                    style={{
                      cursor: "pointer",
                      border: n === pageNumber ? "2px solid var(--accent)" : "1px solid var(--border)",
                      borderRadius: 4,
                    }}
                  >
                    <Page pageNumber={n} width={70} renderTextLayer={false} renderAnnotationLayer={false} />
                  </div>
                ))}
              </Document>
            </div>
          )}

          {/* Main page view */}
          <div style={{ flex: 1, overflow: "auto", background: "var(--bg)", padding: 16 }}>
            <div style={{ position: "relative", display: "inline-block" }}>
              <Document
                file={evidence.viewer_url}
                onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                loading={<p className="muted">Đang tải PDF...</p>}
                error={<p style={{ color: "var(--oppose)" }}>Không tải được PDF.</p>}
              >
                <Page
                  pageNumber={pageNumber}
                  scale={scale}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  onLoadSuccess={(page) => setPageHeightPt(page.view[3] - page.view[1])}
                />
              </Document>
              {evidence.bbox && evidence.page === pageNumber && pageHeightPt !== null && (
                <div
                  style={{
                    position: "absolute",
                    left: evidence.bbox.x0 * scale,
                    top: (pageHeightPt - evidence.bbox.y1) * scale,
                    width: (evidence.bbox.x1 - evidence.bbox.x0) * scale,
                    height: (evidence.bbox.y1 - evidence.bbox.y0) * scale,
                    border: "2px solid var(--accent)",
                    background: "rgba(47, 111, 237, 0.15)",
                    pointerEvents: "none",
                  }}
                />
              )}
            </div>
          </div>

          {/* Citation details panel */}
          <div style={{ width: 240, borderLeft: "1px solid var(--border)", padding: 16, overflowY: "auto" }}>
            <div className="section-title" style={{ fontSize: 14 }}>
              Citation Details
            </div>
            <div style={{ fontSize: 13, marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>
                Extracted Value
              </div>
              <div style={{ fontWeight: 600 }}>{fmtValue(evidence.value)}</div>
            </div>
            <div style={{ fontSize: 13, marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>
                Source
              </div>
              <div>{evidence.doc_type?.replace(/_/g, " ")}</div>
            </div>
            <div style={{ fontSize: 13, marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>
                Page
              </div>
              <div>{evidence.page}</div>
            </div>
            <div style={{ fontSize: 13, marginBottom: 10 }}>
              <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>
                Confidence
              </div>
              <div>{Math.round(evidence.confidence * 100)}%</div>
            </div>
            {evidence.document_url && (
              <a href={evidence.document_url} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: "var(--accent)" }}>
                Tải PDF gốc →
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
