"""Behavioral regressions for runtime discovery and child environments."""

import json
import os
from pathlib import Path
import sys

import pytest

from scripts import raos_checks

ROOT = Path(__file__).resolve().parents[2]


def test_check_children_receive_postgresql_libraries(tmp_path, monkeypatch):
    monkeypatch.setenv("RAOS_PG_BIN", str(tmp_path / "bin"))
    monkeypatch.setenv("RAOS_PG_LIB", str(tmp_path / "lib"))
    monkeypatch.setenv("LD_LIBRARY_PATH", "/synthetic/other-library")
    output = tmp_path / "child.json"
    code = (
        "import json, os, pathlib; pathlib.Path(%r).write_text(json.dumps(dict(os.environ)))"
        % str(output)
    )
    assert (
        raos_checks.run(ROOT, [sys.executable, "-c", code], "runtime-regression") == 0
    )
    child = json.loads(output.read_text())
    assert child["RAOS_PG_BIN"] == str(tmp_path / "bin")
    assert child["RAOS_PG_LIB"] == str(tmp_path / "lib")
    assert child["LD_LIBRARY_PATH"].split(os.pathsep) == [
        str(tmp_path / "lib"),
        "/synthetic/other-library",
    ]


def test_missing_postgresql_is_an_error_not_a_skip(monkeypatch):
    from tests.postgresql18 import _tools

    monkeypatch.delenv("RAOS_PG_BIN", raising=False)
    with pytest.raises(pytest.fail.Exception, match="PostgreSQL"):
        _tools()


def _fake_postgres(tmp_path, version="18.4", status=0):
    from scripts.raos_test_runtime import PG_TOOLS

    directory = tmp_path / "bin"
    directory.mkdir()
    for name in PG_TOOLS:
        executable = directory / name
        executable.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            f"print({name!r} + ' (PostgreSQL) ' + {version!r})\n"
            f"sys.exit({status})\n"
        )
        executable.chmod(0o755)
    return {"RAOS_PG_BIN": str(directory), "PATH": os.environ["PATH"]}


@pytest.mark.parametrize("version", ["18.3", "18.40", "18.4.1", "17.9", "unknown"])
def test_rejects_nonexact_postgres_version(tmp_path, version):
    from scripts.raos_test_runtime import validate_postgres

    with pytest.raises(RuntimeError, match="exact 18.4"):
        validate_postgres(_fake_postgres(tmp_path, version))


def test_accepts_exact_version_and_rejects_broken_client(tmp_path):
    from scripts.raos_test_runtime import validate_postgres

    environment = _fake_postgres(tmp_path)
    validate_postgres(environment)
    (Path(environment["RAOS_PG_BIN"]) / "psql").unlink()
    with pytest.raises(RuntimeError, match="missing executable: psql"):
        validate_postgres(environment)


def test_rejects_nonzero_version_probe(tmp_path):
    from scripts.raos_test_runtime import validate_postgres

    with pytest.raises(RuntimeError, match="exact 18.4"):
        validate_postgres(_fake_postgres(tmp_path, status=1))


def test_cache_discovery_is_relocatable_and_environment_idempotent(tmp_path):
    from scripts.raos_test_runtime import runtime_environment

    root = tmp_path / "postgresql/18.4/root"
    postgres = root / "usr/lib/postgresql/18/bin/postgres"
    postgres.parent.mkdir(parents=True)
    postgres.touch()
    environment = runtime_environment(
        {
            "RAOS_TOOLCHAIN_CACHE": str(tmp_path),
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/synthetic/lib",
        }
    )
    assert environment["RAOS_PG_BIN"] == str(postgres.parent)
    assert environment["RAOS_PG_LIB"] == str(root / "usr/lib/x86_64-linux-gnu")
    assert environment["LD_LIBRARY_PATH"].split(os.pathsep)[-1] == "/synthetic/lib"
    assert runtime_environment(environment) == environment


def test_absent_cache_does_not_download_or_fabricate_postgres(tmp_path):
    from scripts.raos_test_runtime import runtime_environment, validate_postgres

    environment = runtime_environment({"RAOS_TOOLCHAIN_CACHE": str(tmp_path)})
    assert "RAOS_PG_BIN" not in environment
    assert not list(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="PostgreSQL 18.4 unavailable"):
        validate_postgres(environment)


