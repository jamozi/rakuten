from __future__ import annotations

import copy
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import wordpress_quality_audit_v1 as audit


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT / "changes/wordpress-quality-audit-v1/quality-audit-contract.v1.json"
)
LEDGER_PATH = ROOT / "changes/wordpress-quality-audit-v1/quality-audit-ledger.v1.json"
EDITORIAL_EVIDENCE_SCHEMA_PATH = (
    ROOT / "changes/wordpress-quality-audit-v1/editorial-evidence.schema.json"
)
EDITORIAL_EVIDENCE_REGISTER_PATH = (
    ROOT / "changes/wordpress-quality-audit-v1/editorial-evidence-register.v1.json"
)
ARTICLE_FIXTURE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
EVALUATED_AT = datetime(2026, 8, 31, 10, 30, 0, tzinfo=UTC)
_TEST_EVIDENCE_ROOT: Path | None = None


@pytest.fixture(autouse=True)
def isolated_evidence_root(
    monkeypatch: pytest.MonkeyPatch,
    fingerprints: dict[str, str],
) -> Iterator[None]:
    global _TEST_EVIDENCE_ROOT
    with tempfile.TemporaryDirectory(
        prefix="raos-quality-evidence-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        _TEST_EVIDENCE_ROOT = root
        monkeypatch.setattr(audit, "DEFAULT_EVIDENCE_ROOT", root)

        def repository_snapshot(
            contract_value: dict[str, object], repository_root: Path = ROOT
        ) -> dict[str, str]:
            audit.validate_contract(contract_value)
            assert repository_root == ROOT
            return copy.deepcopy(fingerprints)

        monkeypatch.setattr(audit, "repository_fingerprints", repository_snapshot)
        yield
    _TEST_EVIDENCE_ROOT = None


@pytest.fixture(scope="session")
def contract() -> tuple[dict[str, object], str]:
    return audit.load_contract(CONTRACT_PATH)


@pytest.fixture(scope="session")
def fingerprints(contract: tuple[dict[str, object], str]) -> dict[str, str]:
    return audit.repository_fingerprints(contract[0], ROOT)


def _evidence_fields(
    *,
    round_id: str,
    reviewer_id: str,
    receipt_id: str,
    gate_id: str,
    surface_id: str,
    bundle: str,
    captured_at: datetime,
    status: str = "PASS",
) -> dict[str, str]:
    assert _TEST_EVIDENCE_ROOT is not None
    artifact_key = hashlib.sha256(f"{round_id}:{gate_id}".encode()).hexdigest()[:20]
    artifact_dir = _TEST_EVIDENCE_ROOT / "artifacts" / artifact_key
    manifest_dir = _TEST_EVIDENCE_ROOT / "manifests"
    artifact_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    command = {"tool": "pytest", "argv": ["pytest", gate_id], "exit_code": 0}
    captured = audit.timestamp_text(captured_at)
    command_record = {
        "schema": audit.COMMAND_RECORD_SCHEMA,
        "gate_id": gate_id,
        "surface_id": surface_id,
        "round_id": round_id,
        "reviewer_id": reviewer_id,
        "receipt_id": receipt_id,
        "fingerprint_bundle_sha256": bundle,
        "captured_at": captured,
        "command_tool": command["tool"],
        "command_argv": command["argv"],
        "command_exit_code": command["exit_code"],
    }
    command_raw = audit.canonical_json(command_record) + b"\n"
    command_path = artifact_dir / "command.json"
    command_path.write_bytes(command_raw)
    result = {
        "schema": audit.GATE_RESULT_SCHEMA,
        "gate_id": gate_id,
        "surface_id": surface_id,
        "round_id": round_id,
        "reviewer_id": reviewer_id,
        "receipt_id": receipt_id,
        "fingerprint_bundle_sha256": bundle,
        "status": status,
        "captured_at": captured,
        "command_tool": command["tool"],
        "command_argv": command["argv"],
        "command_exit_code": command["exit_code"],
    }
    result_raw = audit.canonical_json(result) + b"\n"
    result_path = artifact_dir / "result.json"
    result_path.write_bytes(result_raw)
    artifacts = [
        {
            "path": command_path.relative_to(_TEST_EVIDENCE_ROOT).as_posix(),
            "sha256": hashlib.sha256(command_raw).hexdigest(),
            "size": len(command_raw),
            "evidence_type": "command-record",
        },
        {
            "path": result_path.relative_to(_TEST_EVIDENCE_ROOT).as_posix(),
            "sha256": hashlib.sha256(result_raw).hexdigest(),
            "size": len(result_raw),
            "evidence_type": f"gate-result:{gate_id}",
        },
    ]
    for evidence_type in audit.EXPECTED_GATE_EVIDENCE_TYPES[gate_id]:
        support_path = artifact_dir / f"{evidence_type}.txt"
        support_raw = (
            f"gate={gate_id}\nround={round_id}\nreceipt={receipt_id}\n"
            f"evidence_type={evidence_type}\nstatus={status}\n"
        ).encode()
        support_path.write_bytes(support_raw)
        artifacts.append(
            {
                "path": support_path.relative_to(_TEST_EVIDENCE_ROOT).as_posix(),
                "sha256": hashlib.sha256(support_raw).hexdigest(),
                "size": len(support_raw),
                "evidence_type": evidence_type,
            }
        )
    manifest = audit.seal_evidence_manifest(
        {
            "schema": audit.EVIDENCE_MANIFEST_SCHEMA,
            "manifest_id": f"evidence-manifest-{artifact_key}",
            "receipt_id": receipt_id,
            "gate_id": gate_id,
            "surface_id": surface_id,
            "round_id": round_id,
            "reviewer_id": reviewer_id,
            "fingerprint_bundle_sha256": bundle,
            "captured_at": captured,
            "command": command,
            "artifacts": artifacts,
        }
    )
    manifest_raw = audit.canonical_json(manifest) + b"\n"
    manifest_path = manifest_dir / f"{artifact_key}.json"
    manifest_path.write_bytes(manifest_raw)
    return {
        "evidence_sha256": manifest["aggregate_sha256"],
        "evidence_manifest_path": manifest_path.relative_to(
            _TEST_EVIDENCE_ROOT
        ).as_posix(),
        "evidence_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
    }


def _clean_round(
    *,
    round_id: str,
    reviewer_id: str,
    fingerprints: dict[str, str],
    started_at: datetime,
    completed_at: datetime,
    previous_round_sha256: str | None,
) -> dict[str, object]:
    bundle = audit.fingerprint_bundle_sha256(fingerprints)
    surfaces = []
    receipts = []
    for surface_id, gate_id, _max_age in audit.EXPECTED_SURFACES:
        receipt_key = hashlib.sha256(f"{round_id}:{gate_id}".encode()).hexdigest()[:20]
        receipt_id = f"evidence-receipt-{receipt_key}"
        surfaces.append(
            {
                "surface_id": surface_id,
                "execution_status": "EXECUTED",
                "result": "PASS",
            }
        )
        evidence = _evidence_fields(
            round_id=round_id,
            reviewer_id=reviewer_id,
            receipt_id=receipt_id,
            gate_id=gate_id,
            surface_id=surface_id,
            bundle=bundle,
            captured_at=completed_at,
        )
        receipts.append(
            audit.seal_receipt(
                {
                    "receipt_id": receipt_id,
                    "gate_id": gate_id,
                    "surface_id": surface_id,
                    "round_id": round_id,
                    "reviewer_id": reviewer_id,
                    "fingerprint_bundle_sha256": bundle,
                    "status": "PASS",
                    **evidence,
                    "captured_at": audit.timestamp_text(completed_at),
                    "freshness": "FRESH",
                }
            )
        )
    return audit.seal_round(
        {
            "round_id": round_id,
            "reviewer_id": reviewer_id,
            "started_at": audit.timestamp_text(started_at),
            "completed_at": audit.timestamp_text(completed_at),
            "fingerprints": copy.deepcopy(fingerprints),
            "fingerprint_bundle_sha256": bundle,
            "previous_round_sha256": previous_round_sha256,
            "surfaces": surfaces,
            "gate_receipts": receipts,
            "findings": [],
            "actionable_finding_count": 0,
            "status": "PASS",
        }
    )


def _two_clean_rounds(fingerprints: dict[str, str]) -> list[dict[str, object]]:
    first = _clean_round(
        round_id="independent-quality-round-001",
        reviewer_id="independent-reviewer-alpha",
        fingerprints=fingerprints,
        started_at=EVALUATED_AT - timedelta(seconds=800),
        completed_at=EVALUATED_AT - timedelta(seconds=700),
        previous_round_sha256=None,
    )
    second = _clean_round(
        round_id="independent-quality-round-002",
        reviewer_id="independent-reviewer-bravo",
        fingerprints=fingerprints,
        started_at=EVALUATED_AT - timedelta(seconds=600),
        completed_at=EVALUATED_AT - timedelta(seconds=500),
        previous_round_sha256=str(first["round_sha256"]),
    )
    return [first, second]


def _ledger(
    *,
    contract_hash: str,
    fingerprints: dict[str, str],
    rounds: list[dict[str, object]],
    evaluated_at: datetime = EVALUATED_AT,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": audit.LEDGER_SCHEMA,
        "version": audit.VERSION,
        "audit_phase": audit.PRE_PUBLICATION_PHASE_ID,
        "contract_sha256": contract_hash,
        "evaluated_at": audit.timestamp_text(evaluated_at),
        "repository_fingerprints": copy.deepcopy(fingerprints),
        "external_execution": copy.deepcopy(audit.EXPECTED_EXTERNAL_EXECUTION),
        "rounds": rounds,
    }
    value["completion"] = audit.completion_for_rounds(rounds, fingerprints)
    return audit.seal_ledger(value)


def _contract_with_trusted_reviewer(
    contract: dict[str, object],
    private_key: Ed25519PrivateKey,
    *,
    reviewer_key_id: str = "trusted-independent-reviewer-key-001",
    reviewer_id: str = "independent-reviewer-bravo",
) -> tuple[dict[str, object], str]:
    value = copy.deepcopy(contract)
    policy = value["independent_reviewer_attestation"]
    assert isinstance(policy, dict)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    policy["trusted_reviewer_keys"] = [
        {
            "reviewer_key_id": reviewer_key_id,
            "reviewer_id": reviewer_id,
            "signature_algorithm": audit.ATTESTATION_SIGNATURE_ALGORITHM,
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        }
    ]
    audit.validate_contract(value)
    return value, hashlib.sha256(audit.canonical_json(value)).hexdigest()


def _codex_owner_inputs(
    tmp_path: Path,
    contract_hash: str,
    fingerprints: dict[str, str],
    rounds: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    rounds = rounds if rounds is not None else _two_clean_rounds(fingerprints)
    ledger = _ledger(
        contract_hash=contract_hash, fingerprints=fingerprints, rounds=rounds
    )
    ledger_raw = (json.dumps(ledger, ensure_ascii=False) + "\n").encode()
    ledger_path = tmp_path / "unsigned-ledger.json"
    ledger_path.write_bytes(ledger_raw)
    report: dict[str, object] = {
        "schema": audit.CODEX_OWNER_REPORT_SCHEMA,
        "audit_mode": "codex-owner",
        "review_kind": "CODEX_TECHNICAL_REVIEW",
        "publication_authority": False,
        "owner_approval_required": True,
        "execution_identity_authentication": "OWNER_REVIEW_REQUIRED",
        "reviewer_attestation_verified": False,
        "contract_file_sha256": contract_hash,
        "ledger_file_sha256": hashlib.sha256(ledger_raw).hexdigest(),
        "ledger_sha256": ledger["ledger_sha256"],
        "fingerprint_bundle_sha256": audit.fingerprint_bundle_sha256(fingerprints),
        "evaluated_at": audit.timestamp_text(EVALUATED_AT),
        "expires_at": audit.timestamp_text(EVALUATED_AT + timedelta(seconds=600)),
        "implementation_execution_ids": ["synthetic-author-execution"],
        "review_runs": [
            {
                **{
                    key: row[key] for key in ("round_id", "reviewer_id", "round_sha256")
                },
                "execution_id": f"synthetic-codex-review-{index}",
            }
            for index, row in enumerate(rounds)
        ],
    }
    report_path = tmp_path / "synthetic-codex-owner-report.json"
    report_path.write_bytes(audit.canonical_json(report) + b"\n")
    return report_path, ledger_path, report


def test_codex_owner_checks_do_not_become_signed_or_publication_authority(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
) -> None:
    report_path, ledger_path, _ = _codex_owner_inputs(
        tmp_path, contract[1], fingerprints
    )
    binding = audit.validate_codex_owner_report(
        report_path,
        ledger_path=ledger_path,
        now=EVALUATED_AT,
    )
    assert binding["completion_state"] == "READY_FOR_OWNER_REVIEW"
    assert binding["reviewer_attestation_verified"] is False
    assert binding["publication_authority"] is False
    assert binding["owner_approval_required"] is True
    assert binding["execution_identity_authentication"] == "OWNER_REVIEW_REQUIRED"
    ledger, _raw = audit.read_json(ledger_path)
    legacy = audit.validate_document(ledger, contract[0], contract[1], now=EVALUATED_AT)
    assert legacy.status == "BLOCKED"
    assert legacy.reviewer_attestation_verified is False


def test_codex_owner_binding_shortens_expiry_to_earliest_gate(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
) -> None:
    first_end = EVALUATED_AT - timedelta(
        seconds=min(age for _, _, age in audit.EXPECTED_SURFACES) - 100
    )
    first = _clean_round(
        round_id="codex-round-early",
        reviewer_id="codex-reviewer-early",
        fingerprints=fingerprints,
        started_at=first_end - timedelta(seconds=100),
        completed_at=first_end,
        previous_round_sha256=None,
    )
    second = _clean_round(
        round_id="codex-round-late",
        reviewer_id="codex-reviewer-late",
        fingerprints=fingerprints,
        started_at=EVALUATED_AT - timedelta(seconds=600),
        completed_at=EVALUATED_AT - timedelta(seconds=500),
        previous_round_sha256=str(first["round_sha256"]),
    )
    report_path, ledger_path, _ = _codex_owner_inputs(
        tmp_path,
        contract[1],
        fingerprints,
        [first, second],
    )
    result = audit.validate_codex_owner_report(
        report_path, ledger_path=ledger_path, now=EVALUATED_AT
    )
    assert result["expires_at"] == audit.timestamp_text(
        EVALUATED_AT + timedelta(seconds=100)
    )
    with pytest.raises(audit.QualityAuditFailure, match="CODEX_REPORT_EXPIRED"):
        audit.validate_codex_owner_report(
            report_path,
            ledger_path=ledger_path,
            now=EVALUATED_AT + timedelta(seconds=100),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("audit_mode", "signed-independent"),
        ("reviewer_attestation_verified", True),
        ("reviewer_attestation_verified", 0),
        ("publication_authority", True),
        ("owner_approval_required", False),
        ("execution_identity_authentication", "VERIFIED"),
        ("ledger_file_sha256", "f" * 64),
        ("fingerprint_bundle_sha256", "f" * 64),
        ("implementation_execution_ids", []),
        ("implementation_execution_ids", ["synthetic-codex-review-0"]),
        ("review_runs", []),
        ("expires_at", "2026-08-31T11:30:00Z"),
    ],
)
def test_codex_owner_report_rejects_tampering(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    field: str,
    value: object,
) -> None:
    report_path, ledger_path, report = _codex_owner_inputs(
        tmp_path, contract[1], fingerprints
    )
    report[field] = value
    report_path.write_bytes(audit.canonical_json(report) + b"\n")
    with pytest.raises(audit.QualityAuditFailure):
        audit.validate_codex_owner_report(
            report_path, ledger_path=ledger_path, now=EVALUATED_AT
        )


def test_codex_owner_rejects_same_execution_for_both_reviews(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
) -> None:
    report_path, ledger_path, report = _codex_owner_inputs(
        tmp_path, contract[1], fingerprints
    )
    report["review_runs"][1]["execution_id"] = report["review_runs"][0]["execution_id"]
    report_path.write_bytes(audit.canonical_json(report) + b"\n")
    with pytest.raises(audit.QualityAuditFailure, match="CODEX_EXECUTION_INVALID"):
        audit.validate_codex_owner_report(
            report_path, ledger_path=ledger_path, now=EVALUATED_AT
        )


def test_codex_owner_rejects_expiry_and_missing_evidence(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
) -> None:
    report_path, ledger_path, _ = _codex_owner_inputs(
        tmp_path, contract[1], fingerprints
    )
    with pytest.raises(audit.QualityAuditFailure, match="CODEX_REPORT_EXPIRED"):
        audit.validate_codex_owner_report(
            report_path,
            ledger_path=ledger_path,
            now=EVALUATED_AT + timedelta(seconds=600),
        )
    assert _TEST_EVIDENCE_ROOT is not None
    artifact = next((_TEST_EVIDENCE_ROOT / "artifacts").rglob("test-report.txt"))
    artifact.write_text("tampered evidence\n")
    with pytest.raises(audit.QualityAuditFailure):
        audit.validate_codex_owner_report(
            report_path, ledger_path=ledger_path, now=EVALUATED_AT
        )


def test_codex_owner_rejects_blocked_baseline(
    tmp_path: Path,
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
) -> None:
    report_path, ledger_path, report = _codex_owner_inputs(
        tmp_path, contract[1], fingerprints
    )
    baseline = audit.build_blocked_baseline(
        contract[0], contract[1], fingerprints, evaluated_at=EVALUATED_AT
    )
    raw = (json.dumps(baseline, ensure_ascii=False) + "\n").encode()
    ledger_path.write_bytes(raw)
    report["ledger_file_sha256"] = hashlib.sha256(raw).hexdigest()
    report["ledger_sha256"] = baseline["ledger_sha256"]
    report_path.write_bytes(audit.canonical_json(report) + b"\n")
    with pytest.raises(audit.QualityAuditFailure, match="CODEX_EVIDENCE_INCOMPLETE"):
        audit.validate_codex_owner_report(
            report_path, ledger_path=ledger_path, now=EVALUATED_AT
        )


def _attestation_payload(
    rounds: list[dict[str, object]],
    fingerprints: dict[str, str],
    contract_hash: str,
    *,
    completed_at: datetime = EVALUATED_AT,
    expires_at: datetime | None = None,
    reviewer_key_id: str = "trusted-independent-reviewer-key-001",
) -> dict[str, object]:
    expiry = expires_at or completed_at + timedelta(seconds=600)
    return {
        "schema": audit.ATTESTATION_SCHEMA,
        "version": audit.VERSION,
        "audit_phase": audit.PRE_PUBLICATION_PHASE_ID,
        "signature_algorithm": audit.ATTESTATION_SIGNATURE_ALGORITHM,
        "reviewer_key_id": reviewer_key_id,
        "reviewer_id": rounds[-1]["reviewer_id"],
        "audit_contract_sha256": contract_hash,
        "repository_fingerprint_bundle_sha256": (
            audit.fingerprint_bundle_sha256(fingerprints)
        ),
        "rounds": [
            {
                "round_id": row["round_id"],
                "reviewer_id": row["reviewer_id"],
                "round_sha256": row["round_sha256"],
            }
            for row in rounds[-2:]
        ],
        "completed_at": audit.timestamp_text(completed_at),
        "expires_at": audit.timestamp_text(expiry),
        "independence_statement": audit.INDEPENDENCE_STATEMENT,
    }


def _write_attestation_files(
    tmp_path: Path,
    payload: dict[str, object],
    private_key: Ed25519PrivateKey,
    *,
    canonical: bool = True,
) -> tuple[Path, Path]:
    payload_path = tmp_path / "independent-reviewer-attestation.json"
    signature_path = tmp_path / "independent-reviewer-attestation.ed25519.b64"
    signed_bytes = audit.canonical_json(payload)
    if canonical:
        payload_path.write_bytes(signed_bytes + b"\n")
    else:
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    signature = private_key.sign(signed_bytes)
    signature_path.write_bytes(base64.b64encode(signature) + b"\n")
    payload_path.chmod(0o600)
    signature_path.chmod(0o600)
    return payload_path, signature_path


def _attested_ledger(
    *,
    contract_hash: str,
    fingerprints: dict[str, str],
    rounds: list[dict[str, object]],
) -> dict[str, object]:
    value = _ledger(
        contract_hash=contract_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )
    external_execution = value["external_execution"]
    assert isinstance(external_execution, dict)
    external_execution["independent_reviewer_attestation_verification"] = "EXECUTED"
    value["completion"] = audit.completion_for_rounds(
        rounds,
        fingerprints,
        reviewer_attestation_verified=True,
    )
    return audit.seal_ledger(value)


def _post_apply_result(
    contract_hash: str,
    *,
    captured_at: datetime = EVALUATED_AT,
) -> dict[str, object]:
    return audit.seal_post_apply_result(
        {
            "schema": audit.POST_APPLY_RESULT_SCHEMA,
            "version": audit.VERSION,
            "audit_phase": audit.POST_APPLY_PHASE_ID,
            "status": "COMPLETE",
            "completion_state": audit.POST_APPLY_COMPLETION_STATE,
            "contract_sha256": contract_hash,
            "pre_publication_ledger_sha256": "a" * 64,
            "captured_at": audit.timestamp_text(captured_at),
            "origin": "https://kurashinoshirube.com",
            "release_receipt_sha256": "b" * 64,
            "external_execution": {
                name: "EXECUTED"
                for name in audit.EXPECTED_POST_APPLY_EXTERNAL_EXECUTION
            },
            "surface": {
                "surface_id": "production_migration_parity_readback",
                "gate_id": "production_migration_parity_readback",
                "execution_status": "EXECUTED",
                "result": "PASS",
                "freshness": "FRESH",
            },
            "parity_checks": {name: "PASS" for name in audit.POST_APPLY_PARITY_CHECKS},
            "evidence_bindings": {
                name: hashlib.sha256(f"post-apply:{name}".encode()).hexdigest()
                for name in audit.POST_APPLY_PARITY_CHECKS
            },
        }
    )


def _rechain_and_seal(
    value: dict[str, object], fingerprints: dict[str, str]
) -> dict[str, object]:
    rounds = value["rounds"]
    assert isinstance(rounds, list)
    previous = None
    sealed_rounds = []
    for raw in rounds:
        row = copy.deepcopy(raw)
        row["previous_round_sha256"] = previous
        row = audit.seal_round(row)
        previous = row["round_sha256"]
        sealed_rounds.append(row)
    value["rounds"] = sealed_rounds
    value["completion"] = audit.completion_for_rounds(sealed_rounds, fingerprints)
    return audit.seal_ledger(value)


def _assert_failure(
    value: dict[str, object],
    contract: tuple[dict[str, object], str],
    code: str,
) -> None:
    with pytest.raises(audit.QualityAuditFailure, match=code):
        audit.validate_document(
            value,
            contract[0],
            contract[1],
            repository_root=ROOT,
            now=EVALUATED_AT,
        )


def _read_receipt_manifest(
    receipt: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    assert _TEST_EVIDENCE_ROOT is not None
    path = _TEST_EVIDENCE_ROOT / str(receipt["evidence_manifest_path"])
    return path, json.loads(path.read_text(encoding="utf-8"))


def _resign_manifest_receipt(
    round_row: dict[str, object],
    receipt_index: int,
    path: Path,
    manifest: dict[str, object],
) -> None:
    sealed_manifest = audit.seal_evidence_manifest(manifest)
    manifest_raw = audit.canonical_json(sealed_manifest) + b"\n"
    path.write_bytes(manifest_raw)
    receipts = round_row["gate_receipts"]
    assert isinstance(receipts, list)
    receipt = receipts[receipt_index]
    assert isinstance(receipt, dict)
    receipt["evidence_sha256"] = sealed_manifest["aggregate_sha256"]
    receipt["evidence_manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    receipts[receipt_index] = audit.seal_receipt(receipt)


def test_contract_has_exact_required_surface_and_boundary_inventory(
    contract: tuple[dict[str, object], str],
) -> None:
    value, contract_hash = contract
    assert len(contract_hash) == 64
    assert (
        value["editorial_evidence_policy"] == audit.EXPECTED_EDITORIAL_EVIDENCE_POLICY
    )
    assert [row["fingerprint_id"] for row in value["fingerprint_groups"]] == [
        "source",
        "theme",
        "fixture",
        "navigation",
        "inventory",
    ]
    phases = value["audit_phases"]
    pre_publication = phases["pre_publication"]
    post_apply = phases["post_apply"]
    assert pre_publication["phase_id"] == audit.PRE_PUBLICATION_PHASE_ID
    assert pre_publication["completion_state"] == (
        audit.PRE_PUBLICATION_COMPLETION_STATE
    )
    assert [row["surface_id"] for row in pre_publication["required_surfaces"]] == [
        row[0] for row in audit.EXPECTED_PRE_PUBLICATION_SURFACES
    ]
    assert post_apply["phase_id"] == audit.POST_APPLY_PHASE_ID
    assert post_apply["completion_state"] == audit.POST_APPLY_COMPLETION_STATE
    assert [row["surface_id"] for row in post_apply["required_surfaces"]] == [
        row[0] for row in audit.EXPECTED_POST_APPLY_SURFACES
    ]
    independent_surfaces = {
        "epistemic_negative_claims_and_calculation_semantics",
        "editorial_language_story_ia",
        "editorial_accountability_author_credentials_corrections",
        "content_originality_copyright_near_duplicate_risk",
        "contact_corrections_operational_deliverability",
        "search_intent_cannibalization_orphaning",
        "product_selection_lifecycle_support",
        "candidate_universe_representativeness_and_brand_blindspots",
        "consumer_safety_recall_compatibility",
        "smart_device_app_cloud_security_update_eol_privacy",
        "battery_large_appliance_disposal_recycling_transport",
        "freshness_maintenance_ownership",
        "affiliate_fairness_dark_patterns",
        "legal_disclosure_media_rights",
        "provenance_reproducibility_recovery",
        "wordpress_backup_rollback_reproducible_restoration",
        "dependency_supply_chain_plugin_integrity",
        "analytics_data_minimization_accuracy",
        "cognitive_accessibility_japanese_readability",
        "browser_resilience_no_js_error_recovery",
        "browser_compatibility_restricted_environment_resilience",
        "task_based_decision_usability_reader_comprehension",
        "japanese_locale_measurement_semantics_inclusive_language",
        "touch_gesture_orientation_400_percent_reflow_target_size",
        "wordpress_public_attack_abuse_surface",
        "operations_observability_incident_ownership",
        "affiliate_program_compliance_destination_integrity",
        "slow_device_network_resource_budget_caching",
    }
    assert independent_surfaces <= {
        row["surface_id"] for row in pre_publication["required_surfaces"]
    }
    gate_ids = [row["gate_id"] for row in pre_publication["required_surfaces"]]
    assert len(pre_publication["required_surfaces"]) == 37
    assert len(gate_ids) == len(set(gate_ids))
    assert {
        row["gate_id"]: tuple(row["required_evidence_types"])
        for row in (
            *pre_publication["required_surfaces"],
            *post_apply["required_surfaces"],
        )
    } == audit.EXPECTED_GATE_EVIDENCE_TYPES
    assert pre_publication["completion_policy"] == (
        audit.EXPECTED_PRE_PUBLICATION_POLICY
    )
    assert post_apply["completion_policy"] == audit.EXPECTED_POST_APPLY_POLICY
    assert tuple(post_apply["required_external_execution"]) == (
        audit.EXPECTED_POST_APPLY_EXTERNAL_EXECUTION
    )
    assert value["independent_reviewer_attestation"] == {
        **audit.EXPECTED_ATTESTATION_POLICY_FIXED,
        "trusted_reviewer_keys": [],
    }
    assert value["external_execution"] == audit.EXPECTED_EXTERNAL_EXECUTION
    assert set(value["external_execution"].values()) == {"NOT_EXECUTED"}
    assert {
        value["external_execution"][boundary]
        for boundary in {
            "contact_delivery_operational_test",
            "independent_reviewer_attestation_verification",
            "legal_review",
            "production_affiliate_destination_integrity_readback",
            "production_cache_cdn_invalidation_readback",
            "production_consent_runtime_readback",
            "production_content_roundtrip_readback",
            "production_migration_parity_readback",
            "production_observability_readback",
            "production_public_attack_surface_readback",
            "production_robots_indexability_readback",
            "production_seo_schema_readback",
            "production_taxonomy_term_identity",
        }
    } == {"NOT_EXECUTED"}
    source_inputs = value["fingerprint_groups"][0]["inputs"]
    assert "changes/editorial-measurement-v1" in source_inputs
    assert "changes/st-1704/self-hosted-editorial-pilot-v1/media" in source_inputs
    assert (
        "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
        in source_inputs
    )
    assert "changes/wordpress-quality-audit-v1/README.md" in source_inputs
    assert (
        "python/raos/application/editorial/product_safety_receipts.py" in source_inputs
    )
    assert "tests/editorial_product_safety_receipts" in source_inputs
    assert "tests/wordpress_quality_audit_v1" in source_inputs
    assert "changes/wordpress-mcp-v1/runtime-manifest.v1.json" not in source_inputs


@pytest.mark.parametrize(
    "required_input",
    [
        "python/raos/application/editorial/product_safety_receipts.py",
        "tests/editorial_product_safety_receipts",
    ],
)
def test_product_safety_fingerprint_input_omission_is_rejected(
    contract: tuple[dict[str, object], str], required_input: str
) -> None:
    tampered = copy.deepcopy(contract[0])
    tampered["fingerprint_groups"][0]["inputs"].remove(required_input)
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_CONTRACT_FINGERPRINTS_INVALID",
    ):
        audit.validate_contract(tampered)


def test_production_parity_cannot_be_moved_back_into_pre_publication_phase(
    contract: tuple[dict[str, object], str],
) -> None:
    tampered = copy.deepcopy(contract[0])
    phases = tampered["audit_phases"]
    phases["pre_publication"]["required_surfaces"].append(
        copy.deepcopy(phases["post_apply"]["required_surfaces"][0])
    )
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_CONTRACT_SURFACES_INVALID",
    ):
        audit.validate_contract(tampered)


def test_post_apply_phase_or_surface_omission_is_rejected(
    contract: tuple[dict[str, object], str],
) -> None:
    missing_phase = copy.deepcopy(contract[0])
    missing_phase["audit_phases"].pop("post_apply")
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_CONTRACT_PHASES_INVALID",
    ):
        audit.validate_contract(missing_phase)

    missing_surface = copy.deepcopy(contract[0])
    missing_surface["audit_phases"]["post_apply"]["required_surfaces"] = []
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_CONTRACT_SURFACES_INVALID",
    ):
        audit.validate_contract(missing_surface)


