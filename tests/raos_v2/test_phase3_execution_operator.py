from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator
import pytest

from scripts import build_raos_v2_successor as successor_builder
from scripts import raos_v2_phase3_execution as operator
from scripts import validate_raos_v2_successor as validator

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = Path(
    "changes/raos-v2/recorded-inputs/phase3/preaction-public-20260828-v1.json"
)


def _capture() -> dict[str, object]:
    value = json.loads((ROOT / CAPTURE).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _raw_export(*, captured_at: str) -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PHASE3_OWNER_EXPORT_RAW_V1",
        "version": "1.0.0",
        "captured_at": captured_at,
        "target": {
            "origin": validator.ORIGIN,
            "route": validator.PHASE3_PUBLIC_PATH,
            "kind": "EXISTING_POST",
            "post_id": 19,
            "exact_match_count": 1,
        },
        "fields": {
            "canonical_url": validator.PHASE3_PUBLIC_URL,
            "comment_status": "closed",
            "meta_description": "owner-held value never persisted by the operator",
            "ping_status": "closed",
            "post_content": "owner-held current post content",
            "post_excerpt": "owner-held current excerpt",
            "post_name": "carry-on-suitcase-comparison",
            "post_status": "publish",
            "post_title": "owner-held current title",
        },
        "restore_completeness": {name: True for name in sorted(operator.RESTORE_ITEMS)},
        "wordpress_environment": {
            "wordpress_core_version": "6.8.2",
            "active_theme": {"slug": "current-theme", "version": "1.2.3"},
            "relevant_plugins": [{"slug": "wordpress-seo", "version": "25.8"}],
        },
    }


def _external_inputs(
    tmp_path: Path, *, raw: dict[str, object]
) -> tuple[Path, dict[str, Path]]:
    owner_export = tmp_path / "owner-export.json"
    owner_export.write_text(
        json.dumps(raw, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    artifacts: dict[str, Path] = {}
    for index, name in enumerate(sorted(operator.ARTIFACT_ARGUMENTS), start=1):
        path = tmp_path / f"{name}.bin"
        path.write_bytes(f"owner-artifact-{index}".encode("ascii"))
        artifacts[name] = path
    return owner_export, artifacts


def _valid_document(tmp_path: Path) -> dict[str, object]:
    capture = _capture()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    raw = _raw_export(captured_at=str(observation["observed_at"]))
    owner_export, artifacts = _external_inputs(tmp_path, raw=raw)
    return operator.derive_preaction_execution_input(
        public_capture_path=CAPTURE,
        owner_export_path=owner_export,
        artifact_paths=artifacts,
        evaluated_at=datetime.fromisoformat(str(observation["observed_at"])),
    )


def test_preaction_operator_derives_content_free_tree_bound_input(
    tmp_path: Path,
) -> None:
    document = _valid_document(tmp_path)
    result = validator.verify_phase3_preaction_execution_input(document)
    assert result == {
        "status": "VERIFIED_PREACTION_INPUT",
        "preaction_binding_sha256": document["preaction_binding_sha256"],
        "post_id": 19,
        "raw_values_persisted": False,
    }
    assert document["capabilities"] == {
        "network": False,
        "wordpress_read": False,
        "wordpress_write": False,
        "publish": False,
    }
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True)
    for prohibited in (
        "owner-held current post content",
        "owner-held current excerpt",
        "owner-held current title",
        "owner-held value never persisted",
        str(tmp_path),
    ):
        assert prohibited not in serialized


def test_preaction_operator_hashes_all_restore_inputs(tmp_path: Path) -> None:
    document = _valid_document(tmp_path)
    owner = document["owner_export"]
    assert isinstance(owner, dict)
    artifacts = owner["artifacts"]
    assert isinstance(artifacts, dict)
    assert set(artifacts) == set(operator.ARTIFACT_ARGUMENTS)
    for evidence in artifacts.values():
        assert isinstance(evidence, dict)
        assert evidence["bytes"] > 0
        assert validator.HEX64.fullmatch(str(evidence["sha256"]))
    fields = owner["field_hashes"]
    assert isinstance(fields, dict)
    assert set(fields) == validator.PHASE3_WORDPRESS_FIELD_NAMES
    assert owner["legacy_post_content_sha256"] == validator.sha256(
        b"owner-held current post content"
    )
    binding = document["preaction_binding"]
    assert isinstance(binding, dict)
    assert binding["legacy_post_content_sha256"] == owner["legacy_post_content_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-field",
        "wrong-route",
        "missing-restore-field",
        "credential-like-extra-field",
        "unpublished-status",
    ],
)
def test_raw_owner_export_fails_closed(tmp_path: Path, mutation: str) -> None:
    capture = _capture()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    raw = _raw_export(captured_at=str(observation["observed_at"]))
    if mutation == "unknown-field":
        raw["fields"]["unknown"] = "x"  # type: ignore[index]
    elif mutation == "wrong-route":
        raw["target"]["route"] = "/other/"  # type: ignore[index]
    elif mutation == "missing-restore-field":
        raw["restore_completeness"].pop("author")  # type: ignore[union-attr]
    elif mutation == "credential-like-extra-field":
        raw["credential"] = "must-never-be-accepted"
    else:
        raw["fields"]["post_status"] = "draft"  # type: ignore[index]
    owner_export, artifacts = _external_inputs(tmp_path, raw=raw)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_OWNER_EXPORT_INVALID",
    ):
        operator.derive_preaction_execution_input(
            public_capture_path=CAPTURE,
            owner_export_path=owner_export,
            artifact_paths=artifacts,
        )


