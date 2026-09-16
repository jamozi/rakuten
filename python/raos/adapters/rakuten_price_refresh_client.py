"""Owner-private I/O for the Rakuten price refresh (KS-020).

Contains the only network call (one itemCode GET per plan entry, behind an
injected transport), the credential reader, the 0600 private store under the
owner checkout ``.secrets`` directory, and the tracked-file leak scan. Nothing
here prints or returns credential values.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import ssl
import stat
import subprocess
import time
from typing import Any, Final, Protocol
from urllib.parse import quote

from raos.domain.editorial.rakuten_price_refresh import (
    API_HOST,
    CREDENTIAL_PROFILE,
    CREDENTIAL_RELATIVE,
    MAX_CACHE_AGE,
    MAX_RESPONSE_BYTES,
    MIN_REQUEST_INTERVAL_SECONDS,
    OBSERVATION_SCHEMA,
    PREPARED_CANDIDATES_KEY,
    PRIVATE_ROOT_RELATIVE,
    PURGE_PUBLISH_HASH_KEYS,
    PURGED_SCHEMA,
    RUN_ID_PATTERN,
    UTC,
    RefreshError,
    contextual_leaks,
    fail,
    iso,
    leak_needles,
    parse_time,
    redact_approval,
    request_path,
    require_run_id,
    sha256_hex,
    validate_approval,
    validate_overlay,
)

USER_AGENT: Final = "RAOS-KS020-price-refresh/1"
# The one place the key travels: the Rakuten request header, never the query (ST-0505).
ACCESS_KEY_HEADER: Final = "accessKey"
CONNECT_TIMEOUT_SECONDS: Final = 10.0
MAX_CREDENTIAL_BYTES: Final = 4096
MAX_PRIVATE_JSON_BYTES: Final = 8_000_000
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
# scripts/raos_wordpress_direct_publish.py PRIVATE: candidate directories named by candidate_id.
OWNER_DIRECT_CANDIDATE_RELATIVE: Final = ".secrets/wordpress-mcp/owner-direct-v1"
# scripts/raos_wordpress_direct_preview.py: frozen display themes (theme-<tree>) and fixtures.
PREVIEW_PRIVATE_RELATIVE: Final = ".secrets/wordpress-direct-preview"
# scripts/raos_wordpress_price_overlay.py _materialize: an interrupted derived candidate is
# left as .staging-<candidate_id>/ (injected bodies, injected theme) before candidate.json.
STAGING_PREFIX: Final = ".staging-"
# A replace write leaves <file>.tmp only when it was interrupted between create and rename;
# a younger one may belong to a concurrent writer and is never removed.
STALE_TMP_SECONDS: Final = 60
# scripts/raos_wordpress_direct_preview.py freezes the injected display theme as
# ``<preview base>/theme-<injected tree sha256>`` at *preview* time - before any publish record
# exists. The needle sweep takes its injected hashes from the approval's publish records, so a
# run that is previewed and never published left that copy (and the injected body hashes inside
# it) where nothing could find it. The preview records what it is about to freeze in the run's
# own directory instead, and the sweep deletes it from there (contract §5).
PREVIEW_COPIES_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_PREVIEW_COPIES_V1"
PREVIEW_COPIES_FILE: Final = "preview-copies.v1.json"
# A run previews a handful of candidates at most; a record that grew past this is not one of
# ours, and the sweep must never be handed an unbounded list of paths to delete.
MAX_PREVIEW_COPIES: Final = 64


def require_preview_copy_name(relative: object) -> str:
    """One path segment directly under the preview base: all a preview may record.

    ``theme-<tree>`` today. Refused here rather than in ``delete_preview_copy``, so a
    hand-edited record cannot aim the sweep at a path outside the preview base. Each clause
    carries its own case: ``name`` is the last segment, so it differs from the whole string
    for anything holding ``/`` and is empty for ``"."``; the length bound refuses ``""``,
    which ``name`` lets through; ``".."`` is a segment as far as ``name`` is concerned, so it
    is named; and ``\\`` - legal on POSIX, a separator elsewhere - is refused so a recorded
    name means one thing wherever the record is read.
    """
    if (
        not isinstance(relative, str)
        or not 1 <= len(relative) <= 255
        or PurePosixPath(relative).name != relative
        or relative == ".."
        or "\\" in relative
    ):
        fail("PREVIEW_COPY_NAME_INVALID")
    return relative


@dataclass(frozen=True, slots=True, repr=False)
class RefreshCredentials:
    application_id: str
    access_key: str

    def __post_init__(self) -> None:
        for value in (self.application_id, self.access_key):
            if (
                type(value) is not str
                or not 1 <= len(value) <= 256
                or any(ord(c) < 0x21 or ord(c) > 0x7E for c in value)
            ):
                fail("CREDENTIAL_UNSAFE")

    def __repr__(self) -> str:
        return "RefreshCredentials(<redacted>)"

    __str__ = __repr__

    def reflections(self) -> tuple[bytes, ...]:
        forms = set()
        for value in (self.application_id, self.access_key):
            forms.add(value.encode())
            forms.add(quote(value, safe="").encode())
        return tuple(sorted(forms))


def _read_private_bytes(path: Path, maximum: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        fail("PRIVATE_FILE_UNAVAILABLE")
    except OSError:
        fail("PRIVATE_FILE_UNSAFE")
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != PRIVATE_FILE_MODE
            or info.st_nlink != 1
            or not 1 <= info.st_size <= maximum
        ):
            fail("PRIVATE_FILE_UNSAFE")
        raw = os.read(descriptor, info.st_size + 1)
        if len(raw) != info.st_size:
            fail("PRIVATE_FILE_UNSAFE")
        return raw
    finally:
        os.close(descriptor)


def read_refresh_credentials(owner_checkout: Path) -> RefreshCredentials:
    """Read application_id / access_key only; affiliate_id is never loaded into use."""
    try:
        raw = _read_private_bytes(
            owner_checkout / CREDENTIAL_RELATIVE, MAX_CREDENTIAL_BYTES
        )
    except ValueError as error:
        code = getattr(error, "code", "")
        fail(
            "CREDENTIAL_UNAVAILABLE"
            if code == "PRIVATE_FILE_UNAVAILABLE"
            else "CREDENTIAL_UNSAFE"
        )
    try:
        document = json.loads(raw)
    except ValueError:
        fail("CREDENTIAL_UNSAFE")
    if (
        not isinstance(document, dict)
        or document.get("profile") != CREDENTIAL_PROFILE
        or not isinstance(document.get("application_id"), str)
        or not isinstance(document.get("access_key"), str)
    ):
        fail("CREDENTIAL_UNSAFE")
    return RefreshCredentials(document["application_id"], document["access_key"])


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class Transport(Protocol):
    def get(
        self, *, host: str, path: str, headers: Mapping[str, str], max_bytes: int
    ) -> HttpResult: ...


class SystemHttpsTransport:
    """TLS >= 1.2, certificate and hostname verified, no proxy, never follows redirects."""

    def get(
        self, *, host: str, path: str, headers: Mapping[str, str], max_bytes: int
    ) -> HttpResult:
        if host != API_HOST:
            fail("HOST_NOT_ALLOWED")
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        connection = http.client.HTTPSConnection(
            host, 443, timeout=CONNECT_TIMEOUT_SECONDS, context=context
        )
        try:
            connection.request("GET", path, headers=dict(headers))
            response = connection.getresponse()
            body = response.read(max_bytes + 1)
            return HttpResult(response.status, tuple(response.getheaders()), body)
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class FetchedObservation:
    http_status: int
    body: str | None
    observed_at: datetime


class PriceRefreshClient:
    def __init__(
        self,
        transport: Transport,
        credentials: RefreshCredentials,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._credentials = credentials
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: float | None = None

    def __repr__(self) -> str:
        return "PriceRefreshClient(<redacted>)"

    def fetch(self, item_code: str) -> FetchedObservation:
        path = request_path(item_code, self._credentials.application_id)
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
            "User-Agent": USER_AGENT,
            ACCESS_KEY_HEADER: self._credentials.access_key,
        }
        if self._last is not None:
            wait = MIN_REQUEST_INTERVAL_SECONDS - (self._monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._monotonic()
        observed_at = self._clock()
        try:
            result = self._transport.get(
                host=API_HOST, path=path, headers=headers, max_bytes=MAX_RESPONSE_BYTES
            )
        except BaseException as error:  # noqa: BLE001 - never surface transport text (may echo the URL)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            return FetchedObservation(0, None, observed_at)
        self._last = self._monotonic()
        lowered = {k.lower(): v for k, v in result.headers}
        if 300 <= result.status < 400 or "location" in lowered:
            fail("RAKUTEN_REDIRECT_REFUSED")
        if len(result.body) > MAX_RESPONSE_BYTES:
            fail("RAKUTEN_RESPONSE_TOO_LARGE")
        header_bytes = "\n".join(v for _k, v in result.headers).encode(
            "utf-8", "replace"
        )
        if any(
            secret in result.body or secret in header_bytes
            for secret in self._credentials.reflections()
        ):
            fail("RAKUTEN_CREDENTIAL_REFLECTED")
        if result.status != 200:
            # Error bodies (and 429/5xx in particular) are never persisted.
            return FetchedObservation(result.status, None, observed_at)
        content_type = lowered.get("content-type", "")
        if not content_type.split(";")[0].strip().lower() == "application/json":
            return FetchedObservation(200, None, observed_at)
        try:
            text = result.body.decode("utf-8")
        except UnicodeDecodeError:
            return FetchedObservation(200, None, observed_at)
        return FetchedObservation(200, text, observed_at)


def observation_record(
    run_id: str, offer_id: str, item_code: str, fetched: FetchedObservation
) -> dict[str, Any]:
    return {
        "schema": OBSERVATION_SCHEMA,
        "run_id": require_run_id(run_id),
        "offer_id": offer_id,
        "item_code": item_code,
        "http_status": fetched.http_status,
        "observed_at": iso(fetched.observed_at),
        "body_sha256": sha256_hex(fetched.body.encode("utf-8"))
        if fetched.body is not None
        else None,
        "body": fetched.body,
    }


# ---------------------------------------------------------------------------
# Private store
# ---------------------------------------------------------------------------

GitRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def _git(
    root: Path, *args: str, runner: GitRunner = subprocess.run
) -> subprocess.CompletedProcess[bytes]:
    return runner(["git", "-C", str(root), *args], capture_output=True, check=False)


class PrivateStore:
    """``<owner checkout>/.secrets/rakuten-price-refresh/<run_id>/`` (dirs 0700, files 0600)."""

    def __init__(
        self, owner_checkout: Path, *, runner: GitRunner = subprocess.run
    ) -> None:
        self._runner = runner
        try:
            valid = (
                owner_checkout.is_absolute()
                and owner_checkout.is_dir()
                and not owner_checkout.is_symlink()
                and owner_checkout.resolve(strict=True) == owner_checkout
                and (owner_checkout / ".secrets").is_dir()
                and not (owner_checkout / ".secrets").is_symlink()
            )
        except OSError:
            valid = False
        if not valid:
            fail("OWNER_CHECKOUT_INVALID")
        self.owner_checkout = owner_checkout
        self.root = owner_checkout / PRIVATE_ROOT_RELATIVE

    def run_directory(self, run_id: str) -> Path:
        return self.root / require_run_id(run_id)

    def require_untracked_ignored(self, path: Path) -> None:
        relative = path.relative_to(self.owner_checkout).as_posix()
        ignored = _git(
            self.owner_checkout,
            "check-ignore",
            "-q",
            "--no-index",
            "--",
            relative,
            runner=self._runner,
        )
        tracked = _git(
            self.owner_checkout,
            "ls-files",
            "--error-unmatch",
            "--",
            relative,
            runner=self._runner,
        )
        if ignored.returncode != 0 or tracked.returncode == 0:
            fail("PRIVATE_PATH_NOT_GIT_IGNORED")

    def _ensure_directory(self, directory: Path) -> None:
        current = self.owner_checkout / ".secrets"
        for part in directory.relative_to(current).parts:
            current = current / part
            if current.is_symlink():
                fail("PRIVATE_PATH_UNSAFE")
            if not current.exists():
                current.mkdir(mode=PRIVATE_DIRECTORY_MODE)
            if (
                not current.is_dir()
                or stat.S_IMODE(current.stat().st_mode) != PRIVATE_DIRECTORY_MODE
            ):
                fail("PRIVATE_PATH_UNSAFE")

    def write_json(self, path: Path, value: object, *, replace: bool = False) -> None:
        if self.root not in path.parents:
            fail("PRIVATE_PATH_UNSAFE")
        self.require_untracked_ignored(path)
        self._ensure_directory(path.parent)
        payload = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        target = path.with_name(path.name + ".tmp") if replace else path
        if replace:
            self._remove_stale_tmp(target)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(target, flags, PRIVATE_FILE_MODE)
        except FileExistsError:
            fail("PRIVATE_FILE_EXISTS")
        try:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if replace:
            os.replace(target, path)

    def _remove_stale_tmp(self, target: Path) -> bool:
        """Remove a leftover ``<file>.tmp`` of an interrupted replace write.

        Only a regular 0600 file of this user that is older than STALE_TMP_SECONDS is
        removed; a younger one may be a concurrent write (PRIVATE_TMP_BUSY), anything else
        is refused (PRIVATE_PATH_UNSAFE). The leftover can hold the injected hashes of an
        interrupted approval write, so it is deleted, never renamed into place.
        """
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            return False
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            fail("PRIVATE_PATH_UNSAFE")
        if time.time() - metadata.st_mtime < STALE_TMP_SECONDS:
            fail("PRIVATE_TMP_BUSY")
        target.unlink()
        return True

    def run_tmp_files(self, run_id: str) -> list[Path]:
        directory = self.run_directory(run_id)
        if directory.is_symlink() or not directory.is_dir():
            return []
        return sorted(directory.glob("*.tmp"))

    def remove_stale_tmp_files(self, run_id: str) -> int:
        return sum(self._remove_stale_tmp(path) for path in self.run_tmp_files(run_id))

    def read_json(self, path: Path) -> Any:
        if self.root not in path.parents:
            fail("PRIVATE_PATH_UNSAFE")
        return json.loads(_read_private_bytes(path, MAX_PRIVATE_JSON_BYTES))

    def raw_records(self, run_id: str) -> list[dict[str, Any]]:
        directory = self.run_directory(run_id) / "raw"
        if not directory.is_dir() or directory.is_symlink():
            fail("RAW_OBSERVATIONS_MISSING")
        return [self.read_json(p) for p in sorted(directory.glob("*.json"))]

    def delete_raw(self, run_id: str) -> int:
        directory = self.run_directory(run_id) / "raw"
        if not directory.exists():
            return 0
        if directory.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        count = len(list(directory.iterdir()))
        shutil.rmtree(directory)
        return count

    def run_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and not p.is_symlink()
        )

    def _safe_base(self, relative: str) -> Path:
        current = self.owner_checkout
        for part in PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                fail("PRIVATE_PATH_UNSAFE")
        return current

    def owner_direct_candidates_containing(self, needles: Sequence[str]) -> list[str]:
        """Candidate directory names that may hold injected bytes.

        Every ``.staging-*`` directory (an interrupted derived candidate: its injected theme
        carries only hashes no record names yet), and every candidate directory any of whose
        files (candidate.json, journal.json, preview.json, bodies/, theme/, *.tmp ...) carries
        a needle.
        """
        base = self._safe_base(OWNER_DIRECT_CANDIDATE_RELATIVE)
        if not base.is_dir():
            return []
        variants = _needle_variants(needles)
        found = []
        for directory in sorted(base.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                continue
            if directory.name.startswith(STAGING_PREFIX) or (
                variants
                and any(_file_contains(p, variants) for p in sorted(directory.rglob("*")))
            ):
                found.append(directory.name)
        return found

    def preview_copies_containing(self, needles: Sequence[str]) -> list[str]:
        """Preview paths (relative to the preview directory) that carry any needle.

        A frozen display theme ``theme-<tree>`` is reported as a whole when any of its
        files does (the injected runtime JSON holds injected body hashes, functions.php the
        rebound runtime hash); fixture files are reported one by one.

        A file directly under the base is reported by itself: the preview's own bookkeeping
        lands there (a ``compose.override.yaml`` naming the candidate directory and the frozen
        theme, the ``.tmp`` an interrupted atomic write leaves beside it), and until round 11
        nothing in this sweep ever looked at it, so those ids outlived the purge that redacted
        them from the approval record. Directories that are neither ``theme-*`` nor ``fixtures``
        (``downloads``, ``plugins``, ``media``) are still not walked: they hold the pinned Yoast
        archive and the mirrored thumbnails, never injected bytes.
        """
        base = self._safe_base(PREVIEW_PRIVATE_RELATIVE)
        variants = _needle_variants(needles)
        if not base.is_dir() or not variants:
            return []
        found = []
        for entry in sorted(base.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir() and entry.name.startswith("theme-"):
                if any(_file_contains(p, variants) for p in sorted(entry.rglob("*"))):
                    found.append(entry.name)
            elif entry.is_dir() and entry.name == "fixtures":
                found.extend(
                    p.relative_to(base).as_posix()
                    for p in sorted(entry.rglob("*"))
                    if _file_contains(p, variants)
                )
            elif entry.is_file() and _file_contains(entry, variants):
                found.append(entry.name)
        return found

    def delete_preview_copy(self, relative: str) -> bool:
        base = self._safe_base(PREVIEW_PRIVATE_RELATIVE)
        parts = PurePosixPath(relative).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            fail("PRIVATE_PATH_UNSAFE")
        current = base
        for part in parts:
            current = current / part
            if current.is_symlink():
                fail("PRIVATE_PATH_UNSAFE")
        # ``theme-*`` and the ``fixtures`` subtree are deleted as before; a *file* directly
        # under the base (the preview's compose override, an interrupted ``.tmp``) is deleted
        # as a file, which is what ``preview_copies_containing`` now reports. Never a directory
        # of another name: ``downloads``, ``plugins`` and ``media`` stay whole.
        if not (
            (len(parts) == 1 and parts[0].startswith("theme-"))
            or parts[0] == "fixtures"
            or (len(parts) == 1 and current.is_file())
        ):
            fail("PRIVATE_PATH_UNSAFE")
        if current.is_dir():
            shutil.rmtree(current)
            return True
        if current.is_file():
            current.unlink()
            return True
        return False

    def preview_copy_exists(self, relative: str) -> bool:
        """Whether a *recorded* preview copy is still on disk (symlinks count as present).

        Never follows a link and never reads: a symlink where the copy should be is reported
        as present so ``delete_preview_copy`` gets to refuse it (PRIVATE_PATH_UNSAFE) instead
        of the run quietly reaching PURGED.
        """
        path = self.owner_checkout / PREVIEW_PRIVATE_RELATIVE / require_preview_copy_name(relative)
        return path.is_symlink() or path.exists()

    def delete_run_file(self, run_id: str, name: str) -> bool:
        """Delete one bookkeeping file of a run directory (the preview-copy record).

        The record names ``theme-<injected tree sha256>``, so it is price-recoverable itself
        and has to die with the copies it points at.
        """
        if PurePosixPath(name).name != name or name in {"", ".", ".."}:
            fail("PRIVATE_PATH_UNSAFE")
        directory = self.run_directory(run_id)
        if directory.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        path = directory / name
        if path.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        if not path.is_file():
            return False
        path.unlink()
        return True

    def delete_owner_direct_candidate(self, candidate_id: object) -> bool:
        """Delete one publisher candidate directory (injected bodies, runtime, theme, journal):
        ``<candidate_id>`` or an interrupted ``.staging-<name>``."""
        if not isinstance(candidate_id, str):
            return False
        staging = (
            candidate_id.startswith(STAGING_PREFIX)
            and len(candidate_id) > len(STAGING_PREFIX)
            and PurePosixPath(candidate_id).name == candidate_id
        )
        if not staging and (
            len(candidate_id) != 64 or any(c not in "0123456789abcdef" for c in candidate_id)
        ):
            return False
        base = self._safe_base(OWNER_DIRECT_CANDIDATE_RELATIVE)
        directory = base / candidate_id
        if directory.is_symlink():
            fail("PRIVATE_PATH_UNSAFE")
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True


def _needle_variants(needles: Sequence[str]) -> set[bytes]:
    return {n.encode("utf-8") for n in needles if n} | {
        json.dumps(n)[1:-1].encode("utf-8") for n in needles if n
    }


def _file_contains(path: Path, variants: set[bytes]) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    payload = path.read_bytes()
    return any(v in payload for v in variants)


# Local values are purged but the run is not finished. All four block fetch and gate:
# - PUBLISHED_NOT_PURGED: WordPress still serves the injected values (no purge publish and
#   no owner incident resolution recorded);
# - REDACTION_PENDING: the approval still names price-recoverable ids, a replace write left
#   a .tmp, or a publisher candidate / preview copy still carries the run's markers or values;
# - WORDPRESS_REDACTION_UNCONFIRMED: the plugin's stored copies are not known to be gone
#   (purge_publish.wordpress_redaction is not COMPLETE and the owner recorded no manual
#   plugin cleanup for the run). Contract §5.
UNFINISHED_PURGE_STATUSES: Final = frozenset(
    {"PUBLISHED_NOT_PURGED", "REDACTION_PENDING", "WORDPRESS_REDACTION_UNCONFIRMED"}
)
# The only other way out of PUBLISHED_NOT_PURGED: the owner records, after purge-expired,
# that WordPress no longer serves the run's values although no purge publish was recorded
# (for example the post was restored or withdrawn by hand). Contract §5.
INCIDENT_RESOLUTION_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_INCIDENT_RESOLUTION_V1"
INCIDENT_RESOLUTION_FILE: Final = "incident-resolution.v1.json"
INCIDENT_RESOLUTIONS: Final = frozenset(
    {"WORDPRESS_RESTORED_OUTSIDE_PUBLISHER", "WORDPRESS_POSTS_WITHDRAWN"}
)


PLUGIN_CLEANUP_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_PLUGIN_CLEANUP_V1"
PLUGIN_CLEANUP_FILE: Final = "plugin-cleanup.v1.json"
PLUGIN_CLEANUP_REASONS: Final = frozenset(
    {"WORDPRESS_REDACTION_INCOMPLETE", "WORDPRESS_REDACTION_NOT_REPORTED", "INCIDENT_RESOLUTION"}
)


def plugin_cleanup_confirmation_text(run_id: str) -> str:
    """What the owner types after removing the run's injected bodies from the plugin rows
    and undo options by hand (``--owner-confirmed-plugin-cleanup``)."""
    return "PLUGIN_COPIES_REMOVED:" + require_run_id(run_id)


def plugin_cleanup(store: PrivateStore, run_id: str) -> dict[str, Any] | None:
    path = store.run_directory(run_id) / PLUGIN_CLEANUP_FILE
    if not path.exists():
        return None
    record = store.read_json(path)
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "run_id", "reason", "confirmation", "recorded_at"}
        or record["schema"] != PLUGIN_CLEANUP_SCHEMA
        or record["run_id"] != run_id
        or record["reason"] not in PLUGIN_CLEANUP_REASONS
        or record["confirmation"] != plugin_cleanup_confirmation_text(run_id)
    ):
        fail("PLUGIN_CLEANUP_RECORD_INVALID")
    parse_time(record["recorded_at"])
    return record


def preview_copy_record(store: PrivateStore, run_id: str) -> dict[str, Any] | None:
    """The run's own record of what its previews froze under the preview base (contract §5)."""
    path = store.run_directory(run_id) / PREVIEW_COPIES_FILE
    if not path.exists():
        return None
    record = store.read_json(path)
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "run_id", "copies", "recorded_at"}
        or record["schema"] != PREVIEW_COPIES_SCHEMA
        or record["run_id"] != run_id
        or not isinstance(record["copies"], list)
        or not 1 <= len(record["copies"]) <= MAX_PREVIEW_COPIES
    ):
        fail("PREVIEW_COPY_RECORD_INVALID")
    for name in record["copies"]:
        require_preview_copy_name(name)
    parse_time(record["recorded_at"])
    return record