def test_post_apply_parity_requires_fresh_exact_complete_evidence(
    contract: tuple[dict[str, object], str],
) -> None:
    result = _post_apply_result(contract[1])
    validated = audit.validate_post_apply_result(
        result,
        contract[0],
        contract[1],
        now=EVALUATED_AT,
    )
    assert validated.audit_phase == audit.POST_APPLY_PHASE_ID
    assert validated.status == "COMPLETE"
    assert validated.completion_state == audit.POST_APPLY_COMPLETION_STATE


@pytest.mark.parametrize(
    ("tamper", "code"),
    [
        ("phase", "QUALITY_AUDIT_POST_APPLY_INVALID"),
        ("execution", "QUALITY_AUDIT_POST_APPLY_EXECUTION_INVALID"),
        ("check", "QUALITY_AUDIT_POST_APPLY_CHECKS_INVALID"),
        ("evidence_reuse", "QUALITY_AUDIT_POST_APPLY_EVIDENCE_INVALID"),
        ("surface", "QUALITY_AUDIT_POST_APPLY_SURFACE_INVALID"),
    ],
)
def test_post_apply_parity_tamper_is_rejected_after_resealing(
    contract: tuple[dict[str, object], str], tamper: str, code: str
) -> None:
    result = _post_apply_result(contract[1])
    if tamper == "phase":
        result["audit_phase"] = audit.PRE_PUBLICATION_PHASE_ID
    elif tamper == "execution":
        result["external_execution"]["production"] = "NOT_EXECUTED"
    elif tamper == "check":
        result["parity_checks"]["options"] = "NOT_EXECUTED"
    elif tamper == "evidence_reuse":
        result["evidence_bindings"]["menus"] = result["evidence_bindings"]["options"]
    else:
        result["surface"]["freshness"] = "STALE"
    result = audit.seal_post_apply_result(result)
    with pytest.raises(audit.QualityAuditFailure, match=code):
        audit.validate_post_apply_result(
            result,
            contract[0],
            contract[1],
            now=EVALUATED_AT,
        )


