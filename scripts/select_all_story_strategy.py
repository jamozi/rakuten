#!/usr/bin/env python3
"""Select or execute one RAOS strategy from explicit JSON inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from scripts import build_all_story_strategy_catalog as generator  # noqa: E402

from raos.strategy_switchboard.catalog import build_complete_catalog  # noqa: E402
from raos.strategy_switchboard.config import (  # noqa: E402
    load_gate_context_json,
    load_profile_json,
)
from raos.strategy_switchboard.model import (  # noqa: E402
    StrategySelectionError,
    canonical_json_bytes,
)
from raos.strategy_switchboard.runtime import StrategyRuntime  # noqa: E402
from raos.strategy_switchboard.switchboard import StrategySwitchboard  # noqa: E402


_MAX_INPUT_BYTES = 4_194_304


def _read_regular(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID")
    try:
        size = path.stat().st_size
    except OSError:
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID") from None
    if size <= 0 or size > maximum_bytes:
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID")
    try:
        return path.read_bytes()
    except OSError:
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID") from None


def _payload(document: bytes) -> dict[str, object]:
    try:
        value = json.loads(document.decode("utf-8", errors="strict"))
        canonical = canonical_json_bytes(value)
        reparsed = json.loads(canonical.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, StrategySelectionError, ValueError):
        raise StrategySelectionError("STRATEGY_PAYLOAD_INVALID") from None
    if type(reparsed) is not dict:
        raise StrategySelectionError("STRATEGY_PAYLOAD_INVALID")
    return reparsed


def _write_json(stream: object, document: dict[str, object]) -> None:
    encoded = canonical_json_bytes(document) + b"\n"
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(encoded)
        buffer.flush()
        return
    write = getattr(stream, "write", None)
    if not callable(write):
        raise RuntimeError("output stream is unavailable")
    write(encoded.decode("utf-8"))


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--override")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(arguments)


def run(options: argparse.Namespace) -> dict[str, object]:
    root = options.root.resolve()
    profile_document = _read_regular(
        options.profile.resolve(),
        label="profile",
        maximum_bytes=65_536,
    )
    context_document = _read_regular(
        options.context.resolve(),
        label="context",
        maximum_bytes=65_536,
    )
    profile = load_profile_json(profile_document)
    context = load_gate_context_json(context_document)
    payload = (
        {}
        if options.payload is None
        else _payload(
            _read_regular(
                options.payload.resolve(),
                label="payload",
                maximum_bytes=_MAX_INPUT_BYTES,
            )
        )
    )

    catalog = build_complete_catalog(generator.canonical_story_ids(root))
    switchboard = StrategySwitchboard(catalog)
    if not options.execute:
        decision = switchboard.select(
            boundary_id=options.boundary,
            profile=profile,
            context=context,
            override_strategy_id=options.override,
        )
        return {
            "catalog_sha256": catalog.sha256,
            "decision": decision.to_record(),
            "mode": "selection",
            "status": "PASS",
        }

    execution = StrategyRuntime(switchboard=switchboard).execute(
        boundary_id=options.boundary,
        profile=profile,
        context=context,
        payload=payload,
        override_strategy_id=options.override,
    )
    return {
        "catalog_sha256": catalog.sha256,
        "execution": execution.to_record(),
        "mode": "execution",
        "status": "PASS",
    }


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        result = run(options)
    except StrategySelectionError as error:
        _write_json(
            sys.stderr,
            {
                "boundary_id": error.boundary_id,
                "error_code": error.code,
                "status": "REFUSED",
                "strategy_id": error.strategy_id,
            },
        )
        return 2
    except (OSError, RuntimeError, ValueError, TypeError):
        _write_json(
            sys.stderr,
            {
                "error_code": "STRATEGY_CLI_INTERNAL_FAILURE",
                "status": "REFUSED",
            },
        )
        return 3
    _write_json(sys.stdout, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
