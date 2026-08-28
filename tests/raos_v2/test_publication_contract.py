from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
import yaml

from scripts import build_raos_v2_successor as successor_builder
from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.wordpress_disabled import DisabledWordPressDraft
from raos.application.decision_support_v2.publication import build_evidence_candidate
from raos.domain.decision_support_v2.publication import (
    ClaimEvidenceBinding,
    PublicationPackage,
    PublicationState,
    ReviewBinding,
)
from raos.domain.decision_support_v2.models import FreshnessState, RiskClass


CREATED = datetime.fromisoformat("2026-08-28T12:00:00+09:00")
ROOT = Path(__file__).resolve().parents[2]
HASHES = {
    "article": "a" * 64,
    "claims": "b" * 64,
    "sources": "c" * 64,
    "render": "d" * 64,
    "migration": "e" * 64,
    "editorial": "1" * 64,
    "products": "2" * 64,
    "review": "3" * 64,
    "render_model": "4" * 64,
    "phase3_claim_authority": "5" * 64,
}
FRESH_CLAIMS = (
    ClaimEvidenceBinding("CLM-SYNTHETIC-FACT", RiskClass.HIGH, FreshnessState.FRESH),
)


def _synthetic() -> PublicationPackage:
    return PublicationPackage(
        package_id="SYNTHETIC-PACKAGE-V2",
        target_origin="https://kurashinoshirube.com",
        target_route="/synthetic-contract-fixture/",
        article_id="SYNTHETIC-ARTICLE-V2",
        input_hashes=HASHES,
        render_hash="d" * 64,
        source_snapshot_hash="c" * 64,
        claim_evidence=FRESH_CLAIMS,
        review_binding=ReviewBinding(
            "SYNTHETIC-REVIEWER-NOT-A-PERSON",
            CREATED,
            "SYNTHETIC-V1",
            True,
        ),
        migration_manifest={
            "sha256": "e" * 64,
            "wordpress_intent": "CREATE_OR_UPDATE",
            "previous": None,
            "next": "synthetic",
        },
        created_at=CREATED,
        state=PublicationState.DRAFT,
        synthetic=True,
    )


def _sealed() -> PublicationPackage:
    return (
        _synthetic()
        .transition(PublicationState.EVIDENCE_COMPLETE)
        .transition(PublicationState.HUMAN_REVIEWED)
        .transition(PublicationState.PACKAGE_SEALED)
    )


def test_real_content_stops_at_evidence_complete_without_review() -> None:
    package = build_evidence_candidate(
        package_id="REAL-CANDIDATE",
        route="/carry-on-suitcase-comparison/",
        article_id="A05",
        input_hashes=HASHES,
        render_hash="d" * 64,
        source_snapshot_hash="c" * 64,
        claim_evidence=FRESH_CLAIMS,
        migration_manifest={
            "schema": "RAOS_V2_MIGRATION_MANIFEST_V1",
            "mode": "LOCAL_SIMULATION_ONLY",
            "target_route": "/carry-on-suitcase-comparison/",
            "sha256": "e" * 64,
        },
        created_at=CREATED,
    )
    assert package.state is PublicationState.EVIDENCE_COMPLETE
    with pytest.raises(ValueError):
        package.transition(PublicationState.HUMAN_REVIEWED)


def test_v1_real_candidate_remains_compatible_without_phase3_authority() -> None:
    legacy_hashes = {
        name: digest
        for name, digest in HASHES.items()
        if name != "phase3_claim_authority"
    }
    package = build_evidence_candidate(
        package_id="REAL-V1-COMPATIBLE-CANDIDATE",
        route="/carry-on-suitcase-comparison/",
        article_id="A05",
        input_hashes=legacy_hashes,
        render_hash="d" * 64,
        source_snapshot_hash="c" * 64,
        claim_evidence=FRESH_CLAIMS,
        migration_manifest={
            "schema": "RAOS_V2_MIGRATION_MANIFEST_V1",
            "mode": "LOCAL_SIMULATION_ONLY",
            "target_route": "/carry-on-suitcase-comparison/",
            "sha256": "e" * 64,
        },
        created_at=CREATED,
    )
    Draft202012Validator(successor_builder.publication_package_schema()).validate(
        package.to_contract_record()
    )
    assert package.state is PublicationState.EVIDENCE_COMPLETE


def test_t_v2_031_only_structured_synthetic_review_can_seal() -> None:
    real = replace(_synthetic(), synthetic=False)
    evidence = real.transition(PublicationState.EVIDENCE_COMPLETE)
    with pytest.raises(ValueError):
        evidence.transition(PublicationState.HUMAN_REVIEWED)


