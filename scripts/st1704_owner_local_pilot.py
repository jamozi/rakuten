#!/usr/bin/env python3
"""Fixed-path owner CLI for the ST-1704 local pilot ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Final


SOURCE_ROOT: Final = Path(os.path.abspath(__file__)).parent.parent
OWNER_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
PYTHON_ROOT: Final = SOURCE_ROOT / "python"
if PYTHON_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, PYTHON_ROOT.as_posix())

from raos.adapters.owner_local_pilot_json import OwnerLocalPilotJsonStore  # noqa: E402
from raos.application.editorial.owner_local_pilot import (  # noqa: E402
    OwnerLocalPilotService,
)
from raos.domain.editorial.owner_local_pilot import PilotFailure  # noqa: E402


COMMANDS: Final = frozenset({"doctor", "init", "record", "report"})


def _render(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def run_command(command: str, repository_root: Path) -> dict[str, object]:
    if type(command) is not str or command not in COMMANDS:
        raise ValueError("OWNER_LOCAL_PILOT_COMMAND_INVALID")
    store = OwnerLocalPilotJsonStore(repository_root)
    service = OwnerLocalPilotService(store=store, observation_input=store)
    if command == "doctor":
        return service.doctor()
    if command == "init":
        return service.initialize()
    if command == "record":
        return service.record()
    return service.report()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv if argv is None else argv
    if (
        type(arguments) is not list
        or len(arguments) != 2
        or type(arguments[1]) is not str
        or arguments[1] not in COMMANDS
        or SOURCE_ROOT != OWNER_REPOSITORY_ROOT
    ):
        print(
            _render(
                {
                    "code": "OWNER_LOCAL_PILOT_COMMAND_INVALID",
                    "status": "REFUSED",
                }
            )
        )
        return 2
    try:
        result = run_command(arguments[1], OWNER_REPOSITORY_ROOT)
    except PilotFailure as error:
        print(_render({"code": error.code.value, "status": "REFUSED"}))
        return 2
    except Exception:
        print(
            _render(
                {
                    "code": "OWNER_LOCAL_PILOT_INTERNAL_FAILURE",
                    "status": "REFUSED",
                }
            )
        )
        return 2
    print(_render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
