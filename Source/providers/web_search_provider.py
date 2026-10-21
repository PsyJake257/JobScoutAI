import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from config import (
    ETHICAL_SCRAPING_USER_AGENT,
    SERP_SEARCH_MAX_PAGES,
    SERP_SEARCH_RATE_LIMIT_SECONDS,
    SERP_SEARCH_TIMEOUT_SECONDS,
)
from models import Job, SearchRequest
from paths import BASIS_ORDNER
from providers.base_provider import JobProvider
from providers.env_loader import lade_env_wert
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient
from providers.serp_usage_tracker import SerpApiUsageTracker


class WebSearchBackend(ABC):
    """Austauschbare Schnittstelle fuer offizielle Websuch-APIs."""

    @abstractmethod
    def deaktivierungsgrund(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def suchen(self, suchanfrage: SearchRequest) -> list[dict]:
        raise NotImplementedError

    def statusdetails(self, aktualisieren: bool = False) -> dict[str, object]:
        return {}


class SerpApiWebSearchBackend(WebSearchBackend):
    API_URL = "https://serpapi.com/search.json"
    ACCOUNT_URL = "https://serpapi.com/account.json"
    ENV_KEY = "SERP_SEARCH_API_KEY"

    def __init__(
        self,
        http_client: JsonHttpClient | None = None,
        env_datei: Path | None = None,
        usage_tracker: SerpApiUsageTracker | None = None,
    ):
        self.http_client = http_client or JsonHttpClient(SERP_SEARCH_TIMEOUT_SECONDS)
        self.env_datei = env_datei or (BASIS_ORDNER / ".env")
        self.usage_tracker = usage_tracker or SerpApiUsageTracker()
        self._letzter_fehler = ""

    def deaktivierungsgrund(self) -> str:
        if not self.env_datei.exists():
            return "Websuche deaktiviert: .env wurde nicht gefunden."
        if not lade_env_wert(self.env_datei, self.ENV_KEY):
            return "Websuche deaktiviert: SERP_SEARCH_API_KEY fehlt in .env."
        if self.usage_tracker.status().get("limit_erreicht"):
            return "Websuche deaktiviert: Das monatliche SerpApi-Limit ist erreicht."
        return ""

    def statusdetails(self, aktualisieren: bool = False) -> dict[str, object]:
        api_key = lade_env_wert(self.env_datei, self.ENV_KEY)
        status = self.usage_tracker.status()
        statusfehler = ""
        if aktualisieren and api_key:
            try:
                status = self._konto_status_laden(api_key)
                self._letzter_fehler = ""
            except ProviderError as fehler:
                self._letzter_fehler = fehler.benutzer_meldung
                statusfehler = fehler.benutzer_meldung
        if status.get("limit_erreicht"):
            self._letzter_fehler = (
                "Websuche deaktiviert: Das monatliche SerpApi-Limit ist erreicht."
            )
        details = {
            **status,
            "konfiguriert": bool(api_key),
            "provider_status": self._letzter_fehler or str(status.get("kontostatus") or "Konfiguriert"),
        }
        if statusfehler:
            details["statusfehler"] = statusfehler
        return details

    def suchen(self, suchanfrage: SearchRequest) -> list[dict]:
        api_key = lade_env_wert(self.env_datei, self.ENV_KEY)
        if not api_key:
            raise ProviderError(
                "SERP_SEARCH_API_KEY fehlt in .env.",
                "Websuche ist nicht konfiguriert. Bitte SERP_SEARCH_API_KEY in der .env pruefen.",
            )

        try:
            status = self._konto_status_laden(api_key)
            self._letzter_fehler = ""
        except ProviderError as fehler:
            logging.warning("SerpApi-Kontostand vor der Suche nicht erreichbar: %s", fehler)
            status = self.usage_tracker.status()
        lokal_zaehlen = status.get("quelle") != "SerpApi"
        if bool(status.get("limit_erreicht")):
            self._letzter_fehler = (
                "Websuche deaktiviert: Das monatliche SerpApi-Limit ist erreicht."
            )
            raise ProviderError(
                "SerpApi-Monatslimit erreicht.",
                "Websuche uebersprungen: Das monatliche SerpApi-Limit ist erreicht. "
                "Die uebrigen Jobquellen werden weiter durchsucht.",
            )

        ergebnisse = []
        naechste_seite = ""
        for seite in range(SERP_SEARCH_MAX_PAGES):
            aktueller_status = self.usage_tracker.status()
            if bool(aktueller_status.get("limit_erreicht")):
                self._letzter_fehler = (
                    "Websuche deaktiviert: Das monatliche SerpApi-Limit ist erreicht."
                )
                break
            if seite:
                time.sleep(max(0.0, SERP_SEARCH_RATE_LIMIT_SECONDS))
            parameter = {
                "engine": "google_jobs",
                "q": self._suchausdruck(suchanfrage),
                "location": suchanfrage.ort,
                "google_domain": "google.de",
                "gl": "de",
                "hl": "de",
                "output": "json",
                "api_key": api_key,
            }
            radius = self._radius(suchanfrage.umkreis)
            if radius:
                parameter["lrad"] = radius
            if naechste_seite:
                parameter["next_page_token"] = naechste_seite
            try:
                daten = self.http_client.get_json(
                    self.API_URL,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": ETHICAL_SCRAPING_USER_AGENT,
                    },
                    params=parameter,
                )
            except ProviderError as fehler:
                self._letzter_fehler = (
                    "Websuche deaktiviert: SerpApi ist nicht erreichbar oder hat den API-Key abgelehnt."
                )
                raise ProviderError(
                    str(fehler),
                    "Websuche uebersprungen: SerpApi ist nicht erreichbar oder der API-Key ist ungueltig. "
                    "Die uebrigen Jobquellen werden weiter durchsucht.",
                ) from fehler

            if lokal_zaehlen:
                self.usage_tracker.verbrauch_erhoehen()
            api_fehler = str(daten.get("error") or "").strip()
            if api_fehler:
                if self._ist_leere_suche(api_fehler):
                    logging.info("SerpApi-Suche ohne Ergebnisse: %s", api_fehler)
                    self._letzter_fehler = ""
                    break
                self._letzter_fehler = f"Websuche deaktiviert: SerpApi meldet: {api_fehler}"
                raise ProviderError(
                    f"SerpApi-Fehler: {api_fehler}",
                    "Websuche uebersprungen: SerpApi hat die Anfrage abgelehnt. "
                    "Die uebrigen Jobquellen werden weiter durchsucht.",
                )
            status_name = str((daten.get("search_metadata") or {}).get("status") or "")
            if status_name and status_name.lower() != "success":
                raise ProviderError(
                    f"SerpApi-Suchstatus: {status_name}",
                    "Websuche hat keinen erfolgreichen Suchstatus geliefert.",
                )
            seiten_ergebnisse = daten.get("jobs_results", [])
            if not isinstance(seiten_ergebnisse, list):
                raise ProviderError(
                    "SerpApi-Antwort enthaelt keine gueltige Ergebnisliste.",
                    "Websuche hat ein unerwartetes Antwortformat geliefert.",
                )
            for eintrag in seiten_ergebnisse:
                if isinstance(eintrag, dict):
                    normalisiert = self._normalisieren(eintrag)
                    if normalisiert.get("title") and normalisiert.get("url"):
                        ergebnisse.append(normalisiert)
            seiten_info = daten.get("serpapi_pagination") or {}
            naechste_seite = (
                str(seiten_info.get("next_page_token") or "").strip()
                if isinstance(seiten_info, dict)
                else ""
            )
            if not naechste_seite:
                break
        self._letzter_fehler = ""
        if not lokal_zaehlen:
            try:
                self._konto_status_laden(api_key)
            except ProviderError:
                logging.warning("SerpApi-Kontingent konnte nach der Suche nicht erneut geladen werden.")
        return ergebnisse

    def _konto_status_laden(self, api_key: str) -> dict[str, object]:
        try:
            daten = self.http_client.get_json(
                self.ACCOUNT_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": ETHICAL_SCRAPING_USER_AGENT,
                },
                params={"api_key": api_key},
            )
        except ProviderError as fehler:
            raise ProviderError(
                str(fehler),
                "SerpApi-Kontostatus ist nicht erreichbar oder der API-Key ist ungueltig.",
            ) from fehler
        api_fehler = str(daten.get("error") or "").strip()
        if api_fehler:
            raise ProviderError(
                f"SerpApi-Kontofehler: {api_fehler}",
                "SerpApi hat den API-Key abgelehnt.",
            )
        return self.usage_tracker.status(daten)

    def _normalisieren(self, eintrag: dict) -> dict:
        detected = eintrag.get("detected_extensions") or {}
        if not isinstance(detected, dict):
            detected = {}
        return {
            "title": eintrag.get("title"),
            "url": self._stellenlink(eintrag),
            "description": eintrag.get("description"),
            "company": eintrag.get("company_name"),
            "location": eintrag.get("location"),
            "source": eintrag.get("via"),
            "date": detected.get("posted_at"),
            "job_id": eintrag.get("job_id"),
            "is_detail": True,
        }

    def _stellenlink(self, eintrag: dict) -> str:
        optionen = eintrag.get("apply_options") or []
        if isinstance(optionen, list):
            for option in optionen:
                if not isinstance(option, dict):
                    continue
                link = str(option.get("link") or "").strip()
                if link.startswith(("http://", "https://")):
                    return link
        link = str(eintrag.get("share_link") or "").strip()
        return link if link.startswith(("http://", "https://")) else ""

    def _suchausdruck(self, suchanfrage: SearchRequest) -> str:
        return suchanfrage.suchbegriff or suchanfrage.ort

    def _ist_leere_suche(self, meldung: str) -> bool:
        text = str(meldung or "").casefold()
        return "hasn't returned any results" in text or "keine ergebnisse" in text

    def _radius(self, wert: str) -> str:
        treffer = re.search(r"\d+", str(wert or ""))
        return treffer.group(0) if treffer else ""


