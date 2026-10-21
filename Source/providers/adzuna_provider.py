import logging
from html.parser import HTMLParser
from html import unescape
from pathlib import Path

from config import ETHICAL_SCRAPING_USER_AGENT, HTTP_TIMEOUT_SECONDS, MAX_PROVIDER_PAGES, MAX_SEARCH_RESULTS
from models import Job, SearchRequest
from paths import BASIS_ORDNER
from providers.base_provider import JobProvider
from providers.env_loader import lade_env_wert
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"br", "p", "div", "li", "ul", "ol", "section", "article", "h1", "h2", "h3"}

    def __init__(self):
        super().__init__()
        self.teile = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.BLOCK_TAGS:
            self.teile.append(" ")

    def handle_data(self, data):
        text = unescape(str(data)).strip()
        if text:
            self.teile.append(text)

    def text(self) -> str:
        return " ".join(" ".join(self.teile).split())


class AdzunaProvider(JobProvider):
    name = "adzuna"
    anzeigename = "Adzuna"
    aktiv = True

    API_URL = "https://api.adzuna.com/v1/api/jobs/de/search/{page}"
    ENV_APP_ID = "ADZUNA_APP_ID"
    ENV_API_KEY = "ADZUNA_API_KEY"

    def __init__(self, http_client: JsonHttpClient | None = None, env_datei: Path | None = None):
        self.http_client = http_client or JsonHttpClient(HTTP_TIMEOUT_SECONDS)
        self.env_datei = env_datei or (BASIS_ORDNER / ".env")

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        app_id, api_key = self._zugangsdaten()
        anfrage = suchanfrage.bereinigt()
        jobs = []
        for seite in range(1, MAX_PROVIDER_PAGES + 1):
            daten = self.http_client.get_json(
                self.API_URL.format(page=seite),
                headers={"Accept": "application/json", "User-Agent": ETHICAL_SCRAPING_USER_AGENT},
                params=self._suchparameter(anfrage, app_id, api_key),
            )

            ergebnisse = daten.get("results", [])
            if ergebnisse is None:
                ergebnisse = []
            if not isinstance(ergebnisse, list):
                raise ProviderError(
                    "Adzuna-Antwort enthaelt keine gueltige Jobliste.",
                    "Adzuna hat ein unerwartetes Antwortformat geliefert.",
                )

            jobs.extend(self._jobs_aus_ergebnissen(ergebnisse))
            if len(ergebnisse) < MAX_SEARCH_RESULTS:
                break

        if not jobs:
            logging.info("Adzuna-Suche ohne Ergebnisse")
        return jobs

    def _jobs_aus_ergebnissen(self, ergebnisse: list) -> list[Job]:
        jobs = []
        for index, eintrag in enumerate(ergebnisse):
            if not isinstance(eintrag, dict):
                logging.warning("Adzuna-Datensatz uebersprungen: Index %s ist %s", index, type(eintrag).__name__)
                continue
            try:
                job = self._job_aus_eintrag(eintrag)
            except Exception:
                logging.exception("Adzuna-Datensatz konnte nicht gemappt werden: Index %s", index)
                continue
            if job.titel or job.firma:
                jobs.append(job)
            else:
                logging.warning("Adzuna-Datensatz ohne Titel und Firma uebersprungen: Index %s", index)
        return jobs

    def deaktivierungsgrund(self) -> str:
        if not self.env_datei.exists():
            return "Adzuna deaktiviert: .env wurde nicht gefunden."
        app_id = lade_env_wert(self.env_datei, self.ENV_APP_ID)
        api_key = lade_env_wert(self.env_datei, self.ENV_API_KEY)
        if not app_id and not api_key:
            return "Adzuna deaktiviert: ADZUNA_APP_ID und ADZUNA_API_KEY fehlen in .env."
        if not app_id:
            return "Adzuna deaktiviert: ADZUNA_APP_ID fehlt in .env."
        if not api_key:
            return "Adzuna deaktiviert: ADZUNA_API_KEY fehlt in .env."
        return ""

    def _zugangsdaten(self) -> tuple[str, str]:
        app_id = lade_env_wert(self.env_datei, self.ENV_APP_ID)
        api_key = lade_env_wert(self.env_datei, self.ENV_API_KEY)
        if not app_id or not api_key:
            raise ProviderError(
                "Adzuna-Zugangsdaten fehlen in .env.",
                "Adzuna ist nicht konfiguriert. Bitte ADZUNA_APP_ID und ADZUNA_API_KEY in der .env pruefen.",
            )
        return app_id, api_key

    def _suchparameter(self, suchanfrage: SearchRequest, app_id: str, api_key: str) -> dict[str, str]:
        parameter = {
            "app_id": app_id,
            "app_key": api_key,
            "results_per_page": str(MAX_SEARCH_RESULTS),
            "content-type": "application/json",
        }
        if suchanfrage.suchbegriff:
            parameter["what"] = suchanfrage.suchbegriff
        if suchanfrage.ort:
            parameter["where"] = suchanfrage.ort
        if suchanfrage.umkreis:
            parameter["distance"] = suchanfrage.umkreis
        return parameter

    def _job_aus_eintrag(self, eintrag: dict) -> Job:
        return Job(
            titel=self._text(eintrag, "title"),
            firma=self._firma(eintrag),
            ort=self._ort(eintrag),
            quelle=self.anzeigename,
            link=self._url(eintrag),
            entfernung="",
            kurzbeschreibung=self._html_zu_text(self._text(eintrag, "description")),
            veroeffentlichungsdatum=self._datum(eintrag),
            gehalt_min=self._zahl_als_text(eintrag.get("salary_min")),
            gehalt_max=self._zahl_als_text(eintrag.get("salary_max")),
            kategorie=self._kategorie(eintrag),
        )

    def _firma(self, eintrag: dict) -> str:
        unternehmen = eintrag.get("company")
        if isinstance(unternehmen, dict):
            return self._text(unternehmen, "display_name", "name")
        return self._wert_zu_text(unternehmen)

    def _ort(self, eintrag: dict) -> str:
        standort = eintrag.get("location")
        if isinstance(standort, dict):
            area = standort.get("area")
            if isinstance(area, list):
                teile = [self._wert_zu_text(wert) for wert in area if self._wert_zu_text(wert)]
                if teile:
                    return ", ".join(teile[-2:] if len(teile) > 1 else teile)
            return self._text(standort, "display_name")
        return self._wert_zu_text(standort)

    def _kategorie(self, eintrag: dict) -> str:
        kategorie = eintrag.get("category")
        if isinstance(kategorie, dict):
            return self._text(kategorie, "label", "tag")
        return self._wert_zu_text(kategorie)

    def _url(self, eintrag: dict) -> str:
        url = self._text(eintrag, "redirect_url", "adref", "url")
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return ""

    def _datum(self, eintrag: dict) -> str:
        datum = self._text(eintrag, "created")
        if len(datum) >= 10 and datum[4:5] == "-" and datum[7:8] == "-":
            return datum[:10]
        return datum

    def _text(self, daten: dict, *feldnamen: str) -> str:
        if not isinstance(daten, dict):
            return ""
        for feldname in feldnamen:
            text = self._wert_zu_text(daten.get(feldname))
            if text:
                return text
        return ""

    def _wert_zu_text(self, wert) -> str:
        if wert is None:
            return ""
        if isinstance(wert, str):
            return unescape(wert).strip()
        if isinstance(wert, (int, float)):
            return str(wert).strip()
        return ""

    def _zahl_als_text(self, wert) -> str:
        if isinstance(wert, int):
            return str(wert)
        if isinstance(wert, float):
            return str(int(wert)) if wert.is_integer() else str(wert)
        return self._wert_zu_text(wert)

    def _html_zu_text(self, html: str) -> str:
        if not html:
            return ""
        parser = _TextExtractor()
        parser.feed(str(html))
        return parser.text() or " ".join(unescape(str(html)).split())
