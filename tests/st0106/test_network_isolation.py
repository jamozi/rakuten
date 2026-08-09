"""Runtime and structural checks for the ST-0106 network-denied boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
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


def _unprivileged_user_namespaces_available() -> bool:
    result = subprocess.run(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-current-user",
            "--",
            "/bin/true",
        ],
        cwd=REPOSITORY_ROOT,
        env={"PATH": os.defpath},
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    return result.returncode == 0


USER_NAMESPACE_AVAILABLE = _unprivileged_user_namespaces_available()
requires_user_namespace = pytest.mark.skipif(
    not USER_NAMESPACE_AVAILABLE,
    reason="host does not permit unprivileged user-namespace setup for this negative fixture",
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
    assert "launch_mode=user_namespace" in content
    assert "launch_mode=privileged_namespace_then_drop" in content
    assert (
        '"$unshare_executable" --user --map-current-user --net --pid --fork' in content
    )
    assert (
        '"$unshare_executable" --net --pid --fork --kill-child --mount-proc' in content
    )
    assert "trusted passwordless sudo fallback" in content
    assert '"$sudo_executable" -n --' in content
    assert (
        '--reuid="$caller_uid" --regid="$caller_gid" --clear-groups --no-new-privs'
        in content
    )
    assert "--kill-child --" in content
    assert "EUID == 0" in content
    assert "RAOS_PARENT_NET_NS" in content
    assert "RAOS_PARENT_PID_NS" in content
    assert "RAOS_NETWORK_DENIED=1" in content
    assert "/usr/bin/python3 -I" in content
    assert "os.closerange" in content
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


@requires_user_namespace
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


@requires_user_namespace
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
