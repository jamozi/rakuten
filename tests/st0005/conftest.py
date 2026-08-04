"""Shared ST-0005 status-validator fixtures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from scripts import build_st0005_status as status


TEST_EVIDENCE_PREFIX = "tests/st0005/fixtures/evidence/"
TEST_ARTIFACT_PREFIX = "tests/st0005/fixtures/artifacts/"


@pytest.fixture
def canonical_context() -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    registry, stories, suites, _ = status.canonical_inputs()
    state = status.initial_effective_state(registry, stories, suites)
    state["proposals"] = []
    state["applied_transitions"] = []
    return (
        state,
        status.index_records(
            stories, collection="stories", source="canonical story catalog"
        ),
        status.index_records(
            suites, collection="suites", source="canonical suite catalog"
        ),
    )


def repo_evidence(
    path: str,
    *,
    suite_id: str | None = None,
    environment: str | None = None,
    evidence_class: str | None = None,
    observed_at: str = "2026-08-01T08:00:00Z",
    expires_at: str | None = None,
) -> dict[str, Any]:
    resolved = status.REPO_ROOT / path
    result: dict[str, Any] = {
        "uri": f"repo://{path}",
        "sha256": status.sha256_file(resolved),
        "observed_at": observed_at,
    }
    if suite_id is not None:
        result.update(
            {
                "suite_id": suite_id,
                "environment": environment,
                "evidence_class": evidence_class,
            }
        )
    if expires_at is not None:
        result["expires_at"] = expires_at
    return result


def set_story_state(
    state: dict[str, Any],
    *,
    story_id: str,
    implementation_status: str,
    verification_status: str,
) -> None:
    row = next(row for row in state["stories"] if row["story_id"] == story_id)
    row["effective_implementation_status"] = implementation_status
    row["effective_verification_status"] = verification_status


def apply_request(
    state: dict[str, Any],
    story_index: dict[str, dict[str, Any]],
    *,
    source_implementation: str,
    source_verification: str,
    target_implementation: str,
    target_verification: str,
    evidence_class: str,
    environment: str,
    requester_type: str = "HUMAN",
    requester_id: str = "requester-human",
    story_id: str = "ST-0005",
    fixture_name: str | None = None,
    request_number: int = 1,
    requested_at: str = "2026-08-01T09:00:00Z",
    evidence_observed_at: str = "2026-08-01T08:00:00Z",
    evidence_expires_at: str | None = None,
    pr_observed_at: str = "2026-08-01T08:30:00Z",
    approval_decided_at: str = "2026-08-01T09:30:00Z",
    approval_artifact: str | None = None,
) -> dict[str, Any]:
    set_story_state(
        state,
        story_id=story_id,
        implementation_status=source_implementation,
        verification_status=source_verification,
    )
    suites = story_index[story_id]["test_suites"]
    fixture_names = {
        ("ST-0005", "CHANGE_PLAN", "NOT_EXECUTED"): "st0005-change-plan.yaml",
        ("ST-0005", "RUNTIME_SUITE_RESULT", "PARTIAL"): ("st0005-runtime-partial.yaml"),
        ("ST-0005", "RUNTIME_SUITE_RESULT", "FAIL"): "st0005-runtime-fail.yaml",
        ("ST-0005", "RUNTIME_SUITE_RESULT", "PASS"): "st0005-runtime-pass.yaml",
        ("ST-0005", "REGRESSION", "FAIL"): "st0005-regression.yaml",
        ("ST-0005", "EXPIRY", "NOT_EXECUTED"): "st0005-expiry.yaml",
        ("ST-0005", "ROLLBACK_DECISION", "PASS"): "st0005-rollback.yaml",
        ("ST-0005", "ROLLBACK_DECISION", "NOT_EXECUTED"): ("st0005-rollback.yaml"),
        ("ST-0005", "PRODUCTION_RELEASE", "PASS"): "st0005-production.yaml",
        ("ST-0005", "SCOPE_DECISION", "NOT_APPLICABLE"): "st0005-scope.yaml",
        ("ST-0005", "SCOPE_DECISION", "NOT_EXECUTED"): "st0005-scope.yaml",
        ("ST-0002", "CHANGE_PLAN", "NOT_EXECUTED"): "st0002-change-plan.yaml",
        ("ST-0002", "RUNTIME_SUITE_RESULT", "PARTIAL"): ("st0002-runtime-partial.yaml"),
        ("ST-0002", "REGRESSION", "FAIL"): "st0002-regression.yaml",
        ("ST-1206", "CHANGE_PLAN", "NOT_EXECUTED"): "st1206-change-plan.yaml",
        ("ST-0505", "RUNTIME_SUITE_RESULT", "PARTIAL"): ("st0505-runtime-partial.yaml"),
        ("ST-1606", "RUNTIME_SUITE_RESULT", "PARTIAL"): ("st1606-runtime-partial.yaml"),
    }
    if fixture_name is None:
        try:
            fixture_name = fixture_names[
                (story_id, evidence_class, target_verification)
            ]
        except KeyError as exc:
            raise AssertionError(
                "missing strict evidence fixture for "
                f"{story_id}/{evidence_class}/{target_verification}"
            ) from exc
    evidence_path = f"{TEST_EVIDENCE_PREFIX}{fixture_name}"
    if approval_artifact is None:
        approval_artifacts = [
            (
                f"{TEST_ARTIFACT_PREFIX}"
                "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e-"
                "manifest.json"
            ),
            (
                f"{TEST_ARTIFACT_PREFIX}"
                "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8-"
                "status-registry.yaml"
            ),
            (
                f"{TEST_ARTIFACT_PREFIX}"
                "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d-"
                "story-backlog.yaml"
            ),
            (
                f"{TEST_ARTIFACT_PREFIX}"
                "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
                "test-catalog.yaml"
            ),
            (
                f"{TEST_ARTIFACT_PREFIX}"
                "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b-"
                "status-taxonomy.yaml"
            ),
        ]
        approval_artifact = approval_artifacts[
            (request_number - 1) % len(approval_artifacts)
        ]
    pr_uri = f"https://github.com/example/raos/pull/{122 + request_number}"
    implementation_commit_sha = "1" * 40
    return {
        "document": {
            "id": (
                f"STATUS-{story_id.replace('-', '')}-APPLY-TEST-{request_number:03d}"
            ),
            "schema_version": 1,
            "intent": "APPLY",
        },
        "requested_by": {"id": requester_id, "actor_type": requester_type},
        "requested_at": requested_at,
        "reason": "Exercise a strict effective status transition in a local test.",
        "expected": {
            "canonical_base_sha256": status.canonical_base_digest(),
            "effective_status_sha256": status.effective_status_digest(state),
        },
        "changes": [
            {
                "story_id": story_id,
                "expected": {
                    "implementation_status": source_implementation,
                    "verification_status": source_verification,
                },
                "target": {
                    "implementation_status": target_implementation,
                    "verification_status": target_verification,
                },
                "evidence": [
                    repo_evidence(
                        evidence_path,
                        suite_id=suite_id,
                        environment=environment,
                        evidence_class=evidence_class,
                        observed_at=evidence_observed_at,
                        expires_at=evidence_expires_at,
                    )
                    for suite_id in suites
                ],
            }
        ],
        "pr_evidence": {
            "uri": pr_uri,
            "implementation_commit_sha": implementation_commit_sha,
            "sha256": status.pr_evidence_digest(pr_uri, implementation_commit_sha),
            "observed_at": pr_observed_at,
        },
        "approval": {
            "approver": {"id": "approver-human", "actor_type": "HUMAN"},
            "decision": "APPROVED",
            "reason": "A separate human reviewed the status evidence and approved it.",
            "decided_at": approval_decided_at,
            "evidence": repo_evidence(approval_artifact),
        },
    }


def clone(value: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(value)


__all__ = [
    "TEST_EVIDENCE_PREFIX",
    "TEST_ARTIFACT_PREFIX",
    "apply_request",
    "clone",
    "repo_evidence",
    "set_story_state",
]
