"""Systemic physical-CHECK guards for every ST-0308 scalar mapper."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import partial
import hashlib
import inspect
from pathlib import Path
from typing import Callable, TypeAlias, cast
from uuid import UUID

import pytest

from raos.adapters.persistence.sqlalchemy import physical_constraints as runtime
from raos.adapters.persistence.sqlalchemy.generated import (
    physical_constraints as generated,
)
from raos.adapters.persistence.sqlalchemy.mappers import (
    ai,
    catalog,
    editorial,
    evidence,
    iam,
    ops,
    policy,
    portfolio,
)
from raos.domain.iam.ids import PrincipalId
from raos.domain.portfolio.aggregates import ActionCandidateState
from raos.domain.portfolio.enums import (
    ActionCandidateActionType,
    ActionCandidateStatus,
    ActionCandidateTargetEntityType,
)
from raos.domain.portfolio.ids import ActionCandidateId, SiteId
from raos.domain.portfolio.values import ActionCandidateRationaleJson
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import AggregateVersion, AwareUtcDateTime
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from scripts import build_st0308_persistence as generator


NOW = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)
VALID_UUID = UUID("018f0000-0000-7000-8000-000000000001")
MAPPER_MODULES = {
    "ai": ai,
    "catalog": catalog,
    "editorial": editorial,
    "evidence": evidence,
    "iam": iam,
    "ops": ops,
    "policy": policy,
    "portfolio": portfolio,
}
CheckRow: TypeAlias = tuple[object, ...]
CheckMap: TypeAlias = Mapping[str, tuple[CheckRow, ...]]


def _neutral_row(relation: str) -> dict[str, object]:
    row: dict[str, object] = {}
    for column, nullable, rule in generated.COLUMN_RULES_BY_RELATION[relation]:
        if nullable:
            row[column] = None
            continue
        kind = rule[0]
        row[column] = {
            "boolean": False,
            "date": date(2026, 8, 24),
            "integer": 0,
            "jsonb": {},
            "numeric": Decimal("0"),
            "text": "x",
            "text_array": (),
            "timestamptz": NOW,
            "uuid": VALID_UUID,
        }[kind]
    return row


def _true_checks(relation: str) -> tuple[CheckRow, ...]:
    return tuple(
        (name, digest, ("boolean", True))
        for name, digest, _ast in generated.CHECKS_BY_RELATION[relation]
    )


def _action_state() -> ActionCandidateState:
    return ActionCandidateState(
        id=ActionCandidateId(VALID_UUID),
        display_id="ACTION-001",
        site_id=SiteId(UUID("018f0000-0000-7000-8000-000000000002")),
        category_id=None,
        action_type=ActionCandidateActionType.CREATE,
        target_entity_type=ActionCandidateTargetEntityType.ARTICLE,
        target_entity_id=None,
        secondary_entity_id=None,
        source_signal="editorial-gap",
        expected_incremental_profit_jpy=None,
        urgency_score=Decimal("50"),
        confidence=Decimal("0.9000"),
        priority_score=Decimal("45"),
        status=ActionCandidateStatus.PROPOSED,
        rationale=ActionCandidateRationaleJson(
            FrozenJsonObject.from_mapping({"reason": "coverage gap"})
        ),
        generated_at=AwareUtcDateTime(NOW),
        expires_at=AwareUtcDateTime(LATER),
        decided_by_principal_id=None,
        decided_at=None,
        decision_note=None,
        created_at=AwareUtcDateTime(NOW),
        updated_at=AwareUtcDateTime(NOW),
        lock_version=AggregateVersion(0),
    )


def _action_row() -> dict[str, object]:
    relation, _direction, columns = generated.MAPPER_CALLABLES[
        "map_portfolio_action_candidate_to_row"
    ]
    assert relation == "portfolio.action_candidate"
    values = portfolio.map_portfolio_action_candidate_to_row(_action_state())
    return dict(zip(columns, values, strict=True))


def _assert_corruption(call: Callable[[], object]) -> None:
    with pytest.raises(PersistenceError) as captured:
        call()
    assert captured.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
    assert captured.value.__cause__ is None
    assert str(captured.value) == "STORAGE_CORRUPTION"


def test_generated_inventory_covers_exact_physical_519_checks() -> None:
    catalog_ir = generator._load_json(
        generator.REPO_ROOT,
        generator.OUTPUT_CATALOG_IR_PATH,
    )
    expected = tuple(
        sorted(
            (
                relation["relation"],
                check["name"],
                "EXACT_RUNTIME_AST",
                hashlib.sha256(check["expression"].encode("utf-8")).hexdigest(),
            )
            for relation in catalog_ir["relations"]
            for check in relation["check_constraints"]
        )
    )
    assert generated.CHECK_CONSTRAINT_COUNT == 519
    assert generated.CHECK_EVALUATOR_KIND == "EXACT_RUNTIME_AST"
    assert generated.CHECK_EVALUATOR_INVENTORY == expected
    assert len({row[:2] for row in expected}) == 519
    assert sum(map(len, generated.CHECKS_BY_RELATION.values())) == 519
    assert len(generated.CHECKS_BY_RELATION) == 104


def test_all_205_mapper_callables_have_one_guard_and_no_unhooked_mapper() -> None:
    observed: set[str] = set()
    for name, (relation, _direction, _columns) in generated.MAPPER_CALLABLES.items():
        schema = relation.split(".", 1)[0]
        function = getattr(MAPPER_MODULES[schema], name)
        observed.add(name)
        assert getattr(function, "__raos_physical_constraint_guard__", False) is True
        assert hasattr(function, "__wrapped__")
        assert (
            getattr(function.__wrapped__, "__raos_physical_constraint_guard__", False)
            is False
        )
        assert inspect.unwrap(function) is function.__wrapped__
    assert observed == set(generated.MAPPER_CALLABLES)
    assert len(observed) == generated.MAPPER_CALLABLE_COUNT == 205


def test_every_relation_and_check_position_is_runtime_enforced_by_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cast(CheckMap, generated.CHECKS_BY_RELATION)
    mutations = 0
    for relation, checks in original.items():
        row = _neutral_row(relation)
        for target_index in range(len(checks)):
            candidate: dict[str, tuple[CheckRow, ...]] = dict(original)
            candidate[relation] = tuple(
                (
                    name,
                    digest,
                    ("boolean", index != target_index),
                )
                for index, (name, digest, _ast) in enumerate(checks)
            )
            monkeypatch.setattr(runtime, "CHECKS_BY_RELATION", candidate)
            _assert_corruption(partial(runtime.validate_physical_row, relation, row))
            mutations += 1
    monkeypatch.setattr(runtime, "CHECKS_BY_RELATION", original)
    assert mutations == 519


@pytest.mark.parametrize(
    ("field", "tampered"),
    (
        ("confidence", Decimal("2.0000")),
        ("urgency_score", Decimal("101")),
        ("confidence", Decimal("0.12345")),
        ("expires_at", AwareUtcDateTime(NOW - timedelta(seconds=1))),
        (
            "decided_by_principal_id",
            PrincipalId(UUID("018f0000-0000-7000-8000-000000000003")),
        ),
        ("action_type", "UNRECOGNIZED"),
        ("rationale", ("not", "an", "object")),
    ),
)
def test_action_candidate_from_and_to_row_reject_same_physical_tamper(
    field: str,
    tampered: object,
) -> None:
    row = _action_row()
    row[field] = tampered
    from_row = cast(
        Callable[..., object], portfolio.map_portfolio_action_candidate_from_row
    )
    _assert_corruption(lambda: from_row(**row))

    state = _action_state()
    object.__setattr__(state, field, tampered)
    _assert_corruption(lambda: portfolio.map_portfolio_action_candidate_to_row(state))


def test_regex_length_and_numeric_precision_scale_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _neutral_row("portfolio.site")
    site.update(
        {
            "primary_domain": "example.test",
            "currency": "JPY",
            "status": "ACTIVE",
            "public_settings": {},
            "lock_version": 0,
        }
    )
    runtime.validate_physical_row("portfolio.site", site)
    site["currency"] = "jpy"
    _assert_corruption(lambda: runtime.validate_physical_row("portfolio.site", site))

    disclosure = _neutral_row("editorial.article_disclosure_context")
    disclosure.update(
        {
            "material_benefit_relationship": False,
            "benefit_types": (),
            "additional_disclosure_text": None,
            "disclosure_policy_version": "v1",
            "reviewed_by_principal_id": None,
            "reviewed_at": None,
        }
    )
    runtime.validate_physical_row("editorial.article_disclosure_context", disclosure)
    disclosure["disclosure_policy_version"] = ""
    _assert_corruption(
        lambda: runtime.validate_physical_row(
            "editorial.article_disclosure_context", disclosure
        )
    )

    relation = "ai.model_definition"
    original = cast(CheckMap, generated.CHECKS_BY_RELATION)
    candidate: dict[str, tuple[CheckRow, ...]] = dict(original)
    candidate[relation] = _true_checks(relation)
    monkeypatch.setattr(runtime, "CHECKS_BY_RELATION", candidate)
    model = _neutral_row(relation)
    model["input_price_per_million"] = Decimal("999999999999.99999999")
    runtime.validate_physical_row(relation, model)
    for invalid in (
        Decimal("0.000000001"),
        Decimal("1000000000000.00000000"),
    ):
        model["input_price_per_million"] = invalid
        _assert_corruption(lambda: runtime.validate_physical_row(relation, model))


def test_postgresql_three_value_quantifier_distinct_and_function_semantics() -> None:
    empty: dict[str, object] = {}
    null_comparison = ("binary", ">", ("null",), ("number", "0"))
    assert runtime._evaluate(null_comparison, empty) is None
    assert (
        runtime._evaluate(("binary", "or", ("boolean", True), null_comparison), empty)
        is True
    )
    assert (
        runtime._evaluate(("binary", "and", ("boolean", False), null_comparison), empty)
        is False
    )
    assert (
        runtime._evaluate(
            (
                "quantified",
                "=",
                "ANY",
                ("string", "ACTIVE"),
                ("array", (("string", "DRAFT"), ("string", "ACTIVE"))),
            ),
            empty,
        )
        is True
    )
    assert (
        runtime._evaluate(
            (
                "quantified",
                "<>",
                "ALL",
                ("string", "ACTIVE"),
                ("array", (("string", "DRAFT"), ("null",))),
            ),
            empty,
        )
        is None
    )
    assert (
        runtime._evaluate(("is_distinct", False, ("null",), ("string", "x")), empty)
        is True
    )
    assert (
        runtime._evaluate(
            (
                "call",
                "ai.canonical_metric_unit",
                (("string", "critical_claim_support_rate"),),
            ),
            empty,
        )
        == "ratio"
    )


def test_generator_rejects_any_unclassified_physical_check_syntax() -> None:
    with pytest.raises(generator.PersistenceBuildError) as captured:
        generator._CheckExpressionParser(
            "untrusted_extension(value)",
            frozenset({"value"}),
        ).parse()
    assert captured.value.code == "CHECK_EXPRESSION_UNSUPPORTED"

    expression = next(
        check["expression"]
        for relation in generator._load_json(
            generator.REPO_ROOT,
            generator.OUTPUT_CATALOG_IR_PATH,
        )["relations"]
        for check in relation["check_constraints"]
    )
    with pytest.raises(generator.PersistenceBuildError) as captured:
        generator._CheckExpressionParser(
            f"({expression}) OR untrusted_extension(value)",
            frozenset({"value", "status", "input_sha256"}),
        ).parse()
    assert captured.value.code == "CHECK_EXPRESSION_UNSUPPORTED"


def test_no_live_or_external_boundary_is_introduced() -> None:
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "exec(" not in source
    assert "sqlalchemy" not in source.lower().replace(
        "raos.adapters.persistence.sqlalchemy", ""
    )
    assert "requests" not in source
    assert "httpx" not in source