def test_post_apply_parity_rejects_stale_and_hash_tamper(
    contract: tuple[dict[str, object], str],
) -> None:
    stale = _post_apply_result(
        contract[1], captured_at=EVALUATED_AT - timedelta(seconds=901)
    )
    with pytest.raises(
        audit.QualityAuditFailure, match="QUALITY_AUDIT_POST_APPLY_TIME_INVALID"
    ):
        audit.validate_post_apply_result(
            stale,
            contract[0],
            contract[1],
            now=EVALUATED_AT,
        )

    tampered_hash = _post_apply_result(contract[1])
    tampered_hash["result_sha256"] = "f" * 64
    with pytest.raises(
        audit.QualityAuditFailure, match="QUALITY_AUDIT_POST_APPLY_HASH_INVALID"
    ):
        audit.validate_post_apply_result(
            tampered_hash,
            contract[0],
            contract[1],
            now=EVALUATED_AT,
        )


def test_post_apply_path_requires_absolute_owner_controlled_canonical_json(
    contract: tuple[dict[str, object], str], tmp_path: Path
) -> None:
    result = _post_apply_result(contract[1])
    path = (tmp_path / "production-parity-result.v1.json").resolve()
    path.write_bytes(audit.canonical_json(result) + b"\n")
    path.chmod(0o600)
    validated = audit.validate_post_apply_path(path, now=EVALUATED_AT)
    assert validated.status == "COMPLETE"

    with pytest.raises(
        audit.QualityAuditFailure, match="QUALITY_AUDIT_POST_APPLY_PATH_INVALID"
    ):
        audit.validate_post_apply_path(Path(path.name), now=EVALUATED_AT)

    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_POST_APPLY_CANONICAL_JSON_INVALID",
    ):
        audit.validate_post_apply_path(path, now=EVALUATED_AT)


