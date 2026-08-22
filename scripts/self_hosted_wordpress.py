#!/usr/bin/env python3
"""Fixed owner-local commands for the ST-1703 self-hosted draft path."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import termios
from typing import Callable, NoReturn

_SCRIPT_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_ROOT = _SCRIPT_REPOSITORY_ROOT / "scripts"
_PYTHON_ROOT = _SCRIPT_REPOSITORY_ROOT / "python"
for _trusted_import_root in (_SCRIPTS_ROOT, _PYTHON_ROOT):
    if str(_trusted_import_root) not in sys.path:
        sys.path.insert(0, str(_trusted_import_root))

from build_st1703_self_hosted_theme import source_check as theme_source_check  # noqa: E402
from raos.adapters.self_hosted_wordpress_credentials import (  # noqa: E402
    OwnerPrivateSelfHostedWordPressCredentialStore,
    SelfHostedWordPressCredentials,
)
from raos.adapters.self_hosted_wordpress_https import (  # noqa: E402
    OfficialSelfHostedWordPressDraftAdapter,
)
from raos.adapters.self_hosted_wordpress_journal import (  # noqa: E402
    DurableSelfHostedWordPressDraftAdapter,
)
from raos.application.editorial.self_hosted_minimum_start import (  # noqa: E402
    load_first_article_candidate,
)
from raos.domain.editorial.self_hosted_wordpress import (  # noqa: E402
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    fail_self_hosted_wordpress,
)


EXPECTED_REPOSITORY_ROOT = Path("/home/minami/rakuten")
_MAX_TTY_BYTES = 4096


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


class _ClosedArgumentParser(argparse.ArgumentParser):
    """Reject malformed controls without reflecting untrusted argv values."""

    def error(self, message: str) -> NoReturn:
        del message
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)


def _physical_repository_root(value: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    try:
        if value.is_symlink() or value.resolve(strict=True) != value:
            _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    except OSError:
        _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
    return value


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        offset += written


def _read_private_tty(prompt: bytes) -> bytes:
    descriptor = -1
    original: list[int | list[bytes | int]] | None = None
    try:
        descriptor = os.open(
            "/dev/tty", os.O_RDWR | os.O_CLOEXEC | os.O_NOCTTY | os.O_NOFOLLOW
        )
        if not os.isatty(descriptor):
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        original = termios.tcgetattr(descriptor)
        hidden = list(original)
        local_flags = hidden[3]
        if type(local_flags) is not int:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        hidden[3] = local_flags & ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(descriptor, termios.TCSAFLUSH, hidden)
        _write_all(descriptor, prompt)
        chunks: list[bytes] = []
        total = 0
        while total <= _MAX_TTY_BYTES:
            byte = os.read(descriptor, 1)
            if not byte or byte in {b"\n", b"\r"}:
                break
            chunks.append(byte)
            total += len(byte)
        _write_all(descriptor, b"\n")
        value = b"".join(chunks)
        if not 1 <= len(value) <= _MAX_TTY_BYTES:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        return value
    except SelfHostedWordPressFailure:
        raise
    except BaseException:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    finally:
        if descriptor >= 0:
            if original is not None:
                try:
                    termios.tcsetattr(descriptor, termios.TCSAFLUSH, original)
                except BaseException:
                    pass
            os.close(descriptor)


def _install_credentials(
    repository_root: Path,
    *,
    tty_reader: Callable[[bytes], bytes],
) -> dict[str, object]:
    store = OwnerPrivateSelfHostedWordPressCredentialStore(repository_root)
    if store.metadata_status() != "MISSING":
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    username_raw = tty_reader(b"WordPress username (hidden): ")
    password_raw = tty_reader(b"WordPress application password (hidden): ")
    try:
        username = username_raw.decode("ascii", errors="strict")
        decoded_second_field = password_raw.decode("ascii", errors="strict")
    except UnicodeError:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
    store.install(
        SelfHostedWordPressCredentials(
            username=username,
            _application_password=decoded_second_field,
        )
    )
    return {
        "credential_metadata": "METADATA_READY",
        "network_requests": 0,
        "publication_actions": 0,
        "secret_values_printed": 0,
        "status": "INSTALLED",
    }


def _doctor(repository_root: Path) -> dict[str, object]:
    credential_status = OwnerPrivateSelfHostedWordPressCredentialStore(
        repository_root
    ).metadata_status()
    load_first_article_candidate(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    theme = theme_source_check()
    blockers = ["AFFILIATE_SLOTS_PENDING"]
    if credential_status != "METADATA_READY":
        blockers.append("WORDPRESS_CREDENTIAL_INSTALL_REQUIRED")
    if theme["package_ready"] is not True:
        blockers.append("FINAL_THEME_ASSETS_MISSING")
    return {
        "blockers": blockers,
        "content_packet": "VALID",
        "credential_metadata": credential_status,
        "credential_value_reads": 0,
        "external_writes": 0,
        "network_requests": 0,
        "publication_actions": 0,
        "status": "LOCAL_PREPARATION_REQUIRED" if blockers else "LOCAL_READY",
        "theme_source": theme["status"],
    }


def _receipt_output(receipt: SelfHostedWordPressDraftReceipt) -> dict[str, object]:
    return {
        "content_sha256": receipt.content_sha256,
        "disposition": receipt.disposition.value,
        "draft_id": receipt.draft_id,
        "operation": receipt.operation.value,
        "operation_sha256": receipt.operation_sha256,
        "production_eligible": False,
        "publication_authorized": False,
        "response_sha256": receipt.response_sha256,
        "status": receipt.status,
    }


def _apply_draft(
    repository_root: Path,
) -> dict[str, object]:
    if (
        OwnerPrivateSelfHostedWordPressCredentialStore(
            repository_root
        ).metadata_status()
        != "METADATA_READY"
    ):
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID)
    candidate = load_first_article_candidate(
        repository_root,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    attempt = OfficialSelfHostedWordPressDraftAdapter(repository_root)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=repository_root,
        attempt_port=attempt,
    )
    return _receipt_output(durable.apply(candidate))


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", allow_abbrev=False)
    commands.add_parser("install-credentials", allow_abbrev=False)
    commands.add_parser("create-draft", allow_abbrev=False)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path = EXPECTED_REPOSITORY_ROOT,
    tty_reader: Callable[[bytes], bytes] = _read_private_tty,
) -> int:
    os.umask(0o077)
    try:
        arguments = _parser().parse_args(argv)
        root = _physical_repository_root(repository_root)
        if arguments.command == "doctor":
            result = _doctor(root)
        elif arguments.command == "install-credentials":
            result = _install_credentials(root, tty_reader=tty_reader)
        elif arguments.command == "create-draft":
            result = _apply_draft(root)
        else:
            _fail(SelfHostedWordPressFailureCode.OPERATION_NOT_ALLOWED)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except SelfHostedWordPressFailure as error:
        print(
            json.dumps(
                {
                    "publication_authorized": False,
                    "reason_code": error.code.value,
                    "status": "BLOCKED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
