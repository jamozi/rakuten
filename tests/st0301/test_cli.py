"""Safe deterministic CLI behavior."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

from .support import REPOSITORY_ROOT
from raos.migrations import catalog
from raos.migrations.cli import main


def test_verify_emits_one_deterministic_json_document() -> None:
    first = io.StringIO()
    second = io.StringIO()

    assert main(["verify"], repository_root=REPOSITORY_ROOT, stdout=first) == 0
    assert main(["verify"], repository_root=REPOSITORY_ROOT, stdout=second) == 0
    assert first.getvalue() == second.getvalue()
    value = json.loads(first.getvalue())
    assert value["status"] == "PASS"
    assert value["command"] == "verify"
    assert value["revision_source_count"] == len(catalog.REVISION_SPECS)
    assert value["checkpoint_source_count"] == 18
    assert set(value) == {
        "catalog_sha256",
        "changed",
        "checkpoint_source_count",
        "command",
        "current_revision",
        "environment",
        "revision_source_count",
        "status",
    }


def test_invalid_command_never_echoes_untrusted_input() -> None:
    canary = "private-command-canary"
    output = io.StringIO()

    assert main([canary], repository_root=REPOSITORY_ROOT, stdout=output) == 64
    assert canary not in output.getvalue()
    assert json.loads(output.getvalue()) == {
        "code": "MIG-CLI-001",
        "message": "invalid command arguments",
        "status": "ERROR",
    }


def test_invalid_port_and_environment_are_static_errors(tmp_path: Path) -> None:
    password = tmp_path / "private-path-canary"
    password.write_text("private-value-canary", encoding="utf-8")
    password.chmod(0o600)
    for environment, port in (("ENV-PRODUCTION", "5432"), ("ENV-CI", "bad-port")):
        output = io.StringIO()
        arguments = [
            "status",
            "--environment",
            environment,
            "--host",
            "127.0.0.1",
            "--port",
            port,
            "--database",
            "raos",
            "--user",
            "migrator",
            "--password-file",
            os.fspath(password),
        ]
        assert main(arguments, repository_root=REPOSITORY_ROOT, stdout=output) == 64
        rendered = output.getvalue()
        assert environment not in rendered
        assert port not in rendered
        assert os.fspath(password) not in rendered
        assert "private-value-canary" not in rendered


def test_verify_rejects_database_arguments() -> None:
    output = io.StringIO()
    assert (
        main(
            ["verify", "--host", "private-host-canary"],
            repository_root=REPOSITORY_ROOT,
            stdout=output,
        )
        == 64
    )
    assert "private-host-canary" not in output.getvalue()
