"""Deterministic generation and static safety tests for ST-1506."""

from __future__ import annotations

import ast
import os
import runpy
import shutil
import stat
import sys
from pathlib import Path

import pytest
import yaml

from scripts import build_st1506_production_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_render_outputs_match_committed_bytes() -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    for relative, expected in outputs.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == expected


def test_check_is_read_only_on_success() -> None:
    paths = tuple(REPOSITORY_ROOT / path for path in generator.GENERATED_PATHS)
    before = _snapshot(paths)
    generator.build(REPOSITORY_ROOT, check=True)
    assert _snapshot(paths) == before


def test_manifest_inventory_hashes_and_boundary_are_complete() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    for row in manifest["source_artifacts"]:
        path = REPOSITORY_ROOT / row["uri"].removeprefix("repo://")
        content = path.read_bytes()
        assert row["bytes"] == len(content)
        assert row["sha256"] == generator.sha256_bytes(content)
    plan = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": plan.stat().st_size,
            "sha256": generator.sha256_file(plan),
        }
    ]
    boundary = manifest["boundary"]
    assert boundary["environment_label"] == "PRODUCTION"
    assert boundary["reference_region_metadata"] == "ap-northeast-1"
    assert boundary["reference_region_use"] == "METADATA_ONLY"
    assert boundary["apply_target"] is None
    assert boundary["activation"] == "DISABLED"
    assert boundary["approval_artifact_count"] == 0
    assert boundary["action_counts"] == {
        name: 0 for name in generator.ACTION_COUNT_NAMES
    }
    assert boundary["formal_tst_032"] == "NOT_EXECUTED"
    assert boundary["production"] == "NOT_EXECUTED"


def test_manifest_pins_authority_and_immediate_plus_transitive_predecessors() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["provenance"]["authority_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.AUTHORITY_SOURCES.items()
    ]
    assert manifest["provenance"]["predecessor_inputs"] == [
        {"uri": f"repo://{path}", "sha256": digest}
        for path, digest in generator.PREDECESSOR_SOURCES.items()
    ]
    assert manifest["provenance"]["implementation_authority_inputs"] == [
        {
            "uri": generator.HANDOFF_URI,
            "bytes": generator.HANDOFF_BYTES,
            "sha256": generator.HANDOFF_SHA256,
        },
        {
            "uri": generator.APPROVAL_URI,
            "bytes": generator.APPROVAL_BYTES,
            "sha256": generator.APPROVAL_SHA256,
        },
    ]
    assert manifest["provenance"]["approved_preimplementation_inputs"] == list(
        generator.load_and_validate_contract(
            REPOSITORY_ROOT
        ).approved_preimplementation_inputs
    )
    assert len(manifest["provenance"]["approved_preimplementation_inputs"]) == 22

    current = manifest["provenance"]["current_development_rebinding"]
    assert current["classification"] == "REVERSIBLE_REPOSITORY_DEVELOPMENT_ONLY"
    assert {
        key: current[key] for key in generator.CURRENT_DEVELOPMENT_REBINDING_POLICY
    } == generator.CURRENT_DEVELOPMENT_REBINDING_POLICY
    assert current["authority_source"] == {
        "uri": f"repo://{generator.STANDING_DEVELOPMENT_AUTHORITY_PATH}",
        "bytes": generator.STANDING_DEVELOPMENT_AUTHORITY_BYTES,
        "sha256": generator.STANDING_DEVELOPMENT_AUTHORITY_SHA256,
        "authority": "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION",
    }
    assert current["historical_authority_source"] == {
        "uri": "repo://AGENTS.md",
        "bytes": generator.HISTORICAL_STANDING_DEVELOPMENT_AUTHORITY_BYTES,
        "sha256": generator.HISTORICAL_STANDING_DEVELOPMENT_AUTHORITY_SHA256,
        "mutation": "FORBIDDEN",
    }
    assert current["current_authority_inputs"] == [
        {
            "uri": f"repo://{path}",
            "bytes": binding[0],
            "sha256": binding[1],
        }
        for path, binding in generator.CURRENT_DEVELOPMENT_SOURCE_OVERRIDES.items()
    ]
    assert current["historical_source_rows_preserved"] is True
    assert current["semantic_delta_from_approved_interface"] == "NONE"
    assert current["repository_git_authority"] == (
        "ROOT_STANDING_DEVELOPMENT_AUTHORIZATION"
    )
    assert current["external_authority"] == "NONE"


