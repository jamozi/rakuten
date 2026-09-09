"""Render the frozen owner-direct candidate in an isolated local WordPress.

This path performs two-width smoke checks, not the legacy publication audit.
It uses the same pinned containers, theme and local network guard as the preview.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from typing import Any
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "changes/wordpress-local-preview-v1"
DIRECT = ROOT / "changes/wordpress-direct-publish-v1"
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def contained(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("DIRECT_PREVIEW_PATH_INVALID")
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("DIRECT_PREVIEW_PATH_INVALID")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("DIRECT_PREVIEW_PATH_INVALID")
    return target


def preview_plan(candidate: dict, candidate_dir: Path) -> dict:
    if candidate.get("profile") != "owner-direct-v1":
        raise ValueError("DIRECT_PREVIEW_PROFILE_INVALID")
    surfaces = []
    seen = set()
    for article in candidate["articles"]:
        document = article["document"]
        slug = document["slug"]
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise ValueError("DIRECT_PREVIEW_SLUG_INVALID")
        if slug in seen:
            raise ValueError("DIRECT_PREVIEW_DUPLICATE_SLUG")
        seen.add(slug)
        body = contained(candidate_dir, article["body_file"])
        if not body.is_file() or body.stat().st_nlink != 1:
            raise ValueError("DIRECT_PREVIEW_BODY_INVALID")
        raw = body.read_bytes()
        expected_body = (
            article.get("body_sha256") if article.get("patch_source")
            else candidate["sources"][article["body_source"]]
        )
        if (
            digest(raw) != expected_body
            or raw.decode() != document["block_markup"]
        ):
            raise ValueError("DIRECT_PREVIEW_BODY_CHANGED")
        if document['post_type'] == 'page' and slug == 'home':
            surfaces.append({'kind': 'home', 'path': '/'})
        else:
            surfaces.append(
                {"kind": "article", "path": "/" + slug + "/", "title": document["title"]}
            )
    if candidate.get("theme"):
        theme = contained(candidate_dir, candidate["theme"]["directory"])
        if not theme.is_dir():
            raise ValueError("DIRECT_PREVIEW_THEME_MISSING")
        if not surfaces:
            surfaces.append(
                {
                    "kind": "article",
                    "path": "/direct-preview-example/",
                    "title": "ローカル表示確認用の記事",
                }
            )
        surfaces.extend(
            [
                *([] if any(s["kind"] == "home" for s in surfaces) else [{"kind": "home", "path": "/"}]),
                {"kind": "listing", "path": "/?post_type=post"},
            ]
        )
    if not surfaces:
        raise ValueError("DIRECT_PREVIEW_EMPTY")
    return {"widths": [390, 1440], "surfaces": surfaces}


def _private_dir(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("DIRECT_PREVIEW_PRIVATE_PATH_INVALID")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write(path: Path, value: bytes) -> None:
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("DIRECT_PREVIEW_FILE_INVALID")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
    os.replace(temporary, path)


def _run(
    command: list[str],
    *,
    environment: dict[str, str],
    input_text: str | None = None,
    timeout: int = 180,
    check: bool = True,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        # Docker output can contain generated local credentials. Return only a code.
        raise ValueError("DIRECT_PREVIEW_COMMAND_FAILED:" + Path(command[0]).name)
    return result


def _yoast(private: Path, environment: dict[str, str]) -> Path:
    lock_path = THEME.parent / "yoast-seo-28.3.lock.json"
    lock = json.loads(lock_path.read_bytes())
    downloads = private / "downloads"
    _private_dir(downloads)
    files = []
    for name, row, url_key, sha_key in [
        ("wordpress-seo.zip", lock["archive"], "download_url", "sha256"),
        (
            "wordpress-seo.checksums.json",
            lock["official_checksum_api"],
            "url",
            "manifest_sha256",
        ),
    ]:
        target = downloads / name
        if not target.exists():
            with urlopen(row[url_key], timeout=60) as response:
                raw = response.read(20_000_001)
            if len(raw) > 20_000_000 or digest(raw) != row[sha_key]:
                raise ValueError("DIRECT_PREVIEW_PLUGIN_DOWNLOAD_INVALID")
            _write(target, raw)
        if target.is_symlink() or digest(target.read_bytes()) != row[sha_key]:
            raise ValueError("DIRECT_PREVIEW_PLUGIN_CACHE_INVALID")
        files.append(target)
    _run(
        [
            sys.executable,
            str(SLICE / "bin/materialize_yoast.py"),
            "--archive",
            str(files[0]),
            "--checksums",
            str(files[1]),
            "--lock",
            str(lock_path),
            "--output-parent",
            str(private / "plugins"),
        ],
        environment=environment,
    )
    return private / "plugins/wordpress-seo"


def _theme_tree(theme: Path) -> str:
    rows = {}
    for path in sorted(theme.rglob("*")):
        if path.is_symlink():
            raise ValueError("DIRECT_PREVIEW_THEME_PATH_INVALID")
        if path.is_file():
            if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_nlink != 1:
                raise ValueError("DIRECT_PREVIEW_THEME_PATH_INVALID")
            rows[path.relative_to(theme).as_posix()] = digest(path.read_bytes())
    return digest(canonical(rows))


def runtime_fingerprint(candidate: dict, candidate_dir: Path) -> str:
    theme = (
        contained(candidate_dir, candidate["theme"]["directory"])
        if candidate.get("theme")
        else THEME
    )
    if candidate.get("publication_ready") and not candidate.get("theme"):
        manifest = []
        for path in sorted(theme.rglob("*")):
            if path.is_symlink():
                raise ValueError("DIRECT_PREVIEW_THEME_PATH_INVALID")
            if path.is_file():
                payload = path.read_bytes()
                manifest.append(
                    {
                        "path": path.relative_to(theme).as_posix(),
                        "size": len(payload),
                        "sha256": digest(payload),
                    }
                )
        if digest(canonical(manifest)) != candidate.get("baseline_theme_tree_sha256"):
            raise ValueError("DIRECT_PREVIEW_THEME_DIFFERS_INCLUDE_THEME")
    return digest(
        canonical(
            {
                "theme": _theme_tree(theme),
                "python": digest(Path(__file__).read_bytes()),
                "seed": digest((DIRECT / "preview-seed.php").read_bytes()),
                "browser": digest((DIRECT / "preview-browser.mjs").read_bytes()),
                "compose": digest((SLICE / "compose.yaml").read_bytes()),
                "guard": _theme_tree(SLICE / "mu-plugins"),
                "yoast": digest(
                    (THEME.parent / "yoast-seo-28.3.lock.json").read_bytes()
                ),
            }
        )
    )


def verify_preview(candidate: dict, candidate_dir: Path, report: dict) -> None:
    planned = preview_plan(candidate, candidate_dir)
    if (
        report.get("status") != "PASS"
        or report.get("candidate_id") != candidate["candidate_id"]
        or report.get("source_sha256") != candidate["source_sha256"]
        or report.get("runtime_sha256") != runtime_fingerprint(candidate, candidate_dir)
    ):
        raise ValueError("DIRECT_PREVIEW_RESULT_STALE")
    screenshots = report.get("screenshots", [])
    if len(screenshots) != len(planned["surfaces"]) * len(planned["widths"]):
        raise ValueError("DIRECT_PREVIEW_SCREENSHOTS_MISSING")
    seen = set()
    for row in screenshots:
        path = Path(row["path"])
        if (
            not path.is_absolute()
            or not path.is_relative_to(candidate_dir / "screenshots")
            or path in seen
        ):
            raise ValueError("DIRECT_PREVIEW_SCREENSHOT_PATH_INVALID")
        seen.add(path)
        path = contained(candidate_dir, path.relative_to(candidate_dir).as_posix())
        if not path.is_file() or digest(path.read_bytes()) != row.get("sha256"):
            raise ValueError("DIRECT_PREVIEW_SCREENSHOT_CHANGED")


def prepare_candidate_preview(candidate: dict, candidate_dir: Path) -> dict:
    planned = preview_plan(candidate, candidate_dir)
    runtime_sha = runtime_fingerprint(candidate, candidate_dir)
    identity = digest(str(ROOT).encode())[:12]
    port = 40000 + int(identity[:4], 16) % 12000
    origin = f"http://127.0.0.1:{port}"
    private = ROOT / ".secrets/wordpress-direct-preview"
    _private_dir(private)
    for name in ("fixtures", "fixtures/articles", "media"):
        _private_dir(private / name)
    _write(private / "fixtures/posts.json", b"{}")
    environment = dict(os.environ)
    yoast = _yoast(private, environment)
    credential_file = private / "credentials.env"
    if not credential_file.exists():
        _write(
            credential_file,
            "".join(
                f"{key}={secrets.token_hex(32)}\n"
                for key in (
                    "RAOS_WORDPRESS_PREVIEW_DATABASE_PASSWORD",
                    "RAOS_WORDPRESS_PREVIEW_DATABASE_ROOT_PASSWORD",
                    "RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD",
                )
            ).encode(),
        )
    if (
        credential_file.is_symlink()
        or credential_file.stat().st_nlink != 1
        or stat.S_IMODE(credential_file.stat().st_mode) != 0o600
    ):
        raise ValueError("DIRECT_PREVIEW_CREDENTIAL_FILE_INVALID")
    # Local-only generated password stays in memory/stdin and never enters command arguments.
    credentials = dict(
        line.split("=", 1) for line in credential_file.read_text().splitlines()
    )
    if any(not re.fullmatch("[a-f0-9]{64}", value) for value in credentials.values()):
        raise ValueError("DIRECT_PREVIEW_CREDENTIAL_FILE_INVALID")
    theme = (
        contained(candidate_dir, candidate["theme"]["directory"])
        if candidate.get("theme")
        else THEME
    )
    theme_sha = _theme_tree(theme)
    # Freeze the display theme even when it is not being deployed by this candidate.
    frozen_theme = private / ("theme-" + theme_sha)
    if not frozen_theme.exists():
        shutil.copytree(theme, frozen_theme, symlinks=False)
    if _theme_tree(frozen_theme) != theme_sha:
        raise ValueError("DIRECT_PREVIEW_THEME_CHANGED")
    for path in [frozen_theme, *frozen_theme.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    environment.update(
        {
            "RAOS_REPOSITORY_ROOT": str(ROOT),
            "RAOS_WORDPRESS_PREVIEW_ORIGIN": origin,
            "RAOS_WORDPRESS_PREVIEW_PORT": str(port),
            "RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_ROOT": str(
                private / "fixtures/articles"
            ),
            "RAOS_WORDPRESS_PREVIEW_POST_FIXTURE": str(private / "fixtures/posts.json"),
            "RAOS_WORDPRESS_PREVIEW_MIXED_FIXTURE_ROOT": str(private / "fixtures"),
            "RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT": str(private / "media"),
            "RAOS_WORDPRESS_PREVIEW_BASELINE_MEDIA_ROOT": str(private / "media"),
            "RAOS_WORDPRESS_PREVIEW_YOAST_ROOT": str(yoast),
        }
    )
    mounts = [
        {
            "type": "bind",
            "source": str(frozen_theme),
            "target": "/var/www/html/wp-content/themes/kurashinoshirube-child",
            "read_only": True,
        },
        {
            "type": "bind",
            "source": str(DIRECT),
            "target": "/var/www/raos-direct-preview",
            "read_only": True,
        },
        {
            "type": "bind",
            "source": str(candidate_dir.resolve()),
            "target": "/var/www/raos-direct-candidate",
            "read_only": True,
        },
    ]
    override = private / "compose.override.yaml"
    _write(
        override,
        yaml.safe_dump(
            {"services": {name: {"volumes": mounts} for name in ("wordpress", "cli")}}
        ).encode(),
    )
    docker = environment.get("RAOS_WORDPRESS_PREVIEW_DOCKER_BIN", "docker")
    compose = [
        docker,
        "compose",
        "--project-directory",
        str(SLICE),
        "--project-name",
        "raos-direct-preview-" + identity,
        "--env-file",
        str(credential_file),
        "--file",
        str(SLICE / "compose.yaml"),
        "--file",
        str(override),
    ]
    cli = compose + ["run", "--rm", "--no-deps", "-T", "cli"]
    _run(
        compose + ["up", "--detach", "--wait", "database", "wordpress", "gateway"],
        environment=environment,
        timeout=240,
    )
    for attempt in range(45):
        try:
            with urlopen(origin + "/wp-login.php", timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        if attempt == 44:
            raise ValueError("DIRECT_PREVIEW_START_TIMEOUT")
        time.sleep(1)
    if _run(
        cli + ["core", "is-installed"], environment=environment, check=False
    ).returncode:
        _run(
            cli
            + [
                "core",
                "install",
                "--url=" + origin,
                "--title=暮らしのしるべ — ローカル",
                "--admin_user=raos-local-admin",
                "--admin_email=local-preview@example.invalid",
                "--skip-email",
                "--prompt=admin_password",
            ],
            environment=environment,
            input_text=credentials["RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD"] + "\n",
        )
    _run(cli + ["theme", "activate", "kurashinoshirube-child"], environment=environment)
    _run(cli + ["plugin", "activate", "wordpress-seo"], environment=environment)
    if not _run(
        cli + ["plugin", "is-active", "raos-editorial-measurement"],
        environment=environment,
        check=False,
    ).returncode:
        _run(
            cli + ["plugin", "deactivate", "raos-editorial-measurement"],
            environment=environment,
        )
    lock = json.loads((THEME.parent / "yoast-seo-28.3.lock.json").read_bytes())
    _write(
        candidate_dir / "preview-input.json",
        canonical(
            {
                "candidate": candidate,
                "plan": planned,
                "yoast_configuration": lock["required_configuration"],
            }
        ),
    )
    seeded = _run(
        compose
        + [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "cli",
            "eval-file",
            "/var/www/raos-direct-preview/preview-seed.php",
        ],
        environment=environment,
    )
    if "DIRECT_PREVIEW_SEEDED" not in seeded.stdout:
        raise ValueError("DIRECT_PREVIEW_SEED_FAILED")
    _run(
        cli + ["rewrite", "structure", "/%postname%/", "--hard"],
        environment=environment,
    )
    prior = candidate_dir / "preview.json"
    if prior.is_file() and not prior.is_symlink():
        report = json.loads(prior.read_bytes())
        try:
            verify_preview(candidate, candidate_dir, report)
        except ValueError, OSError, KeyError, TypeError:
            pass
        else:
            return report  # Original capture time is preserved after exact local reseed/readback.
    # Lint all PHP in the candidate theme (small, no application regression suite).
    for path in sorted(frozen_theme.rglob("*.php")):
        _run(
            compose
            + [
                "exec",
                "-T",
                "wordpress",
                "php",
                "-l",
                "/var/www/html/wp-content/themes/kurashinoshirube-child/"
                + path.relative_to(frozen_theme).as_posix(),
            ],
            environment=environment,
        )
    for path in sorted(frozen_theme.rglob("*.js")):
        _run(
            [environment.get("RAOS_NODE", "node"), "--check", str(path)],
            environment=environment,
        )
    if runtime_fingerprint(candidate, candidate_dir) != runtime_sha:
        raise ValueError("DIRECT_PREVIEW_RUNTIME_CHANGED")
    screenshots = candidate_dir / "screenshots"
    _private_dir(screenshots)
    browser_input = candidate_dir / "browser-input.json"
    _write(
        browser_input,
        canonical(
            {
                **planned,
                "origin": origin,
                "screenshots": str(screenshots),
                "articles": candidate["articles"],
            }
        ),
    )
    result = _run(
        [
            environment.get("RAOS_NODE", "node"),
            str(DIRECT / "preview-browser.mjs"),
            str(browser_input),
        ],
        environment=environment,
        timeout=240,
    )
    observed = json.loads(result.stdout)
    return {
        "schema": "RAOSOwnerDirectPreviewV1",
        "status": observed["status"],
        "candidate_id": candidate["candidate_id"],
        "source_sha256": candidate["source_sha256"],
        "runtime_sha256": runtime_sha,
        "checked_at": datetime.now(UTC).isoformat(),
        "urls": [origin + row["path"] for row in planned["surfaces"]],
        "screenshots": observed["screenshots"],
        "failures": observed["failures"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate", required=True, type=Path)
    args = parser.parse_args()
    try:
        candidate = json.loads(args.candidate.read_bytes())
        result = prepare_candidate_preview(candidate, args.candidate.parent)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "PASS" else 1
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "code": (
                        str(error)
                        if isinstance(error, ValueError)
                        else type(error).__name__
                    ),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
