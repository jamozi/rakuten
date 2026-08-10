"""Explicit, environment-independent CLI application for strategy switching."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import TextIO, cast

from raos.strategy_switchboard.catalog import build_complete_catalog
from raos.strategy_switchboard.config import (
    load_gate_context_json,
    load_profile_json,
)
from raos.strategy_switchboard.model import (
    StrategySelectionError,
    canonical_json_bytes,
)
from raos.strategy_switchboard.runtime import StrategyRuntime
from raos.strategy_switchboard.switchboard import StrategySwitchboard


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = Path(
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
)
_MAX_INPUT_BYTES = 4_194_304
_STORY_PATTERN = re.compile(r"\bST-[0-9]{4}\b")


@dataclass(frozen=True, slots=True)
class CliOptions:
    root: Path
    boundary: str
    profile: Path
    context: Path
    payload: Path | None
    override: str | None
    execute: bool


def _read_regular(path: Path, *, maximum_bytes: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID")
    try:
        size = path.stat().st_size
        if size <= 0 or size > maximum_bytes:
            raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID")
        return path.read_bytes()
    except StrategySelectionError:
        raise
    except OSError:
        raise StrategySelectionError("STRATEGY_INPUT_FILE_INVALID") from None


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrategySelectionError("STRATEGY_PAYLOAD_INVALID")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _payload(document: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            document.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        canonical = canonical_json_bytes(value)
        reparsed = json.loads(
            canonical.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except StrategySelectionError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise StrategySelectionError("STRATEGY_PAYLOAD_INVALID") from None
    if type(reparsed) is not dict:
        raise StrategySelectionError("STRATEGY_PAYLOAD_INVALID")
    return cast(dict[str, object], reparsed)


def _canonical_story_ids(root: Path) -> tuple[str, ...]:
    document = _read_regular(root / BACKLOG_PATH, maximum_bytes=_MAX_INPUT_BYTES)
    try:
        text = document.decode("utf-8", errors="strict")
    except UnicodeError:
        raise StrategySelectionError("STRATEGY_CANONICAL_SOURCE_INVALID") from None
    story_ids = tuple(sorted(set(_STORY_PATTERN.findall(text))))
    if len(story_ids) < 100:
        raise StrategySelectionError("STRATEGY_CANONICAL_SOURCE_INVALID")
    return story_ids


def _write_json(stream: TextIO, document: dict[str, object]) -> None:
    stream.write((canonical_json_bytes(document) + b"\n").decode("utf-8"))
    stream.flush()


def parse_args(arguments: list[str]) -> CliOptions:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--override")
    parser.add_argument("--execute", action="store_true")
    namespace = parser.parse_args(arguments)
    if (
        type(namespace.root) is not Path
        or type(namespace.boundary) is not str
        or type(namespace.profile) is not Path
        or type(namespace.context) is not Path
        or (
            namespace.payload is not None
            and type(namespace.payload) is not Path
        )
        or (
            namespace.override is not None
            and type(namespace.override) is not str
        )
        or type(namespace.execute) is not bool
    ):
        raise StrategySelectionError("STRATEGY_CLI_ARGUMENT_INVALID")
    return CliOptions(
        root=namespace.root,
        boundary=namespace.boundary,
        profile=namespace.profile,
        context=namespace.context,
        payload=namespace.payload,
        override=namespace.override,
        execute=namespace.execute,
    )


def run(options: CliOptions) -> dict[str, object]:
    if type(options) is not CliOptions:
        raise TypeError("options must be an exact CliOptions")
    root = options.root.resolve()
    profile = load_profile_json(
        _read_regular(options.profile.resolve(), maximum_bytes=65_536)
    )
    context = load_gate_context_json(
        _read_regular(options.context.resolve(), maximum_bytes=65_536)
    )
    payload = (
        {}
        if options.payload is None
        else _payload(
            _read_regular(
                options.payload.resolve(),
                maximum_bytes=_MAX_INPUT_BYTES,
            )
        )
    )

    catalog = build_complete_catalog(_canonical_story_ids(root))
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
    try:
        options = parse_args(sys.argv[1:] if arguments is None else arguments)
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
