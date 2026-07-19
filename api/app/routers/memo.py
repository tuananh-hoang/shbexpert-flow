"""Credit Memo — computed view over CaseState (case + findings + decision).

GET /cases/{id}/memo      → JSON (section list for in-app preview)
GET /cases/{id}/memo/pdf  → PDF download (standard SHB tờ trình A4)
"""
from __future__ import annotations

import datetime as dt
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from shared.db import get_session
from shared.models import Case, DecisionPackage, Finding

router = APIRouter(prefix="/cases", tags=["memo"])

AGENT_LABELS = {
    "financial_analysis":  "III. PHÂN TÍCH TÀI CHÍNH",
    "policy_compliance":   "V.  TUÂN THỦ CHÍNH SÁCH",
    "collateral_legal":    "IV. TÀI SẢN ĐẢM BẢO & PHÁP LÝ",
    "customer_360":        "II. THÔNG TIN KHÁCH HÀNG",
    "cic_check":           "VI. CIC & LỊCH SỬ TÍN DỤNG",
    "legal_review":        "VII. RÀ SOÁT PHÁP LÝ",
}

REC_VI = {
    "APPROVE":                  "PHÊ DUYỆT",
    "APPROVE_WITH_CONDITIONS":  "PHÊ DUYỆT CÓ ĐIỀU KIỆN",
    "REFER":                    "CHUYỂN XEM XÉT",
    "REJECT":                   "TỪ CHỐI",
    "NEED_INFO":                "YÊU CẦU BỔ SUNG HỒ SƠ",
}

GATE_VI = {
    "PASS": "Đạt",
    "FAIL": "Không đạt",
    "WARN": "Cảnh báo",
}


def _fmt_vnd(v) -> str:
    if v is None:
        return "—"
    try:
        n = int(v)
        if n >= 1_000_000_000:
            return f"{n / 1_000_000_000:,.1f} tỷ VND"
        return f"{n / 1_000_000:,.0f} triệu VND"
    except (TypeError, ValueError):
        return str(v)


def _latest_findings(session, case_id: str) -> list[Finding]:
    findings = session.execute(
        select(Finding).where(Finding.case_id == case_id)
    ).scalars().all()
    latest: dict[str, Finding] = {}
    for f in findings:
        cur = latest.get(f.finding_key)
        if cur is None or f.version > cur.version:
            latest[f.finding_key] = f
    return sorted(latest.values(), key=lambda f: f.created_at)


