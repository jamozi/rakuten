"""Shared, user-local PostgreSQL and PHP test runtime setup.

PostgreSQL packages are the Ubuntu 22.04 amd64 builds, extracted without
installing a service. Acquisition happens only at the explicit setup boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PG_VERSION = "18.4"
PHP_IMAGE = (
    "wordpress@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"
)
PG_TOOLS = ("postgres", "initdb", "pg_ctl", "pg_isready", "psql", "createdb")
PG_PACKAGE_BASE = "https://apt.postgresql.org/pub/repos/apt/pool/main/p/postgresql-18/"
# Verified against the upstream package bytes; no floating apt candidate.
PG_PACKAGES = (
    (
        "postgresql-18.deb",
        PG_PACKAGE_BASE + "postgresql-18_18.4-1.pgdg22.04%2B1_amd64.deb",
        "4194359fb7746fdb47517dcaaf1671f671b734e262af596b011ea84adb238029",
    ),
    (
        "postgresql-client-18.deb",
        PG_PACKAGE_BASE + "postgresql-client-18_18.4-1.pgdg22.04%2B1_amd64.deb",
        "ab06b1466c4cfbdf42732a15bb574907a58070544ccd8f99f68c1f944698328a",
    ),
    (
        "libpq5.deb",
        PG_PACKAGE_BASE + "libpq5_18.4-1.pgdg22.04%2B1_amd64.deb",
        "dc22cb89c24d08ebd588650b0bf6f2d8d113ffb29e0183a5d0ff7946212ec025",
    ),
    (
        "liburing2.deb",
        "https://archive.ubuntu.com/ubuntu/pool/main/libu/liburing/liburing2_2.1-2build1_amd64.deb",
        "f6e9bdf50c9683cd9a74ad92d51dde085f40baf0a5fcd8a56fc68425c1bd3c5f",
    ),
)
PHP_MOUNTS = (
    "tests/editorial_measurement_v1",
    "tests/reader_measurement_v1",
    "tests/verified_incremental_v1",
    "tests/st1704_publication_operator/php",
    "tests/wordpress_mcp_v1/php",
    "tests/raos_v2",
    "packages/web-ui/src/decision-support-v2/wordpress/plugin",
    "changes/editorial-measurement-v1/wordpress-plugin",
    "changes/reader-measurement-v1/wordpress-plugin",
    "changes/editorial-portfolio-v3/reader-measurement-privacy.html",
    "changes/wordpress-local-preview-v1/scratch-restore-seed.php",
    "changes/wordpress-local-preview-v1/scratch-theme-restore.php",
    "changes/st-1704/publication-operator-v2/wordpress-plugin",
    "changes/wordpress-mcp-v1/wordpress-plugin",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child",
    "changes/raos-v2/phase-3/wordpress",
    "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json",
)


def postgres_cache(environment: Mapping[str, str]) -> Path:
    cache = environment.get("RAOS_TOOLCHAIN_CACHE")
    if cache is None:
        cache = str(
            Path(environment.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
            / "raos-toolchains"
        )
    return Path(cache).expanduser() / "postgresql" / PG_VERSION


def _prepend(environment: dict[str, str], key: str, value: str) -> None:
    parts = environment.get(key, "").split(os.pathsep)
    environment[key] = os.pathsep.join(dict.fromkeys([value, *(p for p in parts if p)]))


def resolve_php_override(configured: str, environment: Mapping[str, str]) -> str:
    """Resolve once against the caller's PATH, rejecting the fallback itself."""
    selected = shutil.which(
        os.path.expanduser(configured), path=environment.get("PATH", os.defpath)
    )
    if selected is None:
        raise RuntimeError(f"RAOS_PHP_BIN is not an executable: {configured}")
    executable = Path(selected).resolve()
    wrapper = ROOT / "scripts/test-runtime-bin/php"
    if executable.samefile(wrapper):
        raise RuntimeError(
            "RAOS_PHP_BIN refers to the fallback wrapper itself; unset it to use the fallback"
        )
    return str(executable)


