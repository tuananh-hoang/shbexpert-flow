"""Smoke test — Phase 3 new tools: calculate_coverage (mcp-deterministic)
and get_valuation (mcp-external), via the real MCP wire.
"""
import asyncio
import json

from langchain_mcp_adapters.client import MultiServerMCPClient

SERVERS = {
    "deterministic": {"url": "http://mcp-deterministic:8200/mcp", "transport": "streamable_http"},
    "external": {"url": "http://mcp-external:8202/mcp", "transport": "streamable_http"},
}


def unwrap(result):
    return json.loads(result[0]["text"]) if isinstance(result, list) else result


async def main() -> None:
    client = MultiServerMCPClient(SERVERS)
    tools = {t.name: t for t in await client.get_tools()}

    coverage = unwrap(
        await tools["calculate_coverage"].ainvoke({"eligible_value": 10_000_000_000, "requested_amount": 8_000_000_000})
    )
    print("calculate_coverage:", coverage)
    assert coverage["outputs"]["coverage_ratio"] == 1.25

    valuation = unwrap(await tools["get_valuation"].ainvoke({"collateral_id": "C06"}))
    print("get_valuation:", valuation)
    assert valuation["official_value_vnd"] == 9_500_000_000

    print("\nPHASE 3 NEW-TOOL SMOKE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
