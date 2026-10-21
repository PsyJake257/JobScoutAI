import logging
import re
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

from config import (
    ARBEITNOW_MAX_PAGES,
    ARBEITNOW_RATE_LIMIT_SECONDS,
    ETHICAL_SCRAPING_USER_AGENT,
    HTTP_TIMEOUT_SECONDS,
)
from models import Job, SearchRequest
from providers.base_provider import JobProvider
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient


class _HtmlTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.teile: list[str] = []

    def handle_data(self, data):
        text = str(data or "").strip()
        if text:
            self.teile.append(text)

    def text(self) -> str:
        return " ".join(" ".join(self.teile).split())


class ArbeitnowProvider(JobProvider):
    """Kostenloser europaeischer Jobfeed von Arbeitnow."""

    name = "arbeitnow"
    anzeigename = "Arbeitnow"
    aktiv = True
    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, http_client: JsonHttpClient | None = None):
        self.http_client = http_client or JsonHttpClient(HTTP_TIMEOUT_SECONDS)

    def statusdetails(self, aktualisieren: bool = False) -> dict[str, object]:
        return {
            "provider_status": "Kostenlose oeffentliche API",
            "kontingent": "Kein numerisches Monatslimit dokumentiert",
        }

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        anfrage = suchanfrage.bereinigt()
        jobs: list[Job] = []
        naechste_seite = 1
        for seiten_index in range(ARBEITNOW_MAX_PAGES):
            if seiten_index:
                time.sleep(max(0.0, ARBEITNOW_RATE_LIMIT_SECONDS))
            daten = self.http_client.get_json(
                self.API_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": ETHICAL_SCRAPING_USER_AGENT,
                },
                params={"page": str(naechste_seite)},
            )
            eintraege = daten.get("data", [])
            if not isinstance(eintraege, list):
                raise ProviderError(
                    "Arbeitnow-Antwort enthaelt keine gueltige Ergebnisliste.",
                    "Arbeitnow hat ein unerwartetes Antwortformat geliefert.",
                )
            for index, eintrag in enumerate(eintraege):
                if not isinstance(eintrag, dict):
                    continue
                try:
                    job = self._job_aus_eintrag(eintrag)
                except Exception:
                    logging.exception("Arbeitnow-Datensatz konnte nicht gemappt werden: Index %s", index)
                    continue
                if job.titel and job.link and self._passt(job, eintrag, anfrage):
                    jobs.append(job)
            naechster_link = (daten.get("links") or {}).get("next")
            if not naechster_link:
                break
            naechste_seite += 1
        if not jobs:
            logging.info("Arbeitnow-Suche ohne passende Ergebnisse")
        return jobs

    def _job_aus_eintrag(self, eintrag: dict) -> Job:
        tags = self._textliste(eintrag.get("tags"))
        jobtypen = self._textliste(eintrag.get("job_types"))
        return Job(
            titel=self._text(eintrag.get("title")),
            firma=self._text(eintrag.get("company_name")),
            ort=self._text(eintrag.get("location")) or ("Remote" if eintrag.get("remote") else ""),
            quelle=self.anzeigename,
            link=self._text(eintrag.get("url")),
            kurzbeschreibung=self._html_zu_text(self._text(eintrag.get("description"))),
            veroeffentlichungsdatum=self._datum(eintrag.get("created_at")),
            kategorie=", ".join([*jobtypen, *tags]),
        )

    def _passt(self, job: Job, eintrag: dict, anfrage: SearchRequest) -> bool:
        such_tokens = self._tokens(anfrage.suchbegriff)
        titel = job.titel.lower()
        if such_tokens and not all(token in titel for token in such_tokens):
            return False

        ort_tokens = self._tokens(anfrage.ort)
        if not ort_tokens:
            return True
        ort_text = job.ort.lower()
        ist_remote = bool(eintrag.get("remote"))
        return ist_remote or all(token in ort_text for token in ort_tokens)

    def _html_zu_text(self, html: str) -> str:
        parser = _HtmlTextExtractor()
        try:
            parser.feed(unescape(html))
        except Exception:
            return " ".join(re.sub(r"<[^>]+>", " ", html).split())
        return parser.text()

    def _datum(self, wert) -> str:
        try:
            return datetime.fromtimestamp(int(wert), timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return ""

    def _tokens(self, wert: str) -> list[str]:
        return [
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", str(wert or ""))
            if len(token) >= 3
        ]

    def _textliste(self, wert) -> list[str]:
        if not isinstance(wert, list):
            return []
        return [self._text(eintrag) for eintrag in wert if self._text(eintrag)]

    def _text(self, wert) -> str:
        return str(wert or "").strip() if isinstance(wert, (str, int, float)) else ""
