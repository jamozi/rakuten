#!/usr/bin/env python3
"""Closed CLI for exact ST-1704 one-article publication proposals."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
from typing import Final, NoReturn
import types


_EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
_EXPECTED_PYTHON: Final = _EXPECTED_REPOSITORY_ROOT / ".venv/bin/python"
_EXPECTED_PYTHON_BASE: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu"
)
_STAGE_HEAD_ENV: Final = "RAOS_ST1704_PUBLICATION_V2_STAGE_HEAD"
_STAGE_CLI_BLOB_ENV: Final = "RAOS_ST1704_PUBLICATION_V2_STAGE_CLI_BLOB"
_STAGE_CLI_SHA256_ENV: Final = "RAOS_ST1704_PUBLICATION_V2_STAGE_CLI_SHA256"
_STAGE_REFUSAL: Final = "ST1704_PUBLICATION_OPERATOR_V2_LAUNCH_REFUSED"
_STAGE_MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
_STAGE_GIT_ENVIRONMENT: Final = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_STAGE_RUNTIME_PATHS: Final = (
    "changes/st-1704/publication-operator-v2/runtime-manifest.v2.json",
    "python/raos/__init__.py",
    "python/raos/adapters/__init__.py",
    "python/raos/adapters/self_hosted_editorial_pilot_json.py",
    "python/raos/adapters/self_hosted_wordpress_operator_credentials.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_https_v2.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_journal_v2.py",
    "python/raos/adapters/self_hosted_wordpress_publication_operator_json_v2.py",
    "python/raos/domain/editorial/self_hosted_editorial_pilot.py",
    "python/raos/domain/operations/self_hosted_wordpress_operator.py",
    "python/raos/domain/operations/self_hosted_wordpress_draft_revision_operator_v2.py",
    "python/raos/domain/operations/self_hosted_wordpress_publication_operator_v2.py",
    "python/raos/ports/__init__.py",
    "python/raos/ports/self_hosted_editorial_pilot.py",
    "python/raos/ports/self_hosted_wordpress_publication_operator_v2.py",
    "scripts/build_st1704_wordpress_publication_operator_v2.py",
    "scripts/st1704_wordpress_publication_operator_v2.py",
    "scripts/st1704_wordpress_publication_operator_v2_python.sh",
)
_STAGE_MODULE_PATHS: Final = {
    "raos.domain.editorial.self_hosted_editorial_pilot": (
        "python/raos/domain/editorial/self_hosted_editorial_pilot.py"
    ),
    "raos.ports.self_hosted_editorial_pilot": (
        "python/raos/ports/self_hosted_editorial_pilot.py"
    ),
    "raos.adapters.self_hosted_editorial_pilot_json": (
        "python/raos/adapters/self_hosted_editorial_pilot_json.py"
    ),
    "raos.domain.operations.self_hosted_wordpress_operator": (
        "python/raos/domain/operations/self_hosted_wordpress_operator.py"
    ),
    "raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2": (
        "python/raos/domain/operations/self_hosted_wordpress_draft_revision_operator_v2.py"
    ),
    "raos.adapters.self_hosted_wordpress_operator_credentials": (
        "python/raos/adapters/self_hosted_wordpress_operator_credentials.py"
    ),
    "raos.domain.operations.self_hosted_wordpress_publication_operator_v2": (
        "python/raos/domain/operations/self_hosted_wordpress_publication_operator_v2.py"
    ),
    "raos.ports.self_hosted_wordpress_publication_operator_v2": (
        "python/raos/ports/self_hosted_wordpress_publication_operator_v2.py"
    ),
    "raos.adapters.self_hosted_wordpress_publication_operator_json_v2": (
        "python/raos/adapters/self_hosted_wordpress_publication_operator_json_v2.py"
    ),
    "raos.adapters.self_hosted_wordpress_publication_operator_journal_v2": (
        "python/raos/adapters/self_hosted_wordpress_publication_operator_journal_v2.py"
    ),
    "raos.adapters.self_hosted_wordpress_publication_operator_https_v2": (
        "python/raos/adapters/self_hosted_wordpress_publication_operator_https_v2.py"
    ),
}
_STAGE_PACKAGE_NAMES: Final = (
    "raos",
    "raos.adapters",
    "raos.domain",
    "raos.domain.editorial",
    "raos.domain.operations",
    "raos.ports",
    "scripts",
)
_STAGE_ZERO_VERIFIED = False
_STAGE_VERIFIED_BYTES: dict[str, bytes] | None = None


def _stage_refuse() -> NoReturn:
    print(_STAGE_REFUSAL, file=sys.stderr)
    raise SystemExit(69) from None


def _stage_git(*arguments: str, maximum_stdout: int) -> bytes:
    if (
        not arguments
        or any(type(value) is not str or not value for value in arguments)
        or type(maximum_stdout) is not int
        or not 0 <= maximum_stdout <= _STAGE_MAX_SOURCE_BYTES
    ):
        _stage_refuse()
    try:
        result = subprocess.run(
            (
                "/usr/bin/git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                _EXPECTED_REPOSITORY_ROOT.as_posix(),
                *arguments,
            ),
            check=False,
            env=_STAGE_GIT_ENVIRONMENT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except BaseException:
        _stage_refuse()
    if result.returncode != 0 or len(result.stdout) > maximum_stdout:
        _stage_refuse()
    return result.stdout


def _stage_head_bytes(head: str, relative: str) -> bytes:
    object_name = f"{head}:{relative}"
    raw_size = _stage_git("cat-file", "-s", object_name, maximum_stdout=80)
    try:
        size_text = raw_size.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _stage_refuse()
    if str(size) != size_text or not 1 <= size <= _STAGE_MAX_SOURCE_BYTES:
        _stage_refuse()
    payload = _stage_git(
        "cat-file", "blob", object_name, maximum_stdout=_STAGE_MAX_SOURCE_BYTES
    )
    if len(payload) != size:
        _stage_refuse()
    return payload


def _stage_working_bytes(relative: str) -> bytes:
    path = _EXPECTED_REPOSITORY_ROOT / relative
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _stage_refuse()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not 1 <= metadata.st_size <= _STAGE_MAX_SOURCE_BYTES
        or len(payload) != metadata.st_size
    ):
        _stage_refuse()
    return payload


class _VerifiedSourceLoader(importlib.abc.Loader):
    __slots__ = ("_fullname", "_payload", "_relative")

    def __init__(self, fullname: str, relative: str, payload: bytes) -> None:
        if (
            type(fullname) is not str
            or not fullname
            or relative not in _STAGE_RUNTIME_PATHS
            or type(payload) is not bytes
            or not 1 <= len(payload) <= _STAGE_MAX_SOURCE_BYTES
        ):
            _stage_refuse()
        self._fullname = fullname
        self._relative = relative
        self._payload = payload

    def create_module(
        self, spec: importlib.machinery.ModuleSpec
    ) -> types.ModuleType | None:
        del spec
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        if module.__name__ != self._fullname:
            _stage_refuse()
        filename = (_EXPECTED_REPOSITORY_ROOT / self._relative).as_posix()
        try:
            code = compile(self._payload, filename, "exec", dont_inherit=True)
            module.__file__ = filename
            setattr(module, "__cached__", None)
            module.__loader__ = self
            module.__package__ = self._fullname.rpartition(".")[0]
            exec(code, module.__dict__)
        except SystemExit:
            raise
        except BaseException:
            _stage_refuse()


class _VerifiedSourceFinder(importlib.abc.MetaPathFinder):
    __slots__ = ("_payloads",)

    def __init__(self, verified_bytes: dict[str, bytes]) -> None:
        if set(_STAGE_MODULE_PATHS.values()) - set(verified_bytes):
            _stage_refuse()
        self._payloads = {
            fullname: verified_bytes[relative]
            for fullname, relative in _STAGE_MODULE_PATHS.items()
        }

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        relative = _STAGE_MODULE_PATHS.get(fullname)
        if relative is not None:
            return importlib.machinery.ModuleSpec(
                fullname,
                _VerifiedSourceLoader(fullname, relative, self._payloads[fullname]),
                origin=(_EXPECTED_REPOSITORY_ROOT / relative).as_posix(),
                is_package=False,
            )
        if fullname.startswith("raos.") or fullname.startswith("scripts."):
            _stage_refuse()
        return None


def _install_verified_runtime_imports(verified_bytes: dict[str, bytes]) -> None:
    if (
        not _STAGE_ZERO_VERIFIED
        or type(verified_bytes) is not dict
        or any(
            name == package or name.startswith(f"{package}.")
            for name in sys.modules
            for package in ("raos", "scripts")
        )
    ):
        _stage_refuse()
    for name in _STAGE_PACKAGE_NAMES:
        module = types.ModuleType(name)
        module.__package__ = name
        module.__loader__ = None
        specification = importlib.machinery.ModuleSpec(
            name, loader=None, is_package=True
        )
        specification.submodule_search_locations = []
        module.__spec__ = specification
        setattr(module, "__path__", [])
        sys.modules[name] = module
        parent_name, separator, child_name = name.rpartition(".")
        if separator:
            parent = sys.modules.get(parent_name)
            if parent is None:
                _stage_refuse()
            setattr(parent, child_name, module)
    sys.meta_path.insert(0, _VerifiedSourceFinder(verified_bytes))


def _verify_stage_zero() -> None:
    global _STAGE_VERIFIED_BYTES, _STAGE_ZERO_VERIFIED
    expected_environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    try:
        stage_head = os.environ.pop(_STAGE_HEAD_ENV)
        stage_cli_blob = os.environ.pop(_STAGE_CLI_BLOB_ENV)
        stage_cli_sha256 = os.environ.pop(_STAGE_CLI_SHA256_ENV)
        stdin_metadata = os.fstat(0)
        current_directory = os.getcwd()
        resolved_root = _EXPECTED_REPOSITORY_ROOT.resolve(strict=True)
    except KeyError, OSError:
        _stage_refuse()
    if (
        __name__ != "__main__"
        or globals().get("__file__") != "<stdin>"
        or current_directory != _EXPECTED_REPOSITORY_ROOT.as_posix()
        or resolved_root != _EXPECTED_REPOSITORY_ROOT
        or dict(os.environ) != expected_environment
        or sys.version_info[:3] != (3, 14, 6)
        or sys.executable != _EXPECTED_PYTHON.as_posix()
        or Path(sys.prefix) != _EXPECTED_REPOSITORY_ROOT / ".venv"
        or Path(sys.base_prefix) != _EXPECTED_PYTHON_BASE
        or sys.flags.dont_write_bytecode != 1
        or sys.flags.ignore_environment != 1
        or sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or sys.flags.no_user_site != 1
        or not sys.flags.safe_path
        or sys.pycache_prefix != "/dev/null"
        or sys.argv[0] != "-"
        or tuple(sys.orig_argv[:7])
        != (
            _EXPECTED_PYTHON.as_posix(),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            "-",
        )
        or sys.orig_argv[7:] != sys.argv[1:]
        or os.isatty(0)
        or not stat.S_ISFIFO(stdin_metadata.st_mode)
        or any(
            name == "raos"
            or name.startswith("raos.")
            or name == "scripts"
            or name.startswith("scripts.")
            or name in {"site", "sitecustomize", "usercustomize"}
            for name in sys.modules
        )
        or len(stage_head) != 40
        or any(character not in "0123456789abcdef" for character in stage_head)
        or len(stage_cli_blob) != 40
        or any(character not in "0123456789abcdef" for character in stage_cli_blob)
        or len(stage_cli_sha256) != 64
        or any(character not in "0123456789abcdef" for character in stage_cli_sha256)
    ):
        _stage_refuse()
    top = _stage_git("rev-parse", "--show-toplevel", maximum_stdout=256)
    current_head = _stage_git(
        "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=80
    ).strip()
    if top != os.fsencode(
        _EXPECTED_REPOSITORY_ROOT.as_posix()
    ) + b"\n" or current_head != stage_head.encode("ascii"):
        _stage_refuse()
    verified_bytes: dict[str, bytes] = {}
    cli_bytes: bytes | None = None
    cli_relative = "scripts/st1704_wordpress_publication_operator_v2.py"
    for relative in _STAGE_RUNTIME_PATHS:
        committed = _stage_head_bytes(stage_head, relative)
        if committed != _stage_working_bytes(relative):
            _stage_refuse()
        verified_bytes[relative] = committed
        if relative == cli_relative:
            cli_bytes = committed
            object_id = _stage_git(
                "rev-parse",
                "--verify",
                f"{stage_head}:{relative}",
                maximum_stdout=80,
            ).strip()
            if object_id != stage_cli_blob.encode("ascii"):
                _stage_refuse()
    if cli_bytes is None or hashlib.sha256(cli_bytes).hexdigest() != stage_cli_sha256:
        _stage_refuse()
    if _stage_git(
        "rev-parse", "--verify", "HEAD^{commit}", maximum_stdout=80
    ).strip() != current_head or set(verified_bytes) != set(_STAGE_RUNTIME_PATHS):
        _stage_refuse()
    _STAGE_VERIFIED_BYTES = verified_bytes
    _STAGE_ZERO_VERIFIED = True


if __name__ == "__main__":
    _verify_stage_zero()
    if _STAGE_VERIFIED_BYTES is None:
        _stage_refuse()
    _install_verified_runtime_imports(_STAGE_VERIFIED_BYTES)


REPOSITORY_ROOT: Final = (
    _EXPECTED_REPOSITORY_ROOT
    if _STAGE_ZERO_VERIFIED
    else Path(__file__).resolve().parents[1]
)
if not _STAGE_ZERO_VERIFIED:
    for _import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "python"):
        if str(_import_root) not in sys.path:
            sys.path.insert(0, str(_import_root))

from raos.adapters.self_hosted_wordpress_publication_operator_https_v2 import (  # noqa: E402
    OfficialSelfHostedWordPressPublicationOperatorV2Adapter,
)
from raos.adapters.self_hosted_wordpress_publication_operator_journal_v2 import (  # noqa: E402
    OwnerPrivatePublicationProposalJournalV2,
    PublicationIntentPhase,
)
from raos.adapters.self_hosted_wordpress_publication_operator_json_v2 import (  # noqa: E402
    OwnerPrivateCommittedReviewDraftBindingAdapter,
)
from raos.adapters.self_hosted_editorial_pilot_json import (  # noqa: E402
    OwnerPrivateReviewDraftGenerationLedger,
)
from raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2 import (  # noqa: E402
    DraftRevisionProposal,
    DraftRevisionRecoveryDisposition,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (  # noqa: E402
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationProposal,
    PublicationProposalReceipt,
    PublicationProposalState,
    canonical_json_bytes,
    fail_publication_operator,
    require_publish_article_id,
    require_sha256,
)
from raos.ports.self_hosted_editorial_pilot import (  # noqa: E402
    ReviewDraftRevisionDisposition,
    ReviewDraftRevisionObservation,
)


_RESULT_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_OPERATOR_CLI_RESULT_V2"
_NOT_CREATED_AT: Final = "1970-01-01T00:00:00Z"
_NOT_CREATED_EXPIRES_AT: Final = "1970-01-01T00:15:00Z"
_ERROR_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_OPERATOR_CLI_ERROR_V2"
_SANITIZED_EXCEPTIONS: Final = (OSError, ValueError, TypeError, RuntimeError)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        fail_publication_operator(PublicationOperatorFailureCode.INVALID_ARGUMENT)


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="st1704-wordpress-publication-operator-v2",
        description="Exact one-article ST-1704 publication proposal operator.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("revision-status")
    for command in ("propose-article-publication",):
        child = commands.add_parser(command)
        child.add_argument("--article-id", required=True)
    for command in (
        "recover-article-publication",
        "apply-article-publication",
        "recover-review-draft-revision",
        "apply-review-draft-revision",
        "verify-review-draft-revision",
    ):
        child = commands.add_parser(command)
        child.add_argument("--article-id", required=True)
        child.add_argument("--proposal-id", required=True)
    child = commands.add_parser("propose-review-draft-revision")
    child.add_argument("--article-id", required=True)
    return parser


def _request_token() -> str:
    return require_sha256(secrets.token_hex(32))


def _write_result(command: str, result: dict[str, object]) -> None:
    print(
        json.dumps(
            {"command": command, "result": result, "schema": _RESULT_SCHEMA},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _write_failure(code: PublicationOperatorFailureCode) -> None:
    print(
        json.dumps(
            {"code": code.value, "schema": _ERROR_SCHEMA},
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def _proposal_from_intent(
    article_id: str,
    request_token: str,
) -> PublicationProposal:
    binding = OwnerPrivateCommittedReviewDraftBindingAdapter(REPOSITORY_ROOT).load(
        article_id
    )
    return PublicationProposal.bind(binding, request_token)


def _revision_proposal_from_intent(
    article_id: str,
    request_token: str,
    expected_proposal_id: str | None = None,
) -> DraftRevisionProposal:
    ledger = OwnerPrivateReviewDraftGenerationLedger(REPOSITORY_ROOT)
    if expected_proposal_id is None:
        return DraftRevisionProposal.bind(
            ledger.pending_binding(article_id), request_token
        )
    expected_proposal_id = require_sha256(expected_proposal_id)
    candidates = tuple(
        proposal
        for binding in ledger.revision_bindings(article_id)
        if (
            proposal := DraftRevisionProposal.bind(binding, request_token)
        ).proposal_id
        == expected_proposal_id
    )
    if len(candidates) != 1:
        fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
    return candidates[0]


def _revision_observation(
    proposal: DraftRevisionProposal,
    payload: dict[str, object],
    disposition: ReviewDraftRevisionDisposition,
) -> ReviewDraftRevisionObservation:
    return ReviewDraftRevisionObservation(
        operation_sha256=proposal.binding.operation_sha256,
        response_sha256=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        draft_id=proposal.binding.draft_id,
        disposition=disposition,
    )


def _receipt_payload(receipt: PublicationProposalReceipt) -> dict[str, object]:
    value = receipt.public_payload()
    if receipt.state is PublicationProposalState.APPLIED:
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "RUN_ST1704_VERIFY_PUBLIC",
            }
        )
    elif receipt.state is PublicationProposalState.NEEDS_RECOVERY:
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "MANUAL_WORDPRESS_RECOVERY_REQUIRED",
            }
        )
    elif receipt.requires_new_proposal():
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "NEW_PROPOSAL_REQUIRED",
            }
        )
    elif receipt.state is PublicationProposalState.PROPOSED:
        value.update(
            {
                "approval_surface": "WORDPRESS_ADMIN_TOOLS_ONLY",
                "human_approval_required": True,
                "next_action": "HUMAN_APPROVAL_REQUIRED_BEFORE_APPLY",
            }
        )
    elif receipt.state is PublicationProposalState.APPROVED:
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "RUN_MATCHING_APPLY_COMMAND",
            }
        )
    elif receipt.state is PublicationProposalState.APPLYING:
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "RUN_MATCHING_APPLY_COMMAND",
            }
        )
    else:
        value.update(
            {
                "approval_surface": "NOT_APPLICABLE",
                "human_approval_required": False,
                "next_action": "RECOVER_EXACT_PROPOSAL_BEFORE_ANY_RETRY",
            }
        )
    return value


def _reconcile_receipt(
    journal: OwnerPrivatePublicationProposalJournalV2,
    proposal: PublicationProposal,
    receipt: PublicationProposalReceipt,
) -> int:
    if (
        receipt.proposal_id != proposal.proposal_id
        or receipt.operation is not proposal.operation
        or receipt.replayed is not True
    ):
        fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
    intent = journal.require_matching(proposal)
    if receipt.state is PublicationProposalState.APPLIED:
        journal.clear_matching(proposal)
        return 0
    if receipt.state in {
        PublicationProposalState.FAILED,
        PublicationProposalState.NEEDS_RECOVERY,
        PublicationProposalState.EXPIRED,
    } or (
        receipt.state
        in {
            PublicationProposalState.PROPOSED,
            PublicationProposalState.APPROVED,
        }
        and receipt.is_expired()
    ):
        journal.clear_matching(proposal)
        return 2
    if intent.phase is PublicationIntentPhase.CREATE_INTENT and receipt.state in {
        PublicationProposalState.PROPOSED,
        PublicationProposalState.APPROVED,
    }:
        journal.advance(
            proposal,
            expected=PublicationIntentPhase.CREATE_INTENT,
            target=PublicationIntentPhase.PROPOSED,
        )
    elif intent.phase is PublicationIntentPhase.APPLY_INTENT and receipt.state in {
        PublicationProposalState.PROPOSED,
        PublicationProposalState.APPROVED,
    }:
        journal.advance(
            proposal,
            expected=PublicationIntentPhase.APPLY_INTENT,
            target=PublicationIntentPhase.PROPOSED,
        )
    return (
        0
        if receipt.state
        in {PublicationProposalState.PROPOSED, PublicationProposalState.APPROVED}
        else 2
    )


def _propose(article_id: str) -> tuple[dict[str, object], int]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if intent is None:
            proposal = _proposal_from_intent(article_id, _request_token())
            journal.record_create_intent(proposal)
            try:
                receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
                    REPOSITORY_ROOT
                ).propose(proposal)
            except PublicationOperatorFailure as failure:
                if failure.code is PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED:
                    journal.clear_matching(proposal)
                raise
            if receipt.replayed:
                fail_publication_operator(
                    PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                )
            if (
                receipt.proposal_id != proposal.proposal_id
                or receipt.operation is not proposal.operation
                or receipt.state is not PublicationProposalState.PROPOSED
            ):
                fail_publication_operator(
                    PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                )
            journal.advance(
                proposal,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            return _receipt_payload(receipt), 0
        if intent.article_id != article_id:
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        proposal = _proposal_from_intent(article_id, intent.request_token)
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).recover_proposal(proposal)
        code = _reconcile_receipt(journal, proposal, receipt)
        return _receipt_payload(receipt), code


def _recover(article_id: str, proposal_id: str) -> tuple[dict[str, object], int]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if (
            intent is None
            or intent.article_id != article_id
            or intent.proposal_id != proposal_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        proposal = _proposal_from_intent(article_id, intent.request_token)
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).recover_proposal(proposal)
        code = _reconcile_receipt(journal, proposal, receipt)
        return _receipt_payload(receipt), code


def _apply(article_id: str, proposal_id: str) -> dict[str, object]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if (
            intent is None
            or intent.article_id != article_id
            or intent.proposal_id != proposal_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        proposal = _proposal_from_intent(article_id, intent.request_token)
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        if intent.phase is PublicationIntentPhase.PROPOSED:
            journal.advance(
                proposal,
                expected=PublicationIntentPhase.PROPOSED,
                target=PublicationIntentPhase.APPLY_INTENT,
            )
        elif intent.phase is not PublicationIntentPhase.APPLY_INTENT:
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        # APPLY_INTENT is an exact crash-recovery retry: the journal binding
        # above reconstructs the same proposal id, while the HTTPS adapter
        # deterministically sends the same empty JSON body and CAS headers.
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).apply(proposal.proposal_id)
        if receipt.proposal_id != proposal.proposal_id:
            fail_publication_operator(PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS)
        journal.clear_matching(proposal)
        return receipt.public_payload()


def _reconcile_revision_receipt(
    journal: OwnerPrivatePublicationProposalJournalV2,
    proposal: DraftRevisionProposal,
    receipt: PublicationProposalReceipt,
) -> tuple[dict[str, object], int]:
    if (
        receipt.proposal_id != proposal.proposal_id
        or receipt.operation is not proposal.operation
        or receipt.replayed is not True
    ):
        fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
    intent = journal.require_matching(proposal)
    ledger = OwnerPrivateReviewDraftGenerationLedger(REPOSITORY_ROOT)
    if receipt.state is PublicationProposalState.APPLIED:
        verification = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).verify_revision(proposal.proposal_id)
        if (
            verification.operation_sha256 != proposal.binding.operation_sha256
            or verification.draft_post_id != proposal.binding.draft_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
        observation = _revision_observation(
            proposal,
            verification.public_payload(),
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
        )
        ledger.recover(proposal.binding, observation)
        journal.clear_matching(proposal)
        return verification.public_payload(), 0
    if (
        intent.phase is PublicationIntentPhase.CREATE_INTENT
        and receipt.state is PublicationProposalState.FAILED
        and receipt.created_at == _NOT_CREATED_AT
        and receipt.expires_at == _NOT_CREATED_EXPIRES_AT
    ):
        # No server proposal means no apply authority existed. Preserve the
        # still-pending generation and allow a new token to repropose it.
        journal.clear_matching(proposal)
        return _receipt_payload(receipt), 2
    if (
        receipt.state is PublicationProposalState.NEEDS_RECOVERY
        or receipt.requires_new_proposal()
    ):
        recovery = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).recover_revision_state(proposal.proposal_id)
        if (
            recovery.operation_sha256 != proposal.binding.operation_sha256
            or recovery.draft_post_id != proposal.binding.draft_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
        if recovery.disposition is DraftRevisionRecoveryDisposition.SUCCESSOR:
            disposition = (
                ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
            )
            code = 0
        else:
            disposition = (
                ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR
            )
            code = 2
        ledger.recover(
            proposal.binding,
            _revision_observation(
                proposal,
                recovery.public_payload(),
                disposition,
            ),
        )
        journal.clear_matching(proposal)
        return recovery.public_payload(), code
    if intent.phase is PublicationIntentPhase.CREATE_INTENT and receipt.state in {
        PublicationProposalState.PROPOSED,
        PublicationProposalState.APPROVED,
    }:
        journal.advance(
            proposal,
            expected=PublicationIntentPhase.CREATE_INTENT,
            target=PublicationIntentPhase.PROPOSED,
        )
    elif intent.phase is PublicationIntentPhase.APPLY_INTENT and receipt.state in {
        PublicationProposalState.PROPOSED,
        PublicationProposalState.APPROVED,
    }:
        journal.advance(
            proposal,
            expected=PublicationIntentPhase.APPLY_INTENT,
            target=PublicationIntentPhase.PROPOSED,
        )
    return _receipt_payload(receipt), (
        0
        if receipt.state
        in {PublicationProposalState.PROPOSED, PublicationProposalState.APPROVED}
        else 2
    )


def _propose_revision(article_id: str) -> tuple[dict[str, object], int]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if intent is None:
            proposal = _revision_proposal_from_intent(article_id, _request_token())
            journal.record_create_intent(proposal)
            try:
                receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
                    REPOSITORY_ROOT
                ).propose_revision(proposal)
            except PublicationOperatorFailure as failure:
                if failure.code is PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED:
                    journal.clear_matching(proposal)
                raise
            if (
                receipt.replayed
                or receipt.proposal_id != proposal.proposal_id
                or receipt.operation is not proposal.operation
                or receipt.state is not PublicationProposalState.PROPOSED
            ):
                fail_publication_operator(
                    PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                )
            journal.advance(
                proposal,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            return _receipt_payload(receipt), 0
        if intent.article_id != article_id or intent.operation != "REVISE_ST1704_DRAFT":
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        proposal = _revision_proposal_from_intent(
            article_id, intent.request_token, intent.proposal_id
        )
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).recover_revision_proposal(proposal)
        return _reconcile_revision_receipt(journal, proposal, receipt)


def _recover_revision(
    article_id: str, proposal_id: str
) -> tuple[dict[str, object], int]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if (
            intent is None
            or intent.article_id != article_id
            or intent.operation != "REVISE_ST1704_DRAFT"
            or intent.proposal_id != proposal_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        proposal = _revision_proposal_from_intent(
            article_id, intent.request_token, intent.proposal_id
        )
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).recover_revision_proposal(proposal)
        return _reconcile_revision_receipt(journal, proposal, receipt)


def _apply_revision(article_id: str, proposal_id: str) -> dict[str, object]:
    journal = OwnerPrivatePublicationProposalJournalV2(REPOSITORY_ROOT)
    with journal.exclusive():
        intent = journal.load()
        if (
            intent is None
            or intent.article_id != article_id
            or intent.operation != "REVISE_ST1704_DRAFT"
            or intent.proposal_id != proposal_id
        ):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        proposal = _revision_proposal_from_intent(
            article_id, intent.request_token, intent.proposal_id
        )
        if not intent.matches(proposal):
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        ledger = OwnerPrivateReviewDraftGenerationLedger(REPOSITORY_ROOT)
        ledger.mark_attempted(proposal.binding)
        if intent.phase is PublicationIntentPhase.PROPOSED:
            journal.advance(
                proposal,
                expected=PublicationIntentPhase.PROPOSED,
                target=PublicationIntentPhase.APPLY_INTENT,
            )
        elif intent.phase is not PublicationIntentPhase.APPLY_INTENT:
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
            REPOSITORY_ROOT
        ).apply_revision(proposal.proposal_id)
        disposition = (
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED
            if receipt.replayed
            else ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED
        )
        observation = _revision_observation(
            proposal, receipt.public_payload(), disposition
        )
        if receipt.replayed:
            ledger.recover(proposal.binding, observation)
        else:
            ledger.commit(proposal.binding, observation)
        journal.clear_matching(proposal)
        return receipt.public_payload()


def _verify_revision(article_id: str, proposal_id: str) -> dict[str, object]:
    ledger = OwnerPrivateReviewDraftGenerationLedger(REPOSITORY_ROOT)
    receipt = OfficialSelfHostedWordPressPublicationOperatorV2Adapter(
        REPOSITORY_ROOT
    ).verify_revision(proposal_id)
    binding = ledger.revision_binding(article_id, receipt.operation_sha256)
    if (
        receipt.operation_sha256 != binding.operation_sha256
        or receipt.draft_post_id != binding.draft_id
    ):
        fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
    proposal = DraftRevisionProposal.bind(binding, "0" * 64)
    observation = _revision_observation(
        proposal,
        receipt.public_payload(),
        ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
    )
    ledger.verify(binding, observation)
    return receipt.public_payload()


def _run(arguments: argparse.Namespace) -> int:
    command = arguments.command
    if type(command) is not str:
        fail_publication_operator(PublicationOperatorFailureCode.INVALID_ARGUMENT)
    if command == "status":
        result = (
            OfficialSelfHostedWordPressPublicationOperatorV2Adapter(REPOSITORY_ROOT)
            .status()
            .public_payload()
        )
        _write_result(command, result)
        return 0
    if command == "revision-status":
        result = (
            OfficialSelfHostedWordPressPublicationOperatorV2Adapter(REPOSITORY_ROOT)
            .revision_status()
            .public_payload()
        )
        _write_result(command, result)
        return 0
    article_id = require_publish_article_id(getattr(arguments, "article_id", None))
    if command == "propose-article-publication":
        result, code = _propose(article_id)
    elif command == "propose-review-draft-revision":
        result, code = _propose_revision(article_id)
    else:
        proposal_id = require_sha256(getattr(arguments, "proposal_id", None))
        if command == "recover-article-publication":
            result, code = _recover(article_id, proposal_id)
        elif command == "apply-article-publication":
            result = _apply(article_id, proposal_id)
            code = 0
        elif command == "recover-review-draft-revision":
            result, code = _recover_revision(article_id, proposal_id)
        elif command == "apply-review-draft-revision":
            result = _apply_revision(article_id, proposal_id)
            code = 0
        elif command == "verify-review-draft-revision":
            result = _verify_revision(article_id, proposal_id)
            code = 0
        else:
            fail_publication_operator(
                PublicationOperatorFailureCode.OPERATION_NOT_ALLOWED
            )
    _write_result(command, result)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    if not _STAGE_ZERO_VERIFIED:
        _stage_refuse()
    try:
        return _run(_parser().parse_args(argv))
    except PublicationOperatorFailure as failure:
        _write_failure(failure.code)
        return 2
    except _SANITIZED_EXCEPTIONS:
        _write_failure(PublicationOperatorFailureCode.INTERNAL_FAILURE)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
