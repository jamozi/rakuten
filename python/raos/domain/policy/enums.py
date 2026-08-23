"""Closed physical enums for the ST-0308 POLICY persistence slice."""

from enum import Enum


class BundleRuleBindingMode(str, Enum):
    ENFORCE = "ENFORCE"
    SHADOW = "SHADOW"
    DISABLED = "DISABLED"


class FindingEntityType(str, Enum):
    ARTICLE_VERSION = "ARTICLE_VERSION"
    BLOCK = "BLOCK"
    CLAIM = "CLAIM"
    PRODUCT = "PRODUCT"
    OFFER = "OFFER"
    LINK = "LINK"
    SOURCE_PACKET = "SOURCE_PACKET"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    FIXED = "FIXED"
    WAIVED = "WAIVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ACCEPTED_RISK = "ACCEPTED_RISK"


class GateDecisionGateCode(str, Enum):
    GATE_0 = "GATE-0"
    GATE_1 = "GATE-1"
    GATE_2 = "GATE-2"
    GATE_3 = "GATE-3"
    GATE_4 = "GATE-4"


class GateDecisionResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"


class GateDecisionScopeType(str, Enum):
    SITE = "SITE"
    CATEGORY = "CATEGORY"
    ARTICLE_TYPE = "ARTICLE_TYPE"
    RELEASE = "RELEASE"


class PolicyBundleStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class QualityCheckRunStatus(str, Enum):
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class QualityCheckRunTriggeredByActorType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"


class RuleVersionImplementationType(str, Enum):
    PYTHON = "PYTHON"
    SQL = "SQL"
    REGEX = "REGEX"
    JSON_SCHEMA = "JSON_SCHEMA"
    MANUAL = "MANUAL"


class RuleVersionRuleCategory(str, Enum):
    COMPLIANCE = "COMPLIANCE"
    FACTUAL = "FACTUAL"
    QUALITY = "QUALITY"
    FRESHNESS = "FRESHNESS"
    LINK = "LINK"
    SECURITY = "SECURITY"
    ACCESSIBILITY = "ACCESSIBILITY"
    SEO = "SEO"


class RuleVersionSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class WaiverScopeType(str, Enum):
    FINDING = "FINDING"
    ARTICLE_VERSION = "ARTICLE_VERSION"
    ARTICLE = "ARTICLE"
    CATEGORY = "CATEGORY"


class WaiverStatus(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


__all__ = [
    "BundleRuleBindingMode",
    "FindingEntityType",
    "FindingSeverity",
    "FindingStatus",
    "GateDecisionGateCode",
    "GateDecisionResult",
    "GateDecisionScopeType",
    "PolicyBundleStatus",
    "QualityCheckRunStatus",
    "QualityCheckRunTriggeredByActorType",
    "RuleVersionImplementationType",
    "RuleVersionRuleCategory",
    "RuleVersionSeverity",
    "RuleVersionStatus",
    "WaiverScopeType",
    "WaiverStatus",
]