def recorded_preview_copies(store: PrivateStore, run_id: str) -> list[str]:
    record = preview_copy_record(store, run_id)
    return list(record["copies"]) if record is not None else []


def record_preview_copy(
    store: PrivateStore,
    run_id: str,
    relative: str,
    now: datetime | None = None,
) -> list[str]:
    """Record a preview copy *before* it is written (contract §5, §8).

    The copy is named after the injected theme tree and holds the injected body hashes, so it
    is price-recoverable; but it is frozen at preview time, when the approval has no publish
    record for the needle sweep to work from. This is the only thing that can find it when the
    candidate is never published. Written first, so an interrupted preview is covered too, and
    the caller must fail closed when this raises: nothing may be frozen unrecorded.
    """
    run_id = require_run_id(run_id)
    name = require_preview_copy_name(relative)
    existing = preview_copy_record(store, run_id)
    copies = sorted({*(existing["copies"] if existing else ()), name})
    if len(copies) > MAX_PREVIEW_COPIES:
        fail("PREVIEW_COPY_RECORD_FULL")
    if existing is not None and existing["copies"] == copies:
        return copies
    store.write_json(
        store.run_directory(run_id) / PREVIEW_COPIES_FILE,
        {
            "schema": PREVIEW_COPIES_SCHEMA,
            "run_id": run_id,
            "copies": copies,
            "recorded_at": iso(now if now is not None else datetime.now(UTC)),
        },
        replace=existing is not None,
    )
    return copies


