#!/usr/bin/env python3
"""Validate and generate the ST-0308 local persistence runtime slice.

The executable matrices are the only semantic input.  This owner never opens a
database connection and never resolves credentials.  It validates the complete
physical/matrix inventory, then emits only the explicitly selected OPS reference
slice and its provenance metadata.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from types import MappingProxyType
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import TagToken

from scripts.raos_build_core import input_hash_required


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
GENERATOR_PATH: Final = Path("scripts/build_st0308_persistence.py")
RUNTIME_CONTRACT_PATH: Final = Path(
    "changes/st-0308/contracts/persistence-runtime.v2.yaml"
)
OPS_SLICE_PATH: Final = Path(
    "changes/st-0308/contracts/persistence/ops-reference-slice.v1.yaml"
)
ST0303_CATALOG_PATH: Final = Path("changes/st-0303/generated/iam-ops-catalog.v1.json")
ST0304_CATALOG_PATH: Final = Path("changes/st-0304/generated/domain-catalog.v1.json")
EVENT_SCHEMA_ROOT: Final = Path("contracts/raos-v0.4/contracts/schemas/events")
OUTPUT_METADATA_PATH: Final = Path(
    "changes/st-0308/generated/persistence-runtime.ops-reference.v1.json"
)
OUTPUT_CATALOG_IR_PATH: Final = Path(
    "changes/st-0308/generated/persistence-catalog-ir.v1.json"
)
OUTPUT_PACKAGE_PATH: Final = Path(
    "python/raos/adapters/persistence/sqlalchemy/generated/__init__.py"
)
OUTPUT_CODE_PATH: Final = Path(
    "python/raos/adapters/persistence/sqlalchemy/generated/ops_reference.py"
)
OUTPUT_IDENTITY_PATH: Final = Path(
    "python/raos/adapters/persistence/sqlalchemy/generated/identity_contract.py"
)
OUTPUT_FULL_CATALOG_PATH: Final = Path(
    "python/raos/adapters/persistence/sqlalchemy/generated/catalog.py"
)
OUTPUT_PHYSICAL_CONSTRAINTS_PATH: Final = Path(
    "python/raos/adapters/persistence/sqlalchemy/generated/physical_constraints.py"
)
OWNER_OUTPUT_PATHS: Final = (
    OUTPUT_METADATA_PATH,
    OUTPUT_CATALOG_IR_PATH,
    OUTPUT_PACKAGE_PATH,
    OUTPUT_CODE_PATH,
    OUTPUT_IDENTITY_PATH,
    OUTPUT_FULL_CATALOG_PATH,
    OUTPUT_PHYSICAL_CONSTRAINTS_PATH,
)
OWNER_GENERATED_DIRECTORY_ALLOWLISTS: Final = MappingProxyType(
    {
        Path("changes/st-0308/generated"): (
            "persistence-boundary.reference-plan.v1.json",
            "persistence-catalog-ir.v1.json",
            "persistence-runtime.ops-reference.v1.json",
        ),
        Path("python/raos/adapters/persistence/sqlalchemy/generated"): (
            "__init__.py",
            "catalog.py",
            "identity_contract.py",
            "ops_reference.py",
            "physical_constraints.py",
        ),
    }
)
MATRIX_KEYS: Final = (
    "repository_surface",
    "concurrency",
    "state_cas",
    "uow_surface",
    "domain_mapper",
    "event_emission",
    "idempotency",
    "identity",
)
SLICE_RELATIONS: Final = (
    "ops.object_artifact",
    "ops.runtime_setting_version",
    "ops.audit_event",
    "ops.outbox_event",
    "ops.idempotency_record",
)
RELATION_CONSTANTS: Final = MappingProxyType(
    {
        "ops.object_artifact": "OBJECT_ARTIFACT",
        "ops.runtime_setting_version": "RUNTIME_SETTING_VERSION",
        "ops.audit_event": "AUDIT_EVENT",
        "ops.outbox_event": "OUTBOX_EVENT",
        "ops.idempotency_record": "IDEMPOTENCY_RECORD",
    }
)
MAX_INPUT_BYTES: Final = 8 * 1024 * 1024
MAX_YAML_CONTAINERS: Final = 200_000
MAX_YAML_DEPTH: Final = 128
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
CREATE_TABLE_PATTERN: Final = re.compile(
    r'CREATE TABLE "([^"]+)"\."([^"]+)" \(\n', re.MULTILINE
)
PHYSICAL_OBJECT_HEADER: Final = re.compile(
    r"^--\n-- Name: (.*?); Type: (.*?); Schema: (.*?); Owner: -\n--\n\n",
    re.DOTALL,
)
EXPECTED_RUNTIME_DECISIONS: Final = MappingProxyType(
    {
        "ports": "AGGREGATE_SPECIFIC_PROTOCOLS_NO_GENERIC_CRUD_OR_RAW_MAPPING",
        "mapping": "GENERATED_ADAPTER_OWNED_SQLALCHEMY_METADATA_AND_EXPLICIT_MAPPERS_NO_REFLECTION_OR_LAZY_LOAD",
        "transaction": "SYNC_OUTER_OR_JOINED_UOW_ONLY_OUTER_COMMIT_ROLLBACK_NO_SAVEPOINT_OR_BLIND_RETRY",
        "atomicity": "BUSINESS_AUDIT_OUTBOX_IDEMPOTENCY_ONE_TRANSACTION",
        "events": "CLOSED_18_EVENT_REGISTRY_PENDING_ACKNOWLEDGE_RESTORE_ON_KNOWN_ROLLBACK",
        "idempotency": "EXACT_CLAIM_LOOKUP_REPLAY_IN_PROGRESS_MISMATCH_EXPIRY_COMPLETION_CAS",
        "identity": "FACTORY_OWNS_EXPECTED_PROFILE_AND_CHECKED_OUT_EFFECTIVE_ROLE_IS_VERIFIED_BEFORE_SESSION_BEGIN",
        "deterministic_ids_and_bytes": "REQUIRED",
        "cross_module_write": "REJECTED_BEFORE_DML",
    }
)
EXPECTED_RUNTIME_BOUNDARY: Final = MappingProxyType(
    {
        "external_io_inside_transaction": "FORBIDDEN",
        "secret_or_credential_resolution": "FORBIDDEN",
        "live_connection": "NOT_EXECUTED",
        "migrations_roles_or_grants": "FORBIDDEN",
        "dispatcher_lease_retry_inbox_dlq": "ST-1404",
        "publication": "FORBIDDEN",
        "staging": "NOT_EXECUTED",
        "release": "FORBIDDEN",
        "production": "FORBIDDEN",
    }
)
EXPECTED_EXECUTION_CONTROL: Final = MappingProxyType(
    {
        "visibility": "ADAPTER_PRIVATE",
        "factory_configuration": "IMMUTABLE_BUDGET_AND_CLOCK_COMPOSITION",
        "public_factory_signature_change": "FORBIDDEN",
        "persistence_context_field": "FORBIDDEN",
        "caller_generic_callback": "FORBIDDEN",
        "outer_state": "ONE_MUTABLE_STATE_OWNED_BY_EACH_OUTER_UOW",
        "joined_state": "EXACT_SAME_OBJECT_IDENTITY_AS_OUTER",
        "time_source": "MONOTONIC_NOT_WALL_CLOCK",
        "lifecycle_checks": [
            "PRE_CHECKOUT",
            "POST_CHECKOUT",
            "POST_IDENTITY",
            "PRE_SESSION_BEGIN",
            "PRE_EXPOSURE",
            "PRE_REPOSITORY_QUERY_OR_DML",
            "PRE_FLUSH",
            "PRE_COMMIT",
            "POST_KNOWN_DRIVER_RETURN",
        ],
        "rejection_precedence": "CANCELLED_THEN_DEADLINE_EXCEEDED",
        "known_precommit_rejection": "ROLLBACK_AND_RESTORE",
        "indeterminate_commit": ("UNKNOWN_COMMIT_NEVER_CANCELLED_OR_DEADLINE_EXCEEDED"),
    }
)
EXPECTED_IDENTITY_RUNTIME: Final = MappingProxyType(
    {
        "query_owner": "ST0308_ADAPTER",
        "semantic_anchor": {
            "path": "changes/st-0306/contracts/database-roles-grants.v1.yaml",
            "sha256": (
                "93f03ff2a762ff0d0b950b06a5b7416687ce20e44f7e7b7f6ea2a7ed2b873206"
            ),
            "authority": "CANDIDATE_IDENTITY_EVIDENCE_ONLY",
        },
        "migration_validation_sql_reuse": "FORBIDDEN",
        "selected_relation_inventory": ("EXACT_103_TABLES_AND_CATALOG_SAFE_OFFER_VIEW"),
        "query_result_fields": [
            "login_role",
            "inherited_groups",
            "is_superuser",
            "bypass_rls",
            "create_role",
            "create_database",
            "owns_selected_relation",
        ],
        "inherited_groups": (
            "ALL_EFFECTIVE_NON_LOGIN_GROUPS_EXACT_MEMBERSHIP_REQUIRED"
        ),
        "profile_binding": "FACTORY_PRIVATE_EXPECTED_PROFILE",
        "execution_stage": "CHECKED_OUT_CONNECTION_BEFORE_SESSION_BEGIN",
    }
)
EXPECTED_RUNTIME_ROOT_KEYS: Final = (
    "document",
    "story",
    "sources",
    "physical_fragments",
    "executable_matrices",
    "representative_slices",
    "inventory",
    "runtime_decisions",
    "execution_control",
    "identity_runtime",
    "boundary",
    "two_way_gates",
)
EXPECTED_RUNTIME_STORY: Final = MappingProxyType(
    {
        "dependencies": ["ST-0304", "ST-0105"],
        "affected_inputs_not_dependencies": ["ST-0107", "ST-0301", "ST-0306"],
        "deliverables": [
            "aggregate_specific_repositories",
            "transaction_boundary",
        ],
        "acceptance": ["cross_module_write_rules"],
        "open_decisions": [],
    }
)
EXPECTED_RUNTIME_SOURCE_PATHS: Final = (
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
    "changes/st-0105/README.md",
    "changes/st-0105/manifest.json",
    "changes/st-0303/generated/iam-ops-catalog.v1.json",
    "changes/st-0304/contracts/domain-schema.v1.yaml",
    "changes/st-0304/generated/domain-catalog.v1.json",
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md",
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md",
    "changes/st-0306/contracts/database-roles-grants.v1.yaml",
)
EXPECTED_PHYSICAL_FRAGMENT_PATHS: Final = tuple(
    f"changes/st-0304/contracts/physical/{index:02d}-domain-physical.sql"
    for index in range(1, 12)
)
EXPECTED_MATRIX_PATHS: Final = MappingProxyType(
    {
        "repository_surface": (
            "changes/st-0308/contracts/persistence/repository-surface-matrix.v1.yaml"
        ),
        "concurrency": (
            "changes/st-0308/contracts/persistence/concurrency-matrix.v1.yaml"
        ),
        "state_cas": ("changes/st-0308/contracts/persistence/state-cas-matrix.v1.yaml"),
        "uow_surface": (
            "changes/st-0308/contracts/persistence/uow-surface-matrix.v1.yaml"
        ),
        "domain_mapper": (
            "changes/st-0308/contracts/persistence/domain-mapper-matrix.v1.yaml"
        ),
        "event_emission": (
            "changes/st-0308/contracts/persistence/event-emission-matrix.v1.yaml"
        ),
        "idempotency": (
            "changes/st-0308/contracts/persistence/idempotency-matrix.v1.yaml"
        ),
        "identity": ("changes/st-0308/contracts/persistence/identity-matrix.v1.yaml"),
    }
)
EXPECTED_RUNTIME_SCHEMAS: Final = (
    "ops",
    "iam",
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
)
EXPECTED_BOUND_INPUT_SHA256: Final = MappingProxyType(
    {
        "changes/st-0303/generated/iam-ops-catalog.v1.json": (
            "0cab8decf1a9a874248ef16a5b1bfd01c19d1babbf45bb0f73eb42b89913720a"
        ),
        "changes/st-0304/generated/domain-catalog.v1.json": (
            "41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208"
        ),
        "changes/st-0306/contracts/database-roles-grants.v1.yaml": (
            "93f03ff2a762ff0d0b950b06a5b7416687ce20e44f7e7b7f6ea2a7ed2b873206"
        ),
        "changes/st-0304/contracts/physical/01-domain-physical.sql": (
            "b2f937ae00d526a886e5e875e095e247702f4bd7831a3164e2eda93423d7fdb8"
        ),
        "changes/st-0304/contracts/physical/02-domain-physical.sql": (
            "b685751e4e2743ea6c7202e8ce726486ac152e46987bb832e6777e61b987aafc"
        ),
        "changes/st-0304/contracts/physical/03-domain-physical.sql": (
            "f95ad5a2fd349177b01f97237d0d9a3fb598b2781828e9531a04c3c42b811b45"
        ),
        "changes/st-0304/contracts/physical/04-domain-physical.sql": (
            "4a3c029980e8c27957fac2291e7b0a8efb81eaf1faa74dee4e757b0836e7ba30"
        ),
        "changes/st-0304/contracts/physical/05-domain-physical.sql": (
            "c78e946f9be015d461350f347f125a2cf8f01b267647a8685158af207cefc0ec"
        ),
        "changes/st-0304/contracts/physical/06-domain-physical.sql": (
            "cc520254390d68fdc68d54c01ed6b95e031ea422814e5be924849ec61636904d"
        ),
        "changes/st-0304/contracts/physical/07-domain-physical.sql": (
            "739cc2ecae7e49702da5e36be6e37eaebaa7a535be4a623c79dee86926212870"
        ),
        "changes/st-0304/contracts/physical/08-domain-physical.sql": (
            "eafb7b89c6fa08bd74a8c13d89aa19aea3a946e739720a8cff9e6faa3ca2bfc4"
        ),
        "changes/st-0304/contracts/physical/09-domain-physical.sql": (
            "6cebf09249f027662557038f8367bdc586030197911046be242543cd43502ae5"
        ),
        "changes/st-0304/contracts/physical/10-domain-physical.sql": (
            "3d806436b7ed91f25e0396e15b914dda7258b743589ec4dc6c3f4272c9fcb38d"
        ),
        "changes/st-0304/contracts/physical/11-domain-physical.sql": (
            "947e480157a52b0d926461a4d40a7409e92e6e50482c216d394953a462d8cd09"
        ),
        "changes/st-0308/contracts/persistence/concurrency-matrix.v1.yaml": (
            "66cb474d428703e83b7b84744c4f843463b0a040714b907e00137438f5ba08ab"
        ),
        "changes/st-0308/contracts/persistence/domain-mapper-matrix.v1.yaml": (
            "8b2499f99faa223fbc5b6329bd0f0e441441e89b45d507b6bbb0ffbce470e872"
        ),
        "changes/st-0308/contracts/persistence/event-emission-matrix.v1.yaml": (
            "3c4f8e429824849b9219faefb2867dd8444828562d0d0a1d9c79bfa2cc511ad0"
        ),
        "changes/st-0308/contracts/persistence/idempotency-matrix.v1.yaml": (
            "1645b6b67d8ab6ae01520094cbc7f14405f2545c41d019ecb98ea48412c39e1b"
        ),
        "changes/st-0308/contracts/persistence/identity-matrix.v1.yaml": (
            "aa009ab2423069f782621d6f7e4cb4c4fa57185d03ad3195ad5df29c75360d0b"
        ),
        "changes/st-0308/contracts/persistence/repository-surface-matrix.v1.yaml": (
            "0dcd8edabe662bb94dc38960b372dfabf1afc8e83f74e3acc4757049fda6f1f0"
        ),
        "changes/st-0308/contracts/persistence/state-cas-matrix.v1.yaml": (
            "f865a30c2c000dfd9ca6f2f43d0be7c5cc3883077cfd41f3dcc4c340d03c94d1"
        ),
        "changes/st-0308/contracts/persistence/uow-surface-matrix.v1.yaml": (
            "2e298605a9679b593244d78b49a6e4f331d8927363d3513d8f7aa6527c10bdc0"
        ),
    }
)
EXPECTED_ST0304_CATALOG_ROOT_KEYS: Final = (
    "baseline_metadata",
    "boundary",
    "document",
    "foreign_key_boundary",
    "inventory",
    "object_inventory",
    "physical_fragments",
    "postgresql_18_4_catalog_digests",
    "revision",
    "rls_boundary",
    "source_contract",
    "validation",
)
EXPECTED_ST0304_OBJECT_COUNT: Final = 1842
EXPECTED_ST0304_RELATION_OBJECT_COUNT: Final = 885
EXPECTED_ST0304_RELATION_OBJECT_TYPE_COUNTS: Final = MappingProxyType(
    {
        "TABLE": 86,
        "VIEW": 1,
        "CONSTRAINT": 179,
        "FK CONSTRAINT": 264,
        "INDEX": 274,
        "TRIGGER": 81,
    }
)
EXPECTED_DOMAIN_MAPPER_ROOT_KEYS: Final = (
    "document",
    "canonical_serialization",
    "physical_inputs",
    "layout",
    "scalar_bindings",
    "relations",
    "cardinality",
    "row_rules",
    "two_way_gate",
    "closed_enum_bindings",
    "enum_member_policy",
)
EXPECTED_RELATION_KEYS: Final = (
    "relation",
    "physical_source",
    "treatment",
    "repository_owner",
    "domain_path",
    "domain_type",
    "domain_kind",
    "physical_columns",
    "physical_columns_sha256",
    "primary_key",
    "identity",
    "json_contracts",
    "physical_check_constraints",
    "write_pattern",
    "child_ownership",
    "mapper",
    "corruption_policy",
    "relation_contract_sha256",
)
EXPECTED_MAPPER_KEYS: Final = (
    "path",
    "from_row",
    "to_row",
    "signature",
    "input_parameters",
    "output",
)
EXPECTED_MAPPER_SIGNATURE: Final = (
    "keyword-only exact typed scalar fields; no Row, Mapping, dict, ORM instance, "
    "generated binding, Result, Session, or provider value"
)
EXPECTED_REPOSITORY_OWNER_KEYS: Final = ("module", "uow_property", "protocol")
EXPECTED_PHYSICAL_COLUMN_KEYS: Final = (
    "ordinal",
    "physical_column",
    "physical_sql_type",
    "nullable",
    "server_default",
    "domain_field",
    "domain_type",
    "domain_definition_kind",
    "domain_definition_path",
    "corruption_behavior",
)
EXPECTED_IDENTITY_KEYS: Final = ("type", "columns")
EXPECTED_JSON_CONTRACT_KEYS: Final = (
    "physical_column",
    "domain_wrapper",
    "wrapper_path",
    "root",
    "additional_invariants",
    "corruption_behavior",
)
EXPECTED_CHECK_CONSTRAINT_KEYS: Final = ("name", "expression")
EXPECTED_CHILD_OWNERSHIP_KEYS: Final = ("root_relation", "mode")
EXPECTED_CORRUPTION_POLICY: Final = MappingProxyType(
    {
        "error_code": "STORAGE_CORRUPTION",
        "reject_exact_column_set_mismatch": True,
        "reject_child_or_owner_mismatch": True,
        "raw_value_sql_driver_error_or_cause_disclosure": "FORBIDDEN",
        "normalization_or_defaulting_of_bad_storage": "FORBIDDEN",
    }
)
EXPECTED_TWO_WAY_GATES: Final = (
    "physical inventory to Domain mapper matrix to generated SQLAlchemy metadata",
    "repository relation/method ownership to generated Protocol and concrete adapter surfaces",
    "lock/state concurrency matrices to generated DML predicates and focused negative tests",
    "UoW matrix to generated Protocols concrete UoWs and API/worker composition",
    "event matrix to module event classes registry schemas and Outbox validation",
    "idempotency matrix to the shared result unions and exact generated claim replacement completion SQL",
    "identity matrix to effective-role query verification and begin-before-identity negative tests",
    "manifest v2 records semantic inputs, owner identity/version, and generated output integrity",
)


class PersistenceBuildError(RuntimeError):
    """A closed, sanitized owner-generator failure."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _PhysicalObject:
    """One hash-bound ST-0304 pg_dump object with fragment provenance."""

    name: str
    object_type: str
    schema: str
    sql: str
    sha256: str
    fragment_path: str
    fragment_sha256: str


