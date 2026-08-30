from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "changes/wordpress-publication-bundle-v3/measurement_plugin_proposal.py"
)
CONTRACT = (
    ROOT / "changes/wordpress-publication-bundle-v3/production-sequence.v3.json"
)
SPEC = importlib.util.spec_from_file_location("measurement_plugin_proposal", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)


def _artifact_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> bytes:
    package = b"deterministic-measurement-plugin-zip"
    package_path = tmp_path / "raos-editorial-measurement-v1.zip"
    package_path.write_bytes(package)
    package_path.chmod(0o600)
    digest = __import__("hashlib").sha256(package).hexdigest()
    manifest_path = tmp_path / "runtime-manifest.v1.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "RAOS_EDITORIAL_MEASUREMENT_RUNTIME_MANIFEST_V1",
                "artifact_id": "raos-editorial-measurement-v1",
                "plugin_slug": "raos-editorial-measurement",
                "plugin_version": "1.0.0",
                "default_enabled": False,
                "host_gate": "RAOS_MEASUREMENT_ENABLED",
                "package_sha256": digest,
                "package_size": len(package),
                "plugin_files": [{"path": "plugin.php", "sha256": "1" * 64}],
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
                        "artifact_id": "raos-editorial-measurement-v1",
                        "slug": "raos-editorial-measurement",
                        "version": "1.0.0",
                        "package_sha256": digest,
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