def test_preaction_pair_older_than_five_minutes_is_rejected(tmp_path: Path) -> None:
    capture = _capture()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    observed_at = datetime.fromisoformat(str(observation["observed_at"]))
    raw = _raw_export(captured_at=(observed_at + timedelta(seconds=301)).isoformat())
    owner_export, artifacts = _external_inputs(tmp_path, raw=raw)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_PREACTION_PAIR_STALE",
    ):
        operator.derive_preaction_execution_input(
            public_capture_path=CAPTURE,
            owner_export_path=owner_export,
            artifact_paths=artifacts,
            evaluated_at=observed_at + timedelta(seconds=301),
        )


@pytest.mark.parametrize("offset_seconds", [-1, 301])
def test_preaction_inputs_must_be_current_at_derivation(
    tmp_path: Path, offset_seconds: int
) -> None:
    capture = _capture()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    observed_at = datetime.fromisoformat(str(observation["observed_at"]))
    raw = _raw_export(captured_at=observed_at.isoformat())
    owner_export, artifacts = _external_inputs(tmp_path, raw=raw)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_PREACTION_INPUT_NOT_CURRENT",
    ):
        operator.derive_preaction_execution_input(
            public_capture_path=CAPTURE,
            owner_export_path=owner_export,
            artifact_paths=artifacts,
            evaluated_at=observed_at + timedelta(seconds=offset_seconds),
        )


@pytest.mark.parametrize(
    ("export_offset_seconds", "evaluation_offset_seconds"),
    [(300, 600), (-300, 300)],
)
def test_preaction_freshness_window_applies_to_both_inputs(
    tmp_path: Path,
    export_offset_seconds: int,
    evaluation_offset_seconds: int,
) -> None:
    capture = _capture()
    observation = capture["observation"]
    assert isinstance(observation, dict)
    observed_at = datetime.fromisoformat(str(observation["observed_at"]))
    raw = _raw_export(
        captured_at=(observed_at + timedelta(seconds=export_offset_seconds)).isoformat()
    )
    owner_export, artifacts = _external_inputs(tmp_path, raw=raw)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_PREACTION_INPUT_NOT_CURRENT",
    ):
        operator.derive_preaction_execution_input(
            public_capture_path=CAPTURE,
            owner_export_path=owner_export,
            artifact_paths=artifacts,
            evaluated_at=observed_at + timedelta(seconds=evaluation_offset_seconds),
        )


