from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from .client import EndpointValidator, FetchError, fetch_resource
from .config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    atomic_write_config,
    initial_config,
    load_config,
    provider_diagnostics,
    redact,
    validate_config,
)
from .providers import PROVIDERS, get_provider
from .storage import persist_batch


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.affiliate_ingestion",
        description=(
            "Official API/feed/file ingestion for A8.net, ValueCommerce, "
            "もしも, LinkShare, AccessTrade and afb"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"owner-only account config (default: {DEFAULT_CONFIG_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init-config", help="create a disabled, secret-free local template"
    )
    init.add_argument("--force", action="store_true")

    sub.add_parser("list-providers", help="list the six configured provider adapters")

    register = sub.add_parser("register", help="register one approved provider account")
    register.add_argument("provider")
    register.add_argument("--resource", default="programs")
    register.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    register.add_argument(
        "--non-interactive",
        action="store_true",
        help="apply only --set values; secrets should preferably use env:NAME",
    )

    doctor = sub.add_parser(
        "doctor", help="validate configuration without network access"
    )
    doctor.add_argument("provider", nargs="?", default="all")
    doctor.add_argument("--show-redacted", action="store_true")

    fetch = sub.add_parser("fetch", help="fetch configured resources for one provider")
    fetch.add_argument("provider")
    fetch.add_argument("--resource", default="all")
    fetch.add_argument("--dry-run", action="store_true")

    fetch_all = sub.add_parser(
        "fetch-all", help="fetch every enabled provider/resource"
    )
    fetch_all.add_argument("--dry-run", action="store_true")
    return parser


