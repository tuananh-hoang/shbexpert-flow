from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


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


def export_master_data(data: dict[str, Any], output: Path) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", data["manifest"])
    write_json(output / "customer_master.json", data["customers"])
    write_csv(output / "customer_master.csv", data["customers"])
    write_json(output / "credit_applications.json", data["applications"])
    write_json(output / "legal_documents.json", data["legal_documents"])
    write_jsonl(output / "legal_documents.jsonl", data["legal_documents"])
    write_json(output / "financial_statements.json", data["financials"])
    write_jsonl(output / "financial_statements.jsonl", data["financials"])
    write_xlsx(output / "financial_statements.xlsx", data["financials"])
    write_csv(output / "account_transactions.csv", data["transactions"])
    write_json(output / "cic_mock.json", data["cic_reports"])
    write_json(output / "kyc_aml_mock.json", data["kyc_screenings"])
    write_json(output / "collateral.json", data["collateral"])
    write_jsonl(output / "collateral.jsonl", data["collateral"])
    write_json(output / "shb_relationship.json", data["relationships"])
    write_csv(output / "shb_relationship.csv", data["relationships"])
    write_json(output / "policy_rulebook.json", data["policies"])
    write_jsonl(output / "policy_rulebook.jsonl", data["policies"])
    policy_md = "# Mock Policy Rulebook\n\nSYNTHETIC — FOR HACKATHON ONLY\n\n" + "\n".join(f"- {p['policy_id']}" for p in data["policies"])
    (output / "policy_rulebook.md").write_text(policy_md, encoding="utf-8")
    write_csv(output / "industry_data.csv", data["industry"])
    (output / "industry_data.md").write_text("# Synthetic Industry Data\n\nSee `industry_data.csv`.\n", encoding="utf-8")
    hashes = {str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob("*") if path.is_file()}
    write_json(output / "artifact_hashes.json", hashes)
    return hashes