def test_generated_plan_records_detached_authority_and_exact_interface() -> None:
    model = generator.load_and_validate_contract(REPOSITORY_ROOT)
    plan = generator.reference_plan_document(model)
    assert plan["document"]["version"] == "1.1.0"
    assert plan["implementation_authority"] == {
        "story_id": "ST-1506",
        "handoff_uri": generator.HANDOFF_URI,
        "handoff_bytes": generator.HANDOFF_BYTES,
        "handoff_sha256": generator.HANDOFF_SHA256,
        "approval_uri": generator.APPROVAL_URI,
        "approval_bytes": generator.APPROVAL_BYTES,
        "approval_sha256": generator.APPROVAL_SHA256,
        "status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_authority": (
            "ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1_ONLY"
        ),
        "open_decisions": [],
    }
    assert (
        plan["wordpress_signed_delivery_interface"]
        == model.contract["wordpress_signed_delivery_interface"]
    )


def test_full_render_consumes_each_validated_source_snapshot_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protected = (
        generator.CONTRACT_PATH,
        generator.HANDOFF_PATH,
        generator.APPROVAL_PATH,
    )
    calls: dict[Path, int] = {}
    original_reader = generator._read_repository_file

    def guarded_reader(
        root: Path,
        relative: Path,
        field: str,
        *,
        max_bytes: int,
        size_error_code: str,
    ) -> bytes:
        calls[relative] = calls.get(relative, 0) + 1
        if calls[relative] > 1:
            return b"rejected second source read\n"
        return original_reader(
            root,
            relative,
            field,
            max_bytes=max_bytes,
            size_error_code=size_error_code,
        )

    monkeypatch.setattr(generator, "_read_repository_file", guarded_reader)
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    assert all(count == 1 for count in calls.values())
    assert {relative: calls[relative] for relative in protected} == {
        relative: 1 for relative in protected
    }


def test_predecessor_snapshot_ignores_ambient_temp_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    poisoned = tmp_path / "ambient-temp-must-remain-empty"
    poisoned.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(poisoned))
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    assert set(outputs) == set(generator.GENERATED_PATHS)
    assert list(poisoned.iterdir()) == []


def test_check_rejects_drift_without_writing_or_echoing_bytes(
    tmp_path: Path,
) -> None:
    outputs = generator.render_outputs(REPOSITORY_ROOT)
    for relative, content in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    marker = b"REJECTED_OUTPUT_MARKER_1506"
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    target.write_bytes(marker)
    before = _snapshot(tuple(tmp_path / path for path in generator.GENERATED_PATHS))
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, outputs)
    assert captured.value.code == "GENERATED_OUTPUT_DRIFT"
    assert marker.decode("ascii") not in str(captured.value)
    assert (
        _snapshot(tuple(tmp_path / path for path in generator.GENERATED_PATHS))
        == before
    )


def test_check_rejects_missing_and_unsafe_outputs_without_escape(
    tmp_path: Path,
) -> None:
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "GENERATED_OUTPUT_MISSING"
    assert list(tmp_path.iterdir()) == []

    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "infra").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator.check_outputs(tmp_path, generator.render_outputs(REPOSITORY_ROOT))
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert list(outside.iterdir()) == []


def test_atomic_writer_is_scoped_and_rejects_symlinks(tmp_path: Path) -> None:
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"first\n")
    generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"second\n")
    target = tmp_path / generator.REFERENCE_PLAN_PATH
    assert target.read_bytes() == b"second\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, generator.REFERENCE_PLAN_PATH, b"blocked\n")
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside.read_bytes() == b"outside"
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(tmp_path, Path("../escape"), b"blocked\n")
    assert captured.value.code == "UNSAFE_OUTPUT_PATH"


def test_physical_root_ancestor_swap_is_rejected_without_outside_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    physical = tmp_path / "physical-root-race-1506"
    repository = physical / "repository"
    repository.mkdir(parents=True)
    (repository / "input.txt").write_bytes(b"owned")
    moved = tmp_path / "physical-root-race-1506-owned"
    outside = tmp_path / "outside-root"
    outside_repository = outside / "repository"
    outside_repository.mkdir(parents=True)
    outside_marker = outside_repository / "input.txt"
    outside_marker.write_bytes(b"outside")
    original_open = generator.os.open
    swapped = False

    def interleaved_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == physical.name and dir_fd is not None and not swapped:
            swapped = True
            physical.rename(moved)
            physical.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", interleaved_open)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            repository,
            Path("input.txt"),
            "hostile",
            max_bytes=16,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSAFE_ROOT_TYPE"
    assert outside_marker.read_bytes() == b"outside"


def test_default_root_binding_is_lexical_and_rejects_symlinked_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside-root"
    marker = outside / generator.CONTRACT_PATH
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"outside")
    linked_root = tmp_path / "linked-repository"
    linked_root.symlink_to(outside, target_is_directory=True)
    script_path = linked_root / "scripts/build_st1506_production_deployment.py"
    lexical_root = generator._lexical_repository_root(script_path)
    assert lexical_root == linked_root

    original_read = generator.os.read
    reads = 0

    def counted_read(descriptor: int, size: int) -> bytes:
        nonlocal reads
        reads += 1
        return original_read(descriptor, size)

    monkeypatch.setattr(generator.os, "read", counted_read)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            lexical_root,
            generator.CONTRACT_PATH,
            "default_root",
            max_bytes=16,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSAFE_ROOT_TYPE"
    assert captured.value.field == "default_root"
    assert reads == 0
    assert marker.read_bytes() == b"outside"


