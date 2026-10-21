import base64
import logging
from html.parser import HTMLParser
from urllib.parse import quote

from config import ETHICAL_SCRAPING_USER_AGENT, HTTP_TIMEOUT_SECONDS, MAX_PROVIDER_PAGES, MAX_SEARCH_RESULTS
from models import Job, SearchRequest
from providers.base_provider import JobProvider
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.teile = []

    def handle_data(self, data):
        text = str(data).strip()
        if text:
            self.teile.append(text)

    def text(self) -> str:
        return " ".join(self.teile)


class ArbeitsagenturProvider(JobProvider):
    name = "arbeitsagentur"
    anzeigename = "Bundesagentur fuer Arbeit"
    aktiv = True

    SUCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
    DETAIL_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{code}"
    JOBDETAIL_WEB_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

    HEADERS = {
        "User-Agent": ETHICAL_SCRAPING_USER_AGENT,
        "Accept": "application/json",
        "X-API-Key": "jobboerse-jobsuche",
    }

    def __init__(self, http_client: JsonHttpClient | None = None):
        self.http_client = http_client or JsonHttpClient(HTTP_TIMEOUT_SECONDS)

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        anfrage = suchanfrage.bereinigt()
        jobs = []
        for seite in range(1, MAX_PROVIDER_PAGES + 1):
            daten = self.http_client.get_json(
                self.SUCH_URL,
                headers=self.HEADERS,
                params=self._suchparameter(anfrage, seite),
            )

            stellenangebote = daten.get("ergebnisliste")
            if stellenangebote is None:
                stellenangebote = daten.get("stellenangebote", [])
            if stellenangebote is None:
                stellenangebote = []

            if not isinstance(stellenangebote, list):
                raise ProviderError(
                    "Arbeitsagentur-Antwort enthaelt keine gueltige Stellenliste.",
                    "Die Jobquelle hat ein unerwartetes Antwortformat geliefert.",
                )

            jobs.extend(self._jobs_aus_stellenangeboten(stellenangebote))
            if len(stellenangebote) < MAX_SEARCH_RESULTS:
                break

        if not jobs:
            logging.info("Arbeitsagentur-Suche ohne Ergebnisse")

        return jobs

    def _suchparameter(self, suchanfrage: SearchRequest, seite: int) -> dict[str, str]:
        params = {
            "angebotsart": "1",
            "page": str(seite),
            "pav": "false",
            "size": str(MAX_SEARCH_RESULTS),
        }

        if suchanfrage.suchbegriff:
            params["was"] = suchanfrage.suchbegriff
        if suchanfrage.ort:
            params["wo"] = suchanfrage.ort
        if suchanfrage.umkreis:
            params["umkreis"] = suchanfrage.umkreis

        return params

    def _jobs_aus_stellenangeboten(self, stellenangebote: list) -> list[Job]:
        jobs = []
        for index, eintrag in enumerate(stellenangebote):
            if not isinstance(eintrag, dict):
                logging.warning("Arbeitsagentur-Datensatz uebersprungen: Index %s ist %s", index, type(eintrag).__name__)
                continue

            try:
                job = self._job_aus_suchergebnis(eintrag)
            except Exception:
                logging.exception("Arbeitsagentur-Datensatz konnte nicht gemappt werden: Index %s", index)
                continue

            if job.titel or job.firma:
                jobs.append(job)
            else:
                logging.warning("Arbeitsagentur-Datensatz ohne Titel und Firma uebersprungen: Index %s", index)
        return jobs

    def _job_aus_suchergebnis(self, eintrag: dict) -> Job:
        refnr = self._text(eintrag, "refnr", "referenznummer", "hashId")
        details = self._details_laden(refnr) if refnr else {}

        titel = self._erstes_textfeld(
            details,
            eintrag,
            ["stellenangebotsTitel", "titel", "beruf", "berufsbezeichnung"],
        )
        firma = self._erstes_textfeld(
            details,
            eintrag,
            ["arbeitgeber", "firma", "unternehmen", "arbeitgeberName"],
        )
        ort = self._arbeitsort(details) or self._arbeitsort(eintrag)
        kurzbeschreibung = self._kurzbeschreibung(details, eintrag)
        url = self._url(eintrag, details, refnr)

        return Job(
            titel=titel,
            firma=firma,
            ort=ort,
            quelle=self.anzeigename,
            link=url,
            entfernung=self._entfernung(eintrag),
            kurzbeschreibung=kurzbeschreibung,
            veroeffentlichungsdatum=self._datum(details, eintrag),
        )

    def _details_laden(self, refnr: str) -> dict:
        code = base64.b64encode(refnr.encode("utf-8")).decode("ascii")

        try:
            daten = self.http_client.get_json(
                self.DETAIL_URL.format(code=quote(code, safe="")),
                headers=self.HEADERS,
            )
            return daten if isinstance(daten, dict) else {}
        except ProviderError:
            logging.exception("Arbeitsagentur-Details konnten nicht geladen werden: %s", refnr)
            return {}

    def _kurzbeschreibung(self, details: dict, eintrag: dict) -> str:
        beschreibung = self._erstes_textfeld(
            details,
            eintrag,
            ["stellenangebotsBeschreibung", "beschreibung", "stellenbeschreibung", "kurzbeschreibung"],
        )
        text = self._html_zu_text(beschreibung)
        return text

    def _url(self, eintrag: dict, details: dict, refnr: str) -> str:
        externe_url = self._erstes_textfeld(
            details,
            eintrag,
            ["externeUrl", "externe_url", "url", "link", "angebotsUrl"],
        )
        if externe_url.startswith("http://") or externe_url.startswith("https://"):
            return externe_url
        if refnr:
            return self.JOBDETAIL_WEB_URL.format(refnr=quote(refnr, safe=""))
        return ""

    def _arbeitsort(self, daten: dict) -> str:
        if not isinstance(daten, dict):
            return ""

        arbeitsort = (
            daten.get("arbeitsort")
            or daten.get("arbeitsorte")
            or daten.get("arbeitsorteListe")
            or daten.get("stellenlokationen")
        )
        if isinstance(arbeitsort, list):
            arbeitsort = next((ort for ort in arbeitsort if isinstance(ort, (dict, str))), None)

        if isinstance(arbeitsort, dict):
            adresse = arbeitsort.get("adresse")
            if isinstance(adresse, dict):
                arbeitsort = adresse
            teile = [
                self._text(arbeitsort, "plz", "postleitzahl"),
                self._text(arbeitsort, "ort", "ortName", "stadt"),
                self._text(arbeitsort, "region", "land", "bundesland"),
            ]
            return " ".join([teil for teil in teile if teil]).strip()

        if isinstance(arbeitsort, str):
            return arbeitsort.strip()

        return self._text(daten, "ort", "arbeitsort_ort", "arbeitsortOrt", "standort")

    def _entfernung(self, daten: dict) -> str:
        entfernung = self._text(daten, "entfernung", "distance", "distanz")
        if not entfernung:
            return ""
        if entfernung.lower().endswith("km"):
            return entfernung
        return f"{entfernung} km"

    def _datum(self, details: dict, eintrag: dict) -> str:
        datum = self._erstes_textfeld(
            details,
            eintrag,
            [
                "aktuelleVeroeffentlichungsdatum",
                "aktuelle_veroeffentlichungsdatum",
                "datumErsteVeroeffentlichung",
                "veroeffentlichtAm",
                "veroeffentlichungsdatum",
                "datum",
            ],
        )
        if len(datum) >= 10 and datum[4:5] == "-" and datum[7:8] == "-":
            return datum[:10]
        return datum

    def _erstes_textfeld(self, details: dict, eintrag: dict, feldnamen: list[str]) -> str:
        for daten in (details, eintrag):
            wert = self._text(daten, *feldnamen)
            if wert:
                return wert
        return ""

    def _text(self, daten, *feldnamen: str) -> str:
        if not isinstance(daten, dict):
            return ""

        for feldname in feldnamen:
            wert = daten.get(feldname)
            text = self._wert_zu_text(wert)
            if text:
                return text
        return ""

    def _wert_zu_text(self, wert) -> str:
        if wert is None:
            return ""
        if isinstance(wert, str):
            return wert.strip()
        if isinstance(wert, (int, float)):
            return str(wert).strip()
        if isinstance(wert, dict):
            for feldname in ("name", "bezeichnung", "arbeitgeber", "firma", "unternehmen", "ort"):
                text = self._wert_zu_text(wert.get(feldname))
                if text:
                    return text
            return ""
        if isinstance(wert, list):
            for eintrag in wert:
                text = self._wert_zu_text(eintrag)
                if text:
                    return text
            return ""
        return str(wert).strip()

    def _html_zu_text(self, html: str) -> str:
        if not html:
            return ""

        parser = _TextExtractor()
        parser.feed(str(html))
        return parser.text() or str(html).strip()
