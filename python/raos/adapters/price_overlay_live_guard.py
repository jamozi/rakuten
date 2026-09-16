"""Contract §8: refuse every path from this repository to the live site while Rakuten price
overlay values may be published.

The owner-direct publisher (``scripts/raos_wordpress_direct_publish.py``) and the deployment
operator (``scripts/raos_wordpress_deployment_operator.py``) keep their own copy of this check
because they answer with their own refusal codes; every other caller in the repository uses
this module, so one fix covers the editor MCP path, the public readback, the audits and the
legacy self-hosted operators. Node entry points use the operator's ``price-overlay-live-check``
command instead (``scripts/raos_price_overlay_live_check.mjs``).

Fail closed: run state that cannot be read, and a run directory that is a symlink or not a
directory, refuse as well.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Final

# The runs live in the owner checkout even when a command runs from a worktree (contract §8).
OWNER_CHECKOUT: Final = Path("/home/minami/rakuten")
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
RUNS_RELATIVE: Final = ".secrets/rakuten-price-refresh"
LIVE: Final = "PRICE_OVERLAY_LIVE"
STATE_INVALID: Final = "PRICE_OVERLAY_STATE_INVALID"


class PriceOverlayLive(RuntimeError):
    """Raised instead of reaching WordPress. ``code`` is ``LIVE`` or ``STATE_INVALID``."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def checkouts(extra: Iterable[Path | str | None] = ()) -> list[Path]:
    """Every checkout to look in: the caller's own, the fixed owner checkout, this repository."""

    found: list[Path] = []
    for value in (*extra, OWNER_CHECKOUT, REPOSITORY_ROOT):
        if value is None:
            continue
        path = Path(value)
        if path not in found:
            found.append(path)
    return found


def price_overlay_refusal(*extra: Path | str | None) -> str | None:
    """``None`` when no run may be live; a refusal code otherwise."""

    candidates = checkouts(extra)
    try:
        if not any(
            (checkout / RUNS_RELATIVE).exists()
            or (checkout / RUNS_RELATIVE).is_symlink()
            for checkout in candidates
        ):
            return None
        from raos.adapters.rakuten_price_refresh_client import live_run_ids
        from raos.domain.editorial.rakuten_price_refresh import RefreshError

        try:
            live = live_run_ids(candidates)
        except RefreshError:
            return STATE_INVALID
    except OSError:
        return STATE_INVALID
    return LIVE if live else None


def refuse_while_price_overlay_live(*extra: Path | str | None) -> None:
    code = price_overlay_refusal(*extra)
    if code is not None:
        raise PriceOverlayLive(code)
