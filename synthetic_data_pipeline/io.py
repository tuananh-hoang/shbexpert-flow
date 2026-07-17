from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "Financials"
    if rows:
        keys = list(rows[0])
        sheet.append(keys)
        for row in rows:
            sheet.append([row.get(key) for key in keys])
        sheet.freeze_panes = "A2"
    book.save(path)


def write_pdf(path: Path, title: str, lines: list[str]) -> None:
    """Small valid PDF writer used for synthetic mock documents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    def escape(value: str) -> str:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    commands = ["BT", "/F1 10 Tf", "50 780 Td"]
    for index, text in enumerate([title, "SYNTHETIC DATA - NOT A CREDIT DECISION", *lines]):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({escape(str(text)[:110])}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(result)


def export_master_data(data: dict[str, Any], output: Path, render_documents: bool = False) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", data["manifest"])
    write_json(output / "customer_master.json", data["customers"])
    write_csv(output / "customer_master.csv", data["customers"])
    write_json(output / "credit_applications.json", data["applications"])
    write_json(output / "legal_documents.json", data["legal_documents"])
    write_json(output / "financial_statements.json", data["financials"])
    write_xlsx(output / "financial_statements.xlsx", data["financials"])
    write_csv(output / "account_transactions.csv", data["transactions"])
    write_json(output / "cic_mock.json", data["cic_reports"])
    write_json(output / "kyc_aml_mock.json", data["kyc_screenings"])
    write_json(output / "collateral.json", data["collateral"])
    write_json(output / "shb_relationship.json", data["relationships"])
    write_csv(output / "shb_relationship.csv", data["relationships"])
    write_json(output / "policy_rulebook.json", data["policies"])
    policy_md = "# Mock Policy Rulebook\n\nSYNTHETIC — FOR HACKATHON ONLY\n\n" + "\n".join(f"- {p['policy_id']}" for p in data["policies"])
    (output / "policy_rulebook.md").write_text(policy_md, encoding="utf-8")
    write_pdf(output / "policy_rulebook.pdf", "Mock Policy Rulebook", [p["policy_id"] for p in data["policies"]])
    write_csv(output / "industry_data.csv", data["industry"])
    (output / "industry_data.md").write_text("# Synthetic Industry Data\n\nSee `industry_data.csv`.\n", encoding="utf-8")
    if render_documents:
        for document in data["legal_documents"]:
            fields = document["canonical_fields"]
            write_pdf(output / "legal" / f"{document['document_id']}.pdf", document["document_type"], [
                f"Document ID: {document['document_id']}", f"Customer: {fields['legal_name']}", f"Tax ID: {fields['mock_tax_id']}", f"Issued: {document['issued_at']}"])
        for row in data["collateral"]:
            write_pdf(output / "collateral" / f"{row['collateral_id']}.pdf", "Mock Collateral Valuation", [
                f"Collateral: {row['collateral_id']}", f"Value: {row['valuation_amount']}", f"Haircut: {row['haircut_rate']}"])
    hashes = {str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob("*") if path.is_file()}
    write_json(output / "artifact_hashes.json", hashes)
    return hashes
