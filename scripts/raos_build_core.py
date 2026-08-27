"""Shared build graph and deterministic generator utilities for RAOS.

The registry deliberately treats normal repository files as version-controlled
inputs, not as hash-bound authorities. Checksums are retained only for immutable
or content-addressed material and generated outputs.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Final, NoReturn, TypedDict, TypeGuard, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
ACTIVE_MANIFEST_PATH: Final = Path("changes/build/manifest.v2.json")
BUILD_SCRIPT_GLOB: Final = "build_*.py"
BUILD_INFRASTRUCTURE_PATHS: Final = frozenset(
    {Path("scripts/raos_build.py"), Path("scripts/raos_build_core.py")}
)
STORY_PATTERN: Final = re.compile(r"st([0-9]{4})", re.IGNORECASE)
REPO_URI_PATTERN: Final = re.compile(r"repo://([^#\s]+)")
HEX64_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
OUTPUT_OWNER_OVERRIDES: Final = {
    Path("docker-compose.yml"): "build_local_compose",
}
OWNER_PRIVATE_OWNER_IDS: Final = frozenset(
    {
        "build_st1703_self_hosted_runtime_manifest",
        "build_st1703_self_hosted_theme",
        "build_st1704_self_hosted_theme",
    }
)
DECLARED_OUTPUT_MANIFESTS: Final = {
    "build_st0002_revision": Path("changes/st-0002/manifest.yaml"),
    "build_st0003_revision": Path("changes/st-0003/manifest.yaml"),
    "build_st0004_revision": Path("changes/st-0004/manifest.yaml"),
    "build_st0005_status": Path("changes/st-0005/manifest.yaml"),
    "build_st0006_decision_gates": Path("changes/st-0006/manifest.yaml"),
    "build_st0104_contract_repository": Path(
        "contracts/raos-v0.4/contract-repository.v0.4.json"
    ),
    "build_st0105_generated_contracts": Path("changes/st-0105/manifest.json"),
}
EXPLICIT_OWNER_OUTPUTS: Final = {
    "build_st0106_reviewed_findings_rebind": (
        Path("changes/st-0106/contracts/reviewed-secret-findings.v3.yaml"),
        Path("changes/st-0106/generated/reviewed-findings-rebind.v3.manifest.json"),
    ),
    "build_st1704_self_hosted_editorial_manifest": (
        Path("changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"),
    ),
}
EXPLICIT_OWNER_DEPENDENCIES: Final[dict[str, tuple[str, ...]]] = {
    # Some predecessor paths are declared by YAML contracts rather than Python
    # constants. Keep those semantic edges explicit so affected generation never
    # relies on a legacy digest to discover ordering.
    "build_st0203_queue_fake": ("build_local_compose",),
    "build_st0707_evaluation_harness_runtime": (
        "build_st0705_ai_output_validation_runtime",
    ),
    "build_st0307_migration_fixtures": ("build_st0306_database_roles",),
    "build_st0308_persistence": ("build_st0307_migration_fixtures",),
    "build_st0604_source_packet_lifecycle_runtime": (
        "build_st0602_fact_extraction_runtime",
        "build_st0603_fact_conflict_runtime",
    ),
    "build_st0605_claim_evidence_runtime": (
        "build_st0604_source_packet_lifecycle_runtime",
    ),
    "build_st0708_openai_live_bounded_evaluation_reference_plan": (
        "build_st0707_evaluation_harness_runtime",
    ),
    "build_st0709_ai_governance_workspace": (
        "build_st0705_ai_output_validation_runtime",
        "build_st0707_evaluation_harness_runtime",
        "build_st0708_openai_live_bounded_evaluation_reference_plan",
    ),
    "build_st0905_publication_commands_runtime_v2": (
        "build_st0903_publication_snapshot_runtime_v2",
        "build_st0904_public_projection_runtime_v2",
    ),
    "build_st1002_public_article_renderer": (
        "build_st0904_public_projection_runtime_v2",
    ),
    "build_st1004_disclosure_affiliate_runtime": (
        "build_st1002_public_article_renderer",
    ),
    "build_st1105_admin_visual_accessibility": (
        "build_st0606_evidence_workspace_v2",
        "build_st0709_ai_governance_workspace",
        "build_st0906_publication_review_workspace_v2",
        "build_st1102_article_workspace_v2",
        "build_st1103_freshness_operations_workspace",
        "build_st1104_analytics_finance_dashboard",
    ),
    "build_st1202_public_event_instrumentation": (
        "build_st1002_public_article_renderer",
        "build_st1004_disclosure_affiliate_runtime",
    ),
    "build_st1502_data_services": ("build_st1501_terraform_foundation",),
    "build_st1503_compute_edge": ("build_st1501_terraform_foundation",),
    "build_st1504_github_oidc": (
        "build_st0107_pr_governance",
        "build_st1501_terraform_foundation",
    ),
    "build_st1505_staging_deployment": (
        "build_st1501_terraform_foundation",
        "build_st1502_data_services",
        "build_st1503_compute_edge",
        "build_st1504_github_oidc",
    ),
    "build_st1506_production_deployment": (
        "build_st1501_terraform_foundation",
        "build_st1502_data_services",
        "build_st1503_compute_edge",
        "build_st1504_github_oidc",
        "build_st1505_staging_deployment",
    ),
    "build_st1506_production_canary_runtime": (
        "build_st1505_staging_deployment",
        "build_st1506_production_deployment",
    ),
    "build_st1805_portfolio_decision": ("build_st1804_gate3_economics",),
    "build_st1901_model_judge_calibration": (
        "build_st0707_evaluation_harness_runtime",
    ),
    "build_st1902_champion_challenger": (
        "build_st0708_openai_live_bounded_evaluation_reference_plan",
    ),
    "build_st1903_partial_auto_publication": (
        "build_st1805_portfolio_decision",
    ),
    "build_st1904_multi_category": ("build_st1805_portfolio_decision",),
    "build_st1905_advanced_rank_provider": ("build_st1206_keyword_rank_import",),
    "build_st1906_advanced_causal_attribution": (
        "build_st1303_attribution_engine",
    ),
    "build_st1908_fine_tuning_evaluation": (
        "build_st0707_evaluation_harness_runtime",
    ),
}


class InputKind(StrEnum):
    IMMUTABLE = "immutable"
    TRACKED = "tracked"
    PREDECESSOR = "predecessor"
    DEPENDENCY = "dependency"


@dataclass(frozen=True, slots=True)
class BuildInput:
    uri: str
    kind: InputKind
    owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class BuildSpec:
    owner_id: str
    story_ids: tuple[str, ...]
    generator: Path
    inputs: tuple[BuildInput, ...]
    outputs: tuple[Path, ...]
    owner_dependencies: tuple[str, ...]
    test_paths: tuple[Path, ...]
    supports_check: bool
    isolated_python: bool
    owner_version: int = 2

    def command(self, *, check: bool = False) -> tuple[str, ...]:
        command = [sys.executable]
        if self.isolated_python:
            command.extend(("-I", "-B"))
        command.append(self.generator.as_posix())
        if check:
            if not self.supports_check:
                raise ValueError(f"{self.owner_id} has no check mode")
            command.append("--check")
        return tuple(command)

    def as_json(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "story_ids": list(self.story_ids),
            "generator": self.generator.as_posix(),
            "inputs": [
                {
                    "uri": item.uri,
                    "kind": item.kind.value,
                    **({"owner_id": item.owner_id} if item.owner_id else {}),
                }
                for item in self.inputs
            ],
            "outputs": [path.as_posix() for path in self.outputs],
            "owner_dependencies": list(self.owner_dependencies),
            "test_paths": [path.as_posix() for path in self.test_paths],
            "supports_check": self.supports_check,
            "isolated_python": self.isolated_python,
            "owner_version": self.owner_version,
            "output_scope": (
                "owner_private"
                if self.owner_id in OWNER_PRIVATE_OWNER_IDS
                else "tracked"
            ),
        }


class _ProvisionalBuild(TypedDict):
    generator: Path
    source: str
    paths: set[Path]
    outputs: set[Path]
    story_ids: tuple[str, ...]
    dependencies: set[str]


class BuildRegistryError(RuntimeError):
    pass


class StagingDeploymentContractError(BuildRegistryError):
    """Compatibility-safe sanitized error for shared generator I/O."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class NoAliasDumper(yaml.SafeDumper):
    """Deterministic YAML dumper without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    construct = cast(
        Callable[[object, bool], object], getattr(loader, "construct_object")
    )
    for key_node, value_node in node.value:
        key = construct(cast(object, key_node), deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found duplicate key",
                key_node.start_mark,
            )
        result[key] = construct(cast(object, value_node), deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _fail(code: str, field: str) -> NoReturn:
    raise StagingDeploymentContractError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _is_any_list(value: object) -> TypeGuard[list[Any]]:
    return type(value) is list


def _list(value: object, field: str) -> list[Any]:
    if not _is_any_list(value):
        _fail("TYPE_MISMATCH", field)
    return value


def _strict_match(actual: object, expected: object, field: str) -> None:
    if type(expected) is dict:
        value = _mapping(actual, field)
        expected_mapping = _mapping(cast(object, expected), field)
        if set(value) != set(expected_mapping):
            _fail("CLOSED_SCHEMA_VIOLATION", field)
        for key, expected_value in expected_mapping.items():
            _strict_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(cast(object, expected), field)
        if not expected_list and value_list:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        if len(value_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_match(value_list[index], expected_value, f"{field}.item")
        return
    if expected is None:
        if actual is not None:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        return
    if type(actual) is not type(expected):
        _fail("TYPE_MISMATCH", field)
    if actual != expected:
        if type(expected) is bool or (type(expected) is int and expected == 0):
            _fail("SAFE_BOUNDARY_VIOLATION", field)
        _fail("FIXED_VALUE_VIOLATION", field)


def _regular_file(path: Path, field: str) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_FILE_TYPE", field)


def _real_repository_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    try:
        return root.resolve(strict=True)
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")


def _repository_regular_file(root: Path, relative: Path, field: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _fail("FILE_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_ANCESTOR", field)
    target = current / relative.name
    _regular_file(target, field)
    return target


def load_yaml(path: Path) -> object:
    _regular_file(path, "yaml")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "yaml")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("YAML_SIZE_LIMIT", "yaml")
    try:
        text = content.decode("utf-8")
        scan = cast(Callable[[str], Sequence[object]], getattr(yaml, "scan"))
        for token in scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", "yaml")
        return cast(object, yaml.load(text, Loader=UniqueKeyLoader))
    except StagingDeploymentContractError:
        raise
    except (UnicodeError, yaml.YAMLError):
        _fail("YAML_INVALID", "yaml")


def load_json(path: Path) -> object:
    _regular_file(path, "json")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "json")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("JSON_SIZE_LIMIT", "json")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("JSON_DUPLICATE_KEY", "json")
            result[key] = value
        return result

    try:
        return cast(
            object,
            json.loads(
                content.decode("utf-8"),
                object_pairs_hook=unique_pairs,
                parse_constant=lambda _value: _fail("JSON_INVALID", "json"),
            ),
        )
    except StagingDeploymentContractError:
        raise
    except (UnicodeError, json.JSONDecodeError):
        _fail("JSON_INVALID", "json")


def _repo_relative_uri(value: object) -> Path:
    if type(value) is not str or not value.startswith("repo://"):
        _fail("SOURCE_URI_INVALID", "sources")
    raw = value.removeprefix("repo://")
    if not raw or "\\" in raw:
        _fail("SOURCE_URI_INVALID", "sources")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("SOURCE_URI_INVALID", "sources")
    return Path(*pure.parts)


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_OUTPUT_PATH", "output")
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            try:
                current.mkdir(mode=0o755)
                metadata = current.lstat()
            except OSError:
                _fail("OUTPUT_DIRECTORY_FAILED", "output")
        except OSError:
            _fail("OUTPUT_DIRECTORY_FAILED", "output")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
    return current


def _output_file(root: Path, relative: Path) -> Path:
    parent = _safe_output_parent(root, relative, create=False)
    target = parent / relative.name
    _regular_file(target, "generated_output")
    return target


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    parent = _safe_output_parent(root, relative, create=True)
    target = parent / relative.name
    if target.exists() or target.is_symlink():
        _regular_file(target, "generated_output")
    try:
        atomic_write(relative, content, root=root)
    except (BuildRegistryError, OSError):
        _fail("OUTPUT_WRITE_FAILED", "output")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def input_hash_required(path: str | Path) -> bool:
    """Return whether an input belongs to an approved integrity category."""

    relative = Path(path)
    value = relative.as_posix()
    return value.startswith(("docs/canonical/", "docs/upstream/", "zip/")) or (
        relative.name in {"uv.lock", "package-lock.json"}
        or "toolchain.lock" in relative.name
        or "runtime-inventory" in relative.name
        or "image-digest" in relative.name
    )


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def atomic_write(path: Path, content: bytes, *, root: Path = REPOSITORY_ROOT) -> None:
    target = (root / path).resolve()
    repository = root.resolve()
    if target != repository and repository not in target.parents:
        raise BuildRegistryError(f"output escapes repository: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".next", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _path_value(
    node: ast.AST, known: Mapping[str, tuple[Path, ...]] | None = None
) -> tuple[Path, ...]:
    known = {} if known is None else known
    if isinstance(node, ast.Name):
        return known.get(node.id, ())
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "Path" and len(node.args) == 1:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                value = argument.value
                if value and not Path(value).is_absolute():
                    return (Path(value),)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _path_value(node.right, known)
        if not right and isinstance(node.right, ast.Constant):
            if isinstance(node.right.value, str) and node.right.value:
                right = (Path(node.right.value),)
        left = _path_value(node.left, known)
        if right and left:
            return tuple(base / suffix for base in left for suffix in right)
        if right and isinstance(node.left, ast.Name) and node.left.id.upper() in {
            "ROOT",
            "REPO_ROOT",
            "REPOSITORY_ROOT",
        }:
            return right
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        paths: list[Path] = []
        for item in node.elts:
            paths.extend(_path_value(item, known))
        return tuple(paths)
    if isinstance(node, ast.Dict):
        paths = []
        for key_or_value in (*node.keys, *node.values):
            if key_or_value is None:
                continue
            paths.extend(_path_value(key_or_value, known))
        return tuple(paths)
    return ()


def _top_level_paths(source: str) -> dict[str, tuple[Path, ...]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise BuildRegistryError(f"generator syntax invalid: {exc}") from exc
    values: dict[str, tuple[Path, ...]] = {}
    for statement in tree.body:
        name: str | None = None
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name = statement.target.id
            value = statement.value
        if name is not None and value is not None:
            paths = _path_value(value, values)
            if paths:
                values[name] = paths
    return values


def _looks_like_output(name: str) -> bool:
    upper = name.upper()
    if re.match(r"^ST[0-9]{4}_", upper):
        return False
    if upper.startswith(("EXPECTED_", "HISTORICAL_", "SOURCE_", "INPUT_")) or any(
        token in upper
        for token in (
            "PREDECESSOR",
            "SUPERSEDED",
            "CANONICAL",
            "AUTHORITY",
            "HANDOFF",
            "APPROVAL",
        )
    ):
        return False
    if upper in {"GENERATOR_PATH", "README_PATH", "CONTRACT_PATH", "FIXTURE_PATH"}:
        return False
    if upper in {"GENERATED_PATH", "GENERATED_PATHS", "OUTPUT_PATH", "OUTPUT_PATHS"}:
        return True
    if upper in {"OUTPUT", "MANIFEST", "GENERATED", "EVIDENCE"}:
        return True
    if upper.startswith("OUTPUT_") and upper.endswith("_PATH"):
        return True
    return upper in {
        "MANIFEST_PATH",
        "REPORT_PATH",
        "REFERENCE_PLAN_PATH",
        "PROJECTION_PATH",
        "RULESET_PATH",
        "COMPOSE_PATH",
        "RUNTIME_MANIFEST_PATH",
    }


def _story_ids(generator: Path, source: str) -> tuple[str, ...]:
    identifiers = {
        f"ST-{match.group(1)}" for match in STORY_PATTERN.finditer(generator.stem)
    }
    for match in re.finditer(r"[\"']ST-([0-9]{4})[\"']", source):
        identifiers.add(f"ST-{match.group(1)}")
    primary = STORY_PATTERN.search(generator.stem)
    if primary:
        preferred = f"ST-{primary.group(1)}"
        return (preferred, *sorted(identifiers - {preferred}))
    return tuple(sorted(identifiers))


def _test_paths(story_ids: Sequence[str], *, root: Path) -> tuple[Path, ...]:
    found: set[Path] = set()
    tests_root = root / "tests"
    if not tests_root.is_dir():
        return ()
    for story_id in story_ids:
        prefix = story_id.lower().replace("-", "")
        for candidate in tests_root.glob(f"{prefix}*"):
            if candidate.is_dir():
                found.add(candidate.relative_to(root))
    return tuple(sorted(found))


def _input_kind(path: Path) -> InputKind:
    value = path.as_posix()
    if value.startswith(("docs/canonical/", "docs/upstream/", "zip/")):
        return InputKind.IMMUTABLE
    if path.name in {"uv.lock", "package-lock.json"} or "runtime-inventory" in path.name:
        return InputKind.DEPENDENCY
    return InputKind.TRACKED


def _is_workflow_governance_path(path: Path) -> bool:
    value = path.as_posix()
    upper = value.upper()
    return (
        path.name == "AGENTS.md"
        or value.startswith((".codex/", "docs/execplans/", "docs/worklogs/"))
        or any(
            marker in upper
            for marker in (
                "EXECPLAN",
                "DESIGN_HANDOFF",
                "DESIGN-HANDOFF-APPROVAL",
                "CANONICAL-RECONCILIATION",
                "DESIGN-DECISION-REQUEST",
                "PREFLIGHT",
                "LOCAL-IMPLEMENTATION-COMPLETION",
                "GOAL-PROMPT",
                "GOAL_PROMPT",
            )
        )
    )


def _cross_builder_dependencies(source: str) -> set[str]:
    dependencies: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return dependencies
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        module: str | None = None
        if isinstance(node, ast.ImportFrom):
            module = node.module
            for alias in node.names:
                if module == "scripts" and alias.name.startswith("build_"):
                    dependencies.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts.build_"):
                    dependencies.add(alias.name.rsplit(".", 1)[-1])
        else:
            pending.extend(ast.iter_child_nodes(node))
    return dependencies


def _declared_outputs(owner_id: str, *, root: Path) -> set[Path]:
    manifest_path = DECLARED_OUTPUT_MANIFESTS.get(owner_id)
    outputs = set(EXPLICIT_OWNER_OUTPUTS.get(owner_id, ()))
    if manifest_path is None:
        return outputs
    manifest = yaml.safe_load((root / manifest_path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise BuildRegistryError(f"output manifest is not a mapping: {manifest_path}")
    entries: object
    if owner_id == "build_st0104_contract_repository":
        entries = manifest.get("artifacts")
    elif owner_id == "build_st0105_generated_contracts":
        output_section = manifest.get("outputs")
        entries = output_section.get("artifacts") if isinstance(output_section, dict) else None
    else:
        entries = manifest.get("generated_artifacts")
    if not isinstance(entries, list):
        raise BuildRegistryError(f"output inventory is absent: {manifest_path}")
    outputs.add(manifest_path)
    for entry in entries:
        if not isinstance(entry, dict):
            raise BuildRegistryError(f"output inventory row is invalid: {manifest_path}")
        value = entry.get("path") or entry.get("uri")
        if not isinstance(value, str):
            raise BuildRegistryError(f"output inventory path is invalid: {manifest_path}")
        relative = Path(value.removeprefix("repo://"))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise BuildRegistryError(f"output inventory path is unsafe: {relative}")
        if owner_id == "build_st0104_contract_repository":
            # The repository index stores paths relative to the versioned
            # contract package, not relative to the Git worktree.
            relative = Path("contracts/raos-v0.4") / relative
        outputs.add(relative)
    return outputs


def discover_registry(*, root: Path = REPOSITORY_ROOT) -> dict[str, BuildSpec]:
    provisional: dict[str, _ProvisionalBuild] = {}
    for absolute_generator in sorted((root / "scripts").glob(BUILD_SCRIPT_GLOB)):
        if not absolute_generator.is_file():
            continue
        generator = absolute_generator.relative_to(root)
        source = absolute_generator.read_text(encoding="utf-8")
        owner_id = generator.stem
        paths_by_name = _top_level_paths(source)
        outputs = {
            path
            for name, paths in paths_by_name.items()
            if _looks_like_output(name)
            for path in paths
        }
        outputs.update(_declared_outputs(owner_id, root=root))
        paths = {
            path
            for values in paths_by_name.values()
            for path in values
            if not _is_workflow_governance_path(path)
        }
        story_ids = _story_ids(generator, source)
        provisional[owner_id] = {
            "generator": generator,
            "source": source,
            "paths": paths,
            "outputs": outputs,
            "story_ids": story_ids,
            "dependencies": _cross_builder_dependencies(source),
        }

    output_owner: dict[Path, str] = {}
    for owner_id, item in provisional.items():
        for output in item["outputs"]:
            override = OUTPUT_OWNER_OVERRIDES.get(output)
            if override is not None and owner_id != override:
                continue
            previous = output_owner.get(output)
            if previous is not None and previous != owner_id:
                previous_story = STORY_PATTERN.search(previous)
                current_story = STORY_PATTERN.search(owner_id)
                if (
                    previous_story is None
                    or current_story is None
                    or previous_story.group(1) == current_story.group(1)
                ):
                    raise BuildRegistryError(
                        "generated output has multiple owners: "
                        f"{output}: {previous}, {owner_id}"
                    )
                if int(previous_story.group(1)) > int(current_story.group(1)):
                    continue
            output_owner[output] = owner_id

    registry: dict[str, BuildSpec] = {}
    for owner_id, item in provisional.items():
        generator = item["generator"]
        source = item["source"]
        paths = item["paths"]
        outputs = {
            path
            for path in item["outputs"]
            if output_owner.get(path) == owner_id
        }
        dependencies = set(item["dependencies"])
        dependencies.update(EXPLICIT_OWNER_DEPENDENCIES.get(owner_id, ()))
        inputs: list[BuildInput] = []
        for path in sorted(paths - outputs):
            predecessor = output_owner.get(path)
            consumer_story = STORY_PATTERN.search(generator.stem)
            producer_generator = (
                provisional[predecessor]["generator"]
                if predecessor is not None
                else None
            )
            producer_story = (
                STORY_PATTERN.search(producer_generator.stem)
                if isinstance(producer_generator, Path)
                else None
            )
            ordered_predecessor = bool(
                predecessor is not None
                and predecessor != owner_id
                and consumer_story is not None
                and producer_story is not None
                and int(producer_story.group(1)) < int(consumer_story.group(1))
            )
            if ordered_predecessor and predecessor is not None:
                dependencies.add(predecessor)
            inputs.append(
                BuildInput(
                    uri=f"repo://{path.as_posix()}",
                    kind=(
                        InputKind.PREDECESSOR
                        if ordered_predecessor
                        else _input_kind(path)
                    ),
                    owner_id=predecessor if ordered_predecessor else None,
                )
            )
        inputs.append(
            BuildInput(uri=f"repo://{generator.as_posix()}", kind=InputKind.TRACKED)
        )
        dependencies.discard(owner_id)
        registry[owner_id] = BuildSpec(
            owner_id=owner_id,
            story_ids=item["story_ids"],
            generator=generator,
            inputs=tuple(sorted(set(inputs), key=lambda value: value.uri)),
            outputs=tuple(sorted(outputs)),
            owner_dependencies=tuple(sorted(dependencies)),
            test_paths=_test_paths(item["story_ids"], root=root),
            supports_check='"--check"' in source or "'--check'" in source,
            isolated_python="sys.flags.isolated" in source,
        )
    validate_registry(registry)
    return registry


def validate_registry(registry: Mapping[str, BuildSpec]) -> None:
    missing = {
        dependency
        for spec in registry.values()
        for dependency in spec.owner_dependencies
        if dependency not in registry
    }
    if missing:
        raise BuildRegistryError(f"unknown owner dependencies: {sorted(missing)}")
    topological_order(registry)


def topological_order(
    registry: Mapping[str, BuildSpec], owners: Iterable[str] | None = None
) -> tuple[str, ...]:
    selected = set(registry if owners is None else owners)
    expanded = set(selected)
    queue = deque(selected)
    while queue:
        owner = queue.popleft()
        if owner not in registry:
            raise BuildRegistryError(f"unknown owner: {owner}")
        for dependency in registry[owner].owner_dependencies:
            if dependency not in expanded:
                expanded.add(dependency)
                queue.append(dependency)
    incoming = {
        owner: set(registry[owner].owner_dependencies) & expanded for owner in expanded
    }
    followers: dict[str, set[str]] = defaultdict(set)
    for owner, dependencies in incoming.items():
        for dependency in dependencies:
            followers[dependency].add(owner)
    ready = deque(sorted(owner for owner, values in incoming.items() if not values))
    ordered: list[str] = []
    while ready:
        owner = ready.popleft()
        ordered.append(owner)
        for follower in sorted(followers[owner]):
            incoming[follower].discard(owner)
            if not incoming[follower]:
                ready.append(follower)
    if len(ordered) != len(expanded):
        cycle = sorted(owner for owner, values in incoming.items() if values)
        raise BuildRegistryError(f"owner dependency cycle: {cycle}")
    return tuple(ordered)


def changed_paths(*, root: Path = REPOSITORY_ROOT, base: str | None = None) -> tuple[Path, ...]:
    if base is None:
        branch = subprocess.run(
            ("git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        base = branch.stdout.strip().removeprefix("refs/remotes/") or "HEAD"
    merge_base = subprocess.run(
        ("git", "merge-base", base, "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    comparison = merge_base.stdout.strip() if merge_base.returncode == 0 else base
    result = subprocess.run(
        ("git", "diff", "--name-only", comparison, "--"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = {Path(line) for line in result.stdout.splitlines() if line}
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    for line in status.stdout.splitlines():
        if len(line) > 3:
            tracked.add(Path(line[3:]))
    return tuple(sorted(tracked))


def affected_owners(
    registry: Mapping[str, BuildSpec], paths: Iterable[Path]
) -> tuple[str, ...]:
    changed = set(paths)
    if changed & BUILD_INFRASTRUCTURE_PATHS:
        return topological_order(registry)
    direct: set[str] = set()
    for owner, spec in registry.items():
        owned = {spec.generator, *spec.outputs}
        owned.update(
            Path(item.uri.removeprefix("repo://"))
            for item in spec.inputs
            if item.uri.startswith("repo://")
        )
        if any(
            candidate in changed
            or any(candidate.is_relative_to(path) for path in changed if path.suffix == "")
            for candidate in owned
        ):
            direct.add(owner)
    reverse: dict[str, set[str]] = defaultdict(set)
    for owner, spec in registry.items():
        for dependency in spec.owner_dependencies:
            reverse[dependency].add(owner)
    queue = deque(direct)
    while queue:
        owner = queue.popleft()
        for follower in reverse[owner]:
            if follower not in direct:
                direct.add(follower)
                queue.append(follower)
    return tuple(owner for owner in topological_order(registry) if owner in direct)


def directly_changed_owners(
    registry: Mapping[str, BuildSpec], paths: Iterable[Path]
) -> tuple[str, ...]:
    """Select output owners without legacy metadata propagation."""

    changed = set(paths)
    output_owner = {
        output: owner for owner, spec in registry.items() for output in spec.outputs
    }
    selected: set[str] = {
        owner for path, owner in output_owner.items() if path in changed
    }
    for owner, spec in registry.items():
        if spec.generator in changed:
            selected.add(owner)
            continue
        tracked_inputs = {
            _repo_path(item.uri)
            for item in spec.inputs
            if item.uri.startswith("repo://")
            and _repo_path(item.uri) not in output_owner
            and not (
                _repo_path(item.uri).parent == Path("scripts")
                and _repo_path(item.uri).name.startswith("build_")
                and _repo_path(item.uri) != spec.generator
            )
        }
        if tracked_inputs & changed:
            selected.add(owner)
    return tuple(owner for owner in topological_order(registry) if owner in selected)


def registry_document(registry: Mapping[str, BuildSpec]) -> dict[str, object]:
    return {
        "document": {
            "id": "RAOS-BUILD-REGISTRY-002",
            "version": "2.0.0",
            "authority": "DISCOVERED_TRACKED_BUILD_GRAPH",
            "mutable_source_hash_authority": "FORBIDDEN",
        },
        "integrity_policy": {
            "allowed_input_hash_kinds": [
                "canonical_package",
                "dependency_lock",
                "container_image",
            ],
            "allowed_output_hash_kinds": [
                "generated_output",
                "runtime_data_integrity",
                "release_provenance",
            ],
        },
        "owners": [registry[owner].as_json() for owner in sorted(registry)],
    }


def _repo_path(uri: str) -> Path:
    if not uri.startswith("repo://"):
        raise BuildRegistryError(f"unsupported build input URI: {uri}")
    return Path(uri.removeprefix("repo://"))


def active_manifest_document(
    registry: Mapping[str, BuildSpec], *, root: Path = REPOSITORY_ROOT
) -> dict[str, object]:
    owners: list[dict[str, object]] = []
    for owner_id in sorted(registry):
        spec = registry[owner_id]
        semantic_inputs: list[dict[str, object]] = []
        for item in spec.inputs:
            row: dict[str, object] = {"uri": item.uri, "kind": item.kind.value}
            if item.kind in {InputKind.IMMUTABLE, InputKind.DEPENDENCY}:
                path = root / _repo_path(item.uri)
                if not path.is_file() or path.is_symlink():
                    raise BuildRegistryError(f"integrity input is not regular: {path}")
                row["sha256"] = sha256_bytes(path.read_bytes())
            else:
                row["semantic_id"] = _repo_path(item.uri).as_posix()
                row["version"] = spec.owner_version
            if item.owner_id:
                row["owner_id"] = item.owner_id
                row["owner_version"] = registry[item.owner_id].owner_version
            semantic_inputs.append(row)

        outputs: list[dict[str, object]] = []
        for relative in spec.outputs:
            path = root / relative
            if not path.is_file() or path.is_symlink():
                raise BuildRegistryError(f"generated output is not regular: {relative}")
            content = path.read_bytes()
            outputs.append(
                {
                    "uri": f"repo://{relative.as_posix()}",
                    "bytes": len(content),
                    "sha256": sha256_bytes(content),
                }
            )
        owners.append(
            {
                "owner_id": spec.owner_id,
                "owner_version": spec.owner_version,
                "story_ids": list(spec.story_ids),
                "owner_dependencies": list(spec.owner_dependencies),
                "output_scope": (
                    "owner_private"
                    if spec.owner_id in OWNER_PRIVATE_OWNER_IDS
                    else "tracked"
                ),
                "semantic_inputs": semantic_inputs,
                "outputs": outputs,
            }
        )
    return {
        "document": {
            "id": "RAOS-BUILD-MANIFEST-002",
            "version": "2.0.0",
            "owner_count": len(owners),
            "mutable_source_hash_authority": False,
        },
        "owners": owners,
    }


def write_active_manifest(
    registry: Mapping[str, BuildSpec], *, root: Path = REPOSITORY_ROOT
) -> None:
    atomic_write(
        ACTIVE_MANIFEST_PATH,
        canonical_json_bytes(active_manifest_document(registry, root=root)),
        root=root,
    )


def check_active_manifest(
    registry: Mapping[str, BuildSpec], *, root: Path = REPOSITORY_ROOT
) -> None:
    path = root / ACTIVE_MANIFEST_PATH
    expected = canonical_json_bytes(active_manifest_document(registry, root=root))
    if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
        raise BuildRegistryError(f"active manifest drift: {ACTIVE_MANIFEST_PATH}")


def generation_relevant_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    ignored_prefixes = (
        ".codex/",
        ".github/",
        "docs/execplans/",
        "docs/worklogs/",
        "tests/",
    )
    ignored_files = {
        Path(".playwright-cli"),
        Path("AGENTS.md"),
        Path("Makefile"),
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("uv.toml"),
    }
    return tuple(
        path
        for path in paths
        if path not in ignored_files
        and not path.as_posix().startswith(ignored_prefixes)
        and path != ACTIVE_MANIFEST_PATH
        and path.name not in {"manifest.yaml", "manifest.json"}
        and path
        != Path("changes/st-0107/contracts/pr-governance.v1.yaml")
        and not path.as_posix().startswith("changes/status/")
    )


def run_commands(
    commands: Iterable[Sequence[str]], *, root: Path = REPOSITORY_ROOT
) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (
            str(root),
            str(root / "python"),
            environment.get("PYTHONPATH", ""),
        )
        if value
    )
    for command in commands:
        process = subprocess.run(
            tuple(command), cwd=root, check=False, env=environment
        )
        if process.returncode != 0:
            raise BuildRegistryError(
                f"command failed ({process.returncode}): {' '.join(command)}"
            )
