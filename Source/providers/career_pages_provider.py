import json
import logging
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from config import CAREER_SITE_MAX_PAGES_PER_SITE
from models import Job, SearchRequest, job_schluessel
from paths import BASIS_ORDNER
from providers.base_provider import JobProvider
from providers.env_loader import lade_env_wert
from providers.ethical_http_client import EthicalHttpClient, RobotsDeniedError
from providers.exceptions import ProviderError


class _CareerPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.json_ld_texte: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title_teile: list[str] = []
        self.meta_description = ""
        self.canonical_url = ""
        self._in_json_ld = False
        self._json_teile: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attribute = {str(name).lower(): str(wert or "") for name, wert in attrs}
        tag = tag.lower()
        if tag == "script" and "ld+json" in attribute.get("type", "").lower():
            self._in_json_ld = True
            self._json_teile = []
        elif tag == "a" and attribute.get("href"):
            self.links.append((attribute["href"], attribute.get("title", "")))
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (attribute.get("name") or attribute.get("property") or "").lower()
            if name in ("description", "og:description") and not self.meta_description:
                self.meta_description = attribute.get("content", "")
        elif tag == "link" and "canonical" in attribute.get("rel", "").lower():
            self.canonical_url = attribute.get("href", "")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script" and self._in_json_ld:
            self.json_ld_texte.append("".join(self._json_teile).strip())
            self._in_json_ld = False
            self._json_teile = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_json_ld:
            self._json_teile.append(data)
        elif self._in_title:
            self.title_teile.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_teile).split())


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.teile: list[str] = []

    def handle_data(self, data):
        text = str(data or "").strip()
        if text:
            self.teile.append(text)

    def text(self) -> str:
        return " ".join(" ".join(self.teile).split())


