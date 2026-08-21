#!/usr/bin/env python3
"""Build the additive, exact-reviewed ST-0106 V3 findings ledger."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if os.fspath(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY_ROOT))

from scripts.scan_secrets import (  # noqa: E402
    Finding,
    RULE_GENERIC_CREDENTIAL,
    parse_reviewed_findings,
    scan_bytes,
)


SOURCE_PATH: Final = Path(
    "changes/st-0106/contracts/reviewed-secret-findings.v3-additions.json"
)
PARENT_LEDGER_PATH: Final = Path(
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
OUTPUT_PATH: Final = Path("changes/st-0106/contracts/reviewed-secret-findings.v3.yaml")
CURRENT_OPERATOR_PATH: Final = Path("scripts/github_ruleset_operator.py")
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0106_reviewed_secret_findings_v3.py"
)
EXPECTED_PARENT_BYTES: Final = 59_769
EXPECTED_PARENT_SHA256: Final = (
    "667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b"
)
EXPECTED_PARENT_ENTRIES: Final = 115
EXPECTED_NEW_ENTRIES: Final = 3
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
OBJECT_ID: Final = re.compile(r"^[0-9a-f]{40}$")
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0106-REVIEWED-SECRET-FINDINGS-V3-ADDITIONS",
    "version": "1.0.0",
    "story_id": "ST-0106",
    "status": "LOCAL_EXACT_REVIEW_CANDIDATE",
    "parent_ledger": {
        "uri": "repo://changes/st-0106/contracts/reviewed-secret-findings.v2.yaml",
        "bytes": EXPECTED_PARENT_BYTES,
        "sha256": EXPECTED_PARENT_SHA256,
        "entry_count": EXPECTED_PARENT_ENTRIES,
    },
}
EXPECTED_REVIEW: Final = {
    "rule_id": RULE_GENERIC_CREDENTIAL,
    "classification": "REVIEWED_FALSE_POSITIVE",
    "rationale": "Sanitized source location reviewed; no live credential is present.",
    "method": "HASH_BOUND_PYTHON_AST_ASSIGNMENT_CALL_WITHOUT_STRING_LITERALS",
    "matched_values_extracted": False,
    "matched_values_printed": False,
    "matched_values_persisted": False,
    "specific_rule_suppression": "FORBIDDEN",
}
ENTRY_KEYS: Final = {
    "scope",
    "exact_source_identifier",
    "exact_line_number",
    "exact_source_bytes",
    "exact_source_sha256",
    "exact_line_sha256",
    "path_hint",
    "expected_ast",
}
EXPECTED_AST: Final = {
    "node": "Assign",
    "target": "token",
    "call": "read_token_from_environment",
    "string_literal_count": 0,
}


class DuplicateKeyError(ValueError):
    """A strict JSON object repeated a key."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _regular_file(root: Path, relative: Path, label: str) -> bytes:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe {label} path")
    path = root / relative
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular non-symlink file")
    if metadata.st_size < 1 or metadata.st_size > MAX_INPUT_BYTES:
        raise RuntimeError(f"{label} size is invalid")
    return path.read_bytes()


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (DuplicateKeyError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} must be an object")
    return parsed


def _physical_line(data: bytes, line_number: int) -> bytes:
    lines = data.split(b"\n")
    if line_number < 1 or line_number > len(lines):
        raise RuntimeError("reviewed line is outside its source")
    selected = lines[line_number - 1]
    if line_number < len(lines):
        selected += b"\n"
    return selected


