from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ProviderManifest:
    key: str
    display_name: str
    aliases: tuple[str, ...]
    env_prefix: str
    account_id_label: str
    supported_modes: tuple[str, ...] = ("api", "feed", "file")
    supported_auth_types: tuple[str, ...] = (
        "none",
        "bearer",
        "api_key_header",
        "api_key_query",
        "basic",
        "oauth2_client_credentials",
        "custom_headers",
    )


PROVIDERS: Final[dict[str, ProviderManifest]] = {
    manifest.key: manifest
    for manifest in (
        ProviderManifest(
            key="a8net",
            display_name="A8.net",
            aliases=("a8", "a8.net"),
            env_prefix="A8NET",
            account_id_label="media/member account ID",
        ),
        ProviderManifest(
            key="valuecommerce",
            display_name="ValueCommerce",
            aliases=("value-commerce", "vc", "バリューコマース"),
            env_prefix="VALUECOMMERCE",
            account_id_label="publisher/site account ID",
        ),
        ProviderManifest(
            key="moshimo",
            display_name="もしもアフィリエイト",
            aliases=("moshimo-affiliate", "もしも", "もしもアフィリエイト"),
            env_prefix="MOSHIMO",
            account_id_label="publisher account ID",
        ),
        ProviderManifest(
            key="linkshare",
            display_name="LinkShare Affiliate / Rakuten Advertising",
            aliases=("linkshare-affiliate", "rakuten-advertising", "リンクシェア"),
            env_prefix="LINKSHARE",
            account_id_label="publisher/SID account ID",
        ),
        ProviderManifest(
            key="accesstrade",
            display_name="AccessTrade",
            aliases=("access-trade", "at", "アクセストレード"),
            env_prefix="ACCESSTRADE",
            account_id_label="partner/site account ID",
        ),
        ProviderManifest(
            key="afb",
            display_name="afb",
            aliases=("affiliate-b", "アフィビー"),
            env_prefix="AFB",
            account_id_label="partner account ID",
        ),
    )
}

_ALIAS_INDEX: Final[dict[str, str]] = {
    alias.casefold(): manifest.key
    for manifest in PROVIDERS.values()
    for alias in (manifest.key, manifest.display_name, *manifest.aliases)
}


def get_provider(value: str) -> ProviderManifest:
    try:
        return PROVIDERS[_ALIAS_INDEX[value.strip().casefold()]]
    except KeyError as exc:
        supported = ", ".join(PROVIDERS)
        raise KeyError(f"Unknown provider {value!r}; supported: {supported}") from exc


def provider_skeleton(manifest: ProviderManifest) -> dict[str, object]:
    """Return a disabled, secret-free provider configuration."""
    return {
        "display_name": manifest.display_name,
        "enabled": False,
        "account_id": "",
        "mode": "api",
        "auth": {
            "type": "none",
        },
        "resources": {
            "programs": {
                "enabled": False,
                "endpoint": "",
                "format": "auto",
                "record_path": "",
                "pagination": {"type": "none", "max_pages": 1},
            },
            "products": {
                "enabled": False,
                "endpoint": "",
                "format": "auto",
                "record_path": "",
                "pagination": {"type": "none", "max_pages": 1},
            },
            "reports": {
                "enabled": False,
                "endpoint": "",
                "format": "auto",
                "record_path": "",
                "pagination": {"type": "none", "max_pages": 1},
            },
        },
    }
