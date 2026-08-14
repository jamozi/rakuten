"""Adversarial contract tests for the ST-0106 standard-library scanner."""

from __future__ import annotations

import ast
import io
import os
from pathlib import Path
import random
import runpy
import shutil
import stat
import subprocess
import sys
import tokenize
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNER_SOURCE = REPOSITORY_ROOT / "scripts" / "scan_secrets.py"
PYTHON = sys.executable
GIT = shutil.which("git")

PROTECTED_GENERIC_SOURCES = (
    "changes/st-0502/DESIGN_HANDOFF_V1_ST0502_RAKUTEN_PRODUCT_SEARCH_OFFLINE_V1.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml",
    "python/raos/adapters/wordpresscom_mvp_draft_https.py",
    "python/raos/adapters/wordpresscom_oauth.py",
    "python/raos/adapters/wordpresscom_review_draft_https.py",
    "scripts/wordpresscom_review_draft.py",
    "tests/st1703/test_wordpresscom_oauth.py",
    "tests/st1703/test_wordpresscom_review_draft_cli.py",
    "tests/st1703/test_wordpresscom_review_draft_https.py",
    "tests/st1703/test_wordpresscom_review_draft_journal.py",
)


def aws_credential() -> str:
    return "AK" + "IA" + "A1B2C3D4E5F6G7H8"


def github_credential() -> str:
    return "gh" + "p_" + "A1b2" * 9


def openai_credential() -> str:
    return "s" + "k-proj-" + "aB3dE5fG7hJ9kL2mN4pQ6rS8"


def private_key_header() -> str:
    return "-----BE" + "GIN PRIVATE KEY-----"


def generic_assignment() -> str:
    return "api_" + 'key = "' + "s9Vx-3pQm-7nLk-2rTz" + '"'


def install_scanner(root: Path) -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    target = scripts / "scan_secrets.py"
    shutil.copyfile(SCANNER_SOURCE, target)
    return target


