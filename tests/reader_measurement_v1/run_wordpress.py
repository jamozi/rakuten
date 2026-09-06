#!/usr/bin/env python3
"""Real dbDelta/activation check in a disposable, network-isolated WordPress.

Only already-cached digest-pinned images are accepted. The database lives on
tmpfs, no host port is published, and every created Docker object carries a
unique test label that is checked again during teardown.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/reader_measurement_v1/fixtures"
PACKAGE = (
    ROOT / ".secrets/wordpress-mcp/repo-plugin-artifacts/raos-reader-measurement-v1.zip"
)
MANIFEST = ROOT / "changes/reader-measurement-v1/runtime-manifest.v1.json"
RECORD = (
    ROOT / "output/playwright/reader-measurement-v1/wordpress-integration/latest.json"
)

DB_IMAGE = (
    "mariadb@sha256:ae6119716edac6998ae85508431b3d2e666530ddf4e94c61a10710caec9b0f71"
)
WP_IMAGE = (
    "wordpress@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"
)
CLI_IMAGE = (
    "wordpress@sha256:2b5e9d4d3e51909dca1aaa4732e9f5e5bf0377c2114dbd8ff39f060bff202586"
)
IMAGES = (DB_IMAGE, WP_IMAGE, CLI_IMAGE)
PLUGIN = "raos-reader-measurement/raos-reader-measurement.php"


class IntegrationFailure(RuntimeError):
    """A bounded integration precondition or assertion failed."""


def command(
    args: list[str],
    *,
    timeout: int = 30,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stdout + result.stderr)[-4096:].strip()
        raise IntegrationFailure(detail or "RAOS_READER_WORDPRESS_COMMAND_FAILED")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(kind: str, name: str) -> dict[str, Any] | None:
    result = command(["docker", kind, "inspect", name], check=False)
    if result.returncode != 0:
        return None
    value = json.loads(result.stdout)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise IntegrationFailure("RAOS_READER_WORDPRESS_DOCKER_INSPECT_INVALID")
    return value[0]


def exact_label(value: dict[str, Any], run_id: str) -> bool:
    labels = value.get("Labels")
    if not isinstance(labels, dict):
        labels = value.get("Config", {}).get("Labels")
    return isinstance(labels, dict) and labels.get("raos.reader.test") == run_id


def parse_prefixed_json(output: str, prefix: str) -> dict[str, Any]:
    matches = [
        line.removeprefix(prefix)
        for line in output.splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1:
        raise IntegrationFailure("RAOS_READER_WORDPRESS_RESULT_INVALID")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise IntegrationFailure("RAOS_READER_WORDPRESS_RESULT_INVALID")
    return value


def write_record(value: dict[str, Any]) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECORD.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, RECORD)


def main() -> int:
    run_id = f"{os.getpid()}-{secrets.token_hex(6)}"
    label = f"raos.reader.test={run_id}"
    db_name = f"raos-reader-wordpress-{run_id}-db"
    wp_name = f"raos-reader-wordpress-{run_id}-wp"
    network_name = f"raos-reader-wordpress-{run_id}-net"
    volume_name = f"raos-reader-wordpress-{run_id}-html"
    test_root: Path | None = None
    failure: Exception | None = None
    package_manifest: dict[str, Any] = {}
    record: dict[str, Any] = {
        "schema": "RAOS_READER_WORDPRESS_INTEGRATION_V1",
        "status": "RUNNING",
        "observed_at": datetime.now(UTC).isoformat(),
        "production_authority": False,
        "release_audit": False,
        "fake_or_test_approval_is_production_evidence": False,
    }

    try:
        if shutil.which("docker") is None:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_DOCKER_UNAVAILABLE")
        command(["docker", "version", "--format", "{{.Server.Version}}"])
        image_ids: dict[str, str] = {}
        for image in IMAGES:
            result = command(
                ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                check=False,
            )
            if result.returncode != 0:
                raise IntegrationFailure(f"RAOS_READER_WORDPRESS_IMAGE_MISSING:{image}")
            image_ids[image] = result.stdout.strip()

        required = (
            MANIFEST,
            PACKAGE,
            FIXTURES / "wordpress_admin_activate.php",
            FIXTURES / "wordpress_probe.php",
        )
        if any(not path.is_file() or path.is_symlink() for path in required):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_INPUT_INVALID")
        package_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if (
            package_manifest.get("schema")
            != "RAOS_READER_MEASUREMENT_RUNTIME_MANIFEST_V1"
        ):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_MANIFEST_INVALID")
        package_hash = sha256(PACKAGE)
        if package_hash != package_manifest.get("package_sha256"):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_PACKAGE_DIGEST_MISMATCH")

        test_root = Path(
            tempfile.mkdtemp(prefix="raos-reader-wordpress-", dir="/tmp")
        ).resolve()
        if test_root.parent != Path("/tmp") or not test_root.name.startswith(
            "raos-reader-wordpress-"
        ):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_TEMP_INVALID")
        test_root.chmod(0o700)
        staged_package = test_root / "reader.zip"
        shutil.copyfile(PACKAGE, staged_package)
        staged_package.chmod(0o644)
        if sha256(staged_package) != package_hash:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_STAGED_PACKAGE_DRIFT")

        db_password = secrets.token_urlsafe(48)
        db_root_password = secrets.token_urlsafe(48)
        admin_password = secrets.token_urlsafe(48)

        command(
            [
                "docker",
                "network",
                "create",
                "--internal",
                "--driver",
                "bridge",
                "--label",
                label,
                network_name,
            ]
        )
        command(["docker", "volume", "create", "--label", label, volume_name])
        command(
            [
                "docker",
                "run",
                "--pull=never",
                "--rm",
                "--detach",
                "--name",
                db_name,
                "--label",
                label,
                "--network",
                network_name,
                "--network-alias",
                "database",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "mysql",
                "--tmpfs",
                "/var/lib/mysql:rw,nosuid,uid=999,gid=999,mode=0700,size=256m",
                "--tmpfs",
                "/run/mysqld:rw,nosuid,uid=999,gid=999,mode=0700,size=16m",
                "--tmpfs",
                "/tmp:rw,nosuid,size=32m",
                "--env",
                "MARIADB_DATABASE=wordpress",
                "--env",
                "MARIADB_USER=wordpress",
                "--env",
                f"MARIADB_PASSWORD={db_password}",
                "--env",
                f"MARIADB_ROOT_PASSWORD={db_root_password}",
                DB_IMAGE,
                "--bind-address=0.0.0.0",
            ],
            timeout=20,
        )

        deadline = time.monotonic() + 45
        while True:
            ready = command(
                [
                    "docker",
                    "exec",
                    db_name,
                    "mariadb-admin",
                    "--protocol=tcp",
                    "--host=127.0.0.1",
                    "--user=root",
                    f"--password={db_root_password}",
                    "ping",
                    "--silent",
                ],
                check=False,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise IntegrationFailure("RAOS_READER_WORDPRESS_DATABASE_TIMEOUT")
            time.sleep(0.3)

        config_extra = "\n".join(
            (
                "define('WP_HOME', 'https://kurashinoshirube.com');",
                "define('WP_SITEURL', 'https://kurashinoshirube.com');",
                "define('RAOS_OPERATOR_WRITES_ENABLED', true);",
                "$_SERVER['HTTPS'] = 'on';",
                "$_SERVER['HTTP_X_FORWARDED_PROTO'] = 'https';",
            )
        )
        shared_mounts = [
            "--mount",
            f"type=volume,src={volume_name},dst=/var/www/html",
            "--mount",
            f"type=bind,src={staged_package},dst=/var/www/raos-test/reader.zip,readonly",
            "--mount",
            f"type=bind,src={FIXTURES},dst=/var/www/raos-test/fixtures,readonly",
        ]
        database_environment = [
            "--env",
            "WORDPRESS_DB_HOST=database:3306",
            "--env",
            "WORDPRESS_DB_NAME=wordpress",
            "--env",
            "WORDPRESS_DB_USER=wordpress",
            "--env",
            f"WORDPRESS_DB_PASSWORD={db_password}",
        ]
        command(
            [
                "docker",
                "run",
                "--pull=never",
                "--rm",
                "--detach",
                "--name",
                wp_name,
                "--label",
                label,
                "--network",
                network_name,
                "--network-alias",
                "wordpress",
                *database_environment,
                "--env",
                f"WORDPRESS_CONFIG_EXTRA={config_extra}",
                *shared_mounts,
                WP_IMAGE,
            ],
            timeout=20,
        )

        def wp_cli(
            args: list[str], *, input_text: str | None = None, timeout: int = 60
        ) -> str:
            result = command(
                [
                    "docker",
                    "run",
                    "--pull=never",
                    "--rm",
                    "--interactive",
                    "--label",
                    label,
                    "--network",
                    network_name,
                    "--user",
                    "33:33",
                    *database_environment,
                    *shared_mounts,
                    "--workdir",
                    "/var/www/html",
                    "--entrypoint",
                    "wp",
                    CLI_IMAGE,
                    *args,
                ],
                input_text=input_text,
                timeout=timeout,
            )
            return result.stdout

        deadline = time.monotonic() + 60
        while True:
            ready = command(
                [
                    "docker",
                    "exec",
                    wp_name,
                    "sh",
                    "-c",
                    "test -f /var/www/html/wp-config.php && test -f /var/www/html/wp-load.php",
                ],
                check=False,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise IntegrationFailure("RAOS_READER_WORDPRESS_BOOT_TIMEOUT")
            time.sleep(0.5)

        record["stage"] = "wordpress_core_install"
        wp_cli(
            [
                "core",
                "install",
                "--url=https://kurashinoshirube.com",
                "--title=RAOS Reader Measurement Integration",
                "--admin_user=raos-reader-test-admin",
                "--admin_email=reader-test@example.invalid",
                "--skip-email",
                "--prompt=admin_password",
            ],
            input_text=admin_password + "\n",
        )
        record["stage"] = "wordpress_version_check"
        if wp_cli(["core", "version"]).strip() != "7.1":
            raise IntegrationFailure("RAOS_READER_WORDPRESS_VERSION_INVALID")
        record["stage"] = "plugin_zip_install_inactive"
        wp_cli(["plugin", "install", "/var/www/raos-test/reader.zip"])

        record["stage"] = "preactivation_probe"
        before = parse_prefixed_json(
            wp_cli(
                [
                    "eval-file",
                    "/var/www/raos-test/fixtures/wordpress_probe.php",
                    "before",
                ]
            ),
            "RAOS_READER_WORDPRESS_JSON=",
        )
        if before != {
            "wordpress_version": "7.1",
            "plugin_installed": True,
            "plugin_active": False,
            "dedicated_tables": [],
            "active_plugins": [],
        }:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_PREACTIVATION_INVALID")

        record["stage"] = "test_admin_lookup"
        admin_id = wp_cli(
            ["user", "get", "raos-reader-test-admin", "--field=ID"]
        ).strip()
        record["stage"] = "nonce_protected_core_activation"
        activation_result = command(
            [
                "docker",
                "exec",
                "--user",
                "www-data",
                "--env",
                f"RAOS_READER_TEST_ADMIN_ID={admin_id}",
                wp_name,
                "php",
                "/var/www/raos-test/fixtures/wordpress_admin_activate.php",
            ],
            timeout=60,
        )
        activation = parse_prefixed_json(
            activation_result.stdout,
            "RAOS_READER_WORDPRESS_ACTIVATION_JSON=",
        )
        expected_activation = {
            "method": "wordpress_core_activate_plugin_with_real_nonce",
            "test_only_admin": True,
            "nonce_verified": True,
            "plugin_active": True,
            "collection_enabled": False,
            "approval": None,
        }
        if activation != expected_activation:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_ACTIVATION_RESULT_INVALID")

        record["stage"] = "postactivation_dbdelta_probe"
        observed = parse_prefixed_json(
            wp_cli(
                [
                    "eval-file",
                    "/var/www/raos-test/fixtures/wordpress_probe.php",
                    "inspect",
                ]
            ),
            "RAOS_READER_WORDPRESS_JSON=",
        )
        expected_tables = sorted(
            [
                "wp_raos_reader_raw_v1",
                "wp_raos_reader_daily_v1",
                "wp_raos_reader_rate_v1",
            ]
        )
        expected_columns = {
            "raw": sorted(
                [
                    "event_date",
                    "event_name",
                    "article_id",
                    "target_article_id",
                    "journey_stage",
                    "panel_id",
                    "source_ref",
                ]
            ),
            "daily": sorted(
                [
                    "event_date",
                    "event_name",
                    "article_id",
                    "target_article_id",
                    "journey_stage",
                    "panel_id",
                    "source_ref",
                    "event_count",
                ]
            ),
            "rate": sorted(
                [
                    "bucket_key",
                    "tokens_milli",
                    "refilled_millis",
                    "budget_date",
                    "accepted_count",
                ]
            ),
        }
        if (
            observed.get("wordpress_version") != "7.1"
            or observed.get("plugin_active") is not True
            or observed.get("collection_enabled") is not False
            or observed.get("state") != {"enabled": False, "approval": None}
            or observed.get("db_version") != "1.0.0"
            or observed.get("storage_ready") is not True
            or observed.get("cleanup_scheduled") is not True
            or observed.get("dedicated_tables") != expected_tables
            or observed.get("columns") != expected_columns
            or set(observed.get("engines", {}).values()) != {"InnoDB"}
            or observed.get("active_plugins") != [PLUGIN]
            or observed.get("old_eight_event_plugin_active") is not False
        ):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_DBDELTA_STATE_INVALID")
        if observed.get("cleanup_status", {}).get("healthy") is not True:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_INITIAL_CLEANUP_INVALID")

        record["stage"] = "retention_cleanup_probe"
        cleanup = parse_prefixed_json(
            wp_cli(
                [
                    "eval-file",
                    "/var/www/raos-test/fixtures/wordpress_probe.php",
                    "cleanup",
                ]
            ),
            "RAOS_READER_WORDPRESS_JSON=",
        )
        if (
            cleanup.get("cleanup_returned") is not True
            or cleanup.get("remaining")
            != {
                "raw_expired": 0,
                "raw_kept": 1,
                "daily_expired": 0,
                "daily_kept": 1,
            }
            or cleanup.get("collection_enabled") is not False
            or cleanup.get("cleanup_status", {}).get("healthy") is not True
        ):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_CLEANUP_RESULT_INVALID")

        record["stage"] = "isolation_inspection"
        network = inspect("network", network_name)
        database = inspect("container", db_name)
        wordpress = inspect("container", wp_name)
        if (
            network is None
            or not exact_label(network, run_id)
            or network.get("Internal") is not True
        ):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_NETWORK_NOT_INTERNAL")
        if database is None or wordpress is None:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_CONTAINER_MISSING")
        if not exact_label(database, run_id) or not exact_label(wordpress, run_id):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_CONTAINER_LABEL_INVALID")
        db_tmpfs = database.get("HostConfig", {}).get("Tmpfs", {})
        if "/var/lib/mysql" not in db_tmpfs:
            raise IntegrationFailure("RAOS_READER_WORDPRESS_DATABASE_NOT_TMPFS")
        if database.get("HostConfig", {}).get("PortBindings") not in (None, {}):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_DATABASE_PORT_PUBLISHED")
        if wordpress.get("HostConfig", {}).get("PortBindings") not in (None, {}):
            raise IntegrationFailure("RAOS_READER_WORDPRESS_HTTP_PORT_PUBLISHED")

        record.update(
            {
                "status": "PASS",
                "stage": "completed",
                "images": image_ids,
                "package": {
                    "artifact_id": package_manifest.get("artifact_id"),
                    "package_sha256": package_hash,
                    "plugin_version": package_manifest.get("plugin_version"),
                },
                "isolation": {
                    "network_internal": True,
                    "published_ports": [],
                    "database_tmpfs": sorted(db_tmpfs),
                    "external_gets": 0,
                    "production_requests": 0,
                },
                "before_activation": before,
                "activation": activation,
                "storage": observed,
                "cleanup": cleanup,
                "old_eight_event_and_ga_enabled": False,
            }
        )
    except Exception as error:  # teardown and a bounded record are mandatory.
        failure = error
        record["status"] = "FAIL"
        message = (
            str(error).strip().splitlines()[-1]
            if str(error).strip()
            else type(error).__name__
        )
        record["error"] = message[:512]
    finally:
        teardown_errors: list[str] = []
        containers = command(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--filter",
                f"label={label}",
            ],
            check=False,
        )
        for container_id in containers.stdout.split():
            value = inspect("container", container_id)
            if value is None or not exact_label(value, run_id):
                teardown_errors.append("container_label")
                continue
            removed = command(
                ["docker", "rm", "--force", container_id], check=False, timeout=15
            )
            if removed.returncode != 0:
                teardown_errors.append("container_remove")

        volume = inspect("volume", volume_name)
        if volume is not None:
            if not exact_label(volume, run_id):
                teardown_errors.append("volume_label")
            elif (
                command(["docker", "volume", "rm", volume_name], check=False).returncode
                != 0
            ):
                teardown_errors.append("volume_remove")
        network = inspect("network", network_name)
        if network is not None:
            if not exact_label(network, run_id):
                teardown_errors.append("network_label")
            elif (
                command(
                    ["docker", "network", "rm", network_name], check=False
                ).returncode
                != 0
            ):
                teardown_errors.append("network_remove")

        if test_root is not None:
            resolved = test_root.resolve()
            if resolved.parent != Path("/tmp") or not resolved.name.startswith(
                "raos-reader-wordpress-"
            ):
                teardown_errors.append("temp_path")
            else:
                shutil.rmtree(resolved, ignore_errors=False)

        absent = {
            "containers": command(
                [
                    "docker",
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"label={label}",
                ],
                check=False,
            ).stdout.strip()
            == "",
            "network": inspect("network", network_name) is None,
            "volume": inspect("volume", volume_name) is None,
            "temporary_directory": test_root is None or not test_root.exists(),
        }
        record["teardown"] = {
            "safe": not teardown_errors and all(absent.values()),
            "absent": absent,
            "errors": teardown_errors,
        }
        if teardown_errors or not all(absent.values()):
            record["status"] = "FAIL"
            failure = failure or IntegrationFailure(
                "RAOS_READER_WORDPRESS_TEARDOWN_FAILED"
            )
        record["completed_at"] = datetime.now(UTC).isoformat()
        write_record(record)

    if failure is not None:
        print(f"RAOS_READER_WORDPRESS_INTEGRATION_FAIL:{record.get('error', failure)}")
        print(f"RAOS_READER_WORDPRESS_RECORD={RECORD.relative_to(ROOT)}")
        return 1
    print("RAOS_READER_WORDPRESS_INTEGRATION_OK")
    print(f"RAOS_READER_WORDPRESS_RECORD={RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
