"""Static architecture, no-I/O, redaction, and closed-policy assertions."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
import pickle

import pytest

from conftest import IDENTITY, NOW, quote, reservation_request, routing_service
from raos.domain.ai.routing import (
    AuthorizedRouteReservation,
    BudgetReservation,
    FallbackPolicy,
    ReservationIntent,
    RouteIdentity,
    RouteReservationRequest,
    RoutingFailure,
    RoutingFailureCode,
    SyntheticRouteCertification,
    SyntheticRouteQuote,
)
from raos.ports.ai_routing import (
    DevelopmentAiControlPort,
    SyntheticRouteEligibilityPort,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOMAIN = Path("python/raos/domain/ai/routing.py")
PORTS = Path("python/raos/ports/ai_routing.py")
APPLICATION_INIT = Path("python/raos/application/ai/__init__.py")
APPLICATION = Path("python/raos/application/ai/routing.py")
ADAPTER = Path("python/raos/adapters/development_ai_controls.py")
OWNED_SOURCE = (DOMAIN, PORTS, APPLICATION_INIT, APPLICATION, ADAPTER)


@contextmanager
def _reraising_context() -> Iterator[None]:
    try:
        yield
    except Exception:
        raise


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _calls(path: Path) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def test_dependencies_point_inward_and_domain_is_stdlib_only() -> None:
    assert not {name for name in _imports(DOMAIN) if name.startswith("raos.")}
    assert {name for name in _imports(PORTS) if name.startswith("raos.")} == {
        "raos.domain.ai.routing"
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ai.contracts",
        "raos.domain.ai.routing",
        "raos.ports.ai_routing",
        "raos.ports.task_registry",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ai.routing",
    }


def test_runtime_slice_has_no_provider_sdk_or_external_io_surface() -> None:
    all_imports = set().union(*(_imports(path) for path in OWNED_SOURCE))
    forbidden_roots = {
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "starlette",
        "subprocess",
        "urllib",
    }
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }

    forbidden_calls = {
        "Client",
        "Thread",
        "create_task",
        "execute",
        "getenv",
        "open",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "sleep",
        "urlopen",
    }
    assert (
        set()
        .union(*(_calls(path) for path in OWNED_SOURCE))
        .isdisjoint(forbidden_calls)
    )


def test_no_retry_fallback_reset_half_open_or_background_state_machine() -> None:
    prohibited = {
        "background",
        "fallback",
        "half_open",
        "halfopen",
        "reset",
        "retry",
    }
    defined_names = {
        node.name.lower()
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined_names.isdisjoint(prohibited)
    assert not any(
        isinstance(node, ast.AsyncFunctionDef)
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
    )
    assert not any(
        isinstance(node, (ast.While, ast.AsyncFor))
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
    )


def test_source_contains_no_real_model_price_fx_or_provider_choice() -> None:
    source = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8").lower()
        for path in OWNED_SOURCE
    )
    for prohibited in (
        "gpt-",
        "input_per_million",
        "output_per_million",
        "jpy_per_native_unit",
        "exchange_rate",
        "fx_rate",
        "api_key",
    ):
        assert prohibited not in source


def test_quote_reservation_and_authorization_displays_are_redacted_and_immutable() -> (
    None
):
    service, _, _ = routing_service()
    route_quote = quote()
    authorization = service.authorize_and_reserve(
        request=reservation_request(route_quote=route_quote),
        now=NOW,
    )

    for value in (
        IDENTITY,
        route_quote,
        authorization,
        authorization.reservation,
    ):
        assert "synthetic.model.local.v1" not in repr(value)
        assert "synthetic.quote.local.v1" not in repr(value)
        assert "synthetic.model.local.v1" not in str(value)
        assert "synthetic.quote.local.v1" not in str(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)

    with pytest.raises(FrozenInstanceError):
        route_quote.estimated_cost_jpy = 999  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        authorization.reservation.reserved_jpy = 999  # type: ignore[misc]


def test_domain_route_values_have_no_prompt_or_content_payload_field() -> None:
    for value_type in (
        RouteIdentity,
        SyntheticRouteCertification,
        SyntheticRouteQuote,
        RouteReservationRequest,
        ReservationIntent,
        BudgetReservation,
        AuthorizedRouteReservation,
    ):
        field_names = set(value_type.__annotations__)
        assert field_names.isdisjoint(
            {"content", "messages", "prompt", "raw_content", "source_packet"}
        )


def test_inward_protocols_are_satisfied_by_development_adapters() -> None:
    _, eligibility, controls = routing_service()
    assert isinstance(eligibility, SyntheticRouteEligibilityPort)
    assert isinstance(controls, DevelopmentAiControlPort)


def test_authorized_result_makes_zero_fallbacks_explicit() -> None:
    service, _, _ = routing_service()
    authorization = service.authorize_and_reserve(
        request=reservation_request(), now=NOW
    )
    assert authorization.fallback_policy is FallbackPolicy.DENY_ALL
    assert authorization.max_fallbacks == 0
    assert not hasattr(authorization, "fallback_model_id")


def test_sanitized_failure_is_immutable_and_retains_only_stable_code() -> None:
    error = RoutingFailure(RoutingFailureCode.BUDGET_EXCEEDED)
    assert error.args == (RoutingFailureCode.BUDGET_EXCEEDED.value,)
    assert vars(error) == {}
    with pytest.raises(AttributeError):
        error.code = RoutingFailureCode.INVALID_REQUEST  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(error)


def test_sanitized_failure_survives_standard_context_manager_reraise() -> None:
    with pytest.raises(RoutingFailure) as captured:
        with _reraising_context():
            raise RoutingFailure(RoutingFailureCode.CONTROL_FAILURE)
    assert captured.value.code is RoutingFailureCode.CONTROL_FAILURE
    assert captured.value.__cause__ is None
