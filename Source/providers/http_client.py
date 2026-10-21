import json
import logging
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.exceptions import ProviderError


class JsonHttpClient:
    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds

    def get_json(self, url: str, headers: dict[str, str], params: dict[str, str] | None = None) -> dict:
        request_url = self._url_mit_parametern(url, params or {})
        request = Request(request_url, headers=headers, method="GET")
        return self._json_request(request, self._sichere_url(url))

    def post_json(self, url: str, headers: dict[str, str], body: dict) -> dict:
        daten = json.dumps(body).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **headers}
        request = Request(url, data=daten, headers=request_headers, method="POST")
        return self._json_request(request, self._sichere_url(url))

    def _json_request(self, request: Request, sichere_url: str) -> dict:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise ProviderError(
                        f"HTTP-Status {status} fuer {sichere_url}",
                        "Die Jobquelle ist gerade nicht erreichbar.",
                    )

                inhalt = response.read().decode("utf-8")
        except HTTPError as fehler:
            logging.exception("HTTP-Fehler beim Abruf von %s", sichere_url)
            retry_after = self._retry_after_seconds(getattr(fehler, "headers", None))
            if fehler.code == 429:
                benutzer_meldung = "Die Jobquelle hat ihr Anfragelimit erreicht und wird kurz pausiert."
            elif fehler.code == 403:
                benutzer_meldung = "Die Jobquelle lehnt Anfragen momentan ab und wird fuer diesen Suchlauf pausiert."
            else:
                benutzer_meldung = "Die Jobquelle hat die Anfrage abgelehnt oder ist voruebergehend nicht erreichbar."
            raise ProviderError(
                f"HTTP-Fehler {fehler.code} fuer {sichere_url}",
                benutzer_meldung,
                status_code=fehler.code,
                retry_after_seconds=retry_after,
            ) from fehler
        except (URLError, SocketTimeout, TimeoutError) as fehler:
            logging.exception("Netzwerkfehler beim Abruf von %s", sichere_url)
            raise ProviderError(
                f"Netzwerkfehler fuer {sichere_url}: {fehler}",
                "Keine Verbindung zur Jobquelle. Bitte Internetverbindung pruefen und spaeter erneut suchen.",
            ) from fehler

        try:
            daten = json.loads(inhalt)
        except json.JSONDecodeError as fehler:
            logging.exception("Ungueltige JSON-Antwort von %s", sichere_url)
            raise ProviderError(
                f"Ungueltige JSON-Antwort von {sichere_url}",
                "Die Jobquelle hat eine ungueltige Antwort geliefert.",
            ) from fehler

        if not isinstance(daten, dict):
            raise ProviderError(
                f"Unerwarteter Antworttyp von {sichere_url}: {type(daten).__name__}",
                "Die Jobquelle hat ein unerwartetes Antwortformat geliefert.",
            )

        return daten

    def _url_mit_parametern(self, url: str, params: dict[str, str]) -> str:
        if not params:
            return url

        return f"{url}?{urlencode(params)}"

    def _sichere_url(self, url: str) -> str:
        if "/api/" in url:
            return f"{url.split('/api/', 1)[0]}/api/<hidden>"
        return url

    def _retry_after_seconds(self, headers) -> float | None:
        if headers is None:
            return None
        try:
            wert = headers.get("Retry-After")
            if wert is None:
                return None
            return max(0.0, float(wert))
        except (AttributeError, TypeError, ValueError):
            return None
