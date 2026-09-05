#!/usr/bin/env python3
"""Prepare/propose the fixed measurement plugin; never approve, apply, or gate it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PUBLICATION_SCRIPT = ROOT / "scripts/raos_wordpress_publication_request.py"
BUILD_SCRIPT = ROOT / "scripts/build_editorial_measurement_v1.py"
MANIFEST_PATH = ROOT / "changes/editorial-measurement-v1/runtime-manifest.v1.json"
REGISTRY_PATH = (
    ROOT / "changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json"
)
PACKAGE_PATH = (
    ROOT
    / ".secrets/wordpress-mcp/repo-plugin-artifacts"
    / "raos-editorial-measurement-v1.zip"
)
RECEIPT_PATH = (
    ROOT
    / ".secrets/wordpress-mcp/publication-requests"
    / "measurement-plugin-proposal-v3.json"
)
ABILITIES_PROPOSAL_RECEIPT_PATH = (
    ROOT
    / ".secrets/wordpress-mcp/publication-requests"
    / "abilities-plugin-proposal-v3.json"
)
SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")
REVIEWED_MIGRATION_ASSESSMENT = "REVIEWED_PLUGIN_OWNED_ACTIVATION_MIGRATION"
RAKUTEN_ATTRIBUTION_CONTRACT = {
    "provider_slot_count": 20,
    "provider_measurement_id_count": 20,
    "internal_cta_identity_count": 74,
    "live_link_count": 74,
    "direct_attribution_granularity": "ARTICLE_PLACEMENT",
    "product_or_cta_provider_attribution_allowed": False,
}

spec = importlib.util.spec_from_file_location("raos_publication_for_plugin", PUBLICATION_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("RAOS_MEASUREMENT_PLUGIN_PUBLICATION_IMPORT_FAILED")
publication = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = publication
spec.loader.exec_module(publication)


class SequenceFailure(RuntimeError):
    pass


def fail(code: str) -> None:
    raise SequenceFailure(code) from None


def load_json(path: Path, maximum: int = 4 * 1024 * 1024) -> dict[str, object]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_UNAVAILABLE")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != len(payload)
        or not 1 <= len(payload) <= maximum
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_INVALID")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_INVALID")
    if type(value) is not dict:
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_INVALID")
    return dict(value)


def load_private_json(path: Path) -> dict[str, object]:
    value = load_json(path)
    try:
        metadata = path.lstat()
    except OSError:
        fail("RAOS_MEASUREMENT_PLUGIN_APPLY_RECEIPT_INVALID")
    if (
        metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_APPLY_RECEIPT_INVALID")
    return value


def _write_receipt(value: Mapping[str, object]) -> Path:
    publication._ensure_private_directory()
    publication._atomic_receipt(RECEIPT_PATH, value)
    return RECEIPT_PATH


def validate_abilities_apply_receipt(path: Path | None) -> dict[str, object]:
    """Bind the measurement proposal to a separately applied MCP 1.3 release."""

    if path is None:
        fail("RAOS_MEASUREMENT_PLUGIN_ABILITIES_RECEIPT_REQUIRED")
    assert path is not None
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        fail("RAOS_MEASUREMENT_PLUGIN_ABILITIES_RECEIPT_INVALID")
    proposal_receipt = load_private_json(ABILITIES_PROPOSAL_RECEIPT_PATH)
    apply_receipt = load_private_json(resolved)
    proposal = proposal_receipt.get("proposal")
    if (
        proposal_receipt.get("state")
        != "WAITING_FOR_SEPARATE_HUMAN_WP_ADMIN_BOOTSTRAP_ATTESTATION"
        or proposal_receipt.get("artifact_id") != "raos-codex-mcp-abilities-v1"
        or proposal_receipt.get("plugin_slug") != "raos-codex-mcp-abilities"
        or proposal_receipt.get("plugin_version") != "1.3.1"
        or type(proposal) is not dict
        or apply_receipt.get("schema") != "OperationReceiptV1"
        or apply_receipt.get("proposal_id") != proposal.get("proposal_id")
        or apply_receipt.get("operation_id") != proposal.get("operation_id")
        or apply_receipt.get("state") != "APPLIED"
        or apply_receipt.get("result_code")
        not in {
            "PLUGIN_CHANGE_APPLIED",
            "PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL",
        }
        or apply_receipt.get("after_sha256") != proposal.get("after_sha256")
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_ABILITIES_RECEIPT_INVALID")
    return {
        "proposal_id": apply_receipt["proposal_id"],
        "operation_id": apply_receipt["operation_id"],
        "after_sha256": apply_receipt["after_sha256"],
        "plugin_version": "1.3.1",
    }


def prepare(
    *,
    preview: Callable[[], None] = publication.run_preview_checks,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, object]:
    preview()
    for mode in ("--check", "--package"):
        try:
            result = runner(
                (sys.executable, BUILD_SCRIPT.as_posix(), mode),
                cwd=ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=180,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "TZ": "UTC",
                },
            )
        except (OSError, subprocess.SubprocessError):
            fail("RAOS_MEASUREMENT_PLUGIN_BUILD_FAILED")
        if result.returncode != 0 or len(result.stdout) > 4096 or len(result.stderr) > 4096:
            fail("RAOS_MEASUREMENT_PLUGIN_BUILD_FAILED")
    manifest = load_json(MANIFEST_PATH)
    registry = load_json(REGISTRY_PATH)
    try:
        package_metadata = PACKAGE_PATH.lstat()
        package = PACKAGE_PATH.read_bytes()
    except OSError:
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_UNAVAILABLE")
    package_sha256 = hashlib.sha256(package).hexdigest()
    artifacts = registry.get("artifacts")
    matching = [
        row
        for row in artifacts
        if type(row) is dict
        and row.get("artifact_id") == "raos-editorial-measurement-v1"
    ] if type(artifacts) is list else []
    file_manifest_sha256 = hashlib.sha256(
        json.dumps(
            manifest.get("plugin_files"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    migration_review = (
        matching[0].get("migration_review") if len(matching) == 1 else None
    )
    if (
        manifest.get("schema") != "RAOS_EDITORIAL_MEASUREMENT_RUNTIME_MANIFEST_V1"
        or manifest.get("artifact_id") != "raos-editorial-measurement-v1"
        or manifest.get("plugin_slug") != "raos-editorial-measurement"
        or manifest.get("plugin_version") != "1.0.0"
        or manifest.get("default_enabled") is not False
        or manifest.get("host_gate") != "RAOS_MEASUREMENT_ENABLED"
        or manifest.get("package_sha256") != package_sha256
        or manifest.get("package_size") != len(package)
        or len(matching) != 1
        or matching[0].get("slug") != manifest.get("plugin_slug")
        or matching[0].get("version") != manifest.get("plugin_version")
        or matching[0].get("package_sha256") != package_sha256
        or type(migration_review) is not dict
        or set(migration_review)
        != {
            "schema",
            "assessment",
            "package_sha256",
            "file_manifest_sha256",
        }
        or migration_review.get("schema")
        != "RAOS_WORDPRESS_PLUGIN_MIGRATION_REVIEW_V1"
        or migration_review.get("assessment") != REVIEWED_MIGRATION_ASSESSMENT
        or migration_review.get("package_sha256") != package_sha256
        or migration_review.get("file_manifest_sha256")
        != file_manifest_sha256
        or PACKAGE_PATH.is_symlink()
        or not stat.S_ISREG(package_metadata.st_mode)
        or package_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(package_metadata.st_mode) != 0o600
        or not package
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_ARTIFACT_INVALID")
    return {
        "schema": "RAOS_MEASUREMENT_PLUGIN_PROPOSAL_RECEIPT_V3",
        "state": "LOCAL_PREVIEW_VERIFIED_PACKAGE_READY",
        "artifact_id": manifest["artifact_id"],
        "plugin_slug": manifest["plugin_slug"],
        "plugin_version": manifest["plugin_version"],
        "package_sha256": package_sha256,
        "file_manifest_sha256": file_manifest_sha256,
        "activation_intent": "activate",
        "separate_admin_approval_required": True,
        "apply_command_exposed": False,
        "measurement_gate_default_off": True,
        "rakuten_attribution_contract": dict(RAKUTEN_ATTRIBUTION_CONTRACT),
        "proposal": None,
    }


def propose(
    *,
    abilities_apply_receipt: Path | None,
    preview: Callable[[], None] = publication.run_preview_checks,
    build_runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    deployment_call: Callable[..., dict[str, object]] = publication._deployment_mcp_call,
) -> Path:
    abilities = validate_abilities_apply_receipt(abilities_apply_receipt)
    receipt = prepare(preview=preview, runner=build_runner)
    response = deployment_call(
        "plugin-propose-change",
        {
            "source": "repo_artifact",
            "artifact_id": receipt["artifact_id"],
            "slug": receipt["plugin_slug"],
            "version": receipt["plugin_version"],
            "activation_intent": "activate",
        },
        timeout=120,
    )
    proposal = response.get("proposal")
    operation = response.get("operation")
    code_package = proposal.get("code_package") if type(proposal) is dict else None
    if (
        type(proposal) is not dict
        or proposal.get("schema") != "CodeReleaseProposalV1"
        or proposal.get("kind") != "PLUGIN_CHANGE"
        or type(code_package) is not dict
        or code_package.get("artifact_id") != receipt["artifact_id"]
        or code_package.get("slug") != receipt["plugin_slug"]
        or code_package.get("new_version") != receipt["plugin_version"]
        or code_package.get("package_sha256") != receipt["package_sha256"]
        or code_package.get("file_manifest_sha256")
        != receipt["file_manifest_sha256"]
        or code_package.get("activation_intent") != "activate"
        or code_package.get("migration_assessment")
        != REVIEWED_MIGRATION_ASSESSMENT
        or code_package.get("automatic_apply_eligible") is not True
        or proposal.get("after_tree_sha256") != receipt["file_manifest_sha256"]
        or type(proposal.get("proposal_id")) is not str
        or SHA256_RE.fullmatch(proposal["proposal_id"]) is None
        or type(operation) is not dict
        or operation.get("proposal_id") != proposal["proposal_id"]
        or operation.get("state") != "PENDING"
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_PROPOSAL_INVALID")
    assert type(proposal) is dict
    assert type(operation) is dict
    receipt["state"] = "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL"
    receipt["abilities_plugin_apply"] = abilities
    receipt["proposal"] = {
        "proposal_id": proposal["proposal_id"],
        "operation_id": operation.get("operation_id"),
        "after_sha256": proposal.get("after_tree_sha256"),
    }
    return _write_receipt(receipt)


def content_command(
    apply_receipt_path: Path,
    rakuten_activation_dry_run: Path | None,
    quality_audit_attestation: Path | None,
    quality_audit_signature: Path | None,
) -> str:
    proposal_receipt = load_private_json(RECEIPT_PATH)
    apply_receipt = load_private_json(apply_receipt_path)
    proposal = proposal_receipt.get("proposal")
    if (
        proposal_receipt.get("state") != "WAITING_FOR_SEPARATE_ADMIN_PLUGIN_APPROVAL"
        or proposal_receipt.get("rakuten_attribution_contract")
        != RAKUTEN_ATTRIBUTION_CONTRACT
        or type(proposal) is not dict
        or apply_receipt.get("schema") != "OperationReceiptV1"
        or apply_receipt.get("proposal_id") != proposal.get("proposal_id")
        or apply_receipt.get("operation_id") != proposal.get("operation_id")
        or apply_receipt.get("state") != "APPLIED"
        or apply_receipt.get("result_code") != "PLUGIN_CHANGE_APPLIED"
        or apply_receipt.get("after_sha256") != proposal.get("after_sha256")
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_APPLY_RECEIPT_INVALID")
    if rakuten_activation_dry_run is None:
        fail("RAOS_MEASUREMENT_PLUGIN_RAKUTEN_ACTIVATION_INVALID")
    try:
        activation = publication.validate_rakuten_activation_dry_run(
            rakuten_activation_dry_run,
            require_recent=True,
        )
    except publication.PublicationFailure:
        fail("RAOS_MEASUREMENT_PLUGIN_RAKUTEN_ACTIVATION_INVALID")
    if (
        activation.article_count != 10
        or activation.provider_slot_count
        != RAKUTEN_ATTRIBUTION_CONTRACT["provider_slot_count"]
        or activation.provider_measurement_id_count
        != RAKUTEN_ATTRIBUTION_CONTRACT["provider_measurement_id_count"]
        or activation.internal_cta_identity_count
        != RAKUTEN_ATTRIBUTION_CONTRACT["internal_cta_identity_count"]
        or activation.cta_count != 74
        or activation.live_link_count
        != RAKUTEN_ATTRIBUTION_CONTRACT["live_link_count"]
    ):
        fail("RAOS_MEASUREMENT_PLUGIN_RAKUTEN_ACTIVATION_INVALID")
    try:
        publication.strict_local_quality_audit(
            quality_audit_attestation,
            quality_audit_signature,
        )
    except publication.PublicationFailure:
        fail("RAOS_MEASUREMENT_PLUGIN_QUALITY_AUDIT_INVALID")
    assert quality_audit_attestation is not None
    assert quality_audit_signature is not None
    return (
        ".venv/bin/python scripts/raos_wordpress_publication_request.py "
        "--articles all --measurement-plugin-apply-receipt "
        + shlex.quote(apply_receipt_path.resolve(strict=True).as_posix())
        + " --rakuten-activation-dry-run "
        + shlex.quote(rakuten_activation_dry_run.resolve(strict=True).as_posix())
        + " --quality-audit-attestation "
        + shlex.quote(quality_audit_attestation.resolve(strict=True).as_posix())
        + " --quality-audit-signature "
        + shlex.quote(quality_audit_signature.resolve(strict=True).as_posix())
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    group = result.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--propose", action="store_true")
    group.add_argument("--content-ready", type=Path)
    result.add_argument("--abilities-plugin-apply-receipt", type=Path)
    result.add_argument("--rakuten-activation-dry-run", type=Path)
    result.add_argument("--quality-audit-attestation", type=Path)
    result.add_argument("--quality-audit-signature", type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        if arguments.prepare:
            path = _write_receipt(prepare())
            print(path)
        elif arguments.propose:
            print(
                propose(
                    abilities_apply_receipt=arguments.abilities_plugin_apply_receipt
                )
            )
            print("Separate administrator approval/apply is required; measurement gate remains off.")
        else:
            print(
                content_command(
                    arguments.content_ready,
                    arguments.rakuten_activation_dry_run,
                    arguments.quality_audit_attestation,
                    arguments.quality_audit_signature,
                )
            )
        return 0
    except SequenceFailure as error:
        print(str(error), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
