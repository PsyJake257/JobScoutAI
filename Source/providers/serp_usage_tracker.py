import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from config import SERP_SEARCH_MONTHLY_LIMIT
from paths import SERP_NUTZUNG_DATEI


class SerpApiUsageTracker:
    """Persistiert ein monatliches Ersatzkontingent fuer SerpApi."""

    def __init__(
        self,
        datei: Path = SERP_NUTZUNG_DATEI,
        monatslimit: int = SERP_SEARCH_MONTHLY_LIMIT,
        now=None,
    ):
        self.datei = datei
        self.monatslimit = max(1, int(monatslimit))
        self._now = now or datetime.now
        self._lock = threading.Lock()

    def status(self, api_status: dict | None = None) -> dict[str, object]:
        with self._lock:
            daten = self._laden()
            if api_status:
                daten = self._api_status_uebernehmen(daten, api_status)
                self._speichern(daten)
            return self._oeffentlicher_status(daten)

    def verbrauch_erhoehen(self, anzahl: int = 1) -> dict[str, object]:
        with self._lock:
            daten = self._laden()
            daten["verbraucht"] = min(
                int(daten["limit"]),
                max(0, int(daten["verbraucht"])) + max(0, int(anzahl)),
            )
            daten["quelle"] = "lokal"
            self._speichern(daten)
            return self._oeffentlicher_status(daten)

    def _laden(self) -> dict[str, object]:
        monat = self._monat()
        standard = {
            "monat": monat,
            "limit": self.monatslimit,
            "verbraucht": 0,
            "quelle": "lokal",
            "kontostatus": "Konfiguriert",
            "tarif": "Free",
        }
        try:
            daten = json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return standard
        if not isinstance(daten, dict) or daten.get("monat") != monat:
            return standard
        return {**standard, **daten}

    def _api_status_uebernehmen(self, daten: dict, api_status: dict) -> dict:
        limit = self._zahl(api_status.get("searches_per_month"), self.monatslimit)
        verbleibend = self._zahl(
            api_status.get("plan_searches_left", api_status.get("total_searches_left")),
            -1,
        )
        verbraucht = self._zahl(api_status.get("this_month_usage"), -1)
        if verbraucht < 0 and verbleibend >= 0:
            verbraucht = max(0, limit - verbleibend)
        if verbleibend < 0 and verbraucht >= 0:
            verbleibend = max(0, limit - verbraucht)
        if verbraucht < 0 or verbleibend < 0:
            return daten
        return {
            "monat": self._monat(),
            "limit": limit,
            "verbraucht": min(limit, verbraucht),
            "quelle": "SerpApi",
            "kontostatus": str(api_status.get("account_status") or "Aktiv"),
            "tarif": str(api_status.get("plan_name") or ""),
            "erneuerung": str(api_status.get("plan_renewal_date") or ""),
        }

    def _oeffentlicher_status(self, daten: dict) -> dict[str, object]:
        limit = max(1, self._zahl(daten.get("limit"), self.monatslimit))
        verbraucht = min(limit, max(0, self._zahl(daten.get("verbraucht"), 0)))
        return {
            **daten,
            "limit": limit,
            "verbraucht": verbraucht,
            "verbleibend": max(0, limit - verbraucht),
            "limit_erreicht": verbraucht >= limit,
        }

    def _speichern(self, daten: dict) -> None:
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            temporaer = self.datei.with_suffix(".tmp")
            temporaer.write_text(
                json.dumps(daten, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporaer.replace(self.datei)
        except OSError:
            logging.exception("Lokaler SerpApi-Verbrauch konnte nicht gespeichert werden.")

    def _monat(self) -> str:
        return self._now().strftime("%Y-%m")

    def _zahl(self, wert, fallback: int) -> int:
        try:
            return int(wert)
        except (TypeError, ValueError):
            return fallback