def discard_preview_copy_record(store: PrivateStore, run_id: str) -> bool:
    """Delete the record once every copy it names is gone: it names them, so it leaks too."""
    record = preview_copy_record(store, run_id)
    if record is None:
        return False
    if any(store.preview_copy_exists(name) for name in record["copies"]):
        return False
    return store.delete_run_file(run_id, PREVIEW_COPIES_FILE)


def local_copy_needles(
    run_id: str, overlay: object, approval: object
) -> tuple[set[str], list[str]]:
    """(candidate ids recorded for the run, content needles: marker, values, injected hashes)."""
    candidate_ids: set[str] = set()
    record = approval if isinstance(approval, dict) else None
    if record is not None:
        for part, keys in (
            (record.get("publish"), ("candidate_id",)),
            (record.get("purge_publish"), PURGE_PUBLISH_HASH_KEYS),
        ):
            if isinstance(part, dict):
                candidate_ids.update(str(part[key]) for key in keys if part.get(key))
        prepared = record.get(PREPARED_CANDIDATES_KEY)
        if isinstance(prepared, dict):
            candidate_ids.update(str(v) for v in prepared.values() if v)
    source = (
        overlay
        if isinstance(overlay, dict) and overlay.get("run_id") == run_id
        else {"run_id": run_id, "entries": []}
    )
    try:
        needles = leak_needles(source, record)
    except KeyError, TypeError:
        needles = leak_needles({"run_id": run_id, "entries": []}, None)
    return candidate_ids, needles


