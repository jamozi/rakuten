"""Owner-gated fixed-origin WordPress HTTPS adapter for ST-1704.

The adapter exposes only closed review-draft operations and fixed public reads.
It has no generic request API and no publish, update, media, taxonomy, plugin,
theme, delete, private-status, or scheduling path.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import threading
from typing import Final, NoReturn, cast, final
from urllib.parse import unquote_to_bytes, urlsplit
import unicodedata
import xml.etree.ElementTree as ElementTree

from raos.adapters.self_hosted_wordpress_credentials import (
    OwnerPrivateSelfHostedWordPressCredentialStore,
)
from raos.adapters.self_hosted_wordpress_https import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    READ_TIMEOUT_SECONDS,
    SELF_HOSTED_WORDPRESS_HOST,
    SELF_HOSTED_WORDPRESS_PORT,
    SelfHostedWordPressHttpsConnection,
    SelfHostedWordPressHttpsConnectionFactory,
    SelfHostedWordPressHttpsResponse,
    SystemSelfHostedWordPressHttpsConnectionFactory,
    require_clean_self_hosted_wordpress_environment,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    CarryOnSingleUrlReconciliationBinding,
    CarryOnSingleUrlReconciliationEvidence,
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PILOT_ARTICLE_IDENTITIES,
    PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID,
    PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID,
    PILOT_CREATE_PATH,
    PILOT_CTA_LABEL,
    PILOT_ORIGIN,
    PILOT_POSTS_PATH,
    PILOT_PUBLIC_VERIFICATION_CHECKS,
    PILOT_REVIEW_STATUS,
    PILOT_SNAPSHOT_META_KEY,
    PilotArticleIdentity,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    PublicVerification,
    ReviewDraftDisposition,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    bytes_sha256,
    canonical_json_bytes,
    canonical_sha256,
    fail_editorial_pilot,
)
from raos.domain.editorial.self_hosted_wordpress import SelfHostedWordPressFailure


OWNER_GATE_DIRECTORY: Final = Path(
    ".secrets/st1704-self-hosted-editorial-pilot/owner-live-gates"
)
OWNER_GATE_SCHEMA: Final = "RAOS_ST1704_OWNER_LIVE_GATE_V1"
OWNER_GATE_AUTHORITY: Final = "HUMAN_OWNER_ONE_OPERATION"

_CONTENT_TYPE = re.compile(
    r"application/json(?:\s*;\s*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_HTML_CONTENT_TYPE = re.compile(
    r'text/html(?:\s*;\s*charset="?utf-8"?)?\Z', re.ASCII | re.IGNORECASE
)
_ROBOTS_CONTENT_TYPE = re.compile(
    r'text/plain(?:\s*;\s*charset="?utf-8"?)?\Z', re.ASCII | re.IGNORECASE
)
_XML_CONTENT_TYPE = re.compile(
    r'(?:application|text)/xml(?:\s*;\s*charset="?utf-8"?)?\Z',
    re.ASCII | re.IGNORECASE,
)
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_REMAINING_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}", re.ASCII)
_REVIEW_LEAK_TOKEN = re.compile(r"[^\W_]{16,}", re.UNICODE)
_REVIEW_LEAK_FRAGMENT_LENGTH: Final = 24
_REVIEW_CTA_HIGH_SIGNAL_FRAGMENTS: Final = (
    "楽天市場で写真・価格・在庫",
    "楽天市場で写真・価格を見る",
    "楽天市場で価格・在庫を見る",
    "楽天市場で価格を見る",
    "楽天市場で在庫を見る",
)
_RECOVERY_FIELDS: Final = (
    "id%2Ctype%2Cslug%2Cstatus%2Ccategories%2Cdate_gmt%2Cmodified_gmt%2Ctitle.raw%2C"
    "excerpt.raw%2Ccontent.raw%2Cmeta._raos_publication_snapshot_v1"
)
_TARGET_FIELDS: Final = "id%2Ctype%2Cslug%2Cstatus"
_ALLOWED_COMMANDS: Final = frozenset(
    {
        "create-review-draft",
        "recover-create-review-draft",
        "verify-carry-on-single-url",
        "verify-public",
    }
)
_GATE_KEYS: Final = frozenset(
    {
        "article_id",
        "authority",
        "command",
        "origin",
        "packet_sha256",
        "request_sha256",
        "schema",
    }
)
_PRIVATE_FILE_MODE: Final = 0o600
_PRIVATE_DIRECTORY_MODE: Final = 0o700
_MAX_GATE_BYTES: Final = 16_384
_MAX_ROBOTS_BYTES: Final = 262_144
_MAX_THEME_CONTRACT_BYTES: Final = 262_144
_THEME_CONTRACT_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/theme-contract.v1.json"
)
_SITEMAP_NAMESPACE: Final = "http://www.sitemaps.org/schemas/sitemap/0.9"
_PUBLISHED_ROBOTS: Final = (
    "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
)
_SOCIAL_IMAGE_URL: Final = (
    f"{PILOT_ORIGIN}/wp-content/themes/kurashinoshirube-child/"
    "assets/images/home-hero.webp"
)
_WORDPRESS_API_DISCOVERY_LINK: Final = (
    f'<{PILOT_ORIGIN}/wp-json/>; rel="https://api.w.org/"'
)
_YOAST_CORE_SITEMAP_REDIRECT: Final = f"{PILOT_ORIGIN}/sitemap_index.xml"
_YOAST_REDIRECT_BY: Final = "Yoast SEO"
_PUBLIC_KINDS: Final = frozenset(
    {
        "wordpress-post",
        "article-html",
        "category",
        "core-sitemap",
        "draft-inventory",
        "homepage-html",
        "homepage-targets",
        "robots",
        "sitemap-index",
        "post-sitemap",
        "page-sitemap",
        "publication-target",
        "related-target",
        "review-draft-rest",
        "review-public-rest",
        "review-url-html",
    }
)
_HTML_VOID_TAGS: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_REVIEW_EVIDENCE_KINDS: Final = frozenset(
    {"review-draft-rest", "review-public-rest", "review-url-html"}
)


@dataclass(frozen=True, slots=True)
class _FixedPublicReadCapture:
    """One validated fixed GET plus the metadata needed for evidence hashing."""

    kind: str
    path: str
    http_status: int
    content_type: str
    location_header: str | None
    x_wp_total: str | None
    x_wp_total_pages: str | None
    body: bytes

    def evidence_sha256(self) -> str:
        if (
            self.kind not in _REVIEW_EVIDENCE_KINDS
            or type(self.path) is not str
            or not self.path.startswith("/")
            or type(self.http_status) is not int
            or type(self.content_type) is not str
            or self.location_header is not None
            or (self.x_wp_total is not None and type(self.x_wp_total) is not str)
            or (
                self.x_wp_total_pages is not None
                and type(self.x_wp_total_pages) is not str
            )
            or type(self.body) is not bytes
        ):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        return canonical_sha256(
            {
                "body_sha256": bytes_sha256(self.body),
                "content_type": self.content_type,
                "http_status": self.http_status,
                "kind": self.kind,
                "location_header": self.location_header,
                "method": "GET",
                "path": self.path,
                "schema": "RAOS_ST1704_REVIEW_SURFACE_EVIDENCE_V1",
                "x_wp_total": self.x_wp_total,
                "x_wp_total_pages": self.x_wp_total_pages,
            }
        )


def _fail(
    code: EditorialPilotFailureCode = EditorialPilotFailureCode.TRANSPORT_REFUSED,
) -> NoReturn:
    fail_editorial_pilot(code)


def _collection_link_header_is_fixed(value: object) -> bool:
    """Accept only no Link header or WordPress's fixed API-discovery relation."""

    return value is None or value == _WORDPRESS_API_DISCOVERY_LINK


class _DeadlineExpired(TimeoutError):
    pass


@contextmanager
def _deadline(seconds: float) -> Generator[None, None, None]:
    try:
        current_handler = signal.getsignal(signal.SIGALRM)
        current_timer = signal.getitimer(signal.ITIMER_REAL)
    except BaseException:
        _fail()
    if (
        threading.current_thread() is not threading.main_thread()
        or current_handler not in {signal.SIG_DFL, signal.SIG_IGN}
        or current_timer != (0.0, 0.0)
        or type(seconds) not in {int, float}
        or not 0 < seconds <= 60
    ):
        _fail()
    previous_handler = current_handler

    def expire(signum: int, frame: object) -> NoReturn:
        del signum, frame
        raise _DeadlineExpired from None

    try:
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def _strict_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)


def _gate_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
        result[key] = value
    return result


def _reject_gate_constant(value: str) -> NoReturn:
    del value
    _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)


def _decode_response(raw: bytes) -> object:
    if type(raw) is not bytes or not 2 <= len(raw) <= MAX_RESPONSE_BYTES:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)


def _read_theme_contract(repository_root: Path) -> Mapping[str, object]:
    path = repository_root / _THEME_CONTRACT_RELATIVE_PATH
    descriptor = -1
    try:
        before_path = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before_path.st_mode)
            or stat.S_ISLNK(before_path.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before_path.st_dev != before.st_dev
            or before_path.st_ino != before.st_ino
            or not 2 <= before.st_size <= _MAX_THEME_CONTRACT_BYTES
        ):
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.PACKET_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    contract = _mapping(_decode_response(raw))
    if contract.get("schema") != "SELF_HOSTED_EDITORIAL_THEME_CONTRACT_V1":
        _fail(EditorialPilotFailureCode.PACKET_INVALID)
    return contract


def _load_theme_related_navigation(
    repository_root: Path,
) -> dict[str, dict[str, object]]:
    contract = _read_theme_contract(repository_root)
    related = _mapping(contract.get("related_navigation"))
    raw_map = _mapping(related.get("map"))
    article_ids = {identity.article_id for identity in PILOT_ARTICLE_IDENTITIES}
    if (
        related.get("owner") != "THEME_FIXED_ALLOWLIST"
        or related.get("target_requirement")
        != "PUBLISHED_EXACT_SAME_ORIGIN_PERMALINK_WITH_BOUND_RAOS_SNAPSHOT"
        or related.get("map_sha256") != canonical_sha256(dict(raw_map))
        or set(raw_map) != article_ids
    ):
        _fail(EditorialPilotFailureCode.PACKET_INVALID)
    normalized: dict[str, dict[str, object]] = {}
    for article_id, raw_relation in raw_map.items():
        relation = _mapping(raw_relation)
        if set(relation) != {"home_anchor", "home_label", "targets"}:
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        anchor = relation["home_anchor"]
        label = relation["home_label"]
        targets = _mapping(relation["targets"])
        if (
            type(anchor) is not str
            or re.fullmatch(r"cluster-[a-z]+", anchor, re.ASCII) is None
            or type(label) is not str
            or not label
            or len(targets) > 1
        ):
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        target: tuple[str, str] | None = None
        if targets:
            target_id, target_label = next(iter(targets.items()))
            if (
                target_id not in article_ids
                or target_id == article_id
                or type(target_label) is not str
                or not target_label
            ):
                _fail(EditorialPilotFailureCode.PACKET_INVALID)
            target = (target_id, target_label)
        normalized[article_id] = {
            "home": (f"{PILOT_ORIGIN}/#{anchor}", label),
            "target": target,
        }
    return normalized


