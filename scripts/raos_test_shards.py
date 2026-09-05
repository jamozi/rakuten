"""Deterministic test-case sharding across isolated CI runners."""

from __future__ import annotations

import hashlib

import pytest


def belongs_to_shard(key: str, index: int, total: int) -> bool:
    if not 1 <= index <= total:
        raise ValueError("test shard index must be within 1..total")
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") % total == index - 1


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("raos-sharding")
    group.addoption("--raos-shard-index", type=int, default=1)
    group.addoption("--raos-shard-total", type=int, default=1)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    index = config.getoption("--raos-shard-index")
    total = config.getoption("--raos-shard-total")
    if not 1 <= index <= total:
        raise pytest.UsageError("test shard index must be within 1..total")
    if total == 1:
        return
    selected, deselected = [], []
    for item in items:
        target = selected if belongs_to_shard(item.nodeid, index, total) else deselected
        target.append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