def _parse_set(values: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ConfigError("--set requires KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError("--set key cannot be empty")
        parsed[key] = value
    return parsed


def _bool_prompt(label: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{label} {suffix}: ").strip().casefold()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def _prompt(label: str, default: str = "", *, secret: bool = False) -> str:
    suffix = f" [{default}]" if default and not secret else ""
    reader = getpass.getpass if secret else input
    value = reader(f"{label}{suffix}: ").strip()
    return value or default


def _set_path(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _coerce(value: str) -> Any:
    lowered = value.casefold()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value


def _register(args: argparse.Namespace) -> int:
    manifest = get_provider(args.provider)
    config_path = Path(args.config).expanduser()
    config = load_config(config_path) if config_path.exists() else initial_config()
    provider = config["providers"][manifest.key]
    resource_name = args.resource.strip()
    resources = provider.setdefault("resources", {})
    resource = resources.setdefault(
        resource_name,
        {
            "enabled": False,
            "endpoint": "",
            "format": "auto",
            "record_path": "",
            "pagination": {"type": "none", "max_pages": 1},
        },
    )
    supplied = _parse_set(args.set)
    for key, value in supplied.items():
        if key.startswith("provider."):
            field = key.removeprefix("provider.")
            _set_path(provider, field, _coerce(value) if field == "enabled" else value)
        elif key.startswith("resource."):
            _set_path(resource, key.removeprefix("resource."), _coerce(value))
        elif key.startswith(("auth.", "account_")):
            _set_path(provider, key, value)
        else:
            _set_path(resource, key, _coerce(value))
    if not args.non_interactive:
        print(f"Registering {manifest.display_name}; no network request will be made.")
        provider["account_id"] = _prompt(
            manifest.account_id_label, str(provider.get("account_id", "")), secret=True
        )
        mode = _prompt(
            "resource mode (api/feed/file)",
            str(resource.get("mode", provider.get("mode", "api"))),
        )
        resource["mode"] = mode
        if mode == "file":
            resource["path"] = _prompt(
                "official export file path", str(resource.get("path", ""))
            )
        else:
            resource["endpoint"] = _prompt(
                "provider-issued API/feed HTTPS endpoint",
                str(resource.get("endpoint", "")),
                secret=True,
            )
        resource["format"] = _prompt(
            "format (auto/json/csv/tsv/xml)", str(resource.get("format", "auto"))
        )
        auth = provider.setdefault("auth", {"type": "none"})
        auth_type = _prompt(
            "auth type (none/bearer/api_key_header/api_key_query/basic/oauth2_client_credentials/custom_headers)",
            str(auth.get("type", "none")),
        )
        auth["type"] = auth_type
        if auth_type == "bearer":
            auth["token"] = _prompt("access token (or env:NAME)", secret=True)
        elif auth_type in {"api_key_header", "api_key_query"}:
            auth["api_key"] = _prompt("API key (or env:NAME)", secret=True)
            if auth_type == "api_key_header":
                auth["header"] = _prompt(
                    "API-key header", str(auth.get("header", "X-API-Key"))
                )
            else:
                auth["parameter"] = _prompt(
                    "API-key query parameter", str(auth.get("parameter", "api_key"))
                )
        elif auth_type == "basic":
            auth["username"] = _prompt(
                "username", str(auth.get("username", "")), secret=True
            )
            auth["password"] = _prompt("password (or env:NAME)", secret=True)
        elif auth_type == "oauth2_client_credentials":
            auth["token_url"] = _prompt(
                "OAuth token HTTPS endpoint",
                str(auth.get("token_url", "")),
                secret=True,
            )
            auth["client_id"] = _prompt(
                "OAuth client_id", str(auth.get("client_id", "")), secret=True
            )
            auth["client_secret"] = _prompt(
                "OAuth client_secret (or env:NAME)", secret=True
            )
            auth["scope"] = _prompt(
                "OAuth scope (optional)", str(auth.get("scope", ""))
            )
        provider["enabled"] = _bool_prompt("Enable provider", False)
        resource["enabled"] = _bool_prompt(f"Enable resource {resource_name}", False)
    validate_config(config)
    target = atomic_write_config(args.config, config, overwrite=True)
    print(f"Saved owner-only configuration: {target}")
    print("Run `doctor` before the first fetch.")
    return 0


def _doctor(config: Mapping[str, Any], provider_keys: Iterable[str], show: bool) -> int:
    failed = False
    for key in provider_keys:
        errors = provider_diagnostics(config, key)
        provider = config["providers"][key]
        for resource_name, resource in provider.get("resources", {}).items():
            if not isinstance(resource, Mapping) or not resource.get("enabled"):
                continue
            mode = str(resource.get("mode", provider.get("mode", "api")))
            if mode in {"api", "feed"} and resource.get("endpoint"):
                try:
                    # Syntax-only: doctor must never contact a provider or DNS.
                    EndpointValidator.validate_syntax(str(resource["endpoint"]))
                except FetchError as exc:
                    errors.append(f"resources.{resource_name}: {exc}")
        status = "READY" if not errors else "NOT READY"
        print(f"{key}: {status}")
        for error in errors:
            print(f"  - {error}")
        failed = failed or bool(errors)
        if show:
            print(
                json.dumps(
                    redact(provider), ensure_ascii=False, indent=2, sort_keys=True
                )
            )
    return 1 if failed else 0


def _resources_for(
    config: Mapping[str, Any], provider_key: str, requested: str
) -> list[str]:
    resources = config["providers"][provider_key].get("resources", {})
    if requested != "all":
        if requested not in resources:
            raise ConfigError(f"Unknown resource {provider_key}/{requested}")
        if not resources[requested].get("enabled"):
            raise ConfigError(f"{provider_key}/{requested} is disabled")
        return [requested]
    return [
        name
        for name, resource in resources.items()
        if isinstance(resource, Mapping) and resource.get("enabled")
    ]


def _fetch_one(
    config: Mapping[str, Any], provider_key: str, resource_name: str, dry_run: bool
) -> None:
    resource = config["providers"][provider_key]["resources"][resource_name]
    provider = config["providers"][provider_key]
    if resource.get("mode", provider.get("mode", "api")) == "file":
        if not Path(resource["path"]).expanduser().is_file():
            raise ConfigError("Configured provider export file does not exist")
    if dry_run:
        print(f"DRY RUN ready: {provider_key}/{resource_name}")
        return
    batch = fetch_resource(config, provider_key, resource_name)
    manifest = persist_batch(batch, config["storage"])
    print(
        json.dumps(
            {
                "provider": provider_key,
                "resource": resource_name,
                "record_count": manifest["record_count"],
                "page_count": manifest["page_count"],
                "manifest_path": manifest["manifest_path"],
                "warnings": manifest["warnings"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init-config":
            target = atomic_write_config(
                args.config, initial_config(), overwrite=bool(args.force)
            )
            print(f"Created owner-only template: {target}")
            return 0
        if args.command == "list-providers":
            for manifest in PROVIDERS.values():
                print(f"{manifest.key}\t{manifest.display_name}")
            return 0
        if args.command == "register":
            return _register(args)
        config = load_config(args.config)
        if args.command == "doctor":
            keys = (
                list(PROVIDERS)
                if args.provider == "all"
                else [get_provider(args.provider).key]
            )
            return _doctor(config, keys, bool(args.show_redacted))
        if args.command == "fetch":
            key = get_provider(args.provider).key
            errors = provider_diagnostics(config, key)
            if errors:
                raise ConfigError(f"{key} is not ready: {'; '.join(errors)}")
            for resource in _resources_for(config, key, args.resource):
                _fetch_one(config, key, resource, bool(args.dry_run))
            return 0
        if args.command == "fetch-all":
            failures: list[str] = []
            for key, provider in config["providers"].items():
                if key not in PROVIDERS or not provider.get("enabled"):
                    continue
                errors = provider_diagnostics(config, key)
                if errors:
                    failures.append(f"{key}: {'; '.join(errors)}")
                    continue
                for resource in _resources_for(config, key, "all"):
                    try:
                        _fetch_one(config, key, resource, bool(args.dry_run))
                    except (ConfigError, FetchError) as exc:
                        failures.append(f"{key}/{resource}: {exc}")
                    except OSError:
                        failures.append(f"{key}/{resource}: local I/O failed")
            if failures:
                for failure in failures:
                    print(f"ERROR: {failure}", file=sys.stderr)
                return 1
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except (ConfigError, FetchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyError, OSError, ValueError, TypeError:
        print("ERROR: Invalid configuration or local I/O failure", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
