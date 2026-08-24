"""Strict recorded/synthetic ST-0705 adapter; no live provider surface."""

from __future__ import annotations

from datetime import datetime
import json
from types import MappingProxyType
from typing import Mapping, NoReturn, SupportsIndex, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.output_validation import (
    AiOutputValidationInput,
    CoverageMode,
    JsonLocator,
    OrderLocator,
    PROFILE_REGISTRY_VERSION,
    ProviderMode,
    RecordedOutputEnvelope,
    ResourceBinding,
    ResourceKind,
    ResourceValidationStatus,
    ReferenceFormat,
    ResourceLocator,
    RuntimeCheckBinding,
    ScalarKind,
    ScalarLocator,
    SemanticReceiptBinding,
    SemanticReceiptKind,
    SemanticReceiptRequirement,
    SemanticReceiptStatus,
    TaskValidationProfile,
    TRUSTED_PROFILE_REGISTRY_SHA256,
    TRUSTED_PROFILE_SHA256_BY_TASK,
    ValidationManifest,
    canonical_validation_time,
    evaluate_ai_output,
)
from raos.domain.ai.provider import (
    CanonicalJsonObject,
    Sha256Digest,
    StructuredOutputSchema,
)


_MAX_FIXTURE_BYTES = 1_048_576
_MAX_SCHEMA_BYTES = 4 * 1024 * 1024
_MAX_STRING_LENGTH = 4096
_MAX_PROFILE_COLLECTION = 256
_MAX_RECORDED_CASES = 128


@final
class RecordedAiOutputValidationError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_RECORDED_AI_OUTPUT_VALIDATION")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded validation errors are not serializable")


def _fail() -> NoReturn:
    raise RecordedAiOutputValidationError() from None


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        _fail()
    return cast(dict[str, object], value)


def _string(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_STRING_LENGTH
    ):
        _fail()
    return value


def _sha(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value))
    except Exception:
        _fail()


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _strings(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > _MAX_PROFILE_COLLECTION:
        _fail()
    return tuple(_string(item) for item in cast(list[object], value))


def _items(value: object, *, maximum: int = _MAX_PROFILE_COLLECTION) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        _fail()
    return cast(list[object], value)


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


_PROFILE_KEYS = frozenset(
    {
        "task_id",
        "task_code",
        "lifecycle",
        "output_schema_path",
        "output_schema_id",
        "output_schema_sha256",
        "task_binding_sha256",
        "task_sha256",
        "prompt_sha256",
        "route_sha256",
        "max_output_tokens",
        "max_output_bytes",
        "allowed_input_fields",
        "denied_input_fields",
        "required_runtime_checks",
        "prompt_required_runtime_checks",
        "runtime_check_bindings",
        "alignment_required_inputs",
        "alignment_required_outputs",
        "alignment_prohibited_outputs",
        "required_semantic_receipts",
        "semantic_capability_limitations",
        "resource_locators",
        "scalar_locators",
        "order_locators",
        "claim_collection",
        "schema_version",
        "coverage_mode",
        "profile_sha256",
    }
)
_TRUST_ANCHOR_SENTINEL = object()


@final
class TrustedTaskValidationProfiles:
    """Content-addressed immutable lookup for exactly twelve owner profiles."""

    __slots__ = ("_profiles",)

    def __init__(
        self,
        *,
        profiles: Mapping[str, TaskValidationProfile],
        trust_anchor: object,
    ) -> None:
        if (
            trust_anchor is not _TRUST_ANCHOR_SENTINEL
            or type(profiles) is not dict
            or tuple(sorted(profiles))
            != tuple(f"AIT-{number:03d}" for number in range(1, 13))
            or any(
                type(item) is not TaskValidationProfile for item in profiles.values()
            )
        ):
            _fail()
        self._profiles = MappingProxyType(dict(profiles))

    def get(self, task_id: str) -> TaskValidationProfile | None:
        if type(task_id) is not str:
            return None
        return self._profiles.get(task_id)

    def values(self) -> tuple[TaskValidationProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))


