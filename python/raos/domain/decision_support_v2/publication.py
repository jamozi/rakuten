"""Local-only publication-package state machine and semantic seal."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import re
from typing import Mapping, cast

from raos.domain.decision_support_v2.models import FreshnessState, RiskClass


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_ROUTE = re.compile(r"/(?:[a-z0-9][a-z0-9-]*/)*\Z")
_BASE_BINDINGS = frozenset({"article", "claims", "sources", "render", "migration"})
_REAL_BINDINGS = _BASE_BINDINGS | frozenset(
    {"editorial", "products", "review", "render_model"}
)


def _require_instance(value: object, expected_type: type[object], message: str) -> None:
    """Keep runtime validation at typed dataclass construction boundaries."""

    if not isinstance(value, expected_type):
        raise ValueError(message)


def _all_instances(values: tuple[object, ...], expected_type: type[object]) -> bool:
    return all(isinstance(value, expected_type) for value in values)


def _string_object_mapping(value: object, message: str) -> dict[str, object]:
    """Validate an untyped contract mapping and give Pyright precise keys."""

    if not isinstance(value, Mapping):
        raise ValueError(message)
    raw = cast(Mapping[object, object], value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError(message)
        result[key] = item
    return result


class PublicationState(StrEnum):
    DRAFT = "DRAFT"
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    PACKAGE_SEALED = "PACKAGE_SEALED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    # Plan-language aliases. They do not introduce additional machine states.
    REVIEWED = "EVIDENCE_COMPLETE"
    APPROVED = "HUMAN_REVIEWED"
    SEALED = "PACKAGE_SEALED"


_TRANSITIONS: Mapping[PublicationState, frozenset[PublicationState]] = {
    PublicationState.DRAFT: frozenset({PublicationState.EVIDENCE_COMPLETE}),
    PublicationState.EVIDENCE_COMPLETE: frozenset(
        {PublicationState.HUMAN_REVIEWED, PublicationState.REVIEW_REQUIRED}
    ),
    PublicationState.HUMAN_REVIEWED: frozenset({PublicationState.PACKAGE_SEALED}),
}


def semantic_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewBinding:
    reviewer_id: str
    reviewed_at: datetime
    review_version: str
    synthetic: bool

    def __post_init__(self) -> None:
        if not self.reviewer_id or not self.review_version:
            raise ValueError("review binding fields cannot be blank")
        _require_instance(
            self.synthetic, bool, "review synthetic marker must be boolean"
        )
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("review time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ClaimEvidenceBinding:
    claim_id: str
    risk_class: RiskClass
    freshness: FreshnessState

    def __post_init__(self) -> None:
        _require_instance(
            self.risk_class, RiskClass, "invalid claim evidence classification"
        )
        _require_instance(
            self.freshness,
            FreshnessState,
            "invalid claim evidence classification",
        )
        if not self.claim_id.startswith("CLM-") or not _MACHINE_ID.fullmatch(
            self.claim_id
        ):
            raise ValueError("invalid claim evidence ID")


@dataclass(frozen=True, slots=True)
class PublicationPackage:
    package_id: str
    target_origin: str
    target_route: str
    article_id: str
    input_hashes: Mapping[str, str]
    render_hash: str
    source_snapshot_hash: str
    claim_evidence: tuple[ClaimEvidenceBinding, ...]
    review_binding: ReviewBinding | None
    migration_manifest: Mapping[str, object]
    created_at: datetime
    state: PublicationState
    package_digest: str | None = None
    synthetic: bool = False

    def __post_init__(self) -> None:
        _require_instance(
            self.state,
            PublicationState,
            "invalid publication state or content class",
        )
        _require_instance(
            self.synthetic, bool, "invalid publication state or content class"
        )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.target_origin != "https://kurashinoshirube.com":
            raise ValueError("unexpected target origin")
        if not _MACHINE_ID.fullmatch(self.package_id) or not _MACHINE_ID.fullmatch(
            self.article_id
        ):
            raise ValueError("package and article IDs must be machine identifiers")
        if not _ROUTE.fullmatch(self.target_route):
            raise ValueError("invalid target route")
        if not self.input_hashes or any(
            not _MACHINE_ID.fullmatch(name) or not _SHA256.fullmatch(value)
            for name, value in self.input_hashes.items()
        ):
            raise ValueError("invalid input hash binding")
        if not _SHA256.fullmatch(self.render_hash) or not _SHA256.fullmatch(
            self.source_snapshot_hash
        ):
            raise ValueError("invalid render or source snapshot hash")
        if self.input_hashes.get("render") != self.render_hash:
            raise ValueError("render hash conflicts with bound render input")
        if self.input_hashes.get("sources") != self.source_snapshot_hash:
            raise ValueError("source snapshot hash conflicts with bound source input")
        migration_hash = self.migration_manifest.get("sha256")
        if (
            not isinstance(migration_hash, str)
            or not _SHA256.fullmatch(migration_hash)
            or self.input_hashes.get("migration") != migration_hash
        ):
            raise ValueError("migration manifest hash conflicts with bound input")
        if self.package_digest is not None and not _SHA256.fullmatch(
            self.package_digest
        ):
            raise ValueError("invalid package digest")
        if not self.claim_evidence or not _all_instances(
            self.claim_evidence, ClaimEvidenceBinding
        ):
            raise ValueError("invalid claim evidence binding")
        if len({binding.claim_id for binding in self.claim_evidence}) != len(
            self.claim_evidence
        ):
            raise ValueError("claim evidence must be nonempty and unique")
        required_bindings = _BASE_BINDINGS if self.synthetic else _REAL_BINDINGS
        if self.state in {
            PublicationState.EVIDENCE_COMPLETE,
            PublicationState.HUMAN_REVIEWED,
            PublicationState.PACKAGE_SEALED,
            PublicationState.REVIEW_REQUIRED,
        } and not required_bindings.issubset(self.input_hashes):
            raise ValueError("advanced publication state needs evidence bindings")
        if not self.synthetic and self.state in {
            PublicationState.HUMAN_REVIEWED,
            PublicationState.PACKAGE_SEALED,
        }:
            raise ValueError("real Phase 2 content cannot advance past evidence")
        if (
            self.state
            in {
                PublicationState.HUMAN_REVIEWED,
                PublicationState.PACKAGE_SEALED,
            }
            and self.review_binding is None
        ):
            raise ValueError("advanced publication state needs review binding")
        if self.state is PublicationState.PACKAGE_SEALED:
            if (
                not self.synthetic
                or self.review_binding is None
                or not self.review_binding.synthetic
                or self.package_digest is None
            ):
                raise ValueError("sealed package must be a reviewed synthetic fixture")
            if self.package_digest != semantic_digest(self.semantic_payload()):
                raise ValueError("sealed package digest is invalid")
        elif self.package_digest is not None:
            raise ValueError("only a sealed package may carry a digest")

    def semantic_payload(self) -> Mapping[str, object]:
        return {
            "package_id": self.package_id,
            "target_origin": self.target_origin,
            "target_route": self.target_route,
            "article_id": self.article_id,
            "input_hashes": dict(self.input_hashes),
            "render_hash": self.render_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "claim_evidence": [
                {
                    "claim_id": binding.claim_id,
                    "risk_class": binding.risk_class.value,
                    "freshness": binding.freshness.value,
                }
                for binding in sorted(
                    self.claim_evidence, key=lambda item: item.claim_id
                )
            ],
            "review_binding": (
                {
                    "reviewer_id": self.review_binding.reviewer_id,
                    "reviewed_at": self.review_binding.reviewed_at.isoformat(),
                    "review_version": self.review_binding.review_version,
                    "synthetic": self.review_binding.synthetic,
                }
                if self.review_binding is not None
                else None
            ),
            "migration_manifest": dict(self.migration_manifest),
            "created_at": self.created_at.isoformat(),
            "synthetic": self.synthetic,
            "content_class": (
                "SYNTHETIC_FIXTURE" if self.synthetic else "REAL_CONTENT"
            ),
            "state": self.state.value,
        }

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema_version": "1.0.0",
            "package_id": self.package_id,
            "target_origin": self.target_origin,
            "target_route": self.target_route,
            "article_id": self.article_id,
            "input_hashes": dict(self.input_hashes),
            "render_hash": self.render_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "claim_evidence": [
                {
                    "claim_id": binding.claim_id,
                    "risk_class": binding.risk_class.value,
                    "freshness": binding.freshness.value,
                }
                for binding in sorted(
                    self.claim_evidence, key=lambda item: item.claim_id
                )
            ],
            "review_binding": (
                {
                    "reviewer_id": self.review_binding.reviewer_id,
                    "reviewed_at": self.review_binding.reviewed_at.isoformat(),
                    "review_version": self.review_binding.review_version,
                    "synthetic": self.review_binding.synthetic,
                }
                if self.review_binding is not None
                else None
            ),
            "migration_manifest": dict(self.migration_manifest),
            "created_at": self.created_at.isoformat(),
            "content_class": (
                "SYNTHETIC_FIXTURE" if self.synthetic else "REAL_CONTENT"
            ),
            "state": self.state.value,
            "package_digest": self.package_digest,
        }

    @classmethod
    def from_contract_record(cls, value: Mapping[str, object]) -> PublicationPackage:
        """Strictly round-trip the machine publication contract into the domain."""

        expected = {
            "schema_version",
            "package_id",
            "target_origin",
            "target_route",
            "article_id",
            "input_hashes",
            "render_hash",
            "source_snapshot_hash",
            "claim_evidence",
            "review_binding",
            "migration_manifest",
            "created_at",
            "content_class",
            "state",
            "package_digest",
        }
        if set(value) != expected or value.get("schema_version") != "1.0.0":
            raise ValueError("invalid publication contract fields")
        string_fields = (
            "package_id",
            "target_origin",
            "target_route",
            "article_id",
            "render_hash",
            "source_snapshot_hash",
            "created_at",
            "content_class",
            "state",
        )
        if any(not isinstance(value[field], str) for field in string_fields):
            raise ValueError("invalid publication contract field type")
        input_hash_values = _string_object_mapping(
            value["input_hashes"], "invalid publication contract payload"
        )
        input_hashes: dict[str, str] = {}
        for key, item in input_hash_values.items():
            if not isinstance(item, str):
                raise ValueError("invalid publication contract payload")
            input_hashes[key] = item
        migration_manifest = _string_object_mapping(
            value["migration_manifest"], "invalid publication contract payload"
        )
        claim_records_raw = value["claim_evidence"]
        review_record_raw = value["review_binding"]
        package_digest = value["package_digest"]
        if (
            not isinstance(claim_records_raw, list)
            or package_digest is not None
            and not isinstance(package_digest, str)
        ):
            raise ValueError("invalid publication contract payload")
        claim_records = cast(list[object], claim_records_raw)
        claims: list[ClaimEvidenceBinding] = []
        for record_raw in claim_records:
            record = _string_object_mapping(record_raw, "invalid claim evidence record")
            if set(record) != {
                "claim_id",
                "risk_class",
                "freshness",
            }:
                raise ValueError("invalid claim evidence record")
            claim_id = record["claim_id"]
            risk_class = record["risk_class"]
            freshness = record["freshness"]
            if (
                not isinstance(claim_id, str)
                or not isinstance(risk_class, str)
                or not isinstance(freshness, str)
            ):
                raise ValueError("invalid claim evidence type")
            claims.append(
                ClaimEvidenceBinding(
                    claim_id,
                    RiskClass(risk_class),
                    FreshnessState(freshness),
                )
            )
        review: ReviewBinding | None = None
        if review_record_raw is not None:
            review_record = _string_object_mapping(
                review_record_raw, "invalid review binding record"
            )
            if set(review_record) != {
                "reviewer_id",
                "reviewed_at",
                "review_version",
                "synthetic",
            }:
                raise ValueError("invalid review binding record")
            reviewer_id = review_record["reviewer_id"]
            reviewed_at = review_record["reviewed_at"]
            review_version = review_record["review_version"]
            review_synthetic = review_record["synthetic"]
            if (
                not isinstance(reviewer_id, str)
                or not isinstance(reviewed_at, str)
                or not isinstance(review_version, str)
                or not isinstance(review_synthetic, bool)
            ):
                raise ValueError("invalid review binding type")
            review = ReviewBinding(
                reviewer_id,
                _parse_contract_time(reviewed_at),
                review_version,
                review_synthetic,
            )
        content_class = str(value["content_class"])
        if content_class not in {"REAL_CONTENT", "SYNTHETIC_FIXTURE"}:
            raise ValueError("invalid publication content class")
        return cls(
            package_id=str(value["package_id"]),
            target_origin=str(value["target_origin"]),
            target_route=str(value["target_route"]),
            article_id=str(value["article_id"]),
            input_hashes=input_hashes,
            render_hash=str(value["render_hash"]),
            source_snapshot_hash=str(value["source_snapshot_hash"]),
            claim_evidence=tuple(claims),
            review_binding=review,
            migration_manifest=migration_manifest,
            created_at=_parse_contract_time(str(value["created_at"])),
            state=PublicationState(str(value["state"])),
            package_digest=(
                str(package_digest) if package_digest is not None else None
            ),
            synthetic=content_class == "SYNTHETIC_FIXTURE",
        )

    def transition(self, target: PublicationState) -> PublicationPackage:
        if target not in _TRANSITIONS.get(self.state, frozenset()):
            raise ValueError("forbidden publication transition")
        if target is PublicationState.EVIDENCE_COMPLETE and not (
            (_BASE_BINDINGS if self.synthetic else _REAL_BINDINGS).issubset(
                self.input_hashes
            )
        ):
            raise ValueError("evidence input binding incomplete")
        if (
            target
            in {
                PublicationState.HUMAN_REVIEWED,
                PublicationState.PACKAGE_SEALED,
            }
            and not self.review_binding
        ):
            raise ValueError("review binding required")
        if target is PublicationState.PACKAGE_SEALED:
            if not self.synthetic:
                raise ValueError("automated seal is restricted to synthetic fixtures")
            if self.review_binding is None or not self.review_binding.synthetic:
                raise ValueError("synthetic review binding required")
            if not _BASE_BINDINGS.issubset(self.input_hashes):
                raise ValueError("seal input binding incomplete")
            if any(
                binding.freshness not in {FreshnessState.FRESH, FreshnessState.DUE}
                for binding in self.claim_evidence
            ):
                raise ValueError("nonfresh claim blocks seal")
            payload = dict(self.semantic_payload())
            payload["state"] = target.value
            digest = semantic_digest(payload)
            return replace(self, state=target, package_digest=digest)
        return replace(self, state=target)

    def verify_seal(self) -> bool:
        return (
            self.package_digest is not None
            and self.package_digest == semantic_digest(self.semantic_payload())
        )


def real_content_candidate(
    *,
    package_id: str,
    target_route: str,
    article_id: str,
    input_hashes: Mapping[str, str],
    render_hash: str,
    source_snapshot_hash: str,
    claim_evidence: tuple[ClaimEvidenceBinding, ...],
    migration_manifest: Mapping[str, object],
    created_at: datetime,
) -> PublicationPackage:
    package = PublicationPackage(
        package_id=package_id,
        target_origin="https://kurashinoshirube.com",
        target_route=target_route,
        article_id=article_id,
        input_hashes=input_hashes,
        render_hash=render_hash,
        source_snapshot_hash=source_snapshot_hash,
        claim_evidence=claim_evidence,
        review_binding=None,
        migration_manifest=migration_manifest,
        created_at=created_at,
        state=PublicationState.DRAFT,
        synthetic=False,
    )
    return package.transition(PublicationState.EVIDENCE_COMPLETE)


def _parse_contract_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid publication contract time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publication contract time must be timezone-aware")
    return parsed


__all__ = [
    "ClaimEvidenceBinding",
    "PublicationPackage",
    "PublicationState",
    "ReviewBinding",
    "real_content_candidate",
    "semantic_digest",
]
