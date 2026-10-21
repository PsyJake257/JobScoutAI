from models import Job, SearchRequest
from providers.base_provider import JobProvider


class DummyProvider(JobProvider):
    name = "dummy"
    anzeigename = "Demo"
    aktiv = False

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        anfrage = suchanfrage.bereinigt()
        suchbegriff = anfrage.suchbegriff or "Offene Stelle"
        ort = anfrage.ort or "Remote"
        umkreis = anfrage.umkreis or "30"

        return [
            Job(
                titel=suchbegriff,
                firma="Testfirma GmbH",
                ort=ort,
                quelle=self.anzeigename,
                link="https://example.com/job/testfirma",
                entfernung="",
                kurzbeschreibung="Demo-Stellenangebot fuer lokale Tests.",
            ),
            Job(
                titel=f"{suchbegriff} Assistenz",
                firma="Muster Personalservice",
                ort=f"{ort} + {umkreis} km",
                quelle=self.anzeigename,
                link="https://example.com/job/muster",
                entfernung=umkreis,
                kurzbeschreibung="Demo-Stellenangebot fuer lokale Tests.",
            ),
            Job(
                titel=f"Quereinstieg {suchbegriff}",
                firma="Regionale Chancen AG",
                ort=ort,
                quelle=self.anzeigename,
                link="https://example.com/job/chancen",
                entfernung="",
                kurzbeschreibung="Demo-Stellenangebot fuer lokale Tests.",
            ),
        ]
