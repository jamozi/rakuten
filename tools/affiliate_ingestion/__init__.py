"""Provider-neutral affiliate-network ingestion for RAOS.

The package is intentionally standard-library-only and performs no network
request on import.  Live access is possible only after an owner supplies a
local, permission-restricted account configuration.
"""

from .providers import PROVIDERS, ProviderManifest, get_provider

__all__ = ["PROVIDERS", "ProviderManifest", "get_provider"]
__version__ = "1.0.0"