def test_preaction_validator_rejects_any_binding_or_capture_mutation(
    tmp_path: Path,
) -> None:
    document = _valid_document(tmp_path)
    for section, key, value in (
        ("public_capture", "body_sha256", "f" * 64),
        ("owner_export", "raw_export_bytes", 0),
        ("owner_export", "legacy_post_content_sha256", "f" * 64),
        ("preaction_binding", "current_public_body_sha256", "f" * 64),
        ("preaction_binding", "legacy_post_content_sha256", "f" * 64),
        ("pairing", "observed_delta_milliseconds", 300_001),
    ):
        mutated = deepcopy(document)
        target = mutated[section]
        assert isinstance(target, dict)
        target[key] = value
        with pytest.raises(
            validator.ValidationFailure,
            match="RAOS_V2_PHASE3_PREACTION_EXECUTION_INPUT_INVALID",
        ):
            validator.verify_phase3_preaction_execution_input(mutated)


def test_owner_export_and_artifacts_must_remain_outside_repository() -> None:
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_OWNER_EXPORT_UNREADABLE",
    ):
        operator.derive_preaction_execution_input(
            public_capture_path=CAPTURE,
            owner_export_path=ROOT / "package.json",
            artifact_paths={
                name: ROOT / "package.json" for name in operator.ARTIFACT_ARGUMENTS
            },
        )


def test_seal_output_preflight_leaves_no_partial_package_when_binding_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_root = tmp_path / "output-preflight-repository"
    recorded_root = isolated_root / validator.PHASE3_RECORDED_ROOT
    recorded_root.mkdir(parents=True)
    sealed_output = validator.PHASE3_RECORDED_ROOT / "sealed-package.json"
    cutover_output = validator.PHASE3_RECORDED_ROOT / "cutover-binding.json"
    (isolated_root / cutover_output).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(operator, "ROOT", isolated_root)
    monkeypatch.setattr(validator, "ROOT", isolated_root)

    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PHASE3_CAPTURE_OUTPUT_ALREADY_EXISTS",
    ):
        operator._preflight_seal_outputs(sealed_output, cutover_output)

    assert not (isolated_root / sealed_output).exists()


def test_repository_reader_rejects_symlinked_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_root = tmp_path / "symlinked-repository"
    outside = tmp_path / "outside"
    isolated_root.mkdir()
    outside.mkdir()
    (isolated_root / "changes").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(operator, "ROOT", isolated_root)

    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
    ):
        operator._repository_bytes(
            Path("changes/raos-v2/recorded-inputs/phase3/input.json"),
            maximum=1024,
            code="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
        )


def test_validator_reader_is_not_redirected_by_ancestor_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_root = tmp_path / "validator-reader-repository"
    original_directory = isolated_root / "contracts"
    outside_directory = tmp_path / "outside-contracts"
    original_directory.mkdir(parents=True)
    outside_directory.mkdir()
    (original_directory / "binding.json").write_bytes(b"trusted\n")
    (outside_directory / "binding.json").write_bytes(b"attacker\n")
    real_open = validator.os.open
    swapped = False

    def swapping_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "binding.json" and dir_fd is not None and not swapped:
            swapped = True
            original_directory.rename(isolated_root / "contracts-before-swap")
            original_directory.symlink_to(outside_directory, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(validator.os, "open", swapping_open)
    assert (
        validator._repository_regular_file_bytes(
            Path("contracts/binding.json"),
            root=isolated_root,
            maximum=128,
            code="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
        )
        == b"trusted\n"
    )
    assert swapped is True


def test_validator_reader_rejects_symlinked_file(tmp_path: Path) -> None:
    isolated_root = tmp_path / "validator-symlinked-file-repository"
    outside = tmp_path / "outside-binding.json"
    (isolated_root / "contracts").mkdir(parents=True)
    outside.write_bytes(b"attacker\n")
    (isolated_root / "contracts/binding.json").symlink_to(outside)

    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
    ):
        validator._repository_regular_file_bytes(
            Path("contracts/binding.json"),
            root=isolated_root,
            maximum=128,
            code="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
        )


