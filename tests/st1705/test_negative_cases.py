from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import build_st1705_pilot_signoff as builder


@pytest.mark.parametrize(
    ("section", "key", "invalid"),
    (
        ("document", "acceptance_criteria_satisfied", True),
        ("formal_evidence_port", "activation", "ENABLED"),
        ("formal_evidence_port", "current_input_uri", "repo://fake.json"),
        ("formal_evidence_port", "default_decision", "PASS"),
        ("article_artifact_boundary", "local_artifacts_are_pilot_observations", True),
        ("decision", "overall", "PASS"),
        ("decision", "security_sign_off", "SIGNED_OFF"),
        ("decision", "pilot_eligibility", "ELIGIBLE"),
        ("authority_boundary", "publication_authority", "GRANTED"),
        ("authority_boundary", "production_authority", "GRANTED"),
        ("execution_boundary", "external_action_count", 1),
        ("evidence_boundary", "source_freeze_status", "PRESENT"),
        ("evidence_boundary", "validated_claim", True),
        ("evidence_boundary", "story_acceptance", True),
        ("evidence_boundary", "release_eligible", True),
    ),
)
def test_eligibility_or_authority_escalation_is_rejected(
    section: str,
    key: str,
    invalid: object,
    contract: dict[str, object],
) -> None:
    value = contract[section]
    assert isinstance(value, dict)
    value[key] = invalid
    with pytest.raises(builder.PilotSignoffError):
        builder.validate_contract(contract)


def test_unknown_missing_duplicate_and_alias_contract_shapes_are_rejected(
    contract: dict[str, object], repository_copy: Path
) -> None:
    unknown = copy.deepcopy(contract)
    unknown["unknown"] = None
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.validate_contract(unknown)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    missing = copy.deepcopy(contract)
    del missing["decision"]
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.validate_contract(missing)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    contract_path = repository_copy / builder.CONTRACT_PATH
    original = contract_path.read_text()
    contract_path.write_text(original + "document: {}\n")
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.load_contract(repository_copy)
    assert error.value.code == "YAML_INVALID"
    contract_path.write_text("a: &anchor {}\nb: *anchor\n")
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.load_contract(repository_copy)
    assert error.value.code == "YAML_ALIAS_FORBIDDEN"


def test_canonical_hash_is_protected_and_tracked_inputs_are_semantic(
    repository_copy: Path,
) -> None:
    canonical = repository_copy / next(iter(builder.EXPECTED_SOURCE_HASHES))
    canonical.chmod(0o600)
    original = canonical.read_bytes()
    canonical.write_bytes(original + b"\n")
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.load_contract(repository_copy)
    assert error.value.code == "SOURCE_HASH_DRIFT"
    canonical.write_bytes(original)

    for relative in (
        next(iter(builder.EXPECTED_DEPENDENCY_HASHES)),
        builder.FORMAL_SCHEMA_PATH.as_posix(),
    ):
        target = repository_copy / relative
        target.write_bytes(target.read_bytes() + b"\n")
    assert builder.load_contract(repository_copy)


def test_duplicate_key_in_json_dependency_is_rejected_even_after_hash_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path(
        "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json"
    )
    target = repository_copy / relative
    target.write_text('{"classification":"x","classification":"y"}\n')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    hashes = dict(builder.EXPECTED_DEPENDENCY_HASHES)
    hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_DEPENDENCY_HASHES", hashes)
    raw = builder._load_yaml(repository_copy, builder.CONTRACT_PATH, "contract")  # noqa: SLF001
    raw["dependency_bindings"]["st_1607"]["artifacts"][0]["sha256"] = digest
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "JSON_DUPLICATE_KEY"