def local_copies(
    store: PrivateStore, run_id: str, overlay: object, approval: object
) -> tuple[list[str], list[str]]:
    """Publisher candidates and preview copies that still hold this run's injected bytes."""
    candidate_ids, needles = local_copy_needles(run_id, overlay, approval)
    base = store.owner_checkout / OWNER_DIRECT_CANDIDATE_RELATIVE
    recorded = {
        c
        for c in candidate_ids
        if len(c) == 64 and all(ch in "0123456789abcdef" for ch in c) and (base / c).exists()
    }
    candidates = sorted(recorded | set(store.owner_direct_candidates_containing(needles)))
    # By content, plus what the run's previews recorded before freezing it: a preview that is
    # never published leaves no needle anywhere, so the record is the only way to that copy.
    previews = set(store.preview_copies_containing(needles))
    previews.update(
        name
        for name in recorded_preview_copies(store, run_id)
        if store.preview_copy_exists(name)
    )
    return candidates, sorted(previews)


def sweep_local_copies(
    store: PrivateStore, run_id: str, overlay: object, approval: object
) -> dict[str, int]:
    """Delete every local copy of the run's injected bytes outside the run directory.

    Covers the ids recorded by the publisher, every interrupted ``.staging-*`` candidate,
    any candidate any of whose files still carries the run's marker, values or injected
    hashes (for example a flag-free candidate prepared while values were live), preview
    copies (frozen display themes and fixtures) found by content, and every copy the run's
    own previews recorded before freezing it - the only handle on a candidate that was
    previewed and never published. Run it before redacting the approval: for a published run
    the injected hashes are what find a frozen injected theme.
    """
    candidates, previews = local_copies(store, run_id, overlay, approval)
    return {
        "candidate_directories_deleted": sum(
            store.delete_owner_direct_candidate(c) for c in candidates
        ),
        "preview_copies_deleted": sum(store.delete_preview_copy(p) for p in previews),
        # Last: the record names ``theme-<injected tree sha256>`` itself, so it may only go
        # once every copy it points at is gone.
        "preview_copy_records_deleted": int(
            discard_preview_copy_record(store, run_id)
        ),
    }


