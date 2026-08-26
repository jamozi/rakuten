#!/usr/bin/env python3
"""Build the deterministic ST-0304 domain-schema migration bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml
from yaml.tokens import AliasToken, AnchorToken

try:
    from scripts import build_st0201_postgres_service as shared
except ModuleNotFoundError:
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0304/contracts/domain-schema.v1.yaml")
UPSTREAM_CATALOG_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"
)
UPSTREAM_DESIGN_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"
)
README_PATH: Final = Path("changes/st-0304/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st0304_domain_schemas.py")
REVISION_PATH: Final = Path("migrations/versions/202608030004_domain_schemas.py")
CATALOG_PATH: Final = Path("changes/st-0304/generated/domain-catalog.v1.json")
VALIDATION_PATH: Final = Path("changes/st-0304/generated/domain-validation.v1.sql")
MANIFEST_PATH: Final = Path("changes/st-0304/manifest.yaml")
PREDECESSOR_MANIFEST_PATH: Final = Path("changes/st-0303/manifest.yaml")
SUCCESSOR_CONTRACT_PATH: Final = Path(
    "changes/st-0305/contracts/publication-analytics-finance.v1.yaml"
)
GENERATED_PATHS: Final = (
    REVISION_PATH,
    CATALOG_PATH,
    VALIDATION_PATH,
    MANIFEST_PATH,
)
REVISION: Final = "202608030004"
DOWN_REVISION: Final = "202608030003"
RUNNER_VERSION: Final = "1.3.0"
EXPECTED_SERVER_VERSION_NUM: Final = 180004
EXPECTED_CONTRACT_SHA256: Final = (
    "8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122"
)
EXPECTED_UPSTREAM_CATALOG_SHA256: Final = (
    "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d"
)
EXPECTED_UPSTREAM_DESIGN_SHA256: Final = (
    "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
)
EXPECTED_PREDECESSOR_MANIFEST_SHA256: Final = (
    "816b59f87f80ec3c672f271fb3a1efd3e3cdb63a24981ab8aaea64f79356186c"
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python "
    "scripts/build_st0304_domain_schemas.py"
)
SCHEMAS: Final = ("portfolio", "catalog", "evidence", "editorial", "ai", "policy")
SCHEMA_COMMENTS: Final = {
    "portfolio": "サイト、カテゴリ、検索意図、キーワード、機会評価、優先アクション",
    "catalog": "楽天取得、商品同定、ショップ、Offer、外部事実Observation、Current Projection",
    "evidence": "Source、Snapshot、Fact、Source Packet、Claim、根拠対応",
    "editorial": "記事企画、構造化記事版、比較、推薦、レビューコメント、内部リンク",
    "ai": "AI Task、Prompt、Schema、Model Route、Job、Attempt、Token・費用、評価",
    "policy": "Policy Bundle、Rule、品質検査、Finding、Score、Waiver、Gate",
}
FRAGMENT_PATHS: Final = tuple(
    Path(f"changes/st-0304/contracts/physical/{index:02d}-domain-physical.sql")
    for index in range(1, 12)
)
PINNED_INPUTS: Final = {
    UPSTREAM_CATALOG_PATH.as_posix(): EXPECTED_UPSTREAM_CATALOG_SHA256,
    UPSTREAM_DESIGN_PATH.as_posix(): EXPECTED_UPSTREAM_DESIGN_SHA256,
    "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md": "d05d1d4ebe3f3904e58c104e0b1836bc897377dbf27f9019f57c3fc6440bd137",
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    "docs/canonical/01_integration/RAOS_07_canonical_contract_overlay_v1.0.yaml": "f9080e1744096b743b2ada2261d2a023cebf310a08cf3a9fc2d14a53ac56cf3e",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
}
EXPECTED_FINALIZED_OVERLAY_CHECKPOINTS: Final = (
    (
        Path("changes/st-0003/database/202607300007_ai_governance_expand.sql"),
        "a9d07f07ed15541ca19cf8b6324b680ac2addf9370c70b35f86afa9d2bd82064",
    ),
    (
        Path("changes/st-0003/database/202607300008_ai_governance_expand_validate.sql"),
        "9bd988e4fdd9e8c4fc9b631481092af3d92cbf649c7164c83eb7d6ab64efc978",
    ),
    (
        Path("changes/st-0003/database/202607300009_ai_governance_migrate_batch.sql"),
        "30cd41619c7b59c8d759bf854c86d0ac2b381b7d5c320051402919816602545a",
    ),
    (
        Path(
            "changes/st-0003/database/202607300010_ai_governance_contract_prepare.sql"
        ),
        "380ab7c96bdc73c1a562baef4918c4c4dfbc533e05014435363db9eeea682b25",
    ),
    (
        Path("changes/st-0003/database/202607300011_ai_governance_contract.sql"),
        "8aa37799806be8bbbafd952b03627d16ec6dce459a77a03503f562b61550d9da",
    ),
    (
        Path("changes/st-0004/database/202607300013_content_expand.sql"),
        "cdb4ba3f94691425059b2282f343b0cdc82e6b82bb93fdbfe8dd3a6a3dd4290e",
    ),
    (
        Path("changes/st-0004/database/202607300014_content_expand_validate.sql"),
        "16333a0a0aa8cb1f30d488faaef2dc387043619aed2937ed0d9a0aebd4d32704",
    ),
    (
        Path("changes/st-0004/database/202607300015_content_migrate_batch.sql"),
        "271af87f846489ac855ba66b371dc659698604f35f1dd82e34b8eb0b52a8c00c",
    ),
    (
        Path("changes/st-0004/database/202607300016_content_contract_prepare.sql"),
        "b61ffcba92a270a90c9a2492fa602b43b8e048ea75e74ef57016852079ddf968",
    ),
    (
        Path("changes/st-0004/database/202607300017_content_contract.sql"),
        "c3598c730dfb0c2354f227e574db88d56399c2cfd78974827738d5cceaf0a845",
    ),
)
EXPECTED_FRAGMENT_SHA256: Final = (
    "b2f937ae00d526a886e5e875e095e247702f4bd7831a3164e2eda93423d7fdb8",
    "b685751e4e2743ea6c7202e8ce726486ac152e46987bb832e6777e61b987aafc",
    "f95ad5a2fd349177b01f97237d0d9a3fb598b2781828e9531a04c3c42b811b45",
    "4a3c029980e8c27957fac2291e7b0a8efb81eaf1faa74dee4e757b0836e7ba30",
    "c78e946f9be015d461350f347f125a2cf8f01b267647a8685158af207cefc0ec",
    "cc520254390d68fdc68d54c01ed6b95e031ea422814e5be924849ec61636904d",
    "739cc2ecae7e49702da5e36be6e37eaebaa7a535be4a623c79dee86926212870",
    "eafb7b89c6fa08bd74a8c13d89aa19aea3a946e739720a8cff9e6faa3ca2bfc4",
    "6cebf09249f027662557038f8367bdc586030197911046be242543cd43502ae5",
    "3d806436b7ed91f25e0396e15b914dda7258b743589ec4dc6c3f4272c9fcb38d",
    "947e480157a52b0d926461a4d40a7409e92e6e50482c216d394953a462d8cd09",
)
RLS_TABLES: Final = (
    "editorial.article_disclosure_context",
    "editorial.article_methodology_binding",
    "editorial.article_template_version",
    "editorial.article_type_version",
    "editorial.content_schema_version",
    "editorial.editorial_methodology_version",
    "editorial.media_asset",
    "editorial.seo_metadata_version",
    "editorial.structured_data_manifest",
    "evidence.first_hand_experience_asset",
    "evidence.first_hand_experience_record",
)
BASELINE_SCHEMA_KEYS: Final = frozenset({"id", "name", "purpose", "tables"})
BASELINE_TABLE_KEYS: Final = frozenset(
    {
        "name",
        "fully_qualified_name",
        "purpose",
        "owner_module",
        "write_pattern",
        "classification",
        "retention_class",
        "primary_key",
        "expected_scale",
        "partitioning",
        "requirements",
        "architecture_refs",
        "implementation_slice",
        "notes",
        "columns",
        "unique_constraints",
        "check_constraints",
        "foreign_keys",
        "indexes",
    }
)
BASELINE_COLUMN_KEYS: Final = frozenset(
    {"name", "type", "nullable", "default", "description", "classification", "pii"}
)
CURRENT_SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    *FRAGMENT_PATHS,
    *(path for path, _digest in EXPECTED_FINALIZED_OVERLAY_CHECKPOINTS),
    *(Path(path) for path in PINNED_INPUTS),
    README_PATH,
    Path("Makefile"),
    Path("README.md"),
    Path("docs/execplans/ST-0304.md"),
    Path("docs/worklogs/ST-0304.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0303_iam_ops.py"),
    PREDECESSOR_MANIFEST_PATH,
    Path("migrations/versions/202608030003_iam_ops_tables.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/runner.py"),
    Path("scripts/build_st0201_postgres_service.py"),
    Path("tests/postgresql18.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("tests/st0304/conftest.py"),
    Path("tests/st0304/test_contract.py"),
    Path("tests/st0304/test_generation.py"),
    Path("tests/st0304/test_postgresql.py"),
)


@dataclass(frozen=True, slots=True)
class PhysicalObject:
    """One reviewed object block from the frozen PostgreSQL 18.4 translation."""

    name: str
    object_type: str
    schema: str
    sql: str
    sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _required_open_flags() -> tuple[int, int, int]:
    """Return Linux descriptor-safety flags, failing closed if any are unusable."""

    values: list[int] = []
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        value = getattr(os, name, None)
        _require(
            type(value) is int and value > 0,
            f"required secure open flag {name} is unavailable or invalid",
        )
        values.append(value)
    return values[0], values[1], values[2]


def _secure_read(root: Path, relative: Path, label: str, limit: int) -> bytes:
    """Read a repository file descriptor-relatively without following symlinks."""

    directory_flag, nofollow_flag, nonblock_flag = _required_open_flags()
    _require(
        not relative.is_absolute()
        and bool(relative.parts)
        and all(part not in {"", ".", ".."} for part in relative.parts),
        f"unsafe {label} path",
    )
    root_metadata = root.lstat()
    _require(
        stat.S_ISDIR(root_metadata.st_mode) and not stat.S_ISLNK(root_metadata.st_mode),
        "repository root must be a real directory",
    )
    directory_flags = os.O_RDONLY | directory_flag | nofollow_flag
    descriptors: list[int] = []
    descriptor = os.open(root, directory_flags)
    descriptors.append(descriptor)
    try:
        for part in relative.parts[:-1]:
            descriptor = os.open(part, directory_flags, dir_fd=descriptor)
            descriptors.append(descriptor)
        path_before = os.stat(
            relative.name,
            dir_fd=descriptor,
            follow_symlinks=False,
        )
        _require(stat.S_ISREG(path_before.st_mode), f"{label} must be a regular file")
        file_descriptor = os.open(
            relative.name,
            os.O_RDONLY | nofollow_flag | nonblock_flag,
            dir_fd=descriptor,
        )
        try:
            metadata_before = os.fstat(file_descriptor)
            _require(
                stat.S_ISREG(metadata_before.st_mode),
                f"{label} must be a regular file",
            )
            _require(metadata_before.st_size <= limit, f"{label} exceeds size limit")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            _require(len(content) <= limit, f"{label} exceeds size limit")
            metadata_after = os.fstat(file_descriptor)
            path_after = os.stat(
                relative.name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            stable_fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            _require(
                all(
                    getattr(path_before, field)
                    == getattr(metadata_before, field)
                    == getattr(metadata_after, field)
                    == getattr(path_after, field)
                    for field in stable_fields
                ),
                f"{label} changed while it was being verified",
            )
            return content
        finally:
            os.close(file_descriptor)
    finally:
        for opened in reversed(descriptors):
            os.close(opened)


def _load_yaml(content: bytes, label: str) -> dict[str, Any]:
    text = content.decode("utf-8")
    for token in yaml.scan(text):
        _require(
            not isinstance(token, (AliasToken, AnchorToken)),
            f"{label} aliases and anchors are forbidden",
        )
    value = yaml.load(text, Loader=shared.UniqueKeyLoader)
    _require(isinstance(value, dict), f"{label} must be a mapping")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be a mapping")
    return value  # type: ignore[return-value]


def _sequence(value: object, label: str) -> Sequence[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, str | bytes),
        f"{label} must be a sequence",
    )
    return value


def _load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    content = _secure_read(root, CONTRACT_PATH, "ST-0304 contract", 2 * 1024 * 1024)
    contract = _load_yaml(content, "ST-0304 contract")
    document = _mapping(contract.get("document"), "document")
    _require(document.get("story_id") == "ST-0304", "contract story differs")
    story = _mapping(contract.get("story"), "story")
    _require(story.get("open_decisions") == [], "contract has open decisions")
    precedence = _mapping(contract.get("source_precedence"), "source precedence")
    _require(tuple(precedence.get("schemas", ())) == SCHEMAS, "schema order differs")
    fragment_rows = _sequence(
        precedence.get("physical_translation_fragments"), "fragments"
    )
    observed_fragments = tuple(
        (
            str(_mapping(row, "fragment").get("path")),
            str(_mapping(row, "fragment").get("sha256")),
        )
        for row in fragment_rows
    )
    _require(
        observed_fragments
        == tuple(
            zip(
                (path.as_posix() for path in FRAGMENT_PATHS),
                EXPECTED_FRAGMENT_SHA256,
                strict=True,
            )
        ),
        "fragment inventory differs",
    )
    checkpoint_inventory = _mapping(
        precedence.get("finalized_overlay_checkpoints"),
        "finalized overlay checkpoints",
    )
    _require(
        checkpoint_inventory.get("execution") == "PROVENANCE_ONLY_NOT_CONCATENATED",
        "finalized overlay checkpoint execution boundary differs",
    )
    checkpoint_rows = _sequence(
        checkpoint_inventory.get("files"), "finalized overlay checkpoint files"
    )
    observed_checkpoints = tuple(
        (
            Path(str(_mapping(row, "finalized overlay checkpoint").get("path"))),
            str(_mapping(row, "finalized overlay checkpoint").get("sha256")),
        )
        for row in checkpoint_rows
    )
    _require(
        observed_checkpoints == EXPECTED_FINALIZED_OVERLAY_CHECKPOINTS,
        "finalized overlay checkpoint inventory differs",
    )
    inventory = _mapping(contract.get("expected_inventory"), "inventory")
    expected_inventory = {
        "schemas_created": 6,
        "tables": 86,
        "views": 1,
        "columns": 1141,
        "not_null_constraints": 861,
        "primary_keys": 86,
        "named_unique_constraints": 93,
        "check_constraints": 453,
        "immediate_foreign_keys": 264,
        "deferred_foreign_keys": 1,
        "standalone_indexes": 274,
        "total_indexes": 453,
        "functions": 48,
        "triggers": 81,
        "rls_policies": 0,
        "rls_enabled_tables": 11,
        "rls_forced_tables": 11,
        "ignored_st0306_policies": 22,
    }
    for key, expected in expected_inventory.items():
        _require(inventory.get(key) == expected, f"inventory {key} differs")
    security = _mapping(contract.get("security"), "security")
    _require(
        security.get("create_rls_policies") is False, "RLS policy ownership differs"
    )
    _require(
        security.get("rls_policy_owner_story") == "ST-0306", "RLS policy owner differs"
    )
    _require(
        tuple(_sequence(security.get("rls_enabled_and_forced_tables"), "RLS tables"))
        == RLS_TABLES,
        "RLS table inventory differs",
    )
    return contract


def _load_objects(root: Path = REPO_ROOT) -> tuple[PhysicalObject, ...]:
    blocks: list[str] = []
    for path, _historical_digest in zip(
        FRAGMENT_PATHS, EXPECTED_FRAGMENT_SHA256, strict=True
    ):
        content = _secure_read(root, path, "physical fragment", 128 * 1024)
        text = content.decode("utf-8")
        start = text.find("--\n-- Name: ")
        _require(start >= 0, "physical fragment has no object block")
        blocks.extend(re.split(r"(?=^--\n-- Name: )", text[start:], flags=re.MULTILINE))
    objects: list[PhysicalObject] = []
    header = re.compile(
        r"^--\n-- Name: (.*?); Type: (.*?); Schema: (.*?); Owner: -\n--\n\n", re.DOTALL
    )
    for block in blocks:
        if not block.strip():
            continue
        match = header.match(block)
        _require(match is not None, "physical object header is invalid")
        name, object_type, schema = match.groups()
        sql = block[match.end() :].strip()
        _require(schema in SCHEMAS, "physical object schema is outside scope")
        _require(sql.endswith(";"), "physical object SQL is incomplete")
        objects.append(
            PhysicalObject(name, object_type, schema, sql, _sha256(sql.encode()))
        )
    return tuple(objects)


def _table_column_entries(sql: str) -> tuple[str, ...]:
    """Return top-level column clauses from one pg_dump CREATE TABLE block."""

    match = re.search(r"^CREATE TABLE .*? \(\n(?P<body>.*?)\n\);", sql, re.DOTALL)
    _require(match is not None, "table block is missing CREATE TABLE")
    entries: list[str] = []
    current: list[str] = []
    for line in match.group("body").splitlines():
        if re.match(r'^    (?:"[^"]+"|CONSTRAINT )', line):
            if current and current[0].startswith('    "'):
                entries.append("\n".join(current))
            current = [line]
        else:
            _require(bool(current), "table clause continuation is invalid")
            current.append(line)
    if current and current[0].startswith('    "'):
        entries.append("\n".join(current))
    return tuple(entries)


def validate_source_inputs(root: Path = REPO_ROOT) -> dict[str, int]:
    """Validate every frozen input without producing or changing an artifact."""

    _load_contract(root)
    for path_text, expected_digest in PINNED_INPUTS.items():
        content = _secure_read(
            root, Path(path_text), "pinned design input", 16 * 1024 * 1024
        )
        _require(
            _sha256(content) == expected_digest, "pinned design input digest differs"
        )
    for path, _historical_digest in EXPECTED_FINALIZED_OVERLAY_CHECKPOINTS:
        _secure_read(
            root,
            path,
            "finalized overlay checkpoint",
            16 * 1024 * 1024,
        )
    _secure_read(
        root,
        PREDECESSOR_MANIFEST_PATH,
        "ST-0303 predecessor manifest",
        2 * 1024 * 1024,
    )

    objects = _load_objects(root)
    _load_baseline_metadata(root, objects)
    counts = Counter(item.object_type for item in objects)
    expected_object_counts = {
        "COMMENT": 898,
        "CONSTRAINT": 179,
        "FK CONSTRAINT": 264,
        "FUNCTION": 48,
        "INDEX": 274,
        "ROW SECURITY": 11,
        "TABLE": 86,
        "TRIGGER": 81,
        "VIEW": 1,
    }
    _require(dict(counts) == expected_object_counts, "physical object counts differ")

    table_objects = tuple(item for item in objects if item.object_type == "TABLE")
    columns = tuple(
        entry for item in table_objects for entry in _table_column_entries(item.sql)
    )
    _require(len(columns) == 1141, "physical column count differs")
    _require(
        sum(" NOT NULL" in entry for entry in columns) == 861, "NOT NULL count differs"
    )
    _require(
        sum(item.sql.count('CONSTRAINT "ck_') for item in table_objects) == 453,
        "CHECK constraint count differs",
    )
    constraints = tuple(item for item in objects if item.object_type == "CONSTRAINT")
    _require(
        sum(" PRIMARY KEY " in item.sql for item in constraints) == 86,
        "PK count differs",
    )
    _require(
        sum(" UNIQUE " in item.sql for item in constraints) == 93,
        "unique count differs",
    )

    all_sql = "\n".join(item.sql for item in objects)
    _require(
        all_sql.count(" FORCE ROW LEVEL SECURITY") == 11, "FORCE RLS count differs"
    )
    _require(
        all_sql.count(" ENABLE ROW LEVEL SECURITY") == 11, "ENABLE RLS count differs"
    )
    _require("CREATE POLICY" not in all_sql, "role-bound RLS policy entered ST-0304")
    _require("CREATE ROLE" not in all_sql, "database role entered ST-0304")
    _require(
        "ALTER DEFAULT PRIVILEGES" not in all_sql, "default privilege entered ST-0304"
    )
    _require(re.search(r"(?m)^GRANT\s", all_sql) is None, "grant entered ST-0304")
    _require(
        "\\restrict" not in all_sql and "\\unrestrict" not in all_sql,
        "pg_dump session marker entered fragments",
    )

    return {
        "columns": len(columns),
        "foreign_keys": counts["FK CONSTRAINT"],
        "functions": counts["FUNCTION"],
        "objects": len(objects),
        "rls_enabled": all_sql.count(" ENABLE ROW LEVEL SECURITY"),
        "rls_forced": all_sql.count(" FORCE ROW LEVEL SECURITY"),
        "rls_policies": 0,
        "tables": counts["TABLE"],
        "triggers": counts["TRIGGER"],
        "views": counts["VIEW"],
    }


def _split_sql_statements(script: str) -> tuple[str, ...]:
    """Split reviewed PostgreSQL SQL without splitting quoted function bodies."""

    statements: list[str] = []
    start = 0
    index = 0
    state = "normal"
    dollar_tag = ""
    while index < len(script):
        if state == "single":
            if script[index] == "'":
                if index + 1 < len(script) and script[index + 1] == "'":
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue
        if state == "double":
            if script[index] == '"':
                if index + 1 < len(script) and script[index + 1] == '"':
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue
        if state == "line_comment":
            if script[index] == "\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if script.startswith("*/", index):
                state = "normal"
                index += 2
            else:
                index += 1
            continue
        if state == "dollar":
            if script.startswith(dollar_tag, index):
                state = "normal"
                index += len(dollar_tag)
            else:
                index += 1
            continue

        if script.startswith("--", index):
            state = "line_comment"
            index += 2
        elif script.startswith("/*", index):
            state = "block_comment"
            index += 2
        elif script[index] == "'":
            state = "single"
            index += 1
        elif script[index] == '"':
            state = "double"
            index += 1
        elif script[index] == "$":
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", script[index:])
            if match is None:
                index += 1
            else:
                dollar_tag = match.group(0)
                state = "dollar"
                index += len(dollar_tag)
        elif script[index] == ";":
            statement = script[start : index + 1].strip()
            if statement:
                statements.append(statement)
            start = index + 1
            index += 1
        else:
            index += 1
    _require(state == "normal", "physical SQL has an unterminated quote")
    _require(not script[start:].strip(), "physical SQL is missing a terminator")
    return tuple(statements)


def _quote_identifier(value: str) -> str:
    _require(
        re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value) is not None, "invalid identifier"
    )
    return f'"{value}"'


def _quoted_table(schema: str, table: str) -> str:
    return f"{_quote_identifier(schema)}.{_quote_identifier(table)}"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _foreign_key_identity(item: PhysicalObject) -> tuple[str, str, str]:
    match = re.search(
        r'^ALTER TABLE ONLY "(?P<schema>[a-z0-9_]+)"\."(?P<table>[a-z0-9_]+)"\s+'
        r'ADD CONSTRAINT "(?P<constraint>[a-z0-9_]+)" FOREIGN KEY',
        item.sql,
    )
    _require(match is not None, "foreign key statement shape differs")
    return match.group("schema"), match.group("table"), match.group("constraint")


def _table_identity(item: PhysicalObject) -> tuple[str, str]:
    match = re.match(
        r'^CREATE TABLE "(?P<schema>[a-z0-9_]+)"\."(?P<table>[a-z0-9_]+)"',
        item.sql,
    )
    _require(match is not None, "table statement shape differs")
    return match.group("schema"), match.group("table")


def _load_baseline_metadata(
    root: Path,
    objects: Sequence[PhysicalObject],
) -> dict[str, Any]:
    """Load and validate the complete selected upstream baseline metadata."""

    content = _secure_read(
        root,
        UPSTREAM_CATALOG_PATH,
        "upstream machine data catalog",
        16 * 1024 * 1024,
    )
    _require(
        _sha256(content) == EXPECTED_UPSTREAM_CATALOG_SHA256,
        "upstream machine data catalog digest differs",
    )
    upstream = _load_yaml(content, "upstream machine data catalog")
    document = _mapping(upstream.get("document"), "upstream catalog document")
    _require(document.get("id") == "RAOS-DATA-001", "upstream catalog id differs")
    _require(document.get("version") == "0.1", "upstream catalog version differs")
    _require(
        document.get("status") == "BASELINE_CANDIDATE",
        "upstream catalog status differs",
    )
    _require(
        document.get("target_postgresql") == "18.4",
        "upstream catalog PostgreSQL target differs",
    )

    upstream_schema_rows = _sequence(upstream.get("schemas"), "upstream schemas")
    selected_schemas: list[dict[str, Any]] = []
    for schema_id in SCHEMAS:
        matches = [
            _mapping(row, "upstream schema")
            for row in upstream_schema_rows
            if _mapping(row, "upstream schema").get("id") == schema_id
        ]
        _require(len(matches) == 1, f"upstream schema {schema_id} differs")
        selected_schemas.append(dict(matches[0]))

    physical_columns: dict[tuple[str, str], set[str]] = {}
    for item in objects:
        if item.object_type != "TABLE":
            continue
        identity = _table_identity(item)
        column_names: set[str] = set()
        for entry in _table_column_entries(item.sql):
            match = re.match(r'^    "(?P<name>[a-z0-9_]+)"(?:\s|\n)', entry)
            _require(match is not None, "physical column identity differs")
            column_names.add(match.group("name"))
        physical_columns[identity] = column_names

    observed_fqns: set[str] = set()
    table_count = 0
    column_count = 0
    for expected_schema_id, schema in zip(SCHEMAS, selected_schemas, strict=True):
        _require(set(schema) == BASELINE_SCHEMA_KEYS, "baseline schema keys differ")
        _require(
            schema.get("id") == expected_schema_id, "baseline schema order differs"
        )
        tables = _sequence(schema.get("tables"), "baseline tables")
        for table_value in tables:
            table = _mapping(table_value, "baseline table")
            _require(set(table) == BASELINE_TABLE_KEYS, "baseline table keys differ")
            table_name = table.get("name")
            fully_qualified_name = table.get("fully_qualified_name")
            _require(type(table_name) is str, "baseline table name differs")
            _require(type(fully_qualified_name) is str, "baseline table FQN differs")
            _require(
                fully_qualified_name not in observed_fqns,
                "baseline table FQN is duplicated",
            )
            observed_fqns.add(fully_qualified_name)
            _require(
                fully_qualified_name == f"{expected_schema_id}.{table_name}",
                "baseline table FQN differs",
            )
            physical_identity = (expected_schema_id, table_name)
            _require(
                physical_identity in physical_columns,
                "baseline table is missing from physical inventory",
            )
            columns = _sequence(table.get("columns"), "baseline columns")
            observed_column_names: set[str] = set()
            for column_value in columns:
                column = _mapping(column_value, "baseline column")
                _require(
                    set(column) == BASELINE_COLUMN_KEYS,
                    "baseline column keys differ",
                )
                column_name = column.get("name")
                _require(type(column_name) is str, "baseline column name differs")
                _require(
                    column_name not in observed_column_names,
                    "baseline column name is duplicated",
                )
                observed_column_names.add(column_name)
                _require(
                    column_name in physical_columns[physical_identity],
                    "baseline column is missing from physical inventory",
                )
            table_count += 1
            column_count += len(columns)

    _require(len(selected_schemas) == 6, "baseline schema count differs")
    _require(table_count == 66, "baseline table count differs")
    _require(column_count == 821, "baseline column count differs")
    return {
        "provenance": {
            "translation_rule": "PRESERVE_ALL_BASELINE_TABLE_METADATA",
            "machine_source": {
                "path": f"repo://{UPSTREAM_CATALOG_PATH.as_posix()}",
                "sha256": EXPECTED_UPSTREAM_CATALOG_SHA256,
                "role": "BASELINE_MACHINE_TABLE_INVENTORY",
            },
            "design_source": {
                "path": f"repo://{UPSTREAM_DESIGN_PATH.as_posix()}",
                "sha256": EXPECTED_UPSTREAM_DESIGN_SHA256,
                "role": "DOMAIN_AND_IMMUTABILITY_DESIGN",
            },
        },
        "schema_count": len(selected_schemas),
        "table_count": table_count,
        "column_count": column_count,
        "schemas": selected_schemas,
    }


def _view_identity(item: PhysicalObject) -> tuple[str, str]:
    match = re.match(
        r'^CREATE VIEW "(?P<schema>[a-z0-9_]+)"\."(?P<view>[a-z0-9_]+)"',
        item.sql,
    )
    _require(match is not None, "view statement shape differs")
    return match.group("schema"), match.group("view")


def _function_drop_identity(item: PhysicalObject) -> str:
    match = re.fullmatch(r"(?P<name>[a-z][a-z0-9_]*)\((?P<args>.*)\)", item.name)
    _require(match is not None, "function identity differs")
    return (
        f"{_quote_identifier(item.schema)}.{_quote_identifier(match.group('name'))}"
        f"({match.group('args')})"
    )


def render_upgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Render one additive, transaction-safe ST-0304 upgrade."""

    objects = _load_objects(root)
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL TIME ZONE 'UTC';",
        "SET LOCAL check_function_bodies = false;",
    ]
    for schema in SCHEMAS:
        quoted = _quote_identifier(schema)
        statements.extend(
            (
                f"CREATE SCHEMA {quoted};",
                f"COMMENT ON SCHEMA {quoted} IS {_sql_literal(SCHEMA_COMMENTS[schema])};",
                f"REVOKE ALL PRIVILEGES ON SCHEMA {quoted} FROM PUBLIC;",
            )
        )

    validations: list[str] = []
    for item in objects:
        object_statements = _split_sql_statements(item.sql)
        if item.object_type != "FK CONSTRAINT":
            statements.extend(object_statements)
            continue
        _require(
            len(object_statements) == 1, "foreign key block must contain one statement"
        )
        statement = object_statements[0]
        _require(
            " NOT VALID" not in statement, "source foreign key is unexpectedly pending"
        )
        schema, table, constraint = _foreign_key_identity(item)
        statements.append(statement[:-1] + " NOT VALID;")
        validations.append(
            f"ALTER TABLE ONLY {_quoted_table(schema, table)} "
            f"VALIDATE CONSTRAINT {_quote_identifier(constraint)};"
        )
    statements.extend(validations)

    statements.append(
        """DO $raos_st0304_site_fk_preflight$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM ops.job AS job
        LEFT JOIN portfolio.site AS site ON site.id = job.site_id
        WHERE job.site_id IS NOT NULL AND site.id IS NULL
        LIMIT 1
    ) THEN
        RAISE EXCEPTION 'ST0304_OPS_JOB_SITE_ORPHAN'
            USING ERRCODE = '23503';
    END IF;
END
$raos_st0304_site_fk_preflight$;"""
    )
    statements.extend(
        (
            'ALTER TABLE ONLY "ops"."job" ADD CONSTRAINT "fk_ops_job_site_id" '
            'FOREIGN KEY ("site_id") REFERENCES "portfolio"."site"("id") '
            "ON DELETE RESTRICT NOT VALID;",
            'ALTER TABLE ONLY "ops"."job" VALIDATE CONSTRAINT "fk_ops_job_site_id";',
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "
            + ", ".join(_quote_identifier(schema) for schema in SCHEMAS)
            + " FROM PUBLIC;",
            "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA "
            + ", ".join(_quote_identifier(schema) for schema in SCHEMAS)
            + " FROM PUBLIC;",
        )
    )
    joined = "\n".join(statements)
    _require(
        "fk_iam_break_glass_record_incident_id" not in joined,
        "incident FK entered ST-0304",
    )
    _require("CREATE POLICY" not in joined, "RLS policy entered upgrade")
    _require(
        sum(" NOT VALID;" in item for item in statements) == 265,
        "pending FK add count differs",
    )
    _require(
        sum("VALIDATE CONSTRAINT" in item for item in statements) == 265,
        "FK validation count differs",
    )
    return tuple(statements)


