"""Closed repository surface and representative behavior for ST-0308 W2B."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import re
from typing import Any, Iterator, cast
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories import (
    editorial as editorial_adapters,
)
from raos.adapters.persistence.sqlalchemy.repositories import (
    evidence as evidence_adapters,
)
from raos.domain.editorial.aggregates import (
    ArticleBlock,
    ArticleBlockProduct,
    ArticlePlan,
    ArticlePlanState,
    ArticleTypeVersion,
    ArticleTypeVersionState,
    ArticleVersion,
    ArticleVersionState,
    ComparisonAxis,
    ComparisonValue,
    Recommendation,
    RecommendationRationale,
    RecommendationSet,
)
from raos.domain.editorial.enums import (
    ArticleBlockBlockType,
    ArticleBlockProductPlacementRole,
    ArticlePlanArticleType,
    ArticlePlanStatus,
    ArticleTypeVersionStatus,
    ArticleVersionCreatedByActorType,
    ArticleVersionStatus,
    ComparisonAxisDataType,
    ComparisonValueValidationStatus,
    RecommendationRationaleRationaleType,
    RecommendationStatus,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticleId,
    ArticlePlanId,
    ArticleTemplateVersionId,
    ArticleTypeVersionId,
    ArticleVersionId,
    ComparisonAxisId,
    ComparisonValueId,
    ContentSchemaVersionId,
    RecommendationId,
    RecommendationRationaleId,
    RecommendationSetId,
    SeoMetadataVersionId,
)
from raos.domain.editorial.values import (
    ArticleBlockContentJson,
    ArticlePlanBriefJson,
    ArticleTypeVersionContractJson,
)
from raos.domain.catalog.ids import CanonicalProductId, OfferId
from raos.domain.evidence.aggregates import Source, SourceSnapshot, SourceState
from raos.domain.evidence.enums import (
    SourceAuthorityLevel,
    SourceSnapshotValidationStatus,
    SourceSourceType,
    SourceStatus,
)
from raos.domain.evidence.ids import (
    FactId,
    SourceId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.evidence.values import SourceMetadataJson
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.ids import ObjectArtifactId
from raos.domain.portfolio.ids import (
    CategoryId,
    IntentClusterId,
    KeywordId,
    SiteId,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.identity import ActorId
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    Sha256Digest,
    UriReference,
)
from raos.ports.editorial import repositories as editorial_ports
from raos.ports.evidence import repositories as evidence_ports
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


NOW = datetime(2026, 8, 24, 4, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_session_runtime_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the repository SQL unit tests independent of the UoW fixture."""

    for module in (evidence_adapters, editorial_adapters):
        monkeypatch.setattr(
            module, "register_pending_events", lambda *args, **kwargs: None
        )
    monkeypatch.setattr(
        evidence_adapters,
        "stage_registered_events",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        editorial_adapters,
        "stage_registered_events",
        lambda *args, **kwargs: None,
    )


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        rows: tuple[dict[str, object], ...] = (),
        scalar: object = None,
    ) -> None:
        self._row = row
        self._rows = rows
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row

    def scalar_one_or_none(self) -> object:
        return self._scalar

    def __iter__(self) -> Iterator[dict[str, object]]:
        return iter(self._rows)


