"""Offline command tests for the exact WordPress.com review-draft slice."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
from types import ModuleType
from typing import Any

import pytest

from raos.adapters.wordpresscom_oauth import (
    WordPressComOAuthCallbackDiagnosticCode,
    WordPressComOAuthCallbackFailure,
    WordPressComOAuthTokenDiagnosticCode,
    WordPressComOAuthTokenFailure,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_STATUS,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    WordPressComReviewDraftReceipt,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/wordpresscom_review_draft.py"
LAUNCHER_PATH = REPOSITORY_ROOT / "scripts/wordpresscom_review_draft_python.sh"


def _load_script() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "st1703_wordpresscom_review_draft_cli", SCRIPT_PATH
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module._EXPECTED_REPOSITORY_ROOT == Path("/home/minami/rakuten")
    # Standing development authority permits reversible tests in an isolated
    # worktree; production keeps the exact physical-root requirement above.
    module._EXPECTED_REPOSITORY_ROOT = REPOSITORY_ROOT
    return module


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)


def _copy_bound_sources(module: ModuleType, repository: Path) -> None:
    for relative, _, _ in module._FIXED_SOURCES:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPOSITORY_ROOT / relative).read_bytes())


def _prepare_repository(module: ModuleType, tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _copy_bound_sources(module, repository)
    _private_directory(repository / ".secrets")
    _private_directory(repository / ".secrets/wordpresscom-review-draft")
    module._EXPECTED_REPOSITORY_ROOT = repository
    return repository


def test_cli_preserves_predecessor_commands_and_sanitized_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    calls: list[tuple[str, Path]] = []

    def oauth_runner(root: Path) -> dict[str, object]:
        calls.append(("oauth", root))
        return {
            "access_token_alias": "wordpresscom_oauth_access_token",
            "access_token_stored": True,
            "command": "oauth-setup",
            "publication_authorized": False,
            "scope": "posts",
            "target_origin": "https://kurashierabinote.wordpress.com",
        }

    def create_runner(root: Path) -> dict[str, object]:
        calls.append(("create", root))
        return {
            "command": "create-review-draft",
            "draft_id": 1703,
            "publication_authorized": False,
            "status": "draft",
        }

    assert (
        module.main(
            ["oauth-setup"],
            oauth_runner=oauth_runner,
            create_runner=create_runner,
        )
        == 0
    )
    oauth_output = json.loads(capsys.readouterr().out)
    assert oauth_output == {
        "access_token_alias": "wordpresscom_oauth_access_token",
        "access_token_stored": True,
        "command": "oauth-setup",
        "ok": True,
        "publication_authorized": False,
        "scope": "posts",
        "target_origin": "https://kurashierabinote.wordpress.com",
    }

    assert (
        module.main(
            ["create-review-draft"],
            oauth_runner=oauth_runner,
            create_runner=create_runner,
        )
        == 0
    )
    create_output = json.loads(capsys.readouterr().out)
    assert create_output == {
        "command": "create-review-draft",
        "draft_id": 1703,
        "ok": True,
        "publication_authorized": False,
        "status": "draft",
    }
    assert calls == [
        ("oauth", REPOSITORY_ROOT),
        ("create", REPOSITORY_ROOT),
    ]

    subcommands = module._parser()._subparsers._group_actions[0].choices
    assert set(subcommands) == {
        "oauth-setup",
        "create-review-draft",
        "prepare-mvp-drafts",
        "preview-mvp",
    }
    for forbidden in {
        "publish",
        "schedule",
        "update",
        "delete",
        "media",
        "retry",
        "target",
    }:
        assert forbidden not in subcommands


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["oauth"],
        ["create"],
        ["oauth-setup", "--scope", "global"],
        ["create-review-draft", "--api-origin", "https://example.invalid"],
        ["create-review-draft", "--site-id", "256699520"],
        ["create-review-draft", "--path", "/wp/v2/sites/256699520/posts"],
        [
            "create-review-draft",
            "--path",
            "/rest/v1.1/sites/256699520/posts/new",
        ],
        ["create-review-draft", "--publicize", "true"],
        ["create-review-draft", "--target", "https://example.invalid"],
        ["create-review-draft", "--status", "publish"],
        ["create-review-draft", "--publish"],
        ["create-review-draft", "--schedule"],
        ["create-review-draft", "--update"],
        ["create-review-draft", "--delete"],
        ["create-review-draft", "--media"],
        ["create-review-draft", "--retry"],
    ],
)
def test_cli_rejects_missing_near_or_extra_controls(arguments: list[str]) -> None:
    module = _load_script()
    with pytest.raises(SystemExit) as caught:
        module.main(arguments)
    assert caught.value.code == 2


def test_missing_client_files_returns_only_fixed_registration_guidance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)

    def no_tty(_: str) -> bytes:
        raise WordPressComReviewDraftFailure(
            WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID
        )

    monkeypatch.setattr(module, "_read_private_tty", no_tty)

    assert module.main(["oauth-setup"], repository_root=repository) == 2

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "manual_action": "REGISTER_APPLICATION_AND_CREATE_PRIVATE_CLIENT_FILES",
        "ok": False,
        "reason_code": "REVIEW_DRAFT_OAUTH_SECRET_STORE_INVALID",
        "redirect_uri": "http://127.0.0.1:18703/oauth/wordpresscom/callback",
        "registration_url": "https://developer.wordpress.com/apps/new/",
        "scope": "posts",
        "target_origin": "https://kurashierabinote.wordpress.com",
    }
    assert not (
        repository
        / ".secrets/wordpresscom-review-draft/wordpresscom_oauth_access_token"
    ).exists()


def test_client_credentials_are_hidden_input_and_exclusive_private_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)
    values = {
        "WordPress.com Client ID: ": b"synthetic-client-id",
        "WordPress.com Client Secret: ": b"synthetic-client-secret-not-real",
    }
    prompts: list[str] = []

    def reader(prompt: str) -> bytes:
        prompts.append(prompt)
        return values[prompt]

    module._initialize_client_credentials(repository, reader=reader)

    root = repository / ".secrets/wordpresscom-review-draft"
    assert prompts == list(values)
    assert (root / "wordpresscom_oauth_client_id").read_bytes() == (
        values[prompts[0]] + b"\n"
    )
    assert (root / "wordpresscom_oauth_client_secret").read_bytes() == (
        values[prompts[1]] + b"\n"
    )
    assert all(
        stat.S_IMODE((root / name).stat().st_mode) == 0o600
        for name in {
            "wordpresscom_oauth_client_id",
            "wordpresscom_oauth_client_secret",
        }
    )
    assert capsys.readouterr().out == ""

    def must_not_prompt(_: str) -> bytes:
        pytest.fail("existing credentials must not be prompted or overwritten")

    module._initialize_client_credentials(repository, reader=must_not_prompt)


def test_private_tty_writes_the_complete_prompt_after_partial_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    descriptor = 1703
    prompt = "WordPress.com Client Secret: "
    input_bytes = bytearray(b"synthetic-client-secret-not-real\n")
    output = bytearray()
    terminal_modes: list[list[Any]] = []
    closed: list[int] = []
    original = [0, 0, 0, termios_flags := module.termios.ECHO, 0, 0, []]

    def fake_open(path: str, flags: int) -> int:
        assert path == "/dev/tty"
        assert flags & os.O_RDWR
        return descriptor

    def fake_write(target: int, value: bytes) -> int:
        assert target == descriptor
        count = min(3, len(value))
        output.extend(value[:count])
        return count

    def fake_read(target: int, count: int) -> bytes:
        assert target == descriptor
        assert count == 1
        return bytes([input_bytes.pop(0)])

    def fake_tcsetattr(target: int, when: int, attributes: list[Any]) -> None:
        assert target == descriptor
        assert when == module.termios.TCSANOW
        terminal_modes.append(attributes.copy())

    monkeypatch.setattr(module.os, "open", fake_open)
    monkeypatch.setattr(
        module.os,
        "fstat",
        lambda target: os.stat_result((stat.S_IFCHR, 0, 0, 1, 0, 0, 0, 0, 0, 0)),
    )
    monkeypatch.setattr(module.os, "read", fake_read)
    monkeypatch.setattr(module.os, "write", fake_write)
    monkeypatch.setattr(module.os, "close", closed.append)
    monkeypatch.setattr(module.termios, "tcgetattr", lambda target: original.copy())
    monkeypatch.setattr(module.termios, "tcsetattr", fake_tcsetattr)

    value = module._read_private_tty(prompt)

    assert value == b"synthetic-client-secret-not-real"
    assert output == prompt.encode("ascii") + b"\n"
    assert terminal_modes[0][3] == termios_flags & ~module.termios.ECHO
    assert terminal_modes[-1] == original
    assert closed == [descriptor]


def test_launcher_ignores_hostile_path_browser_and_tls_environment(
    tmp_path: Path,
) -> None:
    hostile_bin = tmp_path / "hostile-bin"
    hostile_bin.mkdir()
    sentinel = tmp_path / "hostile-command-ran"
    for command in {"browser", "dirname", "id", "readlink", "stat"}:
        executable = hostile_bin / command
        executable.write_text(
            f"#!/bin/sh\n/usr/bin/touch '{sentinel}'\nexit 97\n",
            encoding="ascii",
        )
        executable.chmod(0o700)
    environment = os.environ.copy()
    environment.update(
        {
            "BROWSER": str(hostile_bin / "browser"),
            "PATH": str(hostile_bin),
            "SSL_CERT_DIR": str(tmp_path / "untrusted-cert-dir"),
            "SSL_CERT_FILE": str(tmp_path / "untrusted-cert-file"),
            "SSLKEYLOGFILE": str(tmp_path / "tls-key-log"),
        }
    )

    result = subprocess.run(
        [str(LAUNCHER_PATH), "--help"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    if REPOSITORY_ROOT != Path("/home/minami/rakuten"):
        assert result.returncode == 69
        assert result.stdout == ""
        assert result.stderr == (
            "error: WordPress.com review-draft launcher is outside the physical "
            "RAOS repository\n"
        )
        assert not sentinel.exists()
        assert not (tmp_path / "tls-key-log").exists()
        return

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert (
        "{oauth-setup,create-review-draft,prepare-mvp-drafts,preview-mvp}"
        in result.stdout
    )
    assert not sentinel.exists()
    assert not (tmp_path / "tls-key-log").exists()

    environment_snapshot = tmp_path / "environment.snapshot"
    argument_snapshot = tmp_path / "arguments.snapshot"
    probe = subprocess.run(
        [
            "/bin/bash",
            "-p",
            "-c",
            r"""