class CareerPagesProvider(JobProvider):
    name = "karriereseiten"
    anzeigename = "Karriereseite"
    aktiv = True
    ENV_URLS = "CAREER_SITE_URLS"
    LINK_BEGRIFFE = ("job", "jobs", "career", "careers", "karriere", "stelle", "stellen", "vacan", "position")

    def __init__(
        self,
        http_client: EthicalHttpClient | None = None,
        env_datei: Path | None = None,
        start_urls: list[str] | None = None,
    ):
        self.http_client = http_client or EthicalHttpClient()
        self.env_datei = env_datei or (BASIS_ORDNER / ".env")
        self.start_urls = start_urls

    def deaktivierungsgrund(self) -> str:
        if not self._start_urls():
            return "Karriereseiten deaktiviert: CAREER_SITE_URLS fehlt oder enthaelt keine gueltige HTTP-Adresse."
        return ""

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        anfrage = suchanfrage.bereinigt()
        jobs: list[Job] = []
        bekannte_jobs = set()
        for start_url in self._start_urls():
            for job in self._seite_und_links_durchsuchen(start_url, anfrage):
                schluessel = job_schluessel(job)
                if schluessel not in bekannte_jobs:
                    jobs.append(job)
                    bekannte_jobs.add(schluessel)
        if not jobs:
            logging.info("Karriereseiten-Suche ohne Ergebnisse")
        return jobs

    def _seite_und_links_durchsuchen(self, start_url: str, anfrage: SearchRequest) -> list[Job]:
        origin = self._origin(start_url)
        queue = [start_url]
        besucht = set()
        jobs = []
        while queue and len(besucht) < CAREER_SITE_MAX_PAGES_PER_SITE:
            url = queue.pop(0)
            if url in besucht:
                continue
            besucht.add(url)
            try:
                html = self.http_client.get_public_html(url)
            except RobotsDeniedError as fehler:
                logging.info("Karriereseite wegen robots.txt uebersprungen: %s", fehler)
                continue
            except ProviderError as fehler:
                logging.warning("Karriereseite konnte nicht gelesen werden: %s", fehler)
                continue
            if not html:
                continue

            parser = _CareerPageParser()
            try:
                parser.feed(html)
            except Exception:
                logging.exception("Karriereseiten-HTML konnte nicht geparst werden: %s", origin)
                continue

            strukturierte_jobs = self._jobs_aus_json_ld(parser.json_ld_texte, url)
            passende_jobs = [job for job in strukturierte_jobs if self._passt(job, anfrage)]
            jobs.extend(passende_jobs)
            if not strukturierte_jobs:
                fallback = self._fallback_job(parser, url, anfrage)
                if fallback is not None:
                    jobs.append(fallback)

            for href, link_text in parser.links:
                kandidat = urljoin(url, href).split("#", 1)[0]
                if kandidat not in besucht and self._ist_relevanter_link(kandidat, link_text, origin):
                    queue.append(kandidat)
        return jobs

    def _jobs_aus_json_ld(self, json_texte: list[str], seiten_url: str) -> list[Job]:
        jobs = []
        for text in json_texte:
            if not text:
                continue
            try:
                daten = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                logging.debug("Ungueltiges JSON-LD auf Karriereseite uebersprungen: %s", self._origin(seiten_url))
                continue
            for eintrag in self._jobposting_eintraege(daten):
                job = self._job_aus_json_ld(eintrag, seiten_url)
                if job.titel:
                    jobs.append(job)
        return jobs

    def _jobposting_eintraege(self, daten) -> list[dict]:
        gefunden = []
        if isinstance(daten, list):
            for eintrag in daten:
                gefunden.extend(self._jobposting_eintraege(eintrag))
        elif isinstance(daten, dict):
            typ = daten.get("@type")
            typen = typ if isinstance(typ, list) else [typ]
            if any(str(eintrag).lower() == "jobposting" for eintrag in typen):
                gefunden.append(daten)
            for name in ("@graph", "itemListElement"):
                if name in daten:
                    gefunden.extend(self._jobposting_eintraege(daten[name]))
            if isinstance(daten.get("item"), (dict, list)):
                gefunden.extend(self._jobposting_eintraege(daten["item"]))
        return gefunden

    def _job_aus_json_ld(self, daten: dict, seiten_url: str) -> Job:
        link = self._text(daten.get("url")) or seiten_url
        firma = self._objekt_text(daten.get("hiringOrganization"), "name")
        ort = self._job_ort(daten.get("jobLocation"))
        gehalt_min, gehalt_max = self._gehalt(daten.get("baseSalary"))
        return Job(
            titel=self._text(daten.get("title")),
            firma=firma or self._firma_aus_url(link),
            ort=ort,
            quelle=self.anzeigename,
            link=urljoin(seiten_url, link),
            kurzbeschreibung=self._html_zu_text(self._text(daten.get("description"))),
            veroeffentlichungsdatum=self._datum(daten.get("datePosted")),
            gehalt_min=gehalt_min,
            gehalt_max=gehalt_max,
            kategorie=self._text(daten.get("employmentType")),
        )

    def _fallback_job(
        self,
        parser: _CareerPageParser,
        url: str,
        anfrage: SearchRequest,
    ) -> Job | None:
        if not self._ist_job_url(url) or not parser.title:
            return None
        titel, firma = self._fallback_titel_und_firma(parser.title, url)
        job = Job(
            titel=titel,
            firma=firma,
            ort=anfrage.ort,
            quelle=self.anzeigename,
            link=urljoin(url, parser.canonical_url) if parser.canonical_url else url,
            kurzbeschreibung=self._html_zu_text(parser.meta_description),
            kategorie="Karriereseite",
        )
        return job if self._passt(job, anfrage) else None

    def _fallback_titel_und_firma(self, seitentitel: str, url: str) -> tuple[str, str]:
        muster = re.match(r"^Job Application for (.+) at (.+)$", seitentitel, flags=re.IGNORECASE)
        if muster:
            return muster.group(1).strip(), muster.group(2).strip()
        return seitentitel, self._firma_aus_url(url)

    def _passt(self, job: Job, anfrage: SearchRequest) -> bool:
        tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", anfrage.suchbegriff)
            if len(token) >= 3
        ]
        if not tokens:
            return True
        haystack = " ".join((job.titel, job.kurzbeschreibung, job.kategorie)).lower()
        return any(token in haystack for token in tokens)

    def _ist_relevanter_link(self, url: str, link_text: str, origin: str) -> bool:
        if self._origin(url) != origin:
            return False
        text = f"{url} {link_text}".lower()
        return any(begriff in text for begriff in self.LINK_BEGRIFFE)

    def _ist_job_url(self, url: str) -> bool:
        pfad = urlsplit(url).path.lower()
        return any(begriff in pfad for begriff in self.LINK_BEGRIFFE)

    def _start_urls(self) -> list[str]:
        if self.start_urls is not None:
            rohwerte = self.start_urls
        else:
            rohwerte = lade_env_wert(self.env_datei, self.ENV_URLS).replace(",", ";").split(";")
        urls = []
        for wert in rohwerte:
            url = str(wert or "").strip()
            if self._origin(url) and url not in urls:
                urls.append(url)
        return urls

    def _job_ort(self, wert) -> str:
        eintraege = wert if isinstance(wert, list) else [wert]
        orte = []
        for eintrag in eintraege:
            if not isinstance(eintrag, dict):
                continue
            adresse = eintrag.get("address")
            if isinstance(adresse, dict):
                teile = [
                    self._text(adresse.get("postalCode")),
                    self._text(adresse.get("addressLocality")),
                    self._text(adresse.get("addressRegion")),
                ]
                ort = " ".join(teil for teil in teile if teil)
                if ort and ort not in orte:
                    orte.append(ort)
        return ", ".join(orte)

    def _gehalt(self, wert) -> tuple[str, str]:
        if not isinstance(wert, dict):
            return "", ""
        value = wert.get("value")
        if isinstance(value, dict):
            return self._text(value.get("minValue")), self._text(value.get("maxValue"))
        text = self._text(value)
        return text, text

    def _objekt_text(self, wert, feld: str) -> str:
        return self._text(wert.get(feld)) if isinstance(wert, dict) else ""

    def _datum(self, wert) -> str:
        text = self._text(wert)
        return text[:10] if len(text) >= 10 else text

    def _html_zu_text(self, html: str) -> str:
        parser = _TextExtractor()
        parser.feed(unescape(str(html or "")))
        return parser.text()

    def _firma_aus_url(self, url: str) -> str:
        host = urlsplit(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host

    def _origin(self, url: str) -> str:
        try:
            teile = urlsplit(str(url or "").strip())
        except ValueError:
            return ""
        if teile.scheme not in ("http", "https") or not teile.netloc:
            return ""
        return f"{teile.scheme.lower()}://{teile.netloc.lower()}"

    def _text(self, wert) -> str:
        return str(wert or "").strip() if isinstance(wert, (str, int, float)) else ""