def test_third_party_editorial_boundary_is_fail_closed_in_contract(
    contract: tuple[dict[str, object], str],
) -> None:
    tampered = copy.deepcopy(contract[0])
    tampered["editorial_evidence_policy"][
        "third_party_blog_recommendation_evidence"
    ] = "ALLOWED"
    with pytest.raises(
        audit.QualityAuditFailure, match="QUALITY_AUDIT_CONTRACT_INVALID"
    ):
        audit.validate_contract(tampered)


def test_editorial_evidence_schema_register_and_current_articles_are_fail_closed() -> (
    None
):
    schema = json.loads(EDITORIAL_EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    register = json.loads(EDITORIAL_EVIDENCE_REGISTER_PATH.read_text(encoding="utf-8"))

    audit.validate_editorial_evidence_schema(schema)
    audit.validate_editorial_evidence_register(register)
    audit.validate_editorial_article_surfaces(register, ARTICLE_FIXTURE_ROOT)

    assert register["reviewed_on"] == "2026-09-01"
    assert len(register["article_modes"]) == 10
    assert {row["evidence_mode"] for row in register["article_modes"]} == {
        "OFFICIAL_SPEC_COMPARISON_NON_HANDS_ON"
    }
    assert register["records"] == []


def _third_party_report() -> dict[str, object]:
    return {
        "record_id": "third-party-report-001",
        "evidence_kind": "THIRD_PARTY_REPORT",
        "article_slug": "carry-on-suitcase-comparison",
        "exact_model": "Example Model 01",
        "publisher": "Example Publisher",
        "published_date": "2026-08-20",
        "checked_date": "2026-09-01",
        "usage_conditions": "舗装路を5km走行し、荷物5kgを収納",
        "source_url": "https://example.com/reports/example-model-01",
        "locator": "h2『走行条件』直下の第2段落",
        "attribution_label": "第三者による報告",
        "recommendation_use": False,
        "review_label_use": False,
        "best_claim_use": False,
    }


@pytest.mark.parametrize(
    "missing_field",
    [
        "exact_model",
        "publisher",
        "published_date",
        "checked_date",
        "usage_conditions",
        "source_url",
        "locator",
    ],
)
def test_third_party_report_rejects_every_missing_attribution_field(
    missing_field: str,
) -> None:
    record = _third_party_report()
    record.pop(missing_field)

    with pytest.raises(
        audit.QualityAuditFailure, match="EDITORIAL_EVIDENCE_RECORD_INVALID"
    ):
        audit.validate_editorial_evidence_record(
            record, article_slugs={"carry-on-suitcase-comparison"}
        )


@pytest.mark.parametrize(
    "prohibited_field", ["recommendation_use", "review_label_use", "best_claim_use"]
)
def test_third_party_report_cannot_be_recommendation_review_or_best_evidence(
    prohibited_field: str,
) -> None:
    record = _third_party_report()
    record[prohibited_field] = True

    with pytest.raises(
        audit.QualityAuditFailure, match="EDITORIAL_EVIDENCE_RECORD_INVALID"
    ):
        audit.validate_editorial_evidence_record(
            record, article_slugs={"carry-on-suitcase-comparison"}
        )


def _hands_on_record() -> dict[str, object]:
    return {
        "record_id": "editorial-hands-on-001",
        "evidence_kind": "EDITORIAL_HANDS_ON",
        "article_slug": "carry-on-suitcase-comparison",
        "exact_model": "Example Model 01",
        "checked_date": "2026-09-01",
        "direct_use_confirmed": True,
        "acquisition_route": "編集部が正規販売店で購入",
        "provided_or_loaned": False,
        "conflict_disclosure": "提供・貸与・広告主の事前確認なし",
        "usage_start_date": "2026-08-20",
        "usage_end_date": "2026-08-31",
        "usage_environment": "屋内と舗装路、荷物5kg",
        "verification_method": "寸法・重量・走行条件を事前定義して記録",
        "original_device_evidence_refs": [
            {
                "kind": "PHOTO",
                "path": "evidence/example-model-01/photo-001.webp",
                "sha256": "1" * 64,
            }
        ],
    }


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_direct_use",
        "direct_use_false",
        "missing_conflict",
        "missing_method",
        "missing_original_evidence",
    ],
)
def test_hands_on_label_rejects_missing_direct_use_evidence(tamper: str) -> None:
    record = _hands_on_record()
    if tamper == "missing_direct_use":
        record.pop("direct_use_confirmed")
    elif tamper == "direct_use_false":
        record["direct_use_confirmed"] = False
    elif tamper == "missing_conflict":
        record.pop("conflict_disclosure")
    elif tamper == "missing_method":
        record.pop("verification_method")
    else:
        record["original_device_evidence_refs"] = []

    with pytest.raises(
        audit.QualityAuditFailure, match="EDITORIAL_EVIDENCE_RECORD_INVALID"
    ):
        audit.validate_editorial_evidence_record(
            record, article_slugs={"carry-on-suitcase-comparison"}
        )


