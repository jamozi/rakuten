#!/usr/bin/env python3
"""Create content-free Phase 3 execution inputs from owner-held export bytes.

This operator never connects to WordPress and never writes outside the one
allowlisted recorded-input directory. Raw exports and restore artifacts must
remain outside the repository; only hashes, version identifiers and the exact
target binding are recorded.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Final, Mapping, NoReturn, Sequence

try:
    from scripts import validate_raos_v2_successor as validator
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    import validate_raos_v2_successor as validator


ROOT: Final = Path(__file__).resolve().parents[1]
MAX_OWNER_EXPORT_BYTES: Final = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES: Final = 128 * 1024 * 1024
MAX_PAIR_AGE_SECONDS: Final = 300
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
RAW_FIELDS: Final = frozenset(validator.PHASE3_WORDPRESS_FIELD_NAMES)
RESTORE_ITEMS: Final = frozenset(
    {
        "author",
        "comment_status",
        "content",
        "excerpt",
        "featured_media",
        "modified_at",
        "ping_status",
        "published_at",
        "seo_fields",
        "slug",
        "status",
        "taxonomy",
        "title",
    }
)
ARTIFACT_ARGUMENTS: Final = {
    "restore_artifact": "restore_artifact_sha256",
    "theme_plugin_artifact": "theme_plugin_artifact_sha256",
    "seo_state": "seo_state_sha256",
    "redirect_map": "redirect_map_sha256",
    "sitemap_state": "sitemap_state_sha256",
}
HISTORICAL_REVIEW_CANDIDATE_PATH: Final = Path(
    "changes/raos-v2/phase-3/generated/review-candidate.v1.json"
)
MAX_REISSUE_AGE_SECONDS: Final = 300
MAX_HUMAN_REVIEW_RECEIPT_BYTES: Final = 64 * 1024
UNAUTHENTICATED_ASSERTION_STATUS: Final = "UNAUTHENTICATED_OWNER_ASSERTION"
OWNER_ASSERTION_REVIEWER_ID: Final = "OWNER_ASSERTION_LOCAL"
OWNER_ASSERTION_REVIEW_VERSION: Final = "P3-OWNER-ASSERTION-V1"


class Phase3ExecutionFailure(RuntimeError):
    """Sanitized operator failure."""


def fail(code: str) -> NoReturn:
    raise Phase3ExecutionFailure(code) from None


def _external_bytes(path: Path, *, maximum: int, code: str) -> bytes:
    """Read one owner-held regular file without exposing its path or content."""

    if not path.is_absolute():
        fail(code)
    try:
        resolved = path.resolve(strict=True)
        repository = ROOT.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        fail(code)
    try:
        resolved.relative_to(repository)
    except ValueError:
        pass
    else:
        fail(code)
    if (
        path.is_symlink()
        or resolved != path
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= maximum
    ):
        fail(code)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
            ):
                fail(code)
            payload = b""
            while len(payload) <= maximum:
                chunk = os.read(
                    descriptor, min(1024 * 1024, maximum + 1 - len(payload))
                )
                if not chunk:
                    break
                payload += chunk
            final_metadata = os.fstat(descriptor)
            if (
                final_metadata.st_dev != opened.st_dev
                or final_metadata.st_ino != opened.st_ino
                or final_metadata.st_size != opened.st_size
                or final_metadata.st_mtime_ns != opened.st_mtime_ns
                or final_metadata.st_ctime_ns != opened.st_ctime_ns
            ):
                fail(code)
        finally:
            os.close(descriptor)
    except OSError:
        fail(code)
    if len(payload) != metadata.st_size or not payload:
        fail(code)
    return payload


def _repository_bytes(path: Path, *, maximum: int, code: str) -> bytes:
    """Read a repository file through no-follow directory descriptors."""

    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail(code)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.open(ROOT, directory_flags)
        for component in path.parts[:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
        try:
            opened = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or not 1 <= opened.st_size <= maximum
            ):
                fail(code)
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    fail(code)
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                fail(code)
            final_metadata = os.fstat(file_descriptor)
            if (
                final_metadata.st_dev != opened.st_dev
                or final_metadata.st_ino != opened.st_ino
                or final_metadata.st_size != opened.st_size
                or final_metadata.st_mtime_ns != opened.st_mtime_ns
                or final_metadata.st_ctime_ns != opened.st_ctime_ns
            ):
                fail(code)
            return b"".join(chunks)
        finally:
            os.close(file_descriptor)
    except OSError:
        fail(code)
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)


def _recorded_capture(path: Path) -> tuple[dict[str, object], datetime, str]:
    if path.is_absolute():
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_PATH_INVALID")
    allowed = validator.PHASE3_RECORDED_ROOT.parts
    if (
        path.parts[: len(allowed)] != allowed
        or len(path.parts) != len(allowed) + 1
        or path.suffix != ".json"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_PATH_INVALID")
    try:
        document = validator.load_json_strict(
            _repository_bytes(
                path,
                maximum=validator.MAX_RESPONSE_BYTES,
                code="RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID",
            )
        )
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID")
    if not isinstance(document, dict):
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID")
    try:
        observation, _captured_at, observed_at = validator._phase3_capture_observation(
            document, code="RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID"
        )
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID")
    body_sha256 = observation.get("body_sha256")
    if (
        observation.get("status") != 200
        or observation.get("redirect_chain") != []
        or observation.get("canonical") != validator.PHASE3_PUBLIC_URL
        or observation.get("canonical_tag_count") != 1
        or observation.get("sitemap_membership") is not True
        or observation.get("body_storage") != "DISCARDED_AFTER_HASH"
        or not isinstance(body_sha256, str)
        or validator.HEX64.fullmatch(body_sha256) is None
    ):
        fail("RAOS_V2_PHASE3_EXECUTION_CAPTURE_INVALID")
    return document, observed_at, body_sha256


def _raw_owner_export(payload: bytes) -> dict[str, object]:
    try:
        value = validator.load_json_strict(payload)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "version",
        "captured_at",
        "target",
        "fields",
        "restore_completeness",
        "wordpress_environment",
    }:
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    target = value.get("target")
    fields = value.get("fields")
    restore = value.get("restore_completeness")
    environment = value.get("wordpress_environment")
    if (
        value.get("schema") != "RAOS_V2_PHASE3_OWNER_EXPORT_RAW_V1"
        or value.get("version") != "1.0.0"
        or not isinstance(target, dict)
        or target
        != {
            "origin": validator.ORIGIN,
            "route": validator.PHASE3_PUBLIC_PATH,
            "kind": "EXISTING_POST",
            "post_id": target.get("post_id"),
            "exact_match_count": 1,
        }
        or type(target.get("post_id")) is not int
        or int(target["post_id"]) < 1
        or not isinstance(fields, dict)
        or set(fields) != RAW_FIELDS
        or any(not isinstance(item, str) for item in fields.values())
        or fields.get("post_status") != "publish"
        or fields.get("post_name") != "carry-on-suitcase-comparison"
        or fields.get("canonical_url") != validator.PHASE3_PUBLIC_URL
        or not isinstance(restore, dict)
        or set(restore) != RESTORE_ITEMS
        or any(value is not True for value in restore.values())
        or not isinstance(environment, dict)
        or set(environment)
        != {"wordpress_core_version", "active_theme", "relevant_plugins"}
    ):
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    try:
        captured_at = datetime.fromisoformat(str(value.get("captured_at")))
    except ValueError:
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    active_theme = environment.get("active_theme")
    plugins = environment.get("relevant_plugins")
    if (
        captured_at.tzinfo is None
        or captured_at.utcoffset() is None
        or not isinstance(environment.get("wordpress_core_version"), str)
        or VERSION.fullmatch(str(environment["wordpress_core_version"])) is None
        or not isinstance(active_theme, dict)
        or set(active_theme) != {"slug", "version"}
        or not isinstance(active_theme.get("slug"), str)
        or SLUG.fullmatch(active_theme["slug"]) is None
        or not isinstance(active_theme.get("version"), str)
        or VERSION.fullmatch(active_theme["version"]) is None
        or not isinstance(plugins, list)
        or plugins
        != sorted(
            plugins,
            key=lambda row: str(row.get("slug")) if isinstance(row, Mapping) else "",
        )
    ):
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    seen: set[str] = set()
    for plugin in plugins:
        if (
            not isinstance(plugin, dict)
            or set(plugin) != {"slug", "version"}
            or not isinstance(plugin.get("slug"), str)
            or SLUG.fullmatch(plugin["slug"]) is None
            or not isinstance(plugin.get("version"), str)
            or VERSION.fullmatch(plugin["version"]) is None
            or plugin["slug"] in seen
        ):
            fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
        seen.add(plugin["slug"])
    return value


def derive_preaction_execution_input(
    *,
    public_capture_path: Path,
    owner_export_path: Path,
    artifact_paths: Mapping[str, Path],
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    capture, observed_at, body_sha256 = _recorded_capture(public_capture_path)
    raw_export = _external_bytes(
        owner_export_path,
        maximum=MAX_OWNER_EXPORT_BYTES,
        code="RAOS_V2_PHASE3_OWNER_EXPORT_UNREADABLE",
    )
    owner = _raw_owner_export(raw_export)
    try:
        export_at = datetime.fromisoformat(str(owner["captured_at"]))
    except ValueError:
        fail("RAOS_V2_PHASE3_OWNER_EXPORT_INVALID")
    assert export_at.tzinfo is not None
    effective_evaluation = evaluated_at or datetime.now().astimezone()
    if effective_evaluation.tzinfo is None or effective_evaluation.utcoffset() is None:
        fail("RAOS_V2_PHASE3_PREACTION_EVALUATION_TIME_INVALID")
    age_milliseconds = abs(int((export_at - observed_at).total_seconds() * 1000))
    if age_milliseconds > MAX_PAIR_AGE_SECONDS * 1000:
        fail("RAOS_V2_PHASE3_PREACTION_PAIR_STALE")
    public_capture_age_milliseconds = int(
        (effective_evaluation - observed_at).total_seconds() * 1000
    )
    owner_export_age_milliseconds = int(
        (effective_evaluation - export_at).total_seconds() * 1000
    )
    if (
        not 0 <= public_capture_age_milliseconds <= MAX_PAIR_AGE_SECONDS * 1000
        or not 0 <= owner_export_age_milliseconds <= MAX_PAIR_AGE_SECONDS * 1000
    ):
        fail("RAOS_V2_PHASE3_PREACTION_INPUT_NOT_CURRENT")
    if set(artifact_paths) != set(ARTIFACT_ARGUMENTS):
        fail("RAOS_V2_PHASE3_OWNER_ARTIFACT_SET_INVALID")
    artifacts: dict[str, dict[str, object]] = {}
    for role in sorted(artifact_paths):
        payload = _external_bytes(
            artifact_paths[role],
            maximum=MAX_ARTIFACT_BYTES,
            code="RAOS_V2_PHASE3_OWNER_ARTIFACT_UNREADABLE",
        )
        artifacts[role] = {"bytes": len(payload), "sha256": validator.sha256(payload)}
    target = owner["target"]
    fields = owner["fields"]
    assert isinstance(target, dict) and isinstance(fields, dict)
    field_hashes = {
        name: validator._semantic_digest({"field": name, "value": fields[name]})
        for name in sorted(RAW_FIELDS)
    }
    legacy_post_content_sha256 = validator.sha256(
        fields["post_content"].encode("utf-8")
    )
    owner_evidence_sha256 = validator._semantic_digest(
        {
            "field_hashes": field_hashes,
            "legacy_post_content_sha256": legacy_post_content_sha256,
            "restore_completeness": owner["restore_completeness"],
            "wordpress_environment": owner["wordpress_environment"],
            "artifacts": artifacts,
        }
    )
    binding = {
        "schema": "RAOS_V2_PHASE3_PREACTION_BINDING_V1",
        "version": "1.0.0",
        "status": "VERIFIED_PREACTION",
        "provenance": "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT",
        "captured_at": max(observed_at, export_at).isoformat(),
        "target": target,
        "current_public_body_sha256": body_sha256,
        "public_capture_sha256": validator._semantic_digest(capture),
        "wordpress_export_sha256": validator.sha256(raw_export),
        "wordpress_export_bytes": len(raw_export),
        "owner_evidence_sha256": owner_evidence_sha256,
        "legacy_post_content_sha256": legacy_post_content_sha256,
    }
    document = {
        "schema": "RAOS_V2_PHASE3_PREACTION_EXECUTION_INPUT_V1",
        "version": "1.0.0",
        "classification": "SANITIZED_DERIVED_INPUT_NO_RAW_EXPORT_BYTES",
        "status": "VERIFIED_PREACTION_INPUT",
        "target": target,
        "pairing": {
            "maximum_age_seconds": MAX_PAIR_AGE_SECONDS,
            "observed_delta_milliseconds": age_milliseconds,
            "evaluated_at": effective_evaluation.isoformat(),
            "public_capture_age_milliseconds": public_capture_age_milliseconds,
            "owner_export_age_milliseconds": owner_export_age_milliseconds,
            "status": "PAIRED_WITHIN_WINDOW",
        },
        "public_capture": {
            "recorded_input": public_capture_path.as_posix(),
            "semantic_sha256": validator._semantic_digest(capture),
            "observed_at": observed_at.isoformat(),
            "body_sha256": body_sha256,
        },
        "owner_export": {
            "captured_at": export_at.isoformat(),
            "raw_export_location": "OWNER_STORAGE_ONLY_NOT_GIT",
            "raw_export_sha256": validator.sha256(raw_export),
            "raw_export_bytes": len(raw_export),
            "field_hashes": field_hashes,
            "legacy_post_content_sha256": legacy_post_content_sha256,
            "restore_completeness": owner["restore_completeness"],
            "wordpress_environment": owner["wordpress_environment"],
            "artifacts": artifacts,
        },
        "preaction_binding": binding,
        "preaction_binding_sha256": validator._semantic_digest(binding),
        "capabilities": {
            "network": False,
            "wordpress_read": False,
            "wordpress_write": False,
            "publish": False,
        },
        "raw_values_persisted": False,
    }
    try:
        validator.verify_phase3_preaction_execution_input(document)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_PREACTION_EXECUTION_INPUT_INVALID")
    return document


def _phase3_recorded_input(path: Path, *, code: str) -> dict[str, object]:
    if path.is_absolute():
        fail(code)
    allowed = validator.PHASE3_RECORDED_ROOT.parts
    if (
        path.parts[: len(allowed)] != allowed
        or len(path.parts) != len(allowed) + 1
        or path.suffix != ".json"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail(code)
    try:
        value = validator.load_json_strict(
            _repository_bytes(
                path,
                maximum=MAX_OWNER_EXPORT_BYTES,
                code=code,
            )
        )
    except validator.ValidationFailure:
        fail(code)
    if not isinstance(value, dict):
        fail(code)
    return value


def reissue_review_candidate(
    *,
    preaction_input_path: Path,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    """Reissue the exact historical candidate from one verified preaction input."""

    preaction_input = _phase3_recorded_input(
        preaction_input_path,
        code="RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID",
    )
    try:
        validator.verify_phase3_preaction_execution_input(preaction_input)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
    binding_record = preaction_input.get("preaction_binding")
    if not isinstance(binding_record, dict):
        fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
    effective_evaluation = evaluated_at or datetime.now().astimezone()
    try:
        captured_at = datetime.fromisoformat(str(binding_record.get("captured_at")))
    except ValueError:
        fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
    public_capture_record = preaction_input.get("public_capture")
    owner_export_record = preaction_input.get("owner_export")
    if not isinstance(public_capture_record, dict) or not isinstance(
        owner_export_record, dict
    ):
        fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
    try:
        public_observed_at = datetime.fromisoformat(
            str(public_capture_record.get("observed_at"))
        )
        owner_export_at = datetime.fromisoformat(
            str(owner_export_record.get("captured_at"))
        )
    except ValueError:
        fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
    if (
        effective_evaluation.tzinfo is None
        or effective_evaluation.utcoffset() is None
        or captured_at.tzinfo is None
        or captured_at.utcoffset() is None
        or public_observed_at.tzinfo is None
        or public_observed_at.utcoffset() is None
        or owner_export_at.tzinfo is None
        or owner_export_at.utcoffset() is None
    ):
        fail("RAOS_V2_PHASE3_REISSUE_INPUT_NOT_CURRENT")
    public_capture_age_milliseconds = int(
        (effective_evaluation - public_observed_at).total_seconds() * 1000
    )
    owner_export_age_milliseconds = int(
        (effective_evaluation - owner_export_at).total_seconds() * 1000
    )
    reissue_age_milliseconds = max(
        public_capture_age_milliseconds, owner_export_age_milliseconds
    )
    if (
        not 0 <= public_capture_age_milliseconds <= MAX_REISSUE_AGE_SECONDS * 1000
        or not 0 <= owner_export_age_milliseconds <= MAX_REISSUE_AGE_SECONDS * 1000
    ):
        fail("RAOS_V2_PHASE3_REISSUE_INPUT_NOT_CURRENT")

    try:
        historical_bytes = _repository_bytes(
            HISTORICAL_REVIEW_CANDIDATE_PATH,
            maximum=MAX_OWNER_EXPORT_BYTES,
            code="RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID",
        )
        historical = validator.load_json_strict(historical_bytes)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
    if not isinstance(historical, dict):
        fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
    try:
        from scripts import build_raos_v2_successor as successor_builder
    except ModuleNotFoundError:  # direct ``python scripts/...`` execution
        successor_builder = import_module("build_raos_v2_successor")
    try:
        current_historical = (
            successor_builder.current_phase3_historical_review_candidate_document()
        )
    except successor_builder.BuildFailure:
        fail("RAOS_V2_PHASE3_CURRENT_CANDIDATE_DERIVATION_INVALID")
    if historical_bytes != validator.canonical_json_bytes(current_historical):
        fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_DRIFT")

    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.application.decision_support_v2.phase3_publication import (
            bind_verified_preaction,
            build_phase3_review_candidate,
        )
        from raos.domain.decision_support_v2.models import (
            ClaimStatus,
            ClaimType,
            FreshnessState,
            RiskClass,
        )
        from raos.domain.decision_support_v2.phase3_publication import (
            Phase3ClaimBinding,
            Phase3PreActionBinding,
            Phase3WordPressUpdateFields,
            Phase3WordPressUpdatePayload,
        )
        from raos.domain.decision_support_v2.publication import PublicationPackage

        phase2_record = historical["phase2_candidate"]
        binding_rows = historical["claim_bindings"]
        historical_update = historical["update_payload"]
        if (
            not isinstance(phase2_record, dict)
            or not isinstance(binding_rows, list)
            or not isinstance(historical_update, dict)
            or historical.get("preaction_status") != "HISTORICAL_BASELINE_ONLY"
            or historical.get("preaction_binding_digest") is not None
        ):
            fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
        phase2_candidate = PublicationPackage.from_contract_record(phase2_record)
        claim_bindings = tuple(
            Phase3ClaimBinding(
                claim_id=str(row["claim_id"]),
                claim_type=ClaimType(str(row["claim_type"])),
                risk_class=RiskClass(str(row["risk_class"])),
                freshness=FreshnessState(str(row["freshness"])),
                authoritative_source_status=ClaimStatus(
                    str(row["authoritative_source_status"])
                ),
                checked_at=datetime.fromisoformat(str(row["checked_at"])),
                next_review_at=datetime.fromisoformat(str(row["next_review_at"])),
            )
            for row in binding_rows
            if isinstance(row, dict)
        )
        if len(claim_bindings) != len(binding_rows):
            fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
        fields_record = historical_update["fields"]
        target_record = historical_update["target"]
        if not isinstance(fields_record, dict) or not isinstance(target_record, dict):
            fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
        fields = Phase3WordPressUpdateFields(
            post_title=str(fields_record["post_title"]),
            post_content=str(fields_record["post_content"]),
            post_excerpt=str(fields_record["post_excerpt"]),
            meta_description=str(fields_record["meta_description"]),
            post_name=str(fields_record["post_name"]),
            post_status=str(fields_record["post_status"]),
            comment_status=str(fields_record["comment_status"]),
            ping_status=str(fields_record["ping_status"]),
        )
        historical_payload = Phase3WordPressUpdatePayload(
            fields=fields,
            expected_public_body_sha256=str(
                target_record["expected_public_body_sha256"]
            ),
        )
        rebuilt_historical = build_phase3_review_candidate(
            phase2_candidate=phase2_candidate,
            claim_bindings=claim_bindings,
            update_payload=historical_payload,
        )
        if rebuilt_historical.to_contract_record() != historical:
            fail("RAOS_V2_PHASE3_HISTORICAL_CANDIDATE_INVALID")
        target = binding_record["target"]
        if not isinstance(target, dict):
            fail("RAOS_V2_PHASE3_REISSUE_PREACTION_INPUT_INVALID")
        binding = Phase3PreActionBinding(
            captured_at=captured_at,
            post_id=int(target["post_id"]),
            current_public_body_sha256=str(
                binding_record["current_public_body_sha256"]
            ),
            public_capture_sha256=str(binding_record["public_capture_sha256"]),
            wordpress_export_sha256=str(binding_record["wordpress_export_sha256"]),
            wordpress_export_bytes=int(binding_record["wordpress_export_bytes"]),
            owner_evidence_sha256=str(binding_record["owner_evidence_sha256"]),
            legacy_post_content_sha256=str(
                binding_record["legacy_post_content_sha256"]
            ),
        )
        rebound_payload = bind_verified_preaction(
            payload=historical_payload,
            binding=binding,
        )
        candidate = build_phase3_review_candidate(
            phase2_candidate=phase2_candidate,
            claim_bindings=claim_bindings,
            update_payload=rebound_payload,
        )
    except KeyError, TypeError, ValueError:
        fail("RAOS_V2_PHASE3_REISSUE_CONTRACT_INVALID")
    blockers = candidate.seal_blockers(reviewed_at=effective_evaluation)
    if blockers:
        fail("RAOS_V2_PHASE3_REISSUE_CLAIM_GATE_BLOCKED")
    candidate_record = dict(candidate.to_contract_record())
    document: dict[str, object] = {
        "schema": "RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_V1",
        "version": "1.0.0",
        "classification": "LOCAL_REISSUE_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW",
        "state": "READY_FOR_ARTIFACT_SPECIFIC_HUMAN_REVIEW",
        "reissued_at": effective_evaluation.isoformat(),
        "reissue_age_milliseconds": reissue_age_milliseconds,
        "public_capture_age_milliseconds": public_capture_age_milliseconds,
        "owner_export_age_milliseconds": owner_export_age_milliseconds,
        "maximum_reissue_age_seconds": MAX_REISSUE_AGE_SECONDS,
        "source": {
            "historical_review_candidate": (
                HISTORICAL_REVIEW_CANDIDATE_PATH.as_posix()
            ),
            "historical_review_candidate_sha256": validator.sha256(historical_bytes),
            "preaction_input": preaction_input_path.as_posix(),
            "preaction_input_sha256": validator._semantic_digest(preaction_input),
            "preaction_binding_sha256": binding.binding_digest,
        },
        "review_candidate": candidate_record,
        "candidate_digest": candidate.candidate_digest,
        "payload_digest": candidate.payload_digest,
        "review_request": {
            "required_receipt_schema": ("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"),
            "candidate_digest": candidate.candidate_digest,
            "payload_digest": candidate.payload_digest,
            "target_route": validator.PHASE3_PUBLIC_PATH,
            "generic_approval_accepted": False,
            "artifact_specific_review_required": True,
        },
        "capabilities": {
            "network": False,
            "wordpress_read": False,
            "wordpress_write": False,
            "publish": False,
        },
        "external_actions": "NOT_EXECUTED",
    }
    document["review_bundle_sha256"] = validator._semantic_digest(document)
    try:
        validator.verify_phase3_reissued_review_bundle(document, root=ROOT)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_REISSUED_REVIEW_BUNDLE_INVALID")
    return document


def _reconstruct_review_candidate(
    candidate_record: Mapping[str, object],
    *,
    code: str,
) -> object:
    """Rebuild the candidate through closed domain constructors."""

    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.application.decision_support_v2.phase3_publication import (
            build_phase3_review_candidate,
        )
        from raos.domain.decision_support_v2.models import (
            ClaimStatus,
            ClaimType,
            FreshnessState,
            RiskClass,
        )
        from raos.domain.decision_support_v2.phase3_publication import (
            Phase3ClaimBinding,
            Phase3PreActionBinding,
            Phase3WordPressUpdateFields,
            Phase3WordPressUpdatePayload,
        )
        from raos.domain.decision_support_v2.publication import PublicationPackage

        phase2_record = candidate_record["phase2_candidate"]
        claim_rows = candidate_record["claim_bindings"]
        update_record = candidate_record["update_payload"]
        if (
            not isinstance(phase2_record, dict)
            or not isinstance(claim_rows, list)
            or not isinstance(update_record, dict)
        ):
            fail(code)
        phase2_candidate = PublicationPackage.from_contract_record(phase2_record)
        claim_bindings = tuple(
            Phase3ClaimBinding(
                claim_id=str(row["claim_id"]),
                claim_type=ClaimType(str(row["claim_type"])),
                risk_class=RiskClass(str(row["risk_class"])),
                freshness=FreshnessState(str(row["freshness"])),
                authoritative_source_status=ClaimStatus(
                    str(row["authoritative_source_status"])
                ),
                checked_at=datetime.fromisoformat(str(row["checked_at"])),
                next_review_at=datetime.fromisoformat(str(row["next_review_at"])),
            )
            for row in claim_rows
            if isinstance(row, dict)
        )
        fields_record = update_record["fields"]
        target_record = update_record["target"]
        preaction_record = update_record["preaction"]
        if (
            len(claim_bindings) != len(claim_rows)
            or not isinstance(fields_record, dict)
            or not isinstance(target_record, dict)
            or not isinstance(preaction_record, dict)
        ):
            fail(code)
        binding_record = preaction_record["binding"]
        if not isinstance(binding_record, dict):
            fail(code)
        binding_target = binding_record["target"]
        if not isinstance(binding_target, dict):
            fail(code)
        fields = Phase3WordPressUpdateFields(
            post_title=str(fields_record["post_title"]),
            post_content=str(fields_record["post_content"]),
            post_excerpt=str(fields_record["post_excerpt"]),
            meta_description=str(fields_record["meta_description"]),
            post_name=str(fields_record["post_name"]),
            post_status=str(fields_record["post_status"]),
            comment_status=str(fields_record["comment_status"]),
            ping_status=str(fields_record["ping_status"]),
        )
        binding = Phase3PreActionBinding(
            captured_at=datetime.fromisoformat(str(binding_record["captured_at"])),
            post_id=int(binding_target["post_id"]),
            current_public_body_sha256=str(
                binding_record["current_public_body_sha256"]
            ),
            public_capture_sha256=str(binding_record["public_capture_sha256"]),
            wordpress_export_sha256=str(binding_record["wordpress_export_sha256"]),
            wordpress_export_bytes=int(binding_record["wordpress_export_bytes"]),
            owner_evidence_sha256=str(binding_record["owner_evidence_sha256"]),
            legacy_post_content_sha256=str(
                binding_record["legacy_post_content_sha256"]
            ),
        )
        payload = Phase3WordPressUpdatePayload(
            fields=fields,
            expected_public_body_sha256=str(
                target_record["expected_public_body_sha256"]
            ),
            preaction_binding=binding,
        )
        candidate = build_phase3_review_candidate(
            phase2_candidate=phase2_candidate,
            claim_bindings=claim_bindings,
            update_payload=payload,
        )
        if candidate.to_contract_record() != candidate_record:
            fail(code)
        return candidate
    except KeyError, TypeError, ValueError:
        fail(code)


def _review_timing_is_current(
    *,
    bundle: Mapping[str, object],
    reviewed_at: datetime,
    evaluated_at: datetime,
) -> bool:
    try:
        reissued_at = datetime.fromisoformat(str(bundle.get("reissued_at")))
    except KeyError, TypeError, ValueError:
        return False
    public_age = bundle.get("public_capture_age_milliseconds")
    owner_age = bundle.get("owner_export_age_milliseconds")
    if type(public_age) is not int or type(owner_age) is not int:
        return False
    if any(
        instant.tzinfo is None or instant.utcoffset() is None
        for instant in (evaluated_at, reissued_at, reviewed_at)
    ):
        return False
    review_delay = int((reviewed_at - reissued_at).total_seconds() * 1000)
    return (
        0 <= review_delay <= MAX_REISSUE_AGE_SECONDS * 1000
        and 0 <= public_age + review_delay <= MAX_REISSUE_AGE_SECONDS * 1000
        and 0 <= owner_age + review_delay <= MAX_REISSUE_AGE_SECONDS * 1000
        and reviewed_at <= evaluated_at
    )


def verify_phase3_sealed_package_semantics(
    sealed_package: Mapping[str, object],
    *,
    review_bundle: Mapping[str, object],
    evaluated_at: datetime | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Independently reconstruct and verify one simulation-only local seal."""

    code = "RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID"
    effective_root = root or ROOT
    try:
        validator.verify_phase3_reissued_review_bundle(
            review_bundle, root=effective_root
        )
        validator._validate_phase3_publication_package_schema(
            sealed_package, root=effective_root
        )
    except validator.ValidationFailure:
        fail(code)
    candidate_record = sealed_package.get("review_candidate")
    receipt_record = sealed_package.get("human_review_receipt")
    if (
        not isinstance(candidate_record, dict)
        or candidate_record != review_bundle.get("review_candidate")
        or not isinstance(receipt_record, dict)
        or set(receipt_record)
        != {
            "schema",
            "version",
            "reviewer_id",
            "reviewed_at",
            "review_version",
            "correction_count",
            "accepted",
            "synthetic",
            "candidate_digest",
            "payload_digest",
            "target_route",
            "assertion_status",
            "acceptance_authority",
        }
        or receipt_record.get("assertion_status") != UNAUTHENTICATED_ASSERTION_STATUS
        or receipt_record.get("reviewer_id") != OWNER_ASSERTION_REVIEWER_ID
        or receipt_record.get("review_version") != OWNER_ASSERTION_REVIEW_VERSION
        or receipt_record.get("acceptance_authority") is not False
        or sealed_package.get("simulation_only") is not True
        or sealed_package.get("approval_acceptance_authority") is not False
    ):
        fail(code)
    candidate = _reconstruct_review_candidate(candidate_record, code=code)
    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.application.decision_support_v2.phase3_publication import (
            bind_human_review,
            seal_reviewed_package,
        )
        from raos.domain.decision_support_v2.phase3_publication import (
            Phase3HumanReviewReceipt,
        )

        reviewed_at = datetime.fromisoformat(str(receipt_record["reviewed_at"]))
        effective_evaluation = evaluated_at or datetime.now().astimezone()
        if not _review_timing_is_current(
            bundle=review_bundle,
            reviewed_at=reviewed_at,
            evaluated_at=effective_evaluation,
        ):
            fail(code)
        receipt = Phase3HumanReviewReceipt(
            reviewer_id=str(receipt_record["reviewer_id"]),
            reviewed_at=reviewed_at,
            review_version=str(receipt_record["review_version"]),
            correction_count=int(receipt_record["correction_count"]),
            accepted=receipt_record["accepted"],
            synthetic=receipt_record["synthetic"],
            candidate_digest=str(receipt_record["candidate_digest"]),
            payload_digest=str(receipt_record["payload_digest"]),
            target_route=str(receipt_record["target_route"]),
            assertion_status=str(receipt_record["assertion_status"]),
            acceptance_authority=receipt_record["acceptance_authority"],
        )
        expected = seal_reviewed_package(
            bind_human_review(candidate=candidate, receipt=receipt)
        )
        expected_record = dict(expected.to_contract_record())
        if expected_record != sealed_package or not expected.verify_seal(
            as_of=effective_evaluation
        ):
            fail(code)
    except KeyError, TypeError, ValueError:
        fail(code)
    return {
        "state": "PACKAGE_SEALED",
        "simulation_only": True,
        "assertion_status": UNAUTHENTICATED_ASSERTION_STATUS,
        "acceptance_authority": False,
        "phase_exit": "BLOCKED_EXTERNAL",
        "public_write_authority": False,
    }