def render_downgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Render the single-transaction guarded downgrade to exact ST-0303."""

    objects = _load_objects(root)
    tables = tuple(
        _table_identity(item) for item in objects if item.object_type == "TABLE"
    )
    views = tuple(
        _view_identity(item) for item in objects if item.object_type == "VIEW"
    )
    foreign_keys = tuple(
        _foreign_key_identity(item)
        for item in objects
        if item.object_type == "FK CONSTRAINT"
    )
    functions = tuple(item for item in objects if item.object_type == "FUNCTION")
    _require(len(tables) == 86, "downgrade table inventory differs")

    lock_targets = ((_quote_identifier("ops"), _quote_identifier("job")),) + tuple(
        (_quote_identifier(schema), _quote_identifier(table))
        for schema, table in tables
    )
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL TIME ZONE 'UTC';",
        "LOCK TABLE "
        + ", ".join(f"{schema}.{table}" for schema, table in lock_targets)
        + " IN ACCESS EXCLUSIVE MODE;",
    ]
    statements.extend(
        f"ALTER TABLE ONLY {_quoted_table(*table.split('.', 1))} NO FORCE ROW LEVEL SECURITY;"
        for table in RLS_TABLES
    )
    empty_expressions = [
        f"EXISTS (SELECT 1 FROM {_quoted_table(schema, table)} LIMIT 1)"
        for schema, table in tables
    ]
    statements.append(
        "DO $raos_st0304_downgrade_preflight$\nBEGIN\n    IF\n        "
        + "\n        OR ".join(empty_expressions)
        + "\n    THEN\n        RAISE EXCEPTION 'ST0304_DOWNGRADE_NONEMPTY' "
        "USING ERRCODE = '55000';\n    END IF;\nEND\n"
        "$raos_st0304_downgrade_preflight$;"
    )
    statements.append(
        'ALTER TABLE ONLY "ops"."job" DROP CONSTRAINT "fk_ops_job_site_id" RESTRICT;'
    )
    statements.extend(
        f"DROP VIEW {_quoted_table(schema, view)} RESTRICT;"
        for schema, view in reversed(views)
    )
    statements.extend(
        f"ALTER TABLE ONLY {_quoted_table(schema, table)} "
        f"DROP CONSTRAINT {_quote_identifier(constraint)} RESTRICT;"
        for schema, table, constraint in reversed(foreign_keys)
    )
    statements.extend(
        f"DROP TABLE {_quoted_table(schema, table)} RESTRICT;"
        for schema, table in reversed(tables)
    )
    statements.extend(
        f"DROP FUNCTION {_function_drop_identity(item)} RESTRICT;"
        for item in reversed(functions)
    )
    statements.extend(
        f"DROP SCHEMA {_quote_identifier(schema)} RESTRICT;"
        for schema in reversed(SCHEMAS)
    )
    joined = "\n".join(statements)
    _require(" CASCADE" not in joined, "downgrade must remain RESTRICT-only")
    _require(joined.count("DROP TABLE ") == 86, "downgrade table drop count differs")
    _require(
        joined.count("DROP FUNCTION ") == 48, "downgrade function drop count differs"
    )
    return tuple(statements)


def _render_bytes_tuple(name: str, content: bytes) -> str:
    chunks = [content[index : index + 80] for index in range(0, len(content), 80)]
    return "\n".join(
        [f"{name}: tuple[bytes, ...] = ("]
        + [f'    b"{chunk.decode("ascii")}",' for chunk in chunks]
        + [")"]
    )


def render_revision(root: Path = REPO_ROOT) -> bytes:
    """Render a bounded single Alembic revision with an integrity-bound payload."""

    payload = json.dumps(
        {
            "upgrade": render_upgrade_statements(root),
            "downgrade": render_downgrade_statements(root),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload_sha256 = _sha256(payload)
    encoded = base64.b85encode(zlib.compress(payload, level=9))
    encoded_tuple = _render_bytes_tuple("_PAYLOAD_B85", encoded)
    text = f'''\
"""Install the exact ST-0304 domain-schema physical contract.

