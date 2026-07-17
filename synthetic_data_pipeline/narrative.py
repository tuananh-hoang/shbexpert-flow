from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .core import INDUSTRIES

NARRATIVE_FIELDS = (
    "business_description",
    "rm_note",
    "financial_note",
    "collateral_description",
)


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 60
    max_output_tokens: int = 600

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        load_dotenv()
        api_key = os.getenv("FPT_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("FPT_API_KEY is missing from the environment or .env")
        return cls(
            api_key=api_key,
            base_url=os.getenv("FPT_BASE_URL", "https://mkp-api.fptcloud.com").rstrip("/"),
            model=os.getenv("FPT_MODEL", "Llama-3.3-70B-Instruct"),
            timeout_seconds=float(os.getenv("FPT_TIMEOUT_SECONDS", "60")),
            max_output_tokens=int(os.getenv("FPT_MAX_OUTPUT_TOKENS", "600")),
        )


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Provider response does not contain a JSON object")
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Provider response must be a JSON object")
    return payload


def validate_narrative_payload(payload: dict[str, Any]) -> dict[str, str]:
    if set(payload) != set(NARRATIVE_FIELDS):
        raise ValueError(f"Narrative keys must be exactly: {', '.join(NARRATIVE_FIELDS)}")
    normalized: dict[str, str] = {}
    for field in NARRATIVE_FIELDS:
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        if re.search(r"\d", value):
            raise ValueError(f"{field} introduced a numeric token")
        if re.search(r"\b(?:CUS|APP|COL|MOCK|FIN|CIC|POLICY)-", value, re.IGNORECASE):
            raise ValueError(f"{field} introduced an identifier or policy reference")
        normalized[field] = value.strip()
    return normalized


def _prompt_for_customer(data: dict[str, Any], customer_id: str) -> tuple[str, list[str]]:
    customer = next(row for row in data["customers"] if row["customer_id"] == customer_id)
    application = next(row for row in data["applications"] if row["customer_id"] == customer_id)
    relationship = next(row for row in data["relationships"] if row["customer_id"] == customer_id)
    collateral = next(row for row in data["collateral"] if row["application_id"] == application["application_id"])
    latest = next(row for row in data["financials"] if row["customer_id"] == customer_id and row["period"] == "2026-H1")
    facts = {
        "business_sector": next(name for code, name in INDUSTRIES if code == customer["industry_code"]),
        "purpose": application["purpose_code"],
        "repayment_source": application["repayment_source"],
        "profitability": "positive" if latest["net_profit"] > 0 else "negative",
        "relationship_status": "no_past_due" if relationship["past_due"] == 0 else "has_past_due",
        "collateral_type": collateral["property_type"],
        "encumbrance_status": collateral["encumbrance_status"],
    }
    fact_ids = [
        f"FACT-{customer_id}-INDUSTRY",
        f"FACT-{customer_id}-PURPOSE",
        f"FACT-{customer_id}-PROFITABILITY",
        f"FACT-{customer_id}-RELATIONSHIP",
        f"FACT-{customer_id}-COLLATERAL",
    ]
    prompt = (
        "Viết bốn đoạn mô tả ngắn bằng tiếng Việt tự nhiên cho một hồ sơ tín dụng doanh nghiệp hoàn toàn giả lập. "
        "Chỉ diễn đạt lại facts được cung cấp. Không thêm suy đoán, con số, ngày tháng, tên riêng, mã định danh, "
        "ngưỡng chính sách hay kết luận phê duyệt. Trả về duy nhất JSON hợp lệ với đúng bốn khóa: "
        "business_description, rm_note, financial_note, collateral_description. Mỗi giá trị là một chuỗi, không dùng markdown.\n"
        f"FACTS={json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )
    return prompt, fact_ids


def enrich_narratives(data: dict[str, Any], limit: int, config: ProviderConfig | None = None) -> list[dict[str, Any]]:
    provider = config or ProviderConfig.from_env()
    client = OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=provider.timeout_seconds)
    records: list[dict[str, Any]] = []
    for customer in data["customers"][:limit]:
        prompt, fact_ids = _prompt_for_customer(data, customer["customer_id"])
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        last_error: Exception | None = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model=provider.model,
                    messages=[
                        {"role": "system", "content": "Bạn là biên tập viên dữ liệu synthetic cho nghiệp vụ ngân hàng. Tuân thủ chặt schema và không tạo fact mới."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=provider.max_output_tokens,
                    stream=False,
                )
                content = response.choices[0].message.content or ""
                narrative = validate_narrative_payload(_parse_json_content(content))
                usage = getattr(response, "usage", None)
                records.append(
                    {
                        "customer_id": customer["customer_id"],
                        **narrative,
                        "asserted_fact_ids": fact_ids,
                        "generation_provenance": {
                            "provider": "FPT_AI_FACTORY",
                            "base_url": provider.base_url,
                            "model": provider.model,
                            "prompt_hash": prompt_hash,
                            "attempt": attempt + 1,
                            "latency_ms": round((time.perf_counter() - started) * 1000),
                            "input_tokens": getattr(usage, "prompt_tokens", None),
                            "output_tokens": getattr(usage, "completion_tokens", None),
                        },
                    }
                )
                break
            except Exception as exc:
                last_error = exc
        else:
            raise RuntimeError(f"Narrative enrichment failed for {customer['customer_id']} after two attempts: {last_error}") from last_error
    return records
