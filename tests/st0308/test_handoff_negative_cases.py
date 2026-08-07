"""Independent negative cases for the bounded, fail-closed preflight."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from conftest import (
    CONTRACT_PATH,
    EXPECTED_HANDOFF_BYTES,
    EXPECTED_YAML_DEPTH,
    EXPECTED_YAML_NODES,
    REPOSITORY_ROOT,
    VALIDATOR,
    clone_candidate,
    disposable_repository_root,
    load_validator_module,
    report,
    run_validator,
    snapshot_repository_tree,
)


def _write_yaml(tmp_path: Path, value: object, name: str = "candidate.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _write_bytes(tmp_path: Path, value: bytes, name: str = "candidate.yaml") -> Path:
    path = tmp_path / name
    path.write_bytes(value)
    return path


def _run_candidate(
    tmp_path: Path,
    candidate: dict[str, object],
    name: str = "candidate.yaml",
) -> dict[str, object]:
    path = _write_yaml(tmp_path, candidate, name)
    process = run_validator(path)
    assert process.returncode == 1
    return report(process)


def _write_candidate_at_exact_size(
    tmp_path: Path,
    candidate: dict[str, object],
    size: int,
) -> Path:
    base = yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False).encode(
        "utf-8"
    )
    assert len(base) < size
    path = tmp_path / f"candidate-{size}.yaml"
    path.write_bytes(base + b"#" + b"x" * (size - len(base) - 1))
    assert path.stat().st_size == size
    return path


def _nested_mapping_yaml(nested_maps: int) -> bytes:
    lines = ["root:"]
    for index in range(nested_maps):
        lines.append(f"{'  ' * (index + 1)}level_{index}:")
    lines.append(f"{'  ' * (nested_maps + 1)}value: 1")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _node_budget_yaml(value_count: int) -> bytes:
    values = ",".join("0" for _ in range(value_count))
    return f"root: [{values}]\n".encode("utf-8")


def _member_ref(candidate: dict[str, object]) -> dict[str, str]:
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    return next(row for row in refs if "archive_path" in row)  # type: ignore[return-value]


@pytest.mark.parametrize(
    "raw",
    [
        "DESIGN_HANDOFF_V1:\n  authority: {}\n  authority: {}\n",
        "DESIGN_HANDOFF_V1: &handoff {}\n",
        "DESIGN_HANDOFF_V1: *handoff\n",
        "DESIGN_HANDOFF_V1: {}\n---\nDESIGN_HANDOFF_V1: {}\n",
        "!unknown DESIGN_HANDOFF_V1: {}\n",
    ],
)
def test_yaml_safety_failures_are_candidate_failures(tmp_path: Path, raw: str) -> None:
    path = _write_bytes(tmp_path, raw.encode("utf-8"), "unsafe.yaml")
    process = run_validator(
        path,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    result = report(process)
    assert process.returncode == 1
    assert result["status"] == "FAIL"
    assert result["candidate_sha256"]
    assert result["candidate_sha256_complete"] is True
    assert result["implementation_authority"] == "NOT_GRANTED"


def test_non_utf8_and_nul_candidates_are_rejected(tmp_path: Path) -> None:
    for content, code in ((b"\xff", "yaml_non_utf8"), (b"\x00", "yaml_nul_byte")):
        path = _write_bytes(tmp_path, content, f"{code}.yaml")
        result = report(run_validator(path))
        assert result["status"] == "FAIL"
        assert result["candidate_sha256"]
        assert result["checks"]["candidate_yaml_safety"]["reason_codes"] == [code]


def test_oversized_candidate_reports_a_bounded_digest(tmp_path: Path) -> None:
    limit = EXPECTED_HANDOFF_BYTES
    path = _write_bytes(tmp_path, b"x" * (limit + 1), "oversized.yaml")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    result = report(run_validator(path, expected_sha256=expected))
    assert result["status"] == "FAIL"
    assert result["checks"]["candidate_yaml_safety"]["reason_codes"] == [
        "handoff_oversized"
    ]
    assert result["candidate_sha256"]
    assert result["candidate_sha256_complete"] is False
    assert result["candidate_bytes_read"] == limit + 1
    assert result["candidate_sha256"] == hashlib.sha256(b"x" * (limit + 1)).hexdigest()
    assert result["checks"]["expected_sha256_match"]["status"] == "FAIL"


def test_exact_handoff_limit_passes_and_first_over_is_bounded_failure(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    exact_path = _write_candidate_at_exact_size(
        tmp_path,
        pass_candidate,
        EXPECTED_HANDOFF_BYTES,
    )
    exact = report(run_validator(exact_path))
    assert exact["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"
    assert exact["candidate_bytes_read"] == EXPECTED_HANDOFF_BYTES
    assert exact["candidate_sha256_complete"] is True

    oversized_path = _write_bytes(
        tmp_path,
        b"x" * (EXPECTED_HANDOFF_BYTES + 1),
        "first-over-handoff.yaml",
    )
    oversized = report(run_validator(oversized_path))
    assert oversized["checks"]["candidate_yaml_safety"]["reason_codes"] == [
        "handoff_oversized"
    ]
    assert oversized["candidate_bytes_read"] == EXPECTED_HANDOFF_BYTES + 1


@pytest.mark.parametrize("candidate", [True, False])
def test_yaml_exact_depth_and_node_limits_reject_first_over_before_construction(
    monkeypatch: pytest.MonkeyPatch,
    candidate: bool,
) -> None:
    validator = load_validator_module()
    failure_type = validator.CandidateFailure if candidate else validator.TrustedFailure
    depth_code = "yaml_depth_limit" if candidate else "trusted_yaml_depth_limit"
    node_code = "yaml_node_limit" if candidate else "trusted_yaml_node_limit"

    exact_depth = validator._load_yaml_mapping(
        _nested_mapping_yaml(EXPECTED_YAML_DEPTH - 2),
        candidate=candidate,
        depth_limit=EXPECTED_YAML_DEPTH,
        node_limit=EXPECTED_YAML_NODES,
    )
    assert isinstance(exact_depth, dict)
    over_depth = _nested_mapping_yaml(EXPECTED_YAML_DEPTH - 1)
    mapping_tag = validator.yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
    with monkeypatch.context() as context:

        def unexpected_construction(*args: object, **kwargs: object) -> object:
            raise AssertionError(
                "mapping construction occurred before budget rejection"
            )

        context.setitem(
            validator.UniqueKeyLoader.yaml_constructors,
            mapping_tag,
            unexpected_construction,
        )
        with pytest.raises(failure_type) as depth_error:
            validator._load_yaml_mapping(
                over_depth,
                candidate=candidate,
                depth_limit=EXPECTED_YAML_DEPTH,
                node_limit=EXPECTED_YAML_NODES,
            )
    assert depth_error.value.code == depth_code

    exact_nodes = validator._load_yaml_mapping(
        _node_budget_yaml(EXPECTED_YAML_NODES - 3),
        candidate=candidate,
        depth_limit=EXPECTED_YAML_DEPTH,
        node_limit=EXPECTED_YAML_NODES,
    )
    assert isinstance(exact_nodes, dict)
    over_nodes = _node_budget_yaml(EXPECTED_YAML_NODES - 2)
    with monkeypatch.context() as context:
        context.setitem(
            validator.UniqueKeyLoader.yaml_constructors,
            mapping_tag,
            unexpected_construction,
        )
        with pytest.raises(failure_type) as node_error:
            validator._load_yaml_mapping(
                over_nodes,
                candidate=candidate,
                depth_limit=EXPECTED_YAML_DEPTH,
                node_limit=EXPECTED_YAML_NODES,
            )
    assert node_error.value.code == node_code


def test_yaml_second_document_is_rejected_before_constructing_its_large_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = load_validator_module()
    mapping_tag = validator.yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
    original_constructor = validator.UniqueKeyLoader.yaml_constructors[mapping_tag]
    constructed = 0

    def counting_constructor(
        loader: object,
        node: object,
        deep: bool = False,
    ) -> dict[object, object]:
        nonlocal constructed
        constructed += 1
        return original_constructor(loader, node, deep=deep)

    raw = b"{}\n---\n" + _node_budget_yaml(EXPECTED_YAML_NODES)
    with monkeypatch.context() as context:
        context.setitem(
            validator.UniqueKeyLoader.yaml_constructors,
            mapping_tag,
            counting_constructor,
        )
        with pytest.raises(validator.CandidateFailure) as error:
            validator._load_yaml_mapping(
                raw,
                candidate=True,
                depth_limit=EXPECTED_YAML_DEPTH,
                node_limit=EXPECTED_YAML_NODES,
            )
    assert error.value.code == "yaml_multiple_documents"
    assert constructed == 1


def test_harmless_extra_payload_keys_are_allowed(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["review_note"] = {  # type: ignore[index]
        "format": "future-compatible"
    }
    path = _write_yaml(tmp_path, candidate)
    process = run_validator(path)
    result = report(process)
    assert process.returncode == 0
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_root_ordinary_sections_are_not_recursed_for_boundary_claims(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    payload = candidate["DESIGN_HANDOFF_V1"]  # type: ignore[index]
    payload["decision"]["domain_fields"] = {  # type: ignore[index]
        "status": "FindingStatus",
        "approved_at": "datetime | None",
        "completion": "DomainCompletion",
    }
    payload["review_packet"] = [  # type: ignore[index]
        {"status": "APPROVED", "approved_at": "ordinary nested design data"}
    ]
    result = report(
        run_validator(_write_yaml(tmp_path, candidate, "ordinary-scope.yaml"))
    )
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_boundary_aliases_accept_only_declared_non_authoritative_forms(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    authority = candidate["DESIGN_HANDOFF_V1"]["authority"]  # type: ignore[index]
    approval = candidate["DESIGN_HANDOFF_V1"]["approval"]  # type: ignore[index]
    authority["StAtUs"] = "proposal"  # type: ignore[index]
    approval["owner approval"] = "PENDING"  # type: ignore[index]
    approval["APPROVED-BY"] = None  # type: ignore[index]
    approval["approved timestamp"] = None  # type: ignore[index]
    approval["Implementation Authority"] = "not-granted"  # type: ignore[index]
    approval["canonical-reconciliation"] = "not executed"  # type: ignore[index]
    approval["review_note"] = "AUTHORIZED GRANTED COMPLETE"  # type: ignore[index]
    path = _write_yaml(tmp_path, candidate, "safe-boundary-aliases.yaml")
    result = report(run_validator(path))
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_boundary_prose_is_not_scanned_lexically(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["approval"]["review_packet"] = [  # type: ignore[index]
        [
            {
                "note": "APPROVED AUTHORIZED COMPLETE GRANTED",
                "details": [{"text": "owner approval is not an instruction"}],
            }
        ]
    ]
    result = report(
        run_validator(_write_yaml(tmp_path, candidate, "boundary-prose.yaml"))
    )
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_mixed_case_separator_boundary_section_is_recognized(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    payload = candidate["DESIGN_HANDOFF_V1"]  # type: ignore[index]
    payload.pop("approval")
    payload["App-roval"] = {"StAtUs": "PENDING"}
    result = report(
        run_validator(_write_yaml(tmp_path, candidate, "mixed-section.yaml"))
    )
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_non_mapping_root_boundary_section_fails(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"].pop("approval")  # type: ignore[index]
    candidate["DESIGN_HANDOFF_V1"]["App-roval"] = "PENDING"  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, "scalar-section.yaml")
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "optional_boundary_section_invalid"
    ]


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("authority", "STATUS", "APPROVED"),
        ("authority", "authority status", "AUTHORIZED"),
        ("approval", "approval-status", "COMPLETE"),
        ("approval", "implementation-authority", "GRANTED"),
        ("approval", "authorityGranted", True),
        ("approval", "owner approval", "APPROVED"),
        ("approval", "approved by", "owner@example.invalid"),
        ("approval", "approved_at", "2026-08-05T00:00:00Z"),
        ("approval", "timestamp", "2026-08-05T00:00:00Z"),
        ("approval", "canonical reconciliation", "COMPLETE"),
    ],
)
def test_boundary_aliases_reject_authority_or_approval_claims(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    section: str,
    key: str,
    value: object,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][section][key] = value  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, f"boundary-{key}.yaml")
    assert result["status"] == "FAIL"
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"
    assert (
        "boundary_claim_invalid"
        in result["checks"]["candidate_shape_and_story"]["reason_codes"]
    )


@pytest.mark.parametrize(
    "nested",
    [
        {"review": {"Implementation Authority": "AUTHORIZED"}},
        {"review": [{"status": "APPROVED"}]},
        {"review": {"canonical_reconciliation": {"status": "COMPLETE"}}},
    ],
)
def test_nested_boundary_claims_cannot_self_grant(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    nested: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["approval"]["nested"] = nested  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, "nested-boundary.yaml")
    assert result["status"] == "FAIL"
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("status", "APPROVED"),
        ("IMPLEMENTATION__AUTHORITY", "GRANTED"),
        ("approved", "APPROVED"),
        ("authorization", "AUTHORIZED"),
        ("authorisation", "AUTHORISED"),
        ("completion", "COMPLETE"),
        ("completed", "COMPLETED"),
        ("grant", "GRANTED"),
        ("is_authorized", True),
        ("canonical-reconciliation-status", "COMPLETE"),
        ("authorization_granted", True),
        ("approval_granted", True),
        ("completion_authorized", True),
        ("implementation_is_authorized", True),
        ("canonical_reconciliation_is_approved", True),
        ("is_canonical_reconciliation_status", True),
        ("owner_approval_is_authorized", True),
        ("is_implementation_authority", True),
        ("is_implementation_status", True),
        ("is_canonical_reconciliation", True),
        ("is_status", True),
        ("is_approval_status", True),
    ],
)
def test_root_and_separator_normalized_boundary_claims_fail(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    key: str,
    value: object,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = value  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, f"root-boundary-{key}.yaml")
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("implementation_authorized_status", "APPROVED"),
        ("implementation_is_authorized_status", "APPROVED"),
        ("is_implementation_authorized_status", "APPROVED"),
        ("authorization_granted_status", "APPROVED"),
        ("implementation_approved_by", "owner@example.invalid"),
        ("canonical_reconciliation_approved_at", "2026-08-05T00:00:00Z"),
        ("owner_approval_authorized_by", "owner@example.invalid"),
        ("implementation_authorized_timestamp", "2026-08-05T00:00:00Z"),
        ("is_authorization_implementation", True),
        ("authorization_is_implementation", True),
        ("approval_is_authorization", True),
        ("canonical_reconciliation_is_approval", True),
    ],
)
def test_complete_alias_closure_parent_probes_fail(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    key: str,
    value: object,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = value  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, f"closure-parent-{key}.yaml")
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


@pytest.mark.parametrize(
    "key",
    [
        "implementation-authorized-status",
        "implementation authorized status",
        "implementation__authorized__status",
        "implementationAuthorizedStatus",
        "ImplementationAuthorizedStatus",
        "IMPLEMENTATION_AUTHORIZED_STATUS",
        "implementationauthorizedstatus",
    ],
)
def test_complete_alias_closure_normalization_surfaces_fail(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    key: str,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = "APPROVED"  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, f"closure-normalized-{key}.yaml")
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


def test_case_normalized_approval_section_claim_fails(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["Approval"] = {  # type: ignore[index]
        "StAtUs": "APPROVED",
    }
    result = _run_candidate(tmp_path, candidate, "case-approval-section.yaml")
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "optional_boundary_section_duplicate"
    ]


def test_boundary_claims_traverse_mapping_list_list_mapping(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["approval"]["review_packet"] = [  # type: ignore[index]
        [{"deep": {"Is__Authorised": "AUTHORISED"}}]
    ]
    result = _run_candidate(tmp_path, candidate, "arbitrary-depth-boundary.yaml")
    assert result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


@pytest.mark.parametrize(
    "key",
    [
        "automated_pass_authorizes_implementation",
        "authority_granted",
        "authorized",
        "authorised",
        "is_granted",
        "is_approval",
        "is_authorization",
        "authorization_granted",
        "approval_granted",
        "completion_authorized",
        "implementation_is_authorized",
        "canonical_reconciliation_is_approved",
        "canonical_reconciliation_is_approval",
        "approval_is_authorization",
        "is_authorization_implementation",
        "authorization_is_implementation",
        "owner_approval_is_authorized",
        "is_implementation_authority",
        "is_canonical_reconciliation",
        "is_owner_approved",
    ],
)
def test_explicit_false_denial_aliases_are_allowed(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    key: str,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = False  # type: ignore[index]
    process = run_validator(_write_yaml(tmp_path, candidate, f"false-{key}.yaml"))
    result = report(process)
    assert process.returncode == 0
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


@pytest.mark.parametrize(
    "key",
    [
        "status",
        "timestamp",
        "approved_at",
        "is_status",
        "is_implementation_status",
        "is_approval_status",
        "is_canonical_reconciliation_status",
    ],
)
def test_boolean_true_or_generic_false_boundary_values_fail(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    key: str,
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = False  # type: ignore[index]
    false_result = _run_candidate(tmp_path, candidate, f"false-{key}.yaml")
    assert false_result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]

    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"][key] = True  # type: ignore[index]
    true_result = _run_candidate(tmp_path, candidate, f"true-{key}.yaml")
    assert true_result["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]


def test_safe_denial_strings_and_nulls_keep_field_specific_rules(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["implementation_authority"] = "NOT_GRANTED"  # type: ignore[index]
    safe = report(run_validator(_write_yaml(tmp_path, candidate, "not-granted.yaml")))
    assert safe["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"

    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["implementation_authority"] = "GRANTED"  # type: ignore[index]
    dangerous = _run_candidate(tmp_path, candidate, "granted.yaml")
    assert dangerous["checks"]["candidate_shape_and_story"]["reason_codes"] == [
        "boundary_claim_invalid"
    ]

    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["approved_at"] = None  # type: ignore[index]
    null_time = report(
        run_validator(_write_yaml(tmp_path, candidate, "null-time.yaml"))
    )
    assert null_time["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"


def test_missing_or_wrong_mandatory_story_shape_fails(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["rationale"] = []  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, "empty.yaml")
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"

    candidate = clone_candidate(pass_candidate)
    candidate["DESIGN_HANDOFF_V1"]["approved_story"]["required_suites"] = "TST-005"  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, "suite-type.yaml")
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"


def test_source_traversal_and_wrong_repository_hash_fail(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    for current_v3_path in (
        "changes/st-0308/PRO-CORRECTION-REQUEST-v3.md",
        "changes/st-0308/CANONICAL-RECONCILIATION-v3.md",
        "changes/st-0308/IMPLEMENTATION-READINESS-v3.md",
    ):
        candidate = clone_candidate(pass_candidate)
        refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
            "required_v3_authority_inputs"
        ]  # type: ignore[index]
        refs[:] = [  # type: ignore[index]
            row for row in refs if row.get("path") != current_v3_path
        ]
        result = _run_candidate(
            tmp_path,
            candidate,
            f"missing-{Path(current_v3_path).name}.yaml",
        )
        assert result["checks"]["source_design_refs"]["reason_codes"] == [
            "source_reference_minimum_missing"
        ]

    candidate = clone_candidate(pass_candidate)
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    refs.append(  # type: ignore[union-attr]
        {
            "path": "changes/st-0308/PRO-CORRECTION-REQUEST-v2.md",
            "sha256": "d443a7d64291022d02ae0c7d924b3905d5d2cde0b5b4f5945c2aebb13ccaa1f2",
        }
    )
    result = _run_candidate(tmp_path, candidate, "direct-v2-bundle-source.yaml")
    assert result["checks"]["source_design_refs"]["reason_codes"] == [
        "trusted_bundle_source_direct_reference_forbidden"
    ]

    candidate = clone_candidate(pass_candidate)
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    refs.append({"path": "../outside", "sha256": "0" * 64})  # type: ignore[union-attr]
    result = _run_candidate(tmp_path, candidate, "traversal.yaml")
    assert result["checks"]["source_design_refs"]["status"] == "FAIL"

    candidate = clone_candidate(pass_candidate)
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    refs[0]["sha256"] = "0" * 64  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate, "hash.yaml")
    assert result["checks"]["source_design_refs"]["status"] == "FAIL"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "approved_archive_member_reference_missing"),
        ("wrong_archive_hash", "archive_reference_not_pinned"),
        ("wrong_member_hash", "archive_member_hash_mismatch"),
        ("missing_member", "archive_member_missing_or_not_regular"),
        ("traversal_member", "archive_member_path_invalid"),
        ("secret_member", "archive_member_secret_path"),
        ("duplicate", "archive_reference_duplicate"),
        ("unbound_member_key", "archive_reference_ambiguous_or_unbound"),
    ],
)
def test_archive_member_references_fail_closed(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    mutation: str,
    reason: str,
) -> None:
    candidate = clone_candidate(pass_candidate)
    refs = candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    member = _member_ref(candidate)
    if mutation == "missing":
        refs.remove(member)  # type: ignore[union-attr]
    elif mutation == "wrong_archive_hash":
        member["archive_sha256"] = "0" * 64
    elif mutation == "wrong_member_hash":
        member["member_sha256"] = "0" * 64
    elif mutation == "missing_member":
        member["member_path"] = "approved-input/no-such-file.yaml"
    elif mutation == "traversal_member":
        member["member_path"] = "../outside.yaml"
    elif mutation == "secret_member":
        member["member_path"] = ".secrets/not-a-member"
    elif mutation == "duplicate":
        refs.append(member.copy())  # type: ignore[union-attr]
    else:
        refs.append({"member_path": member["member_path"]})  # type: ignore[union-attr]
    result = _run_candidate(tmp_path, candidate, f"{mutation}.yaml")
    assert result["checks"]["source_design_refs"]["status"] == "FAIL"
    assert reason in result["checks"]["source_design_refs"]["reason_codes"]


def test_archive_member_positive_binding_is_not_a_repository_path(
    candidate_path: Path,
) -> None:
    result = report(run_validator(candidate_path))
    assert result["status"] == "PASS_AUTOMATED_PREFLIGHT_ONLY"
    assert result["checks"]["source_design_refs"]["status"] == "PASS"


def test_source_symlink_and_special_file_references_fail_without_following(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    repository_root = disposable_repository_root(tmp_path)
    symlink = repository_root / "probes" / "source-link"
    fifo = repository_root / "probes" / "source-fifo"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    refs_path = pass_candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    try:
        symlink.symlink_to(repository_root / "AGENTS.md")
        refs_path.append(  # type: ignore[union-attr]
            {
                "path": symlink.relative_to(repository_root).as_posix(),
                "sha256": "0" * 64,
            }
        )
        symlink_path = _write_yaml(tmp_path, pass_candidate, "source-link.yaml")
        symlink_result = report(
            run_validator(symlink_path, repository_root=repository_root)
        )
        assert symlink_result["checks"]["source_design_refs"]["status"] == "FAIL"

        refs_path.pop()  # type: ignore[union-attr]
        os.mkfifo(fifo)
        refs_path.append(  # type: ignore[union-attr]
            {"path": fifo.relative_to(repository_root).as_posix(), "sha256": "0" * 64}
        )
        fifo_path = _write_yaml(tmp_path, pass_candidate, "source-fifo.yaml")
        fifo_result = report(run_validator(fifo_path, repository_root=repository_root))
        assert fifo_result["checks"]["source_design_refs"]["status"] == "FAIL"
    finally:
        symlink.unlink(missing_ok=True)
        fifo.unlink(missing_ok=True)


def test_lock_version_set_and_classifications_are_disjoint(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    models = candidate["DESIGN_HANDOFF_V1"]["decision"]["port_contracts"][
        "concurrency_models"
    ]  # type: ignore[index]
    models["LOCK_VERSION_CAS"]["relations"].remove("ai.ai_job")  # type: ignore[index]
    models["STATE_CAS_WITHOUT_LOCK_VERSION"]["relations"].append("ai.ai_job")  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate)
    assert result["checks"]["lock_version_cas_reconciliation"]["status"] == "FAIL"
    assert (
        result["checks"]["state_cas_without_lock_version_reconciliation"]["status"]
        == "FAIL"
    )


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("missing", "state_cas_relation_set_mismatch"),
        ("extra", "state_cas_relation_set_mismatch"),
        ("overlap", "state_cas_overlaps_lock_version_set"),
        ("outside", "state_cas_relation_outside_physical_set"),
    ],
)
def test_state_cas_set_rejects_missing_extra_overlap_and_outside_entries(
    tmp_path: Path,
    pass_candidate: dict[str, object],
    mutation: str,
    expected_check: str,
) -> None:
    candidate = clone_candidate(pass_candidate)
    relations = candidate["DESIGN_HANDOFF_V1"]["decision"]["port_contracts"][
        "concurrency_models"
    ]["STATE_CAS_WITHOUT_LOCK_VERSION"]["relations"]  # type: ignore[index]
    if mutation == "missing":
        relations.remove("policy.finding")  # type: ignore[union-attr]
    elif mutation == "extra":
        relations.append("policy.quality_score")  # type: ignore[union-attr]
    elif mutation == "overlap":
        relations.append("ai.ai_job")  # type: ignore[union-attr]
    else:
        relations.append("not.a_physical_relation")  # type: ignore[union-attr]
    result = _run_candidate(tmp_path, candidate, f"state-{mutation}.yaml")
    check = result["checks"]["state_cas_without_lock_version_reconciliation"]
    assert check["status"] == "FAIL"
    assert check["reason_codes"] == [expected_check]


def test_d6_is_structural_only_and_missing_presence_fails(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    del candidate["DESIGN_HANDOFF_V1"]["decision"]["connection_and_identity_boundary"]  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate)
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"


def test_self_asserted_authority_never_passes(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    candidate = clone_candidate(pass_candidate)
    approval = candidate["DESIGN_HANDOFF_V1"]["approval"]  # type: ignore[index]
    approval["implementation_authority"] = "GRANTED"  # type: ignore[index]
    result = _run_candidate(tmp_path, candidate)
    assert result["status"] == "FAIL"
    assert result["implementation_authority"] == "NOT_GRANTED"
    assert result["checks"]["candidate_shape_and_story"]["status"] == "FAIL"


def test_wrong_expected_hash_fails_and_binds_actual_candidate(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    path = _write_yaml(tmp_path, pass_candidate)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    wrong = "0" * 64 if actual != "0" * 64 else "1" * 64
    process = run_validator(path, expected_sha256=wrong)
    result = report(process)
    assert process.returncode == 1
    assert result["status"] == "FAIL"
    assert result["candidate_sha256"] == actual
    assert result["expected_sha256"] == wrong
    assert result["checks"]["expected_sha256_match"]["status"] == "FAIL"


def test_complete_repository_snapshot_detects_arbitrary_additions_modifications_deletions(
    tmp_path: Path,
) -> None:
    repository_root = disposable_repository_root(tmp_path)
    before = snapshot_repository_tree(repository_root)

    added = repository_root / "arbitrary" / "new.txt"
    added.parent.mkdir(parents=True)
    added.write_text("new\n", encoding="utf-8")
    assert snapshot_repository_tree(repository_root) != before
    added.unlink()

    sentinel = repository_root / "unrelated" / "sentinel.txt"
    original = sentinel.read_bytes()
    sentinel.write_bytes(original + b"modified\n")
    assert snapshot_repository_tree(repository_root) != before
    sentinel.write_bytes(original)

    deleted = repository_root / "changes/st-0308/PRO-CORRECTION-REQUEST-v2.md"
    deleted.unlink()
    assert snapshot_repository_tree(repository_root) != before


def test_validator_no_write_proof_snapshots_complete_disposable_root(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    repository_root = disposable_repository_root(tmp_path)
    path = _write_yaml(tmp_path, pass_candidate)
    before = snapshot_repository_tree(repository_root)
    process = run_validator(path, repository_root=repository_root)
    assert process.returncode == 0
    after = snapshot_repository_tree(repository_root)
    assert after == before
    assert "unrelated/sentinel.txt" in before
    assert before["unrelated/sentinel.txt"][0] == "regular"


def test_disposable_contract_mutation_is_a_compact_trusted_error(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    repository_root = disposable_repository_root(tmp_path)
    disposable_contract = (
        repository_root / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
    )
    original = disposable_contract.read_bytes()
    mutated = original[:1] + bytes([original[1] ^ 1]) + original[2:]
    assert sum(left != right for left, right in zip(original, mutated)) == 1
    disposable_contract.write_bytes(mutated)

    real_contract_before = CONTRACT_PATH.read_bytes()
    candidate_path = _write_yaml(tmp_path, pass_candidate, "contract-digest.yaml")
    process = run_validator(candidate_path, repository_root=repository_root)
    result = report(process)
    assert process.returncode == 2
    assert result["status"] == "ERROR"
    assert result["errors"] == ["validator_contract_digest_mismatch"]
    assert result["checks"]["trusted_repository_inputs"]["reason_codes"] == [
        "validator_contract_digest_mismatch"
    ]
    assert process.stdout == (
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    assert CONTRACT_PATH.read_bytes() == real_contract_before


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--handoff"],
        ["--expected-sha256"],
        ["--repository-root"],
        ["--unknown"],
        ["--help"],
        ["--hand", "candidate.yaml", "--expected-sha256", "0" * 64],
        ["--handoff", "candidate.yaml", "--expected-sha256", "0" * 64, "extra"],
    ],
)
def test_invalid_cli_is_one_sorted_json_line_without_stderr(
    argv: list[str],
) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, str(VALIDATOR), *argv],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert process.returncode == 2
    assert process.stderr == ""
    assert process.stdout.count("\n") == 1
    result = json.loads(process.stdout)
    assert result["status"] == "ERROR"
    assert result["validation_status"] == "ERROR"
    assert process.stdout == (
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
