"""Hostile boundary and exact-type cases for the ST-0308 reference builder."""

from __future__ import annotations

import ast
import copy
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from conftest import RepositoryHarness
from scripts import build_st0308_persistence_boundary_reference as builder
from scripts import build_st1506_production_deployment as secure_io


REPO_ROOT = Path(__file__).resolve().parents[2]


def _rejects(document: dict[str, Any]) -> None:
    with pytest.raises(builder.PersistenceReferenceError):
        builder.validate_contract(document, REPO_ROOT)


def test_missing_extra_and_reordered_top_level_keys(
    contract: dict[str, Any],
) -> None:
    missing = copy.deepcopy(contract)
    missing.pop("scope")
    _rejects(missing)

    extra = copy.deepcopy(contract)
    extra["unexpected"] = None
    _rejects(extra)

    keys = list(contract)
    keys[0], keys[1] = keys[1], keys[0]
    reordered = {key: copy.deepcopy(contract[key]) for key in keys}
    _rejects(reordered)


@pytest.mark.parametrize("section", ["sources", "ST-0304", "ST-0105"])
def test_bound_rows_reject_missing_extra_and_reordering(
    contract: dict[str, Any], section: str
) -> None:
    def rows(document: dict[str, Any]) -> list[dict[str, Any]]:
        if section == "sources":
            return cast(list[dict[str, Any]], document["sources"])
        return cast(
            list[dict[str, Any]],
            document["predecessor_bindings"][section]["rows"],
        )

    missing = copy.deepcopy(contract)
    rows(missing).pop()
    _rejects(missing)

    extra = copy.deepcopy(contract)
    rows(extra).append(copy.deepcopy(rows(extra)[-1]))
    _rejects(extra)

    reordered = copy.deepcopy(contract)
    rows(reordered)[0], rows(reordered)[1] = rows(reordered)[1], rows(reordered)[0]
    _rejects(reordered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uri", "repo://../escape"),
        ("uri", "repo:///absolute"),
        ("uri", "repo://docs\\escape"),
        ("bytes", False),
        ("bytes", "7943"),
        ("bytes", 7943.0),
        ("bytes", -1),
        ("sha256", "0" * 64),
        ("sha256", "invalid"),
    ],
)
def test_source_rows_reject_uri_bytes_and_hash_mutations(
    contract: dict[str, Any], field: str, value: object
) -> None:
    contract["sources"][0][field] = value
    _rejects(contract)


def test_bound_row_key_order_is_closed(contract: dict[str, Any]) -> None:
    original = contract["sources"][0]
    contract["sources"][0] = {
        "bytes": original["bytes"],
        "uri": original["uri"],
        "sha256": original["sha256"],
    }
    _rejects(contract)


def test_gap_registry_rejects_missing_extra_and_reordered_gaps(
    contract: dict[str, Any],
) -> None:
    missing = copy.deepcopy(contract)
    missing["local_design_gaps"]["gaps"].pop()
    _rejects(missing)

    extra = copy.deepcopy(contract)
    extra["local_design_gaps"]["gaps"].append(
        copy.deepcopy(extra["local_design_gaps"]["gaps"][-1])
    )
    _rejects(extra)

    reordered = copy.deepcopy(contract)
    gaps = reordered["local_design_gaps"]["gaps"]
    gaps[0], gaps[1] = gaps[1], gaps[0]
    _rejects(reordered)


@pytest.mark.parametrize("value", [False, 0, "", [], {}, "selected"])
@pytest.mark.parametrize("field", ["selected_value", "resolution_payload"])
def test_every_gap_selection_and_payload_must_be_exact_null(
    contract: dict[str, Any], field: str, value: object
) -> None:
    contract["local_design_gaps"]["gaps"][0][field] = value
    _rejects(contract)


