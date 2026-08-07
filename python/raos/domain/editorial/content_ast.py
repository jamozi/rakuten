"""Hash-bound loading for the RAOS Content AST v1 contract.

The frozen JSON Schema remains the structural authority.  The generated
Pydantic model is reused as the typed domain projection, but it is never used
as a weaker substitute for that schema.  Runtime file checks establish disk
parity for the selected generated entry files at the load/dump call boundary,
after normal Python import.  Pre-execution integrity for the complete generated
tree remains the ST-0105 deployment/code-generation gate's responsibility.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
import hashlib
import json
import os
import re
import stat
import threading
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from pydantic import ValidationError

from raos.generated.contracts import (
    BlockBulletList,
    BlockDecisionSummary,
    BlockFaq,
    BlockNumberedList,
    BlockProsCons,
    BlockSelectionCriteria,
)
from raos.generated.contracts.content_ast import ArticleType, PublicationFlags
from raos.generated.contracts.content_ast import Schema as ContentAst


CONTENT_AST_SCHEMA_VERSION = "1.0.0"
CONTENT_AST_SCHEMA_SHA256 = (
    "a9e9f927d1646bb56f5124c70e5cc8a34e5e3b0de57d4fd1ac6633da1cfb2bac"
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = Path(
    "contracts/raos-v0.4/contracts/content/schemas/content-ast.schema.json"
)
_CONTENT_AST_SCHEMA_BYTES = 46_209
_PINNED_MODEL_FILES = {
    Path("python/raos/generated/contracts/__init__.py"): (
        "a592d42f7fac1d6a93ae66f5593352c1842c8d5dfc316b75799d6caf4bf901e3",
        43_711,
    ),
    Path("python/raos/generated/contracts/content_ast.py"): (
        "2b7eaf20108494c857fe942a390a0d8557cbda2547e547bf8f5a039231d651cf",
        434,
    ),
    Path("python/raos/generated/contracts/_internal.py"): (
        "bccdefcfd53c052e5091ff2ee00dbb482d3fe86241d8a6f91cd02ba58b6e75c9",
        221_159,
    ),
}
_SAFE_ERROR_COMPONENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_RFC3339_DATE_TIME = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[Tt]"
    r"(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d):"
    r"(?P<second>[0-5]\d|60)(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z"
)
_SERIALIZER_REBUILD_MODELS = (
    BlockDecisionSummary,
    BlockSelectionCriteria,
    BlockBulletList,
    BlockNumberedList,
    BlockProsCons,
    BlockFaq,
)
_GENERATED_MODELS_LOCK = threading.Lock()
_generated_models_ready = False


class _SchemaValidationFailure(Protocol):
    @property
    def absolute_path(self) -> Iterable[str | int]: ...

    @property
    def validator(self) -> object: ...


class _SchemaValidator(Protocol):
    def iter_errors(self, instance: object) -> Iterator[_SchemaValidationFailure]: ...


class _FormatCheckerRegistration(Protocol):
    def checks(
        self, format_name: str
    ) -> Callable[[Callable[[object], bool]], Callable[[object], bool]]: ...


class ContentAstValidationError(ValueError):
    """A redacted failure for caller-controlled Content AST input."""

    __slots__ = ("category", "keyword", "pointer")

    def __init__(self, category: str, pointer: str, keyword: str) -> None:
        self.category = category
        self.pointer = pointer
        self.keyword = keyword
        super().__init__(
            "content AST input is invalid "
            f"(category={category}, pointer={pointer}, keyword={keyword})"
        )

    def __repr__(self) -> str:
        return (
            "ContentAstValidationError("
            f"category={self.category!r}, pointer={self.pointer!r}, "
            f"keyword={self.keyword!r})"
        )


class ContentAstContractError(RuntimeError):
    """A fail-closed error for drift in the installed schema/type contract."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("content AST contract is unavailable")

    def __repr__(self) -> str:
        return "ContentAstContractError('content AST contract is unavailable')"


