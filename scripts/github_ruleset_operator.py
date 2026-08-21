#!/usr/bin/env python3
"""Operate one hash-bound GitHub ruleset for the fixed RAOS repository."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import secrets
import socket
import ssl
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0107/contracts/github-ruleset-operator.v1.json")
POLICY_PATH: Final = Path("changes/st-0107/ruleset-policy.v1.json")
GOVERNANCE_SOURCE_PATH: Final = Path("changes/st-0107/contracts/pr-governance.v1.yaml")
CODEOWNERS_PATH: Final = Path(".github/CODEOWNERS")
PRIVATE_ROOT_PATH: Final = Path(".secrets/github-ruleset-runs")
TOKEN_FILE_ENVIRONMENT: Final = "RAOS_GITHUB_RULESET_TOKEN_FILE"
API_ORIGIN: Final = "https://api.github.com"
API_HOST: Final = "api.github.com"
API_VERSION: Final = "2026-03-10"
OWNER: Final = "jamozi"
REPOSITORY: Final = "rakuten"
REPOSITORY_FULL_NAME: Final = f"{OWNER}/{REPOSITORY}"
DEFAULT_BRANCH: Final = "main"
RULESET_NAME: Final = "RAOS protected default branch"
REPOSITORY_API_PATH: Final = f"/repos/{REPOSITORY_FULL_NAME}"
RULESETS_API_PATH: Final = f"{REPOSITORY_API_PATH}/rulesets"
RULESET_INVENTORY_PATH: Final = (
    f"{RULESETS_API_PATH}?includes_parents=true&per_page=100"
)
MAIN_COMMIT_PATH: Final = f"{REPOSITORY_API_PATH}/commits/{DEFAULT_BRANCH}"
CHECK_RUNS_PATH: Final = f"{MAIN_COMMIT_PATH}/check-runs?filter=latest&per_page=100"
EFFECTIVE_RULES_PATH: Final = f"{REPOSITORY_API_PATH}/rules/branches/{DEFAULT_BRANCH}"
REQUIRED_CONTEXTS: Final = (
    "Static",
    "Unit",
    "Contracts",
    "Database",
    "Storage",
    "Secrets",
    "Validate status overlay",
)
EXPECTED_RULE_TYPES: Final = (
    "deletion",
    "non_fast_forward",
    "required_linear_history",
    "pull_request",
    "required_status_checks",
)
MAX_TOKEN_BYTES: Final = 8 * 1024
MAX_RECORD_BYTES: Final = 4 * 1024 * 1024
MAX_HTTP_BYTES: Final = 4 * 1024 * 1024
REQUIRED_OWNER_BINDING_STATUS: Final = "LIVE_VERIFIED"
RUN_ID_PATTERN: Final = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{24}$")
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN: Final = re.compile(r"^[0-9a-f]{40,64}$")
RULESET_DETAIL_PATTERN: Final = re.compile(
    rf"^{re.escape(RULESETS_API_PATH)}/([1-9][0-9]*)$"
)


class OperatorError(RuntimeError):
    """A closed, non-sensitive ruleset-operator failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AmbiguousMutationError(OperatorError):
    """A mutation may have reached GitHub and must never be retried."""


