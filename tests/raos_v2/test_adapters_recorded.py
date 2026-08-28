import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import yaml

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.recorded_airline import RecordedRuleRegistry
from raos.adapters.decision_support_v2.recorded_catalog import RecordedProductCatalog
from raos.adapters.decision_support_v2.recorded_rakuten import (
    RecordedRakutenSearch,
    identity_match,
)
from raos.application.decision_support_v2.checker import CarryOnChecker
from raos.application.decision_support_v2.offer_lookup import (
    OfferLookupState,
    lookup_recorded_offers,
)
from raos.domain.decision_support_v2.models import (
    AirlineRuleSet,
    BagInput,
    CaptureMode,
    DecisionStatus,
    DimensionEdges,
    IdentityStatus,
    JourneySegment,
    OfferObservation,
    OfferStatus,
    SourceRecord,
)


ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "changes/raos-v2/phase-2"
CATALOG = PHASE / "data/ace-carry-on-models.v2.json"
RAKUTEN = PHASE / "fixtures/recorded-rakuten-item-search-2026-07-01.json"
RULES = PHASE / "fixtures/recorded-airline-rules.v2.json"
CONTRACTS = ROOT / "contracts/raos-v2/v1"
SOURCES = PHASE / "sources/source-registry.v2.yaml"
PAGES = ROOT / "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"


def _catalog() -> RecordedProductCatalog:
    return RecordedProductCatalog.from_file(CATALOG)


def test_recorded_airline_fixture_has_no_network_authority_or_raw_body() -> None:
    adapter = RecordedRuleRegistry.from_file(RULES)
    text = RULES.read_text(encoding="utf-8")
    assert adapter.mode == "RECORDED_ONLY"
    assert adapter.external_action_count == 0
    assert "raw_body" not in text
    assert "api_key" not in text


def test_recorded_airline_rejects_unknown_journey_scope(tmp_path: Path) -> None:
    payload = json.loads(RULES.read_text(encoding="utf-8"))
    payload["rule_sets"][0]["journey_scope"] = "UNSCOPED"
    mutated = tmp_path / "unknown-scope.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AdapterError) as error:
        RecordedRuleRegistry.from_file(mutated)
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


def test_t_v2_041_recorded_rakuten_parses_without_credentials() -> None:
    catalog = _catalog()
    adapter = RecordedRakutenSearch.from_file(
        RAKUTEN, products={product.product_id: product for product in catalog.all()}
    )
    offers = adapter.search(
        {
            "schema_version": "2026-07-01",
            "product_ids": ["PRD-ACE-CRESTA-06316"],
        }
    )
    assert adapter.mode == "RECORDED_ONLY"
    assert adapter.external_action_count == 0
    assert len(offers) == 1
    assert offers[0].status is OfferStatus.UNAVAILABLE
    assert offers[0].display_price_jpy is None


def test_difference_official_model_name_matches_source_and_display() -> None:
    product = _catalog().get("PRD-ACE-DIFFERENCE-05721")
    assert product is not None
    assert product.model_name == "ディフェレンス"
    sources = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    source = next(
        row
        for row in sources["sources"]
        if row["source_id"] == "SRC-ACE-DIFFERENCE-05721"
    )
    pages_text = PAGES.read_text(encoding="utf-8")
    assert "ディフェレンス" in source["title"]
    assert "ディフェレンス" in pages_text
    assert "ディファレンス" not in pages_text
    catalog = _catalog()
    adapter = RecordedRakutenSearch.from_file(
        RAKUTEN, products={item.product_id: item for item in catalog.all()}
    )
    offers = adapter.search(
        {
            "schema_version": "2026-07-01",
            "product_ids": [product.product_id],
        }
    )
    assert offers[0].identity_evidence == ("EXACT",)


