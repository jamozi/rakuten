"""Owner-generation and explicit-mapper checks for the first vertical slice."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from raos.adapters.persistence.sqlalchemy.generated import (
    identity_contract,
    ops_reference,
)
import raos.adapters.persistence.sqlalchemy.generated as generated_package
from raos.adapters.persistence.sqlalchemy.mappers import ops as mappers
from raos.domain.shared.idempotency import (
    ActorFingerprint,
    ClaimGranted,
    IdempotencyClaim,
    IdempotencyIdentity,
    IdempotencyKey,
    IdempotencyOutcome,
    RequestHash,
    RouteKey,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent
from scripts import build_st0308_persistence as generator
from tests.st0308_persistence.support import (
    FIXED_TIME,
    make_artifact,
    make_audit,
    make_context,
    make_event,
    make_factory,
    make_runtime_setting,
)


def test_owner_generation_is_deterministic_and_check_is_no_write() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert tuple(first) == generator.OWNER_OUTPUT_PATHS
    assert first == second
    before = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in generator.OWNER_OUTPUT_PATHS
    }
    generator.build(check=True)
    after = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in generator.OWNER_OUTPUT_PATHS
    }
    assert before == after
    assert all(path in generator.render_outputs() for path in before)


def test_direct_check_entrypoint_bootstraps_repository_imports() -> None:
    process = subprocess.run(
        [
            sys.executable,
            str(generator.REPO_ROOT / generator.GENERATOR_PATH),
            "--check",
        ],
        cwd=generator.REPO_ROOT,
        env={
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "ST0308_PERSISTENCE_CHECK_OK"


def test_full_catalog_ir_has_closed_exact_two_way_inventory() -> None:
    catalog_ir = json.loads(
        (generator.REPO_ROOT / generator.OUTPUT_CATALOG_IR_PATH).read_bytes()
    )
    assert catalog_ir["closed_owner_outputs"] == [
        path.as_posix() for path in generator.OWNER_OUTPUT_PATHS
    ]
    assert catalog_ir["inventory"] == {
        "check_constraints": 519,
        "columns": 1376,
        "generated_columns": ["ai.evaluation_case_result.zero_tolerance_failure_count"],
        "relations": 104,
        "repository_excluded_relations": ["ops.inbox_receipt"],
        "repository_owned_relations": 103,
        "schemas": [
            "ops",
            "iam",
            "portfolio",
            "catalog",
            "evidence",
            "editorial",
            "ai",
            "policy",
        ],
        "st0304_physical_objects": 1842,
        "st0304_relation_object_assignments": 885,
        "tables": 103,
        "treatments": {
            "EXPLICIT_BIDIRECTIONAL_SCALAR_MAPPER": 102,
            "GENERATED_METADATA_ONLY_NO_RUNTIME_MAPPER_OR_PORT": 1,
            "READ_ONLY_EXPLICIT_FROM_ROW_MAPPER_NO_DML": 1,
        },
        "views": 1,
    }
    target = catalog_ir["target_runtime_inventory"]
    assert len(target["sqlalchemy_table_relations"]) == 103
    assert len(target["bidirectional_mapper_relations"]) == 102
    assert target["from_only_mapper_relations"] == ["catalog.v_safe_offer_current"]
    assert target["metadata_only_no_mapper_relations"] == ["ops.inbox_receipt"]
    assert len(catalog_ir["relations"]) == 104


def test_st0304_physical_object_catalog_drift_fails_closed() -> None:
    runtime = generator.load_yaml(generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH)
    objects = generator._parse_st0304_objects(
        generator.REPO_ROOT,
        runtime["physical_fragments"],
    )
    catalog = generator._load_json(
        generator.REPO_ROOT,
        generator.ST0304_CATALOG_PATH,
    )
    generator._validate_st0304_object_inventory(catalog, objects)
    tampered = (replace(objects[0], sha256="0" * 64), *objects[1:])
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._validate_st0304_object_inventory(catalog, tampered)
    assert caught.value.code == "ST0304_OBJECT_INVENTORY_MISMATCH"


def test_st0304_catalog_rejects_correlated_extension_and_extra_object() -> None:
    runtime = generator.load_yaml(generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH)
    objects = generator._parse_st0304_objects(
        generator.REPO_ROOT,
        runtime["physical_fragments"],
    )
    catalog = generator._load_json(
        generator.REPO_ROOT,
        generator.ST0304_CATALOG_PATH,
    )

    extended_catalog = dict(catalog)
    extended_catalog["unrecognized_owner_authority"] = "GRANTED"
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._validate_st0304_object_inventory(extended_catalog, objects)
    assert caught.value.code == "ST0304_CATALOG_SHAPE_INVALID"

    extra = replace(
        objects[-1],
        name="injected_comment",
        object_type="COMMENT",
        sha256="1" * 64,
    )
    correlated_objects = (*objects, extra)
    object_rows = [
        {
            "name": item.name,
            "schema": item.schema,
            "sha256": item.sha256,
            "type": item.object_type,
        }
        for item in correlated_objects
    ]
    correlated_catalog = deepcopy(catalog)
    correlated_catalog["object_inventory"] = {
        "count": len(object_rows),
        "objects": object_rows,
        "sha256": generator._sha256(
            json.dumps(
                object_rows,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ),
    }
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._validate_st0304_object_inventory(
            correlated_catalog,
            correlated_objects,
        )
    assert caught.value.code == "ST0304_OBJECT_INVENTORY_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("root_extension", "MAPPER_ROOT_SHAPE_INVALID"),
        ("relation_extension", "MAPPER_RELATION_SHAPE_INVALID"),
        ("untyped_mapper", "MAPPER_CONTRACT_INVALID"),
    ),
)
def test_mapper_contract_rejects_correlated_authority_drift(
    mutation: str,
    expected_code: str,
) -> None:
    matrix = deepcopy(
        generator.load_yaml(
            generator.REPO_ROOT / generator.EXPECTED_MATRIX_PATHS["domain_mapper"]
        )
    )
    if mutation == "root_extension":
        matrix["unrecognized_owner_authority"] = "GRANTED"
    else:
        relation = matrix["relations"][0]
        if mutation == "relation_extension":
            relation["unrecognized_runtime_authority"] = "GRANTED"
        else:
            relation["mapper"] = {
                "path": relation["mapper"]["path"],
                "from_row": 1,
                "to_row": True,
                "signature": relation["mapper"]["signature"],
                "input_parameters": relation["mapper"]["input_parameters"],
                "output": relation["mapper"]["output"],
            }
        relation["relation_contract_sha256"] = generator._semantic_sha256(
            {
                key: value
                for key, value in relation.items()
                if key != "relation_contract_sha256"
            }
        )
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._relation_index(matrix)
    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    "relative",
    (
        generator.ST0304_CATALOG_PATH,
        Path("changes/st-0304/contracts/physical/01-domain-physical.sql"),
    ),
)
def test_tracked_source_digest_is_observed_not_authority_bound(
    tmp_path: Path,
    relative: Path,
) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"correlated but unauthorized input")
    correlated_digest = generator._sha256(target.read_bytes())
    assert generator._verify_digest(tmp_path, relative, correlated_digest) == correlated_digest


def test_physical_fragment_parser_rejects_preamble_sql_injection(
    tmp_path: Path,
) -> None:
    relative = Path("changes/st-0304/contracts/physical/01-domain-physical.sql")
    original = (generator.REPO_ROOT / relative).read_bytes()
    injected = b'DROP TABLE "catalog"."offer";\n' + original
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(injected)
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._parse_st0304_objects(
            tmp_path,
            [{"path": relative.as_posix(), "sha256": generator._sha256(injected)}],
        )
    assert caught.value.code == "PHYSICAL_FRAGMENT_PREAMBLE_INVALID"


def test_owner_generated_directories_reject_rogue_file_and_cache(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "python/raos/adapters/persistence/sqlalchemy/generated"
    generated.mkdir(parents=True)
    (generated / "unexpected.py").write_text("AUTHORITY = 'GRANTED'\n")
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._validate_owner_generated_directories(tmp_path)
    assert caught.value.code == "OWNER_GENERATED_DIRECTORY_DRIFT"

    (generated / "unexpected.py").unlink()
    cache = generated / "__pycache__"
    cache.mkdir()
    (cache / "unexpected.cpython-314.pyc").write_bytes(b"rogue")
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator._validate_owner_generated_directories(tmp_path)
    assert caught.value.code == "OWNER_GENERATED_DIRECTORY_DRIFT"


def test_every_generated_artifact_records_complete_provenance() -> None:
    metadata = json.loads(
        (generator.REPO_ROOT / generator.OUTPUT_METADATA_PATH).read_bytes()
    )
    catalog_ir = json.loads(
        (generator.REPO_ROOT / generator.OUTPUT_CATALOG_IR_PATH).read_bytes()
    )
    owner_hash = generator._sha256(
        (generator.REPO_ROOT / generator.GENERATOR_PATH).read_bytes()
    )
    source_hashes = metadata["source_sha256"]
    matrix_hashes = metadata["matrix_sha256"]
    assert metadata["owner"]["generator_sha256"] == owner_hash
    assert catalog_ir["provenance"] == {
        "owner_generator": {
            "path": generator.GENERATOR_PATH.as_posix(),
            "sha256": owner_hash,
        },
        "source_sha256": source_hashes,
        "matrix_sha256": matrix_hashes,
    }
    for module in (generated_package, identity_contract, ops_reference):
        assert module.OWNER_GENERATOR_SHA256 == owner_hash
        assert dict(module.SOURCE_SHA256) == source_hashes
        assert dict(module.MATRIX_SHA256) == matrix_hashes
    assert (
        identity_contract.ST0306_CONTRACT_SHA256
        == source_hashes["changes/st-0306/contracts/database-roles-grants.v1.yaml"]
    )


def test_identity_query_is_exact_seven_fact_hash_bound_static_inventory() -> None:
    assert identity_contract.IDENTITY_RESULT_FIELDS == (
        "login_role",
        "inherited_groups",
        "is_superuser",
        "bypass_rls",
        "create_role",
        "create_database",
        "owns_selected_relation",
    )
    assert len(identity_contract.SELECTED_RELATIONS) == 104
    assert len(set(identity_contract.SELECTED_RELATIONS)) == 104
    assert sum(row[2] == "r" for row in identity_contract.SELECTED_RELATIONS) == 103
    assert sum(row[2] == "v" for row in identity_contract.SELECTED_RELATIONS) == 1
    assert identity_contract.PROFILE_REQUIRED_GROUP == {
        "API_COMMAND": "raos_api_rw",
        "WORKER_COMMAND": "raos_worker_rw",
    }
    assert identity_contract.ST0306_CONTRACT_SHA256 == (
        "93f03ff2a762ff0d0b950b06a5b7416687ce20e44f7e7b7f6ea2a7ed2b873206"
    )
    sql = identity_contract.IDENTITY_FACTS_SQL_TEXT
    assert "SESSION_USER = CURRENT_USER" in sql
    assert "pg_catalog.pg_has_role(login.login_oid, candidate.oid, 'MEMBER')" in sql
    assert ":required_group" in sql
    assert set(identity_contract.IDENTITY_FACTS_SQL._bindparams) == {  # noqa: SLF001
        "required_group"
    }
    compiled = identity_contract.IDENTITY_FACTS_SQL.bindparams(
        required_group="raos_api_rw"
    ).compile(dialect=postgresql.dialect())
    assert str(compiled)


def test_generated_ops_metadata_has_exact_representative_columns() -> None:
    assert set(ops_reference.METADATA.tables) == {
        "ops.audit_event",
        "ops.idempotency_record",
        "ops.object_artifact",
        "ops.outbox_event",
        "ops.runtime_setting_version",
    }
    assert tuple(ops_reference.OBJECT_ARTIFACT.c.keys()) == (
        "id",
        "display_id",
        "artifact_kind",
        "storage_provider",
        "bucket_name",
        "object_key",
        "object_version",
        "content_type",
        "byte_size",
        "sha256",
        "encryption_state",
        "retention_class",
        "is_immutable",
        "source_system",
        "acquired_at",
        "created_by_principal_id",
        "metadata",
        "created_at",
    )
    assert tuple(ops_reference.RUNTIME_SETTING_VERSION.c.keys()) == (
        "id",
        "setting_key",
        "scope_type",
        "scope_id",
        "version_no",
        "setting_class",
        "value",
        "value_sha256",
        "status",
        "effective_from",
        "effective_to",
        "created_by_principal_id",
        "approved_by_principal_id",
        "approval_reason",
        "created_at",
    )
    assert {
        table.fullname: table.primary_key.name
        for table in ops_reference.METADATA.tables.values()
    } == {
        "ops.audit_event": "pk_ops_audit_event",
        "ops.idempotency_record": "pk_ops_idempotency_record",
        "ops.object_artifact": "pk_ops_object_artifact",
        "ops.outbox_event": "pk_ops_outbox_event",
        "ops.runtime_setting_version": "pk_ops_runtime_setting_version",
    }
    assert {
        foreign_key.name
        for name in (
            "ops.idempotency_record",
            "ops.runtime_setting_version",
        )
        for foreign_key in ops_reference.METADATA.tables[name].foreign_key_constraints
    } == {
        "fk_ops_idempotency_record_response_artifact_id",
        "fk_ops_runtime_setting_version_approved_by_principal_id",
        "fk_ops_runtime_setting_version_created_by_principal_id",
    }
    assert (
        sum(len(table.indexes) for table in ops_reference.METADATA.tables.values())
        == 18
    )
    assert ops_reference.IMMUTABILITY_TRIGGER_NAMES == (
        ("ops.object_artifact", "trg_ops_object_artifact_immutable"),
        ("ops.audit_event", "trg_ops_audit_event_immutable"),
    )


def test_generated_metadata_and_statements_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()
    for table in ops_reference.METADATA.tables.values():
        external_foreign_keys = tuple(table.foreign_key_constraints)
        compiled = str(
            CreateTable(
                table,
                include_foreign_key_constraints=([] if external_foreign_keys else None),
            ).compile(dialect=dialect)
        )
        assert f"CREATE TABLE ops.{table.name}" in compiled
        for index in table.indexes:
            assert "CREATE " in str(CreateIndex(index).compile(dialect=dialect))
    for statement in (
        ops_reference.OBJECT_ARTIFACT_BY_ID,
        ops_reference.OBJECT_ARTIFACT_INSERT,
        ops_reference.RUNTIME_SETTING_CURRENT,
        ops_reference.RUNTIME_SETTING_INSERT,
        *ops_reference.RUNTIME_SETTING_TRANSITIONS.values(),
        *ops_reference.IDEMPOTENCY_SQL.values(),
    ):
        assert str(statement.compile(dialect=dialect))


def test_explicit_nominal_mapper_round_trip_and_sanitized_corruption() -> None:
    artifact = make_artifact()
    artifact_row = mappers.map_ops_object_artifact_to_row(artifact)
    round_trip = mappers.map_ops_object_artifact_from_row(
        id=artifact_row[0],
        display_id=artifact_row[1],
        artifact_kind=artifact_row[2],
        storage_provider=artifact_row[3],
        bucket_name=artifact_row[4],
        object_key=artifact_row[5],
        object_version=artifact_row[6],
        content_type=artifact_row[7],
        byte_size=artifact_row[8],
        sha256=artifact_row[9],
        encryption_state=artifact_row[10],
        retention_class=artifact_row[11],
        is_immutable=artifact_row[12],
        source_system=artifact_row[13],
        acquired_at=artifact_row[14],
        created_by_principal_id=artifact_row[15],
        metadata=artifact_row[16],
        created_at=artifact_row[17],
    )
    assert round_trip == artifact

    setting = make_runtime_setting().state
    setting_row = mappers.map_ops_runtime_setting_version_to_row(setting)
    assert (
        mappers.map_ops_runtime_setting_version_from_row(
            id=setting_row[0],
            setting_key=setting_row[1],
            scope_type=setting_row[2],
            scope_id=setting_row[3],
            version_no=setting_row[4],
            setting_class=setting_row[5],
            value=setting_row[6],
            value_sha256=setting_row[7],
            status=setting_row[8],
            effective_from=setting_row[9],
            effective_to=setting_row[10],
            created_by_principal_id=setting_row[11],
            approved_by_principal_id=setting_row[12],
            approval_reason=setting_row[13],
            created_at=setting_row[14],
        )
        == setting
    )

    with pytest.raises(PersistenceError) as caught:
        mappers.map_ops_object_artifact_from_row(
            id=artifact_row[0],
            display_id=artifact_row[1],
            artifact_kind=artifact_row[2],
            storage_provider=artifact_row[3],
            bucket_name=artifact_row[4],
            object_key=artifact_row[5],
            object_version=artifact_row[6],
            content_type=artifact_row[7],
            byte_size=True,
            sha256=artifact_row[9],
            encryption_state=artifact_row[10],
            retention_class=artifact_row[11],
            is_immutable=artifact_row[12],
            source_system=artifact_row[13],
            acquired_at=artifact_row[14],
            created_by_principal_id=artifact_row[15],
            metadata=artifact_row[16],
            created_at=artifact_row[17],
        )
    assert caught.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
    assert caught.value.__cause__ is None
    assert str(caught.value) == "STORAGE_CORRUPTION"


def test_shared_atomic_record_mappers_round_trip() -> None:
    factory, store, _pool = make_factory(id_prefix="mapper")
    identity = IdempotencyIdentity(
        ActorFingerprint("e" * 64),
        RouteKey("POST:/ops/mapper"),
        IdempotencyKey("mapper-key"),
    )
    with factory.begin_idempotent(make_context(suffix="mapper")) as outer:
        outer.audit.append_many((make_audit(),))
        outer.outbox.append_many((ValidatedOutboxEvent(make_event(suffix="mapper")),))
        decision = outer.idempotency.claim(
            IdempotencyClaim(
                identity,
                RequestHash("f" * 64),
                FIXED_TIME.replace(minute=10),
            )
        )
        assert isinstance(decision, ClaimGranted)
        outer.idempotency.complete_success(
            decision.handle,
            IdempotencyOutcome(
                200,
                FrozenJsonObject.from_mapping({"mapped": True}),
            ),
        )
        outer.commit()
    snapshot = store.snapshot()

    audit = snapshot.audit_events[0]
    audit_row = mappers.map_ops_audit_event_to_row(audit)
    assert (
        mappers.map_ops_audit_event_from_row(
            id=audit_row[0],
            occurred_at=audit_row[1],
            actor_type=audit_row[2],
            actor_id=audit_row[3],
            action=audit_row[4],
            target_type=audit_row[5],
            target_id=audit_row[6],
            outcome=audit_row[7],
            severity=audit_row[8],
            correlation_id=audit_row[9],
            request_id=audit_row[10],
            before_hash=audit_row[11],
            after_hash=audit_row[12],
            details=audit_row[13],
            created_at=audit_row[14],
        )
        == audit
    )

    outbox = snapshot.outbox_events[0]
    outbox_row = mappers.map_ops_outbox_event_to_row(outbox)
    assert (
        mappers.map_ops_outbox_event_from_row(
            id=outbox_row[0],
            event_type=outbox_row[1],
            event_version=outbox_row[2],
            producer=outbox_row[3],
            aggregate_type=outbox_row[4],
            aggregate_id=outbox_row[5],
            aggregate_version=outbox_row[6],
            correlation_id=outbox_row[7],
            causation_id=outbox_row[8],
            actor_type=outbox_row[9],
            actor_id=outbox_row[10],
            payload=outbox_row[11],
            payload_schema_hash=outbox_row[12],
            status=outbox_row[13],
            available_at=outbox_row[14],
            published_at=outbox_row[15],
            publish_attempts=outbox_row[16],
            last_error=outbox_row[17],
            created_at=outbox_row[18],
        )
        == outbox
    )

    idempotency = snapshot.idempotency_records[0]
    idempotency_row = mappers.map_ops_idempotency_record_to_row(idempotency)
    assert (
        mappers.map_ops_idempotency_record_from_row(
            id=idempotency_row[0],
            actor_fingerprint=idempotency_row[1],
            route_key=idempotency_row[2],
            idempotency_key=idempotency_row[3],
            request_hash=idempotency_row[4],
            status=idempotency_row[5],
            response_status=idempotency_row[6],
            response_body=idempotency_row[7],
            response_artifact_id=idempotency_row[8],
            resource_type=idempotency_row[9],
            resource_id=idempotency_row[10],
            expires_at=idempotency_row[11],
            completed_at=idempotency_row[12],
            created_at=idempotency_row[13],
        )
        == idempotency
    )