class _ScriptedSession(Session):
    def __init__(self, *results: _Result) -> None:
        super().__init__()
        self._results = list(results)
        self.statements: list[object] = []

    def execute(self, statement: object, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("unexpected SQL execution")
        return self._results.pop(0)


def _source(*, version: int = 0, name: str = "primary") -> Source:
    return Source(
        SourceState(
            id=SourceId(UUID("018f0000-0000-7000-8000-000000000101")),
            display_id="SRC-101",
            source_type=SourceSourceType.MANUFACTURER,
            provider_endpoint_id=None,
            name=name,
            base_url=UriReference("https://example.test/source"),
            authority_level=SourceAuthorityLevel.PRIMARY,
            permitted_use="EDITORIAL_EVIDENCE",
            terms_checked_at=None,
            terms_checked_by_principal_id=None,
            status=SourceStatus.ACTIVE,
            metadata=SourceMetadataJson(
                FrozenJsonObject.from_mapping({"fixture": True})
            ),
            created_at=AwareUtcDateTime(NOW),
            updated_at=AwareUtcDateTime(NOW),
            lock_version=AggregateVersion(version),
        )
    )


def _snapshot(source_id: SourceId) -> SourceSnapshot:
    return SourceSnapshot(
        id=SourceSnapshotId(UUID("018f0000-0000-7000-8000-000000000111")),
        display_id="SNAP-111",
        source_id=source_id,
        artifact_id=ObjectArtifactId(UUID("018f0000-0000-7000-8000-000000000112")),
        external_reference="fixture",
        acquired_at=AwareUtcDateTime(NOW),
        effective_at=None,
        expires_at=None,
        content_sha256=Sha256Digest("2" * 64),
        parser_version="fixture-v1",
        validation_status=SourceSnapshotValidationStatus.VALID,
        validation_message=None,
        created_at=AwareUtcDateTime(NOW),
    )


def _article_plan(*, version: int = 0) -> ArticlePlan:
    return ArticlePlan(
        ArticlePlanState(
            id=ArticlePlanId(UUID("018f0000-0000-7000-8000-000000000201")),
            display_id="PLAN-201",
            site_id=SiteId(UUID("018f0000-0000-7000-8000-000000000202")),
            category_id=CategoryId(UUID("018f0000-0000-7000-8000-000000000203")),
            intent_cluster_id=IntentClusterId(
                UUID("018f0000-0000-7000-8000-000000000204")
            ),
            primary_keyword_id=KeywordId(UUID("018f0000-0000-7000-8000-000000000205")),
            article_type=ArticlePlanArticleType.PRODUCT_COMPARISON,
            working_title="比較記事",
            objective="一次情報に基づく条件別比較",
            status=ArticlePlanStatus.DRAFT,
            priority=1,
            opportunity_assessment_id=None,
            created_by_principal_id=PrincipalId(
                UUID("018f0000-0000-7000-8000-000000000206")
            ),
            approved_by_principal_id=None,
            approved_at=None,
            brief=ArticlePlanBriefJson(
                FrozenJsonObject.from_mapping({"intent": "comparison"})
            ),
            created_at=AwareUtcDateTime(NOW),
            updated_at=AwareUtcDateTime(NOW),
            lock_version=AggregateVersion(version),
        )
    )


def _article_type(status: ArticleTypeVersionStatus) -> ArticleTypeVersion:
    state = ArticleTypeVersionState(
        id=ArticleTypeVersionId(UUID("018f0000-0000-7000-8000-000000000301")),
        article_type_code="comparison",
        semantic_version="1.0.0",
        contract=ArticleTypeVersionContractJson(
            FrozenJsonObject.from_mapping({"blocks": ["comparison"]})
        ),
        contract_sha256=Sha256Digest("1" * 64),
        status=status,
        approved_by_principal_id=None,
        approved_at=None,
        created_at=AwareUtcDateTime(NOW),
    )
    return ArticleTypeVersion(state)


def _uuid(suffix: int) -> UUID:
    return UUID(f"018f0000-0000-7000-8000-{suffix:012d}")


def _article_version_graph(*, version: int = 0) -> ArticleVersion:
    version_id = ArticleVersionId(_uuid(401))
    block = ArticleBlock(
        id=ArticleBlockId(_uuid(410)),
        article_version_id=version_id,
        block_key="product-card",
        block_type=ArticleBlockBlockType.PRODUCT_CARD,
        position=0,
        heading_level=None,
        content=ArticleBlockContentJson(
            FrozenJsonObject.from_mapping({"kind": "product-card"})
        ),
        plain_text="商品カード",
        content_sha256=Sha256Digest("3" * 64),
        created_at=AwareUtcDateTime(NOW),
    )
    product_id = CanonicalProductId(_uuid(411))
    block_product = ArticleBlockProduct(
        article_block_id=block.id,
        product_id=product_id,
        offer_id=None,
        placement_role=ArticleBlockProductPlacementRole.PRIMARY,
        position=0,
        placement_id="primary-1",
        created_at=AwareUtcDateTime(NOW),
    )
    axis = ComparisonAxis(
        id=ComparisonAxisId(_uuid(420)),
        article_version_id=version_id,
        axis_code="capacity",
        name="容量",
        description="公称容量",
        data_type=ComparisonAxisDataType.TEXT,
        unit_code=None,
        position=0,
        is_required=True,
        created_at=AwareUtcDateTime(NOW),
    )
    value = ComparisonValue(
        id=ComparisonValueId(_uuid(421)),
        comparison_axis_id=axis.id,
        product_id=product_id,
        value_text="288 Wh",
        value_numeric=None,
        value_boolean=None,
        value_date=None,
        value_code=None,
        display_value="288 Wh",
        source_fact_id=FactId(_uuid(422)),
        validation_status=ComparisonValueValidationStatus.VALID,
        created_at=AwareUtcDateTime(NOW),
    )
    recommendation_set = RecommendationSet(
        id=RecommendationSetId(_uuid(430)),
        article_version_id=version_id,
        set_code="portable",
        name="持ち運び重視",
        target_segment="小容量を持ち運びたい人",
        methodology="一次仕様を条件照合",
        editorial_policy_version="1.0.0",
        position=0,
        created_at=AwareUtcDateTime(NOW),
    )
    recommendation = Recommendation(
        id=RecommendationId(_uuid(431)),
        recommendation_set_id=recommendation_set.id,
        product_id=product_id,
        rank_position=1,
        suitability_score=Decimal("90.00"),
        status=RecommendationStatus.RECOMMENDED,
        created_at=AwareUtcDateTime(NOW),
    )
    rationale = RecommendationRationale(
        id=RecommendationRationaleId(_uuid(432)),
        recommendation_id=recommendation.id,
        rationale_type=RecommendationRationaleRationaleType.FIT,
        rationale_text="持ち運び条件に合う",
        claim_id=None,
        source_fact_id=FactId(_uuid(433)),
        position=0,
        created_at=AwareUtcDateTime(NOW),
    )
    return ArticleVersion(
        state=ArticleVersionState(
            id=version_id,
            display_id="ARV-401",
            article_id=ArticleId(_uuid(402)),
            version_no=1,
            content_schema_version=1,
            title="比較記事",
            meta_title=None,
            meta_description=None,
            excerpt=None,
            body_sha256=Sha256Digest("4" * 64),
            status=ArticleVersionStatus.DRAFT,
            source_packet_version_id=SourcePacketVersionId(_uuid(403)),
            based_on_version_id=None,
            ai_job_id=None,
            created_by_actor_type=ArticleVersionCreatedByActorType.USER,
            created_by_actor_id=ActorId(_uuid(404)),
            submitted_at=None,
            reviewed_at=None,
            created_at=AwareUtcDateTime(NOW),
            updated_at=AwareUtcDateTime(NOW),
            lock_version=AggregateVersion(version),
            content_schema_version_id=ContentSchemaVersionId(_uuid(405)),
            article_type_version_id=ArticleTypeVersionId(_uuid(406)),
            article_template_version_id=ArticleTemplateVersionId(_uuid(407)),
            seo_metadata_version_id=SeoMetadataVersionId(_uuid(408)),
        ),
        article_block_rows=(block,),
        article_block_product_rows=(block_product,),
        comparison_axis_rows=(axis,),
        comparison_value_rows=(value,),
        recommendation_set_rows=(recommendation_set,),
        recommendation_rows=(recommendation,),
        recommendation_rationale_rows=(rationale,),
    )


REPOSITORY_PAIRS = tuple(
    (getattr(evidence_ports, name), getattr(evidence_adapters, f"SqlAlchemy{name}"))
    for name in evidence_ports.__all__
) + tuple(
    (
        getattr(editorial_ports, name),
        getattr(editorial_adapters, f"SqlAlchemy{name}"),
    )
    for name in editorial_ports.__all__
)


def _public_methods(value: type[object]) -> dict[str, Callable[..., object]]:
    return {
        name: cast(Callable[..., object], member)
        for name, member in value.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def _parameter_shape(
    function: Callable[..., object],
) -> tuple[tuple[str, inspect._ParameterKind], ...]:
    return tuple(
        (parameter.name, parameter.kind)
        for parameter in inspect.signature(function).parameters.values()
    )


def test_all_11_protocols_and_56_methods_have_exact_concrete_shapes() -> None:
    assert len(REPOSITORY_PAIRS) == 11
    method_count = 0
    for protocol, concrete in REPOSITORY_PAIRS:
        protocol_methods = _public_methods(protocol)
        concrete_methods = _public_methods(concrete)
        assert protocol_methods.keys() == concrete_methods.keys()
        method_count += len(protocol_methods)
        for name, protocol_method in protocol_methods.items():
            implementation = concrete_methods[name]
            assert _parameter_shape(implementation) == _parameter_shape(protocol_method)
            source = inspect.getsource(implementation)
            assert "NotImplementedError" not in source
            assert " pass" not in source
            assert any(
                marker in source
                for marker in (
                    "select(",
                    "insert(",
                    "update(",
                    "_cas_",
                    "self._get(",
                    "self._get_version(",
                )
            )
    assert method_count == 56


def test_repositories_are_session_only_and_bind_all_owned_relations() -> None:
    session = Session()
    try:
        instances = [concrete(session) for _, concrete in REPOSITORY_PAIRS]
    finally:
        session.close()
    assert len(instances) == 11
    assert all(
        tuple(inspect.signature(type(item)).parameters) == ("session",)
        for item in instances
    )


def test_modules_have_no_generic_destructive_or_reflective_surface() -> None:
    for module in (evidence_adapters, editorial_adapters):
        source = inspect.getsource(module)
        assert re.search(r"\bdelete\(", source) is None
        assert re.search(r"\btext\(", source) is None
        assert re.search(r"\bgetattr\(", source) is None
        assert re.search(r"\bhasattr\(", source) is None
        assert "automap" not in source
        assert "reflect(" not in source


def test_event_emitters_bind_exact_matrix_specialization_literals() -> None:
    expected = (
        (
            evidence_adapters.SqlAlchemySourceSnapshotRepository.append,
            "jp.raos.evidence.source_snapshot_captured.v1",
        ),
        (
            editorial_adapters.SqlAlchemyArticlePlanRepository.save,
            "jp.raos.editorial.article_plan_approved.v1",
        ),
        (
            editorial_adapters.SqlAlchemyArticleRepository.add,
            "jp.raos.editorial.article_created.v1",
        ),
        (
            editorial_adapters.SqlAlchemyArticleRepository.add_version,
            "jp.raos.editorial.draft_generated.v1",
        ),
        (
            editorial_adapters.SqlAlchemyArticleRepository.save_version,
            "jp.raos.editorial.article_version_submitted.v1",
        ),
    )
    for method, event_type in expected:
        source = inspect.getsource(method)
        assert "stage_registered_events(" in source
        assert f'expected_event_type="{event_type}"' in source


def test_state_cas_methods_consume_only_session_runtime_context_bindings() -> None:
    expected_tokens = (
        (
            evidence_adapters.SqlAlchemySourcePacketRepository.transition_version,
            (
                "_context_principal_id(self._session)",
                "transaction_timestamp(self._session)",
            ),
        ),
        (
            evidence_adapters.SqlAlchemyFirstHandExperienceRepository.transition,
            (
                "_context_principal_id(self._session, human=True)",
                "transaction_timestamp(self._session)",
            ),
        ),
        (
            editorial_adapters.SqlAlchemyArticleRepository.transition_slug,
            ("transaction_timestamp(self._session)",),
        ),
        (
            editorial_adapters.SqlAlchemyReviewCommentRepository.close,
            ("_context_principal_id(self._session)",),
        ),
        (
            editorial_adapters.SqlAlchemyMediaAssetRepository.transition,
            (
                "_context_principal_id(self._session)",
                "transaction_timestamp(self._session)",
            ),
        ),
        (
            editorial_adapters.SqlAlchemyEditorialContractRepository.record_disclosure_review,
            ("_context_principal_id(self._session)",),
        ),
    )
    for method, tokens in expected_tokens:
        source = inspect.getsource(method)
        for token in tokens:
            assert token in source

    contract_source = inspect.getsource(
        editorial_adapters.SqlAlchemyEditorialContractRepository
    )
    assert contract_source.count("_context_approval(") == 5
    assert (
        "_context_time(self._session, transition.state.validated_at)" in contract_source
    )


def test_source_positive_get_add_and_lock_cas_paths() -> None:
    source = _source()
    row = evidence_adapters._encode_evidence_source(source.state)
    read = _ScriptedSession(_Result(row=row))
    assert (
        evidence_adapters.SqlAlchemySourceRepository(read).get(source.state.id)
        == source
    )

    add = _ScriptedSession(_Result())
    assert evidence_adapters.SqlAlchemySourceRepository(add).add(
        source
    ) == AggregateVersion(0)

    save = _ScriptedSession(_Result(scalar=1))
    assert evidence_adapters.SqlAlchemySourceRepository(save).save(
        source, AggregateVersion(0)
    ) == AggregateVersion(1)


def test_source_snapshot_stages_exact_registered_source_event_after_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    registrations: list[dict[str, object]] = []
    stages: list[dict[str, object]] = []
    monkeypatch.setattr(
        evidence_adapters,
        "register_pending_events",
        lambda session, **kwargs: registrations.append(kwargs),
    )
    read = _ScriptedSession(
        _Result(row=evidence_adapters._encode_evidence_source(source.state))
    )
    loaded = evidence_adapters.SqlAlchemySourceRepository(read).get(source.state.id)
    assert loaded == source
    assert registrations == [
        {
            "aggregate_type": "evidence.source",
            "aggregate_id": source.state.id.value,
            "buffer": loaded._events,
        }
    ]

    write = _ScriptedSession(_Result(scalar=1), _Result())

    def stage(session: Session, **kwargs: object) -> None:
        assert session is write
        assert len(write.statements) == 2
        stages.append(kwargs)

    monkeypatch.setattr(evidence_adapters, "stage_registered_events", stage)
    persisted = evidence_adapters.SqlAlchemySourceSnapshotRepository(write).append(
        source.state.id,
        _snapshot(source.state.id),
        AggregateVersion(0),
    )
    assert persisted == AggregateVersion(1)
    assert stages == [
        {
            "aggregate_type": "evidence.source",
            "aggregate_id": source.state.id.value,
            "owning_method": "SourceSnapshotRepository.append",
            "persisted_version": AggregateVersion(1),
            "expected_event_type": ("jp.raos.evidence.source_snapshot_captured.v1"),
        }
    ]


@pytest.mark.parametrize(
    ("observed", "code"),
    (
        (None, PersistenceErrorCode.NOT_FOUND),
        (
            {"id": UUID(int=1), "lock_version": 3},
            PersistenceErrorCode.CONCURRENCY_CONFLICT,
        ),
    ),
)
def test_source_lock_cas_classifies_missing_and_stale(
    observed: dict[str, object] | None,
    code: PersistenceErrorCode,
) -> None:
    session = _ScriptedSession(_Result(scalar=None), _Result(row=observed))
    with pytest.raises(PersistenceError) as captured:
        evidence_adapters.SqlAlchemySourceRepository(session).save(
            _source(), AggregateVersion(0)
        )
    assert captured.value.code is code


def test_article_plan_positive_get_add_and_lock_cas_paths() -> None:
    plan = _article_plan()
    row = editorial_adapters._encode_editorial_article_plan(plan.state)
    read = _ScriptedSession(_Result(row=row))
    assert (
        editorial_adapters.SqlAlchemyArticlePlanRepository(read).get(plan.state.id)
        == plan
    )
    add = _ScriptedSession(_Result())
    assert editorial_adapters.SqlAlchemyArticlePlanRepository(add).add(
        plan
    ) == AggregateVersion(0)
    save = _ScriptedSession(_Result(scalar=1))
    assert editorial_adapters.SqlAlchemyArticlePlanRepository(save).save(
        plan, AggregateVersion(0)
    ) == AggregateVersion(1)


def test_semantic_version_series_positive_and_stale_paths() -> None:
    version = _article_type(ArticleTypeVersionStatus.DRAFT)
    positive = _ScriptedSession(_Result(rows=()), _Result())
    assert editorial_adapters.SqlAlchemyEditorialContractRepository(
        positive
    ).append_article_type_version(version, None) == AggregateVersion(1)

    stale = _ScriptedSession(_Result(rows=({"id": version.state.id.value},)))
    with pytest.raises(PersistenceError) as captured:
        editorial_adapters.SqlAlchemyEditorialContractRepository(
            stale
        ).append_article_type_version(version, None)
    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT


def test_article_type_invalid_state_edge_fails_before_update() -> None:
    current = _article_type(ArticleTypeVersionStatus.DRAFT)
    row = editorial_adapters._encode_editorial_article_type_version(current.state)
    invalid = ArticleTypeVersion(
        replace(current.state, status=ArticleTypeVersionStatus.DRAFT)
    )
    session = _ScriptedSession(_Result(row=row))
    with pytest.raises(PersistenceError) as captured:
        editorial_adapters.SqlAlchemyEditorialContractRepository(
            session
        ).transition_article_type_version(
            current.state.id,
            invalid,
            ArticleTypeVersionStatus.DRAFT,
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert len(session.statements) == 1


@pytest.mark.parametrize("spoof", ("actor", "time"))
def test_article_type_approval_rejects_spoofed_context_fields_before_update(
    spoof: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _article_type(ArticleTypeVersionStatus.DRAFT)
    context_principal = PrincipalId(UUID("018f0000-0000-7000-8000-000000000311"))
    proposed_principal = (
        PrincipalId(UUID("018f0000-0000-7000-8000-000000000312"))
        if spoof == "actor"
        else context_principal
    )
    context_at = AwareUtcDateTime(NOW)
    proposed_at = (
        AwareUtcDateTime(datetime(2026, 8, 24, 4, 0, 1, tzinfo=timezone.utc))
        if spoof == "time"
        else context_at
    )
    transition = ArticleTypeVersion(
        replace(
            current.state,
            status=ArticleTypeVersionStatus.ACTIVE,
            approved_by_principal_id=proposed_principal,
            approved_at=proposed_at,
        )
    )
    monkeypatch.setattr(
        editorial_adapters,
        "_context_principal_id",
        lambda _session: context_principal,
    )
    monkeypatch.setattr(
        editorial_adapters,
        "transaction_timestamp",
        lambda _session: context_at,
    )
    session = _ScriptedSession(
        _Result(
            row=editorial_adapters._encode_editorial_article_type_version(current.state)
        )
    )
    with pytest.raises(PersistenceError) as captured:
        editorial_adapters.SqlAlchemyEditorialContractRepository(
            session
        ).transition_article_type_version(
            current.state.id,
            transition,
            ArticleTypeVersionStatus.DRAFT,
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert len(session.statements) == 1


def test_article_version_loads_complete_transitive_owned_graph() -> None:
    expected = _article_version_graph()
    block = expected.article_block_rows[0]
    block_product = expected.article_block_product_rows[0]
    axis = expected.comparison_axis_rows[0]
    value = expected.comparison_value_rows[0]
    recommendation_set = expected.recommendation_set_rows[0]
    recommendation = expected.recommendation_rows[0]
    rationale = expected.recommendation_rationale_rows[0]
    session = _ScriptedSession(
        _Result(
            row=editorial_adapters._encode_editorial_article_version(expected.state)
        ),
        _Result(rows=()),
        _Result(rows=(editorial_adapters._encode_editorial_article_block(block),)),
        _Result(
            rows=(
                editorial_adapters._encode_editorial_article_block_product(
                    block_product
                ),
            )
        ),
        _Result(rows=()),
        _Result(rows=()),
        _Result(rows=(editorial_adapters._encode_editorial_comparison_axis(axis),)),
        _Result(rows=(editorial_adapters._encode_editorial_comparison_value(value),)),
        _Result(
            rows=(
                editorial_adapters._encode_editorial_recommendation_set(
                    recommendation_set
                ),
            )
        ),
        _Result(
            rows=(editorial_adapters._encode_editorial_recommendation(recommendation),)
        ),
        _Result(
            rows=(
                editorial_adapters._encode_editorial_recommendation_rationale(
                    rationale
                ),
            )
        ),
        _Result(rows=()),
        _Result(rows=()),
        _Result(rows=()),
    )

    loaded = editorial_adapters.SqlAlchemyArticleRepository(session).get_version(
        expected.state.id
    )

    assert loaded == expected
    assert len(session.statements) == 14


def test_article_version_add_inserts_complete_graph_parent_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _article_version_graph()
    operations: list[str] = []
    staged: list[dict[str, object]] = []

    def record_execute(_session: Session, statement: object) -> None:
        operations.append(cast(Any, statement).table.fullname)

    def record_stage(_session: Session, **kwargs: object) -> None:
        operations.append("EVENT")
        staged.append(kwargs)

    monkeypatch.setattr(editorial_adapters, "_execute", record_execute)
    monkeypatch.setattr(editorial_adapters, "stage_registered_events", record_stage)
    session = Session()
    try:
        persisted = editorial_adapters.SqlAlchemyArticleRepository(session).add_version(
            version
        )
    finally:
        session.close()

    assert persisted == AggregateVersion(0)
    assert operations == [
        "editorial.article_version",
        "editorial.article_block",
        "editorial.article_block_product",
        "editorial.comparison_axis",
        "editorial.comparison_value",
        "editorial.recommendation_set",
        "editorial.recommendation",
        "editorial.recommendation_rationale",
        "EVENT",
    ]
    assert staged == [
        {
            "aggregate_type": "editorial.article_version",
            "aggregate_id": version.state.id.value,
            "owning_method": "ArticleRepository.add_version",
            "persisted_version": AggregateVersion(0),
            "expected_event_type": "jp.raos.editorial.draft_generated.v1",
        }
    ]


def test_article_version_save_appends_complete_graph_after_one_root_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed = _article_version_graph()
    current = replace(
        proposed,
        article_block_rows=(),
        article_block_product_rows=(),
        comparison_axis_rows=(),
        comparison_value_rows=(),
        recommendation_set_rows=(),
        recommendation_rows=(),
        recommendation_rationale_rows=(),
    )
    operations: list[str] = []

    def get_current(
        _repository: editorial_adapters.SqlAlchemyArticleRepository,
        version_id: ArticleVersionId,
    ) -> ArticleVersion | None:
        assert version_id == current.state.id
        return current

    def record_cas(*args: object, **kwargs: object) -> AggregateVersion:
        del args, kwargs
        operations.append("CAS")
        return AggregateVersion(1)

    def record_execute(_session: Session, statement: object) -> None:
        operations.append(cast(Any, statement).table.fullname)

    monkeypatch.setattr(
        editorial_adapters.SqlAlchemyArticleRepository, "_get_version", get_current
    )
    monkeypatch.setattr(editorial_adapters, "_cas_update", record_cas)
    monkeypatch.setattr(editorial_adapters, "_execute", record_execute)
    session = Session()
    try:
        persisted = editorial_adapters.SqlAlchemyArticleRepository(
            session
        ).save_version(proposed, AggregateVersion(0))
    finally:
        session.close()

    assert persisted == AggregateVersion(1)
    assert operations == [
        "CAS",
        "editorial.article_block",
        "editorial.article_block_product",
        "editorial.comparison_axis",
        "editorial.comparison_value",
        "editorial.recommendation_set",
        "editorial.recommendation",
        "editorial.recommendation_rationale",
    ]


def test_article_version_child_dml_is_not_attempted_after_stale_root_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed = _article_version_graph()
    current = replace(
        proposed,
        article_block_rows=(),
        article_block_product_rows=(),
        comparison_axis_rows=(),
        comparison_value_rows=(),
        recommendation_set_rows=(),
        recommendation_rows=(),
        recommendation_rationale_rows=(),
    )
    operations: list[str] = []

    def get_current(
        _repository: editorial_adapters.SqlAlchemyArticleRepository,
        version_id: ArticleVersionId,
    ) -> ArticleVersion | None:
        assert version_id == current.state.id
        return current

    def stale_cas(*args: object, **kwargs: object) -> AggregateVersion:
        del args, kwargs
        operations.append("CAS")
        raise PersistenceError(PersistenceErrorCode.CONCURRENCY_CONFLICT)

    def reject_execute(_session: Session, _statement: object) -> None:
        raise AssertionError("child DML must not run after failed root CAS")

    monkeypatch.setattr(
        editorial_adapters.SqlAlchemyArticleRepository, "_get_version", get_current
    )
    monkeypatch.setattr(editorial_adapters, "_cas_update", stale_cas)
    monkeypatch.setattr(editorial_adapters, "_execute", reject_execute)
    session = Session()
    try:
        with pytest.raises(PersistenceError) as captured:
            editorial_adapters.SqlAlchemyArticleRepository(session).save_version(
                proposed, AggregateVersion(0)
            )
    finally:
        session.close()

    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
    assert operations == ["CAS"]


def test_article_version_rejects_mutation_of_each_existing_owned_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _article_version_graph()
    variants = (
        replace(
            current,
            article_block_product_rows=(
                replace(
                    current.article_block_product_rows[0],
                    offer_id=OfferId(_uuid(440)),
                ),
            ),
        ),
        replace(
            current,
            comparison_value_rows=(
                replace(current.comparison_value_rows[0], display_value="288Wh"),
            ),
        ),
        replace(
            current,
            recommendation_rows=(
                replace(
                    current.recommendation_rows[0],
                    suitability_score=Decimal("89.00"),
                ),
            ),
        ),
        replace(
            current,
            recommendation_rationale_rows=(
                replace(
                    current.recommendation_rationale_rows[0],
                    rationale_text="変更は禁止",
                ),
            ),
        ),
    )

    def get_current(
        _repository: editorial_adapters.SqlAlchemyArticleRepository,
        version_id: ArticleVersionId,
    ) -> ArticleVersion | None:
        assert version_id == current.state.id
        return current

    monkeypatch.setattr(
        editorial_adapters.SqlAlchemyArticleRepository, "_get_version", get_current
    )
    session = Session()
    try:
        repository = editorial_adapters.SqlAlchemyArticleRepository(session)
        for proposed in variants:
            with pytest.raises(PersistenceError) as captured:
                repository.save_version(proposed, AggregateVersion(0))
            assert captured.value.code is PersistenceErrorCode.APPEND_ONLY_RELATION
    finally:
        session.close()


def test_article_version_rejects_all_broken_transitive_owner_chains_before_dml() -> (
    None
):
    valid = _article_version_graph()
    variants = (
        replace(
            valid,
            article_block_product_rows=(
                replace(
                    valid.article_block_product_rows[0],
                    article_block_id=ArticleBlockId(_uuid(450)),
                ),
            ),
        ),
        replace(
            valid,
            comparison_value_rows=(
                replace(
                    valid.comparison_value_rows[0],
                    comparison_axis_id=ComparisonAxisId(_uuid(451)),
                ),
            ),
        ),
        replace(
            valid,
            recommendation_rows=(
                replace(
                    valid.recommendation_rows[0],
                    recommendation_set_id=RecommendationSetId(_uuid(452)),
                ),
            ),
        ),
        replace(
            valid,
            recommendation_rationale_rows=(
                replace(
                    valid.recommendation_rationale_rows[0],
                    recommendation_id=RecommendationId(_uuid(453)),
                ),
            ),
        ),
    )
    session = _ScriptedSession()
    repository = editorial_adapters.SqlAlchemyArticleRepository(session)

    for invalid in variants:
        with pytest.raises(ValueError, match="INVALID_ARTICLE_VERSION"):
            repository.add_version(invalid)
    assert session.statements == []
