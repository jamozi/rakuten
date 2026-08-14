#!/usr/bin/env python3
"""Deterministically scan maintained files and fetched Git blobs for secrets.

The command deliberately has no allowlist: a maintained input that cannot be
read and inspected safely is an operational failure.  Findings contain only a
rule identifier and source location; matched bytes are never rendered.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tokenize
import unicodedata
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve(strict=True).parents[1]

READ_CHUNK_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_DEPTH = 4
MAX_COMPRESSION_RATIO = 200
COMPRESSION_RATIO_MINIMUM_BYTES = 1024 * 1024
GIT_TIMEOUT_SECONDS = 60

MAX_RHS_PHYSICAL_LINE_BYTES = 4096
MAX_RHS_EXPRESSION_BYTES = 2048
MAX_RHS_SUBSTANTIVE_TOKENS = 256
MAX_RHS_AST_NODES = 128
MAX_RHS_AST_DEPTH = 24
MAX_RHS_LITERAL_TOKENS = 16
MAX_RHS_DECODED_BYTES_LITERAL = 1024
MAX_RHS_DECODED_STR_CODE_POINTS = 1024
MAX_RHS_DECODED_STR_UTF8_BYTES = 1024
MAX_RHS_AGGREGATE_LITERAL_BYTES = 2048
MAX_GENERIC_CANDIDATE_BYTES = 512

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_OPERATIONAL_ERROR = 2

RULE_AWS_ACCESS_KEY = "AWS_ACCESS_KEY_ID"
RULE_GITHUB_TOKEN = "GITHUB_TOKEN"
RULE_OPENAI_API_KEY = "OPENAI_API_KEY"
RULE_PRIVATE_KEY = "PRIVATE_KEY"
RULE_GENERIC_CREDENTIAL = "GENERIC_CREDENTIAL"

SPECIFIC_RULES = (
    (
        RULE_AWS_ACCESS_KEY,
        re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    ),
    (
        RULE_GITHUB_TOKEN,
        re.compile(
            rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,255}"
            rb"|github_pat_[A-Za-z0-9_]{20,255})(?![A-Za-z0-9_])"
        ),
    ),
    (
        RULE_OPENAI_API_KEY,
        re.compile(
            rb"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?"
            rb"[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9_-])"
        ),
    ),
    (
        RULE_PRIVATE_KEY,
        re.compile(
            rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?"
            rb"PRIVATE KEY-----"
        ),
    ),
)

GENERIC_ASSIGNMENT = re.compile(
    rb"(?ix)"
    rb"(?<![A-Za-z0-9_])['\"]?"
    rb"(?:api[_-]?key|access[_-]?(?:key|token)|auth[_-]?token|"
    rb"client[_-]?secret|password|passwd|pwd|secret|token)"
    rb"['\"]?[ \t]*(?::|=)[ \t]*"
    rb"(?:"
    rb"\"(?P<double>[^\"\r\n]{8,512})\"|"
    rb"'(?P<single>[^'\r\n]{8,512})'|"
    rb"(?P<bare>[^\s,;#{}\[\]]{8,512})"
    rb")"
)

GENERIC_PLACEHOLDER = re.compile(
    rb"(?:"
    rb"change[-_]?me|changeme|do[-_]?not[-_]?read|dummy|example|fake|"
    rb"fixture|forbidden|masked|not[-_]?a[-_]?(?:real[-_]?)?secret|"
    rb"placeholder|redacted|replace[-_]?me|sample|test[-_]?token|"
    rb"your[-_]?(?:key|password|secret|token)"
    rb")"
    rb"(?:[-_.](?:"
    rb"access|api|auth|client|credential|credentials|deployment|dev|"
    rb"development|env|environment|example|fixture|for|here|in|key|"
    rb"local|only|password|placeholder|production|pwd|required|sample|"
    rb"secret|staging|test|tests|token|use|value"
    rb"))*"
)

GENERIC_SENTINELS = frozenset({b"none", b"null", b"required", b"undefined"})

NOT_REAL_CREDENTIAL_KINDS_HYPHEN = (
    rb"(?:access-key|api-key|auth-token|client-secret|"
    rb"credential|key|password|secret|token)"
)
NOT_REAL_CREDENTIAL_KINDS_UNDERSCORE = (
    rb"(?:access_key|api_key|auth_token|client_secret|"
    rb"credential|key|password|secret|token)"
)
EXPLICIT_NOT_REAL_FIXTURE = re.compile(
    rb"not-a-real-"
    + NOT_REAL_CREDENTIAL_KINDS_HYPHEN
    + rb"(?:-(?:[0-9]+|ST[0-9]+))?(?:-x{4,})?"
    + rb"|not_real_"
    + NOT_REAL_CREDENTIAL_KINDS_UNDERSCORE
    + rb"(?:_(?:[0-9]+|ST[0-9]+))?(?:_x{4,})?"
)
KIND_FIRST_NOT_REAL_FIXTURE = re.compile(
    rb"(?:client-secret|access-token)-not-real-[0-9]+-x{4,}"
)

ASCII_IDENTIFIER = rb"[A-Za-z_][A-Za-z0-9_]*"
ANGLE_PLACEHOLDER_IDENTIFIER = (
    rb"(?i:access_key|access_token|api_key|auth_token|client_secret|"
    rb"password|passwd|pwd|secret|token)"
)
EXTERNAL_REFERENCE = re.compile(
    rb"(?:"
    rb"\$" + ASCII_IDENTIFIER + rb"|"
    rb"\$\{" + ASCII_IDENTIFIER + rb"\}|"
    rb"%" + ASCII_IDENTIFIER + rb"%|"
    rb"\{\{" + ASCII_IDENTIFIER + rb"\}\}|"
    rb"<" + ANGLE_PLACEHOLDER_IDENTIFIER + rb">"
    rb")"
)

CREDENTIAL_VOCABULARY = frozenset(
    {
        b"access",
        b"api",
        b"auth",
        b"client",
        b"credential",
        b"credentials",
        b"key",
        b"password",
        b"secret",
        b"token",
    }
)
SYMBOLIC_REFERENCE = re.compile(rb"[a-z]+(?:[-_][a-z]+)*")
LOWER_CASE_PASSPHRASE = re.compile(rb"[a-z]+(?:-[a-z]+){2,}")

ENTROPY_FAMILY_DIGIT_BEARING = "digit_bearing"
ENTROPY_FAMILY_DIGIT_FREE_OPAQUE = "digit_free_opaque"
ENTROPY_FAMILY_LOWER_CASE_PASSPHRASE = "lower_case_passphrase"
ENTROPY_THRESHOLDS = {
    ENTROPY_FAMILY_DIGIT_BEARING: (7, 2),
    ENTROPY_FAMILY_DIGIT_FREE_OPAQUE: (15, 4),
    ENTROPY_FAMILY_LOWER_CASE_PASSPHRASE: (33, 10),
}

SAFE_BARE_SOURCE_EXPRESSIONS = frozenset(
    {
        b'content.decode("utf-8")',
        b"_read_password_file(target.password_file)",
    }
)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".idea",
        ".mypy_cache",
        ".next",
        ".node-offline-check",
        ".npm-cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".secrets",
        ".tox",
        ".venv",
        ".venv-offline-check",
        ".vscode",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "venv",
    }
)

EXCLUDED_FILE_NAMES = frozenset(
    {
        ".coverage",
        ".DS_Store",
        "Thumbs.db",
        "coverage.xml",
        "settings.local.json",
    }
)

ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
ZIP_SUFFIXES = (".zip", ".jar", ".whl", ".docx", ".xlsx", ".pptx")
HEX_OBJECT_ID = re.compile(rb"[0-9a-f]{40}(?:[0-9a-f]{24})?")
ARCHIVE_READ_ERRORS = (
    EOFError,
    NotImplementedError,
    OSError,
    RuntimeError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
)
GIT_EXECUTION_ERRORS = (OSError, subprocess.TimeoutExpired)
ASCII_LITERAL_ERRORS = (
    SyntaxError,
    UnicodeError,
    ValueError,
    tokenize.TokenError,
)
TOKENIZED_LITERAL_ERRORS = (IndentationError, tokenize.TokenError)
SOURCE_EXPRESSION_ERRORS = (SyntaxError, UnicodeError, ValueError)
RHS_TOKEN_ERRORS = (IndentationError, SyntaxError, tokenize.TokenError)
ENTROPY_LOOKUP_ERRORS = (KeyError, TypeError)


@dataclass(frozen=True, order=True)
class Finding:
    """A sanitized secret finding."""

    source: str
    line: int
    rule_id: str


@dataclass
class ArchiveBudget:
    """Expansion limits shared by one outer archive and all nested archives."""

    members: int = 0
    expanded_bytes: int = 0


class ScanError(RuntimeError):
    """An unsafe or unreadable input, represented without attacker data."""

    def __init__(self, code: str, source: str) -> None:
        super().__init__(code)
        self.code = code
        self.source = source


def _line_number(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def _generic_value(
    match: re.Match[bytes],
) -> tuple[str, bytes, tuple[int, int]]:
    for group in ("double", "single", "bare"):
        value = match.group(group)
        if value is not None:
            return group, value, match.span(group)
    raise AssertionError("generic credential expression has no value")


def _greatest_common_divisor(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return left


def _byte_histogram(candidate: bytes) -> tuple[int, ...]:
    histogram = [0] * 256
    for byte in candidate:
        histogram[byte] += 1
    return tuple(histogram)


def _validated_entropy_threshold(family: str) -> tuple[int, int]:
    expected_thresholds = (
        ("digit_bearing", (7, 2)),
        ("digit_free_opaque", (15, 4)),
        ("lower_case_passphrase", (33, 10)),
    )
    if type(ENTROPY_THRESHOLDS) is not dict or len(ENTROPY_THRESHOLDS) != 3:
        raise RuntimeError("invalid entropy configuration") from None
    for expected_family, expected_pair in expected_thresholds:
        configured_pair = ENTROPY_THRESHOLDS.get(expected_family)
        if (
            type(configured_pair) is not tuple
            or len(configured_pair) != 2
            or configured_pair != expected_pair
            or type(configured_pair[0]) is not int
            or type(configured_pair[1]) is not int
            or configured_pair[0] <= 0
            or configured_pair[1] <= 0
            or _greatest_common_divisor(*configured_pair) != 1
        ):
            raise RuntimeError("invalid entropy configuration")
    try:
        return ENTROPY_THRESHOLDS[family]
    except ENTROPY_LOOKUP_ERRORS:
        raise RuntimeError("invalid entropy configuration") from None


def _entropy_integer_operands(
    candidate: bytes,
    family: str,
) -> tuple[int, int] | None:
    numerator, denominator = _validated_entropy_threshold(family)
    if type(candidate) is not bytes:
        raise RuntimeError("invalid entropy candidate")

    length = len(candidate)
    if length > MAX_GENERIC_CANDIDATE_BYTES:
        raise RuntimeError("invalid entropy candidate")
    histogram = _byte_histogram(candidate)
    if type(histogram) is not tuple or len(histogram) != 256:
        raise RuntimeError("invalid entropy histogram")
    positive_bins = 0
    total = 0
    for count in histogram:
        if type(count) is not int or count < 0:
            raise RuntimeError("invalid entropy histogram")
        if count:
            positive_bins += 1
            total += count
    if positive_bins > 256 or total != length:
        raise RuntimeError("invalid entropy histogram")
    if length == 0:
        return None

    left = pow(length, denominator * length)
    right = 1 << (numerator * length)
    for count in histogram:
        if count:
            right *= pow(count, denominator * count)
    return left, right


def _entropy_meets_threshold(candidate: bytes, family: str) -> bool:
    operands = _entropy_integer_operands(candidate, family)
    return operands is not None and operands[0] >= operands[1]


def _has_digit_bearing_evidence(candidate: bytes) -> bool:
    has_lower = any(0x61 <= byte <= 0x7A for byte in candidate)
    has_upper = any(0x41 <= byte <= 0x5A for byte in candidate)
    has_digit = any(0x30 <= byte <= 0x39 for byte in candidate)
    has_non_alphanumeric = any(
        not (0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A)
        for byte in candidate
    )
    return (
        has_digit
        and (has_lower or has_upper)
        and (
            has_lower
            and has_upper
            or has_non_alphanumeric
            or len(candidate) >= 20
            and _entropy_meets_threshold(candidate, ENTROPY_FAMILY_DIGIT_BEARING)
        )
    )


def _has_digit_free_opaque_evidence(candidate: bytes) -> bool:
    return (
        not any(0x30 <= byte <= 0x39 for byte in candidate)
        and len(candidate) >= 24
        and any(0x61 <= byte <= 0x7A for byte in candidate)
        and any(0x41 <= byte <= 0x5A for byte in candidate)
        and all(
            0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A or byte in b"+/_-="
            for byte in candidate
        )
        and _entropy_meets_threshold(candidate, ENTROPY_FAMILY_DIGIT_FREE_OPAQUE)
    )


def _has_lower_case_passphrase_evidence(candidate: bytes) -> bool:
    return (
        len(candidate) >= 20
        and LOWER_CASE_PASSPHRASE.fullmatch(candidate) is not None
        and not CREDENTIAL_VOCABULARY.intersection(candidate.split(b"-"))
        and _entropy_meets_threshold(
            candidate,
            ENTROPY_FAMILY_LOWER_CASE_PASSPHRASE,
        )
    )


def _has_high_confidence_generic_evidence(candidate: bytes) -> bool:
    if len(set(candidate)) < 6:
        return False
    return (
        _has_digit_bearing_evidence(candidate)
        or _has_digit_free_opaque_evidence(candidate)
        or _has_lower_case_passphrase_evidence(candidate)
    )


def _decoded_single_ascii_literal(candidate: bytes) -> bytes | None:
    try:
        source = candidate.decode("ascii")
        tokens = [
            token
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type not in {tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
        ]
        if (
            len(tokens) != 1
            or tokens[0].type != tokenize.STRING
            or tokens[0].start != (1, 0)
            or tokens[0].end != (1, len(source))
        ):
            return None
        decoded = ast.literal_eval(source)
        if isinstance(decoded, str):
            return decoded.encode("ascii")
        if isinstance(decoded, bytes):
            decoded.decode("ascii")
            return decoded
    except ASCII_LITERAL_ERRORS:
        return None
    return None


def _is_explicit_not_real_fixture(candidate: bytes) -> bool:
    if (
        EXPLICIT_NOT_REAL_FIXTURE.fullmatch(candidate) is not None
        or KIND_FIRST_NOT_REAL_FIXTURE.fullmatch(candidate) is not None
    ):
        return True
    decoded = _decoded_single_ascii_literal(candidate)
    return decoded is not None and (
        EXPLICIT_NOT_REAL_FIXTURE.fullmatch(decoded) is not None
        or KIND_FIRST_NOT_REAL_FIXTURE.fullmatch(decoded) is not None
    )


def _raw_string_constant_payload(source: str, node: ast.Constant) -> bytes | None:
    segment = ast.get_source_segment(source, node)
    if segment is None:
        return None
    try:
        tokens = [
            token
            for token in tokenize.generate_tokens(io.StringIO(segment).readline)
            if token.type not in {tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
        ]
    except TOKENIZED_LITERAL_ERRORS:
        return None
    if len(tokens) != 1 or tokens[0].type != tokenize.STRING:
        return None
    literal = tokens[0].string
    quote_index = min(
        (index for index in (literal.find("'"), literal.find('"')) if index >= 0),
        default=-1,
    )
    if quote_index < 0:
        return None
    quote = literal[quote_index]
    delimiter = (
        quote * 3 if literal[quote_index : quote_index + 3] == quote * 3 else quote
    )
    if not literal.endswith(delimiter):
        return None
    payload = literal[quote_index + len(delimiter) : -len(delimiter)]
    return payload.encode("utf-8")


def _constant_has_allowed_context(
    node: ast.Constant,
    parents: dict[int, ast.AST],
) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Call):
        return node in parent.args
    if isinstance(parent, ast.keyword):
        grandparent = parents.get(id(parent))
        return (
            parent.arg is not None
            and parent.value is node
            and isinstance(grandparent, ast.Call)
        )
    if isinstance(parent, ast.Subscript):
        return parent.slice is node
    if isinstance(parent, ast.Slice):
        grandparent = parents.get(id(parent))
        return node in {parent.lower, parent.upper, parent.step} and isinstance(
            grandparent, ast.Subscript
        )
    return False


def _closed_source_expression_is_safe(
    source: str,
    expression: ast.Expression,
    *,
    rhs_literal_tokens: int | None = None,
) -> bool:
    if not isinstance(
        expression.body, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)
    ):
        return False
    allowed_nodes = (
        ast.Expression,
        ast.Name,
        ast.Load,
        ast.Attribute,
        ast.Call,
        ast.Subscript,
        ast.Constant,
        ast.keyword,
        ast.Slice,
    )
    enforce_rhs_limits = rhs_literal_tokens is not None
    if enforce_rhs_limits and rhs_literal_tokens > MAX_RHS_LITERAL_TOKENS:
        return False

    nodes: list[ast.AST] = []
    parents: dict[int, ast.AST] = {}
    stack: list[tuple[ast.AST, ast.AST | None, int]] = [(expression, None, 0)]
    while stack:
        node, parent, depth = stack.pop()
        nodes.append(node)
        if parent is not None:
            parents[id(node)] = parent
        if enforce_rhs_limits and (
            len(nodes) > MAX_RHS_AST_NODES or depth > MAX_RHS_AST_DEPTH
        ):
            return False
        children = tuple(ast.iter_child_nodes(node))
        stack.extend((child, node, depth + 1) for child in reversed(children))

    if any(not isinstance(node, allowed_nodes) for node in nodes):
        return False
    aggregate_literal_bytes = 0
    for node in nodes:
        if isinstance(node, ast.keyword) and node.arg is None:
            return False
        if not isinstance(node, ast.Constant):
            continue
        if not _constant_has_allowed_context(node, parents):
            return False
        if isinstance(node.value, (str, bytes)):
            if enforce_rhs_limits:
                if isinstance(node.value, bytes):
                    decoded_size = len(node.value)
                    if decoded_size > MAX_RHS_DECODED_BYTES_LITERAL:
                        return False
                else:
                    if len(node.value) > MAX_RHS_DECODED_STR_CODE_POINTS:
                        return False
                    try:
                        decoded_size = len(node.value.encode("utf-8"))
                    except UnicodeError:
                        return False
                    if decoded_size > MAX_RHS_DECODED_STR_UTF8_BYTES:
                        return False
                aggregate_literal_bytes += decoded_size
                if aggregate_literal_bytes > MAX_RHS_AGGREGATE_LITERAL_BYTES:
                    return False
            payload = _raw_string_constant_payload(source, node)
            if (
                payload is None
                or len(payload) > MAX_GENERIC_CANDIDATE_BYTES
                or _has_high_confidence_generic_evidence(payload)
            ):
                return False
    return True


def _is_safe_bare_source_expression(candidate: bytes) -> bool:
    if candidate in SAFE_BARE_SOURCE_EXPRESSIONS:
        return True
    try:
        source = candidate.decode("utf-8")
        expression = ast.parse(source, mode="eval")
    except SOURCE_EXPRESSION_ERRORS:
        return False
    return _closed_source_expression_is_safe(source, expression)


def _rhs_literal_token_count(source: str) -> int | None:
    try:
        tokens = tuple(tokenize.generate_tokens(io.StringIO(source).readline))
    except RHS_TOKEN_ERRORS:
        return None
    ignored_types = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    substantive_tokens = 0
    literal_tokens = 0
    for token in tokens:
        if token.type == tokenize.COMMENT:
            return None
        if token.type == tokenize.ERRORTOKEN:
            return None
        if token.type == tokenize.OP and token.string == ";":
            return None
        if token.type == tokenize.STRING:
            literal_tokens += 1
        if token.type not in ignored_types:
            substantive_tokens += 1
    if (
        substantive_tokens == 0
        or substantive_tokens > MAX_RHS_SUBSTANTIVE_TOKENS
        or literal_tokens > MAX_RHS_LITERAL_TOKENS
    ):
        return None
    return literal_tokens


def _rhs_reconstruction_is_safe(
    data: bytes,
    value_span: tuple[int, int],
    candidate: bytes,
) -> bool:
    start, end = value_span
    if (
        type(data) is not bytes
        or type(candidate) is not bytes
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or end < start
        or end > len(data)
        or data[start:end] != candidate
    ):
        raise RuntimeError("invalid RHS reconstruction input")
    if (
        not candidate
        or not candidate.isascii()
        or not _has_digit_bearing_evidence(candidate)
    ):
        return False

    candidate_source = candidate.decode("ascii")
    try:
        ast.parse(
            candidate_source,
            mode="eval",
            feature_version=(3, 10),
        )
    except SyntaxError:
        pass
    except Exception:
        return False
    else:
        return False

    line_start = data.rfind(b"\n", 0, start) + 1
    line_feed = data.find(b"\n", start)
    content_end = len(data) if line_feed < 0 else line_feed
    if line_feed >= 0 and content_end > line_start and data[content_end - 1] == 0x0D:
        content_end -= 1
    if start < line_start or end > content_end:
        return False
    physical_line = data[line_start:content_end]
    if len(physical_line) > MAX_RHS_PHYSICAL_LINE_BYTES:
        return False
    if any(byte != 0x09 and not 0x20 <= byte <= 0x7E for byte in physical_line):
        return False
    if end >= content_end:
        return False

    rhs = data[start:content_end]
    if (
        len(rhs) > MAX_RHS_EXPRESSION_BYTES
        or not rhs.startswith(candidate)
        or rhs[: len(candidate)] != candidate
        or rhs[0] in b" \t"
        or rhs[-1] in b" \t"
    ):
        return False
    source = rhs.decode("ascii")
    literal_tokens = _rhs_literal_token_count(source)
    if literal_tokens is None:
        return False
    try:
        expression = ast.parse(
            source,
            mode="eval",
            feature_version=(3, 10),
        )
    except SyntaxError:
        return False
    return _closed_source_expression_is_safe(
        source,
        expression,
        rhs_literal_tokens=literal_tokens,
    )


def _is_symbolic_reference(candidate: bytes) -> bool:
    if SYMBOLIC_REFERENCE.fullmatch(candidate) is None:
        return False
    words = re.split(rb"[-_]", candidate)
    return bool(CREDENTIAL_VOCABULARY.intersection(words))


def _looks_like_real_generic_credential(value: bytes, *, kind: str) -> bool:
    candidate = value
    if GENERIC_PLACEHOLDER.fullmatch(candidate.lower()) is not None:
        return False
    if candidate.lower() in GENERIC_SENTINELS:
        return False
    if _is_explicit_not_real_fixture(candidate):
        return False
    if EXTERNAL_REFERENCE.fullmatch(candidate) is not None:
        return False
    if kind == "bare" and _is_safe_bare_source_expression(candidate):
        return False
    if kind == "bare" and _is_symbolic_reference(candidate):
        return False
    return _has_high_confidence_generic_evidence(candidate)


def scan_bytes(data: bytes, source: str) -> set[Finding]:
    """Return sanitized findings from one non-archive byte sequence."""

    findings: set[Finding] = set()
    specific_spans: list[tuple[int, int]] = []
    for rule_id, pattern in SPECIFIC_RULES:
        for match in pattern.finditer(data):
            specific_spans.append(match.span())
            findings.add(
                Finding(
                    source=source,
                    line=_line_number(data, match.start()),
                    rule_id=rule_id,
                )
            )

    for match in GENERIC_ASSIGNMENT.finditer(data):
        value_kind, value, value_span = _generic_value(match)
        if any(_overlaps(value_span, span) for span in specific_spans):
            continue
        if not _looks_like_real_generic_credential(value, kind=value_kind):
            continue
        if value_kind == "bare" and _rhs_reconstruction_is_safe(
            data,
            value_span,
            value,
        ):
            continue
        findings.add(
            Finding(
                source=source,
                line=_line_number(data, match.start()),
                rule_id=RULE_GENERIC_CREDENTIAL,
            )
        )
    return findings


def _archive_candidate(data: bytes, path_hint: str) -> bool:
    return data.startswith(ZIP_SIGNATURES) or path_hint.casefold().endswith(
        ZIP_SUFFIXES
    )


def _validated_archive_member(
    info: zipfile.ZipInfo,
    source: str,
) -> PurePosixPath | None:
    original = info.orig_filename
    if "\x00" in original or "\\" in original:
        raise ScanError("unsafe-archive-member", source)
    raw_parts = original.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts[:-1]):
        raise ScanError("unsafe-archive-member", source)

    member = PurePosixPath(original)
    if member.is_absolute() or ".." in member.parts:
        raise ScanError("unsafe-archive-member", source)
    if member.parts and member.parts[0].endswith(":"):
        raise ScanError("unsafe-archive-member", source)
    if not member.parts:
        raise ScanError("unsafe-archive-member", source)

    if info.flag_bits & (0x1 | 0x40):
        raise ScanError("encrypted-archive-member", source)

    if info.create_system == 3:
        file_type = stat.S_IFMT(info.external_attr >> 16)
        allowed_type = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
        if file_type not in {0, allowed_type}:
            raise ScanError("unsafe-archive-member-type", source)

    if info.is_dir():
        return None
    if original.endswith("/"):
        raise ScanError("unsafe-archive-member", source)
    return member


def _read_archive_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    source: str,
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        with archive.open(info, "r") as stream:
            while chunk := stream.read(READ_CHUNK_BYTES):
                size += len(chunk)
                if size > info.file_size or size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ScanError("archive-member-expanded-too-large", source)
                chunks.append(chunk)
    except ScanError:
        raise
    except ARCHIVE_READ_ERRORS:
        raise ScanError("unreadable-archive-member", source) from None
    if size != info.file_size:
        raise ScanError("archive-member-size-mismatch", source)
    return b"".join(chunks)


def scan_archive(
    data: bytes,
    source: str,
    *,
    depth: int,
    budget: ArchiveBudget,
) -> set[Finding]:
    """Scan a ZIP and nested ZIPs while enforcing one shared expansion budget."""

    if depth > MAX_ARCHIVE_DEPTH:
        raise ScanError("archive-nesting-too-deep", source)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except ARCHIVE_READ_ERRORS:
        raise ScanError("invalid-archive", source) from None

    findings: set[Finding] = set()
    seen_paths: set[str] = set()
    normalized_paths: set[str] = set()
    try:
        with archive:
            validated: list[tuple[PurePosixPath, zipfile.ZipInfo]] = []
            for info in archive.infolist():
                member = _validated_archive_member(info, source)
                if member is None:
                    continue
                member_name = member.as_posix()
                normalized = unicodedata.normalize("NFC", member_name).casefold()
                if member_name in seen_paths or normalized in normalized_paths:
                    raise ScanError("duplicate-archive-member", source)
                seen_paths.add(member_name)
                normalized_paths.add(normalized)

                budget.members += 1
                budget.expanded_bytes += info.file_size
                if budget.members > MAX_ARCHIVE_MEMBERS:
                    raise ScanError("archive-member-limit", source)
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ScanError("archive-member-too-large", source)
                if budget.expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
                    raise ScanError("archive-expansion-limit", source)
                if (
                    info.file_size >= COMPRESSION_RATIO_MINIMUM_BYTES
                    and info.file_size / max(info.compress_size, 1)
                    > MAX_COMPRESSION_RATIO
                ):
                    raise ScanError("archive-compression-ratio", source)
                validated.append((member, info))

            for member, info in sorted(
                validated,
                key=lambda item: item[0].as_posix().encode("utf-8", "surrogatepass"),
            ):
                member_source = f"{source}!{member.as_posix()}"
                member_data = _read_archive_member(archive, info, member_source)
                if _archive_candidate(member_data, member.as_posix()):
                    if depth >= MAX_ARCHIVE_DEPTH:
                        raise ScanError("archive-nesting-too-deep", member_source)
                    findings.update(
                        scan_archive(
                            member_data,
                            member_source,
                            depth=depth + 1,
                            budget=budget,
                        )
                    )
                else:
                    findings.update(scan_bytes(member_data, member_source))
    except ScanError:
        raise
    except ARCHIVE_READ_ERRORS:
        raise ScanError("invalid-archive", source) from None
    return findings


def scan_payload(data: bytes, source: str, path_hint: str) -> set[Finding]:
    if _archive_candidate(data, path_hint):
        return scan_archive(data, source, depth=1, budget=ArchiveBudget())
    return scan_bytes(data, source)


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _validated_relative_parts(relative: str, source: str) -> tuple[str, ...]:
    if not relative or relative.startswith("/") or "\x00" in relative:
        raise ScanError("unsafe-worktree-path", source)
    parts = tuple(relative.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ScanError("unsafe-worktree-path", source)
    return parts


def read_maintained_file(root: Path, relative: str) -> bytes:
    """Read a regular file descriptor-relatively without following symlinks."""

    source = relative
    parts = _validated_relative_parts(relative, source)
    descriptors: list[int] = []
    try:
        root_fd = os.open(os.fspath(root), _directory_open_flags())
        descriptors.append(root_fd)
        parent_fd = root_fd
        for part in parts[:-1]:
            next_fd = os.open(part, _directory_open_flags(), dir_fd=parent_fd)
            descriptors.append(next_fd)
            parent_fd = next_fd
        file_fd = os.open(parts[-1], _file_open_flags(), dir_fd=parent_fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ScanError("unsafe-worktree-file-type", source)
        if before.st_size < 0 or before.st_size > MAX_INPUT_BYTES:
            raise ScanError("worktree-file-too-large", source)

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(file_fd, READ_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_INPUT_BYTES:
                raise ScanError("worktree-file-too-large", source)
            chunks.append(chunk)
        after = os.fstat(file_fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after or size != before.st_size:
            raise ScanError("worktree-file-changed", source)
        return b"".join(chunks)
    except ScanError:
        raise
    except OSError:
        raise ScanError("unreadable-worktree-input", source) from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _is_fallback_excluded(parts: tuple[str, ...], is_directory: bool) -> bool:
    name = parts[-1]
    if is_directory:
        if name in EXCLUDED_DIRECTORY_NAMES:
            return True
        if name.startswith(".node-offline-check."):
            return True
        return False

    if name in EXCLUDED_FILE_NAMES:
        return True
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if name.endswith((".log", ".pyc", ".swp", ".tmp", "~")):
        return True
    return parts == (".claude", "settings.local.json")


def _walk_fallback_directory(
    directory_fd: int,
    parts: tuple[str, ...],
    files: list[str],
) -> None:
    try:
        with os.scandir(directory_fd) as iterator:
            entries = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
    except OSError:
        source = "/".join(parts) or "."
        raise ScanError("unreadable-worktree-directory", source) from None

    for entry in entries:
        child_parts = (*parts, entry.name)
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError:
            raise ScanError(
                "unreadable-worktree-input", "/".join(child_parts)
            ) from None
        mode = metadata.st_mode
        is_directory = stat.S_ISDIR(mode)
        if _is_fallback_excluded(child_parts, is_directory):
            continue
        if stat.S_ISLNK(mode):
            raise ScanError("unsafe-worktree-symlink", "/".join(child_parts))
        if is_directory:
            try:
                child_fd = os.open(
                    entry.name,
                    _directory_open_flags(),
                    dir_fd=directory_fd,
                )
            except OSError:
                raise ScanError(
                    "unreadable-worktree-directory", "/".join(child_parts)
                ) from None
            try:
                _walk_fallback_directory(child_fd, child_parts, files)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(mode):
            files.append("/".join(child_parts))
        else:
            raise ScanError("unsafe-worktree-file-type", "/".join(child_parts))


def fallback_worktree_files(root: Path) -> list[str]:
    descriptors: list[int] = []
    try:
        root_fd = os.open(os.fspath(root), _directory_open_flags())
        descriptors.append(root_fd)
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ScanError("invalid-repository-root", ".")
        files: list[str] = []
        _walk_fallback_directory(root_fd, (), files)
        return sorted(set(files), key=os.fsencode)
    except ScanError:
        raise
    except OSError:
        raise ScanError("invalid-repository-root", ".") from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _git_executable() -> str | None:
    for candidate in ("/usr/bin/git", "/bin/git"):
        try:
            metadata = os.stat(candidate, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(metadata.st_mode) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _git_environment() -> dict[str, str]:
    return {
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
    }


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    executable = _git_executable()
    if executable is None:
        raise ScanError("git-unavailable", ".")
    try:
        return subprocess.run(
            [executable, "-c", "core.quotePath=true", *arguments],
            cwd=root,
            env=_git_environment(),
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except GIT_EXECUTION_ERRORS:
        raise ScanError("git-command-failed", ".") from None


def _empty_git_marker(root: Path) -> bool:
    marker = root / ".git"
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not stat.S_ISDIR(metadata.st_mode):
        return False
    try:
        return next(marker.iterdir(), None) is None
    except OSError:
        return False


def git_repository_available(root: Path) -> bool:
    executable = _git_executable()
    if executable is None:
        if _empty_git_marker(root):
            return False
        raise ScanError("git-unavailable", ".")
    marker = root / ".git"
    try:
        marker_metadata = marker.lstat()
    except FileNotFoundError:
        marker_metadata = None
    except OSError:
        raise ScanError("unsafe-git-metadata", ".") from None
    if marker_metadata is not None and not stat.S_ISDIR(marker_metadata.st_mode):
        raise ScanError("unsafe-git-metadata", ".")
    result = _run_git(root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        if _empty_git_marker(root):
            return False
        raise ScanError("invalid-git-repository", ".")
    try:
        reported = Path(os.fsdecode(result.stdout.strip()))
        if not reported.is_absolute() or not os.path.samefile(root, reported):
            raise ScanError("git-root-mismatch", ".")
    except OSError:
        raise ScanError("git-root-mismatch", ".") from None
    return True


def git_worktree_files(root: Path) -> list[str]:
    result = _run_git(
        root,
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"],
    )
    if result.returncode != 0 or not result.stdout.endswith(b"\x00") and result.stdout:
        raise ScanError("git-worktree-enumeration-failed", ".")
    paths: set[str] = set()
    for raw_path in result.stdout.split(b"\x00"):
        if not raw_path:
            continue
        if raw_path.startswith(b"/") or b"\x00" in raw_path:
            raise ScanError("unsafe-git-path", ".")
        raw_parts = raw_path.split(b"/")
        if any(part in {b"", b".", b".."} for part in raw_parts):
            raise ScanError("unsafe-git-path", ".")
        relative = os.fsdecode(raw_path)
        _validated_relative_parts(relative, relative)
        paths.add(relative)
    return sorted(paths, key=os.fsencode)


def worktree_files(root: Path) -> list[str]:
    if git_repository_available(root):
        return git_worktree_files(root)
    return fallback_worktree_files(root)


def scan_worktree(root: Path) -> set[Finding]:
    findings: set[Finding] = set()
    for relative in worktree_files(root):
        data = read_maintained_file(root, relative)
        findings.update(scan_payload(data, relative, relative))
    return findings


def _require_complete_git_repository(root: Path) -> None:
    if not git_repository_available(root):
        raise ScanError("git-history-requires-repository", ".")
    shallow = _run_git(root, ["rev-parse", "--is-shallow-repository"])
    if shallow.returncode != 0 or shallow.stdout.strip() not in {b"true", b"false"}:
        raise ScanError("git-shallow-check-failed", ".")
    if shallow.stdout.strip() != b"false":
        raise ScanError("shallow-git-history", ".")


def git_blob_inventory(root: Path) -> list[tuple[bytes, int]]:
    """Enumerate every blob physically available from the local object database."""

    result = _run_git(
        root,
        [
            "cat-file",
            "--batch-all-objects",
            "--unordered",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ],
    )
    if result.returncode != 0:
        raise ScanError("git-object-enumeration-failed", ".")

    blobs: dict[bytes, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split(b" ")
        if len(fields) != 3 or HEX_OBJECT_ID.fullmatch(fields[0]) is None:
            raise ScanError("invalid-git-object-metadata", ".")
        object_id, object_type, raw_size = fields
        try:
            object_size = int(raw_size)
        except ValueError:
            raise ScanError("invalid-git-object-metadata", ".") from None
        if object_size < 0:
            raise ScanError("invalid-git-object-metadata", ".")
        if object_type != b"blob":
            continue
        if object_size > MAX_INPUT_BYTES:
            raise ScanError(
                "git-blob-too-large", f"git-blob:{object_id.decode('ascii')}"
            )
        previous = blobs.setdefault(object_id, object_size)
        if previous != object_size:
            raise ScanError("invalid-git-object-metadata", ".")
    return sorted(blobs.items())


def _read_exact(stream: object, size: int, source: str) -> bytes:
    reader = getattr(stream, "read")
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = reader(min(remaining, READ_CHUNK_BYTES))
        if not chunk:
            raise ScanError("truncated-git-object", source)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def scan_git_history(root: Path) -> set[Finding]:
    _require_complete_git_repository(root)
    inventory = git_blob_inventory(root)
    if not inventory:
        return set()

    executable = _git_executable()
    if executable is None:
        raise ScanError("git-unavailable", ".")
    try:
        process = subprocess.Popen(
            [executable, "cat-file", "--batch"],
            cwd=root,
            env=_git_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise ScanError("git-object-reader-failed", ".") from None

    findings: set[Finding] = set()
    try:
        if process.stdin is None or process.stdout is None:
            raise ScanError("git-object-reader-failed", ".")
        for object_id, expected_size in inventory:
            source = f"git-blob:{object_id.decode('ascii')}"
            try:
                process.stdin.write(object_id + b"\n")
                process.stdin.flush()
                header = process.stdout.readline()
            except OSError:
                raise ScanError("git-object-reader-failed", source) from None
            fields = header.rstrip(b"\n").split(b" ")
            if len(fields) != 3 or fields[0] != object_id or fields[1] != b"blob":
                raise ScanError("invalid-git-object-response", source)
            try:
                actual_size = int(fields[2])
            except ValueError:
                raise ScanError("invalid-git-object-response", source) from None
            if actual_size != expected_size:
                raise ScanError("invalid-git-object-response", source)
            data = _read_exact(process.stdout, actual_size, source)
            if process.stdout.read(1) != b"\n":
                raise ScanError("invalid-git-object-response", source)
            findings.update(scan_payload(data, source, source))

        process.stdin.close()
        try:
            return_code = process.wait(timeout=GIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise ScanError("git-object-reader-timeout", ".") from None
        if return_code != 0:
            raise ScanError("git-object-reader-failed", ".")
    except ScanError:
        process.kill()
        process.wait()
        raise
    finally:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
    return findings


def _render_source(source: str) -> str:
    return json.dumps(source, ensure_ascii=True)


def emit_findings(findings: set[Finding]) -> None:
    for finding in sorted(findings):
        print(
            f"FINDING rule={finding.rule_id} "
            f"source={_render_source(finding.source)} line={finding.line}"
        )


def emit_error(error: ScanError) -> None:
    print(
        f"ERROR code={error.code} source={_render_source(error.source)}",
        file=sys.stderr,
    )


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan maintained worktree files and fetched Git history."
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="scan tracked and nonignored untracked maintained files",
    )
    parser.add_argument(
        "--git-history",
        action="store_true",
        help="scan every blob in a complete, non-shallow local Git object database",
    )
    arguments = parser.parse_args(argv)
    if not arguments.worktree and not arguments.git_history:
        parser.error("at least one of --worktree or --git-history is required")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    findings: set[Finding] = set()
    try:
        if arguments.worktree:
            findings.update(scan_worktree(REPOSITORY_ROOT))
        if arguments.git_history:
            findings.update(scan_git_history(REPOSITORY_ROOT))
    except ScanError as error:
        emit_error(error)
        return EXIT_OPERATIONAL_ERROR
    except Exception:
        emit_error(ScanError("internal-scanner-error", "."))
        return EXIT_OPERATIONAL_ERROR

    emit_findings(findings)
    return EXIT_FINDINGS if findings else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