def runtime_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Discover installed assets without downloading or starting any service."""
    result = dict(environment)
    configured_php = environment.get("RAOS_PHP_BIN")
    if configured_php:
        result["RAOS_PHP_BIN"] = resolve_php_override(configured_php, environment)
    cached_root = postgres_cache(result) / "root"
    if (
        not result.get("RAOS_PG_BIN")
        and (cached_root / "usr/lib/postgresql/18/bin/postgres").is_file()
    ):
        result["RAOS_PG_BIN"] = str(cached_root / "usr/lib/postgresql/18/bin")
        result.setdefault("RAOS_PG_LIB", str(cached_root / "usr/lib/x86_64-linux-gnu"))
    if result.get("RAOS_PG_BIN"):
        _prepend(result, "PATH", result["RAOS_PG_BIN"])
    if result.get("RAOS_PG_LIB"):
        _prepend(result, "LD_LIBRARY_PATH", result["RAOS_PG_LIB"])
    wrapper = ROOT / "scripts/test-runtime-bin" / "php"
    discovered_php = shutil.which("php", path=result.get("PATH", ""))
    if (
        configured_php
        or discovered_php is None
        or Path(discovered_php).samefile(wrapper)
    ):
        _prepend(result, "PATH", str(wrapper.parent))
    return result


def validate_postgres(environment: Mapping[str, str]) -> None:
    """Required database tests must error for missing, broken or wrong tools."""
    directory = environment.get("RAOS_PG_BIN")
    if not directory:
        raise RuntimeError(
            "PostgreSQL 18.4 unavailable; run make setup or configure RAOS_PG_BIN and RAOS_PG_LIB"
        )
    for name in PG_TOOLS:
        executable = Path(directory) / name
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f"PostgreSQL 18.4 missing executable: {name}")
        try:
            result = subprocess.run(
                [str(executable), "--version"],
                env=dict(environment),
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"PostgreSQL 18.4 could not execute: {name}") from exc
        if (
            result.returncode
            or re.search(r"\(PostgreSQL\) 18\.4(?:\s|$)", result.stdout) is None
        ):
            raise RuntimeError(
                f"PostgreSQL runtime must be exact 18.4: {name}: {result.stdout.strip()} {result.stderr.strip()}"
            )


def setup_postgres(environment: Mapping[str, str]) -> dict[str, str]:
    """Validate explicit tools, otherwise acquire the locked Ubuntu packages."""
    if environment.get("RAOS_PG_BIN"):
        result = runtime_environment(environment)
        validate_postgres(result)
        return result
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError(
            "PostgreSQL test packages require Ubuntu 22.04 amd64 (WSL supported)"
        )
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "22.04":
        raise RuntimeError("PostgreSQL test packages require Ubuntu 22.04")
    cache = postgres_cache(environment)
    packages = cache / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    for name, url, digest in PG_PACKAGES:
        package = packages / name
        if not package.exists():
            with urlopen(url, timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"PostgreSQL package digest mismatch: {name}")
            with tempfile.NamedTemporaryFile(dir=packages, delete=False) as stream:
                stream.write(data)
                temporary = Path(stream.name)
            temporary.replace(package)
        if hashlib.sha256(package.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"PostgreSQL package digest mismatch: {name}")
        subprocess.run(
            ["dpkg-deb", "--extract", str(package), str(cache / "root")], check=True
        )
    result = dict(environment)
    result["RAOS_PG_BIN"] = str(cache / "root/usr/lib/postgresql/18/bin")
    result["RAOS_PG_LIB"] = str(cache / "root/usr/lib/x86_64-linux-gnu")
    result = runtime_environment(result)
    validate_postgres(result)
    return result


def php_command(
    arguments: Sequence[str], *, root: Path = ROOT, docker: str = "docker"
) -> list[str]:
    """Run pure PHP harnesses, with only declared source and synthetic fixtures."""
    command = [
        docker,
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size=64m,mode=0700,uid={os.getuid()},gid={os.getgid()}",
        "--env",
        "TMPDIR=/tmp",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--workdir",
        str(root),
        "--entrypoint",
        "php",
    ]
    # The WordPress image declares a writable /var/www/html volume even with
    # --read-only. Mask it with synthetic fixtures so no writable volume remains.
    fixtures = root / "tests/raos_v2"
    command.extend(["--mount", f"type=bind,src={fixtures},dst=/var/www/html,readonly"])
    for relative in PHP_MOUNTS:
        source = root / relative
        if source.exists():
            command.extend(["--mount", f"type=bind,src={source},dst={source},readonly"])
    command.extend([PHP_IMAGE, *arguments])
    return command


def php_main(arguments: Sequence[str]) -> int:
    try:
        configured = os.environ.get("RAOS_PHP_BIN")
        command = (
            [resolve_php_override(configured, os.environ), *arguments]
            if configured
            else php_command(arguments)
        )
        return subprocess.run(command, check=False).returncode
    except (OSError, RuntimeError) as exc:
        print(
            f"PHP test runtime unavailable: {exc}. Install PHP CLI or load {PHP_IMAGE}.",
            file=sys.stderr,
        )
        return 1
