"""One-shot caller-bytes adapter for the ST-1904 synthetic recording."""

from __future__ import annotations

import json
from threading import RLock
from typing import Final, Literal, NoReturn, SupportsIndex, cast, final

from raos.domain.catalog.multi_category import (
    EXPECTED_BINDING_NAMES,
    EXPECTED_SYNTHETIC_CATEGORY_COUNT,
    MAX_MULTI_CATEGORY_SOURCE_BYTES,
    MULTI_CATEGORY_CONTRACT_VERSION,
    MULTI_CATEGORY_FIXTURE_PROFILE,
    MULTI_CATEGORY_PARSER_VERSION,
    FreshnessRuleState,
    IdentityDisposition,
    IdentityRuleState,
    MultiCategoryEvaluationCommand,
    MultiCategoryFailureCode,
    MultiCategoryScope,
    MultiCategorySourceBinding,
    RecordedMultiCategoryBundle,
    SyntheticCategoryProfile,
    TemplateCandidateState,
    binding_set_sha256,
    canonical_json_bytes,
    fail_multi_category,
    sha256_bytes,
)


_REDACTED: Final = "<redacted-recorded-multi-category-source>"
_ROOT_KEYS = frozenset({"authority", "bindings", "categories", "document"})
_DOCUMENT_KEYS = frozenset(
    {
        "contract_version",
        "fixture_profile",
        "parser_version",
        "recording_id",
        "schema",
        "scope",
        "synthetic",
    }
)
_BINDING_KEYS = frozenset({"name", "sha256"})
_CATEGORY_KEYS = frozenset(
    {
        "category_id",
        "display_name",
        "freshness",
        "human_review_required",
        "identity",
        "real_category_selected",
        "synthetic",
        "template",
    }
)
_IDENTITY_KEYS = frozenset(
    {
        "automatic_merge_enabled",
        "automatic_split_enabled",
        "disposition",
        "rule_state",
    }
)
_FRESHNESS_KEYS = frozenset(
    {
        "category_override",
        "policy_id",
        "policy_version",
        "provider_override",
        "recommendation_auto_reorder",
        "stale_never_fresh",
        "state",
    }
)
_TEMPLATE_KEYS = frozenset({"active", "sha256", "state", "template_id"})
_AUTHORITY_KEYS = frozenset(
    {
        "editorial_mutation_enabled",
        "freshness_overrides_applied",
        "identity_decisions_applied",
        "network_enabled",
        "persistence_enabled",
        "production_authorized",
        "provider_access_enabled",
        "publication_authorized",
        "recommendation_mutation_enabled",
        "release_authorized",
        "runtime_enabled",
        "templates_activated",
    }
)