def test_t_v2_042_missing_required_response_field_is_closed(tmp_path: Path) -> None:
    payload = json.loads(RAKUTEN.read_text(encoding="utf-8"))
    del payload["offers"][0]["offer_observation"]["offer_id"]
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    catalog = _catalog()
    with pytest.raises(AdapterError) as error:
        RecordedRakutenSearch.from_file(
            mutated, products={product.product_id: product for product in catalog.all()}
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


def test_synthetic_offer_observation_cannot_be_after_fixture_creation(
    tmp_path: Path,
) -> None:
    payload = json.loads(RAKUTEN.read_text(encoding="utf-8"))
    payload["offers"][0]["offer_observation"]["observed_at"] = (
        "2026-08-28T06:41:53+09:00"
    )
    mutated = tmp_path / "future-observation.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    catalog = _catalog()
    with pytest.raises(AdapterError) as error:
        RecordedRakutenSearch.from_file(
            mutated, products={product.product_id: product for product in catalog.all()}
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("location", "key", "value"),
    [
        ("payload", "unexpected", "value"),
        ("record", "unexpected", "value"),
        ("offer", "unexpected", "value"),
        ("identity", "unexpected", "value"),
        ("offer", "affiliate_url_ref", "javascript:alert"),
        ("offer", "affiliate_url_ref", "SAFE-BUT-NOT-OPAQUE-PROVIDER-REF"),
        ("offer", "image_ref", "SAFE-BUT-NOT-OPAQUE-PROVIDER-REF"),
        ("offer", "image_ref", "https://example.invalid/image?token=value"),
        ("offer", "item_code", "credential-secret"),
    ],
)
def test_recorded_rakuten_unknown_keys_and_unsafe_refs_fail_closed(
    tmp_path: Path, location: str, key: str, value: str
) -> None:
    payload = json.loads(RAKUTEN.read_text(encoding="utf-8"))
    targets = {
        "payload": payload,
        "record": payload["offers"][0],
        "offer": payload["offers"][0]["offer_observation"],
        "identity": payload["offers"][0]["identity_input"],
    }
    targets[location][key] = value
    mutated = tmp_path / f"mutated-{location}-{key}.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    catalog = _catalog()
    with pytest.raises(AdapterError) as error:
        RecordedRakutenSearch.from_file(
            mutated, products={product.product_id: product for product in catalog.all()}
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize("kind", ["airline", "catalog", "rakuten"])
def test_recorded_json_adapters_reject_duplicate_keys(
    tmp_path: Path, kind: str
) -> None:
    source = {"airline": RULES, "catalog": CATALOG, "rakuten": RAKUTEN}[kind]
    raw = source.read_text(encoding="utf-8")
    mutated = raw.replace("{", '{"schema":"DUPLICATE",', 1)
    path = tmp_path / f"duplicate-{kind}.json"
    path.write_text(mutated, encoding="utf-8")
    with pytest.raises(AdapterError) as error:
        if kind == "airline":
            RecordedRuleRegistry.from_file(path)
        elif kind == "catalog":
            RecordedProductCatalog.from_file(path)
        else:
            catalog = _catalog()
            RecordedRakutenSearch.from_file(
                path,
                products={product.product_id: product for product in catalog.all()},
            )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_recorded_json_adapters_reject_nonstandard_nonfinite_numbers(
    tmp_path: Path, constant: str
) -> None:
    raw = RAKUTEN.read_text(encoding="utf-8").replace(
        '"price_jpy": null', f'"price_jpy": {constant}', 1
    )
    path = tmp_path / "nonfinite.json"
    path.write_text(raw, encoding="utf-8")
    catalog = _catalog()
    with pytest.raises(AdapterError) as error:
        RecordedRakutenSearch.from_file(
            path, products={product.product_id: product for product in catalog.all()}
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


def test_t_v2_043_identity_normalizes_case_and_spacing_only() -> None:
    product = _catalog().get("PRD-ACE-CRESTA-06316")
    assert product is not None
    assert (
        identity_match(
            product=product,
            observed_model_number=" 06316 ",
            title="ＡＣＥ  クレスタ 06316",
        )
        is IdentityStatus.EXACT
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="06316 交換用キャスター",
        )
        is IdentityStatus.REJECTED
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06315",
            title="ACE CRESTA 06315",
        )
        is IdentityStatus.AMBIGUOUS
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="ACE スーツケース クレスタ 06316",
        )
        is IdentityStatus.EXACT
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="ACE スーツケース用カバー クレスタ 06316",
        )
        is IdentityStatus.REJECTED
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="ACE 06316",
        )
        is IdentityStatus.AMBIGUOUS
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="RACE クレスタ 06316",
        )
        is IdentityStatus.AMBIGUOUS
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="ACE クレスタ 06316 2個セット",
        )
        is IdentityStatus.AMBIGUOUS
    )
    assert (
        identity_match(
            product=product,
            observed_model_number="06316",
            title="ACE クレスタ 06316 旧モデル",
        )
        is IdentityStatus.AMBIGUOUS
    )


def test_adapter_errors_render_only_closed_code() -> None:
    error = AdapterError(AdapterFailure.TIMEOUT)
    assert str(error) == "TIMEOUT"
    assert "credential" not in repr(error).casefold()