def _load_profile(row_value: object) -> TaskValidationProfile:
    row = _mapping(row_value, _PROFILE_KEYS)
    resources: list[ResourceLocator] = []
    for raw in _items(row["resource_locators"]):
        item = _mapping(
            raw,
            frozenset(
                {
                    "locator_id",
                    "pointer",
                    "reference_format",
                    "resource_kind",
                    "membership_required",
                }
            ),
        )
        if type(item["membership_required"]) is not bool:
            _fail()
        resources.append(
            ResourceLocator(
                locator=JsonLocator(
                    _string(item["locator_id"]), _string(item["pointer"])
                ),
                reference_format=ReferenceFormat(_string(item["reference_format"])),
                resource_kind=ResourceKind(_string(item["resource_kind"])),
                membership_required=item["membership_required"],
            )
        )
    scalars: list[ScalarLocator] = []
    for raw in _items(row["scalar_locators"]):
        item = _mapping(raw, frozenset({"locator_id", "pointer", "scalar_kind"}))
        scalars.append(
            ScalarLocator(
                locator=JsonLocator(
                    _string(item["locator_id"]), _string(item["pointer"])
                ),
                scalar_kind=ScalarKind(_string(item["scalar_kind"])),
            )
        )
    orders: list[OrderLocator] = []
    for raw in _items(row["order_locators"]):
        item = _mapping(
            raw,
            frozenset(
                {
                    "locator_id",
                    "collection_pointer",
                    "identity_field",
                    "rank_field",
                }
            ),
        )
        locator_id = _string(item["locator_id"])
        orders.append(
            OrderLocator(
                locator_id=locator_id,
                collection=JsonLocator(
                    f"{locator_id}.collection",
                    _string(item["collection_pointer"]),
                ),
                identity_field=_string(item["identity_field"]),
                rank_field=_string(item["rank_field"]),
            )
        )
    requirements: list[SemanticReceiptRequirement] = []
    for raw in _items(row["required_semantic_receipts"]):
        item = _mapping(
            raw,
            frozenset({"receipt_kind", "owner_story_id", "owner_contract_sha256"}),
        )
        requirements.append(
            SemanticReceiptRequirement(
                receipt_kind=SemanticReceiptKind(_string(item["receipt_kind"])),
                owner_story_id=_string(item["owner_story_id"]),
                owner_contract_sha256=_sha(item["owner_contract_sha256"]),
            )
        )
    check_bindings: list[RuntimeCheckBinding] = []
    for raw in _items(row["runtime_check_bindings"]):
        item = _mapping(raw, frozenset({"check_name", "enforcement_refs"}))
        check_bindings.append(
            RuntimeCheckBinding(
                check_name=_string(item["check_name"]),
                enforcement_refs=_strings(item["enforcement_refs"]),
            )
        )
    claim_collection = None
    max_claim_count = 0
    if row["claim_collection"] is not None:
        claim = _mapping(
            row["claim_collection"],
            frozenset({"locator_id", "pointer", "max_claim_count"}),
        )
        claim_collection = JsonLocator(
            _string(claim["locator_id"]), _string(claim["pointer"])
        )
        max_claim_count = _integer(claim["max_claim_count"])
    versions: list[JsonLocator] = []
    version_value: str | None = None
    if row["schema_version"] is not None:
        version = _mapping(row["schema_version"], frozenset({"locators", "value"}))
        version_value = _string(version["value"])
        for raw in _items(version["locators"]):
            item = _mapping(raw, frozenset({"locator_id", "pointer"}))
            versions.append(
                JsonLocator(_string(item["locator_id"]), _string(item["pointer"]))
            )
    try:
        profile = TaskValidationProfile(
            task_id=_string(row["task_id"]),
            task_code=_string(row["task_code"]),
            lifecycle=_string(row["lifecycle"]),
            output_schema_path=_string(row["output_schema_path"]),
            output_schema_id=_string(row["output_schema_id"]),
            output_schema_sha256=_sha(row["output_schema_sha256"]),
            task_binding_sha256=_sha(row["task_binding_sha256"]),
            task_sha256=_sha(row["task_sha256"]),
            prompt_sha256=_sha(row["prompt_sha256"]),
            route_sha256=_sha(row["route_sha256"]),
            max_output_tokens=_integer(row["max_output_tokens"]),
            max_output_bytes=_integer(row["max_output_bytes"]),
            allowed_input_fields=_strings(row["allowed_input_fields"]),
            denied_input_fields=_strings(row["denied_input_fields"]),
            required_runtime_checks=_strings(row["required_runtime_checks"]),
            prompt_required_runtime_checks=_strings(
                row["prompt_required_runtime_checks"]
            ),
            runtime_check_bindings=tuple(check_bindings),
            alignment_required_inputs=_strings(row["alignment_required_inputs"]),
            alignment_required_outputs=_strings(row["alignment_required_outputs"]),
            alignment_prohibited_outputs=_strings(row["alignment_prohibited_outputs"]),
            required_semantic_receipts=tuple(requirements),
            semantic_capability_limitations=_strings(
                row["semantic_capability_limitations"]
            ),
            resource_locators=tuple(resources),
            scalar_locators=tuple(scalars),
            order_locators=tuple(orders),
            claim_collection=claim_collection,
            max_claim_count=max_claim_count,
            schema_version_locators=tuple(versions),
            schema_version_value=version_value,
            coverage_mode=CoverageMode(_string(row["coverage_mode"])),
        )
    except Exception:
        _fail()
    if profile.profile_sha256 != _sha(row["profile_sha256"]):
        _fail()
    return profile