Revision ID: {REVISION}
Revises: {DOWN_REVISION}
Create Date: 2026-08-04

RAOS metadata:
- story: ST-0304
- requirement IDs: FR-001, FR-002, FR-003, FR-004, FR-007, FR-018
- architecture: MIG-002/MIG-003/MIG-004/MIG-005/MIG-006 policy-only domain slice
- runner version: {RUNNER_VERSION}
- server version: {EXPECTED_SERVER_VERSION_NUM}
- risk class: B (additive schemas, tables, constraints, indexes, functions, and triggers)
- estimated lock: additive catalog DDL; guarded ACCESS EXCLUSIVE on downgrade
- backfill job: none
- rollback category: reversible only while all 86 owned tables are empty; RESTRICT
- transaction: one PostgreSQL transaction for the complete Story revision
- rollback: lock and prove all 86 owned tables empty, then RESTRICT only
"""

from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections.abc import Sequence
from typing import Any

from alembic import op


revision: str = "{REVISION}"
down_revision: str | None = "{DOWN_REVISION}"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_PAYLOAD_SHA256 = "{payload_sha256}"
_MAX_PAYLOAD_BYTES = 2 * 1024 * 1024


{encoded_tuple}


def _decode_payload() -> tuple[tuple[str, ...], tuple[str, ...]]:
    compressed = base64.b85decode(b"".join(_PAYLOAD_B85))
    raw = zlib.decompress(compressed)
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise RuntimeError("ST0304_PAYLOAD_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != _PAYLOAD_SHA256:
        raise RuntimeError("ST0304_PAYLOAD_DIGEST_MISMATCH")
    value: Any = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {{"upgrade", "downgrade"}}:
        raise RuntimeError("ST0304_PAYLOAD_SHAPE_INVALID")
    upgrade = value["upgrade"]
    downgrade = value["downgrade"]
    if (
        not isinstance(upgrade, list)
        or not isinstance(downgrade, list)
        or not all(isinstance(item, str) for item in (*upgrade, *downgrade))
    ):
        raise RuntimeError("ST0304_PAYLOAD_STATEMENTS_INVALID")
    return tuple(upgrade), tuple(downgrade)


UPGRADE_STATEMENTS, DOWNGRADE_STATEMENTS = _decode_payload()


def _execute_statements(statements: tuple[str, ...]) -> None:
    connection = op.get_bind().execution_options(no_parameters=True)
    for statement in statements:
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute_statements(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute_statements(DOWNGRADE_STATEMENTS)
'''
    content = text.encode("utf-8")
    _require(len(content) < 256 * 1024, "generated revision exceeds 256 KiB")
    compile(content, REVISION_PATH.as_posix(), "exec")
    return content


def render_catalog(
    root: Path,
    contract: Mapping[str, Any],
    revision: bytes,
    validation: bytes,
) -> bytes:
    """Render the reviewable machine inventory for every translated object."""

    objects = _load_objects(root)
    baseline_metadata = _load_baseline_metadata(root, objects)
    object_rows = [
        {
            "name": item.name,
            "schema": item.schema,
            "sha256": item.sha256,
            "type": item.object_type,
        }
        for item in objects
    ]
    object_inventory_bytes = json.dumps(
        object_rows,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    document = {
        "document": {
            "id": "RAOS-DOMAIN-SCHEMA-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0304",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "path": f"repo://{REVISION_PATH.as_posix()}",
            "bytes": len(revision),
            "sha256": _sha256(revision),
            "single_transaction": True,
            "compressed_payload": True,
        },
        "validation": {
            "path": f"repo://{VALIDATION_PATH.as_posix()}",
            "bytes": len(validation),
            "sha256": _sha256(validation),
        },
        "source_contract": {
            "path": f"repo://{CONTRACT_PATH.as_posix()}",
            "sha256": EXPECTED_CONTRACT_SHA256,
        },
        "baseline_metadata": baseline_metadata,
        "physical_fragments": [
            {"path": f"repo://{path.as_posix()}", "sha256": digest}
            for path, digest in zip(
                FRAGMENT_PATHS, EXPECTED_FRAGMENT_SHA256, strict=True
            )
        ],
        "inventory": dict(_mapping(contract["expected_inventory"], "inventory")),
        "postgresql_18_4_catalog_digests": dict(
            _mapping(
                contract["expected_postgresql_18_4_catalog_digests"],
                "catalog digests",
            )
        ),
        "object_inventory": {
            "count": len(object_rows),
            "sha256": _sha256(object_inventory_bytes),
            "objects": object_rows,
        },
        "foreign_key_boundary": {
            "source_schema_foreign_keys": 264,
            "connected_from_st0303": "fk_ops_job_site_id",
            "connected_target": "portfolio.site(id)",
            "connected_on_delete": "RESTRICT",
            "connected_via": "ORPHAN_PREFLIGHT_NOT_VALID_THEN_VALIDATE",
            "retained_deferred": "fk_iam_break_glass_record_incident_id",
        },
        "rls_boundary": {
            "enabled_and_forced_tables": list(RLS_TABLES),
            "policy_count": 0,
            "deferred_policy_count": 22,
            "policy_owner_story": "ST-0306",
            "without_policies": "INTENTIONALLY_FAIL_CLOSED",
        },
        "boundary": dict(_mapping(contract["boundary"], "boundary")),
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _values(rows: Sequence[Sequence[object]]) -> str:
    rendered: list[str] = []
    for row in rows:
        values = []
        for value in row:
            if isinstance(value, int):
                values.append(str(value))
            else:
                values.append(_sql_literal(str(value)))
        rendered.append("(" + ", ".join(values) + ")")
    return ",\n        ".join(rendered)


def render_validation_sql(contract: Mapping[str, Any], revision_sha256: str) -> bytes:
    """Render a no-write exact PostgreSQL 18.4 catalog validator."""

    digests = _mapping(
        contract["expected_postgresql_18_4_catalog_digests"], "catalog digests"
    )
    expected_digest_rows = [
        (
            kind,
            int(_mapping(digests[kind], kind)["count"]),
            str(_mapping(digests[kind], kind)["md5"]),
        )
        for kind in (
            "relations",
            "columns",
            "constraints",
            "indexes",
            "functions",
            "triggers",
        )
    ]
    schema_rows = [(schema, SCHEMA_COMMENTS[schema]) for schema in SCHEMAS]
    rls_rows = [tuple(table.split(".", 1)) for table in RLS_TABLES]
    text = f"""\
