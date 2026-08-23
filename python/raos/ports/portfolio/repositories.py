"""Aggregate-specific inward Portfolio repository protocols for ST-0308."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.portfolio.aggregates import (
    ActionCandidate,
    Category,
    IntentCluster,
    Keyword,
    KeywordMetricObservation,
    OpportunityAssessment,
    Site,
)
from raos.domain.portfolio.ids import (
    ActionCandidateId,
    CategoryId,
    IntentClusterId,
    KeywordId,
    OpportunityAssessmentId,
    SiteId,
)
from raos.domain.shared.persistence import AggregateVersion, PersistedVersion


@runtime_checkable
class SiteRepository(Protocol):
    def get(self, site_id: SiteId) -> Site | None: ...
    def add(self, site: Site) -> PersistedVersion: ...
    def save(
        self, site: Site, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class CategoryRepository(Protocol):
    def get(self, category_id: CategoryId) -> Category | None: ...
    def add(self, category: Category) -> PersistedVersion: ...
    def save(
        self, category: Category, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class IntentClusterRepository(Protocol):
    def get(self, cluster_id: IntentClusterId) -> IntentCluster | None: ...
    def add(self, cluster: IntentCluster) -> PersistedVersion: ...
    def save(
        self, cluster: IntentCluster, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


@runtime_checkable
class KeywordRepository(Protocol):
    def get(self, keyword_id: KeywordId) -> Keyword | None: ...
    def add(self, keyword: Keyword) -> PersistedVersion: ...
    def save(
        self, keyword: Keyword, expected_version: AggregateVersion
    ) -> PersistedVersion: ...
    def append_metric_observations(
        self,
        keyword_id: KeywordId,
        observations: tuple[KeywordMetricObservation, ...],
        expected_version: AggregateVersion,
    ) -> PersistedVersion: ...


@runtime_checkable
class OpportunityAssessmentRepository(Protocol):
    def get(
        self, assessment_id: OpportunityAssessmentId
    ) -> OpportunityAssessment | None: ...
    def append(self, assessment: OpportunityAssessment) -> None: ...


@runtime_checkable
class ActionCandidateRepository(Protocol):
    def get(self, candidate_id: ActionCandidateId) -> ActionCandidate | None: ...
    def add(self, candidate: ActionCandidate) -> PersistedVersion: ...
    def save(
        self, candidate: ActionCandidate, expected_version: AggregateVersion
    ) -> PersistedVersion: ...


__all__ = [
    "ActionCandidateRepository",
    "CategoryRepository",
    "IntentClusterRepository",
    "KeywordRepository",
    "OpportunityAssessmentRepository",
    "SiteRepository",
]