def _build_memo_data(case_id: str) -> dict:
    """Shared data assembly used by both JSON and PDF endpoints."""
    with get_session() as session:
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"case {case_id} not found")

        decision = (
            session.execute(
                select(DecisionPackage)
                .where(DecisionPackage.case_id == case_id)
                .order_by(DecisionPackage.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if decision is None:
            raise HTTPException(
                status_code=409,
                detail="Chưa có DecisionPackage — chạy phân tích AI trước khi tạo Credit Memo.",
            )

        findings = _latest_findings(session, case_id)
        by_agent: dict[str, list[Finding]] = {}
        for f in findings:
            by_agent.setdefault(f.agent_id, []).append(f)

        # Hard gate rows
        gate_rows = [
            {
                "id": g["gate_id"],
                "status": GATE_VI.get(g["status"], g["status"]),
                "label": g.get("label", g["gate_id"]),
            }
            for g in (decision.hard_gates or [])
        ]

        # Finding rows by agent
        agent_sections = []
        for agent_id, afindings in by_agent.items():
            agent_sections.append({
                "agent": agent_id,
                "title": AGENT_LABELS.get(agent_id, agent_id),
                "findings": [
                    {
                        "key": f.issue_key,
                        "claim": f.claim,
                        "stance": f.stance,
                        "confidence": f.confidence,
                    }
                    for f in afindings
                ],
            })

        facility = case.requested_facility or {}
        return {
            "case_id": case_id,
            "customer_id": case.customer_id,
            "product": case.product,
            "amount_vnd": facility.get("amount_vnd"),
            "tenor_months": facility.get("tenor_months"),
            "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recommendation": decision.recommendation,
            "recommendation_vi": REC_VI.get(decision.recommendation, decision.recommendation),
            "recommended_amount_vnd": decision.recommended_amount_vnd,
            "conditions_precedent": list(decision.conditions_precedent or []),
            "gate_rows": gate_rows,
            "agent_sections": agent_sections,
            # Legacy flat sections for backwards-compat with existing CreditMemoPanel
            "sections": _flat_sections(case, decision, by_agent),
        }


def _flat_sections(case, decision, by_agent) -> list[dict]:
    """Backwards-compatible flat section list for JSON endpoint."""
    facility = case.requested_facility or {}
    gate_summary = ", ".join(
        f"{g['gate_id']}={GATE_VI.get(g['status'], g['status'])}"
        for g in (decision.hard_gates or [])
    )
    sections = [
        {
            "title": "I. Thông tin khách hàng & khoản vay",
            "content": [
                f"Khách hàng: {case.customer_id}",
                f"Sản phẩm: {case.product}",
                f"Số tiền đề nghị: {_fmt_vnd(facility.get('amount_vnd'))}",
                f"Kỳ hạn: {facility.get('tenor_months', '—')} tháng",
            ],
        },
        {
            "title": "VIII. Kết luận & kiến nghị",
            "content": [
                f"Khuyến nghị: {REC_VI.get(decision.recommendation, decision.recommendation)}",
                f"Hạn mức đề xuất: {_fmt_vnd(decision.recommended_amount_vnd)}",
                f"Kiểm tra hard gates: {gate_summary or '—'}",
            ],
        },
    ]
    for agent_id, afindings in by_agent.items():
        sections.append({
            "title": AGENT_LABELS.get(agent_id, agent_id),
            "content": [
                f"[{f.issue_key}] {f.claim} ({f.stance}, {int((f.confidence or 0) * 100)}%)"
                for f in afindings
            ],
        })
    if decision.conditions_precedent:
        sections.append({
            "title": "IX. Điều kiện tiên quyết",
            "content": list(decision.conditions_precedent),
        })
    return sections


# ─── JSON endpoint ────────────────────────────────────────────────────────────

@router.get("/{case_id}/memo")
def get_credit_memo(case_id: str) -> dict:
    data = _build_memo_data(case_id)
    return {
        "case_id": data["case_id"],
        "prepared_at": data["prepared_at"],
        "recommendation": data["recommendation"],
        "sections": data["sections"],
    }


# ─── PDF endpoint ─────────────────────────────────────────────────────────────

@router.get("/{case_id}/memo/pdf")
def get_credit_memo_pdf(case_id: str) -> Response:
    data = _build_memo_data(case_id)
    pdf_bytes = _render_pdf(data)
    filename = f"to-trinh-{case_id}-{dt.date.today().isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── PDF rendering (reportlab) ────────────────────────────────────────────────

def _render_pdf(data: dict) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, KeepTogether,
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab not installed")

    # Register Vietnamese-capable font
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        pdfmetrics.registerFont(TTFont("DV", FONT_PATH))
        pdfmetrics.registerFont(TTFont("DV-Bold", FONT_BOLD_PATH))
    except Exception:
        pass  # already registered

    NAVY  = colors.HexColor("#2F2E79")
    ORANGE = colors.HexColor("#F37021")
    LIGHT  = colors.HexColor("#F0F0F8")
    GRAY   = colors.HexColor("#6B6B9A")
    GREEN  = colors.HexColor("#1E8E5A")
    RED    = colors.HexColor("#D93B3B")
    AMBER  = colors.HexColor("#C4870F")
    WHITE  = colors.white
    BLACK  = colors.HexColor("#1A1A2E")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    def style(name, font="DV", **kw) -> ParagraphStyle:
        base = kw.pop("parent", "Normal")
        return ParagraphStyle(name, parent=styles[base], fontName=font, **kw)

    s_bank   = style("bank",   fontSize=9,  textColor=GRAY,  leading=13)
    s_title  = style("title",  fontSize=15, textColor=NAVY,  leading=20, font="DV-Bold",
                     spaceAfter=2 * mm)
    s_ref    = style("ref",    fontSize=8,  textColor=GRAY,  leading=12, spaceAfter=4 * mm)
    s_h1     = style("h1",     fontSize=10, textColor=WHITE, font="DV-Bold", leading=15)
    s_h2     = style("h2",     fontSize=9,  textColor=NAVY,  font="DV-Bold", leading=14,
                     spaceBefore=3 * mm, spaceAfter=1 * mm)
    s_body   = style("body",   fontSize=8.5, textColor=BLACK, leading=13)
    s_label  = style("label",  fontSize=8,  textColor=GRAY,  leading=12)
    s_value  = style("value",  fontSize=8.5, textColor=BLACK, font="DV-Bold", leading=12)
    s_rec    = style("rec",    fontSize=11, font="DV-Bold", leading=16)
    s_footer = style("footer", fontSize=7.5, textColor=GRAY, leading=11)
    s_cond   = style("cond",   fontSize=8.5, textColor=BLACK, leading=13, leftIndent=4 * mm,
                     bulletIndent=2 * mm)

    prepared = dt.datetime.fromisoformat(data["prepared_at"]).strftime("%d/%m/%Y %H:%M")
    ref_no   = f"SHB/{data['case_id']}/{dt.date.today().strftime('%Y%m%d')}"
    rec      = data["recommendation"]
    rec_color = GREEN if rec == "APPROVE" else (RED if rec == "REJECT" else AMBER)

    story = []

    # ── Header block ──────────────────────────────────────────────────────────
    header_data = [[
        Paragraph("<b>NGÂN HÀNG TMCP SÀI GÒN – HÀ NỘI (SHB)</b><br/>"
                  "Phòng Thẩm định Tín dụng Doanh nghiệp", s_bank),
        Paragraph(f"Số: {ref_no}<br/>Ngày lập: {prepared}", s_ref),
    ]]
    header_tbl = Table(header_data, colWidths=["60%", "40%"])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN",  (1, 0), (1, 0),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=3 * mm))

    story.append(Paragraph("TỜ TRÌNH THẨM ĐỊNH TÍN DỤNG", s_title))
    story.append(Paragraph(
        f"Hồ sơ: <b>{data['case_id']}</b> &nbsp;|&nbsp; "
        f"Khách hàng: <b>{data['customer_id']}</b> &nbsp;|&nbsp; "
        f"Sản phẩm: <b>{data['product']}</b>",
        s_ref,
    ))

    # ── I. Thông tin khoản vay ────────────────────────────────────────────────
    story.append(_section_header("I. THÔNG TIN KHOẢN VAY ĐỀ NGHỊ", NAVY, s_h1))
    kv_data = [
        ["Khách hàng",    data["customer_id"],
         "Sản phẩm",      data["product"]],
        ["Số tiền",       _fmt_vnd(data["amount_vnd"]),
         "Kỳ hạn",        f"{data['tenor_months'] or '—'} tháng"],
        ["Hạn mức đề xuất", _fmt_vnd(data["recommended_amount_vnd"]),
         "Ngày lập",      prepared],
    ]
    story.append(_info_table(kv_data, s_label, s_value, LIGHT))
    story.append(Spacer(1, 3 * mm))

    # ── Agent finding sections ─────────────────────────────────────────────────
    agent_order = ["customer_360", "financial_analysis", "collateral_legal",
                   "policy_compliance", "cic_check", "legal_review"]
    by_agent = {s["agent"]: s for s in data["agent_sections"]}

    for agent_id in agent_order:
        sec = by_agent.get(agent_id)
        if not sec:
            continue
        block = [_section_header(sec["title"], NAVY, s_h1)]
        rows = []
        for f in sec["findings"]:
            stance_color = GREEN if f["stance"] == "SUPPORT" else (
                RED if f["stance"] == "OPPOSE" else AMBER)
            conf_pct = f"{int((f['confidence'] or 0) * 100)}%"
            rows.append([
                Paragraph(f["key"], s_label),
                Paragraph(f["claim"], s_body),
                Paragraph(f"<font color='#{_hex(stance_color)}'>{f['stance']}</font>", s_body),
                Paragraph(conf_pct, s_label),
            ])
        if rows:
            ftbl = Table(rows, colWidths=["18%", "58%", "14%", "10%"])
            ftbl.setStyle(TableStyle([
                ("FONTNAME",      (0, 0), (-1, -1), "DV"),
                ("FONTSIZE",      (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT]),
                ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDEE")),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ]))
            block.append(ftbl)
        block.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(block))

    # ── Hard gates ────────────────────────────────────────────────────────────
    if data["gate_rows"]:
        story.append(_section_header("VIII. KIỂM TRA HARD GATES", NAVY, s_h1))
        gate_rows = [[
            Paragraph("<b>Gate ID</b>", s_label),
            Paragraph("<b>Nội dung</b>", s_label),
            Paragraph("<b>Kết quả</b>", s_label),
        ]]
        for g in data["gate_rows"]:
            st = g["status"]
            c = GREEN if st == "Đạt" else (RED if st == "Không đạt" else AMBER)
            gate_rows.append([
                Paragraph(g["id"], s_label),
                Paragraph(g.get("label", g["id"]), s_body),
                Paragraph(f"<font color='#{_hex(c)}'><b>{st}</b></font>", s_body),
            ])
        gtbl = Table(gate_rows, colWidths=["25%", "55%", "20%"])
        gtbl.setStyle(TableStyle([
            ("FONTNAME",   (0, 0), (-1, -1), "DV"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
            ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDEE")),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ]))
        story.append(gtbl)
        story.append(Spacer(1, 3 * mm))

    # ── Conditions precedent ─────────────────────────────────────────────────
    if data["conditions_precedent"]:
        story.append(_section_header("IX. ĐIỀU KIỆN TIÊN QUYẾT GIẢI NGÂN", NAVY, s_h1))
        for i, cond in enumerate(data["conditions_precedent"], 1):
            story.append(Paragraph(f"{i}. {cond}", s_cond))
        story.append(Spacer(1, 3 * mm))

    # ── Conclusion ───────────────────────────────────────────────────────────
    story.append(_section_header("X. KẾT LUẬN VÀ KIẾN NGHỊ", ORANGE, s_h1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Căn cứ kết quả phân tích, AI Credit Engine đưa ra khuyến nghị:", s_body))
    story.append(Spacer(1, 2 * mm))
    rec_data = [[Paragraph(
        f"<font color='#{_hex(rec_color)}'>{data['recommendation_vi']}</font>",
        s_rec,
    )]]
    rtbl = Table(rec_data, colWidths=["100%"])
    rtbl.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BOX",           (0, 0), (-1, -1), 1.5, rec_color),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor(
            "#F0FAF5" if rec == "APPROVE" else
            "#FFF1F0" if rec == "REJECT" else
            "#FFFBF0"
        )),
    ]))
    story.append(rtbl)
    story.append(Spacer(1, 6 * mm))

    # ── Signature block ───────────────────────────────────────────────────────
    sig_data = [[
        Paragraph("<b>Cán bộ thẩm định</b>", s_label),
        Paragraph("<b>Trưởng phòng thẩm định</b>", s_label),
        Paragraph("<b>Giám đốc phê duyệt</b>", s_label),
    ], [
        Paragraph("(Ký, ghi rõ họ tên)", s_footer),
        Paragraph("(Ký, ghi rõ họ tên)", s_footer),
        Paragraph("(Ký, đóng dấu)", s_footer),
    ], [
        Paragraph(" ", s_footer),
        Paragraph(" ", s_footer),
        Paragraph(" ", s_footer),
    ], [
        Paragraph("Nguyễn Văn An", s_body),
        Paragraph(" ", s_body),
        Paragraph(" ", s_body),
    ]]
    stbl = Table(sig_data, colWidths=["33%", "34%", "33%"])
    stbl.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, NAVY),
        ("FONTNAME",      (0, 0), (-1, -1), "DV"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (2, 0), (-1, -1), [LIGHT]),
    ]))
    sig_rows_blank = Table([[Paragraph("", s_body)] * 3] * 4,
                           colWidths=["33%", "34%", "33%"])
    story.append(stbl)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceBefore=4 * mm))
    story.append(Paragraph(
        f"Tài liệu mật — SHBExpert AI v1.0 &nbsp;|&nbsp; "
        f"Ref: {ref_no} &nbsp;|&nbsp; Lập ngày {prepared}",
        s_footer,
    ))

    doc.build(story)
    return buf.getvalue()


def _section_header(title: str, bg_color, style) -> "Table":
    from reportlab.platypus import Table, TableStyle, Paragraph
    tbl = Table([[Paragraph(title, style)]], colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _info_table(rows, s_label, s_value, light_color) -> "Table":
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph
    tbl_rows = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            s = s_label if i % 2 == 0 else s_value
            cells.append(Paragraph(str(cell), s))
        tbl_rows.append(cells)
    tbl = Table(tbl_rows, colWidths=["20%", "30%", "20%", "30%"])
    tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "DV"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, light_color]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDEE")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, -1), "LEFT"),
        ("ALIGN",         (3, 0), (3, -1), "LEFT"),
    ]))
    return tbl


def _hex(color) -> str:
    """Extract hex string from a reportlab HexColor."""
    try:
        return f"{color.hexval():06X}"
    except Exception:
        return "000000"
