"""Product-level persistence inventory checks independent of archived preflight."""

from __future__ import annotations

from .support import (
    EXPECTED_LOCK_VERSION_RELATIONS,
    EXPECTED_PHYSICAL_TABLE_RELATIONS,
    EXPECTED_STATE_CAS_RELATIONS,
    EXPECTED_TABLE_COUNT,
    _live_physical_relation_sets,
)


def test_live_catalog_matches_the_product_persistence_inventory() -> None:
    live_relations, live_lock_relations = _live_physical_relation_sets()
    assert live_relations == set(EXPECTED_PHYSICAL_TABLE_RELATIONS)
    assert live_lock_relations == set(EXPECTED_LOCK_VERSION_RELATIONS)
    assert len(live_relations) == EXPECTED_TABLE_COUNT


def test_state_cas_and_lock_version_relations_are_separate() -> None:
    live_relations, live_lock_relations = _live_physical_relation_sets()
    assert len(EXPECTED_STATE_CAS_RELATIONS) == 24
    assert EXPECTED_STATE_CAS_RELATIONS <= live_relations
    assert EXPECTED_STATE_CAS_RELATIONS.isdisjoint(live_lock_relations)
