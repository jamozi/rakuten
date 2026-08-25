#!/usr/bin/env python3
"""Build the deterministic, recorded-only ST-1403 runtime bindings."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn, TypeVar


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_policy_engine import load_recorded_policy_fixture  # noqa: E402
from raos.application.freshness.refresh_proposal import (  # noqa: E402
    bind_refresh_proposal_request,
)
from raos.domain.editorial.policy_engine_v2 import (  # noqa: E402
    PolicyEvaluationStatusV2,
    evaluate_editorial_policy_v2,
)
from raos.domain.freshness.freshness import (  # noqa: E402
    FreshnessEvaluationRequest,
    FreshnessObservationStatus,
    evaluate_freshness,
)
from raos.domain.freshness.refresh_proposal import (  # noqa: E402
    RefreshActionType,
    RefreshChangeType,
    RefreshChangedEntityType,
    RefreshDiff,
    RefreshDiffKind,
    RefreshImpactLevel,
    RefreshImpactSurface,
    RefreshProposalCandidate,
    RefreshRequiredAction,
    build_refresh_proposal,
)
from secure_generated_publication import publish_generated  # noqa: E402


CONTRACT_PATH = ROOT / "changes/st-1403/contracts/refresh-proposal-runtime.v2.json"
OUTPUT_PATH = ROOT / "changes/st-1403/generated/refresh-proposal-recorded.v2.json"
MANIFEST_PATH = ROOT / "changes/st-1403/runtime-manifest.v2.json"
INTEGRATION_BASE_SHA = "d96614da45f7676b622df20164de28cc8d12c2d8"
MAXIMUM_SOURCE_BYTES = 8 * 1024 * 1024
MAXIMUM_OUTPUT_BYTES = 2 * 1024 * 1024
_SHA = frozenset("0123456789abcdef")
_EnumT = TypeVar("_EnumT", bound=Enum)

SOURCE_PATHS = (
    "changes/st-1403/contracts/refresh-proposal-runtime.v2.json",
    "changes/st-1403/README.md",
    "python/raos/domain/freshness/refresh_proposal.py",
    "python/raos/ports/refresh_proposal.py",
    "python/raos/application/freshness/refresh_proposal.py",
    "python/raos/adapters/recorded_refresh_proposal.py",
    "scripts/build_st1403_refresh_proposal_runtime.py",
    "scripts/secure_generated_publication.py",
)

ROOT_KEYS = (
    "schemaVersion",
    "storyId",
    "classification",
    "environment",
    "recordedAt",
    "bindings",
    "candidate",
    "freshness",
    "diffs",
    "authority",
)
BINDING_KEYS = (
    "canonicalIntegration",
    "canonicalDecisions",
    "canonicalOpenDecisions",
    "storyBacklog",
    "testCatalog",
    "securityCatalog",
    "st1401Completion",
    "st1401Domain",
    "st0805Completion",
    "st0805Contract",
    "st0805Fixture",
    "st0805Domain",
    "securePublication",
)
DEPENDENCY_BINDING_KEYS = tuple(sorted(BINDING_KEYS))


class GeneratorFailure(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str = "ST1403_GENERATION_INVALID") -> NoReturn:
    raise GeneratorFailure(code) from None


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail()


def _mapping(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(keys):
        _fail()
    return value


def _string(value: object, *, maximum: int = 512) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail()
    return value


def _sha256(value: object) -> str:
    text = _string(value, maximum=64)
    if len(text) != 64 or any(character not in _SHA for character in text):
        _fail()
    return text


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _enum(enum_type: type[_EnumT], value: object) -> _EnumT:
    text = _string(value)
    try:
        result = enum_type(text)
    except ValueError:
        _fail()
    return result


def _instant(value: object) -> datetime:
    text = _string(value, maximum=32)
    if not text.endswith("Z"):
        _fail()
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError:
        _fail()
    if (
        parsed.tzinfo != timezone.utc
        or parsed.isoformat().replace("+00:00", "Z") != text
    ):
        _fail()
    return parsed


def _read_regular(path: Path, *, maximum: int = MAXIMUM_SOURCE_BYTES) -> bytes:
    try:
        before = path.lstat()
    except OSError:
        _fail("ST1403_SOURCE_UNAVAILABLE")
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_size <= 0
        or before.st_size > maximum
    ):
        _fail("ST1403_SOURCE_INVALID")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _fail("ST1403_SOURCE_INVALID")
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            _fail("ST1403_SOURCE_CHANGED")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail("ST1403_SOURCE_CHANGED")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail("ST1403_SOURCE_CHANGED")
        after = os.fstat(descriptor)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _fail("ST1403_SOURCE_CHANGED")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json_bytes(value: object) -> bytes:
    try:
        payload = (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8", errors="strict")
            + b"\n"
        )
    except TypeError, ValueError, UnicodeError, RecursionError:
        _fail()
    if len(payload) > MAXIMUM_OUTPUT_BYTES:
        _fail()
    return payload


def _load_contract() -> tuple[dict[str, object], bytes]:
    raw = _read_regular(CONTRACT_PATH)
    try:
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except GeneratorFailure:
        raise
    except Exception:
        _fail()
    contract = _mapping(parsed, ROOT_KEYS)
    if (
        contract["schemaVersion"] != 2
        or contract["storyId"] != "ST-1403"
        or contract["classification"] != "RECORDED_SYNTHETIC_REFRESH_PROPOSAL_V2"
        or contract["environment"] != "CI"
        or contract["recordedAt"] != "2026-08-24T03:00:00Z"
    ):
        _fail()
    return contract, raw


def _verify_bindings(contract: dict[str, object]) -> dict[str, str]:
    bindings = _mapping(contract["bindings"], BINDING_KEYS)
    output: dict[str, str] = {}
    for key in BINDING_KEYS:
        binding = _mapping(bindings[key], ("path", "sha256"))
        relative = _string(binding["path"], maximum=512)
        expected = _sha256(binding["sha256"])
        path = ROOT / relative
        if path != Path(os.path.abspath(path)) or not path.is_relative_to(ROOT):
            _fail()
        actual = hashlib.sha256(_read_regular(path)).hexdigest()
        if actual != expected:
            _fail("ST1403_SOURCE_BINDING_MISMATCH")
        output[key] = expected
    return output


def _build_record(contract: dict[str, object], contract_raw: bytes) -> bytes:
    dependency_bindings = _verify_bindings(contract)
    policy_fixture_relative = _string(
        _mapping(
            _mapping(contract["bindings"], BINDING_KEYS)["st0805Fixture"],
            ("path", "sha256"),
        )["path"],
        maximum=512,
    )
    policy_fixture_path = ROOT / policy_fixture_relative
    envelope = load_recorded_policy_fixture(_read_regular(policy_fixture_path))
    report = evaluate_editorial_policy_v2(envelope)
    report.require_valid()
    if (
        report.status is not PolicyEvaluationStatusV2.LOCAL_EVALUATED
        or not report.locally_evaluated
        or report.article_version_id is None
    ):
        _fail("ST1403_POLICY_DEPENDENCY_INELIGIBLE")

    candidate_value = _mapping(
        contract["candidate"],
        (
            "articleVersionId",
            "baselinePublicationSnapshotSha256",
            "candidateSnapshotSha256",
        ),
    )
    if candidate_value["articleVersionId"] != str(report.article_version_id.value):
        _fail("ST1403_POLICY_DEPENDENCY_MISMATCH")
    freshness_value = _mapping(
        contract["freshness"],
        (
            "freshnessClassId",
            "observationStatus",
            "observedAt",
            "evaluatedAt",
            "recommendationBasisAffected",
        ),
    )
    freshness_request = FreshnessEvaluationRequest(
        freshness_class_id=_string(freshness_value["freshnessClassId"]),
        observation_status=_enum(
            FreshnessObservationStatus,
            freshness_value["observationStatus"],
        ),
        observed_at=_instant(freshness_value["observedAt"]),
        evaluated_at=_instant(freshness_value["evaluatedAt"]),
        recommendation_basis_affected=_boolean(
            freshness_value["recommendationBasisAffected"]
        ),
    )
    freshness_report = evaluate_freshness(freshness_request)

    raw_diffs = contract["diffs"]
    if type(raw_diffs) is not list or not 1 <= len(raw_diffs) <= 1_000:
        _fail()
    diffs: list[RefreshDiff] = []
    for value in raw_diffs:
        item = _mapping(
            value,
            (
                "diffId",
                "kind",
                "changeType",
                "changedEntityType",
                "changedEntityId",
                "beforeSha256",
                "afterSha256",
                "affectedClaimIds",
                "impactLevel",
                "requiredAction",
                "impactSurfaces",
                "actionType",
                "deterministicPriorityRank",
                "recommendationRankChange",
            ),
        )
        claims = item["affectedClaimIds"]
        surfaces = item["impactSurfaces"]
        if (
            type(claims) is not list
            or any(type(value) is not str for value in claims)
            or type(surfaces) is not list
        ):
            _fail()
        before = item["beforeSha256"]
        after = item["afterSha256"]
        diffs.append(
            RefreshDiff(
                diff_id=_string(item["diffId"]),
                kind=_enum(RefreshDiffKind, item["kind"]),
                change_type=_enum(RefreshChangeType, item["changeType"]),
                changed_entity_type=_enum(
                    RefreshChangedEntityType,
                    item["changedEntityType"],
                ),
                changed_entity_id=_string(item["changedEntityId"]),
                before_sha256=None if before is None else _sha256(before),
                after_sha256=None if after is None else _sha256(after),
                affected_claim_ids=tuple(_string(value) for value in claims),
                impact_level=_enum(RefreshImpactLevel, item["impactLevel"]),
                required_action=_enum(
                    RefreshRequiredAction,
                    item["requiredAction"],
                ),
                impact_surfaces=tuple(
                    _enum(RefreshImpactSurface, value) for value in surfaces
                ),
                action_type=_enum(RefreshActionType, item["actionType"]),
                deterministic_priority_rank=_integer(
                    item["deterministicPriorityRank"],
                    minimum=1,
                    maximum=1_000,
                ),
                recommendation_rank_change=_boolean(item["recommendationRankChange"]),
            )
        )
    candidate = RefreshProposalCandidate(
        article_version_id=_string(candidate_value["articleVersionId"]),
        baseline_publication_snapshot_sha256=_sha256(
            candidate_value["baselinePublicationSnapshotSha256"]
        ),
        candidate_snapshot_sha256=_sha256(candidate_value["candidateSnapshotSha256"]),
        diffs=tuple(diffs),
    )
    request = bind_refresh_proposal_request(
        candidate=candidate,
        freshness_request=freshness_request,
        freshness_result=freshness_report,
        policy_request=envelope,
        policy_result=report,
    )
    proposal = build_refresh_proposal(request)

    authority = _mapping(
        contract["authority"],
        (
            "humanApprovalRequired",
            "proposalOnly",
            "automaticReorderingAuthorized",
            "canChangeState",
            "persistenceAuthorized",
            "publicationAuthorized",
            "releaseAuthorized",
            "productionEligible",
        ),
    )
    expected_authority = {
        "humanApprovalRequired": True,
        "proposalOnly": True,
        "automaticReorderingAuthorized": False,
        "canChangeState": False,
        "persistenceAuthorized": False,
        "publicationAuthorized": False,
        "releaseAuthorized": False,
        "productionEligible": False,
    }
    if authority != expected_authority:
        _fail()
    return _json_bytes(
        {
            "schemaVersion": 2,
            "storyId": "ST-1403",
            "classification": "RECORDED_SYNTHETIC_REFRESH_PROPOSAL_V2",
            "environment": "CI",
            "recordedAt": contract["recordedAt"],
            "contractSha256": hashlib.sha256(contract_raw).hexdigest(),
            "dependencyBindings": {
                key: dependency_bindings[key] for key in DEPENDENCY_BINDING_KEYS
            },
            "fixtureBindings": [
                {
                    "requestFingerprint": request.fingerprint,
                    "proposalFingerprint": proposal.fingerprint,
                }
            ],
            "authority": expected_authority,
            "formalStatus": {
                "TST-020": "NOT_EXECUTED",
                "TST-021": "NOT_EXECUTED",
                "hostedCi": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
                "publication": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
            },
        }
    )


def _source_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        payload = _read_regular(ROOT / relative)
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    return records


def _manifest_bytes(record: bytes) -> bytes:
    return _json_bytes(
        {
            "schemaVersion": 2,
            "storyId": "ST-1403",
            "classification": "LOCAL_RECORDED_GENERATION_PROVENANCE_V2",
            "integrationBaseSha": INTEGRATION_BASE_SHA,
            "ownerCommand": (
                ".venv/bin/python scripts/build_st1403_refresh_proposal_runtime.py"
            ),
            "checkCommand": (
                ".venv/bin/python scripts/build_st1403_refresh_proposal_runtime.py --check"
            ),
            "sources": _source_records(),
            "artifacts": [
                {
                    "path": str(OUTPUT_PATH.relative_to(ROOT)),
                    "sha256": hashlib.sha256(record).hexdigest(),
                    "bytes": len(record),
                }
            ],
            "authority": {
                "statusAuthority": False,
                "formalEvidenceAuthority": False,
                "publicationAuthority": False,
                "releaseAuthority": False,
                "productionAuthority": False,
            },
        }
    )


def _check_exact(path: Path, expected: bytes) -> bool:
    try:
        actual = _read_regular(path, maximum=MAXIMUM_OUTPUT_BYTES)
    except GeneratorFailure:
        return False
    return actual == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    contract, raw = _load_contract()
    record = _build_record(contract, raw)
    manifest = _manifest_bytes(record)
    if args.check:
        if not _check_exact(OUTPUT_PATH, record) or not _check_exact(
            MANIFEST_PATH, manifest
        ):
            print("ST1403_GENERATED_DRIFT", file=sys.stderr)
            return 1
        return 0
    publish_generated(
        ((OUTPUT_PATH, record), (MANIFEST_PATH, manifest)),
        namespace="st1403-runtime",
        maximum_payload_bytes=MAXIMUM_OUTPUT_BYTES,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GeneratorFailure as failure:
        print(failure.code, file=sys.stderr)
        raise SystemExit(2) from None