@pytest.mark.parametrize(
    "freshness",
    [
        FreshnessState.SOFT_STALE,
        FreshnessState.HARD_STALE,
        FreshnessState.UNKNOWN,
        FreshnessState.UNAVAILABLE,
        FreshnessState.REJECTED,
    ],
)
@pytest.mark.parametrize("risk_class", list(RiskClass))
def test_t_v2_014_nonfresh_claim_blocks_package_seal(
    freshness: FreshnessState, risk_class: RiskClass
) -> None:
    package = replace(
        _synthetic(),
        claim_evidence=(ClaimEvidenceBinding("CLM-NONFRESH", risk_class, freshness),),
    )
    reviewed = package.transition(PublicationState.EVIDENCE_COMPLETE).transition(
        PublicationState.HUMAN_REVIEWED
    )
    with pytest.raises(ValueError):
        reviewed.transition(PublicationState.PACKAGE_SEALED)


def test_due_high_risk_claim_is_bound_and_can_seal_at_exact_review_boundary() -> None:
    package = replace(
        _synthetic(),
        claim_evidence=(
            ClaimEvidenceBinding(
                "CLM-HIGH-RISK-DUE", RiskClass.HIGH, FreshnessState.DUE
            ),
        ),
    )
    sealed = (
        package.transition(PublicationState.EVIDENCE_COMPLETE)
        .transition(PublicationState.HUMAN_REVIEWED)
        .transition(PublicationState.PACKAGE_SEALED)
    )
    assert sealed.verify_seal()


def test_t_v2_037_semantic_drift_invalidates_seal() -> None:
    sealed = _sealed()
    assert sealed.verify_seal()
    with pytest.raises(ValueError):
        replace(sealed, target_route="/tampered/")
    with pytest.raises(ValueError):
        replace(sealed, state=PublicationState.DRAFT)
    with pytest.raises(ValueError):
        replace(sealed, synthetic=False)


def test_direct_sealed_constructor_cannot_bypass_review_and_digest() -> None:
    with pytest.raises(ValueError):
        replace(_synthetic(), state=PublicationState.PACKAGE_SEALED)
    with pytest.raises(ValueError):
        replace(
            _synthetic(),
            state=PublicationState.PACKAGE_SEALED,
            package_digest="f" * 64,
        )


@pytest.mark.parametrize(
    "missing", ["article", "claims", "sources", "render", "migration"]
)
def test_t_v2_038_seal_requires_every_binding(missing: str) -> None:
    with pytest.raises(ValueError):
        package = replace(
            _synthetic(),
            input_hashes={k: v for k, v in HASHES.items() if k != missing},
        )
        package.transition(PublicationState.EVIDENCE_COMPLETE)


@pytest.mark.parametrize(
    "missing", sorted(set(HASHES) - {"phase3_claim_authority"})
)
def test_real_evidence_candidate_requires_full_nine_hash_closure(missing: str) -> None:
    with pytest.raises(ValueError):
        build_evidence_candidate(
            package_id="REAL-CANDIDATE",
            route="/carry-on-suitcase-comparison/",
            article_id="A05",
            input_hashes={
                key: value for key, value in HASHES.items() if key != missing
            },
            render_hash="d" * 64,
            source_snapshot_hash="c" * 64,
            claim_evidence=FRESH_CLAIMS,
            migration_manifest={"action": "KEEP_ROUTE", "sha256": "e" * 64},
            created_at=CREATED,
        )


