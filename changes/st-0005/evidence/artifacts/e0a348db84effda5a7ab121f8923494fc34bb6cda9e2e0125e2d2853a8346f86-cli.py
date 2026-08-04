"""JSON-only command interface for the ST-0301 migration runner."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn, TextIO

from .catalog import CatalogError
from .runner import (
    DatabaseTarget,
    MigrationEnvironment,
    MigrationError,
    MigrationRunner,
    verification_result,
    verify_repository,
)


class _UsageError(RuntimeError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _UsageError


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m raos.migrations", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")
    for name in ("status", "upgrade"):
        command = subparsers.add_parser(name)
        command.add_argument("--environment", required=True)
        command.add_argument("--host", required=True)
        command.add_argument("--port", required=True)
        command.add_argument("--database", required=True)
        command.add_argument("--user", required=True)
        command.add_argument("--password-file", required=True)
    return parser


def _write(value: dict[str, object], stream: TextIO) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _target(namespace: argparse.Namespace) -> DatabaseTarget:
    try:
        environment = MigrationEnvironment(namespace.environment)
    except TypeError, ValueError:
        raise _UsageError from None
    if (
        type(namespace.port) is not str
        or re.fullmatch(r"[0-9]{1,5}", namespace.port) is None
    ):
        raise _UsageError
    return DatabaseTarget(
        environment=environment,
        host=namespace.host,
        port=int(namespace.port),
        database=namespace.database,
        user=namespace.user,
        password_file=Path(namespace.password_file),
    )


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run one command and emit exactly one safe JSON object."""

    output = sys.stdout if stdout is None else stdout
    root = (
        Path(__file__).resolve().parents[3]
        if repository_root is None
        else repository_root
    )
    try:
        namespace = _parser().parse_args(argv)
        if namespace.command == "verify":
            result = verification_result(verify_repository(root))
        else:
            runner = MigrationRunner(root, _target(namespace))
            result = (
                runner.status() if namespace.command == "status" else runner.upgrade()
            )
        _write(result.public_dict(), output)
        return 0
    except _UsageError:
        _write(
            {
                "code": "MIG-CLI-001",
                "message": "invalid command arguments",
                "status": "ERROR",
            },
            output,
        )
        return 64
    except (CatalogError, MigrationError) as error:
        _write(
            {
                "code": error.code.value,
                "message": str(error),
                "status": "ERROR",
            },
            output,
        )
        return 1
    except Exception:
        _write(
            {
                "code": "MIG-CLI-002",
                "message": "migration command failed",
                "status": "ERROR",
            },
            output,
        )
        return 1
