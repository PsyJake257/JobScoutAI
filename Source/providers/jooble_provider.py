import logging
from pathlib import Path

from config import ETHICAL_SCRAPING_USER_AGENT, HTTP_TIMEOUT_SECONDS, MAX_PROVIDER_PAGES, MAX_SEARCH_RESULTS
from models import Job, SearchRequest
from paths import BASIS_ORDNER
from providers.base_provider import JobProvider
from providers.env_loader import lade_env_wert
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient


class JoobleProvider(JobProvider):
    name = "jooble"
    anzeigename = "Jooble"
    aktiv = True

    API_URL = "https://de.jooble.org/api/{api_key}"
    ENV_KEY = "JOOBLE_API_KEY"
    JOOBLE_RADIUS_VALUES = [0, 4, 8, 16, 26, 40, 80]

    def __init__(self, http_client: JsonHttpClient | None = None, env_datei: Path | None = None):
        self.http_client = http_client or JsonHttpClient(HTTP_TIMEOUT_SECONDS)
        self.env_datei = env_datei or (BASIS_ORDNER / ".env")

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        api_key = self._api_key()
        anfrage = suchanfrage.bereinigt()
        jobs = []
        for seite in range(1, MAX_PROVIDER_PAGES + 1):
            daten = self.http_client.post_json(
                self.API_URL.format(api_key=api_key),
                headers={"Accept": "application/json", "User-Agent": ETHICAL_SCRAPING_USER_AGENT},
                body=self._request_body(anfrage, seite),
            )

            jobs_daten = daten.get("jobs", [])
            if jobs_daten is None:
                jobs_daten = []
            if not isinstance(jobs_daten, list):
                raise ProviderError(
                    "Jooble-Antwort enthaelt keine gueltige Jobliste.",
                    "Jooble hat ein unerwartetes Antwortformat geliefert.",
                )

            jobs.extend(self._jobs_aus_daten(jobs_daten))
            if len(jobs_daten) < MAX_SEARCH_RESULTS:
                break

        if not jobs:
            logging.info("Jooble-Suche ohne Ergebnisse")

        return jobs

    def _api_key(self) -> str:
        api_key = lade_env_wert(self.env_datei, self.ENV_KEY)
        if not api_key:
            raise ProviderError(
                "JOOBLE_API_KEY fehlt in .env.",
                "Jooble ist nicht konfiguriert. Bitte JOOBLE_API_KEY in der .env pruefen.",
            )
        return api_key

    def deaktivierungsgrund(self) -> str:
        if not self.env_datei.exists():
            return "Jooble deaktiviert: .env wurde nicht gefunden."
        if not lade_env_wert(self.env_datei, self.ENV_KEY):
            return "Jooble deaktiviert: JOOBLE_API_KEY fehlt in .env."
        return ""

    def _request_body(self, suchanfrage: SearchRequest, seite: int) -> dict:
        body = {
            "keywords": suchanfrage.suchbegriff,
            "location": suchanfrage.ort,
            "page": str(seite),
            "ResultOnPage": MAX_SEARCH_RESULTS,
            "companysearch": "false",
        }

        radius = self._jooble_radius(suchanfrage.umkreis)
        if radius:
            body["radius"] = str(radius)

        return body

    def _jobs_aus_daten(self, jobs_daten: list) -> list[Job]:
        jobs = []
        for index, eintrag in enumerate(jobs_daten):
            if not isinstance(eintrag, dict):
                logging.warning("Jooble-Datensatz uebersprungen: Index %s ist %s", index, type(eintrag).__name__)
                continue

            try:
                job = self._job_aus_eintrag(eintrag)
            except Exception:
                logging.exception("Jooble-Datensatz konnte nicht gemappt werden: Index %s", index)
                continue

            if job.titel or job.firma:
                jobs.append(job)
            else:
                logging.warning("Jooble-Datensatz ohne Titel und Firma uebersprungen: Index %s", index)
        return jobs

    def _jooble_radius(self, umkreis: str) -> int:
        try:
            wert = int(umkreis)
        except ValueError:
            return 0

        for erlaubt in self.JOOBLE_RADIUS_VALUES:
            if wert <= erlaubt:
                return erlaubt
        return self.JOOBLE_RADIUS_VALUES[-1]

    def _job_aus_eintrag(self, eintrag: dict) -> Job:
        return Job(
            titel=self._text(eintrag, "title"),
            firma=self._text(eintrag, "company"),
            ort=self._text(eintrag, "location"),
            quelle=self.anzeigename,
            link=self._url(eintrag),
            entfernung="",
            kurzbeschreibung=self._text(eintrag, "snippet"),
            veroeffentlichungsdatum=self._datum(eintrag),
        )

    def _url(self, eintrag: dict) -> str:
        link = self._text(eintrag, "link")
        if link.startswith("http://") or link.startswith("https://"):
            return link
        return ""

    def _datum(self, eintrag: dict) -> str:
        datum = self._text(eintrag, "updated")
        if len(datum) >= 10 and datum[4:5] == "-" and datum[7:8] == "-":
            return datum[:10]
        return datum

    def _text(self, daten: dict, feldname: str) -> str:
        wert = daten.get(feldname)
        if wert is None:
            return ""
        if isinstance(wert, (str, int, float)):
            return str(wert).strip()
        return ""
