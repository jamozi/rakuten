"""Application composition for owner-authorized live GSC and GA4 imports."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import final

from raos.adapters.google_live import (
    FixedOwnerPrivateAnalyticsSiteBindings,
    GoogleServiceAccountAuthorizedTransport,
    LiveGa4AdminProvider,
    LiveGa4DataProvider,
    LiveSearchConsoleProvider,
    SystemGoogleImportClock,
    SystemGoogleRetrySleeper,
)
from raos.domain.analytics.google_live import (
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    Ga4LiveQuery,
    GoogleImportCommitResult,
    GoogleImportExecutionContext,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    SearchConsoleLiveQuery,
    fail_google,
)
from raos.ports.google_live import (
    AnalyticsImportRepository,
    AnalyticsSiteBindingPort,
    Ga4AdminProviderPort,
    Ga4DataProviderPort,
    GoogleImportClock,
    SearchConsoleProviderPort,
)


@final
class LiveGoogleAnalyticsImport:
    """Fetch a complete provider batch, then commit it through one atomic port."""

    __slots__ = (
        "_bindings",
        "_clock",
        "_ga4_admin",
        "_ga4_data",
        "_repository",
        "_search_console",
    )

    def __init__(
        self,
        *,
        bindings: AnalyticsSiteBindingPort,
        search_console: SearchConsoleProviderPort,
        ga4_data: Ga4DataProviderPort,
        ga4_admin: Ga4AdminProviderPort,
        repository: AnalyticsImportRepository,
        clock: GoogleImportClock,
    ) -> None:
        if (
            not isinstance(bindings, AnalyticsSiteBindingPort)
            or not isinstance(search_console, SearchConsoleProviderPort)
            or not isinstance(ga4_data, Ga4DataProviderPort)
            or not isinstance(ga4_admin, Ga4AdminProviderPort)
            or not isinstance(repository, AnalyticsImportRepository)
            or not isinstance(clock, GoogleImportClock)
        ):
            fail_google()
        self._bindings = bindings
        self._search_console = search_console
        self._ga4_data = ga4_data
        self._ga4_admin = ga4_admin
        self._repository = repository
        self._clock = clock

    def import_search_console(
        self,
        *,
        context: GoogleImportExecutionContext,
        date_from: date,
        date_to: date,
    ) -> GoogleImportCommitResult:
        binding = self._bindings.gsc()
        if context.site_id != binding.site_id:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        batch = self._search_console.query(
            SearchConsoleLiveQuery(
                site_id=binding.site_id,
                site_url=binding.resource,
                date_from=date_from,
                date_to=date_to,
            )
        )
        try:
            return self._repository.commit_gsc(context=context, batch=batch)
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.PERSISTENCE_FAILED)

    def import_ga4(
        self,
        *,
        context: GoogleImportExecutionContext,
        date_from: date,
        date_to: date,
        dimensions: tuple[str, ...] = GA4_BASELINE_DIMENSIONS,
        metrics: tuple[str, ...] = GA4_BASELINE_METRICS,
    ) -> GoogleImportCommitResult:
        binding = self._bindings.ga4()
        if context.site_id != binding.site_id:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        configuration = self._ga4_admin.get_property_configuration(
            property_id=binding.property_id,
            retrieved_at=self._clock.now(),
        )
        batch = self._ga4_data.run_report(
            Ga4LiveQuery(
                site_id=binding.site_id,
                property_id=binding.property_id,
                date_from=date_from,
                date_to=date_to,
                dimensions=dimensions,
                metrics=metrics,
            ),
            configuration=configuration,
        )
        try:
            return self._repository.commit_ga4(context=context, batch=batch)
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.PERSISTENCE_FAILED)


def compose_live_google_analytics_import(
    *,
    owner_private_root: Path,
    repository: AnalyticsImportRepository,
) -> LiveGoogleAnalyticsImport:
    """Construct the live seam; this is the only credential-opening composition."""

    bindings = FixedOwnerPrivateAnalyticsSiteBindings(owner_private_root)
    clock = SystemGoogleImportClock()
    sleeper = SystemGoogleRetrySleeper()
    gsc_transport = GoogleServiceAccountAuthorizedTransport(binding=bindings.gsc())
    ga4_transport = GoogleServiceAccountAuthorizedTransport(binding=bindings.ga4())
    return LiveGoogleAnalyticsImport(
        bindings=bindings,
        search_console=LiveSearchConsoleProvider(
            transport=gsc_transport, clock=clock, sleeper=sleeper
        ),
        ga4_data=LiveGa4DataProvider(
            transport=ga4_transport, clock=clock, sleeper=sleeper
        ),
        ga4_admin=LiveGa4AdminProvider(transport=ga4_transport, sleeper=sleeper),
        repository=repository,
        clock=clock,
    )


__all__ = ["LiveGoogleAnalyticsImport", "compose_live_google_analytics_import"]
