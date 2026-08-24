"""Editorial domain types backed by the frozen RAOS content contracts.

The facade stays lazy so importing nominal editorial identities does not initialize
the full generated Content AST model graph.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any, Final


if TYPE_CHECKING:
    from raos.domain.editorial.content_ast import (
        ArticleType,
        CONTENT_AST_SCHEMA_SHA256,
        CONTENT_AST_SCHEMA_VERSION,
        ContentAst,
        ContentAstContractError,
        ContentAstValidationError,
        PublicationFlags,
        dump_content_ast_json,
        load_content_ast,
    )

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

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    name: ("raos.domain.editorial.content_ast", name) for name in __all__
}


def __getattr__(name: str) -> Any:
    """Resolve a documented facade export without eager generated-model imports."""

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy facade names to interactive and inspection consumers."""

    return sorted((*globals(), *_LAZY_EXPORTS))