def live_run_ids(checkouts: Iterable[Path | None]) -> list[str]:
    """Run ids whose values may be live, over every given checkout that has a run directory.

    The publisher and the deployment operator pass the fixed owner checkout whether or not
    ``--owner-checkout`` was given: runs live there while commands run from a worktree
    (contract §8). A run directory that is a symlink or not a directory, and a checkout whose
    store cannot be opened, are refused (fail closed).
    """
    found: set[str] = set()
    seen: set[Path] = set()
    for value in checkouts:
        if value is None or Path(value) in seen:
            continue
        checkout = Path(value)
        seen.add(checkout)
        runs = checkout / PRIVATE_ROOT_RELATIVE
        if not runs.exists() and not runs.is_symlink():
            continue
        if runs.is_symlink() or not runs.is_dir():
            fail("PRIVATE_PATH_UNSAFE")
        # A run entry that is a symlink or not a directory is refused instead of skipped
        # (``run_ids()`` skips it): its approval record cannot be read, so its values would
        # count as not live (contract §8, §10.1-10).
        try:
            entries = sorted(runs.iterdir())
        except OSError:
            fail("PRIVATE_PATH_UNSAFE")
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                fail("PRIVATE_PATH_UNSAFE")
        found.update(run_id for run_id, _keys in live_publish_runs(PrivateStore(checkout)))
    return sorted(found)


