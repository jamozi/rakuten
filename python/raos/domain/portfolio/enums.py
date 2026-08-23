"""Closed physical enums for the ST-0308 PORTFOLIO persistence slice."""

from enum import Enum


class ActionCandidateActionType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    MERGE = "MERGE"
    DELETE = "DELETE"
    ARCHIVE = "ARCHIVE"
    PAUSE = "PAUSE"
    HOLD = "HOLD"
    INVESTIGATE = "INVESTIGATE"


class ActionCandidateTargetEntityType(str, Enum):
    CATEGORY = "CATEGORY"
    CLUSTER = "CLUSTER"
    KEYWORD = "KEYWORD"
    ARTICLE_PLAN = "ARTICLE_PLAN"
    ARTICLE = "ARTICLE"
    PRODUCT = "PRODUCT"
    OFFER = "OFFER"


class ActionCandidateStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class CategoryRiskClass(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    PROHIBITED = "PROHIBITED"


class CategoryStage(str, Enum):
    CANDIDATE = "CANDIDATE"
    RESEARCH = "RESEARCH"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class IntentClusterIntentType(str, Enum):
    SELECTION_GUIDE = "SELECTION_GUIDE"
    USE_CASE = "USE_CASE"
    COMPARISON = "COMPARISON"
    MODEL_DIFFERENCE = "MODEL_DIFFERENCE"
    CONDITION_FILTER = "CONDITION_FILTER"
    INFORMATIONAL_SUPPORT = "INFORMATIONAL_SUPPORT"


class IntentClusterStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class IntentClusterKeywordBindingKeywordRole(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    QUESTION = "QUESTION"
    EXCLUSION = "EXCLUSION"


class KeywordStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    BLOCKED = "BLOCKED"


class KeywordMetricObservationMetricType(str, Enum):
    SEARCH_VOLUME = "SEARCH_VOLUME"
    COMPETITION = "COMPETITION"
    RANK = "RANK"
    CPC = "CPC"
    TREND_INDEX = "TREND_INDEX"
    RESULT_COUNT_ESTIMATE = "RESULT_COUNT_ESTIMATE"


class KeywordMetricObservationDevice(str, Enum):
    ALL = "ALL"
    DESKTOP = "DESKTOP"
    MOBILE = "MOBILE"
    TABLET = "TABLET"


class OpportunityAssessmentAssessmentType(str, Enum):
    CATEGORY = "CATEGORY"
    CLUSTER = "CLUSTER"
    KEYWORD = "KEYWORD"
    ARTICLE_PLAN = "ARTICLE_PLAN"


class OpportunityAssessmentDecision(str, Enum):
    PURSUE = "PURSUE"
    RESEARCH = "RESEARCH"
    HOLD = "HOLD"
    REJECT = "REJECT"
    EXIT = "EXIT"


class SiteStatus(str, Enum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


__all__ = [
    "ActionCandidateActionType",
    "ActionCandidateTargetEntityType",
    "ActionCandidateStatus",
    "CategoryRiskClass",
    "CategoryStage",
    "IntentClusterIntentType",
    "IntentClusterStatus",
    "IntentClusterKeywordBindingKeywordRole",
    "KeywordStatus",
    "KeywordMetricObservationMetricType",
    "KeywordMetricObservationDevice",
    "OpportunityAssessmentAssessmentType",
    "OpportunityAssessmentDecision",
    "SiteStatus",
]