def test_corrupt_cached_package_is_rejected_before_extraction(tmp_path, monkeypatch):
    from scripts import raos_test_runtime as runtime

    monkeypatch.setattr(
        runtime.platform,
        "freedesktop_os_release",
        lambda: {"ID": "ubuntu", "VERSION_ID": "22.04"},
    )
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    packages = tmp_path / "postgresql/18.4/packages"
    packages.mkdir(parents=True)
    (packages / runtime.PG_PACKAGES[0][0]).write_bytes(b"synthetic corrupt package")
    with pytest.raises(RuntimeError, match="package digest mismatch"):
        runtime.setup_postgres({"RAOS_TOOLCHAIN_CACHE": str(tmp_path)})
    assert not (packages.parent / "root").exists()


def test_php_override_is_discoverable_by_both_calling_conventions(tmp_path):
    import subprocess
    from scripts.raos_test_runtime import runtime_environment

    native = tmp_path / "php83"
    native.write_text(
        "#!" + sys.executable + "\nimport sys\nprint('synthetic PHP', *sys.argv[1:])\n"
    )
    native.chmod(0o755)
    environment = runtime_environment(dict(os.environ, RAOS_PHP_BIN=str(native)))
    direct = subprocess.run(
        [environment["RAOS_PHP_BIN"], "--version"],
        env=environment,
        capture_output=True,
        text=True,
    )
    path_lookup = subprocess.run(
        ["php", "--version"], env=environment, capture_output=True, text=True
    )
    assert direct.returncode == path_lookup.returncode == 0
    assert direct.stdout == path_lookup.stdout == "synthetic PHP --version\n"


def test_php_docker_invocation_has_only_readonly_fixture_and_source_mounts(tmp_path):
    import subprocess
    from scripts.raos_test_runtime import php_command, PHP_IMAGE, PHP_MOUNTS

    docker = tmp_path / "docker"
    docker.write_text(
        "#!" + sys.executable + "\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n"
    )
    docker.chmod(0o755)
    result = subprocess.run(
        php_command(["-r", "echo PHP_VERSION;"], docker=str(docker)),
        text=True,
        capture_output=True,
        check=True,
    )
    args = json.loads(result.stdout)
    for option in [
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pull=never",
    ]:
        assert option in args
    assert args[args.index("--tmpfs") + 1] == (
        f"/tmp:rw,noexec,nosuid,nodev,size=64m,mode=0700,uid={os.getuid()},gid={os.getgid()}"
    )
    assert args[args.index("--env") + 1] == "TMPDIR=/tmp"
    assert args[args.index("--entrypoint") + 1] == "php"
    assert args[-3:] == [PHP_IMAGE, "-r", "echo PHP_VERSION;"]
    mounts = [args[index + 1] for index, value in enumerate(args) if value == "--mount"]
    expected = [
        f"type=bind,src={ROOT / name},dst={ROOT / name},readonly"
        for name in PHP_MOUNTS
        if (ROOT / name).exists()
    ]
    assert mounts == [
        f"type=bind,src={ROOT / 'tests/raos_v2'},dst=/var/www/html,readonly",
        *expected,
    ]


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize(
    "suite",
    [
        "tests/test_runtime/test_postgres_smoke.py",
        "tests/st0002/test_postgresql_migration.py::test_immutable_baseline_fixture_is_postgresql_18",
    ],
)
def test_selected_database_test_errors_when_runtime_absent(tmp_path, configured, suite):
    import subprocess

    environment = dict(os.environ, RAOS_TOOLCHAIN_CACHE=str(tmp_path))
    for key in ("RAOS_PG_BIN", "RAOS_PG_LIB", "LD_LIBRARY_PATH"):
        environment.pop(key, None)
    if configured:
        environment["RAOS_PG_BIN"] = str(tmp_path / "absent")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            suite,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PostgreSQL" in result.stdout
    assert "1 error" in result.stdout
    assert "skipped" not in result.stdout


@pytest.mark.parametrize("marker", ["external", "live", "raos_owner_private"])
def test_excluded_database_tests_do_not_require_runtime(tmp_path, marker):
    import subprocess
    from scripts.raos_checks import LOCAL_MARKERS

    plugin = tmp_path / "runtime_exclusion_probe.py"
    plugin.write_text(
        "import pytest\n"
        "def pytest_collection_modifyitems(items):\n"
        f"    for item in items: item.add_marker(pytest.mark.{marker})\n"
    )
    environment = dict(
        os.environ,
        RAOS_TOOLCHAIN_CACHE=str(tmp_path),
        RAOS_PG_BIN=str(tmp_path / "absent"),
        PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT), str(ROOT / "python")]),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "runtime_exclusion_probe",
            "-m",
            LOCAL_MARKERS,
            "tests/test_runtime/test_postgres_smoke.py",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 5, result.stdout + result.stderr
    assert "1 deselected" in result.stdout
    assert "ERROR" not in result.stdout


