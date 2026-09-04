#!/usr/bin/env python3
"""Validate that CI dependency hydration is constrained to reviewed sources.

This command deliberately uses only the Python 3.10 standard library.  It runs
before the managed Python and Node dependency trees exist, so it must not rely
on either tree.  Successful output contains only fixed labels and aggregate
counts; untrusted manifest or lockfile values are never rendered.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit


PYTHON_VERSION = "3.14.6"
UV_LOCK_VERSION = 1
UV_LOCK_REVISION = 3
PYPI_INDEX = "https://pypi.org/simple"
PYTHON_ARCHIVE_HOST = "files.pythonhosted.org"
NPM_REGISTRY = "https://registry.npmjs.org/"
EXCLUDE_NEWER = "2026-08-01T16:50:16Z"
EXCLUDE_NEWER_TIMESTAMP = datetime.fromisoformat(
    EXCLUDE_NEWER.removesuffix("Z") + "+00:00"
)

ROOT_CONTRACT_FILES = (
    ".python-version",
    "pyproject.toml",
    "uv.toml",
    "uv.lock",
    ".npmrc",
    "package.json",
    "package-lock.json",
)
MAX_CONTRACT_BYTES = {
    ".python-version": 128,
    "pyproject.toml": 1_000_000,
    "uv.toml": 1_000_000,
    "uv.lock": 64_000_000,
    ".npmrc": 64_000,
    "package.json": 4_000_000,
    "package-lock.json": 64_000_000,
}

EXPECTED_UV_CONFIG: dict[str, Any] = {
    "required-version": ">=0.12.1,<0.13",
    "no-sources": True,
    "python-downloads": "manual",
    "python-preference": "only-managed",
    "prerelease": "disallow",
    "resolution": "highest",
    "exclude-newer": EXCLUDE_NEWER,
    "index-strategy": "first-index",
    "keyring-provider": "disabled",
    "link-mode": "copy",
    "index": [
        {
            "name": "pypi",
            "url": PYPI_INDEX,
            "default": True,
        }
    ],
}

EXPECTED_NPM_CONFIG = {
    "audit": "false",
    "cache": ".npm-cache",
    "engine-strict": "true",
    "fund": "false",
    "ignore-scripts": "true",
    "install-links": "true",
    "legacy-peer-deps": "false",
    "omit-lockfile-registry-resolved": "false",
    "package-lock": "true",
    "prefer-dedupe": "true",
    "registry": NPM_REGISTRY,
    "save-exact": "true",
    "strict-peer-deps": "true",
    "update-notifier": "false",
}
EXPECTED_NPM_OVERRIDES: dict[str, Any] = {
    "next@16.2.12": {
        "postcss": "8.5.25",
        "sharp": "0.35.3",
    },
    "vite": "8.2.0",
}
NPM_GLOBAL_OVERRIDE_SPECS = {
    "vite": "8.2.0",
}
NPM_PARENT_OVERRIDE_SPECS = {
    ("next", "16.2.12", "postcss"): "8.5.25",
    ("next", "16.2.12", "sharp"): "0.35.3",
}
NPM_REVIEWED_LOCK_PARTIAL_SPECS = {
    (
        "@paulirish/trace_engine",
        "0.0.59",
        "legacy-javascript",
        "latest",
    ): "0.0.1",
    (
        "@paulirish/trace_engine",
        "0.0.59",
        "third-party-web",
        "latest",
    ): "0.27.0",
    (
        "@sentry/node-core",
        "9.47.1",
        "@opentelemetry/instrumentation",
        ">=0.57.1 <1",
    ): ">=0.57.1 <1.0.0",
    ("express-rate-limit", "8.6.2", "express", ">= 4.11"): ">=4.11.0",
    ("https-proxy-agent", "7.0.6", "debug", "4"): ">=4.0.0 <5.0.0",
    (
        "iconv-lite",
        "0.4.24",
        "safer-buffer",
        ">= 2.1.2 < 3",
    ): ">=2.1.2 <3.0.0",
    ("once", "1.4.0", "wrappy", "1"): ">=1.0.0 <2.0.0",
}

NPM_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
LOCK_DEPENDENCY_SECTIONS = (
    "dependencies",
    "optionalDependencies",
    "peerDependencies",
)

BARE_TOML_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
CANONICAL_PYTHON_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PYTHON_PIN = re.compile(
    r"^(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"(?:\[(?P<extras>[a-z0-9]+(?:-[a-z0-9]+)*"
    r"(?:,[a-z0-9]+(?:-[a-z0-9]+)*)*)\])?=="
    r"(?P<version>[0-9]+(?:\.[0-9]+)+"
    r"(?:[A-Za-z][0-9A-Za-z.-]*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)$"
)
REVIEWED_PYTHON_EXTRAS = {"psycopg": ("binary",)}
PYTHON_VERSION_VALUE = re.compile(
    r"^[0-9]+(?:\.[0-9]+)+(?:[A-Za-z][0-9A-Za-z.-]*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
NPM_PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")
NPM_EXACT_VERSION = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
NPM_RANGE_NUMBER = r"(?:0|[1-9][0-9]*)"
NPM_RANGE_PRERELEASE = r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
NPM_RANGE_BUILD = r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
NPM_RANGE_VERSION = (
    rf"(?:{NPM_RANGE_NUMBER}\.{NPM_RANGE_NUMBER}\.{NPM_RANGE_NUMBER}"
    rf"{NPM_RANGE_PRERELEASE}{NPM_RANGE_BUILD}|"
    rf"{NPM_RANGE_NUMBER}(?:\.{NPM_RANGE_NUMBER})?|"
    rf"{NPM_RANGE_NUMBER}\.[xX*](?:\.[xX*])?|[xX*])"
)
NPM_RANGE_COMPARATOR = (
    rf"(?:(?:[~^=]|[<>]=?)[ ]?{NPM_RANGE_VERSION}|{NPM_RANGE_VERSION})"
)
NPM_LOCK_SEMVER_RANGE = re.compile(
    rf"^{NPM_RANGE_COMPARATOR}(?:[ ]{NPM_RANGE_COMPARATOR})*"
    rf"(?:[ ]\|\|[ ]{NPM_RANGE_COMPARATOR}(?:[ ]{NPM_RANGE_COMPARATOR})*)*$"
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
SAFE_WORKSPACE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LOCK_PACKAGE_PATH = re.compile(
    r"^node_modules/(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+"
    r"(?:/node_modules/(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+)*$"
)
NPM_MAX_SAFE_INTEGER = 9_007_199_254_740_991
NpmSemVer = tuple[int, int, int, tuple[str, ...]]
NpmConstraint = tuple[str, NpmSemVer]
NpmRangeAtom = tuple[str, tuple[int, ...], tuple[str, ...]]


def _parse_npm_core_number(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed > NPM_MAX_SAFE_INTEGER:
        return None
    return parsed


def _split_npm_version_text(value: str) -> tuple[str, tuple[str, ...]] | None:
    without_build, separator, build = value.partition("+")
    if separator and (not build or any(not part for part in build.split("."))):
        return None
    core, separator, prerelease_text = without_build.partition("-")
    if not separator:
        return core, ()
    prerelease = tuple(prerelease_text.split("."))
    if not prerelease or any(
        not part or (part.isdigit() and len(part) > 1 and part.startswith("0"))
        for part in prerelease
    ):
        return None
    return core, prerelease


def _parse_exact_npm_semver(value: str) -> NpmSemVer | None:
    split = _split_npm_version_text(value)
    if split is None:
        return None
    core, prerelease = split
    components = core.split(".")
    if len(components) != 3:
        return None
    numbers = tuple(_parse_npm_core_number(component) for component in components)
    if any(number is None for number in numbers):
        return None
    return cast(NpmSemVer, (numbers[0], numbers[1], numbers[2], prerelease))


def _parse_npm_range_version(
    value: str,
) -> tuple[tuple[int, ...], tuple[str, ...]] | None:
    split = _split_npm_version_text(value)
    if split is None:
        return None
    core, prerelease = split
    components = core.split(".")
    numbers: list[int] = []
    for component in components:
        if component in {"x", "X", "*"}:
            break
        parsed = _parse_npm_core_number(component)
        if parsed is None:
            return None
        numbers.append(parsed)
    if prerelease and len(numbers) != 3:
        return None
    return tuple(numbers), prerelease


def _compare_prerelease(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            left_key = (len(left_part), left_part)
            right_key = (len(right_part), right_part)
            return -1 if left_key < right_key else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_part < right_part else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


def _compare_npm_semver(left: NpmSemVer, right: NpmSemVer) -> int:
    left_core = left[:3]
    right_core = right[:3]
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    return _compare_prerelease(left[3], right[3])


def _npm_upper_bound(numbers: tuple[int, ...], mode: str) -> NpmSemVer | None:
    if not numbers:
        return None
    major = numbers[0]
    minor = numbers[1] if len(numbers) > 1 else 0
    patch = numbers[2] if len(numbers) > 2 else 0
    if mode == "tilde":
        if len(numbers) == 1:
            if major == NPM_MAX_SAFE_INTEGER:
                return None
            return major + 1, 0, 0, ("0",)
        if minor == NPM_MAX_SAFE_INTEGER:
            return None
        return major, minor + 1, 0, ("0",)
    if mode == "caret":
        if major or len(numbers) == 1:
            if major == NPM_MAX_SAFE_INTEGER:
                return None
            return major + 1, 0, 0, ("0",)
        if minor or len(numbers) == 2:
            if minor == NPM_MAX_SAFE_INTEGER:
                return None
            return 0, minor + 1, 0, ("0",)
        if patch == NPM_MAX_SAFE_INTEGER:
            return None
        return 0, 0, patch + 1, ("0",)
    if len(numbers) == 1:
        if major == NPM_MAX_SAFE_INTEGER:
            return None
        return major + 1, 0, 0, ("0",)
    if minor == NPM_MAX_SAFE_INTEGER:
        return None
    return major, minor + 1, 0, ("0",)


def _expand_npm_comparator(
    operator: str, numbers: tuple[int, ...], prerelease: tuple[str, ...]
) -> list[NpmConstraint] | None:
    if not numbers:
        return []
    base: NpmSemVer = (
        numbers[0],
        numbers[1] if len(numbers) > 1 else 0,
        numbers[2] if len(numbers) > 2 else 0,
        prerelease,
    )
    if operator in {"", "="}:
        if len(numbers) == 3:
            return [("=", base)]
        upper = _npm_upper_bound(numbers, "partial")
        return [(">=", base), ("<", upper)] if upper is not None else None
    if operator == ">=":
        return [(operator, base)]
    if operator == ">":
        if len(numbers) == 3:
            return [(operator, base)]
        upper = _npm_upper_bound(numbers, "partial")
        if upper is None:
            return None
        return [(">=", (upper[0], upper[1], upper[2], ()))]
    if operator == "<=":
        if len(numbers) == 3:
            return [(operator, base)]
        upper = _npm_upper_bound(numbers, "partial")
        return [("<", upper)] if upper is not None else None
    if operator == "<":
        if len(numbers) == 3:
            return [(operator, base)]
        return [(operator, (base[0], base[1], base[2], ("0",)))]
    if operator in {"~", "^"}:
        upper = _npm_upper_bound(numbers, "tilde" if operator == "~" else "caret")
        return [(">=", base), ("<", upper)] if upper is not None else None
    return None


def _npm_constraint_matches(version: NpmSemVer, constraint: NpmConstraint) -> bool:
    operator, bound = constraint
    comparison = _compare_npm_semver(version, bound)
    return {
        "=": comparison == 0,
        ">": comparison > 0,
        ">=": comparison >= 0,
        "<": comparison < 0,
        "<=": comparison <= 0,
    }[operator]


def _parse_supported_npm_range(range_text: str) -> list[list[NpmRangeAtom]] | None:
    if not NPM_LOCK_SEMVER_RANGE.fullmatch(range_text):
        return None
    raw_sets = range_text.split(" || ")
    parsed_sets: list[list[NpmRangeAtom]] = []
    for raw_set in range_text.split(" || "):
        normalized = re.sub(r"([~^=]|[<>]=?)[ ]", r"\1", raw_set)
        tokens = normalized.split(" ")
        atoms: list[NpmRangeAtom] = []
        for token in normalized.split(" "):
            match = re.fullmatch(r"(?P<operator>[~^=]|[<>]=?)?(?P<version>.+)", token)
            if match is None:
                return None
            operator = match.group("operator") or ""
            version_token = match.group("version")
            parsed = _parse_npm_range_version(version_token)
            if parsed is None:
                return None
            numbers, prerelease = parsed
            version_core = version_token.split("+", 1)[0].split("-", 1)[0]
            has_wildcard = any(
                component in {"x", "X", "*"} for component in version_core.split(".")
            )
            if len(tokens) > 1:
                if len(raw_sets) > 1 or operator not in {">", ">=", "<", "<="}:
                    return None
                if len(numbers) != 3 or has_wildcard:
                    return None
            elif has_wildcard:
                if operator or prerelease:
                    return None
                if len(raw_sets) > 1 and not numbers:
                    return None
            elif len(numbers) < 3:
                # The reviewed lock uses major/minor caret ranges (for example
                # ^2 and ^9.7) but no bare, tilde, or comparator partials.
                if operator != "^" or len(numbers) not in {1, 2}:
                    return None
            elif operator not in {"", "=", "^", "~", ">", ">=", "<", "<="}:
                return None
            if (
                len(raw_sets) > 1
                and operator == ">="
                and numbers == (0, 0, 0)
                and not prerelease
            ):
                # node-semver normalizes this union branch to universal `*`,
                # which suppresses an otherwise explicit prerelease branch.
                return None
            atoms.append((operator, numbers, prerelease))
        parsed_sets.append(atoms)
    return parsed_sets


def _npm_version_satisfies_range(version_text: str, range_text: str) -> bool:
    version = _parse_exact_npm_semver(version_text)
    parsed_sets = _parse_supported_npm_range(range_text)
    if version is None or parsed_sets is None:
        return False
    for atoms in parsed_sets:
        constraints: list[NpmConstraint] = []
        prerelease_cores: set[tuple[int, int, int]] = set()
        for operator, numbers, prerelease in atoms:
            expanded = _expand_npm_comparator(operator, numbers, prerelease)
            if expanded is None:
                return False
            constraints.extend(expanded)
            if prerelease and len(numbers) == 3:
                prerelease_cores.add((numbers[0], numbers[1], numbers[2]))
        if not all(
            _npm_constraint_matches(version, constraint) for constraint in constraints
        ):
            continue
        if version[3] and version[:3] not in prerelease_cores:
            continue
        return True
    return False


class ValidationError(Exception):
    """A safe, fixed-code validation failure."""

    def __init__(self, code: str, source: str) -> None:
        super().__init__(code)
        self.code = code
        self.source = source


def reject(code: str, source: str) -> NoReturn:
    """Raise a validation error without including untrusted content."""

    raise ValidationError(code, source)


def _read_open_file(path: Path, maximum: int, source: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        reject("NO_NOFOLLOW_SUPPORT", source)
    flags |= nofollow
    try:
        descriptor = os.open(path, flags)
    except OSError:
        reject("UNSAFE_OR_MISSING_FILE", source)

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            reject("NOT_REGULAR_NONEMPTY_FILE", source)
        if metadata.st_size > maximum:
            reject("FILE_SIZE_LIMIT", source)

        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if not content or len(content) > maximum:
            reject("FILE_SIZE_LIMIT", source)
        return content
    except OSError:
        reject("FILE_READ_FAILED", source)
    finally:
        os.close(descriptor)


def read_contract_file(root: Path, relative: str) -> str:
    """Read one required regular, non-symlink contract file as strict UTF-8."""

    maximum = MAX_CONTRACT_BYTES.get(relative, MAX_CONTRACT_BYTES["package.json"])
    content = _read_open_file(root / relative, maximum, relative)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        reject("INVALID_UTF8", relative)
    if "\x00" in text or text.startswith("\ufeff"):
        reject("UNSAFE_TEXT_ENCODING", relative)
    return text


def ensure_workspace_ancestors(root: Path, relative: str) -> None:
    """Reject workspace paths that traverse a symlink or non-directory."""

    current = root
    for component in PurePosixPath(relative).parts[:-1]:
        current = current / component
        try:
            metadata = os.lstat(current)
        except OSError:
            reject("UNSAFE_WORKSPACE_PATH", "package.json")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            reject("UNSAFE_WORKSPACE_PATH", "package.json")


def _strip_toml_comment(line: str, source: str) -> str:
    quote = ""
    escaped = False
    for index, character in enumerate(line):
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
        elif quote == "'":
            if character == quote:
                quote = ""
        elif character in ('"', "'"):
            quote = character
        elif character == "#":
            return line[:index]
    if quote:
        reject("UNSUPPORTED_TOML_STRING", source)
    return line


def _toml_value_is_complete(value: str, source: str) -> bool:
    stack: list[str] = []
    quote = ""
    escaped = False
    for character in value:
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if quote == "'":
            if character == quote:
                quote = ""
            continue
        if character in ('"', "'"):
            quote = character
        elif character in "[{":
            stack.append(character)
        elif character in "]}":
            expected = "[" if character == "]" else "{"
            if not stack or stack.pop() != expected:
                reject("INVALID_TOML_NESTING", source)
    if quote:
        reject("UNSUPPORTED_TOML_STRING", source)
    return not stack


def _parse_toml_key_path(value: str, source: str) -> list[str]:
    parts = value.split(".")
    if not parts or any(not BARE_TOML_KEY.fullmatch(part) for part in parts):
        reject("UNSUPPORTED_TOML_KEY", source)
    return parts


class TomlValueParser:
    """Small fail-closed parser for the TOML value shapes used by the inputs."""

    def __init__(self, value: str, source: str) -> None:
        self.value = value
        self.source = source
        self.index = 0

    def parse(self) -> Any:
        parsed = self._parse_value()
        self._skip_space()
        if self.index != len(self.value):
            reject("UNSUPPORTED_TOML_VALUE", self.source)
        return parsed

    def _skip_space(self) -> None:
        while self.index < len(self.value) and self.value[self.index] in " \t\r\n":
            self.index += 1

    def _parse_value(self) -> Any:
        self._skip_space()
        if self.index >= len(self.value):
            reject("MISSING_TOML_VALUE", self.source)
        character = self.value[self.index]
        if character == '"':
            return self._parse_basic_string()
        if character == "'":
            return self._parse_literal_string()
        if character == "[":
            return self._parse_array()
        if character == "{":
            return self._parse_inline_table()
        return self._parse_bare_value()

    def _parse_basic_string(self) -> str:
        self.index += 1
        output: list[str] = []
        escapes = {
            "b": "\b",
            "t": "\t",
            "n": "\n",
            "f": "\f",
            "r": "\r",
            '"': '"',
            "\\": "\\",
        }
        while self.index < len(self.value):
            character = self.value[self.index]
            self.index += 1
            if character == '"':
                return "".join(output)
            if character == "\\":
                if self.index >= len(self.value):
                    reject("INVALID_TOML_ESCAPE", self.source)
                escape = self.value[self.index]
                self.index += 1
                if escape in escapes:
                    output.append(escapes[escape])
                    continue
                if escape not in ("u", "U"):
                    reject("INVALID_TOML_ESCAPE", self.source)
                digits = 4 if escape == "u" else 8
                encoded = self.value[self.index : self.index + digits]
                if len(encoded) != digits or not re.fullmatch(
                    rf"[0-9A-Fa-f]{{{digits}}}", encoded
                ):
                    reject("INVALID_TOML_ESCAPE", self.source)
                self.index += digits
                codepoint = int(encoded, 16)
                if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                    reject("INVALID_TOML_ESCAPE", self.source)
                output.append(chr(codepoint))
                continue
            if ord(character) < 0x20:
                reject("INVALID_TOML_STRING", self.source)
            output.append(character)
        reject("UNTERMINATED_TOML_STRING", self.source)

    def _parse_literal_string(self) -> str:
        self.index += 1
        end = self.value.find("'", self.index)
        if end < 0:
            reject("UNTERMINATED_TOML_STRING", self.source)
        parsed = self.value[self.index : end]
        if any(ord(character) < 0x20 for character in parsed):
            reject("INVALID_TOML_STRING", self.source)
        self.index = end + 1
        return parsed

    def _parse_array(self) -> list[Any]:
        self.index += 1
        parsed: list[Any] = []
        self._skip_space()
        if self._consume("]"):
            return parsed
        while True:
            parsed.append(self._parse_value())
            self._skip_space()
            if self._consume("]"):
                return parsed
            if not self._consume(","):
                reject("INVALID_TOML_ARRAY", self.source)
            self._skip_space()
            if self._consume("]"):
                return parsed

    def _parse_inline_table(self) -> dict[str, Any]:
        self.index += 1
        parsed: dict[str, Any] = {}
        self._skip_space()
        if self._consume("}"):
            return parsed
        while True:
            key = self._parse_inline_key()
            self._skip_space()
            if not self._consume("="):
                reject("INVALID_TOML_INLINE_TABLE", self.source)
            if key in parsed:
                reject("DUPLICATE_TOML_KEY", self.source)
            parsed[key] = self._parse_value()
            self._skip_space()
            if self._consume("}"):
                return parsed
            if not self._consume(","):
                reject("INVALID_TOML_INLINE_TABLE", self.source)
            self._skip_space()
            if self.index >= len(self.value) or self.value[self.index] == "}":
                reject("INVALID_TOML_INLINE_TABLE", self.source)

    def _parse_inline_key(self) -> str:
        self._skip_space()
        start = self.index
        while self.index < len(self.value) and (
            self.value[self.index].isalnum() or self.value[self.index] in "_-"
        ):
            self.index += 1
        key = self.value[start : self.index]
        if not BARE_TOML_KEY.fullmatch(key):
            reject("UNSUPPORTED_TOML_KEY", self.source)
        return key

    def _parse_bare_value(self) -> Any:
        start = self.index
        while (
            self.index < len(self.value) and self.value[self.index] not in ",]} \t\r\n"
        ):
            self.index += 1
        token = self.value[start : self.index]
        if token == "true":
            return True
        if token == "false":
            return False
        if re.fullmatch(r"[+-]?(?:0|[1-9][0-9]*)", token):
            return int(token)
        reject("UNSUPPORTED_TOML_VALUE", self.source)

    def _consume(self, expected: str) -> bool:
        if self.value.startswith(expected, self.index):
            self.index += len(expected)
            return True
        return False


def _resolve_toml_table(
    root: dict[str, Any], parts: list[str], is_array: bool, source: str
) -> dict[str, Any]:
    current = root
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        child = current[part]
        if isinstance(child, list):
            if not child or not isinstance(child[-1], dict):
                reject("INVALID_TOML_TABLE", source)
            current = child[-1]
        elif isinstance(child, dict):
            current = child
        else:
            reject("INVALID_TOML_TABLE", source)

    final = parts[-1]
    if is_array:
        if final not in current:
            current[final] = []
        table_array = current[final]
        if not isinstance(table_array, list):
            reject("INVALID_TOML_TABLE", source)
        table: dict[str, Any] = {}
        table_array.append(table)
        return table

    if final not in current:
        current[final] = {}
    table = current[final]
    if not isinstance(table, dict):
        reject("INVALID_TOML_TABLE", source)
    return table


def _assign_toml_value(
    table: dict[str, Any], key_parts: list[str], value: Any, source: str
) -> None:
    current = table
    for part in key_parts[:-1]:
        if part not in current:
            current[part] = {}
        child = current[part]
        if not isinstance(child, dict):
            reject("INVALID_TOML_DOTTED_KEY", source)
        current = child
    final = key_parts[-1]
    if final in current:
        reject("DUPLICATE_TOML_KEY", source)
    current[final] = value


def parse_toml(text: str, source: str) -> dict[str, Any]:
    """Parse the conservative TOML subset emitted by the pinned toolchains."""

    parsed: dict[str, Any] = {}
    current = parsed
    pending_key: list[str] | None = None
    pending_value = ""

    for raw_line in text.splitlines():
        line = _strip_toml_comment(raw_line, source).strip()
        if pending_key is not None:
            if line:
                pending_value += "\n" + line
            if _toml_value_is_complete(pending_value, source):
                value = TomlValueParser(pending_value, source).parse()
                _assign_toml_value(current, pending_key, value, source)
                pending_key = None
                pending_value = ""
            continue
        if not line:
            continue

        if line.startswith("[["):
            if not line.endswith("]]") or line.count("[[") != 1:
                reject("INVALID_TOML_TABLE", source)
            parts = _parse_toml_key_path(line[2:-2].strip(), source)
            current = _resolve_toml_table(parsed, parts, True, source)
            continue
        if line.startswith("["):
            if not line.endswith("]") or line.startswith("[["):
                reject("INVALID_TOML_TABLE", source)
            parts = _parse_toml_key_path(line[1:-1].strip(), source)
            current = _resolve_toml_table(parsed, parts, False, source)
            continue

        key, separator, value_text = line.partition("=")
        if not separator:
            reject("INVALID_TOML_ASSIGNMENT", source)
        key_parts = _parse_toml_key_path(key.strip(), source)
        value_text = value_text.strip()
        if not value_text:
            reject("MISSING_TOML_VALUE", source)
        if _toml_value_is_complete(value_text, source):
            value = TomlValueParser(value_text, source).parse()
            _assign_toml_value(current, key_parts, value, source)
        else:
            pending_key = key_parts
            pending_value = value_text

    if pending_key is not None:
        reject("UNTERMINATED_TOML_VALUE", source)
    return parsed


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("duplicate JSON key")
        parsed[key] = value
    return parsed


def parse_json(text: str, source: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite JSON number")
            ),
        )
    except TypeError:
        reject("INVALID_JSON", source)
    except ValueError:
        reject("INVALID_JSON", source)
    if not isinstance(parsed, dict):
        reject("INVALID_JSON_ROOT", source)
    return parsed


def _is_plain_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_https_url(value: Any, host: str, path_prefix: str, source: str) -> None:
    if not isinstance(value, str) or any(ord(character) < 0x20 for character in value):
        reject("UNSAFE_URL", source)
    try:
        parsed = urlsplit(value)
    except ValueError:
        reject("UNSAFE_URL", source)
    if (
        parsed.scheme != "https"
        or parsed.netloc != host
        or parsed.hostname != host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(path_prefix)
        or "\\" in parsed.path
    ):
        reject("UNSAFE_URL", source)


def parse_python_pin(
    requirement: Any,
    source: str,
    *,
    project_requirement: bool = False,
) -> tuple[str, str]:
    if not isinstance(requirement, str):
        reject("UNSAFE_PYTHON_REQUIREMENT", source)
    match = PYTHON_PIN.fullmatch(requirement)
    if match is None:
        reject("UNSAFE_PYTHON_REQUIREMENT", source)
    name = match.group("name")
    extras_text = match.group("extras")
    extras = tuple(extras_text.split(",")) if extras_text is not None else ()
    if project_requirement:
        if extras != REVIEWED_PYTHON_EXTRAS.get(name, ()):
            reject("UNSAFE_PYTHON_REQUIREMENT", source)
    elif extras:
        reject("UNSAFE_PYTHON_REQUIREMENT", source)
    return name, match.group("version")


def parse_python_requirements(value: Any, source: str) -> dict[str, str]:
    if not isinstance(value, list):
        reject("UNSAFE_PYTHON_REQUIREMENT", source)
    pins: dict[str, str] = {}
    for requirement in value:
        name, version = parse_python_pin(requirement, source, project_requirement=True)
        if name in pins:
            reject("DUPLICATE_PYTHON_REQUIREMENT", source)
        pins[name] = version
    return pins


def validate_python_project(
    project_config: dict[str, Any],
) -> tuple[dict[str, str], dict[str, dict[str, str]], int]:
    source = "pyproject.toml"
    project = project_config.get("project")
    if not isinstance(project, dict):
        reject("MISSING_PROJECT_TABLE", source)
    if project.get("requires-python") != f"=={PYTHON_VERSION}":
        reject("WRONG_PYTHON_VERSION", source)
    runtime_pins = parse_python_requirements(project.get("dependencies"), source)

    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        reject("UNSAFE_PYTHON_REQUIREMENT", source)
    optional_pins: dict[str, dict[str, str]] = {}
    for group, requirements in optional.items():
        if not isinstance(group, str) or not BARE_TOML_KEY.fullmatch(group):
            reject("UNSAFE_PYTHON_REQUIREMENT", source)
        optional_pins[group] = parse_python_requirements(requirements, source)

    dependency_groups = project_config.get("dependency-groups")
    if not isinstance(dependency_groups, dict) or not dependency_groups:
        reject("MISSING_DEPENDENCY_GROUPS", source)
    group_pins: dict[str, dict[str, str]] = {}
    for group, requirements in dependency_groups.items():
        if not isinstance(group, str) or not BARE_TOML_KEY.fullmatch(group):
            reject("UNSAFE_PYTHON_REQUIREMENT", source)
        group_pins[group] = parse_python_requirements(requirements, source)

    if "build-system" in project_config:
        reject("UNSUPPORTED_BUILD_SYSTEM", source)
    tool = project_config.get("tool")
    uv_project = tool.get("uv") if isinstance(tool, dict) else None
    if uv_project != {"package": False, "default-groups": ["dev"]}:
        reject("UNSAFE_UV_PROJECT_CONFIG", source)

    requirement_count = len(runtime_pins)
    requirement_count += sum(len(pins) for pins in optional_pins.values())
    requirement_count += sum(len(pins) for pins in group_pins.values())
    return runtime_pins, group_pins, requirement_count


def validate_uv_config(config: dict[str, Any]) -> None:
    if config != EXPECTED_UV_CONFIG:
        reject("UNSAFE_UV_CONFIG", "uv.toml")
    validate_https_url(config["index"][0]["url"], "pypi.org", "/simple", "uv.toml")


def _parse_lock_extras(value: Any, source: str, error: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(extra, str) or CANONICAL_PYTHON_NAME.fullmatch(extra) is None
            for extra in value
        )
        or value != sorted(set(value))
    ):
        reject(error, source)
    return tuple(value)


def _locked_metadata_pins(
    value: Any,
    source: str,
    expected_extras: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    if not isinstance(value, list):
        reject("UNSAFE_LOCK_METADATA", source)
    pins: dict[str, str] = {}
    for requirement in value:
        if (
            not isinstance(requirement, dict)
            or not {"name", "specifier"}.issubset(requirement)
            or not set(requirement).issubset({"name", "specifier", "extras"})
        ):
            reject("UNSAFE_LOCK_METADATA", source)
        name = requirement.get("name")
        specifier = requirement.get("specifier")
        if not isinstance(name, str) or not isinstance(specifier, str):
            reject("UNSAFE_LOCK_METADATA", source)
        parsed_name, version = parse_python_pin(name + specifier, source)
        extras = (
            _parse_lock_extras(requirement["extras"], source, "UNSAFE_LOCK_METADATA")
            if "extras" in requirement
            else ()
        )
        if extras != expected_extras.get(parsed_name, ()):
            reject("LOCK_PROJECT_PIN_MISMATCH", source)
        if parsed_name in pins:
            reject("UNSAFE_LOCK_METADATA", source)
        pins[parsed_name] = version
    return pins


def _validate_uv_dependency_references(
    value: Any,
    source: str,
    *,
    expected_extras: dict[str, tuple[str, ...]] | None = None,
) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        reject("UNSAFE_LOCK_DEPENDENCY", source)
    names: set[str] = set()
    for dependency in value:
        allowed_keys = {"name", "marker"}
        if expected_extras is not None:
            allowed_keys.add("extra")
        if not isinstance(dependency, dict) or not set(dependency).issubset(
            allowed_keys
        ):
            reject("UNSAFE_LOCK_DEPENDENCY", source)
        name = dependency.get("name")
        if not isinstance(name, str) or not CANONICAL_PYTHON_NAME.fullmatch(name):
            reject("UNSAFE_LOCK_DEPENDENCY", source)
        if name in names:
            reject("UNSAFE_LOCK_DEPENDENCY", source)
        names.add(name)
        if "marker" in dependency and not isinstance(dependency["marker"], str):
            reject("UNSAFE_LOCK_DEPENDENCY", source)
        extras = (
            _parse_lock_extras(dependency["extra"], source, "UNSAFE_LOCK_DEPENDENCY")
            if "extra" in dependency
            else ()
        )
        if expected_extras is not None and extras != expected_extras.get(name, ()):
            reject("LOCK_PROJECT_PIN_MISMATCH", source)
    return names


def _validate_uv_optional_dependencies(
    value: Any,
    package_name: str,
    source: str,
) -> set[str]:
    expected = REVIEWED_PYTHON_EXTRAS.get(package_name, ())
    if not expected:
        if value is not None:
            reject("UNSAFE_UV_LOCK_PACKAGE", source)
        return set()
    if not isinstance(value, dict) or set(value) != set(expected):
        reject("UNSAFE_UV_LOCK_PACKAGE", source)
    references: set[str] = set()
    for extra in expected:
        references.update(_validate_uv_dependency_references(value[extra], source))
    return references


def _validate_python_artifact(artifact: Any) -> None:
    source = "uv.lock"
    if not isinstance(artifact, dict) or set(artifact) != {
        "url",
        "hash",
        "size",
        "upload-time",
    }:
        reject("UNSAFE_PYTHON_ARTIFACT", source)
    validate_https_url(artifact.get("url"), PYTHON_ARCHIVE_HOST, "/packages/", source)
    if not isinstance(artifact.get("hash"), str) or not SHA256.fullmatch(
        artifact["hash"]
    ):
        reject("MISSING_OR_UNSAFE_SHA256", source)
    if not _is_plain_integer(artifact.get("size")) or artifact["size"] <= 0:
        reject("UNSAFE_PYTHON_ARTIFACT", source)
    upload_time = artifact.get("upload-time")
    if not isinstance(upload_time, str) or UTC_TIMESTAMP.fullmatch(upload_time) is None:
        reject("UNSAFE_PYTHON_ARTIFACT", source)
    try:
        timestamp_format = (
            "%Y-%m-%dT%H:%M:%S.%fZ" if "." in upload_time else "%Y-%m-%dT%H:%M:%SZ"
        )
        uploaded_at = datetime.strptime(upload_time, timestamp_format).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        reject("UNSAFE_PYTHON_ARTIFACT", source)
    if uploaded_at.tzinfo != timezone.utc or uploaded_at > EXCLUDE_NEWER_TIMESTAMP:
        reject("UNSAFE_PYTHON_ARTIFACT", source)


def validate_uv_lock(
    lock: dict[str, Any],
    runtime_pins: dict[str, str],
    group_pins: dict[str, dict[str, str]],
) -> tuple[int, int]:
    source = "uv.lock"
    if set(lock) != {"version", "revision", "requires-python", "options", "package"}:
        reject("UNEXPECTED_UV_LOCK_SHAPE", source)
    if lock.get("version") != UV_LOCK_VERSION or isinstance(lock.get("version"), bool):
        reject("WRONG_UV_LOCK_VERSION", source)
    if lock.get("revision") != UV_LOCK_REVISION or isinstance(
        lock.get("revision"), bool
    ):
        reject("WRONG_UV_LOCK_REVISION", source)
    if lock.get("requires-python") != f"=={PYTHON_VERSION}":
        reject("WRONG_PYTHON_VERSION", source)
    if lock.get("options") != {
        "prerelease-mode": EXPECTED_UV_CONFIG["prerelease"],
        "exclude-newer": EXPECTED_UV_CONFIG["exclude-newer"],
    }:
        reject("UNSAFE_UV_LOCK_OPTIONS", source)

    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        reject("MISSING_UV_LOCK_PACKAGES", source)
    root_packages: list[dict[str, Any]] = []
    registry_packages: dict[str, dict[str, Any]] = {}
    dependency_references: set[str] = set()
    artifact_count = 0

    for package in packages:
        if not isinstance(package, dict):
            reject("UNSAFE_UV_LOCK_PACKAGE", source)
        name = package.get("name")
        version = package.get("version")
        package_source = package.get("source")
        if (
            not isinstance(name, str)
            or not CANONICAL_PYTHON_NAME.fullmatch(name)
            or not isinstance(version, str)
            or not PYTHON_VERSION_VALUE.fullmatch(version)
            or not isinstance(package_source, dict)
        ):
            reject("UNSAFE_UV_LOCK_PACKAGE", source)

        if package_source == {"virtual": "."}:
            root_packages.append(package)
            continue
        if package_source != {"registry": PYPI_INDEX}:
            reject("UNSAFE_PYTHON_SOURCE", source)
        if not set(package).issubset(
            {
                "name",
                "version",
                "source",
                "dependencies",
                "optional-dependencies",
                "sdist",
                "wheels",
            }
        ):
            reject("UNSAFE_UV_LOCK_PACKAGE", source)
        if name in registry_packages:
            reject("DUPLICATE_UV_LOCK_PACKAGE", source)
        registry_packages[name] = package
        dependency_references.update(
            _validate_uv_dependency_references(package.get("dependencies"), source)
        )
        dependency_references.update(
            _validate_uv_optional_dependencies(
                package.get("optional-dependencies"), name, source
            )
        )

        artifacts: list[Any] = []
        if "sdist" in package:
            artifacts.append(package["sdist"])
        wheels = package.get("wheels", [])
        if not isinstance(wheels, list):
            reject("UNSAFE_PYTHON_ARTIFACT", source)
        artifacts.extend(wheels)
        if not artifacts:
            reject("MISSING_PYTHON_ARTIFACT", source)
        for artifact in artifacts:
            _validate_python_artifact(artifact)
        artifact_count += len(artifacts)

    if len(root_packages) != 1 or not registry_packages:
        reject("UNSAFE_UV_LOCK_ROOT", source)
    root = root_packages[0]
    if (
        set(root)
        != {
            "name",
            "version",
            "source",
            "dependencies",
            "dev-dependencies",
            "metadata",
        }
        or root.get("name") != "raos"
        or root.get("version") != "0.0.0"
    ):
        reject("UNSAFE_UV_LOCK_ROOT", source)
    runtime_extras = {
        name: REVIEWED_PYTHON_EXTRAS[name]
        for name in runtime_pins
        if name in REVIEWED_PYTHON_EXTRAS
    }
    root_dependencies = _validate_uv_dependency_references(
        root.get("dependencies"), source, expected_extras=runtime_extras
    )
    if root_dependencies != set(runtime_pins):
        reject("LOCK_PROJECT_PIN_MISMATCH", source)
    dependency_references.update(root_dependencies)
    if not dependency_references.issubset(registry_packages):
        reject("UNSAFE_LOCK_DEPENDENCY", source)

    metadata = root.get("metadata")
    if not isinstance(metadata, dict) or set(metadata) != {
        "requires-dist",
        "requires-dev",
    }:
        reject("UNSAFE_LOCK_METADATA", source)
    if (
        _locked_metadata_pins(metadata["requires-dist"], source, runtime_extras)
        != runtime_pins
    ):
        reject("LOCK_PROJECT_PIN_MISMATCH", source)
    locked_groups = metadata.get("requires-dev")
    if not isinstance(locked_groups, dict) or set(locked_groups) != set(group_pins):
        reject("LOCK_PROJECT_PIN_MISMATCH", source)
    for group, pins in group_pins.items():
        if _locked_metadata_pins(locked_groups[group], source, {}) != pins:
            reject("LOCK_PROJECT_PIN_MISMATCH", source)

    for name, version in {
        **runtime_pins,
        **{key: value for pins in group_pins.values() for key, value in pins.items()},
    }.items():
        package = registry_packages.get(name)
        if package is None or package.get("version") != version:
            reject("LOCK_PROJECT_PIN_MISMATCH", source)

    return len(packages), artifact_count


def validate_workspace_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        reject("UNSAFE_WORKSPACE_PATH", "package.json")
    pure = PurePosixPath(value)
    parts = pure.parts
    if (
        pure.is_absolute()
        or str(pure) != value
        or not parts
        or parts[0] == "node_modules"
        or any(
            part in ("", ".", "..") or not SAFE_WORKSPACE_COMPONENT.fullmatch(part)
            for part in parts
        )
    ):
        reject("UNSAFE_WORKSPACE_PATH", "package.json")
    return value


def _validate_npm_package_name(value: Any, source: str) -> str:
    if not isinstance(value, str) or not NPM_PACKAGE_NAME.fullmatch(value):
        reject("UNSAFE_NPM_PACKAGE_NAME", source)
    return value


def validate_npm_spec(
    value: Any,
    dependency_name: str,
    current_name: str,
    workspace_names: set[str],
    source: str,
) -> None:
    if not isinstance(value, str):
        reject("UNSAFE_NPM_SPECIFIER", source)
    if (
        NPM_EXACT_VERSION.fullmatch(value)
        and _parse_exact_npm_semver(value) is not None
    ):
        return
    if (
        value == "workspace:*"
        and dependency_name in workspace_names
        and dependency_name != current_name
    ):
        return
    reject("UNSAFE_NPM_SPECIFIER", source)


def _split_override_key(value: Any, source: str) -> tuple[str, str | None]:
    if not isinstance(value, str):
        reject("UNSAFE_NPM_OVERRIDE", source)
    selector_index = value.rfind("@")
    if value.startswith("@") and selector_index == 0:
        selector_index = -1
    if selector_index > 0:
        name = value[:selector_index]
        selector = value[selector_index + 1 :]
    else:
        name = value
        selector = None
    _validate_npm_package_name(name, source)
    if selector is not None and (
        not NPM_EXACT_VERSION.fullmatch(selector)
        or _parse_exact_npm_semver(selector) is None
    ):
        reject("UNSAFE_NPM_OVERRIDE", source)
    return name, selector


def _validate_npm_overrides(
    value: Any, current_name: str, workspace_names: set[str], source: str
) -> None:
    if not isinstance(value, dict) or not value:
        reject("UNSAFE_NPM_OVERRIDE", source)
    for key, child in value.items():
        name, _selector = _split_override_key(key, source)
        if isinstance(child, dict):
            _validate_npm_overrides(child, current_name, workspace_names, source)
        else:
            validate_npm_spec(child, name, current_name, workspace_names, source)


def validate_npm_manifest(
    manifest: dict[str, Any], workspace_names: set[str], source: str
) -> None:
    current_name = _validate_npm_package_name(manifest.get("name"), source)
    if "workspaces" in manifest and source != "package.json":
        reject("NESTED_NPM_WORKSPACES", source)
    for section in NPM_DEPENDENCY_SECTIONS:
        dependencies = manifest.get(section, {})
        if not isinstance(dependencies, dict):
            reject("UNSAFE_NPM_SPECIFIER", source)
        for name, specifier in dependencies.items():
            dependency_name = _validate_npm_package_name(name, source)
            validate_npm_spec(
                specifier,
                dependency_name,
                current_name,
                workspace_names,
                source,
            )
    if "overrides" in manifest:
        _validate_npm_overrides(
            manifest["overrides"], current_name, workspace_names, source
        )
    if source == "package.json":
        if manifest.get("overrides") != EXPECTED_NPM_OVERRIDES:
            reject("UNSAFE_NPM_OVERRIDE", source)
    elif "overrides" in manifest:
        reject("UNSAFE_NPM_OVERRIDE", source)
    if "resolutions" in manifest or any(
        key in manifest for key in ("bundleDependencies", "bundledDependencies")
    ):
        reject("UNSAFE_NPM_MANIFEST_FEATURE", source)


def load_npm_manifests(
    root: Path, root_manifest: dict[str, Any]
) -> tuple[list[str], dict[str, dict[str, Any]], set[str]]:
    workspaces = root_manifest.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        reject("UNSAFE_WORKSPACE_PATH", "package.json")
    workspace_paths: list[str] = []
    seen_paths: set[str] = set()
    for value in workspaces:
        workspace = validate_workspace_path(value)
        if workspace in seen_paths:
            reject("DUPLICATE_WORKSPACE", "package.json")
        seen_paths.add(workspace)
        workspace_paths.append(workspace)

    manifests: dict[str, dict[str, Any]] = {"": root_manifest}
    names: set[str] = set()
    root_name = _validate_npm_package_name(root_manifest.get("name"), "package.json")
    names.add(root_name)
    workspace_names: set[str] = set()
    for workspace in workspace_paths:
        relative = f"{workspace}/package.json"
        ensure_workspace_ancestors(root, relative)
        manifest = parse_json(read_contract_file(root, relative), relative)
        name = _validate_npm_package_name(manifest.get("name"), relative)
        if name in names or manifest.get("private") is not True:
            reject("UNSAFE_WORKSPACE_MANIFEST", relative)
        names.add(name)
        workspace_names.add(name)
        manifests[workspace] = manifest

    for workspace, manifest in manifests.items():
        source = "package.json" if not workspace else f"{workspace}/package.json"
        validate_npm_manifest(manifest, workspace_names, source)
    return workspace_paths, manifests, workspace_names


def validate_npm_config(text: str) -> None:
    parsed: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        key, separator, value = line.partition("=")
        if (
            not separator
            or key != key.strip()
            or value != value.strip()
            or not key
            or key in parsed
        ):
            reject("UNSAFE_NPM_CONFIG", ".npmrc")
        parsed[key] = value
    if parsed != EXPECTED_NPM_CONFIG:
        reject("UNSAFE_NPM_CONFIG", ".npmrc")
    validate_https_url(parsed["registry"], "registry.npmjs.org", "/", ".npmrc")


def _captured_lock_dependency_path(
    package_path: str, dependency_name: str, package_paths: set[str]
) -> str | None:
    package_chain = package_path.removeprefix("node_modules/").split("/node_modules/")
    for depth in range(len(package_chain), -1, -1):
        if depth:
            ancestor = "node_modules/" + "/node_modules/".join(package_chain[:depth])
            candidate = f"{ancestor}/node_modules/{dependency_name}"
        else:
            candidate = f"node_modules/{dependency_name}"
        if candidate in package_paths:
            return candidate
    return None


def _lock_package_name(package_path: str) -> str:
    return package_path.removeprefix("node_modules/").split("/node_modules/")[-1]


def _effective_lock_dependency_spec(
    package_path: str,
    package_version: str,
    dependency_name: str,
    descriptor: str,
) -> str:
    parent_override = NPM_PARENT_OVERRIDE_SPECS.get(
        (_lock_package_name(package_path), package_version, dependency_name)
    )
    if parent_override is not None:
        return parent_override
    return NPM_GLOBAL_OVERRIDE_SPECS.get(dependency_name, descriptor)


def _optional_peer_dependencies(metadata: dict[str, Any]) -> set[str]:
    peers = metadata.get("peerDependencies", {})
    peer_metadata = metadata.get("peerDependenciesMeta", {})
    if not isinstance(peers, dict) or not isinstance(peer_metadata, dict):
        reject("UNSAFE_NPM_LOCK_REFERENCE", "package-lock.json")
    optional: set[str] = set()
    for name, flags in peer_metadata.items():
        dependency_name = _validate_npm_package_name(name, "package-lock.json")
        if (
            not isinstance(flags, dict)
            or set(flags) != {"optional"}
            or type(flags["optional"]) is not bool
        ):
            reject("UNSAFE_NPM_LOCK_REFERENCE", "package-lock.json")
        # npm-generated lockfiles can retain inert metadata for a peer omitted
        # from peerDependencies. Such entries never grant a closure exemption.
        if flags["optional"] is True and dependency_name in peers:
            optional.add(dependency_name)
    return optional


def _validate_lock_dependency_specs(
    package_path: str,
    metadata: dict[str, Any],
    packages: dict[str, Any],
) -> None:
    optional_peers = _optional_peer_dependencies(metadata)
    package_paths = {path for path in packages if isinstance(path, str)}
    package_version = metadata.get("version")
    if (
        not isinstance(package_version, str)
        or not NPM_EXACT_VERSION.fullmatch(package_version)
        or _parse_exact_npm_semver(package_version) is None
    ):
        reject("UNSAFE_NPM_LOCK_VERSION", "package-lock.json")
    for section in LOCK_DEPENDENCY_SECTIONS:
        dependencies = metadata.get(section, {})
        if not isinstance(dependencies, dict):
            reject("UNSAFE_NPM_LOCK_REFERENCE", "package-lock.json")
        for name, specifier in dependencies.items():
            dependency_name = _validate_npm_package_name(name, "package-lock.json")
            # package-lock dependency descriptors may be arbitrary npm package
            # specs (including VCS and local sources). Accept only the ASCII
            # semver-range shapes present in the reviewed lock contract. npm
            # retains a small number of partial descriptors from upstream
            # package metadata; normalize only their exact package/version/
            # dependency tuple so the general partial-range rejection remains.
            reviewed_specifier = (
                NPM_REVIEWED_LOCK_PARTIAL_SPECS.get(
                    (
                        _lock_package_name(package_path),
                        package_version,
                        dependency_name,
                        specifier,
                    )
                )
                if isinstance(specifier, str)
                else None
            )
            supported_specifier = (
                specifier
                if isinstance(specifier, str)
                and _parse_supported_npm_range(specifier) is not None
                else reviewed_specifier
            )
            if supported_specifier is None:
                reject("UNSAFE_NPM_LOCK_REFERENCE", "package-lock.json")
            captured_path = _captured_lock_dependency_path(
                package_path, dependency_name, package_paths
            )
            if captured_path is None:
                if section == "peerDependencies" and dependency_name in optional_peers:
                    continue
                reject("MISSING_NPM_LOCK_DEPENDENCY", "package-lock.json")
            captured = packages.get(captured_path)
            captured_version = (
                captured.get("version") if isinstance(captured, dict) else None
            )
            effective_specifier = _effective_lock_dependency_spec(
                package_path,
                package_version,
                dependency_name,
                supported_specifier,
            )
            if not isinstance(
                captured_version, str
            ) or not _npm_version_satisfies_range(
                captured_version, effective_specifier
            ):
                reject("NPM_LOCK_RANGE_MISMATCH", "package-lock.json")


def _validate_local_lock_dependencies(
    manifest: dict[str, Any],
    packages: dict[str, Any],
    workspace_name_paths: dict[str, str],
) -> None:
    for section in NPM_DEPENDENCY_SECTIONS:
        dependencies = manifest.get(section, {})
        if not isinstance(dependencies, dict):
            reject("UNSAFE_NPM_LOCK_REFERENCE", "package-lock.json")
        for name, specifier in dependencies.items():
            dependency_name = _validate_npm_package_name(name, "package-lock.json")
            candidate = f"node_modules/{dependency_name}"
            captured = packages.get(candidate)
            if not isinstance(captured, dict):
                reject("MISSING_NPM_LOCK_DEPENDENCY", "package-lock.json")
            if specifier == "workspace:*":
                expected_workspace = workspace_name_paths.get(dependency_name)
                if captured != {"resolved": expected_workspace, "link": True}:
                    reject("UNSAFE_NPM_WORKSPACE_LINK", "package-lock.json")
                continue
            captured_version = captured.get("version")
            if captured.get("link") is True or captured_version != specifier:
                reject("NPM_LOCK_RANGE_MISMATCH", "package-lock.json")


def _validate_sha512_integrity(value: Any) -> None:
    if not isinstance(value, str):
        reject("MISSING_OR_UNSAFE_SHA512", "package-lock.json")
    tokens = value.split()
    if not tokens:
        reject("MISSING_OR_UNSAFE_SHA512", "package-lock.json")
    for token in tokens:
        algorithm, separator, encoded = token.partition("-")
        if algorithm != "sha512" or not separator or not encoded:
            reject("MISSING_OR_UNSAFE_SHA512", "package-lock.json")
        try:
            digest = base64.b64decode(encoded.encode("ascii"), validate=True)
        except ValueError:
            reject("MISSING_OR_UNSAFE_SHA512", "package-lock.json")
        if len(digest) != 64:
            reject("MISSING_OR_UNSAFE_SHA512", "package-lock.json")


def _validate_lock_manifest_match(
    locked: Any, manifest: dict[str, Any], source: str
) -> None:
    if not isinstance(locked, dict):
        reject("LOCK_MANIFEST_MISMATCH", source)
    if locked.get("name") != manifest.get("name") or locked.get(
        "version"
    ) != manifest.get("version"):
        reject("LOCK_MANIFEST_MISMATCH", source)
    for section in NPM_DEPENDENCY_SECTIONS:
        if locked.get(section, {}) != manifest.get(section, {}):
            reject("LOCK_MANIFEST_MISMATCH", source)


def validate_package_lock(
    package_lock: dict[str, Any],
    workspace_paths: list[str],
    manifests: dict[str, dict[str, Any]],
) -> int:
    source = "package-lock.json"
    if set(package_lock) != {
        "name",
        "version",
        "lockfileVersion",
        "requires",
        "packages",
    }:
        reject("UNEXPECTED_NPM_LOCK_SHAPE", source)
    root_manifest = manifests[""]
    if (
        package_lock.get("name") != root_manifest.get("name")
        or package_lock.get("version") != root_manifest.get("version")
        or package_lock.get("lockfileVersion") != 3
        or isinstance(package_lock.get("lockfileVersion"), bool)
        or package_lock.get("requires") is not True
    ):
        reject("WRONG_NPM_LOCK_CONTRACT", source)
    packages = package_lock.get("packages")
    if not isinstance(packages, dict) or not packages:
        reject("MISSING_NPM_LOCK_PACKAGES", source)

    _validate_lock_manifest_match(packages.get(""), root_manifest, source)
    root_locked = packages[""]
    if root_locked.get("workspaces") != workspace_paths:
        reject("LOCK_MANIFEST_MISMATCH", source)
    for workspace in workspace_paths:
        _validate_lock_manifest_match(
            packages.get(workspace), manifests[workspace], source
        )

    expected_links = {
        f"node_modules/{manifests[path]['name']}": path for path in workspace_paths
    }
    workspace_name_paths = {manifests[path]["name"]: path for path in workspace_paths}
    for manifest in manifests.values():
        _validate_local_lock_dependencies(manifest, packages, workspace_name_paths)
    observed_links: dict[str, str] = {}
    external_count = 0
    local_paths = {"", *workspace_paths}
    forbidden_metadata = {"from", "inBundle", "resolvedGit", "resolvedFile"}

    for package_path, metadata in packages.items():
        if not isinstance(package_path, str) or not isinstance(metadata, dict):
            reject("UNSAFE_NPM_LOCK_PACKAGE", source)
        if package_path in local_paths:
            if any(key in metadata for key in ("resolved", "integrity", "link")):
                reject("UNSAFE_NPM_LOCK_PACKAGE", source)
            continue
        if not LOCK_PACKAGE_PATH.fullmatch(package_path):
            reject("UNSAFE_NPM_LOCK_PACKAGE", source)
        path_parts = package_path.split("/")
        if any(part in (".", "..", "") for part in path_parts):
            reject("UNSAFE_NPM_LOCK_PACKAGE", source)

        if metadata.get("link") is True:
            if set(metadata) != {"resolved", "link"}:
                reject("UNSAFE_NPM_WORKSPACE_LINK", source)
            resolved = metadata.get("resolved")
            if expected_links.get(package_path) != resolved:
                reject("UNSAFE_NPM_WORKSPACE_LINK", source)
            observed_links[package_path] = resolved
            continue
        if "link" in metadata or forbidden_metadata.intersection(metadata):
            reject("UNSAFE_NPM_LOCK_PACKAGE", source)
        version = metadata.get("version")
        if (
            not isinstance(version, str)
            or not NPM_EXACT_VERSION.fullmatch(version)
            or _parse_exact_npm_semver(version) is None
        ):
            reject("UNSAFE_NPM_LOCK_VERSION", source)
        validate_https_url(metadata.get("resolved"), "registry.npmjs.org", "/", source)
        _validate_sha512_integrity(metadata.get("integrity"))
        _validate_lock_dependency_specs(package_path, metadata, packages)
        external_count += 1

    if observed_links != expected_links or external_count == 0:
        reject("UNSAFE_NPM_WORKSPACE_LINK", source)
    return external_count


def validate(root: Path) -> dict[str, Any]:
    texts = {
        relative: read_contract_file(root, relative) for relative in ROOT_CONTRACT_FILES
    }
    if texts[".python-version"] != f"{PYTHON_VERSION}\n":
        reject("WRONG_PYTHON_VERSION", ".python-version")

    project_config = parse_toml(texts["pyproject.toml"], "pyproject.toml")
    uv_config = parse_toml(texts["uv.toml"], "uv.toml")
    uv_lock = parse_toml(texts["uv.lock"], "uv.lock")
    runtime_pins, group_pins, requirement_count = validate_python_project(
        project_config
    )
    validate_uv_config(uv_config)
    python_packages, python_artifacts = validate_uv_lock(
        uv_lock, runtime_pins, group_pins
    )

    root_manifest = parse_json(texts["package.json"], "package.json")
    workspace_paths, manifests, _workspace_names = load_npm_manifests(
        root, root_manifest
    )
    validate_npm_config(texts[".npmrc"])
    package_lock = parse_json(texts["package-lock.json"], "package-lock.json")
    external_packages = validate_package_lock(package_lock, workspace_paths, manifests)

    return {
        "npm": {
            "external_packages": external_packages,
            "lockfile_version": 3,
            "manifests": len(manifests),
            "workspaces": len(workspace_paths),
        },
        "python": {
            "artifacts": python_artifacts,
            "lock_packages": python_packages,
            "lock_revision": UV_LOCK_REVISION,
            "lock_version": UV_LOCK_VERSION,
            "requirements": requirement_count,
            "version": PYTHON_VERSION,
        },
        "status": "PASS",
    }


def main() -> int:
    if len(sys.argv) != 1:
        failure = {"error": "INVALID_ARGUMENTS", "source": "command", "status": "FAIL"}
        print(
            json.dumps(failure, sort_keys=True, separators=(",", ":")), file=sys.stderr
        )
        return 64
    root = Path(__file__).resolve().parent.parent
    try:
        result = validate(root)
    except ValidationError as error:
        failure = {"error": error.code, "source": error.source, "status": "FAIL"}
        print(
            json.dumps(failure, sort_keys=True, separators=(",", ":")), file=sys.stderr
        )
        return 1
    except Exception:
        failure = {
            "error": "INTERNAL_VALIDATION_FAILURE",
            "source": "validator",
            "status": "FAIL",
        }
        print(
            json.dumps(failure, sort_keys=True, separators=(",", ":")), file=sys.stderr
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
