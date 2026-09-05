#!/usr/bin/env python3
"""Execute one portless backup-restore rehearsal on a separate local Docker project."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "python"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import raos_wordpress_local_restore as local_restore  # noqa: E402
from raos.application.editorial.local_scratch_restore_v1 import (  # noqa: E402
    build_scratch_restoration,
    verify_scratch_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    IncrementalPublicationFailure,
    canonical,
    digest,
    fail,
    validate_hash,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    read_private_bytes,
    read_private_json,
    write_private_bytes,
)

DOCKER = ("/usr/bin/docker", "--host", "unix:///var/run/docker.sock")
COMPOSE = ROOT / "changes/wordpress-local-preview-v1/scratch-restore.compose.yaml"


def run_command(
    arguments: list[str],
    *,
    phase: str,
    input_bytes: bytes | None = None,
    required: bool = True,
    timeout: int = 180,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        arguments,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if required and result.returncode:
        match = re.search(rb"RAOS_SCRATCH_[A-Z_]+", result.stdout + result.stderr)
        fail(match.group().decode() if match else f"SCRATCH_{phase}_FAILED")
    return result


def execute(preparation_sha256: str) -> Path:
    validate_hash(preparation_sha256)
    _, baseline = local_restore.prepared_restoration(preparation_sha256)
    snapshot_name = baseline.preparation["snapshot_name"]
    if type(snapshot_name) is not str:
        fail("SCRATCH_SNAPSHOT_INVALID")
    snapshot_root = local_restore.owner_root() / "incremental-snapshots"
    snapshot = read_private_json(snapshot_root, snapshot_name)
    environment_id = preparation_sha256[:8] + "-" + secrets.token_hex(6)
    project = "raos-wp-scratch-" + environment_id
    private = local_restore.owner_root() / ("scratch-restore-" + environment_id)
    if private.exists() or private.is_symlink() or os.getuid() == 0 or os.getgid() == 0:
        fail("SCRATCH_ENVIRONMENT_INVALID")
    expected = build_scratch_restoration(
        snapshot,
        article_slugs=local_restore.production_article_slugs(),
        preparation_sha256=preparation_sha256,
        environment_id=environment_id,
    )
    admin_password = secrets.token_hex(32)
    credentials = {
        "RAOS_SCRATCH_DB_PASSWORD": secrets.token_hex(32),
        "RAOS_SCRATCH_ROOT_PASSWORD": secrets.token_hex(32),
        "RAOS_SCRATCH_ENVIRONMENT": environment_id,
        "RAOS_SCRATCH_SEED_SHA256": digest(expected.seed),
        "RAOS_SCRATCH_UID": str(os.getuid()),
        "RAOS_SCRATCH_GID": str(os.getgid()),
        "RAOS_SCRATCH_SOURCE_ROOT": str(ROOT),
        "RAOS_SCRATCH_PRIVATE_ROOT": str(private),
    }
    if any(
        "\n" in value or "\r" in value or "=" in value for value in credentials.values()
    ):
        fail("SCRATCH_ENVIRONMENT_INVALID")
    write_private_bytes(
        private,
        "credentials.env",
        (
            "\n".join(f"{key}={value}" for key, value in credentials.items()) + "\n"
        ).encode(),
    )
    write_private_bytes(
        private,
        "source-snapshot.v1.json",
        read_private_bytes(snapshot_root, snapshot_name),
    )
    write_private_bytes(private, "scratch-seed.v1.json", expected.seed)
    for slug, body in expected.bodies.items():
        write_private_bytes(private / "content", f"{slug}.html", body)
    command = [
        *DOCKER,
        "compose",
        "--project-name",
        project,
        "--project-directory",
        str(COMPOSE.parent),
        "--env-file",
        str(private / "credentials.env"),
        "--file",
        str(COMPOSE),
    ]
    run_command(
        [*DOCKER, "info", "--format", "{{.ServerVersion}}"], phase="LOCAL_DOCKER"
    )
    for volume in ("scratch_database", "scratch_wordpress"):
        if (
            run_command(
                [*DOCKER, "volume", "inspect", f"{project}_{volume}"],
                phase="VOLUME_CHECK",
                required=False,
            ).returncode
            == 0
        ):
            fail("SCRATCH_VOLUME_ALREADY_EXISTS")
    started = False
    verified = False
    try:
        started = True
        print(
            "Scratch restore: starting a separate, portless local environment",
            flush=True,
        )
        run_command(
            [
                *command,
                "up",
                "--detach",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "120",
                "database",
                "wordpress",
            ],
            phase="START",
        )
        wp = [*command, "run", "--rm", "--no-deps", "-T", "cli"]
        for attempt in range(30):
            if (
                run_command(
                    [*wp, "core", "version"], phase="BOOT", required=False, timeout=30
                ).returncode
                == 0
            ):
                break
            if attempt == 29:
                fail("SCRATCH_BOOT_TIMEOUT")
            time.sleep(1)
        run_command(
            [
                *wp,
                "core",
                "install",
                "--url=http://scratch.wordpress.invalid",
                "--title=Scratch restoration rehearsal",
                "--admin_user=scratch_restore",
                "--admin_email=scratch@example.invalid",
                "--skip-email",
                "--prompt=admin_password",
            ],
            phase="INSTALL",
            input_bytes=(admin_password + "\n").encode(),
        )
        print(
            "Scratch restore: importing the fourteen backed-up original documents",
            flush=True,
        )
        run_command(
            [*wp, "eval-file", "/var/www/raos-scratch-restore-seed.php"],
            phase="RESTORE",
        )
        readback = read_private_json(private, "scratch-readback.v1.json")
        receipt = verify_scratch_restoration(expected, readback)
        receipt["verified_at"] = datetime.now(UTC).isoformat()
        write_private_bytes(
            private, "scratch-restoration-receipt.v1.json", canonical(receipt)
        )
        verified = True
        print(
            "Scratch restore: 14/14 original IDs and stored fields verified", flush=True
        )
    finally:
        if started:
            stopped = (
                run_command(
                    [*command, "down", "--timeout", "10"],
                    phase="STOP",
                    required=False,
                    timeout=90,
                ).returncode
                == 0
            )
            write_private_bytes(
                private,
                "scratch-environment-state.v1.json",
                canonical(
                    {
                        "schema": "RAOS_WORDPRESS_SCRATCH_ENVIRONMENT_STATE_V1",
                        "environment_id": environment_id,
                        "docker_project": project,
                        "containers_stopped": stopped,
                        "dedicated_volumes_retained": True,
                        "restoration_verified": verified,
                        "production_authority": False,
                        "current_preview_modified": False,
                    }
                ),
            )
            if not stopped:
                fail("SCRATCH_STOP_FAILED")
    return private


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--preparation-sha256", required=True)
    arguments = parser.parse_args()
    try:
        private = execute(arguments.preparation_sha256)
        print(f"Private scratch receipt and backup: {private}")
        print(
            "Scratch containers stopped; dedicated volumes retained. Existing preview and production unchanged."
        )
        return 0
    except (IncrementalPublicationFailure, EditorialEconomicsV3Failure) as error:
        sys.stderr.write(f"{error}\n")
        return 69
    except OSError, ValueError, subprocess.TimeoutExpired:
        sys.stderr.write("RAOS_SCRATCH_EXECUTION_UNAVAILABLE\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