def test_symlinked_default_root_stops_before_predecessor_module_execution(
    tmp_path: Path,
) -> None:
    linked_root = tmp_path / "linked-repository"
    linked_root.symlink_to(REPOSITORY_ROOT, target_is_directory=True)
    linked_builder = linked_root / "scripts/build_st1506_production_deployment.py"
    original_sys_path = list(sys.path)
    try:
        namespace = runpy.run_path(str(linked_builder), run_name="st1506_linked_cli")
    finally:
        sys.path[:] = original_sys_path

    predecessor_name = "scripts.build_st1505_staging_deployment"
    predecessor_before = sys.modules.get(predecessor_name)
    with pytest.raises(Exception) as captured:
        namespace["build"]()
    assert getattr(captured.value, "code", None) == "UNSAFE_ROOT_TYPE"
    assert getattr(captured.value, "field", None) == "contract"
    assert sys.modules.get(predecessor_name) is predecessor_before


def test_preexisting_predecessor_module_symlink_is_never_read_or_executed(
    tmp_path: Path, contract_document: dict[str, object]
) -> None:
    repository = tmp_path / "repository"
    handoff = yaml.safe_load((REPOSITORY_ROOT / generator.HANDOFF_PATH).read_bytes())
    handoff_refs = tuple(
        row["uri"].removeprefix("repo://")
        for row in handoff["DESIGN_HANDOFF_V1"]["source_design_refs"]
        if row["uri"].startswith("repo://")
    )
    for relative in dict.fromkeys((*generator.PINNED_SOURCES, *handoff_refs)):
        source = REPOSITORY_ROOT / relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    execution_marker = tmp_path / "outside-executed"
    outside_module = tmp_path / "outside-predecessor.py"
    outside_module.write_text(
        "from pathlib import Path\n"
        f"Path({str(execution_marker)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    predecessor_module = repository / "scripts/build_st1505_staging_deployment.py"
    predecessor_module.parent.mkdir(parents=True, exist_ok=True)
    predecessor_module.symlink_to(outside_module)

    model = generator.validate_contract(contract_document, repository)
    assert model.contract["document"]["story_id"] == "ST-1506"
    assert not execution_marker.exists()


def test_repository_ancestor_and_leaf_swaps_are_rejected_without_outside_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    owned = root / "owned"
    owned.mkdir(parents=True)
    (owned / "input.txt").write_bytes(b"owned")
    moved = root / "owned-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_marker = outside / "input.txt"
    outside_marker.write_bytes(b"outside")
    original_open = generator.os.open
    swapped = False

    def ancestor_swap_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "owned" and dir_fd is not None and not swapped:
            swapped = True
            owned.rename(moved)
            owned.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", ancestor_swap_open)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            root,
            Path("owned/input.txt"),
            "hostile",
            max_bytes=16,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert outside_marker.read_bytes() == b"outside"

    monkeypatch.setattr(generator.os, "open", original_open)
    owned.unlink()
    moved.rename(owned)
    leaf = owned / "input.txt"
    swapped = False

    def leaf_swap_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "input.txt" and dir_fd is not None and not swapped:
            swapped = True
            leaf.unlink()
            leaf.symlink_to(outside_marker)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", leaf_swap_open)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            root,
            Path("owned/input.txt"),
            "hostile",
            max_bytes=16,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSAFE_FILE_TYPE"
    assert outside_marker.read_bytes() == b"outside"


def test_output_ancestor_and_target_swaps_never_touch_outside_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    owned = root / "owned"
    owned.mkdir(parents=True)
    moved = root / "owned-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_marker = outside / "marker.txt"
    outside_marker.write_bytes(b"outside")
    original_open = generator.os.open
    swapped = False

    def ancestor_swap_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "owned" and dir_fd is not None and not swapped:
            swapped = True
            owned.rename(moved)
            owned.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(generator.os, "open", ancestor_swap_open)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(root, Path("owned/output.json"), b"blocked\n")
    assert captured.value.code == "UNSAFE_OUTPUT_ANCESTOR"
    assert outside_marker.read_bytes() == b"outside"
    assert not (outside / "output.json").exists()

    monkeypatch.setattr(generator.os, "open", original_open)
    owned.unlink()
    moved.rename(owned)
    target = owned / "output.json"
    target.write_bytes(b"old\n")
    original_replace = generator.os.replace
    replaced = False

    def target_swap_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal replaced
        if not replaced:
            replaced = True
            target.unlink()
            target.symlink_to(outside_marker)
        original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(generator.os, "replace", target_swap_replace)
    generator._atomic_write(root, Path("owned/output.json"), b"new\n")
    assert target.read_bytes() == b"new\n"
    assert outside_marker.read_bytes() == b"outside"


@pytest.mark.parametrize(
    "flag_name", ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
)
def test_missing_required_safe_io_flag_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag_name: str
) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"owned")
    monkeypatch.setattr(generator.os, flag_name, 0)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._read_repository_file(
            tmp_path,
            Path("input.txt"),
            "hostile",
            max_bytes=16,
            size_error_code="FILE_SIZE_LIMIT",
        )
    assert captured.value.code == "UNSUPPORTED_SAFE_IO"
    assert captured.value.field == "filesystem"