def _abilities_apply_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    proposal_path = tmp_path / "abilities-proposal.json"
    apply_path = tmp_path / "abilities-applied.json"
    proposal_path.write_text(
        json.dumps(
            {
                "state": "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL",
                "artifact_id": "raos-codex-mcp-abilities-v1",
                "plugin_slug": "raos-codex-mcp-abilities",
                "plugin_version": "1.3.0",
                "proposal": {
                    "proposal_id": "d" * 64,
                    "operation_id": "e" * 64,
                    "after_sha256": "f" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    apply_path.write_text(
        json.dumps(
            {
                "schema": "OperationReceiptV1",
                "proposal_id": "d" * 64,
                "operation_id": "e" * 64,
                "state": "APPLIED",
                "result_code": "PLUGIN_CHANGE_APPLIED",
                "after_sha256": "f" * 64,
            }
        ),
        encoding="utf-8",
    )
    proposal_path.chmod(0o600)
    apply_path.chmod(0o600)
    monkeypatch.setattr(bundle, "ABILITIES_PROPOSAL_RECEIPT_PATH", proposal_path)
    return apply_path


def test_prepare_requires_preview_then_check_and_package(
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
    assert receipt["state"] == "LOCAL_PREVIEW_VERIFIED_PACKAGE_READY"
    assert receipt["measurement_gate_default_off"] is True
    assert receipt["apply_command_exposed"] is False
    assert stat.S_IMODE(bundle.PACKAGE_PATH.stat().st_mode) == 0o600


def test_proposal_stops_for_separate_admin_and_never_applies_or_enables_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _artifact_set(monkeypatch, tmp_path)
    abilities_apply = _abilities_apply_set(monkeypatch, tmp_path)
    digest = __import__("hashlib").sha256(package).hexdigest()
    file_manifest_sha256 = __import__("hashlib").sha256(
        json.dumps(
            [{"path": "plugin.php", "sha256": "1" * 64}],
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
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
            "artifact_id": "raos-editorial-measurement-v1",
            "slug": "raos-editorial-measurement",
            "version": "1.0.0",
            "activation_intent": "activate",
        }
        return {
            "proposal": {
                "schema": "CodeReleaseProposalV1",
                "kind": "PLUGIN_CHANGE",
                "proposal_id": "a" * 64,
                "after_tree_sha256": file_manifest_sha256,
                "code_package": {
                    "artifact_id": "raos-editorial-measurement-v1",
                    "slug": "raos-editorial-measurement",
                    "new_version": "1.0.0",
                    "package_sha256": digest,
                    "file_manifest_sha256": file_manifest_sha256,
                    "activation_intent": "activate",
                },
            },
            "operation": {
                "proposal_id": "a" * 64,
                "operation_id": "c" * 64,
                "state": "PENDING",
            },
        }

    receipt_path = tmp_path / "receipt.json"

    def write_receipt(receipt: dict[str, object]) -> Path:
        stored.update(receipt)
        return receipt_path

    monkeypatch.setattr(bundle, "_write_receipt", write_receipt)
    assert bundle.propose(
        abilities_apply_receipt=abilities_apply,
        preview=lambda: events.append("preview"),
        build_runner=runner,
        deployment_call=deployment_call,
    ) == receipt_path
    assert events == ["preview", "--check", "--package", "plugin-propose-change"]
    assert stored["state"] == "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL"
    assert stored["apply_command_exposed"] is False
    assert stored["measurement_gate_default_off"] is True
    assert stored["abilities_plugin_apply"] == {
        "proposal_id": "d" * 64,
        "operation_id": "e" * 64,
        "after_sha256": "f" * 64,
        "plugin_version": "1.3.0",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"plugin-apply-change"' not in source
    assert "RAOS_MEASUREMENT_ENABLED=" not in source


def test_proposal_requires_exact_applied_abilities_1_3_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _artifact_set(monkeypatch, tmp_path)
    apply_path = _abilities_apply_set(monkeypatch, tmp_path)

    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_MEASUREMENT_PLUGIN_ABILITIES_RECEIPT_REQUIRED",
    ):
        bundle.propose(abilities_apply_receipt=None)

    value = json.loads(apply_path.read_text(encoding="utf-8"))
    value["state"] = "APPROVED"
    apply_path.write_text(json.dumps(value), encoding="utf-8")
    apply_path.chmod(0o600)
    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_MEASUREMENT_PLUGIN_ABILITIES_RECEIPT_INVALID",
    ):
        bundle.propose(abilities_apply_receipt=apply_path)


def test_content_command_requires_exact_separate_plugin_apply_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposal_path = tmp_path / "proposal.json"
    apply_path = tmp_path / "apply.json"
    activation_path = tmp_path / "activation-dry-run.json"
    proposal_path.write_text(
        json.dumps(
            {
                "state": "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL",
                "proposal": {
                    "proposal_id": "a" * 64,
                    "operation_id": "c" * 64,
                    "after_sha256": "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    apply_receipt = {
        "schema": "OperationReceiptV1",
        "proposal_id": "a" * 64,
        "operation_id": "c" * 64,
        "state": "APPLIED",
        "result_code": "PLUGIN_CHANGE_APPLIED",
        "after_sha256": "b" * 64,
    }
    apply_path.write_text(json.dumps(apply_receipt), encoding="utf-8")
    proposal_path.chmod(0o600)
    apply_path.chmod(0o600)
    activation_path.write_text("{}", encoding="utf-8")
    activation_path.chmod(0o600)
    monkeypatch.setattr(bundle, "RECEIPT_PATH", proposal_path)
    observed_activation: list[Path | None] = []

    def validate_activation(path: Path | None, **_kwargs: object) -> object:
        observed_activation.append(path)
        if path is None:
            raise bundle.publication.PublicationFailure("required")
        return SimpleNamespace(article_count=10, cta_count=74)

    monkeypatch.setattr(
        bundle.publication,
        "validate_rakuten_activation_dry_run",
        validate_activation,
    )

    command = bundle.content_command(apply_path, activation_path)
    assert "--articles all --measurement-plugin-apply-receipt" in command
    assert "--rakuten-activation-dry-run" in command
    assert command.endswith(activation_path.resolve().as_posix())
    assert observed_activation == [activation_path]

    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_MEASUREMENT_PLUGIN_RAKUTEN_ACTIVATION_INVALID",
    ):
        bundle.content_command(apply_path, None)

    apply_receipt["state"] = "APPROVED"
    apply_path.write_text(json.dumps(apply_receipt), encoding="utf-8")
    apply_path.chmod(0o600)
    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_MEASUREMENT_PLUGIN_APPLY_RECEIPT_INVALID",
    ):
        bundle.content_command(apply_path, activation_path)


def test_sequence_contract_orders_plugin_before_content_and_caps_batch() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == "RAOS_WORDPRESS_PRODUCTION_SEQUENCE_V3"
    assert contract["order"].index("abilities_plugin_proposal") < contract[
        "order"
    ].index("measurement_plugin_proposal")
    assert contract["order"].index("measurement_plugin_proposal") < contract[
        "order"
    ].index("content_theme_batch_proposal")
    assert contract["content_batch"]["members"] == {
        "policy_pages": 3,
        "posts": 10,
        "theme_maximum": 1,
    }
    assert contract["content_batch"]["maximum_proposals"] == 14
    assert "--rakuten-activation-dry-run" in contract["content_batch"]["command"]
    assert "rakuten_v3_activation_dry_run_and_overlay" in contract["order"]
    assert contract["measurement_plugin"]["apply_command_exposed"] is False
    assert contract["measurement_gate"]["enable_command_exposed"] is False
    rollback = contract["incident_rollback"]
    assert rollback["automatic_execution"] is False
    assert rollback["rollback_command_exposed"] is False
    assert rollback["separate_admin_approval_required"] is True
    assert rollback["measurement_gate_off_first"] is True
    assert rollback["rakuten_links_must_remain_available"] is True
    assert rollback["post_rollback_readback_required"] is True
    assert rollback["order"] == [
        "measurement_gate_off",
        "preserve_rakuten_links",
        "restore_last_separately_admin_approved_snapshot",
        "authenticated_and_anonymous_readback",
    ]
    assert rollback["restore_scope"] == ["theme", "policy_pages", "posts"]
    assert rollback["snapshot_precondition"] == (
        "last_separately_admin_approved_publication_snapshot_with_exact_hashes"
    )
