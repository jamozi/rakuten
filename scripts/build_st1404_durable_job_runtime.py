#!/usr/bin/env python3
"""Owner-generate the deterministic ST-1404 local durability projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Final, NoReturn, cast


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.domain.ops.durable_job_runtime import CommitFault  # noqa: E402
from raos.domain.ops.job_runtime import (  # noqa: E402
    ALLOWED_JOB_TRANSITIONS,
    AttemptState,
    InboxState,
    JobState,
    OutboxState,
)


CONTRACT: Final = Path("changes/st-1404/contracts/durable-job-runtime.v2.json")
FIXTURE: Final = Path("changes/st-1404/fixtures/durable-job-runtime.synthetic.v2.json")
OUTPUT: Final = Path("changes/st-1404/generated/durable-job-runtime.v2.json")
MANIFEST: Final = Path("changes/st-1404/manifest.v2.json")
GENERATOR: Final = Path("scripts/build_st1404_durable_job_runtime.py")
CANONICAL: Final = (
    Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
    Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"),
    Path("docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"),
    Path("docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md"),
)
RUNTIME_SOURCE: Final = (
    Path("python/raos/domain/ops/job_runtime.py"),
    Path("python/raos/domain/ops/durable_job_runtime.py"),
    Path("python/raos/ports/durable_job_runtime.py"),
    Path("python/raos/application/ops/durable_job_runtime.py"),
    Path("python/raos/adapters/recorded_durable_job_runtime.py"),
)
MAX_BYTES: Final = 2 * 1024 * 1024
GENERATION_COMMAND: Final = "python scripts/build_st1404_durable_job_runtime.py"


class BuildError(RuntimeError):
    """Stable owner-generator refusal without rejected content."""


def _fail(code: str) -> NoReturn:
    raise BuildError(f"ST-1404 build failed: {code}") from None


def _path(relative: Path) -> Path:
    candidate = REPO_ROOT / relative
    try:
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or REPO_ROOT not in candidate.resolve().parents
        ):
            _fail("SOURCE_PATH_INVALID")
    except OSError:
        _fail("SOURCE_PATH_INVALID")
    return candidate


def _read(relative: Path) -> bytes:
    try:
        value = _path(relative).read_bytes()
    except OSError:
        _fail("SOURCE_UNAVAILABLE")
    if len(value) > MAX_BYTES:
        _fail("SOURCE_SIZE_LIMIT")
    return value


def _sha(relative: Path) -> str:
    return hashlib.sha256(_read(relative)).hexdigest()


def _json_object(relative: Path) -> dict[str, object]:
    try:
        value = cast(object, json.loads(_read(relative)))
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID")
    if type(value) is not dict:
        _fail("JSON_OBJECT_REQUIRED")
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        _fail("JSON_OBJECT_REQUIRED")
    return {cast(str, key): item for key, item in raw.items()}


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("NESTED_OBJECT_REQUIRED")
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        _fail("NESTED_OBJECT_REQUIRED")
    return {cast(str, key): item for key, item in raw.items()}


def _validate(contract: dict[str, object], fixture: dict[str, object]) -> None:
    if (
        contract.get("schema_version") != "2.0.0"
        or contract.get("story_id") != "ST-1404"
    ):
        _fail("CONTRACT_IDENTITY_INVALID")
    if contract.get("local_implementation_status") != "LOCAL_CODE_COMPLETE":
        _fail("LOCAL_STATUS_INVALID")
    runtime = _mapping(contract.get("runtime"))
    formal = _mapping(contract.get("formal_evidence"))
    data = _mapping(contract.get("data_boundary"))
    if any(
        runtime.get(key) is not False
        for key in ("activation", "background_worker", "external_write_authority")
    ):
        _fail("ACTIVATION_BOUNDARY_INVALID")
    if (
        formal.get("TST-013") != "NOT_EXECUTED"
        or formal.get("TST-028") != "NOT_EXECUTED"
    ):
        _fail("FORMAL_BOUNDARY_INVALID")
    if any(
        data.get(key) is not False
        for key in (
            "raw_payload",
            "raw_handler_result",
            "exception_text",
            "credential",
            "provider_response",
        )
    ):
        _fail("DATA_BOUNDARY_INVALID")
    if (
        fixture.get("schema_version") != "2.0.0"
        or fixture.get("synthetic") is not True
        or fixture.get("operational_default") is not False
        or fixture.get("activation") is not False
        or fixture.get("commit_faults") != [item.value for item in CommitFault]
    ):
        _fail("FIXTURE_BOUNDARY_INVALID")


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _render() -> tuple[bytes, bytes]:
    contract = _json_object(CONTRACT)
    fixture = _json_object(FIXTURE)
    _validate(contract, fixture)
    transitions = sorted(
        (source.value, target.value) for source, target in ALLOWED_JOB_TRANSITIONS
    )
    projection = {
        "schema_version": "2.0.0",
        "story_id": "ST-1404",
        "classification": contract["classification"],
        "local_implementation_status": "LOCAL_CODE_COMPLETE",
        "canonical_status": "UNCHANGED",
        "state_contract": {
            "job": [item.value for item in JobState],
            "attempt": [item.value for item in AttemptState],
            "outbox": [item.value for item in OutboxState],
            "inbox": [item.value for item in InboxState],
            "job_transitions": transitions,
        },
        "commit_fault_contract": [item.value for item in CommitFault],
        "synthetic_fixture": fixture,
        "runtime_boundary": contract["runtime"],
        "transaction_boundary": contract["transaction_boundary"],
        "recovery_boundary": contract["recovery_boundary"],
        "data_boundary": contract["data_boundary"],
        "formal_evidence": contract["formal_evidence"],
        "external_actions": [],
    }
    output_bytes = _bytes(projection)
    sources = (*CANONICAL, *RUNTIME_SOURCE, CONTRACT, FIXTURE, GENERATOR)
    manifest = {
        "schema_version": "2.0.0",
        "story_id": "ST-1404",
        "generation_command": GENERATION_COMMAND,
        "source_sha256": {str(path): _sha(path) for path in sources},
        "generated_sha256": {str(OUTPUT): hashlib.sha256(output_bytes).hexdigest()},
        "formal_evidence": "NOT_EXECUTED",
        "live_provider": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }
    return output_bytes, _bytes(manifest)


def _write(relative: Path, content: bytes) -> None:
    target = REPO_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _check(relative: Path, expected: bytes) -> None:
    if _read(relative) != expected:
        _fail("GENERATED_DRIFT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output, manifest = _render()
    if args.check:
        _check(OUTPUT, output)
        _check(MANIFEST, manifest)
    else:
        _write(OUTPUT, output)
        _write(MANIFEST, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
