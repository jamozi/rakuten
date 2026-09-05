#!/usr/bin/env python3
"""Prepare or explicitly execute a portless scratch-only files rollback."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from importlib import import_module
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "python", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import raos_wordpress_local_restore as local_restore  # noqa: E402
from scripts.raos_wordpress_scratch_restore import DOCKER, COMPOSE, run_command  # noqa: E402
from raos.application.editorial.local_scratch_theme_restore_v1 import (  # noqa: E402
    ScratchThemeRestoration,
    THEME_SLUG,
    build_theme_package,
    build_scratch_theme_restoration,
    json_document,
    theme_tree_sha256,
    verify_scratch_theme_restoration,
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
    write_private_bytes,
)

BASELINE_COMMIT = "5bd4a8d06be87494961012d38336879ad1e123cb"
BASELINE_TREE = "086ce67f586701de2be1da5386f6c21f007a758c42245f42961f5cf00be933dc"
THEME_RELATIVE = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def private_root(environment_id: str) -> Path:
    if re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{12}", environment_id) is None:
        fail("SCRATCH_THEME_ENVIRONMENT_INVALID")
    root = local_restore.owner_root() / ("scratch-restore-" + environment_id)
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        fail("SCRATCH_THEME_ENVIRONMENT_INVALID")
    return root


def git_bytes(*arguments: str) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "--no-optional-locks", "-C", str(ROOT), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
        },
    )
    if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
        fail("SCRATCH_THEME_GIT_INVALID")
    return result.stdout


def baseline_package() -> bytes:
    entries = git_bytes("ls-tree", "-rz", BASELINE_COMMIT, "--", THEME_RELATIVE)
    files: dict[str, bytes] = {}
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, separator, raw_path = entry.partition(b"\t")
        parts = metadata.split()
        if (
            not separator
            or len(parts) != 3
            or parts[0] != b"100644"
            or parts[1] != b"blob"
        ):
            fail("SCRATCH_THEME_GIT_INVALID")
        blob = parts[2].decode("ascii")
        path = raw_path.decode("utf-8")
        if re.fullmatch(r"[0-9a-f]{40}", blob) is None or not path.startswith(
            THEME_RELATIVE + "/"
        ):
            fail("SCRATCH_THEME_GIT_INVALID")
        relative = path[len(THEME_RELATIVE) + 1 :]
        if relative in files:
            fail("SCRATCH_THEME_GIT_INVALID")
        files[relative] = git_bytes("cat-file", "blob", blob)
    if theme_tree_sha256(files) != BASELINE_TREE:
        fail("SCRATCH_THEME_BASELINE_GIT_MISMATCH")
    return build_theme_package(files)


def candidate_package(expected_tree: str) -> bytes:
    # The real deployment package owner checks a clean tracked theme and validates
    # every ZIP member. No caller-chosen file, URL or Git revision is accepted.
    factory: object = getattr(
        import_module("raos_wordpress_deployment_operator"), "theme_package"
    )
    if not callable(factory):
        fail("SCRATCH_THEME_CANDIDATE_INVALID")
    package: object = factory()
    if type(package) is not tuple or len(package) != 2:
        fail("SCRATCH_THEME_CANDIDATE_INVALID")
    raw, descriptor = package
    if type(raw) is not bytes or type(descriptor) is not dict:
        fail("SCRATCH_THEME_CANDIDATE_INVALID")
    if descriptor.get("file_manifest_sha256") != validate_hash(expected_tree):
        fail("SCRATCH_THEME_CANDIDATE_CHANGED")
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            if not member.filename.startswith(THEME_SLUG + "/") or member.is_dir():
                fail("SCRATCH_THEME_CANDIDATE_INVALID")
            files[member.filename[len(THEME_SLUG) + 1 :]] = archive.read(member)
    if theme_tree_sha256(files) != expected_tree:
        fail("SCRATCH_THEME_CANDIDATE_CHANGED")
    return build_theme_package(files)


def expected_restoration(
    root: Path, baseline: bytes, candidate: bytes
) -> ScratchThemeRestoration:
    return build_scratch_theme_restoration(
        json_document(read_private_bytes(root, "source-snapshot.v1.json")),
        article_slugs=local_restore.production_article_slugs(),
        content_receipt_raw=read_private_bytes(
            root, "scratch-restoration-receipt.v1.json"
        ),
        content_readback_raw=read_private_bytes(root, "scratch-readback.v1.json"),
        baseline_package_raw=baseline,
        candidate_package_raw=candidate,
    )


def prepare(environment_id: str, candidate_tree: str) -> Path:
    root = private_root(environment_id)
    target = root / "theme-restore"
    if (target / "readback.v1.json").exists() or (target / "receipt.v1.json").exists():
        fail("SCRATCH_THEME_ALREADY_EXECUTED")
    expected = expected_restoration(
        root, baseline_package(), candidate_package(candidate_tree)
    )
    write_private_bytes(target, "baseline-package.v1.json", expected.baseline_package)
    write_private_bytes(target, "candidate-package.v1.json", expected.candidate_package)
    write_private_bytes(target, "preparation.v1.json", expected.preparation)
    return target


def execute(environment_id: str, preparation_sha256: str) -> Path:
    root = private_root(environment_id)
    target = root / "theme-restore"
    preparation = read_private_bytes(target, "preparation.v1.json")
    if digest(preparation) != validate_hash(preparation_sha256):
        fail("SCRATCH_THEME_PREPARATION_CHANGED")
    expected = expected_restoration(
        root,
        read_private_bytes(target, "baseline-package.v1.json"),
        read_private_bytes(target, "candidate-package.v1.json"),
    )
    if (
        expected.preparation != preparation
        or json_document(preparation)["environment_id"] != environment_id
    ):
        fail("SCRATCH_THEME_PREPARATION_CHANGED")
    # Do not silently test an obsolete package after an intervening theme edit.
    candidate_tree = str(json_document(preparation)["candidate_tree_sha256"])
    if candidate_package(candidate_tree) != expected.candidate_package:
        fail("SCRATCH_THEME_CANDIDATE_CHANGED")
    project = "raos-wp-scratch-" + environment_id
    command = [
        *DOCKER,
        "compose",
        "--project-name",
        project,
        "--project-directory",
        str(COMPOSE.parent),
        "--env-file",
        str(root / "credentials.env"),
        "--file",
        str(COMPOSE),
    ]
    # Only existing, dedicated rehearsal volumes may be reopened; never initialize
    # a replacement DB silently or share the regular preview volume names.
    for suffix in ("scratch_database", "scratch_wordpress"):
        run_command(
            [*DOCKER, "volume", "inspect", project + "_" + suffix],
            phase="THEME_EXISTING_VOLUME",
        )
    started = False
    verified = False
    try:
        started = True
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
            phase="THEME_START",
        )
        # Give only this dedicated scratch's themes parent to the private-data
        # owner. This does not touch normal preview files or any WordPress option.
        if os.getuid() == 0 or os.getgid() == 0:
            fail("SCRATCH_THEME_OWNER_INVALID")
        run_command(
            [
                *command,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--user",
                "0:0",
                "--entrypoint",
                "chown",
                "cli",
                f"{os.getuid()}:{os.getgid()}",
                "/var/www/html/wp-content/themes",
            ],
            phase="THEME_SCRATCH_DIRECTORY_OWNER",
        )
        run_command(
            [
                *command,
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "-e",
                "RAOS_SCRATCH_THEME_PREPARATION_SHA256=" + preparation_sha256,
                "cli",
                "--skip-themes",
                "--skip-plugins",
                "eval-file",
                "/var/www/raos-scratch-theme-restore.php",
            ],
            phase="THEME_RESTORE",
        )
        readback = json_document(read_private_bytes(target, "readback.v1.json"))
        receipt = verify_scratch_theme_restoration(expected, readback)
        receipt["verified_at"] = datetime.now(UTC).isoformat()
        write_private_bytes(target, "receipt.v1.json", canonical(receipt))
        verified = True
    finally:
        if started:
            stopped = (
                run_command(
                    [*command, "down", "--timeout", "10"],
                    phase="THEME_STOP",
                    required=False,
                    timeout=90,
                ).returncode
                == 0
            )
            write_private_bytes(
                target,
                "environment-state.v1.json",
                canonical(
                    {
                        "schema": "RAOS_WORDPRESS_SCRATCH_THEME_ENVIRONMENT_STATE_V1",
                        "environment_id": environment_id,
                        "production_authority": False,
                        "containers_stopped": stopped,
                        "dedicated_volumes_retained": True,
                        "theme_restoration_verified": verified,
                        "current_preview_modified": False,
                    }
                ),
            )
            if not stopped:
                fail("SCRATCH_THEME_STOP_FAILED")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare", allow_abbrev=False)
    prepare_command.add_argument("--environment-id", required=True)
    prepare_command.add_argument("--candidate-tree-sha256", required=True)
    execute_command = commands.add_parser("execute", allow_abbrev=False)
    execute_command.add_argument("--environment-id", required=True)
    execute_command.add_argument("--preparation-sha256", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "prepare":
            path = prepare(arguments.environment_id, arguments.candidate_tree_sha256)
            print(
                "Scratch theme backup prepared; restoration NOT_EXECUTED; authority false"
            )
        else:
            path = execute(arguments.environment_id, arguments.preparation_sha256)
            print(
                "Scratch theme rollback verified; 14 saved documents and options unchanged; authority false"
            )
        print("Private artifacts: " + str(path))
        return 0
    except (IncrementalPublicationFailure, EditorialEconomicsV3Failure) as error:
        sys.stderr.write(str(error) + "\n")
        return 69
    except OSError, ValueError, subprocess.TimeoutExpired:
        sys.stderr.write("RAOS_SCRATCH_THEME_EXECUTION_UNAVAILABLE\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
