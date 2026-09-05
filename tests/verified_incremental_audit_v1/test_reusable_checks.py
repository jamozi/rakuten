"""Synthetic reviews share immutable execution outputs, not reviewer observations."""

import json

import pytest

from raos.application.editorial import verified_incremental_audit_v1 as audit
from scripts import raos_wordpress_verification as verification
from tests.verified_incremental_audit_v1 import test_contract as examples


EXPECTED = {
    "source_tree_sha256": "a" * 64,
    "selection_sha256": "c" * 64,
    "head_sha": "b" * 40,
}


def modern_pair():
    report, artifacts = examples.synthetic_pair()
    report["schema"] = audit.SCHEMA_V2
    artifacts["original-fast-log"] = b"Synthetic focused success\n"
    artifacts["original-fast-result"] = audit.canonical_json_bytes(
        {
            "schema": verification.SCHEMA,
            "check_id": "fast",
            "inputs": {
                key: value for key, value in EXPECTED.items() if key != "head_sha"
            },
            "exit_code": 0,
            "started_at": "2026-09-05T10:00:00Z",
            "captured_at": "2026-09-05T10:05:00Z",
            "output_sha256": examples.digest(artifacts["original-fast-log"]),
        }
    )
    artifacts["original-ci"] = audit.canonical_json_bytes(
        {
            "schema": "RAOS_WORDPRESS_REQUIRED_CI_V2",
            "repository": verification.REPOSITORY,
            "workflow": verification.WORKFLOW,
            "head_sha": EXPECTED["head_sha"],
            "conclusion": "success",
            "final_integration": "success",
        }
    )
    for row in report["rounds"]:
        for surface in row["surfaces"]:
            key = surface["evidence_id"]
            if key is None:
                continue
            proof = json.loads(artifacts[key])
            proof["schema"] = audit.EVIDENCE_SCHEMA_V2
            if surface["surface_id"] == "code":
                proof["attachments"] += [
                    "original-fast-log",
                    "original-fast-result",
                    "original-ci",
                ]
                proof["checks"] = {
                    "commands": [
                        {
                            "command_id": command,
                            "exit_code": 0,
                            "output_artifact_id": output,
                        }
                        for command, output in (
                            ("fast", "original-fast-result"),
                            ("required-ci", "original-ci"),
                        )
                    ]
                }
            artifacts[key] = audit.canonical_json_bytes(proof)
    report["evidence_artifact_hashes"] = {
        key: examples.digest(raw) for key, raw in artifacts.items()
    }
    return report, artifacts


def validate(report, artifacts):
    return audit.validate_verified_incremental_audit_v1(
        report,
        manifest_sha256=examples.MANIFEST,
        expected_artifact_hashes=examples.INPUTS,
        evidence_artifacts=artifacts,
        expected_backup_snapshot=examples.BACKUP_SNAPSHOT,
        expected_backup_article_slugs=examples.BACKUP_SLUGS,
        implementation_execution_ids=examples.IMPLEMENTERS,
        scope=examples.scope(),
        now=examples.NOW,
        verification_inputs=EXPECTED,
    )


def test_two_actual_review_observations_can_share_original_focused_and_ci_outputs():
    report, artifacts = modern_pair()
    result = validate(report, artifacts)
    assert result.to_document()["consecutive_clean_rounds"] == 2
    assert result.to_document()["publication_authority"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "failed",
        "changed_inputs",
        "changed_selection",
        "expired",
        "wrong_ci_commit",
        "ci_cancelled",
        "missing_output",
    ],
)
def test_rehashing_invalid_shared_results_cannot_pass(mutation):
    report, artifacts = modern_pair()
    key = (
        "original-ci"
        if mutation in {"wrong_ci_commit", "ci_cancelled"}
        else "original-fast-result"
    )
    result = json.loads(artifacts[key])
    if mutation == "failed":
        result["exit_code"] = 1
    elif mutation == "changed_inputs":
        result["inputs"]["source_tree_sha256"] = "f" * 64
    elif mutation == "changed_selection":
        result["inputs"]["selection_sha256"] = "f" * 64
    elif mutation == "expired":
        result["started_at"] = result["captured_at"] = "2026-09-04T00:00:00Z"
    elif mutation == "wrong_ci_commit":
        result["head_sha"] = "f" * 40
    elif mutation == "ci_cancelled":
        result["conclusion"] = "cancelled"
    else:
        result["output_sha256"] = "f" * 64
    artifacts[key] = audit.canonical_json_bytes(result)
    report["evidence_artifact_hashes"][key] = examples.digest(artifacts[key])
    with pytest.raises(audit.IncrementalAuditFailure):
        validate(report, artifacts)


def test_reusing_review_identity_remains_rejected():
    report, artifacts = modern_pair()
    report["rounds"][1]["execution_id"] = report["rounds"][0]["execution_id"]
    with pytest.raises(audit.IncrementalAuditFailure, match="ROUND_NOT_INDEPENDENT"):
        validate(report, artifacts)