@pytest.mark.parametrize("value", [False, 0, "", [], {}, "approved"])
@pytest.mark.parametrize(
    "field",
    [
        "repository_and_aggregate_inventory",
        "inward_port_contracts",
        "sqlalchemy_and_domain_mapping",
        "unit_of_work_and_session_lifecycle",
        "cross_module_writes_outbox_audit_and_idempotency",
        "connection_factory_and_workload_identity",
        "approved_handoff_uri",
        "approved_handoff_sha256",
        "conflict_free_canonical_reconciliation",
        "repository_owner_approval",
    ],
)
def test_every_selected_design_field_must_be_exact_null(
    contract: dict[str, Any], field: str, value: object
) -> None:
    contract["selected_design"][field] = value
    _rejects(contract)


def test_canonical_open_decision_population_is_rejected(
    contract: dict[str, Any],
) -> None:
    scope = copy.deepcopy(contract)
    scope["scope"]["open_decisions"] = ["ST0308-D1"]
    _rejects(scope)

    registry = copy.deepcopy(contract)
    registry["local_design_gaps"]["canonical_open_decision_count"] = 1
    registry["local_design_gaps"]["canonical_open_decisions"] = ["ST0308-D1"]
    _rejects(registry)


@pytest.mark.parametrize("value", [False, "0", 0.0, -1, 1])
@pytest.mark.parametrize(
    "section",
    ["implementation_inventory", "action_boundary.counts"],
)
def test_zero_counts_reject_bool_string_float_negative_and_nonzero(
    contract: dict[str, Any], section: str, value: object
) -> None:
    if section == "implementation_inventory":
        contract[section]["repository_ports"] = value
    else:
        contract["action_boundary"]["counts"]["repository_runtime"] = value
    _rejects(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda doc: doc["document"].__setitem__("executable", True),
        lambda doc: doc["activation"].__setitem__("enabled", True),
        lambda doc: doc["activation"].__setitem__("runtime_eligible", True),
        lambda doc: doc["activation"].__setitem__("status", "ACTIVE"),
        lambda doc: doc["activation"].__setitem__("authority", "GRANTED"),
        lambda doc: doc["evidence_boundary"].__setitem__("formal_tst_005", "PASS"),
        lambda doc: doc["evidence_boundary"].__setitem__(
            "acceptance_criteria_satisfied", True
        ),
        lambda doc: doc["downstream_boundary"].__setitem__(
            "st0308_runtime_readiness", True
        ),
        lambda doc: doc["scope"].__setitem__("implementation_status", "IMPLEMENTED"),
    ],
)
def test_executable_activation_status_and_readiness_promotions_are_rejected(
    contract: dict[str, Any], mutation: Callable[[dict[str, Any]], None]
) -> None:
    mutation(contract)
    _rejects(contract)


@pytest.mark.parametrize(
    "field",
    [
        "approved_handoff_uri",
        "approved_handoff_sha256",
        "conflict_free_canonical_reconciliation",
        "repository_owner_approval",
    ],
)
def test_activation_handoff_reconciliation_and_approval_stay_null(
    contract: dict[str, Any], field: str
) -> None:
    contract["activation"][field] = "populated"
    _rejects(contract)


def test_yaml_rejects_duplicate_alias_anchor_tag_and_multidoc(tmp_path: Path) -> None:
    samples = (
        "document: 1\ndocument: 2\n",
        "document: &a {}\ncopy: *a\n",
        "document: !unsafe value\n",
        "document: {}\n---\ndocument: {}\n",
    )
    for index, sample in enumerate(samples):
        path = tmp_path / f"hostile-{index}.yaml"
        path.write_text(sample, encoding="utf-8")
        with pytest.raises(secure_io.ProductionDeploymentContractError):
            secure_io.load_yaml(path)


