"""Sinh bộ eval case tiếng Việt theo ARCHETYPE nghiệp vụ (không phải theo
"mutation đã cấy"), kèm golden_cases.jsonl và overlay dữ liệu cho tools-mock.

Nguyên tắc thiết kế (quan trọng — đọc trước khi sửa file này):

1. Golden case = ĐÁP ÁN ĐÚNG THEO NGHIỆP VỤ TÍN DỤNG, độc lập hoàn toàn với
   việc hệ thống hiện tại có làm được hay không. Không có trường nào kiểu
   "known_gap" để bào chữa cho hệ thống — nếu pipeline trượt một case, đó là
   KẾT QUẢ TRUNG THỰC cần báo cáo, không phải thứ để giấu vào file đáp án.

2. Số liệu mỗi case được neo có chủ đích ở đúng phía ngưỡng THẬT trong code
   (đã đọc và verify), để case thực sự đi vào code path cần test:
     - DSCR >= 1.3            -> SUPPORT, else CAUTION  (financial.py:47,300)
     - coverage_tier < 0.7    -> UNDER_SECURED/OPPOSE -> gate G5 -> REJECT
                                 (mcp-deterministic server.py:124-129,
                                  decision.py:111-119)
     - identity_match < 90    -> NEED_DATA -> gate G2 -> REFER
                                 (customer360.py:66,144; decision.py:79-86)
     - lệch doanh thu > 5%    -> NEED_DATA -> gate G4 -> NEED_INFO
                                 (policy.py:33,68; decision.py:94-104)
     - report_expiry < as_of  -> CAUTION/REQUIRE_REVALUATION (collateral.py:150-155)
   Đây là thiết kế test case cho ĐÚNG code path, KHÔNG phải rig kết quả: nhãn
   kỳ vọng suy ra từ logic rủi ro tín dụng, không suy ngược từ "muốn kiến trúc
   nào thắng".

3. Doanh nghiệp yếu trong thực tế hiếm khi chỉ yếu ĐÚNG một chỗ — một khách
   DSCR kém thường đồng thời đòn bẩy cao, lợi nhuận mỏng. Nên các archetype
   "xấu" được dựng với các tín hiệu yếu tương quan nhau cho giống hồ sơ thật,
   chứ không phải chỉ vặn đúng 1 biến rồi giữ mọi thứ khác hoàn hảo.

Output:
  artifacts/eval_cases/<case_id>/case.json      -- cùng schema artifacts/cases/*
  artifacts/eval_cases/tools_mock_overlay.json  -- record cho tools-mock
                                                   (valuation/obligations/CIC)
  eval/golden_cases.jsonl                       -- đáp án đúng theo nghiệp vụ

Chạy: python -m eval.generate_cases
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "artifacts" / "eval_cases"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden_cases.jsonl"

AS_OF = "2026-06-30"
AS_OF_DATE = date.fromisoformat(AS_OF)

# Ngưỡng thật, copy từ code (dùng để TÍNH nhãn kỳ vọng, không phải để rig)
DSCR_SUPPORT = 1.3
COVERAGE_UNDER_SECURED = 0.7
IDENTITY_THRESHOLD = 90.0
REVENUE_MISMATCH_PCT = 5.0
FORCED_SALE_FACTOR = 0.85  # tools-mock/app/main.py::_valuation_record
HAIRCUT_REAL_ESTATE = 0.35  # haircut_matrix, scripts/seed_collateral_reference.py
DEBT_AMORT_YEARS = 5  # seed_synthetic_cases.py::_DEBT_AMORTIZATION_YEARS

B = 1_000_000_000  # tỷ VND


def _fin(period: str, *, revenue, cogs, opex, interest, cash, receivables, inventory,
         fixed_assets, payables, debt, ocf, icf, fcf, reported_revenue=None) -> dict:
    """Dựng 1 kỳ BCTC cân đối: assets = TSNH + TSCĐ, liabilities = nợ ngắn +
    nợ dài, equity = assets - liabilities (bảng cân đối luôn khớp)."""
    gross = revenue - cogs
    pbt = gross - opex - interest
    tax = round(pbt * 0.2) if pbt > 0 else 0
    net = pbt - tax
    assets = cash + receivables + inventory + fixed_assets
    liabilities = payables + debt
    row = {
        "financial_id": f"FIN-{period}",
        "period": period,
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross,
        "operating_expenses": opex,
        "interest_expense": interest,
        "profit_before_tax": pbt,
        "tax": tax,
        "net_profit": net,
        "cash": cash,
        "receivables": receivables,
        "inventory": inventory,
        "fixed_assets": fixed_assets,
        "assets": assets,
        "payables": payables,
        "debt": debt,
        "liabilities": liabilities,
        "equity": assets - liabilities,
        "operating_cash_flow": ocf,
        "investing_cash_flow": icf,
        "financing_cash_flow": fcf,
        "synthetic_flag": True,
    }
    if reported_revenue is not None:
        row["reported_revenue"] = reported_revenue
    return row


# debt_service_annual = interest + debt/5, với interest = INTEREST_RATE*debt
# (xem seed_synthetic_cases.py::_build_docs) => debt_service = DS_PER_DEBT * debt.
INTEREST_RATE = 0.16
DS_PER_DEBT = INTEREST_RATE + 1 / DEBT_AMORT_YEARS  # 0.36

# EBITDA = profit_before_tax + interest_expense = revenue - cogs - opex
# (interest triệt tiêu) => DSCR = EBITDA / (DS_PER_DEBT * debt), nên muốn có
# DSCR mục tiêu thì suy ngược ra `debt` thay vì vặn hệ số mò.


def _profile(scale: float, *, cogs_pct=0.667, opex_pct=0.15, target_dscr=6.0,
             cash_b=6.0, recv_b=10.0, inv_b=7.0, fixed_b=12.0, payables_b=12.0,
             reported_revenue_pct=None):
    """Dựng 3 kỳ BCTC với DSCR 2025 đúng bằng `target_dscr`.

    Neo theo DSCR mục tiêu (không phải theo hệ số nợ mò) vì DSCR là biến quyết
    định stance của REPAYMENT_CAPACITY (ngưỡng 1.3, financial.py:47) — muốn case
    nằm đúng phía ngưỡng thì phải giải ngược ra `debt`, nếu không rất dễ tạo ra
    doanh nghiệp EBITDA âm (DSCR âm) trông phi thực tế."""
    rev = round(60 * B * scale)
    cogs = round(rev * cogs_pct)
    opex = round(rev * opex_pct)
    ebitda = rev - cogs - opex
    debt = round(ebitda / (DS_PER_DEBT * target_dscr))
    interest = round(debt * INTEREST_RATE)

    cash, recv = round(cash_b * B * scale), round(recv_b * B * scale)
    inv, fixed = round(inv_b * B * scale), round(fixed_b * B * scale)
    payables = round(payables_b * B * scale)

    def prior(mult: float, debt_mult: float):
        r = round(rev * mult)
        c, o = round(r * cogs_pct), round(r * opex_pct)
        d = round(debt * debt_mult)
        return dict(revenue=r, cogs=c, opex=o, interest=round(d * INTEREST_RATE),
                    cash=round(cash * mult), receivables=round(recv * mult),
                    inventory=round(inv * mult), fixed_assets=round(fixed * mult),
                    payables=round(payables * mult), debt=d)

    ocf = round(ebitda * 0.8)
    icf = round(-0.27 * ebitda)
    fcf = round(-0.18 * ebitda)

    return [
        _fin("2023", **prior(0.83, 1.05), ocf=round(ocf * 0.85), icf=round(icf * 0.85), fcf=round(fcf * 0.85)),
        _fin("2024", **prior(0.92, 1.02), ocf=round(ocf * 0.93), icf=round(icf * 0.93), fcf=round(fcf * 0.93)),
        _fin("2025", revenue=rev, cogs=cogs, opex=opex, interest=interest, cash=cash,
             receivables=recv, inventory=inv, fixed_assets=fixed, payables=payables, debt=debt,
             ocf=ocf, icf=icf, fcf=fcf,
             reported_revenue=round(rev * (1 - reported_revenue_pct / 100)) if reported_revenue_pct else None),
    ]


def _collateral_for(total_obligation: int, tier: str) -> tuple[int, int]:
    """Trả (valuation_amount khách nộp, official_value của ngân hàng) sao cho
    coverage sau haircut rơi đúng tier mong muốn.

    adjusted = official * FORCED_SALE_FACTOR * (1 - haircut) = 0.5525 * official
    => OVER_SECURED cần official >= 1.81 * tổng nghĩa vụ; UNDER_SECURED cần
    official < 1.27 * tổng nghĩa vụ. Tính ngược như vậy để archetype nào không
    nói về TSBĐ thì KHÔNG vô tình dính gate G5 (REJECT vì thiếu TSBĐ) — mỗi
    case chỉ được kích hoạt đúng tín hiệu mà nó muốn kiểm tra."""
    mult = {"OVER_SECURED": 2.0, "UNDER_SECURED": 0.9}[tier]
    official = round(total_obligation * mult)
    return round(official / 0.97), official


CONG_TY = [
    ("CÔNG TY TNHH SẢN XUẤT THỰC PHẨM MINH PHÁT", "C101", "Hà Nội"),
    ("CÔNG TY CỔ PHẦN DỆT MAY AN BÌNH", "C131", "Nam Định"),
    ("CÔNG TY TNHH CHẾ BIẾN GỖ TRƯỜNG THÀNH", "C161", "Bình Dương"),
    ("CÔNG TY CỔ PHẦN CƠ KHÍ ĐÔNG Á", "C251", "Hải Phòng"),
    ("CÔNG TY TNHH THƯƠNG MẠI NÔNG SẢN THÁI SƠN", "G463", "Đắk Lắk"),
    ("CÔNG TY CỔ PHẦN XÂY DỰNG HOÀNG GIA", "F410", "Hà Nội"),
    ("CÔNG TY TNHH NHỰA KỸ THUẬT VIỆT TIẾN", "C222", "Đồng Nai"),
    ("CÔNG TY CỔ PHẦN THỦY SẢN BIỂN ĐÔNG", "C102", "Cà Mau"),
]

MUC_DICH = [
    ("Bổ sung vốn lưu động phục vụ đơn hàng xuất khẩu quý III-IV/2026", "WC01"),
    ("Bổ sung vốn lưu động thu mua nguyên liệu đầu vụ", "WC02"),
    ("Bổ sung vốn lưu động thanh toán nhà cung cấp trong nước", "WC03"),
]


def _case(idx: int, archetype: str, variant: int, *, fin_years, requested_amount,
          valuation_amount, official_value, obligations_vnd, cic, valuation_date,
          report_expiry_date, ghi_chu_kich_ban) -> tuple[dict, dict, dict]:
    n = idx
    case_id = f"GOLD-{n:03d}"
    customer_id = f"CUSG-{n:03d}"
    name, industry, tinh = CONG_TY[(n - 1) % len(CONG_TY)]
    name = f"{name} {n:03d}"
    muc_dich, purpose_code = MUC_DICH[(variant - 1) % len(MUC_DICH)]

    case = {
        "case_id": case_id,
        "kich_ban": ghi_chu_kich_ban,
        "archetype": archetype,
        "customer": {
            "customer_id": customer_id,
            "legal_name": name,
            "mock_tax_id": f"MOCK-TAX-{n:07d}",
            "industry_code": industry,
            "industry_version": "VSIC-2018",
            "incorporation_date": "2014-03-18",
            "legal_address": f"Số {n * 7 % 200 + 1}, đường Lê Lợi, {tinh}",
            "representative_party_id": f"PTY-{n:05d}",
            "related_party_ids": [],
            "as_of_date": AS_OF,
        },
        "application": {
            "application_id": f"APP-{n:05d}",
            "customer_id": customer_id,
            "product_code": "SME_WC",
            "requested_amount": requested_amount,
            "currency": "VND",
            "tenor_months": 12,
            "purpose_code": purpose_code,
            "muc_dich_vay": muc_dich,
            "repayment_method": "Trả gốc cuối kỳ, lãi hàng tháng",
            "repayment_source": "Doanh thu từ hoạt động kinh doanh chính",
            "proposed_collateral_ids": [f"COL-{n:05d}"],
        },
        "legal_documents": [
            {
                "document_id": f"DOC-{n:05d}-1",
                "customer_id": customer_id,
                "application_id": f"APP-{n:05d}",
                "document_type": "BUSINESS_REGISTRATION",
                "document_number": f"MOCK-BUS-{n:05d}",
                "issued_at": "2014-03-18",
                "valid_to": None,
                "canonical_fields": {"legal_name": name, "mock_tax_id": f"MOCK-TAX-{n:07d}"},
                "synthetic_flag": True,
            }
        ],
        "financials": fin_years,
        "transactions": [],
        "cic_reports": [
            {
                "cic_report_id": f"CIC-{n:05d}",
                "customer_id": customer_id,
                "checked_at": "2026-06-25",
                "facilities": [
                    {
                        "facility_id": f"CICF-{n:05d}-1",
                        "mock_lender_code": "MOCK_BANK_02",
                        "current_outstanding": cic["total_outstanding_other_ctcd"],
                        "debt_group": cic["cic_debt_group"],
                        "days_past_due": 0 if not cic["overdue_events"] else cic["overdue_events"][0]["overdue_days"],
                        "delinquency_history": cic["overdue_events"],
                    }
                ],
                "inquiry_count_30d": 1,
                "inquiry_count_12m": 2,
                "synthetic_flag": True,
            }
        ],
        "kyc_screenings": [
            {
                "screening_id": f"KYC-{n:05d}",
                "customer_id": customer_id,
                "match_status": "NO_MATCH" if cic["identity_match_score"] >= IDENTITY_THRESHOLD else "POTENTIAL_MATCH",
                "identity_match_score": cic["identity_match_score"],
                "screened_at": "2026-06-25",
                "synthetic_flag": True,
            }
        ],
        "collateral": [
            {
                "collateral_id": f"COL-{n:05d}",
                "application_id": f"APP-{n:05d}",
                "owner_party_id": f"PTY-{n:05d}",
                "property_type": "RESIDENTIAL_REAL_ESTATE",
                "mock_address": f"Thửa đất số {n * 3 % 90 + 10}, {tinh}",
                "valuation_amount": valuation_amount,
                "valuation_date": valuation_date,
                "haircut_rate": HAIRCUT_REAL_ESTATE,
                "eligible_value": round(valuation_amount * (1 - HAIRCUT_REAL_ESTATE)),
                "encumbrance_status": "NONE",
                "encumbrance_amount": 0,
                "ownership_document_id": f"DOC-{n:05d}-1",
                "synthetic_flag": True,
            }
        ],
        "relationships": [
            {
                "relationship_id": f"REL-{n:05d}",
                "customer_id": customer_id,
                "product_used": "SME_WC",
                "relationship_start_date": "2019-05-10",
                "current_exposure": obligations_vnd,
                "synthetic_flag": True,
            }
        ],
        "policy_snapshot_id": "MOCK-POLICY-PACK-V3",
        "as_of_date": AS_OF,
        "applied_mutations": [],
        "synthetic_data_notice": (
            "Dữ liệu tổng hợp (synthetic) phục vụ đánh giá hệ thống — không phải hồ sơ khách hàng thật."
        ),
    }

    valuation_record = {
        "collateral_id": case_id,
        "official_value_vnd": official_value,
        "forced_sale_value": round(official_value * FORCED_SALE_FACTOR),
        "valuation_date": valuation_date,
        "valuation_method": "so_sanh",
        "report_expiry_date": report_expiry_date,
        "source": "SHB_INTERNAL_REGISTRY",
    }
    obligation_record = {
        "outstanding_loan_vnd": obligations_vnd,
        "outstanding_guarantee_vnd": 0,
        "outstanding_lc_vnd": 0,
    }
    return case, valuation_record, {"customer_id": customer_id, "cic": cic,
                                    "valuation": valuation_record, "obligation": obligation_record}


def _derive_truth(case: dict, official_value: int, obligations_vnd: int, report_expiry_date: str) -> dict:
    """Tính các con số ground-truth TỪ CHÍNH số liệu của case, bằng đúng công
    thức tool xác định đang dùng. Dùng cho metric numeric_accuracy: single-agent
    tự tính trong đầu sẽ lệch, multi-agent lấy từ tool nên khớp."""
    f25 = next(f for f in case["financials"] if f["period"] == "2025")
    requested = case["application"]["requested_amount"]
    col = case["collateral"][0]

    ebitda = f25["profit_before_tax"] + f25["interest_expense"]
    debt_service = f25["interest_expense"] + f25["debt"] / DEBT_AMORT_YEARS
    dscr = round(ebitda / debt_service, 3)

    naive_coverage = round(col["valuation_amount"] / requested, 3)

    forced_sale = round(official_value * FORCED_SALE_FACTOR)
    adjusted = round(forced_sale * (1 - HAIRCUT_REAL_ESTATE), 2)
    total_obligation = obligations_vnd + requested
    real_coverage = round(adjusted / total_obligation, 3)
    tier = ("OVER_SECURED" if real_coverage >= 1.0
            else "ADEQUATE" if real_coverage >= COVERAGE_UNDER_SECURED else "UNDER_SECURED")

    reported = f25.get("reported_revenue")
    mismatch_pct = round(abs(f25["revenue"] - reported) / f25["revenue"] * 100, 2) if reported else 0.0

    cert_expiry = (date.fromisoformat(col["valuation_date"]) + timedelta(days=365)).isoformat()
    # debt_ratio/current_ratio: tính được TRỰC TIẾP từ case.json bằng định
    # nghĩa kế toán chuẩn, không cần quy ước riêng của ngân hàng — nên dùng
    # được để đối chiếu số cho CẢ HAI variant một cách công bằng.
    total_capital_source = f25["liabilities"] + f25["equity"]
    return {
        "dscr": dscr,
        "debt_ratio": round(f25["liabilities"] / total_capital_source, 4),
        "current_ratio": round(
            (f25["cash"] + f25["receivables"] + f25["inventory"]) / f25["payables"], 4
        ),
        "ebitda_vnd": ebitda,
        "debt_service_annual_vnd": round(debt_service),
        "coverage_ratio_naive": naive_coverage,
        "coverage_ratio_after_haircut": real_coverage,
        "coverage_tier": tier,
        "revenue_mismatch_pct": mismatch_pct,
        "cert_expiry_date": cert_expiry,
        "report_expiry_date": report_expiry_date,
        "report_is_stale": date.fromisoformat(report_expiry_date) < AS_OF_DATE,
    }


# ---------------------------------------------------------------------------
# 8 archetype nghiệp vụ × 3 biến thể = 24 case
# ---------------------------------------------------------------------------
def build_all() -> tuple[list[dict], dict, list[dict]]:
    cases, overlay_rows, goldens = [], [], []
    idx = 0

    def add(archetype, variant, *, fin_years, requested, valuation, official, obligations,
            cic, valuation_date="2026-01-15", report_expiry="2027-01-15", kich_ban,
            expected_decision, expected_decision_not, must_flag, must_not_flag, ly_do,
            expected_conflict=None):
        nonlocal idx
        idx += 1
        case, val_rec, meta = _case(idx, archetype, variant, fin_years=fin_years,
                                    requested_amount=requested, valuation_amount=valuation,
                                    official_value=official, obligations_vnd=obligations, cic=cic,
                                    valuation_date=valuation_date, report_expiry_date=report_expiry,
                                    ghi_chu_kich_ban=kich_ban)
        truth = _derive_truth(case, official, obligations, report_expiry)
        cases.append(case)
        overlay_rows.append(meta)
        goldens.append({
            "case_id": case["case_id"],
            "archetype": archetype,
            "kich_ban": kich_ban,
            "expected_decision": expected_decision,
            "expected_decision_not": expected_decision_not,
            "expected_conflict": expected_conflict,
            "must_flag_risks": must_flag,
            "must_not_flag_risks": must_not_flag,
            "ground_truth_numbers": truth,
            "ly_do_nghiep_vu": ly_do,
        })

    # Chuẩn "an toàn" dùng chung cho các archetype KHÔNG nói về TSBĐ/CIC:
    # TSBĐ dư bảo đảm, CIC nhóm 1 sạch, khớp nhận dạng cao — để mỗi case chỉ
    # kích hoạt đúng một tín hiệu rủi ro mà nó muốn kiểm tra.
    def cic_sach(scale):
        return {"cic_debt_group": 1, "total_outstanding_other_ctcd": round(2 * B * scale),
                "overdue_events": [], "identity_match_score": 97}

    def tsbd_du(scale, requested, obligations, tier="OVER_SECURED"):
        return _collateral_for(obligations + requested, tier)

    # 1. HỒ SƠ SẠCH — mọi tín hiệu tốt. Kiểm tra hệ thống KHÔNG bịa ra rủi ro.
    for v, scale in enumerate([1.0, 1.4, 0.75], start=1):
        requested, obligations = round(8 * B * scale), round(2 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("CLEAN_APPROVE", v, fin_years=_profile(scale), requested=requested,
            valuation=val, official=off, obligations=obligations, cic=cic_sach(scale),
            kich_ban="Doanh nghiệp SME sản xuất, tài chính lành mạnh, DSCR cao, TSBĐ dư bảo đảm, "
                     "CIC nhóm 1 không nợ quá hạn, doanh thu BCTC khớp tờ khai thuế.",
            expected_decision="APPROVE", expected_decision_not=["REJECT", "NEED_INFO"],
            must_flag=[],
            # Mọi tín hiệu dưới đây đều LÀNH MẠNH KHÁCH QUAN trong dữ liệu case
            # này (DSCR 6.0; lệch doanh thu 0%; CIC nhóm 1, khớp nhận dạng 97;
            # TSBĐ OVER_SECURED; cả 4 nhóm tỷ số đều Tốt/Khá so với trung bình
            # ngành). Nêu rủi ro ở bất kỳ mục nào trong số này là cảnh báo giả.
            must_not_flag=["REPAYMENT_CAPACITY", "REVENUE_RECONCILIATION", "CREDIT_CONDUCT",
                           "COLLATERAL_COVERAGE", "LIQUIDITY", "PROFITABILITY", "LEVERAGE", "ACTIVITY"],
            expected_conflict=False,
            ly_do="Không có tín hiệu rủi ro nào vượt ngưỡng; hồ sơ đủ điều kiện phê duyệt. "
                  "Case này kiểm tra tỷ lệ cảnh báo giả (bịa rủi ro không có thật).")

    # 2. LỆCH DOANH THU BCTC vs TỜ KHAI THUẾ (>5% -> gate G4 -> NEED_INFO)
    for v, (scale, pct) in enumerate([(1.0, 18.0), (1.2, 12.0), (0.85, 25.0)], start=1):
        requested, obligations = round(8 * B * scale), round(2 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("REVENUE_MISMATCH", v, fin_years=_profile(scale, reported_revenue_pct=pct),
            requested=requested, valuation=val, official=off, obligations=obligations, cic=cic_sach(scale),
            kich_ban=f"Doanh thu trên BCTC cao hơn doanh thu chịu thuế trên tờ khai quyết toán "
                     f"khoảng {pct}% mà chưa có giải trình của khách hàng.",
            expected_decision="NEED_INFO", expected_decision_not=["APPROVE"],
            must_flag=["REVENUE_RECONCILIATION"], must_not_flag=[], expected_conflict=None,
            ly_do="Chênh lệch doanh thu giữa hai nguồn độc lập vượt ngưỡng trọng yếu là dấu hiệu "
                  "cần làm rõ trước khi cấp tín dụng — phải yêu cầu bổ sung giải trình, "
                  "không được phê duyệt khi chưa đối chiếu được.")

    # 3. KHẢ NĂNG TRẢ NỢ YẾU — DSCR dưới 1.3 nhưng vẫn DƯƠNG (doanh nghiệp còn
    #    lãi, chỉ là đệm trả nợ mỏng), kèm biên lợi nhuận hẹp cho giống thật.
    for v, (scale, dscr, cogs_pct) in enumerate([(1.0, 1.05, 0.74), (1.3, 1.2, 0.72), (0.8, 0.85, 0.76)], start=1):
        requested, obligations = round(8 * B * scale), round(2 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("WEAK_DSCR", v, fin_years=_profile(scale, target_dscr=dscr, cogs_pct=cogs_pct),
            requested=requested, valuation=val, official=off, obligations=obligations, cic=cic_sach(scale),
            kich_ban="Dòng tiền EBITDA không đủ đệm an toàn để bao phủ nghĩa vụ trả nợ gốc và lãi "
                     "hàng năm (DSCR dưới ngưỡng 1.3), biên lợi nhuận mỏng.",
            expected_decision="REFER", expected_decision_not=["APPROVE"],
            must_flag=["REPAYMENT_CAPACITY"], must_not_flag=[], expected_conflict=None,
            ly_do="DSCR dưới 1.3 nghĩa là nguồn trả nợ không đủ đệm an toàn — bắt buộc phải nêu "
                  "rủi ro khả năng trả nợ, không được phê duyệt trơn.")

    # 4. TSBĐ KHÔNG ĐỦ BAO PHỦ -> UNDER_SECURED -> OPPOSE -> gate G5 -> REJECT.
    #    Đây cũng là case MÂU THUẪN LIÊN AGENT có thật: Financial dùng giá trị
    #    định giá khách nộp (naive, coverage >= 1 -> SUPPORT) trong khi
    #    Collateral dùng giá trị thanh lý sau haircut so với TỔNG nghĩa vụ
    #    (-> OPPOSE). Hai agent cùng ghi issue_key COLLATERAL_COVERAGE với
    #    stance trái chiều => conflict detector phải phát hiện.
    for v, scale in enumerate([1.0, 1.1, 0.9], start=1):
        requested, obligations = round(10 * B * scale), round(3 * B * scale)
        val, off = _collateral_for(obligations + requested, "UNDER_SECURED")
        add("COLLATERAL_SHORTFALL", v, fin_years=_profile(scale), requested=requested,
            valuation=val, official=off, obligations=obligations, cic=cic_sach(scale),
            kich_ban="Giá trị tài sản bảo đảm sau khấu trừ thanh lý và haircut không đủ bao phủ "
                     "tổng nghĩa vụ sau giải ngân (dư nợ hiện hữu cộng hạn mức đề nghị), "
                     "trong khi giá trị định giá khách hàng nộp nhìn qua vẫn có vẻ đủ.",
            expected_decision="REJECT", expected_decision_not=["APPROVE", "APPROVE_WITH_CONDITIONS"],
            must_flag=["COLLATERAL_COVERAGE"], must_not_flag=[], expected_conflict=True,
            ly_do="TSBĐ thiếu hụt nghiêm trọng so với tổng nghĩa vụ là điều kiện loại trừ — phải "
                  "từ chối hoặc yêu cầu bổ sung tài sản. Đồng thời giá trị khách nộp và giá trị "
                  "thanh lý sau haircut cho kết luận trái ngược nhau nên hệ thống phải phát hiện "
                  "mâu thuẫn thay vì lặng lẽ chọn một phía.")

    # 5. REPORT ĐỊNH GIÁ HẾT HIỆU LỰC -> cần định giá lại
    for v, (scale, rpt_exp) in enumerate([(1.0, "2026-03-01"), (1.2, "2026-01-20"), (0.85, "2026-05-15")], start=1):
        requested, obligations = round(8 * B * scale), round(2 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("VALUATION_STALE", v, fin_years=_profile(scale), requested=requested,
            valuation=val, official=off, obligations=obligations, cic=cic_sach(scale), report_expiry=rpt_exp,
            kich_ban=f"Báo cáo định giá nội bộ đã hết hiệu lực từ {rpt_exp}, trước ngày thẩm định "
                     f"{AS_OF} — giá trị TSBĐ không còn được coi là cập nhật.",
            expected_decision="NEED_INFO", expected_decision_not=["APPROVE"],
            must_flag=["COLLATERAL_COVERAGE"], must_not_flag=[], expected_conflict=None,
            ly_do="Định giá hết hiệu lực thì giá trị TSBĐ chưa được xác nhận tại thời điểm cấp "
                  "tín dụng — phải đặt điều kiện định giá lại, không phê duyệt vô điều kiện.")

    # 6. LỊCH SỬ TÍN DỤNG XẤU (CIC nhóm >= 3 -> OPPOSE)
    for v, (scale, group) in enumerate([(1.0, 3), (1.15, 4), (0.9, 3)], start=1):
        requested, obligations = round(8 * B * scale), round(3 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("BAD_CREDIT_HISTORY", v, fin_years=_profile(scale, target_dscr=2.2, cogs_pct=0.70),
            requested=requested, valuation=val, official=off, obligations=obligations,
            cic={"cic_debt_group": group, "total_outstanding_other_ctcd": round(4 * B * scale),
                 "overdue_events": [{"institution": "MOCK_BANK_07", "overdue_days": 95,
                                     "overdue_amount": round(0.4 * B * scale),
                                     "reason": "Chậm thanh toán gốc nhiều kỳ liên tiếp"}],
                 "identity_match_score": 96},
            kich_ban=f"Khách hàng đang bị phân loại nợ nhóm {group} trên CIC, có lịch sử quá hạn "
                     f"kéo dài tại tổ chức tín dụng khác.",
            expected_decision="REJECT", expected_decision_not=["APPROVE"],
            must_flag=["CREDIT_CONDUCT"], must_not_flag=[], expected_conflict=None,
            ly_do="Nợ nhóm 3 trở lên là nợ xấu theo phân loại NHNN — bắt buộc nêu rủi ro lịch sử "
                  "tín dụng và không được phê duyệt như hồ sơ bình thường.")

    # 7. NHẬN DẠNG KHÁCH HÀNG CHƯA RÕ (identity_match < 90 -> NEED_DATA -> G2 -> REFER)
    for v, (scale, score) in enumerate([(1.0, 72), (1.2, 65), (0.9, 84)], start=1):
        requested, obligations = round(8 * B * scale), round(2 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("IDENTITY_UNCLEAR", v, fin_years=_profile(scale), requested=requested,
            valuation=val, official=off, obligations=obligations,
            cic={"cic_debt_group": 1, "total_outstanding_other_ctcd": round(2 * B * scale),
                 "overdue_events": [], "identity_match_score": score},
            kich_ban=f"Bản ghi CIC/KYC chỉ khớp nhận dạng ở mức {score}/100 — chưa đủ tin cậy để "
                     f"khẳng định đây đúng là khách hàng đang thẩm định.",
            expected_decision="REFER", expected_decision_not=["APPROVE", "REJECT"],
            must_flag=["CREDIT_CONDUCT"], must_not_flag=[], expected_conflict=None,
            ly_do="Khớp nhận dạng thấp phải chuyển chuyên viên xác minh thủ công. Tuyệt đối không "
                  "được KẾT LUẬN đây là hồ sơ xấu (REJECT) dựa trên bản ghi có thể của người khác, "
                  "cũng không được coi như đã xác minh (APPROVE).")

    # 8. ĐÒN BẨY CAO / VỐN MỎNG — nợ chiếm tỷ trọng lớn trong tổng nguồn vốn.
    #    DSCR vẫn giữ trên 1.3 để tín hiệu được kiểm tra là ĐÒN BẨY, không lẫn
    #    sang khả năng trả nợ.
    for v, (scale, fixed_b, payables_b) in enumerate([(1.0, 20.0, 14.0), (1.25, 18.0, 13.0), (0.8, 22.0, 15.0)], start=1):
        requested, obligations = round(8 * B * scale), round(3 * B * scale)
        val, off = tsbd_du(scale, requested, obligations)
        add("HIGH_LEVERAGE", v,
            fin_years=_profile(scale, target_dscr=1.45, cogs_pct=0.70, fixed_b=fixed_b,
                               payables_b=payables_b, cash_b=3.0, inv_b=5.0),
            requested=requested, valuation=val, official=off, obligations=obligations, cic=cic_sach(scale),
            kich_ban="Tỷ lệ nợ trên tổng nguồn vốn cao hơn nhiều so với trung bình ngành, vốn chủ "
                     "sở hữu mỏng, cơ cấu nguồn vốn mất cân đối.",
            expected_decision="REFER", expected_decision_not=["APPROVE"],
            must_flag=["LEVERAGE"], must_not_flag=[], expected_conflict=None,
            ly_do="Đòn bẩy vượt xa trung bình ngành làm giảm khả năng chống chịu cú sốc — phải nêu "
                  "rủi ro cơ cấu vốn trong nhóm chỉ số đòn bẩy.")

    overlay = {
        "_notice": "Fixture cho tools-mock phục vụ eval — dữ liệu tổng hợp, không phải hệ thống thật.",
        "valuations": {m["valuation"]["collateral_id"]: m["valuation"] for m in overlay_rows},
        "obligations": {m["customer_id"]: m["obligation"] for m in overlay_rows},
        "cic": {m["customer_id"]: m["cic"] for m in overlay_rows},
    }
    return cases, overlay, goldens


def main() -> None:
    cases, overlay, goldens = build_all()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for case in cases:
        d = OUT_DIR / case["case_id"]
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "case.json", "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)

    with open(OUT_DIR / "tools_mock_overlay.json", "w", encoding="utf-8") as f:
        json.dump(overlay, f, ensure_ascii=False, indent=2)

    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        for g in goldens:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    # ASCII-only prints: Windows console mặc định cp1252, in tiếng Việt có dấu
    # ra stdout sẽ ném UnicodeEncodeError (nội dung file vẫn luôn là UTF-8).
    print(f"Generated {len(cases)} cases -> {OUT_DIR}")
    print(f"Golden -> {GOLDEN_PATH}")
    by_arch: dict[str, int] = {}
    for g in goldens:
        by_arch[g["archetype"]] = by_arch.get(g["archetype"], 0) + 1
    for a, c in by_arch.items():
        print(f"  {a}: {c}")


if __name__ == "__main__":
    main()
