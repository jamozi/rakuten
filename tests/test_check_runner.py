"""The test partitions must be disjoint and cover every local test."""

from pathlib import Path
import subprocess
import sys

from scripts.raos_checks import PYTEST_GROUPS, check_documents

import pytest


def test_all_local_tests_belong_to_exactly_one_partition(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n serial\n database\n storage\n live\n external\n raos_owner_private\n"
    )
    (tmp_path / "test_sample.py").write_text("""import pytest
def test_parallel(): pass
@pytest.mark.serial
def test_serial(): pass
@pytest.mark.database
def test_database(): pass
@pytest.mark.storage
def test_storage(): pass
@pytest.mark.database
@pytest.mark.storage
def test_both(): pass
@pytest.mark.external
def test_external(): pass
@pytest.mark.live
def test_live(): pass
@pytest.mark.raos_owner_private
def test_private(): pass
""")
    observed: set[str] = set()
    for expression in PYTEST_GROUPS.values():
        result = subprocess.run(
            (
                sys.executable,
                "-m",
                "pytest",
                "--disable-plugin-autoload",
                "--collect-only",
                "-q",
                "-m",
                expression,
            ),
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        selected = {
            line
            for line in result.stdout.splitlines()
            if line.startswith("test_sample.py::")
        }
        assert not observed & selected
        observed.update(selected)
    assert observed == {
        f"test_sample.py::test_{name}"
        for name in ("parallel", "serial", "database", "storage", "both")
    }


def test_broken_local_document_link_is_reported(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](missing.md)\n")
    with pytest.raises(ValueError, match="broken document reference"):
        check_documents(tmp_path, ("README.md",))
    (tmp_path / "missing.md").write_text("target\n")
    check_documents(tmp_path, ("README.md",))
