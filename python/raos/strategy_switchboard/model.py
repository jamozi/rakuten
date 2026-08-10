"""Immutable strategy-selection contracts with deterministic evidence records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, IntEnum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")


class Environment(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class StrategyTier(IntEnum):
    SAFE = 0
    STANDARD = 1
    ADVANCED = 2


class FallbackPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    FALLBACK_CHAIN = "fallback_chain"
    SAFE_ONLY = "safe_only"


class ExecutionKind(str, Enum):
    DETERMINISTIC_PLAN = "deterministic_plan"
    MANUAL_INPUT = "manual_input"
    INJECTED_ADAPTER = "injected_adapter"


class StrategySelectionError(RuntimeError):
    """Stable, content-free selection or execution refusal."""

    def __init__(
        self,
        code: str,
        *,
        boundary_id: str | None = None,
        strategy_id: str | None = None,
    ) -> None:
        if _IDENTIFIER.fullmatch(code) is None:
            raise ValueError("error code must be a bounded identifier")
        self.code = code
        self.boundary_id = boundary_id
        self.strategy_id = strategy_id
        super().__init__(code)


def _identifier(value: str, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded identifier")
    return value


def _strings(values: Iterable[str], *, label: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        normalized.append(_identifier(value, label=label))
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} values must be unique")
    return tuple(sorted(normalized))


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic JSON bytes or fail closed."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise StrategySelectionError("STRATEGY_CANONICALIZATION_FAILED") from None
    if len(encoded) > 4_194_304:
        raise StrategySelectionError("STRATEGY_DOCUMENT_TOO_LARGE")
    return encoded


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class GateRequirements:
    approvals: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    allowed_environments: tuple[Environment, ...] = (Environment.LOCAL,)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "approvals", _strings(self.approvals, label="approval")
        )
        object.__setattr__(self, "evidence", _strings(self.evidence, label="evidence"))
        object.__setattr__(
            self, "capabilities", _strings(self.capabilities, label="capability")
        )
        environments = tuple(self.allowed_environments)
        if not environments or any(type(item) is not Environment for item in environments):
            raise ValueError("allowed_environments must contain exact Environment values")
        if len(set(environments)) != len(environments):
            raise ValueError("allowed_environments must be unique")
        object.__setattr__(
            self,
            "allowed_environments",
            tuple(sorted(environments, key=lambda item: item.value)),
        )

    def missing(self, context: GateContext) -> tuple[str, ...]:
        missing = [
            *(f"approval:{item}" for item in self.approvals if item not in context.approvals),
            *(f"evidence:{item}" for item in self.evidence if item not in context.evidence),
            *(
                f"capability:{item}"
                for item in self.capabilities
                if item not in context.capabilities
            ),
        ]
        if context.environment not in self.allowed_environments:
            missing.append(f"environment:{context.environment.value}")
        return tuple(missing)

    def to_record(self) -> dict[str, object]:
        return {
            "allowed_environments": [
                environment.value for environment in self.allowed_environments
            ],
            "approvals": list(self.approvals),
            "capabilities": list(self.capabilities),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class GateContext:
    environment: Environment
    approvals: frozenset[str] = frozenset()
    evidence: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if type(self.environment) is not Environment:
            raise ValueError("environment must be an exact Environment")
        object.__setattr__(
            self, "approvals", frozenset(_strings(self.approvals, label="approval"))
        )
        object.__setattr__(
            self, "evidence", frozenset(_strings(self.evidence, label="evidence"))
        )
        object.__setattr__(
            self,
            "capabilities",
            frozenset(_strings(self.capabilities, label="capability")),
        )

    @classmethod
    def local_empty(cls) -> GateContext:
        return cls(environment=Environment.LOCAL)

    def to_record(self) -> dict[str, object]:
        return {
            "approvals": sorted(self.approvals),
            "capabilities": sorted(self.capabilities),
            "environment": self.environment.value,
            "evidence": sorted(self.evidence),
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(self.to_record())


@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    strategy_id: str
    boundary_id: str
    tier: StrategyTier
    title: str
    description: str
    execution_kind: ExecutionKind
    requirements: GateRequirements
    safe_default: bool = False
    adapter_key: str | None = None
    side_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.strategy_id, label="strategy_id")
        _identifier(self.boundary_id, label="boundary_id")
        if type(self.tier) is not StrategyTier:
            raise ValueError("tier must be an exact StrategyTier")
        if type(self.title) is not str or not self.title.strip() or len(self.title) > 160:
            raise ValueError("title must be non-empty and bounded")
        if (
            type(self.description) is not str
            or not self.description.strip()
            or len(self.description) > 2_000
        ):
            raise ValueError("description must be non-empty and bounded")
        if type(self.execution_kind) is not ExecutionKind:
            raise ValueError("execution_kind must be exact")
        if type(self.requirements) is not GateRequirements:
            raise ValueError("requirements must be exact")
        if type(self.safe_default) is not bool:
            raise ValueError("safe_default must be bool")
        if self.execution_kind is ExecutionKind.INJECTED_ADAPTER:
            if self.adapter_key is None:
                raise ValueError("injected adapter strategies require adapter_key")
            _identifier(self.adapter_key, label="adapter_key")
        elif self.adapter_key is not None:
            raise ValueError("only injected adapter strategies may name adapter_key")
        object.__setattr__(
            self, "side_effects", _strings(self.side_effects, label="side_effect")
        )
        if self.safe_default:
            if self.tier is not StrategyTier.SAFE:
                raise ValueError("safe_default must use SAFE tier")
            if self.execution_kind is not ExecutionKind.DETERMINISTIC_PLAN:
                raise ValueError("safe_default must be deterministic")
            if self.requirements.missing(GateContext.local_empty()):
                raise ValueError("safe_default must be selectable in empty local context")
            if self.side_effects:
                raise ValueError("safe_default must have no side effects")

    def to_record(self) -> dict[str, object]:
        return {
            "adapter_key": self.adapter_key,
            "boundary_id": self.boundary_id,
            "description": self.description,
            "execution_kind": self.execution_kind.value,
            "requirements": self.requirements.to_record(),
            "safe_default": self.safe_default,
            "side_effects": list(self.side_effects),
            "strategy_id": self.strategy_id,
            "tier": self.tier.name.lower(),
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    profile_id: str
    preferred_tier: StrategyTier
    fallback_policy: FallbackPolicy
    overrides: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.profile_id, label="profile_id")
        if type(self.preferred_tier) is not StrategyTier:
            raise ValueError("preferred_tier must be exact")
        if type(self.fallback_policy) is not FallbackPolicy:
            raise ValueError("fallback_policy must be exact")
        normalized: list[tuple[str, str]] = []
        boundaries: set[str] = set()
        for item in self.overrides:
            if type(item) is not tuple or len(item) != 2:
                raise ValueError("override must be a boundary/strategy pair")
            boundary_id = _identifier(item[0], label="override boundary")
            strategy_id = _identifier(item[1], label="override strategy")
            if boundary_id in boundaries:
                raise ValueError("profile contains duplicate boundary override")
            boundaries.add(boundary_id)
            normalized.append((boundary_id, strategy_id))
        object.__setattr__(self, "overrides", tuple(sorted(normalized)))

    @classmethod
    def from_mapping(
        cls,
        *,
        profile_id: str,
        preferred_tier: StrategyTier,
        fallback_policy: FallbackPolicy,
        overrides: Mapping[str, str] | None = None,
    ) -> StrategyProfile:
        return cls(
            profile_id=profile_id,
            preferred_tier=preferred_tier,
            fallback_policy=fallback_policy,
            overrides=tuple((overrides or {}).items()),
        )

    def override_for(self, boundary_id: str) -> str | None:
        for item_boundary, strategy_id in self.overrides:
            if item_boundary == boundary_id:
                return strategy_id
        return None

    def to_record(self) -> dict[str, object]:
        return {
            "fallback_policy": self.fallback_policy.value,
            "overrides": dict(self.overrides),
            "preferred_tier": self.preferred_tier.name.lower(),
            "profile_id": self.profile_id,
        }


@dataclass(frozen=True, slots=True)
class StrategyCatalog:
    version: str
    candidates: tuple[StrategyCandidate, ...]

    def __post_init__(self) -> None:
        _identifier(self.version, label="catalog version")
        if not self.candidates:
            raise ValueError("catalog must contain candidates")
        by_id: dict[str, StrategyCandidate] = {}
        by_boundary: dict[str, list[StrategyCandidate]] = defaultdict(list)
        for candidate in self.candidates:
            if type(candidate) is not StrategyCandidate:
                raise ValueError("catalog candidates must be exact")
            if candidate.strategy_id in by_id:
                raise ValueError("duplicate strategy_id")
            by_id[candidate.strategy_id] = candidate
            by_boundary[candidate.boundary_id].append(candidate)
        for boundary_id, items in by_boundary.items():
            defaults = [item for item in items if item.safe_default]
            if len(defaults) != 1:
                raise ValueError(f"{boundary_id} must have exactly one safe default")
            tiers = [item.tier for item in items]
            if len(set(tiers)) != len(tiers):
                raise ValueError(f"{boundary_id} has duplicate strategy tiers")
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(self.candidates, key=lambda item: item.strategy_id)),
        )

    @property
    def boundary_ids(self) -> tuple[str, ...]:
        return tuple(sorted({candidate.boundary_id for candidate in self.candidates}))

    def for_boundary(self, boundary_id: str) -> tuple[StrategyCandidate, ...]:
        _identifier(boundary_id, label="boundary_id")
        result = tuple(
            sorted(
                (
                    candidate
                    for candidate in self.candidates
                    if candidate.boundary_id == boundary_id
                ),
                key=lambda item: item.tier,
                reverse=True,
            )
        )
        if not result:
            raise StrategySelectionError(
                "STRATEGY_BOUNDARY_UNKNOWN", boundary_id=boundary_id
            )
        return result

    def get(self, strategy_id: str) -> StrategyCandidate:
        _identifier(strategy_id, label="strategy_id")
        for candidate in self.candidates:
            if candidate.strategy_id == strategy_id:
                return candidate
        raise StrategySelectionError("STRATEGY_UNKNOWN", strategy_id=strategy_id)

    def to_record(self) -> dict[str, object]:
        return {
            "boundary_count": len(self.boundary_ids),
            "candidates": [candidate.to_record() for candidate in self.candidates],
            "strategy_count": len(self.candidates),
            "version": self.version,
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(self.to_record())


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    boundary_id: str
    profile_id: str
    requested_strategy_id: str
    selected_strategy_id: str
    fallback_chain: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    context_sha256: str
    catalog_sha256: str

    def __post_init__(self) -> None:
        for label, value in (
            ("boundary_id", self.boundary_id),
            ("profile_id", self.profile_id),
            ("requested_strategy_id", self.requested_strategy_id),
            ("selected_strategy_id", self.selected_strategy_id),
        ):
            _identifier(value, label=label)
        normalized_chain: list[str] = []
        for value in self.fallback_chain:
            normalized_chain.append(_identifier(value, label="fallback strategy"))
        if len(set(normalized_chain)) != len(normalized_chain):
            raise ValueError("fallback_chain values must be unique")
        object.__setattr__(self, "fallback_chain", tuple(normalized_chain))
        object.__setattr__(
            self,
            "missing_requirements",
            tuple(sorted(set(self.missing_requirements))),
        )
        for digest in (self.context_sha256, self.catalog_sha256):
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("decision digests must be lowercase SHA-256")

    @property
    def used_fallback(self) -> bool:
        return self.requested_strategy_id != self.selected_strategy_id

    def to_record(self) -> dict[str, object]:
        return {
            "boundary_id": self.boundary_id,
            "catalog_sha256": self.catalog_sha256,
            "context_sha256": self.context_sha256,
            "fallback_chain": list(self.fallback_chain),
            "missing_requirements": list(self.missing_requirements),
            "profile_id": self.profile_id,
            "requested_strategy_id": self.requested_strategy_id,
            "selected_strategy_id": self.selected_strategy_id,
            "used_fallback": self.used_fallback,
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(self.to_record())