def test_current_non_hands_on_register_rejects_even_complete_hands_on_record() -> None:
    register = json.loads(EDITORIAL_EVIDENCE_REGISTER_PATH.read_text(encoding="utf-8"))
    register["records"] = [_hands_on_record()]

    with pytest.raises(
        audit.QualityAuditFailure, match="EDITORIAL_EVIDENCE_REGISTER_INVALID"
    ):
        audit.validate_editorial_evidence_register(register)


def test_v2_selection_input_cannot_mark_unfinished_due_diligence_complete() -> None:
    portfolio = json.loads(
        (ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_text(
            encoding="utf-8"
        )
    )
    products = portfolio["selection_audits"]["products"]
    assert len(products) == len(portfolio["products"]) == 33
    assert {product["product_id"] for product in products} == {
        product["product_id"] for product in portfolio["products"]
    }
    for product in products:
        assessments = product["axis_assessments"]
        for axis in ("safety", "warranty_and_support", "maintainability"):
            assert assessments[axis] == (
                "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
            )


def test_split_crosscutting_surfaces_have_separate_blocked_receipts_and_findings(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    ledger = audit.build_blocked_baseline(
        contract[0], contract[1], fingerprints, evaluated_at=EVALUATED_AT
    )
    round_row = ledger["rounds"][0]
    split_ids = {
        "epistemic_negative_claims_and_calculation_semantics",
        "editorial_language_story_ia",
        "editorial_accountability_author_credentials_corrections",
        "content_originality_copyright_near_duplicate_risk",
        "contact_corrections_operational_deliverability",
        "search_intent_cannibalization_orphaning",
        "product_selection_lifecycle_support",
        "candidate_universe_representativeness_and_brand_blindspots",
        "consumer_safety_recall_compatibility",
        "smart_device_app_cloud_security_update_eol_privacy",
        "battery_large_appliance_disposal_recycling_transport",
        "freshness_maintenance_ownership",
        "affiliate_fairness_dark_patterns",
        "legal_disclosure_media_rights",
        "provenance_reproducibility_recovery",
        "wordpress_backup_rollback_reproducible_restoration",
        "dependency_supply_chain_plugin_integrity",
        "analytics_data_minimization_accuracy",
        "cognitive_accessibility_japanese_readability",
        "browser_resilience_no_js_error_recovery",
        "browser_compatibility_restricted_environment_resilience",
        "task_based_decision_usability_reader_comprehension",
        "japanese_locale_measurement_semantics_inclusive_language",
        "touch_gesture_orientation_400_percent_reflow_target_size",
        "wordpress_public_attack_abuse_surface",
        "operations_observability_incident_ownership",
        "affiliate_program_compliance_destination_integrity",
        "slow_device_network_resource_budget_caching",
    }
    receipts = {
        receipt["surface_id"]: receipt for receipt in round_row["gate_receipts"]
    }
    findings = {finding["surface_id"]: finding for finding in round_row["findings"]}
    assert split_ids <= receipts.keys()
    assert split_ids <= findings.keys()
    assert len({receipts[surface_id]["receipt_id"] for surface_id in split_ids}) == len(
        split_ids
    )
    assert all(
        receipts[surface_id]["status"] == "NOT_EXECUTED"
        and receipts[surface_id]["freshness"] == "NOT_EXECUTED"
        for surface_id in split_ids
    )
    assert all(
        findings[surface_id]["actionable"] is True
        and findings[surface_id]["status"] == "OPEN"
        for surface_id in split_ids
    )
    summary_blob = " ".join(
        (
            *audit.BASELINE_FINDING_SUMMARIES.values(),
            *audit.POST_APPLY_FINDING_SUMMARIES.values(),
        )
    ).lower()
    for required_phrase in (
        "claim/locator trace audit",
        "source-packet completeness, conflicts, snapshot locators",
        "every contributor locator for multi-source claims",
        "required llms.txt absence",
        "negative claims lack explicit official evidence checks",
        "unknown promotion",
        "superlatives",
        "difference calculations across mismatched scope, units, dimension axes",
        "product names and sales state",
        "seven-axis due diligence is 0/33 complete",
        "sku use fit",
        "no-buy/keep conclusions",
        "cross-brand multi-brand official sources",
        "selected+external direct/lifecycle sets",
        "4-slot compression",
        "same-axis visible exclusion tradeoffs",
        "brand bias",
        "dominant-peer role-only exclusion",
        "price/reward/rakuten weight zero",
        "all 33 selected-product safety reviews are recheck_required",
        "sku recall receipts (query/period/ambiguity)",
        "safety/notice/compatibility/japan-warranty locators",
        "generic pages cannot pass",
        "none_found is observed-only",
        "publication blocked",
        "smart-device app/cloud/account dependencies",
        "offline degradation",
        "security-update and vulnerability commitments",
        "app/cloud/device eol behavior",
        "battery and large-appliance products",
        "japan-specific official disposal",
        "battery removal",
        "damaged-cell handling",
        "transport restrictions",
        "claim expiry and sales/specification/recall/warranty/model-end/successor",
        "recheck owners and cadence",
        "source-snapshot expiry",
        "consumables/repair continuity",
        "per-article opening monetization-status disclosure",
        "formal legal review has not been executed",
        "without asserting legal compliance",
        "dark-pattern absence",
        "first-50-word hook",
        "formal product name at first mention",
        "single takeaway",
        "comparison-to-judgment-to-action story flow",
        "heading-only scan quality",
        "category and internal-link intent",
        "closing-loop quality",
        "proof-before-action cta order",
        "equal exposure for all selected products",
        "count, density and prominence",
        "neutral labels",
        "existing id/slug and no-new-post invariants",
        "local category-term identity",
        "10-article audience/scope/writer/fact-checker/date/no-hands-on",
        "who/how/why fields",
        "reader-visible ai-assistance and independent-audit explanations",
        "no false credentials",
        "policy/ai links",
        "contact@kurashinoshirube.com",
        "correction/update/history ownership",
        "byline/schema match",
        "originality/near-duplicate",
        "quotation-limit, attribution",
        "copyright-safe paraphrase audits",
        "third-party blogs are axis exploration only",
        "never experience/recommendation",
        "review/aggregaterating are prohibited",
        "contact deliverability",
        "correction triage and escalation",
        "bounce monitoring",
        "assumed address is not operational proof",
        "search-intent ownership, cannibalization, orphan detection",
        "primary-secondary internal routes",
        "actual cookies, web storage, indexeddb, cache, service workers",
        "consent withdrawal",
        "default-off tracking",
        "image/copyright licenses",
        "image/control accessible names",
        "table header relations for screen readers",
        "overlong headings",
        "repeated cta pressure",
        "acyclic predecessor/successor",
        "semantic-independent runtime revisions",
        "rest-to-db-to-rest/html round-trip",
        "kses/gutenberg preservation",
        "class/data/aria/details/table/cta attributes",
        "checksum-bound wordpress backup and restore",
        "content/theme/plugin/options rollback",
        "same-fixture resync idempotency",
        "cache/cdn invalidation and old-html absence",
        "rpo/rto evidence",
        "post-restore verification",
        "yoast checksum/version pinning",
        "parent-theme/php/wordpress compatibility",
        "supply-chain integrity",
        "legacy-slug and trailing-slash redirects",
        "sponsored/nofollow rel",
        "final destinations",
        "37 product-card placements; 33 unique products",
        "74 cta",
        "130 runtime screenshots",
        "product-misidentification controls",
        "neutral/manufacturer fallback absence",
        "10 article-specific header comparison visuals",
        "exactly one hero per page",
        "runtime screenshots",
        "javascript and no-javascript behavior",
        "console/network failures",
        "state reset",
        "no-storage/no-cookie/private/restricted-network modes",
        "third-party blocking",
        "font/image/cta failure",
        "print/no-css information retention",
        "author/date/tag/attachment/feed/rest exposure and indexability",
        "xml sitemap/robots",
        "pagination/legacy canonicals",
        "html lang",
        "timezone/date formatting",
        "fixture-only evidence is not runtime proof",
        "representative reader tasks",
        "correct product/no-buy outcomes",
        "static proxy checks cannot pass",
        "japanese units, dimension axes, rounding",
        "inclusive non-stereotyping language",
        "400% reflow",
        "target size/spacing",
        "comment forms/feeds/x-pingback",
        "xml-rpc and rest users",
        "closed seed defaults are not production proof",
        "tls/domain/email expiry",
        "alert routing",
        "rakuten program/image terms",
        "sku/variant landing consistency",
        "slow-device/network request, byte, font, image",
        "cache-header and third-party budgets",
        "production id/slug/meta/taxonomy/options/menu/media-guid/permalink parity",
        "local mappings cannot substitute",
    ):
        assert required_phrase in summary_blob


def test_independent_surface_receipt_cannot_be_relabelled_as_another_gate(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    round_row = value["rounds"][0]
    receipts = round_row["gate_receipts"]
    source = next(
        receipt
        for receipt in receipts
        if receipt["surface_id"] == "legal_disclosure_media_rights"
    )
    target_index = next(
        index
        for index, receipt in enumerate(receipts)
        if receipt["surface_id"] == "affiliate_fairness_dark_patterns"
    )
    copied = copy.deepcopy(source)
    copied["receipt_id"] = "cross-surface-relabelled-receipt-001"
    copied["evidence_sha256"] = hashlib.sha256(
        b"cross-surface-relabelled-evidence-001"
    ).hexdigest()
    receipts[target_index] = audit.seal_receipt(copied)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_RECEIPT_BINDING_INVALID")


def test_copy_review_criteria_are_bound_to_their_independent_surfaces() -> None:
    editorial = audit.BASELINE_FINDING_SUMMARIES["editorial_language_story_ia"].lower()
    search_ia = audit.BASELINE_FINDING_SUMMARIES[
        "search_intent_cannibalization_orphaning"
    ].lower()
    cognitive = audit.BASELINE_FINDING_SUMMARIES[
        "cognitive_accessibility_japanese_readability"
    ].lower()
    affiliate = audit.BASELINE_FINDING_SUMMARIES[
        "affiliate_fairness_dark_patterns"
    ].lower()

    for phrase in (
        "first-50-word hook",
        "formal product name at first mention",
        "single takeaway",
        "comparison-to-judgment-to-action story flow",
        "closing-loop quality",
    ):
        assert phrase in editorial
    assert "category and internal-link intent" in search_ia
    assert "heading-only scan quality" in cognitive
    for phrase in (
        "proof-before-action cta order",
        "count, density and prominence",
        "neutral labels",
        "equal exposure for all selected products",
    ):
        assert phrase in affiliate


def test_recent_reader_media_and_source_regressions_have_explicit_gates() -> None:
    sources = audit.BASELINE_FINDING_SUMMARIES["editorial_sources"].lower()
    media = audit.BASELINE_FINDING_SUMMARIES["product_media_cta_evidence"].lower()
    assert "every contributor locator for multi-source claims" in sources
    assert "exactly one hero per page" in media
    assert "10 article-specific header comparison visuals" in media
    assert "runtime screenshots" in media


def test_tracked_baseline_is_exact_blocked_not_executed_document(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    evaluated = datetime.strptime(ledger["evaluated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    expected = audit.build_blocked_baseline(
        contract[0], contract[1], fingerprints, evaluated_at=evaluated
    )
    assert ledger == expected
    result = audit.validate_document(
        ledger,
        contract[0],
        contract[1],
        repository_root=ROOT,
        now=evaluated + timedelta(days=30),
    )
    assert result.status == "BLOCKED"
    assert result.consecutive_clean_rounds == 0
    assert all(
        surface["execution_status"] == "NOT_EXECUTED"
        for surface in ledger["rounds"][0]["surfaces"]
    )
    assert all(
        receipt["status"] == receipt["freshness"] == "NOT_EXECUTED"
        for receipt in ledger["rounds"][0]["gate_receipts"]
    )
    assert len(ledger["rounds"][0]["findings"]) == len(audit.EXPECTED_SURFACES)
    assert all(
        finding["actionable"] is True and finding["status"] == "OPEN"
        for finding in ledger["rounds"][0]["findings"]
    )


def test_cli_reserves_success_for_complete_and_reports_baseline_blocked() -> None:
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/wordpress_quality_audit_v1.py"),
            "validate",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "BLOCKED"
    assert result.stderr == ""


def test_cli_renderer_can_only_emit_an_honest_blocked_baseline() -> None:
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/wordpress_quality_audit_v1.py"),
            "render-blocked-baseline",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    ledger = json.loads(result.stdout)
    assert ledger["completion"]["status"] == "BLOCKED"
    assert ledger["completion"]["consecutive_clean_rounds"] == 0
    assert set(ledger["external_execution"].values()) == {"NOT_EXECUTED"}
    assert all(
        surface["execution_status"] == "NOT_EXECUTED" and surface["result"] == "BLOCKED"
        for surface in ledger["rounds"][0]["surfaces"]
    )


def test_cli_writer_updates_only_the_tracked_blocked_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "quality-audit-ledger.v1.json"
    monkeypatch.setattr(audit, "DEFAULT_LEDGER_PATH", output)

    assert audit.main(["write-blocked-baseline"]) == 0

    ledger = json.loads(output.read_text(encoding="utf-8"))
    assert ledger["completion"]["status"] == "BLOCKED"
    assert ledger["completion"]["consecutive_clean_rounds"] == 0
    assert set(ledger["external_execution"].values()) == {"NOT_EXECUTED"}


def test_two_fresh_self_asserted_clean_rounds_stay_blocked_without_attestation(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    rounds = _two_clean_rounds(fingerprints)
    one = _ledger(
        contract_hash=contract[1], fingerprints=fingerprints, rounds=rounds[:1]
    )
    one_result = audit.validate_document(
        one,
        contract[0],
        contract[1],
        repository_root=ROOT,
        now=EVALUATED_AT,
    )
    assert one_result.status == "BLOCKED"
    assert one_result.consecutive_clean_rounds == 1
    assert (
        "INDEPENDENT_REVIEWER_ATTESTATION_NOT_VERIFIED"
        in one["completion"]["reason_codes"]
    )

    two = _ledger(contract_hash=contract[1], fingerprints=fingerprints, rounds=rounds)
    two_result = audit.validate_document(
        two,
        contract[0],
        contract[1],
        repository_root=ROOT,
        now=EVALUATED_AT,
    )
    assert two_result.status == "BLOCKED"
    assert two_result.consecutive_clean_rounds == 2
    assert two["completion"]["reason_codes"] == [
        "INDEPENDENT_REVIEWER_ATTESTATION_NOT_VERIFIED"
    ]


def test_two_clean_rounds_complete_only_with_trusted_ed25519_attestation(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key
    )
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    result = audit.validate_document(
        ledger,
        trusted_contract,
        trusted_hash,
        repository_root=ROOT,
        attestation_path=payload_path,
        attestation_signature_path=signature_path,
        now=EVALUATED_AT,
    )

    assert result.status == "COMPLETE"
    assert result.audit_phase == audit.PRE_PUBLICATION_PHASE_ID
    assert result.completion_state == audit.PRE_PUBLICATION_COMPLETION_STATE
    assert result.production_parity_state == audit.POST_APPLY_PENDING_STATE
    assert result.consecutive_clean_rounds == 2
    assert result.reviewer_attestation_verified is True
    assert ledger["external_execution"]["production_migration_parity_readback"] == (
        "NOT_EXECUTED"
    )
    assert ledger["completion"]["production_parity_state"] == (
        audit.POST_APPLY_PENDING_STATE
    )


def test_attestation_payload_tamper_is_rejected_even_when_ledger_is_resealed(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key
    )
    payload["independence_statement"] = "TAMPERED_INDEPENDENCE_STATEMENT"
    payload_path.write_bytes(audit.canonical_json(payload) + b"\n")
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_SIGNATURE_INVALID",
    ):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_attestation_signed_by_wrong_key_is_rejected(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    trusted_private_key = Ed25519PrivateKey.generate()
    wrong_private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], trusted_private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, wrong_private_key
    )
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_SIGNATURE_INVALID",
    ):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_caller_generated_key_cannot_replace_the_tracked_trust_store(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    caller_private_key = Ed25519PrivateKey.generate()
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, contract[1])
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, caller_private_key
    )
    ledger = _attested_ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_REVIEWER_NOT_TRUSTED",
    ):
        audit.validate_document(
            ledger,
            contract[0],
            contract[1],
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_attestation_replay_against_a_different_completion_time_is_rejected(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key
    )
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )
    ledger["evaluated_at"] = audit.timestamp_text(EVALUATED_AT + timedelta(seconds=1))
    ledger = audit.seal_ledger(ledger)

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_TIME_INVALID",
    ):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_expired_attestation_is_rejected(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    expires_at = EVALUATED_AT + timedelta(seconds=60)
    payload = _attestation_payload(
        rounds, fingerprints, trusted_hash, expires_at=expires_at
    )
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key
    )
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(
        audit.QualityAuditFailure, match="QUALITY_AUDIT_ATTESTATION_EXPIRED"
    ):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=expires_at + timedelta(seconds=1),
        )


