"""Repository command, documentation, and Story-boundary checks."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys

from conftest import REPO_ROOT


def test_make_targets_separate_mutation_from_read_only_gate() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "contract-install: | python-sync" in makefile
    for target in (
        "contract-check",
        "contract-verify",
        "contract-test",
        "contract-gate",
    ):
        assert f"{target}:\n" in makefile
        assert f"{target}: | python-sync" not in makefile
    assert "UV_READONLY_RUN :=" in makefile
    assert "--locked --offline --no-cache" in makefile
    assert "--no-sync --no-env-file --no-python-downloads" in makefile
    gate = makefile.split("contract-gate:\n", maxsplit=1)[1]
    assert "build_st0104_contract_repository.py --check" in gate
    assert "scripts/verify_contract_repository.py" in gate
    assert "pytest -p no:cacheprovider -q tests/st0104" in gate
    assert "build_st0104_contract_repository.py\n" not in gate


def test_readme_documents_layout_commands_and_formal_boundary() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "## Installed contract repository",
        "contracts/raos-v0.4/job-state.v1.yaml",
        "contracts/raos-v0.4/contracts/",
        "contract-repository.v0.4.json",
        "contract-install",
        "contract-check",
        "contract-verify",
        "contract-test",
        "contract-gate",
        "scripts/python_toolchain.sh --uv /absolute/path/to/uv",
        "not formal TST-002 CI evidence",
        "scripts/contract_validation_resources/",
        "2,940 OpenAPI references",
        "557 AsyncAPI references",
        "all 3,844 physical `$ref` occurrences",
        "all 192 references to remain at their frozen document/JSON-Pointer locations",
        "all 99 schema-bearing catalog paths",
        "seven meta-validated embedded public-resource schemas",
        "Wrong-category targets",
        "non-schema Reference Object cycles fail closed",
    ):
        assert required in readme
    assert "generate Python/TypeScript types" in readme


def test_pinned_specification_resources_are_documented_and_hash_bound() -> None:
    resource_root = REPO_ROOT / "scripts" / "contract_validation_resources"
    expected = {
        "openapi-3.1-schema-2025-11-23.json": (
            "1b8ccc6e34234b17536f2dd0eb3597142a32bd108438cd42471a5fca4c1a07ef"
        ),
        "asyncapi-3.0.0-schema.json": (
            "d4571a420e6ffb7fcc7066c95a6db1202f299a3c51daa103d0706bf30f95e626"
        ),
        "OPENAPI-LICENSE.txt": (
            "4948367c65e1ce06690e2cadc6e86fce1a6a6db55ef874ce4b78c0f472ce5f13"
        ),
        "ASYNCAPI-LICENSE.txt": (
            "43070e2d4e532684de521b885f385d0841030efa2b1a20bafb76133a5e1379c1"
        ),
    }
    provenance = (resource_root / "README.md").read_text(encoding="utf-8")
    for name, digest in expected.items():
        payload = (resource_root / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest
        assert name in provenance
        assert digest in provenance or name.endswith("LICENSE.txt")
    assert "spec.openapis.org/oas/3.1/schema/2025-11-23" in provenance
    assert "e609fc2341007395d75df5756fc6fccf662c2087" in provenance


def test_agents_records_contract_ownership_and_non_goals() -> None:
    instructions = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for required in (
        "wrapper command `contract-install`",
        "wrapper command `contract-check`",
        "`contract-verify`",
        "`contract-test`",
        "`contract-gate`",
        "contracts/raos-v0.4/{job-state.v1.yaml,contracts/**}",
        "hash 固定済み payload を平坦化または書き換えたり",
        "scripts/contract_validation_resources/",
    ):
        assert required in instructions


def test_python_evidence_wrapper_dispatches_every_contract_command() -> None:
    wrapper = REPO_ROOT / "scripts" / "python_toolchain.sh"
    content = wrapper.read_text(encoding="utf-8")
    for command in (
        "contract-install",
        "contract-check",
        "contract-verify",
        "contract-test",
        "contract-gate",
    ):
        assert f"{command}) target={command} ;;" in content
    syntax = subprocess.run(
        ["bash", "-n", str(wrapper)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_execplan_and_worklog_preserve_proposal_only_status() -> None:
    plan = (REPO_ROOT / "docs" / "execplans" / "ST-0104.md").read_text(encoding="utf-8")
    log = (REPO_ROOT / "docs" / "worklogs" / "ST-0104.md").read_text(encoding="utf-8")
    assert "5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458" in plan
    assert "formal TST-002" in plan
    assert "canonical effective status" in plan
    assert "Effective canonical implementation status: `NOT_STARTED`" in log
    assert "Verification status: `NOT_EXECUTED`" in log
    assert "Formal TST-002 requires CI" in log


def test_workspace_marker_remains_source_generated_and_drift_free() -> None:
    marker = (REPO_ROOT / "contracts" / "README.md").read_text(encoding="utf-8")
    assert marker.startswith(
        "<!-- Generated from workspace-layout.json by scripts/bootstrap_workspace.py."
    )
    process = subprocess.run(
        [sys.executable, "scripts/bootstrap_workspace.py", "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["status"] == "PASS"
    assert result["changed"] == []


def test_loader_module_keeps_standard_library_only_runtime_boundary() -> None:
    source_path = REPO_ROOT / "python" / "raos" / "shared" / "contract_repository.py"
    assert source_path.is_file()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", maxsplit=1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])
    assert imported_roots <= sys.stdlib_module_names


def test_dependency_locks_remain_exact_after_the_later_codegen_story() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pydantic==2.13.4"' in pyproject
    assert '"datamodel-code-generator==0.71.0"' in pyproject
    assert '"pyyaml==6.0.3"' in pyproject
    assert '"jsonschema==4.26.0"' in pyproject
    assert '"referencing==0.37.0"' in pyproject
    assert (REPO_ROOT / "uv.lock").is_file()
    assert (REPO_ROOT / "package-lock.json").is_file()
