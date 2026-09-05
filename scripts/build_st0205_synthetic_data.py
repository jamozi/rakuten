#!/usr/bin/env python3
"""Build the deterministic, privacy-safe ST-0205 synthetic fixture bundle."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml
from yaml.tokens import AliasToken, AnchorToken

try:
    from scripts import build_st0201_postgres_service as shared
    from scripts import scan_secrets
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]
    import scan_secrets  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0205/contracts/synthetic-data-factory.v1.yaml")
FIXTURE_BUNDLE_PATH: Final = Path(
    "changes/st-0205/generated/synthetic-fixtures.v1.json"
)
CATALOG_PATH: Final = Path("changes/st-0205/generated/fixture-catalog.v1.json")
MANIFEST_PATH: Final = Path("changes/st-0205/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0205_synthetic_data.py")
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st0205_synthetic_data.py"
)
DEFAULT_SEED: Final = "raos-st-0205-v1"
ORIGIN: Final = "RAOS_ST0205_DETERMINISTIC_FACTORY"
LICENSE: Final = "UNLICENSED"
LICENSE_AUTHORITY_PATH: Final = Path("package.json")
LICENSE_AUTHORITY_SHA256: Final = (
    "730029961c3713d0b2cd6888ae3f04c25d0dbf0ee97b2ed562a43ea792f7e968"
)
MAXIMUM_SEED_BYTES: Final = 128
MAXIMUM_REPOSITORY_ARTIFACT_BYTES: Final = 8 * 1024 * 1024
REPOSITORY_READ_CHUNK_BYTES: Final = 64 * 1024

DOMAIN_ORDER: Final = (
    "ops",
    "iam",
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
    "publishing",
    "freshness",
    "analytics",
    "finance",
    "readmodel",
)
PAYLOAD_ALLOWLISTS: Final = {
    "ops": ("logical_event_id", "delivery_no", "status", "occurred_at"),
    "iam": ("principal_id", "principal_kind", "active", "locale"),
    "portfolio": ("site_id", "locale", "timezone", "business_date"),
    "catalog": ("product_id", "label", "currency", "amount_minor", "observed_at"),
    "evidence": (
        "fact_id",
        "source_ref",
        "confidence_basis_points",
        "observed_at",
    ),
    "editorial": ("article_id", "title", "locale", "version"),
    "ai": ("task_id", "model_ref", "token_count", "cost_minor"),
    "policy": ("bundle_id", "state", "effective_at", "rule_count"),
    "publishing": ("snapshot_id", "state", "content_sha256", "published_at"),
    "freshness": (
        "assessment_id",
        "logical_event_id",
        "sequence_no",
        "observed_at",
        "timezone",
    ),
    "analytics": ("event_id", "event_kind", "pseudonym_sha256", "occurred_at"),
    "finance": ("commission_id", "currency", "amount_minor", "attribution_basis"),
    "readmodel": ("route", "publication_id", "headline", "locale"),
}
SCENARIO_DIMENSIONS: Final = (
    "TIME",
    "CURRENCY",
    "LOCALE",
    "UNICODE",
    "LARGE_VALUE",
    "DST",
    "JST",
    "DUPLICATE",
    "OUT_OF_ORDER",
)
FIXTURE_SCENARIOS: Final = (
    ("ops", "baseline"),
    ("ops", "duplicate-original"),
    ("ops", "duplicate-replay"),
    ("iam", "baseline"),
    ("portfolio", "jst"),
    ("catalog", "unicode-large-jpy"),
    ("evidence", "baseline"),
    ("editorial", "unicode-locale"),
    ("ai", "baseline"),
    ("policy", "baseline"),
    ("publishing", "baseline"),
    ("freshness", "dst-before"),
    ("freshness", "dst-after"),
    ("freshness", "out-of-order-later"),
    ("freshness", "out-of-order-earlier"),
    ("analytics", "baseline"),
    ("finance", "currency-large"),
    ("readmodel", "unicode-locale"),
)
CLASSIFICATION_BY_DOMAIN: Final = {
    "ops": "INTERNAL",
    "iam": "CONFIDENTIAL",
    "portfolio": "INTERNAL",
    "catalog": "INTERNAL",
    "evidence": "CONFIDENTIAL",
    "editorial": "CONFIDENTIAL",
    "ai": "CONFIDENTIAL",
    "policy": "INTERNAL",
    "publishing": "INTERNAL",
    "freshness": "INTERNAL",
    "analytics": "CONFIDENTIAL",
    "finance": "CONFIDENTIAL",
    "readmodel": "PUBLIC",
}
CLASSIFICATIONS: Final = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"})
DOMAIN_ALLOWED_CLASSIFICATIONS: Final = {
    domain: frozenset({classification, "CONFIDENTIAL"})
    for domain, classification in CLASSIFICATION_BY_DOMAIN.items()
}

PINNED_CANONICAL_INPUTS: Final = {
    "docs/manifest.json": (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml": (
        "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d"
    ),
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": (
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
    ),
}
PREDECESSOR_MANIFESTS: Final = (
    (
        "ST-0201",
        Path("changes/st-0201/manifest.yaml"),
        "fce4b7f18cec09425264a1058bda59759e081be0c04826ffa3eae433a68fcda3",
    ),
    (
        "ST-0202",
        Path("changes/st-0202/manifest.yaml"),
        "1aa87d0c3e372cd23a44320584a6fdefb18381c2329caaed3219540c4181cc1e",
    ),
)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0205/README.md"),
    Path("docs/execplans/ST-0205.md"),
    Path("docs/worklogs/ST-0205.md"),
    GENERATOR_PATH,
    Path("tests/st0205/conftest.py"),
    Path("tests/st0205/test_contract.py"),
    Path("tests/st0205/test_factory.py"),
    Path("tests/st0205/test_scenarios.py"),
    Path("tests/st0205/test_privacy.py"),
    Path("tests/st0205/test_generation.py"),
    Path("tests/st0205/test_negative_cases.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("Makefile"),
    Path("README.md"),
    LICENSE_AUTHORITY_PATH,
    Path("scripts/scan_secrets.py"),
)
GENERATED_PATHS: Final = (FIXTURE_BUNDLE_PATH, CATALOG_PATH, MANIFEST_PATH)
JSON_SCALAR_TYPES: Final = (str, int, bool, type(None))
FIXTURE_KEYS: Final = frozenset(
    {
        "fixture_id",
        "schema_domain",
        "scenario",
        "classification",
        "origin",
        "license",
        "payload",
    }
)
REQUIRED_FIXTURE_KEYS: Final = FIXTURE_KEYS - {"classification"}
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
EMAIL_PATTERN: Final = re.compile(
    r"(?i)(?<![a-z0-9.!#$%&'*+/=?^_`{|}~-])[a-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-z0-9-]+(?:\.[a-z0-9-]+)+"
)
IPV4_CANDIDATE_PATTERN: Final = re.compile(
    r"(?<![A-Za-z0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![A-Za-z0-9.])"
)
PROHIBITED_VALUE_MARKERS: Final = (
    "mozilla/",
    "user-agent:",
    "copied-from-production",
    "production-copy",
    "real-customer",
    "live-provider-response",
    "recorded-provider-response",
)
PROHIBITED_STRUCTURAL_KEYS: Final = frozenset(
    {
        "review_body",
        "review_text",
        "review_author",
        "poster_id",
        "poster_name",
        "customer_id",
        "customer_name",
        "person_name",
        "email",
        "ip_address",
        "raw_ip",
        "user_agent",
        "raw_user_agent",
        "credential",
        "password",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
        "raw_prompt",
        "provider_body",
    }
)


class FixtureValidationError(RuntimeError):
    """A fixture crossed a closed ST-0205 construction boundary."""


CapturedRepositoryFile = tuple[bytes, os.stat_result]


def _repository_metadata_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _normalized_repository_path(relative: Path, *, label: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or "\\" in relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe repository path for {label}")
    return Path(*relative.parts)


def _required_repository_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        raise RuntimeError("required repository filesystem safety is unavailable")
    return value


def _read_repository_file(
    root: Path,
    relative: Path,
    label: str,
    *,
    maximum_bytes: int = MAXIMUM_REPOSITORY_ARTIFACT_BYTES,
) -> CapturedRepositoryFile:
    """Capture one stable repository file without pathname reopens or symlinks."""

    normalized = _normalized_repository_path(relative, label=label)
    if (
        type(maximum_bytes) is not int
        or maximum_bytes < 0
        or maximum_bytes > MAXIMUM_REPOSITORY_ARTIFACT_BYTES
    ):
        raise RuntimeError(f"invalid size limit for {label}")

    directory_flag = _required_repository_flag("O_DIRECTORY")
    nofollow_flag = _required_repository_flag("O_NOFOLLOW")
    nonblock_flag = _required_repository_flag("O_NONBLOCK")
    close_on_exec_flag = _required_repository_flag("O_CLOEXEC")
    directory_flags = os.O_RDONLY | directory_flag | nofollow_flag | close_on_exec_flag
    file_flags = os.O_RDONLY | nofollow_flag | nonblock_flag | close_on_exec_flag
    descriptors: list[int] = []
    ancestor_captures: list[tuple[int, str, int, tuple[int, ...]]] = []
    primary_error: BaseException | None = None
    try:
        try:
            root_path_before = root.lstat()
            if stat.S_ISLNK(root_path_before.st_mode) or not stat.S_ISDIR(
                root_path_before.st_mode
            ):
                raise RuntimeError("repository root must be a real directory")
            root_descriptor = os.open(root, directory_flags)
            descriptors.append(root_descriptor)
            root_opened_before = os.fstat(root_descriptor)
            if not stat.S_ISDIR(
                root_opened_before.st_mode
            ) or _repository_metadata_signature(
                root_path_before
            ) != _repository_metadata_signature(root_opened_before):
                raise RuntimeError("repository root changed before secure capture")

            parent_descriptor = root_descriptor
            for part in normalized.parts[:-1]:
                path_before = os.stat(
                    part,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(path_before.st_mode):
                    raise RuntimeError(f"{label} ancestor must be a real directory")
                directory_descriptor = os.open(
                    part,
                    directory_flags,
                    dir_fd=parent_descriptor,
                )
                descriptors.append(directory_descriptor)
                opened_before = os.fstat(directory_descriptor)
                signature = _repository_metadata_signature(path_before)
                if not stat.S_ISDIR(
                    opened_before.st_mode
                ) or signature != _repository_metadata_signature(opened_before):
                    raise RuntimeError(
                        f"{label} ancestor changed during secure capture"
                    )
                ancestor_captures.append(
                    (parent_descriptor, part, directory_descriptor, signature)
                )
                parent_descriptor = directory_descriptor

            leaf = normalized.name
            path_before = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(path_before.st_mode):
                raise RuntimeError(f"{label} must be a regular non-symlink file")
            if path_before.st_nlink != 1:
                raise RuntimeError(f"{label} must have one filesystem link")
            if path_before.st_size < 0 or path_before.st_size > maximum_bytes:
                raise RuntimeError(f"{label} exceeds its size limit")

            file_descriptor = os.open(
                leaf,
                file_flags,
                dir_fd=parent_descriptor,
            )
            descriptors.append(file_descriptor)
            opened_before = os.fstat(file_descriptor)
            stable_signature = _repository_metadata_signature(path_before)
            if not stat.S_ISREG(
                opened_before.st_mode
            ) or stable_signature != _repository_metadata_signature(opened_before):
                raise RuntimeError(f"{label} changed before secure capture")

            remaining = opened_before.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(
                    file_descriptor,
                    min(REPOSITORY_READ_CHUNK_BYTES, remaining),
                )
                if not chunk:
                    raise RuntimeError(f"{label} changed while it was read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                raise RuntimeError(f"{label} changed while it was read")
            content = b"".join(chunks)

            opened_after = os.fstat(file_descriptor)
            path_after = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened_after.st_mode)
                or not stat.S_ISREG(path_after.st_mode)
                or stable_signature != _repository_metadata_signature(opened_after)
                or stable_signature != _repository_metadata_signature(path_after)
                or len(content) != opened_after.st_size
            ):
                raise RuntimeError(f"{label} changed while it was read")

            for (
                ancestor_parent,
                ancestor_name,
                ancestor_descriptor,
                ancestor_signature,
            ) in reversed(ancestor_captures):
                ancestor_opened_after = os.fstat(ancestor_descriptor)
                ancestor_path_after = os.stat(
                    ancestor_name,
                    dir_fd=ancestor_parent,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(ancestor_opened_after.st_mode)
                    or not stat.S_ISDIR(ancestor_path_after.st_mode)
                    or ancestor_signature
                    != _repository_metadata_signature(ancestor_opened_after)
                    or ancestor_signature
                    != _repository_metadata_signature(ancestor_path_after)
                ):
                    raise RuntimeError(
                        f"{label} ancestor changed during secure capture"
                    )

            root_opened_after = os.fstat(root_descriptor)
            root_path_after = root.lstat()
            root_signature = _repository_metadata_signature(root_path_before)
            if (
                not stat.S_ISDIR(root_opened_after.st_mode)
                or not stat.S_ISDIR(root_path_after.st_mode)
                or stat.S_ISLNK(root_path_after.st_mode)
                or root_signature != _repository_metadata_signature(root_opened_after)
                or root_signature != _repository_metadata_signature(root_path_after)
            ):
                raise RuntimeError("repository root changed during secure capture")
            return content, opened_after
        except OSError:
            raise RuntimeError(f"{label} could not be captured safely") from None
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        close_failed = False
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
        if close_failed and primary_error is not None:
            try:
                primary_error.add_note("descriptor cleanup also failed")
            except BaseException:
                pass
        elif close_failed:
            raise RuntimeError(f"{label} descriptor cleanup failed") from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object, *, compact: bool = False) -> bytes:
    separators = (",", ":") if compact else None
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=separators,
            sort_keys=True,
        )
        + ("" if compact else "\n")
    ).encode("utf-8")


def _stable_hex(seed: str, label: str, length: int = 16) -> str:
    return _sha256(f"{seed}\0{label}".encode())[0:length]


def _validate_seed(seed: object) -> str:
    if type(seed) is not str:
        raise FixtureValidationError("fixture seed must be plain text")
    encoded = seed.encode("utf-8")
    if not encoded or len(encoded) > MAXIMUM_SEED_BYTES:
        raise FixtureValidationError("fixture seed is outside the reviewed size bound")
    if any(character.isspace() or ord(character) < 0x21 for character in seed):
        raise FixtureValidationError("fixture seed contains a forbidden character")
    if scan_secrets.scan_bytes(encoded, "fixture-seed"):
        raise FixtureValidationError(
            "fixture seed contains prohibited credential material"
        )
    return seed


def _validate_string_value(value: str) -> None:
    folded = value.casefold()
    if EMAIL_PATTERN.search(value):
        raise FixtureValidationError("fixture contains prohibited personal data")
    candidates = list(IPV4_CANDIDATE_PATTERN.findall(value))
    candidates.extend(re.split(r"[\s,;\[\](){}<>\"']+", value))
    for token in candidates:
        candidate = token.strip().strip(".,")
        if not candidate or (":" not in candidate and "." not in candidate):
            continue
        candidate = candidate.split("%", 1)[0]
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        raise FixtureValidationError(
            "fixture contains prohibited network identity data"
        )
    if any(marker in folded for marker in PROHIBITED_VALUE_MARKERS):
        raise FixtureValidationError("fixture contains prohibited sensitive data")


def _normalized_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    with_word_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
    return re.sub(r"[^a-z0-9]+", "_", with_word_boundaries.casefold()).strip("_")


def _reject_prohibited_structural_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if type(key) is not str:
                raise FixtureValidationError("fixture contains a non-text field name")
            if _normalized_key(key) in PROHIBITED_STRUCTURAL_KEYS:
                raise FixtureValidationError("fixture contains a prohibited data field")
            _reject_prohibited_structural_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_prohibited_structural_keys(child)


def _validate_scalar(value: object) -> None:
    if type(value) not in JSON_SCALAR_TYPES:
        raise FixtureValidationError(
            "fixture payload values must be strict JSON scalars"
        )
    if isinstance(value, str):
        _validate_string_value(value)


def _scenario_payload(domain: str, scenario: str, seed: str) -> dict[str, object]:
    baseline_time = "2026-07-30T03:04:05+00:00"
    event_id = f"event-{_stable_hex(seed, 'duplicate-logical-event')}"
    out_of_order_id = f"event-{_stable_hex(seed, 'out-of-order-logical-event')}"
    payloads: dict[tuple[str, str], dict[str, object]] = {
        ("ops", "baseline"): {
            "logical_event_id": f"event-{_stable_hex(seed, 'ops-baseline')}",
            "delivery_no": 1,
            "status": "READY",
            "occurred_at": baseline_time,
        },
        ("ops", "duplicate-original"): {
            "logical_event_id": event_id,
            "delivery_no": 1,
            "status": "READY",
            "occurred_at": "2026-07-30T03:05:00+00:00",
        },
        ("ops", "duplicate-replay"): {
            "logical_event_id": event_id,
            "delivery_no": 1,
            "status": "READY",
            "occurred_at": "2026-07-30T03:05:00+00:00",
        },
        ("iam", "baseline"): {
            "principal_id": f"synthetic-principal-{_stable_hex(seed, 'iam')}",
            "principal_kind": "SERVICE",
            "active": True,
            "locale": "ja-JP",
        },
        ("portfolio", "jst"): {
            "site_id": f"synthetic-site-{_stable_hex(seed, 'portfolio')}",
            "locale": "ja-JP",
            "timezone": "Asia/Tokyo",
            "business_date": "2026-07-30",
        },
        ("catalog", "unicode-large-jpy"): {
            "product_id": f"synthetic-product-{_stable_hex(seed, 'catalog')}",
            "label": "合成商品 Ω 🧪",
            "currency": "JPY",
            "amount_minor": 9_007_199_254_740_991,
            "observed_at": "2026-07-30T12:04:05+09:00",
        },
        ("evidence", "baseline"): {
            "fact_id": f"synthetic-fact-{_stable_hex(seed, 'evidence')}",
            "source_ref": f"synthetic-source-{_stable_hex(seed, 'source')}",
            "confidence_basis_points": 9_500,
            "observed_at": baseline_time,
        },
        ("editorial", "unicode-locale"): {
            "article_id": f"synthetic-article-{_stable_hex(seed, 'editorial')}",
            "title": "合成比較ガイド Ω 🧪",
            "locale": "ja-JP",
            "version": 1,
        },
        ("ai", "baseline"): {
            "task_id": f"synthetic-task-{_stable_hex(seed, 'ai')}",
            "model_ref": "synthetic-model-v1",
            "token_count": 123_456,
            "cost_minor": 999_999,
        },
        ("policy", "baseline"): {
            "bundle_id": f"synthetic-policy-{_stable_hex(seed, 'policy')}",
            "state": "DRAFT",
            "effective_at": "2026-07-30T00:00:00+09:00",
            "rule_count": 7,
        },
        ("publishing", "baseline"): {
            "snapshot_id": f"synthetic-snapshot-{_stable_hex(seed, 'publishing')}",
            "state": "CANDIDATE",
            "content_sha256": _stable_hex(seed, "publication-content", 64),
            "published_at": None,
        },
        ("freshness", "dst-before"): {
            "assessment_id": f"synthetic-assessment-{_stable_hex(seed, 'dst-before')}",
            "logical_event_id": f"event-{_stable_hex(seed, 'dst-event')}",
            "sequence_no": 1,
            "observed_at": "2026-11-01T01:30:00-04:00",
            "timezone": "America/New_York",
        },
        ("freshness", "dst-after"): {
            "assessment_id": f"synthetic-assessment-{_stable_hex(seed, 'dst-after')}",
            "logical_event_id": f"event-{_stable_hex(seed, 'dst-event')}",
            "sequence_no": 2,
            "observed_at": "2026-11-01T01:30:00-05:00",
            "timezone": "America/New_York",
        },
        ("freshness", "out-of-order-later"): {
            "assessment_id": f"synthetic-assessment-{_stable_hex(seed, 'ooo-later')}",
            "logical_event_id": out_of_order_id,
            "sequence_no": 2,
            "observed_at": "2026-07-30T03:12:00+00:00",
            "timezone": "UTC",
        },
        ("freshness", "out-of-order-earlier"): {
            "assessment_id": f"synthetic-assessment-{_stable_hex(seed, 'ooo-earlier')}",
            "logical_event_id": out_of_order_id,
            "sequence_no": 1,
            "observed_at": "2026-07-30T03:11:00+00:00",
            "timezone": "UTC",
        },
        ("analytics", "baseline"): {
            "event_id": f"synthetic-analytics-{_stable_hex(seed, 'analytics')}",
            "event_kind": "PAGE_VIEW",
            "pseudonym_sha256": _stable_hex(seed, "analytics-pseudonym", 64),
            "occurred_at": baseline_time,
        },
        ("finance", "currency-large"): {
            "commission_id": f"synthetic-commission-{_stable_hex(seed, 'finance')}",
            "currency": "USD",
            "amount_minor": 9_007_199_254_740_991,
            "attribution_basis": "UNATTRIBUTED",
        },
        ("readmodel", "unicode-locale"): {
            "route": f"/synthetic/{_stable_hex(seed, 'route')}",
            "publication_id": f"synthetic-publication-{_stable_hex(seed, 'readmodel')}",
            "headline": "公開用の合成見出し Ω 🧪",
            "locale": "ja-JP",
        },
    }
    try:
        return dict(payloads[(domain, scenario)])
    except KeyError:
        raise FixtureValidationError("unknown fixture domain or scenario") from None


def build_fixture(
    domain: str,
    scenario: str,
    *,
    seed: str = DEFAULT_SEED,
    classification: str | None = None,
) -> dict[str, object]:
    """Build one reviewed scenario without accepting arbitrary fixture payloads."""

    reviewed_seed = _validate_seed(seed)
    if (domain, scenario) not in FIXTURE_SCENARIOS:
        raise FixtureValidationError("unknown fixture domain or scenario")
    reviewed_classification = (
        CLASSIFICATION_BY_DOMAIN[domain] if classification is None else classification
    )
    fixture = {
        "fixture_id": (
            f"fx-{domain}-{scenario}-{_stable_hex(reviewed_seed, f'{domain}:{scenario}', 12)}"
        ),
        "schema_domain": domain,
        "scenario": scenario,
        "classification": reviewed_classification,
        "origin": ORIGIN,
        "license": LICENSE,
        "payload": _scenario_payload(domain, scenario, reviewed_seed),
    }
    return validate_fixture(fixture)


def validate_fixture(value: object) -> dict[str, object]:
    """Return a normalized safe fixture and reject unknown or sensitive content."""

    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        raise FixtureValidationError("fixture must be a string-keyed mapping")
    _reject_prohibited_structural_keys(value)
    keys = frozenset(value)
    if not REQUIRED_FIXTURE_KEYS.issubset(keys) or not keys.issubset(FIXTURE_KEYS):
        raise FixtureValidationError(
            "fixture fields differ from the reviewed allowlist"
        )
    domain = value.get("schema_domain")
    scenario = value.get("scenario")
    if type(domain) is not str or type(scenario) is not str:
        raise FixtureValidationError("fixture identity fields must be plain text")
    if (domain, scenario) not in FIXTURE_SCENARIOS:
        raise FixtureValidationError("unknown fixture domain or scenario")

    classification = value.get("classification", "CONFIDENTIAL")
    if type(classification) is not str:
        raise FixtureValidationError("fixture classification must be plain text")
    if classification == "RESTRICTED":
        raise FixtureValidationError("restricted data cannot enter fixture artifacts")
    if classification not in CLASSIFICATIONS:
        raise FixtureValidationError("unknown classification")
    if classification not in DOMAIN_ALLOWED_CLASSIFICATIONS[domain]:
        raise FixtureValidationError(
            "fixture classification weakens the domain boundary"
        )

    if value.get("origin") != ORIGIN:
        raise FixtureValidationError("fixture origin is missing or invalid")
    if value.get("license") != LICENSE:
        raise FixtureValidationError("fixture license is missing or invalid")
    fixture_id = value.get("fixture_id")
    if type(fixture_id) is not str or not re.fullmatch(
        rf"fx-{re.escape(domain)}-[a-z0-9-]+-[0-9a-f]{{12}}", fixture_id
    ):
        raise FixtureValidationError("fixture identifier is invalid")

    payload = value.get("payload")
    if not isinstance(payload, Mapping) or not all(type(key) is str for key in payload):
        raise FixtureValidationError("fixture payload must be a string-keyed mapping")
    if set(payload) != set(PAYLOAD_ALLOWLISTS[domain]):
        raise FixtureValidationError(
            "fixture payload fields differ from the domain allowlist"
        )
    for payload_value in payload.values():
        _validate_scalar(payload_value)

    normalized = dict(value)
    normalized["classification"] = classification
    normalized["payload"] = {key: payload[key] for key in PAYLOAD_ALLOWLISTS[domain]}
    if scan_secrets.scan_bytes(_json_bytes(normalized, compact=True), "fixture"):
        raise FixtureValidationError("fixture contains prohibited credential material")
    return normalized


def _assert_scenario_coverage(fixtures: Sequence[Mapping[str, object]]) -> None:
    pairs = tuple(
        (fixture.get("schema_domain"), fixture.get("scenario")) for fixture in fixtures
    )
    if pairs != FIXTURE_SCENARIOS:
        raise FixtureValidationError("seed scenario ordering or coverage differs")
    if {domain for domain, _scenario in pairs} != set(DOMAIN_ORDER):
        raise FixtureValidationError("seed scenarios do not cover every schema domain")

    by_pair = {
        (fixture["schema_domain"], fixture["scenario"]): fixture for fixture in fixtures
    }
    duplicate_original = by_pair[("ops", "duplicate-original")]["payload"]
    duplicate_replay = by_pair[("ops", "duplicate-replay")]["payload"]
    if duplicate_original != duplicate_replay:
        raise FixtureValidationError("duplicate scenario payloads differ")

    later = by_pair[("freshness", "out-of-order-later")]["payload"]
    earlier = by_pair[("freshness", "out-of-order-earlier")]["payload"]
    if not isinstance(later, Mapping) or not isinstance(earlier, Mapping):
        raise FixtureValidationError("out-of-order scenario payload is invalid")
    if (
        later.get("logical_event_id") != earlier.get("logical_event_id")
        or later.get("sequence_no") != 2
        or earlier.get("sequence_no") != 1
        or not isinstance(later.get("observed_at"), str)
        or not isinstance(earlier.get("observed_at"), str)
        or later["observed_at"] <= earlier["observed_at"]
    ):
        raise FixtureValidationError("out-of-order scenario semantics differ")

    dst_before = by_pair[("freshness", "dst-before")]["payload"]
    dst_after = by_pair[("freshness", "dst-after")]["payload"]
    if not isinstance(dst_before, Mapping) or not isinstance(dst_after, Mapping):
        raise FixtureValidationError("DST scenario payload is invalid")
    if not (
        str(dst_before.get("observed_at", "")).endswith("-04:00")
        and str(dst_after.get("observed_at", "")).endswith("-05:00")
        and dst_before.get("timezone") == "America/New_York"
        and dst_after.get("timezone") == "America/New_York"
    ):
        raise FixtureValidationError("DST scenario semantics differ")

    catalog_payload = by_pair[("catalog", "unicode-large-jpy")]["payload"]
    finance_payload = by_pair[("finance", "currency-large")]["payload"]
    portfolio_payload = by_pair[("portfolio", "jst")]["payload"]
    if not all(
        isinstance(payload, Mapping)
        for payload in (catalog_payload, finance_payload, portfolio_payload)
    ):
        raise FixtureValidationError("edge scenario payload is invalid")
    if (
        catalog_payload.get("currency") != "JPY"
        or finance_payload.get("currency") != "USD"
        or catalog_payload.get("amount_minor") != 9_007_199_254_740_991
        or finance_payload.get("amount_minor") != 9_007_199_254_740_991
        or portfolio_payload.get("timezone") != "Asia/Tokyo"
        or portfolio_payload.get("locale") != "ja-JP"
        or not any(
            ord(character) > 127 for character in str(catalog_payload.get("label", ""))
        )
    ):
        raise FixtureValidationError(
            "currency, locale, Unicode, large, or JST coverage differs"
        )


def build_seed_bundle(seed: str = DEFAULT_SEED) -> dict[str, object]:
    """Build every approved seed scenario as one deterministic versioned bundle."""

    reviewed_seed = _validate_seed(seed)
    fixtures = [
        build_fixture(domain, scenario, seed=reviewed_seed)
        for domain, scenario in FIXTURE_SCENARIOS
    ]
    _assert_scenario_coverage(fixtures)
    return {
        "document": {
            "id": "RAOS-SYNTHETIC-FIXTURE-BUNDLE-001",
            "version": "1.0.0",
            "story_id": "ST-0205",
            "factory_version": "synthetic-data-factory.v1",
        },
        "seed_fingerprint_sha256": _sha256(reviewed_seed.encode()),
        "scenario_dimensions": list(SCENARIO_DIMENSIONS),
        "domain_count": len(DOMAIN_ORDER),
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "boundary": {
            "synthetic_only": True,
            "provider_or_network_access": "FORBIDDEN",
            "database_or_object_storage_write": "FORBIDDEN",
            "production_or_staging_use": "FORBIDDEN",
        },
    }


def _render_fixture_bundle_once(seed: str = DEFAULT_SEED) -> bytes:
    return _json_bytes(build_seed_bundle(seed))


def render_fixture_bundle(seed: str = DEFAULT_SEED) -> bytes:
    """Render twice and fail if any source of nondeterminism affects bytes."""

    first = _render_fixture_bundle_once(seed)
    second = _render_fixture_bundle_once(seed)
    if first != second:
        raise FixtureValidationError("nondeterministic fixture generation detected")
    return first


def _fixture_record(fixture: Mapping[str, object]) -> dict[str, object]:
    content = _json_bytes(fixture, compact=True)
    return {
        "fixture_id": fixture["fixture_id"],
        "schema_domain": fixture["schema_domain"],
        "scenario": fixture["scenario"],
        "classification": fixture["classification"],
        "origin": fixture["origin"],
        "license": fixture["license"],
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_catalog(bundle_bytes: bytes | None = None) -> bytes:
    """Render the per-fixture integrity/license/origin catalog."""

    content = render_fixture_bundle() if bundle_bytes is None else bundle_bytes
    loaded = json.loads(content)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("fixtures"), list):
        raise FixtureValidationError("fixture bundle is invalid")
    fixtures = [validate_fixture(item) for item in loaded["fixtures"]]
    _assert_scenario_coverage(fixtures)
    catalog = {
        "document": {
            "id": "RAOS-SYNTHETIC-FIXTURE-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0205",
        },
        "bundle": {
            "path": FIXTURE_BUNDLE_PATH.as_posix(),
            "bytes": len(content),
            "sha256": _sha256(content),
            "fixture_count": len(fixtures),
        },
        "fixtures": [_fixture_record(fixture) for fixture in fixtures],
        "control_ids": [
            "SEC-DATA-003",
            "SEC-DATA-004",
            "SEC-DATA-007",
            "SEC-SDLC-006",
        ],
    }
    return _json_bytes(catalog)


def _captured_repository_file(
    root: Path,
    relative: Path,
    label: str,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None,
    *,
    maximum_bytes: int = MAXIMUM_REPOSITORY_ARTIFACT_BYTES,
) -> CapturedRepositoryFile:
    if captured_files is not None:
        try:
            content, metadata = captured_files[relative]
        except KeyError:
            raise RuntimeError(f"missing secure capture for {label}") from None
        if len(content) > maximum_bytes or metadata.st_size > maximum_bytes:
            raise RuntimeError(f"{label} exceeds its size limit")
        return content, metadata
    return _read_repository_file(
        root,
        relative,
        label,
        maximum_bytes=maximum_bytes,
    )


def _assert_digest(
    root: Path,
    relative: Path,
    expected: str,
    label: str,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None = None,
) -> bytes:
    content, _metadata = _captured_repository_file(
        root,
        relative,
        label,
        captured_files,
    )
    if _sha256(content) != expected:
        raise RuntimeError(f"{label} digest drift: {relative}")
    return content


def assert_pinned_inputs(
    root: Path = REPO_ROOT,
    *,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None = None,
) -> None:
    """Fail closed on canonical or ST-0201/ST-0202 manifest drift."""

    for name, digest in PINNED_CANONICAL_INPUTS.items():
        _assert_digest(
            root,
            Path(name),
            digest,
            "canonical input",
            captured_files,
        )
    authority_content = _assert_digest(
        root,
        LICENSE_AUTHORITY_PATH,
        LICENSE_AUTHORITY_SHA256,
        "fixture license authority",
        captured_files,
    )
    try:
        authority = json.loads(authority_content)
    except UnicodeError, json.JSONDecodeError:
        raise RuntimeError("fixture license authority is invalid") from None
    if not isinstance(authority, dict) or authority.get("license") != LICENSE:
        raise RuntimeError("fixture license authority differs from the reviewed value")


def _require_exact(value: object, expected: object, label: str) -> None:
    shared._require_exact(value, expected, label)


def _load_yaml_bytes(content: bytes, *, label: str) -> object:
    if len(content) > shared.MAX_YAML_BYTES:
        raise RuntimeError(f"{label} exceeds its YAML size limit")
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise RuntimeError(f"YAML anchors and aliases are forbidden in {label}")
        return yaml.load(text, Loader=shared.UniqueKeyLoader)
    except UnicodeError:
        raise RuntimeError(f"{label} must be UTF-8 YAML") from None
    except yaml.YAMLError:
        raise RuntimeError(f"{label} is invalid YAML") from None


def load_and_validate_contract(
    root: Path = REPO_ROOT,
    *,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None = None,
) -> dict[str, Any]:
    """Load the source contract and reject semantic or field drift."""

    assert_pinned_inputs(root, captured_files=captured_files)
    contract_content, _metadata = _captured_repository_file(
        root,
        CONTRACT_PATH,
        "ST-0205 contract",
        captured_files,
        maximum_bytes=shared.MAX_YAML_BYTES,
    )
    loaded = _load_yaml_bytes(contract_content, label="ST-0205 contract")
    if not isinstance(loaded, dict):
        raise RuntimeError("ST-0205 contract must be a mapping")
    expected_top_level = {
        "document",
        "story",
        "factory",
        "domains",
        "seed_scenarios",
        "privacy",
        "provenance",
        "security",
        "verification",
        "boundary",
        "out_of_scope",
    }
    if set(loaded) != expected_top_level:
        raise RuntimeError("ST-0205 contract top-level fields differ")
    _require_exact(
        loaded["document"],
        {
            "id": "RAOS-SYNTHETIC-DATA-FACTORY-001",
            "version": "1.0.0",
            "story_id": "ST-0205",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "ST-0205 contract document",
    )
    _require_exact(
        loaded["story"],
        {
            "epic_id": "EPIC-02",
            "title": "Synthetic data factory",
            "objective": "SAFE_FIXTURE_GENERATION_FOR_ALL_DOMAINS",
            "dependencies": ["ST-0201", "ST-0202"],
            "design_refs": ["RAOS-TEST-001"],
            "deliverables": ["DETERMINISTIC_FACTORY", "VERSIONED_SEED_SCENARIOS"],
            "acceptance": ["NO_REVIEW_BODY", "NO_PII"],
            "required_suites": ["TST-005", "TST-031"],
            "open_decisions": [],
        },
        "ST-0205 contract story",
    )
    _require_exact(
        loaded["factory"],
        {
            "version": "synthetic-data-factory.v1",
            "default_seed": DEFAULT_SEED,
            "execution": "PURE_OFFLINE",
            "deterministic": True,
            "network": "FORBIDDEN",
            "environment_read": "FORBIDDEN",
            "provider_sdk": "FORBIDDEN",
            "credentials": "FORBIDDEN",
            "database_write": "FORBIDDEN",
            "object_storage_write": "FORBIDDEN",
            "production_or_staging_data": "FORBIDDEN",
            "unknown_fields": "REJECT",
            "unknown_domain": "REJECT",
            "unknown_scenario": "REJECT",
            "maximum_seed_bytes": MAXIMUM_SEED_BYTES,
        },
        "ST-0205 contract factory",
    )
    domains = loaded["domains"]
    if not isinstance(domains, dict):
        raise RuntimeError("ST-0205 domains must be a mapping")
    _require_exact(
        domains,
        {
            "exact_count": 13,
            "ordered": list(DOMAIN_ORDER),
            "payload_allowlists": {
                name: list(fields) for name, fields in PAYLOAD_ALLOWLISTS.items()
            },
        },
        "ST-0205 domains",
    )
    scenarios = loaded["seed_scenarios"]
    if not isinstance(scenarios, dict):
        raise RuntimeError("ST-0205 seed scenarios must be a mapping")
    _require_exact(
        scenarios,
        {
            "bundle_version": "seed-scenarios.v1",
            "required_dimensions": list(SCENARIO_DIMENSIONS),
            "ordered_fixture_scenarios": [list(pair) for pair in FIXTURE_SCENARIOS],
        },
        "ST-0205 seed scenarios",
    )
    _require_exact(
        loaded["privacy"],
        {
            "construction": "EXACT_DOMAIN_PAYLOAD_ALLOWLISTS",
            "classification_values": [
                "PUBLIC",
                "INTERNAL",
                "CONFIDENTIAL",
                "RESTRICTED",
            ],
            "missing_classification_default": "CONFIDENTIAL",
            "unknown_classification": "REJECT",
            "restricted_classification": "FORBIDDEN_IN_REPOSITORY_AND_LOGS",
            "review_body": "FORBIDDEN",
            "review_author_or_poster": "FORBIDDEN",
            "customer_or_person_data": "FORBIDDEN",
            "email": "FORBIDDEN",
            "raw_ip": "FORBIDDEN",
            "raw_user_agent": "FORBIDDEN",
            "credentials_or_secret_material": "FORBIDDEN",
            "raw_prompt_or_provider_body": "FORBIDDEN",
            "production_copy": "FORBIDDEN",
        },
        "ST-0205 privacy boundary",
    )
    provenance = loaded["provenance"]
    if not isinstance(provenance, dict):
        raise RuntimeError("ST-0205 provenance must be a mapping")
    _require_exact(
        provenance,
        {
            "fixture_origin": ORIGIN,
            "fixture_license": LICENSE,
            "fixture_license_authority": {
                "path": LICENSE_AUTHORITY_PATH.as_posix(),
                "json_pointer": "/license",
                "sha256": LICENSE_AUTHORITY_SHA256,
            },
            "per_fixture_sha256": "REQUIRED",
            "catalog_sha256": "REQUIRED",
            "predecessor_manifests": [
                {"story_id": story, "path": path.as_posix(), "sha256": digest}
                for story, path, digest in PREDECESSOR_MANIFESTS
            ],
        },
        "ST-0205 provenance",
    )
    _require_exact(
        loaded["security"],
        {
            "control_mappings": [
                {
                    "id": "SEC-APP-001",
                    "relationship": "EXACT_UNKNOWN_DOMAIN_FIELD_AND_SCENARIO_REJECTION",
                },
                {
                    "id": "SEC-DATA-003",
                    "relationship": "NO_SECRET_IN_FIXTURE_REPO_OR_LOG",
                },
                {
                    "id": "SEC-DATA-004",
                    "relationship": "HASH_AND_VERSION_EVERY_FIXTURE",
                },
                {
                    "id": "SEC-DATA-007",
                    "relationship": "MINIMAL_ALLOWLISTED_SYNTHETIC_FIELDS",
                },
                {
                    "id": "SEC-SDLC-006",
                    "relationship": "SECRET_CANARY_NEGATIVE_TESTS",
                },
            ]
        },
        "ST-0205 security controls",
    )
    _require_exact(
        loaded["verification"],
        {
            "local_command": (
                "uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0205"
            ),
            "generator_check": (
                "uv run --locked --no-sync python "
                "scripts/build_st0205_synthetic_data.py --check"
            ),
            "negative_cases": [
                "PREDECESSOR_HASH_MISMATCH",
                "SECRET_PII_REVIEW_BODY_CANARIES",
                "UNKNOWN_FIELD",
                "UNKNOWN_CLASSIFICATION",
                "NONDETERMINISM",
                "PRODUCTION_COPY",
                "MISSING_ORIGIN_OR_LICENSE",
            ],
            "local_result_can_promote_formal_suite": False,
        },
        "ST-0205 verification contract",
    )
    boundary = loaded["boundary"]
    if not isinstance(boundary, dict):
        raise RuntimeError("ST-0205 boundary must be a mapping")
    _require_exact(
        boundary,
        {
            "environment": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_031": "NOT_EXECUTED",
            "privacy_security_review": "NOT_EXECUTED",
            "database_or_object_storage_write": "FORBIDDEN",
            "provider_or_network_access": "FORBIDDEN",
            "production_or_staging_use": "FORBIDDEN",
            "retention_period_decision": "NOT_MADE",
            "status_apply": "FORBIDDEN",
            "effective_canonical_status": "UNCHANGED",
        },
        "ST-0205 boundary",
    )
    _require_exact(
        loaded["out_of_scope"],
        [
            "DATABASE_SCHEMA_OR_MIGRATION",
            "POSTGRESQL_OR_S3_SEED_WRITE",
            "LIVE_OR_RECORDED_PROVIDER_DATA",
            "PRODUCTION_OR_STAGING_DATA",
            "RETENTION_OR_AUTOMATIC_DELETION_POLICY",
            "STATUS_EVIDENCE_OR_CANONICAL_APPLY",
        ],
        "ST-0205 out-of-scope boundary",
    )
    return dict(loaded)


def _source_record(
    root: Path,
    relative: Path,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None = None,
) -> dict[str, object]:
    content, _metadata = _captured_repository_file(
        root,
        relative,
        "ST-0205 source artifact",
        captured_files,
        maximum_bytes=(
            shared.MAX_YAML_BYTES
            if relative == CONTRACT_PATH
            else MAXIMUM_REPOSITORY_ARTIFACT_BYTES
        ),
    )
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _generated_record(relative: Path, content: bytes) -> dict[str, object]:
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(
    bundle: bytes,
    catalog: bytes,
    root: Path = REPO_ROOT,
    *,
    validated_contract: Mapping[str, Any] | None = None,
    captured_files: Mapping[Path, CapturedRepositoryFile] | None = None,
) -> bytes:
    """Render the deterministic source and output integrity manifest."""

    contract = (
        load_and_validate_contract(root, captured_files=captured_files)
        if validated_contract is None
        else validated_contract
    )
    sources = [
        _source_record(root, path, captured_files) for path in SOURCE_ARTIFACT_PATHS
    ]
    manifest = {
        "document": {
            "id": "RAOS-SYNTHETIC-DATA-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0205",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "canonical_inputs": [
                {"uri": f"repo://{name}", "sha256": digest}
                for name, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "predecessor_manifests": [
                {
                    "story_id": story,
                    "uri": f"repo://{path.as_posix()}",
                    "sha256": digest,
                }
                for story, path, digest in PREDECESSOR_MANIFESTS
            ],
        },
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": 2,
        "generated_artifacts": [
            _generated_record(FIXTURE_BUNDLE_PATH, bundle),
            _generated_record(CATALOG_PATH, catalog),
        ],
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": dict(contract["boundary"]),
    }
    return yaml.dump(
        manifest,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    """Render all generated artifacts after verifying immutable inputs."""

    capture_paths = dict.fromkeys(
        [
            *(Path(name) for name in PINNED_CANONICAL_INPUTS),
            *(path for _story, path, _digest in PREDECESSOR_MANIFESTS),
            LICENSE_AUTHORITY_PATH,
            CONTRACT_PATH,
            *SOURCE_ARTIFACT_PATHS,
        ]
    )
    captured_files = {
        path: _read_repository_file(
            root,
            path,
            "ST-0205 repository input",
            maximum_bytes=(
                shared.MAX_YAML_BYTES
                if path == CONTRACT_PATH
                else MAXIMUM_REPOSITORY_ARTIFACT_BYTES
            ),
        )
        for path in capture_paths
    }
    contract = load_and_validate_contract(root, captured_files=captured_files)
    bundle = render_fixture_bundle()
    catalog = render_catalog(bundle)
    manifest = render_manifest(
        bundle,
        catalog,
        root,
        validated_contract=contract,
        captured_files=captured_files,
    )
    return {
        FIXTURE_BUNDLE_PATH: bundle,
        CATALOG_PATH: catalog,
        MANIFEST_PATH: manifest,
    }


def _write_artifact_atomic(root: Path, relative: Path, content: bytes) -> None:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError("unsafe ST-0205 generated path")
    root_metadata = root.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("generated-artifact root must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    temporary_name: str | None = None
    output_descriptor: int | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in relative.parent.parts:
            try:
                next_descriptor = os.open(part, directory_flags, dir_fd=current)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=current)
                next_descriptor = os.open(part, directory_flags, dir_fd=current)
            current = next_descriptor
            descriptors.append(current)
        parent_descriptor = descriptors[-1]
        try:
            metadata = os.stat(
                relative.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            metadata = None
        if metadata is not None and not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("generated target must be a regular non-symlink file")
        for suffix in range(100):
            candidate = f".{relative.name}.st0205-{os.getpid()}-{suffix}"
            try:
                output_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise RuntimeError("cannot allocate a safe ST-0205 staging file")
        view = memoryview(content)
        while view:
            written = os.write(output_descriptor, view)
            if written <= 0:
                raise RuntimeError("short write while staging ST-0205 artifact")
            view = view[written:]
        os.fsync(output_descriptor)
        os.close(output_descriptor)
        output_descriptor = None
        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if output_descriptor is not None:
            os.close(output_descriptor)
        if temporary_name is not None and descriptors:
            try:
                os.unlink(temporary_name, dir_fd=descriptors[-1])
            except FileNotFoundError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def generate_artifacts(root: Path = REPO_ROOT) -> None:
    outputs = render_outputs(root)
    for relative in GENERATED_PATHS:
        _write_artifact_atomic(root, relative, outputs[relative])


def check_generated(root: Path = REPO_ROOT) -> None:
    outputs = render_outputs(root)
    for relative in GENERATED_PATHS:
        content, metadata = _read_repository_file(root, relative, "ST-0205 output")
        if metadata.st_mode & 0o022:
            raise RuntimeError("ST-0205 output cannot be group/world writable")
        if content != outputs[relative]:
            raise RuntimeError(f"generated ST-0205 artifact drift: {relative}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the source contract and generated artifacts without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            generate_artifacts()
            mode = "generate"
    except (FixtureValidationError, OSError, RuntimeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "domains": len(DOMAIN_ORDER),
                "fixtures": len(FIXTURE_SCENARIOS),
                "generated_artifacts": len(GENERATED_PATHS),
                "mode": mode,
                "status": "PASS",
                "story_id": "ST-0205",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