def test_duplicate_trusted_reviewer_identity_is_rejected(
    contract: tuple[dict[str, object], str],
) -> None:
    first_key = Ed25519PrivateKey.generate()
    second_key = Ed25519PrivateKey.generate()
    trusted_contract, _trusted_hash = _contract_with_trusted_reviewer(
        contract[0], first_key
    )
    policy = trusted_contract["independent_reviewer_attestation"]
    assert isinstance(policy, dict)
    trusted_keys = policy["trusted_reviewer_keys"]
    assert isinstance(trusted_keys, list)
    second_public = second_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trusted_keys.append(
        {
            "reviewer_key_id": "trusted-independent-reviewer-key-002",
            "reviewer_id": "independent-reviewer-bravo",
            "signature_algorithm": audit.ATTESTATION_SIGNATURE_ALGORITHM,
            "public_key_base64": base64.b64encode(second_public).decode("ascii"),
        }
    )

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_TRUST_STORE_DUPLICATE",
    ):
        audit.validate_contract(trusted_contract)


@pytest.mark.parametrize("invalid_input", ["relative_path", "symlink", "mode", "size"])
def test_attestation_input_path_is_fail_closed(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
    invalid_input: str,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key
    )
    expected = {
        "relative_path": "QUALITY_AUDIT_ATTESTATION_PATH_INVALID",
        "symlink": "QUALITY_AUDIT_ATTESTATION_SYMLINK_REFUSED",
        "mode": "QUALITY_AUDIT_ATTESTATION_MODE_INVALID",
        "size": "QUALITY_AUDIT_ATTESTATION_SIZE_INVALID",
    }[invalid_input]
    if invalid_input == "relative_path":
        payload_path = Path(payload_path.name)
    elif invalid_input == "symlink":
        preserved = tmp_path / "preserved-attestation.json"
        payload_path.rename(preserved)
        payload_path.symlink_to(preserved)
    elif invalid_input == "mode":
        payload_path.chmod(0o666)
    else:
        payload_path.write_bytes(b"x" * (audit.MAX_ATTESTATION_BYTES + 1))
        payload_path.chmod(0o600)
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(audit.QualityAuditFailure, match=expected):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_attestation_file_must_be_exact_canonical_json(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted_contract, trusted_hash = _contract_with_trusted_reviewer(
        contract[0], private_key
    )
    rounds = _two_clean_rounds(fingerprints)
    payload = _attestation_payload(rounds, fingerprints, trusted_hash)
    payload_path, signature_path = _write_attestation_files(
        tmp_path, payload, private_key, canonical=False
    )
    ledger = _attested_ledger(
        contract_hash=trusted_hash,
        fingerprints=fingerprints,
        rounds=rounds,
    )

    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_CANONICAL_JSON_INVALID",
    ):
        audit.validate_document(
            ledger,
            trusted_contract,
            trusted_hash,
            repository_root=ROOT,
            attestation_path=payload_path,
            attestation_signature_path=signature_path,
            now=EVALUATED_AT,
        )


