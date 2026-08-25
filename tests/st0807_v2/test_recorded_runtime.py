from __future__ import annotations

# pyright: reportPrivateUsage=false

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture
from raos.domain.editorial.policy_engine_v2 import evaluate_editorial_policy_v2
from raos.domain.editorial.seo_renderer import ExternalCheck
from scripts import build_st0807_seo_render_runtime as generator


def _canonical_json(value: object) -> str:
    serialized = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _schema_types(value: object) -> tuple[str, ...]:
    found: list[str] = []

    def visit(item: object) -> None:
        if type(item) is dict:
            for key, child in cast(dict[object, object], item).items():
                if key == "@type" and type(child) is str:
                    found.append(child)
                else:
                    visit(child)
        elif type(item) is list:
            for child in cast(list[object], item):
                visit(child)

    visit(value)
    return tuple(found)


def test_recorded_result_is_exactly_recomputed_and_generated(
    result_document: dict[str, object],
    generated_document: dict[str, Any],
) -> None:
    assert generated_document == result_document
    dependency = generated_document["dependency"]
    fixture = (generator.REPO_ROOT / generator.POLICY_FIXTURE_PATH).read_bytes()
    envelope = load_recorded_policy_fixture(fixture)
    report = evaluate_editorial_policy_v2(envelope)
    report.require_valid()

    assert dependency == {
        "st0802_article_id": "018f3e90-7b00-7000-8000-000000000805",
        "st0802_article_version_id": "018f3e90-7b00-7000-8000-000000000806",
        "st0802_body_sha256": (
            "4c9bf36fac581e746126668ef8b36a27ea8e1acc0dc18bf9fc76c3af274311b9"
        ),
        "st0802_published_at": None,
        "st0802_state": "DRAFT",
        "st0805_evaluation_input_sha256": (
            "d4376e4554da70e821a575344ee8a25262178b749e4c243feb88c2d12ec041f5"
        ),
        "st0805_fixture_sha256": generator.ST0805_FIXTURE_SHA256,
        "st0805_local_eligibility": True,
        "st0805_report_sha256": (
            "4222b076411f165967b5802f5b2057fc8635c0f0e94aadf6bcd7462e9ffa4fec"
        ),
        "st0805_status": "LOCAL_EVALUATED",
    }
    assert dependency["st0805_report_sha256"] == report.report_sha256.value
    assert envelope.draft.snapshot.published_at is None
    assert (
        generated_document["render_date_semantics"]
        == "SYNTHETIC_PREVIEW_INPUT_NOT_PUBLICATION_FACT"
    )
    assert report.evaluation_input_sha256 is not None
    assert (
        dependency["st0805_evaluation_input_sha256"]
        == report.evaluation_input_sha256.value
    )
    render = generated_document["render"]
    assert render["visible"]["title"] == envelope.draft.snapshot.title
    assert render["visible"]["article_version_id"].casefold() == str(
        envelope.draft.snapshot.version_id
    )


def test_only_st0805_is_pass_and_every_external_fact_stays_not_evaluated(
    generated_document: dict[str, Any],
) -> None:
    assessments = generated_document["render"]["external_assessments"]
    by_check = {item["check"]: item for item in assessments}
    assert tuple(by_check) == tuple(item.value for item in ExternalCheck)
    assert by_check["ST_0805_POLICY_ELIGIBILITY"] == {
        "article_version_id": "018F3E90-7B00-7000-8000-000000000806",
        "assessor_ref": "ASSESSOR-ST0805-POLICY-ENGINE-V2",
        "check": "ST_0805_POLICY_ELIGIBILITY",
        "evidence": {
            "ref": "EVIDENCE-ST0805-POLICY-REPORT-V2",
            "sha256": generated_document["dependency"]["st0805_report_sha256"],
        },
        "state": "PASS",
    }
    assert all(
        item["state"] == "NOT_EVALUATED" and item["evidence"] is None
        for key, item in by_check.items()
        if key != "ST_0805_POLICY_ELIGIBILITY"
    )


def test_route_only_preview_is_noindex_and_never_conditionally_eligible(
    generated_document: dict[str, Any],
) -> None:
    render = generated_document["render"]
    metadata = render["rendered_metadata"]
    assert render["status"] == "RENDERED_LOCAL"
    assert render["mode"] == "PREVIEW"
    assert render["origin_mode"] == "ROUTE_ONLY"
    assert render["caller_origin"] is None
    assert render["site_projection"] is None
    assert render["conditional_local_eligibility"] is False
    assert render["eligibility_reasons"] == [
        "ROUTE_ONLY_ORIGIN_UNAVAILABLE",
        "PREVIEW_NOINDEX",
        "EXTERNAL_ASSESSMENT_NOT_EVALUATED",
    ]
    assert metadata["canonical_url"] is None
    assert metadata["index_state"] == "noindex"
    assert metadata["robots"] == ["noindex", "nofollow"]
    assert metadata["sitemap_inclusion"] is False


def test_jsonld_is_visible_bound_article_only_without_prohibited_types(
    generated_document: dict[str, Any],
) -> None:
    render = generated_document["render"]
    jsonld = json.loads(render["jsonld_json"])
    graph = jsonld["@graph"]
    article = graph[0]
    visible = render["visible"]

    assert _schema_types(jsonld) == ("Article", "Organization")
    assert not {
        "Product",
        "Offer",
        "Review",
        "AggregateRating",
        "FAQPage",
    }.intersection(_schema_types(jsonld))
    assert article["headline"] == visible["title"] == visible["h1"]
    assert article["author"] == {
        "@type": visible["author"]["kind"],
        "name": visible["author"]["display_name"],
    }
    assert article["datePublished"] == visible["date_published"]
    assert article["dateModified"] == visible["date_modified"]
    assert "url" not in article
    assert "mainEntityOfPage" not in article
    assert render["manifest"]["validation_result"] == "pass"
    assert render["manifest"]["visible_content_hash"] == visible["visible_content_hash"]


def test_result_hashes_and_authority_are_exact_and_deterministic(
    generated_document: dict[str, Any],
) -> None:
    render_json = _canonical_json(generated_document["render"])
    assert (
        generated_document["render_local_result_sha256"]
        == hashlib.sha256(render_json.encode("utf-8")).hexdigest()
    )
    jsonld = generated_document["render"]["jsonld_json"]
    assert (
        generated_document["jsonld_sha256"]
        == hashlib.sha256(jsonld.encode("utf-8")).hexdigest()
    )
    assert set(generated_document["authority"].values()) == {False}
    assert set(generated_document["verification"].values()) == {"NOT_EXECUTED"}
    assert set(generated_document["render"]["authority"].values()) == {
        False,
        "NONE",
        "NOT_EXECUTED",
    }


def test_tampered_st0805_fixture_is_rejected_before_decode(
    contract: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generator._read_regular

    def tampered_read(
        root: Path,
        relative: Path,
        *,
        maximum_bytes: int = generator.MAXIMUM_SOURCE_BYTES,
    ) -> bytes:
        payload = original(root, relative, maximum_bytes=maximum_bytes)
        if relative == generator.POLICY_FIXTURE_PATH:
            return payload + b" "
        return payload

    monkeypatch.setattr(generator, "_read_regular", tampered_read)
    with pytest.raises(generator.SeoRuntimeBuildError) as caught:
        generator._result_document(generator.REPO_ROOT, contract)
    assert caught.value.code == "ST0805_FIXTURE_HASH_DRIFT"
