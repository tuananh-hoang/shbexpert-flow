"use client";

/**
 * "Tổng quan" tab — ported from the prototype's OverviewTab.tsx (3-column
 * grid: customer identity / loan request / income & collateral), rewired
 * to real fields from GET /cases/{id} (api/app/routers/cases.py::_case_identity).
 *
 * Fields the prototype's mock CreditCase has but this backend doesn't
 * (loan `purpose`, `disbursementMethod`, monthly-granularity income,
 * `segment`) are simply omitted — never fabricated. `identity`/
 * `collateral_summary` are null whenever the case's customer/collateral
 * was never seeded into those domain tables; the section renders an
 * honest "chưa có dữ liệu" note instead of blank fields in that case.
 */
import { Banknote, Building2, FileCheck2, FileX2, Landmark } from "lucide-react";
import type { CaseDetail } from "../lib/types";
import { Card, SectionTitle, formatVnd } from "./ui";
import { useI18n } from "../lib/i18n";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs" style={{ color: "var(--text-muted-2)" }}>
        {label}
      </div>
      <div className="text-sm" style={{ color: "var(--text-primary)" }}>
        {value ?? "—"}
      </div>
    </div>
  );
}

const INCOME_FIELD_KEY: Record<string, string> = {
  revenue_2025: "overview.field.revenue2025",
  ebitda_2025: "overview.field.ebitda2025",
  net_profit_after_tax: "overview.field.netProfitAfterTax",
  valuation_amount: "overview.field.valuationAmount",
};

function incomeFieldValue(value: Record<string, unknown>, lang: "vi" | "en"): string {
  if (typeof value.amount_vnd === "number") return formatVnd(value.amount_vnd, lang);
  return JSON.stringify(value);
}

export function OverviewTab({
  caseDetail,
  onOpenEvidence,
}: {
  caseDetail: CaseDetail;
  onOpenEvidence: (evidenceId: string) => void;
}) {
  const { t, lang } = useI18n();
  const { identity, collateral_summary: collateral, income_evidence: income, requested_facility: facility } = caseDetail;

  const presentDocTypes = new Set(caseDetail.documents.map((d) => d.doc_type));

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="space-y-3 p-4">
        <SectionTitle>
          <span className="flex items-center gap-1.5">
            <Building2 size={14} /> {t("overview.customerInfo")}
          </span>
        </SectionTitle>
        {identity ? (
          <>
            <Field label={t("overview.legalName")} value={identity.customer_name} />
            <Field label={t("overview.taxCode")} value={identity.tax_code} />
            <Field label={t("overview.industry")} value={identity.industry_code} />
            <Field
              label={t("overview.representative")}
              value={identity.representative_name ? `${identity.representative_name} — ${identity.representative_role ?? ""}` : null}
            />
            <Field label={t("overview.establishDate")} value={identity.establish_date?.slice(0, 10)} />
          </>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
            {t("overview.noIdentity")}
          </p>
        )}
      </Card>

      <Card className="space-y-3 p-4">
        <SectionTitle>
          <span className="flex items-center gap-1.5">
            <Banknote size={14} /> {t("overview.loanInfo")}
          </span>
        </SectionTitle>
        <Field label={t("overview.product")} value={caseDetail.product} />
        <Field label={t("overview.requestedAmount")} value={formatVnd(facility.amount_vnd as number, lang)} />
        <Field label={t("overview.tenor")} value={facility.tenor_months ? `${facility.tenor_months} ${t("overview.tenorMonths")}` : null} />
        <div>
          <div className="mb-1 text-xs" style={{ color: "var(--text-muted-2)" }}>
            {t("overview.documents")}
          </div>
          <ul className="space-y-1">
            {caseDetail.required_doc_types.map((docType) => {
              const present = presentDocTypes.has(docType);
              return (
                <li key={docType} className="flex items-center gap-1.5 text-sm">
                  {present ? (
                    <FileCheck2 size={14} style={{ color: "var(--status-good)" }} />
                  ) : (
                    <FileX2 size={14} style={{ color: "var(--status-critical)" }} />
                  )}
                  {docType}
                </li>
              );
            })}
          </ul>
        </div>
      </Card>

      <Card className="space-y-3 p-4">
        <SectionTitle>
          <span className="flex items-center gap-1.5">
            <Landmark size={14} /> {t("overview.incomeCollateral")}
          </span>
        </SectionTitle>
        {income.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted-2)" }}>
            {t("overview.noFinancials")}
          </p>
        ) : (
          income.map((item) => (
            <button
              key={item.field_key}
              onClick={() => onOpenEvidence(item.evidence_id)}
              className="block w-full text-left"
            >
              <Field
                label={INCOME_FIELD_KEY[item.field_key] ? t(INCOME_FIELD_KEY[item.field_key]) : item.field_key}
                value={
                  <span className="underline" style={{ color: "var(--brand)" }}>
                    {incomeFieldValue(item.value, lang)}
                  </span>
                }
              />
            </button>
          ))
        )}
        {collateral && (
          <div className="border-t pt-3" style={{ borderColor: "var(--border-hairline)" }}>
            <Field label={t("overview.collateralType")} value={collateral.collateral_type} />
            <Field label={t("overview.collateralOwner")} value={collateral.owner_name} />
          </div>
        )}
      </Card>
    </div>
  );
}
