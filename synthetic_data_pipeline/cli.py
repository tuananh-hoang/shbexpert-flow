from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .case import assemble_case, default_overlays, export_case
from .core import PipelineConfig, build_master_data, validate_master_data
from .io import export_master_data, write_json
from .narrative import ProviderConfig, enrich_narratives
from .references import sync_reference_snapshots


def _config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(args.customers, args.seed, date.fromisoformat(args.as_of_date))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mockdata", description="Dataset-first synthetic banking pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in [("build", "generate clean master datasets"), ("validate", "validate master datasets"), ("mutate", "write mutation overlays"), ("assemble", "assemble one case from frozen-style master data"), ("enrich-narratives", "enrich non-authoritative narrative fields through FPT AI Factory"), ("refs-sync", "freeze whitelisted public reference snapshots")]:
        command = commands.add_parser(name, help=description)
        command.add_argument("--customers", type=int, default=120)
        command.add_argument("--seed", type=int, default=20260718)
        command.add_argument("--as-of-date", default="2026-06-30")
    commands.choices["build"].add_argument("--output", type=Path, default=Path("artifacts/master"))
    commands.choices["mutate"].add_argument("--output", type=Path, default=Path("artifacts/mutations.json"))
    commands.choices["assemble"].add_argument("customer_id")
    commands.choices["assemble"].add_argument("--output", type=Path, default=Path("artifacts/cases"))
    commands.choices["assemble"].add_argument("--mutation-file", type=Path)
    commands.choices["enrich-narratives"].add_argument("--limit", type=int, default=3)
    commands.choices["enrich-narratives"].add_argument("--output", type=Path, default=Path("artifacts/narrative_enrichment.json"))
    commands.choices["refs-sync"].add_argument("--output", type=Path, default=Path("artifacts/reference_snapshots"))
    args = parser.parse_args(argv)
    if args.command == "refs-sync":
        manifest = sync_reference_snapshots(args.output)
        failed = [row["source_id"] for row in manifest["sources"] if row["status"] == "failed"]
        print(json.dumps({"output": str(args.output), "fetched": sum(row["status"] == "fetched" for row in manifest["sources"]), "failed": failed}))
        return 1 if failed else 0
    data = build_master_data(_config(args))
    errors = validate_master_data(data)
    if errors:
        parser.error("validation failed:\n" + "\n".join(errors))
    if args.command == "build":
        hashes = export_master_data(data, args.output)
        print(json.dumps({"validation": "passed", "output": str(args.output), "artifact_count": len(hashes)}))
    elif args.command == "validate":
        print(json.dumps({"validation": "passed", "customers": len(data["customers"])}))
    elif args.command == "mutate":
        overlays = default_overlays(data)
        write_json(args.output, overlays)
        print(json.dumps({"output": str(args.output), "overlay_count": len(overlays)}))
    elif args.command == "assemble":
        overlays = []
        if args.mutation_file:
            overlays = [row for row in json.loads(args.mutation_file.read_text(encoding="utf-8")) if row["customer_id"] == args.customer_id]
        case = assemble_case(data, args.customer_id, overlays)
        export_case(case, args.output)
        print(json.dumps({"case_id": case["case_id"], "mutations": case["applied_mutations"]}))
    else:
        provider = ProviderConfig.from_env()
        records = enrich_narratives(data, min(args.limit, len(data["customers"])), provider)
        write_json(args.output, records)
        print(json.dumps({"output": str(args.output), "records": len(records), "provider": "FPT_AI_FACTORY", "model": provider.model}))
    return 0
