"""Wave 2A repository coverage and closed-adapter boundary tests."""

from __future__ import annotations

import ast
import inspect

import pytest
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.catalog import (
    SqlAlchemyCatalogRepositories,
)
from raos.adapters.persistence.sqlalchemy.iam import SqlAlchemyIamRepositories
from raos.adapters.persistence.sqlalchemy.ops import SqlAlchemyOpsRepositories
from raos.adapters.persistence.sqlalchemy.portfolio import (
    SqlAlchemyPortfolioRepositories,
)
from raos.adapters.persistence.sqlalchemy.repositories import (
    catalog as catalog_adapters,
)
from raos.adapters.persistence.sqlalchemy.repositories import iam as iam_adapters
from raos.adapters.persistence.sqlalchemy.repositories import ops as ops_adapters
from raos.adapters.persistence.sqlalchemy.repositories import (
    portfolio as portfolio_adapters,
)
from raos.ports.catalog import repositories as catalog_ports
from raos.ports.iam import repositories as iam_ports
from raos.ports.ops import repositories as ops_ports
from raos.ports.portfolio import repositories as portfolio_ports


REPOSITORY_PAIRS = (
    (ops_ports.JobRepository, ops_adapters.SqlAlchemyJobRepository),
    (
        ops_ports.ObjectArtifactRepository,
        ops_adapters.SqlAlchemyObjectArtifactRepository,
    ),
    (
        ops_ports.RuntimeSettingRepository,
        ops_adapters.SqlAlchemyRuntimeSettingRepository,
    ),
    (iam_ports.PrincipalRepository, iam_adapters.SqlAlchemyPrincipalRepository),
    (
        iam_ports.RoleCatalogRepository,
        iam_adapters.SqlAlchemyRoleCatalogRepository,
    ),
    (
        iam_ports.PrincipalRoleAssignmentRepository,
        iam_adapters.SqlAlchemyPrincipalRoleAssignmentRepository,
    ),
    (
        iam_ports.SessionRevocationRepository,
        iam_adapters.SqlAlchemySessionRevocationRepository,
    ),
    (
        iam_ports.BreakGlassRecordRepository,
        iam_adapters.SqlAlchemyBreakGlassRecordRepository,
    ),
    (portfolio_ports.SiteRepository, portfolio_adapters.SqlAlchemySiteRepository),
    (
        portfolio_ports.CategoryRepository,
        portfolio_adapters.SqlAlchemyCategoryRepository,
    ),
    (
        portfolio_ports.IntentClusterRepository,
        portfolio_adapters.SqlAlchemyIntentClusterRepository,
    ),
    (
        portfolio_ports.KeywordRepository,
        portfolio_adapters.SqlAlchemyKeywordRepository,
    ),
    (
        portfolio_ports.OpportunityAssessmentRepository,
        portfolio_adapters.SqlAlchemyOpportunityAssessmentRepository,
    ),
    (
        portfolio_ports.ActionCandidateRepository,
        portfolio_adapters.SqlAlchemyActionCandidateRepository,
    ),
    (
        catalog_ports.ProviderEndpointRepository,
        catalog_adapters.SqlAlchemyProviderEndpointRepository,
    ),
    (
        catalog_ports.IngestionRequestRepository,
        catalog_adapters.SqlAlchemyIngestionRequestRepository,
    ),
    (
        catalog_ports.RakutenGenreRepository,
        catalog_adapters.SqlAlchemyRakutenGenreRepository,
    ),
    (catalog_ports.ShopRepository, catalog_adapters.SqlAlchemyShopRepository),
    (
        catalog_ports.CanonicalProductRepository,
        catalog_adapters.SqlAlchemyCanonicalProductRepository,
    ),
    (
        catalog_ports.ProductCandidateRepository,
        catalog_adapters.SqlAlchemyProductCandidateRepository,
    ),
    (
        catalog_ports.GroupingDecisionRepository,
        catalog_adapters.SqlAlchemyGroupingDecisionRepository,
    ),
    (
        catalog_ports.AttributeDefinitionRepository,
        catalog_adapters.SqlAlchemyAttributeDefinitionRepository,
    ),
    (catalog_ports.OfferRepository, catalog_adapters.SqlAlchemyOfferRepository),
    (
        catalog_ports.SafeOfferCurrentReader,
        catalog_adapters.SqlAlchemySafeOfferCurrentReader,
    ),
)


def _public_methods(value: type[object]) -> dict[str, object]:
    return {
        name: member
        for name, member in value.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def _parameter_shape(
    function: object,
) -> tuple[tuple[str, inspect._ParameterKind], ...]:
    return tuple(
        (parameter.name, parameter.kind)
        for parameter in inspect.signature(function).parameters.values()
    )


def test_all_w2a_protocol_methods_have_exact_concrete_method_shapes() -> None:
    assert len(REPOSITORY_PAIRS) == 24
    method_count = 0
    for protocol, concrete in REPOSITORY_PAIRS:
        protocol_methods = _public_methods(protocol)
        concrete_methods = _public_methods(concrete)
        assert protocol_methods.keys() <= concrete_methods.keys()
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
                    "self.get(",
                    "self._load(",
                    "register_pending_events(",
                )
            )
    assert method_count == 76


@pytest.mark.parametrize(
    ("bundle", "expected_attributes"),
    (
        (
            SqlAlchemyOpsRepositories,
            {"jobs", "object_artifacts", "runtime_settings"},
        ),
        (
            SqlAlchemyIamRepositories,
            {
                "break_glass_records",
                "principals",
                "role_assignments",
                "role_catalog",
                "session_revocations",
            },
        ),
        (
            SqlAlchemyPortfolioRepositories,
            {
                "action_candidates",
                "categories",
                "intent_clusters",
                "keywords",
                "opportunity_assessments",
                "sites",
            },
        ),
        (
            SqlAlchemyCatalogRepositories,
            {
                "attribute_definitions",
                "canonical_products",
                "grouping_decisions",
                "ingestion_requests",
                "offers",
                "product_candidates",
                "provider_endpoints",
                "rakuten_genres",
                "safe_offer_current",
                "shops",
            },
        ),
    ),
)
def test_session_only_module_composition_constructs_all_repositories(
    bundle: type[object], expected_attributes: set[str]
) -> None:
    session = Session()
    try:
        repositories = bundle(session)
        assert set(repositories.__slots__) == expected_attributes
        assert all(hasattr(repositories, name) for name in expected_attributes)
    finally:
        session.close()


def test_catalog_view_is_resolved_only_from_read_only_mapping() -> None:
    source = inspect.getsource(catalog_adapters.SqlAlchemySafeOfferCurrentReader)
    assert '_view("catalog.v_safe_offer_current")' in source
    assert '_table("catalog.v_safe_offer_current")' not in source


def test_concrete_repository_modules_have_no_generic_or_destructive_surface() -> None:
    for module in (
        ops_adapters,
        iam_adapters,
        portfolio_adapters,
        catalog_adapters,
    ):
        source = inspect.getsource(module)
        forbidden_sql_calls = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "delete" not in forbidden_sql_calls
        assert "text" not in forbidden_sql_calls
        assert "getattr(" not in source
        assert "hasattr(" not in source
        assert "automap" not in source
        assert "reflect(" not in source
