"""Offline command-boundary tests for self-hosted owner-local WordPress."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from raos.adapters.self_hosted_wordpress_credentials import (
    CREDENTIAL_RELATIVE_PATH,
    OwnerPrivateSelfHostedWordPressCredentialStore,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
SLICE_MAKEFILE = (
    REPOSITORY_ROOT / "changes/st-1703/self-hosted-minimum-start-v1/Makefile"
)
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "self_hosted_wordpress_cli_for_test",
    SCRIPTS_ROOT / "self_hosted_wordpress.py",
)
assert SPEC is not None and SPEC.loader is not None
cli = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cli
SPEC.loader.exec_module(cli)


def _authorize_imported_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_runtime_authorized", True)
    monkeypatch.setattr(
        cli,
        "_verified_runtime_bytes",
        {cli._CONTENT_PACKET_RUNTIME_PATH: b"synthetic-bound-packet"},
    )


def test_doctor_is_metadata_only_and_has_zero_network_or_external_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden_read(store: object) -> None:
        del store
        raise AssertionError("doctor read credential values")

    def forbidden_transport(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("doctor constructed a live transport")

    monkeypatch.setattr(
        cli.OwnerPrivateSelfHostedWordPressCredentialStore,
        "read",
        forbidden_read,
    )
    monkeypatch.setattr(
        cli,
        "OfficialSelfHostedWordPressDraftAdapter",
        forbidden_transport,
    )
    monkeypatch.setattr(
        cli,
        "load_first_article_candidate",
        lambda *args, **kwargs: object(),
    )
    result = cli._doctor(tmp_path)
    assert result == {
        "blockers": [
            "AFFILIATE_SLOTS_PENDING",
            "WORDPRESS_CREDENTIAL_INSTALL_REQUIRED",
            "FINAL_THEME_ASSETS_MISSING",
        ],
        "content_packet": "VALID",
        "credential_metadata": "MISSING",
        "credential_value_reads": 0,
        "external_writes": 0,
        "network_requests": 0,
        "publication_actions": 0,
        "status": "LOCAL_PREPARATION_REQUIRED",
        "theme_source": "SOURCE_VALID",
    }
    assert not (tmp_path / ".secrets").exists()


def test_main_projects_verified_final_webp_bytes_into_theme_doctor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_path = "assets/images/home-hero.webp"
    image_bytes = b"RIFF\x0c\x00\x00\x00WEBPsynthetic"
    monkeypatch.setattr(cli, "_runtime_authorized", True)
    monkeypatch.setattr(
        cli,
        "_verified_runtime_bytes",
        {
            cli._CONTENT_PACKET_RUNTIME_PATH: b"synthetic-bound-packet",
            f"{cli._THEME_RUNTIME_PREFIX}{image_path}": image_bytes,
        },
    )
    monkeypatch.setattr(cli, "_physical_repository_root", lambda root: root)
    observed: dict[str, bytes] = {}

    def doctor(
        repository_root: Path,
        *,
        content_packet_bytes: bytes | None,
        theme_payloads: dict[str, bytes] | None,
    ) -> dict[str, object]:
        assert repository_root == tmp_path
        assert content_packet_bytes == b"synthetic-bound-packet"
        assert theme_payloads is not None
        observed.update(theme_payloads)
        return {"status": "SYNTHETIC_LOCAL_ONLY"}

    monkeypatch.setattr(cli, "_doctor", doctor)
    assert cli.main(["doctor"], repository_root=tmp_path) == 0
    assert observed == {image_path: image_bytes}
    assert json.loads(capsys.readouterr().out) == {"status": "SYNTHETIC_LOCAL_ONLY"}


def test_hidden_installer_prints_no_values_and_creates_owner_private_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _authorize_imported_cli(monkeypatch)
    username = "owner-test-user"
    application_password = "synthetic app password 1703"

    def tty_reader(prompt: bytes) -> bytes:
        if b"username" in prompt:
            return username.encode("ascii")
        return application_password.encode("ascii")

    assert (
        cli.main(
            ["install-credentials"],
            repository_root=tmp_path,
            tty_reader=tty_reader,
        )
        == 0
    )
    output = capsys.readouterr()
    assert username not in output.out + output.err
    assert application_password not in output.out + output.err
    result = json.loads(output.out)
    assert result["secret_values_printed"] == 0

    credential_path = tmp_path / CREDENTIAL_RELATIVE_PATH
    assert stat.S_IMODE(credential_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(credential_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(credential_path.parent.parent.stat().st_mode) == 0o700
    credentials = OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path).read()
    assert username not in repr(credentials)
    assert application_password not in repr(credentials)


@pytest.mark.parametrize(
    "argv",
    [
        ["update-draft", "--draft-id", "0"],
        ["update-draft", "--draft-id", "-1"],
        ["update-draft", "--draft-id", str(1 << 63)],
        ["publish"],
        ["delete"],
        ["create-draft", "--application-password", "never-reflect-this-secret"],
        ["doc"],
    ],
)
def test_unknown_forbidden_and_invalid_controls_are_sanitized(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _authorize_imported_cli(monkeypatch)
    assert cli.main(argv, repository_root=tmp_path) == 2
    output = capsys.readouterr()
    assert "never-reflect-this-secret" not in output.out + output.err
    assert output.err == ""
    refusal = json.loads(output.out)
    assert refusal["status"] == "BLOCKED"
    assert refusal["publication_authorized"] is False
    assert refusal["reason_code"] in {"INVALID_ARGUMENT", "OPERATION_NOT_ALLOWED"}


def test_direct_linked_worktree_execution_refuses_before_command_imports() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            str(SCRIPTS_ROOT / "self_hosted_wordpress.py"),
            "--help",
        ],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert b"Traceback" not in result.stdout
    refusal = json.loads(result.stdout)
    assert refusal == {
        "publication_authorized": False,
        "reason_code": "SELF_HOSTED_RUNTIME_BINDING_INVALID",
        "status": "BLOCKED",
    }


def test_exact_root_launcher_doctor_is_sanitized_and_read_only() -> None:
    expected_root = Path("/home/minami/rakuten")
    if REPOSITORY_ROOT != expected_root:
        pytest.skip("exact-root launcher evidence runs after integration")
    result = subprocess.run(
        [str(SCRIPTS_ROOT / "self_hosted_wordpress_python.sh"), "doctor"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
        env={
            "PATH": "/untrusted",
            "LD_PRELOAD": "/untrusted/preload.so",
            "PYTHONPATH": "/untrusted/python",
            "SSL_CERT_FILE": "/untrusted/ca.pem",
        },
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert b"Traceback" not in result.stdout
    receipt = json.loads(result.stdout)
    assert receipt["credential_value_reads"] == 0
    assert receipt["network_requests"] == 0
    assert receipt["external_writes"] == 0
    assert receipt["publication_actions"] == 0


def test_launcher_is_exact_root_pinned_isolated_and_sanitizes_environment() -> None:
    launcher_path = SCRIPTS_ROOT / "self_hosted_wordpress_python.sh"
    launcher = launcher_path.read_text(encoding="utf-8")
    assert launcher_path.stat().st_mode & 0o777 == 0o755
    assert launcher.startswith("#!/usr/bin/busybox sh\n")
    assert "expected_root=/home/minami/rakuten" in launcher
    assert "umask 0077" in launcher
    assert "/usr/bin/busybox env -i" in launcher
    assert "cpython-3.14.6-linux-x86_64-gnu" in launcher
    assert "python=$expected_root/.venv/bin/python" in launcher
    assert "approved_base=b5a6157b878ca0435ee4120d33162aba5ae51f77" in launcher
    assert "fixed_git status --porcelain=v1 --untracked-files=all" in launcher
    assert "fixed_git hash-object --no-filters" in launcher
    assert "fixed_git cat-file blob" in launcher
    assert "python-runtime-code-inventory.v1.sha256" in launcher
    assert "SELF_HOSTED_PYTHON_RUNTIME_CODE_INVENTORY_V1" in launcher
    assert "python314.zip" in launcher
    assert "python_startup_landmark_state=ABSENT" in launcher
    assert "python_pybuilddir=$python_root/bin/pybuilddir.txt" in launcher
    assert launcher.count("startup_landmarks_absent || refuse") == 2
    assert launcher.count("runtime_bin_path_sets_match || refuse") == 2
    assert "dynamic_loader=$dynamic_library_directory/ld-linux-x86-64.so.2" in launcher
    assert "--inhibit-cache" in launcher
    assert "--inhibit-rpath ''" in launcher
    assert "--glibc-hwcaps-mask ''" in launcher
    assert '--library-path "$dynamic_library_directory"' in launcher
    assert '--argv0 "$python"' in launcher
    assert "current_code_path_sha" in launcher
    assert "inventory_code_path_sha" in launcher
    assert "capture_sentinel=RAOS_SELF_HOSTED_COMMITTED_CLI_CAPTURE_END_" in launcher
    assert '"RAOS_SELF_HOSTED_STAGE_HEAD=$head_commit"' in launcher
    assert '"RAOS_SELF_HOSTED_STAGE_CLI_BLOB=$stage_cli_blob"' in launcher
    assert '"RAOS_SELF_HOSTED_STAGE_CLI_SHA256=$captured_cli_sha"' in launcher
    assert '"$python_target" \\' in launcher
    assert "-B -I -S -X pycache_prefix=/dev/null -" in launcher
    assert "doctor:1|install-credentials:1|create-draft:1" in launcher
    assert "update-draft" not in launcher
    assert "curl" not in launcher
    assert "wget" not in launcher


def test_imported_main_refuses_before_credentials_or_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("capability")
        raise AssertionError("capability reached")

    monkeypatch.setattr(cli, "_runtime_authorized", False)
    monkeypatch.setattr(cli, "_verified_runtime_bytes", None)
    monkeypatch.setattr(cli, "_apply_draft", forbidden)
    assert cli.main(["create-draft"], repository_root=tmp_path) == 2
    assert calls == []
    assert json.loads(capsys.readouterr().out)["reason_code"] == (
        "SELF_HOSTED_RUNTIME_BINDING_INVALID"
    )
    assert not (tmp_path / ".secrets").exists()


def test_story_makefile_has_closed_targets_and_sanitized_help() -> None:
    result = subprocess.run(
        ["/usr/bin/make", "-f", str(SLICE_MAKEFILE), "help"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert result.stdout.splitlines() == [
        b"Offline: doctor runtime-manifest-check theme-source-check theme-check",
        b"Local maintenance: runtime-manifest-generate",
        b"Human gated: install-credentials create-draft theme-package",
    ]
    assert b"update" not in result.stdout
    content = SLICE_MAKEFILE.read_text(encoding="utf-8")
    assert "override OWNER_REPOSITORY_ROOT := /home/minami/rakuten" in content
    assert "override OWNER_LAUNCHER :=" in content
    assert "override MANAGED_PYTHON :=" in content
    assert (
        "override ROOT_OWNED_RUNTIME_GENERATOR_PYTHON := /usr/bin/python3.10" in content
    )
    assert content.count("/usr/bin/busybox env -i PATH=/usr/bin:/bin") == 2
    assert "update-draft" not in content


@pytest.mark.parametrize(
    "make_arguments",
    [
        ["-n"],
        ["-i"],
        ["-t"],
        ["-e"],
        ["MAKEFLAGS=n"],
    ],
)
def test_story_makefile_rejects_non_verifying_modes(
    make_arguments: list[str],
) -> None:
    result = subprocess.run(
        [
            "/usr/bin/make",
            *make_arguments,
            "-f",
            str(SLICE_MAKEFILE),
            "help",
        ],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert b"Offline:" not in combined
    assert b"owner-local gates" in combined or b"non-verifying GNU Make" in combined


def test_story_makefile_rejects_preloaded_makefiles(tmp_path: Path) -> None:
    preload = tmp_path / "preloaded.mk"
    preload.write_text("PRELOADED_VARIABLE := inert\n", encoding="utf-8")
    result = subprocess.run(
        ["/usr/bin/make", "-f", str(SLICE_MAKEFILE), "help"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "MAKEFILES": str(preload),
        },
    )
    assert result.returncode != 0
    assert b"Offline:" not in result.stdout + result.stderr
    assert b"Preloaded MAKEFILES are not allowed" in result.stdout + result.stderr


def test_story_makefile_ignores_hostile_shell_startup_environment(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "shell-startup-executed"
    startup = tmp_path / "startup.sh"
    startup.write_text(f"/usr/bin/touch {marker}\n", encoding="utf-8")
    result = subprocess.run(
        ["/usr/bin/make", "-f", str(SLICE_MAKEFILE), "help"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "BASH_ENV": str(startup),
            "ENV": str(startup),
            "BASH_FUNC_echo%%": f"() {{ /usr/bin/touch {marker}; }}",
        },
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == b""
    assert not marker.exists()
    assert result.stdout.startswith(b"Offline: doctor")