def _load_theme_homepage_clusters(
    repository_root: Path,
) -> dict[str, object]:
    contract = _read_theme_contract(repository_root)
    homepage = _mapping(contract.get("homepage_clusters"))
    config = _mapping(homepage.get("config"))
    clusters = _mapping(config.get("clusters"))
    display_order = config.get("display_order")
    article_ids = {identity.article_id for identity in PILOT_ARTICLE_IDENTITIES}
    related = _mapping(_mapping(contract.get("related_navigation")).get("map"))
    if (
        set(homepage) != {"config", "config_sha256", "link_requirement", "owner"}
        or homepage.get("owner") != "THEME_FIXED_ALLOWLIST"
        or homepage.get("link_requirement")
        != "PUBLISHED_EXACT_SAME_ORIGIN_PERMALINK_WITH_BOUND_RAOS_SNAPSHOT"
        or homepage.get("config_sha256") != canonical_sha256(dict(config))
        or set(config) != {"clusters", "display_order"}
        or type(display_order) is not list
        or len(cast(list[object], display_order)) != 3
        or len(set(cast(list[object], display_order))) != 3
        or set(cast(list[object], display_order)) != set(clusters)
    ):
        _fail(EditorialPilotFailureCode.PACKET_INVALID)
    normalized_clusters: dict[str, dict[str, object]] = {}
    observed_article_ids: set[str] = set()
    for cluster_id in cast(list[object], display_order):
        if (
            type(cluster_id) is not str
            or re.fullmatch(r"cluster-[a-z]+", cluster_id, re.ASCII) is None
        ):
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        cluster = _mapping(clusters[cluster_id])
        if set(cluster) != {
            "description",
            "heading",
            "label",
            "post_order",
            "posts",
        }:
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        posts = _mapping(cluster["posts"])
        post_order = cluster["post_order"]
        if (
            not posts
            or type(post_order) is not list
            or len(cast(list[object], post_order)) != len(posts)
            or len(set(cast(list[object], post_order))) != len(posts)
            or set(cast(list[object], post_order)) != set(posts)
        ):
            _fail(EditorialPilotFailureCode.PACKET_INVALID)
        normalized_posts: list[tuple[str, str]] = []
        for article_id in cast(list[object], post_order):
            if type(article_id) is not str:
                _fail(EditorialPilotFailureCode.PACKET_INVALID)
            label = posts[article_id]
            relation = _mapping(related.get(article_id))
            if (
                article_id not in article_ids
                or article_id in observed_article_ids
                or type(label) is not str
                or not label
                or label != label.strip()
                or relation.get("home_anchor") != cluster_id
            ):
                _fail(EditorialPilotFailureCode.PACKET_INVALID)
            observed_article_ids.add(article_id)
            normalized_posts.append((article_id, label))
        for key in ("description", "heading", "label"):
            value = cluster[key]
            if type(value) is not str or not value or value != value.strip():
                _fail(EditorialPilotFailureCode.PACKET_INVALID)
        normalized_clusters[cluster_id] = {
            "description": cluster["description"],
            "heading": cluster["heading"],
            "label": cluster["label"],
            "posts": tuple(normalized_posts),
        }
    if observed_article_ids != article_ids:
        _fail(EditorialPilotFailureCode.PACKET_INVALID)
    return {
        "clusters": normalized_clusters,
        "display_order": tuple(cast(list[str], display_order)),
    }


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    return cast(Mapping[str, object], value)


def _public_observation_string(value: object) -> str:
    if type(value) is not str:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return value


def _public_observation_optional_string(value: object) -> str | None:
    if value is not None and type(value) is not str:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return value


def _raw_field(value: object, expected: str) -> None:
    field = _mapping(value)
    if set(field) != {"raw"} or field["raw"] != expected:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)


def _validate_post(
    value: object,
    *,
    request: ReviewDraftRequest,
    expected_status: str,
) -> int:
    post = _mapping(value)
    required = {"content", "excerpt", "id", "meta", "slug", "status", "title", "type"}
    if not required <= set(post):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    post_id = post["id"]
    if (
        type(post_id) is not int
        or not 1 <= post_id <= (1 << 63) - 1
        or post["type"] != "post"
        or post["slug"]
        != (
            request.slug
            if expected_status == PILOT_REVIEW_STATUS
            else request.snapshot.payload.slug
        )
        or post["status"] != expected_status
    ):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    _raw_field(post["title"], request.title)
    _raw_field(post["excerpt"], request.excerpt)
    _raw_field(post["content"], request.content)
    meta = _mapping(post["meta"])
    if (
        set(meta) != {PILOT_SNAPSHOT_META_KEY}
        or meta[PILOT_SNAPSHOT_META_KEY] != request.snapshot.json_string()
    ):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    return post_id


def _matching_snapshot_drafts(
    value: object, request: ReviewDraftRequest
) -> list[object]:
    if type(value) is not list:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    matching_posts: list[object] = []
    for raw_post in cast(list[object], value):
        post = _mapping(raw_post)
        required = {
            "content",
            "excerpt",
            "id",
            "meta",
            "slug",
            "status",
            "title",
            "type",
        }
        if not required <= set(post):
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        meta = _mapping(post["meta"])
        if meta.get(PILOT_SNAPSHOT_META_KEY) == request.snapshot.json_string():
            matching_posts.append(raw_post)
    return matching_posts


def _review_slug_family_drafts(
    value: object, request: ReviewDraftRequest
) -> list[object]:
    if type(value) is not list:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    expression = re.compile(re.escape(request.slug) + r"(?:-[1-9][0-9]*)?\Z", re.ASCII)
    family: list[object] = []
    for raw_post in cast(list[object], value):
        post = _mapping(raw_post)
        slug = post.get("slug")
        if type(slug) is not str:
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        if expression.fullmatch(slug) is not None:
            family.append(raw_post)
    return family


def _wordpress_utc(value: object) -> str:
    if (
        type(value) is not str
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",
            value,
            re.ASCII,
        )
        is None
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    if parsed.strftime("%Y-%m-%dT%H:%M:%S") != value:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return value + "Z"


def _public_post_dates(value: object) -> tuple[str, str]:
    post = _mapping(value)
    published = _wordpress_utc(post.get("date_gmt"))
    modified = _wordpress_utc(post.get("modified_gmt"))
    if modified < published:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return published, modified


def _related_target_identity(
    request: ReviewDraftRequest,
    related_navigation: Mapping[str, Mapping[str, object]],
) -> PilotArticleIdentity | None:
    relation = related_navigation.get(request.article_id)
    if relation is None:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    target = relation.get("target")
    if target is None:
        return None
    if type(target) is not tuple:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    target_values = cast(tuple[object, ...], target)
    if len(target_values) != 2:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    target_id = target_values[0]
    matches = [
        identity
        for identity in PILOT_ARTICLE_IDENTITIES
        if identity.article_id == target_id
    ]
    if len(matches) != 1:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return matches[0]


def _related_target_is_bound(
    raw: bytes,
    request: ReviewDraftRequest,
    related_navigation: Mapping[str, Mapping[str, object]],
) -> bool:
    identity = _related_target_identity(request, related_navigation)
    if identity is None:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    decoded = _decode_response(raw)
    if type(decoded) is not list:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    rows = cast(list[object], decoded)
    if not rows:
        return False
    if len(rows) != 1:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    relation = related_navigation[request.article_id]
    target = cast(tuple[str, str], relation["target"])
    _validate_bound_public_post(rows[0], identity, expected_title=target[1])
    return True