def load_trusted_ai_output_validation_profiles(
    registry_bytes: bytes,
) -> TrustedTaskValidationProfiles:
    if (
        type(registry_bytes) is not bytes
        or not registry_bytes
        or len(registry_bytes) > _MAX_FIXTURE_BYTES
        or Sha256Digest.of(registry_bytes) != TRUSTED_PROFILE_REGISTRY_SHA256
    ):
        _fail()
    try:
        document = json.loads(
            registry_bytes,
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: _fail(),
        )
    except RecordedAiOutputValidationError:
        raise
    except Exception:
        _fail()
    root = _mapping(
        document,
        frozenset(
            {
                "document",
                "source_bindings",
                "canonical_input_names",
                "alignment_source_required_inputs",
                "profiles",
            }
        ),
    )
    header = _mapping(
        root["document"],
        frozenset(
            {
                "id",
                "version",
                "story_id",
                "profile_registry_version",
                "status",
                "authority",
                "production_eligible",
            }
        ),
    )
    if (
        header
        != {
            "id": "RAOS-AI-OUTPUT-VALIDATION-PROFILES-001",
            "version": "1.0.0",
            "story_id": "ST-0705",
            "profile_registry_version": PROFILE_REGISTRY_VERSION,
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "authority": "NONE",
            "production_eligible": False,
        }
        or type(root["profiles"]) is not list
        or len(cast(list[object], root["profiles"])) != 12
    ):
        _fail()
    profiles: dict[str, TaskValidationProfile] = {}
    for raw in _items(root["profiles"], maximum=12):
        profile = _load_profile(raw)
        if profile.task_id in profiles:
            _fail()
        profiles[profile.task_id] = profile
    if {key: value.profile_sha256 for key, value in profiles.items()} != dict(
        TRUSTED_PROFILE_SHA256_BY_TASK
    ):
        _fail()
    return TrustedTaskValidationProfiles(
        profiles=profiles, trust_anchor=_TRUST_ANCHOR_SENTINEL
    )


