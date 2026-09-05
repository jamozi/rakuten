"""Read-only selected official-source replay with separate contract/evidence roots.

No capture, network access, source edits, owner attestation or publication occurs.
Only selected articles' captures are opened. Raw bodies, URLs and fragments are
never returned; downstream authoring receives stable IDs and integrity bindings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
from typing import NoReturn, cast

from raos.adapters.self_hosted_editorial_pilot_json import (
    MAX_SOURCE_EVIDENCE_BYTES,
    read_exact_private_evidence_file,
    read_official_source_capture_evidence,
    source_evidence_relative_path,
)
from raos.adapters.self_hosted_editorial_source_capture import (
    LOCATOR_CONTRACT_RELATIVE_PATH,
    MAX_CONTRACT_BYTES,
    MAX_REGISTRY_BYTES,
    SOURCE_REGISTRY_RELATIVE_PATH,
    OfficialSourceCaptureFailure,
    SourceCaptureTarget,
    read_exact_tracked_source_file,
    decode_strict_source_json,
    load_source_capture_plan,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    canonical_json_bytes,
)

SCHEMA = "RAOS_VERIFIED_INCREMENTAL_OFFICIAL_SOURCES_V1"
RECEIPT_SCHEMA = "RAOS_VERIFIED_INCREMENTAL_OFFICIAL_SOURCE_RECEIPT_V1"
MAX_SOURCE_AGE = timedelta(hours=24)


class SelectedOfficialSourcesFailure(ValueError):
    """Codes contain no filesystem locations, URLs, source content or credentials."""


def _fail(code: str) -> NoReturn:
    raise SelectedOfficialSourcesFailure(f"RAOS_INCREMENTAL_SOURCES_{code}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SelectedSourceIssueV1:
    source_ref: str
    article_ids: tuple[str, ...]
    code: str

    def to_document(self) -> dict[str, object]:
        return {
            "source_ref": self.source_ref,
            "article_ids": list(self.article_ids),
            "code": self.code,
        }


@dataclass(frozen=True)
class SelectedOfficialSourceReceiptV1:
    source_ref: str
    retrieved_at: str
    expires_at: str
    evidence_file_sha256: str
    body_file_sha256: str
    response_sha256: str
    locator_binding_sha256: str
    contract_file_sha256: Mapping[str, str]
    claim_statement_sha256: Mapping[str, str]

    def to_document(self) -> dict[str, object]:
        return {
            "schema": RECEIPT_SCHEMA,
            "source_ref": self.source_ref,
            "retrieved_at": self.retrieved_at,
            "expires_at": self.expires_at,
            "evidence_file_sha256": self.evidence_file_sha256,
            "body_file_sha256": self.body_file_sha256,
            "response_sha256": self.response_sha256,
            "locator_binding_sha256": self.locator_binding_sha256,
            "contract_file_sha256": dict(self.contract_file_sha256),
            "claim_statement_sha256": dict(self.claim_statement_sha256),
            "provenance": "OFFICIAL_CAPTURE_REPLAY_VERIFIED",
            "publication_authority": False,
        }

    @property
    def receipt_sha256(self) -> str:
        return _sha(canonical_json_bytes(self.to_document()))


@dataclass(frozen=True)
class SelectedOfficialSourcesV1:
    article_ids: tuple[str, ...]
    article_claim_sources: Mapping[str, Mapping[str, tuple[str, ...]]]
    article_source_refs: Mapping[str, tuple[str, ...]]
    sources: Mapping[str, SelectedOfficialSourceReceiptV1]
    issues: tuple[SelectedSourceIssueV1, ...]
    contract_file_sha256: Mapping[str, str]
    evaluated_at: str

    @property
    def status(self) -> str:
        return "BLOCKED" if self.issues else "VERIFIED"

    @property
    def source_receipt_sha256(self) -> dict[str, str]:
        return {ref: source.receipt_sha256 for ref, source in self.sources.items()}

    @property
    def expires_at(self) -> str | None:
        if self.issues or not self.sources:
            return None
        return min(source.expires_at for source in self.sources.values())

    def require_complete(self) -> SelectedOfficialSourcesV1:
        if self.issues:
            _fail("SELECTED_SET_INCOMPLETE")
        return self

    def to_document(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "article_ids": list(self.article_ids),
            "article_claim_sources": {
                article: {claim: list(refs) for claim, refs in claims.items()}
                for article, claims in self.article_claim_sources.items()
            },
            "article_source_refs": {
                article: list(refs)
                for article, refs in self.article_source_refs.items()
            },
            "sources": {
                ref: {**source.to_document(), "receipt_sha256": source.receipt_sha256}
                for ref, source in self.sources.items()
            },
            "issues": [issue.to_document() for issue in self.issues],
            "contract_file_sha256": dict(self.contract_file_sha256),
            "evaluated_at": self.evaluated_at,
            "expires_at": self.expires_at,
            "publication_authority": False,
            "network_requests": 0,
            "external_writes": 0,
        }


def _contract_bytes(root: Path) -> dict[str, bytes]:
    return {
        "source_registry": read_exact_tracked_source_file(
            root, SOURCE_REGISTRY_RELATIVE_PATH, MAX_REGISTRY_BYTES
        ),
        "locator_contract": read_exact_tracked_source_file(
            root, LOCATOR_CONTRACT_RELATIVE_PATH, MAX_CONTRACT_BYTES
        ),
    }


def _replay(
    root: Path,
    target: SourceCaptureTarget,
    contract_hashes: Mapping[str, str],
    now: datetime,
) -> SelectedOfficialSourceReceiptV1:
    if target.locator_status != "READY":
        _fail("LOCATORS_PENDING")
    if target.media_type not in {"text/html", "application/pdf"}:
        # The existing trusted evidence domain cannot represent JavaScript.
        # Relabelling a JavaScript body as HTML would manufacture provenance.
        _fail("MEDIA_TYPE_UNSUPPORTED_BY_READER")
    evidence = read_official_source_capture_evidence(root, source_ref=target.source_ref)
    if evidence.final_url != target.url or evidence.content_type != target.media_type:
        _fail("TARGET_MISMATCH")
    expected = tuple(
        (
            locator.claim_id,
            locator.claim_statement_sha256,
            tuple(
                (fragment, _sha(fragment.encode("utf-8")))
                for fragment in locator.exact_utf8_fragments
            ),
        )
        for locator in target.locators
    )
    if evidence.locators != expected or (
        target.expected_body_sha256 is not None
        and evidence.body_sha256 != target.expected_body_sha256
    ):
        _fail("CURRENT_LOCATOR_MISMATCH")
    captured = datetime.fromisoformat(evidence.retrieved_at.replace("Z", "+00:00"))
    if captured.date() < target.observed_on:
        _fail("CAPTURE_BEFORE_OBSERVED_FLOOR")
    if not timedelta(0) <= now - captured < MAX_SOURCE_AGE:
        _fail("CAPTURE_EXPIRED_OR_FUTURE")
    raw = read_exact_private_evidence_file(
        root / source_evidence_relative_path(target.source_ref),
        maximum_bytes=MAX_SOURCE_EVIDENCE_BYTES,
        missing_code=EditorialPilotFailureCode.RESOURCE_NOT_READY,
    )
    parsed = decode_strict_source_json(raw, maximum=MAX_SOURCE_EVIDENCE_BYTES)
    if parsed != evidence.value():
        _fail("CAPTURE_CHANGED_DURING_READ")
    return SelectedOfficialSourceReceiptV1(
        target.source_ref,
        evidence.retrieved_at,
        _timestamp(captured + MAX_SOURCE_AGE),
        _sha(raw),
        evidence.body_sha256,
        evidence.response_sha256,
        _sha(canonical_json_bytes(expected)),
        dict(contract_hashes),
        {
            locator.claim_id: locator.claim_statement_sha256
            for locator in target.locators
        },
    )


def _issue_code(error: Exception) -> str:
    if isinstance(error, SelectedOfficialSourcesFailure):
        return str(error).removeprefix("RAOS_INCREMENTAL_SOURCES_")
    if isinstance(error, EditorialPilotFailure):
        if error.code is EditorialPilotFailureCode.RESOURCE_NOT_READY:
            return "CAPTURE_MISSING"
        if error.code is EditorialPilotFailureCode.JOURNAL_UNSAFE:
            return "CAPTURE_UNSAFE"
    return "CAPTURE_INVALID"


def validate_selected_official_sources(
    repository_root: Path,
    evidence_root: Path,
    article_ids: Sequence[str],
    now: datetime,
) -> SelectedOfficialSourcesV1:
    """Replay selected sources, never requiring another article's capture files.

    `evidence_root` is the explicit repository-style root containing `.secrets`,
    not the `.secrets` directory itself. Source contracts always come from
    `repository_root`; no network request, credential read or write is made.
    """
    if (
        not isinstance(cast(object, repository_root), Path)
        or not repository_root.is_absolute()
        or not isinstance(cast(object, evidence_root), Path)
        or not evidence_root.is_absolute()
        or not isinstance(cast(object, article_ids), Sequence)
        or isinstance(article_ids, (str, bytes))
        or not article_ids
        or any(type(article) is not str or not article for article in article_ids)
        or len(set(article_ids)) != len(article_ids)
        or type(now) is not datetime
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        _fail("ARGUMENT_INVALID")
    active_now = now.astimezone(UTC)
    selected = tuple(sorted(article_ids))
    try:
        before = _contract_bytes(repository_root)
        plan = load_source_capture_plan(repository_root)
        targets_by_article = {
            article: plan.for_article(article) for article in selected
        }
        if _contract_bytes(repository_root) != before:
            _fail("CONTRACT_CHANGED")
        registry = cast(
            dict[str, object],
            decode_strict_source_json(
                before["source_registry"], maximum=MAX_REGISTRY_BYTES
            ),
        )
        packets = {
            cast(str, packet["article_id"]): packet
            for packet in cast(list[dict[str, object]], registry["source_packets"])
        }
        article_claim_sources: dict[str, dict[str, tuple[str, ...]]] = {}
        article_source_refs: dict[str, tuple[str, ...]] = {}
        for article in selected:
            target_refs = {target.source_ref for target in targets_by_article[article]}
            article_source_refs[article] = tuple(sorted(target_refs))
            claims: dict[str, tuple[str, ...]] = {}
            for claim in cast(list[dict[str, object]], packets[article]["claims"]):
                claim_id = cast(str, claim["claim_id"])
                refs = tuple(sorted(cast(list[str], claim["evidence_refs"])))
                if not refs or not set(refs) <= target_refs or claim_id in claims:
                    _fail("CLAIM_SOURCE_BINDING_INVALID")
                claims[claim_id] = refs
            if not claims:
                _fail("ARTICLE_CLAIMS_EMPTY")
            article_claim_sources[article] = claims
        hashes = {key: _sha(raw) for key, raw in before.items()}
        targets = {
            target.source_ref: target
            for rows in targets_by_article.values()
            for target in rows
        }
        receipts: dict[str, SelectedOfficialSourceReceiptV1] = {}
        issues: dict[str, SelectedSourceIssueV1] = {}

        def issue(ref: str, code: str) -> None:
            issues[ref] = SelectedSourceIssueV1(
                ref,
                tuple(
                    article
                    for article in selected
                    if ref in article_source_refs[article]
                ),
                code,
            )

        for ref, target in sorted(targets.items()):
            try:
                receipts[ref] = _replay(evidence_root, target, hashes, active_now)
            except (
                EditorialPilotFailure,
                OfficialSourceCaptureFailure,
                SelectedOfficialSourcesFailure,
            ) as error:
                issue(ref, _issue_code(error))
        # Reopen every accepted pair after the set has been read. This detects
        # body/metadata replacement while another selected source was inspected.
        for ref in tuple(receipts):
            try:
                current = _replay(evidence_root, targets[ref], hashes, active_now)
                if current != receipts[ref]:
                    _fail("CAPTURE_CHANGED_DURING_READ")
            except (
                EditorialPilotFailure,
                OfficialSourceCaptureFailure,
                SelectedOfficialSourcesFailure,
            ) as error:
                del receipts[ref]
                issue(ref, _issue_code(error))
        if _contract_bytes(repository_root) != before:
            _fail("CONTRACT_CHANGED")
        return SelectedOfficialSourcesV1(
            selected,
            article_claim_sources,
            article_source_refs,
            receipts,
            tuple(issues[ref] for ref in sorted(issues)),
            hashes,
            _timestamp(active_now),
        )
    except OfficialSourceCaptureFailure, EditorialPilotFailure:
        _fail("CURRENT_CONTRACT_INVALID")