class _DuplicateJsonMemberError(ValueError):
    pass


class _NonFiniteJsonNumberError(ValueError):
    pass


class _PinnedFileReadError(Exception):
    pass


def _raise_invalid(
    category: str = "INPUT",
    pointer: str = "/",
    keyword: str = "invalid",
) -> NoReturn:
    raise ContentAstValidationError(category, pointer, keyword) from None


def _raise_contract_error() -> NoReturn:
    raise ContentAstContractError() from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_pinned_file(
    relative: Path, expected_sha256: str, expected_size: int
) -> bytes:
    portable = PurePosixPath(relative.as_posix())
    if (
        portable.is_absolute()
        or any(component in {"", ".", ".."} for component in portable.parts)
        or expected_size < 0
    ):
        _raise_contract_error()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    file_descriptor: int | None = None
    content: bytes | None = None
    operation_failed = False
    try:
        current = os.open(_REPOSITORY_ROOT, directory_flags)
        descriptors.append(current)
        for component in portable.parent.parts:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
        file_descriptor = os.open(
            portable.name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=descriptors[-1],
        )
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected_size:
            raise _PinnedFileReadError
        buffer = bytearray()
        remaining = expected_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise _PinnedFileReadError
            buffer.extend(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise _PinnedFileReadError
        final_metadata = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(final_metadata.st_mode)
            or final_metadata.st_size != expected_size
        ):
            raise _PinnedFileReadError
        content = bytes(buffer)
    except OSError, _PinnedFileReadError:
        operation_failed = True
    finally:
        close_failed = False
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                close_failed = True
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
    if operation_failed or close_failed or content is None:
        _raise_contract_error()
    if _sha256(content) != expected_sha256:
        _raise_contract_error()
    return content


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJsonMemberError
        result[name] = value
    return result


def _reject_non_finite_number(value: str) -> NoReturn:
    del value
    raise _NonFiniteJsonNumberError


def _parse_json(source: str | bytes | bytearray) -> object:
    if type(source) not in {str, bytes, bytearray}:
        _raise_invalid("JSON", "/", "input_type")
    immutable_source: str | bytes
    if isinstance(source, bytearray):
        immutable_source = bytes(source)
    else:
        immutable_source = source
    try:
        return json.loads(
            immutable_source,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_non_finite_number,
        )
    except _DuplicateJsonMemberError:
        _raise_invalid("JSON", "/", "duplicate_members")
    except _NonFiniteJsonNumberError:
        _raise_invalid("JSON", "/", "finite_number")
    except ValueError:
        _raise_invalid("JSON", "/", "syntax")
    except UnicodeError, RecursionError:
        _raise_invalid("JSON", "/", "syntax")


def _is_rfc3339_date_time(value: object) -> bool:
    if type(value) is not str:
        return True
    match = _RFC3339_DATE_TIME.fullmatch(value)
    if match is None:
        return False
    try:
        date(
            int(match["year"]),
            int(match["month"]),
            int(match["day"]),
        )
    except ValueError:
        return False
    return True


_format_checker = FormatChecker()
cast(_FormatCheckerRegistration, _format_checker).checks("date-time")(
    _is_rfc3339_date_time
)
_validator: _SchemaValidator | None = None


def _schema_validator() -> _SchemaValidator:
    global _validator

    schema_bytes = _read_pinned_file(
        _SCHEMA_PATH,
        CONTENT_AST_SCHEMA_SHA256,
        _CONTENT_AST_SCHEMA_BYTES,
    )
    for relative, (digest, size) in _PINNED_MODEL_FILES.items():
        _read_pinned_file(relative, digest, size)
    if _validator is None:
        try:
            schema = json.loads(schema_bytes)
            Draft202012Validator.check_schema(schema)
            _validator = cast(
                _SchemaValidator,
                Draft202012Validator(
                    schema,
                    format_checker=_format_checker,
                ),
            )
        except json.JSONDecodeError, UnicodeError, SchemaError, TypeError:
            _raise_contract_error()
    return _validator


