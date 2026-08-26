"""Repository-wide pytest configuration for the unified suite."""

from pathlib import Path
from functools import lru_cache
import sys

import pytest


sys.dont_write_bytecode = True


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "python"))

_DATABASE_FILE_TOKENS = (
    "database",
    "postgres",
    "sqlite",
)

_STORAGE_FILE_TOKENS = (
    "object_storage",
    "storage",
)

_SHARED_CHECKOUT_FILE_TOKENS = (
    "cli",
    "commands_and_docs",
    "determinism",
    "generated",
    "generation",
    "installer",
    "manifest",
    "toolchain",
    "wrapper",
)

_PROCESS_GLOBAL_SOURCE_TOKENS = (
    "monkeypatch.chdir(",
    "os.chdir(",
)


@lru_cache(maxsize=None)
def _uses_process_global_state(path: Path) -> bool:
    """Conservatively classify files that can mutate the shared checkout."""

    try:
        source = path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        return True
    return any(token in source for token in _PROCESS_GLOBAL_SOURCE_TOKENS)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep DB, storage, subprocess, and shared-checkout tests out of xdist."""

    for item in items:
        filename = item.path.name.lower()
        if any(token in filename for token in _DATABASE_FILE_TOKENS):
            item.add_marker(pytest.mark.database)
            item.add_marker(pytest.mark.serial)
        elif any(token in filename for token in _STORAGE_FILE_TOKENS):
            item.add_marker(pytest.mark.storage)
            item.add_marker(pytest.mark.serial)
        elif any(token in filename for token in _SHARED_CHECKOUT_FILE_TOKENS):
            item.add_marker(pytest.mark.serial)
        elif item.path.is_file() and _uses_process_global_state(item.path):
            item.add_marker(pytest.mark.serial)