@pytest.mark.parametrize(
    "failure",
    [
        AdapterFailure.TIMEOUT,
        AdapterFailure.RATE_LIMIT,
        AdapterFailure.INVALID_RESPONSE,
        AdapterFailure.DISABLED,
        AdapterFailure.STALE,
    ],
)
def test_typed_rule_adapter_failure_falls_back_to_unknown_without_cta(
    failure: AdapterFailure,
) -> None:
    class FailingRegistry:
        def resolve(
            self, segment: JourneySegment, *, at: datetime
        ) -> tuple[AirlineRuleSet, ...]:
            raise AdapterError(failure)

    at = datetime.fromisoformat("2026-08-28T12:00:00+09:00")
    result = CarryOnChecker(FailingRegistry()).check(
        segments=(JourneySegment("S1", "ANA", at, seat_count=100),),
        bag=BagInput(
            DimensionEdges(Decimal("55"), Decimal("40"), Decimal("25")),
            Decimal("10"),
            appendages_included=True,
            expanded=False,
        ),
    )
    assert result.status is DecisionStatus.UNKNOWN
    assert result.reason_codes == (f"RULE_ADAPTER_{failure.value}",)
    assert result.source_ids == ()


@pytest.mark.parametrize(
    "failure",
    [
        AdapterFailure.TIMEOUT,
        AdapterFailure.RATE_LIMIT,
        AdapterFailure.INVALID_RESPONSE,
        AdapterFailure.DISABLED,
        AdapterFailure.STALE,
    ],
)
def test_typed_offer_failure_returns_unknown_and_no_synthetic_offer(
    failure: AdapterFailure,
) -> None:
    class FailingSearch:
        mode = "RECORDED_ONLY"

        def search(self, request: Mapping[str, object]) -> tuple[OfferObservation, ...]:
            raise AdapterError(failure)

    result = lookup_recorded_offers(
        FailingSearch(),
        {"schema_version": "2026-07-01", "product_ids": []},
    )
    assert result.state is OfferLookupState.UNKNOWN
    assert result.failure is failure
    assert result.offers == ()


def test_recorded_core_entities_validate_against_phase_1_contracts() -> None:
    rule_envelope = json.loads(RULES.read_text(encoding="utf-8"))
    product_envelope = json.loads(CATALOG.read_text(encoding="utf-8"))
    offer_envelope = json.loads(RAKUTEN.read_text(encoding="utf-8"))
    rule_schema = json.loads(
        (CONTRACTS / "airline-rule-set.schema.json").read_text(encoding="utf-8")
    )
    product_schema = json.loads(
        (CONTRACTS / "product-model.schema.json").read_text(encoding="utf-8")
    )
    variant_schema = json.loads(
        (CONTRACTS / "product-variant.schema.json").read_text(encoding="utf-8")
    )
    offer_schema = json.loads(
        (CONTRACTS / "offer-observation.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        variant_schema["$id"], Resource.from_contents(variant_schema)
    )
    for rule in rule_envelope["rule_sets"]:
        Draft202012Validator(rule_schema).validate(rule)
    for product in product_envelope["products"]:
        Draft202012Validator(product_schema, registry=registry).validate(product)
    for recorded in offer_envelope["offers"]:
        Draft202012Validator(offer_schema).validate(recorded["offer_observation"])


def test_source_registry_rows_validate_against_schema_and_runtime_domain() -> None:
    envelope = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    schema = json.loads(
        (CONTRACTS / "source-record.schema.json").read_text(encoding="utf-8")
    )
    records: list[SourceRecord] = []
    for row in envelope["sources"]:
        Draft202012Validator(schema).validate(row)
        record = SourceRecord.from_contract_record(row)
        assert record.to_contract_record() == row
        records.append(record)
    assert len(records) == 8
    airline = next(item for item in records if item.source_id == "SRC-V2-ANA-CARRY-ON")
    ace = next(item for item in records if item.source_id == "SRC-ACE-CRESTA-06316")
    assert airline.capture_provenance.mode is CaptureMode.PUBLIC_READ_ONLY
    assert ace.capture_provenance.mode is CaptureMode.RECORDED_FIXTURE
    assert airline.checked_at != ace.checked_at

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    rows = {row["source_id"]: row for row in envelope["sources"]}
    captures = {row["source_id"]: row for row in rules["source_captures"]}
    for rule in rules["rule_sets"]:
        source = rows[rule["source_id"]]
        capture = captures[rule["source_id"]]
        assert rule["checked_at"] == source["checked_at"]
        assert rule["source_next_review_at"] == source["next_review_at"]
        assert rule["source_content_sha256"] == source["content_sha256"]
        assert rule["source_content_sha256"] == capture["body_sha256"]
        assert capture["status"] == source["status"]


def test_source_runtime_mapping_rejects_schema_drift() -> None:
    envelope = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    row = dict(envelope["sources"][0])
    row["stored_material"] = "RAW_BODY"
    with pytest.raises(ValueError):
        SourceRecord.from_contract_record(row)