def test_attestation_and_signature_paths_form_a_required_pair(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    ledger = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    with pytest.raises(
        audit.QualityAuditFailure,
        match="QUALITY_AUDIT_ATTESTATION_INPUT_PAIR_REQUIRED",
    ):
        audit.validate_document(
            ledger,
            contract[0],
            contract[1],
            repository_root=ROOT,
            attestation_path=Path("/does/not/matter.json"),
            now=EVALUATED_AT,
        )


def test_one_byte_input_drift_changes_exact_file_set_fingerprint(
    tmp_path: Path,
) -> None:
    target = tmp_path / "input.txt"
    target.write_bytes(b"A")
    first = audit.sha256_value(
        {
            "algorithm": audit.FINGERPRINT_ALGORITHM,
            "files": audit._fingerprint_files(tmp_path, ("input.txt",)),
            "fingerprint_id": "source",
        }
    )
    target.write_bytes(b"B")
    second = audit.sha256_value(
        {
            "algorithm": audit.FINGERPRINT_ALGORITHM,
            "files": audit._fingerprint_files(tmp_path, ("input.txt",)),
            "fingerprint_id": "source",
        }
    )
    assert first != second


def test_latest_one_byte_fingerprint_tamper_is_rejected(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    first = _two_clean_rounds(fingerprints)[0]
    changed = copy.deepcopy(fingerprints)
    original = changed["source"]
    changed["source"] = ("0" if original[0] != "0" else "1") + original[1:]
    second = _clean_round(
        round_id="tampered-fingerprint-round-002",
        reviewer_id="tampered-fingerprint-reviewer-bravo",
        fingerprints=changed,
        started_at=EVALUATED_AT - timedelta(seconds=600),
        completed_at=EVALUATED_AT - timedelta(seconds=500),
        previous_round_sha256=str(first["round_sha256"]),
    )
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=[first, second],
    )
    _assert_failure(value, contract, "QUALITY_AUDIT_LATEST_FINGERPRINTS_DRIFTED")


def test_historical_fingerprint_drift_resets_streak_instead_of_counting_two(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    old = copy.deepcopy(fingerprints)
    old["theme"] = ("0" if old["theme"][0] != "0" else "1") + old["theme"][1:]
    first = _clean_round(
        round_id="historical-quality-round-001",
        reviewer_id="historical-reviewer-alpha",
        fingerprints=old,
        started_at=EVALUATED_AT - timedelta(seconds=800),
        completed_at=EVALUATED_AT - timedelta(seconds=700),
        previous_round_sha256=None,
    )
    second = _clean_round(
        round_id="current-quality-round-002",
        reviewer_id="current-reviewer-bravo",
        fingerprints=fingerprints,
        started_at=EVALUATED_AT - timedelta(seconds=600),
        completed_at=EVALUATED_AT - timedelta(seconds=500),
        previous_round_sha256=str(first["round_sha256"]),
    )
    value = _ledger(
        contract_hash=contract[1], fingerprints=fingerprints, rounds=[first, second]
    )
    result = audit.validate_document(
        value,
        contract[0],
        contract[1],
        repository_root=ROOT,
        now=EVALUATED_AT,
    )
    assert result.status == "BLOCKED"
    assert result.consecutive_clean_rounds == 1
    assert "FINGERPRINT_DRIFT_RESET" in value["completion"]["reason_codes"]


@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        ("reviewer", "QUALITY_AUDIT_REVIEWER_ID_DUPLICATE"),
        ("round", "QUALITY_AUDIT_ROUND_ID_DUPLICATE"),
        ("receipt", "QUALITY_AUDIT_RECEIPT_ID_DUPLICATE"),
    ],
)
def test_duplicate_independent_identities_are_rejected(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    identity: str,
    expected: str,
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    first, second = value["rounds"]
    if identity == "reviewer":
        second["reviewer_id"] = first["reviewer_id"]
        for index, receipt in enumerate(second["gate_receipts"]):
            receipt["reviewer_id"] = second["reviewer_id"]
            second["gate_receipts"][index] = audit.seal_receipt(receipt)
    elif identity == "round":
        second["round_id"] = first["round_id"]
        for index, receipt in enumerate(second["gate_receipts"]):
            receipt["round_id"] = second["round_id"]
            second["gate_receipts"][index] = audit.seal_receipt(receipt)
    else:
        second["gate_receipts"][0]["receipt_id"] = first["gate_receipts"][0][
            "receipt_id"
        ]
        second["gate_receipts"][0] = audit.seal_receipt(second["gate_receipts"][0])
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, expected)


@pytest.mark.parametrize("missing_kind", ["surface", "findings"])
def test_missing_or_unexecuted_surface_with_empty_findings_is_rejected(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    missing_kind: str,
) -> None:
    value = audit.build_blocked_baseline(
        contract[0], contract[1], fingerprints, evaluated_at=EVALUATED_AT
    )
    row = value["rounds"][0]
    row["findings"] = []
    row["actionable_finding_count"] = 0
    if missing_kind == "surface":
        row["surfaces"].pop()
        expected = "QUALITY_AUDIT_SURFACES_INVALID"
    else:
        expected = "QUALITY_AUDIT_NONPASS_WITHOUT_FINDING"
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, expected)


