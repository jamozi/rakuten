"""Maximum-safe recorded category-fixture boundary for ST-1702.

Only synthetic DEV/CI fixtures are accepted.  The unresolved category,
identity, and freshness decisions remain disabled and no result can authorize
provider access, persistence, publication, or Production use.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Literal, NoReturn, SupportsIndex, cast
from uuid import RFC_4122, UUID


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,15}\Z", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z", re.ASCII)
_REDACTED = "<redacted-category-fixture>"


class CategoryFixtureFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FIXTURE_INVALID = "FIXTURE_INVALID"
    FIXTURE_HASH_MISMATCH = "FIXTURE_HASH_MISMATCH"
    RESULT_MISMATCH = "RESULT_MISMATCH"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(slots=True, repr=False)
class CategoryFixtureFailure(RuntimeError):
    code: CategoryFixtureFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not CategoryFixtureFailureCode:
            raise TypeError("invalid category fixture failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"CategoryFixtureFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("category fixture failure serialization is not supported")


def fail_category_fixture(
    code: CategoryFixtureFailureCode = CategoryFixtureFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise CategoryFixtureFailure(code) from None


class CategoryActivation(str, Enum):
    DISABLED_UNRESOLVED_OD_001 = "DISABLED_UNRESOLVED_OD_001"


class IdentityActivation(str, Enum):
    DISABLED_UNRESOLVED_OD_006 = "DISABLED_UNRESOLVED_OD_006"


class FreshnessActivation(str, Enum):
    DISABLED_UNRESOLVED_OD_007 = "DISABLED_UNRESOLVED_OD_007"


class IdentityScenario(str, Enum):
    EXACT_SYNTHETIC_FIELDS = "EXACT_SYNTHETIC_FIELDS"
    VARIANT_DIFFERENCE = "VARIANT_DIFFERENCE"
    SET_COUNT_DIFFERENCE = "SET_COUNT_DIFFERENCE"


class ExpectedIdentityOutcome(str, Enum):
    HUMAN_REVIEW = "HUMAN_REVIEW"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("category fixture serialization is not supported")


def category_fixture_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_category_fixture()
    return value


def _text(
    value: object, *, maximum: int, pattern: re.Pattern[str] | None = None
) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(unicodedata.category(character) == "Cc" for character in value)
        or (pattern is not None and pattern.fullmatch(value) is None)
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return value


def _uuid7(value: object) -> UUID:
    if type(value) is not str:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    try:
        parsed = UUID(value)
    except ValueError:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    if (
        str(parsed) != value
        or parsed.int == 0
        or parsed.variant != RFC_4122
        or parsed.version != 7
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return parsed


def _object(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    mapping = cast(dict[object, object], value)
    if len(mapping) != len(keys) or not all(type(key) is str for key in mapping):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    if set(mapping) != set(keys):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return cast(dict[str, object], mapping)


def _array(value: object, *, minimum: int, maximum: int) -> list[object]:
    if type(value) is not list:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    items = cast(list[object], value)
    if not minimum <= len(items) <= maximum:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return items


def _enum(enum_type: type[Enum], value: object) -> Enum:
    if type(value) is not str:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    try:
        return enum_type(value)
    except ValueError:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class CategoryAttributeDefinition(_RedactedValue):
    key: str
    label: str
    required: Literal[True]
    identity_rule_applied: Literal[False]

    def __post_init__(self) -> None:
        _text(self.key, maximum=64, pattern=_KEY)
        _text(self.label, maximum=120)
        if self.required is not True or self.identity_rule_applied is not False:
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticGoldenProduct(_RedactedValue):
    product_id: UUID
    fixture_key: str
    display_name: str
    attributes: tuple[tuple[str, str], ...]
    source: Literal["SYNTHETIC_ONLY"]
    provider_evidence_present: Literal[False]
    publication_eligible: Literal[False]

    def __post_init__(self) -> None:
        if (
            type(self.product_id) is not UUID
            or self.product_id.version != 7
            or self.product_id.variant != RFC_4122
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        _text(self.fixture_key, maximum=96, pattern=_SLUG)
        _text(self.display_name, maximum=160)
        if (
            type(self.attributes) is not tuple
            or not self.attributes
            or self.source != "SYNTHETIC_ONLY"
            or self.provider_evidence_present is not False
            or self.publication_eligible is not False
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        keys: list[str] = []
        for pair in self.attributes:
            if type(pair) is not tuple or len(pair) != 2:
                fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
            key, value = pair
            keys.append(_text(key, maximum=64, pattern=_KEY))
            _text(value, maximum=120, pattern=_CODE)
        if len(set(keys)) != len(keys):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticIdentityCase(_RedactedValue):
    case_id: UUID
    left_product_id: UUID
    right_product_id: UUID
    scenario: IdentityScenario
    expected_outcome: ExpectedIdentityOutcome
    reason_code: Literal["OD006_EVIDENCE_REQUIRED"]

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID or value.version != 7 or value.variant != RFC_4122
            for value in (self.case_id, self.left_product_id, self.right_product_id)
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        if (
            self.left_product_id == self.right_product_id
            or type(self.scenario) is not IdentityScenario
            or type(self.expected_outcome) is not ExpectedIdentityOutcome
            or self.expected_outcome is not ExpectedIdentityOutcome.HUMAN_REVIEW
            or self.reason_code != "OD006_EVIDENCE_REQUIRED"
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class CategoryFixtureSourceBinding(_RedactedValue):
    name: str
    sha256: str

    def __post_init__(self) -> None:
        _text(self.name, maximum=64, pattern=_KEY)
        category_fixture_sha256(self.sha256)


@dataclass(frozen=True, slots=True, repr=False)
class CategoryFixtureBundle(_RedactedValue):
    fixture_id: UUID
    category_id: str
    display_name: str
    candidate_category_id: str
    category_activation: CategoryActivation
    attribute_schema: tuple[CategoryAttributeDefinition, ...]
    golden_products: tuple[SyntheticGoldenProduct, ...]
    identity_cases: tuple[SyntheticIdentityCase, ...]
    source_bindings: tuple[CategoryFixtureSourceBinding, ...]
    source_fixture_sha256: str
    record_fingerprint: str
    data_class: Literal["SYNTHETIC_VALIDATOR_FIXTURE_ONLY"]
    identity_activation: IdentityActivation
    freshness_activation: FreshnessActivation
    automatic_merge_enabled: Literal[False]
    automatic_split_enabled: Literal[False]
    human_review_required: Literal[True]
    domain_reviewer_approval: Literal["NOT_OBTAINED"]
    category_overrides: tuple[()]
    provider_overrides: tuple[()]
    stale_never_fresh: Literal[True]
    recommendation_auto_reorder: Literal["FORBIDDEN"]
    runtime_enabled: Literal[False]
    provider_access_enabled: Literal[False]
    network_enabled: Literal[False]
    persistence_enabled: Literal[False]
    external_actions_enabled: Literal[False]
    publication_authorized: Literal[False]
    activation_authorized: Literal[False]
    release_authorized: Literal[False]
    production_authorized: Literal[False]
    formal_tst_020: Literal["NOT_EXECUTED"]
    formal_acceptance_achieved: Literal[False]

    def __post_init__(self) -> None:
        if (
            type(self.fixture_id) is not UUID
            or self.fixture_id.version != 7
            or self.fixture_id.variant != RFC_4122
            or self.category_id != "synthetic_validator_category"
            or self.candidate_category_id != "suitcase_and_carry_bags"
            or type(self.category_activation) is not CategoryActivation
            or type(self.identity_activation) is not IdentityActivation
            or type(self.freshness_activation) is not FreshnessActivation
            or type(self.attribute_schema) is not tuple
            or type(self.golden_products) is not tuple
            or type(self.identity_cases) is not tuple
            or type(self.source_bindings) is not tuple
            or any(
                type(item) is not CategoryAttributeDefinition
                for item in self.attribute_schema
            )
            or any(
                type(item) is not SyntheticGoldenProduct
                for item in self.golden_products
            )
            or any(
                type(item) is not SyntheticIdentityCase for item in self.identity_cases
            )
            or any(
                type(item) is not CategoryFixtureSourceBinding
                for item in self.source_bindings
            )
            or self.data_class != "SYNTHETIC_VALIDATOR_FIXTURE_ONLY"
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        _text(self.display_name, maximum=160)
        category_fixture_sha256(self.source_fixture_sha256)
        category_fixture_sha256(self.record_fingerprint)
        false_values = (
            self.automatic_merge_enabled,
            self.automatic_split_enabled,
            self.runtime_enabled,
            self.provider_access_enabled,
            self.network_enabled,
            self.persistence_enabled,
            self.external_actions_enabled,
            self.publication_authorized,
            self.activation_authorized,
            self.release_authorized,
            self.production_authorized,
            self.formal_acceptance_achieved,
        )
        if (
            any(value is not False for value in false_values)
            or self.human_review_required is not True
            or self.domain_reviewer_approval != "NOT_OBTAINED"
            or self.category_overrides != ()
            or self.provider_overrides != ()
            or self.stale_never_fresh is not True
            or self.recommendation_auto_reorder != "FORBIDDEN"
            or self.formal_tst_020 != "NOT_EXECUTED"
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        attribute_keys = tuple(item.key for item in self.attribute_schema)
        product_ids = tuple(item.product_id for item in self.golden_products)
        if (
            len(attribute_keys) != 4
            or len(set(attribute_keys)) != len(attribute_keys)
            or len(product_ids) != 4
            or len(set(product_ids)) != len(product_ids)
            or len({item.fixture_key for item in self.golden_products}) != 4
            or len(self.identity_cases) != 3
            or len({item.case_id for item in self.identity_cases}) != 3
            or len(self.source_bindings) != 6
            or len({item.name for item in self.source_bindings}) != 6
            or tuple((item.name, item.sha256) for item in self.source_bindings)
            != _EXPECTED_BINDINGS
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        for product in self.golden_products:
            if tuple(key for key, _value in product.attributes) != attribute_keys:
                fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        known_products = set(product_ids)
        for case in self.identity_cases:
            if (
                case.left_product_id not in known_products
                or case.right_product_id not in known_products
            ):
                fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
        if self.record_fingerprint != _bundle_fingerprint(
            self
        ) or self.source_fixture_sha256 != _bundle_source_sha256(self):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class CategoryFixtureLoadRequest(_RedactedValue):
    fixture_id: UUID
    expected_source_fixture_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.fixture_id) is not UUID
            or self.fixture_id.version != 7
            or self.fixture_id.variant != RFC_4122
        ):
            fail_category_fixture()
        category_fixture_sha256(self.expected_source_fixture_sha256)

    @property
    def fingerprint(self) -> str:
        material = (
            f"ST-1702\n{self.fixture_id}\n{self.expected_source_fixture_sha256}\n"
        ).encode("ascii")
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class CategoryFixtureLoadResult(_RedactedValue):
    request_fingerprint: str
    bundle: CategoryFixtureBundle
    source_mode: Literal["RECORDED_SYNTHETIC_DEV_CI_ONLY"]
    persistence: Literal["NOT_EXECUTED"]
    external_actions: Literal["NOT_EXECUTED"]

    def __post_init__(self) -> None:
        category_fixture_sha256(self.request_fingerprint)
        if (
            type(self.bundle) is not CategoryFixtureBundle
            or self.source_mode != "RECORDED_SYNTHETIC_DEV_CI_ONLY"
            or self.persistence != "NOT_EXECUTED"
            or self.external_actions != "NOT_EXECUTED"
        ):
            fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)


_TOP_LEVEL_KEYS = (
    "schemaVersion",
    "storyId",
    "classification",
    "dataClass",
    "environment",
    "fixtureId",
    "localStatus",
    "canonicalStatus",
    "bindings",
    "category",
    "attributeSchema",
    "goldenProducts",
    "identityCases",
    "identityPolicy",
    "freshnessPolicy",
    "authority",
)
_BINDING_KEYS = (
    "v1_reference_plan",
    "st1701_decision_package",
    "st1701_approval",
    "st0504_reference_plan",
    "st1401_completion",
    "st1401_freshness_policy",
)
_EXPECTED_BINDINGS = (
    (
        "v1_reference_plan",
        "07f2ea06d3d28fafd7a895dfc4c6be0f66a8185a6e032a27c997e5709c3f73fc",
    ),
    (
        "st1701_decision_package",
        "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f",
    ),
    (
        "st1701_approval",
        "749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34",
    ),
    (
        "st0504_reference_plan",
        "f3ce4f99f5309fdc0349bd7b5a9d930ae18006d72aeb0fd480165b870d8e3f1b",
    ),
    (
        "st1401_completion",
        "37be7ef769384885aafb802f6c69bb15dc8d7cb0aeaf15dff013144526b6f866",
    ),
    (
        "st1401_freshness_policy",
        "a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2",
    ),
)
_ATTRIBUTE_KEYS = ("model_code", "size_code", "variant_code", "set_count")


def _canonical_fingerprint(record: dict[str, object]) -> str:
    try:
        payload = json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return hashlib.sha256(payload).hexdigest()


def _bundle_record(bundle: CategoryFixtureBundle) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "storyId": "ST-1702",
        "classification": "RECORDED_SYNTHETIC_CATEGORY_FIXTURE_V2",
        "dataClass": bundle.data_class,
        "environment": "CI",
        "fixtureId": str(bundle.fixture_id),
        "localStatus": "LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY",
        "canonicalStatus": {
            "implementation": "NOT_STARTED",
            "verification": "NOT_EXECUTED",
        },
        "bindings": {
            binding.name: binding.sha256 for binding in bundle.source_bindings
        },
        "category": {
            "categoryId": bundle.category_id,
            "displayName": bundle.display_name,
            "candidateCategoryId": bundle.candidate_category_id,
            "candidateApplied": False,
            "activation": bundle.category_activation.value,
        },
        "attributeSchema": [
            {
                "key": attribute.key,
                "label": attribute.label,
                "required": attribute.required,
                "identityRuleApplied": attribute.identity_rule_applied,
            }
            for attribute in bundle.attribute_schema
        ],
        "goldenProducts": [
            {
                "productId": str(product.product_id),
                "fixtureKey": product.fixture_key,
                "displayName": product.display_name,
                "attributes": dict(product.attributes),
                "source": product.source,
                "providerEvidencePresent": product.provider_evidence_present,
                "publicationEligible": product.publication_eligible,
            }
            for product in bundle.golden_products
        ],
        "identityCases": [
            {
                "caseId": str(identity_case.case_id),
                "leftProductId": str(identity_case.left_product_id),
                "rightProductId": str(identity_case.right_product_id),
                "scenario": identity_case.scenario.value,
                "expectedOutcome": identity_case.expected_outcome.value,
                "reasonCode": identity_case.reason_code,
            }
            for identity_case in bundle.identity_cases
        ],
        "identityPolicy": {
            "automaticMergeEnabled": bundle.automatic_merge_enabled,
            "automaticSplitEnabled": bundle.automatic_split_enabled,
            "humanReviewRequired": bundle.human_review_required,
            "domainReviewerApproval": bundle.domain_reviewer_approval,
            "activation": bundle.identity_activation.value,
        },
        "freshnessPolicy": {
            "policyId": "RAOS-CONTENT-FRESH-001",
            "policyVersion": "1.0.0",
            "authority": "PROVISIONAL_CANONICAL_SAFE_DEFAULT",
            "activation": bundle.freshness_activation.value,
            "categoryOverrides": list(bundle.category_overrides),
            "providerOverrides": list(bundle.provider_overrides),
            "staleNeverFresh": bundle.stale_never_fresh,
            "recommendationAutoReorder": bundle.recommendation_auto_reorder,
        },
        "authority": {
            "runtimeEnabled": bundle.runtime_enabled,
            "providerAccessEnabled": bundle.provider_access_enabled,
            "networkEnabled": bundle.network_enabled,
            "persistenceEnabled": bundle.persistence_enabled,
            "externalActionsEnabled": bundle.external_actions_enabled,
            "publicationAuthorized": bundle.publication_authorized,
            "activationAuthorized": bundle.activation_authorized,
            "releaseAuthorized": bundle.release_authorized,
            "productionAuthorized": bundle.production_authorized,
            "formalTst020": bundle.formal_tst_020,
        },
    }


def _bundle_fingerprint(bundle: CategoryFixtureBundle) -> str:
    return _canonical_fingerprint(_bundle_record(bundle))


def _bundle_source_sha256(bundle: CategoryFixtureBundle) -> str:
    try:
        payload = (
            json.dumps(
                _bundle_record(bundle),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    return hashlib.sha256(payload).hexdigest()


def build_category_fixture_bundle(
    record: object,
    *,
    source_fixture_sha256: object,
) -> CategoryFixtureBundle:
    """Validate one exact generated recorded fixture and return immutable values."""

    source_sha = category_fixture_sha256(source_fixture_sha256)
    top = _object(record, _TOP_LEVEL_KEYS)
    data_class = _text(top["dataClass"], maximum=80, pattern=_CODE)
    if (
        top["schemaVersion"] != 2
        or top["storyId"] != "ST-1702"
        or top["classification"] != "RECORDED_SYNTHETIC_CATEGORY_FIXTURE_V2"
        or data_class != "SYNTHETIC_VALIDATOR_FIXTURE_ONLY"
        or top["environment"] != "CI"
        or top["localStatus"] != "LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY"
        or top["canonicalStatus"]
        != {"implementation": "NOT_STARTED", "verification": "NOT_EXECUTED"}
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    fixture_id = _uuid7(top["fixtureId"])

    binding_map = _object(top["bindings"], _BINDING_KEYS)
    source_bindings = tuple(
        CategoryFixtureSourceBinding(name, category_fixture_sha256(binding_map[name]))
        for name in _BINDING_KEYS
    )
    if tuple((binding.name, binding.sha256) for binding in source_bindings) != (
        _EXPECTED_BINDINGS
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)

    category = _object(
        top["category"],
        (
            "categoryId",
            "displayName",
            "candidateCategoryId",
            "candidateApplied",
            "activation",
        ),
    )
    category_id = _text(category["categoryId"], maximum=64, pattern=_KEY)
    candidate_category_id = _text(
        category["candidateCategoryId"], maximum=64, pattern=_KEY
    )
    if (
        category_id != "synthetic_validator_category"
        or candidate_category_id != "suitcase_and_carry_bags"
        or category["candidateApplied"] is not False
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    display_name = _text(category["displayName"], maximum=160)
    category_activation = cast(
        CategoryActivation,
        _enum(CategoryActivation, category["activation"]),
    )

    attributes: list[CategoryAttributeDefinition] = []
    for value in _array(top["attributeSchema"], minimum=4, maximum=4):
        item = _object(value, ("key", "label", "required", "identityRuleApplied"))
        attributes.append(
            CategoryAttributeDefinition(
                key=_text(item["key"], maximum=64, pattern=_KEY),
                label=_text(item["label"], maximum=120),
                required=cast(Literal[True], item["required"]),
                identity_rule_applied=cast(Literal[False], item["identityRuleApplied"]),
            )
        )
    if tuple(item.key for item in attributes) != _ATTRIBUTE_KEYS:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)

    products: list[SyntheticGoldenProduct] = []
    for value in _array(top["goldenProducts"], minimum=4, maximum=4):
        item = _object(
            value,
            (
                "productId",
                "fixtureKey",
                "displayName",
                "attributes",
                "source",
                "providerEvidencePresent",
                "publicationEligible",
            ),
        )
        attribute_map = _object(item["attributes"], _ATTRIBUTE_KEYS)
        products.append(
            SyntheticGoldenProduct(
                product_id=_uuid7(item["productId"]),
                fixture_key=_text(item["fixtureKey"], maximum=96, pattern=_SLUG),
                display_name=_text(item["displayName"], maximum=160),
                attributes=tuple(
                    (key, _text(attribute_map[key], maximum=120, pattern=_CODE))
                    for key in _ATTRIBUTE_KEYS
                ),
                source=cast(Literal["SYNTHETIC_ONLY"], item["source"]),
                provider_evidence_present=cast(
                    Literal[False], item["providerEvidencePresent"]
                ),
                publication_eligible=cast(Literal[False], item["publicationEligible"]),
            )
        )

    cases: list[SyntheticIdentityCase] = []
    for value in _array(top["identityCases"], minimum=3, maximum=3):
        item = _object(
            value,
            (
                "caseId",
                "leftProductId",
                "rightProductId",
                "scenario",
                "expectedOutcome",
                "reasonCode",
            ),
        )
        cases.append(
            SyntheticIdentityCase(
                case_id=_uuid7(item["caseId"]),
                left_product_id=_uuid7(item["leftProductId"]),
                right_product_id=_uuid7(item["rightProductId"]),
                scenario=cast(
                    IdentityScenario, _enum(IdentityScenario, item["scenario"])
                ),
                expected_outcome=cast(
                    ExpectedIdentityOutcome,
                    _enum(ExpectedIdentityOutcome, item["expectedOutcome"]),
                ),
                reason_code=cast(
                    Literal["OD006_EVIDENCE_REQUIRED"], item["reasonCode"]
                ),
            )
        )

    identity = _object(
        top["identityPolicy"],
        (
            "automaticMergeEnabled",
            "automaticSplitEnabled",
            "humanReviewRequired",
            "domainReviewerApproval",
            "activation",
        ),
    )
    freshness = _object(
        top["freshnessPolicy"],
        (
            "policyId",
            "policyVersion",
            "authority",
            "activation",
            "categoryOverrides",
            "providerOverrides",
            "staleNeverFresh",
            "recommendationAutoReorder",
        ),
    )
    if (
        freshness["policyId"] != "RAOS-CONTENT-FRESH-001"
        or freshness["policyVersion"] != "1.0.0"
        or freshness["authority"] != "PROVISIONAL_CANONICAL_SAFE_DEFAULT"
        or freshness["categoryOverrides"] != []
        or freshness["providerOverrides"] != []
    ):
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    authority = _object(
        top["authority"],
        (
            "runtimeEnabled",
            "providerAccessEnabled",
            "networkEnabled",
            "persistenceEnabled",
            "externalActionsEnabled",
            "publicationAuthorized",
            "activationAuthorized",
            "releaseAuthorized",
            "productionAuthorized",
            "formalTst020",
        ),
    )

    bundle = CategoryFixtureBundle(
        fixture_id=fixture_id,
        category_id=category_id,
        display_name=display_name,
        candidate_category_id=candidate_category_id,
        category_activation=category_activation,
        attribute_schema=tuple(attributes),
        golden_products=tuple(products),
        identity_cases=tuple(cases),
        source_bindings=source_bindings,
        source_fixture_sha256=source_sha,
        record_fingerprint=_canonical_fingerprint(top),
        data_class="SYNTHETIC_VALIDATOR_FIXTURE_ONLY",
        identity_activation=cast(
            IdentityActivation,
            _enum(IdentityActivation, identity["activation"]),
        ),
        freshness_activation=cast(
            FreshnessActivation,
            _enum(FreshnessActivation, freshness["activation"]),
        ),
        automatic_merge_enabled=cast(Literal[False], identity["automaticMergeEnabled"]),
        automatic_split_enabled=cast(Literal[False], identity["automaticSplitEnabled"]),
        human_review_required=cast(Literal[True], identity["humanReviewRequired"]),
        domain_reviewer_approval=cast(
            Literal["NOT_OBTAINED"], identity["domainReviewerApproval"]
        ),
        category_overrides=cast(
            tuple[()], tuple(cast(list[object], freshness["categoryOverrides"]))
        ),
        provider_overrides=cast(
            tuple[()], tuple(cast(list[object], freshness["providerOverrides"]))
        ),
        stale_never_fresh=cast(Literal[True], freshness["staleNeverFresh"]),
        recommendation_auto_reorder=cast(
            Literal["FORBIDDEN"], freshness["recommendationAutoReorder"]
        ),
        runtime_enabled=cast(Literal[False], authority["runtimeEnabled"]),
        provider_access_enabled=cast(
            Literal[False], authority["providerAccessEnabled"]
        ),
        network_enabled=cast(Literal[False], authority["networkEnabled"]),
        persistence_enabled=cast(Literal[False], authority["persistenceEnabled"]),
        external_actions_enabled=cast(
            Literal[False], authority["externalActionsEnabled"]
        ),
        publication_authorized=cast(Literal[False], authority["publicationAuthorized"]),
        activation_authorized=cast(Literal[False], authority["activationAuthorized"]),
        release_authorized=cast(Literal[False], authority["releaseAuthorized"]),
        production_authorized=cast(Literal[False], authority["productionAuthorized"]),
        formal_tst_020=cast(Literal["NOT_EXECUTED"], authority["formalTst020"]),
        formal_acceptance_achieved=False,
    )
    _validate_case_semantics(bundle)
    return bundle


def _validate_case_semantics(bundle: CategoryFixtureBundle) -> None:
    products = {
        product.product_id: dict(product.attributes)
        for product in bundle.golden_products
    }
    expected_scenarios = (
        IdentityScenario.EXACT_SYNTHETIC_FIELDS,
        IdentityScenario.VARIANT_DIFFERENCE,
        IdentityScenario.SET_COUNT_DIFFERENCE,
    )
    if tuple(case.scenario for case in bundle.identity_cases) != expected_scenarios:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)
    for case in bundle.identity_cases:
        left = products[case.left_product_id]
        right = products[case.right_product_id]
        differences = {key for key in _ATTRIBUTE_KEYS if left[key] != right[key]}
        expected_differences: dict[IdentityScenario, set[str]] = {
            IdentityScenario.EXACT_SYNTHETIC_FIELDS: set(),
            IdentityScenario.VARIANT_DIFFERENCE: {"variant_code"},
            IdentityScenario.SET_COUNT_DIFFERENCE: {"set_count"},
        }
        expected = expected_differences[case.scenario]
        if differences != expected:
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


def validate_category_fixture_bundle(candidate: object) -> CategoryFixtureBundle:
    """Revalidate an exact bundle received across an inward port boundary."""

    if type(candidate) is not CategoryFixtureBundle:
        fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
    try:
        for attribute in candidate.attribute_schema:
            if type(attribute) is not CategoryAttributeDefinition:
                fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
            attribute.__post_init__()
        for product in candidate.golden_products:
            if type(product) is not SyntheticGoldenProduct:
                fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
            product.__post_init__()
        for identity_case in candidate.identity_cases:
            if type(identity_case) is not SyntheticIdentityCase:
                fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
            identity_case.__post_init__()
        for binding in candidate.source_bindings:
            if type(binding) is not CategoryFixtureSourceBinding:
                fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
            binding.__post_init__()
        candidate.__post_init__()
        _validate_case_semantics(candidate)
    except CategoryFixtureFailure:
        raise
    except Exception:
        fail_category_fixture(CategoryFixtureFailureCode.RESULT_MISMATCH)
    return candidate


__all__ = [
    "CategoryActivation",
    "CategoryAttributeDefinition",
    "CategoryFixtureBundle",
    "CategoryFixtureFailure",
    "CategoryFixtureFailureCode",
    "CategoryFixtureLoadRequest",
    "CategoryFixtureLoadResult",
    "CategoryFixtureSourceBinding",
    "ExpectedIdentityOutcome",
    "FreshnessActivation",
    "IdentityActivation",
    "IdentityScenario",
    "SyntheticGoldenProduct",
    "SyntheticIdentityCase",
    "build_category_fixture_bundle",
    "category_fixture_sha256",
    "fail_category_fixture",
    "validate_category_fixture_bundle",
]
