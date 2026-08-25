"""Runtime and structural checks for the ST-0106 network-denied boundary."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import time

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPOSITORY_ROOT / "scripts/run_network_denied.sh"
ASSERTION = REPOSITORY_ROOT / "scripts/assert_network_denied.py"
SYSTEM_PYTHON = Path("/usr/bin/python3")
OUTER_NETWORK_SANDBOX = os.environ.get("RAOS_NETWORK_DENIED") == "1"
UNSANDBOXED_PARENT_REASON = (
    "requires an unsandboxed parent to create or adversarially probe a fresh "
    "network/PID namespace; the outer ci-network-assert already reasserts its guard"
)
requires_unsandboxed_parent = pytest.mark.skipif(
    OUTER_NETWORK_SANDBOX,
    reason=UNSANDBOXED_PARENT_REASON,
)


def run_guard(
    home: Path,
    *command: str,
    extra_environment: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[str]:
    environment = {"PATH": os.defpath, "HOME": str(home)}
    if extra_environment:
        environment.update(extra_environment)
    return subprocess.run(
        [str(WRAPPER), "--home", str(home), "--", *command],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        pass_fds=pass_fds,
        timeout=20,
    )


def rebind_copied_wrapper_system_owner(content: str) -> str:
    """Keep hostile fallback fixtures reachable inside the outer user namespace."""
    fixed_helpers = (
        Path("/usr/bin/false"),
        Path("/usr/bin/setpriv"),
        Path("/usr/bin/sudo"),
        Path("/usr/bin/true"),
        Path("/usr/bin/unshare"),
    )
    helper_owners = {helper.stat().st_uid for helper in fixed_helpers}
    assert len(helper_owners) == 1
    helper_owner = helper_owners.pop()
    if helper_owner == 0:
        return content

    # The outer current-user namespace maps only the caller UID. Host-root
    # files therefore appear under the overflow UID while caller-owned hostile
    # fixtures retain the caller UID. Rebind only the mutation-only wrapper
    # copy so the later owner/mode/setuid checks remain distinguishable.
    uid_map_fields = Path("/proc/self/uid_map").read_text(encoding="utf-8").split()
    assert len(uid_map_fields) == 3
    assert int(uid_map_fields[0]) == os.geteuid()
    assert int(uid_map_fields[2]) == 1
    overflow_uid = int(
        Path("/proc/sys/kernel/overflowuid").read_text(encoding="utf-8").strip()
    )
    assert helper_owner == overflow_uid
    assert helper_owner != os.geteuid()
    replacements = {
        "[[ $unshare_owner != 0 ]]": f"[[ $unshare_owner != {helper_owner} ]]",
        "[[ $owner != 0 ]]": f"[[ $owner != {helper_owner} ]]",
    }
    for expected, replacement in replacements.items():
        assert content.count(expected) == 1
        content = content.replace(expected, replacement)
    return content


def test_network_wrapper_is_hardened_and_has_valid_shell() -> None:
    assert WRAPPER.is_file() and not WRAPPER.is_symlink()
    assert ASSERTION.is_file() and not ASSERTION.is_symlink()
    assert os.access(WRAPPER, os.X_OK)
    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    content = WRAPPER.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/bash -p\n\nPATH=/usr/bin:/bin")
    assert "exec env -i" in content
    assert "launch_mode=UNPRIVILEGED_USER_NAMESPACE" in content
    assert "launch_mode=PRIVILEGED_NAMESPACE_THEN_DROP" in content
    assert "--user --map-current-user --net --pid --fork" in content
    assert '"$sudo_executable" -n --' in content
    assert '"$unshare_executable" --net --pid --mount --fork --kill-child' in content
    assert (
        "--bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs"
        in content
    )
    fallback_launcher = content.split("else\n  launcher=(\n", maxsplit=1)[1].split(
        "\n  )\nfi", maxsplit=1
    )[0]
    assert fallback_launcher.index('"$unshare_executable"') < fallback_launcher.index(
        '"$setpriv_executable"'
    )
    assert fallback_launcher.index('"$setpriv_executable"') < fallback_launcher.index(
        '/usr/bin/python3 -I "$assertion" --exec --'
    )
    assert (
        '/usr/bin/python3 -I -c "$close_descriptors_program" \\\n'
        '    "$sudo_executable" -n -- /bin/true' in content
    )
    assert "--kill-child --" in content
    assert "EUID == 0" in content
    assert "RAOS_PARENT_NET_NS" in content
    assert "RAOS_PARENT_PID_NS" in content
    assert "RAOS_PARENT_MNT_NS" in content
    assert "RAOS_NETWORK_LAUNCH_MODE" in content
    assert "RAOS_NETWORK_DENIED=1" in content
    assert "/usr/bin/python3 -I" in content
    assert "close_range(3, (1 << 32) - 1, 0)" in content
    assert '"$assertion" --exec --' in content


def test_outer_sandbox_delegation_requires_a_real_guard() -> None:
    """Never accept RAOS_NETWORK_DENIED alone as evidence for delegated tests."""
    if not OUTER_NETWORK_SANDBOX:
        return

    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-I", str(ASSERTION)],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_NETWORK_DENIED": "1",
            "RAOS_PARENT_NET_NS": os.environ.get("RAOS_PARENT_NET_NS", ""),
            "RAOS_PARENT_PID_NS": os.environ.get("RAOS_PARENT_PID_NS", ""),
            "RAOS_PARENT_MNT_NS": os.environ.get("RAOS_PARENT_MNT_NS", ""),
            "RAOS_NETWORK_LAUNCH_MODE": os.environ.get("RAOS_NETWORK_LAUNCH_MODE", ""),
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "external_network": "DENIED",
        "launch_mode": os.environ["RAOS_NETWORK_LAUNCH_MODE"],
        "local_socketpair": "ALLOWED",
        "namespace": "ISOLATED",
        "process_namespace": "ISOLATED",
        "socket_api": "DENIED",
        "status": "PASS",
    }
    assert result.stderr == ""


@requires_unsandboxed_parent
def test_guard_creates_a_clean_network_namespace_before_child_execution(
    tmp_path: Path,
) -> None:
    if not SYSTEM_PYTHON.is_file():
        pytest.fail("ST-0106 requires /usr/bin/python3 on the Linux CI runner")
    startup_marker = tmp_path / "startup-ran"
    startup = tmp_path / "startup.sh"
    startup.write_text(f"touch {startup_marker}\n", encoding="utf-8")
    child = (
        "import errno,json,os,socket\n"
        "blocked={'BASH_ENV','GITHUB_TOKEN','HTTPS_PROXY','NODE_OPTIONS',"
        "'npm_config_ignore_scripts'}\n"
        "assert blocked.isdisjoint(os.environ)\n"
        "assert os.getuid()==os.geteuid()!=0\n"
        "assert os.getgid()==os.getegid()!=0\n"
        "try:\n"
        "    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
        "except OSError as error:\n"
        "    assert error.errno in {errno.EACCES,errno.EPERM}\n"
        "else:\n"
        "    s.close()\n"
        "    raise AssertionError('socket API remained available')\n"
        "print(json.dumps({'child':'PASS','network':'DENIED'},sort_keys=True))"
    )
    result = run_guard(
        tmp_path,
        str(SYSTEM_PYTHON),
        "-I",
        "-c",
        child,
        extra_environment={
            "BASH_ENV": str(startup),
            "GITHUB_TOKEN": "must-not-survive",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NODE_OPTIONS": "--require=must-not-survive",
            "npm_config_ignore_scripts": "false",
        },
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    lines = result.stdout.splitlines()
    assert json.loads(lines[0]) == {
        "external_network": "DENIED",
        "launch_mode": "UNPRIVILEGED_USER_NAMESPACE",
        "local_socketpair": "ALLOWED",
        "namespace": "ISOLATED",
        "process_namespace": "ISOLATED",
        "socket_api": "DENIED",
        "status": "PASS",
    }
    assert json.loads(lines[1]) == {"child": "PASS", "network": "DENIED"}
    assert result.stderr == ""
    assert not startup_marker.exists()


@requires_unsandboxed_parent
def test_guard_closes_an_inherited_connected_tcp_socket(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                child = (
                    "import errno,os,sys;fd=int(sys.argv[1]);"
                    "caught=False;"
                    "\ntry:os.write(fd,b'inherited-tcp-bypass')"
                    "\nexcept OSError as error:"
                    "caught=error.errno==errno.EBADF"
                    "\nassert caught;print('INHERITED_FD_CLOSED')"
                )
                result = run_guard(
                    tmp_path,
                    str(SYSTEM_PYTHON),
                    "-I",
                    "-c",
                    child,
                    str(client.fileno()),
                    pass_fds=(client.fileno(),),
                )
                assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
                assert result.stdout.splitlines()[-1] == "INHERITED_FD_CLOSED"
                peer.settimeout(0.1)
                with pytest.raises(TimeoutError):
                    peer.recv(1)


@requires_unsandboxed_parent
def test_guard_closes_a_high_socket_above_a_lowered_soft_limit(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                high_fd = fcntl.fcntl(client.fileno(), fcntl.F_DUPFD, 512)
                try:
                    launcher = (
                        "import os,resource,sys;"
                        "_,hard=resource.getrlimit(resource.RLIMIT_NOFILE);"
                        "resource.setrlimit(resource.RLIMIT_NOFILE,(64,hard));"
                        "os.execve(sys.argv[1],sys.argv[1:],os.environ)"
                    )
                    child = (
                        "import errno,os,sys;fd=int(sys.argv[1]);"
                        "caught=False;"
                        "\ntry:os.write(fd,b'high-fd-bypass')"
                        "\nexcept OSError as error:"
                        "caught=error.errno==errno.EBADF"
                        "\nassert caught;print('HIGH_FD_CLOSED')"
                    )
                    result = subprocess.run(
                        [
                            str(SYSTEM_PYTHON),
                            "-I",
                            "-c",
                            launcher,
                            str(WRAPPER),
                            "--home",
                            str(tmp_path),
                            "--",
                            str(SYSTEM_PYTHON),
                            "-I",
                            "-c",
                            child,
                            str(high_fd),
                        ],
                        cwd=REPOSITORY_ROOT,
                        env={"PATH": os.defpath, "HOME": str(tmp_path)},
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        pass_fds=(high_fd,),
                        timeout=20,
                    )
                finally:
                    os.close(high_fd)
                assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
                assert result.stdout.splitlines()[-1] == "HIGH_FD_CLOSED"
                peer.settimeout(0.1)
                with pytest.raises(TimeoutError):
                    peer.recv(1)


@requires_unsandboxed_parent
def test_guard_rejects_a_connected_socket_as_a_standard_descriptor(
    tmp_path: Path,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                result = subprocess.run(
                    [
                        str(WRAPPER),
                        "--home",
                        str(tmp_path),
                        "--",
                        str(SYSTEM_PYTHON),
                        "-I",
                        "-c",
                        "raise AssertionError('must not execute')",
                    ],
                    cwd=REPOSITORY_ROOT,
                    env={"PATH": os.defpath, "HOME": str(tmp_path)},
                    stdin=client.fileno(),
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=10,
                )
                assert result.returncode == 69
                assert result.stdout == ""
                assert result.stderr == ""


@requires_unsandboxed_parent
def test_guard_blocks_parent_namespace_pathname_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "parent-proxy.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        listener.listen(1)
        child = (
            "import errno,socket,sys;"
            "caught=False;"
            "\ntry:client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)"
            "\nexcept OSError as error:"
            "caught=error.errno in {errno.EACCES,errno.EPERM}"
            "\nelse:client.connect(sys.argv[1]);client.sendall(b'unix-bypass')"
            "\nassert caught;print('UNIX_SOCKET_BLOCKED')"
        )
        result = run_guard(
            tmp_path,
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            child,
            str(socket_path),
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert result.stdout.splitlines()[-1] == "UNIX_SOCKET_BLOCKED"
        listener.settimeout(0.1)
        with pytest.raises(TimeoutError):
            listener.accept()


@requires_unsandboxed_parent
def test_guard_kills_background_descendants_before_returning(tmp_path: Path) -> None:
    marker = tmp_path / "background-survived"
    child = (
        "import os,sys,time;"
        "pid=os.fork();"
        "\nif pid==0:"
        "\n time.sleep(0.5);open(sys.argv[1],'w',encoding='utf-8').write('escape')"
        "\nelse:"
        "\n print('PARENT_EXITING')"
    )

    result = run_guard(
        tmp_path,
        str(SYSTEM_PYTHON),
        "-I",
        "-c",
        child,
        str(marker),
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert result.stdout.splitlines()[-1] == "PARENT_EXITING"
    time.sleep(0.7)
    assert not marker.exists()


def test_assertion_rejects_the_parent_network_namespace() -> None:
    parent = os.readlink("/proc/self/ns/net")
    parent_pid = os.readlink("/proc/self/ns/pid")
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-I", str(ASSERTION)],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_PARENT_NET_NS": parent,
            "RAOS_PARENT_PID_NS": parent_pid,
            "RAOS_NETWORK_LAUNCH_MODE": "UNPRIVILEGED_USER_NAMESPACE",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "network_isolation=namespace-not-isolated" in result.stderr


@requires_unsandboxed_parent
def test_assertion_rejects_a_root_mapped_child_namespace() -> None:
    parent = os.readlink("/proc/self/ns/net")
    parent_pid = os.readlink("/proc/self/ns/pid")
    result = subprocess.run(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--net",
            "--pid",
            "--fork",
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            str(ASSERTION),
        ],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_PARENT_NET_NS": parent,
            "RAOS_PARENT_PID_NS": parent_pid,
            "RAOS_NETWORK_LAUNCH_MODE": "UNPRIVILEGED_USER_NAMESPACE",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "network_isolation=privileged-identity" in result.stderr


def test_assertion_rejects_an_unknown_launch_mode() -> None:
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-I", str(ASSERTION)],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_NETWORK_LAUNCH_MODE": "untrusted",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "network_isolation=launch-mode-invalid" in result.stderr


def test_assertion_requires_a_fresh_fallback_mount_namespace() -> None:
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-I", str(ASSERTION)],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_NETWORK_LAUNCH_MODE": "PRIVILEGED_NAMESPACE_THEN_DROP",
            "RAOS_PARENT_NET_NS": "net:[1]",
            "RAOS_PARENT_PID_NS": "pid:[1]",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "network_isolation=parent-mount-namespace-missing" in result.stderr


@requires_unsandboxed_parent
def test_assertion_rejects_a_reused_fallback_mount_namespace() -> None:
    parent_network = os.readlink("/proc/self/ns/net")
    parent_pid = os.readlink("/proc/self/ns/pid")
    parent_mount = os.readlink("/proc/self/ns/mnt")
    result = subprocess.run(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-current-user",
            "--net",
            "--pid",
            "--fork",
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            str(ASSERTION),
        ],
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "RAOS_NETWORK_LAUNCH_MODE": "PRIVILEGED_NAMESPACE_THEN_DROP",
            "RAOS_PARENT_NET_NS": parent_network,
            "RAOS_PARENT_PID_NS": parent_pid,
            "RAOS_PARENT_MNT_NS": parent_mount,
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "network_isolation=mount-namespace-not-isolated" in result.stderr


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (
            "Groups:\t1000\n"
            "CapInh:\t0000000000000000\n"
            "CapPrm:\t0000000000000000\n"
            "CapEff:\t0000000000000000\n"
            "CapBnd:\t0000000000000000\n"
            "CapAmb:\t0000000000000000\n",
            "supplementary-groups-present",
        ),
        (
            "Groups:\t\n"
            "CapInh:\t0000000000000000\n"
            "CapPrm:\t0000000000000000\n"
            "CapEff:\t0000000000000000\n"
            "CapBnd:\t00000000a80425fb\n"
            "CapAmb:\t0000000000000000\n",
            "capabilities-present",
        ),
    ],
)
def test_fallback_attestation_rejects_residual_privilege(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected_error: str,
) -> None:
    assertion_globals = runpy.run_path(str(ASSERTION))
    assert_privilege_drop = assertion_globals["assert_privilege_drop"]

    class FakePath:
        def __init__(self, _path: str) -> None:
            pass

        def read_bytes(self) -> bytes:
            return status.encode("ascii")

    monkeypatch.setitem(assert_privilege_drop.__globals__, "Path", FakePath)
    with pytest.raises(SystemExit) as raised:
        assert_privilege_drop()
    assert raised.value.code == 2
    assert f"network_isolation={expected_error}" in capsys.readouterr().err


def test_wrapper_rejects_an_untrusted_unshare_helper(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_wrapper = scripts / WRAPPER.name
    copied_assertion = scripts / ASSERTION.name
    shutil.copy2(WRAPPER, copied_wrapper)
    shutil.copy2(ASSERTION, copied_assertion)
    fake_unshare = tmp_path / "unshare"
    fake_unshare.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_unshare.chmod(0o755)
    copied_wrapper.write_text(
        copied_wrapper.read_text(encoding="utf-8").replace(
            "unshare_executable=/usr/bin/unshare",
            f"unshare_executable={fake_unshare}",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(copied_wrapper),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise AssertionError('must not execute')",
        ],
        cwd=repository,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert "unshare executable ownership or mode is unsafe" in result.stderr


def test_wrapper_rejects_a_symlinked_unshare_helper(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_wrapper = scripts / WRAPPER.name
    copied_assertion = scripts / ASSERTION.name
    shutil.copy2(WRAPPER, copied_wrapper)
    shutil.copy2(ASSERTION, copied_assertion)
    fake_unshare = tmp_path / "unshare-link"
    fake_unshare.symlink_to("/usr/bin/false")
    copied_wrapper.write_text(
        copied_wrapper.read_text(encoding="utf-8").replace(
            "unshare_executable=/usr/bin/unshare",
            f"unshare_executable={fake_unshare}",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(copied_wrapper),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise AssertionError('must not execute')",
        ],
        cwd=repository,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert "trusted unshare executable is unavailable" in result.stderr


def test_wrapper_rejects_an_untrusted_setpriv_helper(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_wrapper = scripts / WRAPPER.name
    copied_assertion = scripts / ASSERTION.name
    shutil.copy2(WRAPPER, copied_wrapper)
    shutil.copy2(ASSERTION, copied_assertion)
    fake_setpriv = tmp_path / "setpriv"
    fake_setpriv.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_setpriv.chmod(0o755)
    copied_wrapper.write_text(
        rebind_copied_wrapper_system_owner(copied_wrapper.read_text(encoding="utf-8"))
        .replace(
            "unshare_executable=/usr/bin/unshare", "unshare_executable=/usr/bin/false"
        )
        .replace(
            "readonly setpriv_executable=/usr/bin/setpriv",
            f"readonly setpriv_executable={fake_setpriv}",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(copied_wrapper),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise AssertionError('must not execute')",
        ],
        cwd=repository,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert "setpriv executable ownership or mode is unsafe" in result.stderr


@pytest.mark.parametrize(
    ("sudo_path", "expected_error"),
    [
        ("MISSING", "trusted sudo executable is unavailable"),
        ("/usr/bin/true", "sudo executable is not set-user-ID root"),
    ],
)
def test_wrapper_rejects_an_unavailable_or_non_setuid_sudo_helper(
    tmp_path: Path,
    sudo_path: str,
    expected_error: str,
) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_wrapper = scripts / WRAPPER.name
    copied_assertion = scripts / ASSERTION.name
    shutil.copy2(WRAPPER, copied_wrapper)
    shutil.copy2(ASSERTION, copied_assertion)
    effective_sudo_path = (
        str(tmp_path / "missing-sudo") if sudo_path == "MISSING" else sudo_path
    )
    copied_wrapper.write_text(
        rebind_copied_wrapper_system_owner(copied_wrapper.read_text(encoding="utf-8"))
        .replace(
            "unshare_executable=/usr/bin/unshare", "unshare_executable=/usr/bin/false"
        )
        .replace(
            "readonly sudo_executable=/usr/bin/sudo",
            f"readonly sudo_executable={effective_sudo_path}",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(copied_wrapper),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise AssertionError('must not execute')",
        ],
        cwd=repository,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert expected_error in result.stderr


def test_wrapper_rejects_a_failed_passwordless_sudo_preflight(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_wrapper = scripts / WRAPPER.name
    copied_assertion = scripts / ASSERTION.name
    shutil.copy2(WRAPPER, copied_wrapper)
    shutil.copy2(ASSERTION, copied_assertion)
    copied_wrapper.write_text(
        rebind_copied_wrapper_system_owner(copied_wrapper.read_text(encoding="utf-8"))
        .replace(
            "unshare_executable=/usr/bin/unshare", "unshare_executable=/usr/bin/false"
        )
        .replace(
            '"$sudo_executable" -n -- /bin/true >/dev/null 2>&1',
            '"$sudo_executable" -n -- /bin/false >/dev/null 2>&1',
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(copied_wrapper),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise AssertionError('must not execute')",
        ],
        cwd=repository,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert "trusted passwordless sudo fallback is not authorized" in result.stderr


@requires_unsandboxed_parent
def test_wrapper_rejects_a_root_mapped_caller(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--",
            str(WRAPPER),
            "--home",
            str(tmp_path),
            "--",
            str(SYSTEM_PYTHON),
            "-I",
            "-c",
            "raise SystemExit(0)",
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 69
    assert result.stdout == ""
    assert "must start as a non-root user" in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--home", "relative", "--", "/usr/bin/python3"],
        ["--home", "/tmp", "/usr/bin/python3"],
        ["--home", "/tmp", "--", "python3"],
    ],
)
def test_network_wrapper_rejects_an_extended_or_ambiguous_cli(
    arguments: list[str],
) -> None:
    result = subprocess.run(
        [str(WRAPPER), *arguments],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath, "HOME": str(REPOSITORY_ROOT)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr.lower() or "error:" in result.stderr.lower()


def test_ci_wrapper_runs_only_network_denied_repository_checks() -> None:
    ci_wrapper = (REPOSITORY_ROOT / "scripts/ci_job.sh").read_text(encoding="utf-8")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ci-hydrate: python-sync node-sync" in makefile
    for target in ("ci-static", "ci-unit", "ci-contracts"):
        header = next(
            line for line in makefile.splitlines() if line.startswith(f"{target}:")
        )
        assert "ci-network-assert" in header
    for target in ("ci-database", "ci-storage"):
        header = next(
            line for line in makefile.splitlines() if line.startswith(f"{target}:")
        )
        assert "ci-network-assert" not in header
    assert "ci-storage" not in ci_wrapper
    assert "ci-hydrate" not in ci_wrapper
    assert "dependency-hydration" not in ci_wrapper
    assert "CI_PHASE network=denied purpose=repository-checks" in ci_wrapper
    assert "RAOS_CI_OFFLINE=1" in ci_wrapper
    assert '"$network_wrapper" --home' in ci_wrapper


@pytest.mark.parametrize("value", ["", "00", "2", "0 1", "1 "])
def test_make_rejects_noncanonical_ci_offline_values(value: str) -> None:
    result = subprocess.run(
        [
            "/usr/bin/make",
            "--no-builtin-rules",
            "--no-builtin-variables",
            "--file",
            str(REPOSITORY_ROOT / "Makefile"),
            "ci-network-assert",
            f"RAOS_CI_OFFLINE={value}",
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode != 0
    assert "RAOS_CI_OFFLINE must be 0 or 1" in result.stderr
