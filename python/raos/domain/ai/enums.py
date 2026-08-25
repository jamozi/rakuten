"""Closed physical enums for the ST-0308 AI persistence slice."""

from enum import Enum


class AiAttemptStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUSED = "REFUSED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class AiAttemptValidationStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class AiJobStatus(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    QUARANTINED = "QUARANTINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AiTaskDefinitionRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AiTaskDefinitionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class EvaluationCaseExpectedDisposition(str, Enum):
    CALL_PROVIDER_AND_PASS = "CALL_PROVIDER_AND_PASS"
    CALL_PROVIDER_AND_FLAG = "CALL_PROVIDER_AND_FLAG"
    BLOCK_BEFORE_PROVIDER = "BLOCK_BEFORE_PROVIDER"
    EXPECTED_REFUSAL = "EXPECTED_REFUSAL"
    EXPECTED_TERMINAL_FAILURE = "EXPECTED_TERMINAL_FAILURE"


class EvaluationCaseResultDisposition(str, Enum):
    CALL_PROVIDER_AND_PASS = "CALL_PROVIDER_AND_PASS"
    CALL_PROVIDER_AND_FLAG = "CALL_PROVIDER_AND_FLAG"
    BLOCK_BEFORE_PROVIDER = "BLOCK_BEFORE_PROVIDER"
    EXPECTED_REFUSAL = "EXPECTED_REFUSAL"
    EXPECTED_TERMINAL_FAILURE = "EXPECTED_TERMINAL_FAILURE"


class EvaluationCaseResultStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    INVALID = "INVALID"


class EvaluationCaseRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluationCaseSplit(str, Enum):
    BOOTSTRAP = "BOOTSTRAP"
    DEV = "DEV"
    CALIBRATION = "CALIBRATION"
    HOLDOUT = "HOLDOUT"
    REGRESSION = "REGRESSION"
    ADVERSARIAL = "ADVERSARIAL"
    PRODUCTION_SAMPLE = "PRODUCTION_SAMPLE"


class EvaluationDatasetStatus(str, Enum):
    DRAFT = "DRAFT"
    CURATING = "CURATING"
    LOCKED = "LOCKED"
    ACTIVE = "ACTIVE"
    COMPROMISED = "COMPROMISED"
    RETIRED = "RETIRED"


class EvaluationResultMetricCode(str, Enum):
    SCHEMA_VALID_RATE = "schema_valid_rate"
    COMPLETE_RESPONSE_RATE = "complete_response_rate"
    EVIDENCE_REFERENCE_PRECISION = "evidence_reference_precision"
    CRITICAL_CLAIM_SUPPORT_RATE = "critical_claim_support_rate"
    UNSUPPORTED_CRITICAL_FACT_RATE = "unsupported_critical_fact_rate"
    NUMERIC_EXACTNESS = "numeric_exactness"
    PRODUCT_IDENTITY_ACCURACY = "product_identity_accuracy"
    FABRICATED_EXPERIENCE_RATE = "fabricated_experience_rate"
    RAKUTEN_REVIEW_BODY_LEAKAGE_RATE = "rakuten_review_body_leakage_rate"
    AFFILIATE_BIAS_VIOLATION_RATE = "affiliate_bias_violation_rate"
    PROMPT_INJECTION_FOLLOW_RATE = "prompt_injection_follow_rate"
    POLICY_BLOCKER_RECALL = "policy_blocker_recall"
    FALSE_CLEARANCE_RATE = "false_clearance_rate"
    CRITICAL_CLAIM_RECALL = "critical_claim_recall"
    CLAIM_PRECISION = "claim_precision"
    INTENT_ACCURACY = "intent_accuracy"
    CLUSTER_PURITY = "cluster_purity"
    EDITORIAL_BUSINESS_SEPARATION = "editorial_business_separation"
    FINDING_RESOLUTION_RATE = "finding_resolution_rate"
    NEW_UNSUPPORTED_CLAIM_RATE = "new_unsupported_claim_rate"
    PRIORITY_ORDER_PRESERVATION = "priority_order_preservation"
    BLOCKING_GAP_RECALL = "blocking_gap_recall"
    AFFECTED_CLAIM_RECALL = "affected_claim_recall"
    HUMAN_ACCEPTANCE_RATE = "human_acceptance_rate"
    UNCERTAINTY_CALIBRATION_ERROR = "uncertainty_calibration_error"
    AXIS_RELEVANCE = "axis_relevance"
    INTENT_COVERAGE = "intent_coverage"
    LINK_RELEVANCE = "link_relevance"
    HUMAN_EDIT_DISTANCE = "human_edit_distance"
    LATENCY_P95_MS = "latency_p95_ms"
    COST_JPY_P95 = "cost_jpy_p95"


class EvaluationResultThresholdOperator(str, Enum):
    GREATER_THAN_OR_EQUAL = ">="
    GREATER_THAN = ">"
    LESS_THAN_OR_EQUAL = "<="
    LESS_THAN = "<"
    EQUAL = "=="
    NOT_EQUAL = "!="


class EvaluationRunStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    GRADING = "GRADING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


class EvaluationSuiteRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluationSuiteStatus(str, Enum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class HumanEvaluationDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"
    INVALID = "INVALID"


class JudgeCalibrationStatus(str, Enum):
    DRAFT = "DRAFT"
    PASSED = "PASSED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    RETIRED = "RETIRED"


class ModelDefinitionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EVALUATION = "EVALUATION"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    BLOCKED = "BLOCKED"


class ModelRouteVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    EVALUATING = "EVALUATING"
    CERTIFIED = "CERTIFIED"
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ROLLED_BACK = "ROLLED_BACK"
    RETIRED = "RETIRED"


class OutputSchemaVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class PromptVersionPolicyTestStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    PASSED = "PASSED"
    FAILED = "FAILED"


class PromptVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    EVALUATING = "EVALUATING"
    CERTIFIED = "CERTIFIED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class ReleaseApprovalPhase(str, Enum):
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"


class ReleaseDecisionReleaseScope(str, Enum):
    CANARY = "CANARY"
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"


class ReleaseDecisionRollbackStrategy(str, Enum):
    PREVIOUS_RELEASE = "PREVIOUS_RELEASE"
    DISABLE_ROUTE = "DISABLE_ROUTE"


class ReleaseDecisionStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECTED = "REJECTED"
    APPROVED_CANARY = "APPROVED_CANARY"
    APPROVED_ACTIVE = "APPROVED_ACTIVE"
    REVOKED = "REVOKED"


__all__ = [
    "AiAttemptStatus",
    "AiAttemptValidationStatus",
    "AiJobStatus",
    "AiTaskDefinitionRiskLevel",
    "AiTaskDefinitionStatus",
    "EvaluationCaseExpectedDisposition",
    "EvaluationCaseResultDisposition",
    "EvaluationCaseResultStatus",
    "EvaluationCaseRiskLevel",
    "EvaluationCaseSplit",
    "EvaluationDatasetStatus",
    "EvaluationResultMetricCode",
    "EvaluationResultThresholdOperator",
    "EvaluationRunStatus",
    "EvaluationSuiteRiskLevel",
    "EvaluationSuiteStatus",
    "HumanEvaluationDecision",
    "JudgeCalibrationStatus",
    "ModelDefinitionStatus",
    "ModelRouteVersionStatus",
    "OutputSchemaVersionStatus",
    "PromptVersionPolicyTestStatus",
    "PromptVersionStatus",
    "ReleaseApprovalPhase",
    "ReleaseDecisionReleaseScope",
    "ReleaseDecisionRollbackStrategy",
    "ReleaseDecisionStatus",
]
