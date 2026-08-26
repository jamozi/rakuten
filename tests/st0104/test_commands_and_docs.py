"""Contract integrity and unified workflow documentation checks."""

from __future__ import annotations

import hashlib
import subprocess
import sys

from .support import REPO_ROOT


def test_contract_verification_is_integrated_into_final() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    gate = makefile.split("contracts:\n", 1)[1].split("\n\n", 1)[0]
    assert "build_st0104_contract_repository.py --check" in gate
    assert "scripts/verify_contract_repository.py" in gate
    assert "pytest -q tests/st0104" in gate
    assert "$(MAKE) contracts database storage" in makefile


def test_readme_documents_the_five_commands_and_external_boundary() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for command in ("make setup", "make generate", "make check", "make fast", "make final"):
        assert command in readme
    assert "docs/canonical" in readme
    assert "external" in readme.lower()
    for obsolete in (
        "python_toolchain.sh",
        "node_toolchain.sh",
        "codegen_toolchain.sh",
        "contract-install",
    ):
        assert obsolete not in readme


def test_pinned_specification_resources_remain_hash_bound() -> None:
    resource_root = REPO_ROOT / "scripts" / "contract_validation_resources"
    expected = {
        "openapi-3.1-schema-2025-11-23.json": "1b8ccc6e34234b17536f2dd0eb3597142a32bd108438cd42471a5fca4c1a07ef",
        "asyncapi-3.0.0-schema.json": "d4571a420e6ffb7fcc7066c95a6db1202f299a3c51daa103d0706bf30f95e626",
        "OPENAPI-LICENSE.txt": "4948367c65e1ce06690e2cadc6e86fce1a6a6db55ef874ce4b78c0f472ce5f13",
        "ASYNCAPI-LICENSE.txt": "43070e2d4e532684de521b885f385d0841030efa2b1a20bafb76133a5e1379c1",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((resource_root / name).read_bytes()).hexdigest() == digest


def test_agents_has_two_stop_classes_and_stays_compact() -> None:
    instructions = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for required in ("live 外部作用", "回復不能な操作", "make final"):
        assert required in instructions
    assert len(instructions.splitlines()) <= 80
    assert "exact SHA" not in instructions


def test_contract_repository_is_drift_free() -> None:
    check = subprocess.run(
        [sys.executable, "scripts/build_st0104_contract_repository.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert check.returncode == 0, f"{check.stdout}\n{check.stderr}"


def test_story_specific_python_wrapper_is_retired() -> None:
    assert not (REPO_ROOT / "scripts/python_toolchain.sh").exists()
