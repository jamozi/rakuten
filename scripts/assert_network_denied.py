#!/usr/bin/env python3
"""Fail unless the process is inside a fresh, route-less network namespace."""

from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import re
import socket
import sys


NETWORK_NAMESPACE = re.compile(r"net:\[(?P<inode>[1-9][0-9]*)\]")
PID_NAMESPACE = re.compile(r"pid:\[(?P<inode>[1-9][0-9]*)\]")
EXPECTED_CONNECT_ERRORS = {
    errno.EACCES,
    errno.EADDRNOTAVAIL,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETUNREACH,
    errno.EPERM,
}
AUDIT_ARCH_X86_64 = 0xC000003E
BPF_LD_W_ABS = 0x20
BPF_JMP_JEQ_K = 0x15
BPF_RET_K = 0x06
PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_KILL_PROCESS = 0x80000000
SOCKET_SYSCALLS_X86_64 = (
    41,  # socket
    42,  # connect
    43,  # accept
    49,  # bind
    50,  # listen
    288,  # accept4
    425,  # io_uring_setup
    426,  # io_uring_enter
    427,  # io_uring_register
)


class SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class SockFprog(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ushort),
        ("filters", ctypes.POINTER(SockFilter)),
    ]


def fail(code: str) -> None:
    print(f"ERROR network_isolation={code}", file=sys.stderr)
    raise SystemExit(2)


def namespace(path: str, pattern: re.Pattern[str]) -> str:
    try:
        value = os.readlink(path)
    except OSError:
        fail("namespace-unreadable")
    if pattern.fullmatch(value) is None:
        fail("namespace-malformed")
    return value


def interfaces() -> set[str]:
    try:
        lines = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
    except OSError:
        fail("interfaces-unreadable")
    except UnicodeError:
        fail("interfaces-unreadable")
    observed: set[str] = set()
    for line in lines:
        name, separator, _ = line.partition(":")
        if separator != ":":
            fail("interfaces-malformed")
        observed.add(name.strip())
    return observed


def assert_unreachable(
    family: socket.AddressFamily, address: tuple[object, ...]
) -> None:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(0.25)
            result = client.connect_ex(address)
    except OSError as error:
        result = error.errno or 0
    if result not in EXPECTED_CONNECT_ERRORS:
        fail("outbound-route-present")


def assert_namespace_and_routes(*, require_namespace_init: bool) -> None:
    parent_network = os.environ.get("RAOS_PARENT_NET_NS", "")
    if NETWORK_NAMESPACE.fullmatch(parent_network) is None:
        fail("parent-namespace-missing")
    current_network = namespace("/proc/self/ns/net", NETWORK_NAMESPACE)
    if current_network == parent_network:
        fail("namespace-not-isolated")
    parent_pid = os.environ.get("RAOS_PARENT_PID_NS", "")
    if PID_NAMESPACE.fullmatch(parent_pid) is None:
        fail("parent-process-namespace-missing")
    current_pid = namespace("/proc/self/ns/pid", PID_NAMESPACE)
    if current_pid == parent_pid or (require_namespace_init and os.getpid() != 1):
        fail("process-namespace-not-isolated")
    if os.getuid() == 0 or os.geteuid() == 0 or os.getgid() == 0 or os.getegid() == 0:
        fail("privileged-identity")
    if os.getuid() != os.geteuid() or os.getgid() != os.getegid():
        fail("identity-mismatch")
    if interfaces() != {"lo"}:
        fail("non-loopback-interface-present")

    assert_unreachable(socket.AF_INET, ("192.0.2.1", 9))
    if socket.has_ipv6:
        assert_unreachable(socket.AF_INET6, ("2001:db8::1", 9, 0, 0))


def install_socket_filter() -> None:
    if os.uname().machine != "x86_64":
        fail("unsupported-seccomp-architecture")

    instructions = [
        SockFilter(BPF_LD_W_ABS, 0, 0, 4),
        SockFilter(BPF_JMP_JEQ_K, 1, 0, AUDIT_ARCH_X86_64),
        SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS),
        SockFilter(BPF_LD_W_ABS, 0, 0, 0),
    ]
    for syscall_number in SOCKET_SYSCALLS_X86_64:
        instructions.extend(
            (
                SockFilter(BPF_JMP_JEQ_K, 0, 1, syscall_number),
                SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM),
            )
        )
    instructions.append(SockFilter(BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW))

    filters = (SockFilter * len(instructions))(*instructions)
    program = SockFprog(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        fail("no-new-privileges-unavailable")
    if libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(program)) != 0:
        fail("socket-filter-unavailable")


def assert_socket_filter() -> None:
    try:
        status = Path("/proc/self/status").read_text(encoding="ascii")
    except OSError:
        fail("process-status-unreadable")
    except UnicodeError:
        fail("process-status-unreadable")
    if not re.search(r"(?m)^NoNewPrivs:\s+1$", status):
        fail("no-new-privileges-missing")
    if not re.search(r"(?m)^Seccomp:\s+2$", status):
        fail("socket-filter-missing")
    try:
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError as error:
        if error.errno not in {errno.EACCES, errno.EPERM}:
            fail("socket-filter-unexpected-error")
    else:
        fail("socket-api-available")
    try:
        first, second = socket.socketpair()
        first.close()
        second.close()
    except OSError:
        fail("local-socketpair-unavailable")


def print_report() -> None:
    print(
        json.dumps(
            {
                "external_network": "DENIED",
                "local_socketpair": "ALLOWED",
                "namespace": "ISOLATED",
                "process_namespace": "ISOLATED",
                "socket_api": "DENIED",
                "status": "PASS",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def main(arguments: list[str]) -> int:
    exec_arguments: list[str] | None = None
    if arguments:
        if len(arguments) < 3 or arguments[:2] != ["--exec", "--"]:
            fail("invalid-cli")
        if not os.path.isabs(arguments[2]):
            fail("exec-command-not-absolute")
        exec_arguments = arguments[2:]

    assert_namespace_and_routes(require_namespace_init=exec_arguments is not None)
    if exec_arguments is not None:
        install_socket_filter()
    if os.environ.get("RAOS_NETWORK_DENIED") == "1":
        assert_socket_filter()
    print_report()
    if exec_arguments is not None:
        sys.stdout.flush()
        try:
            os.execv(exec_arguments[0], exec_arguments)
        except OSError:
            fail("exec-failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
