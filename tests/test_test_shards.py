"""Shards cover every eligible case exactly once, including with xdist."""

from collections import Counter
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.raos_checks import execute, LOCAL_MARKERS
from scripts.raos_test_shards import belongs_to_shard

ROOT = Path(__file__).resolve().parents[1]


def test_eight_shards_partition_parametrized_and_serial_cases(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n serial\n live\n external\n raos_owner_private\n"
    )
    (tmp_path / "test_sample.py").write_text("""import pytest
@pytest.mark.parametrize('value', range(40))
def test_parallel(value): assert value >= 0
@pytest.mark.serial
@pytest.mark.parametrize('value', range(40))
def test_serial(value): assert value >= 0
@pytest.mark.live
def test_live(): raise AssertionError('must be excluded')
@pytest.mark.external
def test_external(): raise AssertionError('must be excluded')
@pytest.mark.raos_owner_private
def test_private(): raise AssertionError('must be excluded')
""")
    environment = {**os.environ, "PYTHONPATH": str(ROOT)}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--disable-plugin-autoload",
        "-q",
        "-p",
        "scripts.raos_test_shards",
        "--raos-shard-total=8",
        "-m",
        LOCAL_MARKERS,
    ]
    observed: Counter[str] = Counter()
    third_shard: set[str] = set()
    for index in range(1, 9):
        result = subprocess.run(
            [*command, f"--raos-shard-index={index}", "--collect-only"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        selected = {
            line
            for line in result.stdout.splitlines()
            if line.startswith("test_sample.py::")
        }
        assert selected
        observed.update(selected)
        if index == 3:
            third_shard = selected
    assert observed == Counter(
        {
            f"test_sample.py::test_{group}[{value}]": 1
            for group in ("parallel", "serial")
            for value in range(40)
        }
    )
    # xdist workers must agree on the same selection and execute it successfully.
    result = subprocess.run(
        [*command, "--raos-shard-index=3", "-p", "xdist.plugin", "-n", "2"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"{len(third_shard)} passed" in result.stdout
    invalid = subprocess.run(
        [*command, "--raos-shard-index=9", "--collect-only"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode != 0
    assert "test shard index must be within 1..total" in invalid.stderr


def test_native_tests_and_php_execute_once_across_shards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], str]] = []

    def record(root, command, label, **kwargs):
        calls.append((tuple(command), label))
        return 0

    monkeypatch.setattr("scripts.raos_checks.run", record)
    plan = SimpleNamespace(
        python_tests=(),
        node_tests=tuple(f"tests/example-{i}.test.ts" for i in range(12)),
        vitest_tests=tuple(f"tests/unit-{i}.test.ts" for i in range(4)),
        php=True,
    )
    for index in range(1, 9):
        execute(ROOT, {}, plan, stage="tests", shard_index=index, shard_total=8)
    assert Counter(
        path
        for command, label in calls
        if label in {"node-tests", "vitest"}
        for path in command
        if path.endswith(".test.ts")
    ) == Counter((*plan.node_tests, *plan.vitest_tests))
    execute(ROOT, {}, plan, stage="php")
    for label in (
        "php-lint-harness",
        "php-lint-source",
        "php-lint-generated",
        "php-runtime-source",
        "php-runtime-generated",
    ):
        assert sum(observed_label == label for _, observed_label in calls) == 1


@pytest.mark.parametrize(("index", "total"), [(0, 8), (9, 8), (1, 0)])
def test_invalid_shards_fail(index: int, total: int) -> None:
    with pytest.raises(ValueError, match="test shard index"):
        belongs_to_shard("test", index, total)