def test_validator_reader_rejects_hard_linked_file(tmp_path: Path) -> None:
    isolated_root = tmp_path / "validator-hard-link-repository"
    outside = tmp_path / "owner-held-binding.json"
    (isolated_root / "contracts").mkdir(parents=True)
    outside.write_bytes(b"owner-held\n")
    validator.os.link(outside, isolated_root / "contracts/binding.json")

    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
    ):
        validator._repository_regular_file_bytes(
            Path("contracts/binding.json"),
            root=isolated_root,
            maximum=128,
            code="RAOS_V2_PHASE3_TEST_REPOSITORY_READ_REJECTED",
        )


def _reissue_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], datetime, Path]:
    preaction = _valid_document(tmp_path)
    binding = preaction["preaction_binding"]
    assert isinstance(binding, dict)
    captured_at = datetime.fromisoformat(str(binding["captured_at"]))
    isolated_root = tmp_path / "isolated-repository"
    input_path = validator.PHASE3_RECORDED_ROOT / "verified-preaction-input.json"
    (isolated_root / input_path).parent.mkdir(parents=True)
    (isolated_root / input_path).write_text(
        json.dumps(preaction, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    isolated_capture = isolated_root / CAPTURE
    isolated_capture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / CAPTURE, isolated_capture)
    historical_target = isolated_root / operator.HISTORICAL_REVIEW_CANDIDATE_PATH
    historical_target.parent.mkdir(parents=True)
    shutil.copyfile(
        ROOT / operator.HISTORICAL_REVIEW_CANDIDATE_PATH,
        historical_target,
    )
    shutil.copytree(
        ROOT / "contracts/raos-v2",
        isolated_root / "contracts/raos-v2",
    )
    monkeypatch.setattr(operator, "ROOT", isolated_root)
    monkeypatch.setattr(validator, "ROOT", isolated_root)
    result = operator.reissue_review_candidate(
        preaction_input_path=input_path,
        evaluated_at=captured_at,
    )
    return result, captured_at, isolated_root


def test_verified_preaction_reissues_exact_artifact_specific_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _captured_at, isolated_root = _reissue_fixture(tmp_path, monkeypatch)
    assert result["state"] == "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"
    assert result["external_actions"] == "NOT_EXECUTED"
    assert result["capabilities"] == {
        "network": False,
        "wordpress_read": False,
        "wordpress_write": False,
        "publish": False,
    }
    review = result["review_request"]
    candidate = result["review_candidate"]
    assert isinstance(review, dict) and isinstance(candidate, dict)
    assert review["generic_approval_accepted"] is False
    assert review["artifact_specific_review_required"] is True
    assert candidate["preaction_status"] == "VERIFIED_PREACTION"
    assert (
        candidate["preaction_binding_digest"]
        == result["source"]["preaction_binding_sha256"]  # type: ignore[index]
    )
    digest = result["review_bundle_sha256"]
    unsigned = deepcopy(result)
    unsigned.pop("review_bundle_sha256")
    assert digest == validator._semantic_digest(unsigned)
    assert (
        validator.verify_phase3_reissued_review_bundle(result, root=isolated_root)[
            "state"
        ]
        == "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW"
    )
    mutated = deepcopy(result)
    mutated_review = mutated["review_request"]
    assert isinstance(mutated_review, dict)
    mutated_review["generic_approval_accepted"] = True
    mutated.pop("review_bundle_sha256")
    mutated["review_bundle_sha256"] = validator._semantic_digest(mutated)
    with pytest.raises(
        validator.ValidationFailure,
        match="RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_INVALID",
    ):
        validator.verify_phase3_reissued_review_bundle(mutated, root=isolated_root)


def test_reissue_rejects_preaction_older_than_five_minutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, captured_at, _isolated_root = _reissue_fixture(tmp_path, monkeypatch)
    source = result["source"]
    assert isinstance(source, dict)
    input_path = Path(str(source["preaction_input"]))
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_REISSUE_INPUT_NOT_CURRENT",
    ):
        operator.reissue_review_candidate(
            preaction_input_path=input_path,
            evaluated_at=captured_at + timedelta(seconds=301),
        )


