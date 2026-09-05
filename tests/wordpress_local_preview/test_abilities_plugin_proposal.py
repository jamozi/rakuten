from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "changes/wordpress-publication-bundle-v3/abilities_plugin_proposal.py"
SPEC = importlib.util.spec_from_file_location("abilities_plugin_proposal", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)


def _artifact_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> bytes:
    package = b"deterministic-abilities-plugin-zip"
    package_path = tmp_path / "raos-codex-mcp-abilities-v1.zip"
    package_path.write_bytes(package)
    package_path.chmod(0o600)
    package_sha256 = hashlib.sha256(package).hexdigest()
    file_manifest_sha256 = "1" * 64
    manifest_path = tmp_path / "runtime-manifest.v1.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "RAOS_WORDPRESS_MCP_RUNTIME_MANIFEST_V1",
                "plugin": {
                    "slug": "raos-codex-mcp-abilities",
                    "version": "1.3.1",
                    "package_sha256": package_sha256,
                    "file_manifest_sha256": file_manifest_sha256,
                },
            }
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "repo-plugin-artifacts.v1.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema": "RAOS_WORDPRESS_REPO_PLUGIN_ARTIFACTS_V1",
                "artifacts": [
                    {
                        "artifact_id": "raos-codex-mcp-abilities-v1",
                        "slug": "raos-codex-mcp-abilities",
                        "version": "1.3.1",
                        "package_sha256": package_sha256,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bundle, "PACKAGE_PATH", package_path)
    monkeypatch.setattr(bundle, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(bundle, "REGISTRY_PATH", registry_path)
    return package


def test_prepare_requires_preview_then_builds_private_repo_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _artifact_set(monkeypatch, tmp_path)
    events: list[str] = []

    def runner(arguments: tuple[str, ...], **_kwargs: object) -> Any:
        events.append(arguments[-1])
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    receipt = bundle.prepare(
        preview=lambda: events.append("preview"),
        runner=runner,
    )

    assert events == ["preview", "--check", "--package"]
    assert receipt["artifact_id"] == "raos-codex-mcp-abilities-v1"
    assert receipt["plugin_version"] == "1.3.1"
    assert receipt["apply_command_exposed"] is False
    assert stat.S_IMODE(bundle.PACKAGE_PATH.stat().st_mode) == 0o600


def test_propose_stops_for_separate_admin_and_never_applies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _artifact_set(monkeypatch, tmp_path)
    digest = hashlib.sha256(package).hexdigest()
    events: list[str] = []
    stored: dict[str, object] = {}

    def runner(arguments: tuple[str, ...], **_kwargs: object) -> Any:
        events.append(arguments[-1])
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    def deployment_call(
        command: str, arguments: dict[str, object], **_kwargs: object
    ) -> dict[str, object]:
        events.append(command)
        assert arguments == {
            "source": "repo_artifact",
            "artifact_id": "raos-codex-mcp-abilities-v1",
            "slug": "raos-codex-mcp-abilities",
            "version": "1.3.1",
            "activation_intent": "activate",
        }
        return {
            "proposal": {
                "schema": "CodeReleaseProposalV1",
                "kind": "PLUGIN_CHANGE",
                "proposal_id": "a" * 64,
                "after_tree_sha256": "1" * 64,
                "code_package": {
                    "artifact_id": "raos-codex-mcp-abilities-v1",
                    "slug": "raos-codex-mcp-abilities",
                    "new_version": "1.3.1",
                    "package_sha256": digest,
                    "file_manifest_sha256": "1" * 64,
                    "activation_intent": "activate",
                    "migration_assessment": "MANUAL_REVIEW_REQUIRED",
                    "automatic_apply_eligible": False,
                },
            },
            "operation": {
                "proposal_id": "a" * 64,
                "operation_id": "b" * 64,
                "state": "MANUAL_REQUIRED",
            },
        }

    receipt_path = tmp_path / "receipt.json"

    def write_receipt(receipt: dict[str, object]) -> Path:
        stored.update(receipt)
        return receipt_path

    monkeypatch.setattr(bundle, "_write_receipt", write_receipt)
    assert bundle.propose(
        preview=lambda: events.append("preview"),
        build_runner=runner,
        deployment_call=deployment_call,
    ) == receipt_path
    assert events == ["preview", "--check", "--package", "plugin-propose-change"]
    assert stored["state"] == (
        "WAITING_FOR_SEPARATE_HUMAN_WP_ADMIN_BOOTSTRAP_ATTESTATION"
    )
    assert stored["apply_command_exposed"] is False
    assert '"plugin-apply-change"' not in SCRIPT.read_text(encoding="utf-8")


def test_measurement_command_requires_exact_applied_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposal_path = tmp_path / "proposal.json"
    apply_path = tmp_path / "apply.json"
    proposal_path.write_text(
        json.dumps(
            {
                "state": (
                    "WAITING_FOR_SEPARATE_HUMAN_WP_ADMIN_BOOTSTRAP_ATTESTATION"
                ),
                "proposal": {
                    "proposal_id": "a" * 64,
                    "operation_id": "b" * 64,
                    "after_sha256": "c" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    value = {
        "schema": "OperationReceiptV1",
        "proposal_id": "a" * 64,
        "operation_id": "b" * 64,
        "state": "APPLIED",
        "result_code": "PLUGIN_CHANGE_APPLIED",
        "after_sha256": "c" * 64,
    }
    apply_path.write_text(json.dumps(value), encoding="utf-8")
    proposal_path.chmod(0o600)
    apply_path.chmod(0o600)
    monkeypatch.setattr(bundle, "RECEIPT_PATH", proposal_path)

    command = bundle.measurement_command(apply_path)
    assert "measurement_plugin_proposal.py --propose" in command
    assert "--abilities-plugin-apply-receipt" in command
    assert command.endswith(apply_path.resolve().as_posix())

    value["result_code"] = "PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL"
    apply_path.write_text(json.dumps(value), encoding="utf-8")
    apply_path.chmod(0o600)
    assert "measurement_plugin_proposal.py --propose" in bundle.measurement_command(
        apply_path
    )

    value["result_code"] = "PLUGIN_MANUAL_OVERRIDE"
    apply_path.write_text(json.dumps(value), encoding="utf-8")
    apply_path.chmod(0o600)
    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_ABILITIES_PLUGIN_APPLY_RECEIPT_INVALID",
    ):
        bundle.measurement_command(apply_path)

    value["state"] = "APPROVED"
    value["result_code"] = "PLUGIN_CHANGE_APPLIED"
    apply_path.write_text(json.dumps(value), encoding="utf-8")
    apply_path.chmod(0o600)
    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_ABILITIES_PLUGIN_APPLY_RECEIPT_INVALID",
    ):
        bundle.measurement_command(apply_path)