def seal_reissued_review_candidate(
    *,
    review_bundle_path: Path,
    human_review_receipt_path: Path,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    """Bind an exact non-synthetic receipt and create a local sealed package."""

    bundle = _phase3_recorded_input(
        review_bundle_path,
        code="RAOS_V2_PHASE3_SEAL_REVIEW_BUNDLE_INVALID",
    )
    try:
        validator.verify_phase3_reissued_review_bundle(bundle, root=ROOT)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_SEAL_REVIEW_BUNDLE_INVALID")
    raw_receipt = _external_bytes(
        human_review_receipt_path,
        maximum=MAX_HUMAN_REVIEW_RECEIPT_BYTES,
        code="RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_UNREADABLE",
    )
    try:
        receipt_record = validator.load_json_strict(raw_receipt)
    except validator.ValidationFailure:
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID")
    if not isinstance(receipt_record, dict) or set(receipt_record) != {
        "schema",
        "version",
        "reviewer_id",
        "reviewed_at",
        "review_version",
        "correction_count",
        "accepted",
        "synthetic",
        "candidate_digest",
        "payload_digest",
        "target_route",
        "assertion_status",
        "acceptance_authority",
    }:
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID")
    if (
        receipt_record.get("schema") != "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1"
        or receipt_record.get("version") != "1.0.0"
        or receipt_record.get("reviewer_id") != OWNER_ASSERTION_REVIEWER_ID
        or not isinstance(receipt_record.get("reviewed_at"), str)
        or receipt_record.get("review_version") != OWNER_ASSERTION_REVIEW_VERSION
        or type(receipt_record.get("correction_count")) is not int
        or type(receipt_record.get("accepted")) is not bool
        or type(receipt_record.get("synthetic")) is not bool
        or receipt_record.get("accepted") is not True
        or receipt_record.get("synthetic") is not False
        or not isinstance(receipt_record.get("candidate_digest"), str)
        or receipt_record.get("candidate_digest") != bundle.get("candidate_digest")
        or not isinstance(receipt_record.get("payload_digest"), str)
        or receipt_record.get("payload_digest") != bundle.get("payload_digest")
        or receipt_record.get("target_route") != validator.PHASE3_PUBLIC_PATH
        or receipt_record.get("assertion_status") != UNAUTHENTICATED_ASSERTION_STATUS
        or receipt_record.get("acceptance_authority") is not False
    ):
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID")
    try:
        reviewed_at = datetime.fromisoformat(str(receipt_record.get("reviewed_at")))
    except ValueError:
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID")
    effective_evaluation = evaluated_at or datetime.now().astimezone()
    if not _review_timing_is_current(
        bundle=bundle,
        reviewed_at=reviewed_at,
        evaluated_at=effective_evaluation,
    ):
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_NOT_CURRENT")
    candidate_record = bundle.get("review_candidate")
    if not isinstance(candidate_record, dict):
        fail("RAOS_V2_PHASE3_SEAL_REVIEW_BUNDLE_INVALID")
    candidate = _reconstruct_review_candidate(
        candidate_record,
        code="RAOS_V2_PHASE3_SEAL_REVIEW_BUNDLE_INVALID",
    )
    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.application.decision_support_v2.phase3_publication import (
            bind_human_review,
            seal_reviewed_package,
        )
        from raos.domain.decision_support_v2.phase3_publication import (
            Phase3HumanReviewReceipt,
        )

        receipt = Phase3HumanReviewReceipt(
            reviewer_id=receipt_record["reviewer_id"],
            reviewed_at=reviewed_at,
            review_version=receipt_record["review_version"],
            correction_count=receipt_record["correction_count"],
            accepted=receipt_record["accepted"],
            synthetic=receipt_record["synthetic"],
            candidate_digest=receipt_record["candidate_digest"],
            payload_digest=receipt_record["payload_digest"],
            target_route=receipt_record["target_route"],
            assertion_status=receipt_record["assertion_status"],
            acceptance_authority=receipt_record["acceptance_authority"],
        )
        sealed = seal_reviewed_package(
            bind_human_review(candidate=candidate, receipt=receipt)
        )
        sealed_record = dict(sealed.to_contract_record())
    except KeyError, TypeError, ValueError:
        fail("RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_INVALID")
    verify_phase3_sealed_package_semantics(
        sealed_record,
        review_bundle=bundle,
        evaluated_at=effective_evaluation,
        root=ROOT,
    )
    return sealed_record


def build_wordpress_cutover_binding(
    sealed_package: Mapping[str, object],
    *,
    review_bundle: Mapping[str, object],
) -> dict[str, object]:
    """Fail closed until authenticated approval and pre-write evidence exist."""

    verify_phase3_sealed_package_semantics(
        sealed_package,
        review_bundle=review_bundle,
        root=ROOT,
    )
    # An ARMED binding must be downstream of all three independently verified
    # external artifacts: authenticated artifact-specific approval, a fresh
    # PRE_WRITE_EXPORT captured after that approval, and a disabled-plugin
    # WordPress dry-run receipt.  Phase 3 intentionally has no trusted source or
    # verifier for those artifacts, so local owner-authored JSON cannot arm it.
    fail("RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED")


def _preflight_seal_outputs(sealed_output: Path, cutover_output: Path) -> None:
    """Reject both create-once outputs before consuming a review receipt."""

    if sealed_output == cutover_output:
        fail("RAOS_V2_PHASE3_WORDPRESS_CUTOVER_OUTPUT_COLLISION")
    validator._phase3_capture_output_path(sealed_output)
    validator._phase3_capture_output_path(cutover_output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    derive = commands.add_parser(
        "derive-preaction", help="derive one sanitized preaction input"
    )
    derive.add_argument("--public-capture", type=Path, required=True)
    derive.add_argument("--owner-export", type=Path, required=True)
    for argument in ARTIFACT_ARGUMENTS:
        derive.add_argument(f"--{argument.replace('_', '-')}", type=Path, required=True)
    derive.add_argument("--output", type=Path, required=True)
    reissue = commands.add_parser(
        "reissue-candidate",
        help="reissue one exact review candidate from a fresh preaction input",
    )
    reissue.add_argument("--preaction-input", type=Path, required=True)
    reissue.add_argument("--output", type=Path, required=True)
    seal = commands.add_parser(
        "seal-candidate",
        help="bind an artifact-specific receipt and create a local sealed package",
    )
    seal.add_argument("--review-bundle", type=Path, required=True)
    seal.add_argument("--human-review-receipt", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument(
        "--cutover-binding-output",
        type=Path,
        help=(
            "reserved; ARMED generation is blocked until trusted approval, a "
            "fresh PRE_WRITE_EXPORT, and disabled-plugin dry-run evidence exist"
        ),
    )
    derive_cutover = commands.add_parser(
        "derive-cutover-binding",
        help=(
            "verify a simulation seal, then fail closed until trusted approval, "
            "fresh PRE_WRITE_EXPORT, and disabled-plugin dry-run evidence exist"
        ),
    )
    derive_cutover.add_argument("--sealed-package", type=Path, required=True)
    derive_cutover.add_argument("--review-bundle", type=Path, required=True)
    derive_cutover.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "derive-preaction":
            artifact_paths = {
                name: getattr(arguments, name) for name in ARTIFACT_ARGUMENTS
            }
            document = derive_preaction_execution_input(
                public_capture_path=arguments.public_capture,
                owner_export_path=arguments.owner_export,
                artifact_paths=artifact_paths,
            )
        elif arguments.command == "reissue-candidate":
            document = reissue_review_candidate(
                preaction_input_path=arguments.preaction_input,
            )
        elif arguments.command == "seal-candidate":
            if arguments.cutover_binding_output is not None:
                _preflight_seal_outputs(
                    arguments.output,
                    arguments.cutover_binding_output,
                )
                fail("RAOS_V2_PHASE3_CUTOVER_PREWRITE_EVIDENCE_REQUIRED")
            document = seal_reissued_review_candidate(
                review_bundle_path=arguments.review_bundle,
                human_review_receipt_path=arguments.human_review_receipt,
            )
        else:
            sealed_package = _phase3_recorded_input(
                arguments.sealed_package,
                code="RAOS_V2_PHASE3_SEALED_PACKAGE_INVALID",
            )
            current_review_bundle = _phase3_recorded_input(
                arguments.review_bundle,
                code="RAOS_V2_PHASE3_SEAL_REVIEW_BUNDLE_INVALID",
            )
            document = build_wordpress_cutover_binding(
                sealed_package,
                review_bundle=current_review_bundle,
            )
        validator._write_new_phase3_capture(
            arguments.output, validator.canonical_json_bytes(document)
        )
    except (Phase3ExecutionFailure, validator.ValidationFailure) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    source = document.get("source")
    source_preaction_binding_sha256 = (
        source.get("preaction_binding_sha256") if isinstance(source, dict) else None
    )
    print(
        json.dumps(
            {
                "schema": document["schema"],
                "state": document.get("state", document.get("status")),
                "preaction_binding_sha256": (
                    document.get("preaction_binding_sha256")
                    or source_preaction_binding_sha256
                ),
                "raw_values_persisted": document.get("raw_values_persisted", False),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
