"""Installed-entry and hidden-input tests for the owner-local ST-0505 slice."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import subprocess
import sys
import termios
import pytest

from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator
from scripts import install_rakuten_owner_local_runtime as installer
from scripts import rakuten_owner_local as cli


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _read_pty_until(master_fd: int, marker: bytes) -> bytes:
    observed = bytearray()
    while marker not in observed:
        ready, _write, _errors = select.select([master_fd], [], [], 5)
        if not ready:
            raise AssertionError("PTY child timed out")
        observed.extend(os.read(master_fd, 4096))
    return bytes(observed)


def _tty_child(slave_name: str) -> subprocess.Popen[bytes]:
    code = r"""
import fcntl,importlib.machinery,importlib.util,os,sys,termios
fd=os.open(sys.argv[1],os.O_RDWR|os.O_CLOEXEC)
fcntl.ioctl(fd,termios.TIOCSCTTY,0)
p=sys.argv[2]
loader=importlib.machinery.SourceFileLoader('owner_local_cli',p)
spec=importlib.util.spec_from_loader('owner_local_cli',loader)
module=importlib.util.module_from_spec(spec)
loader.exec_module(module)
value=module._read_hidden_tty(b'Owner-local test prompt: ')
ok=value==b'tty-fixture'
module._wipe(value)
os.write(fd,b'TTY_PASS\n' if ok else b'TTY_FAIL\n')
os.close(fd)
raise SystemExit(0 if ok else 3)
"""
    return subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            code,
            slave_name,
            os.fspath(SOURCE_ROOT / "scripts/rakuten_owner_local.py"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _source_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for source, _installed, _mode in installer._PAYLOADS:  # noqa: SLF001
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE_ROOT / source, target)
        target.chmod(0o600)
    return root


def _bundle_digest(repository: Path) -> str:
    root_fd = installer._open_absolute_directory(repository)  # noqa: SLF001
    try:
        rows, _payloads = installer._payload_rows(root_fd)  # noqa: SLF001
    finally:
        os.close(root_fd)
    return hashlib.sha256(installer._canonical(rows)).hexdigest()  # noqa: SLF001


def _install(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repository = _source_repository(tmp_path)
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    bundle_digest = _bundle_digest(repository)
    assert (
        installer.install(repository, owner_base, bundle_digest) == installer.INSTALLED
    )
    bundle = owner_base / "raos/rakuten-owner-local/runtime" / bundle_digest
    return repository, owner_base, bundle, bundle_digest


def test_install_is_private_external_exact_and_idempotent(tmp_path: Path) -> None:
    repository, owner_base, bundle, digest = _install(tmp_path)
    assert not bundle.is_relative_to(repository)
    for directory in (
        owner_base / "raos",
        owner_base / "raos/rakuten-owner-local",
        owner_base / "raos/rakuten-owner-local/runtime",
        bundle,
        bundle / "bin",
        bundle / "scripts",
        bundle / "python",
    ):
        assert directory.stat().st_uid == os.getuid()
        assert directory.stat().st_mode & 0o777 == 0o700
        assert not directory.is_symlink()
    assert (bundle / "bin/rakuten-owner-local").stat().st_mode & 0o777 == 0o500
    assert (bundle / "scripts/rakuten_owner_local.py").stat().st_mode & 0o777 == 0o400
    manifest_path = bundle / "runtime-manifest.v1.json"
    assert manifest_path.stat().st_mode & 0o777 == 0o400
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest == {
        "schema": "RAOS_ST0505_OWNER_LOCAL_INSTALLED_RUNTIME_V1",
        "version": 1,
        "bundle_sha256": digest,
        "files": manifest["files"],
    }
    assert (
        installer.install(repository, owner_base, digest) == installer.ALREADY_INSTALLED
    )
    assert not tuple((bundle.parent).glob(".install-*"))


def test_install_is_credential_blind_with_existing_secret_tree(tmp_path: Path) -> None:
    repository = _source_repository(tmp_path)
    secret = repository / ".secrets/rakuten-owner-local/credentials.v1.json"
    secret.parent.mkdir(parents=True, mode=0o700)
    secret.write_bytes(b"opaque-sentinel\n")
    secret.chmod(0o000)
    before = secret.lstat()
    owner_base = tmp_path / "owner-base"
    owner_base.mkdir(mode=0o700)
    installer.install(repository, owner_base, _bundle_digest(repository))
    after = secret.lstat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )


def test_installed_runtime_verifies_before_dispatch_and_rejects_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository, owner_base, bundle, _digest = _install(tmp_path)
    monkeypatch.setattr(cli, "TRUSTED_OWNER_ROOT", owner_base / "raos")
    monkeypatch.setattr(
        cli,
        "TRUSTED_RUNTIME_PARENT",
        owner_base / "raos/rakuten-owner-local/runtime",
    )
    monkeypatch.setattr(cli, "__file__", str(bundle / "scripts/rakuten_owner_local.py"))
    assert cli._verify_installed_runtime() == bundle  # noqa: SLF001
    payload = bundle / "python/raos/adapters/rakuten_owner_local.py"
    payload.chmod(0o600)
    payload.write_bytes(payload.read_bytes() + b"\n# tamper\n")
    payload.chmod(0o400)
    with pytest.raises(RuntimeError, match="RUNTIME_UNTRUSTED"):
        cli._verify_installed_runtime()  # noqa: SLF001


def test_direct_repository_cli_refuses_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch_calls = 0

    def forbidden_dispatch(_arguments: tuple[str, ...]) -> tuple[int, str]:
        nonlocal dispatch_calls
        dispatch_calls += 1
        raise AssertionError("repository entry must not reach prompt or credentials")

    monkeypatch.setattr(cli, "_dispatch", forbidden_dispatch)
    assert cli.main(["setup"]) == 2
    assert capsys.readouterr() == ("RAKUTEN_OWNER_LOCAL_FAIL\n", "")
    assert dispatch_calls == 0


def test_direct_installer_refuses_before_runtime_mutation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_calls = 0

    def forbidden_install(*_args: object, **_kwargs: object) -> str:
        nonlocal install_calls
        install_calls += 1
        raise AssertionError("direct installer must not mutate")

    monkeypatch.setattr(installer, "install", forbidden_install)
    assert installer.main([]) == 1
    assert capsys.readouterr() == (
        "RAKUTEN_OWNER_LOCAL_RUNTIME_INSTALL_FAILED\n",
        "",
    )
    assert install_calls == 0


def test_cli_argument_surface_is_closed() -> None:
    for accepted in (
        ("setup",),
        ("rotate",),
        ("doctor",),
        ("list-apis",),
        ("request", "--api", "item-search", "--request-file", "/tmp/input.json"),
        ("smoke", "--api", "product-search"),
    ):
        assert cli._valid_arguments(accepted)  # noqa: SLF001
    for rejected in (
        (),
        ("run",),
        ("request", "--api", "other", "--request-file", "/tmp/input.json"),
        ("request", "--api", "item-search", "--request-file", "relative.json"),
        ("smoke", "--api", "item-search", "--endpoint", "https://example.test"),
        ("setup", "secret"),
    ):
        assert not cli._valid_arguments(rejected)  # noqa: SLF001


def _fake_request_launcher(
    tmp_path: Path,
    *,
    expected_request_file: str,
) -> tuple[Path, str]:
    request_file_sha256 = hashlib.sha256(expected_request_file.encode()).hexdigest()
    launcher = tmp_path / "rakuten-owner-local"
    launcher.write_text(
        "#!/usr/bin/busybox sh\n"
        '[ "$#" -eq 5 ] && [ "$1" = request ] && '
        '[ "$2" = --api ] && [ "$3" = item-search ] && '
        '[ "$4" = --request-file ] || exit 91\n'
        'h=$(/usr/bin/busybox printf "%s" "$5" | '
        "/usr/bin/busybox sha256sum) || exit 92\n"
        f'[ "$h" = "{request_file_sha256}  -" ] || exit 93\n'
        '/usr/bin/busybox printf "%s\\n" FAKE_REQUEST_EXECUTED\n',
        encoding="utf-8",
    )
    launcher.chmod(0o500)
    return launcher, hashlib.sha256(launcher.read_bytes()).hexdigest()


def _render_request_template(
    launcher: Path,
    launcher_sha256: str,
    *,
    api: str = "item-search",
    request_file: str = "/tmp/request.json",
) -> list[str]:
    argv = generator._owner_local_authoritative_request_argv_template()
    script = argv[10]
    assert isinstance(script, str)
    script = script.replace(
        generator.OWNER_LOCAL_INSTALLED_LAUNCHER_PATH,
        os.fspath(launcher),
    ).replace(generator.EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256, launcher_sha256)
    argv[10] = script
    argv[12] = api
    argv[13] = request_file
    return argv


def test_generated_request_template_authenticates_and_preserves_hostile_path(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "must-not-execute"
    request_file = f"/tmp/owner local/'quoted'/$(touch {sentinel});semi\nline.json"
    launcher, digest = _fake_request_launcher(
        tmp_path,
        expected_request_file=request_file,
    )
    result = subprocess.run(
        _render_request_template(
            launcher,
            digest,
            request_file=request_file,
        ),
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout == b"FAKE_REQUEST_EXECUTED\n"
    assert result.stderr == b""
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "arguments",
    (
        ("<item-search|product-search>", "<absolute-json>"),
        ("unknown-api", "/tmp/request.json"),
        ("item-search", "relative.json"),
        (),
        ("item-search", "/tmp/request.json", "extra"),
    ),
)
def test_generated_request_template_rejects_unrendered_invalid_or_extra_arguments(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    launcher, digest = _fake_request_launcher(
        tmp_path,
        expected_request_file="/tmp/request.json",
    )
    argv = _render_request_template(launcher, digest)
    del argv[12:]
    argv.extend(arguments)
    result = subprocess.run(argv, check=False, capture_output=True)
    assert result.returncode == 2
    assert result.stdout == b"RAKUTEN_OWNER_LOCAL_FAIL\n"
    assert result.stderr == b""


def test_generated_request_template_rejects_launcher_tamper_before_body(
    tmp_path: Path,
) -> None:
    launcher, digest = _fake_request_launcher(
        tmp_path,
        expected_request_file="/tmp/request.json",
    )
    argv = _render_request_template(launcher, digest)
    launcher.chmod(0o700)
    launcher.write_bytes(launcher.read_bytes() + b"# tampered\n")
    launcher.chmod(0o500)
    result = subprocess.run(argv, check=False, capture_output=True)
    assert result.returncode == 2
    assert result.stdout == b"RAKUTEN_OWNER_LOCAL_FAIL\n"
    assert result.stderr == b""


def test_hidden_capture_repeats_confirms_and_wipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter(
        [
            bytearray(b"app-fixture"),
            bytearray(b"app-fixture"),
            bytearray(b"key-fixture"),
            bytearray(b"key-fixture"),
            bytearray(b"affiliate-fixture"),
            bytearray(b"affiliate-fixture"),
            bytearray(b"YES"),
        ]
    )
    captured: list[bytearray] = []

    def fake_read(_prompt: bytes, *, maximum: int = 4096) -> bytearray:
        del maximum
        value = next(values)
        captured.append(value)
        return value

    monkeypatch.setattr(cli, "_disable_process_disclosure", lambda: None)
    monkeypatch.setattr(cli, "_read_hidden_tty", fake_read)
    credentials = cli._capture_credentials()  # noqa: SLF001
    assert credentials.application_id_query_value() == "app-fixture"
    assert credentials.access_key_header_value() == "key-fixture"
    assert credentials.affiliate_id_query_value() == "affiliate-fixture"
    assert all(value == bytearray() for value in captured)
    assert "fixture" not in repr(credentials)


def test_hidden_capture_refuses_mismatch_and_wipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = [bytearray(b"one"), bytearray(b"two")]
    values = iter(captured)
    monkeypatch.setattr(cli, "_disable_process_disclosure", lambda: None)
    monkeypatch.setattr(
        cli,
        "_read_hidden_tty",
        lambda _prompt, maximum=4096: next(values),
    )
    with pytest.raises(RuntimeError, match="TTY_CONFIRMATION_FAILED"):
        cli._capture_credentials()  # noqa: SLF001
    assert all(value == bytearray() for value in captured)


def test_real_tty_input_is_hidden_and_restored() -> None:
    master_fd, slave_fd = pty.openpty()
    try:
        original = termios.tcgetattr(slave_fd)
        child = _tty_child(os.ttyname(slave_fd))
        before = _read_pty_until(master_fd, b"Owner-local test prompt: ")
        os.write(master_fd, b"tty-fixture\n")
        after = _read_pty_until(master_fd, b"TTY_PASS")
        assert child.wait(timeout=5) == 0
        assert b"tty-fixture" not in before + after
        restored = termios.tcgetattr(slave_fd)
        assert restored == original
    finally:
        os.close(master_fd)
        os.close(slave_fd)


def test_real_tty_signal_restores_echo_before_refusal() -> None:
    master_fd, slave_fd = pty.openpty()
    child: subprocess.Popen[bytes] | None = None
    try:
        original = termios.tcgetattr(slave_fd)
        child = _tty_child(os.ttyname(slave_fd))
        _read_pty_until(master_fd, b"Owner-local test prompt: ")
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=5) != 0
        restored = termios.tcgetattr(slave_fd)
        assert restored == original
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        os.close(master_fd)
        os.close(slave_fd)


def test_setup_and_rotate_preflight_before_hidden_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Store:
        def setup_ready(self) -> None:
            events.append("setup-ready")
            raise RuntimeError("blocked")

        def rotate_ready(self) -> None:
            events.append("rotate-ready")
            raise RuntimeError("blocked")

    monkeypatch.setattr(cli, "_production_store", Store)
    monkeypatch.setattr(
        cli,
        "_capture_credentials",
        lambda: (_ for _ in ()).throw(AssertionError("TTY must not be opened")),
    )
    with pytest.raises(RuntimeError, match="blocked"):
        cli._dispatch(("setup",))  # noqa: SLF001
    with pytest.raises(RuntimeError, match="blocked"):
        cli._dispatch(("rotate",))  # noqa: SLF001
    assert events == ["setup-ready", "rotate-ready"]


def test_launcher_and_installer_stages_are_static_env_clean_and_parse() -> None:
    launcher = SOURCE_ROOT / "scripts/rakuten_owner_local_launcher.sh"
    stage = SOURCE_ROOT / "scripts/rakuten_owner_local_runtime_install.sh"
    for path in (launcher, stage):
        source = path.read_text(encoding="utf-8")
        assert source.startswith("#!/usr/bin/busybox sh\n")
        assert "exec /usr/bin/busybox env -i" in source
        result = subprocess.run(
            ["/usr/bin/busybox", "sh", "-n", os.fspath(path)],
            check=False,
            capture_output=True,
        )
        assert result.returncode == 0
        assert result.stdout == result.stderr == b""


def test_launcher_checks_exact_cli_hash_and_passes_only_closed_arguments() -> None:
    launcher = (SOURCE_ROOT / "scripts/rakuten_owner_local_launcher.sh").read_text(
        encoding="utf-8"
    )
    cli_hash = hashlib.sha256(
        (SOURCE_ROOT / "scripts/rakuten_owner_local.py").read_bytes()
    ).hexdigest()
    assert f"expected_cli_sha256={cli_hash}" in launcher
    assert '"$python" -B -I -S "$runtime_cli" "$@"' in launcher
    assert "request:5" in launcher and "smoke:3" in launcher


def test_installer_payload_inventory_matches_cli_inventory() -> None:
    expected = {
        installed: f"{mode:04o}"
        for _source, installed, mode in installer._PAYLOADS  # noqa: SLF001
    }
    assert cli._INSTALLED_PAYLOAD_MODES == expected  # noqa: SLF001


def test_no_existing_staging_runtime_file_is_changed() -> None:
    paths = (
        "scripts/rakuten_live_smoke.py",
        "scripts/rakuten_live_smoke_launcher.sh",
        "scripts/rakuten_live_smoke_runtime_install.sh",
        "scripts/install_rakuten_live_smoke_runtime.py",
        "python/raos/adapters/rakuten_live_smoke.py",
    )
    result = subprocess.run(
        ["git", "diff", "--exit-code", "origin/main", "--", *paths],
        cwd=SOURCE_ROOT,
        check=False,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")
