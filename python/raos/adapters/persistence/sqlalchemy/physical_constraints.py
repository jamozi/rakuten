"""Fail-closed execution of generated PostgreSQL physical invariants.

The owner generator compiles every hash-bound physical ``CHECK`` expression to
an inert tuple AST.  This module interprets that closed AST without ``eval`` or
runtime SQL and installs guards around the explicit scalar mappers.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum
from functools import lru_cache, wraps
import json
import math
import re
from typing import Callable, NoReturn, TypeAlias, cast
from uuid import UUID

from raos.adapters.persistence.sqlalchemy.generated.physical_constraints import (
    CANONICAL_METRIC_UNITS,
    CHECKS_BY_RELATION,
    COLUMN_RULES_BY_RELATION,
    MAPPER_CALLABLES,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


class _ConstraintEvaluationError(RuntimeError):
    """Internal closed evaluator failure; never crosses the adapter boundary."""


CheckNode: TypeAlias = tuple[object, ...]
NumericValue: TypeAlias = int | Decimal


def _corrupt() -> NoReturn:
    raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None


def _invalid() -> NoReturn:
    raise _ConstraintEvaluationError from None


def _is_exact_dict(value: object) -> bool:
    return type(value) is dict


def _is_exact_tuple(value: object) -> bool:
    return type(value) is tuple


def _plain(value: object) -> object:
    """Unwrap approved nominal scalar/JSON values without accepting aggregates."""

    if value is None or type(value) in {bool, int, float, str, Decimal, UUID, date}:
        return value
    if type(value) is datetime:
        return value
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        result: dict[str, object] = {}
        for key, item in mapping.items():
            if type(key) is not str or key in result:
                _invalid()
            result[key] = _plain(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        return tuple(_plain(item) for item in sequence)
    value_type = type(value)
    if value_type.__module__.startswith("raos.domain.") and is_dataclass(value):
        value_fields = fields(value)
        if len(value_fields) == 1 and value_fields[0].name == "value":
            return _plain(getattr(value, "value"))
    _invalid()


def _validate_json(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        _invalid()
    if value is None or type(value) in {bool, str}:
        return
    if type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            _invalid()
        return
    if type(value) is Decimal:
        if not value.is_finite():
            _invalid()
        return
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        for key, item in mapping.items():
            if type(key) is not str:
                _invalid()
            _validate_json(item, depth=depth + 1)
        return
    if type(value) is tuple:
        sequence = cast(tuple[object, ...], value)
        for item in sequence:
            _validate_json(item, depth=depth + 1)
        return
    _invalid()


def _validate_column(value: object, rule: tuple[object, ...]) -> None:
    kind = rule[0]
    if kind == "text":
        if type(value) is not str:
            _invalid()
        return
    if kind == "boolean":
        if type(value) is not bool:
            _invalid()
        return
    if kind == "integer":
        minimum = rule[1]
        maximum = rule[2]
        if (
            type(value) is not int
            or type(minimum) is not int
            or type(maximum) is not int
            or not minimum <= value <= maximum
        ):
            _invalid()
        return
    if kind == "numeric":
        if type(value) is not Decimal or not value.is_finite():
            _invalid()
        precision = rule[1]
        scale = rule[2]
        if precision is None and scale is None:
            return
        if type(precision) is not int or type(scale) is not int:
            _invalid()
        try:
            with localcontext() as context:
                context.prec = max(80, precision + scale + 2)
                quantum = Decimal(1).scaleb(-scale)
                quantized = value.quantize(quantum)
        except InvalidOperation:
            _invalid()
        if quantized != value:
            _invalid()
        integer_digits = 0 if quantized.is_zero() else max(quantized.adjusted() + 1, 0)
        if integer_digits > precision - scale:
            _invalid()
        return
    if kind == "uuid":
        if type(value) is not UUID:
            _invalid()
        return
    if kind == "date":
        if type(value) is not date:
            _invalid()
        return
    if kind == "timestamptz":
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            _invalid()
        return
    if kind == "jsonb":
        _validate_json(value)
        return
    if kind == "text_array":
        if not _is_exact_tuple(value):
            _invalid()
        sequence = cast(tuple[object, ...], value)
        if any(item is not None and type(item) is not str for item in sequence):
            _invalid()
        return
    _invalid()


def _truth(value: object) -> bool | None:
    if value is None or type(value) is bool:
        return value
    _invalid()


def _and(left: object, right: object) -> bool | None:
    left_truth = _truth(left)
    right_truth = _truth(right)
    if left_truth is False or right_truth is False:
        return False
    if left_truth is None or right_truth is None:
        return None
    return True


def _or(left: object, right: object) -> bool | None:
    left_truth = _truth(left)
    right_truth = _truth(right)
    if left_truth is True or right_truth is True:
        return True
    if left_truth is None or right_truth is None:
        return None
    return False


def _equal(left: object, right: object) -> bool | None:
    if left is None or right is None:
        return None
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    return left == right


def _compare(operator: str, left: object, right: object) -> bool | None:
    if operator in {"=", "<>"}:
        equal = _equal(left, right)
        if equal is None:
            return None
        return equal if operator == "=" else not equal
    if left is None or right is None:
        return None
    if operator in {">", ">=", "<", "<="}:
        return _ordered_compare(operator, left, right)
    if operator == "~":
        if type(left) is not str or type(right) is not str:
            _invalid()
        return _regex(right).search(left) is not None
    _invalid()


def _ordered_compare(operator: str, left: object, right: object) -> bool:
    if type(left) in {int, Decimal} and type(right) in {int, Decimal}:
        left_numeric = _numeric(left)
        right_numeric = _numeric(right)
        left_decimal = (
            Decimal(left_numeric) if isinstance(left_numeric, int) else left_numeric
        )
        right_decimal = (
            Decimal(right_numeric) if isinstance(right_numeric, int) else right_numeric
        )
        return _ordered_decimal(operator, left_decimal, right_decimal)
    if type(left) is str and type(right) is str:
        return _ordered_text(operator, left, right)
    if type(left) is date and type(right) is date:
        return _ordered_date(operator, left, right)
    if type(left) is datetime and type(right) is datetime:
        return _ordered_datetime(operator, left, right)
    _invalid()


def _ordered_decimal(operator: str, left: Decimal, right: Decimal) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    _invalid()


def _ordered_text(operator: str, left: str, right: str) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    _invalid()


def _ordered_date(operator: str, left: date, right: date) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    _invalid()


def _ordered_datetime(operator: str, left: datetime, right: datetime) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    _invalid()


def _node(value: object) -> CheckNode:
    if type(value) is not tuple:
        _invalid()
    return cast(tuple[object, ...], value)


def _numeric(value: object) -> NumericValue:
    if type(value) is int or type(value) is Decimal:
        return value
    _invalid()


@lru_cache(maxsize=128)
def _regex(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error:
        _invalid()


def _json_type(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is dict:
        return "object"
    if type(value) is tuple:
        return "array"
    if type(value) is str:
        return "string"
    if type(value) is bool:
        return "boolean"
    if type(value) in {int, float, Decimal}:
        return "number"
    if value is _JSON_NULL:
        return "null"
    _invalid()


_JSON_NULL = object()


def _json_get(value: object, key: object, *, text: bool) -> object:
    if value is None or key is None:
        return None
    found: object
    if _is_exact_dict(value) and type(key) is str:
        mapping = cast(dict[object, object], value)
        if key not in mapping:
            return None
        found = mapping[key]
    elif _is_exact_tuple(value) and type(key) is int:
        sequence = cast(tuple[object, ...], value)
        try:
            found = sequence[key]
        except IndexError:
            return None
    else:
        _invalid()
    if found is None:
        found = _JSON_NULL
    if not text:
        return found
    if found is _JSON_NULL:
        return None
    if type(found) is str:
        return found
    if type(found) is bool:
        return "true" if found else "false"
    if type(found) in {int, float, Decimal}:
        return str(found)
    try:
        return json.dumps(
            found, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    except TypeError, ValueError:
        _invalid()


def _cast_value(cast_type: str, value: object) -> object:
    if value is None:
        return None
    if cast_type == "text":
        if type(value) is str:
            return value
        if type(value) in {int, Decimal}:
            return str(value)
        _invalid()
    if cast_type == "numeric":
        if type(value) is Decimal:
            return value
        if type(value) is int:
            return Decimal(value)
        if type(value) is str:
            try:
                parsed = Decimal(value)
            except InvalidOperation:
                _invalid()
            if not parsed.is_finite():
                _invalid()
            return parsed
        _invalid()
    if cast_type == "integer":
        if type(value) is int:
            return value
        if type(value) is Decimal and value == value.to_integral_value():
            return int(value)
        if type(value) is str and re.fullmatch(r"[+-]?\d+", value) is not None:
            return int(value)
        _invalid()
    if cast_type == "jsonb":
        if type(value) is not str:
            _invalid()
        try:
            parsed_json = cast(object, json.loads(value))
        except json.JSONDecodeError:
            _invalid()
        return _plain(parsed_json)
    _invalid()


def _call(name: str, arguments: tuple[object, ...]) -> object:
    if name == "coalesce":
        return next((value for value in arguments if value is not None), None)
    if name == "num_nonnulls":
        return sum(value is not None for value in arguments)
    if name in {"jsonb_typeof", "pg_catalog.jsonb_typeof"}:
        return _json_type(arguments[0])
    if arguments[0] is None:
        return None
    if name == "btrim":
        if type(arguments[0]) is not str:
            _invalid()
        return arguments[0].strip(" ")
    if name == "length":
        if type(arguments[0]) is not str:
            _invalid()
        return len(arguments[0])
    if name == "cardinality":
        if type(arguments[0]) is not tuple:
            _invalid()
        return len(cast(tuple[object, ...], arguments[0]))
    if name == "array_position":
        if type(arguments[0]) is not tuple:
            _invalid()
        sequence = cast(tuple[object, ...], arguments[0])
        for index, item in enumerate(sequence, 1):
            if item is None and arguments[1] is None:
                return index
            if _equal(item, arguments[1]) is True:
                return index
        return None
    if name == "ai.canonical_metric_unit":
        if type(arguments[0]) is not str:
            _invalid()
        return CANONICAL_METRIC_UNITS.get(arguments[0])
    _invalid()


def _evaluate(node: CheckNode, row: Mapping[str, object]) -> object:
    if not node or type(node[0]) is not str:
        _invalid()
    kind = node[0]
    if kind == "null":
        return None
    if kind == "boolean":
        return node[1]
    if kind == "string":
        return node[1]
    if kind == "number":
        literal = node[1]
        if type(literal) is not str:
            _invalid()
        return Decimal(literal) if "." in literal else int(literal)
    if kind == "column":
        column = node[1]
        if type(column) is not str or column not in row:
            _invalid()
        return row[column]
    if kind == "array":
        members = node[1]
        if not _is_exact_tuple(members):
            _invalid()
        return tuple(_evaluate(_node(member), row) for member in _node(members))
    if kind == "cast":
        cast_type = node[1]
        if type(cast_type) is not str:
            _invalid()
        return _cast_value(cast_type, _evaluate(_node(node[2]), row))
    if kind == "unary":
        operator = node[1]
        value = _evaluate(_node(node[2]), row)
        if operator == "not":
            truth = _truth(value)
            return None if truth is None else not truth
        if value is None:
            return None
        if operator == "+" and type(value) in {int, Decimal}:
            return _numeric(value)
        if operator == "-" and type(value) in {int, Decimal}:
            return -_numeric(value)
        _invalid()
    if kind == "binary":
        operator = node[1]
        if type(operator) is not str:
            _invalid()
        left = _evaluate(_node(node[2]), row)
        right = _evaluate(_node(node[3]), row)
        if operator == "and":
            return _and(left, right)
        if operator == "or":
            return _or(left, right)
        if operator in {"=", "<>", ">", ">=", "<", "<=", "~"}:
            return _compare(operator, left, right)
        if left is None or right is None:
            return None
        if (
            operator == "+"
            and type(left) in {int, Decimal}
            and type(right)
            in {
                int,
                Decimal,
            }
        ):
            return _numeric(left) + _numeric(right)
        if operator == "-":
            if (
                _is_exact_dict(left)
                and _is_exact_tuple(right)
                and all(type(item) is str for item in _node(right))
            ):
                mapping = cast(dict[object, object], left)
                excluded = frozenset(cast(str, item) for item in _node(right))
                return {
                    key: value for key, value in mapping.items() if key not in excluded
                }
            if type(left) in {int, Decimal} and type(right) in {int, Decimal}:
                return _numeric(left) - _numeric(right)
            _invalid()
        if (
            operator == "*"
            and type(left) in {int, Decimal}
            and type(right)
            in {
                int,
                Decimal,
            }
        ):
            return _numeric(left) * _numeric(right)
        if (
            operator == "/"
            and type(left) in {int, Decimal}
            and type(right)
            in {
                int,
                Decimal,
            }
        ):
            if right == 0:
                _invalid()
            with localcontext() as context:
                context.prec = 80
                left_numeric = _numeric(left)
                right_numeric = _numeric(right)
                left_decimal = (
                    Decimal(left_numeric) if type(left_numeric) is int else left_numeric
                )
                right_decimal = (
                    Decimal(right_numeric)
                    if type(right_numeric) is int
                    else right_numeric
                )
                return left_decimal / right_decimal
        if operator == "->":
            return _json_get(left, right, text=False)
        if operator == "->>":
            return _json_get(left, right, text=True)
        if operator == "?&":
            if not _is_exact_tuple(right):
                _invalid()
            right_values = _node(right)
            if any(type(item) is not str for item in right_values):
                _invalid()
            required = tuple(cast(str, item) for item in right_values)
            if _is_exact_dict(left):
                mapping = cast(dict[object, object], left)
                return all(item in mapping for item in required)
            if _is_exact_tuple(left):
                sequence = _node(left)
                return all(item in sequence for item in required)
            _invalid()
        if operator == "&&":
            if not _is_exact_tuple(left) or not _is_exact_tuple(right):
                _invalid()
            left_values = _node(left)
            right_values = _node(right)
            return any(item in right_values for item in left_values)
        _invalid()
    if kind == "is_null":
        negated = node[1]
        if type(negated) is not bool:
            _invalid()
        result = _evaluate(_node(node[2]), row) is None
        return not result if negated else result
    if kind == "is_distinct":
        negated = node[1]
        if type(negated) is not bool:
            _invalid()
        left = _evaluate(_node(node[2]), row)
        right = _evaluate(_node(node[3]), row)
        if left is None and right is None:
            result = False
        elif left is None or right is None:
            result = True
        else:
            result = _equal(left, right) is not True
        return not result if negated else result
    if kind == "between":
        value = _evaluate(_node(node[1]), row)
        lower = _evaluate(_node(node[2]), row)
        upper = _evaluate(_node(node[3]), row)
        return _and(_compare(">=", value, lower), _compare("<=", value, upper))
    if kind == "in":
        value = _evaluate(_node(node[1]), row)
        members = node[2]
        if not _is_exact_tuple(members):
            _invalid()
        results = tuple(
            _equal(value, _evaluate(_node(member), row)) for member in _node(members)
        )
        if True in results:
            return True
        return None if None in results else False
    if kind == "quantified":
        operator = node[1]
        quantifier = node[2]
        if type(operator) is not str or quantifier not in {"ANY", "ALL"}:
            _invalid()
        value = _evaluate(_node(node[3]), row)
        members = _evaluate(_node(node[4]), row)
        if members is None:
            return None
        if not _is_exact_tuple(members):
            _invalid()
        results = tuple(_compare(operator, value, member) for member in _node(members))
        if quantifier == "ANY":
            if True in results:
                return True
            return None if None in results else False
        if False in results:
            return False
        return None if None in results else True
    if kind == "call":
        name = node[1]
        arguments = node[2]
        if type(name) is not str or not _is_exact_tuple(arguments):
            _invalid()
        return _call(
            name,
            tuple(_evaluate(_node(argument), row) for argument in _node(arguments)),
        )
    _invalid()


def validate_physical_row(relation: str, raw_row: Mapping[str, object]) -> None:
    """Validate one complete mapper row against types and all physical checks."""

    try:
        column_rules = COLUMN_RULES_BY_RELATION[relation]
        checks = CHECKS_BY_RELATION[relation]
        expected_columns = tuple(rule[0] for rule in column_rules)
        if type(cast(object, raw_row)) is not dict:
            _invalid()
        raw_mapping = cast(dict[str, object], raw_row)
        if len(raw_mapping) != len(expected_columns) or set(raw_mapping) != set(
            expected_columns
        ):
            _invalid()
        row = {column: _plain(raw_mapping[column]) for column in expected_columns}
        for column, nullable, rule in column_rules:
            value = row[column]
            if value is None:
                if nullable is not True:
                    _invalid()
                continue
            _validate_column(value, cast(tuple[object, ...], rule))
        for name, expression_sha256, ast in checks:
            if (
                type(name) is not str
                or type(expression_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expression_sha256) is None
            ):
                _invalid()
            result = _evaluate(cast(tuple[object, ...], ast), row)
            if result is False or (result is not None and result is not True):
                _invalid()
    except PersistenceError:
        raise
    except Exception:
        _corrupt()


def _from_row_guard(
    function: Callable[..., object], relation: str
) -> Callable[..., object]:
    @wraps(function)
    def guarded(*args: object, **kwargs: object) -> object:
        if args:
            _corrupt()
        validate_physical_row(relation, kwargs)
        return function(**kwargs)

    setattr(guarded, "__raos_physical_constraint_guard__", True)
    return guarded


def _to_row_guard(
    function: Callable[..., object], relation: str, columns: tuple[str, ...]
) -> Callable[..., object]:
    @wraps(function)
    def guarded(*args: object, **kwargs: object) -> object:
        result = function(*args, **kwargs)
        if not _is_exact_tuple(result):
            _corrupt()
        items = cast(tuple[object, ...], result)
        if len(items) != len(columns):
            _corrupt()
        validate_physical_row(
            relation,
            dict(zip(columns, items, strict=True)),
        )
        return items

    setattr(guarded, "__raos_physical_constraint_guard__", True)
    return guarded


def install_mapper_physical_constraint_guards(
    namespace: MutableMapping[str, object],
) -> None:
    """Install every generated mapper guard for exactly one schema module."""

    try:
        module_name = namespace["__name__"]
        if type(module_name) is not str:
            _invalid()
        schema = module_name.rsplit(".", 1)[-1]
        expected = {
            name: spec
            for name, spec in MAPPER_CALLABLES.items()
            if spec[0].split(".", 1)[0] == schema
        }
        actual = {
            name
            for name, value in namespace.items()
            if name.startswith(f"map_{schema}_")
            and (name.endswith("_from_row") or name.endswith("_to_row"))
            and callable(value)
        }
        if not expected or actual != set(expected):
            _invalid()
        for name, spec in expected.items():
            function = namespace[name]
            if not callable(function) or getattr(
                function, "__raos_physical_constraint_guard__", False
            ):
                _invalid()
            relation, direction, columns = spec
            if (
                type(relation) is not str
                or direction not in {"from_row", "to_row"}
                or type(columns) is not tuple
                or any(type(column) is not str for column in columns)
            ):
                _invalid()
            if direction == "from_row":
                namespace[name] = _from_row_guard(function, relation)
            else:
                namespace[name] = _to_row_guard(function, relation, columns)
    except PersistenceError:
        raise
    except Exception:
        _corrupt()


__all__ = [
    "install_mapper_physical_constraint_guards",
    "validate_physical_row",
]