def test_owner_assertion_creates_only_a_simulation_sealed_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, reissued_at, isolated_root = _reissue_fixture(tmp_path, monkeypatch)
    bundle_path = validator.PHASE3_RECORDED_ROOT / "reissued-review-bundle.json"
    (isolated_root / bundle_path).write_bytes(validator.canonical_json_bytes(bundle))
    receipt_path = tmp_path / "artifact-specific-human-review-receipt.json"
    receipt_document = {
        "schema": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1",
        "version": "1.0.0",
        "reviewer_id": "OWNER_ASSERTION_LOCAL",
        "reviewed_at": reissued_at.isoformat(),
        "review_version": "P3-OWNER-ASSERTION-V1",
        "correction_count": 0,
        "accepted": True,
        "synthetic": False,
        "candidate_digest": bundle["candidate_digest"],
        "payload_digest": bundle["payload_digest"],
        "target_route": validator.PHASE3_PUBLIC_PATH,
        "assertion_status": "UNAUTHENTICATED_OWNER_ASSERTION",
        "acceptance_authority": False,
    }
    receipt_schema = successor_builder.phase3_human_review_receipt_schema()
    Draft202012Validator.check_schema(receipt_schema)
    assert (
        list(Draft202012Validator(receipt_schema).iter_errors(receipt_document)) == []
    )
    personal_receipt = receipt_document | {"reviewer_id": "PERSON-NAME"}
    assert list(Draft202012Validator(receipt_schema).iter_errors(personal_receipt))
    personal_receipt_path = tmp_path / "person-identifying-review-receipt.json"
    personal_receipt_path.write_bytes(validator.canonical_json_bytes(personal_receipt))
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID",
    ):
        operator.seal_reissued_review_candidate(
            review_bundle_path=bundle_path,
            human_review_receipt_path=personal_receipt_path,
            evaluated_at=reissued_at,
        )
    receipt_path.write_bytes(validator.canonical_json_bytes(receipt_document))

    sealed = operator.seal_reissued_review_candidate(
        review_bundle_path=bundle_path,
        human_review_receipt_path=receipt_path,
        evaluated_at=reissued_at,
    )

    assert sealed["state"] == "PACKAGE_SEALED"
    assert sealed["capabilities"] == {
        "network": False,
        "wordpress_write": False,
        "publish": False,
    }
    assert sealed["simulation_only"] is True
    assert sealed["approval_acceptance_authority"] is False
    review = sealed["human_review_receipt"]
    assert isinstance(review, dict)
    assert review["assertion_status"] == "UNAUTHENTICATED_OWNER_ASSERTION"
    assert review["acceptance_authority"] is False
    assert validator.HEX64.fullmatch(str(sealed["package_digest"]))
    verification = operator.verify_phase3_sealed_package_semantics(
        sealed,
        review_bundle=bundle,
        evaluated_at=reissued_at,
        root=isolated_root,
    )
    assert verification == {
        "state": "PACKAGE_SEALED",
        "simulation_only": True,
        "assertion_status": "UNAUTHENTICATED_OWNER_ASSERTION",
        "acceptance_authority": False,
        "phase_exit": "BLOCKED_EXTERNAL",
        "public_write_authority": False,
    }
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED",
    ):
        operator.build_wordpress_cutover_binding(
            sealed,
            review_bundle=bundle,
        )
    sealed_cli_output = validator.PHASE3_RECORDED_ROOT / "sealed-simulation-cli.json"
    assert (
        operator.main(
            [
                "seal-candidate",
                "--review-bundle",
                bundle_path.as_posix(),
                "--human-review-receipt",
                receipt_path.as_posix(),
                "--output",
                sealed_cli_output.as_posix(),
            ]
        )
        == 0
    )
    cli_sealed = json.loads(
        (isolated_root / sealed_cli_output).read_text(encoding="utf-8")
    )
    assert cli_sealed["simulation_only"] is True
    assert cli_sealed["approval_acceptance_authority"] is False
    capsys.readouterr()
    sealed_cli_target = isolated_root / sealed_cli_output
    interrupted_temporary = sealed_cli_target.parent / (
        f".{sealed_cli_target.name}.{'0' * 24}.next"
    )
    operator.os.link(sealed_cli_target, interrupted_temporary)
    assert sealed_cli_target.stat().st_nlink == 2
    assert (
        operator.main(
            [
                "seal-candidate",
                "--review-bundle",
                bundle_path.as_posix(),
                "--human-review-receipt",
                receipt_path.as_posix(),
                "--output",
                sealed_cli_output.as_posix(),
            ]
        )
        == 0
    )
    assert sealed_cli_target.stat().st_nlink == 1
    assert not interrupted_temporary.exists()
    capsys.readouterr()
    tampered_package = deepcopy(sealed)
    tampered_candidate = tampered_package["review_candidate"]
    assert isinstance(tampered_candidate, dict)
    tampered_update = tampered_candidate["update_payload"]
    assert isinstance(tampered_update, dict)
    tampered_preaction = tampered_update["preaction"]
    assert isinstance(tampered_preaction, dict)
    tampered_binding = tampered_preaction["binding"]
    assert isinstance(tampered_binding, dict)
    tampered_binding["legacy_post_content_sha256"] = "f" * 64
    tampered_preaction["binding_digest"] = validator._semantic_digest(tampered_binding)
    tampered_candidate["preaction_binding_digest"] = tampered_preaction[
        "binding_digest"
    ]
    tampered_candidate["payload_digest"] = validator._semantic_digest(tampered_update)
    tampered_review = tampered_package["human_review_receipt"]
    assert isinstance(tampered_review, dict)
    tampered_review["payload_digest"] = tampered_candidate["payload_digest"]
    tampered_package.pop("package_digest")
    tampered_package["package_digest"] = validator._semantic_digest(tampered_package)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID",
    ):
        operator.verify_phase3_sealed_package_semantics(
            tampered_package,
            review_bundle=bundle,
            root=isolated_root,
        )
    sealed_claims = tampered_candidate["claim_bindings"]
    assert isinstance(sealed_claims, list)
    first_sealed_claim = sealed_claims[0]
    assert isinstance(first_sealed_claim, dict)
    stale_at = datetime.fromisoformat(
        str(first_sealed_claim["next_review_at"])
    ) + timedelta(seconds=1)
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID",
    ):
        operator.verify_phase3_sealed_package_semantics(
            sealed,
            review_bundle=bundle,
            evaluated_at=stale_at,
            root=isolated_root,
        )
    pre_preaction_package = deepcopy(sealed)
    pre_preaction_candidate = pre_preaction_package["review_candidate"]
    assert isinstance(pre_preaction_candidate, dict)
    pre_preaction_update = pre_preaction_candidate["update_payload"]
    assert isinstance(pre_preaction_update, dict)
    pre_preaction = pre_preaction_update["preaction"]
    assert isinstance(pre_preaction, dict)
    pre_preaction.update(
        {
            "status": "HISTORICAL_BASELINE_ONLY",
            "binding_digest": None,
            "binding": None,
        }
    )
    pre_preaction_candidate["preaction_status"] = "HISTORICAL_BASELINE_ONLY"
    pre_preaction_candidate["preaction_binding_digest"] = None
    pre_preaction_candidate["payload_digest"] = validator._semantic_digest(
        pre_preaction_update
    )
    pre_preaction_review = pre_preaction_package["human_review_receipt"]
    assert isinstance(pre_preaction_review, dict)
    pre_preaction_review["payload_digest"] = pre_preaction_candidate["payload_digest"]
    pre_preaction_package.pop("package_digest")
    pre_preaction_package["package_digest"] = validator._semantic_digest(
        pre_preaction_package
    )
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID",
    ):
        operator.build_wordpress_cutover_binding(
            pre_preaction_package,
            review_bundle=bundle,
        )
    structured_drift_package = deepcopy(sealed)
    structured_drift_package["structured_data_expectation_sha256"] = "f" * 64
    structured_drift_package.pop("package_digest")
    structured_drift_package["package_digest"] = validator._semantic_digest(
        structured_drift_package
    )
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID",
    ):
        operator.build_wordpress_cutover_binding(
            structured_drift_package,
            review_bundle=bundle,
        )
    forged_path = validator.PHASE3_RECORDED_ROOT / "forged-sealed-package.json"
    (isolated_root / forged_path).write_bytes(
        validator.canonical_json_bytes(structured_drift_package)
    )
    cutover_output = validator.PHASE3_RECORDED_ROOT / "must-not-be-armed.json"
    assert (
        operator.main(
            [
                "derive-cutover-binding",
                "--sealed-package",
                forged_path.as_posix(),
                "--review-bundle",
                bundle_path.as_posix(),
                "--output",
                cutover_output.as_posix(),
            ]
        )
        == 1
    )
    assert "RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID" in capsys.readouterr().err
    assert not (isolated_root / cutover_output).exists()
    invalid_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    invalid_receipt["schema"] = "RAOS_V2_PHASE3_UNTRUSTED_RECEIPT"
    receipt_path.write_bytes(validator.canonical_json_bytes(invalid_receipt))
    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID",
    ):
        operator.seal_reissued_review_candidate(
            review_bundle_path=bundle_path,
            human_review_receipt_path=receipt_path,
            evaluated_at=reissued_at,
        )