def _git_blob(root: Path, object_id: str) -> bytes:
    kind = subprocess.run(
        ["git", "cat-file", "-t", object_id],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if kind.returncode != 0 or kind.stdout != b"blob\n":
        raise RuntimeError("reviewed Git object is unavailable or not a blob")
    blob = subprocess.run(
        ["git", "cat-file", "blob", object_id],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if blob.returncode != 0 or len(blob.stdout) > MAX_INPUT_BYTES:
        raise RuntimeError("reviewed Git blob cannot be read safely")
    return blob.stdout


def _validate_python_shape(data: bytes, line_number: int) -> None:
    try:
        tree = ast.parse(data.decode("utf-8"), filename="<reviewed-git-blob>")
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError("reviewed Git blob is not valid UTF-8 Python") from exc
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and node.lineno == line_number
    ]
    if len(candidates) != 1:
        raise RuntimeError("reviewed line does not select one assignment")
    node = candidates[0]
    if (
        len(node.targets) != 1
        or not isinstance(node.targets[0], ast.Name)
        or node.targets[0].id != EXPECTED_AST["target"]
        or not isinstance(node.value, ast.Call)
        or not isinstance(node.value.func, ast.Name)
        or node.value.func.id != EXPECTED_AST["call"]
        or node.value.args
        or node.value.keywords
    ):
        raise RuntimeError("reviewed assignment shape differs")
    string_literals = sum(
        isinstance(child, ast.Constant) and isinstance(child.value, (str, bytes))
        for child in ast.walk(node)
    )
    if string_literals != EXPECTED_AST["string_literal_count"]:
        raise RuntimeError("reviewed assignment contains string literal material")


def _ledger_entry(raw: object, root: Path, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != ENTRY_KEYS:
        raise RuntimeError(f"reviewed addition {index} schema differs")
    if raw["scope"] != "git_history":
        raise RuntimeError(f"reviewed addition {index} scope differs")
    object_id = raw["exact_source_identifier"]
    line_number = raw["exact_line_number"]
    source_bytes = raw["exact_source_bytes"]
    source_sha256 = raw["exact_source_sha256"]
    line_sha256 = raw["exact_line_sha256"]
    if (
        not isinstance(object_id, str)
        or OBJECT_ID.fullmatch(object_id) is None
        or type(line_number) is not int
        or line_number < 1
        or type(source_bytes) is not int
        or source_bytes < 1
        or not isinstance(source_sha256, str)
        or SHA256.fullmatch(source_sha256) is None
        or not isinstance(line_sha256, str)
        or SHA256.fullmatch(line_sha256) is None
        or raw["path_hint"] != CURRENT_OPERATOR_PATH.as_posix()
        or raw["expected_ast"] != EXPECTED_AST
    ):
        raise RuntimeError(f"reviewed addition {index} binding differs")

    blob = _git_blob(root, object_id)
    line = _physical_line(blob, line_number)
    if (
        len(blob) != source_bytes
        or hashlib.sha256(blob).hexdigest() != source_sha256
        or hashlib.sha256(line).hexdigest() != line_sha256
    ):
        raise RuntimeError(f"reviewed addition {index} hash binding differs")
    expected_finding = Finding(object_id, line_number, RULE_GENERIC_CREDENTIAL)
    line_findings = {
        finding
        for finding in scan_bytes(blob, object_id)
        if finding.line == line_number
    }
    if line_findings != {expected_finding}:
        raise RuntimeError(f"reviewed addition {index} scanner finding differs")
    _validate_python_shape(blob, line_number)
    return {
        "scope": "git_history",
        "exact_source_identifier": object_id,
        "exact_line_number": line_number,
        "exact_source_bytes": source_bytes,
        "exact_source_sha256": source_sha256,
        "exact_line_sha256": line_sha256,
        "classification": EXPECTED_REVIEW["classification"],
        "rationale": EXPECTED_REVIEW["rationale"],
    }


def render(root: Path = REPOSITORY_ROOT) -> bytes:
    parent_bytes = _regular_file(root, PARENT_LEDGER_PATH, "parent ledger")
    if (
        len(parent_bytes) != EXPECTED_PARENT_BYTES
        or hashlib.sha256(parent_bytes).hexdigest() != EXPECTED_PARENT_SHA256
    ):
        raise RuntimeError("parent ledger binding differs")
    parent = _strict_json(parent_bytes, "parent ledger")
    if len(parse_reviewed_findings(parent_bytes)) != EXPECTED_PARENT_ENTRIES:
        raise RuntimeError("parent ledger entry count differs")

    source = _strict_json(
        _regular_file(root, SOURCE_PATH, "additions source"), "additions source"
    )
    if set(source) != {"document", "review", "entries"}:
        raise RuntimeError("additions source top-level schema differs")
    if source["document"] != EXPECTED_DOCUMENT or source["review"] != EXPECTED_REVIEW:
        raise RuntimeError("additions source policy binding differs")
    raw_entries = source["entries"]
    if not isinstance(raw_entries, list) or len(raw_entries) != EXPECTED_NEW_ENTRIES:
        raise RuntimeError("additions source entry inventory differs")
    additions = [
        _ledger_entry(raw, root, index)
        for index, raw in enumerate(raw_entries, start=1)
    ]
    keys = {
        (entry["scope"], entry["exact_source_identifier"], entry["exact_line_number"])
        for entry in [*parent["entries"], *additions]
    }
    if len(keys) != EXPECTED_PARENT_ENTRIES + EXPECTED_NEW_ENTRIES:
        raise RuntimeError("generated ledger contains duplicate bindings")

    current_operator = _regular_file(root, CURRENT_OPERATOR_PATH, "current operator")
    if scan_bytes(current_operator, CURRENT_OPERATOR_PATH.as_posix()):
        raise RuntimeError("current operator still contains a sanitized finding")

    generated = dict(parent)
    generated["entries"] = [*parent["entries"], *additions]
    content = (json.dumps(generated, indent=2, ensure_ascii=True) + "\n").encode()
    if len(parse_reviewed_findings(content)) != len(generated["entries"]):
        raise RuntimeError("generated ledger does not validate exactly")
    return content


def _install(root: Path, content: bytes) -> None:
    target = root / OUTPUT_PATH
    parent = target.parent
    parent_metadata = parent.lstat()
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
        parent_metadata.st_mode
    ):
        raise RuntimeError("generated ledger parent is unsafe")
    if target.exists() or target.is_symlink():
        target_metadata = target.lstat()
        if stat.S_ISLNK(target_metadata.st_mode) or not stat.S_ISREG(
            target_metadata.st_mode
        ):
            raise RuntimeError("generated ledger target is unsafe")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".reviewed-v3-", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        parent_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        content = render()
        if arguments.check:
            target = REPOSITORY_ROOT / OUTPUT_PATH
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != content
            ):
                raise RuntimeError("generated V3 ledger drift")
            mode = "check"
        else:
            _install(REPOSITORY_ROOT, content)
            mode = "install"
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "entry_count": EXPECTED_PARENT_ENTRIES + EXPECTED_NEW_ENTRIES,
                "mode": mode,
                "specific_rule_suppression": "FORBIDDEN",
                "status": "PASS",
                "story_id": "ST-0106",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
