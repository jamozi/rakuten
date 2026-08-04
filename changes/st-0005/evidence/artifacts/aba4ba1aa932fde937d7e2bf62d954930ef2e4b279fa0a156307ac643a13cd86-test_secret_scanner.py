"""Adversarial contract tests for the ST-0106 standard-library scanner."""

from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNER_SOURCE = REPOSITORY_ROOT / "scripts" / "scan_secrets.py"
PYTHON = sys.executable
GIT = shutil.which("git")


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
        assert value not in output


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

    assert result.returncode == 1, result.stderr
    for rule_id in (
        "AWS_ACCESS_KEY_ID",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "PRIVATE_KEY",
        "GENERIC_CREDENTIAL",
    ):
        assert f"rule={rule_id}" in result.stdout
    assert 'source="credentials.txt"' in result.stdout
    assert "line=1" in result.stdout
    assert "line=5" in result.stdout
    assert result.stderr == ""
    assert_values_are_redacted(result, values)


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

    assert result.returncode == 0, combined_output(result)
    assert_values_are_redacted(result, [value])


def test_generic_rule_does_not_treat_source_expressions_as_credentials(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    source_expressions = (
        "to" + 'ken = raw_token.replace("~1", "/")',
        "pass" + "word = os.environ.get(" + '"PASSWORD")',
        "sec" + "ret = match.group(" + '"secret")',
    )
    (tmp_path / "expressions.py").write_text(
        "\n".join(source_expressions) + "\n", encoding="utf-8"
    )

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 0, combined_output(result)


@pytest.mark.parametrize(
    "assignment",
    [
        "pass" + "word" + "=production-example-A9b8C7d6",
        "to" + "ken" + "=real-fake-A9b8C7d6Z5y4X3w2",
        "client_" + "sec" + "ret" + "=sampled-production-Q7w6E5r4T3y2",
        "api_" + "ke" + "y" + "=fixtureBased-V9n8M7k6J5h4",
    ],
)
def test_generic_rule_does_not_suppress_real_values_containing_placeholder_words(
    tmp_path: Path,
    assignment: str,
) -> None:
    install_scanner(tmp_path)
    (tmp_path / "credential.txt").write_text(assignment + "\n", encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 1, result.stderr
    assert "rule=GENERIC_CREDENTIAL" in result.stdout
    assert 'source="credential.txt"' in result.stdout
    assert assignment not in combined_output(result)


@pytest.mark.parametrize(
    "assignment",
    [
        "api_" + "ke" + "y" + "=replace-me-in-deployment",
        "pass" + "word" + "=your-password-here",
        "auth_" + "to" + "ken" + "=example-api-token-for-tests",
        "client_" + "sec" + "ret" + "=not-a-real-secret",
    ],
)
def test_generic_rule_suppresses_only_complete_placeholder_values(
    tmp_path: Path,
    assignment: str,
) -> None:
    install_scanner(tmp_path)
    (tmp_path / "template.env").write_text(assignment + "\n", encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree")

    assert result.returncode == 0, combined_output(result)


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

    assert result.returncode == 1, result.stderr
    assert 'source="untracked.txt"' in result.stdout
    assert "ignored.txt" not in combined_output(result)
    assert_values_are_redacted(result, [untracked_value, ignored_value])


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

    assert result.returncode == 2
    assert "unsafe-worktree-symlink" in result.stderr
    assert_values_are_redacted(result, [outside.read_text(encoding="utf-8")])


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

    assert result.returncode == 1, result.stderr
    assert "bundle.zip!payload/inner.zip!credentials.txt" in result.stdout
    assert "rule=GITHUB_TOKEN" in result.stdout
    assert_values_are_redacted(result, [value])


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

    assert result.returncode == 1, result.stderr
    assert "rule=OPENAI_API_KEY" in result.stdout
    assert 'source="git-blob:' in result.stdout
    assert "retired.txt" not in result.stdout
    assert_values_are_redacted(result, [value])


def test_combined_mode_returns_operational_error_when_history_is_unavailable(
    tmp_path: Path,
) -> None:
    install_scanner(tmp_path)
    value = aws_credential()
    (tmp_path / "finding.txt").write_text(value, encoding="utf-8")

    result = run_scanner(tmp_path, "--worktree", "--git-history")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "git-history-requires-repository" in result.stderr
    assert_values_are_redacted(result, [value])


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
