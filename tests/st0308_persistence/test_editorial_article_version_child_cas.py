"""ArticleVersion CAS ownership for EditorialContract child mutations."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from sqlalchemy.sql.dml import Insert, Update
import yaml

from raos.adapters.persistence.sqlalchemy.repositories import editorial
from raos.domain.editorial.aggregates import (
    ArticleDisclosureContext,
    ArticleMethodologyBinding,
    StructuredDataManifest,
)
from raos.domain.editorial.enums import StructuredDataManifestValidationStatus
from raos.domain.editorial.ids import (
    EditorialMethodologyVersionId,
    SeoMetadataVersionId,
    StructuredDataManifestId,
)
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.ids import ObjectArtifactId
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
)
from raos.ports.editorial.repositories import EditorialContractRepository
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.st0308_persistence.test_w2b_evidence_editorial_repositories import (
    NOW,
    _Result,
    _ScriptedSession,
    _article_version_graph,
    _uuid,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _disclosure(*, reviewed: bool = False) -> ArticleDisclosureContext:
    principal = PrincipalId(_uuid(601)) if reviewed else None
    reviewed_at = AwareUtcDateTime(NOW) if reviewed else None
    return ArticleDisclosureContext(
        article_version_id=_article_version_graph().state.id,
        affiliate_relationship=True,
        material_benefit_relationship=False,
        benefit_types=(),
        disclosure_policy_version="1.0.0",
        additional_disclosure_text=None,
        reviewed_by_principal_id=principal,
        reviewed_at=reviewed_at,
        created_at=AwareUtcDateTime(NOW),
    )


def _binding() -> ArticleMethodologyBinding:
    return ArticleMethodologyBinding(
        article_version_id=_article_version_graph().state.id,
        methodology_version_id=EditorialMethodologyVersionId(_uuid(602)),
        candidate_universe_artifact_id=ObjectArtifactId(_uuid(603)),
        candidate_universe_sha256=Sha256Digest("5" * 64),
        bound_at=AwareUtcDateTime(NOW),
        bound_by_principal_id=PrincipalId(_uuid(604)),
    )


def _manifest() -> StructuredDataManifest:
    return StructuredDataManifest(
        id=StructuredDataManifestId(_uuid(605)),
        article_version_id=_article_version_graph().state.id,
        seo_metadata_version_id=SeoMetadataVersionId(_uuid(606)),
        generator_version="1.0.0",
        visible_content_sha256=Sha256Digest("6" * 64),
        jsonld_artifact_id=ObjectArtifactId(_uuid(607)),
        jsonld_sha256=Sha256Digest("7" * 64),
        enabled_types=("Article",),
        disabled_types=(),
        validation_status=StructuredDataManifestValidationStatus.PASS,
        validated_at=AwareUtcDateTime(NOW),
        created_at=AwareUtcDateTime(NOW),
    )


def _parameters(value: Callable[..., object]) -> tuple[str, ...]:
    return tuple(inspect.signature(value).parameters)


def _dml_relation(statement: object) -> str:
    if not isinstance(statement, (Insert, Update)):
        raise AssertionError(f"expected DML, received {type(statement).__name__}")
    return cast(str, cast(Any, statement).table.fullname)


APPEND_CASES = (
    (
        "add_disclosure_context",
        _disclosure,
        "editorial.article_disclosure_context",
    ),
    (
        "append_methodology_binding",
        _binding,
        "editorial.article_methodology_binding",
    ),
    (
        "append_structured_data_manifest",
        _manifest,
        "editorial.structured_data_manifest",
    ),
)


def test_port_and_adapter_require_expected_article_version_for_every_child_write() -> (
    None
):
    expected_parameters = {
        "add_disclosure_context": ("self", "context", "expected_version"),
        "record_disclosure_review": (
            "self",
            "article_version_id",
            "review",
            "expected_version",
        ),
        "append_methodology_binding": ("self", "binding", "expected_version"),
        "append_structured_data_manifest": (
            "self",
            "manifest",
            "expected_version",
        ),
    }
    for method_name, parameters in expected_parameters.items():
        assert (
            _parameters(getattr(EditorialContractRepository, method_name)) == parameters
        )
        assert (
            _parameters(
                getattr(editorial.SqlAlchemyEditorialContractRepository, method_name)
            )
            == parameters
        )


@pytest.mark.parametrize(
    ("method_name", "value_factory", "child_relation"),
    APPEND_CASES,
)
def test_append_child_bumps_article_version_before_child_insert(
    method_name: str,
    value_factory: Callable[[], object],
    child_relation: str,
) -> None:
    session = _ScriptedSession(_Result(scalar=1), _Result())
    repository = editorial.SqlAlchemyEditorialContractRepository(session)

    persisted = getattr(repository, method_name)(value_factory(), AggregateVersion(0))

    assert persisted == AggregateVersion(1)
    assert tuple(_dml_relation(statement) for statement in session.statements) == (
        "editorial.article_version",
        child_relation,
    )


@pytest.mark.parametrize(
    ("method_name", "value_factory", "_child_relation"),
    APPEND_CASES,
)
def test_append_child_stale_article_version_rejects_before_child_insert(
    method_name: str,
    value_factory: Callable[[], object],
    _child_relation: str,
) -> None:
    version_id = _article_version_graph().state.id
    session = _ScriptedSession(
        _Result(scalar=None),
        _Result(row={"id": version_id.value, "lock_version": 2}),
    )
    repository = editorial.SqlAlchemyEditorialContractRepository(session)

    with pytest.raises(PersistenceError) as captured:
        getattr(repository, method_name)(value_factory(), AggregateVersion(0))

    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
    assert len(session.statements) == 2
    assert _dml_relation(session.statements[0]) == "editorial.article_version"


def test_disclosure_review_validates_then_bumps_root_before_state_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _disclosure()
    review = replace(
        current,
        reviewed_by_principal_id=PrincipalId(_uuid(601)),
        reviewed_at=AwareUtcDateTime(NOW),
    )
    monkeypatch.setattr(
        editorial,
        "_context_principal_id",
        lambda _session: review.reviewed_by_principal_id,
    )
    session = _ScriptedSession(
        _Result(row=editorial._encode_editorial_article_disclosure_context(current)),
        _Result(scalar=1),
        _Result(row=editorial._encode_editorial_article_disclosure_context(review)),
    )

    persisted_review = editorial.SqlAlchemyEditorialContractRepository(
        session
    ).record_disclosure_review(
        current.article_version_id,
        review,
        AggregateVersion(0),
    )

    assert persisted_review == review
    assert len(session.statements) == 3
    assert _dml_relation(session.statements[1]) == "editorial.article_version"
    assert _dml_relation(session.statements[2]) == (
        "editorial.article_disclosure_context"
    )


def test_disclosure_review_stale_root_rejects_before_child_state_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _disclosure()
    review = replace(
        current,
        reviewed_by_principal_id=PrincipalId(_uuid(601)),
        reviewed_at=AwareUtcDateTime(NOW),
    )
    monkeypatch.setattr(
        editorial,
        "_context_principal_id",
        lambda _session: review.reviewed_by_principal_id,
    )
    session = _ScriptedSession(
        _Result(row=editorial._encode_editorial_article_disclosure_context(current)),
        _Result(scalar=None),
        _Result(
            row={
                "id": current.article_version_id.value,
                "lock_version": 2,
            }
        ),
    )

    with pytest.raises(PersistenceError) as captured:
        editorial.SqlAlchemyEditorialContractRepository(
            session
        ).record_disclosure_review(
            current.article_version_id,
            review,
            AggregateVersion(0),
        )

    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
    assert len(session.statements) == 3
    assert _dml_relation(session.statements[1]) == "editorial.article_version"


@pytest.mark.parametrize(
    ("method_name", "value_factory"),
    tuple((name, factory) for name, factory, _relation in APPEND_CASES),
)
def test_append_child_rejects_non_version_before_dml(
    method_name: str,
    value_factory: Callable[[], object],
) -> None:
    session = _ScriptedSession()
    with pytest.raises(ValueError):
        getattr(editorial.SqlAlchemyEditorialContractRepository(session), method_name)(
            value_factory(), cast(Any, 0)
        )
    assert session.statements == []


def test_contracts_bind_all_article_version_child_mutations_to_root_cas() -> None:
    contract_directory = REPOSITORY_ROOT / "changes/st-0308/contracts/persistence"
    repository_surface = yaml.safe_load(
        (contract_directory / "repository-surface-matrix.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    concurrency = yaml.safe_load(
        (contract_directory / "concurrency-matrix.v1.yaml").read_text(encoding="utf-8")
    )
    state_cas = yaml.safe_load(
        (contract_directory / "state-cas-matrix.v1.yaml").read_text(encoding="utf-8")
    )
    runtime = yaml.safe_load(
        (contract_directory.parent / "persistence-runtime.v2.yaml").read_text(
            encoding="utf-8"
        )
    )

    methods = repository_surface["modules"]["editorial"]["editorial_contracts"][
        "methods"
    ]
    assert {
        "add_disclosure_context(context,expected_version)->PersistedVersion",
        "record_disclosure_review(article_version_id,review,expected_version)->ArticleDisclosureContext",
        "append_methodology_binding(binding,expected_version)->PersistedVersion",
        "append_structured_data_manifest(manifest,expected_version)->PersistedVersion",
    } <= set(methods)

    required_children = {
        "editorial.article_disclosure_context",
        "editorial.article_methodology_binding",
        "editorial.structured_data_manifest",
    }
    child_bumps = concurrency["lock_version_cas"]["child_root_version_bumps"]
    assert required_children <= set(child_bumps["editorial.article_version"])
    child_methods = concurrency["lock_version_cas"]["child_mutation_methods"]
    assert set(child_methods) == required_children
    assert all(
        row["expected_version_parameter"] == "expected_version"
        and row["root_cas_before_child_dml"] == "REQUIRED"
        for rows in child_methods.values()
        for row in rows
    )

    disclosure_edge = state_cas["relations"]["editorial.article_disclosure_context"][
        "edges"
    ][0]
    assert disclosure_edge["method"] == (
        "EditorialContractRepository.record_disclosure_review"
    )
    assert disclosure_edge["root_cas"] == {
        "relation": "editorial.article_version",
        "where": "id=:article_version_id AND lock_version=:expected_version",
        "set": "lock_version=:expected_version+1",
        "ordering": "AFTER_PRECONDITION_VALIDATION_BEFORE_CHILD_STATE_CAS",
    }

    bound_matrices = runtime["executable_matrices"]
    for matrix_name, file_name in (
        ("repository_surface", "repository-surface-matrix.v1.yaml"),
        ("concurrency", "concurrency-matrix.v1.yaml"),
        ("state_cas", "state-cas-matrix.v1.yaml"),
    ):
        assert (
            bound_matrices[matrix_name]["sha256"]
            == hashlib.sha256((contract_directory / file_name).read_bytes()).hexdigest()
        )