def load_recorded_ai_output_validation_fixture(
    *,
    fixture_bytes: bytes,
    profiles: TrustedTaskValidationProfiles,
    schema_bytes: bytes,
) -> AiOutputValidationInput:
    """Reconstruct the one generator-owned pass case from immutable bytes."""

    if (
        type(fixture_bytes) is not bytes
        or not fixture_bytes
        or len(fixture_bytes) > _MAX_FIXTURE_BYTES
        or type(profiles) is not TrustedTaskValidationProfiles
        or type(schema_bytes) is not bytes
        or not schema_bytes
        or len(schema_bytes) > _MAX_SCHEMA_BYTES
    ):
        _fail()
    try:
        document = json.loads(
            fixture_bytes,
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: _fail(),
        )
    except RecordedAiOutputValidationError:
        raise
    except Exception:
        _fail()
    root = _mapping(document, frozenset({"document", "case", "expected_report"}))
    header = _mapping(
        root["document"],
        frozenset(
            {
                "id",
                "version",
                "story_id",
                "fixture_kind",
                "live_provider",
                "publication_authorized",
                "production_eligible",
            }
        ),
    )
    if header != {
        "id": "RAOS-AI-OUTPUT-VALIDATION-PASS-001",
        "version": "1.0.0",
        "story_id": "ST-0705",
        "fixture_kind": "RECORDED_SYNTHETIC",
        "live_provider": False,
        "publication_authorized": False,
        "production_eligible": False,
    }:
        _fail()
    case = _mapping(
        root["case"],
        frozenset(
            {
                "task_id",
                "task_code",
                "evaluated_at",
                "output",
                "request_sha256",
                "provider_exchange_sha256",
                "output_sha256",
                "input_context_sha256",
                "fact_id",
                "fact_value_sha256",
                "semantic_receipts",
                "manifest_sha256",
            }
        ),
    )
    profile = profiles.get(_string(case["task_id"]))
    if (
        profile is None
        or _string(case["task_code"]) != profile.task_code
        or type(case["output"]) is not dict
        or type(case["semantic_receipts"]) is not list
        or len(cast(list[object], case["semantic_receipts"])) > _MAX_PROFILE_COLLECTION
    ):
        _fail()
    try:
        evaluated_at = datetime.fromisoformat(_string(case["evaluated_at"]))
        output_bytes = CanonicalJsonObject(
            cast(Mapping[str, object], case["output"])
        ).canonical_bytes()
        request_sha = _sha(case["request_sha256"])
        exchange_sha = _sha(case["provider_exchange_sha256"])
        expected_output_sha = _sha(case["output_sha256"])
        context_sha = _sha(case["input_context_sha256"])
        envelope = RecordedOutputEnvelope(
            task_code=profile.task_code,
            provider_mode=ProviderMode.RECORDED_SYNTHETIC_ONLY,
            request_sha256=request_sha,
            provider_exchange_sha256=exchange_sha,
            raw_artifact_sha256=exchange_sha,
            output_bytes=output_bytes,
            raw_output_sha256=Sha256Digest.of(output_bytes),
        )
    except RecordedAiOutputValidationError:
        raise
    except Exception:
        _fail()
    if envelope.output_sha256 != expected_output_sha:
        _fail()
    requirements = {
        item.receipt_kind: item for item in profile.required_semantic_receipts
    }
    receipts: list[SemanticReceiptBinding] = []
    for raw in _items(case["semantic_receipts"]):
        row = _mapping(
            raw,
            frozenset(
                {
                    "receipt_kind",
                    "owner_story_id",
                    "owner_contract_sha256",
                    "evidence_sha256",
                }
            ),
        )
        try:
            kind = SemanticReceiptKind(_string(row["receipt_kind"]))
        except Exception:
            _fail()
        requirement = requirements.get(kind)
        if (
            requirement is None
            or _string(row["owner_story_id"]) != requirement.owner_story_id
            or _sha(row["owner_contract_sha256"]) != requirement.owner_contract_sha256
        ):
            _fail()
        receipts.append(
            SemanticReceiptBinding(
                receipt_kind=kind,
                owner_story_id=requirement.owner_story_id,
                owner_contract_sha256=requirement.owner_contract_sha256,
                request_sha256=request_sha,
                raw_output_sha256=envelope.raw_output_sha256,
                output_sha256=envelope.output_sha256,
                input_context_sha256=context_sha,
                evidence_sha256=_sha(row["evidence_sha256"]),
                status=SemanticReceiptStatus.PASS,
            )
        )
    fact_id = _string(case["fact_id"])
    manifest = ValidationManifest(
        manifest_version="ST0705_VALIDATION_MANIFEST_V1",
        profile_registry_version=PROFILE_REGISTRY_VERSION,
        profile_registry_sha256=TRUSTED_PROFILE_REGISTRY_SHA256,
        task_id=profile.task_id,
        task_code=profile.task_code,
        profile_sha256=profile.profile_sha256,
        task_binding_sha256=profile.task_binding_sha256,
        task_sha256=profile.task_sha256,
        prompt_sha256=profile.prompt_sha256,
        route_sha256=profile.route_sha256,
        output_schema_id=profile.output_schema_id,
        output_schema_sha256=profile.output_schema_sha256,
        expected_request_sha256=request_sha,
        expected_raw_output_sha256=envelope.raw_output_sha256,
        expected_output_sha256=envelope.output_sha256,
        expected_input_context_sha256=context_sha,
        input_field_names=("approved_source_packet",),
        resources=(
            ResourceBinding(
                resource_id=fact_id,
                resource_kind=ResourceKind.FACT,
                validation_status=ResourceValidationStatus.VALID,
                value_sha256=_sha(case["fact_value_sha256"]),
                expected_subject_identity_sha256=None,
                observed_subject_identity_sha256=None,
            ),
        ),
        scalar_expectations=(),
        order_expectations=(),
        semantic_receipts=tuple(receipts),
    )
    if manifest.manifest_sha256 != _sha(case["manifest_sha256"]):
        _fail()
    try:
        schema = StructuredOutputSchema(
            name="ai_opportunity_assessment_v1",
            uri=profile.output_schema_id,
            sha256=profile.output_schema_sha256,
            document_bytes=schema_bytes,
        )
        value = AiOutputValidationInput(
            profile=profile,
            schema=schema,
            manifest=manifest,
            envelope=envelope,
            evaluated_at=evaluated_at,
        )
        report = evaluate_ai_output(value)
        expected_report = CanonicalJsonObject(
            cast(Mapping[str, object], root["expected_report"])
        ).canonical_bytes()
    except Exception:
        _fail()
    if report.canonical_bytes() != expected_report:
        _fail()
    return value