def _validate_bound_public_post(
    value: object,
    identity: PilotArticleIdentity,
    *,
    expected_title: str | None = None,
) -> int:
    post = _mapping(value)
    required = {
        "content",
        "date_gmt",
        "excerpt",
        "id",
        "meta",
        "modified_gmt",
        "slug",
        "status",
        "title",
        "type",
    }
    if (
        not required <= set(post)
        or post["type"] != "post"
        or post["status"] != "publish"
        or post["slug"] != identity.slug
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    title = _mapping(post["title"])
    content = _mapping(post["content"])
    excerpt = _mapping(post["excerpt"])
    meta = _mapping(post["meta"])
    if (
        set(title) != {"raw"}
        or set(content) != {"raw"}
        or set(excerpt) != {"raw"}
        or set(meta) != {PILOT_SNAPSHOT_META_KEY}
        or type(title["raw"]) is not str
        or type(content["raw"]) is not str
        or type(excerpt["raw"]) is not str
        or type(meta[PILOT_SNAPSHOT_META_KEY]) is not str
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    wrapper_raw = _public_observation_string(meta[PILOT_SNAPSHOT_META_KEY])
    wrapper = _mapping(_decode_surface_json(wrapper_raw))
    if (
        set(wrapper) != {"payload", "payload_sha256", "schema"}
        or wrapper["schema"] != "RAOS_PUBLICATION_SNAPSHOT_V1"
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    payload = _mapping(wrapper["payload"])
    try:
        visible_content_sha256 = bytes_sha256(
            content["raw"].encode("utf-8", errors="strict")
        )
    except UnicodeError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    canonical_wrapper = canonical_json_bytes(dict(wrapper)).decode("utf-8")
    payload_keys = {
        "article_id",
        "author_name",
        "canonical_url",
        "description",
        "modified_at",
        "og_description",
        "og_title",
        "packet_sha256",
        "published_at",
        "section",
        "seo_title",
        "slug",
        "title",
        "visible_content_sha256",
    }
    if set(payload) != payload_keys:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        payload_model = PublicationSnapshotPayload(
            article_id=_public_observation_string(payload["article_id"]),
            packet_sha256=_public_observation_string(payload["packet_sha256"]),
            slug=_public_observation_string(payload["slug"]),
            title=_public_observation_string(payload["title"]),
            seo_title=_public_observation_string(payload["seo_title"]),
            description=_public_observation_string(payload["description"]),
            canonical_url=_public_observation_string(payload["canonical_url"]),
            og_title=_public_observation_string(payload["og_title"]),
            og_description=_public_observation_string(payload["og_description"]),
            published_at=_public_observation_optional_string(payload["published_at"]),
            modified_at=_public_observation_optional_string(payload["modified_at"]),
            author_name=_public_observation_string(payload["author_name"]),
            section=_public_observation_string(payload["section"]),
            visible_content_sha256=_public_observation_string(
                payload["visible_content_sha256"]
            ),
        )
        snapshot_model = PublicationSnapshot(
            payload=payload_model,
            payload_sha256=_public_observation_string(wrapper["payload_sha256"]),
            schema=_public_observation_string(wrapper["schema"]),
        )
    except EditorialPilotFailure, TypeError, ValueError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    published, modified = _public_post_dates(post)
    if (
        wrapper_raw != canonical_wrapper
        or snapshot_model.json_string() != wrapper_raw
        or payload_model.article_id != identity.article_id
        or payload_model.slug != identity.slug
        or payload_model.section != identity.section
        or payload_model.canonical_url != f"{PILOT_ORIGIN}/{identity.slug}/"
        or payload_model.title != title["raw"]
        or payload_model.description != excerpt["raw"]
        or payload_model.visible_content_sha256 != visible_content_sha256
        or (expected_title is not None and payload_model.title != expected_title)
        or payload_model.published_at not in {None, published}
        or payload_model.modified_at not in {None, modified}
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    post_id = post.get("id")
    if type(post_id) is not int or not 1 <= post_id <= (1 << 63) - 1:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return post_id


def _bound_home_articles(raw: bytes) -> dict[str, int]:
    decoded = _decode_response(raw)
    if type(decoded) is not list:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    identities_by_slug = {
        identity.slug: identity for identity in PILOT_ARTICLE_IDENTITIES
    }
    bound: dict[str, int] = {}
    post_ids: set[int] = set()
    for raw_post in cast(list[object], decoded):
        post = _mapping(raw_post)
        slug = post.get("slug")
        if type(slug) is not str or slug not in identities_by_slug:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        identity = identities_by_slug[slug]
        post_id = _validate_bound_public_post(raw_post, identity)
        if identity.article_id in bound or post_id in post_ids:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        bound[identity.article_id] = post_id
        post_ids.add(post_id)
    if not bound:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return bound


def _validate_public_category(post_value: object, category_raw: bytes) -> None:
    post = _mapping(post_value)
    categories = post.get("categories")
    decoded = _decode_response(category_raw)
    if type(categories) is not list or type(decoded) is not list:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    rows = cast(list[object], decoded)
    if len(rows) != 1:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    category = _mapping(rows[0])
    if (
        set(category) != {"id", "name", "slug"}
        or category["name"] != "暮らしの道具"
        or type(category["slug"]) is not str
        or not category["slug"]
        or type(category["id"]) is not int
        or not 1 <= category["id"] <= (1 << 63) - 1
        or categories != [category["id"]]
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _surface_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        result[key] = value
    return result


def _reject_surface_number(value: str) -> NoReturn:
    del value
    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _decode_surface_json(raw: str) -> object:
    if type(raw) is not str or not 2 <= len(raw.encode("utf-8")) <= 262_144:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        return json.loads(
            raw,
            object_pairs_hook=_surface_pairs,
            parse_float=_reject_surface_number,
            parse_constant=_reject_surface_number,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _html_attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name, value in attrs:
        if name in result:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        result[name] = value
    return result


def _has_forbidden_structured_type(
    attributes: Mapping[str, str | None],
) -> bool:
    forbidden = {"aggregaterating", "faqpage", "offer", "product", "review"}
    for key in ("itemtype", "typeof"):
        value = attributes.get(key)
        if type(value) is not str:
            continue
        for token in value.split():
            normalized = token.strip().rstrip("/#").casefold()
            leaf = re.split(r"[/#:]+", normalized)[-1]
            if leaf in forbidden:
                return True
    return False


class _RenderedContentParser(HTMLParser):
    """Collect the rendered article markers whose absence would hide the draft."""

    __slots__ = (
        "cta_active",
        "cta_parts",
        "cta_records",
        "h1_count",
        "h1_open",
        "h1_parts",
        "marker_counts",
        "product_images",
        "rakuten_hrefs",
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cta_active: tuple[str, ...] | None = None
        self.cta_parts: list[str] = []
        self.cta_records: list[tuple[str, ...]] = []
        self.h1_count = 0
        self.h1_open = False
        self.h1_parts: list[str] = []
        self.marker_counts = {
            "raos-comparison": 0,
            "raos-disclosure": 0,
            "raos-product-card": 0,
        }
        self.product_images: list[tuple[str, str, str, str]] = []
        self.rakuten_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.h1_open or self.cta_active is not None:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        attributes = _html_attributes(attrs)
        class_value = attributes.get("class")
        classes = set(class_value.split()) if type(class_value) is str else set[str]()
        for marker in self.marker_counts:
            if marker in classes:
                self.marker_counts[marker] += 1
        if tag == "h1":
            self.h1_count += 1
            self.h1_open = True
            return
        if tag == "a" and "raos-cta" in classes:
            required = {
                "class",
                "data-raos-article-id",
                "data-raos-placement",
                "data-raos-product-id",
                "href",
                "rel",
            }
            if set(attributes) != required or any(
                type(attributes[key]) is not str for key in required
            ):
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            rel_tokens = cast(str, attributes["rel"]).split()
            if len(rel_tokens) != 2 or set(rel_tokens) != {"nofollow", "sponsored"}:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.cta_active = (
                cast(str, attributes["href"]),
                " ".join(sorted(rel_tokens)),
                cast(str, attributes["data-raos-article-id"]),
                cast(str, attributes["data-raos-product-id"]),
                cast(str, attributes["data-raos-placement"]),
            )
            try:
                cta_host = urlsplit(cast(str, attributes["href"])).hostname
            except ValueError:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            if cta_host != "hb.afl.rakuten.co.jp":
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.rakuten_hrefs.append(cast(str, attributes["href"]))
            self.cta_parts = []
            return
        if tag == "a":
            href = attributes.get("href")
            if type(href) is str:
                try:
                    host = urlsplit(href).hostname
                except ValueError:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                if host == "hb.afl.rakuten.co.jp":
                    self.rakuten_hrefs.append(href)
        if tag == "img":
            source = attributes.get("src")
            if type(source) is str:
                try:
                    host = urlsplit(source).hostname
                except ValueError:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                if host == "thumbnail.image.rakuten.co.jp":
                    allowed = {
                        "alt",
                        "decoding",
                        "height",
                        "loading",
                        "src",
                        "width",
                    }
                    if attributes.get("class") == "raos-comparison__product-image":
                        allowed.add("class")
                    image_size = (
                        attributes.get("width"),
                        attributes.get("height"),
                    )
                    if (
                        set(attributes) != allowed
                        or image_size not in {("64", "64"), ("96", "96"), ("128", "128")}
                        or attributes.get("loading") != "lazy"
                        or attributes.get("decoding") != "async"
                        or type(attributes.get("alt")) is not str
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    self.product_images.append(
                        (
                            source,
                            cast(str, attributes["alt"]),
                            cast(str, attributes["width"]),
                            cast(str, attributes["height"]),
                        )
                    )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"a", "h1"}:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            if not self.h1_open:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.h1_open = False
            return
        if tag == "a" and self.cta_active is not None:
            self.cta_records.append((*self.cta_active, "".join(self.cta_parts)))
            self.cta_active = None
            self.cta_parts = []

    def handle_data(self, data: str) -> None:
        if self.h1_open:
            self.h1_parts.append(data)
        elif self.cta_active is not None:
            self.cta_parts.append(data)


class _CanonicalPostContentParser(HTMLParser):
    """Canonicalize expected HTML or the one public post-content subtree."""

    __slots__ = ("capture_all", "container_count", "depth", "events")

    def __init__(self, *, capture_all: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.capture_all = capture_all
        self.container_count = 0
        self.depth = 1 if capture_all else 0
        self.events: list[tuple[object, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = _html_attributes(attrs)
        class_value = attributes.get("class")
        classes = set(class_value.split()) if type(class_value) is str else set[str]()
        is_container = "wp-block-post-content" in classes
        if not self.capture_all and self.depth == 0:
            if is_container:
                if tag != "div" or self.container_count != 0:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.container_count = 1
                self.depth = 1
            return
        if not self.capture_all and is_container:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        self.events.append(("start", tag, tuple(sorted(attributes.items()))))
        if tag not in _HTML_VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = _html_attributes(attrs)
        if self.capture_all or self.depth > 0:
            self.events.append(("empty", tag, tuple(sorted(attributes.items()))))

    def handle_endtag(self, tag: str) -> None:
        if self.capture_all:
            self.depth -= 1
            if self.depth < 1:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.events.append(("end", tag))
            return
        if self.depth == 0:
            return
        self.depth -= 1
        if self.depth == 0:
            if tag != "div":
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            return
        self.events.append(("end", tag))

    def handle_data(self, data: str) -> None:
        if (self.capture_all or self.depth > 0) and data.strip():
            self.events.append(("data", data))

    def handle_comment(self, data: str) -> None:
        del data
        if self.capture_all or self.depth > 0:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


class _RelatedLinkParser(HTMLParser):
    __slots__ = (
        "active",
        "active_href",
        "active_parts",
        "container_count",
        "links",
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active = False
        self.active_href: str | None = None
        self.active_parts: list[str] = []
        self.container_count = 0
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = _html_attributes(attrs)
        if self.active_href is not None:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        class_value = attributes.get("class")
        classes = set(class_value.split()) if type(class_value) is str else set[str]()
        if "raos-related-guides" in classes:
            if tag != "aside" or self.active or self.container_count != 0:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.active = True
            self.container_count = 1
            return
        if self.active and tag == "a":
            href = attributes.get("href")
            if type(href) is not str:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.active_href = href
            self.active_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.active_href is not None:
            self.links.append((self.active_href, "".join(self.active_parts)))
            self.active_href = None
            self.active_parts = []
            return
        if tag == "aside" and self.active:
            if self.active_href is not None:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active_href is not None:
            self.active_parts.append(data)


class _HomepageClusterParser(HTMLParser):
    """Collect the one theme-owned cluster navigation and all pilot links."""

    __slots__ = (
        "active_cluster",
        "active_href",
        "active_parts",
        "cluster_container_count",
        "cluster_container_depth",
        "cluster_depth",
        "cluster_links",
        "pilot_hrefs",
        "pilot_urls",
        "review_href_count",
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active_cluster: str | None = None
        self.active_href: str | None = None
        self.active_parts: list[str] = []
        self.cluster_container_count = 0
        self.cluster_container_depth = 0
        self.cluster_depth = 0
        self.cluster_links: dict[str, list[tuple[str, str]]] = {}
        self.pilot_urls = {
            f"{PILOT_ORIGIN}/{identity.slug}/" for identity in PILOT_ARTICLE_IDENTITIES
        }
        self.pilot_hrefs: list[str] = []
        self.review_href_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = _html_attributes(attrs)
        href_value = attributes.get("href")
        if type(href_value) is str and _contains_review_draft_href(href_value):
            self.review_href_count += 1
        class_value = attributes.get("class")
        classes = set(class_value.split()) if type(class_value) is str else set[str]()
        opened_container = False
        if "raos-cluster-nav" in classes:
            if (
                tag != "section"
                or self.cluster_container_count != 0
                or self.cluster_container_depth != 0
            ):
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.cluster_container_count = 1
            self.cluster_container_depth = 1
            opened_container = True
        if "raos-cluster" in classes:
            cluster_id = attributes.get("id")
            if (
                tag != "section"
                or self.cluster_container_depth == 0
                or self.active_cluster is not None
                or type(cluster_id) is not str
                or cluster_id in self.cluster_links
            ):
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.active_cluster = cluster_id
            self.cluster_depth = 1
            self.cluster_links[cluster_id] = []
            if not opened_container:
                self.cluster_container_depth += 1
            return
        if (
            self.cluster_container_depth > 0
            and not opened_container
            and tag not in _HTML_VOID_TAGS
        ):
            self.cluster_container_depth += 1
        if self.active_cluster is not None and tag not in _HTML_VOID_TAGS:
            self.cluster_depth += 1
        if tag == "a":
            href = attributes.get("href")
            if (
                self.active_cluster is not None
                and type(href) is str
                and href in self.pilot_urls
            ):
                self.pilot_hrefs.append(href)
            if self.active_cluster is not None:
                if (
                    self.active_href is not None
                    or set(attributes) != {"href"}
                    or type(href) is not str
                ):
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.active_href = href
                self.active_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"a", "section"}:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.active_href is not None:
            if self.active_cluster is None:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.cluster_links[self.active_cluster].append(
                (self.active_href, "".join(self.active_parts))
            )
            self.active_href = None
            self.active_parts = []
        if self.active_cluster is None:
            pass
        else:
            self.cluster_depth -= 1
            if self.cluster_depth < 0:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            if self.cluster_depth == 0:
                if tag != "section" or self.active_href is not None:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.active_cluster = None
        if self.cluster_container_depth > 0:
            self.cluster_container_depth -= 1
            if self.cluster_container_depth == 0 and tag != "section":
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)

    def handle_data(self, data: str) -> None:
        if self.active_href is not None:
            self.active_parts.append(data)


def _validate_homepage_html(
    raw: bytes,
    *,
    bound_articles: Mapping[str, int],
    homepage_clusters: Mapping[str, object],
) -> None:
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        document = raw.decode("utf-8", errors="strict")
        parser = _HomepageClusterParser()
        parser.feed(document)
        parser.close()
    except EditorialPilotFailure:
        raise
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    clusters = cast(Mapping[str, Mapping[str, object]], homepage_clusters["clusters"])
    display_order = cast(tuple[str, ...], homepage_clusters["display_order"])
    identities = {
        identity.article_id: identity for identity in PILOT_ARTICLE_IDENTITIES
    }
    expected_all: list[str] = []
    if (
        parser.cluster_container_count != 1
        or parser.active_cluster is not None
        or parser.active_href is not None
        or parser.cluster_container_depth != 0
        or tuple(parser.cluster_links) != display_order
        or parser.review_href_count != 0
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    for cluster_id in display_order:
        posts = cast(tuple[tuple[str, str], ...], clusters[cluster_id]["posts"])
        expected_links = [
            (f"{PILOT_ORIGIN}/{identities[article_id].slug}/", label)
            for article_id, label in posts
            if article_id in bound_articles
        ]
        if parser.cluster_links[cluster_id] != expected_links:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        expected_all.extend(href for href, _label in expected_links)
    if parser.pilot_hrefs != expected_all:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


class _PublicHeadParser(HTMLParser):
    """Collect only the closed head records needed by the public verifier."""

    __slots__ = (
        "body_count",
        "canonical_values",
        "head_closed",
        "head_count",
        "in_head",
        "json_ld_count",
        "json_ld_open",
        "json_ld_parts",
        "metadata",
        "title_count",
        "title_open",
        "title_parts",
    )

    _META_NAMES: Final = frozenset(
        {
            "description",
            "robots",
            "twitter:card",
            "twitter:description",
            "twitter:image",
            "twitter:title",
        }
    )
    _BOT_ROBOTS_NAMES: Final = frozenset({"bingbot", "googlebot", "googlebot-news"})
    _META_PROPERTIES: Final = frozenset(
        {
            "og:description",
            "og:image",
            "og:image:height",
            "og:image:type",
            "og:image:width",
            "og:title",
            "og:type",
            "og:url",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.body_count = 0
        self.canonical_values: list[str] = []
        self.head_closed = False
        self.head_count = 0
        self.in_head = False
        self.json_ld_count = 0
        self.json_ld_open = False
        self.json_ld_parts: list[str] = []
        self.metadata: dict[str, list[str]] = {}
        self.title_count = 0
        self.title_open = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.title_open or self.json_ld_open:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        attributes = _html_attributes(attrs)
        if _has_forbidden_structured_type(attributes):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        if tag == "head":
            if self.in_head or self.head_closed or self.head_count != 0:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.head_count = 1
            self.in_head = True
            return
        if tag == "body":
            if self.in_head or not self.head_closed or self.body_count != 0:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.body_count = 1
            return
        if not self.in_head:
            if tag == "script":
                script_type = attributes.get("type")
                if attributes.get("id") == "raos-structured-data" or (
                    type(script_type) is str and _is_json_ld_mime(script_type)
                ):
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            return
        if tag == "base":
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        if tag == "title":
            if attributes or self.title_count != 0:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.title_count = 1
            self.title_open = True
            return
        if tag == "meta":
            name = attributes.get("name")
            property_name = attributes.get("property")
            normalized_name = (
                name.strip().lower() if type(name) is str and name.isascii() else name
            )
            normalized_property = (
                property_name.strip().lower()
                if type(property_name) is str and property_name.isascii()
                else property_name
            )
            target: str | None = None
            if normalized_name in self._META_NAMES | self._BOT_ROBOTS_NAMES:
                target = normalized_name
            if normalized_property in self._META_PROPERTIES:
                if target is not None:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                target = normalized_property
            if target is not None:
                content = attributes.get("content")
                if type(content) is not str:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.metadata.setdefault(target, []).append(content)
            return
        if tag == "link":
            rel = attributes.get("rel")
            if type(rel) is str and "canonical" in {
                token.lower() for token in rel.split()
            }:
                href = attributes.get("href")
                if type(href) is not str:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.canonical_values.append(href)
            return
        if tag == "script":
            script_type = attributes.get("type")
            is_json_ld = type(script_type) is str and _is_json_ld_mime(script_type)
            is_raos = attributes.get("id") == "raos-structured-data"
            if is_json_ld or is_raos:
                if (
                    not is_json_ld
                    or not is_raos
                    or self.json_ld_count != 0
                    or set(attributes) != {"id", "type"}
                    or script_type != "application/ld+json"
                ):
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                self.json_ld_count = 1
                self.json_ld_open = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "title", "head", "body"}:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            if not self.title_open:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.title_open = False
            return
        if tag == "script" and self.json_ld_open:
            self.json_ld_open = False
            return
        if tag == "head":
            if not self.in_head or self.title_open or self.json_ld_open:
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            self.in_head = False
            self.head_closed = True

    def handle_data(self, data: str) -> None:
        if self.title_open:
            self.title_parts.append(data)
        elif self.json_ld_open:
            self.json_ld_parts.append(data)

    def handle_comment(self, data: str) -> None:
        del data
        if self.title_open or self.json_ld_open:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _is_json_ld_mime(value: str) -> bool:
    if type(value) is not str or not value.isascii():
        return False
    essence = value.strip().split(";", 1)[0].strip().lower()
    return essence == "application/ld+json"


def _expected_json_ld(
    request: ReviewDraftRequest, *, published: str, modified: str
) -> dict[str, object]:
    payload = request.snapshot.payload
    canonical = payload.canonical_url
    organization = f"{PILOT_ORIGIN}/#organization"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@id": f"{canonical}#article",
                "@type": "Article",
                "articleSection": payload.section,
                "author": {"@id": organization},
                "dateModified": modified,
                "datePublished": published,
                "description": payload.description,
                "headline": payload.title,
                "image": [_SOCIAL_IMAGE_URL],
                "inLanguage": "ja-JP",
                "mainEntityOfPage": canonical,
                "publisher": {"@id": organization},
            },
            {
                "@id": f"{canonical}#breadcrumb",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "item": f"{PILOT_ORIGIN}/",
                        "name": "ホーム",
                        "position": 1,
                    },
                    {
                        "@type": "ListItem",
                        "item": canonical,
                        "name": payload.title,
                        "position": 2,
                    },
                ],
            },
            {
                "@id": organization,
                "@type": "Organization",
                "name": "暮らしのしるべ編集部",
                "url": f"{PILOT_ORIGIN}/",
            },
            {
                "@id": f"{PILOT_ORIGIN}/#website",
                "@type": "WebSite",
                "inLanguage": "ja-JP",
                "name": "暮らしのしるべ",
                "publisher": {"@id": organization},
                "url": f"{PILOT_ORIGIN}/",
            },
        ],
    }


def _validate_article_html(
    raw: bytes,
    *,
    request: ReviewDraftRequest,
    published: str,
    modified: str,
    related_target_bound: bool,
    related_navigation: Mapping[str, Mapping[str, object]],
) -> None:
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        document = raw.decode("utf-8", errors="strict")
        parser = _PublicHeadParser()
        parser.feed(document)
        parser.close()
    except EditorialPilotFailure:
        raise
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    payload = request.snapshot.payload
    expected_metadata = {
        "description": payload.description,
        "og:description": payload.og_description,
        "og:image": _SOCIAL_IMAGE_URL,
        "og:image:height": "900",
        "og:image:type": "image/webp",
        "og:image:width": "1600",
        "og:title": payload.og_title,
        "og:type": "article",
        "og:url": payload.canonical_url,
        "robots": _PUBLISHED_ROBOTS,
        "twitter:card": "summary_large_image",
        "twitter:description": payload.og_description,
        "twitter:image": _SOCIAL_IMAGE_URL,
        "twitter:title": payload.og_title,
    }
    if (
        parser.head_count != 1
        or not parser.head_closed
        or parser.body_count != 1
        or parser.title_open
        or parser.json_ld_open
        or "".join(parser.title_parts) != payload.seo_title
        or parser.canonical_values != [payload.canonical_url]
        or set(parser.metadata) != set(expected_metadata)
        or any(
            parser.metadata[key] != [expected]
            for key, expected in expected_metadata.items()
        )
        or parser.json_ld_count != 1
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    observed_json_ld = _decode_surface_json("".join(parser.json_ld_parts))
    if observed_json_ld != _expected_json_ld(
        request, published=published, modified=modified
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        expected_content = _RenderedContentParser()
        expected_content.feed(request.content)
        expected_content.close()
        public_content = _RenderedContentParser()
        public_content.feed(document)
        public_content.close()
        related = _RelatedLinkParser()
        related.feed(document)
        related.close()
        expected_dom = _CanonicalPostContentParser(capture_all=True)
        expected_dom.feed(request.content)
        expected_dom.close()
        public_dom = _CanonicalPostContentParser(capture_all=False)
        public_dom.feed(document)
        public_dom.close()
    except EditorialPilotFailure:
        raise
    except ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    if (
        expected_content.h1_count != 0
        or expected_content.h1_open
        or expected_content.cta_active is not None
        or public_content.h1_count != 1
        or public_content.h1_open
        or "".join(public_content.h1_parts) != payload.title
        or public_content.cta_active is not None
        or public_content.marker_counts != expected_content.marker_counts
        or public_content.cta_records != expected_content.cta_records
        or expected_content.rakuten_hrefs
        != [record[0] for record in expected_content.cta_records]
        or public_content.rakuten_hrefs != expected_content.rakuten_hrefs
        or public_content.product_images != expected_content.product_images
        or not public_content.product_images
        or not public_content.cta_records
        or related.active
        or related.active_href is not None
        or expected_dom.depth != 1
        or public_dom.depth != 0
        or public_dom.container_count != 1
        or public_dom.events != expected_dom.events
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    relation = related_navigation[request.article_id]
    home = cast(tuple[str, str], relation["home"])
    expected_related: list[tuple[str, str]] = []
    target = relation["target"]
    if related_target_bound:
        if type(target) is not tuple:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        target_values = cast(tuple[object, ...], target)
        if len(target_values) != 2:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        target_identity = _related_target_identity(request, related_navigation)
        if target_identity is None:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        expected_related.append(
            (
                f"{PILOT_ORIGIN}/{target_identity.slug}/",
                _public_observation_string(target_values[1]),
            )
        )
    expected_related.append(home)
    if related.container_count != 1 or related.links != expected_related:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _decode_surface_text(raw: bytes, *, maximum: int) -> str:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= maximum
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\x00" in raw
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


class _ReviewLeakTextParser(HTMLParser):
    __slots__ = ("parts", "suppressed_depth")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "template"}:
            self.suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template"} and self.suppressed_depth:
            self.suppressed_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.suppressed_depth == 0 and data:
            self.parts.append(data)


def _normalized_review_leak_text(value: str) -> str:
    decoded = unescape(value)
    decoded = unescape(decoded)
    normalized = unicodedata.normalize("NFKC", decoded).casefold()
    return " ".join(normalized.split())


def _review_leak_views(value: str) -> tuple[str, ...]:
    decoded = unescape(unescape(value))
    parser = _ReviewLeakTextParser()
    try:
        parser.feed(decoded)
        parser.close()
    except ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    raw = _normalized_review_leak_text(decoded)
    visible = _normalized_review_leak_text(" ".join(parser.parts))
    candidates = (raw, visible, re.sub(r"\s+", "", visible))
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _review_visible_leak_views(value: str) -> tuple[str, ...]:
    """Return entity-decoded visible text without URL or attribute material."""

    decoded = unescape(unescape(value))
    parser = _ReviewLeakTextParser()
    try:
        parser.feed(decoded)
        parser.close()
    except ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    visible = _normalized_review_leak_text(" ".join(parser.parts))
    candidates = (visible, re.sub(r"\s+", "", visible))
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _review_leak_fragments(values: tuple[str, ...]) -> set[str]:
    fragments: set[str] = set()
    for value in values:
        for view in _review_visible_leak_views(value):
            materials = (view, re.sub(r"\s+", "", view))
            for material in materials:
                if len(material) < _REVIEW_LEAK_FRAGMENT_LENGTH:
                    continue
                for offset in range(len(material) - _REVIEW_LEAK_FRAGMENT_LENGTH + 1):
                    fragment = material[offset : offset + _REVIEW_LEAK_FRAGMENT_LENGTH]
                    if sum(character.isalnum() for character in fragment) >= 16:
                        fragments.add(fragment)
    return fragments


def _contains_review_leak_fragment(
    observed_views: tuple[str, ...], fragments: set[str]
) -> bool:
    if not fragments:
        return False
    for view in observed_views:
        for material in (view, re.sub(r"\s+", "", view)):
            if len(material) < _REVIEW_LEAK_FRAGMENT_LENGTH:
                continue
            for offset in range(len(material) - _REVIEW_LEAK_FRAGMENT_LENGTH + 1):
                if (
                    material[offset : offset + _REVIEW_LEAK_FRAGMENT_LENGTH]
                    in fragments
                ):
                    return True
    return False


def _review_snapshot_leak_fragments(
    snapshot_json: str, *, canonical_url: str
) -> set[str]:
    """Keep snapshot windows except the expected clean canonical URL itself."""

    allowed_canonical_views = _review_leak_views(canonical_url)
    return {
        fragment
        for fragment in _review_leak_fragments((snapshot_json,))
        if not any(fragment.strip('",') in view for view in allowed_canonical_views)
    }


def _contains_review_cta_fragment(observed_views: tuple[str, ...]) -> bool:
    normalized_fragments = tuple(
        _normalized_review_leak_text(fragment)
        for fragment in _REVIEW_CTA_HIGH_SIGNAL_FRAGMENTS
    )
    return any(
        fragment in observed
        for fragment in normalized_fragments
        for observed in observed_views
    )


def _validate_review_not_found_body(raw: bytes, *, request: ReviewDraftRequest) -> None:
    """Reject a nominal 404 that contains committed editorial material."""

    document = _decode_surface_text(raw, maximum=MAX_RESPONSE_BYTES)
    exact_committed_values = (
        request.title,
        request.excerpt,
        request.content,
        request.snapshot.json_string(),
    )
    article_markers = (
        PILOT_CTA_LABEL,
        PILOT_SNAPSHOT_META_KEY,
        "data-raos-article-id",
        "hb.afl.rakuten.co.jp",
        "raos-comparison",
        "raos-cta",
        "raos-disclosure",
        "raos-product-card",
        "raos-structured-data",
    )
    observed_views = _review_leak_views(document)
    normalized_exact_values = tuple(
        _normalized_review_leak_text(value) for value in exact_committed_values
    )
    article_fragment_sources = (
        request.title,
        request.excerpt,
        request.content,
    )
    snapshot_json = request.snapshot.json_string()
    snapshot_token_sources = (
        snapshot_json,
        request.snapshot.payload_sha256,
        request.snapshot.payload.packet_sha256,
        request.snapshot.payload.visible_content_sha256,
    )
    source_views = tuple(
        view
        for value in (*article_fragment_sources, *snapshot_token_sources)
        for view in _review_leak_views(value)
    )
    allowed_canonical_views = _review_leak_views(request.snapshot.payload.canonical_url)
    meaningful_tokens = {
        match.group(0)
        for view in source_views
        for match in _REVIEW_LEAK_TOKEN.finditer(view)
        if not any(match.group(0) in allowed for allowed in allowed_canonical_views)
    }
    if (
        any(value in document for value in exact_committed_values)
        or any(
            value and any(value in observed for observed in observed_views)
            for value in normalized_exact_values
        )
        or any(
            marker.casefold() in observed
            for marker in article_markers
            for observed in observed_views
        )
        or any(
            token in observed
            for token in meaningful_tokens
            for observed in observed_views
        )
        or _contains_review_cta_fragment(observed_views)
        or _contains_review_leak_fragment(
            observed_views,
            _review_leak_fragments(article_fragment_sources),
        )
        or _contains_review_leak_fragment(
            observed_views,
            _review_snapshot_leak_fragments(
                snapshot_json,
                canonical_url=request.snapshot.payload.canonical_url,
            ),
        )
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _robots_rule_matches(pattern: str, path: str) -> tuple[bool, int]:
    compact = pattern.replace(" ", "")
    if not compact:
        return False, 0
    anchored = compact.endswith("$")
    body = compact[:-1] if anchored else compact
    try:
        expression = "^" + re.escape(body).replace(r"\*", ".*")
        if anchored:
            expression += "$"
        matched = re.search(expression, path, re.ASCII) is not None
    except re.error:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return matched, len(body.replace("*", ""))


def _robots_group_allows(
    groups: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]],
    *,
    agent: str,
    path: str,
) -> bool:
    specific = [group for group in groups if agent in group[0]]
    applicable = specific or [group for group in groups if "*" in group[0]]
    rules: list[tuple[bool, int]] = []
    for _agents, directives in applicable:
        for field, value in directives:
            if field not in {"allow", "disallow"}:
                continue
            matched, specificity = _robots_rule_matches(value, path)
            if matched:
                rules.append((field == "allow", specificity))
    if not rules:
        return True
    maximum = max(specificity for _allowed, specificity in rules)
    return any(allowed for allowed, specificity in rules if specificity == maximum)


def _validate_robots(raw: bytes, *, canonical_path: str) -> None:
    document = _decode_surface_text(raw, maximum=_MAX_ROBOTS_BYTES)
    if (
        type(canonical_path) is not str
        or not canonical_path.startswith("/")
        or "?" in canonical_path
        or "#" in canonical_path
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    active_agents: list[str] = []
    directives: list[tuple[str, str]] = []
    groups: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = []
    group_has_directive = False
    sitemap_lines = [
        line.strip()
        for line in document.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.lstrip().lower().startswith("sitemap:")
    ]
    for raw_line in document.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if group_has_directive:
                groups.append((tuple(active_agents), tuple(directives)))
                active_agents = []
                directives = []
                group_has_directive = False
            active_agents.append(value.lower())
            continue
        if active_agents:
            group_has_directive = True
            directives.append((field, value))
    if active_agents:
        groups.append((tuple(active_agents), tuple(directives)))
    if (
        not any("*" in agents for agents, _directives in groups)
        or sitemap_lines != [f"Sitemap: {PILOT_ORIGIN}/sitemap_index.xml"]
        or any(
            not _robots_group_allows(groups, agent=agent, path=canonical_path)
            for agent in ("*", "bingbot", "googlebot", "googlebot-news")
        )
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _strict_percent_decoded_url_component(value: str) -> str:
    if type(value) is not str or _MALFORMED_PERCENT_ESCAPE.search(value) is not None:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        decoded = unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError, ValueError, TypeError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    if (
        "%" in decoded
        or _REMAINING_PERCENT_ESCAPE.search(decoded) is not None
        or "\\" in decoded
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return unicodedata.normalize("NFKC", decoded)


def _same_origin_url(value: object) -> str:
    if type(value) is not str or value != value.strip() or not value.isascii():
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    decoded_path = _strict_percent_decoded_url_component(parts.path)
    if (
        parts.scheme != "https"
        or parts.netloc != "kurashinoshirube.com"
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or not parts.path.startswith("/")
        or not decoded_path.startswith("/")
        or parts.query
        or parts.fragment
        or value != PILOT_ORIGIN + parts.path
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return value


def _contains_review_draft_href(value: str) -> bool:
    """Return whether one href exposes a temporary RAOS review slug."""

    if type(value) is not str:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        parts = urlsplit(value)
        components = (parts.netloc, parts.path, parts.query, parts.fragment)
    except ValueError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    marker = "raos-review-"
    return marker in value.casefold() or any(
        marker in _strict_percent_decoded_url_component(component).casefold()
        for component in components
    )


def _xml_document(raw: bytes) -> ElementTree.Element:
    text = _decode_surface_text(raw, maximum=MAX_RESPONSE_BYTES)
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _direct_child_text(parent: ElementTree.Element, tag: str) -> str:
    values = [child.text for child in parent if child.tag == tag]
    if len(values) != 1 or type(values[0]) is not str or values[0] != values[0].strip():
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return values[0]


def _validate_sitemap_index(raw: bytes) -> None:
    root = _xml_document(raw)
    namespace = f"{{{_SITEMAP_NAMESPACE}}}"
    if root.tag != namespace + "sitemapindex":
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    locations: list[str] = []
    for child in root:
        if child.tag != namespace + "sitemap" or any(
            item.tag not in {namespace + "loc", namespace + "lastmod"} for item in child
        ):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        locations.append(_same_origin_url(_direct_child_text(child, namespace + "loc")))
    expected = {
        f"{PILOT_ORIGIN}/page-sitemap.xml",
        f"{PILOT_ORIGIN}/post-sitemap.xml",
    }
    if len(locations) != 2 or set(locations) != expected:
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _sitemap_urls(raw: bytes) -> list[str]:
    root = _xml_document(raw)
    namespace = f"{{{_SITEMAP_NAMESPACE}}}"
    if root.tag != namespace + "urlset":
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    locations: list[str] = []
    allowed = {
        namespace + "changefreq",
        namespace + "lastmod",
        namespace + "loc",
        namespace + "priority",
    }
    for child in root:
        if child.tag != namespace + "url" or any(
            item.tag.startswith(namespace) and item.tag not in allowed for item in child
        ):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        locations.append(_same_origin_url(_direct_child_text(child, namespace + "loc")))
    if not locations or len(locations) != len(set(locations)):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
    return locations


def _validate_post_and_page_sitemaps(
    post_raw: bytes, page_raw: bytes, *, canonical_url: str
) -> None:
    post_urls = _sitemap_urls(post_raw)
    page_urls = _sitemap_urls(page_raw)
    if (
        post_urls.count(canonical_url) != 1
        or canonical_url in page_urls
        or any(_contains_review_draft_href(url) for url in (*post_urls, *page_urls))
    ):
        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)


def _bounded_body(
    response: SelfHostedWordPressHttpsResponse,
    *,
    maximum: int = MAX_RESPONSE_BYTES,
    minimum: int = 2,
) -> bytes:
    if type(minimum) is not int or not 0 <= minimum <= maximum:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    if not hasattr(response, "getheader") or not hasattr(response, "read"):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    getheader = response.getheader
    content_encoding = getheader("Content-Encoding")
    content_length = getheader("Content-Length")
    transfer_encoding = getheader("Transfer-Encoding")
    if content_encoding not in {None, "identity"}:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    if transfer_encoding not in {None, "chunked"} or (
        transfer_encoding is not None and content_length is not None
    ):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    if content_length is not None:
        if (
            type(content_length) is not str
            or re.fullmatch(r"(?:0|[1-9][0-9]*)", content_length, re.ASCII) is None
            or int(content_length) > maximum
        ):
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    body = response.read(maximum + 1)
    if type(body) is not bytes or not minimum <= len(body) <= maximum:
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    if content_length is not None and len(body) != int(content_length):
        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
    return body


def owner_gate_relative_path(request: ReviewDraftRequest, command: str) -> Path:
    if type(request) is not ReviewDraftRequest or command not in _ALLOWED_COMMANDS:
        _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
    return OWNER_GATE_DIRECTORY / (
        f"{request.article_id}.{request.packet_sha256}.{command}.v1.json"
    )


def _require_private_directory(path: Path) -> None:
    try:
        observed = path.lstat()
    except OSError:
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)


def require_owner_live_gate(
    repository_root: Path, request: ReviewDraftRequest, command: str
) -> None:
    if not repository_root.is_absolute() or type(request) is not ReviewDraftRequest:
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    _require_private_directory(repository_root / ".secrets")
    _require_private_directory(repository_root / OWNER_GATE_DIRECTORY.parent)
    gate_directory = repository_root / OWNER_GATE_DIRECTORY
    _require_private_directory(gate_directory)
    path = repository_root / owner_gate_relative_path(request, command)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != _PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= _MAX_GATE_BYTES
        ):
            _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
        raw = os.read(descriptor, _MAX_GATE_BYTES + 1)
        after = os.fstat(descriptor)
        if (
            len(raw) != before.st_size
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        gate = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_gate_pairs,
            parse_constant=_reject_gate_constant,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    if type(gate) is not dict:
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)
    document = cast(dict[str, object], gate)
    if (
        frozenset(document) != _GATE_KEYS
        or document["schema"] != OWNER_GATE_SCHEMA
        or document["authority"] != OWNER_GATE_AUTHORITY
        or document["origin"] != PILOT_ORIGIN
        or document["article_id"] != request.article_id
        or document["packet_sha256"] != request.packet_sha256
        or document["request_sha256"] != request.request_sha256
        or document["command"] != command
    ):
        _fail(EditorialPilotFailureCode.OWNER_GATE_REQUIRED)


@final
class OfficialSelfHostedEditorialPilotWordPressAdapter:
    """One-attempt adapter with no caller-selected origin, path, or method."""

    __slots__ = (
        "_attempt_lock",
        "_attempted",
        "_factory",
        "_homepage_clusters",
        "_root",
        "_related_navigation",
        "_target_command",
        "_target_request_sha256",
        "_target_resolution_used",
        "_target_value",
    )

    def __init__(
        self,
        repository_root: Path,
        connection_factory: object = SystemSelfHostedWordPressHttpsConnectionFactory(),
    ) -> None:
        if not repository_root.is_absolute() or not isinstance(
            connection_factory, SelfHostedWordPressHttpsConnectionFactory
        ):
            _fail()
        self._root = repository_root
        self._related_navigation = _load_theme_related_navigation(repository_root)
        self._homepage_clusters = _load_theme_homepage_clusters(repository_root)
        self._factory = connection_factory
        self._attempt_lock = threading.Lock()
        self._attempted = False
        self._target_command: str | None = None
        self._target_request_sha256: str | None = None
        self._target_resolution_used = False
        self._target_value: int | None = None

    def __repr__(self) -> str:
        return "OfficialSelfHostedEditorialPilotWordPressAdapter(<redacted>)"

    def preflight(self, request: ReviewDraftRequest, command: str) -> None:
        require_owner_live_gate(self._root, request, command)
        try:
            status = OwnerPrivateSelfHostedWordPressCredentialStore(
                self._root
            ).metadata_status()
        except SelfHostedWordPressFailure:
            _fail(EditorialPilotFailureCode.CREDENTIAL_UNAVAILABLE)
        if status != "METADATA_READY":
            _fail(EditorialPilotFailureCode.CREDENTIAL_UNAVAILABLE)
        require_clean_self_hosted_wordpress_environment()

    def _claim_attempt(self) -> None:
        with self._attempt_lock:
            if self._attempted:
                _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
            self._attempted = True

    def _connection(self) -> SelfHostedWordPressHttpsConnection:
        try:
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                _fail()
            return self._factory.open(
                host=SELF_HOSTED_WORDPRESS_HOST,
                port=SELF_HOSTED_WORDPRESS_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
        except EditorialPilotFailure:
            raise
        except BaseException:
            _fail()

    def _credentials_header(self) -> str:
        try:
            return (
                OwnerPrivateSelfHostedWordPressCredentialStore(self._root)
                .read()
                .authorization_header()
            )
        except SelfHostedWordPressFailure:
            _fail(EditorialPilotFailureCode.CREDENTIAL_UNAVAILABLE)

    def _exchange(
        self,
        *,
        request: ReviewDraftRequest,
        command: str,
        method: str,
        path: str,
        body: bytes,
        expected_http_status: int,
        expect_collection: bool,
    ) -> tuple[object, str]:
        expected_exchange = {
            "create-review-draft": (
                "POST",
                self._create_path(request),
                canonical_json_bytes(request.wordpress_body()),
                201,
                False,
            ),
            "recover-create-review-draft": (
                "GET",
                self._collection_path(request, status=PILOT_REVIEW_STATUS),
                b"",
                200,
                True,
            ),
        }.get(command)
        if expected_exchange != (
            method,
            path,
            body,
            expected_http_status,
            expect_collection,
        ):
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        self.preflight(request, command)
        self._claim_attempt()
        authorization = self._credentials_header()
        connection = self._connection()
        attempted = False
        try:
            with _deadline(CONNECT_TIMEOUT_SECONDS):
                connection.connect()
            attempted = True
            with _deadline(READ_TIMEOUT_SECONDS):
                connection.set_read_timeout(READ_TIMEOUT_SECONDS)
                connection.request(
                    method,
                    path,
                    body,
                    {
                        "Accept": "application/json",
                        "Authorization": authorization,
                        "Connection": "close",
                        "Content-Length": str(len(body)),
                        **(
                            {"Content-Type": "application/json"}
                            if method == "POST"
                            else {}
                        ),
                        "Host": SELF_HOSTED_WORDPRESS_HOST,
                        "User-Agent": "RAOS-ST-1704-owner-gated/1",
                    },
                )
                response = connection.getresponse()
                content_type = response.getheader("Content-Type")
                if (
                    type(response.status) is not int
                    or response.status != expected_http_status
                    or type(content_type) is not str
                    or _CONTENT_TYPE.fullmatch(content_type) is None
                    or response.getheader("Location") is not None
                ):
                    _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
                raw = _bounded_body(response)
                decoded = _decode_response(raw)
                if expect_collection:
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
                    collection = cast(list[object], decoded)
                    total = response.getheader("X-WP-Total")
                    pages = response.getheader("X-WP-TotalPages")
                    expected_pages = "0" if not collection else "1"
                    if (
                        not 0 <= len(collection) <= 100
                        or total != str(len(collection))
                        or pages != expected_pages
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
                    return collection, bytes_sha256(raw)
                return decoded, bytes_sha256(raw)
        except EditorialPilotFailure:
            raise
        except BaseException:
            _fail(
                EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
                if attempted
                else EditorialPilotFailureCode.TRANSPORT_REFUSED
            )
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def _fixed_public_read(
        self,
        request: ReviewDraftRequest,
        *,
        kind: str,
        authorization: str,
    ) -> bytes:
        return self._fixed_public_capture(
            request, kind=kind, authorization=authorization
        ).body

    def _fixed_public_capture(
        self,
        request: ReviewDraftRequest,
        *,
        kind: str,
        authorization: str,
    ) -> _FixedPublicReadCapture:
        if kind not in _PUBLIC_KINDS or type(authorization) is not str:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        related_identity = (
            _related_target_identity(request, self._related_navigation)
            if kind == "related-target"
            else None
        )
        if kind == "related-target" and related_identity is None:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        exchanges = {
            "wordpress-post": (
                self._collection_path(request, status="publish"),
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "draft-inventory": (
                self._collection_path(request, status=PILOT_REVIEW_STATUS),
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "publication-target": (
                f"{PILOT_POSTS_PATH}?context=edit&slug={request.public_slug}"
                f"&status=publish&_fields={_TARGET_FIELDS}&per_page=100",
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "related-target": (
                (
                    f"{PILOT_POSTS_PATH}?context=edit&slug="
                    f"{related_identity.slug if related_identity is not None else ''}"
                    f"&status=publish&_fields={_RECOVERY_FIELDS}&per_page=2"
                ),
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "homepage-targets": (
                (
                    f"{PILOT_POSTS_PATH}?context=edit&status=publish&slug="
                    + "%2C".join(identity.slug for identity in PILOT_ARTICLE_IDENTITIES)
                    + f"&page=1&per_page=5&_fields={_RECOVERY_FIELDS}"
                ),
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "article-html": (
                f"/{request.snapshot.payload.slug}/",
                "text/html",
                _HTML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "homepage-html": (
                "/",
                "text/html",
                _HTML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "category": (
                f"{PILOT_POSTS_PATH.removesuffix('/posts')}/categories"
                "?search=%E6%9A%AE%E3%82%89%E3%81%97%E3%81%AE%E9%81%93%E5%85%B7"
                "&_fields=id%2Cname%2Cslug&per_page=100",
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "robots": (
                "/robots.txt",
                "text/plain",
                _ROBOTS_CONTENT_TYPE,
                _MAX_ROBOTS_BYTES,
                False,
                200,
            ),
            "sitemap-index": (
                "/sitemap_index.xml",
                "application/xml,text/xml;q=0.9",
                _XML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "post-sitemap": (
                "/post-sitemap.xml",
                "application/xml,text/xml;q=0.9",
                _XML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "page-sitemap": (
                "/page-sitemap.xml",
                "application/xml,text/xml;q=0.9",
                _XML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "core-sitemap": (
                "/wp-sitemap.xml",
                "text/html",
                _HTML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                301,
            ),
            "review-draft-rest": (
                f"{PILOT_POSTS_PATH}?context=edit&slug={request.slug}"
                f"&status={PILOT_REVIEW_STATUS}&_fields={_RECOVERY_FIELDS}"
                "&page=1&per_page=100",
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                True,
                200,
            ),
            "review-public-rest": (
                f"{PILOT_POSTS_PATH}?slug={request.slug}&status=publish"
                f"&_fields={_TARGET_FIELDS}&page=1&per_page=100",
                "application/json",
                _CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                200,
            ),
            "review-url-html": (
                f"/{request.slug}/",
                "text/html",
                _HTML_CONTENT_TYPE,
                MAX_RESPONSE_BYTES,
                False,
                404,
            ),
        }
        (
            path,
            accept,
            content_type_pattern,
            maximum,
            authenticated,
            expected_status,
        ) = exchanges[kind]
        headers = {
            "Accept": accept,
            "Connection": "close",
            "Content-Length": "0",
            "Host": SELF_HOSTED_WORDPRESS_HOST,
            "User-Agent": "RAOS-ST-1704-owner-gated/1",
        }
        if authenticated:
            headers["Authorization"] = authorization
        connection = self._connection()
        attempted = False
        try:
            with _deadline(CONNECT_TIMEOUT_SECONDS):
                connection.connect()
            attempted = True
            with _deadline(READ_TIMEOUT_SECONDS):
                connection.set_read_timeout(READ_TIMEOUT_SECONDS)
                connection.request("GET", path, b"", headers)
                response = connection.getresponse()
                http_status = response.status
                content_type = response.getheader("Content-Type")
                location_header = response.getheader("Location")
                redirect_by_header = response.getheader("X-Redirect-By")
                x_wp_total = response.getheader("X-WP-Total")
                x_wp_total_pages = response.getheader("X-WP-TotalPages")
                exact_yoast_core_sitemap_redirect = (
                    kind == "core-sitemap"
                    and http_status == 301
                    and location_header == _YOAST_CORE_SITEMAP_REDIRECT
                    and redirect_by_header == _YOAST_REDIRECT_BY
                    and response.getheader("Content-Length") == "0"
                    and response.getheader("Content-Encoding") is None
                    and response.getheader("Transfer-Encoding") is None
                    and response.getheader("Link") is None
                    and x_wp_total is None
                    and x_wp_total_pages is None
                )
                if (
                    type(http_status) is not int
                    or (kind == "core-sitemap" and not exact_yoast_core_sitemap_redirect)
                    or (kind != "core-sitemap" and http_status != expected_status)
                    or type(content_type) is not str
                    or content_type_pattern.fullmatch(content_type) is None
                    or (kind != "core-sitemap" and location_header is not None)
                    or (x_wp_total is not None and type(x_wp_total) is not str)
                    or (
                        x_wp_total_pages is not None
                        and type(x_wp_total_pages) is not str
                    )
                ):
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                if kind == "article-html":
                    x_robots = response.getheader("X-Robots-Tag")
                    if type(x_robots) is str:
                        x_robots_tokens = {
                            token.lower()
                            for token in re.split(r"[\s,;]+", x_robots)
                            if token
                        }
                        if x_robots_tokens & {"noindex", "none"}:
                            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                raw = _bounded_body(
                    response,
                    maximum=maximum,
                    minimum=0 if kind == "core-sitemap" else 2,
                )
                if kind == "core-sitemap" and raw:
                    _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                if kind == "wordpress-post":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    if (
                        len(collection) != 1
                        or response.getheader("X-WP-Total") != "1"
                        or response.getheader("X-WP-TotalPages") != "1"
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "draft-inventory":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
                    collection = cast(list[object], decoded)
                    expected_pages = "0" if not collection else "1"
                    if (
                        not 0 <= len(collection) <= 100
                        or response.getheader("X-WP-Total") != str(len(collection))
                        or response.getheader("X-WP-TotalPages") != expected_pages
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
                elif kind == "publication-target":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    expected_count = (
                        1
                        if request.article_id == "st1703-first-suitcase-comparison"
                        else 0
                    )
                    if (
                        len(collection) != expected_count
                        or response.getheader("X-WP-Total") != str(expected_count)
                        or response.getheader("X-WP-TotalPages")
                        != ("1" if expected_count else "0")
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "related-target":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    if (
                        len(collection) not in {0, 1}
                        or response.getheader("X-WP-Total") != str(len(collection))
                        or response.getheader("X-WP-TotalPages")
                        != ("1" if collection else "0")
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "homepage-targets":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    if (
                        not 1 <= len(collection) <= len(PILOT_ARTICLE_IDENTITIES)
                        or response.getheader("X-WP-Total") != str(len(collection))
                        or response.getheader("X-WP-TotalPages") != "1"
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "category":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    if (
                        len(collection) != 1
                        or response.getheader("X-WP-Total") != "1"
                        or response.getheader("X-WP-TotalPages") != "1"
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "review-public-rest":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    if (
                        collection
                        or response.getheader("X-WP-Total") != "0"
                        or response.getheader("X-WP-TotalPages") != "0"
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                elif kind == "review-draft-rest":
                    decoded = _decode_response(raw)
                    if type(decoded) is not list:
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                    collection = cast(list[object], decoded)
                    expected_count = (
                        1
                        if request.article_id == "st1703-first-suitcase-comparison"
                        else 0
                    )
                    if (
                        len(collection) != expected_count
                        or x_wp_total != str(expected_count)
                        or x_wp_total_pages != ("1" if expected_count else "0")
                        or not _collection_link_header_is_fixed(
                            response.getheader("Link")
                        )
                    ):
                        _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
                return _FixedPublicReadCapture(
                    kind=kind,
                    path=path,
                    http_status=http_status,
                    content_type=content_type,
                    location_header=location_header,
                    x_wp_total=x_wp_total,
                    x_wp_total_pages=x_wp_total_pages,
                    body=raw,
                )
        except EditorialPilotFailure:
            raise
        except BaseException:
            _fail(
                EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
                if attempted
                else EditorialPilotFailureCode.TRANSPORT_REFUSED
            )
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        return self._create(
            request, self._resolved_target(request, "create-review-draft")
        )

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None:
        if type(request) is not ReviewDraftRequest or command not in {
            "create-review-draft",
            "recover-create-review-draft",
        }:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        self.preflight(request, command)
        with self._attempt_lock:
            if self._target_resolution_used:
                _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
            self._target_resolution_used = True
            self._target_command = command
            self._target_request_sha256 = request.request_sha256
        authorization = self._credentials_header()
        raw = self._fixed_public_read(
            request,
            kind="publication-target",
            authorization=authorization,
        )
        rows = cast(list[object], _decode_response(raw))
        target: int | None = None
        if rows:
            post = _mapping(rows[0])
            if (
                set(post) != {"id", "slug", "status", "type"}
                or post["type"] != "post"
                or post["slug"] != request.public_slug
                or post["status"] != "publish"
                or type(post["id"]) is not int
                or not 1 <= post["id"] <= (1 << 63) - 1
            ):
                _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
            target = post["id"]
        with self._attempt_lock:
            self._target_value = target
        if command == "create-review-draft":
            inventory_raw = self._fixed_public_read(
                request,
                kind="draft-inventory",
                authorization=authorization,
            )
            if _matching_snapshot_drafts(_decode_response(inventory_raw), request):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
            if _review_slug_family_drafts(_decode_response(inventory_raw), request):
                _fail(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
        return target

    def _resolved_target(self, request: ReviewDraftRequest, command: str) -> int | None:
        with self._attempt_lock:
            if (
                not self._target_resolution_used
                or self._target_command != command
                or self._target_request_sha256 != request.request_sha256
                or (
                    request.article_id == "st1703-first-suitcase-comparison"
                    and self._target_value is None
                )
                or (
                    request.article_id != "st1703-first-suitcase-comparison"
                    and self._target_value is not None
                )
            ):
                _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
            return self._target_value

    def _create(
        self, request: ReviewDraftRequest, target_public_post_id: int | None
    ) -> ReviewDraftReceipt:
        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.REQUEST_INVALID)
        response, response_sha256 = self._exchange(
            request=request,
            command="create-review-draft",
            method="POST",
            path=self._create_path(request),
            body=canonical_json_bytes(request.wordpress_body()),
            expected_http_status=201,
            expect_collection=False,
        )
        draft_id = _validate_post(
            response,
            request=request,
            expected_status=PILOT_REVIEW_STATUS,
        )
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=response_sha256,
            draft_id=draft_id,
            disposition=ReviewDraftDisposition.OWNER_LIVE_CREATED,
            target_public_post_id=target_public_post_id,
            recorded_evidence_only=False,
            live_authority=True,
        )

    def _create_path(self, request: ReviewDraftRequest) -> str:
        if type(request) is not ReviewDraftRequest or request.path != PILOT_CREATE_PATH:
            _fail(EditorialPilotFailureCode.REQUEST_INVALID)
        return request.path

    def _collection_path(self, request: ReviewDraftRequest, *, status: str) -> str:
        if status not in {PILOT_REVIEW_STATUS, "publish"}:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        if status == PILOT_REVIEW_STATUS:
            return (
                f"{PILOT_POSTS_PATH}?context=edit&status=draft&page=1&per_page=100"
                f"&_fields={_RECOVERY_FIELDS}"
            )
        slug = request.snapshot.payload.slug
        return (
            f"{PILOT_POSTS_PATH}?context=edit&slug={slug}&status={status}"
            f"&_fields={_RECOVERY_FIELDS}&per_page=100"
        )

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        target_public_post_id = self._resolved_target(
            request, "recover-create-review-draft"
        )
        if type(request) is not ReviewDraftRequest:
            _fail(EditorialPilotFailureCode.REQUEST_INVALID)
        response, response_sha256 = self._exchange(
            request=request,
            command="recover-create-review-draft",
            method="GET",
            path=self._collection_path(request, status=PILOT_REVIEW_STATUS),
            body=b"",
            expected_http_status=200,
            expect_collection=True,
        )
        posts = cast(list[object], response)
        matching_posts = _matching_snapshot_drafts(posts, request)
        family_posts = _review_slug_family_drafts(posts, request)
        if (
            len(matching_posts) != 1
            or len(family_posts) != 1
            or _mapping(matching_posts[0]).get("id")
            != _mapping(family_posts[0]).get("id")
        ):
            _fail(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        draft_id = _validate_post(
            matching_posts[0],
            request=request,
            expected_status=PILOT_REVIEW_STATUS,
        )
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=response_sha256,
            draft_id=draft_id,
            disposition=ReviewDraftDisposition.OWNER_LIVE_RECOVERED,
            target_public_post_id=target_public_post_id,
            recorded_evidence_only=False,
            live_authority=True,
        )

    def _verify_public_surfaces(
        self,
        request: ReviewDraftRequest,
        expected_public_post_id: int,
        *,
        command: str,
    ) -> PublicVerification:
        if type(request) is not ReviewDraftRequest or command not in {
            "verify-carry-on-single-url",
            "verify-public",
        }:
            _fail(EditorialPilotFailureCode.REQUEST_INVALID)
        if (
            type(expected_public_post_id) is not int
            or not 1 <= expected_public_post_id <= (1 << 63) - 1
        ):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        self.preflight(request, command)
        self._claim_attempt()
        authorization = self._credentials_header()
        rest_raw = self._fixed_public_read(
            request,
            kind="wordpress-post",
            authorization=authorization,
        )
        posts = cast(list[object], _decode_response(rest_raw))
        post_id = _validate_post(
            posts[0],
            request=request,
            expected_status="publish",
        )
        if post_id != expected_public_post_id:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        published, modified = _public_post_dates(posts[0])
        category_raw = self._fixed_public_read(
            request,
            kind="category",
            authorization=authorization,
        )
        _validate_public_category(posts[0], category_raw)
        related_identity = _related_target_identity(request, self._related_navigation)
        if related_identity is None:
            related_target_bound = False
            related_target_sha256 = canonical_sha256(
                {"article_id": request.article_id, "related_target": None}
            )
        else:
            related_target_raw = self._fixed_public_read(
                request,
                kind="related-target",
                authorization=authorization,
            )
            related_target_bound = _related_target_is_bound(
                related_target_raw, request, self._related_navigation
            )
            related_target_sha256 = bytes_sha256(related_target_raw)
        homepage_targets_raw = self._fixed_public_read(
            request,
            kind="homepage-targets",
            authorization=authorization,
        )
        bound_home_articles = _bound_home_articles(homepage_targets_raw)
        if bound_home_articles.get(request.article_id) != expected_public_post_id:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        article_raw = self._fixed_public_read(
            request,
            kind="article-html",
            authorization=authorization,
        )
        homepage_raw = self._fixed_public_read(
            request,
            kind="homepage-html",
            authorization=authorization,
        )
        robots_raw = self._fixed_public_read(
            request,
            kind="robots",
            authorization=authorization,
        )
        sitemap_index_raw = self._fixed_public_read(
            request,
            kind="sitemap-index",
            authorization=authorization,
        )
        post_sitemap_raw = self._fixed_public_read(
            request,
            kind="post-sitemap",
            authorization=authorization,
        )
        page_sitemap_raw = self._fixed_public_read(
            request,
            kind="page-sitemap",
            authorization=authorization,
        )
        core_sitemap_raw = self._fixed_public_read(
            request,
            kind="core-sitemap",
            authorization=authorization,
        )
        review_draft_rest_capture = self._fixed_public_capture(
            request,
            kind="review-draft-rest",
            authorization=authorization,
        )
        review_draft_rows = cast(
            list[object], _decode_response(review_draft_rest_capture.body)
        )
        review_draft_post_id = (
            _validate_post(
                review_draft_rows[0],
                request=request,
                expected_status=PILOT_REVIEW_STATUS,
            )
            if request.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
            else None
        )
        if (
            request.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
            and review_draft_post_id
            != PILOT_CARRY_ON_RECONCILIATION_REVIEW_DRAFT_POST_ID
        ):
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        review_public_rest_capture = self._fixed_public_capture(
            request,
            kind="review-public-rest",
            authorization=authorization,
        )
        review_url_html_capture = self._fixed_public_capture(
            request,
            kind="review-url-html",
            authorization=authorization,
        )
        _validate_review_not_found_body(review_url_html_capture.body, request=request)
        _validate_article_html(
            article_raw,
            request=request,
            published=published,
            modified=modified,
            related_target_bound=related_target_bound,
            related_navigation=self._related_navigation,
        )
        _validate_homepage_html(
            homepage_raw,
            bound_articles=bound_home_articles,
            homepage_clusters=self._homepage_clusters,
        )
        _validate_robots(
            robots_raw, canonical_path=f"/{request.snapshot.payload.slug}/"
        )
        _validate_sitemap_index(sitemap_index_raw)
        _validate_post_and_page_sitemaps(
            post_sitemap_raw,
            page_sitemap_raw,
            canonical_url=request.snapshot.payload.canonical_url,
        )
        surface_hashes = {
            "article_html_sha256": bytes_sha256(article_raw),
            "category_sha256": bytes_sha256(category_raw),
            "core_sitemap_sha256": bytes_sha256(core_sitemap_raw),
            "homepage_html_sha256": bytes_sha256(homepage_raw),
            "homepage_targets_sha256": bytes_sha256(homepage_targets_raw),
            "page_sitemap_sha256": bytes_sha256(page_sitemap_raw),
            "post_sitemap_sha256": bytes_sha256(post_sitemap_raw),
            "related_target_sha256": related_target_sha256,
            "review_draft_rest_evidence_sha256": (
                review_draft_rest_capture.evidence_sha256()
            ),
            "review_public_rest_evidence_sha256": (
                review_public_rest_capture.evidence_sha256()
            ),
            "review_url_html_evidence_sha256": (
                review_url_html_capture.evidence_sha256()
            ),
            "robots_sha256": bytes_sha256(robots_raw),
            "sitemap_index_sha256": bytes_sha256(sitemap_index_raw),
        }
        return PublicVerification(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256=bytes_sha256(rest_raw),
            post_id=post_id,
            status="publish",
            target_public_post_id=(
                expected_public_post_id
                if request.article_id == PILOT_CARRY_ON_RECONCILIATION_ARTICLE_ID
                else None
            ),
            expected_public_post_id=expected_public_post_id,
            article_html_sha256=surface_hashes["article_html_sha256"],
            category_sha256=surface_hashes["category_sha256"],
            core_sitemap_sha256=surface_hashes["core_sitemap_sha256"],
            homepage_html_sha256=surface_hashes["homepage_html_sha256"],
            homepage_targets_sha256=surface_hashes["homepage_targets_sha256"],
            robots_sha256=surface_hashes["robots_sha256"],
            sitemap_index_sha256=surface_hashes["sitemap_index_sha256"],
            post_sitemap_sha256=surface_hashes["post_sitemap_sha256"],
            page_sitemap_sha256=surface_hashes["page_sitemap_sha256"],
            related_target_sha256=surface_hashes["related_target_sha256"],
            review_draft_post_id=review_draft_post_id,
            review_draft_rest_evidence_sha256=surface_hashes[
                "review_draft_rest_evidence_sha256"
            ],
            review_public_rest_evidence_sha256=surface_hashes[
                "review_public_rest_evidence_sha256"
            ],
            review_url_html_evidence_sha256=surface_hashes[
                "review_url_html_evidence_sha256"
            ],
            public_surface_sha256=canonical_sha256(surface_hashes),
            verified_checks=PILOT_PUBLIC_VERIFICATION_CHECKS,
            public_surface_verified=True,
            recorded_evidence_only=False,
            live_read=True,
        )

    def verify_public(
        self, request: ReviewDraftRequest, expected_public_post_id: int
    ) -> PublicVerification:
        return self._verify_public_surfaces(
            request,
            expected_public_post_id,
            command="verify-public",
        )

    def verify_carry_on_single_url(
        self, binding: CarryOnSingleUrlReconciliationBinding
    ) -> CarryOnSingleUrlReconciliationEvidence:
        if type(binding) is not CarryOnSingleUrlReconciliationBinding:
            _fail(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)
        verification = self._verify_public_surfaces(
            binding.request,
            binding.target_public_post_id,
            command="verify-carry-on-single-url",
        )
        if verification.review_draft_post_id != binding.expected_review_draft_post_id:
            _fail(EditorialPilotFailureCode.PUBLIC_OBSERVATION_MISMATCH)
        return CarryOnSingleUrlReconciliationEvidence.from_strict_verification(
            binding, verification
        )


__all__ = [
    "OWNER_GATE_AUTHORITY",
    "OWNER_GATE_DIRECTORY",
    "OWNER_GATE_SCHEMA",
    "OfficialSelfHostedEditorialPilotWordPressAdapter",
    "owner_gate_relative_path",
    "require_owner_live_gate",
]