def live_publish_runs(store: PrivateStore) -> list[tuple[str, list[str] | None]]:
    """Runs whose values may be live on WordPress: a publish is recorded (or reserved) and
    neither a purge publish nor an owner incident resolution is. Article keys are None when
    the approval record cannot be read (fail safe: every article counts as injected)."""
    live: list[tuple[str, list[str] | None]] = []
    for run_id in store.run_ids():
        if RUN_ID_PATTERN.fullmatch(run_id) is None:
            continue
        path = store.run_directory(run_id) / "approval.v1.json"
        if not path.exists() and not path.is_symlink():
            continue
        try:
            approval = validate_approval(store.read_json(path), run_id)
            publish = approval["publish"]
            if (
                publish is None
                or approval["purge_publish"] is not None
                or incident_resolution(store, run_id) is not None
            ):
                continue
            keys = publish.get("article_keys")
            valid = isinstance(keys, list) and all(isinstance(k, str) for k in keys)
            live.append((run_id, sorted(keys) if valid else None))
        except RefreshError, OSError, ValueError, KeyError, TypeError:
            live.append((run_id, None))
    return live


def incident_resolution(store: PrivateStore, run_id: str) -> dict[str, Any] | None:
    path = store.run_directory(run_id) / INCIDENT_RESOLUTION_FILE
    if not path.exists():
        return None
    record = store.read_json(path)
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "run_id", "resolution", "recorded_at"}
        or record["schema"] != INCIDENT_RESOLUTION_SCHEMA
        or record["run_id"] != run_id
        or record["resolution"] not in INCIDENT_RESOLUTIONS
    ):
        fail("INCIDENT_RESOLUTION_INVALID")
    parse_time(record["recorded_at"])
    return record