@pytest.mark.parametrize(
    "route",
    ["", "//other.example/x/", "/../x/", "/%2e%2e/x/", "/x/?q=1", "/x/#y"],
)
def test_publication_rejects_unsafe_target_routes(route: str) -> None:
    with pytest.raises(ValueError):
        replace(_synthetic(), target_route=route)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("render_hash", "not-a-hash"),
        ("source_snapshot_hash", "A" * 64),
        ("input_hashes", {**HASHES, "article": "0" * 63}),
        ("package_id", ""),
        ("article_id", ""),
    ],
)
def test_publication_rejects_tampered_hashes_and_empty_ids(
    field: str, value: object
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(_synthetic(), **{field: value})


def test_publication_hash_closure_rejects_internal_binding_conflicts() -> None:
    with pytest.raises(ValueError):
        replace(_synthetic(), render_hash="f" * 64)
    with pytest.raises(ValueError):
        replace(_synthetic(), source_snapshot_hash="f" * 64)
    with pytest.raises(ValueError):
        replace(
            _synthetic(),
            migration_manifest={
                **_synthetic().migration_manifest,
                "sha256": "f" * 64,
            },
        )

    record = dict(_synthetic().to_contract_record())
    record["render_hash"] = "f" * 64
    with pytest.raises(ValueError):
        PublicationPackage.from_contract_record(record)


def test_t_v2_039_wordpress_default_is_disabled_dry_run_no_request() -> None:
    port = DisabledWordPressDraft()
    receipt = port.dry_run(_sealed())
    assert port.mode == "DISABLED_DRY_RUN"
    assert port.request_count == 0
    assert port.external_action_count == 0
    assert receipt["status"] == "DRY_RUN"
    assert receipt["external_status"] == "NOT_EXECUTED"
    assert receipt["target"] == {
        "origin": "https://kurashinoshirube.com",
        "route": "/synthetic-contract-fixture/",
    }
    assert receipt["intent"] == "CREATE_OR_UPDATE"
    assert receipt["before"] == {"state": "NOT_OBSERVED", "reason": "DISABLED"}
    assert receipt["after"] == {
        "post_status": "draft",
        "comment_status": "closed",
        "ping_status": "closed",
        "render_hash": "d" * 64,
    }
    assert len(receipt["idempotency_key"]) == 64
    assert receipt == port.dry_run(_sealed())
    assert "credential" not in json.dumps(receipt).casefold()
    assert "endpoint" not in json.dumps(receipt).casefold()

    ports = yaml.safe_load(
        (ROOT / "contracts/raos-v2/v1/ports.v1.yaml").read_text(encoding="utf-8")
    )
    contract = ports["ports"]["WordPressDraftPort"]["receipt_contract"]
    assert set(receipt) == set(contract["required_fields"])
    for field, value in contract["constants"].items():
        assert receipt[field] == value
    assert set(receipt["target"]) == set(contract["target_shape"])
    assert set(receipt["before"]) == set(contract["before_shape"])
    assert set(receipt["after"]) == set(contract["after_shape"])
    for field in contract["opaque_hex64_fields"]:
        assert isinstance(receipt[field], str)
        assert len(receipt[field]) == 64
        int(receipt[field], 16)


def test_wordpress_receipt_intent_must_be_bound_by_migration_manifest() -> None:
    package = replace(
        _synthetic(),
        migration_manifest={
            "sha256": "e" * 64,
            "wordpress_intent": "CREATE",
        },
    )
    package = (
        package.transition(PublicationState.EVIDENCE_COMPLETE)
        .transition(PublicationState.HUMAN_REVIEWED)
        .transition(PublicationState.PACKAGE_SEALED)
    )
    with pytest.raises(AdapterError) as error:
        DisabledWordPressDraft().dry_run(package)
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


def test_wordpress_rejects_unsealed_candidate() -> None:
    with pytest.raises(AdapterError) as error:
        DisabledWordPressDraft().dry_run(_synthetic())
    assert error.value.code is AdapterFailure.DISABLED


def test_publication_machine_has_no_published_state() -> None:
    assert "PUBLISHED" not in PublicationState.__members__
    assert PublicationState.REVIEWED is PublicationState.EVIDENCE_COMPLETE
    assert PublicationState.APPROVED is PublicationState.HUMAN_REVIEWED
    assert PublicationState.SEALED is PublicationState.PACKAGE_SEALED


def test_publication_contract_records_validate_against_phase_1_schema() -> None:
    schema = json.loads(
        (ROOT / "contracts/raos-v2/v1/publication-package.schema.json").read_text(
            encoding="utf-8"
        )
    )
    record = _sealed().to_contract_record()
    Draft202012Validator(schema).validate(record)
    assert PublicationPackage.from_contract_record(record) == _sealed()


def test_generated_real_candidate_round_trips_through_domain_contract() -> None:
    path = ROOT / "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    candidate = PublicationPackage.from_contract_record(record)
    assert candidate.article_id == "A05"
    assert candidate.state is PublicationState.EVIDENCE_COMPLETE
    assert candidate.synthetic is False
    assert candidate.to_contract_record() == record


def test_migration_manifest_has_ordered_local_only_restore_plan() -> None:
    path = ROOT / "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    successor_builder.validate_migration_restore_plan(manifest)
    steps = manifest["rollback"]["ordered_restore_steps"]
    assert [step["sequence"] for step in steps] == [1, 2, 3]
    assert all(step["production_status"] == "NOT_EXECUTED" for step in steps)

    changed = deepcopy(manifest)
    changed["rollback"]["ordered_restore_steps"][1]["sequence"] = 3
    with pytest.raises(successor_builder.BuildFailure, match="MIGRATION_RESTORE_PLAN"):
        successor_builder.validate_migration_restore_plan(changed)
