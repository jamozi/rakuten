"""Closed CLI, transport, domain, and credential-boundary checks."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import pickle
import ssl
import subprocess
import sys
import tempfile
import types
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from raos.adapters import self_hosted_wordpress_operator_credentials as credentials  # noqa: E402
from raos.adapters import self_hosted_wordpress_operator_https as https  # noqa: E402
from raos.domain.operations import self_hosted_wordpress_operator as domain  # noqa: E402
from scripts import st1506_wordpress_operator as cli  # noqa: E402


@pytest.fixture
def private_repository() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="raos-st1506-", dir="/tmp") as location:
        repository = Path(location) / "repository"
        private = repository / ".secrets/wordpress-operator-local"
        private.mkdir(parents=True)
        (repository / ".secrets").chmod(0o700)
        private.chmod(0o700)
        yield repository


def _write_fsynced_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    try:
        assert os.write(descriptor, payload) == len(payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def test_domain_has_only_two_mutations_and_exact_fixed_versions() -> None:
    assert list(domain.WordPressOperatorOperation) == [
        domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        domain.WordPressOperatorOperation.UPDATE_CHILD_THEME,
    ]
    assert domain.WORDPRESS_OPERATOR_ORIGIN == "https://kurashinoshirube.com"
    assert domain.WORDPRESS_OPERATOR_NAMESPACE == "/wp-json/raos-operator/v1"
    assert domain.WORDPRESS_OPERATOR_CONTRACT_VERSION == 1
    assert domain.WORDPRESS_OPERATOR_PROFILE_VERSION == 1
    assert domain.WORDPRESS_OPERATOR_THEME_FROM_VERSION == "1.1.1"
    assert domain.WORDPRESS_OPERATOR_YOAST_VERSION == "28.3"


@pytest.mark.parametrize(
    "code",
    (
        "YOAST_CHECKSUM_CACHE_WRITE_FAILED",
        "YOAST_CHECKSUM_LOCK_LOST",
        "YOAST_CHECKSUM_LOCK_RELEASE_UNCERTAIN",
        "YOAST_CHECKSUM_LOCK_UNAVAILABLE",
    ),
)
def test_checksum_mutex_failures_are_closed_unavailable_results(code: str) -> None:
    result = domain.YoastChecksumResult(
        status=domain.WordPressOperatorChecksumStatus.UNAVAILABLE,
        code=code,
        checked_file_count=0,
        mismatch_count=0,
    )
    assert result.public_payload()["code"] == code


def test_yoast_proposal_bytes_bind_every_fixed_semantic_input() -> None:
    request_token = "1" * 64
    proposal = domain.OperatorProposal.yoast(request_token)
    assert proposal.payload() == {
        "operator_contract_version": 1,
        "operation": "APPLY_YOAST_PROFILE",
        "profile_version": 1,
        "request_token": request_token,
        "site_origin": "https://kurashinoshirube.com",
        "ttl_seconds": 900,
        **domain.fixed_yoast_profile(),
    }
    expected = domain.canonical_json_bytes(proposal.payload())
    assert proposal.canonical_bytes() == expected
    assert proposal.proposal_id == hashlib.sha256(expected).hexdigest()
    assert b" " not in expected and b"\n" not in expected
    assert expected.startswith(b'{"operation":"APPLY_YOAST_PROFILE",')


def test_python_canonicalization_matches_the_committed_php_golden_vector() -> None:
    vector = json.loads(
        (
            ROOT / "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/contracts/"
            "canonical-proposal-golden.v1.json"
        ).read_bytes()
    )
    proposal = domain.OperatorProposal.yoast(vector["request_token"])
    assert proposal.canonical_bytes() == vector["canonical_ascii_json"].encode("ascii")
    assert len(proposal.canonical_bytes()) == vector["canonical_byte_length"] == 870
    assert proposal.proposal_id == vector["proposal_id"]


def _theme(*, from_version: str, to_version: str) -> domain.ThemePackage:
    payload = b"bounded-theme-package"
    entry = domain.ThemeFileManifestEntry(
        path="style.css",
        size=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )
    return domain.ThemePackage.bind(
        from_version=from_version,
        to_version=to_version,
        package_bytes=payload,
        file_manifest=(entry,),
    )


def test_theme_proposal_is_ascii_bounded_sorted_and_upgrade_only() -> None:
    theme = _theme(from_version="1.1.1", to_version="1.1.2")
    proposal = domain.OperatorProposal.theme_update(theme, "2" * 64)
    assert proposal.payload()["theme"] == theme.proposal_payload()
    assert (
        proposal.proposal_id == hashlib.sha256(proposal.canonical_bytes()).hexdigest()
    )
    assert domain.MAX_THEME_PACKAGE_BYTES == 16 * 1024 * 1024
    assert domain.MAX_THEME_FILE_BYTES == 4 * 1024 * 1024
    assert domain.MAX_THEME_FILES == 64

    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        _theme(from_version="1.1.1", to_version="1.1.1")
    assert (
        captured.value.code
        is domain.WordPressOperatorFailureCode.THEME_VERSION_NOT_NEWER
    )
    with pytest.raises(domain.WordPressOperatorFailure):
        domain.ThemeFileManifestEntry(
            path="画像.webp",
            size=1,
            sha256="0" * 64,
        )
    with pytest.raises(domain.WordPressOperatorFailure):
        domain.ThemePackage.bind(
            from_version="1.1.1",
            to_version="1.1.2",
            package_bytes=b"x",
            file_manifest=(
                domain.ThemeFileManifestEntry(
                    path="A.txt", size=1, sha256=hashlib.sha256(b"x").hexdigest()
                ),
                domain.ThemeFileManifestEntry(
                    path="a.txt", size=1, sha256=hashlib.sha256(b"x").hexdigest()
                ),
            ),
        )


def test_create_receipts_have_exact_initial_replay_state_and_ttl_rules() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created = now - timedelta(seconds=100)
    expires = created + timedelta(seconds=900)

    def stamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    fresh = domain.ProposalReceipt(
        proposal_id="4" * 64,
        operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        state=domain.WordPressOperatorProposalState.PROPOSED,
        created_at=stamp(created),
        expires_at=stamp(expires),
        replayed=False,
    )
    assert not fresh.is_expired(now)
    replay = domain.ProposalReceipt(
        proposal_id="5" * 64,
        operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        state=domain.WordPressOperatorProposalState.APPROVED,
        created_at=stamp(now - timedelta(seconds=1000)),
        expires_at=stamp(now - timedelta(seconds=100)),
        replayed=True,
    )
    assert replay.is_expired(now)
    terminal = domain.ProposalReceipt(
        proposal_id="a" * 64,
        operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        state=domain.WordPressOperatorProposalState.APPLIED,
        created_at=stamp(created),
        expires_at=stamp(expires),
        replayed=True,
    )
    assert terminal.requires_new_proposal(now)
    with pytest.raises(domain.WordPressOperatorFailure):
        domain.ProposalReceipt(
            proposal_id="b" * 64,
            operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            state=domain.WordPressOperatorProposalState.FAILED,
            created_at=stamp(created),
            expires_at=stamp(expires),
            replayed=False,
        )
    with pytest.raises(domain.WordPressOperatorFailure):
        domain.ProposalReceipt(
            proposal_id="6" * 64,
            operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            state=domain.WordPressOperatorProposalState.APPROVED,
            created_at=stamp(created),
            expires_at=stamp(expires),
            replayed=False,
        )
    with pytest.raises(domain.WordPressOperatorFailure):
        domain.ProposalReceipt(
            proposal_id="7" * 64,
            operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            state=domain.WordPressOperatorProposalState.PROPOSED,
            created_at=stamp(created),
            expires_at=stamp(expires + timedelta(seconds=1)),
            replayed=True,
        )


def test_owner_private_intent_survives_response_loss_and_reuses_exact_id(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = private_repository
    private = repository / ".secrets/wordpress-operator-local"
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", repository)
    observed: list[domain.OperatorProposal] = []

    class LostResponse:
        def propose(self, proposal: domain.OperatorProposal) -> object:
            observed.append(proposal)
            raise domain.WordPressOperatorFailure(
                domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
            )

    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        cli._proposal_from_intent(
            adapter=LostResponse(),  # type: ignore[arg-type]
            operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        )
    assert captured.value.code is domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
    first = observed[0]
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(repository)
    with journal.exclusive(first.operation):
        pending = journal.load(first.operation)
    assert pending is not None
    assert pending.proposal_id == first.proposal_id
    assert pending.request_token == first.request_token
    assert pending.canonical_request_sha256 == first.proposal_id
    intent_path = private / "proposal-intents" / "apply-yoast-profile.intent.v1.json"
    intent_payload = json.loads(intent_path.read_bytes())
    assert intent_payload == {
        "canonical_request_sha256": first.proposal_id,
        "operation": "APPLY_YOAST_PROFILE",
        "proposal_id": first.proposal_id,
        "request_token": first.request_token,
        "schema": "RAOS_WORDPRESS_OPERATOR_PROPOSAL_INTENT_V1",
    }
    assert intent_path.stat().st_mode & 0o777 == 0o600
    assert intent_path.stat().st_nlink == 1

    now = datetime.now(timezone.utc).replace(microsecond=0)

    class RecoveredResponse:
        def propose(self, proposal: domain.OperatorProposal) -> domain.ProposalReceipt:
            observed.append(proposal)
            return domain.ProposalReceipt(
                proposal_id=proposal.proposal_id,
                operation=proposal.operation,
                state=domain.WordPressOperatorProposalState.PROPOSED,
                created_at=(now - timedelta(seconds=100))
                .isoformat()
                .replace("+00:00", "Z"),
                expires_at=(now + timedelta(seconds=800))
                .isoformat()
                .replace("+00:00", "Z"),
                replayed=True,
            )

    result, expired = cli._proposal_from_intent(
        adapter=RecoveredResponse(),  # type: ignore[arg-type]
        operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
    )
    assert not expired
    assert result["proposal_id"] == first.proposal_id
    assert observed[1].proposal_id == first.proposal_id
    assert observed[1].request_token == first.request_token
    with journal.exclusive(first.operation):
        assert journal.load(first.operation) is None


def test_fresh_intent_rejects_replayed_receipt_and_remains_pending(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", private_repository)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    observed: list[domain.OperatorProposal] = []

    class UnexpectedReplay:
        def propose(self, proposal: domain.OperatorProposal) -> domain.ProposalReceipt:
            observed.append(proposal)
            return domain.ProposalReceipt(
                proposal_id=proposal.proposal_id,
                operation=proposal.operation,
                state=domain.WordPressOperatorProposalState.PROPOSED,
                created_at=(now - timedelta(seconds=100))
                .isoformat()
                .replace("+00:00", "Z"),
                expires_at=(now + timedelta(seconds=800))
                .isoformat()
                .replace("+00:00", "Z"),
                replayed=True,
            )

    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        cli._proposal_from_intent(
            adapter=UnexpectedReplay(),  # type: ignore[arg-type]
            operation=domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
        )
    assert captured.value.code is domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
    proposal = observed[0]
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(
        private_repository
    )
    with journal.exclusive(proposal.operation):
        pending = journal.load(proposal.operation)
    assert pending is not None and pending.proposal_id == proposal.proposal_id


def test_terminal_replay_clears_recovered_intent_and_requires_new_token(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", private_repository)
    operation = domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE
    proposal = domain.OperatorProposal.yoast("c" * 64)
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(
        private_repository
    )
    with journal.exclusive(operation):
        journal.record(proposal)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    class TerminalReplay:
        def propose(self, recovered: domain.OperatorProposal) -> domain.ProposalReceipt:
            assert recovered.proposal_id == proposal.proposal_id
            return domain.ProposalReceipt(
                proposal_id=recovered.proposal_id,
                operation=recovered.operation,
                state=domain.WordPressOperatorProposalState.APPLIED,
                created_at=(now - timedelta(seconds=100))
                .isoformat()
                .replace("+00:00", "Z"),
                expires_at=(now + timedelta(seconds=800))
                .isoformat()
                .replace("+00:00", "Z"),
                replayed=True,
            )

    result, requires_new = cli._proposal_from_intent(
        adapter=TerminalReplay(),  # type: ignore[arg-type]
        operation=operation,
    )
    assert requires_new
    assert result["state"] == "APPLIED"
    assert result["next_action"] == "NEW_PROPOSAL_REQUIRED"
    assert result["human_approval_required"] is False
    with journal.exclusive(operation):
        assert journal.load(operation) is None


def test_validated_applied_receipt_clears_only_matching_create_intent(
    private_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = private_repository
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", repository)
    operation = domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE
    proposal = domain.OperatorProposal.yoast("8" * 64)
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(repository)
    with journal.exclusive(operation):
        journal.record(proposal)
        assert not journal.clear_matching_proposal_id(operation, "9" * 64)
        pending = journal.load(operation)
        assert pending is not None and pending.proposal_id == proposal.proposal_id

    class AmbiguousApply:
        def __init__(self, repository_root: Path) -> None:
            assert repository_root == repository

        def apply_yoast_profile(self, proposal_id: str) -> object:
            assert proposal_id == proposal.proposal_id
            raise domain.WordPressOperatorFailure(
                domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
            )

    arguments = cli._parser().parse_args(
        ["apply-yoast-profile", "--proposal-id", proposal.proposal_id]
    )
    monkeypatch.setattr(
        cli, "OfficialSelfHostedWordPressOperatorAdapter", AmbiguousApply
    )
    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        cli._run(arguments)
    assert captured.value.code is domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS
    with journal.exclusive(operation):
        pending = journal.load(operation)
        assert pending is not None and pending.proposal_id == proposal.proposal_id

    class Applied:
        def __init__(self, repository_root: Path) -> None:
            assert repository_root == repository

        def apply_yoast_profile(self, proposal_id: str) -> domain.ApplyReceipt:
            return domain.ApplyReceipt(
                proposal_id=proposal_id,
                operation=operation,
                result_code="YOAST_PROFILE_APPLIED",
                replayed=False,
            )

    monkeypatch.setattr(cli, "OfficialSelfHostedWordPressOperatorAdapter", Applied)
    assert cli._run(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["state"] == "APPLIED"
    with journal.exclusive(operation):
        assert journal.load(operation) is None
        assert not journal.clear_matching_proposal_id(operation, proposal.proposal_id)


def test_intent_staging_recovery_is_crash_atomic_and_fails_closed(
    private_repository: Path,
) -> None:
    repository = private_repository
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(repository)
    operation = domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE
    proposal = domain.OperatorProposal.yoast("a" * 64)
    intent = credentials.WordPressOperatorProposalIntent(
        operation=operation,
        proposal_id=proposal.proposal_id,
        request_token=proposal.request_token,
        canonical_request_sha256=proposal.proposal_id,
    )
    directory = repository / ".secrets/wordpress-operator-local/proposal-intents"
    final = directory / "apply-yoast-profile.intent.v1.json"
    pending = directory / ".apply-yoast-profile.intent.v1.json.pending"

    with journal.exclusive(operation):
        _write_fsynced_private(pending, intent.canonical_bytes())
        recovered = journal.load(operation)
        assert recovered == intent
        assert final.exists() and not pending.exists()
        assert final.stat().st_nlink == 1

        os.link(final, pending)
        assert final.stat().st_ino == pending.stat().st_ino
        assert final.stat().st_nlink == pending.stat().st_nlink == 2
        assert journal.load(operation) == intent
        assert final.exists() and not pending.exists()
        assert final.stat().st_nlink == 1

        _write_fsynced_private(pending, intent.canonical_bytes())
        assert final.stat().st_ino != pending.stat().st_ino
        with pytest.raises(domain.WordPressOperatorFailure) as captured:
            journal.load(operation)
        assert (
            captured.value.code
            is domain.WordPressOperatorFailureCode.CREDENTIAL_STORE_INVALID
        )

    update = domain.WordPressOperatorOperation.UPDATE_CHILD_THEME
    update_pending = directory / ".update-child-theme.intent.v1.json.pending"
    with journal.exclusive(update):
        _write_fsynced_private(update_pending, b"{}")
        with pytest.raises(domain.WordPressOperatorFailure) as captured:
            journal.load(update)
        assert (
            captured.value.code
            is domain.WordPressOperatorFailureCode.CREDENTIAL_STORE_INVALID
        )


def test_status_values_are_closed_and_theme_payload_has_no_inventory() -> None:
    assert [item.value for item in domain.WordPressOperatorYoastProfileCode] == [
        "YOAST_VERSION_ABSENT",
        "YOAST_VERSION_MISMATCH",
        "YOAST_PROFILE_PREREQUISITE_FAILED",
        "YOAST_PROFILE_MATCH",
        "YOAST_PROFILE_MISMATCH",
    ]
    assert [item.value for item in domain.WordPressOperatorThemeStateCode] == [
        "THEME_ABSENT",
        "THEME_TREE_UNREADABLE",
        "THEME_TREE_READABLE",
    ]
    theme = domain.OperatorThemeStatus(
        installed_version="1.1.1",
        active=True,
        state_code=domain.WordPressOperatorThemeStateCode.TREE_READABLE,
        file_count=2,
        tree_sha256="3" * 64,
    )
    assert theme.public_payload() == {
        "active": True,
        "file_count": 2,
        "installed_version": "1.1.1",
        "slug": "kurashinoshirube-child",
        "state_code": "THEME_TREE_READABLE",
        "tree_sha256": "3" * 64,
    }
    assert not ({"plugins", "site_health", "themes"} & theme.public_payload().keys())


def test_cli_grammar_is_exact_and_has_no_approval_token_package_or_url_input() -> None:
    parser = cli._parser()
    assert parser.allow_abbrev is False
    assert parser.fromfile_prefix_chars is None
    commands = (
        "status",
        "verify-yoast-checksums",
        "propose-yoast-profile",
        "apply-yoast-profile",
        "propose-theme-update",
        "apply-theme-update",
    )
    for command in commands[:3] + commands[4:5]:
        assert parser.parse_args([command]).command == command
    for command in ("apply-yoast-profile", "apply-theme-update"):
        parsed = parser.parse_args([command, "--proposal-id", "a" * 64])
        assert parsed.command == command
        assert parsed.proposal_id == "a" * 64
    for arguments in (
        ["approve", "a" * 64],
        ["publish"],
        ["propose-yoast-profile", "--request-token", "a" * 64],
        ["propose-theme-update", "--package", "/tmp/theme.zip"],
        ["status", "--url", "https://example.invalid"],
        ["status", "extra"],
        ["@/tmp/arguments.txt"],
    ):
        with pytest.raises(domain.WordPressOperatorFailure) as captured:
            parser.parse_args(arguments)
        assert (
            captured.value.code is domain.WordPressOperatorFailureCode.INVALID_ARGUMENT
        )
    source = (ROOT / "scripts/st1506_wordpress_operator.py").read_text(encoding="utf-8")
    assert "secrets.token_hex(32)" in source
    assert 'import_module("scripts.build_st1704_self_hosted_theme")' in source
    assert (
        'import_module("scripts.build_st1704_self_hosted_editorial_manifest")' in source
    )
    assert "runtime_manifest_builder.build_manifest()" in source
    assert "runtime_manifest_builder.OUTPUT_PATH.read_bytes()" in source
    assert "zipfile.ZIP_STORED" in source
    assert "_SanitizedArgumentParser" in source
    assert "--request-token" not in source
    assert "--package" not in source
    assert "--url" not in source


def test_operational_main_and_direct_python_bypass_refuse_before_adapter_use(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ForbiddenAdapter:
        def __init__(self, repository_root: Path) -> None:
            del repository_root
            pytest.fail("unsafe main reached credential or transport adapter")

    monkeypatch.setattr(
        cli, "OfficialSelfHostedWordPressOperatorAdapter", ForbiddenAdapter
    )
    monkeypatch.setattr(cli, "_STAGE_ZERO_VERIFIED", False)
    with pytest.raises(SystemExit) as captured:
        cli.main(["status"])
    assert captured.value.code == 69
    local = capsys.readouterr()
    assert local.out == ""
    assert local.err == "ST1506_WORDPRESS_OPERATOR_LAUNCH_REFUSED\n"

    result = subprocess.run(
        (sys.executable, "scripts/st1506_wordpress_operator.py", "status"),
        cwd=ROOT,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "TZ": "UTC",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert result.returncode == 69
    assert result.stdout == b""
    assert result.stderr == b"ST1506_WORDPRESS_OPERATOR_LAUNCH_REFUSED\n"


def test_operator_launcher_is_fixed_clean_and_binds_every_runtime_source() -> None:
    launcher_path = ROOT / "scripts/st1506_wordpress_operator_python.sh"
    launcher = launcher_path.read_text(encoding="ascii")
    assert launcher_path.stat().st_mode & 0o777 == 0o755
    for token in (
        "#!/usr/bin/busybox sh",
        "/usr/bin/busybox env -i",
        '"$python" -B -I -S -X pycache_prefix=/dev/null - "$@"',
        "RAOS_ST1506_STAGE_HEAD",
        "RAOS_ST1506_STAGE_CLI_BLOB",
        "RAOS_ST1506_STAGE_CLI_SHA256",
        "git hash-object --no-filters",
        "git cat-file blob",
    ):
        assert token in launcher
    assert "HOME=" not in launcher
    assert "curl" not in launcher and "wget" not in launcher
    for relative in cli._STAGE_RUNTIME_PATHS:
        assert relative in launcher

    source = (ROOT / "scripts/st1506_wordpress_operator.py").read_text(encoding="utf-8")
    assert source.index('if __name__ == "__main__":\n    _verify_stage_zero()') < (
        source.index("from raos.adapters.self_hosted_wordpress_operator_https")
    )
    assert source.index("_install_verified_runtime_imports(_STAGE_VERIFIED_BYTES)") < (
        source.index("from raos.adapters.self_hosted_wordpress_operator_https")
    )
    assert "if not _STAGE_ZERO_VERIFIED:\n        _stage_refuse()" in source


def test_verified_source_loader_ignores_post_verification_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = "scripts/build_st1704_self_hosted_theme.py"
    replacement = tmp_path / relative
    replacement.parent.mkdir(parents=True)
    replacement.write_text(
        'raise AssertionError("replacement reached credential or network boundary")\n'
        'VALUE = "replacement"\n',
        encoding="ascii",
    )
    monkeypatch.setattr(cli, "_EXPECTED_REPOSITORY_ROOT", tmp_path)
    loader = cli._VerifiedSourceLoader(
        "sealed_operator_probe",
        relative,
        b'VALUE = "verified-committed-bytes"\n',
    )
    module = types.ModuleType("sealed_operator_probe")
    loader.exec_module(module)
    assert getattr(module, "VALUE") == "verified-committed-bytes"
    assert replacement.read_text(encoding="ascii").startswith("raise AssertionError")


def test_theme_package_binds_captured_manifest_and_rechecks_after_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed_payload = b"committed theme bytes"
    replacement_payload = b"post-verification replacement"
    committed_digest = hashlib.sha256(committed_payload).hexdigest()
    bound_manifest = b"captured ST-1704 manifest"

    def package(payload: bytes) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("kurashinoshirube-child/style.css", payload)
        return output.getvalue()

    class ReplacedBeforeBuild:
        THEME_SLUG = "kurashinoshirube-child"
        THEME_VERSION = "1.1.2"
        SOURCE_FILES = ("style.css",)

        def validate_sources(self) -> dict[str, str]:
            return {"style.css": hashlib.sha256(replacement_payload).hexdigest()}

        def build_package(self) -> bytes:
            return package(replacement_payload)

    def bound_entries(manifest: bytes) -> dict[str, tuple[int, str]]:
        assert manifest == bound_manifest
        return {"style.css": (len(committed_payload), committed_digest)}

    monkeypatch.setattr(cli, "theme_builder", ReplacedBeforeBuild())
    monkeypatch.setattr(cli, "_verify_st1704_runtime_manifest", lambda: bound_manifest)
    monkeypatch.setattr(cli, "_bound_theme_entries", bound_entries)
    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        cli._theme_package()
    assert (
        captured.value.code is domain.WordPressOperatorFailureCode.THEME_PACKAGE_INVALID
    )

    source_replaced = False
    verification_count = 0

    class ReplacedAfterBuild:
        THEME_SLUG = "kurashinoshirube-child"
        THEME_VERSION = "1.1.2"
        SOURCE_FILES = ("style.css",)

        def validate_sources(self) -> dict[str, str]:
            return {"style.css": committed_digest}

        def build_package(self) -> bytes:
            nonlocal source_replaced
            source_replaced = True
            return package(committed_payload)

    def verify_after_build() -> bytes:
        nonlocal verification_count
        verification_count += 1
        if verification_count > 1 and source_replaced:
            domain.fail_wordpress_operator(
                domain.WordPressOperatorFailureCode.THEME_PACKAGE_INVALID
            )
        return bound_manifest

    monkeypatch.setattr(cli, "theme_builder", ReplacedAfterBuild())
    monkeypatch.setattr(cli, "_verify_st1704_runtime_manifest", verify_after_build)
    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        cli._theme_package()
    assert (
        captured.value.code is domain.WordPressOperatorFailureCode.THEME_PACKAGE_INVALID
    )
    assert verification_count == 2


def test_transport_is_one_origin_one_attempt_https_and_exact_apply_headers() -> None:
    assert https.WORDPRESS_OPERATOR_HOST == "kurashinoshirube.com"
    assert https.WORDPRESS_OPERATOR_PORT == 443
    assert https._STATUS_PATH == "/wp-json/raos-operator/v1/status"
    assert https._CHECKSUM_PATH == "/wp-json/raos-operator/v1/yoast-checksum"
    assert https._PROPOSAL_PATH == "/wp-json/raos-operator/v1/proposals"
    source = (
        ROOT / "python/raos/adapters/self_hosted_wordpress_operator_https.py"
    ).read_text(encoding="utf-8")
    for token in (
        'headers["Idempotency-Key"] = proposal_id',
        'headers["If-Match"] = f\'"{proposal_id}"\'',
        'content_type="application/zip"',
        "self._claim_attempt()",
        "ssl.create_default_context()",
        '"redirection"',
    ):
        if token == '"redirection"':
            assert token not in source
        else:
            assert token in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "allow_redirects" not in source
    assert "caller_url" not in source


def test_system_https_connection_forces_debug_off_before_secret_request(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(http.client.HTTPSConnection, "debuglevel", 1)
    context = ssl.create_default_context()
    connection = https.SystemWordPressOperatorHttpsConnectionFactory().open(
        host=https.WORDPRESS_OPERATOR_HOST,
        port=https.WORDPRESS_OPERATOR_PORT,
        connect_timeout_seconds=https.CONNECT_TIMEOUT_SECONDS,
        tls_context=context,
    )
    assert isinstance(connection, https._SystemConnection)
    raw = connection._connection
    assert raw.debuglevel == 0

    class SinkSocket:
        def sendall(self, payload: bytes) -> None:
            assert payload

        def close(self) -> None:
            pass

    raw.sock = SinkSocket()
    raw.debuglevel = 1
    connection.request(
        "POST",
        "/fixed",
        b'{"private-body":"never-log"}',
        {"Authorization": "Basic never-log-credential"},
    )
    assert raw.debuglevel == 0
    captured = capsys.readouterr()
    assert "never-log" not in captured.out
    assert "never-log" not in captured.err


def test_malformed_post_write_receipts_are_always_outcome_ambiguous(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = domain.OperatorProposal.yoast("b" * 64)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    proposal_response: dict[str, object] = {
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=900)).isoformat().replace("+00:00", "Z"),
        "operation": proposal.operation.value,
        "proposal_id": "malformed",
        "replayed": False,
        "schema": "RAOS_OPERATOR_PROPOSAL_V1",
        "state": "PROPOSED",
    }
    monkeypatch.setattr(
        https.OfficialSelfHostedWordPressOperatorAdapter,
        "_execute",
        lambda self, **kwargs: proposal_response,
    )
    adapter = https.OfficialSelfHostedWordPressOperatorAdapter(private_repository)
    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        adapter.propose(proposal)
    assert captured.value.code is domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS


def test_adapter_accepts_only_hash_bound_terminal_create_replay(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = domain.OperatorProposal.yoast("d" * 64)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    response: dict[str, object] = {
        "created_at": (now - timedelta(seconds=100)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=800)).isoformat().replace("+00:00", "Z"),
        "operation": proposal.operation.value,
        "proposal_id": proposal.proposal_id,
        "replayed": True,
        "schema": "RAOS_OPERATOR_PROPOSAL_V1",
        "state": "NEEDS_RECOVERY",
    }
    monkeypatch.setattr(
        https.OfficialSelfHostedWordPressOperatorAdapter,
        "_execute",
        lambda self, **kwargs: response,
    )
    receipt = https.OfficialSelfHostedWordPressOperatorAdapter(
        private_repository
    ).propose(proposal)
    assert receipt.state is domain.WordPressOperatorProposalState.NEEDS_RECOVERY
    assert receipt.replayed
    assert receipt.requires_new_proposal(now)


@pytest.mark.parametrize(
    ("operation", "wrong_result_code"),
    (
        (
            domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            "THEME_UPDATE_APPLIED",
        ),
        (
            domain.WordPressOperatorOperation.UPDATE_CHILD_THEME,
            "YOAST_PROFILE_APPLIED",
        ),
    ),
)
def test_apply_result_code_is_exactly_bound_to_operation(
    private_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: domain.WordPressOperatorOperation,
    wrong_result_code: str,
) -> None:
    proposal_id = "c" * 64
    apply_response: dict[str, object] = {
        "operation": operation.value,
        "proposal_id": proposal_id,
        "replayed": False,
        "result_code": wrong_result_code,
        "schema": "RAOS_OPERATOR_APPLY_V1",
        "state": "APPLIED",
    }
    monkeypatch.setattr(
        https.OfficialSelfHostedWordPressOperatorAdapter,
        "_execute",
        lambda self, **kwargs: apply_response,
    )
    adapter = https.OfficialSelfHostedWordPressOperatorAdapter(private_repository)
    with pytest.raises(domain.WordPressOperatorFailure) as captured:
        if operation is domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE:
            adapter.apply_yoast_profile(proposal_id)
        else:
            adapter.apply_theme_update(
                proposal_id,
                _theme(from_version="1.1.1", to_version="1.1.2"),
            )
    assert captured.value.code is domain.WordPressOperatorFailureCode.OUTCOME_AMBIGUOUS


def test_proxy_environment_is_inert_but_tls_override_environment_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "https://untrusted.invalid:9443")
    https.require_clean_wordpress_operator_environment()

    for name in ("SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"):
        monkeypatch.setenv(name, "/untrusted/nonempty")
        with pytest.raises(domain.WordPressOperatorFailure) as captured:
            https.require_clean_wordpress_operator_environment()
        assert (
            captured.value.code is domain.WordPressOperatorFailureCode.TRANSPORT_REFUSED
        )
        monkeypatch.delenv(name)


def test_credentials_and_failures_are_redacted_and_not_environment_driven() -> None:
    metadata = credentials.WordPressOperatorCredentialMetadata(
        site_origin="https://kurashinoshirube.com",
        username="bounded-executor",
        expected_role="raos_operator_executor",
    )
    value = credentials.WordPressOperatorCredentials(metadata, "secret app password")
    for rendered in (repr(metadata), str(metadata), repr(value), str(value)):
        assert "secret" not in rendered
        assert "bounded-executor" not in rendered
        assert "kurashinoshirube.com" not in rendered
    with pytest.raises(TypeError):
        pickle.dumps(value)
    failure = domain.WordPressOperatorFailure(
        domain.WordPressOperatorFailureCode.TRANSPORT_REFUSED
    )
    assert str(failure) == "WORDPRESS_OPERATOR_TRANSPORT_REFUSED"
    assert "secret" not in repr(failure)

    source = (
        ROOT / "python/raos/adapters/self_hosted_wordpress_operator_credentials.py"
    ).read_text(encoding="utf-8")
    assert ".secrets/wordpress-operator-local/credentials.v1.json" in source
    assert "os.getenv" not in source
    assert "os.environ" not in source
    assert "print(" not in source
    assert "canonical_request_sha256=proposal.proposal_id" in source
    assert "os.fsync(descriptor)" in source
    assert "os.link(" in source
    assert "os.fsync(directory_fd)" in source


def test_credential_and_journal_ownership_capture_effective_uid(
    private_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_euid = private_repository.stat().st_uid
    monkeypatch.setattr(os, "getuid", lambda: actual_euid + 1)
    monkeypatch.setattr(os, "geteuid", lambda: actual_euid)
    private = private_repository / ".secrets/wordpress-operator-local"
    credential_path = private / "credentials.v1.json"
    _write_fsynced_private(
        credential_path,
        json.dumps(
            {
                "application_password": "owner private application password",
                "expected_role": "raos_operator_executor",
                "schema_version": 1,
                "site_origin": "https://kurashinoshirube.com",
                "username": "bounded-executor",
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii"),
    )
    store = credentials.OwnerPrivateWordPressOperatorCredentialStore(private_repository)
    journal = credentials.OwnerPrivateWordPressOperatorProposalIntentJournal(
        private_repository
    )
    monkeypatch.setattr(os, "geteuid", lambda: actual_euid + 2)
    assert store.read_metadata().expected_role == "raos_operator_executor"
    operation = domain.WordPressOperatorOperation.APPLY_YOAST_PROFILE
    with journal.exclusive(operation):
        assert journal.load(operation) is None
    source = (
        ROOT / "python/raos/adapters/self_hosted_wordpress_operator_credentials.py"
    ).read_text(encoding="utf-8")
    assert "os.getuid()" not in source
    assert "os.geteuid()" in source
