"""Execution boundary for selected strategies with injected external adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, runtime_checkable

from raos.strategy_switchboard.model import (
    ExecutionKind,
    GateContext,
    SelectionDecision,
    StrategyCandidate,
    StrategyProfile,
    StrategySelectionError,
    canonical_json_bytes,
    sha256_hex,
)
from raos.strategy_switchboard.switchboard import StrategySwitchboard


@runtime_checkable
class StrategyAdapter(Protocol):
    """Provider-neutral adapter injected by application wiring."""

    def execute(
        self,
        *,
        boundary_id: str,
        strategy_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class StrategyExecution:
    decision: SelectionDecision
    status: str
    payload_sha256: str
    result_sha256: str
    result_bytes: bytes
    side_effects: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.decision) is not SelectionDecision:
            raise ValueError("decision must be exact")
        if self.status not in {"planned", "accepted", "executed"}:
            raise ValueError("status is invalid")
        for digest in (self.payload_sha256, self.result_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("execution digests must be lowercase SHA-256")
        if type(self.result_bytes) is not bytes:
            raise ValueError("result_bytes must be bytes")
        if hashlib.sha256(self.result_bytes).hexdigest() != self.result_sha256:
            raise ValueError("result digest mismatch")
        try:
            parsed = json.loads(self.result_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("result_bytes must contain canonical JSON") from None
        if type(parsed) is not dict or canonical_json_bytes(parsed) != self.result_bytes:
            raise ValueError("result_bytes must be an exact canonical JSON object")
        if tuple(sorted(set(self.side_effects))) != self.side_effects:
            raise ValueError("side_effects must be sorted and unique")

    @property
    def result(self) -> dict[str, object]:
        value = json.loads(self.result_bytes.decode("utf-8"))
        if type(value) is not dict:
            raise RuntimeError("validated result changed shape")
        return value

    def to_record(self) -> dict[str, object]:
        return {
            "decision": self.decision.to_record(),
            "payload_sha256": self.payload_sha256,
            "result_sha256": self.result_sha256,
            "side_effects": list(self.side_effects),
            "status": self.status,
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(self.to_record())


class StrategyRuntime:
    """Select and execute one strategy without ambient configuration or secrets."""

    def __init__(
        self,
        *,
        switchboard: StrategySwitchboard,
        adapters: Mapping[str, StrategyAdapter] | None = None,
    ) -> None:
        if type(switchboard) is not StrategySwitchboard:
            raise TypeError("switchboard must be exact")
        normalized: dict[str, StrategyAdapter] = {}
        for key, adapter in (adapters or {}).items():
            if type(key) is not str or not key:
                raise TypeError("adapter keys must be non-empty strings")
            if not isinstance(adapter, StrategyAdapter):
                raise TypeError("adapter must implement StrategyAdapter")
            if key in normalized:
                raise ValueError("duplicate adapter key")
            normalized[key] = adapter
        self._switchboard = switchboard
        self._adapters = normalized

    def execute(
        self,
        *,
        boundary_id: str,
        profile: StrategyProfile,
        context: GateContext,
        payload: Mapping[str, object],
        override_strategy_id: str | None = None,
    ) -> StrategyExecution:
        normalized_payload, payload_bytes = self._normalize_object(
            payload,
            error_code="STRATEGY_PAYLOAD_INVALID",
        )
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        decision = self._switchboard.select(
            boundary_id=boundary_id,
            profile=profile,
            context=context,
            override_strategy_id=override_strategy_id,
        )
        candidate = self._switchboard.catalog.get(decision.selected_strategy_id)
        result, status = self._execute_candidate(
            candidate=candidate,
            payload=normalized_payload,
            payload_sha256=payload_sha256,
        )
        result_bytes = canonical_json_bytes(result)
        return StrategyExecution(
            decision=decision,
            status=status,
            payload_sha256=payload_sha256,
            result_sha256=hashlib.sha256(result_bytes).hexdigest(),
            result_bytes=result_bytes,
            side_effects=tuple(sorted(candidate.side_effects)),
        )

    def _execute_candidate(
        self,
        *,
        candidate: StrategyCandidate,
        payload: dict[str, object],
        payload_sha256: str,
    ) -> tuple[dict[str, object], str]:
        common: dict[str, object] = {
            "boundary_id": candidate.boundary_id,
            "execution_kind": candidate.execution_kind.value,
            "payload_sha256": payload_sha256,
            "strategy_id": candidate.strategy_id,
        }
        if candidate.execution_kind is ExecutionKind.DETERMINISTIC_PLAN:
            return {**common, "status": "planned"}, "planned"

        if candidate.execution_kind is ExecutionKind.MANUAL_INPUT:
            if not payload:
                raise StrategySelectionError(
                    "STRATEGY_MANUAL_INPUT_REQUIRED",
                    boundary_id=candidate.boundary_id,
                    strategy_id=candidate.strategy_id,
                )
            return {**common, "status": "accepted"}, "accepted"

        adapter_key = candidate.adapter_key
        if adapter_key is None:
            raise StrategySelectionError(
                "STRATEGY_ADAPTER_CONFIGURATION_INVALID",
                boundary_id=candidate.boundary_id,
                strategy_id=candidate.strategy_id,
            )
        adapter = self._adapters.get(adapter_key)
        if adapter is None:
            raise StrategySelectionError(
                "STRATEGY_ADAPTER_MISSING",
                boundary_id=candidate.boundary_id,
                strategy_id=candidate.strategy_id,
            )
        try:
            raw_result = adapter.execute(
                boundary_id=candidate.boundary_id,
                strategy_id=candidate.strategy_id,
                payload=payload,
            )
        except Exception:
            raise StrategySelectionError(
                "STRATEGY_ADAPTER_FAILED",
                boundary_id=candidate.boundary_id,
                strategy_id=candidate.strategy_id,
            ) from None
        result, _ = self._normalize_object(
            raw_result,
            error_code="STRATEGY_ADAPTER_RESULT_INVALID",
        )
        return {
            **common,
            "adapter_result": result,
            "status": "executed",
        }, "executed"

    @staticmethod
    def _normalize_object(
        value: Mapping[str, object],
        *,
        error_code: str,
    ) -> tuple[dict[str, object], bytes]:
        if not isinstance(value, Mapping):
            raise StrategySelectionError(error_code)
        try:
            encoded = canonical_json_bytes(dict(value))
            parsed = json.loads(encoded.decode("utf-8"))
        except Exception:
            raise StrategySelectionError(error_code) from None
        if type(parsed) is not dict:
            raise StrategySelectionError(error_code)
        return parsed, encoded