def test_descriptor_cleanup_close_error_does_not_leak_or_mask_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "owned/nested/input.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"owned")
    original_close = generator.os.close
    closed: list[int] = []
    raised = False

    def close_then_raise_once(descriptor: int) -> None:
        nonlocal raised
        original_close(descriptor)
        closed.append(descriptor)
        if not raised:
            raised = True
            raise OSError("simulated close failure")

    monkeypatch.setattr(generator.os, "close", close_then_raise_once)
    content = generator._read_repository_file(
        tmp_path,
        Path("owned/nested/input.txt"),
        "cleanup",
        max_bytes=16,
        size_error_code="FILE_SIZE_LIMIT",
    )
    assert content == b"owned"
    assert raised is True
    assert len(closed) >= 4


def test_repository_file_snapshot_captures_content_and_mode_from_one_descriptor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"owned")
    path.chmod(0o640)
    snapshot = generator._read_repository_file_snapshot(
        tmp_path,
        Path("input.txt"),
        "snapshot",
        max_bytes=16,
        size_error_code="FILE_SIZE_LIMIT",
    )
    assert snapshot == generator.RepositoryFileSnapshot(content=b"owned", mode=0o640)


def test_atomic_cleanup_unlink_error_preserves_primary_error_and_closes_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_descriptors: list[int] = []
    original_open_parent = generator._open_output_parent

    def captured_open_parent(root: Path, relative: Path, *, create: bool) -> int:
        descriptor = original_open_parent(root, relative, create=create)
        parent_descriptors.append(descriptor)
        return descriptor

    def failed_write(_descriptor: int, _content: object) -> int:
        raise OSError("simulated primary write failure")

    def failed_cleanup_unlink(_path: str, *, dir_fd: int | None = None) -> None:
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(generator, "_open_output_parent", captured_open_parent)
    monkeypatch.setattr(generator.os, "write", failed_write)
    monkeypatch.setattr(generator.os, "unlink", failed_cleanup_unlink)
    with pytest.raises(generator.ProductionDeploymentContractError) as captured:
        generator._atomic_write(
            tmp_path,
            Path("owned/output.json"),
            b"blocked",
        )
    assert captured.value.code == "OUTPUT_WRITE_FAILED"
    assert captured.value.field == "output"
    assert len(parent_descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(parent_descriptors[0])


def test_builder_has_no_env_network_process_provider_or_deployment_surface() -> None:
    path = REPOSITORY_ROOT / "scripts/build_st1506_production_deployment.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_attributes.add(node.func.attr)
    assert imported_roots.isdisjoint(
        {
            "boto3",
            "botocore",
            "github",
            "http",
            "playwright",
            "requests",
            "selenium",
            "socket",
            "subprocess",
            "terraform",
            "urllib",
        }
    )
    assert called_names.isdisjoint({"eval", "exec", "compile"})
    assert called_attributes.isdisjoint(
        {
            "check_call",
            "check_output",
            "connect",
            "environ",
            "getenv",
            "popen",
            "run",
            "spawn",
            "system",
            "urlopen",
        }
    )


def test_cli_accepts_only_optional_exact_check() -> None:
    assert generator.parse_args([]).check is False
    assert generator.parse_args(["--check"]).check is True
    for arguments in (
        ["--chec"],
        ["--check", "--check"],
        ["--deploy"],
        ["--region", "ap-northeast-1"],
        ["--credential", "value"],
        ["--help"],
    ):
        with pytest.raises(SystemExit):
            generator.parse_args(arguments)


def test_owned_sources_contain_no_sensitive_material() -> None:
    forbidden = (
        "AK" + "IA",
        "BEGIN PRIVATE" + " KEY",
        "aws_secret" + "_access_key",
        "github" + "_token",
        ".secret" + "s/",
    )
    for relative in generator.SOURCE_ARTIFACT_PATHS:
        text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden)
