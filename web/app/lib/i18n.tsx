"use client";

/**
 * Minimal EN/VI language switcher for the "main screens" (queue, case
 * detail, its 3 tabs, sidebar, chips, formatters). Deliberately NOT wired
 * into EvidenceViewer.tsx / ExplainabilityDrawer.tsx — out of scope for
 * this pass (see docs/architecture plan discussion), those two stay
 * Vietnamese-only for now.
 *
 * Usage: const { t, lang, setLang } = useI18n();  t("queue.title")
 * Falls back to the Vietnamese string (or the raw key) if a key is
 * missing in the active language — never throws, never renders blank.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "vi" | "en";

const STORAGE_KEY = "shbexpert.lang";

const messages: Record<Lang, Record<string, string>> = {
  vi: {
    // ---- Sidebar / nav ---------------------------------------------------
    "nav.appName": "SHBExpert AI",
    "nav.tagline": "Đội chuyên gia AI thẩm định tín dụng",
    "nav.dashboard": "Dashboard",
    "nav.applications": "Applications",
    "nav.tasks": "Tasks",
    "nav.documents": "Documents",
    "nav.reports": "Reports",
    "nav.auditTrail": "Audit Trail",
    "nav.settings": "Settings",
    "nav.comingSoon": "Sắp có",
    "nav.comingSoonTitle": "Chưa có trang này",
    "nav.officerName": "Nguyễn Văn A",
    "nav.officerRole": "Credit Officer",
    "nav.language": "Ngôn ngữ",

    // ---- Common -----------------------------------------------------------
    "common.cancel": "Huỷ",
    "common.confirm": "Xác nhận",
    "common.loading": "Đang tải...",
    "common.noData": "—",

    // ---- Queue page (page.tsx) --------------------------------------------
    "queue.title": "Hồ sơ chờ thẩm định tín dụng",
    "queue.subtitle": "Đội chuyên gia AI phân tích song song, sắp xếp theo mức độ ưu tiên xử lý.",
    "queue.loading": "Đang tải danh sách hồ sơ...",

    // ---- StatsBar -----------------------------------------------------------
    "stats.pending": "Hồ sơ đang chờ xử lý",
    "stats.urgent": "Hồ sơ khẩn cấp",
    "stats.avgApproval": "Thời gian phê duyệt trung bình",
    "stats.avgApprovalNote": "Chưa có hồ sơ nào xử lý xong để tính trung bình",
    "stats.quality": "Chất lượng phê duyệt",
    "stats.qualityNote": "Cần dữ liệu hiệu suất khoản vay sau giải ngân (nợ xấu/NPL) — hệ thống hiện chưa theo dõi dữ liệu này",

    // ---- FilterBar ----------------------------------------------------------
    "filter.allProducts": "Mọi sản phẩm",
    "filter.allAmounts": "Mọi hạn mức",
    "filter.lt1b": "< 1 tỷ",
    "filter.1to5b": "1 – 5 tỷ",
    "filter.gt5b": "> 5 tỷ",
    "filter.clear": "Xoá bộ lọc",

    // ---- QueueList ----------------------------------------------------------
    "queueList.empty": "Không có hồ sơ nào khớp bộ lọc hiện tại.",
    "queueList.waitPrefix": "Chờ",
    "queueList.tenorSuffix": "tháng",

    // ---- Case detail page ----------------------------------------------------
    "case.back": "Bảng điều khiển",
    "case.loading": "Đang tải case {id}...",
    "case.tenorLabel": "kỳ hạn",
    "case.tenorMonths": "tháng",
    "case.tab.overview": "Tổng quan",
    "case.tab.scoring": "Đánh giá sơ bộ & Chấm điểm",
    "case.tab.chat": "Trao đổi & Kết luận",
    "case.rerun": "Chạy lại phân tích",
    "case.staleTitle": "Chỉ dùng được khi hồ sơ đang ở trạng thái READY_FOR_REVIEW (hiện tại: {state})",
    "case.freshNotice": "Hồ sơ đã có đủ dữ liệu — chưa chạy phân tích AI.",
    "case.startAnalyze": "Bắt đầu thẩm định AI",
    "case.actionFailed": "Không thực hiện được — trạng thái hồ sơ vừa thay đổi, hãy tải lại trang. ({err})",

    // ---- OverviewTab -----------------------------------------------------------
    "overview.customerInfo": "Thông tin cơ bản khách hàng",
    "overview.legalName": "Tên pháp nhân",
    "overview.taxCode": "Mã số thuế",
    "overview.industry": "Ngành nghề",
    "overview.representative": "Người đại diện",
    "overview.establishDate": "Ngày thành lập",
    "overview.noIdentity": "Chưa có dữ liệu định danh khách hàng (Customer 360 chưa chạy cho hồ sơ này).",
    "overview.loanInfo": "Thông tin khoản vay",
    "overview.product": "Sản phẩm",
    "overview.requestedAmount": "Số tiền đề nghị",
    "overview.tenor": "Kỳ hạn",
    "overview.tenorMonths": "tháng",
    "overview.documents": "Hồ sơ giấy tờ",
    "overview.incomeCollateral": "Nguồn thu & Tài sản đảm bảo",
    "overview.noFinancials": "Chưa có số liệu tài chính được trích xuất.",
    "overview.collateralType": "Loại tài sản đảm bảo",
    "overview.collateralOwner": "Chủ sở hữu",
    "overview.field.revenue2025": "Doanh thu thuần (2025)",
    "overview.field.ebitda2025": "EBITDA (2025)",
    "overview.field.netProfitAfterTax": "Lợi nhuận sau thuế",
    "overview.field.valuationAmount": "Giá trị định giá TSBĐ",

    // ---- ScoringTab / TaskGraph --------------------------------------------------
    "taskGraph.plan": "Lập kế hoạch",
    "taskGraph.planSubtitle": "Phân rã yêu cầu, giao việc cho 4 agent chuyên môn",
    "taskGraph.parallelProgress": "Tiến trình của 4 agent chuyên môn được điều phối song song",
    "taskGraph.synthesize": "Tổng hợp",
    "taskGraph.synthesizeSubtitle": "Tổng hợp scorecard, hard gate và khuyến nghị cuối cùng",
    "taskGraph.status.pending": "Chờ xử lý",
    "taskGraph.status.in_progress": "Đang xử lý",
    "taskGraph.status.done": "Hoàn tất",
    "taskGraph.status.failed": "Lỗi",

    // ---- AgentTraceCard -----------------------------------------------------
    "agentTrace.waiting": "Đang chờ xử lý...",
    "agentTrace.metricsComputed": "Chỉ số đã tính ({n})",
    "agentTrace.policyBasis": "Căn cứ chính sách/pháp lý",
    "metric.dscr": "Hệ số trả nợ (DSCR)",
    "metric.ebitda_margin": "Biên EBITDA",
    "metric.coverage_ratio": "Tỷ lệ bao phủ TSBĐ",
    "metric.cert_days_to_expiry": "Số ngày còn hiệu lực chứng thư",
    "metric.haircut_rate": "Tỷ lệ chiết khấu (haircut)",
    "metric.total_obligation_vnd": "Tổng nghĩa vụ nợ (VNĐ)",
    "metric.net_cashflow": "Dòng tiền thuần",
    "metric.operating_cf_ratio": "Tỷ lệ dòng tiền HĐKD / doanh thu",
    "metric.current_ratio": "Hệ số thanh toán hiện hành",
    "metric.quick_ratio": "Hệ số thanh toán nhanh",
    "metric.cash_ratio": "Hệ số thanh toán tiền mặt",
    "metric.roa": "ROA",
    "metric.roe": "ROE",
    "metric.debt_ratio": "Hệ số nợ",
    "metric.self_financing_ratio": "Hệ số tự tài trợ",
    "metric.net_working_capital": "Vốn lưu động ròng",
    "metric.working_capital_turnover": "Vòng quay vốn lưu động",
    "metric.receivables_turnover": "Vòng quay khoản phải thu",
    "metric.inventory_turnover": "Vòng quay hàng tồn kho",
    "metric.total_credit_limit": "Tổng hạn mức đã cấp",
    "metric.total_outstanding_vnd": "Tổng dư nợ hiện tại",
    "metric.limit_utilization_ratio": "Tỷ lệ sử dụng hạn mức",
    "metric.relationship_years": "Số năm quan hệ tín dụng",
    "metric.cic_debt_group": "Nhóm nợ CIC",
    "metric.identity_match_score": "Điểm khớp định danh (CIC)",
    "metric.overdue_event_count": "Số lần quá hạn",
    "metric.group_total_exposure_vnd": "Tổng dư nợ nhóm liên quan",
    "metric.concentration_ratio": "Tỷ lệ tập trung nhóm liên quan",
    "metric.cross_guarantee_total_vnd": "Tổng bảo lãnh chéo",

    // ---- MessageTimeline ------------------------------------------------------
    "messageTimeline.title": "Giao tiếp giữa Orchestrator và agent",
    "messageTimeline.empty": "Không có mâu thuẫn cần hỏi lại — các agent đồng thuận.",
    "messageTimeline.roundLabel": "vòng",

    // ---- ScoringResultPanel -----------------------------------------------------
    "scoringResult.empty": "Chưa có khuyến nghị của AI — chạy phân tích AI trước.",
    "scoringResult.title": "Khuyến nghị của AI",
    "scoringResult.headline": "Hệ thống khuyến nghị: {recommendation} — dựa trên tổng hợp kết luận của 4 agent chuyên môn bên dưới, con người vẫn là người quyết định cuối cùng.",
    "scoringResult.compositeScore": "Điểm tổng hợp /100",
    "scoringResult.hardGatePass": "Hard gate PASS",
    "scoringResult.recommendedAmount": "Hạn mức đề xuất",
    "scoringResult.strengths": "Điểm mạnh",
    "scoringResult.risks": "Rủi ro",
    "scoringResult.dissent": "Dissent (chưa thống nhất)",
    "scoringResult.conditions": "Điều kiện / hành động cần thực hiện",

    // ---- ChatTab ------------------------------------------------------------
    "chat.loading": "Đang tải hội thoại...",
    "chat.emptyHint": "Hỏi agent bất kỳ điều gì về hồ sơ này — câu trả lời chỉ dựa trên dữ liệu case, không tự tính lại hay thực thi hành động.",
    "chat.inputPlaceholder": "Hỏi về hồ sơ này...",
    "chat.suggestion.dscr": "DSCR của khách hàng này là bao nhiêu?",
    "chat.suggestion.collateral": "Tài sản đảm bảo có đủ điều kiện giải ngân không?",
    "chat.suggestion.conflict": "Có mâu thuẫn nào giữa các agent chưa giải quyết?",
    "chat.suggestion.summary": "Tóm tắt kết luận tổng hợp cho hồ sơ này",

    // ---- CreditMemoPanel ------------------------------------------------------
    "creditMemo.title": "Credit Memo",
    "creditMemo.canGenerate": "Tạo bản tóm tắt hồ sơ từ kết luận AI để trình duyệt.",
    "creditMemo.cannotGenerate": "Cần có khuyến nghị của AI trước khi tạo Credit Memo.",
    "creditMemo.generating": "Đang tạo...",
    "creditMemo.generate": "Tạo Credit Memo",
    "creditMemo.preparedAt": "Soạn lúc {time}",

    // ---- ActionBar ------------------------------------------------------------
    "actionBar.title": "Hành động",
    "actionBar.memoRequired": "Cần tạo Credit Memo trước khi thực hiện hành động.",
    "actionBar.wrongState": "Hồ sơ đang ở trạng thái {state} — chỉ thực hiện được hành động khi hồ sơ ở trạng thái Sẵn sàng để duyệt (READY_FOR_REVIEW).",
    "actionBar.overAuthority": "Số tiền đề nghị ({amount}) vượt hạn mức demo ({limit}) — chỉ có thể chuyển lãnh đạo cấp trên, không tự phê duyệt.",
    "actionBar.action.return": "Trả RM bổ sung thông tin",
    "actionBar.action.reject": "Từ chối",
    "actionBar.action.accept": "Phê duyệt",
    "actionBar.action.escalate": "Chuyển hồ sơ lên lãnh đạo cấp trên",
    "actionBar.overrideButton": "Override cảnh báo hệ thống",
    "actionBar.note.return": "Lý do yêu cầu RM bổ sung...",
    "actionBar.note.reject": "Lý do từ chối hồ sơ (bắt buộc)...",
    "actionBar.note.accept": "Ghi chú khi phê duyệt (tuỳ chọn)...",
    "actionBar.note.escalate": "Lý do chuyển cấp trên (bắt buộc)...",
    "actionBar.note.override": "Lý do override cảnh báo hệ thống (bắt buộc, FR-11)...",

    // ---- ApprovalTimer --------------------------------------------------------
    "approvalTimer.resolved": "Thời gian xử lý",
    "approvalTimer.inProgress": "Đang xử lý",

    // ---- AnalyzingView --------------------------------------------------------
    "analyzing.title": "Đang phân tích hồ sơ...",
    "analyzing.starting": "Đang khởi động pipeline...",
    "analyzing.failed": "Pipeline lỗi: {error}",
    "analyzing.unknownError": "Lỗi không xác định",

    // ---- Agent labels (lib/agentMeta.ts) ---------------------------------------
    "agent.financial_analysis.label": "Financial Analysis Agent",
    "agent.financial_analysis.short": "Tài chính",
    "agent.policy_compliance.label": "Policy & Compliance Agent",
    "agent.policy_compliance.short": "Chính sách",
    "agent.collateral_legal.label": "Collateral & Legal Agent",
    "agent.collateral_legal.short": "TSBĐ & Pháp lý",
    "agent.customer_360.label": "Customer 360 & Credit History Agent",
    "agent.customer_360.short": "KH 360",
    "agent.plan.label": "Orchestrator — Lập kế hoạch",
    "agent.plan.short": "Lập kế hoạch",
    "agent.synthesize.label": "Decision Synthesis",
    "agent.synthesize.short": "Tổng hợp",

    // ---- ui.tsx chips -----------------------------------------------------
    "stance.SUPPORT": "Ủng hộ",
    "stance.CAUTION": "Cần lưu ý",
    "stance.OPPOSE": "Phản đối",
    "stance.NEED_DATA": "Thiếu dữ liệu",
    "rec.APPROVE": "Phê duyệt",
    "rec.APPROVE_WITH_CONDITIONS": "Phê duyệt có điều kiện",
    "rec.REFER": "Chuyển thẩm định thủ công",
    "rec.REJECT": "Từ chối",
    "rec.NEED_INFO": "Cần bổ sung hồ sơ",
    "state.DRAFT": "Nháp",
    "state.INTAKE_VALIDATION": "Kiểm tra hồ sơ",
    "state.NEED_INFO": "Cần bổ sung",
    "state.ANALYZING": "Đang phân tích",
    "state.CHALLENGE": "Đang phản biện",
    "state.READY_FOR_REVIEW": "Sẵn sàng duyệt",
    "state.SUBMITTED_FOR_APPROVAL": "Đã trình duyệt",
    "state.CONDITION_FULFILLMENT": "Hoàn thiện điều kiện",
    "state.READY_FOR_DISBURSEMENT": "Sẵn sàng giải ngân",
    "priority.urgent": "Khẩn cấp",
    "priority.high": "Ưu tiên",
    "priority.normal": "Thường",
    "confidence.label": "Độ tin cậy",

    // ---- Formatters ---------------------------------------------------------
    "fmt.billion": "tỷ VND",
    "fmt.million": "triệu VND",
    "fmt.minute": "phút",
    "fmt.hour": "giờ",
    "fmt.day": "ngày",
  },
  en: {
    "nav.appName": "SHBExpert AI",
    "nav.tagline": "AI credit-analysis expert team",
    "nav.dashboard": "Dashboard",
    "nav.applications": "Applications",
    "nav.tasks": "Tasks",
    "nav.documents": "Documents",
    "nav.reports": "Reports",
    "nav.auditTrail": "Audit Trail",
    "nav.settings": "Settings",
    "nav.comingSoon": "Coming soon",
    "nav.comingSoonTitle": "Page not available yet",
    "nav.officerName": "Nguyen Van A",
    "nav.officerRole": "Credit Officer",
    "nav.language": "Language",

    "common.cancel": "Cancel",
    "common.confirm": "Confirm",
    "common.loading": "Loading...",
    "common.noData": "—",

    "queue.title": "Applications pending credit review",
    "queue.subtitle": "The AI expert team analyzes in parallel, sorted by processing priority.",
    "queue.loading": "Loading application list...",

    "stats.pending": "Applications pending",
    "stats.urgent": "Urgent applications",
    "stats.avgApproval": "Average approval time",
    "stats.avgApprovalNote": "No resolved applications yet to compute an average",
    "stats.quality": "Approval quality",
    "stats.qualityNote": "Requires post-disbursement loan performance data (NPL) — not tracked by this system yet",

    "filter.allProducts": "All products",
    "filter.allAmounts": "All amounts",
    "filter.lt1b": "< 1bn",
    "filter.1to5b": "1 – 5bn",
    "filter.gt5b": "> 5bn",
    "filter.clear": "Clear filters",

    "queueList.empty": "No applications match the current filters.",
    "queueList.waitPrefix": "Waiting",
    "queueList.tenorSuffix": "months",

    "case.back": "Dashboard",
    "case.loading": "Loading case {id}...",
    "case.tenorLabel": "tenor",
    "case.tenorMonths": "months",
    "case.tab.overview": "Overview",
    "case.tab.scoring": "Preliminary Review & Scoring",
    "case.tab.chat": "Discussion & Conclusion",
    "case.rerun": "Re-run analysis",
    "case.staleTitle": "Only available while the case is READY_FOR_REVIEW (current: {state})",
    "case.freshNotice": "The application already has enough data — AI analysis hasn't run yet.",
    "case.startAnalyze": "Start AI review",
    "case.actionFailed": "Couldn't complete the action — the case state just changed, please reload the page. ({err})",

    "overview.customerInfo": "Customer basic information",
    "overview.legalName": "Legal entity name",
    "overview.taxCode": "Tax code",
    "overview.industry": "Industry",
    "overview.representative": "Legal representative",
    "overview.establishDate": "Establishment date",
    "overview.noIdentity": "No customer identity data yet (Customer 360 hasn't run for this case).",
    "overview.loanInfo": "Loan information",
    "overview.product": "Product",
    "overview.requestedAmount": "Requested amount",
    "overview.tenor": "Tenor",
    "overview.tenorMonths": "months",
    "overview.documents": "Required documents",
    "overview.incomeCollateral": "Income & Collateral",
    "overview.noFinancials": "No financial figures extracted yet.",
    "overview.collateralType": "Collateral type",
    "overview.collateralOwner": "Owner",
    "overview.field.revenue2025": "Net revenue (2025)",
    "overview.field.ebitda2025": "EBITDA (2025)",
    "overview.field.netProfitAfterTax": "Net profit after tax",
    "overview.field.valuationAmount": "Collateral valuation",

    "taskGraph.plan": "Planning",
    "taskGraph.planSubtitle": "Decompose the request, assign work to 4 expert agents",
    "taskGraph.parallelProgress": "Progress of the 4 expert agents, coordinated in parallel",
    "taskGraph.synthesize": "Synthesis",
    "taskGraph.synthesizeSubtitle": "Synthesize scorecard, hard gates, and the final recommendation",
    "taskGraph.status.pending": "Pending",
    "taskGraph.status.in_progress": "In progress",
    "taskGraph.status.done": "Done",
    "taskGraph.status.failed": "Failed",

    "agentTrace.waiting": "Waiting...",
    "agentTrace.metricsComputed": "Computed metrics ({n})",
    "agentTrace.policyBasis": "Policy/legal basis",
    "metric.dscr": "Debt Service Coverage (DSCR)",
    "metric.ebitda_margin": "EBITDA margin",
    "metric.coverage_ratio": "Collateral coverage ratio",
    "metric.cert_days_to_expiry": "Days until certificate expiry",
    "metric.haircut_rate": "Haircut rate",
    "metric.total_obligation_vnd": "Total debt obligation (VND)",
    "metric.net_cashflow": "Net cashflow",
    "metric.operating_cf_ratio": "Operating CF / revenue ratio",
    "metric.current_ratio": "Current ratio",
    "metric.quick_ratio": "Quick ratio",
    "metric.cash_ratio": "Cash ratio",
    "metric.roa": "ROA",
    "metric.roe": "ROE",
    "metric.debt_ratio": "Debt ratio",
    "metric.self_financing_ratio": "Self-financing ratio",
    "metric.net_working_capital": "Net working capital",
    "metric.working_capital_turnover": "Working capital turnover",
    "metric.receivables_turnover": "Receivables turnover",
    "metric.inventory_turnover": "Inventory turnover",
    "metric.total_credit_limit": "Total credit limit granted",
    "metric.total_outstanding_vnd": "Total current outstanding",
    "metric.limit_utilization_ratio": "Limit utilization ratio",
    "metric.relationship_years": "Years of credit relationship",
    "metric.cic_debt_group": "CIC debt group",
    "metric.identity_match_score": "Identity match score (CIC)",
    "metric.overdue_event_count": "Overdue event count",
    "metric.group_total_exposure_vnd": "Related-party group total exposure",
    "metric.concentration_ratio": "Related-party concentration ratio",
    "metric.cross_guarantee_total_vnd": "Total cross-guarantee",

    "messageTimeline.title": "Orchestrator ↔ agent communication",
    "messageTimeline.empty": "No conflicts requiring follow-up — agents are in agreement.",
    "messageTimeline.roundLabel": "round",

    "scoringResult.empty": "No AI recommendation yet — run the AI analysis first.",
    "scoringResult.title": "AI Recommendation",
    "scoringResult.headline": "The system recommends: {recommendation} — based on the synthesis of all 4 expert agents below; a human still makes the final call.",
    "scoringResult.compositeScore": "Composite score /100",
    "scoringResult.hardGatePass": "Hard gates PASS",
    "scoringResult.recommendedAmount": "Recommended limit",
    "scoringResult.strengths": "Strengths",
    "scoringResult.risks": "Risks",
    "scoringResult.dissent": "Dissent (unresolved)",
    "scoringResult.conditions": "Conditions / required actions",

    "chat.loading": "Loading conversation...",
    "chat.emptyHint": "Ask the agent anything about this case — answers are grounded only in case data, no recalculation or actions are executed.",
    "chat.inputPlaceholder": "Ask about this case...",
    "chat.suggestion.dscr": "What is this customer's DSCR?",
    "chat.suggestion.collateral": "Is the collateral eligible for disbursement?",
    "chat.suggestion.conflict": "Are there any unresolved conflicts between agents?",
    "chat.suggestion.summary": "Summarize the overall conclusion for this case",

    "creditMemo.title": "Credit Memo",
    "creditMemo.canGenerate": "Generate a case summary from the AI conclusion for submission.",
    "creditMemo.cannotGenerate": "An AI recommendation is required before generating a Credit Memo.",
    "creditMemo.generating": "Generating...",
    "creditMemo.generate": "Generate Credit Memo",
    "creditMemo.preparedAt": "Prepared at {time}",

    "actionBar.title": "Actions",
    "actionBar.memoRequired": "A Credit Memo must be generated before taking action.",
    "actionBar.wrongState": "This case is in state {state} — actions are only available while the case is Ready for review (READY_FOR_REVIEW).",
    "actionBar.overAuthority": "The requested amount ({amount}) exceeds the demo authority limit ({limit}) — this can only be escalated, not approved directly.",
    "actionBar.action.return": "Return to RM for more information",
    "actionBar.action.reject": "Reject",
    "actionBar.action.accept": "Approve",
    "actionBar.action.escalate": "Escalate to senior management",
    "actionBar.overrideButton": "Override system warning",
    "actionBar.note.return": "Reason for requesting more info from RM...",
    "actionBar.note.reject": "Reason for rejecting the case (required)...",
    "actionBar.note.accept": "Note when approving (optional)...",
    "actionBar.note.escalate": "Reason for escalating (required)...",
    "actionBar.note.override": "Reason for overriding the system warning (required, FR-11)...",

    "approvalTimer.resolved": "Processing time",
    "approvalTimer.inProgress": "In progress",

    "analyzing.title": "Analyzing the case...",
    "analyzing.starting": "Starting the pipeline...",
    "analyzing.failed": "Pipeline error: {error}",
    "analyzing.unknownError": "Unknown error",

    "agent.financial_analysis.label": "Financial Analysis Agent",
    "agent.financial_analysis.short": "Financial",
    "agent.policy_compliance.label": "Policy & Compliance Agent",
    "agent.policy_compliance.short": "Policy",
    "agent.collateral_legal.label": "Collateral & Legal Agent",
    "agent.collateral_legal.short": "Collateral & Legal",
    "agent.customer_360.label": "Customer 360 & Credit History Agent",
    "agent.customer_360.short": "Customer 360",
    "agent.plan.label": "Orchestrator — Planning",
    "agent.plan.short": "Planning",
    "agent.synthesize.label": "Decision Synthesis",
    "agent.synthesize.short": "Synthesis",

    "stance.SUPPORT": "Support",
    "stance.CAUTION": "Caution",
    "stance.OPPOSE": "Oppose",
    "stance.NEED_DATA": "Needs data",
    "rec.APPROVE": "Approve",
    "rec.APPROVE_WITH_CONDITIONS": "Approve with conditions",
    "rec.REFER": "Refer to manual review",
    "rec.REJECT": "Reject",
    "rec.NEED_INFO": "Needs more information",
    "state.DRAFT": "Draft",
    "state.INTAKE_VALIDATION": "Intake validation",
    "state.NEED_INFO": "Needs info",
    "state.ANALYZING": "Analyzing",
    "state.CHALLENGE": "Under challenge",
    "state.READY_FOR_REVIEW": "Ready for review",
    "state.SUBMITTED_FOR_APPROVAL": "Submitted for approval",
    "state.CONDITION_FULFILLMENT": "Fulfilling conditions",
    "state.READY_FOR_DISBURSEMENT": "Ready for disbursement",
    "priority.urgent": "Urgent",
    "priority.high": "High priority",
    "priority.normal": "Normal",
    "confidence.label": "Confidence",

    "fmt.billion": "bn VND",
    "fmt.million": "M VND",
    "fmt.minute": "min",
    "fmt.hour": "h",
    "fmt.day": "d",
  },
};

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? String(vars[key]) : match));
}

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("vi");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "vi" || stored === "en") setLangState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const template = messages[lang][key] ?? messages.vi[key] ?? key;
      return interpolate(template, vars);
    },
    [lang]
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n() must be used within <LanguageProvider>");
  return ctx;
}

/** Non-hook accessor for the rare spot (agentMeta.ts) that builds plain
 * data structures outside a component — looks up a key in the given
 * language without needing the Provider in scope. */
export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const template = messages[lang][key] ?? messages.vi[key] ?? key;
  return interpolate(template, vars);
}