def run_scanner(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    scanner = root / "scripts" / "scan_secrets.py"
    return subprocess.run(
        [PYTHON, "-I", str(scanner), *arguments],
        cwd=root,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    assert GIT is not None
    result = subprocess.run(
        [GIT, *arguments],
        cwd=root,
        env={
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.defpath,
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result


def initialize_repository(root: Path) -> None:
    if GIT is None:
        pytest.skip("Git is required for history scanner tests")
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "ST-0106 Test")
    git(root, "config", "user.email", "st0106@example.invalid")


def commit_all(root: Path, message: str) -> None:
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", message)


def zip_bytes(entries: list[tuple[str, bytes]], *, compression: int = 0) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def assert_values_are_redacted(
    result: subprocess.CompletedProcess[str], values: list[str]
) -> None:
    output = combined_output(result)
    for value in values:
        if value in output:
            pytest.fail(
                "scanner output exposed prohibited credential bytes",
                pytrace=False,
            )


def generic_assignment_for(value: str, capture_kind: str) -> str:
    key = "pass" + "word"
    if capture_kind == "bare":
        return f"{key}={value}"
    if capture_kind == "double":
        return f'{key}="{value}"'
    if capture_kind == "single":
        return f"{key}='{value}'"
    raise AssertionError("unknown test capture kind")


def run_generic_candidate(
    root: Path,
    value: str,
    *,
    capture_kind: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    install_scanner(root)
    assignment = generic_assignment_for(value, capture_kind)
    (root / "candidate.txt").write_text(assignment + "\n", encoding="utf-8")
    return run_scanner(root, "--worktree"), assignment


def assert_generic_outcome(
    result: subprocess.CompletedProcess[str],
    *,
    assignment: str,
    value: str,
    finding: bool,
) -> None:
    assert_values_are_redacted(result, [value, assignment])
    expected_exit = 1 if finding else 0
    if result.returncode != expected_exit:
        pytest.fail("generic scanner returned an unexpected exit", pytrace=False)
    if result.stderr:
        pytest.fail("generic scanner wrote unexpected stderr", pytrace=False)
    if finding:
        if result.stdout.count("FINDING ") != 1:
            pytest.fail("generic scanner finding count changed", pytrace=False)
        if "rule=GENERIC_CREDENTIAL" not in result.stdout:
            pytest.fail("generic scanner rule changed", pytrace=False)
        if 'source="candidate.txt" line=1' not in result.stdout:
            pytest.fail("generic scanner location changed", pytrace=False)
    elif result.stdout:
        pytest.fail("safe generic candidate produced output", pytrace=False)


@pytest.fixture(scope="module")
def scanner_policy() -> dict[str, object]:
    loaded = runpy.run_path(str(SCANNER_SOURCE))
    entrypoint = loaded.get("main")
    if not callable(entrypoint) or not hasattr(entrypoint, "__globals__"):
        pytest.fail("scanner policy namespace is unavailable", pytrace=False)
    return entrypoint.__globals__


def policy_callable(
    scanner_policy: dict[str, object],
    name: str,
) -> object:
    value = scanner_policy.get(name)
    if not callable(value):
        pytest.fail("scanner policy helper is unavailable", pytrace=False)
    return value


def generic_policy_result(
    scanner_policy: dict[str, object],
    value: str,
    *,
    capture_kind: str,
) -> bool:
    classifier = policy_callable(
        scanner_policy,
        "_looks_like_real_generic_credential",
    )
    result = classifier(value.encode("utf-8"), kind=capture_kind)
    if not isinstance(result, bool):
        pytest.fail("generic classifier returned an invalid shape", pytrace=False)
    return result


def source_expression_policy_result(
    scanner_policy: dict[str, object],
    value: str,
) -> bool:
    classifier = policy_callable(scanner_policy, "_is_safe_bare_source_expression")
    result = classifier(value.encode("utf-8"))
    if not isinstance(result, bool):
        pytest.fail(
            "source-expression classifier returned an invalid shape", pytrace=False
        )
    return result


def rhs_expression() -> bytes:
    return b'receiver1.replace("alpha1", "omega")'


def rhs_payload(
    expression: bytes,
    *,
    prefix: bytes = b"",
    terminator: bytes = b"\n",
) -> bytes:
    return prefix + b"pass" + b"word=" + expression + terminator


def rhs_policy_result(
    scanner_policy: dict[str, object],
    payload: bytes,
) -> bool:
    pattern = scanner_policy.get("GENERIC_ASSIGNMENT")
    if pattern is None or not hasattr(pattern, "search"):
        pytest.fail("scanner assignment policy is unavailable", pytrace=False)
    match = pattern.search(payload)
    if match is None:
        pytest.fail("scanner assignment fixture was not recognized", pytrace=False)
    generic_value = policy_callable(scanner_policy, "_generic_value")
    rhs_classifier = policy_callable(scanner_policy, "_rhs_reconstruction_is_safe")
    kind, candidate, value_span = generic_value(match)
    if kind != "bare":
        pytest.fail("scanner assignment fixture used the wrong capture", pytrace=False)
    result = rhs_classifier(payload, value_span, candidate)
    if not isinstance(result, bool):
        pytest.fail("RHS classifier returned an invalid shape", pytrace=False)
    return result


def assert_payload_generic_finding(
    scanner_policy: dict[str, object],
    payload: bytes,
    *,
    finding: bool,
    line: int = 1,
) -> None:
    scan_bytes = policy_callable(scanner_policy, "scan_bytes")
    findings = scan_bytes(payload, "fixture")
    generic_findings = [
        item
        for item in findings
        if getattr(item, "rule_id", None) == "GENERIC_CREDENTIAL"
    ]
    expected_count = 1 if finding else 0
    if len(generic_findings) != expected_count:
        pytest.fail("RHS generic finding count changed", pytrace=False)
    if generic_findings and getattr(generic_findings[0], "line", None) != line:
        pytest.fail("RHS generic finding location changed", pytrace=False)


def histogram_candidate(counts: tuple[int, ...]) -> bytes:
    if len(counts) > 90:
        pytest.fail("entropy test histogram is invalid", pytrace=False)
    return b"".join(
        bytes((0x21 + index,)) * count for index, count in enumerate(counts)
    )


def permuted_candidates(candidate: bytes) -> tuple[bytes, ...]:
    shuffled = list(candidate)
    random.Random(106).shuffle(shuffled)
    midpoint = len(candidate) // 2
    return (
        candidate,
        candidate[::-1],
        candidate[midpoint:] + candidate[:midpoint],
        candidate[::2] + candidate[1::2],
        bytes(shuffled),
    )


def test_worktree_detects_representative_rules_without_echoing_values(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    values = [
        aws_credential(),
        github_credential(),
        openai_credential(),
        private_key_header(),
        generic_assignment(),
    ]
    (tmp_path / "credentials.txt").write_text(
        "\n".join(values) + "\n", encoding="utf-8"
    )

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, values)
    if result.returncode != 1 or result.stderr:
        pytest.fail("representative scanner outcome changed", pytrace=False)
    for rule_id in (
        "AWS_ACCESS_KEY_ID",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "PRIVATE_KEY",
        "GENERIC_CREDENTIAL",
    ):
        if f"rule={rule_id}" not in result.stdout:
            pytest.fail("representative scanner rule changed", pytrace=False)
    if 'source="credentials.txt"' not in result.stdout:
        pytest.fail("representative scanner source changed", pytrace=False)
    if "line=1" not in result.stdout or "line=5" not in result.stdout:
        pytest.fail("representative scanner location changed", pytrace=False)


def test_clean_worktree_and_missing_mode_have_deterministic_exit_codes(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    (tmp_path / "README.md").write_text("ordinary content\n", encoding="utf-8")

    clean = run_scanner(tmp_path, "--worktree")
    missing_mode = run_scanner(tmp_path)

    assert clean.returncode == 0
    assert clean.stdout == ""
    assert clean.stderr == ""
    assert missing_mode.returncode == 2
    assert "at least one of --worktree or --git-history" in missing_mode.stderr


def test_non_git_fallback_excludes_only_local_and_generated_state(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    ignored_locations = (
        ".secrets/local.txt",
        ".cache/local.txt",
        ".pytest_cache/local.txt",
        ".venv/local.txt",
        "venv/local.txt",
        "node_modules/package/local.txt",
        ".claude/settings.local.json",
        ".env.local",
    )
    value = github_credential()
    (tmp_path / ".git").mkdir()
    for relative in ignored_locations:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + "\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "api_" + "ke" + "y=replace-me-in-deployment\n", encoding="utf-8"
    )

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [value])
    if result.returncode != 0 or combined_output(result):
        pytest.fail("fallback exclusion scanner outcome changed", pytrace=False)


def test_provider_specific_assignment_retains_precedence_without_generic_duplicate(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    value = github_credential()
    assignment = "to" + f'ken = "{value}"'
    (tmp_path / "provider.txt").write_text(assignment + "\n", encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [value, assignment])
    if result.returncode != 1 or result.stderr:
        pytest.fail("provider-specific scanner outcome changed", pytrace=False)
    if result.stdout.count("FINDING ") != 1:
        pytest.fail(
            "provider-specific overlap emitted duplicate authority", pytrace=False
        )
    if "rule=GITHUB_TOKEN" not in result.stdout:
        pytest.fail("provider-specific overlap rule changed", pytrace=False)
    if "rule=GENERIC_CREDENTIAL" in result.stdout:
        pytest.fail("provider-specific overlap reached the generic rule", pytrace=False)


@pytest.mark.parametrize(
    ("capture_kind", "value"),
    [
        pytest.param("bare", "replace-me-in-deployment", id="placeholder-replace"),
        pytest.param("double", "YOUR-PASSWORD-HERE", id="placeholder-case"),
        pytest.param(
            "bare",
            "example-api-token-for-tests",
            id="placeholder-suffix-chain",
        ),
        pytest.param("bare", "not-a-real-secret", id="placeholder-not-real"),
        pytest.param("double", "REQUIRED", id="sentinel-required"),
        pytest.param(
            "bare",
            "not-a-real-access-key",
            id="v1-hyphen-no-suffix",
        ),
        pytest.param(
            "double",
            "not-a-real-api-key-17",
            id="v1-hyphen-decimal-id",
        ),
        pytest.param(
            "bare",
            "not-a-real-auth-token-ST0106-xxxx",
            id="v1-hyphen-st-id-padding",
        ),
        pytest.param(
            "double",
            "not_real_client_secret_17_xxxxx",
            id="v1-underscore-id-padding",
        ),
        pytest.param(
            "bare",
            "not_real_password_xxxx",
            id="v1-underscore-padding-only",
        ),
        pytest.param(
            "bare",
            'b"not-a-real-token-17-xxxx"',
            id="v1-bytes-literal-wrapper",
        ),
    ],
)
def test_v1_complete_placeholders_and_declaration_first_fixtures_are_safe(
    tmp_path: Path,
    capture_kind: str,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind=capture_kind,
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=False,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("NONE", id="none"),
        pytest.param("Null", id="null"),
        pytest.param("UNDEFINED", id="undefined"),
        pytest.param("required", id="required"),
    ],
)
def test_complete_case_insensitive_sentinels_are_safe_in_policy(
    scanner_policy: dict[str, object],
    value: str,
) -> None:
    if generic_policy_result(scanner_policy, value, capture_kind="double"):
        pytest.fail("complete sentinel reached credential evidence", pytrace=False)


@pytest.mark.parametrize(
    ("capture_kind", "value"),
    [
        pytest.param(
            "double",
            "client-secret-not-real-17-xxxx",
            id="client-secret-direct",
        ),
        pytest.param(
            "double",
            "access-token-not-real-1703-xxxxxxxx",
            id="access-token-direct",
        ),
        pytest.param(
            "bare",
            "client-secret-not-real-0007-xxxxx",
            id="leading-zero-decimal",
        ),
        pytest.param(
            "bare",
            'b"client-secret-not-real-17-xxxx"',
            id="complete-bytes-literal",
        ),
        pytest.param(
            "single",
            '"access-token-not-real-17-xxxx"',
            id="complete-str-literal",
        ),
    ],
)
def test_v2_exact_kind_first_fixture_family_is_safe(
    tmp_path: Path,
    capture_kind: str,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind=capture_kind,
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=False,
    )


@pytest.mark.parametrize(
    ("capture_kind", "value"),
    [
        pytest.param(
            "double",
            "secret-not-real-17-xxxx",
            id="unlisted-kind-secret",
        ),
        pytest.param(
            "double",
            "access-key-not-real-17-xxxx",
            id="unlisted-kind-access-key",
        ),
        pytest.param(
            "double",
            "api-key-not-real-17-xxxx",
            id="unlisted-kind-api-key",
        ),
        pytest.param(
            "double",
            "auth-token-not-real-17-xxxx",
            id="unlisted-kind-auth-token",
        ),
        pytest.param(
            "double",
            "credential-not-real-17-xxxx",
            id="unlisted-kind-credential",
        ),
        pytest.param(
            "double",
            "key-not-real-17-xxxx",
            id="unlisted-kind-key",
        ),
        pytest.param(
            "double",
            "password-not-real-17-xxxx",
            id="unlisted-kind-password",
        ),
        pytest.param(
            "double",
            "token-not-real-17-xxxx",
            id="unlisted-kind-token",
        ),
        pytest.param(
            "double",
            "not-a-real-access-token-17-xxxx",
            id="v1-unlisted-access-token",
        ),
        pytest.param(
            "double",
            "client_secret-not-real-17-xxxx",
            id="underscore-kind",
        ),
        pytest.param(
            "double",
            "client-secret_not-real-17-xxxx",
            id="mixed-separator",
        ),
        pytest.param(
            "double",
            "client--secret-not-real-17-xxxx",
            id="repeated-separator",
        ),
        pytest.param(
            "double",
            "CLIENT-SECRET-not-real-17-xxxx",
            id="kind-case",
        ),
        pytest.param(
            "double",
            "client-secret-NOT-REAL-17-xxxx",
            id="declaration-case",
        ),
        pytest.param(
            "double",
            "client-secret-not-a-real-17-xxxx",
            id="alternate-declaration",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-xxxx-A9",
            id="missing-id",
        ),
        pytest.param(
            "double",
            "client-secret-not-real--17-xxxx",
            id="signed-id",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-ST17-xxxx",
            id="st-prefixed-id",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-0x17-xxxx",
            id="hex-id",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-abc-xxxx-A9",
            id="non-decimal-id",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-A9b8C7",
            id="missing-padding",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17",
            id="missing-padding-exact-shape",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-xxx",
            id="short-padding",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-XXXX",
            id="upper-padding",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-xxxy",
            id="mixed-padding",
        ),
        pytest.param(
            "double",
            "prefix-client-secret-not-real-17-xxxx",
            id="prefix",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-xxxx-suffix",
            id="suffix",
        ),
        pytest.param(
            "double",
            "client-secret-not-real-17-extra-xxxx",
            id="extra-component",
        ),
        pytest.param(
            "single",
            'f"client-secret-not-real-17-xxxx-{A9}"',
            id="formatted-wrapper",
        ),
        pytest.param(
            "single",
            'b"client-secret-not-real-17-xxxx" + b"A9"',
            id="concatenated-wrapper",
        ),
        pytest.param(
            "single",
            'b"client-secret-not-real-17-xxxx" b"A9"',
            id="multiple-literal-wrapper",
        ),
        pytest.param(
            "single",
            'q"client-secret-not-real-17-xxxx-A9"',
            id="invalid-wrapper",
        ),
        pytest.param(
            "single",
            'b"client-secret-not-real-17-xxxx-\\xff"',
            id="non-ascii-decoded-wrapper",
        ),
        pytest.param(
            "single",
            '"client-secret-not-real-17-xxxx" ',
            id="trailing-space-after-wrapper",
        ),
        pytest.param(
            "single",
            '"client-secret-not-real-17-xxxx"\t',
            id="trailing-tab-after-wrapper",
        ),
        pytest.param(
            "single",
            '"client-secret-not-real-17-xxxx',
            id="incomplete-wrapper",
        ),
    ],
)
def test_v1_and_v2_fixture_near_misses_remain_detectable(
    tmp_path: Path,
    capture_kind: str,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind=capture_kind,
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=True,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("client-secret-not-real-xxxx", id="missing-id"),
        pytest.param("client-secret-not-real--xxxx", id="empty-id"),
        pytest.param("client-secret-not-real-17", id="missing-padding"),
    ],
)
def test_v2_kind_first_fixture_requires_every_component(
    scanner_policy: dict[str, object],
    value: str,
) -> None:
    classifier = policy_callable(scanner_policy, "_is_explicit_not_real_fixture")
    if classifier(value.encode("ascii")):
        pytest.fail("incomplete fixture shape was treated as safe", pytrace=False)


@pytest.mark.parametrize(
    ("capture_kind", "value"),
    [
        pytest.param("bare", "$PASSWORD", id="dollar-name"),
        pytest.param("double", "${API_KEY}", id="braced-dollar-name"),
        pytest.param("bare", "%AUTH_TOKEN%", id="windows-name"),
        pytest.param("double", "{{CLIENT_SECRET}}", id="template-name"),
        pytest.param("bare", "<API_KEY>", id="angle-placeholder"),
    ],
)
def test_complete_external_reference_wrappers_are_safe(
    tmp_path: Path,
    capture_kind: str,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind=capture_kind,
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=False,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("$API_KEY-A9b8C7", id="dollar-residual"),
        pytest.param("${API_KEY}A9b8C7", id="braced-dollar-residual"),
        pytest.param("%AUTH_TOKEN%A9b8C7", id="windows-residual"),
        pytest.param("{{CLIENT_SECRET}}-A9b8C7", id="template-residual"),
        pytest.param("<API_KEY>-A9b8C7", id="angle-residual"),
        pytest.param("<OTHER_A9b8C7>", id="angle-unapproved-identifier"),
        pytest.param("${{API_KEY}}-A9b8", id="nested-wrapper"),
        pytest.param("https://A9b8C7d6", id="url-prefix"),
    ],
)
def test_external_reference_near_misses_remain_detectable(
    tmp_path: Path,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind="double",
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=True,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("password", id="single-word"),
        pytest.param("service-secret-reference", id="hyphenated"),
        pytest.param("client_credentials", id="underscored"),
        pytest.param("access-token-name", id="compound"),
    ],
)
def test_complete_bare_symbolic_references_are_safe(
    tmp_path: Path,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind="bare",
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=False,
    )


@pytest.mark.parametrize(
    ("capture_kind", "value"),
    [
        pytest.param(
            "double",
            "service-secret-reference-A9b8",
            id="quoted-strong",
        ),
        pytest.param("bare", "service-Secret-A9b8", id="mixed-case"),
        pytest.param("bare", "service-secret-1703-Aa", id="digit-bearing"),
        pytest.param("bare", "service.secret/A9b8", id="dot-slash"),
        pytest.param("bare", "monkey-reference-A9b8", id="substring-vocabulary"),
    ],
)
def test_symbolic_reference_near_misses_remain_detectable(
    tmp_path: Path,
    capture_kind: str,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind=capture_kind,
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=True,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("credential_name", id="name"),
        pytest.param("settings.client_secret", id="attribute"),
        pytest.param('loader.fetch("credential")', id="call"),
        pytest.param('settings["client_secret"]', id="subscript"),
        pytest.param("items[1:3]", id="slice"),
        pytest.param('loader.fetch(name="secret")', id="keyword"),
        pytest.param('content.decode("utf-8")', id="legacy-content-decode"),
        pytest.param(
            "_read_password_file(target.password_file)",
            id="legacy-password-file",
        ),
        pytest.param(
            "_read_password_file(other.password_file)",
            id="general-closed-call",
        ),
    ],
)
def test_complete_bare_source_expression_roots_and_descendants_are_safe(
    scanner_policy: dict[str, object],
    value: str,
) -> None:
    if not source_expression_policy_result(scanner_policy, value):
        pytest.fail("complete source expression was not safe", pytrace=False)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param('"credential"', id="constant-root"),
        pytest.param("credential-name", id="operator"),
        pytest.param("lambda: credential_name", id="lambda"),
        pytest.param("[credential_name]", id="container"),
        pytest.param("[item for item in values]", id="comprehension"),
        pytest.param('f"{credential_name}"', id="formatted-string"),
        pytest.param("loader.fetch(*credential_names)", id="starred-call"),
        pytest.param("loader.fetch(**credential_names)", id="expanded-keyword"),
        pytest.param('loader.fetch("A9b8C7d6")', id="suspicious-string"),
        pytest.param('loader.fetch(b"A9b8C7d6")', id="suspicious-bytes"),
        pytest.param('("A9b8C7d6")()', id="constant-callable"),
        pytest.param('("A9b8C7d6").attribute', id="constant-attribute-base"),
        pytest.param('("A9b8C7d6")[0]', id="constant-subscript-base"),
        pytest.param(
            'loader.fetch(name="A9b8C7d6")',
            id="suspicious-keyword",
        ),
        pytest.param('loader.fetch(r"A9b8C7d6")', id="raw-prefixed-literal"),
        pytest.param('loader.fetch("""A9b8C7d6""")', id="triple-literal"),
        pytest.param('loader.fetch("\\x41b8C7d6")', id="escaped-raw-payload"),
        pytest.param('loader.fetch("A9b8" "C7d6")', id="implicit-concatenation"),
        pytest.param("loader.fetch(", id="malformed"),
        pytest.param("loader.fetch()-residual", id="residual"),
    ],
)
def test_source_expression_parser_rejects_every_unapproved_shape(
    scanner_policy: dict[str, object],
    value: str,
) -> None:
    if source_expression_policy_result(scanner_policy, value):
        pytest.fail("unapproved source expression was treated as safe", pytrace=False)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param('loader.fetch("A9b8C7d6")', id="string-literal"),
        pytest.param('loader.fetch(b"A9b8C7d6")', id="bytes-literal"),
        pytest.param('("A9b8C7d6")()', id="constant-callable"),
        pytest.param('("A9b8C7d6").attribute', id="constant-attribute-base"),
        pytest.param('("A9b8C7d6")[0]', id="constant-subscript-base"),
        pytest.param('loader.fetch(name="A9b8C7d6")', id="keyword-literal"),
        pytest.param('loader.fetch(r"A9b8C7d6")', id="raw-prefixed-literal"),
        pytest.param('loader.fetch("""A9b8C7d6""")', id="triple-literal"),
        pytest.param('loader.fetch("\\x41b8C7d6")', id="escaped-raw-payload"),
        pytest.param("credential_name+A9b8C7d6", id="operator-residual"),
        pytest.param('f"A9b8C7d6-{value}"', id="formatted"),
        pytest.param("[A9b8C7d6]", id="container"),
        pytest.param("lambda:A9b8C7d6", id="lambda"),
        pytest.param('loader.fetch("A9b8" "C7d6")', id="implicit-concat"),
    ],
)
def test_unapproved_source_shapes_with_strong_evidence_are_detected(
    scanner_policy: dict[str, object],
    value: str,
) -> None:
    if not generic_policy_result(scanner_policy, value, capture_kind="bare"):
        pytest.fail("strong unapproved source shape was not detected", pytrace=False)


