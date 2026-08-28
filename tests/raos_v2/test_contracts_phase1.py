"""Versioned schema, IA and design-system checks for Phase 1."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
import yaml

from scripts import build_raos_v2_successor as builder
from scripts import validate_raos_v2_successor as successor_validator


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts/raos-v2/v1"


def schema(name: str) -> dict[str, object]:
    value = json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def errors(name: str, value: object) -> list[object]:
    return list(
        Draft202012Validator(schema(name), format_checker=FormatChecker()).iter_errors(
            value
        )
    )


def base_claim(claim_type: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "claim_id": "CLM-TEST-1",
        "claim_type": claim_type,
        "subject_id": "SUBJECT",
        "predicate": "external_dimensions",
        "value": "55",
        "unit": "cm",
        "source_ids": ["SRC-TEST-1"],
        "logic_inputs": [],
        "checked_at": "2026-08-28T00:00:00+09:00",
        "next_review_at": "2026-09-28T00:00:00+09:00",
        "risk_class": "MEDIUM",
        "status": "VERIFIED",
    }


def test_all_ten_entity_schemas_are_valid_and_closed() -> None:
    paths = sorted(CONTRACTS.glob("*.schema.json"))
    assert len(paths) == 10
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
        assert value["additionalProperties"] is False


def test_claim_contract_allows_only_a_d_unknown_and_enforces_null_rules() -> None:
    official = base_claim("A_OFFICIAL_FACT")
    assert not errors("claim", official)
    unsupported = {**official, "source_ids": []}
    assert errors("claim", unsupported)
    judgement = {**official, "claim_type": "D_EDITORIAL_JUDGEMENT", "logic_inputs": []}
    assert errors("claim", judgement)
    unknown = {
        **official,
        "claim_type": "UNKNOWN",
        "value": None,
        "unit": None,
        "source_ids": [],
        "status": "BLOCKED",
    }
    assert not errors("claim", unknown)
    assert errors("claim", {**unknown, "value": "invented"})
    assert errors("claim", {**official, "claim_type": "B_DERIVED_FACT"})
    malformed_logic = {
        **official,
        "claim_type": "D_EDITORIAL_JUDGEMENT",
        "logic_inputs": [
            {
                "input_id": "RULE_INPUT",
                "value_ref": "SRC-TEST-1",
                "free_text": "x",
            }
        ],
    }
    assert errors("claim", malformed_logic)


def test_product_variant_requires_exact_decimal_strings_and_orientation() -> None:
    value = {
        "schema_version": "1.0.0",
        "variant_id": "06316-NORMAL",
        "external_dimensions_cm": {
            "edges_cm": ["55", "35", "25"],
            "orientation": "ORDERED",
            "includes_wheels_and_handles": True,
        },
        "expanded_dimensions_cm": None,
        "mass_kg": "3.2",
        "capacity_l": "34",
        "expanded_capacity_l": "39",
        "declared_features": [],
        "unknown_fields": [],
    }
    assert not errors("product-variant", value)
    assert errors(
        "product-variant",
        {**value, "mass_kg": 3.2},
    )
    changed = json.loads(json.dumps(value))
    changed["external_dimensions_cm"]["orientation"] = "GUESSED"
    assert errors("product-variant", changed)
    changed = deepcopy(value)
    changed["external_dimensions_cm"]["edges_cm"][0] = "0"
    assert errors("product-variant", changed)


def test_recorded_airline_rules_require_positive_limits_and_semantic_dates() -> None:
    envelope = json.loads(
        (
            ROOT / "changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"
        ).read_text(encoding="utf-8")
    )
    values = envelope["rule_sets"]
    contract = Draft202012Validator(
        schema("airline-rule-set"), format_checker=FormatChecker()
    )
    assert all(not list(contract.iter_errors(value)) for value in values)
    invalid = deepcopy(values[0])
    invalid["variants"][0]["dimension_edges_cm"][0] = "0"
    assert list(contract.iter_errors(invalid))
    invalid = deepcopy(values[0])
    invalid["variants"][0]["applicability"]["min_seat_count"] = 0
    assert list(contract.iter_errors(invalid))
    invalid = deepcopy(values[0])
    invalid["effective_from"] = "2026-02-31"
    assert list(contract.iter_errors(invalid))


def test_recorded_offer_identifiers_are_bounded_and_refs_are_opaque() -> None:
    envelope = json.loads(
        (
            ROOT
            / "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
        ).read_text(encoding="utf-8")
    )
    value = envelope["offers"][0]["offer_observation"]
    assert not errors("offer-observation", value)
    assert errors(
        "offer-observation",
        {**value, "affiliate_url_ref": "https://example.invalid/?credential=x"},
    )
    assert errors("offer-observation", {**value, "item_code": "bad value with spaces"})


def test_source_contract_rejects_credentials_and_nondefault_ports() -> None:
    registry = yaml.safe_load(
        (ROOT / "changes/raos-v2/phase-2/sources/source-registry.v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    value = registry["sources"][0]
    assert not errors("source-record", value)
    assert errors(
        "source-record",
        {**value, "canonical_url": "https://user:password@example.com/source"},
    )
    assert errors(
        "source-record",
        {**value, "canonical_url": "https://example.com:8443/source"},
    )
    assert not errors(
        "source-record",
        {**value, "canonical_url": "https://example.com:443/source"},
    )


def test_media_registry_defaults_to_no_image_and_rejects_unbound_image_refs() -> None:
    media = yaml.safe_load(
        (ROOT / "changes/raos-v2/phase-2/media/media-policy.v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    offers = json.loads(
        (
            ROOT
            / "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
        ).read_text(encoding="utf-8")
    )
    builder.validate_media_policy_document(media, offers)
    assert all(
        row["state"] == "NO_IMAGE_INTENTIONAL"
        and row["image_binding"] is None
        and row["render"] == "NEUTRAL_PLACEHOLDER"
        for row in media["product_registry"]
    )
    mutated = deepcopy(offers)
    mutated["offers"][0]["offer_observation"]["image_ref"] = "IMG-SYNTHETIC-1"
    with pytest.raises(builder.BuildFailure, match="MEDIA_BINDING_UNRESOLVED"):
        builder.validate_media_policy_document(media, mutated)
    expected = {
        "source_id": "SRC-SYNTHETIC-MEDIA",
        "item_code": "synthetic:item-1",
        "content_sha256": "a" * 64,
    }
    complete = {
        **expected,
        "alt": "合成契約画像",
        "checked_at": "2026-08-28T06:41:52+09:00",
    }
    assert builder.media_binding_state(complete, expected) == "BOUND_OFFICIAL_IMAGE"
    missing = deepcopy(complete)
    missing.pop("source_id")
    assert builder.media_binding_state(missing, expected) == "BLOCKED"
    modified_hash = {**complete, "content_sha256": "b" * 64}
    assert builder.media_binding_state(modified_hash, expected) == "BLOCKED"
    modified = deepcopy(media)
    modified["negative_fixtures"][1]["expected_state"] = "ALLOW"
    with pytest.raises(builder.BuildFailure, match="MEDIA_POLICY_INVALID"):
        builder.validate_media_policy_document(modified, offers)


def test_article_blocks_are_required_and_templates_are_exactly_seven() -> None:
    value = schema("article-definition")
    assert value["properties"]["template"]["enum"] == [
        "HOME",
        "HUB",
        "GUIDE",
        "COMPARISON",
        "DIFFERENCE",
        "TOOL",
        "POLICY",
    ]
    assert "blocks" in value["required"]


def test_real_content_cannot_be_sealed_in_phase_0_to_2() -> None:
    bound_names = {
        "article",
        "claims",
        "sources",
        "render",
        "migration",
        "editorial",
        "products",
        "review",
        "render_model",
        "phase3_claim_authority",
    }
    package = {
        "schema_version": "1.0.0",
        "package_id": "PKG-TEST",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": "/carry-on/",
        "article_id": "A01",
        "input_hashes": {name: "a" * 64 for name in bound_names},
        "render_hash": "b" * 64,
        "source_snapshot_hash": "c" * 64,
        "claim_evidence": [
            {"claim_id": "CLM-SYNTHETIC-FRESH", "risk_class": "LOW", "freshness": "FRESH"}
        ],
        "review_binding": {
            "reviewer_id": "SYNTHETIC-REVIEWER",
            "reviewed_at": "2026-08-28T00:00:00+09:00",
            "review_version": "SYNTHETIC-V1",
            "synthetic": True,
        },
        "migration_manifest": {
            "previous": None,
            "next": "synthetic",
            "wordpress_intent": "CREATE_OR_UPDATE",
            "sha256": "a" * 64,
        },
        "created_at": "2026-08-28T00:00:00+09:00",
        "content_class": "REAL_CONTENT",
        "state": "PACKAGE_SEALED",
        "package_digest": "d" * 64,
    }
    assert errors("publication-package", package)
    package["content_class"] = "SYNTHETIC_FIXTURE"
    assert not errors("publication-package", package)
    package["state"] = "PUBLISHED"
    assert errors("publication-package", package)


def test_generated_publication_hash_closure_rejects_alias_mutation() -> None:
    candidate = json.loads(
        (
            ROOT
            / "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
        ).read_text(encoding="utf-8")
    )
    synthetic = json.loads(
        (
            ROOT
            / "changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"
        ).read_text(encoding="utf-8")
    )["package"]
    builder.validate_publication_hash_closure(candidate)
    builder.validate_publication_hash_closure(synthetic)
    for field in ("render_hash", "source_snapshot_hash"):
        changed = deepcopy(candidate)
        changed[field] = "f" * 64
        with pytest.raises(builder.BuildFailure, match="HASH_CLOSURE"):
            builder.validate_publication_hash_closure(changed)
    changed = deepcopy(candidate)
    changed["migration_manifest"]["sha256"] = "f" * 64
    with pytest.raises(builder.BuildFailure, match="HASH_CLOSURE"):
        builder.validate_publication_hash_closure(changed)


def test_offline_validator_recomputes_real_and_synthetic_publication_bindings() -> None:
    values = successor_validator._validate_contract_instances()
    successor_validator._validate_publication_closure(values)

    changed = deepcopy(values)
    changed["candidate"]["input_hashes"]["products"] = "f" * 64
    with pytest.raises(
        successor_validator.ValidationFailure, match="PUBLICATION_HASH_CLOSURE"
    ):
        successor_validator._validate_publication_closure(changed)

    changed = deepcopy(values)
    changed["synthetic_seal"]["package"]["migration_manifest"][
        "wordpress_intent"
    ] = "DELETE"
    with pytest.raises(
        successor_validator.ValidationFailure,
        match="SYNTHETIC_MIGRATION_BINDING",
    ):
        successor_validator._validate_publication_closure(changed)


def test_publication_claim_freshness_is_resolved_from_source_closure() -> None:
    ledger = yaml.safe_load(
        (
            ROOT / "changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"
        ).read_text(encoding="utf-8")
    )
    source_registry = yaml.safe_load(
        (
            ROOT / "changes/raos-v2/phase-2/sources/source-registry.v2.yaml"
        ).read_text(encoding="utf-8")
    )
    claims = {row["claim_id"]: row for row in ledger["claims"]}
    bound = [row for row in ledger["claims"] if row["claim_id"].startswith("CLM-A05-")]
    candidate_at = datetime.fromisoformat("2026-08-28T06:41:52+09:00")
    evidence = builder.publication_claim_evidence(
        bound_claims=bound,
        all_claims=claims,
        source_registry=source_registry,
        candidate_at=candidate_at,
    )
    assert {row["freshness"] for row in evidence} == {"FRESH", "UNKNOWN"}

    rejected = deepcopy(source_registry)
    rejected["sources"][5]["status"] = "REJECTED"
    with pytest.raises(builder.BuildFailure, match="SOURCE_INELIGIBLE"):
        builder.publication_claim_evidence(
            bound_claims=bound,
            all_claims=claims,
            source_registry=rejected,
            candidate_at=candidate_at,
        )

    overdue = deepcopy(source_registry)
    overdue["sources"][5]["next_review_at"] = "2026-08-27T06:41:52+09:00"
    with pytest.raises(builder.BuildFailure, match="CLAIM_FRESHNESS"):
        builder.publication_claim_evidence(
            bound_claims=bound,
            all_claims=claims,
            source_registry=overdue,
            candidate_at=candidate_at,
        )


def test_analytics_event_allowlist_rejects_pii_or_free_fields() -> None:
    event = {
        "schema_version": "1.0.0",
        "event_name": "tool_result_view",
        "event_version": 1,
        "event_time_jst": "2026-08-28T00:00:00+09:00",
        "session_token_hmac": "a" * 64,
        "article_id": "A02",
        "placement": "result_panel",
        "consent_state": "GRANTED",
        "result_state": "UNKNOWN",
    }
    assert not errors("analytics-event", event)
    for forbidden in ("email", "raw_ip", "full_url", "free_text"):
        assert errors("analytics-event", {**event, forbidden: "secret"})
    assert errors("analytics-event", {**event, "session_token_hmac": "a" * 32})


@pytest.mark.parametrize(
    ("event_name", "required_field", "required_value", "irrelevant_field"),
    [
        ("tool_result_view", "result_state", "UNKNOWN", "source_id"),
        ("evidence_link_open", "source_id", "SRC-V2-ANA-CARRY-ON", "product_id"),
        ("official_source_open", "source_id", "SRC-V2-JAL-CARRY-ON", "result_state"),
        (
            "affiliate_outbound_activate",
            "product_id",
            "PRD-ACE-CRESTA-06316",
            "source_id",
        ),
        ("error_state_view", "result_state", "BLOCKED", "product_id"),
    ],
)
def test_analytics_event_specific_required_and_irrelevant_fields(
    event_name: str,
    required_field: str,
    required_value: str,
    irrelevant_field: str,
) -> None:
    base = {
        "schema_version": "1.0.0",
        "event_name": event_name,
        "event_version": 1,
        "event_time_jst": "2026-08-28T00:00:00+09:00",
        "session_token_hmac": "a" * 64,
        "article_id": "A02",
        "placement": "result_panel",
        "consent_state": "GRANTED",
    }
    assert errors("analytics-event", base)
    valid = {**base, required_field: required_value}
    assert not errors("analytics-event", valid)
    assert errors("analytics-event", {**valid, irrelevant_field: required_value})


def test_event_catalog_matches_schema_required_field_matrix() -> None:
    catalog = yaml.safe_load(
        (
            ROOT / "changes/raos-v2/phase-2/events/event-catalog.v2.yaml"
        ).read_text(encoding="utf-8")
    )
    builder.validate_event_catalog_document(catalog)
    changed = deepcopy(catalog)
    changed["event_field_matrix"]["affiliate_outbound_activate"][
        "required_non_null"
    ] = []
    with pytest.raises(builder.BuildFailure, match="EVENT_FIELD_MATRIX"):
        builder.validate_event_catalog_document(changed)


def _luminance(hex_color: str) -> float:
    values = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_declared_design_contrast_pairs_meet_aa() -> None:
    tokens = json.loads(
        (ROOT / "changes/raos-v2/design/design-tokens.v2.json").read_text(
            encoding="utf-8"
        )
    )
    for pair in tokens["contrast_pairs"]:
        foreground = _luminance(tokens["color"][pair["foreground"]])
        background = _luminance(tokens["color"][pair["background"]])
        ratio = (max(foreground, background) + 0.05) / (
            min(foreground, background) + 0.05
        )
        assert ratio + math.ulp(ratio) >= float(pair["minimum"])


def test_route_registry_has_no_collision_or_orphan() -> None:
    registry = yaml.safe_load(
        (ROOT / "changes/raos-v2/route-registry.v2.yaml").read_text(encoding="utf-8")
    )
    routes = {row["route"] for row in registry["routes"]}
    assert len(routes) == 26
    assert registry["collision_policy"] == "FAIL_CLOSED"
    for row in registry["routes"]:
        assert row["primary_intent_id"]
        assert row["template"]
        assert row["internal_links"]
        assert set(row["internal_links"]) <= routes
    assert all(
        "NOINDEX" in row["index_state"] or row["index_state"] == "PRESERVE_CURRENT"
        for row in registry["routes"]
    )


def test_route_article_intent_ids_are_one_closed_cross_ledger_identity() -> None:
    product = builder.product_specification()
    routes = builder.route_registry()
    builder.validate_cross_ledger_identity(product, routes)

    changed = deepcopy(routes)
    target = next(row for row in changed["routes"] if row["article_id"] == "A05")
    target["primary_intent_id"] = "INTENT-A05-COMPARISON"
    with pytest.raises(builder.BuildFailure, match="CROSS_LEDGER_IDENTITY"):
        builder.validate_cross_ledger_identity(product, changed)

    changed = deepcopy(routes)
    target = next(row for row in changed["routes"] if row["article_id"] == "A19")
    target["article_id"] = "A19-FIXTURE"
    with pytest.raises(builder.BuildFailure, match="CROSS_LEDGER_IDENTITY"):
        builder.validate_cross_ledger_identity(product, changed)


def test_package_ui_source_is_authoritative_and_preview_metadata_cannot_drift() -> None:
    root = ROOT / "packages/web-ui/src/decision-support-v2"
    pages = json.loads((root / "preview/pages.v2.json").read_text(encoding="utf-8"))
    route_contract = (root / "contracts.ts").read_text(encoding="utf-8")
    typescript_checker = (root / "checker.ts").read_text(encoding="utf-8")
    preview_checker = (root / "preview/checker.js").read_text(encoding="utf-8")
    builder.validate_authoritative_ui_parity(pages)

    with pytest.raises(builder.BuildFailure, match="AUTHORITATIVE_UI_PARITY"):
        builder.validate_authoritative_ui_parity(
            pages,
            route_contract=route_contract.replace(
                "articleId: 'A19'", "articleId: 'A19-FIXTURE'", 1
            ),
            typescript_checker=typescript_checker,
            preview_checker=preview_checker,
        )
    with pytest.raises(builder.BuildFailure, match="AUTHORITATIVE_UI_PARITY"):
        builder.validate_authoritative_ui_parity(
            pages,
            route_contract=route_contract,
            typescript_checker=typescript_checker.replace(
                "UNKNOWN: 2", "UNKNOWN: 1", 1
            ),
            preview_checker=preview_checker,
        )


def test_portfolio_uses_only_query_intent_contract_values() -> None:
    product = yaml.safe_load(
        (ROOT / "changes/raos-v2/product-spec.v2.yaml").read_text(encoding="utf-8")
    )
    allowed = {"RULE", "DECISION", "TASK", "PRODUCT", "RISK", "HOW_TO", "TRUST"}
    assert len(product["portfolio"]) == 25
    assert {row["intent_class"] for row in product["portfolio"]} <= allowed
