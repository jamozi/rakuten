"""Hostile installed-entry and report-publication tests for ST-0505."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
from types import SimpleNamespace
from typing import Any

import pytest

import raos.adapters.rakuten_live_smoke as live_adapter
from raos.adapters.rakuten_live_smoke import (
    OwnerPrivateRakutenLiveSmokeReportWriter,
)
from raos.domain.catalog.rakuten_live_smoke import RakutenLiveSmokeHttpResponse
from raos.domain.catalog.rakuten_live_smoke import RakutenLiveSmokeFailure
from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator
from scripts import install_rakuten_live_smoke_runtime as installer
from scripts import rakuten_live_smoke as cli
from .test_rakuten_live_smoke_runtime import (
    FakeReader,
    MemoryWriter,
    StaticTransport,
    SUCCESS,
    WIRE_HEADER_PROOF,
    _credential_repository,
)


SOURCE_ROOT = Path(__file__).resolve().parents[2]
INSTALL_STAGE = SOURCE_ROOT / "scripts/rakuten_live_smoke_runtime_install.sh"
INSTALL_FAILURE = b"RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED\n"


@dataclass(frozen=True)
class _InstallStageFixture:
    stage: Path
    python: Path
    installer: Path
    installer_marker: Path
    malicious_marker: Path
    stdlib_probe: Path
    loader: Path
    preload: Path
    path_configuration: Path


def _write_fixture_file(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    path.write_bytes(payload)
    path.chmod(mode)


def _install_stage_fixture(tmp_path: Path) -> _InstallStageFixture:
    fake_root = tmp_path / "os-root"
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True, mode=0o755)
    for directory in (
        fake_root / "usr/bin",
        fake_root / "usr/lib64",
        fake_root / "usr/lib/x86_64-linux-gnu",
        fake_root / "usr/lib/python3.10/lib-dynload",
        fake_root / "usr/lib/python3.10/config-3.10-x86_64-linux-gnu",
        fake_root / "usr/lib/wsl/lib",
        fake_root / "usr/local/lib",
        fake_root / "etc/ld.so.conf.d",
        fake_root / "etc/python3.10",
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o755)

    (fake_root / "lib").symlink_to("usr/lib")
    (fake_root / "lib64").symlink_to("usr/lib64")
    loader = fake_root / "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
    _write_fixture_file(loader, b"fixture-loader\n", 0o755)
    (fake_root / "usr/lib64/ld-linux-x86-64.so.2").symlink_to(
        fake_root / "lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
    )
    _write_fixture_file(
        fake_root / "usr/lib/x86_64-linux-gnu/libpython3.10.so.1.0",
        b"fixture-libpython\n",
    )
    (fake_root / "usr/lib/x86_64-linux-gnu/libpython3.10.so.1").symlink_to(
        "libpython3.10.so.1.0"
    )

    sysconfig = fake_root / "usr/lib/python3.10/_sysconfigdata__x86_64-linux-gnu.py"
    _write_fixture_file(sysconfig, b"# fixture sysconfig\n")
    (
        fake_root / "usr/lib/python3.10/_sysconfigdata__linux_x86_64-linux-gnu.py"
    ).symlink_to("_sysconfigdata__x86_64-linux-gnu.py")
    (
        fake_root / "usr/lib/python3.10/config-3.10-x86_64-linux-gnu/libpython3.10.so"
    ).symlink_to("../../x86_64-linux-gnu/libpython3.10.so.1")
    sitecustomize = fake_root / "etc/python3.10/sitecustomize.py"
    _write_fixture_file(sitecustomize, b"# fixture sitecustomize\n")
    (fake_root / "usr/lib/python3.10/sitecustomize.py").symlink_to(sitecustomize)
    stdlib_probe = fake_root / "usr/lib/python3.10/hashlib.py"
    _write_fixture_file(stdlib_probe, b"# fixture stdlib\n")

    config_payloads = {
        fake_root / "etc/ld.so.conf": b"include fixture\n",
        fake_root / "etc/ld.so.cache": b"fixture-cache\n",
        fake_root
        / "etc/ld.so.conf.d/fakeroot-x86_64-linux-gnu.conf": b"fixture-fakeroot\n",
        fake_root / "etc/ld.so.conf.d/ld.wsl.conf": b"fixture-wsl\n",
        fake_root / "etc/ld.so.conf.d/libc.conf": b"fixture-libc\n",
        fake_root / "etc/ld.so.conf.d/x86_64-linux-gnu.conf": b"fixture-multiarch\n",
    }
    for path, payload in config_payloads.items():
        _write_fixture_file(path, payload)

    installer_marker = tmp_path / "authenticated-installer-ran"
    malicious_marker = tmp_path / "replacement-installer-ran"
    installer_path = scripts / "install_rakuten_live_smoke_runtime.py"
    _write_fixture_file(
        installer_path,
        (
            "#!/usr/bin/busybox sh\n"
            f"/usr/bin/busybox touch {installer_marker.as_posix()}\n"
            "/usr/bin/busybox printf '%s\\n' AUTHENTICATED_INSTALLER_PASS\n"
        ).encode(),
        0o600,
    )
    python_path = fake_root / "usr/bin/python3.10"
    _write_fixture_file(
        python_path,
        (
            "#!/usr/bin/busybox sh\n"
            '[ "$#" -eq 4 ] && [ "$1" = -B ] && [ "$2" = -I ] '
            '&& [ "$3" = -S ] || exit 91\n'
            'exec /usr/bin/busybox sh "$4"\n'
        ).encode(),
        0o755,
    )

    source = INSTALL_STAGE.read_text(encoding="utf-8")
    source = re.sub(
        r"(?<![A-Za-z0-9_])/(lib64|lib)(?=(?:/|[\s\"']))",
        lambda match: (fake_root / match.group(1)).as_posix(),
        source,
    )
    replacements = dict(
        (
            ("/home/minami/rakuten", repository.as_posix()),
            ("/usr/bin/python3.10", python_path.as_posix()),
            (
                "/usr/lib/python310.zip",
                (fake_root / "usr/lib/python310.zip").as_posix(),
            ),
            ("/usr/lib/python3.10", (fake_root / "usr/lib/python3.10").as_posix()),
            (
                "/usr/lib/x86_64-linux-gnu",
                (fake_root / "usr/lib/x86_64-linux-gnu").as_posix(),
            ),
            ("/usr/lib/wsl", (fake_root / "usr/lib/wsl").as_posix()),
            ("/usr/lib64", (fake_root / "usr/lib64").as_posix()),
            ("/usr/lib", (fake_root / "usr/lib").as_posix()),
            ("/usr/local", (fake_root / "usr/local").as_posix()),
            ("/usr/pyvenv.cfg", (fake_root / "usr/pyvenv.cfg").as_posix()),
            ("/usr/bin/python._pth", (fake_root / "usr/bin/python._pth").as_posix()),
            (
                "/usr/bin/python3.10._pth",
                (fake_root / "usr/bin/python3.10._pth").as_posix(),
            ),
            ("/usr/bin/pyvenv.cfg", (fake_root / "usr/bin/pyvenv.cfg").as_posix()),
            ("/etc", (fake_root / "etc").as_posix()),
            ("usr/lib64", "usr/lib64"),
            ("usr/lib", "usr/lib"),
        )
    )
    replacement_pattern = re.compile(
        "|".join(
            re.escape(item) for item in sorted(replacements, key=len, reverse=True)
        )
    )
    source = replacement_pattern.sub(lambda match: replacements[match.group(0)], source)
    source = source.replace(
        '[ "$checked_uid" -eq "$expected_root_uid" ] || refuse',
        '{ [ "$checked_uid" -eq "$expected_root_uid" ] '
        '|| [ "$checked_uid" -eq "$effective_uid" ]; } || refuse',
    )
    source = source.replace(
        '! -user "$expected_root_uid" -o -perm +022',
        '\\( ! -user "$expected_root_uid" ! -user "$effective_uid" \\) -o -perm +022',
    )
    source = source.replace(
        '-type l ! -user "$expected_root_uid"',
        '-type l ! -user "$expected_root_uid" ! -user "$effective_uid"',
    )
    source = source.replace(
        "expected_python_sha256="
        "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
        f"expected_python_sha256={hashlib.sha256(python_path.read_bytes()).hexdigest()}",
    )
    source = source.replace(
        "expected_installer_sha256="
        "e59ba05bfd97b56e9a59b1ceac9ee54a16ef461af43ae5f01ace5322319bf3da",
        f"expected_installer_sha256={hashlib.sha256(installer_path.read_bytes()).hexdigest()}",
    )
    production_hashes = (
        "2cee49274627997b8652f964f3fa07912ee14ddf49566953ce4ecf057f08a5d0",
        "d4b198c463418b493208485def26a6f4c57279467b9dfa491b70433cedb602e8",
        "af7edc777dd224bade078ba540538444db69856533c02e18a7f9fbbdd23bd181",
        "cfab3f46873c9203cab45d9038643fd9b0a02d84a749d12511c5cee5e2bd77c2",
        "90d4c7e43e7661cd116010eb9f50ad5817e43162df344bd1ad10898851b15d41",
        "f03e4740e6922b4f4a1181cd696b52f62f9f10d003740a8940f7121795c59c98",
    )
    fixture_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            fake_root / "etc/ld.so.cache",
            fake_root / "etc/ld.so.conf",
            fake_root / "etc/ld.so.conf.d/fakeroot-x86_64-linux-gnu.conf",
            fake_root / "etc/ld.so.conf.d/ld.wsl.conf",
            fake_root / "etc/ld.so.conf.d/libc.conf",
            fake_root / "etc/ld.so.conf.d/x86_64-linux-gnu.conf",
        )
    )
    for old, new in zip(production_hashes, fixture_hashes, strict=True):
        source = source.replace(old, new)
    stage = scripts / "rakuten_live_smoke_runtime_install.sh"
    stage.write_text(source, encoding="utf-8")
    stage.chmod(0o600)
    return _InstallStageFixture(
        stage=stage,
        python=python_path,
        installer=installer_path,
        installer_marker=installer_marker,
        malicious_marker=malicious_marker,
        stdlib_probe=stdlib_probe,
        loader=loader,
        preload=fake_root / "etc/ld.so.preload",
        path_configuration=fake_root / "usr/lib/python310.zip",
    )


def _run_install_stage(
    stage: Path,
    expected_sha256: str | None = None,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    expected = expected_sha256 or hashlib.sha256(stage.read_bytes()).hexdigest()
    return subprocess.run(
        _install_stage_command(stage, expected),
        check=False,
        capture_output=True,
        env=environment,
    )


def _install_stage_command(stage: Path, expected: str) -> list[str]:
    command = shlex.split(generator._authoritative_runtime_install_command())
    fixed_stage = f"p={generator.REVIEWED_RUNTIME_INSTALL_STAGE}; "
    assert command[-1].count(fixed_stage) == 1
    gate = command[-1].replace(
        fixed_stage,
        'p="$1"; expected="$2"; ',
        1,
    )
    assert gate.count(generator.EXPECTED_RUNTIME_INSTALL_STAGE_SHA256) == 1
    gate = gate.replace(
        generator.EXPECTED_RUNTIME_INSTALL_STAGE_SHA256,
        "$expected",
        1,
    )
    return [
        *command[:-1],
        gate,
        "st0505-install-gate",
        os.fspath(stage),
        expected,
    ]


def _authenticated_installer_validator_command() -> str:
    installer_source = SOURCE_ROOT / "scripts/install_rakuten_live_smoke_runtime.py"
    code = (
        "import importlib.machinery,importlib.util,pathlib;"
        "p='/proc/self/fd/6';"
        "loader=importlib.machinery.SourceFileLoader('st0505_installer',p);"
        "s=importlib.util.spec_from_loader('st0505_installer',loader);"
        "m=importlib.util.module_from_spec(s);loader.exec_module(m);"
        f"m.REVIEWED_INSTALLER_PATH=pathlib.Path({os.fspath(installer_source)!r});"
        "m.install=lambda *a:'AUTHENTICATED_INSTALL_STUB';"
        "raise SystemExit(m.main([]))"
    )
    return (
        "exec 5</usr/bin/python3.10; "
        f"exec 6<{shlex.quote(os.fspath(installer_source))}; "
        f"exec /proc/self/fd/5 -B -I -S -c {shlex.quote(code)}"
    )


def _run_authenticated_installer_validator(
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "/usr/bin/busybox",
            "env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LANG=C.UTF-8",
            "LC_ALL=C.UTF-8",
            "TZ=UTC",
            "/usr/bin/busybox",
            "sh",
            "-c",
            _authenticated_installer_validator_command(),
        ],
        check=False,
        capture_output=True,
        env=environment,
    )


def _source_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for source, _installed, _mode in installer._PAYLOADS:  # noqa: SLF001
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE_ROOT / source, target)
        os.chmod(target, 0o644)
    return root


def _install(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = _source_repository(tmp_path)
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    result = installer.install(
        repository,
        owner_base,
        installer.EXPECTED_BUNDLE_SHA256,
    )
    assert result == installer.INSTALLED
    bundle = (
        owner_base
        / "raos/rakuten-live-smoke/runtime"
        / installer.EXPECTED_BUNDLE_SHA256
    )
    return repository, owner_base, bundle


def test_install_is_external_private_exact_and_idempotent(tmp_path: Path) -> None:
    repository, owner_base, bundle = _install(tmp_path)
    assert not bundle.is_relative_to(repository)
    for directory in (
        owner_base / "raos",
        owner_base / "raos/rakuten-live-smoke",
        owner_base / "raos/rakuten-live-smoke/runtime",
        bundle,
        bundle / "bin",
        bundle / "scripts",
        bundle / "python",
    ):
        assert directory.stat().st_uid == os.getuid()
        assert directory.stat().st_mode & 0o777 == 0o700
        assert not directory.is_symlink()
    assert (bundle / "bin/rakuten-live-smoke").stat().st_mode & 0o777 == 0o500
    assert (bundle / "scripts/rakuten_live_smoke.py").stat().st_mode & 0o777 == 0o400
    manifest_path = bundle / "runtime-manifest.v1.json"
    assert manifest_path.stat().st_mode & 0o777 == 0o400
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["bundle_sha256"] == installer.EXPECTED_BUNDLE_SHA256
    assert {row["mode"] for row in manifest["files"]} == {"0400", "0500"}
    assert (
        installer.install(
            repository,
            owner_base,
            installer.EXPECTED_BUNDLE_SHA256,
        )
        == installer.ALREADY_INSTALLED
    )
    assert not tuple(
        (owner_base / "raos/rakuten-live-smoke/runtime").glob(".install-*")
    )


def test_install_loser_fsyncs_and_revalidates_concurrent_exact_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _source_repository(tmp_path)
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    winner_published = False
    durable_runtime_fsyncs = 0
    durability_events: list[str] = []
    original_fsync = os.fsync
    original_validate_bundle = installer._validate_bundle

    def publish_winner_then_lose(directory_fd: int, source: str, target: str) -> None:
        nonlocal winner_published
        runtime = Path(os.readlink(f"/proc/self/fd/{directory_fd}"))
        shutil.copytree(runtime / source, runtime / target)
        winner_published = True
        raise FileExistsError("simulated exact concurrent winner")

    def recording_fsync(descriptor: int) -> None:
        nonlocal durable_runtime_fsyncs
        if winner_published:
            target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            if target.name == "runtime":
                durable_runtime_fsyncs += 1
                durability_events.append("fsync")
        original_fsync(descriptor)

    def recording_validate_bundle(*args: Any, **kwargs: Any) -> None:
        if winner_published:
            durability_events.append("validate")
        original_validate_bundle(*args, **kwargs)

    monkeypatch.setattr(installer, "_rename_noreplace", publish_winner_then_lose)
    installer_os = getattr(installer, "os")
    monkeypatch.setattr(installer_os, "fsync", recording_fsync)
    monkeypatch.setattr(installer, "_validate_bundle", recording_validate_bundle)
    assert (
        installer.install(repository, owner_base, installer.EXPECTED_BUNDLE_SHA256)
        == installer.ALREADY_INSTALLED
    )
    assert winner_published and durable_runtime_fsyncs == 1
    assert durability_events == ["validate", "fsync", "validate"]


def test_installed_runtime_verifies_before_import_or_credential_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository, owner_base, bundle = _install(tmp_path)
    monkeypatch.setattr(cli, "TRUSTED_OWNER_ROOT", owner_base / "raos")
    monkeypatch.setattr(
        cli,
        "TRUSTED_RUNTIME_PARENT",
        owner_base / "raos/rakuten-live-smoke/runtime",
    )
    monkeypatch.setattr(cli, "__file__", str(bundle / "scripts/rakuten_live_smoke.py"))
    assert cli._verify_installed_runtime() == bundle  # noqa: SLF001

    payload = bundle / "python/raos/adapters/rakuten_live_smoke.py"
    os.chmod(payload, 0o600)
    payload.write_bytes(payload.read_bytes() + b"\n# drift\n")
    os.chmod(payload, 0o400)
    with pytest.raises(RuntimeError, match="RUNTIME_UNTRUSTED"):
        cli._verify_installed_runtime()  # noqa: SLF001


@pytest.mark.parametrize(
    ("relative", "is_directory"),
    [
        ("python/raos/__pycache__", True),
        ("python/raos/domain/__init__.py", False),
    ],
)
def test_installed_runtime_rejects_unmanifested_import_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    is_directory: bool,
) -> None:
    _repository, owner_base, bundle = _install(tmp_path)
    monkeypatch.setattr(cli, "TRUSTED_OWNER_ROOT", owner_base / "raos")
    monkeypatch.setattr(
        cli,
        "TRUSTED_RUNTIME_PARENT",
        owner_base / "raos/rakuten-live-smoke/runtime",
    )
    monkeypatch.setattr(cli, "__file__", str(bundle / "scripts/rakuten_live_smoke.py"))
    extra = bundle / relative
    if is_directory:
        extra.mkdir(mode=0o700)
    else:
        extra.write_bytes(b"raise RuntimeError('must not import')\n")
        os.chmod(extra, 0o400)
    with pytest.raises(RuntimeError, match="RUNTIME_UNTRUSTED"):
        cli._verify_installed_runtime()  # noqa: SLF001


def test_wrong_owner_symlink_and_repository_direct_entry_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repository, owner_base, bundle = _install(tmp_path)
    monkeypatch.setattr(cli, "TRUSTED_OWNER_ROOT", owner_base / "raos")
    monkeypatch.setattr(
        cli,
        "TRUSTED_RUNTIME_PARENT",
        owner_base / "raos/rakuten-live-smoke/runtime",
    )
    monkeypatch.setattr(cli, "__file__", str(bundle / "scripts/rakuten_live_smoke.py"))
    real_uid = os.getuid()
    cli_os = getattr(cli, "os")
    monkeypatch.setattr(cli_os, "getuid", lambda: real_uid + 1)
    with pytest.raises(RuntimeError, match="RUNTIME_UNTRUSTED"):
        cli._verify_installed_runtime()  # noqa: SLF001
    monkeypatch.setattr(cli_os, "getuid", lambda: real_uid)

    actual = owner_base / "raos/rakuten-live-smoke"
    moved = owner_base / "real-rakuten-live-smoke"
    actual.rename(moved)
    actual.symlink_to(moved, target_is_directory=True)
    with pytest.raises(OSError):
        cli._verify_installed_runtime()  # noqa: SLF001

    monkeypatch.setattr(
        cli,
        "__file__",
        str(installer.REPOSITORY_ROOT / "scripts/rakuten_live_smoke.py"),
    )
    monkeypatch.setattr(
        cli,
        "sys",
        SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=1)),
    )
    dependency_calls = 0

    def forbidden_dependencies() -> object:
        nonlocal dependency_calls
        dependency_calls += 1
        raise AssertionError("credential dependency must not be constructed")

    monkeypatch.setattr(cli, "_production_dependencies", forbidden_dependencies)
    assert cli.main(["doctor"]) == 2
    assert capsys.readouterr() == ("RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY\n", "")
    assert dependency_calls == 0


def test_installer_rejects_source_symlink_and_digest_drift(tmp_path: Path) -> None:
    repository = _source_repository(tmp_path)
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    source = repository / "scripts/rakuten_live_smoke.py"
    outside = tmp_path / "outside.py"
    source.rename(outside)
    source.symlink_to(outside)
    with pytest.raises(installer.RuntimeInstallError):
        installer.install(repository, owner_base, installer.EXPECTED_BUNDLE_SHA256)
    assert not (owner_base / "raos").exists()

    source.unlink()
    shutil.copyfile(SOURCE_ROOT / "scripts/rakuten_live_smoke.py", source)
    os.chmod(source, 0o644)
    with pytest.raises(installer.RuntimeInstallError):
        installer.install(repository, owner_base, "0" * 64)
    assert not (owner_base / "raos").exists()


def test_direct_repository_installer_refuses_before_runtime_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_calls = 0

    def forbidden_install(*args: object, **kwargs: object) -> str:
        nonlocal install_calls
        del args, kwargs
        install_calls += 1
        raise AssertionError("direct entry must not mutate runtime")

    monkeypatch.setattr(installer, "install", forbidden_install)
    assert installer.main([]) == 1
    assert capsys.readouterr() == (
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED\n",
        "",
    )
    assert install_calls == 0


def test_authenticated_installer_fd_validator_reaches_stub_install() -> None:
    result = _run_authenticated_installer_validator()
    assert result.returncode == 0
    assert result.stdout == b"AUTHENTICATED_INSTALL_STUB\n"
    assert result.stderr == b""


@pytest.mark.parametrize("loader_variable", ["LD_PRELOAD", "LD_AUDIT"])
def test_install_bootstrap_clears_hostile_loader_state_before_root_python(
    tmp_path: Path,
    loader_variable: str,
) -> None:
    source = tmp_path / "install_loader_hook.c"
    library = tmp_path / "install_loader_hook.so"
    marker = tmp_path / "install-loader-hook-ran"
    source.write_text(
        "#include <fcntl.h>\n"
        "#include <stdlib.h>\n"
        "#include <unistd.h>\n"
        "__attribute__((constructor)) static void run(void) {\n"
        '  const char *p = getenv("RAOS_INSTALL_LOADER_MARKER");\n'
        "  if (p) { int f = open(p, O_WRONLY|O_CREAT, 0600); "
        "if (f >= 0) close(f); }\n"
        "}\n"
        "unsigned int la_version(unsigned int value) { return value; }\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "/usr/bin/cc",
            "-shared",
            "-fPIC",
            "-o",
            os.fspath(library),
            os.fspath(source),
        ],
        check=True,
        capture_output=True,
    )
    result = _run_authenticated_installer_validator(
        {
            "PATH": "/usr/bin:/bin",
            loader_variable: os.fspath(library),
            "RAOS_INSTALL_LOADER_MARKER": os.fspath(marker),
        }
    )
    assert result.returncode == 0
    assert result.stdout == b"AUTHENTICATED_INSTALL_STUB\n"
    assert result.stderr == b""
    assert not marker.exists()


def test_outer_install_gate_rejects_stage_drift_before_body(tmp_path: Path) -> None:
    marker = tmp_path / "drifted-stage-ran"
    stage = tmp_path / "rakuten_live_smoke_runtime_install.sh"
    trusted = INSTALL_STAGE.read_bytes()
    stage.write_bytes(
        b"#!/usr/bin/busybox sh\n/usr/bin/busybox touch " + os.fsencode(marker) + b"\n"
    )
    stage.chmod(0o600)
    result = _run_install_stage(stage, hashlib.sha256(trusted).hexdigest())
    assert result.returncode == 2
    assert result.stdout == INSTALL_FAILURE
    assert result.stderr == b""
    assert not marker.exists()


def test_outer_install_gate_rejects_unsafe_mode_before_first_command(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "unsafe-stage-first-command-ran"
    stage = tmp_path / "rakuten_live_smoke_runtime_install.sh"
    stage.write_bytes(
        b"#!/usr/bin/busybox sh\n/usr/bin/busybox touch " + os.fsencode(marker) + b"\n"
    )
    stage.chmod(0o620)
    expected = hashlib.sha256(stage.read_bytes()).hexdigest()
    result = _run_install_stage(stage, expected)
    assert result.returncode == 2
    assert result.stdout == INSTALL_FAILURE
    assert result.stderr == b""
    assert not marker.exists()


def test_authenticated_install_stage_executes_only_bound_inputs(
    tmp_path: Path,
) -> None:
    fixture = _install_stage_fixture(tmp_path)
    result = _run_install_stage(fixture.stage)
    assert result.returncode == 0
    assert result.stdout == b"AUTHENTICATED_INSTALLER_PASS\n"
    assert result.stderr == b""
    assert fixture.installer_marker.is_file()
    assert not fixture.malicious_marker.exists()


@pytest.mark.parametrize(
    "drift",
    [
        "python_digest",
        "installer_digest",
        "installer_symlink",
        "installer_fifo",
        "installer_directory",
        "installer_hardlink",
        "installer_writable",
        "installer_oversized",
        "stdlib_writable",
        "loader_writable",
        "ld_preload",
        "python_path_configuration",
    ],
)
def test_install_stage_rejects_runtime_or_source_drift_before_installer(
    tmp_path: Path,
    drift: str,
) -> None:
    fixture = _install_stage_fixture(tmp_path)
    if drift == "python_digest":
        fixture.python.write_bytes(fixture.python.read_bytes() + b"# drift\n")
        fixture.python.chmod(0o755)
    elif drift == "installer_digest":
        fixture.installer.write_bytes(fixture.installer.read_bytes() + b"# drift\n")
        fixture.installer.chmod(0o600)
    elif drift == "installer_symlink":
        preserved = fixture.installer.with_suffix(".preserved")
        fixture.installer.rename(preserved)
        fixture.installer.symlink_to(preserved)
    elif drift == "installer_fifo":
        fixture.installer.unlink()
        os.mkfifo(fixture.installer, 0o600)
    elif drift == "installer_directory":
        fixture.installer.unlink()
        fixture.installer.mkdir(mode=0o700)
    elif drift == "installer_hardlink":
        os.link(fixture.installer, fixture.installer.with_suffix(".hardlink"))
    elif drift == "installer_writable":
        fixture.installer.chmod(0o620)
    elif drift == "installer_oversized":
        fixture.installer.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        fixture.installer.chmod(0o600)
    elif drift == "stdlib_writable":
        fixture.stdlib_probe.chmod(0o666)
    elif drift == "loader_writable":
        fixture.loader.chmod(0o777)
    elif drift == "ld_preload":
        _write_fixture_file(fixture.preload, b"fixture-preload\n")
    elif drift == "python_path_configuration":
        _write_fixture_file(fixture.path_configuration, b"fixture-zip\n")
    else:
        raise AssertionError("closed fixture drift")
    result = _run_install_stage(fixture.stage)
    assert result.returncode == 2
    assert result.stdout == INSTALL_FAILURE
    assert result.stderr == b""
    assert not fixture.installer_marker.exists()


@pytest.mark.parametrize("entry_drift", ["symlink", "hardlink", "writable"])
def test_authenticated_install_stage_rejects_unsafe_stage_metadata(
    tmp_path: Path,
    entry_drift: str,
) -> None:
    fixture = _install_stage_fixture(tmp_path)
    expected = hashlib.sha256(fixture.stage.read_bytes()).hexdigest()
    if entry_drift == "symlink":
        preserved = fixture.stage.with_suffix(".preserved")
        fixture.stage.rename(preserved)
        fixture.stage.symlink_to(preserved)
    elif entry_drift == "hardlink":
        os.link(fixture.stage, fixture.stage.with_suffix(".hardlink"))
    elif entry_drift == "writable":
        fixture.stage.chmod(0o620)
    else:
        raise AssertionError("closed entry drift")
    result = _run_install_stage(fixture.stage, expected)
    assert result.returncode == 2
    assert result.stdout == INSTALL_FAILURE
    assert result.stderr == b""
    assert not fixture.installer_marker.exists()


def test_install_stage_executes_opened_installer_not_replaced_path(
    tmp_path: Path,
) -> None:
    fixture = _install_stage_fixture(tmp_path)
    synchronization = tmp_path / "installer-fd-bound"
    resume = tmp_path / "resume-installer-exec"
    stage_source = fixture.stage.read_text(encoding="utf-8")
    boundary = ': "RAOS_ST0505_INSTALLER_FD_EXEC_BOUNDARY"'
    assert stage_source.count(boundary) == 1
    stage_source = stage_source.replace(
        boundary,
        f"/usr/bin/busybox touch {synchronization.as_posix()}\n"
        f"while [ ! -e {resume.as_posix()} ]; do "
        "/usr/bin/busybox sleep 1; done",
    )
    fixture.stage.write_text(stage_source, encoding="utf-8")
    fixture.stage.chmod(0o600)
    expected = hashlib.sha256(fixture.stage.read_bytes()).hexdigest()
    process = subprocess.Popen(
        _install_stage_command(fixture.stage, expected),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ignored in range(100):
            if synchronization.exists():
                break
            time.sleep(0.05)
        assert synchronization.exists()
        preserved = fixture.installer.with_name("authenticated-installer.preserved")
        fixture.installer.rename(preserved)
        _write_fixture_file(
            fixture.installer,
            (
                "#!/usr/bin/busybox sh\n"
                f"/usr/bin/busybox touch {fixture.malicious_marker.as_posix()}\n"
            ).encode(),
            0o600,
        )
        resume.touch(mode=0o600)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    assert process.returncode == 0
    assert stdout == b"AUTHENTICATED_INSTALLER_PASS\n"
    assert stderr == b""
    assert fixture.installer_marker.is_file()
    assert not fixture.malicious_marker.exists()


def test_runtime_install_never_accesses_existing_secret_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _source_repository(tmp_path)
    secret_root = repository / ".secrets/rakuten-live-smoke"
    reports = secret_root / "reports"
    reports.mkdir(parents=True, mode=0o700)
    _write_fixture_file(secret_root / "credentials.v1.json", b"secret-fixture\n", 0o600)
    _write_fixture_file(
        secret_root / "staging-credential-binding.v1.json",
        b"binding-fixture\n",
        0o600,
    )
    _write_fixture_file(reports / "prior.json", b"report-fixture\n", 0o600)
    before = {
        path.relative_to(secret_root).as_posix(): (
            path.read_bytes() if path.is_file() else None,
            path.lstat().st_mode,
            path.lstat().st_mtime_ns,
        )
        for path in (secret_root, *secret_root.rglob("*"))
    }
    observed_names: list[str] = []
    original_open = os.open

    def recording_open(
        path: os.PathLike[str] | str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed_names.append(os.fsdecode(path))
        return original_open(path, flags, mode, dir_fd=dir_fd)

    installer_os = getattr(installer, "os")
    monkeypatch.setattr(installer_os, "open", recording_open)
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    assert (
        installer.install(repository, owner_base, installer.EXPECTED_BUNDLE_SHA256)
        == installer.INSTALLED
    )
    assert (
        installer.install(repository, owner_base, installer.EXPECTED_BUNDLE_SHA256)
        == installer.ALREADY_INSTALLED
    )
    after = {
        path.relative_to(secret_root).as_posix(): (
            path.read_bytes() if path.is_file() else None,
            path.lstat().st_mode,
            path.lstat().st_mtime_ns,
        )
        for path in (secret_root, *secret_root.rglob("*"))
    }
    assert before == after
    assert all(".secrets" not in name for name in observed_names)


@pytest.mark.parametrize("loader_variable", ["LD_PRELOAD", "LD_AUDIT"])
def test_static_stage_zero_never_runs_hostile_loader_hook(
    tmp_path: Path, loader_variable: str
) -> None:
    _repository, _owner_base, bundle = _install(tmp_path)
    source = tmp_path / "loader_hook.c"
    library = tmp_path / "loader_hook.so"
    marker = tmp_path / "loader-hook-ran"
    source.write_text(
        "#include <fcntl.h>\n"
        "#include <stdlib.h>\n"
        "#include <unistd.h>\n"
        "__attribute__((constructor)) static void run(void) {\n"
        '  const char *p = getenv("RAOS_LOADER_MARKER");\n'
        "  if (p) { int f = open(p, O_WRONLY|O_CREAT, 0600); "
        "if (f >= 0) close(f); }\n"
        "}\n"
        "unsigned int la_version(unsigned int value) { return value; }\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "/usr/bin/cc",
            "-shared",
            "-fPIC",
            "-o",
            os.fspath(library),
            os.fspath(source),
        ],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [os.fspath(bundle / "bin/rakuten-live-smoke"), "doctor"],
        check=False,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            loader_variable: os.fspath(library),
            "RAOS_LOADER_MARKER": os.fspath(marker),
        },
    )
    assert result.returncode == 2
    assert result.stdout == b"RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY\n"
    assert result.stderr == b""
    assert not marker.exists()
    busybox = Path("/usr/bin/busybox")
    assert hashlib.sha256(busybox.read_bytes()).hexdigest() == (
        "b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9"
    )
    assert b"/lib64/ld-linux" not in busybox.read_bytes()


def test_report_publication_failure_rolls_back_or_leaves_recovery_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path)
    reports = root / ".secrets/rakuten-live-smoke/reports"
    reports.mkdir(mode=0o700)
    writer = OwnerPrivateRakutenLiveSmokeReportWriter(root)
    original_link = os.link
    original_fsync = os.fsync
    linked = False
    failed = False

    def recording_link(*args: Any, **kwargs: Any) -> None:
        nonlocal linked
        original_link(*args, **kwargs)
        linked = True

    def failing_fsync(descriptor: int) -> None:
        nonlocal failed
        if linked and not failed and stat_is_directory(descriptor):
            failed = True
            raise OSError("post-publication fsync failed")
        original_fsync(descriptor)

    def stat_is_directory(descriptor: int) -> bool:
        return bool(os.fstat(descriptor).st_mode & 0o040000)

    monkeypatch.setattr(
        OwnerPrivateRakutenLiveSmokeReportWriter,
        "preflight",
        lambda _self: None,
    )
    adapter_os = getattr(live_adapter, "os")
    monkeypatch.setattr(adapter_os, "link", recording_link)
    monkeypatch.setattr(adapter_os, "fsync", failing_fsync)
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 2, tzinfo=timezone.utc),
        ]
    )
    code, output = cli.run_live_smoke(
        reader=FakeReader(),
        transport=StaticTransport(
            RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
        ),
        writer=writer,
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
    )
    assert code == 1
    assert output == "RAKUTEN_LIVE_SMOKE_FAIL_REPORT_STORE_INVALID"
    entries = tuple(reports.iterdir())
    assert len(entries) == 1
    assert entries[0].suffix == ".json"
    assert entries[0].stat().st_nlink == 1
    report = json.loads(entries[0].read_bytes())
    assert report["diagnostic_code"] == "REPORT_STORE_INVALID"
    assert report["request_count"] == 1
    assert report["auth_classification"] == "ACCEPTED"
    assert report["schema_classification"] == "VALID"
    assert report["rate_classification"] == "SINGLE_REQUEST_NOT_THROTTLED"
    assert report["affiliate_url_present"] is True
    assert report["response_sha256"] == hashlib.sha256(SUCCESS).hexdigest()
    assert WIRE_HEADER_PROOF.encode() not in entries[0].read_bytes()


def test_invalid_reports_directory_preserves_one_get_metadata(
    tmp_path: Path,
) -> None:
    root = _credential_repository(tmp_path)
    reports = root / ".secrets/rakuten-live-smoke/reports"
    reports.mkdir(mode=0o755)
    memory = MemoryWriter()
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    assert (
        cli.run_live_smoke(
            reader=FakeReader(),
            transport=StaticTransport(
                RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
            ),
            writer=memory,
            clock=lambda: next(clock_values),
            run_id_factory=lambda ignored: (
                "20260821T000000.000000Z-cccccccccccccccccccccccccccccccc"
            ),
        )[0]
        == 0
    )
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeReportWriter(root).write(memory.reports[0])
    failure = caught.value
    assert failure.code.value == "REPORT_STORE_INVALID"
    assert failure.request_count == 1
    assert failure.http_status == 200
    assert failure.auth.value == "ACCEPTED"
    assert failure.schema.value == "VALID"
    assert failure.rate.value == "SINGLE_REQUEST_NOT_THROTTLED"
    assert failure.affiliate_url_present is True
    assert failure.response_sha256 == hashlib.sha256(SUCCESS).hexdigest()


def test_report_link_preflight_failure_happens_before_credentials_or_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path)
    reader = FakeReader()
    transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
    )
    adapter_os = getattr(live_adapter, "os")

    def failing_link(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise OSError("procfs link unavailable")

    monkeypatch.setattr(adapter_os, "link", failing_link)
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    code, output = cli.run_live_smoke(
        reader=reader,
        transport=transport,
        writer=OwnerPrivateRakutenLiveSmokeReportWriter(root),
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        ),
    )
    assert (code, output) == (1, "RAKUTEN_LIVE_SMOKE_FAIL_REPORT_STORE_INVALID")
    assert reader.calls == 0
    assert transport.calls == 0


def test_recovery_evidence_blocks_failure_report_write_before_credentials_or_get(
    tmp_path: Path,
) -> None:
    root = _credential_repository(tmp_path)
    reports = root / ".secrets/rakuten-live-smoke/reports"
    reports.mkdir(mode=0o700)
    marker = reports / "prior-run.recovery-required"
    marker.write_bytes(b"RAOS_ST0505_REPORT_RECOVERY_REQUIRED_V1\n")
    marker.chmod(0o600)
    before = tuple((entry.name, entry.read_bytes()) for entry in reports.iterdir())
    reader = FakeReader()
    transport = StaticTransport(
        RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
    )
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    code, output = cli.run_live_smoke(
        reader=reader,
        transport=transport,
        writer=OwnerPrivateRakutenLiveSmokeReportWriter(root),
        clock=lambda: next(clock_values),
        run_id_factory=lambda ignored: (
            "20260821T000000.000000Z-ffffffffffffffffffffffffffffffff"
        ),
    )
    assert (code, output) == (1, "RAKUTEN_LIVE_SMOKE_FAIL_REPORT_STORE_INVALID")
    assert reader.calls == 0
    assert transport.calls == 0
    assert (
        tuple((entry.name, entry.read_bytes()) for entry in reports.iterdir()) == before
    )


def test_report_rollback_failure_leaves_fixed_private_recovery_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _credential_repository(tmp_path)
    reports = root / ".secrets/rakuten-live-smoke/reports"
    reports.mkdir(mode=0o700)
    memory = MemoryWriter()
    clock_values = iter(
        [
            datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 0, 1, tzinfo=timezone.utc),
        ]
    )
    assert (
        cli.run_live_smoke(
            reader=FakeReader(),
            transport=StaticTransport(
                RakutenLiveSmokeHttpResponse(200, "application/json", SUCCESS)
            ),
            writer=memory,
            clock=lambda: next(clock_values),
            run_id_factory=lambda ignored: (
                "20260821T000000.000000Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
        )[0]
        == 0
    )
    report = memory.reports[0]
    original_link = os.link
    original_fsync = os.fsync
    original_unlink = os.unlink
    linked = False
    failed = False

    def recording_link(*args: Any, **kwargs: Any) -> None:
        nonlocal linked
        original_link(*args, **kwargs)
        linked = True

    def failing_fsync(descriptor: int) -> None:
        nonlocal failed
        if linked and not failed and bool(os.fstat(descriptor).st_mode & 0o040000):
            failed = True
            raise OSError("post-publication fsync failed")
        original_fsync(descriptor)

    def failing_unlink(
        path: os.PathLike[str] | str | bytes, *args: Any, **kwargs: Any
    ) -> None:
        if str(path).endswith(".json"):
            raise OSError("rollback refused")
        original_unlink(path, *args, **kwargs)

    adapter_os = getattr(live_adapter, "os")
    monkeypatch.setattr(adapter_os, "link", recording_link)
    monkeypatch.setattr(adapter_os, "fsync", failing_fsync)
    monkeypatch.setattr(adapter_os, "unlink", failing_unlink)
    with pytest.raises(RakutenLiveSmokeFailure) as caught:
        OwnerPrivateRakutenLiveSmokeReportWriter(root).write(report)
    assert caught.value.request_count == 1
    assert caught.value.code.value == "REPORT_STORE_INVALID"
    marker = reports / f"{report.run_id}.recovery-required"
    target = reports / f"{report.run_id}.json"
    assert target.is_file() and marker.is_file()
    assert target.stat().st_mode & 0o777 == marker.stat().st_mode & 0o777 == 0o600
    assert marker.read_bytes() == b"RAOS_ST0505_REPORT_RECOVERY_REQUIRED_V1\n"
    assert WIRE_HEADER_PROOF.encode() not in marker.read_bytes() + target.read_bytes()


def test_launcher_requires_no_bytecode_and_stage_zero_descriptor() -> None:
    source = (SOURCE_ROOT / "scripts/rakuten_live_smoke_launcher.sh").read_text(
        encoding="utf-8"
    )
    cli_payload = (SOURCE_ROOT / "scripts/rakuten_live_smoke.py").read_bytes()
    expected_cli_hash = hashlib.sha256(cli_payload).hexdigest()
    assert f"expected_cli_sha256={expected_cli_hash}" in source
    assert '[ ! -L "$runtime_cli" ] || refuse "$command"' in source
    assert 'require_metadata "$runtime_cli" regular current 400' in source
    assert '[ "$cli_hash" = "$expected_cli_sha256  $runtime_cli" ]' in source
    assert source.index("cli_hash=$(\n") < source.index('exec 3<"$entry_path"')
    assert 'exec 3<"$entry_path" || refuse "$command"' in source
    assert '"$python" -B -I -S "$runtime_cli" "$command"' in source
    assert '[ "$runtime_root" = "$expected_runtime_parent/$bundle" ]' in source
    assert '[ "$entry_path" = "$launcher_dir/rakuten-live-smoke" ]' in source
    assert "stat -Lc '%d %i %f %u %a %h' /proc/self/fd/4" in source
    assert '[ "$outer_gate_metadata" = "$entry_gate_metadata" ]' in source
    assert "exec 4<&-" in source
    assert "pyvenv.cfg" in source


@pytest.mark.parametrize(
    ("command", "failure"),
    [
        ("doctor", b"RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY\n"),
        ("run", b"RAKUTEN_LIVE_SMOKE_FAIL\n"),
    ],
)
def test_root_owned_stage_zero_refuses_launcher_byte_drift_before_body(
    tmp_path: Path,
    command: str,
    failure: bytes,
) -> None:
    marker = tmp_path / "mutable-launcher-body-ran"
    malicious_launcher = tmp_path / "rakuten-live-smoke"
    malicious_launcher.write_text(
        f"#!/usr/bin/busybox sh\n/usr/bin/busybox touch {marker.as_posix()}\n",
        encoding="utf-8",
    )
    malicious_launcher.chmod(0o500)
    fixed_command = generator._authoritative_installed_command(command)  # noqa: SLF001
    test_command = fixed_command.replace(
        generator.INSTALLED_LAUNCHER_PATH,
        malicious_launcher.as_posix(),
    )
    result = subprocess.run(
        shlex.split(test_command),
        check=False,
        capture_output=True,
        env={"LD_PRELOAD": malicious_launcher.as_posix()},
    )
    assert result.returncode == 2
    assert result.stdout == failure
    assert result.stderr == b""
    assert not marker.exists()


def test_root_owned_stage_zero_passes_authenticated_fd4_to_exact_launcher(
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "rakuten-live-smoke"
    launcher.write_text(
        "#!/usr/bin/busybox sh\n"
        "gate=$(/usr/bin/busybox stat -Lc '%d %i %f %u %a %h' "
        "/proc/self/fd/4) || exit 3\n"
        "named=$(/usr/bin/busybox stat -c '%d %i %f %u %a %h' -- \"$0\") "
        "|| exit 3\n"
        '[ "$gate" = "$named" ] || exit 3\n'
        '[ "$1" = doctor ] || exit 3\n'
        "/usr/bin/busybox printf '%s\\n' OUTER_GATE_FD4_PASS\n",
        encoding="utf-8",
    )
    launcher.chmod(0o500)
    launcher_sha256 = hashlib.sha256(launcher.read_bytes()).hexdigest()
    fixed_command = generator._authoritative_installed_command("doctor")  # noqa: SLF001
    test_command = fixed_command.replace(
        generator.INSTALLED_LAUNCHER_PATH,
        launcher.as_posix(),
    ).replace(generator.EXPECTED_INSTALLED_LAUNCHER_SHA256, launcher_sha256)
    result = subprocess.run(
        shlex.split(test_command),
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == b"OUTER_GATE_FD4_PASS\n"
    assert result.stderr == b""