@dataclass(frozen=True, slots=True)
class _SqlToken:
    """One closed lexeme in the supported PostgreSQL CHECK-expression grammar."""

    kind: str
    value: str
    quoted: bool = False


_CHECK_MULTI_OPERATORS: Final = ("->>", "::", ">=", "<=", "<>", "?&", "&&", "->")
_CHECK_SINGLE_SYMBOLS: Final = frozenset("()[],.+-*/=<>~")
_CHECK_FUNCTION_ARITY: Final = MappingProxyType(
    {
        "ai.canonical_metric_unit": (1, 1),
        "array_position": (2, 2),
        "btrim": (1, 1),
        "cardinality": (1, 1),
        "coalesce": (1, None),
        "jsonb_typeof": (1, 1),
        "length": (1, 1),
        "num_nonnulls": (1, None),
        "pg_catalog.jsonb_typeof": (1, 1),
    }
)
_CHECK_CAST_TYPES: Final = frozenset({"integer", "jsonb", "numeric", "text"})


def _tokenize_check(expression: str) -> tuple[_SqlToken, ...]:
    """Tokenize only the hash-bound PostgreSQL expression subset we execute."""

    tokens: list[_SqlToken] = []
    index = 0
    while index < len(expression):
        character = expression[index]
        if character.isspace():
            index += 1
            continue
        if character == '"':
            index += 1
            value: list[str] = []
            while index < len(expression):
                if expression[index] != '"':
                    value.append(expression[index])
                    index += 1
                    continue
                if index + 1 < len(expression) and expression[index + 1] == '"':
                    value.append('"')
                    index += 2
                    continue
                index += 1
                break
            else:
                _fail("CHECK_EXPRESSION_TOKEN_INVALID")
            if not value:
                _fail("CHECK_EXPRESSION_TOKEN_INVALID")
            tokens.append(_SqlToken("IDENT", "".join(value), True))
            continue
        if character == "'":
            index += 1
            value = []
            while index < len(expression):
                if expression[index] != "'":
                    value.append(expression[index])
                    index += 1
                    continue
                if index + 1 < len(expression) and expression[index + 1] == "'":
                    value.append("'")
                    index += 2
                    continue
                index += 1
                break
            else:
                _fail("CHECK_EXPRESSION_TOKEN_INVALID")
            tokens.append(_SqlToken("STRING", "".join(value)))
            continue
        operator = next(
            (
                value
                for value in _CHECK_MULTI_OPERATORS
                if expression.startswith(value, index)
            ),
            None,
        )
        if operator is not None:
            tokens.append(_SqlToken("SYMBOL", operator))
            index += len(operator)
            continue
        if character in _CHECK_SINGLE_SYMBOLS:
            tokens.append(_SqlToken("SYMBOL", character))
            index += 1
            continue
        if character.isdigit():
            end = index + 1
            while end < len(expression) and expression[end].isdigit():
                end += 1
            if end < len(expression) and expression[end] == ".":
                end += 1
                fractional_start = end
                while end < len(expression) and expression[end].isdigit():
                    end += 1
                if end == fractional_start:
                    _fail("CHECK_EXPRESSION_TOKEN_INVALID")
            tokens.append(_SqlToken("NUMBER", expression[index:end]))
            index = end
            continue
        if character.isalpha() or character == "_":
            end = index + 1
            while end < len(expression) and (
                expression[end].isalnum() or expression[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(_SqlToken("IDENT", expression[index:end]))
            index = end
            continue
        _fail("CHECK_EXPRESSION_TOKEN_INVALID")
    return (*tokens, _SqlToken("EOF", ""))


class _CheckExpressionParser:
    """Compile a closed PostgreSQL CHECK subset to an inert immutable AST."""

    __slots__ = ("_columns", "_index", "_referenced", "_tokens")

    def __init__(self, expression: str, columns: frozenset[str]) -> None:
        self._tokens = _tokenize_check(expression)
        self._index = 0
        self._columns = columns
        self._referenced: set[str] = set()

    def parse(self) -> tuple[object, ...]:
        result = self._parse_or()
        if self._peek().kind != "EOF" or not self._referenced.issubset(self._columns):
            _fail("CHECK_EXPRESSION_UNSUPPORTED")
        return result

    def _peek(self) -> _SqlToken:
        return self._tokens[self._index]

    def _take(self) -> _SqlToken:
        sql_lexeme = self._peek()
        self._index += 1
        return sql_lexeme

    def _accept_symbol(self, value: str) -> bool:
        sql_lexeme = self._peek()
        if sql_lexeme.kind == "SYMBOL" and sql_lexeme.value == value:
            self._index += 1
            return True
        return False

    def _expect_symbol(self, value: str) -> None:
        if not self._accept_symbol(value):
            _fail("CHECK_EXPRESSION_UNSUPPORTED")

    def _accept_word(self, value: str) -> bool:
        sql_lexeme = self._peek()
        if (
            sql_lexeme.kind == "IDENT"
            and not sql_lexeme.quoted
            and sql_lexeme.value.upper() == value
        ):
            self._index += 1
            return True
        return False

    def _expect_word(self, value: str) -> None:
        if not self._accept_word(value):
            _fail("CHECK_EXPRESSION_UNSUPPORTED")

    def _parse_or(self) -> tuple[object, ...]:
        value = self._parse_and()
        while self._accept_word("OR"):
            value = ("binary", "or", value, self._parse_and())
        return value

    def _parse_and(self) -> tuple[object, ...]:
        value = self._parse_not()
        while self._accept_word("AND"):
            value = ("binary", "and", value, self._parse_not())
        return value

    def _parse_not(self) -> tuple[object, ...]:
        if self._accept_word("NOT"):
            return ("unary", "not", self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> tuple[object, ...]:
        value = self._parse_additive()
        if self._accept_word("IS"):
            negated = self._accept_word("NOT")
            if self._accept_word("NULL"):
                return ("is_null", negated, value)
            if self._accept_word("DISTINCT"):
                self._expect_word("FROM")
                return ("is_distinct", negated, value, self._parse_additive())
            _fail("CHECK_EXPRESSION_UNSUPPORTED")
        negated = self._accept_word("NOT")
        if self._accept_word("BETWEEN"):
            lower = self._parse_additive()
            self._expect_word("AND")
            result: tuple[object, ...] = (
                "between",
                value,
                lower,
                self._parse_additive(),
            )
            return ("unary", "not", result) if negated else result
        if self._accept_word("IN"):
            self._expect_symbol("(")
            members: list[tuple[object, ...]] = []
            if not self._accept_symbol(")"):
                members.append(self._parse_or())
                while self._accept_symbol(","):
                    members.append(self._parse_or())
                self._expect_symbol(")")
            if not members:
                _fail("CHECK_EXPRESSION_UNSUPPORTED")
            result = ("in", value, tuple(members))
            return ("unary", "not", result) if negated else result
        if negated:
            _fail("CHECK_EXPRESSION_UNSUPPORTED")
        sql_lexeme = self._peek()
        if sql_lexeme.kind != "SYMBOL" or sql_lexeme.value not in {
            "=",
            "<>",
            ">",
            ">=",
            "<",
            "<=",
            "~",
        }:
            return value
        operator = self._take().value
        if self._accept_word("ANY") or self._accept_word("ALL"):
            quantifier = self._tokens[self._index - 1].value.upper()
            self._expect_symbol("(")
            quantified_members = self._parse_or()
            self._expect_symbol(")")
            return ("quantified", operator, quantifier, value, quantified_members)
        return ("binary", operator, value, self._parse_additive())

    def _parse_additive(self) -> tuple[object, ...]:
        value = self._parse_multiplicative()
        while True:
            sql_lexeme = self._peek()
            if sql_lexeme.kind != "SYMBOL" or sql_lexeme.value not in {
                "+",
                "-",
                "->",
                "->>",
                "?&",
                "&&",
            }:
                return value
            operator = self._take().value
            value = ("binary", operator, value, self._parse_multiplicative())

    def _parse_multiplicative(self) -> tuple[object, ...]:
        value = self._parse_unary_numeric()
        while True:
            sql_lexeme = self._peek()
            if sql_lexeme.kind != "SYMBOL" or sql_lexeme.value not in {"*", "/"}:
                return value
            operator = self._take().value
            value = ("binary", operator, value, self._parse_unary_numeric())

    def _parse_unary_numeric(self) -> tuple[object, ...]:
        if self._accept_symbol("+"):
            return ("unary", "+", self._parse_unary_numeric())
        if self._accept_symbol("-"):
            return ("unary", "-", self._parse_unary_numeric())
        return self._parse_postfix()

    def _parse_postfix(self) -> tuple[object, ...]:
        value = self._parse_primary()
        while self._accept_symbol("::"):
            cast_type = self._take()
            if cast_type.kind != "IDENT":
                _fail("CHECK_EXPRESSION_UNSUPPORTED")
            normalized = cast_type.value.lower()
            if normalized not in _CHECK_CAST_TYPES:
                _fail("CHECK_EXPRESSION_UNSUPPORTED")
            value = ("cast", normalized, value)
        return value

    def _parse_primary(self) -> tuple[object, ...]:
        if self._accept_symbol("("):
            value = self._parse_or()
            self._expect_symbol(")")
            return value
        if self._accept_word("ARRAY"):
            self._expect_symbol("[")
            values: list[tuple[object, ...]] = []
            if not self._accept_symbol("]"):
                values.append(self._parse_or())
                while self._accept_symbol(","):
                    values.append(self._parse_or())
                self._expect_symbol("]")
            return ("array", tuple(values))
        if self._accept_word("NULL"):
            return ("null",)
        if self._accept_word("TRUE"):
            return ("boolean", True)
        if self._accept_word("FALSE"):
            return ("boolean", False)
        sql_lexeme = self._take()
        if sql_lexeme.kind == "STRING":
            return ("string", sql_lexeme.value)
        if sql_lexeme.kind == "NUMBER":
            return ("number", sql_lexeme.value)
        if sql_lexeme.kind != "IDENT":
            _fail("CHECK_EXPRESSION_UNSUPPORTED")
        parts = [sql_lexeme.value]
        while self._accept_symbol("."):
            part = self._take()
            if part.kind != "IDENT":
                _fail("CHECK_EXPRESSION_UNSUPPORTED")
            parts.append(part.value)
        name = ".".join(parts)
        if self._accept_symbol("("):
            arguments: list[tuple[object, ...]] = []
            if not self._accept_symbol(")"):
                arguments.append(self._parse_or())
                while self._accept_symbol(","):
                    arguments.append(self._parse_or())
                self._expect_symbol(")")
            normalized = name.lower()
            arity = _CHECK_FUNCTION_ARITY.get(normalized)
            if (
                arity is None
                or len(arguments) < arity[0]
                or (arity[1] is not None and len(arguments) > arity[1])
            ):
                _fail("CHECK_EXPRESSION_UNSUPPORTED")
            return ("call", normalized, tuple(arguments))
        if len(parts) != 1 or name not in self._columns:
            _fail("CHECK_EXPRESSION_UNSUPPORTED")
        self._referenced.add(name)
        return ("column", name)


class _UniqueLoader(yaml.SafeLoader):
    """Safe YAML loader with duplicate mapping-key rejection."""


def _construct_unique_mapping(
    loader: _UniqueLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate mapping key",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _fail(code: str) -> NoReturn:
    raise PersistenceBuildError(code) from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _semantic_sha256(value: object) -> str:
    try:
        content = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail("SEMANTIC_VALUE_INVALID")
    return _sha256(content)


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        _fail(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value:
        _fail(code)
    return value


def _text_tuple(value: object, code: str) -> tuple[str, ...]:
    return tuple(_text(item, code) for item in _list(value, code))


def _expect_keys(value: Mapping[str, Any], expected: Sequence[str], code: str) -> None:
    """Reject authority-bearing extension fields as well as missing fields."""

    if set(value) != set(expected) or len(value) != len(expected):
        _fail(code)


def _validate_bound_path_row(
    value: object,
    *,
    expected_path: str,
    code: str,
    expected_authority: str | None = None,
) -> None:
    row = _mapping(value, code)
    expected_keys = (
        ("path", "sha256")
        if expected_authority is None
        else ("path", "sha256", "authority")
    )
    if (
        tuple(row) != expected_keys
        or row.get("path") != expected_path
        or type(row.get("sha256")) is not str
        or SHA256_PATTERN.fullmatch(cast(str, row.get("sha256"))) is None
        or (
            expected_authority is not None
            and row.get("authority") != expected_authority
        )
    ):
        _fail(code)


def _validate_product_contract(runtime: Mapping[str, Any]) -> None:
    """Validate the product contract without workflow-approval inputs."""

    if tuple(runtime) != EXPECTED_RUNTIME_ROOT_KEYS:
        _fail("RUNTIME_ROOT_INVALID")
    document = _mapping(runtime.get("document"), "RUNTIME_DOCUMENT_INVALID")
    if dict(document) != {
        "id": "RAOS-PERSISTENCE-RUNTIME-002",
        "version": "2.1.0",
        "story_id": "ST-0308",
        "status": "LOCAL_IMPLEMENTATION_CONTRACT",
        "formal_tst_005": "NOT_EXECUTED",
        "formal_tst_008": "NOT_EXECUTED",
    }:
        _fail("RUNTIME_DOCUMENT_INVALID")
    story = _mapping(runtime.get("story"), "RUNTIME_STORY_INVALID")
    if dict(story) != dict(EXPECTED_RUNTIME_STORY):
        _fail("RUNTIME_STORY_INVALID")

    sources = _list(runtime.get("sources"), "RUNTIME_SOURCES_INVALID")
    if len(sources) != len(EXPECTED_RUNTIME_SOURCE_PATHS):
        _fail("RUNTIME_SOURCE_INVENTORY_INVALID")
    for index, (row, expected_path) in enumerate(
        zip(sources, EXPECTED_RUNTIME_SOURCE_PATHS, strict=True)
    ):
        _validate_bound_path_row(
            row,
            expected_path=expected_path,
            expected_authority=(
                "CANDIDATE_IDENTITY_EVIDENCE_ONLY"
                if index == len(EXPECTED_RUNTIME_SOURCE_PATHS) - 1
                else None
            ),
            code="RUNTIME_SOURCE_INVENTORY_INVALID",
        )

    physical_fragments = _list(
        runtime.get("physical_fragments"), "PHYSICAL_INPUTS_INVALID"
    )
    if len(physical_fragments) != len(EXPECTED_PHYSICAL_FRAGMENT_PATHS):
        _fail("PHYSICAL_FRAGMENT_INVENTORY_INVALID")
    for row, expected_path in zip(
        physical_fragments, EXPECTED_PHYSICAL_FRAGMENT_PATHS, strict=True
    ):
        _validate_bound_path_row(
            row,
            expected_path=expected_path,
            code="PHYSICAL_FRAGMENT_INVENTORY_INVALID",
        )

    raw_matrices = _mapping(runtime.get("executable_matrices"), "MATRICES_INVALID")
    if tuple(raw_matrices) != MATRIX_KEYS:
        _fail("MATRIX_INVENTORY_INVALID")
    for matrix_name in MATRIX_KEYS:
        _validate_bound_path_row(
            raw_matrices[matrix_name],
            expected_path=EXPECTED_MATRIX_PATHS[matrix_name],
            code="MATRIX_INVENTORY_INVALID",
        )

    representative_slices = _mapping(
        runtime.get("representative_slices"), "SLICE_INVALID"
    )
    if tuple(representative_slices) != ("ops_reference",):
        _fail("SLICE_INVALID")
    _validate_bound_path_row(
        representative_slices["ops_reference"],
        expected_path=OPS_SLICE_PATH.as_posix(),
        code="SLICE_INVALID",
    )

    inventory = _mapping(runtime.get("inventory"), "RUNTIME_INVENTORY_INVALID")
    if (
        tuple(inventory)
        != (
            "schemas",
            "tables",
            "views",
            "contract_bidirectional_table_mapper_rows",
            "contract_metadata_only_table_rows",
            "contract_read_only_view_mapper_rows",
        )
        or _text_tuple(inventory.get("schemas"), "RUNTIME_INVENTORY_INVALID")
        != EXPECTED_RUNTIME_SCHEMAS
        or type(inventory.get("tables")) is not int
        or inventory.get("tables") != 103
        or _text_tuple(inventory.get("views"), "RUNTIME_INVENTORY_INVALID")
        != ("catalog.v_safe_offer_current",)
        or type(inventory.get("contract_bidirectional_table_mapper_rows")) is not int
        or inventory.get("contract_bidirectional_table_mapper_rows") != 102
        or _text_tuple(
            inventory.get("contract_metadata_only_table_rows"),
            "RUNTIME_INVENTORY_INVALID",
        )
        != ("ops.inbox_receipt",)
        or _text_tuple(
            inventory.get("contract_read_only_view_mapper_rows"),
            "RUNTIME_INVENTORY_INVALID",
        )
        != ("catalog.v_safe_offer_current",)
    ):
        _fail("RUNTIME_INVENTORY_INVALID")
    if dict(
        _mapping(runtime.get("runtime_decisions"), "RUNTIME_DECISIONS_INVALID")
    ) != dict(EXPECTED_RUNTIME_DECISIONS):
        _fail("RUNTIME_DECISIONS_INVALID")
    if dict(
        _mapping(runtime.get("execution_control"), "EXECUTION_CONTROL_INVALID")
    ) != dict(EXPECTED_EXECUTION_CONTROL):
        _fail("EXECUTION_CONTROL_INVALID")
    if dict(
        _mapping(runtime.get("identity_runtime"), "IDENTITY_RUNTIME_INVALID")
    ) != dict(EXPECTED_IDENTITY_RUNTIME):
        _fail("IDENTITY_RUNTIME_INVALID")
    if dict(_mapping(runtime.get("boundary"), "RUNTIME_BOUNDARY_INVALID")) != dict(
        EXPECTED_RUNTIME_BOUNDARY
    ):
        _fail("RUNTIME_BOUNDARY_INVALID")
    if _text_tuple(runtime.get("two_way_gates"), "TWO_WAY_GATES_INVALID") != (
        EXPECTED_TWO_WAY_GATES
    ):
        _fail("TWO_WAY_GATES_INVALID")


def _relative_path(value: object, code: str) -> Path:
    text = _text(value, code)
    if "\\" in text:
        _fail(code)
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        _fail(code)
    return Path(*pure.parts)


def _event_schema_path(event_type: str) -> Path:
    if type(event_type) is not str or not event_type.startswith("jp.raos."):
        _fail("EVENT_SCHEMA_PATH_INVALID")
    filename = event_type.replace(".", "-").replace("_", "-") + ".schema.json"
    return EVENT_SCHEMA_ROOT / filename


def _safe_input(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        _fail("INPUT_PATH_INVALID")
    root_real = root.resolve(strict=True)
    candidate = root_real.joinpath(relative)
    try:
        metadata = candidate.lstat()
    except OSError:
        _fail("INPUT_UNAVAILABLE")
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("INPUT_NOT_REGULAR")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_real)
    except OSError, ValueError:
        _fail("INPUT_PATH_ESCAPE")
    return resolved


def _read(root: Path, relative: Path) -> bytes:
    path = _safe_input(root, relative)
    try:
        content = path.read_bytes()
    except OSError:
        _fail("INPUT_UNAVAILABLE")
    if len(content) > MAX_INPUT_BYTES:
        _fail("INPUT_SIZE_LIMIT")
    return content


def _validate_yaml_tree(value: object) -> None:
    active: set[int] = set()
    visited: set[int] = set()

    def visit(candidate: object, depth: int) -> None:
        if depth > MAX_YAML_DEPTH:
            _fail("YAML_DEPTH_LIMIT")
        if candidate is None or type(candidate) in {bool, int, str}:
            return
        if type(candidate) is float:
            if not math.isfinite(candidate):
                _fail("YAML_NONFINITE")
            return
        if type(candidate) not in {dict, list}:
            _fail("YAML_VALUE_INVALID")
        identity = id(candidate)
        if identity in active:
            _fail("YAML_ALIAS_CYCLE")
        if identity in visited:
            return
        if len(visited) >= MAX_YAML_CONTAINERS:
            _fail("YAML_CONTAINER_LIMIT")
        visited.add(identity)
        active.add(identity)
        if type(candidate) is dict:
            if not all(type(key) is str for key in candidate):
                _fail("YAML_KEY_INVALID")
            for item in candidate.values():
                visit(item, depth + 1)
        else:
            for item in cast(list[object], candidate):
                visit(item, depth + 1)
        active.remove(identity)

    visit(value, 0)


def load_yaml(path: Path) -> Mapping[str, Any]:
    """Strict-load one tag-free, duplicate-key-free YAML mapping.

    Standard anchors and aliases are allowed because the hash-bound matrices use
    them.  Cycles, unsupported scalar types, and excessive container/depth
    shapes remain fail-closed.
    """

    try:
        content = path.read_bytes()
    except OSError:
        _fail("YAML_UNAVAILABLE")
    if len(content) > MAX_INPUT_BYTES:
        _fail("YAML_SIZE_LIMIT")
    try:
        text = content.decode("utf-8")
        for yaml_lexeme in yaml.scan(text):
            if isinstance(yaml_lexeme, TagToken):
                _fail("YAML_TAG_FORBIDDEN")
        value = yaml.load(text, Loader=_UniqueLoader)
        _validate_yaml_tree(value)
    except PersistenceBuildError:
        raise
    except UnicodeError, yaml.YAMLError, RecursionError:
        _fail("YAML_INVALID")
    return _mapping(value, "YAML_ROOT_INVALID")


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _load_json(root: Path, relative: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(
            _read(root, relative),
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=lambda _value: _fail("JSON_NONFINITE"),
        )
    except PersistenceBuildError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    return _mapping(value, "JSON_ROOT_INVALID")


def _load_yaml_at(root: Path, relative: Path) -> Mapping[str, Any]:
    return load_yaml(_safe_input(root, relative))


def _verify_digest(root: Path, relative: Path, expected: object) -> str:
    digest = _text(expected, "DIGEST_INVALID")
    if SHA256_PATTERN.fullmatch(digest) is None:
        _fail("DIGEST_INVALID")
    actual = _sha256(_read(root, relative))
    protected = input_hash_required(relative) or relative.as_posix().startswith(
        "contracts/"
    )
    if protected and actual != digest:
        _fail("BOUND_INPUT_DIGEST_MISMATCH")
    return actual


def _find_create_table_end(text: str, start: int) -> int:
    depth = 1
    quote = ""
    index = start
    while index < len(text):
        character = text[index]
        if quote:
            if character == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = ""
        elif character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    _fail("PHYSICAL_TABLE_INCOMPLETE")


def _split_sql_items(body: str) -> tuple[str, ...]:
    items: list[str] = []
    depth = 0
    quote = ""
    start = 0
    index = 0
    while index < len(body):
        character = body[index]
        if quote:
            if character == quote:
                if index + 1 < len(body) and body[index + 1] == quote:
                    index += 2
                    continue
                quote = ""
        elif character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                _fail("PHYSICAL_TABLE_INVALID")
        elif character == "," and depth == 0:
            items.append(body[start:index].strip())
            start = index + 1
        index += 1
    if quote or depth != 0:
        _fail("PHYSICAL_TABLE_INVALID")
    items.append(body[start:].strip())
    return tuple(items)


def _parse_physical_column(item: str) -> tuple[str, str, bool, str | None] | None:
    match = re.fullmatch(r'"([^"]+)"\s+(.+)', item, re.DOTALL)
    if match is None:
        return None
    name, declaration = match.groups()
    declaration = " ".join(declaration.split())
    positions = tuple(
        position
        for marker in (" DEFAULT ", " NOT NULL")
        if (position := declaration.find(marker)) >= 0
    )
    physical_type = declaration[: min(positions) if positions else len(declaration)]
    default: str | None = None
    default_at = declaration.find(" DEFAULT ")
    if default_at >= 0:
        remainder = declaration[default_at + len(" DEFAULT ") :]
        not_null_at = remainder.find(" NOT NULL")
        default = remainder[: not_null_at if not_null_at >= 0 else len(remainder)]
    return name, physical_type, " NOT NULL" not in declaration, default


def _parse_st0304_tables(
    root: Path, fragment_paths: Sequence[Path]
) -> Mapping[str, tuple[tuple[str, str, bool, str | None], ...]]:
    tables: dict[str, tuple[tuple[str, str, bool, str | None], ...]] = {}
    for relative in fragment_paths:
        try:
            text = _read(root, relative).decode("utf-8")
        except UnicodeError:
            _fail("PHYSICAL_FRAGMENT_NON_UTF8")
        for match in CREATE_TABLE_PATTERN.finditer(text):
            end = _find_create_table_end(text, match.end())
            if not text[end + 1 :].lstrip().startswith(";"):
                _fail("PHYSICAL_TABLE_TERMINATOR_INVALID")
            relation = ".".join(match.groups())
            if relation in tables:
                _fail("PHYSICAL_RELATION_DUPLICATE")
            columns = tuple(
                column
                for item in _split_sql_items(text[match.end() : end])
                if (column := _parse_physical_column(item)) is not None
            )
            if not columns or len({column[0] for column in columns}) != len(columns):
                _fail("PHYSICAL_COLUMNS_INVALID")
            tables[relation] = columns
    return MappingProxyType(tables)


def _parse_st0304_objects(
    root: Path,
    fragment_rows: Sequence[object],
) -> tuple[_PhysicalObject, ...]:
    """Parse every physical block and retain its exact owning fragment."""

    objects: list[_PhysicalObject] = []
    for raw_row in fragment_rows:
        row = _mapping(raw_row, "PHYSICAL_INPUT_INVALID")
        relative = _relative_path(row.get("path"), "PHYSICAL_INPUT_INVALID")
        fragment_sha256 = _text(row.get("sha256"), "PHYSICAL_INPUT_INVALID")
        content = _read(root, relative)
        if _sha256(content) != fragment_sha256:
            _fail("BOUND_INPUT_DIGEST_MISMATCH")
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            _fail("PHYSICAL_FRAGMENT_NON_UTF8")
        first = text.find("--\n-- Name: ")
        if first < 0:
            _fail("PHYSICAL_OBJECTS_ABSENT")
        try:
            fragment_index = (
                EXPECTED_PHYSICAL_FRAGMENT_PATHS.index(relative.as_posix()) + 1
            )
        except ValueError:
            _fail("PHYSICAL_FRAGMENT_INVENTORY_INVALID")
        expected_preamble = (
            f"-- ST-0304 physical translation fragment {fragment_index:02d} of 11.\n"
            "-- Source: approved RAOS data catalog plus finalized "
            "ST-0003/ST-0004 semantics.\n"
            "-- Capture: PostgreSQL 18.4 pg_dump --schema-only --no-owner "
            "--no-privileges\n"
            "--          --no-security-labels --quote-all-identifiers for the six "
            "owned schemas.\n"
            "-- Schema creation/comments are rendered once by the ST-0304 "
            "generator. The 22\n"
            "-- role-bound CREATE POLICY objects remain ST-0306-owned. ENABLE/FORCE "
            "RLS remains.\n\n"
        )
        if text[:first] != expected_preamble:
            _fail("PHYSICAL_FRAGMENT_PREAMBLE_INVALID")
        for block in re.split(r"(?=^--\n-- Name: )", text[first:], flags=re.MULTILINE):
            if not block.strip():
                continue
            match = PHYSICAL_OBJECT_HEADER.match(block)
            if match is None:
                _fail("PHYSICAL_OBJECT_HEADER_INVALID")
            name, object_type, schema = match.groups()
            sql = block[match.end() :].strip()
            if not sql.endswith(";"):
                _fail("PHYSICAL_OBJECT_SQL_INCOMPLETE")
            objects.append(
                _PhysicalObject(
                    name=name,
                    object_type=object_type,
                    schema=schema,
                    sql=sql,
                    sha256=_sha256(sql.encode("utf-8")),
                    fragment_path=relative.as_posix(),
                    fragment_sha256=fragment_sha256,
                )
            )
    return tuple(objects)


def _validate_st0304_object_inventory(
    catalog: Mapping[str, Any],
    objects: tuple[_PhysicalObject, ...],
) -> None:
    _expect_keys(
        catalog,
        EXPECTED_ST0304_CATALOG_ROOT_KEYS,
        "ST0304_CATALOG_SHAPE_INVALID",
    )
    inventory = _mapping(catalog.get("object_inventory"), "ST0304_INVENTORY_INVALID")
    _expect_keys(
        inventory,
        ("count", "objects", "sha256"),
        "ST0304_INVENTORY_INVALID",
    )
    expected_rows = _list(inventory.get("objects"), "ST0304_OBJECTS_INVALID")
    expected_values: list[tuple[str, str, str, str]] = []
    for raw in expected_rows:
        row = _mapping(raw, "ST0304_OBJECT_INVALID")
        _expect_keys(
            row,
            ("name", "schema", "sha256", "type"),
            "ST0304_OBJECT_INVALID",
        )
        row_sha256 = _text(row.get("sha256"), "ST0304_OBJECT_INVALID")
        if SHA256_PATTERN.fullmatch(row_sha256) is None:
            _fail("ST0304_OBJECT_INVALID")
        expected_values.append(
            (
                _text(row.get("name"), "ST0304_OBJECT_INVALID"),
                _text(row.get("schema"), "ST0304_OBJECT_INVALID"),
                row_sha256,
                _text(row.get("type"), "ST0304_OBJECT_INVALID"),
            )
        )
    expected = tuple(expected_values)
    actual = tuple(
        (item.name, item.schema, item.sha256, item.object_type) for item in objects
    )
    object_rows = [
        {
            "name": item.name,
            "schema": item.schema,
            "sha256": item.sha256,
            "type": item.object_type,
        }
        for item in objects
    ]
    inventory_bytes = json.dumps(
        object_rows,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if (
        type(inventory.get("count")) is not int
        or inventory.get("count") != EXPECTED_ST0304_OBJECT_COUNT
        or len(objects) != EXPECTED_ST0304_OBJECT_COUNT
        or inventory.get("count") != len(objects)
        or inventory.get("sha256") != _sha256(inventory_bytes)
        or expected != actual
    ):
        _fail("ST0304_OBJECT_INVENTORY_MISMATCH")


def _physical_object_relation(item: _PhysicalObject) -> str | None:
    """Resolve relation ownership only for row-shape-relevant object types."""

    if item.object_type in {"TABLE", "VIEW"}:
        relation_name = item.name
    elif item.object_type in {"CONSTRAINT", "FK CONSTRAINT", "TRIGGER"}:
        relation_name, separator, _object_name = item.name.partition(" ")
        if not separator:
            _fail("PHYSICAL_OBJECT_RELATION_INVALID")
    elif item.object_type == "INDEX":
        match = re.search(
            r'\bON(?: ONLY)? "(?P<schema>[a-z][a-z0-9_]*)"\.'
            r'"(?P<table>[a-z][a-z0-9_]*)"',
            item.sql,
        )
        if match is None or match.group("schema") != item.schema:
            _fail("PHYSICAL_INDEX_RELATION_INVALID")
        return f"{match.group('schema')}.{match.group('table')}"
    else:
        return None
    return f"{item.schema}.{relation_name}"


def _view_projection_columns(item: _PhysicalObject) -> tuple[str, ...]:
    if item.object_type != "VIEW":
        _fail("PHYSICAL_VIEW_INVALID")
    match = re.fullmatch(
        r'CREATE VIEW "[a-z][a-z0-9_]*"\."[a-z][a-z0-9_]*" AS\n'
        r" SELECT (?P<select>.*?)\n   FROM .*;",
        item.sql,
        re.DOTALL,
    )
    if match is None:
        _fail("PHYSICAL_VIEW_SHAPE_INVALID")
    columns: list[str] = []
    for expression in _split_sql_items(match.group("select")):
        normalized = " ".join(expression.split())
        column = re.fullmatch(
            r'"[a-z][a-z0-9_]*"\."(?P<source>[a-z][a-z0-9_]*)"'
            r'(?: AS "(?P<alias>[a-z][a-z0-9_]*)")?',
            normalized,
        )
        if column is None:
            _fail("PHYSICAL_VIEW_PROJECTION_INVALID")
        columns.append(column.group("alias") or column.group("source"))
    if not columns or len(columns) != len(set(columns)):
        _fail("PHYSICAL_VIEW_PROJECTION_INVALID")
    return tuple(columns)


def _catalog_tables(catalog: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw in _list(catalog.get("tables"), "ST0303_TABLES_INVALID"):
        table = _mapping(raw, "ST0303_TABLE_INVALID")
        relation = _text(table.get("fully_qualified_name"), "ST0303_RELATION_INVALID")
        if relation in result:
            _fail("ST0303_RELATION_DUPLICATE")
        result[relation] = table
    return MappingProxyType(result)


def _st0304_inventory(catalog: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    inventory = _mapping(catalog.get("object_inventory"), "ST0304_INVENTORY_INVALID")
    tables: set[str] = set()
    views: set[str] = set()
    for raw in _list(inventory.get("objects"), "ST0304_OBJECTS_INVALID"):
        item = _mapping(raw, "ST0304_OBJECT_INVALID")
        kind = item.get("type")
        if kind not in {"TABLE", "VIEW"}:
            continue
        relation = (
            f"{_text(item.get('schema'), 'ST0304_OBJECT_INVALID')}."
            f"{_text(item.get('name'), 'ST0304_OBJECT_INVALID')}"
        )
        target = tables if kind == "TABLE" else views
        if relation in target:
            _fail("ST0304_OBJECT_DUPLICATE")
        target.add(relation)
    return tables, views


def _validate_relation_contract_shape(
    relation: Mapping[str, Any],
    *,
    callable_names: set[str],
) -> None:
    _expect_keys(relation, EXPECTED_RELATION_KEYS, "MAPPER_RELATION_SHAPE_INVALID")
    relation_name = _text(relation.get("relation"), "MAPPER_RELATION_INVALID")
    schema_name, separator, table_name = relation_name.partition(".")
    if (
        not separator
        or re.fullmatch(r"[a-z][a-z0-9_]*", schema_name) is None
        or re.fullmatch(r"[a-z][a-z0-9_]*", table_name) is None
    ):
        _fail("MAPPER_RELATION_INVALID")
    _text(relation.get("physical_source"), "MAPPER_RELATION_INVALID")
    treatment = _text(relation.get("treatment"), "MAPPER_RELATION_INVALID")
    if treatment not in {
        "EXPLICIT_BIDIRECTIONAL_SCALAR_MAPPER",
        "GENERATED_METADATA_ONLY_NO_RUNTIME_MAPPER_OR_PORT",
        "READ_ONLY_EXPLICIT_FROM_ROW_MAPPER_NO_DML",
    }:
        _fail("MAPPER_RELATION_INVALID")

    owner = _mapping(relation.get("repository_owner"), "MAPPER_OWNER_INVALID")
    _expect_keys(owner, EXPECTED_REPOSITORY_OWNER_KEYS, "MAPPER_OWNER_INVALID")
    _text(owner.get("module"), "MAPPER_OWNER_INVALID")
    _text(owner.get("uow_property"), "MAPPER_OWNER_INVALID")
    owner_protocol = owner.get("protocol")
    if owner_protocol is not None and type(owner_protocol) is not str:
        _fail("MAPPER_OWNER_INVALID")

    metadata_only = treatment == "GENERATED_METADATA_ONLY_NO_RUNTIME_MAPPER_OR_PORT"
    for field in ("domain_path", "domain_type", "domain_kind"):
        value = relation.get(field)
        if metadata_only:
            if value is not None:
                _fail("MAPPER_RELATION_INVALID")
        else:
            _text(value, "MAPPER_RELATION_INVALID")
    if metadata_only:
        if dict(owner) != {
            "module": "excluded",
            "uow_property": "metadata_only",
            "protocol": None,
        }:
            _fail("MAPPER_OWNER_INVALID")
    elif type(owner_protocol) is not str or not owner_protocol:
        _fail("MAPPER_OWNER_INVALID")

    columns = _list(relation.get("physical_columns"), "MAPPER_COLUMNS_INVALID")
    column_names: set[str] = set()
    expected_parameters: list[str] = []
    for expected_ordinal, raw_column in enumerate(columns, start=1):
        column = _mapping(raw_column, "MAPPER_COLUMN_INVALID")
        _expect_keys(column, EXPECTED_PHYSICAL_COLUMN_KEYS, "MAPPER_COLUMN_INVALID")
        column_name = _text(column.get("physical_column"), "MAPPER_COLUMN_INVALID")
        if column_name in column_names or column.get("ordinal") != expected_ordinal:
            _fail("MAPPER_COLUMN_INVALID")
        column_names.add(column_name)
        _text(column.get("physical_sql_type"), "MAPPER_COLUMN_INVALID")
        if type(column.get("nullable")) is not bool:
            _fail("MAPPER_COLUMN_INVALID")
        server_default = column.get("server_default")
        if server_default is not None and type(server_default) is not str:
            _fail("MAPPER_COLUMN_INVALID")
        domain_field = column.get("domain_field")
        domain_type = column.get("domain_type")
        if metadata_only:
            if domain_field is not None or domain_type is not None:
                _fail("MAPPER_COLUMN_INVALID")
        else:
            expected_parameters.append(
                f"{_text(domain_field, 'MAPPER_COLUMN_INVALID')}: "
                f"{_text(domain_type, 'MAPPER_COLUMN_INVALID')}"
            )
        _text(column.get("domain_definition_kind"), "MAPPER_COLUMN_INVALID")
        definition_path = column.get("domain_definition_path")
        if definition_path is not None and type(definition_path) is not str:
            _fail("MAPPER_COLUMN_INVALID")
        corruptions = _text_tuple(
            column.get("corruption_behavior"), "MAPPER_COLUMN_INVALID"
        )
        if not corruptions or len(corruptions) != len(set(corruptions)):
            _fail("MAPPER_COLUMN_INVALID")
    if not columns:
        _fail("MAPPER_COLUMNS_INVALID")
    columns_sha256 = _text(
        relation.get("physical_columns_sha256"), "MAPPER_COLUMNS_INVALID"
    )
    physical_column_projection = [
        {
            key: column[key]
            for key in (
                "ordinal",
                "physical_column",
                "physical_sql_type",
                "nullable",
                "server_default",
            )
        }
        for column in (
            _mapping(raw_column, "MAPPER_COLUMN_INVALID") for raw_column in columns
        )
    ]
    if SHA256_PATTERN.fullmatch(
        columns_sha256
    ) is None or columns_sha256 != _semantic_sha256(physical_column_projection):
        _fail("MAPPER_COLUMNS_INVALID")

    primary_key = _text_tuple(relation.get("primary_key"), "MAPPER_RELATION_INVALID")
    if (
        not primary_key
        or len(primary_key) != len(set(primary_key))
        or not set(primary_key).issubset(column_names)
    ):
        _fail("MAPPER_RELATION_INVALID")
    identity = relation.get("identity")
    if identity is not None:
        identity_mapping = _mapping(identity, "MAPPER_IDENTITY_INVALID")
        _expect_keys(
            identity_mapping, EXPECTED_IDENTITY_KEYS, "MAPPER_IDENTITY_INVALID"
        )
        _text(identity_mapping.get("type"), "MAPPER_IDENTITY_INVALID")
        identity_columns = _text_tuple(
            identity_mapping.get("columns"), "MAPPER_IDENTITY_INVALID"
        )
        if (
            not identity_columns
            or len(identity_columns) != len(set(identity_columns))
            or not set(identity_columns).issubset(column_names)
        ):
            _fail("MAPPER_IDENTITY_INVALID")
    elif not metadata_only:
        _fail("MAPPER_IDENTITY_INVALID")

    json_columns: set[str] = set()
    for raw_json in _list(
        relation.get("json_contracts"), "MAPPER_JSON_CONTRACTS_INVALID"
    ):
        json_contract = _mapping(raw_json, "MAPPER_JSON_CONTRACT_INVALID")
        _expect_keys(
            json_contract,
            EXPECTED_JSON_CONTRACT_KEYS,
            "MAPPER_JSON_CONTRACT_INVALID",
        )
        json_column = _text(
            json_contract.get("physical_column"), "MAPPER_JSON_CONTRACT_INVALID"
        )
        if json_column in json_columns or json_column not in column_names:
            _fail("MAPPER_JSON_CONTRACT_INVALID")
        json_columns.add(json_column)
        for field in ("domain_wrapper", "wrapper_path", "root", "corruption_behavior"):
            _text(json_contract.get(field), "MAPPER_JSON_CONTRACT_INVALID")
        _text_tuple(
            json_contract.get("additional_invariants"),
            "MAPPER_JSON_CONTRACT_INVALID",
        )

    check_names: set[str] = set()
    for raw_check in _list(
        relation.get("physical_check_constraints"), "MAPPER_CHECKS_INVALID"
    ):
        check = _mapping(raw_check, "MAPPER_CHECK_INVALID")
        _expect_keys(check, EXPECTED_CHECK_CONSTRAINT_KEYS, "MAPPER_CHECK_INVALID")
        check_name = _text(check.get("name"), "MAPPER_CHECK_INVALID")
        _text(check.get("expression"), "MAPPER_CHECK_INVALID")
        if check_name in check_names:
            _fail("MAPPER_CHECK_INVALID")
        check_names.add(check_name)

    write_pattern = relation.get("write_pattern")
    if write_pattern is not None and type(write_pattern) is not str:
        _fail("MAPPER_RELATION_INVALID")
    child_ownership = relation.get("child_ownership")
    if isinstance(child_ownership, Mapping):
        child_mapping = _mapping(child_ownership, "MAPPER_CHILD_OWNERSHIP_INVALID")
        _expect_keys(
            child_mapping,
            EXPECTED_CHILD_OWNERSHIP_KEYS,
            "MAPPER_CHILD_OWNERSHIP_INVALID",
        )
        _text(child_mapping.get("root_relation"), "MAPPER_CHILD_OWNERSHIP_INVALID")
        _text(child_mapping.get("mode"), "MAPPER_CHILD_OWNERSHIP_INVALID")
    else:
        _text(child_ownership, "MAPPER_CHILD_OWNERSHIP_INVALID")
    if dict(
        _mapping(relation.get("corruption_policy"), "MAPPER_CORRUPTION_INVALID")
    ) != dict(EXPECTED_CORRUPTION_POLICY):
        _fail("MAPPER_CORRUPTION_INVALID")

    mapper = relation.get("mapper")
    if metadata_only:
        if mapper is not None:
            _fail("MAPPER_CONTRACT_INVALID")
        return
    mapper_mapping = _mapping(mapper, "MAPPER_CONTRACT_INVALID")
    _expect_keys(mapper_mapping, EXPECTED_MAPPER_KEYS, "MAPPER_CONTRACT_INVALID")
    if (
        mapper_mapping.get("path")
        != f"python/raos/adapters/persistence/sqlalchemy/mappers/{schema_name}.py"
        or mapper_mapping.get("from_row") != f"map_{schema_name}_{table_name}_from_row"
        or mapper_mapping.get("signature") != EXPECTED_MAPPER_SIGNATURE
        or _text_tuple(
            mapper_mapping.get("input_parameters"), "MAPPER_CONTRACT_INVALID"
        )
        != tuple(expected_parameters)
        or mapper_mapping.get("output") != relation.get("domain_type")
    ):
        _fail("MAPPER_CONTRACT_INVALID")
    expected_to_row = (
        None
        if treatment == "READ_ONLY_EXPLICIT_FROM_ROW_MAPPER_NO_DML"
        else f"map_{schema_name}_{table_name}_to_row"
    )
    if mapper_mapping.get("to_row") != expected_to_row:
        _fail("MAPPER_CONTRACT_INVALID")
    mapper_callables = [cast(str, mapper_mapping["from_row"])]
    if expected_to_row is not None:
        mapper_callables.append(expected_to_row)
    if any(name in callable_names for name in mapper_callables):
        _fail("MAPPER_CALLABLE_DUPLICATE")
    callable_names.update(mapper_callables)


def _relation_index(
    domain_mapper: Mapping[str, Any],
) -> Mapping[str, Mapping[str, Any]]:
    _expect_keys(
        domain_mapper,
        EXPECTED_DOMAIN_MAPPER_ROOT_KEYS,
        "MAPPER_ROOT_SHAPE_INVALID",
    )
    result: dict[str, Mapping[str, Any]] = {}
    callable_names: set[str] = set()
    for raw in _list(domain_mapper.get("relations"), "MAPPER_RELATIONS_INVALID"):
        relation = _mapping(raw, "MAPPER_RELATION_INVALID")
        _validate_relation_contract_shape(
            relation,
            callable_names=callable_names,
        )
        name = _text(relation.get("relation"), "MAPPER_RELATION_INVALID")
        if name in result:
            _fail("MAPPER_RELATION_DUPLICATE")
        declared_hash = _text(
            relation.get("relation_contract_sha256"), "RELATION_HASH_INVALID"
        )
        material = {
            key: value
            for key, value in relation.items()
            if key != "relation_contract_sha256"
        }
        if _semantic_sha256(material) != declared_hash:
            _fail("RELATION_HASH_MISMATCH")
        result[name] = relation
    return MappingProxyType(result)


def _column_projection(
    relation: Mapping[str, Any],
) -> tuple[tuple[str, str, bool, str | None], ...]:
    result: list[tuple[str, str, bool, str | None]] = []
    for expected_ordinal, raw in enumerate(
        _list(relation.get("physical_columns"), "MAPPER_COLUMNS_INVALID"), start=1
    ):
        column = _mapping(raw, "MAPPER_COLUMN_INVALID")
        if column.get("ordinal") != expected_ordinal:
            _fail("MAPPER_COLUMN_ORDINAL_INVALID")
        nullable = column.get("nullable")
        default = column.get("server_default")
        if type(nullable) is not bool or (
            default is not None and type(default) is not str
        ):
            _fail("MAPPER_COLUMN_INVALID")
        result.append(
            (
                _text(column.get("physical_column"), "MAPPER_COLUMN_INVALID"),
                _text(column.get("physical_sql_type"), "MAPPER_COLUMN_INVALID"),
                nullable,
                default,
            )
        )
    if len({row[0] for row in result}) != len(result):
        _fail("MAPPER_COLUMN_DUPLICATE")
    return tuple(result)


def _validate_repository_ownership(
    repository_surface: Mapping[str, Any],
    relations: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    protocols: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    modules = _mapping(repository_surface.get("modules"), "REPOSITORIES_INVALID")
    for module_name, raw_repositories in modules.items():
        repositories = _mapping(raw_repositories, "REPOSITORIES_INVALID")
        for property_name, raw_spec in repositories.items():
            spec = _mapping(raw_spec, "REPOSITORY_INVALID")
            protocol = _text(spec.get("protocol"), "REPOSITORY_INVALID")
            repository_relations = tuple(
                _text(value, "REPOSITORY_INVALID")
                for value in _list(spec.get("relations"), "REPOSITORY_INVALID")
            )
            child_relations = tuple(
                _text(value, "REPOSITORY_INVALID")
                for value in _list(
                    spec.get("child_relations", []), "REPOSITORY_INVALID"
                )
            )
            if protocol in protocols:
                _fail("REPOSITORY_PROTOCOL_DUPLICATE")
            protocols[protocol] = (
                module_name,
                property_name,
                repository_relations + child_relations,
            )
    shared = _mapping(repository_surface.get("shared"), "SHARED_REPOSITORIES_INVALID")
    for property_name, raw_spec in shared.items():
        spec = _mapping(raw_spec, "SHARED_REPOSITORY_INVALID")
        shared_protocol = {
            "audit": "AuditEventAppender",
            "outbox": "OutboxEventAppender",
            "idempotency": "IdempotencyRepository",
        }.get(property_name)
        if shared_protocol is None:
            _fail("SHARED_REPOSITORY_INVALID")
        shared_relation = _text(spec.get("relation"), "SHARED_REPOSITORY_INVALID")
        protocols[shared_protocol] = (
            "shared_persistence",
            property_name,
            (shared_relation,),
        )

    excluded = _mapping(repository_surface.get("excluded"), "EXCLUSIONS_INVALID")
    excluded_relations = set(excluded)
    owned_relations: set[str] = set()
    for protocol, (module_name, property_name, protocol_relations) in protocols.items():
        for name in protocol_relations:
            if name in owned_relations:
                _fail("REPOSITORY_RELATION_DUPLICATE")
            owned_relations.add(name)
            mapped_relation = relations.get(name)
            if mapped_relation is None:
                _fail("REPOSITORY_RELATION_UNKNOWN")
            owner = _mapping(
                mapped_relation.get("repository_owner"), "MAPPER_OWNER_INVALID"
            )
            if (
                owner.get("module") != module_name
                or owner.get("uow_property") != property_name
                or owner.get("protocol") != protocol
            ):
                _fail("REPOSITORY_MAPPER_OWNER_MISMATCH")
    if owned_relations | excluded_relations != set(relations):
        _fail("REPOSITORY_RELATION_COVERAGE_MISMATCH")
    if owned_relations & excluded_relations:
        _fail("REPOSITORY_RELATION_COVERAGE_MISMATCH")
    return tuple(sorted(owned_relations)), tuple(sorted(excluded_relations))


def _repository_method_index(
    repository_surface: Mapping[str, Any],
) -> Mapping[str, frozenset[str]]:
    """Bind every qualified concurrency/event owner to one declared Port method."""

    methods_by_protocol: dict[str, frozenset[str]] = {}
    modules = _mapping(repository_surface.get("modules"), "REPOSITORIES_INVALID")
    for raw_repositories in modules.values():
        repositories = _mapping(raw_repositories, "REPOSITORIES_INVALID")
        for raw_spec in repositories.values():
            spec = _mapping(raw_spec, "REPOSITORY_INVALID")
            protocol = _text(spec.get("protocol"), "REPOSITORY_INVALID")
            names: list[str] = []
            for raw_method in _list(spec.get("methods"), "REPOSITORY_INVALID"):
                signature = _text(raw_method, "REPOSITORY_INVALID")
                name, separator, _remainder = signature.partition("(")
                if (
                    separator != "("
                    or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is None
                ):
                    _fail("REPOSITORY_METHOD_INVALID")
                names.append(name)
            if protocol in methods_by_protocol or len(names) != len(set(names)):
                _fail("REPOSITORY_METHOD_INVALID")
            methods_by_protocol[protocol] = frozenset(names)
    return MappingProxyType(methods_by_protocol)


def _validate_state_cas_method_ownership(
    *,
    repository_surface: Mapping[str, Any],
    state_cas: Mapping[str, Any],
    relations: Mapping[str, Mapping[str, Any]],
) -> None:
    methods_by_protocol = _repository_method_index(repository_surface)
    state_relations = _mapping(state_cas.get("relations"), "STATE_CAS_INVALID")
    for relation_name, raw_spec in state_relations.items():
        relation = relations.get(relation_name)
        if relation is None:
            _fail("STATE_CAS_METHOD_OWNER_MISMATCH")
        owner = _mapping(relation.get("repository_owner"), "MAPPER_OWNER_INVALID")
        expected_protocol = _text(owner.get("protocol"), "MAPPER_OWNER_INVALID")
        allowed_methods = methods_by_protocol.get(expected_protocol)
        if allowed_methods is None:
            _fail("STATE_CAS_METHOD_OWNER_MISMATCH")
        spec = _mapping(raw_spec, "STATE_CAS_INVALID")
        for raw_edge in _list(spec.get("edges"), "STATE_CAS_INVALID"):
            edge = _mapping(raw_edge, "STATE_CAS_INVALID")
            qualified = _text(edge.get("method"), "STATE_CAS_INVALID")
            protocol, separator, method = qualified.partition(".")
            if (
                separator != "."
                or "." in method
                or protocol != expected_protocol
                or method not in allowed_methods
            ):
                _fail("STATE_CAS_METHOD_OWNER_MISMATCH")


def _validate_idempotency_outcome_contract(
    idempotency: Mapping[str, Any],
) -> None:
    """Keep deterministic business failures distinct from transport failure.

    A terminal ``FAILED`` row is replayable application output.  It must never
    be possible to persist cancellation, deadline, rollback, infrastructure,
    or indeterminate-commit failure through the same unclassified value.
    """

    public_protocol = _mapping(
        idempotency.get("public_protocol"), "IDEMPOTENCY_INVALID"
    )
    if public_protocol != {
        "claim": "claim(claim: IdempotencyClaim) -> IdempotencyClaimDecision",
        "lookup": "lookup(identity: IdempotencyIdentity, request_hash: RequestHash) -> IdempotencyLookupDecision",
        "complete_success": "complete_success(handle: IdempotencyClaimHandle, outcome: IdempotencyOutcome) -> None",
        "complete_failure": "complete_failure(handle: IdempotencyClaimHandle, outcome: IdempotencyOutcome) -> None",
    }:
        _fail("IDEMPOTENCY_PROTOCOL_INVALID")
    completion = _mapping(idempotency.get("completion"), "IDEMPOTENCY_INVALID")
    if completion.get(
        "failure_allowance"
    ) != "route-approved deterministic business failures only" or _list(
        completion.get("never_confirm_as_failure"), "IDEMPOTENCY_INVALID"
    ) != [
        "infrastructure failure",
        "cancellation",
        "timeout",
        "rollback",
        "unknown commit",
    ]:
        _fail("IDEMPOTENCY_FAILURE_BOUNDARY_INVALID")
    outcome_shape = _mapping(idempotency.get("outcome_shape"), "IDEMPOTENCY_INVALID")
    if (
        outcome_shape.get("disposition")
        != "SUCCESS for complete_success; ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE for complete_failure"
    ):
        _fail("IDEMPOTENCY_OUTCOME_DISPOSITION_INVALID")


def _inline_check_constraints(item: _PhysicalObject) -> tuple[dict[str, str], ...]:
    match = CREATE_TABLE_PATTERN.search(item.sql)
    if match is None or ".".join(match.groups()) != f"{item.schema}.{item.name}":
        _fail("PHYSICAL_TABLE_OBJECT_INVALID")
    end = _find_create_table_end(item.sql, match.end())
    checks: list[dict[str, str]] = []
    for clause in _split_sql_items(item.sql[match.end() : end]):
        check = re.fullmatch(
            r'CONSTRAINT "(?P<name>[a-z][a-z0-9_]*)" CHECK (?P<expression>.+)',
            clause,
            re.DOTALL,
        )
        if check is not None:
            checks.append(
                {
                    "name": check.group("name"),
                    "expression": " ".join(check.group("expression").split()),
                }
            )
    if len({row["name"] for row in checks}) != len(checks):
        _fail("PHYSICAL_CHECK_DUPLICATE")
    return tuple(checks)


def _constraint_semantics(item: _PhysicalObject) -> dict[str, object]:
    if item.object_type not in {"CONSTRAINT", "FK CONSTRAINT"}:
        _fail("PHYSICAL_CONSTRAINT_INVALID")
    relation_name, separator, header_name = item.name.partition(" ")
    if not separator:
        _fail("PHYSICAL_CONSTRAINT_INVALID")
    base = re.match(
        r'^ALTER TABLE ONLY "(?P<schema>[a-z][a-z0-9_]*)"\.'
        r'"(?P<table>[a-z][a-z0-9_]*)"\s+'
        r'ADD CONSTRAINT "(?P<name>[a-z][a-z0-9_]*)" (?P<body>.*);$',
        item.sql,
        re.DOTALL,
    )
    if (
        base is None
        or base.group("schema") != item.schema
        or base.group("table") != relation_name
        or base.group("name") != header_name
    ):
        _fail("PHYSICAL_CONSTRAINT_INVALID")
    body = " ".join(base.group("body").split())
    if item.object_type == "CONSTRAINT":
        kind_match = re.fullmatch(
            r'(?P<kind>PRIMARY KEY|UNIQUE) \((?P<columns>"[^"]+"'
            r'(?:, "[^"]+")*)\)(?P<tail>.*)',
            body,
        )
        if kind_match is None:
            _fail("PHYSICAL_CONSTRAINT_INVALID")
        columns = tuple(re.findall(r'"([^"]+)"', kind_match.group("columns")))
        return {
            "kind": (
                "PRIMARY_KEY" if kind_match.group("kind") == "PRIMARY KEY" else "UNIQUE"
            ),
            "name": header_name,
            "columns": list(columns),
            "tail": kind_match.group("tail") or None,
        }
    foreign_key = re.fullmatch(
        r'FOREIGN KEY \((?P<columns>"[^"]+"(?:, "[^"]+")*)\) '
        r'REFERENCES "(?P<ref_schema>[a-z][a-z0-9_]*)"\.'
        r'"(?P<ref_table>[a-z][a-z0-9_]*)"\s*'
        r'\((?P<ref_columns>"[^"]+"(?:, "[^"]+")*)\)(?P<tail>.*)',
        body,
    )
    if foreign_key is None:
        _fail("PHYSICAL_FOREIGN_KEY_INVALID")
    return {
        "kind": "FOREIGN_KEY",
        "name": header_name,
        "columns": list(re.findall(r'"([^"]+)"', foreign_key.group("columns"))),
        "references": (
            f"{foreign_key.group('ref_schema')}.{foreign_key.group('ref_table')}"
        ),
        "referenced_columns": list(
            re.findall(r'"([^"]+)"', foreign_key.group("ref_columns"))
        ),
        "tail": foreign_key.group("tail") or None,
    }


def _index_semantics(item: _PhysicalObject) -> dict[str, object]:
    if item.object_type != "INDEX":
        _fail("PHYSICAL_INDEX_INVALID")
    prefix = re.match(
        r'^CREATE (?P<unique>UNIQUE )?INDEX "(?P<name>[a-z][a-z0-9_]*)" '
        r'ON "(?P<schema>[a-z][a-z0-9_]*)"\.'
        r'"(?P<table>[a-z][a-z0-9_]*)" USING '
        r'"(?P<method>[a-z][a-z0-9_]*)" \(',
        item.sql,
    )
    if (
        prefix is None
        or prefix.group("name") != item.name
        or prefix.group("schema") != item.schema
    ):
        _fail("PHYSICAL_INDEX_INVALID")
    close = _find_create_table_end(item.sql, prefix.end())
    expressions = _split_sql_items(item.sql[prefix.end() : close])
    if not expressions:
        _fail("PHYSICAL_INDEX_INVALID")
    suffix = item.sql[close + 1 :]
    nulls_not_distinct = False
    if suffix.startswith(" NULLS NOT DISTINCT"):
        nulls_not_distinct = True
        suffix = suffix.removeprefix(" NULLS NOT DISTINCT")
    where: str | None = None
    if suffix.startswith(" WHERE ") and suffix.endswith(";"):
        where = suffix[len(" WHERE ") : -1]
    elif suffix != ";":
        _fail("PHYSICAL_INDEX_INVALID")
    return {
        "name": item.name,
        "schema": item.schema,
        "table": prefix.group("table"),
        "method": prefix.group("method"),
        "unique": prefix.group("unique") is not None,
        "expressions": list(expressions),
        "nulls_not_distinct": nulls_not_distinct,
        "where": where,
    }


def _object_provenance(item: _PhysicalObject) -> dict[str, object]:
    row: dict[str, object] = {
        "fragment_path": item.fragment_path,
        "fragment_sha256": item.fragment_sha256,
        "name": item.name,
        "object_type": item.object_type,
        "statement_sha256": item.sha256,
    }
    if item.object_type in {"CONSTRAINT", "FK CONSTRAINT"}:
        row["semantics"] = _constraint_semantics(item)
    elif item.object_type == "INDEX":
        row["semantics"] = _index_semantics(item)
    return row


def _build_catalog_ir(
    *,
    runtime: Mapping[str, Any],
    relations: Mapping[str, Mapping[str, Any]],
    st0303_catalog: Mapping[str, Any],
    st0303: Mapping[str, Mapping[str, Any]],
    st0304_catalog: Mapping[str, Any],
    objects: tuple[_PhysicalObject, ...],
    ownership_counts: tuple[tuple[str, ...], tuple[str, ...]],
) -> Mapping[str, Any]:
    """Build the closed semantic fan-out input without inventing runtime APIs."""

    st0304_relation_names = {
        f"{item.schema}.{item.name}"
        for item in objects
        if item.object_type in {"TABLE", "VIEW"}
    }
    relevant_types = {
        "TABLE",
        "VIEW",
        "CONSTRAINT",
        "FK CONSTRAINT",
        "INDEX",
        "TRIGGER",
    }
    by_relation: dict[str, list[_PhysicalObject]] = {
        name: [] for name in st0304_relation_names
    }
    relevant_count = 0
    relevant_type_counts: dict[str, int] = {}
    for item in objects:
        relation_name = _physical_object_relation(item)
        if item.object_type in relevant_types:
            relevant_count += 1
            relevant_type_counts[item.object_type] = (
                relevant_type_counts.get(item.object_type, 0) + 1
            )
            if relation_name is None or relation_name not in by_relation:
                _fail("PHYSICAL_OBJECT_RELATION_COVERAGE_MISMATCH")
            by_relation[relation_name].append(item)
        elif relation_name is not None:
            _fail("PHYSICAL_OBJECT_RELATION_COVERAGE_MISMATCH")
    if (
        len(objects) != EXPECTED_ST0304_OBJECT_COUNT
        or relevant_count != EXPECTED_ST0304_RELATION_OBJECT_COUNT
        or relevant_type_counts != dict(EXPECTED_ST0304_RELATION_OBJECT_TYPE_COUNTS)
        or sum(len(items) for items in by_relation.values()) != relevant_count
    ):
        _fail("PHYSICAL_OBJECT_RELATION_COVERAGE_MISMATCH")

    st0303_triggers_by_relation: dict[str, list[Mapping[str, Any]]] = {
        name: [] for name in st0303
    }
    for raw in _list(st0303_catalog.get("triggers"), "ST0303_TRIGGERS_INVALID"):
        trigger = _mapping(raw, "ST0303_TRIGGER_INVALID")
        relation_name = _text(trigger.get("table"), "ST0303_TRIGGER_INVALID")
        if relation_name not in st0303_triggers_by_relation:
            _fail("ST0303_TRIGGER_RELATION_INVALID")
        st0303_triggers_by_relation[relation_name].append(trigger)

    rows: list[dict[str, object]] = []
    generated_columns: list[str] = []
    physical_object_assignment_count = 0
    primary_key_count = 0
    for relation_name in sorted(relations):
        relation = relations[relation_name]
        treatment = _text(relation.get("treatment"), "MAPPER_RELATION_INVALID")
        columns = [
            dict(_mapping(raw, "MAPPER_COLUMN_INVALID"))
            for raw in _list(relation.get("physical_columns"), "MAPPER_COLUMNS_INVALID")
        ]
        for column in columns:
            if " GENERATED ALWAYS AS " in _text(
                column.get("physical_sql_type"), "MAPPER_COLUMN_INVALID"
            ):
                generated_columns.append(
                    f"{relation_name}.{_text(column.get('physical_column'), 'MAPPER_COLUMN_INVALID')}"
                )
        checks = [
            dict(_mapping(raw, "MAPPER_CHECK_INVALID"))
            for raw in _list(
                relation.get("physical_check_constraints"),
                "MAPPER_CHECKS_INVALID",
            )
        ]
        if relation_name in st0303:
            table = st0303[relation_name]
            if (
                _list(table.get("primary_key"), "ST0303_TABLE_INVALID")
                != _list(relation.get("primary_key"), "MAPPER_RELATION_INVALID")
                or _list(table.get("check_constraints"), "ST0303_TABLE_INVALID")
                != checks
            ):
                _fail("ST0303_CONSTRAINT_MATRIX_MISMATCH")
            primary_key_count += 1
            rows.append(
                {
                    "relation": relation_name,
                    "kind": "TABLE",
                    "physical_source": "ST-0303_CATALOG",
                    "source_row_sha256": _semantic_sha256(table),
                    "treatment": treatment,
                    "relation_contract_sha256": relation.get(
                        "relation_contract_sha256"
                    ),
                    "repository_owner": relation.get("repository_owner"),
                    "domain": {
                        "path": relation.get("domain_path"),
                        "type": relation.get("domain_type"),
                        "kind": relation.get("domain_kind"),
                    },
                    "mapper": relation.get("mapper"),
                    "columns": columns,
                    "primary_key": {
                        "name": table.get("primary_key_name"),
                        "columns": list(table.get("primary_key", [])),
                    },
                    "foreign_keys": list(table.get("foreign_keys", [])),
                    "unique_constraints": list(table.get("unique_constraints", [])),
                    "check_constraints": checks,
                    "indexes": list(table.get("indexes", [])),
                    "triggers": [
                        dict(trigger)
                        for trigger in st0303_triggers_by_relation[relation_name]
                    ],
                    "physical_object_provenance": [],
                }
            )
            continue

        assigned = tuple(by_relation.get(relation_name, ()))
        physical_object_assignment_count += len(assigned)
        base_objects = tuple(
            item for item in assigned if item.object_type in {"TABLE", "VIEW"}
        )
        expected_kind = (
            "VIEW" if relation_name == "catalog.v_safe_offer_current" else "TABLE"
        )
        if len(base_objects) != 1 or base_objects[0].object_type != expected_kind:
            _fail("PHYSICAL_BASE_OBJECT_MISMATCH")
        primary_key: dict[str, object]
        if expected_kind == "VIEW":
            if _view_projection_columns(base_objects[0]) != tuple(
                _text(column.get("physical_column"), "MAPPER_COLUMN_INVALID")
                for column in columns
            ):
                _fail("PHYSICAL_VIEW_COLUMN_MISMATCH")
            if treatment != "READ_ONLY_EXPLICIT_FROM_ROW_MAPPER_NO_DML":
                _fail("PHYSICAL_VIEW_TREATMENT_MISMATCH")
            primary_key = {
                "name": None,
                "columns": list(relation.get("primary_key", [])),
                "contract_identity_only": True,
            }
        else:
            table_object = base_objects[0]
            physical_checks = list(_inline_check_constraints(table_object))
            if physical_checks != checks:
                _fail("ST0304_CHECK_MATRIX_MISMATCH")
            primary_objects = tuple(
                item
                for item in assigned
                if item.object_type == "CONSTRAINT"
                and _constraint_semantics(item)["kind"] == "PRIMARY_KEY"
            )
            if len(primary_objects) != 1:
                _fail("ST0304_PRIMARY_KEY_MISMATCH")
            primary_semantics = _constraint_semantics(primary_objects[0])
            if primary_semantics["columns"] != list(relation.get("primary_key", [])):
                _fail("ST0304_PRIMARY_KEY_MISMATCH")
            primary_key = primary_semantics
            primary_key_count += 1
        rows.append(
            {
                "relation": relation_name,
                "kind": expected_kind,
                "physical_source": relation.get("physical_source"),
                "source_row_sha256": base_objects[0].sha256,
                "treatment": treatment,
                "relation_contract_sha256": relation.get("relation_contract_sha256"),
                "repository_owner": relation.get("repository_owner"),
                "domain": {
                    "path": relation.get("domain_path"),
                    "type": relation.get("domain_type"),
                    "kind": relation.get("domain_kind"),
                },
                "mapper": relation.get("mapper"),
                "columns": columns,
                "primary_key": primary_key,
                "foreign_keys": [
                    _object_provenance(item)
                    for item in assigned
                    if item.object_type == "FK CONSTRAINT"
                ],
                "unique_constraints": [
                    _object_provenance(item)
                    for item in assigned
                    if item.object_type == "CONSTRAINT"
                    and _constraint_semantics(item)["kind"] == "UNIQUE"
                ],
                "check_constraints": checks,
                "indexes": [
                    _object_provenance(item)
                    for item in assigned
                    if item.object_type == "INDEX"
                ],
                "triggers": [
                    _object_provenance(item)
                    for item in assigned
                    if item.object_type == "TRIGGER"
                ],
                "physical_object_provenance": [
                    _object_provenance(item) for item in assigned
                ],
            }
        )

    treatments: dict[str, int] = {}
    for row in rows:
        treatment = cast(str, row["treatment"])
        treatments[treatment] = treatments.get(treatment, 0) + 1
    if (
        len(rows) != 104
        or primary_key_count != 103
        or treatments
        != {
            "EXPLICIT_BIDIRECTIONAL_SCALAR_MAPPER": 102,
            "GENERATED_METADATA_ONLY_NO_RUNTIME_MAPPER_OR_PORT": 1,
            "READ_ONLY_EXPLICIT_FROM_ROW_MAPPER_NO_DML": 1,
        }
        or generated_columns
        != ["ai.evaluation_case_result.zero_tolerance_failure_count"]
        or physical_object_assignment_count != EXPECTED_ST0304_RELATION_OBJECT_COUNT
        or physical_object_assignment_count != relevant_count
    ):
        _fail("CATALOG_IR_COVERAGE_MISMATCH")

    mapper_pairs = tuple(
        cast(Mapping[str, Any], row["mapper"])
        for row in rows
        if row["treatment"] == "EXPLICIT_BIDIRECTIONAL_SCALAR_MAPPER"
    )
    if len(mapper_pairs) != 102 or any(
        not mapper.get("from_row") or not mapper.get("to_row")
        for mapper in mapper_pairs
    ):
        _fail("CATALOG_IR_MAPPER_INVENTORY_MISMATCH")
    view_mapper = cast(
        Mapping[str, Any],
        next(
            row["mapper"]
            for row in rows
            if row["relation"] == "catalog.v_safe_offer_current"
        ),
    )
    inbox_mapper = next(
        row["mapper"] for row in rows if row["relation"] == "ops.inbox_receipt"
    )
    if (
        not view_mapper.get("from_row")
        or view_mapper.get("to_row") is not None
        or inbox_mapper is not None
    ):
        _fail("CATALOG_IR_MAPPER_INVENTORY_MISMATCH")

    inventory = {
        "schemas": list(EXPECTED_RUNTIME_SCHEMAS),
        "relations": 104,
        "tables": 103,
        "views": 1,
        "columns": sum(len(cast(list[object], row["columns"])) for row in rows),
        "check_constraints": sum(
            len(cast(list[object], row["check_constraints"])) for row in rows
        ),
        "generated_columns": generated_columns,
        "treatments": treatments,
        "repository_owned_relations": len(ownership_counts[0]),
        "repository_excluded_relations": list(ownership_counts[1]),
        "st0304_physical_objects": len(objects),
        "st0304_relation_object_assignments": relevant_count,
    }
    if inventory["columns"] != 1376 or inventory["check_constraints"] != 519:
        _fail("CATALOG_IR_COUNT_MISMATCH")
    ir = {
        "document": {
            "id": "ST0308-PERSISTENCE-CATALOG-IR-001",
            "version": "1.0.0",
            "story_id": "ST-0308",
            "status": "LOCAL_GENERATOR_INPUT_IR",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
        },
        "source_contract": RUNTIME_CONTRACT_PATH.as_posix(),
        "source_catalogs": {
            ST0303_CATALOG_PATH.as_posix(): _semantic_sha256(st0303_catalog),
            ST0304_CATALOG_PATH.as_posix(): _semantic_sha256(st0304_catalog),
        },
        "inventory": inventory,
        "closed_owner_outputs": [path.as_posix() for path in OWNER_OUTPUT_PATHS],
        "target_runtime_inventory": {
            "schema_modules": list(EXPECTED_RUNTIME_SCHEMAS),
            "sqlalchemy_table_relations": [
                cast(str, row["relation"]) for row in rows if row["kind"] == "TABLE"
            ],
            "read_only_view_relations": ["catalog.v_safe_offer_current"],
            "bidirectional_mapper_relations": [
                cast(str, row["relation"])
                for row in rows
                if row["treatment"] == "EXPLICIT_BIDIRECTIONAL_SCALAR_MAPPER"
            ],
            "from_only_mapper_relations": ["catalog.v_safe_offer_current"],
            "metadata_only_no_mapper_relations": ["ops.inbox_receipt"],
        },
        "relations": rows,
    }
    return MappingProxyType(ir)


def _validate_complete_inventory(
    root: Path,
    runtime: Mapping[str, Any],
    matrices: Mapping[str, Mapping[str, Any]],
) -> tuple[
    Mapping[str, Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
    tuple[Mapping[str, Any], ...],
    tuple[tuple[str, ...], tuple[str, ...]],
    Mapping[str, Any],
]:
    st0303_catalog = _load_json(root, ST0303_CATALOG_PATH)
    st0303 = _catalog_tables(st0303_catalog)
    st0304_catalog = _load_json(root, ST0304_CATALOG_PATH)
    st0304_tables, st0304_views = _st0304_inventory(st0304_catalog)
    physical_rows = _list(runtime.get("physical_fragments"), "PHYSICAL_INPUTS_INVALID")
    catalog_physical_rows = _list(
        st0304_catalog.get("physical_fragments"),
        "ST0304_PHYSICAL_FRAGMENT_INVENTORY_INVALID",
    )
    if len(catalog_physical_rows) != len(physical_rows):
        _fail("ST0304_PHYSICAL_FRAGMENT_INVENTORY_INVALID")
    for expected_path, raw_runtime_row, raw_catalog_row in zip(
        EXPECTED_PHYSICAL_FRAGMENT_PATHS,
        physical_rows,
        catalog_physical_rows,
        strict=True,
    ):
        runtime_row = _mapping(raw_runtime_row, "PHYSICAL_INPUT_INVALID")
        catalog_row = _mapping(
            raw_catalog_row, "ST0304_PHYSICAL_FRAGMENT_INVENTORY_INVALID"
        )
        _expect_keys(
            catalog_row,
            ("path", "sha256"),
            "ST0304_PHYSICAL_FRAGMENT_INVENTORY_INVALID",
        )
        if (
            runtime_row.get("path") != expected_path
            or catalog_row.get("path") != f"repo://{expected_path}"
            or catalog_row.get("sha256") != runtime_row.get("sha256")
        ):
            _fail("ST0304_PHYSICAL_FRAGMENT_INVENTORY_INVALID")
    fragment_paths = tuple(
        _relative_path(
            _mapping(row, "PHYSICAL_INPUT_INVALID").get("path"),
            "PHYSICAL_INPUT_INVALID",
        )
        for row in physical_rows
    )
    parsed_st0304 = _parse_st0304_tables(root, fragment_paths)
    physical_objects = _parse_st0304_objects(root, physical_rows)
    _validate_st0304_object_inventory(st0304_catalog, physical_objects)
    if set(parsed_st0304) != st0304_tables:
        _fail("ST0304_PHYSICAL_CATALOG_MISMATCH")

    domain_mapper = matrices["domain_mapper"]
    relations = _relation_index(domain_mapper)
    expected_all = set(st0303) | st0304_tables | st0304_views
    if set(relations) != expected_all:
        _fail("PHYSICAL_MAPPER_RELATION_MISMATCH")
    inventory = _mapping(runtime.get("inventory"), "RUNTIME_INVENTORY_INVALID")
    if (
        inventory.get("tables") != 103
        or inventory.get("views") != ["catalog.v_safe_offer_current"]
        or len(st0303) != 17
        or len(st0304_tables) != 86
        or st0304_views != {"catalog.v_safe_offer_current"}
    ):
        _fail("RUNTIME_INVENTORY_MISMATCH")

    for name, table in st0303.items():
        columns_list: list[tuple[str, str, bool, str | None]] = []
        for raw in _list(table.get("columns"), "ST0303_COLUMNS_INVALID"):
            column = _mapping(raw, "ST0303_COLUMN_INVALID")
            nullable = column.get("nullable")
            default = column.get("default")
            if type(nullable) is not bool or (
                default is not None and type(default) is not str
            ):
                _fail("ST0303_COLUMN_INVALID")
            columns_list.append(
                (
                    _text(column.get("name"), "ST0303_COLUMN_INVALID"),
                    _text(column.get("type"), "ST0303_COLUMN_INVALID"),
                    nullable,
                    default,
                )
            )
        columns = tuple(columns_list)
        if columns != _column_projection(relations[name]):
            _fail("ST0303_PHYSICAL_MAPPER_COLUMN_MISMATCH")
    for name, columns in parsed_st0304.items():
        if columns != _column_projection(relations[name]):
            _fail("ST0304_PHYSICAL_MAPPER_COLUMN_MISMATCH")

    ownership_counts = _validate_repository_ownership(
        matrices["repository_surface"], relations
    )
    if len(ownership_counts[0]) != 103 or ownership_counts[1] != ("ops.inbox_receipt",):
        _fail("REPOSITORY_RELATION_COUNT_MISMATCH")
    concurrency = matrices["concurrency"]
    lock_matrix = _mapping(concurrency.get("lock_version_cas"), "CONCURRENCY_INVALID")
    lock_relations = set(
        _text(value, "CONCURRENCY_INVALID")
        for value in _list(lock_matrix.get("relations"), "CONCURRENCY_INVALID")
    )
    physical_lock_relations = {
        name
        for name, relation in relations.items()
        if any(column[0] == "lock_version" for column in _column_projection(relation))
    }
    if lock_relations != physical_lock_relations or len(lock_relations) != 27:
        _fail("LOCK_VERSION_MATRIX_MISMATCH")
    state_relations = set(
        _text(value, "STATE_CAS_INVALID")
        for value in _list(
            _mapping(
                concurrency.get("state_cas_without_lock_version"),
                "STATE_CAS_INVALID",
            ).get("relations"),
            "STATE_CAS_INVALID",
        )
    )
    state_matrix_relations = set(
        _mapping(matrices["state_cas"].get("relations"), "STATE_CAS_INVALID")
    )
    if (
        state_relations != state_matrix_relations
        or len(state_relations) != 24
        or state_relations & lock_relations
    ):
        _fail("STATE_CAS_MATRIX_MISMATCH")
    _validate_state_cas_method_ownership(
        repository_surface=matrices["repository_surface"],
        state_cas=matrices["state_cas"],
        relations=relations,
    )
    _validate_idempotency_outcome_contract(matrices["idempotency"])

    uow_modules = _mapping(matrices["uow_surface"].get("modules"), "UOW_INVALID")
    repository_modules = _mapping(
        matrices["repository_surface"].get("modules"), "REPOSITORIES_INVALID"
    )
    if set(uow_modules) != set(repository_modules):
        _fail("UOW_REPOSITORY_MODULE_MISMATCH")
    for module_name, raw_properties in uow_modules.items():
        properties = set(_list(raw_properties, "UOW_INVALID"))
        if properties != set(
            _mapping(repository_modules[module_name], "REPOSITORIES_INVALID")
        ):
            _fail("UOW_REPOSITORY_SURFACE_MISMATCH")

    events = _list(matrices["event_emission"].get("allowlist"), "EVENTS_INVALID")
    event_types: set[str] = set()
    for raw in events:
        row = _list(raw, "EVENTS_INVALID")
        if len(row) != 5:
            _fail("EVENTS_INVALID")
        event_type, schema_hash, aggregate_type, version_source, owning_method = (
            _text(value, "EVENTS_INVALID") for value in row
        )
        del aggregate_type, version_source, owning_method
        if SHA256_PATTERN.fullmatch(schema_hash) is None:
            _fail("EVENTS_INVALID")
        _verify_digest(root, _event_schema_path(event_type), schema_hash)
        event_types.add(event_type)
    if len(events) != 18 or len(event_types) != 18:
        _fail("EVENT_REGISTRY_MISMATCH")
    identity_profiles = _mapping(
        matrices["identity"].get("profiles"), "IDENTITY_INVALID"
    )
    composition = _mapping(
        matrices["uow_surface"].get("composition"), "UOW_COMPOSITION_INVALID"
    )
    allowed_profiles = {
        name
        for name, raw in identity_profiles.items()
        if _mapping(raw, "IDENTITY_INVALID").get("st0308_allowed") is True
    }
    if allowed_profiles != {"API_COMMAND", "WORKER_COMMAND"} or allowed_profiles != set(
        composition
    ):
        _fail("IDENTITY_COMPOSITION_MISMATCH")
    triggers = tuple(
        _mapping(raw, "ST0303_TRIGGER_INVALID")
        for raw in _list(st0303_catalog.get("triggers"), "ST0303_TRIGGERS_INVALID")
        if _mapping(raw, "ST0303_TRIGGER_INVALID").get("table") in SLICE_RELATIONS
    )
    if {
        _text(trigger.get("name"), "ST0303_TRIGGER_INVALID") for trigger in triggers
    } != {
        "trg_ops_object_artifact_immutable",
        "trg_ops_audit_event_immutable",
    }:
        _fail("ST0303_TRIGGER_MISMATCH")
    catalog_ir = _build_catalog_ir(
        runtime=runtime,
        relations=relations,
        st0303_catalog=st0303_catalog,
        st0303=st0303,
        st0304_catalog=st0304_catalog,
        objects=physical_objects,
        ownership_counts=ownership_counts,
    )
    return relations, st0303, triggers, ownership_counts, catalog_ir


def _validate_runtime(
    root: Path,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
    tuple[Mapping[str, Any], ...],
    tuple[tuple[str, ...], tuple[str, ...]],
    Mapping[str, Any],
    Mapping[str, str],
]:
    runtime = _load_yaml_at(root, RUNTIME_CONTRACT_PATH)
    _validate_product_contract(runtime)

    source_hashes: dict[str, str] = {
        RUNTIME_CONTRACT_PATH.as_posix(): _sha256(_read(root, RUNTIME_CONTRACT_PATH)),
    }
    for raw in _list(runtime.get("sources"), "RUNTIME_SOURCES_INVALID"):
        row = _mapping(raw, "RUNTIME_SOURCE_INVALID")
        relative = _relative_path(row.get("path"), "RUNTIME_SOURCE_INVALID")
        source_hashes[relative.as_posix()] = _verify_digest(
            root, relative, row.get("sha256")
        )
    identity_runtime = _mapping(
        runtime.get("identity_runtime"), "IDENTITY_RUNTIME_INVALID"
    )
    semantic_anchor = _mapping(
        identity_runtime.get("semantic_anchor"), "IDENTITY_RUNTIME_INVALID"
    )
    anchor_path = _relative_path(
        semantic_anchor.get("path"), "IDENTITY_RUNTIME_INVALID"
    ).as_posix()
    anchor_hash = _text(semantic_anchor.get("sha256"), "IDENTITY_RUNTIME_INVALID")
    if anchor_path not in source_hashes or SHA256_PATTERN.fullmatch(anchor_hash) is None:
        _fail("IDENTITY_SEMANTIC_ANCHOR_MISMATCH")
    fragment_paths: set[str] = set()
    for raw in _list(runtime.get("physical_fragments"), "PHYSICAL_INPUTS_INVALID"):
        row = _mapping(raw, "PHYSICAL_INPUT_INVALID")
        relative = _relative_path(row.get("path"), "PHYSICAL_INPUT_INVALID")
        fragment_paths.add(relative.as_posix())
        source_hashes[relative.as_posix()] = _verify_digest(
            root, relative, row.get("sha256")
        )
    if len(fragment_paths) != 11:
        _fail("PHYSICAL_FRAGMENT_INVENTORY_INVALID")

    raw_matrices = _mapping(runtime.get("executable_matrices"), "MATRICES_INVALID")
    if tuple(raw_matrices) != MATRIX_KEYS:
        _fail("MATRIX_INVENTORY_INVALID")
    matrices: dict[str, Mapping[str, Any]] = {}
    matrix_hashes: dict[str, str] = {}
    for key in MATRIX_KEYS:
        row = _mapping(raw_matrices[key], "MATRIX_INVALID")
        relative = _relative_path(row.get("path"), "MATRIX_INVALID")
        digest = _verify_digest(root, relative, row.get("sha256"))
        matrix_hashes[key] = digest
        matrices[key] = _load_yaml_at(root, relative)
    for raw in _list(matrices["event_emission"].get("allowlist"), "EVENTS_INVALID"):
        event_row = _list(raw, "EVENTS_INVALID")
        if len(event_row) != 5:
            _fail("EVENTS_INVALID")
        event_type = _text(event_row[0], "EVENTS_INVALID")
        schema_path = _event_schema_path(event_type)
        source_hashes[schema_path.as_posix()] = _verify_digest(
            root, schema_path, event_row[1]
        )
    representative = _mapping(
        _mapping(runtime.get("representative_slices"), "SLICE_INVALID").get(
            "ops_reference"
        ),
        "SLICE_INVALID",
    )
    slice_path = _relative_path(representative.get("path"), "SLICE_INVALID")
    if slice_path != OPS_SLICE_PATH:
        _fail("SLICE_INVALID")
    source_hashes[slice_path.as_posix()] = _verify_digest(
        root, slice_path, representative.get("sha256")
    )
    (
        relations,
        st0303,
        triggers,
        ownership_counts,
        catalog_ir,
    ) = _validate_complete_inventory(root, runtime, matrices)
    return (
        runtime,
        MappingProxyType(matrices),
        relations,
        st0303,
        triggers,
        ownership_counts,
        catalog_ir,
        MappingProxyType(
            {
                **source_hashes,
                **{f"matrix:{key}": value for key, value in matrix_hashes.items()},
            }
        ),
    )


def _sqlalchemy_type(physical_type: str) -> str:
    known = {
        "uuid": "Uuid(as_uuid=True)",
        "text": "Text()",
        "bigint": "BigInteger()",
        "boolean": "Boolean()",
        "integer": "Integer()",
        "smallint": "SmallInteger()",
        "jsonb": "JSONB()",
        "timestamptz": "DateTime(timezone=True)",
    }
    result = known.get(physical_type)
    if result is None:
        _fail("SLICE_SQL_TYPE_UNSUPPORTED")
    return result


def _render_table(
    name: str, relation: Mapping[str, Any], table: Mapping[str, Any]
) -> str:
    lines = [
        f"{name}: Final[Table] = Table(",
        f"    {relation['relation'].split('.', 1)[1]!r},",
        "    METADATA,",
    ]
    primary_key = tuple(
        _text(value, "SLICE_TABLE_INVALID")
        for value in _list(table.get("primary_key"), "SLICE_TABLE_INVALID")
    )
    foreign_keys: dict[str, Mapping[str, Any]] = {}
    for raw in _list(table.get("foreign_keys"), "SLICE_TABLE_INVALID"):
        foreign_key = _mapping(raw, "SLICE_TABLE_INVALID")
        columns = tuple(
            _text(value, "SLICE_TABLE_INVALID")
            for value in _list(foreign_key.get("columns"), "SLICE_TABLE_INVALID")
        )
        referenced_columns = tuple(
            _text(value, "SLICE_TABLE_INVALID")
            for value in _list(
                foreign_key.get("referenced_columns"), "SLICE_TABLE_INVALID"
            )
        )
        if len(columns) != 1 or len(referenced_columns) != 1:
            _fail("SLICE_FOREIGN_KEY_UNSUPPORTED")
        if columns[0] in foreign_keys:
            _fail("SLICE_FOREIGN_KEY_DUPLICATE")
        foreign_keys[columns[0]] = foreign_key
    for raw in _list(relation.get("physical_columns"), "SLICE_COLUMNS_INVALID"):
        column = _mapping(raw, "SLICE_COLUMN_INVALID")
        column_name = _text(column.get("physical_column"), "SLICE_COLUMN_INVALID")
        arguments = [
            repr(column_name),
            _sqlalchemy_type(
                _text(column.get("physical_sql_type"), "SLICE_COLUMN_INVALID")
            ),
        ]
        column_foreign_key = foreign_keys.get(column_name)
        if column_foreign_key is not None:
            reference = _text(
                column_foreign_key.get("references"), "SLICE_TABLE_INVALID"
            )
            referenced_column = _text(
                _list(
                    column_foreign_key.get("referenced_columns"),
                    "SLICE_TABLE_INVALID",
                )[0],
                "SLICE_TABLE_INVALID",
            )
            arguments.append(
                "ForeignKey("
                f"{f'{reference}.{referenced_column}'!r}, "
                f"name={column_foreign_key.get('name')!r}, "
                f"ondelete={column_foreign_key.get('on_delete')!r}, "
                f"deferrable={column_foreign_key.get('deferrable')!r}"
                ")"
            )
        arguments.append(f"nullable={column.get('nullable')!r}")
        default = column.get("server_default")
        if default is not None:
            arguments.append(f"server_default=text({default!r})")
        lines.append(f"    Column({', '.join(arguments)}),")
    primary_columns = ", ".join(repr(value) for value in primary_key)
    lines.append(
        "    PrimaryKeyConstraint("
        f"{primary_columns}, name={table.get('primary_key_name')!r}),"
    )
    for raw in _list(table.get("check_constraints"), "SLICE_TABLE_INVALID"):
        constraint = _mapping(raw, "SLICE_TABLE_INVALID")
        lines.append(
            "    CheckConstraint("
            f"{constraint.get('expression')!r}, name={constraint.get('name')!r}),"
        )
    for raw in _list(table.get("unique_constraints"), "SLICE_TABLE_INVALID"):
        constraint = _mapping(raw, "SLICE_TABLE_INVALID")
        unique_columns_text = ", ".join(
            repr(value) for value in constraint.get("columns", ())
        )
        lines.append(
            "    UniqueConstraint("
            f"{unique_columns_text}, name={constraint.get('name')!r}),"
        )
    for raw in _list(table.get("indexes"), "SLICE_TABLE_INVALID"):
        index = _mapping(raw, "SLICE_TABLE_INVALID")
        if index.get("expression") is not None or index.get("include") != []:
            _fail("SLICE_INDEX_UNSUPPORTED")
        index_columns_text = ", ".join(
            repr(_text(value, "SLICE_TABLE_INVALID"))
            for value in _list(index.get("columns"), "SLICE_TABLE_INVALID")
        )
        arguments = [repr(index.get("name")), index_columns_text]
        arguments.append(f"unique={index.get('unique')!r}")
        arguments.append(f"postgresql_using={index.get('method')!r}")
        if index.get("where") is not None:
            arguments.append(f"postgresql_where=text({index.get('where')!r})")
        if index.get("nulls_not_distinct") is True:
            arguments.append("postgresql_nulls_not_distinct=True")
        lines.append(f"    Index({', '.join(arguments)}),")
    lines.extend(("    schema='ops',", ")", ""))
    return "\n".join(lines)


def _catalog_column_type(physical_type: str) -> tuple[str, str | None]:
    declaration = physical_type
    computed: str | None = None
    if " GENERATED ALWAYS AS " in declaration:
        declaration, generated = declaration.split(" GENERATED ALWAYS AS ", 1)
        if not generated.endswith(" STORED"):
            _fail("CATALOG_GENERATED_COLUMN_INVALID")
        computed = generated.removesuffix(" STORED")
        if not computed.startswith("(") or not computed.endswith(")"):
            _fail("CATALOG_GENERATED_COLUMN_INVALID")
    declaration = re.sub(
        r' CONSTRAINT "[a-z][a-z0-9_]*"\Z',
        "",
        declaration,
    ).replace('"', "")
    known = {
        "uuid": "Uuid(as_uuid=True)",
        "text": "Text()",
        "text[]": "ARRAY(Text())",
        "bigint": "BigInteger()",
        "boolean": "Boolean()",
        "date": "Date()",
        "integer": "Integer()",
        "smallint": "SmallInteger()",
        "jsonb": "JSONB()",
        "timestamptz": "DateTime(timezone=True)",
        "timestamp with time zone": "DateTime(timezone=True)",
        "numeric": "Numeric()",
    }
    result = known.get(declaration)
    if result is None:
        numeric = re.fullmatch(
            r"numeric\((?P<precision>[0-9]+),(?P<scale>[0-9]+)\)", declaration
        )
        if numeric is None:
            _fail("CATALOG_SQL_TYPE_UNSUPPORTED")
        result = f"Numeric({numeric.group('precision')}, {numeric.group('scale')})"
    return result, computed


def _catalog_server_default(value: object) -> str | None:
    if value is None:
        return None
    default = _text(value, "CATALOG_COLUMN_DEFAULT_INVALID")
    return re.sub(
        r' CONSTRAINT "[a-z][a-z0-9_]*"\Z',
        "",
        default,
    )


def _catalog_semantics(value: object, code: str) -> Mapping[str, Any]:
    row = _mapping(value, code)
    semantics = row.get("semantics")
    return row if semantics is None else _mapping(semantics, code)


def _catalog_foreign_key_arguments(value: object) -> tuple[str, ...]:
    row = _catalog_semantics(value, "CATALOG_FOREIGN_KEY_INVALID")
    columns = _text_tuple(row.get("columns"), "CATALOG_FOREIGN_KEY_INVALID")
    referenced_columns = _text_tuple(
        row.get("referenced_columns"), "CATALOG_FOREIGN_KEY_INVALID"
    )
    reference = _text(row.get("references"), "CATALOG_FOREIGN_KEY_INVALID")
    if not columns or len(columns) != len(referenced_columns):
        _fail("CATALOG_FOREIGN_KEY_INVALID")
    arguments = [
        repr(list(columns)),
        repr([f"{reference}.{column}" for column in referenced_columns]),
        f"name={_text(row.get('name'), 'CATALOG_FOREIGN_KEY_INVALID')!r}",
    ]
    tail = row.get("tail")
    if tail is None:
        on_delete = row.get("on_delete")
        if on_delete is not None:
            arguments.append(
                f"ondelete={_text(on_delete, 'CATALOG_FOREIGN_KEY_INVALID')!r}"
            )
        deferrable = row.get("deferrable")
        initially_deferred = row.get("initially_deferred")
        if type(deferrable) is not bool or type(initially_deferred) is not bool:
            _fail("CATALOG_FOREIGN_KEY_INVALID")
        arguments.append(f"deferrable={deferrable!r}")
        if initially_deferred:
            arguments.append("initially='DEFERRED'")
        return tuple(arguments)
    tail_text = _text(tail, "CATALOG_FOREIGN_KEY_INVALID")
    on_delete_match = re.search(r" ON DELETE (RESTRICT|SET NULL|CASCADE)", tail_text)
    if on_delete_match is not None:
        arguments.append(f"ondelete={on_delete_match.group(1)!r}")
        tail_text = tail_text.replace(on_delete_match.group(0), "", 1)
    if " DEFERRABLE INITIALLY DEFERRED" in tail_text:
        arguments.extend(("deferrable=True", "initially='DEFERRED'"))
        tail_text = tail_text.replace(" DEFERRABLE INITIALLY DEFERRED", "", 1)
    if tail_text:
        _fail("CATALOG_FOREIGN_KEY_INVALID")
    return tuple(arguments)


def _catalog_index_arguments(
    value: object,
    *,
    relation: str,
) -> tuple[str, ...]:
    raw = _mapping(value, "CATALOG_INDEX_INVALID")
    semantics_value = raw.get("semantics")
    if semantics_value is None:
        name = _text(raw.get("name"), "CATALOG_INDEX_INVALID")
        unique = raw.get("unique")
        method = _text(raw.get("method"), "CATALOG_INDEX_INVALID")
        columns = _text_tuple(raw.get("columns"), "CATALOG_INDEX_INVALID")
        expression = raw.get("expression")
        if expression is not None and type(expression) is not str:
            _fail("CATALOG_INDEX_INVALID")
        if expression is not None and columns:
            _fail("CATALOG_INDEX_INVALID")
        expressions = (expression,) if expression is not None else columns
        where = raw.get("where")
        include = _text_tuple(raw.get("include"), "CATALOG_INDEX_INVALID")
        nulls_not_distinct = raw.get("nulls_not_distinct")
    else:
        semantics = _mapping(semantics_value, "CATALOG_INDEX_INVALID")
        schema, table = relation.split(".", 1)
        if semantics.get("schema") != schema or semantics.get("table") != table:
            _fail("CATALOG_INDEX_INVALID")
        name = _text(semantics.get("name"), "CATALOG_INDEX_INVALID")
        unique = semantics.get("unique")
        method = _text(semantics.get("method"), "CATALOG_INDEX_INVALID")
        expressions = _text_tuple(semantics.get("expressions"), "CATALOG_INDEX_INVALID")
        where = semantics.get("where")
        include = ()
        nulls_not_distinct = semantics.get("nulls_not_distinct")
    if (
        type(unique) is not bool
        or type(nulls_not_distinct) is not bool
        or not expressions
        or (where is not None and type(where) is not str)
    ):
        _fail("CATALOG_INDEX_INVALID")
    rendered_expressions: list[str] = []
    for expression in expressions:
        simple = re.fullmatch(r'"?(?P<column>[a-z][a-z0-9_]*)"?', expression)
        rendered_expressions.append(
            repr(simple.group("column"))
            if simple is not None
            else f"text({expression!r})"
        )
    arguments = [repr(name), *rendered_expressions]
    arguments.extend((f"unique={unique!r}", f"postgresql_using={method!r}"))
    if where is not None:
        arguments.append(f"postgresql_where=text({where!r})")
    if include:
        arguments.append(f"postgresql_include={include!r}")
    if nulls_not_distinct:
        arguments.append("postgresql_nulls_not_distinct=True")
    return tuple(arguments)


def _canonical_metric_units(
    objects: tuple[_PhysicalObject, ...],
) -> Mapping[str, str]:
    """Extract the only schema function referenced by a physical CHECK."""

    candidates = tuple(
        item
        for item in objects
        if item.schema == "ai"
        and item.object_type == "FUNCTION"
        and item.name == 'canonical_metric_unit("text")'
    )
    if len(candidates) != 1:
        _fail("CHECK_FUNCTION_SOURCE_INVALID")
    case = re.search(
        r"SELECT CASE\s+(?P<body>.*?)\s+ELSE NULL\s+END",
        candidates[0].sql,
        re.DOTALL,
    )
    if case is None:
        _fail("CHECK_FUNCTION_SOURCE_INVALID")
    clause_pattern = re.compile(
        r"\s*WHEN p_metric_code IN \((?P<members>.*?)\) THEN\s*"
        r"'(?P<in_unit>[^']+)'|\s*WHEN p_metric_code = '(?P<member>[^']+)' "
        r"THEN\s*'(?P<equal_unit>[^']+)'",
        re.DOTALL,
    )
    units: dict[str, str] = {}
    cursor = 0
    clauses = 0
    for match in clause_pattern.finditer(case.group("body")):
        if case.group("body")[cursor : match.start()].strip():
            _fail("CHECK_FUNCTION_SOURCE_INVALID")
        cursor = match.end()
        clauses += 1
        if match.group("members") is not None:
            members_source = cast(str, match.group("members"))
            literal_pattern = re.compile(r"'((?:''|[^'])*)'")
            members = tuple(
                literal.replace("''", "'")
                for literal in literal_pattern.findall(members_source)
            )
            residue = literal_pattern.sub("", members_source)
            if (
                not members
                or residue.replace(",", "").strip()
                or match.group("in_unit") is None
            ):
                _fail("CHECK_FUNCTION_SOURCE_INVALID")
            unit = cast(str, match.group("in_unit"))
        else:
            member = match.group("member")
            unit = match.group("equal_unit")
            if member is None or unit is None:
                _fail("CHECK_FUNCTION_SOURCE_INVALID")
            members = (member,)
        for member in members:
            if member in units or not member or not unit:
                _fail("CHECK_FUNCTION_SOURCE_INVALID")
            units[member] = unit
    if case.group("body")[cursor:].strip() or clauses != 6 or len(units) != 31:
        _fail("CHECK_FUNCTION_SOURCE_INVALID")
    if sum(unit == "ratio" for unit in units.values()) != 24:
        _fail("CHECK_FUNCTION_SOURCE_INVALID")
    return MappingProxyType(dict(sorted(units.items())))


def _physical_column_rule(physical_type: str) -> tuple[object, ...]:
    """Compile one physical type to an exact non-normalizing runtime rule."""

    base = physical_type.split(" GENERATED ALWAYS AS ", 1)[0]
    base = base.split(" CONSTRAINT ", 1)[0]
    normalized = base.replace('"', "").strip().lower()
    numeric = re.fullmatch(
        r"numeric(?:\((?P<precision>\d+),(?P<scale>\d+)\))?", normalized
    )
    if numeric is not None:
        if numeric.group("precision") is None:
            return ("numeric", None, None)
        precision = int(cast(str, numeric.group("precision")))
        scale = int(cast(str, numeric.group("scale")))
        if precision <= 0 or scale < 0 or scale > precision:
            _fail("CHECK_COLUMN_TYPE_UNSUPPORTED")
        return ("numeric", precision, scale)
    known = {
        "bigint": ("integer", -(1 << 63), (1 << 63) - 1),
        "boolean": ("boolean",),
        "date": ("date",),
        "integer": ("integer", -(1 << 31), (1 << 31) - 1),
        "jsonb": ("jsonb",),
        "smallint": ("integer", -(1 << 15), (1 << 15) - 1),
        "text": ("text",),
        "text[]": ("text_array",),
        "timestamp with time zone": ("timestamptz",),
        "timestamptz": ("timestamptz",),
        "uuid": ("uuid",),
    }
    result = known.get(normalized)
    if result is None:
        _fail("CHECK_COLUMN_TYPE_UNSUPPORTED")
    return result


def _compile_physical_constraint_inventory(
    catalog_ir: Mapping[str, Any],
) -> Mapping[str, object]:
    """Compile every physical CHECK and mapper column to closed runtime data."""

    checks_by_relation: dict[str, tuple[tuple[object, ...], ...]] = {}
    columns_by_relation: dict[str, tuple[tuple[object, ...], ...]] = {}
    mapper_callables: dict[str, tuple[object, ...]] = {}
    inventory: list[tuple[str, str, str, str]] = []
    check_count = 0
    for raw_relation in _list(catalog_ir.get("relations"), "CATALOG_RELATIONS_INVALID"):
        relation = _mapping(raw_relation, "CATALOG_RELATION_INVALID")
        relation_name = _text(relation.get("relation"), "CATALOG_RELATION_INVALID")
        raw_columns = _list(relation.get("columns"), "CATALOG_COLUMNS_INVALID")
        column_names = tuple(
            _text(
                _mapping(raw_column, "CATALOG_COLUMN_INVALID").get("physical_column"),
                "CATALOG_COLUMN_INVALID",
            )
            for raw_column in raw_columns
        )
        if not column_names or len(column_names) != len(set(column_names)):
            _fail("CHECK_COLUMN_INVENTORY_INVALID")
        column_set = frozenset(column_names)
        column_rules: list[tuple[object, ...]] = []
        for raw_column in raw_columns:
            column = _mapping(raw_column, "CATALOG_COLUMN_INVALID")
            nullable = column.get("nullable")
            if type(nullable) is not bool:
                _fail("CHECK_COLUMN_INVENTORY_INVALID")
            column_rules.append(
                (
                    _text(column.get("physical_column"), "CATALOG_COLUMN_INVALID"),
                    nullable,
                    _physical_column_rule(
                        _text(column.get("physical_sql_type"), "CATALOG_COLUMN_INVALID")
                    ),
                )
            )
        columns_by_relation[relation_name] = tuple(column_rules)

        compiled_checks: list[tuple[object, ...]] = []
        for raw_check in _list(
            relation.get("check_constraints"), "CATALOG_CHECKS_INVALID"
        ):
            check = _mapping(raw_check, "CATALOG_CHECK_INVALID")
            name = _text(check.get("name"), "CATALOG_CHECK_INVALID")
            expression = _text(check.get("expression"), "CATALOG_CHECK_INVALID")
            expression_sha256 = _sha256(expression.encode("utf-8"))
            ast = _CheckExpressionParser(expression, column_set).parse()
            compiled_checks.append((name, expression_sha256, ast))
            inventory.append(
                (relation_name, name, "EXACT_RUNTIME_AST", expression_sha256)
            )
            check_count += 1
        checks_by_relation[relation_name] = tuple(compiled_checks)

        mapper = relation.get("mapper")
        if mapper is None:
            continue
        mapper_contract = _mapping(mapper, "MAPPER_CONTRACT_INVALID")
        from_row = _text(mapper_contract.get("from_row"), "MAPPER_CONTRACT_INVALID")
        to_row = mapper_contract.get("to_row")
        if from_row in mapper_callables:
            _fail("CHECK_MAPPER_CALLABLE_DUPLICATE")
        mapper_callables[from_row] = (relation_name, "from_row", column_names)
        if to_row is not None:
            to_row_name = _text(to_row, "MAPPER_CONTRACT_INVALID")
            if to_row_name in mapper_callables:
                _fail("CHECK_MAPPER_CALLABLE_DUPLICATE")
            mapper_callables[to_row_name] = (relation_name, "to_row", column_names)
    if (
        len(checks_by_relation) != 104
        or len(columns_by_relation) != 104
        or check_count != 519
        or len(inventory) != 519
        or len(set((row[0], row[1]) for row in inventory)) != 519
        or len(mapper_callables) != 205
    ):
        _fail("CHECK_RUNTIME_INVENTORY_MISMATCH")
    return MappingProxyType(
        {
            "checks_by_relation": MappingProxyType(
                dict(sorted(checks_by_relation.items()))
            ),
            "columns_by_relation": MappingProxyType(
                dict(sorted(columns_by_relation.items()))
            ),
            "mapper_callables": MappingProxyType(
                dict(sorted(mapper_callables.items()))
            ),
            "inventory": tuple(sorted(inventory)),
        }
    )


def _render_physical_constraints(
    *,
    compiled: Mapping[str, object],
    canonical_metric_units: Mapping[str, str],
    owner_hash: str,
    source_hashes: Mapping[str, str],
    matrix_hashes: Mapping[str, str],
) -> bytes:
    """Render inert constraint ASTs; execution remains adapter-private."""

    checks = dict(
        cast(
            Mapping[str, tuple[tuple[object, ...], ...]], compiled["checks_by_relation"]
        )
    )
    columns = dict(
        cast(
            Mapping[str, tuple[tuple[object, ...], ...]],
            compiled["columns_by_relation"],
        )
    )
    callables = dict(
        cast(Mapping[str, tuple[object, ...]], compiled["mapper_callables"])
    )
    inventory = cast(tuple[tuple[str, str, str, str], ...], compiled["inventory"])
    lines = [
        '"""Generated exact physical CHECK runtime inventory for ST-0308.\n\nDo not edit; run scripts/build_st0308_persistence.py.\n"""',
        "",
        "# fmt: off",
        "from __future__ import annotations",
        "",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        f"OWNER_GENERATOR_SHA256: Final = {owner_hash!r}",
        f"SOURCE_SHA256: Final = MappingProxyType({dict(sorted(source_hashes.items()))!r})",
        f"MATRIX_SHA256: Final = MappingProxyType({dict(sorted(matrix_hashes.items()))!r})",
        f"CANONICAL_METRIC_UNITS: Final = MappingProxyType({dict(canonical_metric_units)!r})",
        f"COLUMN_RULES_BY_RELATION: Final = MappingProxyType({columns!r})",
        f"CHECKS_BY_RELATION: Final = MappingProxyType({checks!r})",
        f"MAPPER_CALLABLES: Final = MappingProxyType({callables!r})",
        (
            "CHECK_EVALUATOR_INVENTORY: "
            f"Final[tuple[tuple[str, str, str, str], ...]] = {inventory!r}"
        ),
        "CHECK_CONSTRAINT_COUNT: Final = 519",
        "CHECK_EVALUATOR_KIND: Final = 'EXACT_RUNTIME_AST'",
        "MAPPER_CALLABLE_COUNT: Final = 205",
        "",
        "__all__ = [",
        "    'CANONICAL_METRIC_UNITS',",
        "    'CHECK_CONSTRAINT_COUNT',",
        "    'CHECK_EVALUATOR_INVENTORY',",
        "    'CHECK_EVALUATOR_KIND',",
        "    'CHECKS_BY_RELATION',",
        "    'COLUMN_RULES_BY_RELATION',",
        "    'MAPPER_CALLABLES',",
        "    'MAPPER_CALLABLE_COUNT',",
        "    'MATRIX_SHA256',",
        "    'OWNER_GENERATOR_SHA256',",
        "    'SOURCE_SHA256',",
        "]",
        "# fmt: on",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _catalog_constant(relation: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", relation.upper()).strip("_")


def _render_catalog_relation(value: object) -> tuple[str, str, str]:
    relation = _mapping(value, "CATALOG_RELATION_INVALID")
    relation_name = _text(relation.get("relation"), "CATALOG_RELATION_INVALID")
    schema, separator, table_name = relation_name.partition(".")
    kind = _text(relation.get("kind"), "CATALOG_RELATION_INVALID")
    if not separator or kind not in {"TABLE", "VIEW"}:
        _fail("CATALOG_RELATION_INVALID")
    constant = _catalog_constant(relation_name)
    lines = [
        f"{constant}: Final[Table] = Table(",
        f"    {table_name!r},",
        "    METADATA,",
    ]
    columns = _list(relation.get("columns"), "CATALOG_COLUMNS_INVALID")
    for raw_column in columns:
        column = _mapping(raw_column, "CATALOG_COLUMN_INVALID")
        column_name = _text(column.get("physical_column"), "CATALOG_COLUMN_INVALID")
        type_expression, computed = _catalog_column_type(
            _text(column.get("physical_sql_type"), "CATALOG_COLUMN_INVALID")
        )
        arguments = [repr(column_name), type_expression]
        if computed is not None:
            arguments.append(f"Computed({computed!r}, persisted=True)")
        nullable = column.get("nullable")
        if type(nullable) is not bool:
            _fail("CATALOG_COLUMN_INVALID")
        arguments.append(f"nullable={nullable!r}")
        default = _catalog_server_default(column.get("server_default"))
        if default is not None:
            if computed is not None:
                _fail("CATALOG_GENERATED_COLUMN_INVALID")
            arguments.append(f"server_default=text({default!r})")
        lines.append(f"    Column({', '.join(arguments)}),")
    if kind == "TABLE":
        primary = _mapping(relation.get("primary_key"), "CATALOG_PRIMARY_KEY_INVALID")
        primary_columns = _text_tuple(
            primary.get("columns"), "CATALOG_PRIMARY_KEY_INVALID"
        )
        if not primary_columns:
            _fail("CATALOG_PRIMARY_KEY_INVALID")
        lines.append(
            "    PrimaryKeyConstraint("
            + ", ".join(repr(column) for column in primary_columns)
            + f", name={_text(primary.get('name'), 'CATALOG_PRIMARY_KEY_INVALID')!r}),"
        )
        for raw_foreign_key in _list(
            relation.get("foreign_keys"), "CATALOG_FOREIGN_KEYS_INVALID"
        ):
            lines.append(
                f"    ForeignKeyConstraint({', '.join(_catalog_foreign_key_arguments(raw_foreign_key))}),"
            )
        for raw_unique in _list(
            relation.get("unique_constraints"), "CATALOG_UNIQUES_INVALID"
        ):
            unique = _catalog_semantics(raw_unique, "CATALOG_UNIQUE_INVALID")
            unique_columns = _text_tuple(
                unique.get("columns"), "CATALOG_UNIQUE_INVALID"
            )
            if not unique_columns:
                _fail("CATALOG_UNIQUE_INVALID")
            lines.append(
                "    UniqueConstraint("
                + ", ".join(repr(column) for column in unique_columns)
                + f", name={_text(unique.get('name'), 'CATALOG_UNIQUE_INVALID')!r}),"
            )
        for raw_check in _list(
            relation.get("check_constraints"), "CATALOG_CHECKS_INVALID"
        ):
            check = _mapping(raw_check, "CATALOG_CHECK_INVALID")
            lines.append(
                "    CheckConstraint("
                f"{_text(check.get('expression'), 'CATALOG_CHECK_INVALID')!r}, "
                f"name={_text(check.get('name'), 'CATALOG_CHECK_INVALID')!r}),"
            )
        for raw_index in _list(relation.get("indexes"), "CATALOG_INDEXES_INVALID"):
            lines.append(
                f"    Index({', '.join(_catalog_index_arguments(raw_index, relation=relation_name))}),"
            )
        lines.append(f"    schema={schema!r},")
    else:
        if any(
            _list(relation.get(key), "CATALOG_VIEW_INVALID")
            for key in (
                "foreign_keys",
                "unique_constraints",
                "check_constraints",
                "indexes",
                "triggers",
            )
        ):
            _fail("CATALOG_VIEW_INVALID")
        lines.extend((f"    schema={schema!r},", "    info={'read_only': True},"))
    lines.extend((")", ""))
    return relation_name, kind, "\n".join(lines)


def _render_full_catalog(
    *,
    catalog_ir: Mapping[str, Any],
    catalog_ir_sha256: str,
    owner_hash: str,
    source_hashes: Mapping[str, str],
    matrix_hashes: Mapping[str, str],
) -> bytes:
    relation_rows = _list(catalog_ir.get("relations"), "CATALOG_RELATIONS_INVALID")
    rendered = [_render_catalog_relation(row) for row in relation_rows]
    table_rows = tuple(row for row in rendered if row[1] == "TABLE")
    view_rows = tuple(row for row in rendered if row[1] == "VIEW")
    if (
        len(rendered) != 104
        or len(table_rows) != 103
        or tuple(row[0] for row in view_rows) != ("catalog.v_safe_offer_current",)
        or len({row[0] for row in rendered}) != 104
        or len({_catalog_constant(row[0]) for row in rendered}) != 104
    ):
        _fail("CATALOG_RENDER_INVENTORY_INVALID")
    parts = [
        '"""Generated complete ST-0308 SQLAlchemy physical catalog.\n\nDo not edit; run scripts/build_st0308_persistence.py.\n"""',
        "",
        "# fmt: off",
        "from __future__ import annotations",
        "",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        "from sqlalchemy import (",
        "    BigInteger,",
        "    Boolean,",
        "    CheckConstraint,",
        "    Column,",
        "    Computed,",
        "    Date,",
        "    DateTime,",
        "    ForeignKeyConstraint,",
        "    Index,",
        "    Integer,",
        "    MetaData,",
        "    Numeric,",
        "    PrimaryKeyConstraint,",
        "    SmallInteger,",
        "    Table,",
        "    Text,",
        "    UniqueConstraint,",
        "    Uuid,",
        "    text,",
        ")",
        "from sqlalchemy.dialects.postgresql import ARRAY, JSONB",
        "",
        f"OWNER_GENERATOR_SHA256: Final = {owner_hash!r}",
        f"SOURCE_SHA256: Final = MappingProxyType({dict(sorted(source_hashes.items()))!r})",
        f"MATRIX_SHA256: Final = MappingProxyType({dict(sorted(matrix_hashes.items()))!r})",
        f"CATALOG_IR_SHA256: Final = {catalog_ir_sha256!r}",
        "METADATA: Final[MetaData] = MetaData()",
        "",
    ]
    parts.extend(row[2] for row in rendered)
    parts.extend(("TABLES_BY_RELATION: Final = MappingProxyType({",))
    parts.extend(
        f"    {relation!r}: {_catalog_constant(relation)},"
        for relation, _kind, _code in table_rows
    )
    parts.extend(("})", "READ_ONLY_VIEWS: Final = MappingProxyType({"))
    parts.extend(
        f"    {relation!r}: {_catalog_constant(relation)},"
        for relation, _kind, _code in view_rows
    )
    parts.extend(
        (
            "})",
            "RELATIONS_BY_NAME: Final = MappingProxyType({**TABLES_BY_RELATION, **READ_ONLY_VIEWS})",
            "",
            "__all__ = [",
            "    'CATALOG_IR_SHA256',",
            "    'MATRIX_SHA256',",
            "    'METADATA',",
            "    'OWNER_GENERATOR_SHA256',",
            "    'READ_ONLY_VIEWS',",
            "    'RELATIONS_BY_NAME',",
            "    'SOURCE_SHA256',",
            "    'TABLES_BY_RELATION',",
            "]",
            "# fmt: on",
            "",
        )
    )
    return "\n".join(parts).encode("utf-8")


def _render_python(
    matrices: Mapping[str, Mapping[str, Any]],
    relations: Mapping[str, Mapping[str, Any]],
    st0303: Mapping[str, Mapping[str, Any]],
    triggers: tuple[Mapping[str, Any], ...],
    owner_hash: str,
    source_hashes: Mapping[str, str],
    matrix_hashes: Mapping[str, str],
) -> bytes:
    state_relations = _mapping(
        matrices["state_cas"].get("relations"), "STATE_CAS_INVALID"
    )
    runtime_edges = _mapping(
        state_relations.get("ops.runtime_setting_version"), "STATE_CAS_INVALID"
    )
    edge_rows = _list(runtime_edges.get("edges"), "STATE_CAS_INVALID")
    idempotency_sql = _mapping(
        matrices["idempotency"].get("sql"), "IDEMPOTENCY_INVALID"
    )
    parts = [
        '"""Generated ST-0308 OPS reference SQLAlchemy metadata.\n\nDo not edit; run scripts/build_st0308_persistence.py.\n"""',
        "",
        "# fmt: off",
        "from __future__ import annotations",
        "",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        "from sqlalchemy import (",
        "    BigInteger,",
        "    Boolean,",
        "    CheckConstraint,",
        "    Column,",
        "    DateTime,",
        "    ForeignKey,",
        "    Index,",
        "    Integer,",
        "    MetaData,",
        "    PrimaryKeyConstraint,",
        "    SmallInteger,",
        "    Table,",
        "    Text,",
        "    UniqueConstraint,",
        "    Uuid,",
        "    bindparam,",
        "    insert,",
        "    select,",
        "    text,",
        ")",
        "from sqlalchemy.dialects.postgresql import JSONB",
        "from sqlalchemy.sql.elements import TextClause",
        "",
        f"OWNER_GENERATOR_SHA256: Final = {owner_hash!r}",
        f"SOURCE_SHA256: Final = MappingProxyType({dict(sorted(source_hashes.items()))!r})",
        f"MATRIX_SHA256: Final = MappingProxyType({dict(sorted(matrix_hashes.items()))!r})",
        "METADATA: Final[MetaData] = MetaData()",
        "",
    ]
    for relation_name in SLICE_RELATIONS:
        parts.append(
            _render_table(
                RELATION_CONSTANTS[relation_name],
                relations[relation_name],
                st0303[relation_name],
            )
        )
    trigger_names = tuple(
        (
            _text(trigger.get("table"), "ST0303_TRIGGER_INVALID"),
            _text(trigger.get("name"), "ST0303_TRIGGER_INVALID"),
        )
        for trigger in triggers
    )
    parts.extend(
        (
            f"IMMUTABILITY_TRIGGER_NAMES: Final = {trigger_names!r}",
            "",
        )
    )
    parts.extend(
        (
            "OBJECT_ARTIFACT_BY_ID: Final[object] = select(OBJECT_ARTIFACT).where(",
            "    OBJECT_ARTIFACT.c.id == bindparam('artifact_id')",
            ")",
            "OBJECT_ARTIFACT_INSERT: Final[object] = insert(OBJECT_ARTIFACT)",
            "RUNTIME_SETTING_CURRENT: Final[object] = (",
            "    select(RUNTIME_SETTING_VERSION)",
            "    .where(",
            "        RUNTIME_SETTING_VERSION.c.setting_key == bindparam('setting_key'),",
            "        RUNTIME_SETTING_VERSION.c.scope_type == bindparam('scope_type'),",
            "        RUNTIME_SETTING_VERSION.c.scope_id.is_not_distinct_from(",
            "            bindparam('scope_id')",
            "        ),",
            "    )",
            "    .order_by(",
            "        RUNTIME_SETTING_VERSION.c.version_no.desc(),",
            "        RUNTIME_SETTING_VERSION.c.id.desc(),",
            "    )",
            "    .limit(1)",
            ")",
            "RUNTIME_SETTING_INSERT: Final[object] = insert(RUNTIME_SETTING_VERSION)",
            "",
            "RUNTIME_SETTING_TRANSITIONS: Final[MappingProxyType[tuple[str, str], TextClause]] = MappingProxyType(",
            "    {",
        )
    )
    for raw in edge_rows:
        edge = _mapping(raw, "STATE_CAS_INVALID")
        assignments = ", ".join(_list(edge.get("set"), "STATE_CAS_INVALID"))
        sql = (
            "UPDATE ops.runtime_setting_version "
            f"SET {assignments} WHERE {edge.get('where')} "
            "RETURNING *"
        )
        parts.append(
            f"        ({edge.get('from')!r}, {edge.get('to')!r}): text({sql!r}),"
        )
    parts.extend(
        (
            "    }",
            ")",
            "",
            "IDEMPOTENCY_SQL: Final[MappingProxyType[str, TextClause]] = MappingProxyType(",
            "    {",
        )
    )
    for name, sql in idempotency_sql.items():
        parts.append(f"        {name!r}: text({_text(sql, 'IDEMPOTENCY_INVALID')!r}),")
    parts.extend(
        (
            "    }",
            ")",
            "",
            "__all__ = [",
            "    'AUDIT_EVENT',",
            "    'IDEMPOTENCY_RECORD',",
            "    'IDEMPOTENCY_SQL',",
            "    'IMMUTABILITY_TRIGGER_NAMES',",
            "    'MATRIX_SHA256',",
            "    'METADATA',",
            "    'OBJECT_ARTIFACT',",
            "    'OBJECT_ARTIFACT_BY_ID',",
            "    'OBJECT_ARTIFACT_INSERT',",
            "    'OUTBOX_EVENT',",
            "    'RUNTIME_SETTING_CURRENT',",
            "    'RUNTIME_SETTING_INSERT',",
            "    'RUNTIME_SETTING_TRANSITIONS',",
            "    'RUNTIME_SETTING_VERSION',",
            "    'OWNER_GENERATOR_SHA256',",
            "    'SOURCE_SHA256',",
            "]",
            "# fmt: on",
            "",
        )
    )
    return "\n".join(parts).encode("utf-8")


def _render_identity_contract(
    *,
    relations: Mapping[str, Mapping[str, Any]],
    catalog_ir_sha256: str,
    owner_hash: str,
    source_hashes: Mapping[str, str],
    matrix_hashes: Mapping[str, str],
) -> bytes:
    relation_rows = tuple(
        (
            relation_name.split(".", 1)[0],
            relation_name.split(".", 1)[1],
            ("v" if relation_name == "catalog.v_safe_offer_current" else "r"),
        )
        for relation_name in sorted(relations)
    )
    if (
        len(relation_rows) != 104
        or len(set(relation_rows)) != 104
        or sum(row[2] == "r" for row in relation_rows) != 103
        or sum(row[2] == "v" for row in relation_rows) != 1
    ):
        _fail("IDENTITY_RELATION_INVENTORY_INVALID")
    values_sql = ",\n".join(
        f"        ({schema!r}, {relation!r}, {kind!r})"
        for schema, relation, kind in relation_rows
    )
    schema_values = ", ".join(repr(schema) for schema in EXPECTED_RUNTIME_SCHEMAS)
    sql = f"""WITH expected_relations(schema_name, relation_name, relation_kind) AS (
    VALUES
{values_sql}
),
login_identity AS (
    SELECT role_record.oid AS login_oid,
           SESSION_USER::text AS login_role,
           role_record.rolsuper AS is_superuser,
           role_record.rolbypassrls AS bypass_rls,
           role_record.rolcreaterole AS create_role,
           role_record.rolcreatedb AS create_database
      FROM pg_catalog.pg_roles AS role_record
     WHERE role_record.rolname = SESSION_USER
       AND SESSION_USER = CURRENT_USER
),
effective_groups AS (
    SELECT COALESCE(
               pg_catalog.array_agg(candidate.rolname::text
                                    ORDER BY candidate.rolname)
                   FILTER (WHERE candidate.oid IS NOT NULL),
               ARRAY[]::text[]
           ) AS inherited_groups
      FROM login_identity AS login
      LEFT JOIN pg_catalog.pg_roles AS candidate
        ON candidate.oid <> login.login_oid
       AND pg_catalog.pg_has_role(login.login_oid, candidate.oid, 'MEMBER')
),
required_group_gate AS (
    SELECT pg_catalog.pg_has_role(
               login.login_oid, required_role.oid, 'USAGE'
           ) AS usable
      FROM login_identity AS login
      JOIN pg_catalog.pg_roles AS required_role
        ON required_role.rolname = :required_group
),
selected_relations AS (
    SELECT expected.schema_name,
           expected.relation_name,
           expected.relation_kind,
           relation_record.oid,
           relation_record.relowner
      FROM expected_relations AS expected
      JOIN pg_catalog.pg_namespace AS namespace_record
        ON namespace_record.nspname = expected.schema_name
      JOIN pg_catalog.pg_class AS relation_record
        ON relation_record.relnamespace = namespace_record.oid
       AND relation_record.relname = expected.relation_name
       AND relation_record.relkind = expected.relation_kind
),
selected_inventory_gate AS (
    SELECT pg_catalog.count(*) = 104
       AND pg_catalog.count(DISTINCT oid) = 104 AS exact
      FROM selected_relations
),
selected_relation_ownership AS (
    SELECT COALESCE(
               pg_catalog.bool_or(
                   selected.relowner = login.login_oid
                   OR pg_catalog.pg_has_role(
                       login.login_oid, selected.relowner, 'MEMBER'
                   )
               ),
               false
           ) AS owns_selected_relation
      FROM login_identity AS login
      CROSS JOIN selected_relations AS selected
),
dangerous_owner_gate AS (
    SELECT NOT EXISTS (
               SELECT 1
                 FROM pg_catalog.pg_database AS database_record
                 CROSS JOIN login_identity AS login
                WHERE database_record.datname = pg_catalog.current_database()
                  AND (
                      database_record.datdba = login.login_oid
                      OR pg_catalog.pg_has_role(
                          login.login_oid, database_record.datdba, 'MEMBER'
                      )
                  )
           )
       AND NOT EXISTS (
               SELECT 1
                 FROM pg_catalog.pg_namespace AS namespace_record
                 CROSS JOIN login_identity AS login
                WHERE namespace_record.nspname = ANY(
                          ARRAY[{schema_values}]::text[]
                      )
                  AND (
                      namespace_record.nspowner = login.login_oid
                      OR pg_catalog.pg_has_role(
                          login.login_oid, namespace_record.nspowner, 'MEMBER'
                      )
                  )
           ) AS safe
)
SELECT login.login_role,
       groups.inherited_groups,
       login.is_superuser,
       login.bypass_rls,
       login.create_role,
       login.create_database,
       ownership.owns_selected_relation
  FROM login_identity AS login
  CROSS JOIN effective_groups AS groups
  CROSS JOIN required_group_gate AS required_group
  CROSS JOIN selected_inventory_gate AS inventory
  CROSS JOIN selected_relation_ownership AS ownership
  CROSS JOIN dangerous_owner_gate AS dangerous_owner
 WHERE required_group.usable
   AND inventory.exact
   AND dangerous_owner.safe"""
    selected_inventory_sha256 = _semantic_sha256(relation_rows)
    st0306_hash = source_hashes.get(
        "changes/st-0306/contracts/database-roles-grants.v1.yaml"
    )
    if st0306_hash is None:
        _fail("IDENTITY_SEMANTIC_ANCHOR_MISMATCH")
    lines = [
        '"""Generated ST-0308 seven-fact checkout identity contract.\n\nDo not edit; run scripts/build_st0308_persistence.py.\n"""',
        "",
        "# fmt: off",
        "from __future__ import annotations",
        "",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        "from sqlalchemy import text",
        "from sqlalchemy.sql.elements import TextClause",
        "",
        f"OWNER_GENERATOR_SHA256: Final = {owner_hash!r}",
        f"SOURCE_SHA256: Final = MappingProxyType({dict(sorted(source_hashes.items()))!r})",
        f"MATRIX_SHA256: Final = MappingProxyType({dict(sorted(matrix_hashes.items()))!r})",
        f"ST0306_CONTRACT_SHA256: Final = {st0306_hash!r}",
        f"IDENTITY_MATRIX_SHA256: Final = {matrix_hashes['identity']!r}",
        f"DOMAIN_MAPPER_MATRIX_SHA256: Final = {matrix_hashes['domain_mapper']!r}",
        f"CATALOG_IR_SHA256: Final = {catalog_ir_sha256!r}",
        f"SELECTED_RELATION_INVENTORY_SHA256: Final = {selected_inventory_sha256!r}",
        f"SELECTED_RELATIONS: Final = {relation_rows!r}",
        "IDENTITY_RESULT_FIELDS: Final = (",
        "    'login_role',",
        "    'inherited_groups',",
        "    'is_superuser',",
        "    'bypass_rls',",
        "    'create_role',",
        "    'create_database',",
        "    'owns_selected_relation',",
        ")",
        "PROFILE_REQUIRED_GROUP: Final = MappingProxyType(",
        "    {'API_COMMAND': 'raos_api_rw', 'WORKER_COMMAND': 'raos_worker_rw'}",
        ")",
        f"IDENTITY_FACTS_SQL_TEXT: Final = {sql!r}",
        "IDENTITY_FACTS_SQL: Final[TextClause] = text(IDENTITY_FACTS_SQL_TEXT)",
        "",
        "__all__ = [",
        "    'CATALOG_IR_SHA256',",
        "    'DOMAIN_MAPPER_MATRIX_SHA256',",
        "    'IDENTITY_FACTS_SQL',",
        "    'IDENTITY_FACTS_SQL_TEXT',",
        "    'IDENTITY_MATRIX_SHA256',",
        "    'IDENTITY_RESULT_FIELDS',",
        "    'MATRIX_SHA256',",
        "    'OWNER_GENERATOR_SHA256',",
        "    'PROFILE_REQUIRED_GROUP',",
        "    'SELECTED_RELATIONS',",
        "    'SELECTED_RELATION_INVENTORY_SHA256',",
        "    'ST0306_CONTRACT_SHA256',",
        "    'SOURCE_SHA256',",
        "]",
        "# fmt: on",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> Mapping[Path, bytes]:
    (
        runtime,
        matrices,
        relations,
        st0303,
        triggers,
        ownership_counts,
        catalog_ir,
        provenance,
    ) = _validate_runtime(root)
    owner_hash = _sha256(_read(root, GENERATOR_PATH))
    matrix_hashes = {
        key.removeprefix("matrix:"): value
        for key, value in provenance.items()
        if key.startswith("matrix:")
    }
    source_hashes = {
        key: value for key, value in provenance.items() if not key.startswith("matrix:")
    }
    physical_objects = _parse_st0304_objects(
        root,
        _list(runtime.get("physical_fragments"), "PHYSICAL_INPUTS_INVALID"),
    )
    canonical_metric_units = _canonical_metric_units(physical_objects)
    compiled_physical_constraints = _compile_physical_constraint_inventory(catalog_ir)
    catalog_ir_material = {
        **dict(catalog_ir),
        "provenance": {
            "owner_generator": {
                "path": GENERATOR_PATH.as_posix(),
                "sha256": owner_hash,
            },
            "source_sha256": dict(sorted(source_hashes.items())),
            "matrix_sha256": dict(sorted(matrix_hashes.items())),
        },
    }
    catalog_ir_bytes = (
        json.dumps(
            catalog_ir_material,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    catalog_ir_sha256 = _sha256(catalog_ir_bytes)
    metadata = {
        "document": {
            "id": "ST0308-PERSISTENCE-RUNTIME-OPS-REFERENCE-001",
            "version": "1.0.0",
            "story_id": "ST-0308",
            "status": "LOCAL_REPRESENTATIVE_RUNTIME",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
        },
        "owner": {
            "generator": GENERATOR_PATH.as_posix(),
            "generator_sha256": owner_hash,
            "command": "python scripts/build_st0308_persistence.py",
        },
        "source_sha256": dict(sorted(source_hashes.items())),
        "matrix_sha256": dict(sorted(matrix_hashes.items())),
        "physical_parity": {
            "physical_tables_matched_to_relation_contracts": _mapping(
                runtime.get("inventory"), "RUNTIME_INVENTORY_INVALID"
            ).get("tables"),
            "physical_view_identities_matched_to_relation_contracts": 1,
            "physical_view_projection_identity_parity": "VERIFIED",
            "physical_view_column_type_nullability_parity": "POSTGRESQL_RUNTIME_NOT_EXECUTED",
            "catalog_ir_sha256": catalog_ir_sha256,
            "catalog_ir_relation_count": 104,
            "catalog_ir_column_count": 1376,
            "catalog_ir_check_constraint_count": 519,
            "relation_contract_hashes_verified": len(relations),
            "lock_version_relation_membership_verified": 27,
            "state_cas_relation_membership_verified": 24,
            "slice_triggers": [dict(trigger) for trigger in triggers],
        },
        "contract_inventory_verified": {
            "repository_owned_relation_count": len(ownership_counts[0]),
            "repository_owned_relation_identities": list(ownership_counts[0]),
            "repository_excluded_relation_count": len(ownership_counts[1]),
            "repository_excluded_relation_identities": list(ownership_counts[1]),
            "total_relation_contract_identities": len(relations),
            "contract_uow_repository_property_matrix_parity": "VERIFIED",
            "event_matrix_unique_type_rows": 18,
            "event_schema_byte_hashes": 18,
            "identity_allowed_profile_composition": 2,
            "target_mapper_inventory_coverage": "VERIFIED_IN_CATALOG_IR",
            "runtime_mapper_coverage": "FULL_EXACT_PHYSICAL_CHECK_GUARDS",
            "runtime_physical_check_evaluator_count": 519,
            "runtime_physical_check_evaluator_kind": "EXACT_RUNTIME_AST",
            "event_class_and_payload_coverage": "NOT_VERIFIED_BY_THIS_OWNER",
            "identity_rule_semantics": "NOT_VERIFIED_BY_THIS_OWNER",
        },
        "runtime_artifacts_implemented": {
            "owner_generated_table_metadata": 103,
            "owner_generated_read_only_view_metadata": 1,
            "full_catalog_ir": "PRESENT",
            "full_sqlalchemy_catalog": "PRESENT",
            "seven_fact_identity_sql": "PRESENT",
            "idempotency_sql": "MATRIX_TEXT_EMITTED_WITHOUT_RUNTIME_SEMANTIC_CLAIM",
            "scope": "FULL_LOCAL_PERSISTENCE_CATALOG_WITH_OPS_REFERENCE_SQL",
        },
        "slice": {
            "relations": list(SLICE_RELATIONS),
            "repositories": ["ObjectArtifactRepository", "RuntimeSettingRepository"],
            "shared_atomic": [
                "AuditEventAppender",
                "OutboxEventAppender",
                "IdempotencyRepository",
            ],
            "identity_profiles": ["API_COMMAND", "WORKER_COMMAND"],
            "external_io": "FORBIDDEN",
        },
    }
    metadata_bytes = (
        json.dumps(
            metadata,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    package_bytes = (
        '"""Generated SQLAlchemy metadata for the ST-0308 persistence slice."""\n'
        "\n"
        "# fmt: off\n"
        "from types import MappingProxyType\n"
        "from typing import Final\n"
        "\n"
        "from raos.adapters.persistence.sqlalchemy.generated.catalog import METADATA, READ_ONLY_VIEWS, RELATIONS_BY_NAME, TABLES_BY_RELATION\n"
        "from raos.adapters.persistence.sqlalchemy.generated.identity_contract import IDENTITY_FACTS_SQL\n"
        "\n"
        f"OWNER_GENERATOR_SHA256: Final = {owner_hash!r}\n"
        f"SOURCE_SHA256: Final = MappingProxyType({dict(sorted(source_hashes.items()))!r})\n"
        f"MATRIX_SHA256: Final = MappingProxyType({dict(sorted(matrix_hashes.items()))!r})\n"
        "\n"
        "__all__ = ['IDENTITY_FACTS_SQL', 'MATRIX_SHA256', 'METADATA', 'OWNER_GENERATOR_SHA256', 'READ_ONLY_VIEWS', 'RELATIONS_BY_NAME', 'SOURCE_SHA256', 'TABLES_BY_RELATION']\n"
        "# fmt: on\n"
    ).encode("utf-8")
    code_bytes = _render_python(
        matrices,
        relations,
        st0303,
        triggers,
        owner_hash,
        source_hashes,
        matrix_hashes,
    )
    identity_bytes = _render_identity_contract(
        relations=relations,
        catalog_ir_sha256=catalog_ir_sha256,
        owner_hash=owner_hash,
        source_hashes=source_hashes,
        matrix_hashes=matrix_hashes,
    )
    full_catalog_bytes = _render_full_catalog(
        catalog_ir=catalog_ir,
        catalog_ir_sha256=catalog_ir_sha256,
        owner_hash=owner_hash,
        source_hashes=source_hashes,
        matrix_hashes=matrix_hashes,
    )
    physical_constraints_bytes = _render_physical_constraints(
        compiled=compiled_physical_constraints,
        canonical_metric_units=canonical_metric_units,
        owner_hash=owner_hash,
        source_hashes=source_hashes,
        matrix_hashes=matrix_hashes,
    )
    return MappingProxyType(
        {
            OUTPUT_METADATA_PATH: metadata_bytes,
            OUTPUT_CATALOG_IR_PATH: catalog_ir_bytes,
            OUTPUT_PACKAGE_PATH: package_bytes,
            OUTPUT_CODE_PATH: code_bytes,
            OUTPUT_IDENTITY_PATH: identity_bytes,
            OUTPUT_FULL_CATALOG_PATH: full_catalog_bytes,
            OUTPUT_PHYSICAL_CONSTRAINTS_PATH: physical_constraints_bytes,
        }
    )


def _safe_output(root: Path, relative: Path) -> Path:
    if relative not in OWNER_OUTPUT_PATHS:
        _fail("OWNER_OUTPUT_PATH_INVALID")
    root_real = root.resolve(strict=True)
    current = root_real
    for part in relative.parent.parts:
        current /= part
        if current.exists() and current.is_symlink():
            _fail("OWNER_OUTPUT_PARENT_SYMLINK")
    return root_real / relative


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    target = _safe_output(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _validate_owner_generated_directories(root: Path) -> None:
    """Reject hidden owner-tree drift, including every bytecode cache."""

    root_real = root.resolve(strict=True)
    for relative, allowed_names in OWNER_GENERATED_DIRECTORY_ALLOWLISTS.items():
        directory = root_real / relative
        try:
            directory_metadata = directory.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(directory_metadata.st_mode) or stat.S_ISLNK(
            directory_metadata.st_mode
        ):
            _fail("OWNER_GENERATED_DIRECTORY_INVALID")
        try:
            entries = tuple(os.scandir(directory))
        except OSError:
            _fail("OWNER_GENERATED_DIRECTORY_INVALID")
        for entry in entries:
            if entry.name not in allowed_names:
                _fail("OWNER_GENERATED_DIRECTORY_DRIFT")
            try:
                entry_metadata = entry.stat(follow_symlinks=False)
            except OSError:
                _fail("OWNER_GENERATED_DIRECTORY_INVALID")
            if not stat.S_ISREG(entry_metadata.st_mode) or stat.S_ISLNK(
                entry_metadata.st_mode
            ):
                _fail("OWNER_GENERATED_DIRECTORY_INVALID")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    _validate_owner_generated_directories(root)
    outputs = render_outputs(root)
    if tuple(outputs) != OWNER_OUTPUT_PATHS:
        _fail("OWNER_OUTPUT_INVENTORY_INVALID")
    if check:
        for relative, expected in outputs.items():
            try:
                actual = _read(root, relative)
            except PersistenceBuildError:
                _fail("OWNER_OUTPUT_DRIFT")
            if actual != expected:
                _fail("OWNER_OUTPUT_DRIFT")
        return
    for relative, content in outputs.items():
        _atomic_write(root, relative, content)
    _validate_owner_generated_directories(root)


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_args(arguments)
    try:
        build(check=bool(options.check))
    except OSError, PersistenceBuildError, yaml.YAMLError:
        print("ST0308_PERSISTENCE_BUILD_FAILED", file=sys.stderr)
        return 1
    print(
        "ST0308_PERSISTENCE_CHECK_OK"
        if options.check
        else "ST0308_PERSISTENCE_BUILD_OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