def run_status(store: PrivateStore, run_id: str) -> tuple[str, datetime | None]:
    """PURGED / PUBLISHED_NOT_PURGED / REDACTION_PENDING / WORDPRESS_REDACTION_UNCONFIRMED /
    EMPTY / DATED (with the earliest expiry) / UNDATED (records unreadable or invalid).

    A run whose local values are purged is PURGED only when all of these hold: the purge
    publish or an owner incident resolution is recorded; the approval carries no
    price-recoverable id; no replace write left a .tmp; the run holds no preview-copy record
    (its names are price-recoverable hashes); no publisher candidate or preview copy still
    carries the run's markers or values, and no recorded preview copy is still on disk; and
    the plugin's stored copies are known to be gone (wordpress_redaction COMPLETE, or the
    owner's plugin cleanup record).
    """
    directory = store.run_directory(run_id)
    has_raw = (directory / "raw").exists()
    overlay_path, approval_path = (
        directory / "overlay.v1.json",
        directory / "approval.v1.json",
    )
    try:
        overlay = store.read_json(overlay_path) if overlay_path.exists() else None
        approval = store.read_json(approval_path) if approval_path.exists() else None
        if isinstance(overlay, dict) and overlay.get("schema") == PURGED_SCHEMA:
            # The approval is written before fetch sends anything: without a readable one a
            # purged run cannot show that its publish and purge obligations are met.
            if has_raw or not isinstance(approval, dict):
                return "UNDATED", None
            record = approval
            if (
                record.get("publish") is not None
                and record.get("purge_publish") is None
                and incident_resolution(store, run_id) is None
            ):
                return "PUBLISHED_NOT_PURGED", None
            if redact_approval(record) != record:
                return "REDACTION_PENDING", None
            if (
                store.run_tmp_files(run_id)
                # The preview-copy record carries the frozen tree's name whether or not the
                # copy is still there, so PURGED waits for the record to go as well.
                or preview_copy_record(store, run_id) is not None
                or any(local_copies(store, run_id, overlay, record))
            ):
                return "REDACTION_PENDING", None
            if record.get("publish") is not None:
                purge_publish = record.get("purge_publish")
                redacted_by_plugin = (
                    isinstance(purge_publish, dict)
                    and purge_publish.get("wordpress_redaction") == "COMPLETE"
                )
                if not redacted_by_plugin and plugin_cleanup(store, run_id) is None:
                    return "WORDPRESS_REDACTION_UNCONFIRMED", None
            return "PURGED", None
        if overlay is not None:
            validate_overlay(overlay)
            return "DATED", parse_time(overlay["cache_expires_at"])
        if approval is not None:
            # No overlay yet: every observation is later than approval, so this expiry is earlier.
            return "DATED", parse_time(
                validate_approval(approval, run_id)["approved_at"]
            ) + MAX_CACHE_AGE
    except RefreshError, OSError, ValueError, KeyError, TypeError:
        return "UNDATED", None
    if has_raw:
        return "UNDATED", None
    # No overlay and no approval, but a run directory holding the preview-copy record is not
    # empty: the record names ``theme-<injected tree sha256>`` and the copies it names may
    # still be under the preview base, and EMPTY is a finished answer - ``purge-expired``
    # reports NO_RECORDS without sweeping, ``expired_unpurged_runs`` does not list the run and
    # fetch/gate stop blocking. Reachable when a preview records a copy into a run directory
    # that carries nothing else (contract §5).
    try:
        if preview_copy_record(store, run_id) is not None:
            return "REDACTION_PENDING", None
    except RefreshError, OSError, ValueError, KeyError, TypeError:
        return "UNDATED", None
    return "EMPTY", None


