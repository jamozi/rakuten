#!/usr/bin/env python3
"""Owner for the exact ST-0106 reviewed-finding source rebind.

The owner never classifies a new finding.  It can only carry one already
reviewed V2 entry forward when the reviewed physical line is byte-identical,
the complete sanitized finding set is unchanged, and every source change is
an explicitly hash-bound hunk outside that line.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import cast, Final


REPO_ROOT: Final = Path(__file__).resolve(strict=True).parents[1]
INPUT_PATH: Final = Path("changes/st-0106/reviewed-finding-source-rebind.v3.json")
OWNER_PATH: Final = Path("scripts/build_st0106_reviewed_findings_rebind.py")
HEX_SHA256: Final = re.compile(r"[0-9a-f]{64}")
HEX_OBJECT_ID: Final = re.compile(r"[0-9a-f]{40}")
RATIONALE: Final = "Sanitized source location reviewed; no live credential is present."
EXPECTED_PREDECESSOR_PATH: Final = (
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
EXPECTED_SCANNER_PATH: Final = "scripts/scan_secrets.py"
EXPECTED_LEDGER_PATH: Final = (
    "changes/st-0106/contracts/reviewed-secret-findings.v3.yaml"
)
EXPECTED_MANIFEST_PATH: Final = (
    "changes/st-0106/generated/reviewed-findings-rebind.v3.manifest.json"
)
EXPECTED_BOUNDARIES: Final = {
    "classification_change": "FORBIDDEN",
    "rationale_change": "FORBIDDEN",
    "reviewed_line_change": "FORBIDDEN",
    "specific_rule_suppression": "FORBIDDEN",
    "scanner_semantic_change": "NONE",
    "v1_v2_history_change": "FORBIDDEN",
    "external_action": "NONE",
    "formal_tst_001": "NOT_EXECUTED",
    "formal_tst_002": "NOT_EXECUTED",
    "release_or_production": "NOT_AUTHORIZED",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import scan_secrets as scanner  # noqa: E402


class OwnerError(RuntimeError):
    """A closed, value-free reconciliation refusal."""


class DuplicateKey(ValueError):
    """A duplicate JSON object key."""


@dataclass(frozen=True)
class SourceVersion:
    """One exact source version used by the rebind proof."""

    size: int
    sha256: str
    blob_oid: str


@dataclass(frozen=True)
class ChangedHunk:
    """One value-free physical-line change description."""

    operation: str
    prior_start_line: int
    prior_end_line: int
    current_start_line: int
    current_end_line: int
    prior_line_sha256: str
    current_line_sha256: str


@dataclass(frozen=True)
class RebindPolicy:
    """Closed source-binding policy parsed from the Story input."""

    path: str
    reviewed_line: int
    reviewed_line_sha256: str
    prior: SourceVersion
    current: SourceVersion
    expected_findings: frozenset[tuple[int, str]]
    allowed_hunks: tuple[ChangedHunk, ...]


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(key)
        result[key] = value
    return result


def _load_json(data: bytes, *, code: str) -> dict[str, object]:
    try:
        value: object = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except DuplicateKey, UnicodeDecodeError, ValueError:
        raise OwnerError(code) from None
    if type(value) is not dict:
        raise OwnerError(code)
    return cast(dict[str, object], value)


def _mapping(value: object, *, keys: frozenset[str], code: str) -> dict[str, object]:
    if type(value) is not dict:
        raise OwnerError(code)
    candidate = cast(dict[str, object], value)
    if frozenset(candidate) != keys:
        raise OwnerError(code)
    return candidate


def _sequence(value: object, *, code: str) -> list[object]:
    if type(value) is not list:
        raise OwnerError(code)
    return cast(list[object], value)


def _text(value: object, *, code: str) -> str:
    if type(value) is not str or not value:
        raise OwnerError(code)
    return value


def _positive_int(value: object, *, code: str) -> int:
    if type(value) is not int or value < 1:
        raise OwnerError(code)
    return value


def _sha256(value: object, *, code: str) -> str:
    candidate = _text(value, code=code)
    if HEX_SHA256.fullmatch(candidate) is None:
        raise OwnerError(code)
    return candidate


def _blob_oid(value: object, *, code: str) -> str:
    candidate = _text(value, code=code)
    if HEX_OBJECT_ID.fullmatch(candidate) is None:
        raise OwnerError(code)
    return candidate


def _relative_path(value: object, *, code: str) -> str:
    candidate = _text(value, code=code)
    path = Path(candidate)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise OwnerError(code)
    return candidate


def parse_rebind_policy(document: Mapping[str, object]) -> RebindPolicy:
    source = _mapping(
        document.get("source_rebind"),
        keys=frozenset(
            {
                "scope",
                "path",
                "reviewed_line",
                "reviewed_line_sha256",
                "prior_blob_oid",
                "prior_bytes",
                "prior_sha256",
                "current_blob_oid",
                "current_bytes",
                "current_sha256",
                "expected_findings",
                "allowed_hunks",
            }
        ),
        code="INVALID_REBIND_SCHEMA",
    )
    if source["scope"] != "worktree":
        raise OwnerError("INVALID_REBIND_SCOPE")

    raw_findings = _sequence(
        source["expected_findings"], code="INVALID_EXPECTED_FINDINGS"
    )
    expected_findings: set[tuple[int, str]] = set()
    for raw in raw_findings:
        finding = _mapping(
            raw,
            keys=frozenset({"line", "rule_id"}),
            code="INVALID_EXPECTED_FINDING",
        )
        line = _positive_int(finding["line"], code="INVALID_EXPECTED_FINDING")
        rule_id = _text(finding["rule_id"], code="INVALID_EXPECTED_FINDING")
        if rule_id != scanner.RULE_GENERIC_CREDENTIAL:
            raise OwnerError("SPECIFIC_RULE_REBIND_FORBIDDEN")
        if (line, rule_id) in expected_findings:
            raise OwnerError("DUPLICATE_EXPECTED_FINDING")
        expected_findings.add((line, rule_id))

    raw_hunks = _sequence(source["allowed_hunks"], code="INVALID_ALLOWED_HUNKS")
    hunks: list[ChangedHunk] = []
    for raw in raw_hunks:
        hunk = _mapping(
            raw,
            keys=frozenset(
                {
                    "operation",
                    "prior_start_line",
                    "prior_end_line",
                    "current_start_line",
                    "current_end_line",
                    "prior_line_sha256",
                    "current_line_sha256",
                }
            ),
            code="INVALID_ALLOWED_HUNK",
        )
        parsed = ChangedHunk(
            operation=_text(hunk["operation"], code="INVALID_ALLOWED_HUNK"),
            prior_start_line=_positive_int(
                hunk["prior_start_line"], code="INVALID_ALLOWED_HUNK"
            ),
            prior_end_line=_positive_int(
                hunk["prior_end_line"], code="INVALID_ALLOWED_HUNK"
            ),
            current_start_line=_positive_int(
                hunk["current_start_line"], code="INVALID_ALLOWED_HUNK"
            ),
            current_end_line=_positive_int(
                hunk["current_end_line"], code="INVALID_ALLOWED_HUNK"
            ),
            prior_line_sha256=_sha256(
                hunk["prior_line_sha256"], code="INVALID_ALLOWED_HUNK"
            ),
            current_line_sha256=_sha256(
                hunk["current_line_sha256"], code="INVALID_ALLOWED_HUNK"
            ),
        )
        if parsed.operation != "replace":
            raise OwnerError("INVALID_ALLOWED_HUNK")
        hunks.append(parsed)

    return RebindPolicy(
        path=_relative_path(source["path"], code="INVALID_REBIND_PATH"),
        reviewed_line=_positive_int(
            source["reviewed_line"], code="INVALID_REVIEWED_LINE"
        ),
        reviewed_line_sha256=_sha256(
            source["reviewed_line_sha256"], code="INVALID_REVIEWED_LINE_HASH"
        ),
        prior=SourceVersion(
            size=_positive_int(source["prior_bytes"], code="INVALID_PRIOR_SOURCE"),
            sha256=_sha256(source["prior_sha256"], code="INVALID_PRIOR_SOURCE"),
            blob_oid=_blob_oid(source["prior_blob_oid"], code="INVALID_PRIOR_SOURCE"),
        ),
        current=SourceVersion(
            size=_positive_int(source["current_bytes"], code="INVALID_CURRENT_SOURCE"),
            sha256=_sha256(source["current_sha256"], code="INVALID_CURRENT_SOURCE"),
            blob_oid=_blob_oid(
                source["current_blob_oid"], code="INVALID_CURRENT_SOURCE"
            ),
        ),
        expected_findings=frozenset(expected_findings),
        allowed_hunks=tuple(hunks),
    )


def _verify_source(data: bytes, expected: SourceVersion, *, code: str) -> None:
    if (
        len(data) != expected.size
        or hashlib.sha256(data).hexdigest() != expected.sha256
    ):
        raise OwnerError(code)


def _line_bytes(data: bytes, line: int) -> bytes:
    lines = data.splitlines(keepends=True)
    if line > len(lines):
        raise OwnerError("REVIEWED_LINE_MISSING")
    return lines[line - 1]


def _line_hash(lines: Sequence[bytes], start: int, end: int, *, code: str) -> str:
    if start < 1 or end < start or end > len(lines):
        raise OwnerError(code)
    return hashlib.sha256(b"".join(lines[start - 1 : end])).hexdigest()


def observed_hunks(prior_data: bytes, current_data: bytes) -> tuple[ChangedHunk, ...]:
    prior_lines = prior_data.splitlines(keepends=True)
    current_lines = current_data.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=prior_lines, b=current_lines, autojunk=False)
    result: list[ChangedHunk] = []
    for (
        operation,
        prior_start,
        prior_end,
        current_start,
        current_end,
    ) in matcher.get_opcodes():
        if operation == "equal":
            continue
        prior_start_line = prior_start + 1
        prior_end_line = prior_end
        current_start_line = current_start + 1
        current_end_line = current_end
        if operation != "replace":
            raise OwnerError("SOURCE_CHANGE_OPERATION_FORBIDDEN")
        result.append(
            ChangedHunk(
                operation=operation,
                prior_start_line=prior_start_line,
                prior_end_line=prior_end_line,
                current_start_line=current_start_line,
                current_end_line=current_end_line,
                prior_line_sha256=_line_hash(
                    prior_lines,
                    prior_start_line,
                    prior_end_line,
                    code="INVALID_PRIOR_HUNK",
                ),
                current_line_sha256=_line_hash(
                    current_lines,
                    current_start_line,
                    current_end_line,
                    code="INVALID_CURRENT_HUNK",
                ),
            )
        )
    return tuple(result)


def _hunk_touches_line(hunk: ChangedHunk, line: int) -> bool:
    return (
        hunk.prior_start_line <= line <= hunk.prior_end_line
        or hunk.current_start_line <= line <= hunk.current_end_line
    )


def _sanitized_findings(data: bytes, source: str) -> frozenset[tuple[int, str]]:
    return frozenset(
        (finding.line, finding.rule_id)
        for finding in scanner.scan_payload(data, source, source)
    )


def reconcile_ledger(
    predecessor_data: bytes,
    prior_data: bytes,
    current_data: bytes,
    policy: RebindPolicy,
) -> bytes:
    """Return the exact V3 ledger or refuse without exposing source content."""

    _verify_source(prior_data, policy.prior, code="PRIOR_SOURCE_DRIFT")
    _verify_source(current_data, policy.current, code="CURRENT_SOURCE_DRIFT")
    if (
        hashlib.sha256(_line_bytes(prior_data, policy.reviewed_line)).hexdigest()
        != policy.reviewed_line_sha256
        or hashlib.sha256(_line_bytes(current_data, policy.reviewed_line)).hexdigest()
        != policy.reviewed_line_sha256
    ):
        raise OwnerError("REVIEWED_LINE_DRIFT")

    observed = observed_hunks(prior_data, current_data)
    if observed != policy.allowed_hunks:
        raise OwnerError("SOURCE_CHANGE_NOT_ALLOWLISTED")
    if any(_hunk_touches_line(hunk, policy.reviewed_line) for hunk in observed):
        raise OwnerError("REVIEWED_LINE_TOUCHED")

    prior_findings = _sanitized_findings(prior_data, policy.path)
    current_findings = _sanitized_findings(current_data, policy.path)
    if prior_findings != policy.expected_findings:
        raise OwnerError("PRIOR_FINDING_SET_DRIFT")
    if current_findings != policy.expected_findings:
        raise OwnerError("CURRENT_FINDING_SET_DRIFT")

    predecessor = _load_json(predecessor_data, code="INVALID_PREDECESSOR_LEDGER")
    scanner.parse_reviewed_findings(predecessor_data)
    raw_entries = predecessor.get("entries")
    if type(raw_entries) is not list:
        raise OwnerError("INVALID_PREDECESSOR_LEDGER")
    entries = cast(list[object], raw_entries)
    matches: list[dict[str, object]] = []
    for raw_entry in entries:
        if type(raw_entry) is not dict:
            raise OwnerError("INVALID_PREDECESSOR_LEDGER")
        candidate_entry = cast(dict[str, object], raw_entry)
        if (
            candidate_entry.get("scope") == "worktree"
            and candidate_entry.get("exact_source_identifier") == policy.path
            and candidate_entry.get("exact_line_number") == policy.reviewed_line
        ):
            matches.append(candidate_entry)
    if len(matches) != 1:
        raise OwnerError("REVIEWED_ENTRY_NOT_UNIQUE")
    entry = matches[0]
    if (
        entry.get("exact_source_bytes") != policy.prior.size
        or entry.get("exact_source_sha256") != policy.prior.sha256
        or entry.get("exact_line_sha256") != policy.reviewed_line_sha256
        or entry.get("classification") != "REVIEWED_FALSE_POSITIVE"
        or entry.get("rationale") != RATIONALE
    ):
        raise OwnerError("PREDECESSOR_ENTRY_DRIFT")
    entry["exact_source_bytes"] = policy.current.size
    entry["exact_source_sha256"] = policy.current.sha256
    rendered = (json.dumps(predecessor, ensure_ascii=True, indent=2) + "\n").encode(
        "utf-8"
    )
    scanner.parse_reviewed_findings(rendered)
    return rendered


def _git_blob(root: Path, object_id: str) -> bytes:
    try:
        result = subprocess.run(
            ["/usr/bin/git", "cat-file", "blob", object_id],
            cwd=root,
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except OSError, subprocess.TimeoutExpired:
        raise OwnerError("PRIOR_BLOB_UNAVAILABLE") from None
    if result.returncode != 0:
        raise OwnerError("PRIOR_BLOB_UNAVAILABLE")
    return result.stdout


def _exact_file(root: Path, binding: Mapping[str, object], *, code: str) -> bytes:
    path = _relative_path(binding.get("path"), code=code)
    data = scanner.read_maintained_file(root, path)
    if len(data) != _positive_int(binding.get("bytes"), code=code) or hashlib.sha256(
        data
    ).hexdigest() != _sha256(binding.get("sha256"), code=code):
        raise OwnerError(code)
    return data


def _render_manifest(
    *,
    input_data: bytes,
    owner_data: bytes,
    scanner_data: bytes,
    predecessor_data: bytes,
    prior_data: bytes,
    current_data: bytes,
    ledger_data: bytes,
    policy: RebindPolicy,
    output_path: str,
) -> bytes:
    document = {
        "schema_version": 1,
        "story_id": "ST-0106",
        "status": "LOCAL_RECONCILIATION_COMPLETE_NOT_FORMAL_EVIDENCE",
        "owner": {
            "path": OWNER_PATH.as_posix(),
            "bytes": len(owner_data),
            "sha256": hashlib.sha256(owner_data).hexdigest(),
            "check_command": (
                "/home/minami/rakuten/.venv/bin/python "
                "scripts/build_st0106_reviewed_findings_rebind.py --check"
            ),
        },
        "inputs": [
            {
                "path": INPUT_PATH.as_posix(),
                "bytes": len(input_data),
                "sha256": hashlib.sha256(input_data).hexdigest(),
            },
            {
                "path": "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml",
                "bytes": len(predecessor_data),
                "sha256": hashlib.sha256(predecessor_data).hexdigest(),
            },
            {
                "path": "scripts/scan_secrets.py",
                "bytes": len(scanner_data),
                "sha256": hashlib.sha256(scanner_data).hexdigest(),
            },
        ],
        "source_rebind": {
            "path": policy.path,
            "reviewed_line": policy.reviewed_line,
            "reviewed_line_sha256": policy.reviewed_line_sha256,
            "prior_blob_oid": policy.prior.blob_oid,
            "prior_bytes": len(prior_data),
            "prior_sha256": hashlib.sha256(prior_data).hexdigest(),
            "current_blob_oid": policy.current.blob_oid,
            "current_bytes": len(current_data),
            "current_sha256": hashlib.sha256(current_data).hexdigest(),
            "changed_hunks": [hunk.__dict__ for hunk in policy.allowed_hunks],
            "sanitized_finding_set_unchanged": True,
            "specific_rule_findings": 0,
            "classification_change": "NONE",
            "rationale_change": "NONE",
        },
        "generated_ledger": {
            "path": output_path,
            "bytes": len(ledger_data),
            "sha256": hashlib.sha256(ledger_data).hexdigest(),
            "entry_count": 115,
            "changed_entry_count": 1,
            "specific_rule_suppression": "FORBIDDEN",
        },
        "boundaries": {
            "scanner_semantic_change": "NONE",
            "historical_v1_v2_artifact_change": "NONE",
            "external_action": "NONE",
            "formal_tst_001": "NOT_EXECUTED",
            "formal_tst_002": "NOT_EXECUTED",
            "release_or_production": "NOT_AUTHORIZED",
        },
    }
    return (json.dumps(document, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def build_outputs(root: Path = REPO_ROOT) -> tuple[Path, bytes, Path, bytes]:
    input_data = scanner.read_maintained_file(root, INPUT_PATH.as_posix())
    document = _load_json(input_data, code="INVALID_REBIND_INPUT")
    if set(document) != {
        "schema_version",
        "story_id",
        "status",
        "predecessor_ledger",
        "scanner_source",
        "source_rebind",
        "outputs",
        "boundaries",
    }:
        raise OwnerError("INVALID_REBIND_INPUT")
    if (
        document["schema_version"] != 1
        or document["story_id"] != "ST-0106"
        or document["status"] != "LOCAL_RECONCILIATION_INPUT"
    ):
        raise OwnerError("INVALID_REBIND_INPUT")

    predecessor_binding = _mapping(
        document["predecessor_ledger"],
        keys=frozenset({"path", "bytes", "sha256", "entry_count"}),
        code="INVALID_PREDECESSOR_BINDING",
    )
    if predecessor_binding["path"] != EXPECTED_PREDECESSOR_PATH:
        raise OwnerError("INVALID_PREDECESSOR_BINDING")
    predecessor_data = _exact_file(
        root, predecessor_binding, code="PREDECESSOR_LEDGER_DRIFT"
    )
    predecessor = _load_json(predecessor_data, code="INVALID_PREDECESSOR_LEDGER")
    raw_predecessor_entries = predecessor.get("entries")
    if type(raw_predecessor_entries) is not list:
        raise OwnerError("PREDECESSOR_ENTRY_COUNT_DRIFT")
    predecessor_entries = cast(list[object], raw_predecessor_entries)
    if len(predecessor_entries) != _positive_int(
        predecessor_binding["entry_count"], code="INVALID_PREDECESSOR_BINDING"
    ):
        raise OwnerError("PREDECESSOR_ENTRY_COUNT_DRIFT")

    scanner_binding = _mapping(
        document["scanner_source"],
        keys=frozenset({"path", "bytes", "sha256"}),
        code="INVALID_SCANNER_BINDING",
    )
    if scanner_binding["path"] != EXPECTED_SCANNER_PATH:
        raise OwnerError("INVALID_SCANNER_BINDING")
    scanner_data = _exact_file(root, scanner_binding, code="SCANNER_SOURCE_DRIFT")
    policy = parse_rebind_policy(document)
    prior_data = _git_blob(root, policy.prior.blob_oid)
    current_data = scanner.read_maintained_file(root, policy.path)
    current_blob_data = _git_blob(root, policy.current.blob_oid)
    if current_data != current_blob_data:
        raise OwnerError("CURRENT_BLOB_WORKTREE_MISMATCH")
    ledger_data = reconcile_ledger(predecessor_data, prior_data, current_data, policy)

    outputs = _mapping(
        document["outputs"],
        keys=frozenset({"ledger_path", "manifest_path"}),
        code="INVALID_OUTPUT_BINDING",
    )
    ledger_path_text = _relative_path(
        outputs["ledger_path"], code="INVALID_OUTPUT_BINDING"
    )
    manifest_path_text = _relative_path(
        outputs["manifest_path"], code="INVALID_OUTPUT_BINDING"
    )
    if (
        ledger_path_text != EXPECTED_LEDGER_PATH
        or manifest_path_text != EXPECTED_MANIFEST_PATH
    ):
        raise OwnerError("INVALID_OUTPUT_BINDING")
    boundaries = _mapping(
        document["boundaries"],
        keys=frozenset(EXPECTED_BOUNDARIES),
        code="INVALID_BOUNDARIES",
    )
    if boundaries != EXPECTED_BOUNDARIES:
        raise OwnerError("INVALID_BOUNDARIES")
    owner_data = scanner.read_maintained_file(root, OWNER_PATH.as_posix())
    manifest_data = _render_manifest(
        input_data=input_data,
        owner_data=owner_data,
        scanner_data=scanner_data,
        predecessor_data=predecessor_data,
        prior_data=prior_data,
        current_data=current_data,
        ledger_data=ledger_data,
        policy=policy,
        output_path=ledger_path_text,
    )
    return (
        root / ledger_path_text,
        ledger_data,
        root / manifest_path_text,
        manifest_data,
    )


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _check(path: Path, expected: bytes) -> None:
    try:
        current = path.read_bytes()
    except OSError:
        raise OwnerError(
            f"GENERATED_ARTIFACT_MISSING:{path.relative_to(REPO_ROOT)}"
        ) from None
    if current != expected:
        raise OwnerError(f"GENERATED_ARTIFACT_DRIFT:{path.relative_to(REPO_ROOT)}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        ledger_path, ledger_data, manifest_path, manifest_data = build_outputs()
        if arguments.write:
            _write(ledger_path, ledger_data)
            _write(manifest_path, manifest_data)
            print("ST-0106 reviewed-finding rebind generated")
        else:
            _check(ledger_path, ledger_data)
            _check(manifest_path, manifest_data)
            print("ST-0106 reviewed-finding rebind checked")
    except (OSError, OwnerError, scanner.ScanError) as error:
        code = error.args[0] if error.args else type(error).__name__
        print(f"ST-0106 reviewed-finding rebind failed: {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
