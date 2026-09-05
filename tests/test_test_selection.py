"""Regression tests for selection completeness and read-only planning."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.raos_build_core import BuildInput, BuildSpec, InputKind, changed_paths
from scripts.raos_test_plan import create_plan


def repository(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    subprocess.run(("git", "add", "."), cwd=tmp_path, check=True)
    return tmp_path


def test_test_only_change_runs_itself_without_generators(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "tests/test_one.py": "def test_one(): pass\n",
            "tests/test_other.py": "def test_other(): pass\n",
        },
    )
    plan = create_plan(root, {}, (Path("tests/test_one.py"),))
    assert plan.python_tests == ("tests/test_one.py",)
    assert not plan.full
    assert not plan.generators


def test_shared_import_and_relative_test_helper_reach_all_consumers(
    tmp_path: Path,
) -> None:
    root = repository(
        tmp_path,
        {
            "python/raos/shared.py": "VALUE = 1\n",
            "python/raos/service.py": "from raos import shared\n",
            "tests/group/support.py": "from raos.service import VALUE\n",
            "tests/group/test_one.py": "from .support import VALUE\n",
            "tests/test_two.py": "from raos.shared import VALUE\n",
            "tests/test_other.py": "def test_other(): pass\n",
        },
    )
    plan = create_plan(root, {}, (Path("python/raos/shared.py"),))
    assert set(plan.python_tests) == {"tests/group/test_one.py", "tests/test_two.py"}
    assert not plan.full


@pytest.mark.parametrize("removed", (False, True))
def test_fixture_reference_and_deletion_select_consumer(
    tmp_path: Path, removed: bool
) -> None:
    root = repository(
        tmp_path,
        {
            "fixtures/recorded.json": "{}\n",
            "tests/test_input.py": 'INPUT = "fixtures/recorded.json"\n',
            "tests/test_other.py": "def test_other(): pass\n",
        },
    )
    if removed:
        (root / "fixtures/recorded.json").unlink()
    plan = create_plan(root, {}, (Path("fixtures/recorded.json"),))
    assert plan.python_tests == ("tests/test_input.py",)
    assert not plan.full


def test_directory_input_selects_owner_and_downstream_tests(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "config/inputs/new.json": "{}\n",
            "tests/test_owner.py": "",
            "tests/test_consumer.py": "",
            "scripts/build_owner.py": "",
        },
    )
    owner = BuildSpec(
        "build_owner",
        (),
        Path("scripts/build_owner.py"),
        (BuildInput("repo://config/inputs", InputKind.TRACKED),),
        (Path("generated/value.json"),),
        (),
        (Path("tests/test_owner.py"),),
        True,
        False,
    )
    consumer = BuildSpec(
        "build_consumer",
        (),
        Path("scripts/build_consumer.py"),
        (),
        (Path("generated/consumer.json"),),
        ("build_owner",),
        (Path("tests/test_consumer.py"),),
        True,
        False,
    )
    plan = create_plan(
        root,
        {o.owner_id: o for o in (owner, consumer)},
        (Path("config/inputs/new.json"),),
    )
    assert plan.generators == ("build_owner", "build_consumer")
    assert set(plan.python_tests) == {"tests/test_owner.py", "tests/test_consumer.py"}
    assert not plan.full


def test_plain_docs_do_not_select_product_tests(tmp_path: Path) -> None:
    root = repository(tmp_path, {"README.md": "# Hi\n", "tests/test_other.py": ""})
    plan = create_plan(root, {}, (Path("README.md"),))
    assert plan.documents == ("README.md",)
    assert not plan.python_tests
    assert not plan.jobs["tests"]
    assert not plan.full


@pytest.mark.parametrize(
    "path",
    ("uv.lock", "tests/conftest.py", "scripts/raos_test_plan.py", "new/unknown.yaml"),
)
def test_shared_or_unmapped_input_falls_back_to_full(tmp_path: Path, path: str) -> None:
    root = repository(
        tmp_path, {path: "", "tests/test_one.py": "", "tests/test_two.py": ""}
    )
    plan = create_plan(root, {}, (Path(path),))
    assert plan.full
    assert plan.full_reasons
    assert set(plan.python_tests) == {"tests/test_one.py", "tests/test_two.py"}


def test_rename_spaces_and_untracked_test_are_in_changed_paths(tmp_path: Path) -> None:
    root = repository(
        tmp_path, {"tests/with space/test_old.py": "def test_old(): pass\n"}
    )
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ),
        cwd=root,
        check=True,
    )
    (root / "tests/with space/test_old.py").rename(
        root / "tests/with space/test_new.py"
    )
    subprocess.run(("git", "add", "-A"), cwd=root, check=True)
    (root / "tests/test_untracked.py").write_text("def test_new(): pass\n")
    paths = changed_paths(root=root, base="HEAD")
    assert set(paths) == {
        Path("tests/with space/test_old.py"),
        Path("tests/with space/test_new.py"),
        Path("tests/test_untracked.py"),
    }
    plan = create_plan(root, {}, paths)
    assert set(plan.python_tests) == {
        "tests/with space/test_new.py",
        "tests/test_untracked.py",
    }


def test_js_imports_and_vitest_are_routed_to_distinct_runners(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "packages/component.ts": "export const x = 1;\n",
            "tests/component.test.ts": "import { x } from '../packages/component.ts';\nimport { test } from 'node:test';\n",
            "tests/st0103/unit.test.ts": "import { test } from 'vitest';\n",
        },
    )
    plan = create_plan(
        root, {}, (Path("packages/component.ts"), Path("tests/st0103/unit.test.ts"))
    )
    assert plan.node_tests == ("tests/component.test.ts",)
    assert plan.vitest_tests == ("tests/st0103/unit.test.ts",)
    assert not plan.full


def test_planning_never_executes_generators_or_writes_outputs(tmp_path: Path) -> None:
    root = repository(tmp_path, {"tests/test_one.py": "", "README.md": "text"})
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    create_plan(root, {}, (Path("README.md"),))
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    assert before == after


def test_verification_catalog_literals_do_not_select_unrelated_tests(
    tmp_path: Path,
) -> None:
    root = repository(
        tmp_path,
        {
            "scripts/service.py": "VALUE = 1\n",
            "scripts/raos_build_core.py": 'OWNERS = ("scripts/service.py",)\n',
            "tests/test_service.py": "from scripts.service import VALUE\n",
            "tests/test_other.py": "from scripts.raos_build_core import OWNERS\n",
            "tests/conftest.py": 'SERIAL_MODULES = frozenset({"tests/test_service.py"})\n',
        },
    )
    plan = create_plan(root, {}, (Path("scripts/service.py"),))
    assert not plan.full
    assert plan.python_tests == ("tests/test_service.py",)


def test_generation_input_document_is_not_mistaken_for_plain_docs(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path, {"docs/input.md": "text", "tests/test_owner.py": ""})
    owner = BuildSpec(
        "build_owner",
        (),
        Path("scripts/build_owner.py"),
        (BuildInput("repo://docs/input.md", InputKind.TRACKED),),
        (Path("generated/value.json"),),
        (),
        (Path("tests/test_owner.py"),),
        True,
        False,
    )
    plan = create_plan(root, {owner.owner_id: owner}, (Path("docs/input.md"),))
    assert plan.generators == (owner.owner_id,)
    assert plan.python_tests == ("tests/test_owner.py",)


def test_edited_generated_manifest_still_runs_its_owner_check(tmp_path: Path) -> None:
    root = repository(tmp_path, {"changes/example/manifest.yaml": "tampered: true"})
    owner = BuildSpec(
        "build_owner",
        (),
        Path("scripts/build_owner.py"),
        (),
        (Path("changes/example/manifest.yaml"),),
        (),
        (),
        True,
        False,
    )
    plan = create_plan(
        root, {owner.owner_id: owner}, (Path("changes/example/manifest.yaml"),)
    )
    assert plan.generators == (owner.owner_id,)