def test_reissue_rejects_contract_valid_generated_candidate_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preaction = _valid_document(tmp_path)
    binding = preaction["preaction_binding"]
    assert isinstance(binding, dict)
    captured_at = datetime.fromisoformat(str(binding["captured_at"]))
    isolated_root = tmp_path / "drifted-repository"
    input_path = validator.PHASE3_RECORDED_ROOT / "verified-preaction-input.json"
    (isolated_root / input_path).parent.mkdir(parents=True)
    (isolated_root / input_path).write_text(
        json.dumps(preaction, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    isolated_capture = isolated_root / CAPTURE
    isolated_capture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / CAPTURE, isolated_capture)
    historical = json.loads(
        (ROOT / operator.HISTORICAL_REVIEW_CANDIDATE_PATH).read_text(encoding="utf-8")
    )
    update = historical["update_payload"]
    assert isinstance(update, dict)
    fields = update["fields"]
    assert isinstance(fields, dict)
    fields["post_title"] = "契約上は有効でもgeneratorが所有しない改変タイトル"
    historical_target = isolated_root / operator.HISTORICAL_REVIEW_CANDIDATE_PATH
    historical_target.parent.mkdir(parents=True)
    historical_target.write_bytes(validator.canonical_json_bytes(historical))
    monkeypatch.setattr(operator, "ROOT", isolated_root)

    with pytest.raises(
        operator.Phase3ExecutionFailure,
        match="RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_DRIFT",
    ):
        operator.reissue_review_candidate(
            preaction_input_path=input_path,
            evaluated_at=captured_at,
        )
