#!/usr/bin/env python3
"""Create one owner-private WordPress MCP credential record without logging it."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
DIRECTORY: Final = ROOT / ".secrets/wordpress-mcp"
ORIGIN: Final = "https://kurashinoshirube.com"
PURPOSES: Final = {
    "editor_mcp": "editor-application-password.v1.json",
    "deployment_operator": "operator-application-password.v1.json",
}
APPLICATION_PASSWORD_NAMES: Final = {
    "editor_mcp": "RAOS Codex Editor MCP",
    "deployment_operator": "RAOS Codex Deployment Bridge",
}


class StoreFailure(RuntimeError):
    """Closed credential store failure."""


def fail(code: str) -> NoReturn:
    raise StoreFailure(code) from None


def secure_existing(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        fail("WORDPRESS_MCP_CREDENTIAL_READ_FAILED")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 1 <= len(payload) <= 16 * 1024
    ):
        fail("WORDPRESS_MCP_CREDENTIAL_INSECURE")
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("WORDPRESS_MCP_CREDENTIAL_INVALID")
    if type(value) is not dict:
        fail("WORDPRESS_MCP_CREDENTIAL_INVALID")
    return value


def ensure_directory() -> None:
    DIRECTORY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DIRECTORY, 0o700)
    metadata = DIRECTORY.lstat()
    if (
        DIRECTORY.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail("WORDPRESS_MCP_CREDENTIAL_DIRECTORY_INSECURE")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    result.add_argument("--purpose", choices=tuple(PURPOSES), required=True)
    result.add_argument("--replace-username", action="store_true")
    return result


def record_bytes(record: dict[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                record,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError:
        fail("WORDPRESS_MCP_CREDENTIAL_INVALID")


def replace_record(target: Path, payload: bytes) -> None:
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        written = os.write(descriptor, payload)
        if written != len(payload):
            fail("WORDPRESS_MCP_CREDENTIAL_WRITE_FAILED")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        directory_descriptor = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        fail("WORDPRESS_MCP_CREDENTIAL_WRITE_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            fail("WORDPRESS_MCP_CREDENTIAL_WRITE_FAILED")


def main() -> int:
    try:
        arguments = parser().parse_args()
        purpose = arguments.purpose
        ensure_directory()
        target = DIRECTORY / PURPOSES[purpose]
        if arguments.replace_username:
            record = secure_existing(target)
            if (
                record.get("schema") != "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1"
                or record.get("origin") != ORIGIN
                or record.get("purpose") != purpose
                or type(record.get("application_password")) is not str
            ):
                fail("WORDPRESS_MCP_CREDENTIAL_INVALID")
            username = input("Dedicated WordPress login username: ").strip()
            if (
                not username
                or len(username) > 100
                or username == APPLICATION_PASSWORD_NAMES[purpose]
            ):
                fail("WORDPRESS_MCP_CREDENTIAL_INPUT_INVALID")
            record["username"] = username
            replace_record(target, record_bytes(record))
            print("WORDPRESS_MCP_CREDENTIAL_USERNAME_UPDATED")
            return 0
        if target.exists() or target.is_symlink():
            fail("WORDPRESS_MCP_CREDENTIAL_ALREADY_EXISTS")
        username = input("Dedicated WordPress username: ").strip()
        password = getpass.getpass("Dedicated WordPress Application Password: ")
        if (
            not username
            or len(username) > 100
            or len(password) < 20
            or len(password) > 512
        ):
            fail("WORDPRESS_MCP_CREDENTIAL_INPUT_INVALID")
        other_purpose = (
            "deployment_operator" if purpose == "editor_mcp" else "editor_mcp"
        )
        other = DIRECTORY / PURPOSES[other_purpose]
        if other.exists():
            other_record = secure_existing(other)
            if other_record.get("application_password") == password:
                fail("WORDPRESS_MCP_CREDENTIAL_REUSE_FORBIDDEN")
        record = {
            "schema": "RAOS_WORDPRESS_APPLICATION_PASSWORD_V1",
            "origin": ORIGIN,
            "username": username,
            "application_password": password,
            "purpose": purpose,
        }
        payload = record_bytes(record)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags, 0o600)
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                fail("WORDPRESS_MCP_CREDENTIAL_WRITE_FAILED")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(target, 0o600)
        print("WORDPRESS_MCP_CREDENTIAL_STORED")
        return 0
    except StoreFailure as error:
        print(str(error), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