def test_stale_receipt_cannot_remain_fresh_in_a_clean_round(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    first = value["rounds"][0]
    first["started_at"] = audit.timestamp_text(EVALUATED_AT - timedelta(seconds=1100))
    product_receipt = next(
        receipt
        for receipt in first["gate_receipts"]
        if receipt["gate_id"] == "product_media_cta_activation"
    )
    product_receipt["captured_at"] = audit.timestamp_text(
        EVALUATED_AT - timedelta(seconds=1000)
    )
    index = first["gate_receipts"].index(product_receipt)
    first["gate_receipts"][index] = audit.seal_receipt(product_receipt)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_RECEIPT_FRESHNESS_INVALID")


def test_altered_previous_round_hash_is_rejected(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    second = value["rounds"][1]
    second["previous_round_sha256"] = "0" * 64
    second = audit.seal_round(second)
    value["rounds"][1] = second
    value["completion"] = audit.completion_for_rounds(value["rounds"], fingerprints)
    value = audit.seal_ledger(value)
    _assert_failure(value, contract, "QUALITY_AUDIT_PREVIOUS_ROUND_HASH_INVALID")


def test_copied_clean_receipt_and_evidence_cannot_be_rebound_to_a_new_round(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    first, second = value["rounds"]
    copied = copy.deepcopy(first["gate_receipts"][0])
    copied["receipt_id"] = "copied-clean-code-receipt-unique"
    copied["round_id"] = second["round_id"]
    copied["reviewer_id"] = second["reviewer_id"]
    copied["captured_at"] = second["completed_at"]
    second["gate_receipts"][0] = audit.seal_receipt(copied)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_EVIDENCE_MANIFEST_REUSED")


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("hash", "QUALITY_AUDIT_EVIDENCE_MANIFEST_HASH_INVALID"),
        ("path", "QUALITY_AUDIT_EVIDENCE_FILE_MISSING"),
    ],
)
def test_fabricated_manifest_hash_and_missing_path_cannot_pass(
    contract: tuple[dict[str, object], str],
    fingerprints: dict[str, str],
    tamper: str,
    expected: str,
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    receipt = value["rounds"][0]["gate_receipts"][0]
    if tamper == "hash":
        receipt["evidence_manifest_sha256"] = "f" * 64
    else:
        receipt["evidence_manifest_path"] = "manifests/does-not-exist.json"
    value["rounds"][0]["gate_receipts"][0] = audit.seal_receipt(receipt)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, expected)


def test_arbitrary_receipt_evidence_hash_cannot_replace_manifest_aggregate(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    receipt = value["rounds"][0]["gate_receipts"][0]
    receipt["evidence_sha256"] = "a" * 64
    value["rounds"][0]["gate_receipts"][0] = audit.seal_receipt(receipt)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_EVIDENCE_AGGREGATE_INVALID")


def test_one_byte_evidence_artifact_drift_is_rejected(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    receipt = value["rounds"][0]["gate_receipts"][0]
    _manifest_path, manifest = _read_receipt_manifest(receipt)
    assert _TEST_EVIDENCE_ROOT is not None
    artifact_path = _TEST_EVIDENCE_ROOT / manifest["artifacts"][0]["path"]
    artifact_path.write_bytes(artifact_path.read_bytes() + b"X")
    _assert_failure(value, contract, "QUALITY_AUDIT_EVIDENCE_ARTIFACT_HASH_INVALID")


def test_missing_gate_specific_evidence_type_is_rejected(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    round_row = value["rounds"][0]
    receipt = round_row["gate_receipts"][0]
    manifest_path, manifest = _read_receipt_manifest(receipt)
    manifest["artifacts"][-1]["evidence_type"] = "unrelated-report"
    _resign_manifest_receipt(round_row, 0, manifest_path, manifest)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_GATE_EVIDENCE_TYPE_MISSING")


def test_altered_command_record_cannot_be_resigned_as_pass(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    round_row = value["rounds"][0]
    receipt = round_row["gate_receipts"][0]
    manifest_path, manifest = _read_receipt_manifest(receipt)
    command_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["evidence_type"] == "command-record"
    )
    assert _TEST_EVIDENCE_ROOT is not None
    command_path = _TEST_EVIDENCE_ROOT / command_artifact["path"]
    command_record = json.loads(command_path.read_text(encoding="utf-8"))
    command_record["command_exit_code"] = 7
    command_raw = audit.canonical_json(command_record) + b"\n"
    command_path.write_bytes(command_raw)
    command_artifact["sha256"] = hashlib.sha256(command_raw).hexdigest()
    command_artifact["size"] = len(command_raw)
    _resign_manifest_receipt(round_row, 0, manifest_path, manifest)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_COMMAND_RECORD_INVALID")


def test_altered_gate_result_cannot_be_resigned_as_pass(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    round_row = value["rounds"][0]
    receipt = round_row["gate_receipts"][0]
    manifest_path, manifest = _read_receipt_manifest(receipt)
    result_artifact = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["evidence_type"].startswith("gate-result:")
    )
    assert _TEST_EVIDENCE_ROOT is not None
    result_path = _TEST_EVIDENCE_ROOT / result_artifact["path"]
    gate_result = json.loads(result_path.read_text(encoding="utf-8"))
    gate_result["status"] = "FAIL"
    result_raw = audit.canonical_json(gate_result) + b"\n"
    result_path.write_bytes(result_raw)
    result_artifact["sha256"] = hashlib.sha256(result_raw).hexdigest()
    result_artifact["size"] = len(result_raw)
    _resign_manifest_receipt(round_row, 0, manifest_path, manifest)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_GATE_RESULT_INVALID")


def test_copied_and_relabelled_artifact_cannot_satisfy_another_gate(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    round_row = value["rounds"][0]
    first_receipt = round_row["gate_receipts"][0]
    _first_path, first_manifest = _read_receipt_manifest(first_receipt)
    copied_artifact = first_manifest["artifacts"][-1]

    second_receipt = round_row["gate_receipts"][1]
    second_path, second_manifest = _read_receipt_manifest(second_receipt)
    target_artifact = second_manifest["artifacts"][-1]
    target_type = target_artifact["evidence_type"]
    target_artifact.clear()
    target_artifact.update(copy.deepcopy(copied_artifact))
    target_artifact["evidence_type"] = target_type
    _resign_manifest_receipt(round_row, 1, second_path, second_manifest)
    value = _rechain_and_seal(value, fingerprints)
    _assert_failure(value, contract, "QUALITY_AUDIT_EVIDENCE_ARTIFACTS_REUSED")


def test_symlinked_evidence_artifact_is_refused(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    value = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints)[:1],
    )
    receipt = value["rounds"][0]["gate_receipts"][0]
    _manifest_path, manifest = _read_receipt_manifest(receipt)
    assert _TEST_EVIDENCE_ROOT is not None
    artifact_path = _TEST_EVIDENCE_ROOT / manifest["artifacts"][0]["path"]
    preserved_path = _TEST_EVIDENCE_ROOT / "preserved-command-record.json"
    artifact_path.rename(preserved_path)
    artifact_path.symlink_to(preserved_path)
    _assert_failure(value, contract, "QUALITY_AUDIT_EVIDENCE_SYMLINK_REFUSED")


@pytest.mark.parametrize(
    "boundary",
    [
        "production",
        "contact_delivery_operational_test",
        "legal_review",
        "production_affiliate_destination_integrity_readback",
        "production_cache_cdn_invalidation_readback",
        "production_consent_runtime_readback",
        "production_content_roundtrip_readback",
        "production_migration_parity_readback",
        "production_observability_readback",
        "production_public_attack_surface_readback",
        "production_robots_indexability_readback",
        "production_seo_schema_readback",
        "production_taxonomy_term_identity",
    ],
)
def test_structurally_clean_ledger_stays_blocked_and_boundary_cannot_be_promoted(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str], boundary: str
) -> None:
    structurally_clean = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    result = audit.validate_document(
        structurally_clean,
        contract[0],
        contract[1],
        repository_root=ROOT,
        now=EVALUATED_AT + timedelta(seconds=901),
    )
    assert result.status == "BLOCKED"

    promoted = copy.deepcopy(structurally_clean)
    promoted["external_execution"][boundary] = "EXECUTED"
    promoted = audit.seal_ledger(promoted)
    _assert_failure(promoted, contract, "QUALITY_AUDIT_LEDGER_INVALID")


def test_attestation_execution_state_cannot_be_promoted_without_signed_inputs(
    contract: tuple[dict[str, object], str], fingerprints: dict[str, str]
) -> None:
    promoted = _ledger(
        contract_hash=contract[1],
        fingerprints=fingerprints,
        rounds=_two_clean_rounds(fingerprints),
    )
    promoted["external_execution"]["independent_reviewer_attestation_verification"] = (
        "EXECUTED"
    )
    promoted = audit.seal_ledger(promoted)
    _assert_failure(
        promoted,
        contract,
        "QUALITY_AUDIT_ATTESTATION_EXECUTION_STATE_INVALID",
    )
