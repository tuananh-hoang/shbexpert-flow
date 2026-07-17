from pathlib import Path

from synthetic_data_pipeline.case import assemble_case, default_overlays
from synthetic_data_pipeline.core import PipelineConfig, build_master_data, validate_master_data
from synthetic_data_pipeline.io import export_master_data


def test_clean_master_data_reconciles() -> None:
    data = build_master_data(PipelineConfig(customer_count=6, seed=7))
    assert validate_master_data(data) == []
    assert len(data["industry"]) == 96
    assert all(row["synthetic_flag"] for row in data["customers"])


def test_case_mutation_keeps_master_clean() -> None:
    data = build_master_data(PipelineConfig(customer_count=6, seed=7))
    customer_id = data["customers"][0]["customer_id"]
    before = len([row for row in data["legal_documents"] if row["customer_id"] == customer_id])
    overlay = [row for row in default_overlays(data) if row["customer_id"] == customer_id]
    case = assemble_case(data, customer_id, overlay)
    assert len(case["legal_documents"]) == before - 1
    assert len([row for row in data["legal_documents"] if row["customer_id"] == customer_id]) == before


def test_export_writes_prd_views(tmp_path: Path) -> None:
    data = build_master_data(PipelineConfig(customer_count=3, seed=11))
    hashes = export_master_data(data, tmp_path, render_documents=True)
    assert (tmp_path / "customer_master.csv").exists()
    assert (tmp_path / "financial_statements.xlsx").exists()
    assert (tmp_path / "policy_rulebook.pdf").exists()
    assert len(list((tmp_path / "legal").glob("*.pdf"))) == 15
    assert "manifest.json" in hashes