environment_snapshot=$2
argument_snapshot=$3
exec() {
  /usr/bin/env -0 > "$environment_snapshot"
  /usr/bin/printf '%s\0' "$@" > "$argument_snapshot"
}
source "$1" --help
""",
            "launcher-environment-probe",
            str(LAUNCHER_PATH),
            str(environment_snapshot),
            str(argument_snapshot),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    observed_environment = dict(
        member.split(b"=", 1)
        for member in environment_snapshot.read_bytes().split(b"\0")
        if member
    )
    assert observed_environment[b"PATH"] == b"/usr/bin:/bin"
    for name in {"BROWSER", "SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"}:
        assert name.encode("ascii") not in observed_environment
    assert argument_snapshot.read_bytes().split(b"\0") == [
        str(REPOSITORY_ROOT / ".venv/bin/python").encode("ascii"),
        b"-I",
        str(SCRIPT_PATH).encode("ascii"),
        b"--help",
        b"",
    ]


@pytest.mark.parametrize("source_index", range(5))
def test_any_bound_source_tamper_stops_before_secret_or_state_creation(
    tmp_path: Path, source_index: int
) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)
    source = repository / module._FIXED_SOURCES[source_index][0]
    source.write_bytes(source.read_bytes() + b"tamper")

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        module._run_create_review_draft(repository)

    assert (
        caught.value.code is WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID
    )
    assert not (repository / ".secrets/wordpresscom-review-draft/state").exists()


def test_missing_token_stops_before_state_intent(tmp_path: Path) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)

    with pytest.raises(WordPressComReviewDraftFailure):
        module._run_create_review_draft(repository)

    assert not (
        repository
        / ".secrets/wordpresscom-review-draft/state/review-draft-state.v1.json"
    ).exists()


def test_exact_create_composition_commits_once_then_replays_without_creator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)
    token = repository / (
        ".secrets/wordpresscom-review-draft/wordpresscom_oauth_access_token"
    )
    token.write_bytes(b"synthetic-access-token-not-real\n")
    token.chmod(0o600)
    preflights: list[str] = []
    attempts: list[str] = []

    class FakeCreator:
        def __init__(self, *, token_reader: object, connection_factory: object) -> None:
            del token_reader, connection_factory

        def require_create_capability(self, candidate: WordPressComReviewDraft) -> None:
            preflights.append(candidate.operation_binding_sha256)

        def attempt_create_review_draft(
            self, candidate: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            attempts.append(candidate.operation_binding_sha256)
            return WordPressComReviewDraftReceipt(
                schema=WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
                authority=WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
                network_status=WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
                target_origin=candidate.target_origin,
                draft_id=1703,
                status=WORDPRESSCOM_REVIEW_DRAFT_STATUS,
                operation_binding_sha256=candidate.operation_binding_sha256,
                content_sha256=candidate.content_sha256,
                response_body_sha256=hashlib.sha256(b"synthetic-response").hexdigest(),
                disposition=ReviewDraftDisposition.CREATED,
                publication_authorized=False,
                production_eligible=False,
            )

    real_creator = module.OfficialWordPressComReviewDraftAdapter
    monkeypatch.setattr(module, "OfficialWordPressComReviewDraftAdapter", FakeCreator)
    created = module._run_create_review_draft(repository)
    token.unlink()

    def fail_token_read(*args: object, **kwargs: object) -> object:
        del args, kwargs
        pytest.fail("committed replay reached the token-read boundary")

    class TrapConnectionFactory:
        def open(self, **kwargs: object) -> object:
            del kwargs
            pytest.fail("committed replay reached the HTTPS connection boundary")

    monkeypatch.setattr(module, "OfficialWordPressComReviewDraftAdapter", real_creator)
    monkeypatch.setattr(
        module,
        "SystemWordPressComHttpsConnectionFactory",
        TrapConnectionFactory,
    )
    monkeypatch.setattr(module.WordPressComOAuthSecretStore, "read", fail_token_read)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: pytest.fail(
            "committed replay reached the DNS boundary"
        ),
    )
    replayed = module._run_create_review_draft(repository)

    exact_output = {
        "authority": "OWNER_AUTHORIZED_EXTERNAL_REVIEW_COPY",
        "command": "create-review-draft",
        "content_sha256": (
            "6eab149a4057d3f21dad6fa9efdbe66aadfafa00f100038541a3971693a8503d"
        ),
        "draft_id": 1703,
        "network_status": "EXECUTED_LIVE_DRAFT_CREATE",
        "operation_binding_sha256": (
            "794cee08b70ea1762f2c78b9be9826a486ab1beec44844a9fbd013e740ee2abd"
        ),
        "production_eligible": False,
        "publication_authorized": False,
        "response_body_sha256": hashlib.sha256(b"synthetic-response").hexdigest(),
        "schema": "WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_V1",
        "status": "draft",
        "target_origin": "https://kurashierabinote.wordpress.com",
    }
    assert created == exact_output | {"disposition": "CREATED"}
    assert replayed == exact_output | {"disposition": "COMMITTED_REPLAY"}
    assert preflights == attempts
    assert len(preflights) == len(attempts) == 1
    state_path = repository / (
        ".secrets/wordpresscom-review-draft/state/review-draft-state.v1.json"
    )
    state = json.loads(state_path.read_text(encoding="ascii"))
    assert state["state"] == "COMMITTED"
    assert set(state).isdisjoint({"title", "article_content", "access_token"})
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600


def test_v1_1_preflight_failure_stops_before_state_or_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repository = _prepare_repository(module, tmp_path)
    token = repository / (
        ".secrets/wordpresscom-review-draft/wordpresscom_oauth_access_token"
    )
    token.write_bytes(b"synthetic-access-token-not-real\n")
    token.chmod(0o600)
    preflights: list[str] = []
    attempts: list[str] = []

    class RefusingCreator:
        def __init__(self, *, token_reader: object, connection_factory: object) -> None:
            del token_reader, connection_factory

        def require_create_capability(self, candidate: WordPressComReviewDraft) -> None:
            preflights.append(candidate.operation_binding_sha256)
            raise WordPressComReviewDraftFailure(
                WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID
            )

        def attempt_create_review_draft(
            self, candidate: WordPressComReviewDraft
        ) -> WordPressComReviewDraftReceipt:
            attempts.append(candidate.operation_binding_sha256)
            pytest.fail("preflight refusal must prevent the create attempt")

    monkeypatch.setattr(
        module, "OfficialWordPressComReviewDraftAdapter", RefusingCreator
    )

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        module._run_create_review_draft(repository)

    assert caught.value.code is WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID
    assert len(preflights) == 1
    assert attempts == []
    assert not (
        repository
        / ".secrets/wordpresscom-review-draft/state/review-draft-state.v1.json"
    ).exists()


def test_closed_failure_output_never_includes_exception_or_secret_detail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    secret = "raw-secret-never-render"

    def failing(_: Path) -> dict[str, Any]:
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            raise WordPressComReviewDraftFailure(
                WordPressComReviewDraftFailureCode.OAUTH_CALLBACK_INVALID
            ) from None

    assert module.main(["oauth-setup"], oauth_runner=failing) == 2
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output) == {
        "ok": False,
        "reason_code": "REVIEW_DRAFT_OAUTH_CALLBACK_INVALID",
    }


def test_callback_failure_prints_only_closed_diagnostic_category(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    def failing(_: Path) -> dict[str, Any]:
        raise WordPressComOAuthCallbackFailure(
            WordPressComOAuthCallbackDiagnosticCode.STATE_MISMATCH
        )

    assert module.main(["oauth-setup"], oauth_runner=failing) == 2
    assert json.loads(capsys.readouterr().out) == {
        "diagnostic_code": "OAUTH_CALLBACK_STATE_MISMATCH",
        "ok": False,
        "reason_code": "REVIEW_DRAFT_OAUTH_CALLBACK_INVALID",
    }


def test_token_failure_prints_only_closed_diagnostic_category(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    def failing(_: Path) -> dict[str, Any]:
        raise WordPressComOAuthTokenFailure(
            WordPressComOAuthTokenDiagnosticCode.BLOG_URL_PATH_INVALID
        )

    assert module.main(["oauth-setup"], oauth_runner=failing) == 2
    assert json.loads(capsys.readouterr().out) == {
        "diagnostic_code": "OAUTH_TOKEN_BLOG_URL_PATH_INVALID",
        "ok": False,
        "reason_code": "REVIEW_DRAFT_OAUTH_TOKEN_EXCHANGE_INVALID",
    }