-- ST-0304 deterministic no-write PostgreSQL 18.4 domain-schema validation.
-- Execute as the migration owner with TimeZone=UTC and search_path=pg_catalog.
DO $raos_st0304_validation$
DECLARE
    mismatch_count pg_catalog.int8;
    observed_count pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('server_version_num')::pg_catalog.int4 <> 180004 THEN
        RAISE EXCEPTION 'ST0304_SERVER_VERSION_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('TimeZone') <> 'UTC' THEN
        RAISE EXCEPTION 'ST0304_TIMEZONE_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('search_path') <> 'pg_catalog' THEN
        RAISE EXCEPTION 'ST0304_SEARCH_PATH_MISMATCH';
    END IF;
    IF (SELECT version_num FROM public.raos_migration_version) <> '{REVISION}' THEN
        RAISE EXCEPTION 'ST0304_HEAD_MISMATCH';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history
        WHERE revision_id = '{REVISION}'
          AND story_id = 'ST-0304'
          AND direction = 'UPGRADE'
          AND status = 'SUCCEEDED'
          AND source_sha256 = '{revision_sha256}'
          AND runner_version = '{RUNNER_VERSION}'
          AND server_version_num = 180004
    ) THEN
        RAISE EXCEPTION 'ST0304_HISTORY_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(schema_rows)}
    ) AS expected(schema_name, schema_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    WHERE pg_catalog.pg_get_userbyid(namespace.nspowner) = current_user
      AND pg_catalog.obj_description(namespace.oid, 'pg_namespace') =
          expected.schema_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  namespace.nspacl,
                  pg_catalog.acldefault('n', namespace.nspowner)
              )
          ) AS acl
          WHERE acl.grantee <> namespace.nspowner
      );
    IF observed_count <> 6 THEN
        RAISE EXCEPTION 'ST0304_SCHEMA_CATALOG_MISMATCH';
    END IF;

    WITH selected(schema_name) AS (
        VALUES ('portfolio'), ('catalog'), ('evidence'),
               ('editorial'), ('ai'), ('policy')
    ),
    relation_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   relation.relkind, relation.relpersistence,
                   relation.relreplident, relation.relrowsecurity,
                   relation.relforcerowsecurity,
                   COALESCE(
                       pg_catalog.array_to_string(relation.reloptions, E'\\x1d'),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(relation.oid, 'pg_class'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE relation.relkind IN ('r', 'v')
    ),
    column_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   attribute.attnum, attribute.attname,
                   pg_catalog.format_type(
                       attribute.atttypid, attribute.atttypmod
                   ),
                   attribute.attnotnull, attribute.attidentity,
                   attribute.attgenerated, attribute.attisdropped,
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           attribute_default.adbin,
                           attribute_default.adrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       collation_namespace.nspname || '.'
                       || collation_record.collname,
                       '<NULL>'
                   ),
                   attribute.attstorage, attribute.attcompression,
                   attribute.attstattarget,
                   COALESCE(
                       pg_catalog.col_description(
                           relation.oid, attribute.attnum
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = relation.oid
         AND attribute.attnum > 0
        LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
          ON attribute_default.adrelid = relation.oid
         AND attribute_default.adnum = attribute.attnum
        LEFT JOIN pg_catalog.pg_collation AS collation_record
          ON collation_record.oid = attribute.attcollation
        LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
          ON collation_namespace.oid = collation_record.collnamespace
        WHERE relation.relkind = 'r'
    ),
    constraint_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   constraint_record.conname, constraint_record.contype,
                   constraint_record.condeferrable,
                   constraint_record.condeferred,
                   constraint_record.convalidated,
                   constraint_record.connoinherit,
                   constraint_record.confmatchtype,
                   constraint_record.confupdtype,
                   constraint_record.confdeltype,
                   COALESCE(
                       pg_catalog.pg_get_constraintdef(
                           constraint_record.oid, false
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE constraint_record.contype IN ('c', 'f', 'n', 'p', 'u')
    ),
    index_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, table_record.relname,
                   index_record.relname, index_catalog.indisunique,
                   index_catalog.indisprimary,
                   index_catalog.indisexclusion,
                   index_catalog.indimmediate,
                   index_catalog.indisclustered,
                   index_catalog.indisvalid, index_catalog.indisready,
                   index_catalog.indislive, index_catalog.indisreplident,
                   index_catalog.indnullsnotdistinct,
                   index_catalog.indnkeyatts, index_catalog.indnatts,
                   index_catalog.indkey::pg_catalog.text,
                   index_catalog.indcollation::pg_catalog.text,
                   index_catalog.indclass::pg_catalog.text,
                   index_catalog.indoption::pg_catalog.text,
                   pg_catalog.pg_get_indexdef(index_record.oid, 0, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indpred,
                           index_catalog.indrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indexprs,
                           index_catalog.indrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(
                           index_record.oid, 'pg_class'
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_record
          ON index_record.oid = index_catalog.indexrelid
        JOIN pg_catalog.pg_class AS table_record
          ON table_record.oid = index_catalog.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_record.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
    ),
    function_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_function_result(routine.oid),
                   language_record.lanname, routine.provolatile,
                   routine.proisstrict, routine.prosecdef,
                   routine.proleakproof, routine.proparallel,
                   COALESCE(
                       pg_catalog.array_to_string(routine.proconfig, E'\\x1d'),
                       '<NULL>'
                   ),
                   pg_catalog.pg_get_functiondef(routine.oid),
                   COALESCE(
                       pg_catalog.obj_description(routine.oid, 'pg_proc'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_language AS language_record
          ON language_record.oid = routine.prolang
        WHERE routine.prokind = 'f'
    ),
    trigger_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   trigger_record.tgname, trigger_record.tgtype,
                   trigger_record.tgenabled, trigger_record.tgisinternal,
                   routine_namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_triggerdef(trigger_record.oid, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           trigger_record.tgqual,
                           trigger_record.tgrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(
                           trigger_record.oid, 'pg_trigger'
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_trigger AS trigger_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_record.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_proc AS routine
          ON routine.oid = trigger_record.tgfoid
        JOIN pg_catalog.pg_namespace AS routine_namespace
          ON routine_namespace.oid = routine.pronamespace
        WHERE trigger_record.tgisinternal IS FALSE
    ),
    observed(kind, object_count, digest) AS (
        SELECT 'relations', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM relation_rows
        UNION ALL
        SELECT 'columns', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM column_rows
        UNION ALL
        SELECT 'constraints', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM constraint_rows
        UNION ALL
        SELECT 'indexes', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM index_rows
        UNION ALL
        SELECT 'functions', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM function_rows
        UNION ALL
        SELECT 'triggers', pg_catalog.count(*),
               pg_catalog.md5(
                   pg_catalog.string_agg(row_value, E'\\x1e' ORDER BY row_value)
               )
        FROM trigger_rows
    ),
    expected(kind, object_count, digest) AS (
        VALUES
        {_values(expected_digest_rows)}
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    FULL JOIN observed USING (kind)
    WHERE expected.object_count IS DISTINCT FROM observed.object_count
       OR expected.digest IS DISTINCT FROM observed.digest;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0304_PHYSICAL_CATALOG_DIGEST_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(rls_rows)}
    ) AS expected(schema_name, table_name)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    WHERE relation.relrowsecurity IS TRUE
      AND relation.relforcerowsecurity IS TRUE;
    IF observed_count <> 11 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_policy AS policy_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = policy_record.polrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
    ) <> 0 THEN
        RAISE EXCEPTION 'ST0304_RLS_BOUNDARY_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM pg_catalog.pg_constraint AS constraint_record
    WHERE constraint_record.conname = 'fk_ops_job_site_id'
      AND constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
      AND constraint_record.confrelid = 'portfolio.site'::pg_catalog.regclass
      AND constraint_record.contype = 'f'
      AND constraint_record.convalidated IS TRUE
      AND constraint_record.condeferrable IS FALSE
      AND constraint_record.condeferred IS FALSE
      AND constraint_record.confupdtype = 'a'
      AND constraint_record.confdeltype = 'r'
      AND constraint_record.confmatchtype = 's'
      AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false) =
          'FOREIGN KEY (site_id) REFERENCES portfolio.site(id) ON DELETE RESTRICT';
    IF observed_count <> 1 OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'fk_iam_break_glass_record_incident_id'
    ) THEN
        RAISE EXCEPTION 'ST0304_DEFERRED_FOREIGN_KEY_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
                relation.relacl,
                pg_catalog.acldefault('r', relation.relowner)
            )
        ) AS acl
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
          AND relation.relkind IN ('r', 'v')
          AND acl.grantee <> relation.relowner
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(
                routine.proacl,
                pg_catalog.acldefault('f', routine.proowner)
            )
        ) AS acl
        WHERE namespace.nspname = ANY(
            ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
        )
          AND acl.grantee <> routine.proowner
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS default_acl
        LEFT JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = default_acl.defaclnamespace
        WHERE default_acl.defaclnamespace = 0
           OR namespace.nspname = ANY(
                  ARRAY['portfolio','catalog','evidence','editorial','ai','policy']
              )
    ) THEN
        RAISE EXCEPTION 'ST0304_PUBLIC_OR_DEFAULT_ACL_MISMATCH';
    END IF;
