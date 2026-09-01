from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
from collections.abc import Iterator

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "changes/wordpress-local-preview-v1/bin/wordpress_preview.sh"


def _private_root(tmp_path: Path) -> Path:
    suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]
    return Path("/tmp") / f"raos-wordpress-preview-test.{suffix}"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


@pytest.fixture
def fake_runtime(tmp_path: Path) -> Iterator[dict[str, str]]:
    docker_log = tmp_path / "docker.log"
    fake_docker = tmp_path / "docker"
    fake_curl = tmp_path / "curl"
    fake_materializer = tmp_path / "materialize"
    fake_yoast_materializer = tmp_path / "materialize-yoast"
    _write_executable(
        fake_docker,
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >>"$RAOS_FAKE_DOCKER_LOG"
printf 'article_fixture_root=%s\\n' "${RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_ROOT:-}" >>"$RAOS_FAKE_DOCKER_LOG"
printf 'post_fixture=%s\\n' "${RAOS_WORDPRESS_PREVIEW_POST_FIXTURE:-}" >>"$RAOS_FAKE_DOCKER_LOG"
printf 'product_media_root=%s\\n' "${RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT:-}" >>"$RAOS_FAKE_DOCKER_LOG"
printf 'yoast_root=%s\\n' "${RAOS_WORDPRESS_PREVIEW_YOAST_ROOT:-}" >>"$RAOS_FAKE_DOCKER_LOG"
if [[ "$*" == "compose version" ]]; then
  exit 0
fi
if [[ "$*" == "ps --filter publish="* ]]; then
  if [[ -n "${RAOS_FAKE_PORT_PROJECT:-}" ]]; then
    printf 'deadbeef %s\\n' "$RAOS_FAKE_PORT_PROJECT"
  fi
  exit 0
fi
if [[ "${RAOS_FAKE_DOCKER_UP_FAIL:-0}" == 1 && "$*" == *" up --detach database wordpress gateway"* ]]; then
  exit 42
fi
if [[ "$*" == *" core is-installed"* && "${RAOS_FAKE_CORE_INSTALLED:-1}" == 0 ]]; then
  exit 1
fi
if [[ "$*" == *" option get home"* ]]; then
  printf '%s\\n' "$RAOS_WORDPRESS_PREVIEW_ORIGIN"
fi
if [[ "$*" == *" theme list --name=kurashinoshirube-child --field=status"* ]]; then
  printf '%s\\n' active
fi
if [[ "$*" == *" plugin list --name=raos-editorial-measurement --field=status"* ]]; then
  printf '%s\\n' active
fi
if [[ "$*" == *" plugin list --name=wordpress-seo --field=status"* ]]; then
  printf '%s\\n' active
fi
if [[ "$*" == *" plugin get wordpress-seo --field=version"* ]]; then
  printf '%s\\n' 28.3
fi
exit 0
""",
    )
    _write_executable(fake_curl, "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_materializer,
        """#!/usr/bin/env bash
set -eu
private_root="$1"
fixture_root="$private_root/materialized-fixtures-v2"
mkdir -p "$fixture_root/articles" "$private_root/product-media"
printf '{}\n' >"$fixture_root/posts.json"
for index in {1..10}; do
  printf '<div></div>\n' >"$fixture_root/articles/article-$index.html"
done
""",
    )
    _write_executable(
        fake_yoast_materializer,
        """#!/usr/bin/env bash
set -eu
private_root="$1"
plugin_root="$private_root/plugins/wordpress-seo"
mkdir -p "$plugin_root"
printf '%s\n' '<?php /* Plugin Name: Yoast SEO */' >"$plugin_root/wp-seo.php"
""",
    )
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    yield {
        "RAOS_FAKE_DOCKER_LOG": str(docker_log),
        "RAOS_WORDPRESS_PREVIEW_CURL_BIN": str(fake_curl),
        "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(fake_docker),
        "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
        "RAOS_WORDPRESS_PREVIEW_PORT": "18888",
        "RAOS_WORDPRESS_PREVIEW_TEST_MATERIALIZER_BIN": str(fake_materializer),
        "RAOS_WORDPRESS_PREVIEW_TEST_YOAST_MATERIALIZER_BIN": str(
            fake_yoast_materializer
        ),
    }
    shutil.rmtree(private_root, ignore_errors=True)


def _run(
    command: str,
    environment: dict[str, str],
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WRAPPER), command],
        cwd=ROOT,
        env={**os.environ, **environment},
        check=check,
        capture_output=True,
        text=True,
    )


def test_missing_docker_is_reported_without_creating_private_state(
    tmp_path: Path,
) -> None:
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    result = _run(
        "up",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_DOCKER_UNAVAILABLE"
    assert not private_root.exists()


def test_broad_private_root_override_is_rejected_before_docker(tmp_path: Path) -> None:
    result = _run(
        "up",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(tmp_path),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT_INVALID"


def test_up_generates_private_credentials_and_runs_initial_seed(
    fake_runtime: dict[str, str],
) -> None:
    environment = {
        **fake_runtime,
        "RAOS_FAKE_CORE_INSTALLED": "0",
    }
    result = _run("up", environment, check=True)
    assert "WordPress preview: http://127.0.0.1:18888/" in result.stdout
    assert "raos-local-admin" in result.stdout
    credentials = (
        Path(environment["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"]) / "credentials.env"
    )
    fixture_root = (
        Path(environment["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"])
        / "materialized-fixtures-v2"
    )
    media_root = (
        Path(environment["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"]) / "product-media"
    )
    yoast_root = (
        Path(environment["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"])
        / "plugins"
        / "wordpress-seo"
    )
    assert stat.S_IMODE(credentials.stat().st_mode) == 0o600
    assert (fixture_root / "posts.json").is_file()
    assert len(list((fixture_root / "articles").glob("*.html"))) == 10
    assert media_root.is_dir()
    assert (yoast_root / "wp-seo.php").is_file()
    values = [line.split("=", 1)[1] for line in credentials.read_text().splitlines()]
    assert len(values) == 3
    assert len(set(values)) == 3
    assert all(len(value) == 64 for value in values)
    docker_log = Path(environment["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert "up --detach database wordpress gateway" in docker_log
    assert "--project-name raos-wordpress-preview-" in docker_log
    assert "core install" in docker_log
    assert "theme activate kurashinoshirube-child" in docker_log
    assert "plugin activate raos-editorial-measurement" in docker_log
    assert "plugin activate wordpress-seo" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" in docker_log
    assert f"article_fixture_root={fixture_root / 'articles'}" in docker_log
    assert f"post_fixture={fixture_root / 'posts.json'}" in docker_log
    assert f"product_media_root={media_root}" in docker_log
    assert f"yoast_root={yoast_root}" in docker_log
    assert all(value not in docker_log for value in values)
    assert all(value not in result.stdout for value in values)


def _activated_fixture(root: Path, *, mode: int = 0o700) -> Path:
    articles = root / "articles"
    articles.mkdir(parents=True, mode=0o700)
    root.chmod(mode)
    articles.chmod(0o700)
    posts = root / "posts.json"
    posts.write_text("{}\n", encoding="utf-8")
    posts.chmod(0o600)
    for index in range(1, 11):
        article = articles / f"activated-article-{index}.html"
        article.write_text("<div></div>\n", encoding="utf-8")
        article.chmod(0o600)
    return root


def test_owner_private_fixture_override_skips_v2_materialization(
    fake_runtime: dict[str, str], tmp_path: Path
) -> None:
    private_root = Path(fake_runtime["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"])
    private_root.mkdir(mode=0o700)
    (private_root / "product-media").mkdir(mode=0o700)
    activated = _activated_fixture(tmp_path / "activated-fixture")
    environment = {
        **fake_runtime,
        "RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT": activated.as_posix(),
    }

    _run("up", environment, check=True)

    assert not (private_root / "materialized-fixtures-v2").exists()
    docker_log = Path(environment["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert f"article_fixture_root={activated / 'articles'}" in docker_log
    assert f"post_fixture={activated / 'posts.json'}" in docker_log


def test_fixture_override_rejects_insecure_directory_mode_before_compose_up(
    fake_runtime: dict[str, str], tmp_path: Path
) -> None:
    private_root = Path(fake_runtime["RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT"])
    private_root.mkdir(mode=0o700)
    (private_root / "product-media").mkdir(mode=0o700)
    activated = _activated_fixture(tmp_path / "insecure-fixture", mode=0o755)

    result = _run(
        "up",
        {
            **fake_runtime,
            "RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT": activated.as_posix(),
        },
    )

    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_FIXTURE_OVERRIDE_INVALID"
    docker_log = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert " up --detach" not in docker_log


def test_up_refuses_a_foreign_compose_project_bound_to_preview_port(
    fake_runtime: dict[str, str],
) -> None:
    result = _run(
        "up",
        {**fake_runtime, "RAOS_FAKE_PORT_PROJECT": "another-checkout"},
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_FOREIGN_PORT_OWNER"
    docker_log = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert "ps --filter publish=18888" in docker_log
    assert " up --detach" not in docker_log


def test_up_propagates_compose_start_failure(fake_runtime: dict[str, str]) -> None:
    result = _run(
        "up",
        {**fake_runtime, "RAOS_FAKE_DOCKER_UP_FAIL": "1"},
    )
    assert result.returncode == 42
    docker_log = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"]).read_text()
    assert "up --detach database wordpress gateway" in docker_log
    assert "eval-file" not in docker_log


def test_down_preserves_named_volumes(fake_runtime: dict[str, str]) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    result = _run("down", fake_runtime, check=True)
    assert "DATA_PRESERVED" in result.stdout
    docker_log = log_path.read_text()
    assert " down --remove-orphans" in docker_log
    assert "--volumes" not in docker_log


def test_sync_is_explicit_and_uses_sync_mode(fake_runtime: dict[str, str]) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    _run("sync", fake_runtime, check=True)
    docker_log = log_path.read_text()
    assert "RAOS_PREVIEW_SEED_MODE=sync" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" not in docker_log


def test_reset_requires_confirmation_before_docker_access(tmp_path: Path) -> None:
    private_root = _private_root(tmp_path)
    shutil.rmtree(private_root, ignore_errors=True)
    result = _run(
        "reset",
        {
            "RAOS_WORDPRESS_PREVIEW_DOCKER_BIN": str(tmp_path / "missing-docker"),
            "RAOS_WORDPRESS_PREVIEW_PRIVATE_ROOT": str(private_root),
        },
    )
    assert result.returncode == 69
    assert result.stderr.strip() == "RAOS_WORDPRESS_PREVIEW_RESET_CONFIRMATION_REQUIRED"


def test_confirmed_reset_removes_only_compose_volumes_and_reseeds(
    fake_runtime: dict[str, str],
) -> None:
    _run("up", fake_runtime, check=True)
    log_path = Path(fake_runtime["RAOS_FAKE_DOCKER_LOG"])
    log_path.write_text("", encoding="utf-8")
    _run("reset", {**fake_runtime, "CONFIRM": "YES"}, check=True)
    docker_log = log_path.read_text()
    assert "down --volumes --remove-orphans" in docker_log
    assert "up --detach database wordpress gateway" in docker_log
    assert "RAOS_PREVIEW_SEED_MODE=initialize" in docker_log
