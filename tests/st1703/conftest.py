"""Isolated ST-1703 test path setup."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.domain.catalog.rakuten_item_search import (  # noqa: E402
    CanonicalItemSearchPage,
    PersistenceExecutionStatus,
    ProviderMode,
    RakutenItemSearchResult,
    RateLimitMetadata,
    RawResponseReceipt,
    StorageExecutionStatus,
)
from raos.domain.editorial.policy_engine import (  # noqa: E402
    ExecutionStatus,
    LocalEvaluationStatus,
    PolicyEvaluationResult,
)


ARTICLE_VERSION_ID = "ARTICLE-VERSION-1703"


@pytest.fixture
def eligible_policy_result() -> PolicyEvaluationResult:
    payload: dict[str, object] = {
        "article_version_id": ARTICLE_VERSION_ID,
        "authority": {
            "formal_test": "NOT_EXECUTED",
            "live_validation": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "production_eligible": False,
            "publication_authorized": False,
            "release": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
        },
        "contracts": {},
        "derived": {
            "local_eligibility": True,
            "policy_rules_passed": True,
            "post_publication_required_action": None,
            "predecessors_available": True,
            "quality_floors_met": True,
            "quality_gates_passed": True,
            "quality_threshold_met": True,
            "raw_quality_score": "100",
            "zero_tolerance_clear": True,
        },
        "evaluated_at": "2026-08-12T00:00:00.000000Z",
        "gates": [],
        "policy_assessments": [],
        "policy_findings": [],
        "predecessors": [],
        "profile": "ST0805_LOCAL_RESULT_V1",
        "quality_axes": [],
        "status": "EVALUATED",
        "waiver_attempts": [],
        "waiver_evaluations": [],
        "zero_tolerance": [],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return PolicyEvaluationResult(
        status=LocalEvaluationStatus.EVALUATED,
        input_findings=(),
        policy_findings=(),
        waiver_evaluations=(),
        raw_quality_score=Decimal("100"),
        quality_threshold_met=True,
        quality_floors_met=True,
        policy_rules_passed=True,
        zero_tolerance_clear=True,
        quality_gates_passed=True,
        predecessors_available=True,
        local_eligibility=True,
        post_publication_required_action=None,
        local_result_serialization_profile="ST0805_LOCAL_RESULT_V1",
        local_result_json=serialized,
        local_result_digest=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )


@pytest.fixture
def recorded_rakuten_result() -> RakutenItemSearchResult:
    observed_at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    rate = RateLimitMetadata(limit=100, remaining=99, reset_at=observed_at)
    receipt = RawResponseReceipt(
        artifact_id=UUID("018f3e90-7b00-7000-8000-000000001703"),
        sha256="a" * 64,
        byte_size=2,
        content_type="application/json",
        uri=None,
        storage_status=StorageExecutionStatus.NOT_EXECUTED,
    )
    page = CanonicalItemSearchPage(
        provider="RAKUTEN_ICHIBA",
        api_version="2026-07-01",
        request_sha256="b" * 64,
        raw_artifact=receipt,
        observed_at=observed_at,
        count=0,
        page=1,
        hits=1,
        page_count=0,
        items=(),
        warnings=(),
        provider_rate_limit=rate,
    )
    return RakutenItemSearchResult(
        provider_mode=ProviderMode.RECORDED_TEST_ONLY,
        page=page,
        rate=rate,
        storage_status=StorageExecutionStatus.NOT_EXECUTED,
        persistence_status=PersistenceExecutionStatus.NOT_EXECUTED,
        live_eligible=False,
    )