def _validate_frozen_schema(value: object) -> None:
    try:
        first_error = next(_schema_validator().iter_errors(value), None)
    except RecursionError:
        _raise_invalid("SCHEMA", "/", "recursion")
    if first_error is not None:
        pointer_parts: list[str] = []
        for component in first_error.absolute_path:
            if type(component) is int and component >= 0:
                pointer_parts.append(str(component))
            elif type(component) is str and _SAFE_ERROR_COMPONENT.fullmatch(component):
                pointer_parts.append(component)
            else:
                pointer_parts.append("member")
        pointer = "/" + "/".join(pointer_parts) if pointer_parts else "/"
        validator_keyword = first_error.validator
        keyword = (
            validator_keyword
            if type(validator_keyword) is str
            and _SAFE_ERROR_COMPONENT.fullmatch(validator_keyword)
            else "schema"
        )
        _raise_invalid("SCHEMA", pointer, keyword)


def _assert_unique_block_ids(content_ast: ContentAst) -> None:
    block_ids = [block.block_id for block in content_ast.blocks]
    if len(block_ids) != len(set(block_ids)):
        _raise_invalid("AST_POLICY", "/blocks", "unique_block_id")


def _generated_models_are_ready() -> bool:
    return _generated_models_ready


def _ensure_generated_models_ready() -> None:
    global _generated_models_ready

    if _generated_models_are_ready():
        return
    with _GENERATED_MODELS_LOCK:
        if _generated_models_are_ready():
            return
        try:
            for model_type in _SERIALIZER_REBUILD_MODELS:
                if model_type.model_rebuild(force=True, raise_errors=False) is False:
                    _raise_contract_error()
            if ContentAst.model_rebuild(force=True, raise_errors=False) is False:
                _raise_contract_error()
        except AttributeError, NameError, TypeError, ValueError:
            _raise_contract_error()
        _generated_models_ready = True


def load_content_ast(source: str | bytes | bytearray) -> ContentAst:
    """Load one Content AST v1 document without exposing rejected content.

    Duplicate JSON members, unknown schema versions, unknown fields, schema
    violations, generated-model drift, and duplicate ``block_id`` values all
    fail closed.  No article-template, claim-resolution, or publication-context
    policy is inferred here.
    """

    parsed = _parse_json(source)
    _validate_frozen_schema(parsed)
    _ensure_generated_models_ready()
    try:
        content_ast = ContentAst.model_validate(parsed)
    except AttributeError, TypeError, ValueError, ValidationError:
        _raise_invalid("MODEL", "/", "generated_type")
    _assert_unique_block_ids(content_ast)
    return content_ast


def dump_content_ast_json(content_ast: ContentAst) -> str:
    """Serialize a generated Content AST model to deterministic canonical JSON."""

    if type(content_ast) is not ContentAst:
        _raise_invalid("SERIALIZATION", "/", "model_type")
    _schema_validator()
    _ensure_generated_models_ready()
    try:
        value = content_ast.model_dump(
            mode="json",
            by_alias=True,
            exclude_unset=True,
            warnings=False,
        )
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except AttributeError, TypeError, ValueError, ValidationError:
        _raise_invalid("SERIALIZATION", "/", "generated_model")
    parsed = _parse_json(rendered)
    _validate_frozen_schema(parsed)
    try:
        projected_snapshot = ContentAst.model_validate(parsed)
        _assert_unique_block_ids(projected_snapshot)
    except ContentAstValidationError:
        raise
    except AttributeError, TypeError, ValueError, ValidationError:
        _raise_invalid("SERIALIZATION", "/", "generated_model")
    return f"{rendered}\n"


__all__ = [
    "ArticleType",
    "CONTENT_AST_SCHEMA_SHA256",
    "CONTENT_AST_SCHEMA_VERSION",
    "ContentAst",
    "ContentAstContractError",
    "ContentAstValidationError",
    "PublicationFlags",
    "dump_content_ast_json",
    "load_content_ast",
]
