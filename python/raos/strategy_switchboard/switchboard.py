"""Deterministic profile and override selection with explicit fallback policy."""

from __future__ import annotations

from raos.strategy_switchboard.model import (
    FallbackPolicy,
    GateContext,
    SelectionDecision,
    StrategyCandidate,
    StrategyCatalog,
    StrategyProfile,
    StrategySelectionError,
)


class StrategySwitchboard:
    """Select one eligible candidate without reading ambient configuration."""

    def __init__(self, catalog: StrategyCatalog) -> None:
        if type(catalog) is not StrategyCatalog:
            raise TypeError("catalog must be an exact StrategyCatalog")
        self._catalog = catalog

    @property
    def catalog(self) -> StrategyCatalog:
        return self._catalog

    def select(
        self,
        *,
        boundary_id: str,
        profile: StrategyProfile,
        context: GateContext,
        override_strategy_id: str | None = None,
    ) -> SelectionDecision:
        if type(profile) is not StrategyProfile:
            raise TypeError("profile must be an exact StrategyProfile")
        if type(context) is not GateContext:
            raise TypeError("context must be an exact GateContext")
        if override_strategy_id is not None and type(override_strategy_id) is not str:
            raise TypeError("override_strategy_id must be str or None")

        candidates = self._catalog.for_boundary(boundary_id)
        by_tier = {candidate.tier: candidate for candidate in candidates}
        safe = next(candidate for candidate in candidates if candidate.safe_default)

        profile_override = profile.override_for(boundary_id)
        requested_id = override_strategy_id or profile_override
        if profile.fallback_policy is FallbackPolicy.SAFE_ONLY:
            requested = safe
        elif requested_id is not None:
            requested = self._catalog.get(requested_id)
            if requested.boundary_id != boundary_id:
                raise StrategySelectionError(
                    "STRATEGY_OVERRIDE_BOUNDARY_MISMATCH",
                    boundary_id=boundary_id,
                    strategy_id=requested.strategy_id,
                )
        else:
            try:
                requested = by_tier[profile.preferred_tier]
            except KeyError:
                raise StrategySelectionError(
                    "STRATEGY_TIER_UNAVAILABLE", boundary_id=boundary_id
                ) from None

        attempts = self._attempts(
            requested=requested,
            candidates=candidates,
            safe=safe,
            policy=profile.fallback_policy,
        )
        missing_records: list[str] = []
        attempted_ids: list[str] = []
        for candidate in attempts:
            attempted_ids.append(candidate.strategy_id)
            missing = candidate.requirements.missing(context)
            if not missing:
                return SelectionDecision(
                    boundary_id=boundary_id,
                    profile_id=profile.profile_id,
                    requested_strategy_id=requested.strategy_id,
                    selected_strategy_id=candidate.strategy_id,
                    fallback_chain=tuple(attempted_ids),
                    missing_requirements=tuple(missing_records),
                    context_sha256=context.sha256,
                    catalog_sha256=self._catalog.sha256,
                )
            missing_records.extend(
                f"strategy:{candidate.strategy_id}:{requirement}"
                for requirement in missing
            )

        raise StrategySelectionError(
            "STRATEGY_REQUIREMENTS_UNSATISFIED",
            boundary_id=boundary_id,
            strategy_id=requested.strategy_id,
        )

    @staticmethod
    def _attempts(
        *,
        requested: StrategyCandidate,
        candidates: tuple[StrategyCandidate, ...],
        safe: StrategyCandidate,
        policy: FallbackPolicy,
    ) -> tuple[StrategyCandidate, ...]:
        if policy is FallbackPolicy.SAFE_ONLY:
            return (safe,)
        if policy is FallbackPolicy.FAIL_CLOSED:
            return (requested,)

        ordered = [requested]
        lower = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.tier < requested.tier
                and candidate.strategy_id != requested.strategy_id
            ),
            key=lambda candidate: candidate.tier,
            reverse=True,
        )
        ordered.extend(lower)
        if safe.strategy_id not in {candidate.strategy_id for candidate in ordered}:
            ordered.append(safe)
        return tuple(ordered)