class WebSearchProvider(JobProvider):
    name = "websuche"
    anzeigename = "Websuche"
    aktiv = True

    def __init__(self, backend: WebSearchBackend | None = None):
        self.backend = backend or SerpApiWebSearchBackend()

    def deaktivierungsgrund(self) -> str:
        return self.backend.deaktivierungsgrund()

    def statusdetails(self, aktualisieren: bool = False) -> dict[str, object]:
        return self.backend.statusdetails(aktualisieren)

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        eintraege = self.backend.suchen(suchanfrage.bereinigt())
        jobs = []
        for index, eintrag in enumerate(eintraege):
            if not self._ist_einzelstelle(eintrag):
                logging.info(
                    "Websuch-Sammelseite verworfen: %s",
                    self._text(eintrag.get("url")),
                )
                continue
            try:
                job = self._job_aus_eintrag(eintrag, suchanfrage)
            except Exception:
                logging.exception("Websuch-Datensatz konnte nicht gemappt werden: Index %s", index)
                continue
            if job.titel and job.link:
                jobs.append(job)
        if not jobs:
            logging.info("Websuche ohne Ergebnisse")
        return jobs

    def _job_aus_eintrag(self, eintrag: dict, suchanfrage: SearchRequest) -> Job:
        titel = self._text(eintrag.get("title"))
        link = self._text(eintrag.get("url"))
        return Job(
            titel=titel,
            firma=self._firma(eintrag, link),
            ort=self._text(eintrag.get("location")) or suchanfrage.ort,
            quelle=self.anzeigename,
            link=link if link.startswith(("http://", "https://")) else "",
            kurzbeschreibung=self._text(eintrag.get("description")),
            veroeffentlichungsdatum=self._datum(eintrag),
            kategorie="Webfundstelle",
        )

    def _firma(self, eintrag: dict, link: str) -> str:
        firma = self._text(eintrag.get("company"))
        if firma:
            return firma
        quelle = self._text(eintrag.get("source"))
        if quelle:
            return quelle
        try:
            host = urlsplit(link).netloc.lower()
        except ValueError:
            return ""
        return host[4:] if host.startswith("www.") else host

    def _datum(self, eintrag: dict) -> str:
        datum = self._text(eintrag.get("date"))
        return datum[:10] if len(datum) >= 10 and datum[4:5] == "-" and datum[7:8] == "-" else datum

    def _ist_einzelstelle(self, eintrag: dict) -> bool:
        titel = self._text(eintrag.get("title"))
        link = self._text(eintrag.get("url"))
        if not titel or not link.startswith(("http://", "https://")):
            return False
        if bool(eintrag.get("is_detail")):
            return True
        return not self._ist_sammelseite(titel, link)

    def _ist_sammelseite(self, titel: str, link: str) -> bool:
        titel_klein = titel.casefold()
        starke_titelmuster = (
            r"\bjetzt\s+[\d.,]+\s+offene\s+stellen\s+finden\b",
            r"\b[\d.,]+\s+offene\s+stellen\s+finden\b",
            r"\bjobs?\s+(?:in|bei)\s+.+\|\s+jetzt\b",
            r"\bstellenangebote?\s+(?:in|bei)\b",
            r"\bjobs?\s+finden\b",
        )
        if any(re.search(muster, titel_klein) for muster in starke_titelmuster):
            return True

        try:
            url = urlsplit(link)
        except ValueError:
            return True
        host = url.netloc.casefold()
        pfad = url.path.casefold().rstrip("/")
        parameter = parse_qs(url.query)

        if "google." in host and pfad == "/search":
            return not bool(parameter.get("htidocid"))
        if "indeed." in host and re.fullmatch(r"/q-.+-jobs\.html", pfad):
            return True
        if re.search(r"/(?:job-search|jobsuche|jobboerse|stellensuche|search|suche)(?:/|$)", pfad):
            return True
        if pfad in {
            "",
            "/jobs",
            "/job",
            "/karriere",
            "/careers",
            "/stellenangebote",
            "/stellenanzeigen",
            "/vacancies",
            "/open-positions",
        }:
            return True
        return bool(re.search(r"/(?:jobs?|stellenangebote?)-(?:in|bei)-", pfad))

    def _text(self, wert) -> str:
        return str(wert or "").strip() if isinstance(wert, (str, int, float)) else ""
