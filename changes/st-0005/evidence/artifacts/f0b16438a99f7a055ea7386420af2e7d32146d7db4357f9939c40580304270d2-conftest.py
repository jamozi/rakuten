"""Shared fixtures for the ST-0006 decision-gate suite."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

import pytest

from scripts import build_st0006_decision_gates as gates


@pytest.fixture
def canonical_catalog() -> dict[str, Any]:
    return gates.load_decision_catalog()


def clone(value: Any) -> Any:
    return deepcopy(value)


def synthetic_catalog(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "document": {
            "id": gates.SOURCE_DOCUMENT_ID,
            "version": gates.SOURCE_VERSION,
            "status": gates.SOURCE_STATUS,
        },
        "rules": list(gates.EXPECTED_RULES),
        "items": [dict(item) for item in items],
        "source": {
            "yaml_uri": "test://open-decisions.yaml",
            "yaml_sha256": "0" * 64,
            "csv_mirror_uri": "test://open-decisions.csv",
            "csv_mirror_sha256": "1" * 64,
        },
    }


def write_yaml_source(path: Path, document: Mapping[str, Any]) -> None:
    gates.write_yaml(path, document)


def write_csv_source(path: Path, items: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=gates.CSV_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for value in items:
            row = dict(value)
            row["blocking"] = "True" if value["blocking"] else "False"
            writer.writerow(cast(Any, row))


__all__ = [
    "clone",
    "synthetic_catalog",
    "write_csv_source",
    "write_yaml_source",
]