class JsonTransport(Protocol):
    """Minimal injectable transport used by the operator and recorded tests."""

    def request(self, method: str, path: str, body: object | None = None) -> object:
        """Return one decoded JSON response or raise OperatorError."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OperatorError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _decode_json(content: bytes, code: str) -> object:
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperatorError(code) from error


def _canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise OperatorError("JSON_VALUE_INVALID") from error


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _mapping(value: object, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise OperatorError(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if type(value) is not list:
        raise OperatorError(code)
    return value


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_no_symlink_ancestors(path: Path, code: str) -> None:
    current = _absolute(path)
    while True:
        try:
            metadata = current.lstat()
        except OSError as error:
            raise OperatorError(code) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise OperatorError(code)
        if current.parent == current:
            return
        current = current.parent


def _read_regular_file(
    path: Path,
    maximum_bytes: int,
    code: str,
    *,
    private_mode: int | None = None,
) -> bytes:
    absolute = _absolute(path)
    _require_no_symlink_ancestors(absolute, code)
    try:
        before = absolute.lstat()
    except OSError as error:
        raise OperatorError(code) from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size < 1
        or before.st_size > maximum_bytes
    ):
        raise OperatorError(code)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not no_follow:
        raise OperatorError(code)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            absolute,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise OperatorError(code)
        if private_mode is not None and (
            opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != private_mode
        ):
            raise OperatorError(code)
        content = bytearray()
        while len(content) <= maximum_bytes:
            chunk = os.read(descriptor, min(65_536, maximum_bytes + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > maximum_bytes or len(content) != opened.st_size:
            raise OperatorError(code)
        return bytes(content)
    except OperatorError:
        raise
    except OSError as error:
        raise OperatorError(code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_token_from_environment(environment: Mapping[str, str] | None = None) -> str:
    """Read the sole credential input without exposing its value."""

    values = os.environ if environment is None else environment
    raw_path = values.get(TOKEN_FILE_ENVIRONMENT)
    if not raw_path or "\x00" in raw_path:
        raise OperatorError("TOKEN_FILE_REQUIRED")
    path = _absolute(Path(raw_path))
    content = _read_regular_file(
        path, MAX_TOKEN_BYTES, "TOKEN_FILE_INVALID", private_mode=0o600
    )
    if content.endswith(b"\n"):
        content = content[:-1]
    if not 20 <= len(content) <= 512 or any(
        byte < 0x21 or byte > 0x7E for byte in content
    ):
        raise OperatorError("TOKEN_FILE_INVALID")
    try:
        return content.decode("ascii")
    except UnicodeDecodeError as error:
        raise OperatorError("TOKEN_FILE_INVALID") from error


def load_operator_contract(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    document = _mapping(
        _decode_json(
            _read_regular_file(root / CONTRACT_PATH, 128 * 1024, "CONTRACT_INVALID"),
            "CONTRACT_INVALID",
        ),
        "CONTRACT_INVALID",
    )
    if set(document) != {
        "document",
        "github",
        "local",
        "required_status_contexts",
        "ruleset_invariants",
        "mutation_boundary",
    }:
        raise OperatorError("CONTRACT_INVALID")
    if document["document"] != {
        "id": "RAOS-GITHUB-RULESET-OPERATOR-001",
        "version": "1.0.0",
        "story_id": "ST-0107",
        "status": "LOCAL_OPERATOR_CONTRACT",
    }:
        raise OperatorError("CONTRACT_INVALID")
    if document["github"] != {
        "api_origin": API_ORIGIN,
        "api_version": API_VERSION,
        "owner": OWNER,
        "repository": REPOSITORY,
        "default_branch": DEFAULT_BRANCH,
        "ruleset_name": RULESET_NAME,
    }:
        raise OperatorError("CONTRACT_INVALID")
    if document["local"] != {
        "policy_path": POLICY_PATH.as_posix(),
        "governance_source_path": GOVERNANCE_SOURCE_PATH.as_posix(),
        "generated_codeowners_path": CODEOWNERS_PATH.as_posix(),
        "private_root": PRIVATE_ROOT_PATH.as_posix(),
        "token_file_environment": TOKEN_FILE_ENVIRONMENT,
        "required_owner_binding_status": REQUIRED_OWNER_BINDING_STATUS,
        "private_directory_mode": "0700",
        "private_record_mode": "0600",
        "maximum_token_bytes": MAX_TOKEN_BYTES,
        "maximum_record_bytes": MAX_RECORD_BYTES,
    }:
        raise OperatorError("CONTRACT_INVALID")
    if document["required_status_contexts"] != list(REQUIRED_CONTEXTS):
        raise OperatorError("CONTRACT_INVALID")
    if document["ruleset_invariants"] != {
        "target": "branch",
        "include": ["~DEFAULT_BRANCH"],
        "exclude": [],
        "enforcement": "active",
        "bypass_actors": [],
        "required_rule_types": list(EXPECTED_RULE_TYPES),
        "required_approving_review_count": 0,
        "require_code_owner_review": True,
        "require_last_push_approval": False,
        "strict_required_status_checks_policy": True,
        "expected_check_source": "github-actions",
    }:
        raise OperatorError("CONTRACT_INVALID")
    if document["mutation_boundary"] != {
        "live_mutation_activation": ("DISABLED_PENDING_REVIEWED_ACTIVATION_CONTRACT"),
        "allowed_methods": ["POST", "PUT"],
        "delete_allowed": False,
        "automatic_retry_allowed": False,
        "ambiguous_result_action": "GET_RECONCILIATION_ONLY",
        "new_ruleset_rollback": "PUT_ENFORCEMENT_DISABLED",
        "existing_ruleset_rollback": "PUT_PRIOR_PAYLOAD",
    }:
        raise OperatorError("CONTRACT_INVALID")
    return document


def _require_live_mutation_enabled(contract: Mapping[str, Any]) -> None:
    boundary = _mapping(contract.get("mutation_boundary"), "CONTRACT_INVALID")
    if (
        boundary.get("live_mutation_activation")
        != "ENABLED_BY_REVIEWED_ACTIVATION_CONTRACT"
    ):
        raise OperatorError("LIVE_MUTATION_DISABLED")


def _require_verified_owner_bindings(root: Path = REPOSITORY_ROOT) -> None:
    """Reject placeholder or unrecognized owner bindings before mutation."""

    source = _read_regular_file(
        root / GOVERNANCE_SOURCE_PATH, 512 * 1024, "OWNER_BINDINGS_UNVERIFIED"
    )
    codeowners = _read_regular_file(
        root / CODEOWNERS_PATH, 512 * 1024, "OWNER_BINDINGS_UNVERIFIED"
    )
    block_match = re.search(
        rb"(?m)^owner_bindings:\r?\n(?P<body>(?:^[ \t]+[^\r\n]*\r?\n)+)",
        source,
    )
    if block_match is None:
        raise OperatorError("OWNER_BINDINGS_UNVERIFIED")
    statuses = re.findall(
        rb"(?m)^  status: ([A-Z][A-Z0-9_]*)\r?$", block_match.group("body")
    )
    if statuses != [REQUIRED_OWNER_BINDING_STATUS.encode("ascii")]:
        raise OperatorError("OWNER_BINDINGS_UNVERIFIED")
    if b"UNVERIFIED_PLACEHOLDERS" in codeowners or b"@raos/" in codeowners:
        raise OperatorError("OWNER_BINDINGS_UNVERIFIED")


def load_policy(root: Path = REPOSITORY_ROOT) -> tuple[dict[str, Any], str]:
    content = _read_regular_file(root / POLICY_PATH, 512 * 1024, "POLICY_INVALID")
    document = _mapping(_decode_json(content, "POLICY_INVALID"), "POLICY_INVALID")
    metadata = _mapping(document.get("document"), "POLICY_INVALID")
    if (
        metadata.get("story_id") != "ST-0107"
        or metadata.get("artifact_kind") != "DESIRED_STATE_NOT_API_PAYLOAD"
        or metadata.get("github_api_version") != API_VERSION
    ):
        raise OperatorError("POLICY_INVALID")
    ruleset = _mapping(document.get("ruleset"), "POLICY_INVALID")
    pull_request = _mapping(ruleset.get("pull_request"), "POLICY_INVALID")
    expected_scalars = {
        "name": RULESET_NAME,
        "target": "branch",
        "include": ["~DEFAULT_BRANCH"],
        "exclude": [],
        "desired_enforcement": "active",
        "local_application_status": "NOT_EXECUTED",
        "bypass_actors": [],
        "prohibit_deletion": True,
        "prohibit_force_push": True,
        "require_linear_history": True,
        "strict_required_status_checks_policy": True,
        "do_not_enforce_on_create": False,
    }
    if any(ruleset.get(key) != value for key, value in expected_scalars.items()):
        raise OperatorError("POLICY_INVALID")
    if pull_request != {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": True,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
    }:
        raise OperatorError("POLICY_INVALID")
    checks = _list(ruleset.get("required_status_checks"), "POLICY_INVALID")
    if [row.get("context") for row in checks if type(row) is dict] != list(
        REQUIRED_CONTEXTS
    ) or len(checks) != len(REQUIRED_CONTEXTS):
        raise OperatorError("POLICY_INVALID")
    for row_value in checks:
        row = _mapping(row_value, "POLICY_INVALID")
        if (
            set(row)
            != {
                "context",
                "expected_source",
                "integration_id_binding",
            }
            or row.get("expected_source") != "github-actions"
            or row.get("integration_id_binding") != "REQUIRED_AT_ACTIVATION"
        ):
            raise OperatorError("POLICY_INVALID")
    return document, hashlib.sha256(content).hexdigest()


def _git(root: Path, arguments: Sequence[str]) -> bytes:
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                os.fspath(root),
                *arguments,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError("POLICY_COMMIT_INVALID") from error
    if result.returncode != 0 or len(result.stdout) > MAX_RECORD_BYTES:
        raise OperatorError("POLICY_COMMIT_INVALID")
    return result.stdout


def current_policy_commit(root: Path = REPOSITORY_ROOT) -> str:
    commit = (
        _git(root, ["rev-parse", "--verify", "HEAD^{commit}"])
        .decode("ascii", "strict")
        .strip()
    )
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise OperatorError("POLICY_COMMIT_INVALID")
    tracked = _git(root, ["show", f"{commit}:{POLICY_PATH.as_posix()}"])
    current = _read_regular_file(root / POLICY_PATH, 512 * 1024, "POLICY_INVALID")
    if tracked != current:
        raise OperatorError("POLICY_DRIFT")
    return commit


def _validate_route(method: str, path: str) -> None:
    if method == "GET" and path in {
        REPOSITORY_API_PATH,
        RULESET_INVENTORY_PATH,
        MAIN_COMMIT_PATH,
        CHECK_RUNS_PATH,
        EFFECTIVE_RULES_PATH,
    }:
        return
    match = RULESET_DETAIL_PATTERN.fullmatch(path)
    if method == "GET" and match is not None:
        return
    if method == "POST" and path == RULESETS_API_PATH:
        return
    if method == "PUT" and match is not None:
        return
    raise OperatorError("REQUEST_ROUTE_FORBIDDEN")


class FixedGitHubTransport:
    """Single-attempt HTTPS transport with a compile-time host boundary."""

    def __init__(self, token: str) -> None:
        if type(token) is not str or not token:
            raise OperatorError("TOKEN_FILE_INVALID")
        self._token = token

    def request(self, method: str, path: str, body: object | None = None) -> object:
        _validate_route(method, path)
        if method in {"POST", "PUT"} and body is None:
            raise OperatorError("REQUEST_BODY_REQUIRED")
        encoded = None if body is None else _canonical_json(body)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "raos-github-ruleset-operator/1",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPSConnection(
            API_HOST,
            443,
            timeout=20,
            context=ssl.create_default_context(),
        )
        mutation = method in {"POST", "PUT"}
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            content = response.read(MAX_HTTP_BYTES + 1)
        except (OSError, socket.timeout, http.client.HTTPException) as error:
            if mutation:
                raise AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS") from error
            raise OperatorError("GITHUB_TRANSPORT_FAILED") from error
        finally:
            connection.close()
        if len(content) > MAX_HTTP_BYTES:
            if mutation:
                raise AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS")
            raise OperatorError("GITHUB_RESPONSE_INVALID")
        if not 200 <= response.status < 300:
            if mutation and (response.status in {408, 429} or response.status >= 500):
                raise AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS")
            raise OperatorError("GITHUB_API_REJECTED")
        if not content:
            return {}
        try:
            return _decode_json(content, "GITHUB_RESPONSE_INVALID")
        except OperatorError as error:
            if mutation:
                raise AmbiguousMutationError("MUTATION_RESULT_AMBIGUOUS") from error
            raise


def _request(
    transport: JsonTransport,
    method: str,
    path: str,
    body: object | None = None,
) -> object:
    _validate_route(method, path)
    return transport.request(method, path, body)


def _repository_state(transport: JsonTransport) -> tuple[int, str]:
    repository = _mapping(
        _request(transport, "GET", REPOSITORY_API_PATH), "REPOSITORY_IDENTITY_INVALID"
    )
    repository_id = repository.get("id")
    if (
        type(repository_id) is not int
        or repository_id <= 0
        or repository.get("full_name") != REPOSITORY_FULL_NAME
        or repository.get("default_branch") != DEFAULT_BRANCH
    ):
        raise OperatorError("REPOSITORY_IDENTITY_INVALID")
    commit = _mapping(
        _request(transport, "GET", MAIN_COMMIT_PATH), "MAIN_COMMIT_INVALID"
    ).get("sha")
    if type(commit) is not str or COMMIT_PATTERN.fullmatch(commit) is None:
        raise OperatorError("MAIN_COMMIT_INVALID")
    return repository_id, commit


def _ruleset_inventory(transport: JsonTransport) -> list[dict[str, Any]]:
    rows = _list(
        _request(transport, "GET", RULESET_INVENTORY_PATH),
        "RULESET_INVENTORY_INVALID",
    )
    if len(rows) >= 100:
        raise OperatorError("RULESET_INVENTORY_INCOMPLETE")
    result: list[dict[str, Any]] = []
    for value in rows:
        row = _mapping(value, "RULESET_INVENTORY_INVALID")
        ruleset_id = row.get("id")
        if type(ruleset_id) is not int or ruleset_id <= 0:
            raise OperatorError("RULESET_INVENTORY_INVALID")
        result.append(
            {
                "id": ruleset_id,
                "name": row.get("name"),
                "source": row.get("source"),
                "source_type": row.get("source_type"),
                "enforcement": row.get("enforcement"),
            }
        )
    return sorted(result, key=lambda row: row["id"])


def _target_ruleset(inventory: Sequence[Mapping[str, Any]]) -> int | None:
    matches = [row for row in inventory if row.get("name") == RULESET_NAME]
    if len(matches) > 1:
        raise OperatorError("RULESET_DUPLICATE")
    if not matches:
        return None
    match = matches[0]
    if (
        match.get("source_type") != "Repository"
        or match.get("source") != REPOSITORY_FULL_NAME
    ):
        raise OperatorError("RULESET_SOURCE_INVALID")
    ruleset_id = match.get("id")
    if type(ruleset_id) is not int or ruleset_id <= 0:
        raise OperatorError("RULESET_INVENTORY_INVALID")
    return ruleset_id


def _ruleset_detail(transport: JsonTransport, ruleset_id: int) -> dict[str, Any]:
    return _mapping(
        _request(transport, "GET", f"{RULESETS_API_PATH}/{ruleset_id}"),
        "RULESET_DETAIL_INVALID",
    )


def _extract_bypass_actors(value: object) -> list[dict[str, Any]]:
    rows = _list(value, "RULESET_DETAIL_INVALID")
    result: list[dict[str, Any]] = []
    for value_row in rows:
        row = _mapping(value_row, "RULESET_DETAIL_INVALID")
        if not {"actor_id", "actor_type", "bypass_mode"} <= set(row):
            raise OperatorError("RULESET_DETAIL_INVALID")
        result.append(
            {
                "actor_id": row["actor_id"],
                "actor_type": row["actor_type"],
                "bypass_mode": row["bypass_mode"],
            }
        )
    return result


def _extract_rules(value: object) -> list[dict[str, Any]]:
    rows = _list(value, "RULESET_DETAIL_INVALID")
    result: list[dict[str, Any]] = []
    for value_row in rows:
        row = _mapping(value_row, "RULESET_DETAIL_INVALID")
        rule_type = row.get("type")
        if type(rule_type) is not str or not rule_type:
            raise OperatorError("RULESET_DETAIL_INVALID")
        rule: dict[str, Any] = {"type": rule_type}
        if "parameters" in row:
            rule["parameters"] = _mapping(row["parameters"], "RULESET_DETAIL_INVALID")
        result.append(rule)
    return result


def _extract_update_payload(detail: Mapping[str, Any]) -> dict[str, Any]:
    if "bypass_actors" not in detail:
        raise OperatorError("RULESET_BYPASS_VISIBILITY_REQUIRED")
    payload = {
        "name": detail.get("name"),
        "target": detail.get("target"),
        "enforcement": detail.get("enforcement"),
        "bypass_actors": _extract_bypass_actors(detail.get("bypass_actors")),
        "conditions": _mapping(detail.get("conditions"), "RULESET_DETAIL_INVALID"),
        "rules": _extract_rules(detail.get("rules")),
    }
    if (
        payload["name"] != RULESET_NAME
        or payload["target"] != "branch"
        or type(payload["enforcement"]) is not str
    ):
        raise OperatorError("RULESET_DETAIL_INVALID")
    return payload


def _normalized_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    copied = _mapping(
        _decode_json(_canonical_json(payload), "RULESET_DETAIL_INVALID"),
        "RULESET_DETAIL_INVALID",
    )
    rules = _list(copied.get("rules"), "RULESET_DETAIL_INVALID")
    for value in rules:
        rule = _mapping(value, "RULESET_DETAIL_INVALID")
        parameters = rule.get("parameters")
        if rule.get("type") == "required_status_checks" and type(parameters) is dict:
            checks = _list(
                parameters.get("required_status_checks"), "RULESET_DETAIL_INVALID"
            )
            checks.sort(key=lambda row: str(row.get("context")))
        if rule.get("type") == "pull_request" and type(parameters) is dict:
            methods = parameters.get("allowed_merge_methods")
            if type(methods) is list:
                methods.sort()
    rules.sort(key=lambda row: str(row.get("type")))
    conditions = _mapping(copied.get("conditions"), "RULESET_DETAIL_INVALID")
    for value in conditions.values():
        if type(value) is dict:
            for key in ("include", "exclude"):
                if type(value.get(key)) is list:
                    value[key].sort()
    bypass = _list(copied.get("bypass_actors"), "RULESET_DETAIL_INVALID")
    bypass.sort(
        key=lambda row: (
            str(row.get("actor_type")),
            str(row.get("actor_id")),
            str(row.get("bypass_mode")),
        )
    )
    return copied


def _check_bindings(transport: JsonTransport) -> dict[str, int]:
    response = _mapping(
        _request(transport, "GET", CHECK_RUNS_PATH), "CHECK_BINDINGS_INVALID"
    )
    rows = _list(response.get("check_runs"), "CHECK_BINDINGS_INVALID")
    total_count = response.get("total_count")
    if type(total_count) is not int or total_count != len(rows) or len(rows) >= 100:
        raise OperatorError("CHECK_BINDINGS_INCOMPLETE")
    bindings: dict[str, int] = {}
    for context in REQUIRED_CONTEXTS:
        matching = [
            row for row in rows if type(row) is dict and row.get("name") == context
        ]
        if not matching:
            raise OperatorError("CHECK_BINDING_MISSING")
        identifiers: set[int] = set()
        for row in matching:
            app = _mapping(row.get("app"), "CHECK_BINDINGS_INVALID")
            app_id = app.get("id")
            if (
                app.get("slug") != "github-actions"
                or type(app_id) is not int
                or app_id <= 0
            ):
                raise OperatorError("CHECK_BINDING_SOURCE_INVALID")
            identifiers.add(app_id)
        if len(identifiers) != 1:
            raise OperatorError("CHECK_BINDING_SOURCE_INVALID")
        bindings[context] = identifiers.pop()
    return bindings


def _effective_rules(transport: JsonTransport) -> list[dict[str, Any]]:
    return _extract_rules(_request(transport, "GET", EFFECTIVE_RULES_PATH))


def _build_desired_payload(
    policy: Mapping[str, Any], bindings: Mapping[str, int]
) -> dict[str, Any]:
    ruleset = _mapping(policy.get("ruleset"), "POLICY_INVALID")
    pull_request = _mapping(ruleset.get("pull_request"), "POLICY_INVALID")
    checks = [
        {"context": context, "integration_id": bindings[context]}
        for context in REQUIRED_CONTEXTS
    ]
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": list(ruleset["include"]),
                "exclude": list(ruleset["exclude"]),
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {"type": "pull_request", "parameters": dict(pull_request)},
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": checks,
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                },
            },
        ],
    }


def _validate_desired_payload(payload: Mapping[str, Any]) -> None:
    normalized = _normalized_payload(payload)
    if (
        normalized.get("name") != RULESET_NAME
        or normalized.get("target") != "branch"
        or normalized.get("enforcement") != "active"
        or normalized.get("bypass_actors") != []
        or normalized.get("conditions")
        != {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}
    ):
        raise OperatorError("READBACK_MISMATCH")
    rules = {
        row.get("type"): row
        for row in _list(normalized.get("rules"), "READBACK_MISMATCH")
        if type(row) is dict
    }
    if set(rules) != set(EXPECTED_RULE_TYPES) or len(rules) != len(EXPECTED_RULE_TYPES):
        raise OperatorError("READBACK_MISMATCH")
    pull = _mapping(rules["pull_request"].get("parameters"), "READBACK_MISMATCH")
    if pull != {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": True,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
    }:
        raise OperatorError("READBACK_MISMATCH")
    status = _mapping(
        rules["required_status_checks"].get("parameters"), "READBACK_MISMATCH"
    )
    checks = _list(status.get("required_status_checks"), "READBACK_MISMATCH")
    if (
        status.get("strict_required_status_checks_policy") is not True
        or status.get("do_not_enforce_on_create") is not False
        or {row.get("context") for row in checks if type(row) is dict}
        != set(REQUIRED_CONTEXTS)
        or len(checks) != len(REQUIRED_CONTEXTS)
        or any(
            type(row.get("integration_id")) is not int or row["integration_id"] <= 0
            for row in checks
            if type(row) is dict
        )
    ):
        raise OperatorError("READBACK_MISMATCH")


def _validate_effective_rules(
    effective: Sequence[Mapping[str, Any]], desired: Mapping[str, Any]
) -> None:
    desired_rules = {
        row["type"]: row for row in _list(desired.get("rules"), "READBACK_MISMATCH")
    }
    available: dict[str, list[Mapping[str, Any]]] = {}
    for row in effective:
        rule_type = row.get("type")
        if type(rule_type) is str:
            available.setdefault(rule_type, []).append(row)
    for rule_type in EXPECTED_RULE_TYPES:
        candidates = available.get(rule_type, [])
        if not candidates:
            raise OperatorError("EFFECTIVE_RULES_MISMATCH")
        expected = _normalized_payload(
            {
                "name": RULESET_NAME,
                "target": "branch",
                "enforcement": "active",
                "bypass_actors": [],
                "conditions": {"ref_name": {"include": [], "exclude": []}},
                "rules": [desired_rules[rule_type]],
            }
        )["rules"][0]
        if not any(
            _normalized_payload(
                {
                    "name": RULESET_NAME,
                    "target": "branch",
                    "enforcement": "active",
                    "bypass_actors": [],
                    "conditions": {"ref_name": {"include": [], "exclude": []}},
                    "rules": [candidate],
                }
            )["rules"][0]
            == expected
            for candidate in candidates
        ):
            raise OperatorError("EFFECTIVE_RULES_MISMATCH")


def _live_snapshot(transport: JsonTransport) -> dict[str, Any]:
    repository_id, main_sha = _repository_state(transport)
    inventory = _ruleset_inventory(transport)
    ruleset_id = _target_ruleset(inventory)
    detail = None
    if ruleset_id is not None:
        detail = _extract_update_payload(_ruleset_detail(transport, ruleset_id))
        if detail["bypass_actors"]:
            raise OperatorError("LIVE_BYPASS_PRESENT")
    return {
        "repository_id": repository_id,
        "repository": REPOSITORY_FULL_NAME,
        "default_branch": DEFAULT_BRANCH,
        "main_sha": main_sha,
        "ruleset_inventory": inventory,
        "target_ruleset_id": ruleset_id,
        "target_ruleset": detail,
        "effective_rules": _effective_rules(transport),
        "check_bindings": _check_bindings(transport),
    }


def status_operation(
    transport: JsonTransport, *, root: Path = REPOSITORY_ROOT
) -> dict[str, Any]:
    contract = load_operator_contract(root)
    live = _live_snapshot(transport)
    return {
        "schema": "RAOS_GITHUB_RULESET_STATUS_V1",
        "status": "READY_FOR_PLAN",
        "operator_contract": contract["document"]["id"],
        "repository": live["repository"],
        "default_branch": live["default_branch"],
        "main_sha": live["main_sha"],
        "ruleset": "ABSENT" if live["target_ruleset_id"] is None else "PRESENT",
        "ruleset_id": live["target_ruleset_id"],
        "required_check_bindings": live["check_bindings"],
    }


def _ensure_private_directory(path: Path) -> Path:
    absolute = _absolute(path)
    try:
        if not absolute.exists():
            os.mkdir(absolute, mode=0o700)
    except OSError as error:
        raise OperatorError("PRIVATE_DIRECTORY_INVALID") from error
    _require_no_symlink_ancestors(absolute, "PRIVATE_DIRECTORY_INVALID")
    metadata = absolute.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise OperatorError("PRIVATE_DIRECTORY_INVALID")
    return absolute


def prepare_private_root(
    root: Path = REPOSITORY_ROOT, private_root: Path | None = None
) -> Path:
    selected = root / PRIVATE_ROOT_PATH if private_root is None else private_root
    selected = _absolute(selected)
    if private_root is None:
        _ensure_private_directory(root / ".secrets")
    return _ensure_private_directory(selected)


def _new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(12)}"


def _create_run_directory(
    private_root: Path, run_id: str | None = None
) -> tuple[str, Path]:
    identifier = _new_run_id() if run_id is None else run_id
    if RUN_ID_PATTERN.fullmatch(identifier) is None:
        raise OperatorError("RUN_ID_INVALID")
    root = _ensure_private_directory(private_root)
    target = root / identifier
    try:
        os.mkdir(target, mode=0o700)
    except OSError as error:
        raise OperatorError("RUN_DIRECTORY_INVALID") from error
    return identifier, _ensure_private_directory(target)


def _existing_run_directory(private_root: Path, run_id: str) -> Path:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise OperatorError("RUN_ID_INVALID")
    root = _ensure_private_directory(private_root)
    return _ensure_private_directory(root / run_id)


def _write_private_record(path: Path, value: object) -> None:
    content = _canonical_json(value)
    if len(content) > MAX_RECORD_BYTES:
        raise OperatorError("PRIVATE_RECORD_INVALID")
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not no_follow:
        raise OperatorError("PRIVATE_RECORD_INVALID")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | no_follow,
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except FileExistsError as error:
        raise OperatorError("OPERATION_ALREADY_RECORDED") from error
    except OSError as error:
        raise OperatorError("PRIVATE_RECORD_INVALID") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise OperatorError("PRIVATE_RECORD_INVALID")


def _read_private_record(path: Path) -> dict[str, Any]:
    absolute = _absolute(path)
    content = _read_regular_file(
        absolute,
        MAX_RECORD_BYTES,
        "PRIVATE_RECORD_INVALID",
        private_mode=0o600,
    )
    return _mapping(
        _decode_json(content, "PRIVATE_RECORD_INVALID"), "PRIVATE_RECORD_INVALID"
    )


def create_plan(
    transport: JsonTransport,
    *,
    root: Path = REPOSITORY_ROOT,
    private_root: Path | None = None,
    policy_commit: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    load_operator_contract(root)
    policy, policy_sha256 = load_policy(root)
    commit = current_policy_commit(root) if policy_commit is None else policy_commit
    if type(commit) is not str or COMMIT_PATTERN.fullmatch(commit) is None:
        raise OperatorError("POLICY_COMMIT_INVALID")
    live = _live_snapshot(transport)
    desired = _build_desired_payload(policy, live["check_bindings"])
    _validate_desired_payload(desired)
    existing_id = live["target_ruleset_id"]
    if existing_id is None:
        rollback = {
            "kind": "disable_created",
            "payload": {**desired, "enforcement": "disabled"},
        }
        operation = {"method": "POST", "path": RULESETS_API_PATH}
    else:
        rollback = {"kind": "restore_existing", "payload": live["target_ruleset"]}
        operation = {
            "method": "PUT",
            "path": f"{RULESETS_API_PATH}/{existing_id}",
        }
    selected_root = prepare_private_root(root, private_root)
    identifier, run_directory = _create_run_directory(selected_root, run_id)
    plan = {
        "schema": "RAOS_GITHUB_RULESET_PLAN_V1",
        "run_id": identifier,
        "created_at": datetime.now(UTC).isoformat(),
        "repository": REPOSITORY_FULL_NAME,
        "api_origin": API_ORIGIN,
        "api_version": API_VERSION,
        "policy": {
            "path": POLICY_PATH.as_posix(),
            "sha256": policy_sha256,
            "commit": commit,
        },
        "main": {"branch": DEFAULT_BRANCH, "sha": live["main_sha"]},
        "live_before": live,
        "live_before_sha256": _sha256(live),
        "desired": desired,
        "desired_sha256": _sha256(_normalized_payload(desired)),
        "rollback": rollback,
        "operation": operation,
    }
    plan_sha256 = _sha256(plan)
    record = {
        "document": {
            "id": "RAOS-GITHUB-RULESET-PLAN-001",
            "version": "1.0.0",
        },
        "plan": plan,
        "plan_sha256": plan_sha256,
    }
    _write_private_record(run_directory / "plan.v1.json", record)
    return {
        "schema": "RAOS_GITHUB_RULESET_PLAN_RESULT_V1",
        "status": "PLANNED",
        "run_id": identifier,
        "plan_sha256": plan_sha256,
        "operation": operation["method"],
    }


def _load_bound_plan(
    private_root: Path, run_id: str, requested_sha256: str | None = None
) -> tuple[Path, dict[str, Any], str]:
    run_directory = _existing_run_directory(private_root, run_id)
    record = _read_private_record(run_directory / "plan.v1.json")
    plan = _mapping(record.get("plan"), "PLAN_RECORD_INVALID")
    stored_sha256 = record.get("plan_sha256")
    if (
        record.get("document")
        != {"id": "RAOS-GITHUB-RULESET-PLAN-001", "version": "1.0.0"}
        or plan.get("schema") != "RAOS_GITHUB_RULESET_PLAN_V1"
        or plan.get("run_id") != run_id
        or stored_sha256 != _sha256(plan)
        or type(stored_sha256) is not str
        or SHA256_PATTERN.fullmatch(stored_sha256) is None
        or plan.get("repository") != REPOSITORY_FULL_NAME
        or plan.get("api_origin") != API_ORIGIN
        or plan.get("api_version") != API_VERSION
    ):
        raise OperatorError("PLAN_RECORD_INVALID")
    if requested_sha256 is not None and requested_sha256 != stored_sha256:
        raise OperatorError("PLAN_HASH_MISMATCH")
    return run_directory, plan, stored_sha256


def _verify_policy_binding(root: Path, plan: Mapping[str, Any]) -> None:
    _, policy_sha256 = load_policy(root)
    policy = _mapping(plan.get("policy"), "PLAN_RECORD_INVALID")
    if (
        policy.get("path") != POLICY_PATH.as_posix()
        or policy.get("sha256") != policy_sha256
        or policy.get("commit") != current_policy_commit(root)
    ):
        raise OperatorError("POLICY_DRIFT")


def _reconcile(
    transport: JsonTransport,
    expected_payload: Mapping[str, Any],
    expected_id: int | None,
    *,
    require_effective: bool,
) -> int:
    inventory = _ruleset_inventory(transport)
    ruleset_id = _target_ruleset(inventory)
    if ruleset_id is None or (expected_id is not None and ruleset_id != expected_id):
        raise OperatorError("READBACK_MISMATCH")
    actual = _extract_update_payload(_ruleset_detail(transport, ruleset_id))
    if _normalized_payload(actual) != _normalized_payload(expected_payload):
        raise OperatorError("READBACK_MISMATCH")
    if expected_payload.get("enforcement") == "active":
        _validate_desired_payload(actual)
    if require_effective:
        _validate_effective_rules(_effective_rules(transport), expected_payload)
    return ruleset_id


def _mutation_with_reconciliation(
    transport: JsonTransport,
    *,
    method: str,
    path: str,
    payload: Mapping[str, Any],
    expected_id: int | None,
    require_effective: bool,
    outcome_path: Path,
    outcome_schema: str,
) -> dict[str, Any]:
    ambiguous = False
    try:
        _request(transport, method, path, payload)
    except AmbiguousMutationError:
        ambiguous = True
    except OperatorError as error:
        outcome = {
            "schema": outcome_schema,
            "status": "FAILED",
            "reason_code": error.code,
            "mutation_attempted": True,
            "mutation_retried": False,
        }
        _write_private_record(outcome_path, outcome)
        raise
    try:
        ruleset_id = _reconcile(
            transport,
            payload,
            expected_id,
            require_effective=require_effective,
        )
    except OperatorError as error:
        outcome = {
            "schema": outcome_schema,
            "status": "AMBIGUOUS" if ambiguous else "READBACK_MISMATCH",
            "reason_code": error.code,
            "mutation_attempted": True,
            "mutation_retried": False,
            "get_reconciliation_attempted": True,
        }
        _write_private_record(outcome_path, outcome)
        raise OperatorError("MUTATION_RESULT_UNRESOLVED" if ambiguous else error.code)
    outcome = {
        "schema": outcome_schema,
        "status": "RECONCILED" if ambiguous else "APPLIED",
        "ruleset_id": ruleset_id,
        "mutation_attempted": True,
        "mutation_retried": False,
        "get_reconciliation_attempted": True,
    }
    _write_private_record(outcome_path, outcome)
    return outcome


def apply_plan(
    transport: JsonTransport,
    *,
    run_id: str,
    plan_sha256: str,
    root: Path = REPOSITORY_ROOT,
    private_root: Path | None = None,
) -> dict[str, Any]:
    contract = load_operator_contract(root)
    _require_live_mutation_enabled(contract)
    selected_root = prepare_private_root(root, private_root)
    run_directory, plan, _ = _load_bound_plan(selected_root, run_id, plan_sha256)
    _verify_policy_binding(root, plan)
    _require_verified_owner_bindings(root)
    live = _live_snapshot(transport)
    if _sha256(live) != plan.get("live_before_sha256"):
        raise OperatorError("LIVE_BEFORE_DRIFT")
    desired = _mapping(plan.get("desired"), "PLAN_RECORD_INVALID")
    if _sha256(_normalized_payload(desired)) != plan.get("desired_sha256"):
        raise OperatorError("PLAN_RECORD_INVALID")
    operation = _mapping(plan.get("operation"), "PLAN_RECORD_INVALID")
    method = operation.get("method")
    path = operation.get("path")
    if type(method) is not str or type(path) is not str:
        raise OperatorError("PLAN_RECORD_INVALID")
    expected_id = live["target_ruleset_id"] if method == "PUT" else None
    outcome = _mutation_with_reconciliation(
        transport,
        method=method,
        path=path,
        payload=desired,
        expected_id=expected_id,
        require_effective=True,
        outcome_path=run_directory / "apply.v1.json",
        outcome_schema="RAOS_GITHUB_RULESET_APPLY_V1",
    )
    return {
        "schema": "RAOS_GITHUB_RULESET_APPLY_RESULT_V1",
        "status": outcome["status"],
        "run_id": run_id,
        "ruleset_id": outcome["ruleset_id"],
    }


def rollback_plan(
    transport: JsonTransport,
    *,
    run_id: str,
    root: Path = REPOSITORY_ROOT,
    private_root: Path | None = None,
) -> dict[str, Any]:
    contract = load_operator_contract(root)
    _require_live_mutation_enabled(contract)
    selected_root = prepare_private_root(root, private_root)
    run_directory, plan, _ = _load_bound_plan(selected_root, run_id)
    apply_record = _read_private_record(run_directory / "apply.v1.json")
    if (
        apply_record.get("schema") != "RAOS_GITHUB_RULESET_APPLY_V1"
        or apply_record.get("status") not in {"APPLIED", "RECONCILED"}
        or type(apply_record.get("ruleset_id")) is not int
    ):
        raise OperatorError("ROLLBACK_NOT_ELIGIBLE")
    ruleset_id = apply_record["ruleset_id"]
    desired = _mapping(plan.get("desired"), "PLAN_RECORD_INVALID")
    _reconcile(
        transport,
        desired,
        ruleset_id,
        require_effective=desired.get("enforcement") == "active",
    )
    rollback = _mapping(plan.get("rollback"), "PLAN_RECORD_INVALID")
    payload = _mapping(rollback.get("payload"), "PLAN_RECORD_INVALID")
    if rollback.get("kind") not in {"restore_existing", "disable_created"}:
        raise OperatorError("PLAN_RECORD_INVALID")
    outcome = _mutation_with_reconciliation(
        transport,
        method="PUT",
        path=f"{RULESETS_API_PATH}/{ruleset_id}",
        payload=payload,
        expected_id=ruleset_id,
        require_effective=False,
        outcome_path=run_directory / "rollback.v1.json",
        outcome_schema="RAOS_GITHUB_RULESET_ROLLBACK_V1",
    )
    return {
        "schema": "RAOS_GITHUB_RULESET_ROLLBACK_RESULT_V1",
        "status": outcome["status"],
        "run_id": run_id,
        "ruleset_id": ruleset_id,
        "rollback_kind": rollback["kind"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", allow_abbrev=False)
    commands.add_parser("plan", allow_abbrev=False)
    apply = commands.add_parser("apply", allow_abbrev=False)
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--plan-sha256", required=True)
    rollback = commands.add_parser("rollback", allow_abbrev=False)
    rollback.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.command in {"apply", "rollback"}:
            _require_live_mutation_enabled(load_operator_contract())
        token = read_token_from_environment()
        transport = FixedGitHubTransport(token)
        if arguments.command == "status":
            result = status_operation(transport)
        elif arguments.command == "plan":
            result = create_plan(transport)
        elif arguments.command == "apply":
            result = apply_plan(
                transport,
                run_id=arguments.run_id,
                plan_sha256=arguments.plan_sha256,
            )
        elif arguments.command == "rollback":
            result = rollback_plan(transport, run_id=arguments.run_id)
        else:
            raise OperatorError("COMMAND_INVALID")
    except OperatorError as error:
        print(
            json.dumps(
                {
                    "schema": "RAOS_GITHUB_RULESET_ERROR_V1",
                    "status": "ERROR",
                    "reason_code": error.code,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