def test_fake_gate_eligibility_is_rejected_after_dependency_hash_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path(
        "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json"
    )
    target = repository_copy / relative
    data = json.loads(target.read_text())
    data["gate_report"]["gates"][0]["status"] = "PASS"
    data["evidence_boundary"]["gate_pass_claim"] = True
    target.write_text(json.dumps(data, indent=2) + "\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    hashes = dict(builder.EXPECTED_DEPENDENCY_HASHES)
    hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_DEPENDENCY_HASHES", hashes)
    raw = builder._load_yaml(repository_copy, builder.CONTRACT_PATH, "contract")  # noqa: SLF001
    raw["dependency_bindings"]["st_1607"]["artifacts"][0]["sha256"] = digest
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "ST1607_SEMANTIC_DRIFT"


def test_fake_publication_snapshot_is_rejected_after_dependency_hash_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json"
    )
    target = repository_copy / relative
    data = json.loads(target.read_text())
    data["articles"][0]["immutable_snapshot_sha256"] = "0" * 64
    data["articles"][0]["public_verification"] = "PASS"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    hashes = dict(builder.EXPECTED_DEPENDENCY_HASHES)
    hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_DEPENDENCY_HASHES", hashes)
    raw = builder._load_yaml(repository_copy, builder.CONTRACT_PATH, "contract")  # noqa: SLF001
    raw["dependency_bindings"]["st_1704_self_hosted"]["artifacts"][3]["sha256"] = digest
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "ST1704_ARTIFACT_SEMANTIC_DRIFT"


def test_symlink_hardlink_oversize_and_path_tricks_are_rejected(
    repository_copy: Path, tmp_path: Path
) -> None:
    relative = Path(next(iter(builder.EXPECTED_SOURCE_HASHES)))
    target = repository_copy / relative
    original = target.read_bytes()

    target.unlink()
    target.symlink_to(tmp_path / "outside")
    with pytest.raises(builder.PilotSignoffError) as error:
        builder._read(repository_copy, relative, "input")  # noqa: SLF001
    assert error.value.code == "UNSAFE_FILE_TYPE"

    target.unlink()
    target.write_bytes(original)
    linked = repository_copy / "hardlink"
    os.link(target, linked)
    with pytest.raises(builder.PilotSignoffError) as error:
        builder._read(repository_copy, relative, "input")  # noqa: SLF001
    assert error.value.code == "UNSAFE_FILE_LINK_COUNT"
    linked.unlink()

    target.write_bytes(b"x" * (builder.MAX_INPUT_BYTES + 1))
    with pytest.raises(builder.PilotSignoffError) as error:
        builder._read(repository_copy, relative, "input")  # noqa: SLF001
    assert error.value.code == "INPUT_SIZE_LIMIT"

    for unsafe in (Path("../outside"), Path("/absolute"), Path("a/./../b")):
        with pytest.raises(builder.PilotSignoffError) as error:
            builder._read(repository_copy, unsafe, "input")  # noqa: SLF001
        assert error.value.code == "UNSAFE_REPOSITORY_PATH"