def test_missing_php_override_exits_unsuccessfully(tmp_path):
    import subprocess

    environment = dict(os.environ, RAOS_PHP_BIN=str(tmp_path / "missing-php"))
    result = subprocess.run(
        [str(ROOT / "scripts/test-runtime-bin/php"), "--version"],
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "PHP test runtime unavailable" in result.stderr


def test_bare_php_override_resolves_original_path_before_shim(tmp_path):
    from scripts.raos_test_runtime import runtime_environment

    native = tmp_path / "php"
    native.write_text("#!" + sys.executable + "\nprint('native PHP selected')\n")
    native.chmod(0o755)
    environment = runtime_environment(
        dict(
            os.environ, PATH=str(tmp_path) + os.pathsep + os.defpath, RAOS_PHP_BIN="php"
        )
    )
    # Assert resolution before spawning, so the regression cannot launch recursion.
    assert environment["RAOS_PHP_BIN"] == str(native.resolve())
    import subprocess

    result = subprocess.run(
        ["php", "--version"],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "native PHP selected\n"


@pytest.mark.parametrize("override", ["missing-php", "php"])
def test_missing_or_selfreferential_php_override_is_rejected(tmp_path, override):
    from scripts.raos_test_runtime import runtime_environment

    wrapper = ROOT / "scripts/test-runtime-bin/php"
    (tmp_path / "php").symlink_to(wrapper)
    with pytest.raises(RuntimeError, match="RAOS_PHP_BIN"):
        runtime_environment({"PATH": str(tmp_path), "RAOS_PHP_BIN": override})


def test_explicit_valid_postgres_bypasses_acquisition_platform(tmp_path, monkeypatch):
    from scripts import raos_test_runtime as runtime

    environment = _fake_postgres(tmp_path)
    environment["RAOS_TOOLCHAIN_CACHE"] = str(tmp_path / "unused-cache")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    result = runtime.setup_postgres(environment)
    assert result["RAOS_PG_BIN"] == environment["RAOS_PG_BIN"]
    assert not (tmp_path / "unused-cache").exists()


@pytest.mark.parametrize("override", ["php", "alias", "absolute", "missing-php"])
def test_php_main_rejects_missing_and_wrapper_references_without_recursing(
    tmp_path, override
):
    import subprocess

    wrapper = ROOT / "scripts/test-runtime-bin/php"
    (tmp_path / "php").symlink_to(wrapper)
    (tmp_path / "alias").symlink_to(wrapper)
    configured = str(wrapper) if override == "absolute" else override
    environment = dict(
        os.environ,
        PATH=str(tmp_path) + os.pathsep + os.defpath,
        RAOS_PHP_BIN=configured,
    )
    result = subprocess.run(
        [str(wrapper), "--version"],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "RAOS_PHP_BIN" in result.stderr
    assert (
        "not an executable" in result.stderr
        if override == "missing-php"
        else "wrapper itself" in result.stderr
    )


def test_invalid_explicit_postgres_fails_without_acquisition(tmp_path, monkeypatch):
    from scripts import raos_test_runtime as runtime

    environment = _fake_postgres(tmp_path, version="18.3")
    environment["RAOS_TOOLCHAIN_CACHE"] = str(tmp_path / "unused-cache")
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="exact 18.4"):
        runtime.setup_postgres(environment)
    assert not (tmp_path / "unused-cache").exists()


def test_setup_cli_accepts_explicit_postgres_without_private_library_directory(
    tmp_path,
):
    import subprocess

    fake = _fake_postgres(tmp_path)
    environment = dict(os.environ, **fake)
    environment.pop("RAOS_PG_LIB", None)
    environment.pop("LD_LIBRARY_PATH", None)
    environment["RAOS_TOOLCHAIN_CACHE"] = str(tmp_path / "unused-cache")
    github_env = tmp_path / "github-env"
    environment["GITHUB_ENV"] = str(github_env)
    result = subprocess.run(
        [sys.executable, "scripts/verify_dev_toolchain.py", "--test-runtime-only"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert github_env.read_text() == f"RAOS_PG_BIN={fake['RAOS_PG_BIN']}\n"
    assert not (tmp_path / "unused-cache").exists()
