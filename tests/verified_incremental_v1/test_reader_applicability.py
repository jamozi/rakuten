"""Static applicability regressions; synthetic mutations are never audit evidence."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest

from raos.application.editorial import reader_release_applicability_v1 as adapter
from raos.application.editorial import verified_incremental_audit_v1 as audit
from tests.verified_incremental_audit_v1 import test_contract as audit_examples


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("changes/editorial-portfolio-v2/editorial-portfolio.v2.json")
PROJECTION = Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json")
SUITCASE = "PRD-PROTECA-TRI-AIR-01541"
POWER = "PRD-ANKER-SOLIX-C300"


def read(root, path):
    return json.loads((root / path).read_text(encoding="utf-8"))


def write(root, path, document):
    (root / path).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def source_root(tmp_path):
    for path in (SOURCE, PROJECTION):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    return tmp_path


def product(document, product_id):
    return next(row for row in document["products"] if row["product_id"] == product_id)


@pytest.mark.parametrize(
    ("product_id", "kind", "category", "disposal_basis"),
    [
        (SUITCASE, "suitcase", "mobility", "UNKNOWN"),
        (POWER, "portable_power_station", "preparedness", "TRACKED_KIND"),
        ("PRD-SIROCA-SS-MA251", "dishwasher", "household", "TRACKED_KIND"),
        ("PRD-SWITCHBOT-K11-PRO", "robot_vacuum", "household", "TRACKED_KIND"),
    ],
)
def test_actual_kinds_and_categories_ground_required_reviews(
    product_id, kind, category, disposal_basis
):
    result = adapter.classify_product_audit_scope(ROOT, (product_id,))
    row = result.to_document()["products"][0]
    original = product(read(ROOT, SOURCE), product_id)
    assert row["product_kind"] == kind
    assert set(row["basis"]["article_categories"].values()) == {category}
    assert row["basis"]["product_kind_tokens"] == sorted(
        original["product_kind_tokens"]
    )
    assert row["basis"]["official_url"] == original["official_url"]
    assert row["basis"]["official_models"] == sorted(original["official_models"])
    assert row["basis"]["source_references"]
    assert row["smart_device"]["state"] == row["disposal"]["state"] == "REQUIRED"
    assert row["smart_device"]["basis_status"] == "UNKNOWN"
    assert row["disposal"]["basis_status"] == disposal_basis
    assert row["smart_device"]["rationale"]
    assert row["disposal"]["rationale"]
    assert (
        result.smart_device_product_ids == result.disposal_product_ids == (product_id,)
    )


def test_all_33_products_are_preserved_with_deterministic_detached_documents():
    portfolio = read(ROOT, PROJECTION)
    ids = tuple(row["product_id"] for row in portfolio["products"])
    assert len(ids) == 33
    result = adapter.classify_product_audit_scope(ROOT, ids)
    assert result == adapter.classify_product_audit_scope(ROOT, tuple(reversed(ids)))
    assert result.retained_product_ids == tuple(sorted(ids))
    assert (
        result.smart_device_product_ids
        == result.disposal_product_ids
        == tuple(sorted(ids))
    )
    document = result.to_document()
    assert [row["product_id"] for row in document["products"]] == sorted(ids)
    assert document["audit_completion"] == "NOT_EVALUATED"
    assert document["publication_authority"] is False
    assert all(
        row[concern]["state"] == "REQUIRED"
        for row in document["products"]
        for concern in ("smart_device", "disposal")
    )
    assert document["source_fingerprints"] == {
        path.as_posix(): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in (SOURCE, PROJECTION)
    }
    original = deepcopy(document)
    document["products"][0]["basis"]["product_kind_tokens"].clear()
    document["products"][0]["smart_device"]["state"] = "NOT_APPLICABLE"
    document["source_fingerprints"].clear()
    assert result.to_document() == original
    with pytest.raises(FrozenInstanceError):
        result.products[0].product_id = "changed"


def test_no_selected_article_product_is_missing():
    for article in read(ROOT, PROJECTION)["articles"]:
        selected = tuple(article["product_ids"])
        result = adapter.classify_product_audit_scope(ROOT, selected)
        assert result.retained_product_ids == tuple(sorted(selected))
        assert result.smart_device_product_ids == tuple(sorted(selected))
        assert result.disposal_product_ids == tuple(sorted(selected))


def test_unknown_id_fails_closed_without_returning_a_partial_scope():
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="UNKNOWN_PRODUCT"
    ):
        adapter.classify_product_audit_scope(ROOT, (SUITCASE, "PRD-UNREGISTERED"))


@pytest.mark.parametrize(
    "ids", [(SUITCASE, SUITCASE), ("",), ("../product",), (1,), [SUITCASE]]
)
def test_invalid_or_duplicate_retained_ids_are_rejected(ids):
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="PRODUCT_IDS_INVALID"
    ):
        adapter.classify_product_audit_scope(ROOT, ids)


def test_empty_scope_needs_no_product_sources(tmp_path):
    result = adapter.classify_product_audit_scope(tmp_path, ())
    assert result.retained_product_ids == result.smart_device_product_ids == ()
    assert result.disposal_product_ids == ()
    assert result.to_document()["products"] == []
    assert result.to_document()["source_fingerprints"] == {}
    result.require_current(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_kind_tokens", ["スーツケース"]),
        ("official_url", "https://example.invalid/wrong-model"),
        ("representative_model", "wrong-model"),
    ],
)
def test_stale_or_wrong_product_projection_fails_closed(source_root, field, value):
    document = read(source_root, PROJECTION)
    product(document, POWER)[field] = value
    write(source_root, PROJECTION, document)
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="PRODUCT_MAPPING_MISMATCH"
    ):
        adapter.classify_product_audit_scope(source_root, (POWER,))


@pytest.mark.parametrize("field", ["product_ids", "v2_category", "category"])
def test_stale_or_wrong_article_mapping_fails_closed(source_root, field):
    document = read(source_root, PROJECTION)
    document["articles"][0][field] = [] if field == "product_ids" else "household"
    write(source_root, PROJECTION, document)
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="ARTICLE_MAPPING_MISMATCH"
    ):
        adapter.classify_product_audit_scope(source_root, (SUITCASE,))


@pytest.mark.parametrize(
    "mutation",
    [
        {"product_kind_tokens": []},
        {"product_kind_tokens": ["スーツケース", "未知の電動機能"]},
        {"smart_device": False, "battery": False},
    ],
)
def test_new_unknown_metadata_never_becomes_non_applicable(source_root, mutation):
    for path in (SOURCE, PROJECTION):
        document = read(source_root, path)
        product(document, SUITCASE).update(mutation)
        write(source_root, path, document)
    result = adapter.classify_product_audit_scope(source_root, (SUITCASE,))
    row = result.to_document()["products"][0]
    for concern in ("smart_device", "disposal"):
        assert row[concern]["state"] == "REQUIRED"
        assert row[concern]["basis_status"] == "UNKNOWN"
    assert result.smart_device_product_ids == result.disposal_product_ids == (SUITCASE,)
    if "smart_device" in mutation:
        assert row["basis"]["unrecognized_metadata_fields"] == [
            "battery",
            "smart_device",
        ]
        assert "unrecognized" in row["smart_device"]["rationale"].lower()


def test_new_product_with_unrecognized_kind_is_retained_and_required(source_root):
    new_id = "PRD-NEW-UNKNOWN-KIND"
    for path in (SOURCE, PROJECTION):
        document = read(source_root, path)
        new_product = deepcopy(product(document, SUITCASE))
        new_product.update(product_id=new_id, product_kind_tokens=["未分類"])
        if path == PROJECTION:
            new_product["product_code"] = "p99"
        document["products"].append(new_product)
        document["articles"][0]["product_ids"].append(new_id)
        write(source_root, path, document)
    result = adapter.classify_product_audit_scope(source_root, (SUITCASE, new_id))
    assert result.retained_product_ids == tuple(sorted((SUITCASE, new_id)))
    assert new_id in result.smart_device_product_ids
    assert new_id in result.disposal_product_ids
    row = next(
        row for row in result.to_document()["products"] if row["product_id"] == new_id
    )
    assert row["product_kind"] == "unknown"
    assert row["disposal"]["basis_status"] == "UNKNOWN"


def test_source_changes_invalidate_a_previous_classification_even_when_sets_match(
    source_root,
):
    previous = adapter.classify_product_audit_scope(source_root, (POWER,))
    previous.require_current(source_root)
    for path in (SOURCE, PROJECTION):
        document = read(source_root, path)
        product(document, POWER)["official_name"] += " revised tracked name"
        write(source_root, path, document)
    current = adapter.classify_product_audit_scope(source_root, (POWER,))
    assert previous.retained_product_ids == current.retained_product_ids
    assert previous.smart_device_product_ids == current.smart_device_product_ids
    assert previous.source_fingerprint != current.source_fingerprint
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_CHANGED"
    ):
        previous.require_current(source_root)


def test_forged_basis_or_fingerprint_does_not_survive_reclassification(source_root):
    current = adapter.classify_product_audit_scope(source_root, (POWER,))
    wrong = replace(current, source_fingerprints=())
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_CHANGED"
    ):
        wrong.require_current(source_root)


@pytest.mark.parametrize(
    "mutation", ["duplicate_product", "missing_product", "unbound_product", "schema"]
)
def test_invalid_source_mapping_fails_closed(source_root, mutation):
    for path in (SOURCE, PROJECTION):
        document = read(source_root, path)
        if mutation == "duplicate_product":
            document["products"].append(deepcopy(document["products"][0]))
        elif mutation == "missing_product":
            document["products"] = [
                row for row in document["products"] if row["product_id"] != SUITCASE
            ]
        elif mutation == "unbound_product":
            for article in document["articles"]:
                article["product_ids"] = [
                    value for value in article["product_ids"] if value != SUITCASE
                ]
        else:
            document["schema"] = "UNRECOGNIZED"
        write(source_root, path, document)
    with pytest.raises(adapter.ReaderReleaseApplicabilityFailure):
        adapter.classify_product_audit_scope(source_root, (SUITCASE,))


def test_source_reads_are_bounded_and_reject_duplicate_json_keys(source_root):
    (source_root / SOURCE).write_bytes(b" " * (adapter.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_INVALID"
    ):
        adapter.classify_product_audit_scope(source_root, (POWER,))
    (source_root / SOURCE).write_text(
        '{"products": [], "products": []}', encoding="utf-8"
    )
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_INVALID"
    ):
        adapter.classify_product_audit_scope(source_root, (POWER,))


def test_missing_or_symlinked_sources_fail_closed(source_root):
    path = source_root / SOURCE
    raw = path.read_bytes()
    path.unlink()
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_INVALID"
    ):
        adapter.classify_product_audit_scope(source_root, (POWER,))
    redirected = source_root / "redirected-source.json"
    redirected.write_bytes(raw)
    path.symlink_to(redirected)
    with pytest.raises(
        adapter.ReaderReleaseApplicabilityFailure, match="SOURCE_INVALID"
    ):
        adapter.classify_product_audit_scope(source_root, (POWER,))


@pytest.mark.parametrize("surface_id", [audit.CLOUD_SURFACE, audit.DISPOSAL_SURFACE])
@pytest.mark.parametrize("product_id", [SUITCASE, POWER])
def test_existing_audit_validator_rejects_non_applicable_for_required_products(
    surface_id, product_id
):
    classified = adapter.classify_product_audit_scope(ROOT, (product_id,))
    scope = replace(
        audit_examples.scope(),
        retained_product_ids=classified.retained_product_ids,
        smart_device_product_ids=classified.smart_device_product_ids,
        disposal_product_ids=classified.disposal_product_ids,
    )
    report, artifacts = audit_examples.synthetic_pair(scope)
    audit_examples.validate(report, artifacts, scope)
    row = next(
        row
        for row in report["rounds"][0]["surfaces"]
        if row["surface_id"] == surface_id
    )
    row.update(
        status="NOT_APPLICABLE",
        execution_status="NOT_EXECUTED",
        reason_code="NO_APPLICABLE_PRODUCTS",
        evidence_id=None,
    )
    with pytest.raises(
        audit.IncrementalAuditFailure, match="MANDATORY_SURFACE_NOT_PASSED"
    ):
        audit_examples.validate(report, artifacts, scope)