class RecordedMultiCategorySourceError(ValueError):
    """Sanitized construction error that cannot retain source bytes."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID.value)

    def __repr__(self) -> str:
        return f"RecordedMultiCategorySourceError({_REDACTED})"

    def __str__(self) -> str:
        return MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded multi-category source errors cannot be serialized")


def _invalid() -> NoReturn:
    fail_multi_category(MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID)


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    candidate = cast(dict[object, object], value)
    if any(type(key) is not str for key in candidate) or frozenset(candidate) != keys:
        _invalid()
    return cast(dict[str, object], candidate)


def _array(value: object, *, length: int) -> list[object]:
    if type(value) is not list:
        _invalid()
    candidate = cast(list[object], value)
    if len(candidate) != length:
        _invalid()
    return candidate


def _string(value: object, *, maximum: int = 160) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        _invalid()
    return value


def _enum(
    enum_type: type[IdentityRuleState]
    | type[IdentityDisposition]
    | type[FreshnessRuleState]
    | type[TemplateCandidateState],
    value: object,
) -> (
    IdentityRuleState
    | IdentityDisposition
    | FreshnessRuleState
    | TemplateCandidateState
):
    if type(value) is not str:
        _invalid()
    try:
        return enum_type(value)
    except ValueError:
        _invalid()


def _parse_source(source: bytes) -> dict[str, object]:
    if not 1 <= len(source) <= MAX_MULTI_CATEGORY_SOURCE_BYTES:
        _invalid()
    try:
        parsed: object = json.loads(
            source.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except Exception:
        _invalid()
    if type(parsed) is not dict:
        _invalid()
    document = cast(dict[str, object], parsed)
    if canonical_json_bytes(document) + b"\n" != source:
        _invalid()
    return document


def _build_bundle(
    document: dict[str, object],
    command: MultiCategoryEvaluationCommand,
) -> RecordedMultiCategoryBundle:
    root = _mapping(document, _ROOT_KEYS)
    header = _mapping(root["document"], _DOCUMENT_KEYS)
    if header != {
        "contract_version": MULTI_CATEGORY_CONTRACT_VERSION,
        "fixture_profile": MULTI_CATEGORY_FIXTURE_PROFILE,
        "parser_version": MULTI_CATEGORY_PARSER_VERSION,
        "recording_id": command.recording_id,
        "schema": "ST1904_RECORDED_SYNTHETIC_MULTI_CATEGORY_V1",
        "scope": "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY",
        "synthetic": True,
    }:
        _invalid()

    bindings: list[MultiCategorySourceBinding] = []
    for raw in _array(root["bindings"], length=len(EXPECTED_BINDING_NAMES)):
        row = _mapping(raw, _BINDING_KEYS)
        bindings.append(
            MultiCategorySourceBinding(
                name=_string(row["name"], maximum=64),
                sha256=_string(row["sha256"], maximum=64),
            )
        )
    binding_tuple = tuple(bindings)
    if tuple(binding.name for binding in binding_tuple) != EXPECTED_BINDING_NAMES:
        _invalid()
    if binding_set_sha256(binding_tuple) != command.expected_binding_set_sha256:
        fail_multi_category(MultiCategoryFailureCode.BINDING_SET_MISMATCH)

    categories: list[SyntheticCategoryProfile] = []
    for raw in _array(root["categories"], length=EXPECTED_SYNTHETIC_CATEGORY_COUNT):
        row = _mapping(raw, _CATEGORY_KEYS)
        identity = _mapping(row["identity"], _IDENTITY_KEYS)
        freshness = _mapping(row["freshness"], _FRESHNESS_KEYS)
        template = _mapping(row["template"], _TEMPLATE_KEYS)
        categories.append(
            SyntheticCategoryProfile(
                category_id=_string(row["category_id"], maximum=64),
                display_name=_string(row["display_name"], maximum=120),
                synthetic=cast(Literal[True], row["synthetic"]),
                real_category_selected=cast(
                    Literal[False], row["real_category_selected"]
                ),
                identity_rule_state=cast(
                    IdentityRuleState,
                    _enum(IdentityRuleState, identity["rule_state"]),
                ),
                identity_disposition=cast(
                    IdentityDisposition,
                    _enum(IdentityDisposition, identity["disposition"]),
                ),
                automatic_merge_enabled=cast(
                    Literal[False], identity["automatic_merge_enabled"]
                ),
                automatic_split_enabled=cast(
                    Literal[False], identity["automatic_split_enabled"]
                ),
                freshness_rule_state=cast(
                    FreshnessRuleState,
                    _enum(FreshnessRuleState, freshness["state"]),
                ),
                freshness_policy_id=cast(
                    Literal["RAOS-CONTENT-FRESH-001"], freshness["policy_id"]
                ),
                freshness_policy_version=cast(
                    Literal["1.0.0"], freshness["policy_version"]
                ),
                category_override=cast(None, freshness["category_override"]),
                provider_override=cast(None, freshness["provider_override"]),
                stale_never_fresh=cast(Literal[True], freshness["stale_never_fresh"]),
                recommendation_auto_reorder=cast(
                    Literal["FORBIDDEN"],
                    freshness["recommendation_auto_reorder"],
                ),
                template_id=_string(template["template_id"], maximum=16),
                template_sha256=_string(template["sha256"], maximum=64),
                template_state=cast(
                    TemplateCandidateState,
                    _enum(TemplateCandidateState, template["state"]),
                ),
                template_active=cast(Literal[False], template["active"]),
                human_review_required=cast(Literal[True], row["human_review_required"]),
            )
        )
    authority = _mapping(root["authority"], _AUTHORITY_KEYS)
    if any(value is not False for value in authority.values()):
        _invalid()
    return RecordedMultiCategoryBundle(
        recording_id=command.recording_id,
        source_sha256=command.source_sha256,
        command_sha256=command.command_sha256,
        fixture_profile=MULTI_CATEGORY_FIXTURE_PROFILE,
        parser_version=MULTI_CATEGORY_PARSER_VERSION,
        bindings=binding_tuple,
        categories=tuple(categories),
        runtime_enabled=False,
        persistence_enabled=False,
        provider_access_enabled=False,
        network_enabled=False,
        identity_decisions_applied=False,
        freshness_overrides_applied=False,
        templates_activated=False,
        editorial_mutation_enabled=False,
        recommendation_mutation_enabled=False,
        publication_authorized=False,
        release_authorized=False,
        production_authorized=False,
    )


@final
class CallerBytesRecordedMultiCategorySource:
    """Consume exact canonical caller bytes once; never opens a path or network."""

    __slots__ = ("_consumed", "_lock", "_source", "_source_sha256")

    def __init__(self, source: bytes) -> None:
        if type(source) is not bytes:
            raise RecordedMultiCategorySourceError() from None
        stable = bytes(source)
        try:
            _parse_source(stable)
        except Exception:
            raise RecordedMultiCategorySourceError() from None
        self._source = stable
        self._source_sha256 = sha256_bytes(stable)
        self._consumed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return f"CallerBytesRecordedMultiCategorySource({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def read(
        self, command: MultiCategoryEvaluationCommand
    ) -> RecordedMultiCategoryBundle:
        if type(command) is not MultiCategoryEvaluationCommand:
            fail_multi_category()
        try:
            command.__post_init__()
        except Exception:
            fail_multi_category()
        if (
            command.scope
            is not MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
        ):
            fail_multi_category(MultiCategoryFailureCode.FEATURE_DISABLED)
        with self._lock:
            if self._consumed:
                fail_multi_category(MultiCategoryFailureCode.SOURCE_EXHAUSTED)
            self._consumed = True
            source = self._source
        if (
            command.source_sha256 != self._source_sha256
            or command.source_bytes != len(source)
            or sha256_bytes(source) != self._source_sha256
        ):
            fail_multi_category(MultiCategoryFailureCode.SOURCE_BYTES_MISMATCH)
        parsed = _parse_source(source)
        bundle = _build_bundle(parsed, command)
        bundle.require_valid()
        return bundle


__all__ = (
    "CallerBytesRecordedMultiCategorySource",
    "RecordedMultiCategorySourceError",
)
