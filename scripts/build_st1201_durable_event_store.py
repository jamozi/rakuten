"""Deterministically build the ST-1201 durable recorded-event projection."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import NoReturn, cast

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("changes/st-1201/contracts/durable-recorded-event-store.v2.json")
GENERATED = Path("changes/st-1201/generated/durable-recorded-event-store.v2.json")
MANIFEST = Path("changes/st-1201/manifest.v2.json")
BACKLOG = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.csv")
EVENT_CATALOG = Path("docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml")
OPEN_DECISIONS = Path("docs/canonical/00_master/RAOS_open_decisions_v1.0.csv")
TEST_CATALOG = Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml")
OWNED_SOURCES = (
    CONTRACT,
    Path("changes/st-1201/README.md"),
    Path("changes/st-1201/PREFLIGHT-20260825-v3.md"),
    Path("changes/st-1201/LOCAL-IMPLEMENTATION-COMPLETION-20260825-v2.json"),
    Path("python/raos/domain/analytics/event_collector.py"),
    Path("python/raos/domain/analytics/event_collector_runtime_v2.py"),
    Path("python/raos/ports/event_collector_runtime_v2.py"),
    Path("python/raos/application/analytics/event_collector.py"),
    Path("python/raos/application/analytics/event_collector_runtime_v2.py"),
    Path("python/raos/adapters/recorded_event_store.py"),
    Path("python/raos/adapters/sqlite_event_collector_runtime_v2.py"),
    Path("scripts/build_st1201_durable_event_store.py"),
    Path("tests/st1201/conftest.py"),
    Path("tests/st1201/test_boundaries.py"),
    Path("tests/st1201/test_collector.py"),
    Path("tests/st1201/test_durable_boundary_hardening_v3.py"),
    Path("tests/st1201/test_durable_generation_v2.py"),
    Path("tests/st1201/test_durable_runtime_v2.py"),
    Path("tests/st1201/test_durable_sqlite_hardening_v3.py"),
    Path("tests/st1201/test_failure_isolation.py"),
)
BOUND_SOURCES = (
    BACKLOG,
    EVENT_CATALOG,
    OPEN_DECISIONS,
    TEST_CATALOG,
    Path("changes/st-0305/README.md"),
    Path("changes/st-0404/README.md"),
)


class St1201BuildError(RuntimeError):
    __slots__ = ("code", "field")

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(code)


def _fail(code: str, field: str) -> NoReturn:
    raise St1201BuildError(code, field) from None


def _bytes(path: Path) -> bytes:
    target = ROOT / path
    if not target.is_file() or target.is_symlink():
        _fail("SOURCE_MISSING", path.as_posix())
    try:
        return target.read_bytes()
    except OSError:
        _fail("SOURCE_UNREADABLE", path.as_posix())


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(_bytes(path))
    except json.JSONDecodeError:
        _fail("JSON_INVALID", path.as_posix())
    if type(value) is not dict:
        _fail("JSON_INVALID", path.as_posix())
    return cast(dict[str, object], value)


def _story() -> dict[str, str]:
    try:
        rows = tuple(csv.DictReader(_bytes(BACKLOG).decode("utf-8-sig").splitlines()))
    except UnicodeDecodeError, csv.Error:
        _fail("BACKLOG_INVALID", BACKLOG.as_posix())
    matches = tuple(row for row in rows if row.get("id") == "ST-1201")
    if len(matches) != 1:
        _fail("STORY_MISSING", "ST-1201")
    story = matches[0]
    expected = {
        "depends_on": "ST-0305;ST-0404",
        "test_suites": "TST-012;TST-030;TST-031",
        "open_decisions": "OD-012",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
    }
    if any(story.get(key) != value for key, value in expected.items()):
        _fail("STORY_DRIFT", "ST-1201")
    return {key: str(value) for key, value in story.items()}


def _canonical_checks() -> dict[str, object]:
    try:
        catalog_value: object = yaml.safe_load(_bytes(EVENT_CATALOG))
        tests_value: object = yaml.safe_load(_bytes(TEST_CATALOG))
    except yaml.YAMLError:
        _fail("CANONICAL_YAML_INVALID", "canonical")
    if type(catalog_value) is not dict:
        _fail("EVENT_CATALOG_INVALID", "events")
    catalog = cast(dict[str, object], catalog_value)
    if type(catalog.get("events")) is not list:
        _fail("EVENT_CATALOG_INVALID", "events")
    events = cast(list[object], catalog["events"])
    if len(events) != 20:
        _fail("EVENT_CATALOG_INVALID", "event_count")
    event_rows = tuple(cast(dict[str, object], row) for row in events)
    if tuple(row.get("id") for row in event_rows) != tuple(
        f"EVT-{index:03d}" for index in range(1, 21)
    ):
        _fail("EVENT_CATALOG_INVALID", "event_order")
    if any(
        row.get("prohibited_parameters")
        != [
            "email",
            "phone",
            "raw_ip",
            "full_user_agent",
            "raw_search_query",
            "article_body",
            "source_packet_text",
            "affiliate_url_query_secret",
        ]
        for row in event_rows
    ):
        _fail("EVENT_CATALOG_INVALID", "prohibited_parameters")

    if type(tests_value) is not dict:
        _fail("TEST_CATALOG_INVALID", "suites")
    tests = cast(dict[str, object], tests_value)
    if type(tests.get("suites")) is not list:
        _fail("TEST_CATALOG_INVALID", "suites")
    suites = {
        row.get("id"): row
        for item in cast(list[object], tests["suites"])
        if type(item) is dict
        for row in [cast(dict[str, object], item)]
    }
    if not {"TST-012", "TST-030", "TST-031"}.issubset(suites):
        _fail("TEST_CATALOG_INVALID", "suite_ids")
    for suite_id in ("TST-012", "TST-030", "TST-031"):
        row = suites.get(suite_id)
        if row is None or row.get("release_blocking") is not True:
            _fail("TEST_CATALOG_INVALID", suite_id)

    try:
        decisions = tuple(
            csv.DictReader(_bytes(OPEN_DECISIONS).decode("utf-8-sig").splitlines())
        )
    except UnicodeDecodeError, csv.Error:
        _fail("OPEN_DECISION_INVALID", "OD-012")
    matches = tuple(row for row in decisions if row.get("id") == "OD-012")
    if (
        len(matches) != 1
        or matches[0].get("status") != "HUMAN_DECISION_REQUIRED"
        or "First-party" not in str(matches[0].get("default_behavior"))
    ):
        _fail("OPEN_DECISION_INVALID", "OD-012")
    return {
        "canonical_event_count": 20,
        "mvp_public_event_count": sum(
            row.get("source") == "public_web" and row.get("mvp") is True
            for row in event_rows
        ),
        "open_decision": "OD-012_UNRESOLVED_SAFE_DEFAULT",
        "required_suites": ["TST-012", "TST-030", "TST-031"],
    }


def _binding(path: Path) -> dict[str, object]:
    value = _bytes(path)
    return {"path": path.as_posix(), "bytes": len(value), "sha256": _sha256(value)}


def render() -> tuple[bytes, bytes]:
    contract = _json(CONTRACT)
    if (
        contract.get("story_id") != "ST-1201"
        or contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
    ):
        _fail("CONTRACT_INVALID", CONTRACT.as_posix())
    durability_value = contract.get("durability_boundary")
    application_port_value = contract.get("application_port_boundary")
    if type(durability_value) is not dict or type(application_port_value) is not dict:
        _fail("CONTRACT_INVALID", CONTRACT.as_posix())
    durability = cast(dict[str, object], durability_value)
    application_port = cast(dict[str, object], application_port_value)
    if (
        durability.get("created_only_schema_initialization") is not True
        or durability.get("root_and_database_device_inode_pinned") is not True
        or durability.get("same_process_event_count_head_prefix_anchor") is not True
        or durability.get("fresh_process_rollback_detection_without_external_anchor")
        is not False
        or durability.get("metadata_old_count_head_digest_cas") is not True
        or durability.get("commit_recovery_outcomes")
        != ["COMMITTED", "NOT_COMMITTED", "AMBIGUOUS"]
        or application_port.get("collaborator_inputs_reconstructed") is not True
        or application_port.get(
            "post_success_domain_error_unexpected_error_verification"
        )
        is not True
        or application_port.get(
            "action_count_exact_integer_zero_before_and_after_each_exchange"
        )
        is not True
    ):
        _fail("CONTRACT_INVALID", CONTRACT.as_posix())
    story = _story()
    checks = _canonical_checks()
    source_bindings = [_binding(path) for path in OWNED_SOURCES + BOUND_SOURCES]
    generated_document: dict[str, object] = {
        "schema_version": "2.0.0",
        "story_id": "ST-1201",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "canonical_checks": checks,
        "story_binding": {
            "id": story["id"],
            "depends_on": story["depends_on"],
            "test_suites": story["test_suites"],
            "open_decisions": story["open_decisions"],
        },
        "contract_sha256": _sha256(_bytes(CONTRACT)),
        "source_bindings": source_bindings,
        "durability_boundary": durability,
        "application_port_boundary": application_port,
        "authority": contract["authority"],
        "formal_evidence": contract["formal_evidence"],
    }
    generated = (
        json.dumps(
            generated_document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    manifest_document = {
        "schema_version": "2.0.0",
        "story_id": "ST-1201",
        "owner_generator": "scripts/build_st1201_durable_event_store.py",
        "sources": source_bindings,
        "outputs": [
            {
                "path": GENERATED.as_posix(),
                "bytes": len(generated),
                "sha256": _sha256(generated),
            }
        ],
        "external_action_count": 0,
        "formal_evidence": "NOT_EXECUTED",
    }
    manifest = (
        json.dumps(
            manifest_document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    return generated, manifest


def _write(path: Path, value: bytes) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--check"]):
        print("usage: build_st1201_durable_event_store.py [--check]", file=sys.stderr)
        return 2
    try:
        generated, manifest = render()
        expected = {GENERATED: generated, MANIFEST: manifest}
        if arguments == ["--check"]:
            for path, value in expected.items():
                if _bytes(path) != value:
                    _fail("GENERATED_ARTIFACT_DRIFT", path.as_posix())
        else:
            for path, value in expected.items():
                _write(path, value)
    except St1201BuildError as error:
        print(f"ST1201_ERROR code={error.code} field={error.field}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