END
$raos_st0304_validation$;

SELECT 'PASS'::pg_catalog.text AS status,
       86::pg_catalog.int4 AS tables,
       1141::pg_catalog.int4 AS columns,
       265::pg_catalog.int4 AS scope_foreign_keys,
       11::pg_catalog.int4 AS rls_forced_tables,
       0::pg_catalog.int4 AS rls_policies;
"""
    return text.encode("utf-8")


def _artifact(root: Path, path: Path) -> dict[str, object]:
    content = _secure_read(root, path, "source artifact", 16 * 1024 * 1024)
    return {
        "uri": f"repo://{path.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(
    root: Path,
    contract: Mapping[str, Any],
    outputs: Mapping[Path, bytes],
) -> bytes:
    """Render the complete current-story source and generated hash closure."""

    _require(
        len(CURRENT_SOURCE_ARTIFACT_PATHS) == len(set(CURRENT_SOURCE_ARTIFACT_PATHS)),
        "source artifact inventory contains duplicates",
    )
    source_artifacts = [_artifact(root, path) for path in CURRENT_SOURCE_ARTIFACT_PATHS]
    generated_artifacts = [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": len(outputs[path]),
            "sha256": _sha256(outputs[path]),
        }
        for path in GENERATED_PATHS
        if path != MANIFEST_PATH
    ]
    document = {
        "document": {
            "id": "RAOS-DOMAIN-SCHEMA-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0304",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "canonical_and_upstream_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in PINNED_INPUTS.items()
            ],
            "predecessor_manifest": {
                "story_id": "ST-0303",
                "uri": f"repo://{PREDECESSOR_MANIFEST_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_MANIFEST_SHA256,
            },
            "translation": {
                "source": "POSTGRESQL_18_4_FINAL_PHYSICAL_CATALOG",
                "checkpoint_sql": "PROVENANCE_ONLY_NOT_EXECUTED_OR_CONCATENATED",
                "schema_objects": "GENERATED_FROM_HASH_BOUND_FRAGMENTS",
            },
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "single_transaction": True,
            "maximum_revision_bytes": 256 * 1024,
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "security_boundary": {
            "rls_enabled_and_forced_tables": list(RLS_TABLES),
            "rls_policy_count": 0,
            "deferred_rls_policy_count": 22,
            "public_privileges": "NONE",
            "roles_or_default_privileges_created": False,
        },
        "boundary": {
            **dict(_mapping(contract["boundary"], "boundary")),
            "source_inventory_status": "FINAL_CURRENT_STORY_CLOSURE",
            "future_source_change_requires_regeneration": True,
        },
    }
    return yaml.dump(
        document,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    """Render the complete bundle in memory before any filesystem mutation."""

    validate_source_inputs(root)
    contract = _load_contract(root)
    revision = render_revision(root)
    validation = render_validation_sql(contract, _sha256(revision))
    catalog = render_catalog(root, contract, revision, validation)
    outputs: dict[Path, bytes] = {
        REVISION_PATH: revision,
        CATALOG_PATH: catalog,
        VALIDATION_PATH: validation,
    }
    outputs[MANIFEST_PATH] = render_manifest(root, contract, outputs)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output order differs")
    return outputs


@dataclass(slots=True)
class _StagedOutput:
    relative: Path
    descriptors: list[int]
    parent_descriptor: int
    temporary_name: str
    previous_content: bytes | None
    previous_mode: int | None
    previous_identity: tuple[int, int, int, int, int, int] | None
    committed: bool = False


def _metadata_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_descriptor(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        _require(written > 0, "generated artifact short write")
        view = view[written:]


def _stage_output(
    root: Path,
    relative: Path,
    content: bytes,
    ordinal: int,
) -> _StagedOutput:
    directory_flag, nofollow_flag, nonblock_flag = _required_open_flags()
    _require(
        not relative.is_absolute()
        and bool(relative.parts)
        and all(part not in {"", ".", ".."} for part in relative.parts),
        "unsafe generated path",
    )
    root_metadata = root.lstat()
    _require(
        stat.S_ISDIR(root_metadata.st_mode) and not stat.S_ISLNK(root_metadata.st_mode),
        "generated root must be a real directory",
    )
    directory_flags = os.O_RDONLY | directory_flag | nofollow_flag
    descriptors: list[int] = []
    descriptor = os.open(root, directory_flags)
    descriptors.append(descriptor)
    temporary_name = ""
    try:
        for part in relative.parent.parts:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(part, directory_flags, dir_fd=descriptor)
            descriptor = child
            descriptors.append(descriptor)

        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        previous_content: bytes | None
        previous_mode: int | None
        previous_identity: tuple[int, int, int, int, int, int] | None
        if target_metadata is None:
            previous_content = None
            previous_mode = None
            previous_identity = None
        else:
            _require(
                stat.S_ISREG(target_metadata.st_mode),
                "generated target must be a regular non-symlink file",
            )
            _require(
                stat.S_IMODE(target_metadata.st_mode) == 0o644,
                "generated target mode differs from 0644",
            )
            previous_descriptor = os.open(
                relative.name,
                os.O_RDONLY | nofollow_flag | nonblock_flag,
                dir_fd=descriptor,
            )
            try:
                previous_content = _read_descriptor(previous_descriptor)
                opened_metadata = os.fstat(previous_descriptor)
            finally:
                os.close(previous_descriptor)
            _require(
                _metadata_identity(opened_metadata)
                == _metadata_identity(target_metadata),
                "generated target changed while staging",
            )
            previous_mode = stat.S_IMODE(target_metadata.st_mode)
            previous_identity = _metadata_identity(target_metadata)

        temporary_name = f".{relative.name}.st0304-{os.getpid()}-{ordinal}"
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow_flag,
            0o644,
            dir_fd=descriptor,
        )
        try:
            _write_descriptor(temporary_descriptor, content)
            os.fchmod(temporary_descriptor, 0o644)
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        return _StagedOutput(
            relative=relative,
            descriptors=descriptors,
            parent_descriptor=descriptor,
            temporary_name=temporary_name,
            previous_content=previous_content,
            previous_mode=previous_mode,
            previous_identity=previous_identity,
        )
    except BaseException:
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
        raise


def _verify_stage_target_unchanged(stage: _StagedOutput) -> None:
    try:
        metadata = os.stat(
            stage.relative.name,
            dir_fd=stage.parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        identity = None
    else:
        identity = _metadata_identity(metadata)
    _require(
        identity == stage.previous_identity, "generated target changed before commit"
    )


def _restore_output(stage: _StagedOutput, ordinal: int) -> None:
    _directory_flag, nofollow_flag, _nonblock_flag = _required_open_flags()
    target_name = stage.relative.name
    if stage.previous_content is None:
        try:
            os.unlink(target_name, dir_fd=stage.parent_descriptor)
        except FileNotFoundError:
            pass
        os.fsync(stage.parent_descriptor)
        return
    temporary_name = f".{target_name}.st0304-rollback-{os.getpid()}-{ordinal}"
    descriptor = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow_flag,
        stage.previous_mode or 0o644,
        dir_fd=stage.parent_descriptor,
    )
    try:
        _write_descriptor(descriptor, stage.previous_content)
        os.fchmod(descriptor, stage.previous_mode or 0o644)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(
            temporary_name,
            target_name,
            src_dir_fd=stage.parent_descriptor,
            dst_dir_fd=stage.parent_descriptor,
        )
        temporary_name = ""
        os.fsync(stage.parent_descriptor)
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=stage.parent_descriptor)
            except FileNotFoundError:
                pass


def install_generated(root: Path = REPO_ROOT) -> None:
    """Stage the entire bundle before committing, with reverse rollback."""

    outputs = render_outputs(root)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output inventory differs")
    staged: list[_StagedOutput] = []
    try:
        for ordinal, path in enumerate(GENERATED_PATHS):
            staged.append(_stage_output(root, path, outputs[path], ordinal))
        try:
            for stage in staged:
                _verify_stage_target_unchanged(stage)
                os.replace(
                    stage.temporary_name,
                    stage.relative.name,
                    src_dir_fd=stage.parent_descriptor,
                    dst_dir_fd=stage.parent_descriptor,
                )
                stage.temporary_name = ""
                stage.committed = True
                os.fsync(stage.parent_descriptor)
        except BaseException as install_error:
            rollback_errors: list[BaseException] = []
            for ordinal, stage in enumerate(reversed(staged)):
                if not stage.committed:
                    continue
                try:
                    _restore_output(stage, ordinal)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise RuntimeError(
                    "generated bundle rollback incomplete"
                ) from install_error
            raise
    finally:
        for stage in staged:
            if stage.temporary_name:
                try:
                    os.unlink(stage.temporary_name, dir_fd=stage.parent_descriptor)
                except FileNotFoundError:
                    pass
            for opened in reversed(stage.descriptors):
                try:
                    os.close(opened)
                except OSError:
                    pass


def check_generated(root: Path = REPO_ROOT) -> None:
    """Compare every committed artifact to a freshly rendered byte snapshot."""

    expected = render_outputs(root)
    for path in GENERATED_PATHS:
        observed = _secure_read(root, path, "generated artifact", 4 * 1024 * 1024)
        metadata = (root / path).lstat()
        _require(
            stat.S_IMODE(metadata.st_mode) == 0o644,
            "generated artifact mode differs from 0644",
        )
        _require(observed == expected[path], "generated artifact drift")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify generated artifacts byte-for-byte without writing",
    )
    mode.add_argument(
        "--source-check",
        action="store_true",
        help="validate only frozen source inputs without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.source_check:
            summary = validate_source_inputs()
            mode = "source-check"
        elif arguments.check:
            check_generated()
            summary = {"generated_artifacts": len(GENERATED_PATHS)}
            mode = "check"
        else:
            install_generated()
            summary = {"generated_artifacts": len(GENERATED_PATHS)}
            mode = "install"
    except (OSError, RuntimeError, UnicodeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"mode": mode, "status": "PASS", "story_id": "ST-0304", **summary},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
