"""Closed SQLAlchemy repository surface for the ST-0308 AI/POLICY slice."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from typing import cast

from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories import ai as ai_adapters
from raos.adapters.persistence.sqlalchemy.repositories import policy as policy_adapters
from raos.ports.ai import repositories as ai_ports
from raos.ports.policy import repositories as policy_ports


REPOSITORY_PAIRS = tuple(
    (getattr(ai_ports, name), getattr(ai_adapters, f"SqlAlchemy{name}"))
    for name in ai_ports.__all__
) + tuple(
    (getattr(policy_ports, name), getattr(policy_adapters, f"SqlAlchemy{name}"))
    for name in policy_ports.__all__
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


def _minimal_table(relation: str) -> Table:
    schema, name = relation.split(".", 1)
    return Table(name, MetaData(schema=schema), Column("id", String))


def test_all_18_protocols_and_70_methods_have_exact_concrete_shapes() -> None:
    assert len(REPOSITORY_PAIRS) == 18
    method_count = 0
    for protocol, concrete in REPOSITORY_PAIRS:
        protocol_methods = _public_methods(protocol)
        concrete_methods = _public_methods(concrete)
        assert protocol_methods.keys() == concrete_methods.keys()
        method_count += len(protocol_methods)
        for name, protocol_method in protocol_methods.items():
            concrete_method = concrete_methods[name]
            assert _parameter_shape(concrete_method) == _parameter_shape(
                protocol_method
            )
            source = inspect.getsource(concrete_method)
            assert "NotImplementedError" not in source
            assert " pass" not in source
            assert any(
                marker in source
                for marker in (
                    "select(",
                    "insert(",
                    "update(",
                    "_execute",
                    "_cas_",
                )
            )
    assert method_count == 70


def test_all_repositories_are_session_only_and_resolve_explicit_relations(
    monkeypatch: object,
) -> None:
    ai_relations: list[str] = []
    policy_relations: list[str] = []

    def ai_table(relation: str) -> Table:
        ai_relations.append(relation)
        return _minimal_table(relation)

    def policy_table(relation: str) -> Table:
        policy_relations.append(relation)
        return _minimal_table(relation)

    monkeypatch.setattr(ai_adapters, "_table", ai_table)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        policy_adapters, "_table", policy_table
    )
    session = Session()
    try:
        instances = [concrete(session) for _, concrete in REPOSITORY_PAIRS]
        assert len(instances) == 18
    finally:
        session.close()

    assert frozenset(ai_relations) == frozenset(
        {
            "ai.ai_attempt",
            "ai.ai_job",
            "ai.evaluation_case",
            "ai.evaluation_case_result",
            "ai.evaluation_dataset_version",
            "ai.evaluation_result",
            "ai.evaluation_run",
            "ai.evaluation_suite",
            "ai.human_evaluation",
            "ai.judge_calibration",
            "ai.model_definition",
            "ai.model_route_version",
            "ai.output_schema_version",
            "ai.prompt_version",
            "ai.release_approval",
            "ai.release_decision",
            "ai.task_definition",
            "ai.usage_cost",
        }
    )
    assert frozenset(policy_relations) == frozenset(
        {
            "policy.bundle_rule",
            "policy.finding",
            "policy.gate_decision",
            "policy.policy_bundle",
            "policy.quality_check_run",
            "policy.quality_score",
            "policy.rule_version",
            "policy.waiver",
        }
    )


def test_modules_expose_no_generic_or_destructive_repository_surface() -> None:
    for module in (ai_adapters, policy_adapters):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "delete" not in calls
        assert "text" not in calls
        assert "getattr(" not in source
        assert "hasattr(" not in source
        assert "automap" not in calls
        assert "reflect" not in attributes


def test_event_emitters_bind_every_exact_ai_and_policy_specialization_literal() -> None:
    expected = (
        (
            ai_adapters.SqlAlchemyAiJobRepository.add,
            ("jp.raos.ai.job_requested.v1",),
        ),
        (
            ai_adapters.SqlAlchemyAiJobRepository.transition,
            (
                "jp.raos.ai.job_succeeded.v1",
                "jp.raos.ai.policy_assist_completed.v1",
                "jp.raos.ai.job_failed.v1",
            ),
        ),
        (
            ai_adapters.SqlAlchemyEvaluationRunRepository.transition,
            ("jp.raos.ai.evaluation_completed.v2",),
        ),
        (
            ai_adapters.SqlAlchemyReleaseDecisionRepository.transition,
            (
                "jp.raos.ai.release_decision_approved.v1",
                "jp.raos.ai.release_decision_revoked.v1",
            ),
        ),
        (
            policy_adapters.SqlAlchemyPolicyBundleRepository.transition,
            ("jp.raos.policy.policy_bundle_activated.v1",),
        ),
    )
    for method, event_types in expected:
        source = inspect.getsource(method)
        assert "stage_registered_events(" in source
        for event_type in event_types:
            assert f'expected_event_type="{event_type}"' in source
