#!/usr/bin/env python3
"""Run owner-direct SQL/apply/compensation tests in isolated disposable WordPress."""

from pathlib import Path
import hashlib
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
WP_IMAGE = (
    "wordpress@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"
)
DB_IMAGE = (
    "mariadb@sha256:ae6119716edac6998ae85508431b3d2e666530ddf4e94c61a10710caec9b0f71"
)


def main():
    project = "raos-owner-direct-test-" + secrets.token_hex(5)
    database, wordpress = project + "-db", project + "-wp"

    def run(*args, check=True):
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if check and result.returncode:
            raise RuntimeError(result.stdout[-5000:] + result.stderr[-5000:])
        return result

    with tempfile.TemporaryDirectory(prefix="raos-owner-direct-test-") as raw:
        work = Path(raw)
        (work / "html").mkdir(mode=0o755)
        (work / "code").mkdir(mode=0o755)
        (work / "code/private").mkdir(mode=0o700)
        archive = work / "yoast.zip"
        with urllib.request.urlopen(
            "https://downloads.wordpress.org/plugin/wordpress-seo.28.3.zip", timeout=60
        ) as response:
            payload = response.read()
        assert (
            hashlib.sha256(payload).hexdigest()
            == "381edc1603147bd76af81341f21c9155ff3e9f6ce29ed20886d889fb9d6744fb"
        )
        archive.write_bytes(payload)
        with zipfile.ZipFile(archive) as source:
            source.extractall(work)
        parent = work / "raos-test-parent"
        parent.mkdir()
        (parent / "style.css").write_text(
            "/*\nTheme Name: RAOS disposable test parent\nVersion: 1.0.0\n*/\n"
        )
        (parent / "index.php").write_text("<?php echo 'Synthetic fixture';\n")
        child = work / "kurashinoshirube-child"
        child.mkdir()
        (child / "style.css").write_text(
            "/*\nTheme Name: RAOS disposable child\nTemplate: twentytwentyfive\nVersion: 1.0.0\n*/\n"
        )
        (child / "functions.php").write_text("<?php // Synthetic theme fixture.\n")
        password = secrets.token_urlsafe(32)
        environment = dict(
            os.environ,
            MARIADB_PASSWORD=password,
            MARIADB_ROOT_PASSWORD=password,
            WORDPRESS_DB_PASSWORD=password,
        )

        def private_run(args):
            result = subprocess.run(
                args, env=environment, capture_output=True, text=True, check=False
            )
            if result.returncode:
                raise RuntimeError("Isolated runtime startup failed")

        try:
            run("docker", "network", "create", "--internal", project)
            private_run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    database,
                    "--network",
                    project,
                    "--env",
                    "MARIADB_PASSWORD",
                    "--env",
                    "MARIADB_ROOT_PASSWORD",
                    "--env",
                    "MARIADB_DATABASE=wordpress",
                    "--env",
                    "MARIADB_USER=wordpress",
                    DB_IMAGE,
                ]
            )
            extra = "define('WP_HOME','https://kurashinoshirube.com'); define('WP_SITEURL','https://kurashinoshirube.com'); define('RAOS_OPERATOR_WRITES_ENABLED',true); define('WP_CONTENT_DIR','/var/www/raos-code/wp-content'); define('RAOS_CODEX_PRIVATE_DIR','/var/www/raos-code/private'); $_SERVER['HTTPS']='on';"
            private_run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    wordpress,
                    "--network",
                    project,
                    "--env",
                    "WORDPRESS_DB_PASSWORD",
                    "--env",
                    "WORDPRESS_DB_HOST=" + database,
                    "--env",
                    "WORDPRESS_DB_NAME=wordpress",
                    "--env",
                    "WORDPRESS_DB_USER=wordpress",
                    "--env",
                    "WORDPRESS_CONFIG_EXTRA=" + extra,
                    "--mount",
                    f"type=bind,src={work / 'html'},dst=/var/www/html",
                    "--mount",
                    f"type=bind,src={work / 'code'},dst=/var/www/raos-code",
                    "--mount",
                    f"type=bind,src={ROOT / 'tests/wordpress_mcp_v1/e2e'},dst=/test,readonly",
                    WP_IMAGE,
                ]
            )
            for _ in range(45):
                if (
                    run(
                        "docker",
                        "exec",
                        wordpress,
                        "test",
                        "-f",
                        "/var/www/html/wp-load.php",
                        check=False,
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(1)
            else:
                raise RuntimeError("WordPress startup timed out")
            run(
                "docker",
                "exec",
                wordpress,
                "cp",
                "-a",
                "/var/www/html/wp-content",
                "/var/www/raos-code/wp-content",
            )
            run(
                "docker",
                "exec",
                wordpress,
                "chmod",
                "0700",
                "/var/www/raos-code/private",
            )
            for source, target in (
                (
                    ROOT
                    / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities",
                    "plugins",
                ),
                (work / "wordpress-seo", "plugins"),
                (parent, "themes"),
                (child, "themes"),
            ):
                run(
                    "docker",
                    "cp",
                    str(source),
                    wordpress + ":/var/www/raos-code/wp-content/" + target + "/",
                )
            run(
                "docker",
                "exec",
                wordpress,
                "chown",
                "-R",
                "www-data:www-data",
                "/var/www/raos-code",
            )
            for _ in range(40):
                ready = run(
                    "docker",
                    "exec",
                    "--user",
                    "www-data",
                    wordpress,
                    "php",
                    "/test/owner_direct_runtime.php",
                    "setup",
                    check=False,
                )
                if ready.returncode == 0 and "OWNER_DIRECT_SETUP_OK" in ready.stdout:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(ready.stdout[-5000:] + ready.stderr[-5000:])
            result = run(
                "docker",
                "exec",
                "--user",
                "www-data",
                wordpress,
                "php",
                "/test/owner_direct_runtime.php",
                "run",
            )
            print(result.stdout)
        finally:
            run(
                "docker",
                "exec",
                wordpress,
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/var/www/html",
                "/var/www/raos-code",
                check=False,
            )
            run("docker", "rm", "--force", wordpress, database, check=False)
            run("docker", "network", "rm", project, check=False)


if __name__ == "__main__":
    main()
