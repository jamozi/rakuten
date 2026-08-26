#!/usr/bin/env python3
"""Build inert ST-1506 V2 local canary simulation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NoReturn

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
for import_root in (REPO_ROOT, PYTHON_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from raos.domain.ops.production_canary import (  # noqa: E402
    CanaryCommandKind,
    CanarySession,
    CanaryState,
    PIPELINE_PHASES,
    ProductionCanaryError,
    ProductionCanarySpec,
    REQUIRED_CAPABILITY_IDS,
    advance_once,
    canonical_sha256,
)
from raos.production_canary_runner import (  # noqa: E402
    load_local_production_canary_spec,
    recorded_observations,
)


CONTRACT_PATH: Final = Path(
    "changes/st-1506/contracts/local-production-canary-runtime.v2.yaml"
)
PIPELINE_PATH: Final = Path(
    "infra/terraform/deployment-production/local-production-canary.pipeline.disabled.v2.yaml"
)
RESULT_PATH: Final = Path(
    "infra/terraform/deployment-production/local-production-canary.result.recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1506/manifest.v2.yaml")
GENERATED_PATHS: Final = (PIPELINE_PATH, RESULT_PATH, MANIFEST_PATH)
GENERATOR_URI: Final = "repo://scripts/build_st1506_production_canary_runtime.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1506_production_canary_runtime.py"
)
AUTHORITY_PATHS: Final = (
    Path("AGENTS.md"),
    Path("docs/canonical/00_master/RAOS_MASTER_README_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
    Path("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
    Path("docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"),
    Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
    Path("docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md"),
    Path("docs/canonical/06_ops/RAOS_12_backup_restore_matrix_v1.0.yaml"),
    Path("docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml"),
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("changes/st-1506/DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-1506/IMPLEMENTATION_RECORD_V2_ST1506_LOCAL_CANARY.yaml"),
    Path("changes/st-1506/LOCAL_COMPLETION_EVIDENCE_V2.md"),
    Path("changes/st-1506/README_V2.md"),
    Path("scripts/build_st1506_production_canary_runtime.py"),
    Path("python/raos/domain/ops/production_canary.py"),
    Path("python/raos/ports/production_canary.py"),
    Path("python/raos/application/ops/production_canary.py"),
    Path("python/raos/adapters/disabled_production_activation.py"),
    Path("python/raos/adapters/recorded_production_canary.py"),
    Path("python/raos/production_canary_runner.py"),
    Path("tests/st1506/test_local_canary_runtime.py"),
    Path("tests/st1506/test_local_canary_hostile.py"),
    Path("tests/st1506/test_local_canary_journal.py"),
    Path("tests/st1506/test_local_canary_generation.py"),
)
PREDECESSOR_OWNER_PATHS: Final = tuple(
    Path(path)
    for path in (
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "scripts/build_st1501_terraform_foundation.py",
        "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
        "changes/st-1501/manifest.yaml",
        "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
        "changes/st-1502/contracts/data-services-foundation.v1.yaml",
        "scripts/build_st1502_data_services.py",
        "infra/terraform/data-services/data-services.reference-plan.v1.json",
        "changes/st-1502/manifest.yaml",
        "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
        "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
        "scripts/build_st1503_compute_edge.py",
        "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        "changes/st-1503/manifest.yaml",
        "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
        "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
        "scripts/build_st1504_github_oidc.py",
        "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
        "changes/st-1504/manifest.yaml",
        "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml",
        "changes/st-1505/contracts/local-staging-admission-runtime.v2.yaml",
        "scripts/build_st1505_staging_deployment.py",
        "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
        "changes/st-1505/manifest.yaml",
        "changes/st-1506/contracts/production-deployment-definition.v1.yaml",
    )
)


class BuildError(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str) -> NoReturn:
    raise BuildError(code) from None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _regular_file(root: Path, relative: Path) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("PATH_INVALID")
    cursor = root
    try:
        for part in relative.parts:
            cursor /= part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                _fail("PATH_INVALID")
        if not stat.S_ISREG(cursor.lstat().st_mode):
            _fail("PATH_INVALID")
    except BuildError:
        raise
    except OSError:
        _fail("PATH_UNAVAILABLE")
    return cursor


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _regular_file(root, relative)
    try:
        content = path.read_bytes()
    except OSError:
        _fail("SOURCE_READ_FAILED")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _workflow_inventory(root: Path) -> list[str]:
    workflow_root = root / ".github" / "workflows"
    if workflow_root.is_symlink() or not workflow_root.is_dir():
        _fail("ACTIVE_WORKFLOW_TREE_INVALID")
    rows: list[str] = []
    for path in sorted(workflow_root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            _fail("ACTIVE_WORKFLOW_TREE_INVALID")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            _fail("ACTIVE_WORKFLOW_TREE_INVALID")
        relative = path.relative_to(root).as_posix()
        rows.append(relative)
    return rows


def _pipeline_document(spec: ProductionCanarySpec) -> dict[str, object]:
    return {
        "document": {
            "schema": "RAOS_LOCAL_PRODUCTION_CANARY_PIPELINE_FIXTURE_V2",
            "version": 2,
            "story_id": "ST-1506",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": GENERATOR_URI,
            "classification": "REPOSITORY_INERT_LOCAL_SIMULATION_FIXTURE_ONLY",
        },
        "activation": {
            "enabled": False,
            "default_enabled": False,
            "active_workflow_path": None,
            "trigger": "NONE",
            "selected_provider": None,
            "selected_account": None,
            "selected_region": None,
            "selected_target": None,
            "credentials": "ABSENT",
            "network_client": "ABSENT",
            "commands": [],
            "activation_authority": "NONE",
            "public_write_authority": "NONE",
        },
        "pipeline": {
            "fixture_id": spec.fixture_id,
            "pipeline_id": spec.pipeline_id,
            "contract_sha256": spec.semantic_sha256,
            "phases": list(PIPELINE_PHASES),
            "one_step_per_call": True,
            "auto_advance": "FORBIDDEN",
            "action_counts": dict(spec.action_counts),
        },
        "capability_boundary": {
            "required_capability_ids": list(spec.capability_ids),
            "selected_mapping_count": 0,
            "selected_profile": None,
            "default_profile": None,
            "fallback_profile": None,
            "eligibility": "BLOCKED_NOT_CONFIGURED",
        },
        "kill_switch": {
            "safeguard_enabled": True,
            "deactivation_allowed": False,
            "deactivation_authority": "NONE",
            "external_action_count": 0,
        },
        "human_approval_artifacts": {
            "release_decision": "ABSENT",
            "gate_report": "ABSENT",
            "security_approval": "ABSENT",
            "operations_approval": "ABSENT",
            "populated_count": 0,
        },
        "external_evidence": {
            "formal_tst_009": "NOT_EXECUTED",
            "formal_tst_022": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }


def _result_document(root: Path, spec: ProductionCanarySpec) -> dict[str, object]:
    observations = recorded_observations(root, spec)
    scenarios: list[dict[str, object]] = []
    for index, observation in enumerate(observations, start=1):
        initial = CanarySession(
            run_id=f"st1506-run-generated-{index}",
            version=0,
            state=CanaryState.CANARY_READY,
        )
        started = advance_once(
            spec,
            initial,
            command=CanaryCommandKind.START_CANARY_SIMULATION,
            observation=None,
        )
        decided = advance_once(
            spec,
            started.session,
            command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
            observation=observation,
        )
        scenarios.append(
            {
                "scenario_id": observation.scenario_id,
                "observation_sha256": canonical_sha256(observation.to_payload()),
                "start_outcome": started.outcome.value,
                "decision_outcome": decided.outcome.value,
                "terminal_state": decided.session.state.value,
                "external_actions": 0,
            }
        )
    base: dict[str, object] = {
        "schema": "RAOS_LOCAL_PRODUCTION_CANARY_RESULT_V2",
        "version": 2,
        "fixture_id": spec.fixture_id,
        "pipeline_id": spec.pipeline_id,
        "contract_sha256": spec.semantic_sha256,
        "classification": "DETERMINISTIC_SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_EVIDENCE",
        "status": "LOCAL_CANARY_SIMULATION_COMPLETE",
        "scenarios": scenarios,
        "capability_boundary": {
            "required_capability_ids": list(REQUIRED_CAPABILITY_IDS),
            "selected_mapping_count": 0,
            "eligibility": "BLOCKED_NOT_CONFIGURED",
        },
        "human_approval_artifacts": {
            "release_decision": "ABSENT",
            "gate_report": "ABSENT",
            "security_approval": "ABSENT",
            "operations_approval": "ABSENT",
            "populated_count": 0,
        },
        "activation": {
            "enabled": False,
            "authority": "NONE",
            "public_write_authority": "NONE",
            "auto_advance": "FORBIDDEN",
        },
        "kill_switch": {
            "safeguard_enabled": True,
            "deactivation_allowed": False,
            "external_action_count": 0,
        },
        "action_counts": dict(spec.action_counts),
        "external_evidence": {
            "formal_tst_009": "NOT_EXECUTED",
            "formal_tst_022": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    base["result_sha256"] = canonical_sha256(base)
    return base


def _yaml_bytes(document: object) -> bytes:
    return yaml.dump(
        document,
        Dumper=_NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8")


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    try:
        spec = load_local_production_canary_spec(root)
    except ProductionCanaryError as error:
        raise BuildError(error.code) from None
    workflow_rows = _workflow_inventory(root)
    pipeline_bytes = _yaml_bytes(_pipeline_document(spec))
    result_bytes = _json_bytes(_result_document(root, spec))
    source_artifacts = [_artifact_row(root, path) for path in SOURCE_PATHS]
    predecessor_owner_artifacts = [
        _artifact_row(root, path) for path in PREDECESSOR_OWNER_PATHS
    ]
    authority_inputs = [_artifact_row(root, path) for path in AUTHORITY_PATHS]
    generated_without_manifest = [
        {
            "uri": f"repo://{PIPELINE_PATH.as_posix()}",
            "bytes": len(pipeline_bytes),
            "sha256": _sha256_bytes(pipeline_bytes),
        },
        {
            "uri": f"repo://{RESULT_PATH.as_posix()}",
            "bytes": len(result_bytes),
            "sha256": _sha256_bytes(result_bytes),
        },
    ]
    manifest = {
        "document": {
            "id": "RAOS-LOCAL-PRODUCTION-CANARY-MANIFEST-002",
            "version": "2.0.0",
            "story_id": "ST-1506",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _artifact_row(root, CONTRACT_PATH)["sha256"],
            "contract_semantic_sha256": spec.semantic_sha256,
            "authority_inputs": authority_inputs,
            "predecessor_contracts": [
                {"story_id": story, "sha256": digest}
                for story, digest in spec.predecessor_hashes
            ],
            "predecessor_owner_artifacts": predecessor_owner_artifacts,
            "staging_admission": {
                "contract_sha256": spec.staging_contract_sha256,
                "contract_semantic_sha256": spec.staging_contract_semantic_sha256,
                "manifest_sha256": spec.staging_manifest_sha256,
                "pipeline_sha256": spec.staging_pipeline_sha256,
                "result_file_sha256": spec.staging_result_file_sha256,
                "result_sha256": spec.staging_result_sha256,
                "artifact_sha256": spec.artifact_sha256,
                "sbom_sha256": spec.sbom_sha256,
                "provenance_sha256": spec.provenance_sha256,
            },
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_without_manifest),
        "generated_artifacts": generated_without_manifest,
        "active_workflow_tree": {
            "semantic_id": "github-workflows",
            "semantic_version": 2,
            "changed_by_story": False,
            "files": workflow_rows,
        },
        "boundary": {
            "local_runtime": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE_PROPOSAL",
            "activation": "DISABLED",
            "activation_authority": "NONE",
            "public_write_authority": "NONE",
            "selected_provider": None,
            "selected_account": None,
            "selected_region": None,
            "selected_target": None,
            "credentials": "ABSENT",
            "human_approval_artifact_count": 0,
            "required_capability_ids": list(spec.capability_ids),
            "selected_capability_mapping_count": 0,
            "capability_eligibility": "BLOCKED_NOT_CONFIGURED",
            "kill_switch_safeguard_enabled": True,
            "kill_switch_deactivation_allowed": False,
            "auto_advance": "FORBIDDEN",
            "action_counts": dict(spec.action_counts),
            "formal_tst_009": "NOT_EXECUTED",
            "formal_tst_022": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "canonical_status_effect": "NONE",
        },
    }
    return {
        PIPELINE_PATH: pipeline_bytes,
        RESULT_PATH: result_bytes,
        MANIFEST_PATH: _yaml_bytes(manifest),
    }


def _safe_parent(root: Path, relative: Path, *, create: bool) -> Path:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _fail("OUTPUT_PATH_INVALID")
    current = root
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("OUTPUT_MISSING")
            current.mkdir(mode=0o755)
            metadata = current.lstat()
        except OSError:
            _fail("OUTPUT_PATH_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("OUTPUT_PATH_INVALID")
    return current


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    parent = _safe_parent(root, relative, create=True)
    target = parent / relative.name
    if target.exists() or target.is_symlink():
        metadata = target.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("OUTPUT_PATH_INVALID")
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{relative.name}.", suffix=".tmp", dir=parent
        )
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        _fail("OUTPUT_WRITE_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if tuple(outputs) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT")
    if check:
        for relative, expected in outputs.items():
            try:
                actual = (
                    _safe_parent(root, relative, create=False) / relative.name
                ).read_bytes()
            except OSError:
                _fail("OUTPUT_MISSING")
            if actual != expected:
                _fail("OUTPUT_DRIFT")
        return
    for relative, content in outputs.items():
        _atomic_write(root, relative, content)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        parser.error("unsupported argument")
    return argparse.Namespace(check=arguments == ["--check"])


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(arguments.check))
    except BuildError as error:
        print(f"ERROR code={error.code}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE", file=sys.stderr)
        return 1
    print(
        "ST-1506 local Production canary check passed"
        if arguments.check
        else "ST-1506 local Production canary artifacts generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