def _input_anchor(value: object) -> Sha256Digest:
    if type(value) is not AiOutputValidationInput:
        _fail()
    try:
        evaluated_at = canonical_validation_time(value.evaluated_at)
        if (
            value.profile.profile_sha256
            != Sha256Digest.of(value.profile.canonical_bytes())
            or value.schema.sha256 != Sha256Digest.of(value.schema.document_bytes)
            or value.manifest.manifest_sha256
            != Sha256Digest.of(value.manifest.canonical_bytes())
            or value.envelope.raw_output_sha256
            != Sha256Digest.of(value.envelope.output_bytes)
        ):
            _fail()
        coverage = value.coverage
        coverage_document: object = None
        if coverage is not None:
            coverage.report.require_valid()
            coverage_document = {
                "binding_sha256": coverage.binding_sha256.value,
                "output_sha256": coverage.output_sha256.value,
                "report_sha256": coverage.report.report_sha256.value,
            }
        document = {
            "profile_sha256": value.profile.profile_sha256.value,
            "schema_name": value.schema.name,
            "schema_uri": value.schema.uri,
            "schema_sha256": value.schema.sha256.value,
            "manifest_sha256": value.manifest.manifest_sha256.value,
            "task_code": value.envelope.task_code,
            "request_sha256": value.envelope.request_sha256.value,
            "provider_exchange_sha256": value.envelope.provider_exchange_sha256.value,
            "raw_artifact_sha256": value.envelope.raw_artifact_sha256.value,
            "raw_output_sha256": value.envelope.raw_output_sha256.value,
            "output_sha256": (
                None
                if value.envelope.output_sha256 is None
                else value.envelope.output_sha256.value
            ),
            "evaluated_at": evaluated_at.isoformat(),
            "coverage": coverage_document,
        }
        return Sha256Digest.of(CanonicalJsonObject(document).canonical_bytes())
    except RecordedAiOutputValidationError:
        raise
    except Exception:
        _fail()


@final
class RecordedAiOutputValidationCaseReader:
    """Immutable in-memory reader for ENV-DEV/CI recorded cases."""

    __slots__ = ("_cases",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        cases: tuple[tuple[str, AiOutputValidationInput], ...],
    ) -> None:
        if (
            not _local_environment(environment)
            or type(cases) is not tuple
            or len(cases) > _MAX_RECORDED_CASES
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0]
                or item[0] != item[0].strip()
                or len(item[0]) > 120
                or type(item[1]) is not AiOutputValidationInput
                for item in cases
            )
            or len({item[0] for item in cases}) != len(cases)
        ):
            _fail()
        self._cases = MappingProxyType(
            {case_id: (value, _input_anchor(value)) for case_id, value in cases}
        )

    def get_case(self, case_id: str) -> AiOutputValidationInput | None:
        if (
            type(case_id) is not str
            or not case_id
            or case_id != case_id.strip()
            or len(case_id) > 120
        ):
            return None
        entry = self._cases.get(case_id)
        if entry is None:
            return None
        value, anchor = entry
        try:
            if _input_anchor(value) != anchor:
                return None
        except Exception:
            return None
        return value


__all__ = [
    "RecordedAiOutputValidationCaseReader",
    "RecordedAiOutputValidationError",
    "TrustedTaskValidationProfiles",
    "load_recorded_ai_output_validation_fixture",
    "load_trusted_ai_output_validation_profiles",
]
