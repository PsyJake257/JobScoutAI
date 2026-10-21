import logging
import threading
import time
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from config import (
    ETHICAL_REQUEST_DELAY_SECONDS,
    ETHICAL_SCRAPING_USER_AGENT,
    ETHICAL_SCRAPING_USER_AGENT_TOKEN,
    HTTP_TIMEOUT_SECONDS,
)
from providers.exceptions import ProviderError


class RobotsDeniedError(Exception):
    """Signalisiert, dass eine Seite laut robots.txt nicht abgerufen werden darf."""


@dataclass(frozen=True)
class _RobotsPolicy:
    erlaubt: bool
    crawl_delay: float


class EthicalHttpClient:
    """Leichtgewichtiger HTML-Client mit robots.txt und Host-Rate-Limit."""

    def __init__(
        self,
        timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
        request_delay_seconds: float = ETHICAL_REQUEST_DELAY_SECONDS,
        user_agent: str = ETHICAL_SCRAPING_USER_AGENT,
        user_agent_token: str = ETHICAL_SCRAPING_USER_AGENT_TOKEN,
    ):
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = max(0.0, float(request_delay_seconds))
        self.user_agent = user_agent
        self.user_agent_token = user_agent_token
        self._robots_cache: dict[str, _RobotsPolicy | RobotFileParser] = {}
        self._letzter_abruf: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_public_html(self, url: str) -> str:
        """Laedt eine oeffentliche HTML-Seite nur, wenn robots.txt dies erlaubt."""
        origin = self._origin(url)
        if not origin:
            raise ProviderError(
                f"Ungueltige Karriereseiten-URL: {url}",
                "Eine konfigurierte Karriereseite hat keine gueltige HTTP-Adresse.",
            )

        policy = self._robots_policy(origin)
        if isinstance(policy, _RobotsPolicy):
            if not policy.erlaubt:
                raise RobotsDeniedError(f"robots.txt konnte fuer {origin} nicht sicher ausgewertet werden.")
            crawl_delay = policy.crawl_delay
        else:
            if not policy.can_fetch(self.user_agent_token, url):
                raise RobotsDeniedError(f"robots.txt untersagt den Abruf von {url}.")
            crawl_delay = self._crawl_delay(policy)

        self._warte(origin, max(self.request_delay_seconds, crawl_delay))
        status, inhalt, content_type = self._fetch(url)
        if status < 200 or status >= 300:
            raise ProviderError(
                f"HTTP-Status {status} fuer {origin}",
                "Eine Karriereseite ist voruebergehend nicht erreichbar.",
            )
        if content_type and "html" not in content_type.lower() and "text/" not in content_type.lower():
            logging.info("Karriereseite ohne HTML-Inhalt uebersprungen: %s", origin)
            return ""
        return inhalt

    def _robots_policy(self, origin: str) -> _RobotsPolicy | RobotFileParser:
        with self._lock:
            cached = self._robots_cache.get(origin)
        if cached is not None:
            return cached

        robots_url = f"{origin}/robots.txt"
        self._warte(origin, self.request_delay_seconds)
        try:
            status, inhalt, _content_type = self._fetch(robots_url, http_fehler_zurueckgeben=True)
        except ProviderError:
            logging.warning("robots.txt nicht erreichbar; Host wird sicherheitshalber uebersprungen: %s", origin)
            policy: _RobotsPolicy | RobotFileParser = _RobotsPolicy(False, 0.0)
        else:
            if status in (401, 403):
                logging.info("robots.txt verweigert Zugriff; Host wird uebersprungen: %s", origin)
                policy = _RobotsPolicy(False, 0.0)
            elif status in (404, 410):
                policy = _RobotsPolicy(True, 0.0)
            elif 200 <= status < 300:
                parser = RobotFileParser(robots_url)
                parser.parse(inhalt.splitlines())
                policy = parser
            else:
                logging.warning(
                    "robots.txt lieferte HTTP %s; Host wird sicherheitshalber uebersprungen: %s",
                    status,
                    origin,
                )
                policy = _RobotsPolicy(False, 0.0)

        with self._lock:
            self._robots_cache[origin] = policy
        return policy

    def _fetch(self, url: str, http_fehler_zurueckgeben: bool = False) -> tuple[int, str, str]:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 200))
                content_type = str(response.headers.get("Content-Type", ""))
                charset = response.headers.get_content_charset() or "utf-8"
                inhalt = response.read().decode(charset, errors="replace")
                return status, inhalt, content_type
        except HTTPError as fehler:
            if http_fehler_zurueckgeben:
                return int(fehler.code), "", str(fehler.headers.get("Content-Type", ""))
            logging.warning("HTTP-Fehler beim Karriereseiten-Abruf: %s (%s)", self._sichere_url(url), fehler.code)
            raise ProviderError(
                f"HTTP-Fehler {fehler.code} fuer {self._sichere_url(url)}",
                "Eine Karriereseite hat den Abruf abgelehnt.",
            ) from fehler
        except (URLError, SocketTimeout, TimeoutError) as fehler:
            logging.warning("Netzwerkfehler beim Karriereseiten-Abruf: %s", self._sichere_url(url))
            raise ProviderError(
                f"Netzwerkfehler fuer {self._sichere_url(url)}: {fehler}",
                "Eine Karriereseite ist nicht erreichbar.",
            ) from fehler

    def _warte(self, origin: str, delay: float) -> None:
        with self._lock:
            jetzt = time.monotonic()
            letzter_abruf = self._letzter_abruf.get(origin, 0.0)
            wartezeit = max(0.0, letzter_abruf + delay - jetzt)
            if wartezeit:
                time.sleep(wartezeit)
            self._letzter_abruf[origin] = time.monotonic()

    def _crawl_delay(self, parser: RobotFileParser) -> float:
        wert = parser.crawl_delay(self.user_agent_token)
        if wert is None:
            wert = parser.crawl_delay("*")
        try:
            return max(0.0, float(wert or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _origin(self, url: str) -> str:
        try:
            teile = urlsplit(str(url or "").strip())
        except ValueError:
            return ""
        if teile.scheme not in ("http", "https") or not teile.netloc:
            return ""
        return urlunsplit((teile.scheme.lower(), teile.netloc.lower(), "", "", "")).rstrip("/")

    def _sichere_url(self, url: str) -> str:
        origin = self._origin(url)
        return origin or "<ungueltige-url>"
