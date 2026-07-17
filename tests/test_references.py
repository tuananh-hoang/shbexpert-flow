from synthetic_data_pipeline.references import REFERENCE_SOURCES


def test_reference_sources_are_whitelisted_https() -> None:
    assert len(REFERENCE_SOURCES) == 4
    assert all(source["url"].startswith("https://") for source in REFERENCE_SOURCES)
    assert len({source["source_id"] for source in REFERENCE_SOURCES}) == len(REFERENCE_SOURCES)