@pytest.mark.parametrize(
    ("value", "finding"),
    [
        pytest.param("aA1-baA1", False, id="distinct-minus-one"),
        pytest.param("aA1-bCaA", True, id="distinct-exact"),
        pytest.param("aA1-bCda", True, id="distinct-plus-one"),
        pytest.param("abcdefghi0123456789", False, id="digit-length-minus-one"),
        pytest.param("abcdefghi0123456789a", True, id="digit-length-exact"),
        pytest.param("abcdefghi0123456789ab", True, id="digit-length-plus-one"),
        pytest.param(
            "aaaabbbbccccddddeeffgghh11223344",
            True,
            id="digit-entropy-exact",
        ),
        pytest.param("a" * 26 + "bcde12", False, id="digit-entropy-below"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUvw", False, id="opaque-length-minus-one"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUvwX", True, id="opaque-length-exact"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUvwXy", True, id="opaque-length-plus-one"),
        pytest.param(
            "AAAABBBB" + "ccddeeffgghhiijjkkllmmnn",
            True,
            id="opaque-entropy-exact",
        ),
        pytest.param("A" * 26 + "bcdeF_", False, id="opaque-entropy-below"),
        pytest.param("amber-cobalt-jadesx", False, id="passphrase-length-minus-one"),
        pytest.param("amber-cobalt-jadesxy", True, id="passphrase-length-exact"),
        pytest.param("amber-cobalt-jadesxyz", True, id="passphrase-length-plus-one"),
        pytest.param("abcdefghij-klmnopqrst", False, id="passphrase-words-minus-one"),
        pytest.param("abcdefgh-ijklmn-opqrst", True, id="passphrase-words-exact"),
        pytest.param(
            "abcdef-ghijkl-mnopqr-stuv",
            True,
            id="passphrase-words-plus-one",
        ),
        pytest.param(
            "aaaaaaaa-bbbbbbbb-cccdef",
            False,
            id="passphrase-entropy-below",
        ),
        pytest.param(
            "amber-cobalt-jadesxy",
            True,
            id="passphrase-entropy-above",
        ),
        pytest.param(
            "amber-secret-jadesxy",
            False,
            id="passphrase-credential-word",
        ),
    ],
)
def test_high_confidence_family_threshold_tables(
    tmp_path: Path,
    value: str,
    finding: bool,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind="double",
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=finding,
    )


@pytest.mark.parametrize(
    ("family", "below_counts", "exact_counts", "above_counts"),
    [
        pytest.param(
            "digit_bearing",
            (3, 1, 2, 2) + (1,) * 8,
            (2,) * 4 + (1,) * 8,
            (2,) * 3 + (1,) * 10,
            id="digit-bearing",
        ),
        pytest.param(
            "digit_free_opaque",
            (3, 1) + (1,) * 12,
            (2, 2) + (1,) * 12,
            (1,) * 16,
            id="digit-free-opaque",
        ),
        pytest.param(
            "lower_case_passphrase",
            (26, 7) + (5,) * 6 + (4,) * 4 + (1,),
            (25, 8) + (5,) * 6 + (4,) * 4 + (1,),
            (24, 9) + (5,) * 6 + (4,) * 4 + (1,),
            id="lower-case-passphrase",
        ),
    ],
)
def test_integer_entropy_thresholds_are_exact_and_order_invariant(
    scanner_policy: dict[str, object],
    family: str,
    below_counts: tuple[int, ...],
    exact_counts: tuple[int, ...],
    above_counts: tuple[int, ...],
) -> None:
    operands = policy_callable(scanner_policy, "_entropy_integer_operands")
    meets = policy_callable(scanner_policy, "_entropy_meets_threshold")
    candidates = tuple(
        histogram_candidate(counts)
        for counts in (below_counts, exact_counts, above_counts)
    )
    expected_relations = (-1, 0, 1)
    expected_classifications = (False, True, True)
    for candidate, relation, expected in zip(
        candidates,
        expected_relations,
        expected_classifications,
        strict=True,
    ):
        integer_operands = operands(candidate, family)
        if not isinstance(integer_operands, tuple) or len(integer_operands) != 2:
            pytest.fail("entropy operands returned an invalid shape", pytrace=False)
        left, right = integer_operands
        observed_relation = -1 if left < right else 1 if left > right else 0
        if observed_relation != relation:
            pytest.fail("entropy threshold relation changed", pytrace=False)
        for permutation in permuted_candidates(candidate):
            if meets(permutation, family) is not expected:
                pytest.fail(
                    "entropy classification depends on byte order", pytrace=False
                )


def test_entropy_configuration_and_resource_invariants_are_fatal(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meets = policy_callable(scanner_policy, "_entropy_meets_threshold")
    if meets(b"", "digit_bearing") is not False:
        pytest.fail("empty entropy candidate changed policy", pytrace=False)
    if meets(b"a", "digit_bearing") is not False:
        pytest.fail("single-bin entropy candidate changed policy", pytrace=False)
    if not isinstance(meets(b"ab" * 256, "digit_bearing"), bool):
        pytest.fail(
            "maximum entropy candidate returned an invalid shape", pytrace=False
        )
    with pytest.raises(RuntimeError):
        meets(b"a" * 513, "digit_bearing")
    with pytest.raises(RuntimeError):
        meets(b"abcdef", "unknown_family")

    thresholds = scanner_policy.get("ENTROPY_THRESHOLDS")
    if not isinstance(thresholds, dict):
        pytest.fail("entropy threshold map is unavailable", pytrace=False)
    with monkeypatch.context() as patch:
        patch.setitem(thresholds, "additional_family", (1, 1))
        with pytest.raises(RuntimeError):
            meets(b"abcdef", "digit_bearing")


@pytest.mark.parametrize(
    "configured_pair",
    [
        pytest.param([7, 2], id="non-tuple"),
        pytest.param((7,), id="wrong-arity"),
        pytest.param((True, 2), id="boolean"),
        pytest.param((7.0, 2), id="non-integer"),
        pytest.param((0, 2), id="non-positive"),
        pytest.param((14, 4), id="non-reduced"),
        pytest.param((8, 2), id="wrong-value"),
    ],
)
def test_entropy_threshold_tuple_drift_is_fatal(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    configured_pair: object,
) -> None:
    meets = policy_callable(scanner_policy, "_entropy_meets_threshold")
    thresholds = scanner_policy.get("ENTROPY_THRESHOLDS")
    if not isinstance(thresholds, dict):
        pytest.fail("entropy threshold map is unavailable", pytrace=False)
    with monkeypatch.context() as patch:
        patch.setitem(thresholds, "digit_bearing", configured_pair)
        with pytest.raises(RuntimeError):
            meets(b"abcdef", "digit_bearing")


@pytest.mark.parametrize(
    "histogram_shape",
    [
        pytest.param("short", id="short"),
        pytest.param("non-tuple", id="non-tuple"),
        pytest.param("negative", id="negative"),
        pytest.param("inconsistent", id="inconsistent"),
    ],
)
def test_entropy_histogram_invariant_drift_is_fatal(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    histogram_shape: str,
) -> None:
    operands = policy_callable(scanner_policy, "_entropy_integer_operands")
    if histogram_shape == "short":
        histogram = (0,) * 255
    elif histogram_shape == "non-tuple":
        histogram = [0] * 256
    elif histogram_shape == "negative":
        histogram = (-1,) + (0,) * 255
    else:
        histogram = (0,) * 256
    with monkeypatch.context() as patch:
        patch.setitem(scanner_policy, "_byte_histogram", lambda candidate: histogram)
        with pytest.raises(RuntimeError):
            operands(b"abcdef", "digit_bearing")


def test_entropy_resource_failure_propagates_without_fallback(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meets = policy_callable(scanner_policy, "_entropy_meets_threshold")

    def fail_power(*args: object, **kwargs: object) -> int:
        raise MemoryError

    with monkeypatch.context() as patch:
        patch.setitem(scanner_policy, "pow", fail_power)
        with pytest.raises(MemoryError):
            meets(b"abcdef", "digit_bearing")


def test_entropy_implementation_has_no_floating_or_logarithmic_path() -> None:
    source_tree = ast.parse(SCANNER_SOURCE.read_text(encoding="utf-8"))
    selected_functions = {
        node.name: node
        for node in source_tree.body
        if isinstance(node, ast.FunctionDef)
        and (
            node.name.startswith("_entropy_")
            or node.name.startswith("_has_digit_")
            or node.name == "_has_lower_case_passphrase_evidence"
        )
    }
    if "_shannon_entropy" in {
        node.name for node in source_tree.body if isinstance(node, ast.FunctionDef)
    }:
        pytest.fail("floating entropy helper remains present", pytrace=False)
    forbidden_names = {"Counter", "Decimal", "float", "fsum", "log", "math"}
    for function in selected_functions.values():
        for node in ast.walk(function):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                pytest.fail("floating entropy constant remains present", pytrace=False)
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                pytest.fail("floating entropy operation remains present", pytrace=False)


@pytest.mark.parametrize(
    "hash_seed",
    [
        pytest.param("0", id="zero"),
        pytest.param("1", id="one"),
        pytest.param("106", id="story"),
        pytest.param("random", id="randomized"),
    ],
)
def test_system_python_310_entropy_is_hash_seed_invariant(hash_seed: str) -> None:
    system_python = Path("/usr/bin/python3")
    if not system_python.is_file():
        pytest.fail("system Python is unavailable", pytrace=False)
    program = """
import runpy
import sys

if sys.version_info[:2] != (3, 10):
    raise SystemExit(2)
loaded = runpy.run_path(sys.argv[1])
policy = loaded["main"].__globals__
meets = policy["_entropy_meets_threshold"]
cases = (
    ("digit_bearing", (2,) * 4 + (1,) * 8),
    ("digit_free_opaque", (2, 2) + (1,) * 12),
    ("lower_case_passphrase", (25, 8) + (5,) * 6 + (4,) * 4 + (1,)),
)
for family, counts in cases:
    candidate = b"".join(
        bytes((33 + index,)) * count for index, count in enumerate(counts)
    )
    variants = (
        candidate,
        candidate[::-1],
        candidate[3:] + candidate[:3],
        candidate[::2] + candidate[1::2],
    )
    if not all(meets(variant, family) for variant in variants):
        raise SystemExit(3)
"""
    result = subprocess.run(
        [os.fspath(system_python), "-S", "-c", program, os.fspath(SCANNER_SOURCE)],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath, "PYTHONHASHSEED": hash_seed},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if result.returncode != 0 or result.stdout or result.stderr:
        pytest.fail("system Python entropy invariant failed", pytrace=False)


def test_high_confidence_family_exact_integer_boundaries(
    scanner_policy: dict[str, object],
) -> None:
    digit_classifier = policy_callable(scanner_policy, "_has_digit_bearing_evidence")
    opaque_classifier = policy_callable(
        scanner_policy,
        "_has_digit_free_opaque_evidence",
    )
    passphrase_classifier = policy_callable(
        scanner_policy,
        "_has_lower_case_passphrase_evidence",
    )

    digit_cases = (
        (3, 1, 2, 2) + (1,) * 8,
        (2,) * 4 + (1,) * 8,
        (2,) * 3 + (1,) * 10,
    )
    digit_alphabet = b"0abcdefghijklm"
    exact_digit_candidate = b""
    for counts, expected in zip(digit_cases, (False, True, True), strict=True):
        candidate = b"".join(
            bytes((digit_alphabet[index],)) * (count * 2)
            for index, count in enumerate(counts)
        )
        if digit_classifier(candidate) is not expected:
            pytest.fail("digit-bearing family threshold changed", pytrace=False)
        if counts == digit_cases[1]:
            exact_digit_candidate = candidate
    if digit_classifier(exact_digit_candidate.replace(b"0", b"n")):
        pytest.fail("digit-bearing family accepted a digit-free input", pytrace=False)

    opaque_cases = (
        (3, 1) + (1,) * 12,
        (2, 2) + (1,) * 12,
        (1,) * 16,
    )
    opaque_alphabet = b"ABcdefghijklmnop"
    exact_opaque_candidate = b""
    for counts, expected in zip(opaque_cases, (False, True, True), strict=True):
        candidate = b"".join(
            bytes((opaque_alphabet[index],)) * (count * 2)
            for index, count in enumerate(counts)
        )
        if opaque_classifier(candidate) is not expected:
            pytest.fail("opaque family threshold changed", pytrace=False)
        if counts == opaque_cases[1]:
            exact_opaque_candidate = candidate
    if opaque_classifier(b"0" + exact_opaque_candidate[1:]):
        pytest.fail("opaque family accepted a digit-bearing input", pytrace=False)

    passphrase_cases = (
        (26, 7) + (5,) * 6 + (4,) * 4 + (1,),
        (25, 8) + (5,) * 6 + (4,) * 4 + (1,),
        (24, 9) + (5,) * 6 + (4,) * 4 + (1,),
    )
    passphrase_alphabet = b"abcdefgh-ijkl"
    exact_passphrase_candidate = b""
    for counts, expected in zip(
        passphrase_cases,
        (False, True, True),
        strict=True,
    ):
        multiset = b"".join(
            bytes((passphrase_alphabet[index],)) * count
            for index, count in enumerate(counts)
        )
        letters = multiset.replace(b"-", b"")
        chunk = len(letters) // 5
        candidate = b"-".join(
            (
                letters[:chunk],
                letters[chunk : chunk * 2],
                letters[chunk * 2 : chunk * 3],
                letters[chunk * 3 : chunk * 4],
                letters[chunk * 4 :],
            )
        )
        if passphrase_classifier(candidate) is not expected:
            pytest.fail("passphrase family threshold changed", pytrace=False)
        if counts == passphrase_cases[1]:
            exact_passphrase_candidate = candidate

    if passphrase_classifier(exact_passphrase_candidate.replace(b"-", b"_", 1)):
        pytest.fail("passphrase family accepted a non-word separator", pytrace=False)

    forbidden = bytearray(b"AbCdEfGhIjKlMnOpQrStUvWx")
    forbidden[-1] = ord(".")
    if opaque_classifier(bytes(forbidden)):
        pytest.fail("opaque family accepted a forbidden byte", pytrace=False)


@pytest.mark.parametrize(
    "terminator",
    [
        pytest.param(b"\n", id="lf"),
        pytest.param(b"\r\n", id="crlf"),
        pytest.param(b"", id="end-of-file"),
    ],
)
def test_v3_rhs_reconstruction_suppresses_only_the_original_generic_finding(
    scanner_policy: dict[str, object],
    terminator: bytes,
) -> None:
    payload = rhs_payload(rhs_expression(), terminator=terminator)
    if not rhs_policy_result(scanner_policy, payload):
        pytest.fail("complete RHS expression was not accepted", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=False)


@pytest.mark.parametrize(
    "expression",
    [
        pytest.param(
            b'receiver1.fetch9("alpha1" )',
            id="before-closing-parenthesis",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "omega")',
            id="internal-comma",
        ),
        pytest.param(
            b"receiver1.fetch9((receiver2) )",
            id="nested-parentheses",
        ),
        pytest.param(
            b"receiver1.fetch9(receiver2[1])",
            id="nested-brackets",
        ),
        pytest.param(
            b'receiver1.fetch9("brace{mark}")',
            id="literal-braces",
        ),
    ],
)
def test_v3_rhs_accepts_each_bounded_truncation_structure(
    scanner_policy: dict[str, object],
    expression: bytes,
) -> None:
    payload = rhs_payload(expression)
    if not rhs_policy_result(scanner_policy, payload):
        pytest.fail("bounded RHS truncation structure was refused", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=False)


@pytest.mark.parametrize(
    "expression",
    [
        pytest.param(rhs_expression() + b" ", id="trailing-space"),
        pytest.param(rhs_expression() + b"\t", id="trailing-tab"),
        pytest.param(rhs_expression() + b" # comment", id="comment"),
        pytest.param(rhs_expression() + b"; receiver2", id="semicolon"),
        pytest.param(rhs_expression() + b" receiver2", id="residual-expression"),
        pytest.param(rhs_expression() + b", receiver2", id="tuple-residual"),
        pytest.param(rhs_expression() + b",", id="trailing-comma"),
        pytest.param(rhs_expression()[:-1], id="missing-delimiter"),
        pytest.param(rhs_expression() + b")", id="extra-delimiter"),
        pytest.param(rhs_expression() + b" = receiver2", id="assignment"),
        pytest.param(
            b'(receiver1 := receiver2.replace9("alpha1", "omega"))',
            id="named-expression",
        ),
        pytest.param(rhs_expression() + b"\x00", id="non-printable-byte"),
        pytest.param(rhs_expression() + b"\x80", id="non-ascii-byte"),
    ],
)
def test_v3_rhs_reconstruction_refuses_residual_or_malformed_line_shapes(
    scanner_policy: dict[str, object],
    expression: bytes,
) -> None:
    payload = rhs_payload(expression)
    if rhs_policy_result(scanner_policy, payload):
        pytest.fail("invalid RHS line shape was accepted", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


def test_v3_rhs_reconstruction_refuses_bare_carriage_return(
    scanner_policy: dict[str, object],
) -> None:
    payload = rhs_payload(rhs_expression(), terminator=b"\r")
    if rhs_policy_result(scanner_policy, payload):
        pytest.fail("bare carriage return was accepted", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


@pytest.mark.parametrize(
    "leading_byte",
    [
        pytest.param(b" ", id="space"),
        pytest.param(b"\t", id="tab"),
    ],
)
def test_v3_rhs_reconstruction_refuses_leading_whitespace_in_private_input(
    scanner_policy: dict[str, object],
    leading_byte: bytes,
) -> None:
    candidate = leading_byte + b'receiver1.replace("alpha1"'
    data = candidate + b', "omega")\n'
    classifier = policy_callable(scanner_policy, "_rhs_reconstruction_is_safe")
    if classifier(data, (0, len(candidate)), candidate):
        pytest.fail("leading RHS whitespace was accepted", pytrace=False)


def test_v3_rhs_does_not_suppress_an_independent_later_generic_assignment(
    scanner_policy: dict[str, object],
) -> None:
    payload = rhs_payload(rhs_expression() + b"; pass" + b"word=A9b8C7d6E5f4")
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


def test_v3_rhs_provider_match_retains_specific_rule_precedence(
    scanner_policy: dict[str, object],
) -> None:
    provider = github_credential().encode("ascii")
    expression = b'receiver1.replace("alpha1", "' + provider + b'")'
    payload = rhs_payload(expression)
    scan_bytes = policy_callable(scanner_policy, "scan_bytes")
    findings = scan_bytes(payload, "fixture")
    rules = {getattr(item, "rule_id", None) for item in findings}
    if "GITHUB_TOKEN" not in rules:
        pytest.fail("provider-specific RHS finding was suppressed", pytrace=False)
    if "GENERIC_CREDENTIAL" not in rules:
        pytest.fail(
            "suspicious RHS literal suppressed the generic finding", pytrace=False
        )


@pytest.mark.parametrize(
    ("provider_factory", "rule_id"),
    [
        pytest.param(aws_credential, "AWS_ACCESS_KEY_ID", id="aws"),
        pytest.param(openai_credential, "OPENAI_API_KEY", id="openai"),
        pytest.param(private_key_header, "PRIVATE_KEY", id="private-key"),
    ],
)
def test_v3_rhs_never_suppresses_any_provider_specific_rule(
    scanner_policy: dict[str, object],
    provider_factory: object,
    rule_id: str,
) -> None:
    if not callable(provider_factory):
        pytest.fail("provider fixture factory is unavailable", pytrace=False)
    provider = provider_factory().encode("ascii")
    expression = b'receiver1.replace("alpha1", "' + provider + b'")'
    scan_bytes = policy_callable(scanner_policy, "scan_bytes")
    findings = scan_bytes(rhs_payload(expression), "fixture")
    if rule_id not in {getattr(item, "rule_id", None) for item in findings}:
        pytest.fail("provider-specific RHS finding was suppressed", pytrace=False)


@pytest.mark.parametrize(
    ("offset", "accepted"),
    [
        pytest.param(-1, True, id="below"),
        pytest.param(0, True, id="exact"),
        pytest.param(1, False, id="above"),
    ],
)
def test_v3_rhs_expression_byte_limit_is_inclusive(
    scanner_policy: dict[str, object],
    offset: int,
    accepted: bool,
) -> None:
    target = 2048 + offset
    opening = b'receiver1.replace("alpha1",'
    closing = b'"omega")'
    expression = opening + b" " * (target - len(opening) - len(closing)) + closing
    if len(expression) != target:
        pytest.fail("RHS expression fixture length changed", pytrace=False)
    if rhs_policy_result(scanner_policy, rhs_payload(expression)) is not accepted:
        pytest.fail("RHS expression byte boundary changed", pytrace=False)


@pytest.mark.parametrize(
    ("offset", "accepted"),
    [
        pytest.param(-1, True, id="below"),
        pytest.param(0, True, id="exact"),
        pytest.param(1, False, id="above"),
    ],
)
def test_v3_rhs_physical_line_byte_limit_is_inclusive(
    scanner_policy: dict[str, object],
    offset: int,
    accepted: bool,
) -> None:
    target = 4096 + offset
    unpadded = rhs_payload(rhs_expression(), terminator=b"")
    payload = rhs_payload(
        rhs_expression(),
        prefix=b" " * (target - len(unpadded)),
    )
    if len(payload.rstrip(b"\n")) != target:
        pytest.fail("RHS physical-line fixture length changed", pytrace=False)
    if rhs_policy_result(scanner_policy, payload) is not accepted:
        pytest.fail("RHS physical-line byte boundary changed", pytrace=False)


def test_v3_rhs_substantive_token_limit_is_inclusive(
    scanner_policy: dict[str, object],
) -> None:
    counter = policy_callable(scanner_policy, "_rhs_literal_token_count")
    below = "+".join("item" for _ in range(128))
    exact = "receiver(" + ",".join("item" for _ in range(127)) + ")"
    above = "+".join("item" for _ in range(129))
    ignored_types = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }

    def substantive_count(source: str) -> int:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return sum(token.type not in ignored_types for token in tokens)

    if substantive_count(below) != 255 or counter(below) != 0:
        pytest.fail("RHS token boundary below case changed", pytrace=False)
    if substantive_count(exact) != 256 or counter(exact) != 0:
        pytest.fail("RHS token boundary equality case changed", pytrace=False)
    if substantive_count(above) != 257 or counter(above) is not None:
        pytest.fail("RHS token boundary above case was accepted", pytrace=False)


@pytest.mark.parametrize(
    ("name_count", "literal_count", "expected_nodes", "accepted"),
    [
        pytest.param(61, 1, 127, True, id="below"),
        pytest.param(62, 0, 128, True, id="exact"),
        pytest.param(62, 1, 129, False, id="above"),
    ],
)
def test_v3_rhs_ast_node_limit_is_inclusive(
    scanner_policy: dict[str, object],
    name_count: int,
    literal_count: int,
    expected_nodes: int,
    accepted: bool,
) -> None:
    arguments = ["item"] * name_count + ['"low"'] * literal_count
    source = "receiver(" + ",".join(arguments) + ")"
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    if len(tuple(ast.walk(expression))) != expected_nodes:
        pytest.fail("RHS AST node fixture changed", pytrace=False)
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    if closed(source, expression, rhs_literal_tokens=literal_count) is not accepted:
        pytest.fail("RHS AST node boundary changed", pytrace=False)


@pytest.mark.parametrize(
    ("attribute_count", "expected_depth", "accepted"),
    [
        pytest.param(21, 23, True, id="below"),
        pytest.param(22, 24, True, id="exact"),
        pytest.param(23, 25, False, id="above"),
    ],
)
def test_v3_rhs_ast_parent_child_depth_limit_is_inclusive(
    scanner_policy: dict[str, object],
    attribute_count: int,
    expected_depth: int,
    accepted: bool,
) -> None:
    source = "root" + ".part" * attribute_count
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    maximum_depth = 0
    stack = [(expression, 0)]
    while stack:
        node, depth = stack.pop()
        maximum_depth = max(maximum_depth, depth)
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    if maximum_depth != expected_depth:
        pytest.fail("RHS AST depth fixture changed", pytrace=False)
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    if closed(source, expression, rhs_literal_tokens=0) is not accepted:
        pytest.fail("RHS AST depth boundary changed", pytrace=False)


@pytest.mark.parametrize(
    ("literal_count", "accepted"),
    [
        pytest.param(15, True, id="below"),
        pytest.param(16, True, id="exact"),
        pytest.param(17, False, id="above"),
    ],
)
def test_v3_rhs_literal_token_limit_is_inclusive(
    scanner_policy: dict[str, object],
    literal_count: int,
    accepted: bool,
) -> None:
    source = "receiver(" + ",".join('"low"' for _ in range(literal_count)) + ")"
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    if closed(source, expression, rhs_literal_tokens=literal_count) is not accepted:
        pytest.fail("RHS literal-token boundary changed", pytrace=False)


@pytest.mark.parametrize(
    ("payload_size", "accepted"),
    [
        pytest.param(511, True, id="below"),
        pytest.param(512, True, id="exact"),
        pytest.param(513, False, id="above"),
    ],
)
def test_v3_rhs_lower_raw_literal_bound_remains_effective(
    scanner_policy: dict[str, object],
    payload_size: int,
    accepted: bool,
) -> None:
    source = 'receiver("' + "a" * payload_size + '")'
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    if closed(source, expression, rhs_literal_tokens=1) is not accepted:
        pytest.fail("RHS raw literal boundary changed", pytrace=False)


def test_v3_rhs_lower_raw_literal_bound_precedes_entropy_classification(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = 'receiver("' + "a" * 513 + '")'
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")

    def fail_if_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError

    with monkeypatch.context() as patch:
        patch.setitem(
            scanner_policy, "_has_high_confidence_generic_evidence", fail_if_called
        )
        if closed(source, expression, rhs_literal_tokens=1):
            pytest.fail("overlength raw literal was accepted", pytrace=False)


@pytest.mark.parametrize(
    ("literal_kind", "decoded_size", "accepted"),
    [
        pytest.param("bytes", 1023, True, id="bytes-below"),
        pytest.param("bytes", 1024, True, id="bytes-exact"),
        pytest.param("bytes", 1025, False, id="bytes-above"),
        pytest.param("str-ascii", 1023, True, id="str-codepoints-below"),
        pytest.param("str-ascii", 1024, True, id="str-codepoints-exact"),
        pytest.param("str-ascii", 1025, False, id="str-codepoints-above"),
        pytest.param("str-multibyte", 511, True, id="str-utf8-below"),
        pytest.param("str-multibyte", 512, True, id="str-utf8-exact"),
        pytest.param("str-multibyte", 513, False, id="str-utf8-above"),
    ],
)
def test_v3_rhs_decoded_literal_limits_are_inclusive(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    literal_kind: str,
    decoded_size: int,
    accepted: bool,
) -> None:
    if literal_kind == "bytes":
        literal = 'b"' + "a" * decoded_size + '"'
    elif literal_kind == "str-ascii":
        literal = '"' + "a" * decoded_size + '"'
    else:
        literal = '"' + "\u00e9" * decoded_size + '"'
    source = "receiver(" + literal + ")"
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    with monkeypatch.context() as patch:
        patch.setitem(scanner_policy, "MAX_GENERIC_CANDIDATE_BYTES", 4096)
        if closed(source, expression, rhs_literal_tokens=1) is not accepted:
            pytest.fail("RHS decoded literal boundary changed", pytrace=False)


@pytest.mark.parametrize(
    ("sizes", "accepted"),
    [
        pytest.param((1024, 1023), True, id="below"),
        pytest.param((1024, 1024), True, id="exact"),
        pytest.param((1024, 1024, 1), False, id="above"),
    ],
)
def test_v3_rhs_aggregate_literal_byte_limit_is_inclusive(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    sizes: tuple[int, ...],
    accepted: bool,
) -> None:
    source = "receiver(" + ",".join('b"' + "a" * size + '"' for size in sizes) + ")"
    expression = ast.parse(source, mode="eval", feature_version=(3, 10))
    closed = policy_callable(scanner_policy, "_closed_source_expression_is_safe")
    with monkeypatch.context() as patch:
        patch.setitem(scanner_policy, "MAX_GENERIC_CANDIDATE_BYTES", 4096)
        if closed(source, expression, rhs_literal_tokens=len(sizes)) is not accepted:
            pytest.fail("RHS aggregate literal boundary changed", pytrace=False)


def test_v3_rhs_parser_unconditionally_selects_python_310(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ast_module = scanner_policy.get("ast")
    if ast_module is None or not hasattr(ast_module, "parse"):
        pytest.fail("scanner AST module is unavailable", pytrace=False)
    original_parse = ast_module.parse
    feature_versions: list[object] = []

    def recording_parse(*args: object, **kwargs: object) -> ast.AST:
        feature_versions.append(kwargs.get("feature_version"))
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(ast_module, "parse", recording_parse)
    if not rhs_policy_result(scanner_policy, rhs_payload(rhs_expression())):
        pytest.fail("RHS Python-version fixture was not accepted", pytrace=False)
    if feature_versions != [(3, 10), (3, 10)]:
        pytest.fail("RHS parser feature version changed", pytrace=False)


def test_v3_rhs_expected_refusals_and_internal_failures_remain_distinct(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ast_module = scanner_policy.get("ast")
    tokenize_module = scanner_policy.get("tokenize")
    if ast_module is None or tokenize_module is None:
        pytest.fail("scanner parser modules are unavailable", pytrace=False)

    with monkeypatch.context() as patch:
        patch.setattr(
            ast_module,
            "parse",
            lambda *args, **kwargs: (_ for _ in ()).throw(MemoryError()),
        )
        if rhs_policy_result(scanner_policy, rhs_payload(rhs_expression())):
            pytest.fail(
                "candidate parser invariant failure was accepted", pytrace=False
            )

    calls = 0

    def fail_second_parse(*args: object, **kwargs: object) -> ast.AST:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SyntaxError
        raise MemoryError

    with monkeypatch.context() as patch:
        patch.setattr(ast_module, "parse", fail_second_parse)
        with pytest.raises(MemoryError):
            rhs_policy_result(scanner_policy, rhs_payload(rhs_expression()))

    with monkeypatch.context() as patch:
        patch.setattr(
            tokenize_module,
            "generate_tokens",
            lambda *args, **kwargs: (_ for _ in ()).throw(MemoryError()),
        )
        with pytest.raises(MemoryError):
            rhs_policy_result(scanner_policy, rhs_payload(rhs_expression()))


def test_v3_unexpected_rhs_failure_collapses_to_sanitized_cli_error(
    scanner_policy: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    payload = rhs_payload(rhs_expression())
    assignment = payload.rstrip(b"\n")
    (tmp_path / "candidate.txt").write_bytes(payload)

    def fail_rhs(*args: object, **kwargs: object) -> bool:
        raise MemoryError

    with monkeypatch.context() as patch:
        patch.setitem(scanner_policy, "REPOSITORY_ROOT", tmp_path)
        patch.setitem(scanner_policy, "_rhs_reconstruction_is_safe", fail_rhs)
        exit_code = policy_callable(scanner_policy, "main")(["--worktree"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    if (
        payload.decode("ascii").strip() in combined
        or assignment.decode("ascii") in combined
    ):
        pytest.fail("internal scanner error exposed candidate bytes", pytrace=False)
    if exit_code != 2 or captured.out:
        pytest.fail("internal scanner error exit changed", pytrace=False)
    if captured.err != 'ERROR code=internal-scanner-error source="."\n':
        pytest.fail("internal scanner error shape changed", pytrace=False)


@pytest.mark.parametrize(
    "input_shape",
    [
        pytest.param("mismatched-value", id="mismatched-value"),
        pytest.param("negative-start", id="negative-start"),
        pytest.param("reversed-span", id="reversed-span"),
        pytest.param("past-end", id="past-end"),
        pytest.param("non-integer-span", id="non-integer-span"),
        pytest.param("non-bytes-data", id="non-bytes-data"),
        pytest.param("non-bytes-candidate", id="non-bytes-candidate"),
    ],
)
def test_v3_rhs_input_invariant_drift_is_fatal(
    scanner_policy: dict[str, object],
    input_shape: str,
) -> None:
    payload = rhs_payload(rhs_expression())
    pattern = scanner_policy.get("GENERIC_ASSIGNMENT")
    if pattern is None or not hasattr(pattern, "search"):
        pytest.fail("scanner assignment policy is unavailable", pytrace=False)
    match = pattern.search(payload)
    if match is None:
        pytest.fail("scanner assignment fixture was not recognized", pytrace=False)
    generic_value = policy_callable(scanner_policy, "_generic_value")
    _, candidate, value_span = generic_value(match)
    data_input: object = payload
    candidate_input: object = candidate
    span_input: object = value_span
    if input_shape == "mismatched-value":
        candidate_input = b"x" * len(candidate)
    elif input_shape == "negative-start":
        span_input = (-1, value_span[1])
    elif input_shape == "reversed-span":
        span_input = (value_span[1], value_span[0])
    elif input_shape == "past-end":
        span_input = (value_span[0], len(payload) + 1)
    elif input_shape == "non-integer-span":
        span_input = (str(value_span[0]), value_span[1])
    elif input_shape == "non-bytes-data":
        data_input = payload.decode("ascii")
    else:
        candidate_input = candidate.decode("ascii")
    classifier = policy_callable(scanner_policy, "_rhs_reconstruction_is_safe")
    with pytest.raises(RuntimeError):
        classifier(data_input, span_input, candidate_input)


@pytest.mark.parametrize(
    ("expression", "accepted"),
    [
        pytest.param(
            b'receiver1.replace("alpha1", "omega").attribute',
            True,
            id="attribute-root",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "omega")[1:3]',
            True,
            id="subscript-slice",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", old="omega")',
            True,
            id="keyword",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", receiver2.fetch("omega"))',
            True,
            id="nested-call",
        ),
        pytest.param(
            b'receiver1.replace("alpha1",\t"omega")',
            True,
            id="internal-tab",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "hash#mark")',
            True,
            id="hash-inside-literal",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "brace{mark}")',
            True,
            id="brace-inside-literal",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", b"omega")',
            True,
            id="bytes-literal",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", receiver2 + receiver3)',
            False,
            id="binary-operation",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", [receiver2])',
            False,
            id="container",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", lambda: receiver2)',
            False,
            id="lambda",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", *receivers)',
            False,
            id="starred",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", **options)',
            False,
            id="expanded-keyword",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "A9b8C7d6")',
            False,
            id="suspicious-literal",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", f"omega{receiver2}")',
            False,
            id="formatted-string",
        ),
        pytest.param(
            b'receiver1.replace("alpha1", "omega" "delta")',
            False,
            id="adjacent-literals",
        ),
    ],
)
def test_v3_rhs_reuses_the_exact_closed_ast_inventory(
    scanner_policy: dict[str, object],
    expression: bytes,
    accepted: bool,
) -> None:
    payload = rhs_payload(expression)
    if rhs_policy_result(scanner_policy, payload) is not accepted:
        pytest.fail("RHS closed-AST policy changed", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=not accepted)


def test_v3_rhs_never_reconstructs_across_a_physical_line(
    scanner_policy: dict[str, object],
) -> None:
    payload = b"ordinary\n" + b"pass" + b'word=receiver1.replace("alpha1"\n, "omega")\n'
    if rhs_policy_result(scanner_policy, payload):
        pytest.fail("RHS crossed a physical line boundary", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=True, line=2)


@pytest.mark.parametrize(
    "expression",
    [
        pytest.param(
            b'receiver1.replace("alpha1", \\\n"omega")',
            id="explicit-continuation",
        ),
        pytest.param(
            b'receiver1.replace("alpha1",\n"omega")',
            id="implicit-continuation",
        ),
    ],
)
def test_v3_rhs_refuses_line_continuation(
    scanner_policy: dict[str, object],
    expression: bytes,
) -> None:
    payload = rhs_payload(expression)
    if rhs_policy_result(scanner_policy, payload):
        pytest.fail("RHS line continuation was accepted", pytrace=False)
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


def test_v3_rhs_requires_the_original_bare_candidate_to_be_syntax_invalid(
    scanner_policy: dict[str, object],
) -> None:
    payload = rhs_payload(b"receiver1+attribute9")
    if rhs_policy_result(scanner_policy, payload):
        pytest.fail(
            "syntax-valid bare candidate entered RHS reconstruction", pytrace=False
        )
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


def test_v3_rhs_never_decodes_a_quoted_code_shaped_candidate(
    scanner_policy: dict[str, object],
) -> None:
    payload = b"pass" + b"word=\"receiver1.replace('alpha1', 'omega')\"\n"
    assert_payload_generic_finding(scanner_policy, payload, finding=True)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("production-example-A9b8C7d6", id="example"),
        pytest.param("real-fake-A9b8C7d6Z5y4X3w2", id="fake"),
        pytest.param("sampled-production-Q7w6E5r4T3y2", id="sample"),
        pytest.param("fixtureBased-V9n8M7k6J5h4", id="fixture"),
        pytest.param("A9b8-getenv(PASSWORD)-C7d6", id="getenv-marker"),
        pytest.param("A9b8-os.environ-C7d6", id="environment-marker"),
        pytest.param("A9b8-$PASSWORD-C7d6", id="reference-looking"),
        pytest.param("A9b8-https://example.invalid-C7d6", id="url-looking"),
        pytest.param("A9b8-not-real-client-secret-C7d6", id="fixture-looking"),
    ],
)
def test_strong_values_containing_safe_looking_substrings_are_detected(
    tmp_path: Path,
    value: str,
) -> None:
    result, assignment = run_generic_candidate(
        tmp_path,
        value,
        capture_kind="double",
    )
    assert_generic_outcome(
        result,
        assignment=assignment,
        value=value,
        finding=True,
    )


def test_approved_protected_current_sources_have_no_findings(
    scanner_policy: dict[str, object],
) -> None:
    scan_payload = scanner_policy.get("scan_payload")
    if not callable(scan_payload):
        pytest.fail("scanner payload entrypoint is unavailable", pytrace=False)
    for relative in PROTECTED_GENERIC_SOURCES:
        try:
            data = (REPOSITORY_ROOT / relative).read_bytes()
            findings = scan_payload(data, relative, relative)
        except Exception:  # scanner failure details are intentionally value-free
            pytest.fail("protected source scan failed", pytrace=False)
        if findings:
            pytest.fail("protected source produced a finding", pytrace=False)


def test_git_worktree_scans_tracked_and_untracked_but_not_ignored(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    initialize_repository(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("clean\n", encoding="utf-8")
    commit_all(tmp_path, "initial")
    untracked_value = aws_credential()
    ignored_value = openai_credential()
    (tmp_path / "untracked.txt").write_text(untracked_value, encoding="utf-8")
    (tmp_path / "ignored.txt").write_text(ignored_value, encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [untracked_value, ignored_value])
    if result.returncode != 1 or result.stderr:
        pytest.fail("Git worktree scanner outcome changed", pytrace=False)
    if 'source="untracked.txt"' not in result.stdout:
        pytest.fail("Git worktree scanner source changed", pytrace=False)
    if "ignored.txt" in combined_output(result):
        pytest.fail("ignored worktree path entered scanner output", pytrace=False)


def test_worktree_rejects_symlink_and_special_file_without_following_it(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text(openai_credential(), encoding="utf-8")
    try:
        (tmp_path / "maintained-link").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not supported")

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [outside.read_text(encoding="utf-8")])
    if result.returncode != 2 or result.stdout:
        pytest.fail("symlink refusal outcome changed", pytrace=False)
    if "unsafe-worktree-symlink" not in result.stderr:
        pytest.fail("symlink refusal code changed", pytrace=False)


def test_worktree_rejects_unreadable_maintained_file(tmp_path: Path) -> None:
    install_scanner(tmp_path)
    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_text("ordinary content\n", encoding="utf-8")
    unreadable.chmod(0)
    try:
        result = run_scanner(tmp_path, "--worktree")
    finally:
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert result.returncode == 2
    assert "unreadable-worktree-input" in result.stderr


def test_nested_zip_finding_reports_member_chain_without_value(tmp_path: Path) -> None:
    install_scanner(tmp_path)
    value = github_credential()
    inner = zip_bytes([("credentials.txt", value.encode("ascii"))])
    outer = zip_bytes([("payload/inner.zip", inner)])
    (tmp_path / "bundle.zip").write_bytes(outer)

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [value])
    if result.returncode != 1 or result.stderr:
        pytest.fail("nested provider archive outcome changed", pytrace=False)
    if "bundle.zip!payload/inner.zip!credentials.txt" not in result.stdout:
        pytest.fail("nested provider archive source changed", pytrace=False)
    if "rule=GITHUB_TOKEN" not in result.stdout:
        pytest.fail("nested provider archive rule changed", pytrace=False)


@pytest.mark.parametrize(
    "nested",
    [
        pytest.param(False, id="archive"),
        pytest.param(True, id="nested-archive"),
    ],
)
def test_generic_policy_is_identical_in_archive_and_nested_archive(
    tmp_path: Path,
    nested: bool,
) -> None:
    install_scanner(tmp_path)
    safe_value = "client-secret-not-real-17-xxxx"
    unsafe_value = "client-secret-not-real-17-xxxx-A9b8"
    safe_assignment = generic_assignment_for(safe_value, "double")
    unsafe_assignment = generic_assignment_for(unsafe_value, "double")
    rhs_value = rhs_expression().decode("ascii")
    rhs_assignment = rhs_payload(rhs_expression()).decode("ascii").rstrip("\n")
    payload = (
        safe_assignment + "\n" + rhs_assignment + "\n" + unsafe_assignment + "\n"
    ).encode("ascii")
    member = zip_bytes([("candidate.txt", payload)])
    if nested:
        member = zip_bytes([("inner.zip", member)])
    (tmp_path / "bundle.zip").write_bytes(member)

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(
        result,
        [
            safe_value,
            unsafe_value,
            rhs_value,
            safe_assignment,
            unsafe_assignment,
            rhs_assignment,
        ],
    )
    if result.returncode != 1 or result.stderr:
        pytest.fail("archive generic scanner outcome changed", pytrace=False)
    if result.stdout.count("FINDING ") != 1:
        pytest.fail("archive generic finding count changed", pytrace=False)
    if "rule=GENERIC_CREDENTIAL" not in result.stdout:
        pytest.fail("archive generic rule changed", pytrace=False)
    if 'candidate.txt" line=3' not in result.stdout:
        pytest.fail("archive generic location changed", pytrace=False)


def test_malformed_archive_error_never_exposes_generic_candidate(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    value = "A9b8C7d6E5f4G3h2"
    assignment = generic_assignment_for(value, "double")
    (tmp_path / "broken.zip").write_bytes(b"PK\x03\x04" + assignment.encode("ascii"))

    result = run_scanner(tmp_path, "--worktree")

    assert_values_are_redacted(result, [value, assignment])
    if result.returncode != 2 or result.stdout:
        pytest.fail("malformed archive scanner outcome changed", pytrace=False)
    if "invalid-archive" not in result.stderr:
        pytest.fail("malformed archive error code changed", pytrace=False)


@pytest.mark.parametrize(
    ("entry_name", "expected_code"),
    [
        ("../escape.txt", "unsafe-archive-member"),
        ("/absolute.txt", "unsafe-archive-member"),
        ("folder\\escape.txt", "unsafe-archive-member"),
    ],
)
def test_zip_traversal_is_an_operational_error(
    tmp_path: Path, entry_name: str, expected_code: str
) -> None:
    install_scanner(tmp_path)
    (tmp_path / "unsafe.zip").write_bytes(zip_bytes([(entry_name, b"clean")]))

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 2
    assert expected_code in result.stderr


def test_zip_symlink_member_is_rejected(tmp_path: Path) -> None:
    install_scanner(tmp_path)
    output = io.BytesIO()
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, b"target")
    (tmp_path / "symlink.zip").write_bytes(output.getvalue())

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 2
    assert "unsafe-archive-member-type" in result.stderr


def test_encrypted_zip_metadata_is_rejected(tmp_path: Path) -> None:
    install_scanner(tmp_path)
    archive = bytearray(zip_bytes([("member.txt", b"ordinary")]))
    local_header = archive.index(b"PK" + b"\x03\x04")
    central_header = archive.index(b"PK" + b"\x01\x02")
    archive[local_header + 6 : local_header + 8] = (
        int.from_bytes(archive[local_header + 6 : local_header + 8], "little") | 1
    ).to_bytes(2, "little")
    archive[central_header + 8 : central_header + 10] = (
        int.from_bytes(archive[central_header + 8 : central_header + 10], "little") | 1
    ).to_bytes(2, "little")
    (tmp_path / "encrypted.zip").write_bytes(archive)

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 2
    assert "encrypted-archive-member" in result.stderr


def test_zip_bomb_ratio_and_excessive_nesting_are_rejected(tmp_path: Path) -> None:
    install_scanner(tmp_path)
    compressed = zip_bytes(
        [("expanded.txt", b"Z" * (2 * 1024 * 1024))],
        compression=zipfile.ZIP_DEFLATED,
    )
    (tmp_path / "ratio.zip").write_bytes(compressed)

    ratio_result = run_scanner(tmp_path, "--worktree")

    assert ratio_result.returncode == 2
    assert "archive-compression-ratio" in ratio_result.stderr

    (tmp_path / "ratio.zip").unlink()
    nested = zip_bytes([("end.txt", b"clean")])
    for depth in range(6):
        nested = zip_bytes([(f"level-{depth}.zip", nested)])
    (tmp_path / "deep.zip").write_bytes(nested)

    depth_result = run_scanner(tmp_path, "--worktree")

    assert depth_result.returncode == 2
    assert "archive-nesting-too-deep" in depth_result.stderr


def test_history_mode_requires_a_valid_non_shallow_repository(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)

    absent = run_scanner(tmp_path, "--git-history")

    assert absent.returncode == 2
    assert "git-history-requires-repository" in absent.stderr


def test_history_scans_deleted_blob_from_detached_head_object_database(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    initialize_repository(tmp_path)
    value = openai_credential()
    retired = tmp_path / "retired.txt"
    retired.write_text(value + "\n", encoding="utf-8")
    commit_all(tmp_path, "credential exists")
    retired.unlink()
    commit_all(tmp_path, "credential deleted")
    git(tmp_path, "checkout", "--quiet", "--detach", "HEAD")
    for branch in git(
        tmp_path, "for-each-ref", "--format=%(refname:short)", "refs/heads"
    ).stdout.splitlines():
        git(tmp_path, "branch", "-D", branch)

    result = run_scanner(tmp_path, "--git-history")

    assert_values_are_redacted(result, [value])
    if result.returncode != 1 or result.stderr:
        pytest.fail("provider history scanner outcome changed", pytrace=False)
    if "rule=OPENAI_API_KEY" not in result.stdout:
        pytest.fail("provider history scanner rule changed", pytrace=False)
    if 'source="git-blob:' not in result.stdout:
        pytest.fail("provider history scanner source changed", pytrace=False)
    if "retired.txt" in result.stdout:
        pytest.fail("provider history path entered scanner output", pytrace=False)


def test_generic_policy_scans_deleted_history_blob_without_value(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    initialize_repository(tmp_path)
    safe_value = "access-token-not-real-1703-xxxx"
    unsafe_value = "access-token-not-real-1703-xxxx-A9b8"
    safe_assignment = generic_assignment_for(safe_value, "double")
    unsafe_assignment = generic_assignment_for(unsafe_value, "double")
    rhs_value = rhs_expression().decode("ascii")
    rhs_assignment = rhs_payload(rhs_expression()).decode("ascii").rstrip("\n")
    retired = tmp_path / "retired-generic.txt"
    retired.write_text(
        safe_assignment + "\n" + rhs_assignment + "\n" + unsafe_assignment + "\n",
        encoding="utf-8",
    )
    commit_all(tmp_path, "generic credential exists")
    retired.unlink()
    commit_all(tmp_path, "generic credential deleted")
    git(tmp_path, "checkout", "--quiet", "--detach", "HEAD")
    for branch in git(
        tmp_path, "for-each-ref", "--format=%(refname:short)", "refs/heads"
    ).stdout.splitlines():
        git(tmp_path, "branch", "-D", branch)

    result = run_scanner(tmp_path, "--git-history")

    assert_values_are_redacted(
        result,
        [
            safe_value,
            unsafe_value,
            rhs_value,
            safe_assignment,
            unsafe_assignment,
            rhs_assignment,
        ],
    )
    if result.returncode != 1 or result.stderr:
        pytest.fail("history generic scanner outcome changed", pytrace=False)
    if result.stdout.count("FINDING ") != 1:
        pytest.fail("history generic finding count changed", pytrace=False)
    if "rule=GENERIC_CREDENTIAL" not in result.stdout:
        pytest.fail("history generic rule changed", pytrace=False)
    if 'source="git-blob:' not in result.stdout or "line=3" not in result.stdout:
        pytest.fail("history generic location changed", pytrace=False)


def test_combined_mode_returns_operational_error_when_history_is_unavailable(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    value = aws_credential()
    (tmp_path / "finding.txt").write_text(value, encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree", "--git-history")

    assert_values_are_redacted(result, [value])
    if result.returncode != 2 or result.stdout:
        pytest.fail("combined scanner refusal outcome changed", pytrace=False)
    if "git-history-requires-repository" not in result.stderr:
        pytest.fail("combined scanner refusal code changed", pytrace=False)


def test_shallow_repository_history_is_rejected(tmp_path: Path) -> None:
    if GIT is None:
        pytest.skip("Git is required for history scanner tests")
    origin = tmp_path / "origin"
    origin.mkdir()
    initialize_repository(origin)
    (origin / "tracked.txt").write_text("clean\n", encoding="utf-8")
    commit_all(origin, "initial")
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "--quiet", "--depth=1", origin.as_uri(), str(clone))
    install_scanner(clone)

    result = run_scanner(clone, "--git-history")

    assert result.returncode == 2
    assert "shallow-git-history" in result.stderr