def expired_unpurged_runs(
    store: PrivateStore, now: datetime, *, exclude: str | None = None
) -> list[str]:
    stale = []
    for run_id in store.run_ids():
        if run_id == exclude or RUN_ID_PATTERN.fullmatch(run_id) is None:
            continue
        status, expires = run_status(store, run_id)
        if status == "UNDATED" or status in UNFINISHED_PURGE_STATUSES or (
            status == "DATED" and expires is not None and now >= expires
        ):
            stale.append(run_id)
    return stale


# ---------------------------------------------------------------------------
# Tracked-file leak scan
# ---------------------------------------------------------------------------


HISTORY_REVISION_CHUNK: Final = 200


def _grep_paths(
    repository: Path,
    patterns: Iterable[str],
    mode: str,
    runner: GitRunner,
    revisions: Sequence[str] = (),
) -> list[str]:
    arguments = ["grep", "-z", "-l", "-I", "-F"]
    if mode == "worktree":
        arguments.append("--untracked")
    elif mode == "index":
        arguments.append("--cached")
    for pattern in patterns:
        arguments.extend(["-e", pattern])
    if mode == "history":
        arguments.extend([*revisions, "--"])
    result = _git(repository, *arguments, runner=runner)
    if result.returncode not in (0, 1):
        fail("GIT_GREP_FAILED")
    return sorted(
        {p.decode("utf-8", "surrogateescape") for p in result.stdout.split(b"\0") if p}
    )


def scan_repository_for_overlay(
    repository: Path,
    overlay: Mapping[str, Any],
    approval: Mapping[str, Any] | None = None,
    *,
    runner: GitRunner = subprocess.run,
) -> list[str]:
    """Return ``<code>:<mode>:<path>`` for tracked or untracked-not-ignored files (and the index)."""
    if (
        _git(repository, "rev-parse", "--is-inside-work-tree", runner=runner).returncode
        != 0
    ):
        fail("REPOSITORY_INVALID")
    exact = leak_needles(overlay, approval)
    offers: Sequence[str] = sorted(
        {
            str(e["offer_id"])
            for e in overlay.get("entries", [])
            if isinstance(e, Mapping) and e.get("price_yen") is not None
        }
    )
    findings: set[str] = set()
    for mode in ("worktree", "index"):
        for path in _grep_paths(repository, exact, mode, runner):
            findings.add(f"OVERLAY_EXACT_VALUE:{mode}:{path}")
        if not offers:
            continue
        for path in _grep_paths(repository, offers, mode, runner):
            if mode == "worktree":
                try:
                    text = (repository / path).read_text(encoding="utf-8")
                except OSError, UnicodeDecodeError:
                    continue
            else:
                shown = _git(repository, "show", f":{path}", runner=runner)
                if shown.returncode != 0:
                    continue
                text = shown.stdout.decode("utf-8", "replace")
            for code in contextual_leaks(text, overlay):
                findings.add(f"{code}:{mode}:{path}")
    # Commits not yet on any remote would be pushed by the publisher's sync step.
    if (
        _git(
            repository, "rev-parse", "--verify", "-q", "HEAD", runner=runner
        ).returncode
        == 0
    ):
        listed = _git(
            repository, "rev-list", "HEAD", "--not", "--remotes", runner=runner
        )
        if listed.returncode != 0:
            fail("GIT_REV_LIST_FAILED")
        revisions = listed.stdout.decode("ascii").split()
        for start in range(0, len(revisions), HISTORY_REVISION_CHUNK):
            chunk = revisions[start : start + HISTORY_REVISION_CHUNK]
            for hit in _grep_paths(repository, exact, "history", runner, chunk):
                revision, _separator, path = hit.partition(":")
                findings.add(f"OVERLAY_EXACT_VALUE:history:{revision[:12]}:{path}")
    return sorted(findings)


def scan_revision_for_overlay(
    repository: Path,
    revision: str,
    overlay: Mapping[str, Any],
    approval: Mapping[str, Any] | None = None,
    *,
    runner: GitRunner = subprocess.run,
) -> list[str]:
    """Scan one commit (the publisher checkpoint) with exact and contextual needles."""
    if (
        len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
        or _git(
            repository, "cat-file", "-e", f"{revision}^{{commit}}", runner=runner
        ).returncode
        != 0
    ):
        fail("REVISION_INVALID")
    short = revision[:12]
    findings: set[str] = set()
    for hit in _grep_paths(
        repository, leak_needles(overlay, approval), "history", runner, [revision]
    ):
        findings.add(f"OVERLAY_EXACT_VALUE:revision:{short}:{hit.partition(':')[2]}")
    offers = sorted(
        {
            str(e["offer_id"])
            for e in overlay.get("entries", [])
            if isinstance(e, Mapping) and e.get("price_yen") is not None
        }
    )
    if offers:
        for hit in _grep_paths(repository, offers, "history", runner, [revision]):
            path = hit.partition(":")[2]
            shown = _git(repository, "show", f"{revision}:{path}", runner=runner)
            if shown.returncode != 0:
                continue
            for code in contextual_leaks(
                shown.stdout.decode("utf-8", "replace"), overlay
            ):
                findings.add(f"{code}:revision:{short}:{path}")
    return sorted(findings)
