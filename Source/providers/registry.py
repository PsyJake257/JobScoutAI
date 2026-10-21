from config import ACTIVE_PROVIDER_NAMES
from providers.adzuna_provider import AdzunaProvider
from providers.arbeitnow_provider import ArbeitnowProvider
from providers.arbeitsagentur_provider import ArbeitsagenturProvider
from providers.base_provider import JobProvider
from providers.career_pages_provider import CareerPagesProvider
from providers.dummy_provider import DummyProvider
from providers.indeed_provider import IndeedProvider
from providers.jooble_provider import JoobleProvider
from providers.linkedin_provider import LinkedInProvider
from providers.web_search_provider import WebSearchProvider


class ProviderRegistry:
    def __init__(self, provider: list[JobProvider], aktive_provider: list[str] | None = None):
        self.deaktivierte_meldungen = []

        if aktive_provider is not None:
            aktive_namen = set(aktive_provider)
            for eintrag in provider:
                eintrag.aktiv = eintrag.name in aktive_namen

        for eintrag in provider:
            if not eintrag.aktiv:
                continue

            grund = eintrag.deaktivierungsgrund()
            if grund:
                eintrag.aktiv = False
                self.deaktivierte_meldungen.append(grund)

        self._provider = {eintrag.name: eintrag for eintrag in provider}

    def alle(self) -> list[JobProvider]:
        return list(self._provider.values())

    def aktive(self) -> list[JobProvider]:
        return [provider for provider in self.alle() if provider.aktiv]

    def auswahl(self, namen: list[str]) -> list[JobProvider]:
        if not namen:
            return self.aktive()

        return [
            self._provider[name]
            for name in namen
            if name in self._provider and self._provider[name].aktiv
        ]

    def provider_status(self, aktualisieren: bool = False) -> list[dict[str, object]]:
        return [
            {
                "name": provider.name,
                "anzeigename": provider.anzeigename,
                "aktiv": provider.aktiv,
                "deaktivierungsgrund": provider.deaktivierungsgrund() if not provider.aktiv else "",
                "statusdetails": provider.statusdetails(aktualisieren),
            }
            for provider in self.alle()
        ]


def standard_provider_registry() -> ProviderRegistry:
    return ProviderRegistry([
        ArbeitsagenturProvider(),
        JoobleProvider(),
        AdzunaProvider(),
        WebSearchProvider(),
        CareerPagesProvider(),
        ArbeitnowProvider(),
        DummyProvider(),
        IndeedProvider(),
        LinkedInProvider(),
    ], ACTIVE_PROVIDER_NAMES)
