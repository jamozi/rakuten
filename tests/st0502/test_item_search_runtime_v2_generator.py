"""Owner-generator and sanitized official-source evidence checks for ST-0502 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import cast


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPOSITORY_ROOT / "scripts/build_st0502_item_search_runtime.py"
SOURCE_FACTS = (
    REPOSITORY_ROOT
    / "changes/st-0502/contracts/rakuten-item-search-official-source-facts.v2.json"
)
GENERATED = REPOSITORY_ROOT / "changes/st-0502/generated/item-search-runtime.v2.json"
MANIFEST = REPOSITORY_ROOT / "changes/st-0502/manifest.v2.json"


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return {
        cast(str, key): item for key, item in cast(dict[object, object], value).items()
    }


def test_official_source_record_contains_only_sanitized_facts_and_hash() -> None:
    facts = _object(SOURCE_FACTS)
    normalized = cast(dict[str, object], facts["normalized_facts"])

    assert facts["url"] == (
        "https://webservice.rakuten.co.jp/index.php/documentation/ichiba-item-search"
    )
    assert facts["fetched_at"] == "2026-08-24T16:43:55Z"
    assert facts["raw_response_sha256"] == (
        "063d5a861f2f8677efca7e772256a980a45eb931bcba403f287025847e42e4cb"
    )
    assert facts["raw_response_committed"] is False
    assert facts["raw_html_committed"] is False
    assert facts["api_test_material_committed"] is False
    assert facts["credential_or_sample_value_committed"] is False
    assert normalized["access_key_transport"] == (
        "HTTP_HEADER_SECRET_NAME_ONLY_FUTURE_BINDING"
    )
    assert "raw_html" not in facts
    assert "raw_response" not in facts
    assert "sample_application_id" not in facts
    assert "sample_access_key" not in facts


def test_generated_projection_has_only_closed_secret_name_bindings() -> None:
    generated = _object(GENERATED)
    api = cast(dict[str, object], generated["api"])
    bindings = cast(list[dict[str, object]], api["secret_name_bindings"])

    assert bindings == [
        {
            "provider_name": "accessKey",
            "required": True,
            "secret_name": "rakuten_web_service_access_key",
            "transport": "HEADER_SECRET_NAME_ONLY",
        },
        {
            "provider_name": "affiliateId",
            "required": False,
            "secret_name": "rakuten_affiliate_id",
            "transport": "QUERY_SECRET_NAME_ONLY",
        },
        {
            "provider_name": "applicationId",
            "required": True,
            "secret_name": "rakuten_web_service_application_id",
            "transport": "QUERY_SECRET_NAME_ONLY",
        },
    ]
    assert generated["external_actions"] == []
    assert (
        cast(dict[str, object], generated["provider_boundary"])[
            "live_http_mode_representable"
        ]
        is False
    )
    assert cast(dict[str, object], generated["formal_evidence"])["TST-014"] == (
        "NOT_EXECUTED"
    )
    assert cast(dict[str, object], generated["formal_evidence"])["TST-015"] == (
        "NOT_EXECUTED"
    )


def test_manifest_hashes_generated_output_and_all_sources() -> None:
    manifest = _object(MANIFEST)
    sources = cast(dict[str, object], manifest["source_sha256"])
    generated = cast(dict[str, object], manifest["generated_sha256"])

    assert (
        generated[str(GENERATED.relative_to(REPOSITORY_ROOT))]
        == hashlib.sha256(GENERATED.read_bytes()).hexdigest()
    )
    assert str(GENERATOR.relative_to(REPOSITORY_ROOT)) in sources
    assert str(SOURCE_FACTS.relative_to(REPOSITORY_ROOT)) in sources
    assert all(type(digest) is str and len(digest) == 64 for digest in sources.values())
    assert manifest["raw_official_response_committed"] is False
    assert manifest["credential_or_sample_value_committed"] is False
    assert manifest["formal_evidence"] == "NOT_EXECUTED"
    assert manifest["live_provider"] == "NOT_EXECUTED"
    assert manifest["production"] == "NOT_EXECUTED"


def test_owner_generator_check_is_deterministic_and_no_write() -> None:
    before = {
        path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in (GENERATED, MANIFEST)
    }
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    after = {
        path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in (GENERATED, MANIFEST)
    }

    assert completed.returncode == 0
    assert completed.stdout == completed.stderr == ""
    assert after == before