def test_repository_file_boundary_rejects_symlink_fifo_directory_and_oversize(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target"
    target.write_bytes(b"safe")

    symlink = root / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(builder.PersistenceReferenceError):
        builder._read_bound_file(root, Path("symlink"), "test")

    fifo = root / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(builder.PersistenceReferenceError):
        builder._read_bound_file(root, Path("fifo"), "test")

    directory = root / "directory"
    directory.mkdir()
    with pytest.raises(builder.PersistenceReferenceError):
        builder._read_bound_file(root, Path("directory"), "test")

    oversized = root / "oversized"
    oversized.write_bytes(b"x" * (builder.MAX_BOUND_FILE_BYTES + 1))
    with pytest.raises(builder.PersistenceReferenceError, match="SIZE_LIMIT"):
        builder._read_bound_file(root, Path("oversized"), "test")


def test_predecessor_and_source_byte_changes_are_rejected(
    repository_harness: RepositoryHarness,
) -> None:
    builder.load_and_validate_contract(repository_harness.root)
    paths = (
        Path(builder.SOURCE_ROWS[0][0]),
        Path(builder.ST0304_ROWS[0][0]),
        Path(builder.ST0105_ROWS[0][0]),
    )
    for relative in paths:
        target = repository_harness.root / relative
        target.chmod(0o600)
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(builder.PersistenceReferenceError):
            builder.load_and_validate_contract(repository_harness.root)
        target.write_bytes(original)


def test_st0105_output_byte_change_is_rejected(
    repository_harness: RepositoryHarness,
) -> None:
    manifest = json.loads(
        (repository_harness.root / "changes/st-0105/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    relative = Path(manifest["outputs"]["artifacts"][0]["path"])
    target = repository_harness.root / relative
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(builder.PersistenceReferenceError):
        builder.load_and_validate_contract(repository_harness.root)


def test_output_ancestor_symlink_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "changes").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        builder,
        "render_outputs",
        lambda _root: {
            builder.REFERENCE_PLAN_PATH: b"{}\n",
            builder.MANIFEST_PATH: b"document: {}\n",
        },
    )

    with pytest.raises(builder.PersistenceReferenceError):
        builder.build(root)


@pytest.mark.parametrize("target_kind", ["directory", "fifo", "symlink"])
def test_nonregular_or_symlink_output_target_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_kind: str
) -> None:
    root = tmp_path / "repository"
    target = root / builder.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    if target_kind == "directory":
        target.mkdir()
    elif target_kind == "fifo":
        os.mkfifo(target)
    else:
        outside = tmp_path / "outside"
        outside.write_bytes(b"outside")
        target.symlink_to(outside)
    monkeypatch.setattr(
        builder,
        "render_outputs",
        lambda _root: {
            builder.REFERENCE_PLAN_PATH: b"{}\n",
            builder.MANIFEST_PATH: b"document: {}\n",
        },
    )

    with pytest.raises(builder.PersistenceReferenceError):
        builder.build(root)


def test_all_prohibited_interpretation_mutations_fail_check(
    repository_harness: RepositoryHarness,
) -> None:
    builder.build(repository_harness.root)
    target = repository_harness.root / builder.REFERENCE_PLAN_PATH
    original = target.read_bytes()
    document = json.loads(original)

    def remove(values: list[str]) -> None:
        values.pop()

    def append(values: list[str]) -> None:
        values.append("EXTRA_INTERPRETATION")

    def reorder(values: list[str]) -> None:
        values.reverse()

    mutations: tuple[Callable[[list[str]], None], ...] = (remove, append, reorder)
    for mutation in mutations:
        changed = copy.deepcopy(document)
        mutation(cast(list[str], changed["prohibited_interpretations"]))
        target.write_text(
            json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(builder.PersistenceReferenceError):
            builder.build(repository_harness.root, check=True)
        target.write_bytes(original)


def test_builder_ast_has_no_external_or_runtime_implementation_surface() -> None:
    path = REPO_ROOT / builder.GENERATOR_PATH
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_import_roots = {
        "alembic",
        "asyncpg",
        "boto3",
        "httpx",
        "playwright",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", maxsplit=1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])
    assert imported_roots.isdisjoint(forbidden_import_roots)

    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_attributes.isdisjoint(
        {
            "connect",
            "execute",
            "getenv",
            "popen",
            "request",
            "run",
            "system",
            "urlopen",
        }
    )
    source = path.read_text(encoding="utf-8")
    assert "python.raos.domain" not in source
    assert "python.raos.ports" not in source
    assert "python.raos.adapters" not in source
