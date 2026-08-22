"""Deterministic generation and prohibited-surface tests for ST-1701."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import build_st1506_production_deployment as base_generator
from scripts import build_st1701_business_inputs as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_rendered_outputs_match_owner_generated_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_provenance_rebind_preserves_approved_inputs_and_business_outputs() -> None:
    expected = {
        "changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml": (
            8_680,
            "d07a2f3902dcd23f7ef9d46ecd3ab68162bcc28f2b3ad849bbe0e27891f502aa",
        ),
        "changes/st-1701/DESIGN_HANDOFF_V1_ST1701_MVP_DECISION_PACKAGE_v1.yaml": (
            20_695,
            "f5e8f70b74fd26c68b0dfd8a47dd35fc59b1651e9e553dad738d90b00acd1790",
        ),
        "changes/st-1701/DESIGN-HANDOFF-APPROVAL-v1.yaml": (
            1_478,
            "8a9029410bdad475eca2da7d0ab0f87cf0d3e1a8019e6102522d7cb18ac3dbd0",
        ),
        "changes/st-1701/contracts/mvp-business-decision-package.v1.yaml": (
            10_678,
            "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f",
        ),
        "changes/st-1701/MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml": (
            2_098,
            "749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34",
        ),
        (
            "changes/st-1701/"
            "DESIGN_HANDOFF_V1_ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_v1.yaml"
        ): (
            26_483,
            "c45bea63891448be4af4d696d7d164ea37f246b76f5acce91de791638f49c17f",
        ),
        "changes/st-1701/DESIGN-HANDOFF-APPROVAL-GOLD-EVIDENCE-v1.yaml": (
            1_876,
            "288e96b9e4814e1a3d9409addcee2bf1b5bdf12ab9e0a8e756ec66846f057197",
        ),
        "changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json": (
            10_928,
            "22394f5b37d3fe90cc5c31aff47be0d0f31f061398bbd9d90b4030bcb050c33b",
        ),
        "changes/st-1701/generated/mvp-business-decision-package.v1.json": (
            22_781,
            "623af8942c87c1b14a06b07df1687e3e0cf537085bdd500c59388dd90c0b2f58",
        ),
        "changes/st-1701/generated/canonical-revision-request.v1.md": (
            4_268,
            "6f6425ef97b53ca9a406b98ff5e9b2a64762adc5badc4569cc539afc53da7d04",
        ),
        "changes/st-1701/generated/gold-evidence-validation.v1.json": (
            5_709,
            "cbf7b267ccd1d51b9d2ab0a0d379529a2b2dc237cf65921468999968d677e4da",
        ),
    }
    for relative, (size, digest) in expected.items():
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert len(content) == size
        assert hashlib.sha256(content).hexdigest() == digest


def test_check_mode_is_read_only() -> None:
    paths = tuple(REPOSITORY_ROOT / relative for relative in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_check_mode_does_not_write_authority_canonical_or_predecessor_inputs() -> None:
    relative_paths = (
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        Path("docs/execplans/RAOS-IMPLEMENTATION-FIRST.md"),
        Path("scripts/build_st0006_decision_gates.py"),
        Path("changes/st-0006/contracts/decision-gate-policy.v1.yaml"),
        Path("changes/st-0006/gate-blocker-report.v1.yaml"),
        Path("scripts/build_st1506_production_deployment.py"),
        Path("changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml"),
        Path("changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json"),
        Path("changes/st-1701/README.md"),
        Path("scripts/build_st1701_business_inputs.py"),
        Path("tests/st1701/conftest.py"),
        Path("tests/st1701/test_contract.py"),
        Path("tests/st1701/test_generation.py"),
        Path("tests/st1701/test_negative_cases.py"),
        generator.HANDOFF_PATH,
        generator.HANDOFF_APPROVAL_PATH,
        generator.DECISION_PACKAGE_PATH,
        generator.FINAL_PACKAGE_APPROVAL_PATH,
        generator.GOLD_HANDOFF_PATH,
        generator.GOLD_HANDOFF_APPROVAL_PATH,
    )
    absent_paths = tuple(
        REPOSITORY_ROOT / relative
        for relative in (
            generator.GOLD_LEDGER_PATH,
            generator.GOLD_EVIDENCE_APPROVAL_PATH,
            *generator.GOLD_POSTAPPROVAL_PATHS,
        )
    )
    assert all(not path.exists() for path in absent_paths)
    paths = tuple(REPOSITORY_ROOT / relative for relative in relative_paths)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before
    assert all(not path.exists() for path in absent_paths)


def test_check_rejects_symlinked_output_ancestor_without_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "changes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(base_generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_generated_registry_and_manifest_preserve_unresolved_truth() -> None:
    registry = json.loads((REPOSITORY_ROOT / generator.REFERENCE_PATH).read_bytes())
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert registry["document"]["authority"] == "NON_AUTHORITATIVE"
    assert registry["document"]["executable"] is False
    assert registry["document"]["canonical_acceptance_achieved"] is False
    assert registry["registry"]["resolved_count"] == 0
    assert registry["registry"]["global_unresolved_blocker_count"] == 14
    assert registry["activation"]["status"] == "BLOCKED_UNRESOLVED_INPUTS"
    assert registry["evidence_boundary"]["formal_tst_032"] == "NOT_EXECUTED"
    boundary = manifest["boundary"]
    assert boundary["package_authority"] == (
        "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE"
    )
    assert boundary["source_package_internal_final_approval"] == (
        "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL"
    )
    assert boundary["final_package_approval"] == (
        generator.FINAL_PACKAGE_APPROVAL_STATUS
    )
    assert boundary["final_package_approval_authority"] == (
        generator.FINAL_PACKAGE_APPROVAL_AUTHORITY
    )
    assert boundary["canonical_scoped_unresolved_count"] == 7
    assert boundary["global_unresolved_blocker_count"] == 14
    assert boundary["gate_state"] == "BLOCKED"
    assert boundary["st_1701_acceptance_achieved"] is False
    assert boundary["st_1702_ready"] is False
    assert boundary["production_ready"] is False
    assert boundary["effective_canonical_status"] == "UNCHANGED"
    assert boundary["canonical_revision_request_status"] == (
        generator.CANONICAL_REVISION_REQUEST_STATUS
    )
    assert boundary["canonical_revision_request_authority"] == (
        generator.FINAL_PACKAGE_APPROVAL_AUTHORITY
    )
    assert boundary["canonical_revision_request_readiness"] == "NOT_READY"
    assert boundary["gold_evidence_validation_status"] == "EVIDENCE_INSUFFICIENT"
    assert boundary["gold_evidence_stop_code"] == "STOP_EVIDENCE_INSUFFICIENT"
    assert boundary["gold_evidence_ledger_present"] is False
    assert boundary["gold_domain_editor_approval_present"] is False
    assert boundary["gold_complete_ledger_acceptance_enabled"] is False
    assert boundary["gold_resolution_candidates_generated"] is False
    assert boundary["gold_open_decisions_revision_candidate_generated"] is False
    assert boundary["gold_canonical_revision_request_generated"] is False
    assert boundary["gold_canonical_revision_bundle_manifest_generated"] is False
    assert boundary["gold_canonical_revision_bundle_approval_present"] is False
    assert boundary["gold_candidate_bound_exhaustion_claimed"] is False
    assert boundary["gold_postapproval_generation_enabled"] is False
    assert boundary["canonical_mutation_authority"] == "NONE"
    assert boundary["status_overlays"] == "UNCHANGED"


def test_manifest_hashes_all_owned_sources_and_generated_content() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    for row in manifest["source_artifacts"]:
        content = (REPOSITORY_ROOT / row["uri"].removeprefix("repo://")).read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    assert manifest["generated_artifact_count"] == len(
        generator.GENERATED_CONTENT_PATHS
    )
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path in generator.GENERATED_CONTENT_PATHS
        for content in ((REPOSITORY_ROOT / path).read_bytes(),)
    ]


def test_manifest_binds_exact_implementation_authority() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    authority = manifest["provenance"]["implementation_authority"]
    assert authority["handoff"] == {
        "uri": f"repo://{generator.HANDOFF_PATH.as_posix()}",
        "bytes": generator.HANDOFF_BYTES,
        "sha256": generator.HANDOFF_SHA256,
    }
    assert authority["approval"] == {
        "uri": f"repo://{generator.HANDOFF_APPROVAL_PATH.as_posix()}",
        "bytes": generator.HANDOFF_APPROVAL_BYTES,
        "sha256": generator.HANDOFF_APPROVAL_SHA256,
        "status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_authority": "ST1701_MVP_DECISION_PACKAGE_V1_ONLY",
    }
    assert manifest["provenance"]["gold_evidence_implementation_authority"] == {
        "handoff": {
            "uri": f"repo://{generator.GOLD_HANDOFF_PATH.as_posix()}",
            "bytes": generator.GOLD_HANDOFF_BYTES,
            "sha256": generator.GOLD_HANDOFF_SHA256,
        },
        "approval": {
            "uri": f"repo://{generator.GOLD_HANDOFF_APPROVAL_PATH.as_posix()}",
            "bytes": generator.GOLD_HANDOFF_APPROVAL_BYTES,
            "sha256": generator.GOLD_HANDOFF_APPROVAL_SHA256,
            "status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_authority": (
                "ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_V1_ONLY"
            ),
            "open_decisions": [],
            "self_approval_binding": "NOT_PRESENT_NO_CIRCULAR_APPROVAL",
        },
        "preapproval_generated_output": "GOLD_EVIDENCE_VALIDATION_V1_ONLY",
    }
    assert manifest["provenance"]["final_package_approval"] == {
        "uri": f"repo://{generator.FINAL_PACKAGE_APPROVAL_PATH.as_posix()}",
        "bytes": generator.FINAL_PACKAGE_APPROVAL_BYTES,
        "sha256": generator.FINAL_PACKAGE_APPROVAL_SHA256,
        "status": generator.FINAL_PACKAGE_APPROVAL_STATUS,
        "authority": generator.FINAL_PACKAGE_APPROVAL_AUTHORITY,
        "source_package": {
            "uri": generator.DECISION_PACKAGE_URI,
            "bytes": generator.APPROVED_DECISION_PACKAGE_BYTES,
            "sha256": generator.APPROVED_DECISION_PACKAGE_SHA256,
        },
        "implementation_handoff": {
            "uri": f"repo://{generator.HANDOFF_PATH.as_posix()}",
            "sha256": generator.HANDOFF_SHA256,
        },
        "implementation_handoff_approval": {
            "uri": f"repo://{generator.HANDOFF_APPROVAL_PATH.as_posix()}",
            "sha256": generator.HANDOFF_APPROVAL_SHA256,
        },
        "open_decisions": [],
        "self_approval_binding": "NOT_PRESENT_NO_CIRCULAR_APPROVAL",
    }
    assert len(manifest["provenance"]["approved_preimplementation_inputs"]) == 10
    assert len(
        manifest["provenance"]["gold_evidence_approved_preimplementation_inputs"]
    ) == len(generator.EXPECTED_GOLD_SOURCE_ROWS)


def test_gold_handoff_and_detached_approval_are_exact_and_additive() -> None:
    handoff_bytes = (REPOSITORY_ROOT / generator.GOLD_HANDOFF_PATH).read_bytes()
    approval_bytes = (
        REPOSITORY_ROOT / generator.GOLD_HANDOFF_APPROVAL_PATH
    ).read_bytes()
    assert len(handoff_bytes) == generator.GOLD_HANDOFF_BYTES
    assert hashlib.sha256(handoff_bytes).hexdigest() == generator.GOLD_HANDOFF_SHA256
    assert len(approval_bytes) == generator.GOLD_HANDOFF_APPROVAL_BYTES
    assert hashlib.sha256(approval_bytes).hexdigest() == (
        generator.GOLD_HANDOFF_APPROVAL_SHA256
    )

    handoff, approval = generator.load_gold_authority(REPOSITORY_ROOT)
    assert handoff["approved_story"] == "ST-1701"
    assert handoff["open_decisions"] == []
    assert (
        approval
        == generator.EXPECTED_GOLD_HANDOFF_APPROVAL_DOCUMENT[
            "DESIGN_HANDOFF_APPROVAL_V1"
        ]
    )
    assert approval["handoff_bytes"] == generator.GOLD_HANDOFF_BYTES
    assert approval["handoff_sha256"] == generator.GOLD_HANDOFF_SHA256
    assert approval["open_decisions"] == []
    assert approval["boundaries"]["canonical_mutation_authority"] == "NONE"
    assert approval["boundaries"]["preapproval_generated_output"] == (
        "GOLD_EVIDENCE_VALIDATION_V1_ONLY"
    )
    assert generator.GOLD_HANDOFF_APPROVAL_SHA256.encode() not in approval_bytes


def test_final_package_and_detached_approval_bytes_are_exact_and_non_circular() -> None:
    source = (REPOSITORY_ROOT / generator.DECISION_PACKAGE_PATH).read_bytes()
    approval = (REPOSITORY_ROOT / generator.FINAL_PACKAGE_APPROVAL_PATH).read_bytes()
    assert len(source) == generator.APPROVED_DECISION_PACKAGE_BYTES
    assert hashlib.sha256(source).hexdigest() == (
        generator.APPROVED_DECISION_PACKAGE_SHA256
    )
    assert len(approval) == generator.FINAL_PACKAGE_APPROVAL_BYTES
    assert hashlib.sha256(approval).hexdigest() == (
        generator.FINAL_PACKAGE_APPROVAL_SHA256
    )
    assert generator.FINAL_PACKAGE_APPROVAL_SHA256.encode() not in approval


def test_manifest_provenance_rows_match_independent_approved_literals() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    provenance = manifest["provenance"]
    assert provenance["approved_preimplementation_inputs"] == [
        {
            "uri": "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
            "bytes": 7943,
            "sha256": "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
        },
        {
            "uri": "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
            "bytes": 4956,
            "sha256": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        },
        {
            "uri": "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
            "bytes": 71458,
            "sha256": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
        },
        {
            "uri": "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
            "bytes": 11395,
            "sha256": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
        },
        {
            "uri": "repo://docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
            "bytes": 24993,
            "sha256": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        },
        {
            "uri": "repo://changes/st-0006/contracts/decision-gate-policy.v1.yaml",
            "bytes": 1064,
            "sha256": "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989",
        },
        {
            "uri": "repo://changes/st-0006/gate-blocker-report.v1.yaml",
            "bytes": 9999,
            "sha256": "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15",
        },
        {
            "uri": "repo://changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml",
            "bytes": 8680,
            "sha256": "d07a2f3902dcd23f7ef9d46ecd3ab68162bcc28f2b3ad849bbe0e27891f502aa",
        },
        {
            "uri": "repo://changes/st-1701/README.md",
            "bytes": 4690,
            "sha256": "c7337ffee3bb1e0aa15a9258d3a57a63ac1b65985745ed343d63e530ea77ad1d",
        },
        {
            "uri": "repo://scripts/build_st1701_business_inputs.py",
            "bytes": 23341,
            "sha256": "a9462d347c68ff8da234df16327298190ad54b453fce318358ed39d94a973528",
        },
    ]
    assert provenance["gold_evidence_approved_preimplementation_inputs"] == [
        {"uri": f"repo://{path}", "bytes": size, "sha256": digest}
        for path, size, digest in generator.EXPECTED_GOLD_SOURCE_ROWS
    ]
    assert provenance["authority_inputs"] == [
        {
            "uri": "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
            "bytes": 7943,
            "sha256": "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
        },
        {
            "uri": "repo://docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
            "bytes": 3955,
            "sha256": "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
        },
        {
            "uri": "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
            "bytes": 4956,
            "sha256": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        },
        {
            "uri": "repo://docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
            "bytes": 24993,
            "sha256": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
        },
        {
            "uri": "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
            "bytes": 11395,
            "sha256": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
        },
        {
            "uri": "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
            "bytes": 71458,
            "sha256": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
        },
        {
            "uri": "repo://docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
            "bytes": 10741,
            "sha256": "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b",
        },
    ]
    assert provenance["predecessor_inputs"] == [
        {
            "uri": "repo://scripts/build_st0006_decision_gates.py",
            "bytes": 66037,
            "sha256": "0f6ad788aa90660775cb7852f7bb2ab7d8712d62bbf17dcaa651fe0fb8f6e06f",
        },
        {
            "uri": "repo://changes/st-0006/contracts/decision-gate-policy.v1.yaml",
            "bytes": 1064,
            "sha256": "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989",
        },
        {
            "uri": "repo://changes/st-0006/gate-blocker-report.v1.yaml",
            "bytes": 9999,
            "sha256": "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15",
        },
    ]
    assert provenance["implementation_inputs"] == [
        {
            "uri": "repo://scripts/build_st1506_production_deployment.py",
            "sha256": "f58b1ed91bcfcc4376262a3e3aa3653154dcbb0672e8508daac874e0042f1176",
        }
    ]
    current = provenance["current_development_rebinding"]
    assert current["classification"] == "REVERSIBLE_REPOSITORY_DEVELOPMENT_ONLY"
    assert current["authority_source"] == {
        "uri": f"repo://{generator.STANDING_DEVELOPMENT_AUTHORITY_PATH}",
        "bytes": generator.STANDING_DEVELOPMENT_AUTHORITY_BYTES,
        "sha256": generator.STANDING_DEVELOPMENT_AUTHORITY_SHA256,
        "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
    }
    assert current["current_authority_inputs"] == [
        {
            "uri": f"repo://{path}",
            "bytes": binding[0],
            "sha256": binding[1],
        }
        for path, binding in generator.CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.items()
    ]
    assert current["current_implementation_inputs"] == [
        {
            "uri": f"repo://{path}",
            "bytes": (REPOSITORY_ROOT / path).stat().st_size,
            "sha256": digest,
        }
        for path, digest in generator.IMPLEMENTATION_DEPENDENCIES.items()
    ]
    assert current["historical_source_and_authority_rows_preserved"] is True
    assert current["semantic_delta_from_business_inputs"] == "NONE"
    assert current["formal_evidence"] is False
    for field in (
        "external_authority",
        "live_provider_authority",
        "credential_authority",
        "staging_authority",
        "publication_authority",
        "release_authority",
        "production_authority",
    ):
        assert current[field] == "NONE"
    assert provenance["source_contracts"] == [
        {
            "uri": "repo://changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml",
            "bytes": 8680,
            "sha256": "d07a2f3902dcd23f7ef9d46ecd3ab68162bcc28f2b3ad849bbe0e27891f502aa",
        },
        {
            "uri": "repo://changes/st-1701/contracts/mvp-business-decision-package.v1.yaml",
            "bytes": 10678,
            "sha256": "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f",
        },
    ]
    assert manifest["source_artifact_count"] == 11
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        "repo://changes/st-1701/contracts/unresolved-mvp-business-inputs.v1.yaml",
        "repo://changes/st-1701/contracts/mvp-business-decision-package.v1.yaml",
        "repo://changes/st-1701/MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml",
        (
            "repo://changes/st-1701/"
            "DESIGN_HANDOFF_V1_ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_v1.yaml"
        ),
        "repo://changes/st-1701/DESIGN-HANDOFF-APPROVAL-GOLD-EVIDENCE-v1.yaml",
        "repo://changes/st-1701/README.md",
        "repo://scripts/build_st1701_business_inputs.py",
        "repo://tests/st1701/conftest.py",
        "repo://tests/st1701/test_contract.py",
        "repo://tests/st1701/test_generation.py",
        "repo://tests/st1701/test_negative_cases.py",
    ]
    assert manifest["generated_artifact_count"] == 4
    assert [row["uri"] for row in manifest["generated_artifacts"]] == [
        "repo://changes/st-1701/generated/unresolved-mvp-business-inputs.v1.json",
        "repo://changes/st-1701/generated/mvp-business-decision-package.v1.json",
        "repo://changes/st-1701/generated/canonical-revision-request.v1.md",
        "repo://changes/st-1701/generated/gold-evidence-validation.v1.json",
    ]


def test_generated_gold_validation_is_deterministic_exact_json() -> None:
    path = REPOSITORY_ROOT / generator.GOLD_VALIDATION_PATH
    content = path.read_bytes()
    expected = generator.gold_evidence_validation_document(REPOSITORY_ROOT)
    assert json.loads(content) == expected
    assert (
        content == (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode()
    )
    assert generator.gold_evidence_validation_document(REPOSITORY_ROOT) == expected


def test_generated_decision_read_model_projects_effective_approval_not_readiness() -> (
    None
):
    read_model = json.loads(
        (REPOSITORY_ROOT / generator.DECISION_READ_MODEL_PATH).read_bytes()
    )
    source = (REPOSITORY_ROOT / generator.DECISION_PACKAGE_PATH).read_bytes()
    document = read_model["document"]
    assert document["authority"] == generator.FINAL_PACKAGE_APPROVAL_AUTHORITY
    assert document["status"] == generator.CANONICAL_REVISION_REQUEST_STATUS
    assert document["executable"] is False
    assert document["canonical_resolution_authority"] == "NONE"
    assert document["source_contract_sha256"] == hashlib.sha256(source).hexdigest()
    assert document["approved_handoff_sha256"] == generator.HANDOFF_SHA256
    assert document["handoff_approval_sha256"] == generator.HANDOFF_APPROVAL_SHA256
    assert document["source_contract_internal_status"] == (
        "PENDING_EXACT_REPOSITORY_OWNER_APPROVAL"
    )
    assert document["detached_final_package_approval_sha256"] == (
        generator.FINAL_PACKAGE_APPROVAL_SHA256
    )
    effective = read_model["final_package_approval"]
    assert effective["source_package_internal"] == (
        generator.EXPECTED_FINAL_PACKAGE_APPROVAL
    )
    assert effective["detached_effective"]["status"] == (
        generator.FINAL_PACKAGE_APPROVAL_STATUS
    )
    assert effective["detached_effective"]["authority"] == (
        generator.FINAL_PACKAGE_APPROVAL_AUTHORITY
    )
    assert effective["effective_boundary"]["canonical_revision_request"] == (
        generator.CANONICAL_REVISION_REQUEST_STATUS
    )
    assert tuple(row["id"] for row in read_model["scoped_decisions"]) == (
        generator.SCOPED_IDS
    )
    assert all(
        row["canonical_truth"]["resolution_state"] == "UNRESOLVED"
        for row in read_model["scoped_decisions"]
    )
    assert read_model["canonical_truth_boundary"]["activation"] == (
        "BLOCKED_UNRESOLVED_INPUTS"
    )
    assert read_model["canonical_truth_boundary"]["scoped_unresolved_count"] == 7
    assert (
        read_model["canonical_truth_boundary"]["global_unresolved_blocker_count"] == 14
    )
    assert read_model["canonical_truth_boundary"]["gate_state"] == "BLOCKED"
    assert read_model["canonical_truth_boundary"]["st1701_acceptance"] == (
        "NOT_ACHIEVED"
    )
    assert effective["remaining_prerequisites"] == {
        "od005_alternate_reviewer_or_approved_exception": "NOT_SATISFIED",
        "od006_gold_evidence": "NOT_OBTAINED",
        "od006_domain_editor_acceptance": "NOT_OBTAINED",
        "formal_tst_032": "NOT_EXECUTED",
        "canonical_revision_approval_and_import": "NOT_EXECUTED",
    }
    evidence = read_model["evidence_boundary"]
    assert (
        evidence["source_package_internal"]["exact_final_package_owner_approval"]
        == "PENDING"
    )
    assert evidence["effective_final_package_owner_approval"] == {
        "status": generator.FINAL_PACKAGE_APPROVAL_STATUS,
        "authority": generator.FINAL_PACKAGE_APPROVAL_AUTHORITY,
        "approval_sha256": generator.FINAL_PACKAGE_APPROVAL_SHA256,
    }
    assert evidence["canonical_revision_request_readiness"] == "NOT_READY"


def test_generated_canonical_revision_request_is_owner_approved_but_not_ready() -> None:
    request = (REPOSITORY_ROOT / generator.CANONICAL_REVISION_REQUEST_PATH).read_text(
        encoding="utf-8"
    )
    assert f"Authority: `{generator.FINAL_PACKAGE_APPROVAL_AUTHORITY}`" in request
    assert "Readiness: `NOT_READY`" in request
    assert "Canonical mutation or status-change authority: `NONE`" in request
    assert "Source package SHA-256: `" in request
    assert f"Generated by: `{generator.GENERATOR_URI}`" in request
    assert f"Generation command: `{generator.GENERATION_COMMAND}`" in request
    assert (
        f"Detached final-package approval SHA-256: "
        f"`{generator.FINAL_PACKAGE_APPROVAL_SHA256}`" in request
    )
    assert (
        f"Detached approval status: `{generator.FINAL_PACKAGE_APPROVAL_STATUS}`"
        in request
    )
    assert "Final source-package owner approval: `EFFECTIVE_DETACHED_EXACT_HASH`" in (
        request
    )
    assert "Source-package internal approval field:" in request
    assert "The repository owner approves the exact final source-package" not in request
    assert "OD-005 requires an alternate reviewer" in request
    assert "Formal TST-032 remains `NOT_EXECUTED`" in request
    assert "Canonical-revision approval and import remain separately" in request
    for condition in (
        *generator.SCOPED_PENDING_CONDITIONS,
        *generator.INFORMATIONAL_PENDING_CONDITIONS,
    ):
        assert f"`{condition['id']}` / `{condition['record_status']}`" in request
        assert condition["condition"] in request
    for exact_od006_requirement in (
        "at least 30 listings, 10 product families, and 5 shops",
        "exact_duplicates",
        "color_or_variant_differences",
        "size_or_capacity_differences",
        "missing_jan",
        "bundles_and_set_count",
        "conflicting_fields",
        "maximum false automatic merges is 0",
        "Domain Editor review remains required",
        "raw source links and observations are required",
    ):
        assert exact_od006_requirement in request
    assert "No canonical edit or canonical decision-status change." in request
    assert "No Gate, TST-032, Story, staging, publication, release" in request
    for forbidden_claim in (
        "Status: `RESOLVED`",
        "Status: `VALIDATED`",
        "Gate: `PASS`",
        "Production: `READY`",
    ):
        assert forbidden_claim not in request


def test_existing_unresolved_generated_registry_is_byte_preserved() -> None:
    content = (REPOSITORY_ROOT / generator.REFERENCE_PATH).read_bytes()
    assert len(content) == 10928
    assert hashlib.sha256(content).hexdigest() == (
        "22394f5b37d3fe90cc5c31aff47be0d0f31f061398bbd9d90b4030bcb050c33b"
    )


def test_builder_has_no_external_value_or_approval_surface() -> None:
    tree = ast.parse((REPOSITORY_ROOT / generator.GENERATOR_PATH).read_text())
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imports.isdisjoint(
        {
            "aiohttp",
            "anthropic",
            "boto3",
            "botocore",
            "ftplib",
            "http",
            "httpx",
            "importlib",
            "openai",
            "os",
            "paramiko",
            "playwright",
            "requests",
            "selenium",
            "smtplib",
            "socket",
            "sqlite3",
            "subprocess",
            "urllib",
            "webbrowser",
        }
    )
    assert calls.isdisjoint(
        {
            "__import__",
            "apply",
            "click",
            "connect",
            "create_account",
            "deploy",
            "environ",
            "exec",
            "getenv",
            "import_module",
            "navigate",
            "open_browser",
            "popen",
            "publish",
            "purchase",
            "release",
            "request",
            "run",
            "send",
            "system",
            "urlopen",
        }
    )


def test_cli_accepts_only_no_argument_or_exact_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    for arguments in (
        ["--chec"],
        ["--check", "--check"],
        ["--resolve", "OD-001"],
        ["--value", "anything"],
        ["--approve"],
        ["--publish"],
    ):
        with pytest.raises(SystemExit):
            generator.parse_args(arguments)
