from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
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
        preview=lambda: events.append("preview"),
        build_runner=runner,
        deployment_call=deployment_call,
    ) == receipt_path
    assert events == ["preview", "--check", "--package", "plugin-propose-change"]
    assert stored["state"] == "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL"
    assert stored["apply_command_exposed"] is False
    assert stored["measurement_gate_default_off"] is True
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"plugin-apply-change"' not in source
    assert "RAOS_MEASUREMENT_ENABLED=" not in source


def test_content_command_requires_exact_separate_plugin_apply_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposal_path = tmp_path / "proposal.json"
    apply_path = tmp_path / "apply.json"
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
    monkeypatch.setattr(bundle, "RECEIPT_PATH", proposal_path)

    command = bundle.content_command(apply_path)
    assert command.endswith("--articles all")

    apply_receipt["state"] = "APPROVED"
    apply_path.write_text(json.dumps(apply_receipt), encoding="utf-8")
    apply_path.chmod(0o600)
    with pytest.raises(
        bundle.SequenceFailure,
        match="RAOS_MEASUREMENT_PLUGIN_APPLY_RECEIPT_INVALID",
    ):
        bundle.content_command(apply_path)


def test_sequence_contract_orders_plugin_before_content_and_caps_batch() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == "RAOS_WORDPRESS_PRODUCTION_SEQUENCE_V3"
    assert contract["order"].index("measurement_plugin_proposal") < contract[
        "order"
    ].index("content_theme_batch_proposal")
    assert contract["content_batch"]["members"] == {
        "policy_pages": 3,
        "posts": 10,
        "theme_maximum": 1,
    }
    assert contract["content_batch"]["maximum_proposals"] == 14
    assert contract["measurement_plugin"]["apply_command_exposed"] is False
    assert contract["measurement_gate"]["enable_command_exposed"] is False
