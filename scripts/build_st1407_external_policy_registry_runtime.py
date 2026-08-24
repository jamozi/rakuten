#!/usr/bin/env python3
"""Build the recorded/synthetic ST-1407 registry runtime fixture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import stat
import sys
from collections.abc import Callable
from typing import Final, NoReturn, cast
from uuid import UUID

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from scripts import secure_generated_publication as secure_generated_publication  # noqa: E402

from raos.adapters.recorded_external_policy_registry import (  # noqa: E402
    RECORDED_FIXTURE_REQUEST_SHA256S,
)
from raos.domain.editorial.policy_engine import (  # noqa: E402
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
)
from raos.domain.ops.external_policy_registry import (  # noqa: E402
    CONTRACT_ID,
    CONTRACT_VERSION,
    EXTERNAL_RULE_POLICY_LINKS,
    LOCAL_STATUS,
    ArticlePolicyBinding,
    ExternalPolicyRegistryRequest,
    ExternalPolicySnapshot,
    PolicyVersionLink,
    RegistryContractBinding,
    article_binding_set_fingerprint,
    evaluate_external_policy_registry,
    registry_report_payload,
    registry_request_payload,
)
from raos.domain.shared.persistence import Sha256Digest  # noqa: E402


EXPECTED_PYTHON_IMPLEMENTATION: Final = "cpython"
EXPECTED_PYTHON_VERSION: Final = (3, 14, 6)
EXPECTED_PYYAML_VERSION: Final = "6.0.3"
CONTRACT_PATH: Final = Path(
    "changes/st-1407/contracts/external-policy-registry-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1407/generated/external-policy-registry-recorded.v2.json"
)
MANIFEST_PATH: Final = Path("changes/st-1407/runtime-manifest.v2.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1407_external_policy_registry_runtime.py")
SECURE_HELPER_PATH: Final = Path("scripts/secure_generated_publication.py")
SECURE_HELPER_SHA256: Final = (
    "38412b6223f305b2fb7cd947f9eb2c2ce2e4e0b48773099c71c92a8c5e5cf56e"
)
OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    GENERATOR_PATH,
    Path("python/raos/domain/ops/external_policy_registry.py"),
    Path("python/raos/ports/external_policy_registry.py"),
    Path("python/raos/adapters/recorded_external_policy_registry.py"),
    Path("python/raos/application/ops/external_policy_registry.py"),
    Path("changes/st-1407/EXECPLAN.md"),
    Path("changes/st-1407/README-v2.md"),
    Path("changes/st-1407/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("tests/st1407_v2/conftest.py"),
    Path("tests/st1407_v2/test_domain.py"),
    Path("tests/st1407_v2/test_boundaries.py"),
    Path("tests/st1407_v2/test_generation.py"),
)
EXPECTED_AUTHORITY_INPUTS: Final = (
    (
        "integration",
        Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "open_decisions",
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "story",
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "security_controls",
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "threat_register",
        Path("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    ),
    (
        "alert_catalog",
        Path("docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml"),
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0",
    ),
    (
        "runbook_catalog",
        Path("docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml"),
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100",
    ),
)
EXPECTED_CONTRACT_INPUTS: Final = (
    (
        "external_rule_catalog",
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_external_rule_snapshot_v0.1.yaml"
        ),
        "14a4131215f8c2f70a2f5b73aef0ccb1162f1a8ac6d410079c6a3b6b68955042",
    ),
    (
        "official_reference_catalog",
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_official_references_v0.1.yaml"
        ),
        "d7a3986affce9d2fc1110d6b3fffb196c668dae7db00288d466b9e62ba57e030",
    ),
    (
        "editorial_policy_catalog",
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml"
        ),
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
)
EXPECTED_DEPENDENCY_INPUTS: Final = (
    (
        "ST-0405",
        "audit_port",
        Path("python/raos/ports/audit.py"),
        "d358f8349ebeb70c3b8f046b82c109a80f162fe88432d1e0d4e11e4ff21592ec",
        "NOT_CALLED_NO_AUTHORIZED_BUSINESS_MUTATION",
    ),
    (
        "ST-0805",
        "policy_engine_v1",
        Path("python/raos/domain/editorial/policy_engine.py"),
        "d858a9b010253cf411083bd5eb9da995ff3f9a172c7626ca9e499a6256559e51",
        "EXACT_POLICY_ID_VERSION_AND_CATALOG_BINDING",
    ),
    (
        "ST-0805",
        "policy_engine_v2",
        Path("python/raos/domain/editorial/policy_engine_v2.py"),
        "86e0af8ff6b651b50a7959a0a8c0f85864c230a57144b51e190041d658ee7d93",
        "ADDITIVE_RUNTIME_PROVENANCE_ONLY",
    ),
    (
        "ST-0805",
        "runtime_manifest_v2",
        Path("changes/st-0805/runtime-manifest.v2.yaml"),
        "19dd52b254b648f88c6cda0ea3d9d5b6167b184a0a4ce735431ebb09056d6367",
        "ADDITIVE_RUNTIME_PROVENANCE_ONLY",
    ),
)
MATERIAL_RUNTIME_DEPENDENCIES: Final = (
    (
        Path("python/raos/domain/shared/persistence.py"),
        "2a3d5cdc7d2e93ecd6883c3cdd37a0f27eb36638bd569399fcd95be7a06dfc20",
    ),
    (
        Path("python/raos/domain/shared/identity.py"),
        "d650f46f95fd116ed13f630b9ff84b254c0a8aa6659ef8d52907733a6a49a8e2",
    ),
    (
        Path("python/raos/domain/shared/json_values.py"),
        "c995c2ba5f3dcd9f4302328d423192ae9f8c3b1415f294bf791c92baf07d4644",
    ),
    (
        Path("python/raos/config/runtime.py"),
        "2a1b7b550bcf5365df610c8ebffe1994d12ab888a5be4042dde032ed7c5a0ac3",
    ),
)
LOCKED_TOOLCHAIN_PATHS: Final = (Path("pyproject.toml"), Path("uv.lock"))
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 4 * 1024 * 1024

_ROOT_KEYS: Final = (
    "document",
    "authority_inputs",
    "contract_inputs",
    "dependency_inputs",
    "safe_defaults",
    "fixtures",
)
_DOCUMENT_KEYS: Final = (
    "id",
    "version",
    "story_id",
    "classification",
    "status",
    "authority",
    "official_source_attested",
    "production_eligible",
)
_SOURCE_KEYS: Final = ("role", "uri", "sha256")
_DEPENDENCY_KEYS: Final = ("story_id", "role", "uri", "sha256", "use")
_SAFE_DEFAULT_KEYS: Final = (
    "source_acquisition",
    "legal_review",
    "notification",
    "audit",
    "activation",
    "article_mutation",
    "recommendation_mutation",
    "publication",
    "live",
)
_FIXTURE_KEYS: Final = (
    "fixture_id",
    "snapshot_id",
    "external_rule_id",
    "source_content_sha256",
    "acquired_at",
    "review_due_at",
    "evaluated_at",
    "article_bindings",
)
_ARTICLE_KEYS: Final = (
    "article_id",
    "article_version_id",
    "publication_snapshot_sha256",
    "policy_ids",
)
_RULE_MAP: Final = dict(EXTERNAL_RULE_POLICY_LINKS)


class ExternalPolicyRegistryGenerationError(ValueError):
    __slots__ = ()


def _fail(code: str) -> NoReturn:
    raise ExternalPolicyRegistryGenerationError(code) from None


def _validate_toolchain() -> None:
    if (
        sys.implementation.name != EXPECTED_PYTHON_IMPLEMENTATION
        or sys.version_info[:3] != EXPECTED_PYTHON_VERSION
        or getattr(yaml, "__version__", None) != EXPECTED_PYYAML_VERSION
    ):
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    try:
        observed = distribution_version("PyYAML")
    except PackageNotFoundError:
        _fail("GENERATION_TOOLCHAIN_DRIFT")
    if observed != EXPECTED_PYYAML_VERSION:
        _fail("GENERATION_TOOLCHAIN_DRIFT")


def _validate_relative(relative: Path) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_PATH")


def _lexical_root(root: Path) -> Path:
    absolute = root if root.is_absolute() else Path.cwd() / root
    normalized = Path(os.path.abspath(os.fspath(absolute)))
    if not normalized.is_absolute() or any(
        part in {"", ".", ".."} for part in normalized.parts[1:]
    ):
        _fail("UNSAFE_ROOT")
    return normalized


def _open_root(root: Path) -> int:
    absolute = _lexical_root(root)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, flags))
        for component in absolute.parts[1:]:
            descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
        return descriptors.pop()
    except OSError:
        _fail("UNSAFE_ROOT")
    finally:
        while descriptors:
            os.close(descriptors.pop())


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _validate_directory(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("SOURCE_ANCESTOR_INVALID")


def _validate_regular(metadata: os.stat_result, *, maximum: int) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode)
        & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | 0o022)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= maximum
    ):
        _fail("SOURCE_IDENTITY_INVALID")


def _read_regular(
    root: Path,
    relative: Path,
    *,
    maximum: int = MAX_SOURCE_BYTES,
) -> bytes:
    _validate_relative(relative)
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor = _open_root(root)
        _validate_directory(os.fstat(parent_descriptor))
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        for component in relative.parts[:-1]:
            before = os.stat(component, dir_fd=parent_descriptor, follow_symlinks=False)
            _validate_directory(before)
            child = os.open(component, directory_flags, dir_fd=parent_descriptor)
            opened = os.fstat(child)
            _validate_directory(opened)
            if _identity(opened) != _identity(before):
                os.close(child)
                _fail("SOURCE_CHANGED_DURING_READ")
            os.close(parent_descriptor)
            parent_descriptor = child
        name = relative.parts[-1]
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        _validate_regular(before, maximum=maximum)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        _validate_regular(opened, maximum=maximum)
        if _identity(opened) != _identity(before):
            _fail("SOURCE_CHANGED_DURING_READ")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _fail("SOURCE_SIZE_INVALID")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        _validate_regular(named_after, maximum=maximum)
        if (
            _identity(after) != _identity(opened)
            or _identity(named_after) != _identity(opened)
            or total != opened.st_size
        ):
            _fail("SOURCE_CHANGED_DURING_READ")
        return b"".join(chunks)
    except ExternalPolicyRegistryGenerationError:
        raise
    except OSError:
        _fail("SOURCE_OPEN_FAILED")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {}
    constructor_member: object = getattr(loader, "construct_object")
    constructor = cast(Callable[[yaml.Node, bool], object], constructor_member)
    entries = cast(
        list[tuple[yaml.Node, yaml.Node]],
        cast(object, node.value),
    )
    for key_node, value_node in entries:
        key = constructor(key_node, deep)
        if type(key) is not str or key in result:
            _fail("CONTRACT_PARSE_FAILED")
        result[key] = constructor(value_node, deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _parse_yaml(payload: bytes) -> object:
    if not 2 <= len(payload) <= 256 * 1024:
        _fail("CONTRACT_SHAPE_INVALID")
    try:
        text = payload.decode("utf-8", errors="strict")
        load_yaml = cast(Callable[..., object], cast(object, yaml.load))
        return load_yaml(text, Loader=_UniqueSafeLoader)
    except ExternalPolicyRegistryGenerationError:
        raise
    except Exception:
        _fail("CONTRACT_PARSE_FAILED")


def _mapping(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(dict[str, object], cast(object, value))
    if tuple(result) != keys:
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _list(value: object, *, minimum: int, maximum: int) -> list[object]:
    if type(value) is not list:
        _fail("CONTRACT_SHAPE_INVALID")
    result = cast(list[object], cast(object, value))
    if not minimum <= len(result) <= maximum:
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _string(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail("CONTRACT_SHAPE_INVALID")
    return value


def _sha256(value: object) -> str:
    text = _string(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail("CONTRACT_SHAPE_INVALID")
    return text


def _uuid(value: object) -> UUID:
    text = _string(value, maximum=36)
    try:
        result = UUID(text)
    except Exception:
        _fail("CONTRACT_SHAPE_INVALID")
    if result.int == 0 or str(result) != text:
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _instant(value: object) -> datetime:
    text = _string(value, maximum=27)
    try:
        result = datetime.fromisoformat(text[:-1] + "+00:00")
    except Exception:
        _fail("CONTRACT_SHAPE_INVALID")
    if (
        not text.endswith("Z")
        or len(text) != 27
        or result.tzinfo is not timezone.utc
        or result.fold != 0
        or result.isoformat(timespec="microseconds").replace("+00:00", "Z") != text
    ):
        _fail("CONTRACT_SHAPE_INVALID")
    return result


def _repo_path(value: object) -> Path:
    uri = _string(value, maximum=512)
    if not uri.startswith("repo://"):
        _fail("CONTRACT_SHAPE_INVALID")
    result = Path(uri.removeprefix("repo://"))
    _validate_relative(result)
    return result


def _parse_contract(payload: bytes) -> dict[str, object]:
    root = _mapping(_parse_yaml(payload), _ROOT_KEYS)
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    if document != {
        "id": CONTRACT_ID,
        "version": CONTRACT_VERSION,
        "story_id": "ST-1407",
        "classification": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
        "status": LOCAL_STATUS,
        "authority": "NONE",
        "official_source_attested": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_BINDING_MISMATCH")
    safe_defaults = _mapping(root["safe_defaults"], _SAFE_DEFAULT_KEYS)
    if safe_defaults != {
        "source_acquisition": "NOT_IMPLEMENTED_OPEN_018",
        "legal_review": "NOT_COMPLETED_OD_008",
        "notification": "LOCAL_LOG_ONLY_NOT_DELIVERED_OD_011",
        "audit": "NOT_EXECUTED",
        "activation": "NOT_AUTHORIZED",
        "article_mutation": "NOT_AUTHORIZED",
        "recommendation_mutation": "NOT_AUTHORIZED",
        "publication": "NOT_AUTHORIZED",
        "live": "NOT_EXECUTED",
    }:
        _fail("CONTRACT_BINDING_MISMATCH")
    authority_inputs = tuple(
        (
            _string(row["role"]),
            _repo_path(row["uri"]),
            _sha256(row["sha256"]),
        )
        for row in (
            _mapping(raw, _SOURCE_KEYS)
            for raw in _list(root["authority_inputs"], minimum=7, maximum=7)
        )
    )
    contract_inputs = tuple(
        (
            _string(row["role"]),
            _repo_path(row["uri"]),
            _sha256(row["sha256"]),
        )
        for row in (
            _mapping(raw, _SOURCE_KEYS)
            for raw in _list(root["contract_inputs"], minimum=3, maximum=3)
        )
    )
    dependency_inputs = tuple(
        (
            _string(row["story_id"]),
            _string(row["role"]),
            _repo_path(row["uri"]),
            _sha256(row["sha256"]),
            _string(row["use"], maximum=128),
        )
        for row in (
            _mapping(raw, _DEPENDENCY_KEYS)
            for raw in _list(root["dependency_inputs"], minimum=4, maximum=4)
        )
    )
    if (
        authority_inputs != EXPECTED_AUTHORITY_INPUTS
        or contract_inputs != EXPECTED_CONTRACT_INPUTS
        or dependency_inputs != EXPECTED_DEPENDENCY_INPUTS
    ):
        _fail("SOURCE_INVENTORY_INVALID")
    _list(root["fixtures"], minimum=2, maximum=32)
    return root


def _source_inventory(contract: dict[str, object]) -> tuple[tuple[str, Path, str], ...]:
    del contract
    rows = [*EXPECTED_AUTHORITY_INPUTS, *EXPECTED_CONTRACT_INPUTS]
    rows.extend(
        (f"{story_id}:{role}", path, digest)
        for story_id, role, path, digest, _use in EXPECTED_DEPENDENCY_INPUTS
    )
    if len({path for _role, path, _sha in rows}) != len(rows):
        _fail("SOURCE_INVENTORY_INVALID")
    return tuple(rows)


def _capture_sources(
    root: Path,
    contract_bytes: bytes,
    external_inputs: tuple[tuple[str, Path, str], ...],
) -> dict[Path, bytes]:
    paths = (
        *OWNED_SOURCE_PATHS,
        *(path for _role, path, _sha in external_inputs),
        *(path for path, _sha in MATERIAL_RUNTIME_DEPENDENCIES),
        SECURE_HELPER_PATH,
        *LOCKED_TOOLCHAIN_PATHS,
    )
    if len(set(paths)) != len(paths):
        _fail("SOURCE_INVENTORY_INVALID")
    captured: dict[Path, bytes] = {CONTRACT_PATH: contract_bytes}
    for path in paths:
        if path != CONTRACT_PATH:
            captured[path] = _read_regular(root, path)
    if tuple(captured) != paths:
        _fail("SOURCE_INVENTORY_INVALID")
    for _role, path, expected in external_inputs:
        if hashlib.sha256(captured[path]).hexdigest() != expected:
            _fail("SOURCE_HASH_DRIFT")
    for path, _expected in MATERIAL_RUNTIME_DEPENDENCIES:
        validate_material_runtime_dependency_bytes(path, captured[path])
    if hashlib.sha256(captured[SECURE_HELPER_PATH]).hexdigest() != SECURE_HELPER_SHA256:
        _fail("SOURCE_HASH_DRIFT")
    return captured


def _validate_installed_catalogs(
    captured: dict[Path, bytes],
    external_inputs: tuple[tuple[str, Path, str], ...],
) -> None:
    by_role = {role: path for role, path, _sha in external_inputs}
    external = cast(
        dict[str, object],
        _parse_yaml(captured[by_role["external_rule_catalog"]]),
    )
    rules = _list(external.get("rules"), minimum=13, maximum=13)
    observed: list[tuple[str, tuple[str, ...]]] = []
    for raw in rules:
        if type(raw) is not dict:
            _fail("CATALOG_BINDING_MISMATCH")
        rule = cast(dict[str, object], raw)
        policy_ids = tuple(
            _string(item)
            for item in _list(rule.get("content_policy_ids"), minimum=1, maximum=8)
        )
        observed.append((_string(rule.get("id")), policy_ids))
    if tuple(observed) != EXTERNAL_RULE_POLICY_LINKS:
        _fail("CATALOG_BINDING_MISMATCH")
    official = cast(
        dict[str, object],
        _parse_yaml(captured[by_role["official_reference_catalog"]]),
    )
    if len(_list(official.get("sources"), minimum=12, maximum=12)) != 12:
        _fail("CATALOG_BINDING_MISMATCH")
    policy = cast(
        dict[str, object],
        _parse_yaml(captured[by_role["editorial_policy_catalog"]]),
    )
    policy_rows = _list(policy.get("policies"), minimum=40, maximum=40)
    observed_policy_ids = tuple(
        _string(cast(dict[str, object], row).get("id")) for row in policy_rows
    )
    expected_policy_ids = tuple(
        definition.policy_id for definition in POLICY_DEFINITIONS
    )
    if observed_policy_ids != expected_policy_ids:
        _fail("CATALOG_BINDING_MISMATCH")


def _build_request(raw: object) -> tuple[str, ExternalPolicyRegistryRequest]:
    row = _mapping(raw, _FIXTURE_KEYS)
    fixture_id = _string(row["fixture_id"], maximum=80)
    binding = RegistryContractBinding.current()
    snapshot_id = _uuid(row["snapshot_id"])
    external_rule_id = _string(row["external_rule_id"])
    if external_rule_id not in _RULE_MAP:
        _fail("CONTRACT_BINDING_MISMATCH")
    snapshot = ExternalPolicySnapshot(
        snapshot_id=snapshot_id,
        external_rule_id=external_rule_id,
        source_content_sha256=Sha256Digest(_sha256(row["source_content_sha256"])),
        acquired_at=_instant(row["acquired_at"]),
        review_due_at=_instant(row["review_due_at"]),
        contract_binding_sha256=Sha256Digest(binding.fingerprint),
    )
    links = tuple(
        PolicyVersionLink(
            snapshot_id=snapshot_id,
            external_rule_id=external_rule_id,
            policy_id=policy_id,
            policy_version=POLICY_CATALOG_VERSION,
            policy_catalog_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
        )
        for policy_id in sorted(_RULE_MAP[external_rule_id])
    )
    articles: list[ArticlePolicyBinding] = []
    for raw_article in _list(row["article_bindings"], minimum=1, maximum=5_000):
        article = _mapping(raw_article, _ARTICLE_KEYS)
        policy_ids = tuple(
            _string(item)
            for item in _list(article["policy_ids"], minimum=1, maximum=40)
        )
        articles.append(
            ArticlePolicyBinding(
                article_id=_uuid(article["article_id"]),
                article_version_id=_uuid(article["article_version_id"]),
                publication_snapshot_sha256=Sha256Digest(
                    _sha256(article["publication_snapshot_sha256"])
                ),
                policy_ids=policy_ids,
            )
        )
    request = ExternalPolicyRegistryRequest(
        binding=binding,
        snapshot=snapshot,
        version_links=links,
        article_bindings=tuple(articles),
        article_binding_set_sha256=Sha256Digest(
            article_binding_set_fingerprint(tuple(articles))
        ),
        evaluated_at=_instant(row["evaluated_at"]),
    )
    return fixture_id, request


def _canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    except Exception:
        _fail("GENERATION_SERIALIZATION_FAILED")


def _fixture_bytes(
    contract: dict[str, object],
    contract_bytes: bytes,
    external_inputs: tuple[tuple[str, Path, str], ...],
) -> bytes:
    fixtures: list[dict[str, object]] = []
    fixture_ids: set[str] = set()
    request_hashes: set[str] = set()
    expected_fixture_requests = dict(RECORDED_FIXTURE_REQUEST_SHA256S)
    for raw in cast(list[object], contract["fixtures"]):
        fixture_id, request = _build_request(raw)
        if (
            fixture_id in fixture_ids
            or request.fingerprint in request_hashes
            or expected_fixture_requests.get(fixture_id) != request.fingerprint
        ):
            _fail("FIXTURE_DUPLICATE")
        fixture_ids.add(fixture_id)
        request_hashes.add(request.fingerprint)
        report = evaluate_external_policy_registry(request)
        record: dict[str, object] = {
            "fixture_id": fixture_id,
            "request": registry_request_payload(request),
            "request_sha256": request.fingerprint,
            "report": registry_report_payload(report),
            "report_sha256": report.fingerprint,
        }
        record["fixture_sha256"] = hashlib.sha256(
            json.dumps(
                record,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        fixtures.append(record)
    if fixture_ids != set(expected_fixture_requests):
        _fail("FIXTURE_BINDING_MISMATCH")
    output: dict[str, object] = {
        "schema_version": 2,
        "story_id": "ST-1407",
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "local_status": LOCAL_STATUS,
        "classification": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "pinned_inputs": [
            {
                "role": role,
                "uri": f"repo://{path.as_posix()}",
                "sha256": digest,
            }
            for role, path, digest in external_inputs
        ],
        "external_rule_policy_links": [
            {"external_rule_id": rule_id, "policy_ids": list(policy_ids)}
            for rule_id, policy_ids in EXTERNAL_RULE_POLICY_LINKS
        ],
        "fixtures": fixtures,
        "boundary": {
            "official_source_attested": False,
            "current_source_verified": False,
            "source_acquisition": "NOT_IMPLEMENTED_OPEN_018",
            "legal_review": "NOT_COMPLETED_OD_008",
            "notification": "LOCAL_LOG_ONLY_NOT_DELIVERED_OD_011",
            "audit": "NOT_EXECUTED",
            "database": "NOT_EXECUTED",
            "activation_authorized": False,
            "article_mutation_authorized": False,
            "recommendation_mutation_authorized": False,
            "publication_authorized": False,
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
            "formal_tst_019": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return _canonical_json(output)


def _manifest_bytes(
    captured: dict[Path, bytes],
    fixture_bytes: bytes,
    external_inputs: tuple[tuple[str, Path, str], ...],
) -> bytes:
    external_paths = {path for _role, path, _sha in external_inputs}
    material_runtime_paths = {path for path, _digest in MATERIAL_RUNTIME_DEPENDENCIES}
    sources: list[dict[str, object]] = []
    for path, payload in captured.items():
        sources.append(
            {
                "uri": f"repo://{path.as_posix()}",
                "role": (
                    "OWNER_SOURCE"
                    if path in OWNED_SOURCE_PATHS
                    else "PINNED_AUTHORITY_OR_DEPENDENCY"
                    if path in external_paths
                    else "PINNED_RUNTIME_DEPENDENCY"
                    if path in material_runtime_paths
                    else "SECURE_PUBLICATION_HELPER"
                    if path == SECURE_HELPER_PATH
                    else "LOCKED_TOOLCHAIN"
                ),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    document: dict[str, object] = {
        "schema_version": 2,
        "story_id": "ST-1407",
        "local_status": LOCAL_STATUS,
        "classification": "RECORDED_SYNTHETIC_EXTERNAL_POLICY_REGISTRY_MANIFEST_V2",
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifacts": [
            {
                "uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "role": "RECORDED_SYNTHETIC_REGISTRY_FIXTURE",
                "bytes": len(fixture_bytes),
                "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            }
        ],
        "generation": {
            "owner": f"repo://{GENERATOR_PATH.as_posix()}",
            "check": (
                ".venv/bin/python "
                "scripts/build_st1407_external_policy_registry_runtime.py --check"
            ),
            "publication": "ATOMIC_FOREIGN_PRESERVING_MULTI_OUTPUT_WITH_ROLLBACK",
            "secure_helper_sha256": SECURE_HELPER_SHA256,
            "python_version": ".".join(map(str, EXPECTED_PYTHON_VERSION)),
            "pyyaml_version": EXPECTED_PYYAML_VERSION,
        },
        "boundary": {
            "source_acquisition": "NOT_IMPLEMENTED_OPEN_018",
            "official_source_attested": False,
            "legal_review_completed": False,
            "notification_route": "LOCAL_LOG_ONLY",
            "notification_delivered": False,
            "audit_written": False,
            "activation_authorized": False,
            "publication_authorized": False,
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
            "formal_tst_019": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def expected_artifacts(root: Path = REPO_ROOT) -> tuple[tuple[Path, bytes], ...]:
    _validate_toolchain()
    contract_bytes = _read_regular(root, CONTRACT_PATH)
    contract = _parse_contract(contract_bytes)
    external_inputs = _source_inventory(contract)
    captured = _capture_sources(root, contract_bytes, external_inputs)
    _validate_installed_catalogs(captured, external_inputs)
    fixture = _fixture_bytes(contract, contract_bytes, external_inputs)
    manifest = _manifest_bytes(captured, fixture, external_inputs)
    return ((FIXTURE_PATH, fixture), (MANIFEST_PATH, manifest))


def validate_contract_bytes(payload: bytes) -> None:
    """Validate one candidate contract for focused fail-closed tests."""

    _parse_contract(payload)


def read_regular_source(root: Path, relative: Path) -> bytes:
    """Expose the secure source reader without exposing descriptor internals."""

    return _read_regular(root, relative)


def validate_material_runtime_dependency_bytes(
    relative: Path,
    payload: bytes,
) -> None:
    """Reject bytes that do not match one exact executed local dependency."""

    _validate_relative(relative)
    expected = dict(MATERIAL_RUNTIME_DEPENDENCIES).get(relative)
    if (
        expected is None
        or type(payload) is not bytes
        or hashlib.sha256(payload).hexdigest() != expected
    ):
        _fail("SOURCE_HASH_DRIFT")


def _output_path(root: Path, relative: Path) -> Path:
    _validate_relative(relative)
    return _lexical_root(root) / relative


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    artifacts = expected_artifacts(root)
    if check:
        for path, expected in artifacts:
            if _read_regular(root, path, maximum=MAX_GENERATED_BYTES) != expected:
                _fail("GENERATED_ARTIFACT_DRIFT")
        return
    try:
        secure_generated_publication.publish_generated(
            tuple((_output_path(root, path), payload) for path, payload in artifacts),
            namespace="st1407v2",
            maximum_payload_bytes=MAX_GENERATED_BYTES,
        )
    except secure_generated_publication.SecurePublicationError:
        _fail("GENERATION_TRANSACTION_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    arguments, unknown = parser.parse_known_args(argv)
    if unknown:
        return 2
    try:
        build(check=arguments.check)
    except Exception:
        print("ST-1407 V2 external policy registry generation failed", file=sys.stderr)
        return 1
    print(
        "ST-1407 V2 external policy registry checked"
        if arguments.check
        else "ST-1407 V2 external policy registry generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