def test_ancestor_swap_cannot_escape_captured_repository_root(
    repository_copy: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("authority/source.yaml")
    authority = repository_copy / relative.parent
    authority.mkdir()
    (authority / relative.name).write_text("inside\n")
    parked = repository_copy / "authority.parked"
    outside = tmp_path_factory.mktemp("st1705-outside")
    (outside / relative.name).write_text("outside\n")

    def replace_ancestor(_root_fd: int, observed: Path) -> None:
        assert observed == relative
        authority.rename(parked)
        authority.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(builder, "_input_path_walk_checkpoint", replace_ancestor)
    with pytest.raises(builder.PilotSignoffError) as error:
        builder._read(repository_copy, relative, "input")  # noqa: SLF001
    assert error.value.code == "UNSAFE_ANCESTOR"


@pytest.mark.parametrize("relative", builder.GENERATED_PATHS)
def test_unsafe_output_symlink_preserves_both_outputs(
    relative: Path, repository_copy: Path
) -> None:
    builder.build(repository_copy)
    target = repository_copy / relative
    target.unlink()
    target.symlink_to(repository_copy / builder.CONTRACT_PATH)
    before = {
        path: (
            os.readlink(repository_copy / path)
            if (repository_copy / path).is_symlink()
            else (repository_copy / path).read_bytes()
        )
        for path in builder.GENERATED_PATHS
    }
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.build(repository_copy)
    assert error.value.code == "UNSAFE_OUTPUT_TARGET"
    after = {
        path: (
            os.readlink(repository_copy / path)
            if (repository_copy / path).is_symlink()
            else (repository_copy / path).read_bytes()
        )
        for path in builder.GENERATED_PATHS
    }
    assert after == before


def test_tampered_transaction_is_retained_and_fails_closed(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Crash(BaseException):
        pass

    def crash(name: str) -> None:
        if name == "PREPARED":
            raise Crash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash)
    with pytest.raises(Crash):
        builder.build(repository_copy)
    journal = repository_copy / builder.MANIFEST_PATH.parent / builder.TRANSACTION_NAME
    journal.write_text('{"schema":"wrong"}\n')
    journal.chmod(0o600)
    before = journal.read_bytes()
    with pytest.raises(builder.PilotSignoffError) as error:
        builder.build(repository_copy)
    assert error.value.code == "TRANSACTION_INVALID"
    assert journal.read_bytes() == before


def test_mismatched_committed_next_transaction_is_rejected(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Crash(BaseException):
        pass

    def crash(name: str) -> None:
        if name == "PREPARED":
            raise Crash

    monkeypatch.setattr(builder, "_transaction_checkpoint", crash)
    with pytest.raises(Crash):
        builder.build(repository_copy)
    parent = repository_copy / builder.MANIFEST_PATH.parent
    journal = parent / builder.TRANSACTION_NAME
    committed = json.loads(journal.read_text())
    committed["state"] = "COMMITTED"
    committed["outputs"][0]["next_sha256"] = "0" * 64
    next_journal = parent / builder.TRANSACTION_NEXT_NAME
    next_journal.write_text(json.dumps(committed, separators=(",", ":")) + "\n")
    next_journal.chmod(0o600)

    with pytest.raises(builder.PilotSignoffError) as error:
        builder.build(repository_copy)
    assert error.value.code == "TRANSACTION_INVALID"
    assert journal.exists()
    assert next_journal.exists()


def test_generator_has_no_external_or_dynamic_evidence_surface() -> None:
    source = (builder.REPO_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    forbidden_imports = {
        "boto3",
        "botocore",
        "httpx",
        "importlib",
        "requests",
        "socket",
        "sqlalchemy",
        "psycopg",
        "urllib",
    }
    observed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            observed.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            observed.add(node.module.split(".")[0])
    assert observed.isdisjoint(forbidden_imports)
    for token in (
        "os.environ",
        "getenv(",
        "subprocess.run",
        "requests.",
        "status_apply(",
        "publish(",
        "deploy(",
    ):
        assert token not in source
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"compile", "eval", "exec", "__import__"}
        for node in ast.walk(tree)
    )


def test_cli_accepts_only_build_or_check() -> None:
    assert builder.parse_args([]).check is False
    assert builder.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit) as error:
        builder.parse_args(["--evidence", "fake.json"])
    assert error.value.code == 2


@pytest.mark.parametrize("flags", ((), ("-I",), ("-B",)))
def test_cli_does_not_require_special_interpreter_flags(flags: tuple[str, ...]) -> None:
    result = subprocess.run(
        [
            sys.executable,
            *flags,
            str(builder.REPO_ROOT / builder.GENERATOR_PATH),
            "--check",
        ],
        cwd=builder.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_formal_schema_rejects_unknown_top_level_property_shape() -> None:
    schema = json.loads((builder.REPO_ROOT / builder.FORMAL_SCHEMA_PATH).read_text())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["target"]["additionalProperties"] is False
    assert schema["properties"]["backup_restore"]["additionalProperties"] is False
    assert schema["$defs"]["suite_row"]["additionalProperties"] is False
    assert schema["$defs"]["approval"]["additionalProperties"] is False
