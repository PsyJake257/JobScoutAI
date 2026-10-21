import json
import logging
import os
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import (
    LOCAL_AI_ANALYSIS_CONTEXT_TOKENS,
    LOCAL_AI_ANALYSIS_KEEP_ALIVE,
    LOCAL_AI_ANALYSIS_MAX_JOBS,
    LOCAL_AI_ANALYSIS_MAX_OUTPUT_TOKENS,
    LOCAL_AI_ANALYSIS_MODEL,
    LOCAL_AI_ANALYSIS_TIMEOUT_SECONDS,
    LOCAL_AI_DEDUPLICATION_MAX_PAIRS,
)
from cancellation import OperationCancelled, abbruch_pruefen
from models import Job, SearchRequest, normalisiere_match_score, normalisiere_textliste


OLLAMA_URL = os.environ.get("JOBSCOUT_OLLAMA_URL", "http://localhost:11434")


class OllamaAnalysisClient:
    def __init__(
        self,
        model: str = LOCAL_AI_ANALYSIS_MODEL,
        base_url: str | None = None,
        timeout_seconds: int = LOCAL_AI_ANALYSIS_TIMEOUT_SECONDS,
        response_schema: dict | None = None,
    ):
        self.model = model
        self.base_url = (base_url or os.environ.get("JOBSCOUT_OLLAMA_URL", OLLAMA_URL)).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.response_schema = response_schema
        self.last_error_kind = ""
        self.last_error_message = ""
        self.last_metrics: dict[str, Any] = {}
        self._aktive_antwort = None
        self._antwort_lock = threading.Lock()

    def generate_json(self, prompt: str, abbruch_event=None) -> dict[str, Any] | None:
        abbruch_pruefen(abbruch_event)
        if abbruch_event is None:
            return self._generate_json_synchron(prompt, None)

        ergebnis: dict[str, object] = {}
        abgeschlossen = threading.Event()

        def anfrage_ausfuehren():
            try:
                ergebnis["wert"] = self._generate_json_synchron(prompt, abbruch_event)
            except Exception as fehler:
                ergebnis["fehler"] = fehler
            finally:
                abgeschlossen.set()

        threading.Thread(target=anfrage_ausfuehren, daemon=True).start()
        while not abgeschlossen.wait(0.1):
            if abbruch_event.is_set():
                self.abbrechen()
                raise OperationCancelled("Lokale KI-Anfrage wurde abgebrochen.")

        abbruch_pruefen(abbruch_event)
        if "fehler" in ergebnis:
            raise ergebnis["fehler"]
        return ergebnis.get("wert")

    def _generate_json_synchron(self, prompt: str, abbruch_event=None) -> dict[str, Any] | None:
        abbruch_pruefen(abbruch_event)
        self.last_error_kind = ""
        self.last_error_message = ""
        self.last_metrics = {}
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": self.response_schema or "json",
            "keep_alive": LOCAL_AI_ANALYSIS_KEEP_ALIVE,
            "options": {
                "temperature": 0.1,
                "num_ctx": LOCAL_AI_ANALYSIS_CONTEXT_TOKENS,
                "num_predict": LOCAL_AI_ANALYSIS_MAX_OUTPUT_TOKENS,
            },
        }
        request = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        gestartet = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                with self._antwort_lock:
                    self._aktive_antwort = response
                try:
                    inhalt = response.read().decode("utf-8")
                finally:
                    with self._antwort_lock:
                        if self._aktive_antwort is response:
                            self._aktive_antwort = None
                abbruch_pruefen(abbruch_event)
                daten = json.loads(inhalt)
        except OperationCancelled:
            raise
        except HTTPError as fehler:
            abbruch_pruefen(abbruch_event)
            self._fehler_setzen("http", f"HTTP {fehler.code}")
            logging.warning(
                "Ollama-Analyse fehlgeschlagen: HTTP %s nach %.1f Sekunden.",
                fehler.code,
                time.perf_counter() - gestartet,
            )
            return None
        except json.JSONDecodeError as fehler:
            abbruch_pruefen(abbruch_event)
            self._fehler_setzen("invalid_response", fehler.__class__.__name__)
            logging.warning(
                "Ollama-Analyse fehlgeschlagen: ungueltige API-Antwort nach %.1f Sekunden.",
                time.perf_counter() - gestartet,
            )
            return None
        except (URLError, TimeoutError, OSError, ValueError) as fehler:
            abbruch_pruefen(abbruch_event)
            fehlertext = str(fehler or "").lower()
            art = "timeout" if "timed out" in fehlertext or isinstance(fehler, TimeoutError) else "connection"
            self._fehler_setzen(art, fehler.__class__.__name__)
            logging.warning(
                "Ollama-Analyse fehlgeschlagen: %s nach %.1f Sekunden.",
                art,
                time.perf_counter() - gestartet,
            )
            return None

        self.last_metrics = {
            "elapsed_seconds": round(time.perf_counter() - gestartet, 2),
            "done_reason": str(daten.get("done_reason", "") or ""),
            "prompt_tokens": int(daten.get("prompt_eval_count", 0) or 0),
            "output_tokens": int(daten.get("eval_count", 0) or 0),
            "load_seconds": round(float(daten.get("load_duration", 0) or 0) / 1_000_000_000, 2),
        }
        ergebnis = _parse_json_object(str(daten.get("response", "")))
        if ergebnis is None:
            self._fehler_setzen("invalid_json", "Antwort war kein verwertbares JSON-Objekt.")
            logging.warning(
                "Ollama-Analyse lieferte kein verwertbares JSON: Modell=%s, Zeichen=%s, Grund=%s.",
                self.model,
                len(str(daten.get("response", "") or "")),
                self.last_metrics["done_reason"] or "unbekannt",
            )
            return None

        logging.info(
            "Ollama-Analyse abgeschlossen: Modell=%s, Dauer=%.1fs, Prompt=%s Token, Ausgabe=%s Token, Grund=%s.",
            self.model,
            self.last_metrics["elapsed_seconds"],
            self.last_metrics["prompt_tokens"],
            self.last_metrics["output_tokens"],
            self.last_metrics["done_reason"] or "unbekannt",
        )
        return ergebnis

    def abbrechen(self) -> None:
        with self._antwort_lock:
            response = self._aktive_antwort
        schliessen = getattr(response, "close", None)
        if callable(schliessen):
            try:
                schliessen()
            except Exception:
                logging.debug("Aktive Ollama-Antwort konnte beim Abbruch nicht geschlossen werden.", exc_info=True)

    def _fehler_setzen(self, art: str, meldung: str) -> None:
        self.last_error_kind = art
        self.last_error_message = str(meldung or "").strip()


class AiAnalysisStep:
    def __init__(
        self,
        client: OllamaAnalysisClient | None = None,
        enabled: bool = False,
        max_jobs: int = LOCAL_AI_ANALYSIS_MAX_JOBS,
    ):
        self.client = client
        self.enabled = enabled
        self.max_jobs = max(0, int(max_jobs or 0))
        self.letzte_zusammenfassung = ""
        self.letzte_meldung = "Lokale KI-Auswertung deaktiviert."
        self.letzter_status = "deaktiviert" if not enabled else "nicht_gestartet"
        self.echte_bewertungen = 0
        self.technische_bewertungen = 0

    def analysieren(self, jobs: list[Job], suchanfrage: SearchRequest, abbruch_event=None) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        self.letzte_zusammenfassung = ""
        self.echte_bewertungen = 0
        self.technische_bewertungen = 0
        if not self.enabled:
            self.letzter_status = "deaktiviert"
            self.letzte_meldung = "Lokale KI-Auswertung deaktiviert."
            return jobs
        if not jobs:
            self.letzter_status = "keine_daten"
            self.letzte_meldung = "Lokale KI-Auswertung: keine Jobs zu analysieren."
            return jobs

        client = self.client or OllamaAnalysisClient()
        self.client = client
        analyse_jobs = _analyse_kandidaten(jobs, suchanfrage, self.max_jobs)
        if not analyse_jobs:
            self.letzter_status = "keine_daten"
            self.letzte_meldung = "Lokale KI-Auswertung: keine Kandidaten zu analysieren."
            return jobs

        prompt = _analyse_prompt(analyse_jobs, suchanfrage, gesamt_treffer=len(jobs))
        logging.info(
            "Lokale KI-Analyse gestartet: Modell=%s, Treffer=%s, Kandidaten=%s, Prompt-Zeichen=%s.",
            client.model,
            len(jobs),
            len(analyse_jobs),
            len(prompt),
        )
        daten = (
            client.generate_json(prompt, abbruch_event=abbruch_event)
            if abbruch_event is not None
            else client.generate_json(prompt)
        )
        abbruch_pruefen(abbruch_event)
        if not daten:
            for index, job in enumerate(analyse_jobs):
                _fallback_bewertung_uebernehmen(job, _vorsortier_score(job, suchanfrage), index)
            self.technische_bewertungen = len(analyse_jobs)
            self.letzter_status = "technisch"
            self.letzte_zusammenfassung = _technische_fallback_zusammenfassung(
                getattr(client, "last_error_kind", "")
            )
            self.letzte_meldung = (
                f"Nur technische Vorbewertung: {len(jobs)} Treffer beruecksichtigt, "
                f"{len(analyse_jobs)} Kandidaten ohne echte Ollama-Bewertung vorbewertet."
            )
            return jobs

        self.letzte_zusammenfassung = str(daten.get("summary", "") or "").strip()
        bewertungen = daten.get("jobs", [])
        bewertete_indexe: set[int] = set()
        if isinstance(bewertungen, list):
            for eintrag in bewertungen:
                index = _bewertung_uebernehmen(analyse_jobs, eintrag)
                if index is not None:
                    bewertete_indexe.add(index)

        self.echte_bewertungen = len(bewertete_indexe)
        for index, job in enumerate(analyse_jobs):
            if index not in bewertete_indexe:
                _fallback_bewertung_uebernehmen(job, _vorsortier_score(job, suchanfrage), index)
                self.technische_bewertungen += 1

        if not self.echte_bewertungen:
            self.letzter_status = "technisch"
            if not self.letzte_zusammenfassung:
                self.letzte_zusammenfassung = (
                    "Die lokale KI hat keine verwertbaren Einzelbewertungen geliefert. "
                    "JobScout AI zeigt deshalb eine technische Vorbewertung der besten Kandidaten."
                )
        elif self.technische_bewertungen:
            self.letzter_status = "teilweise"
            hinweis = (
                f"Die lokale KI lieferte {self.echte_bewertungen} von {len(analyse_jobs)} "
                "Einzelbewertungen; fehlende Kandidaten sind klar als technische Vorbewertung markiert."
            )
            self.letzte_zusammenfassung = " ".join(
                teil for teil in (self.letzte_zusammenfassung, hinweis) if teil
            )
        else:
            self.letzter_status = "echt"
            if not self.letzte_zusammenfassung:
                self.letzte_zusammenfassung = (
                    f"Die lokale KI hat {self.echte_bewertungen} Top-Kandidaten bewertet."
                )

        self.letzte_meldung = (
            f"{'Echte lokale KI-Auswertung' if self.letzter_status == 'echt' else 'Teilweise lokale KI-Auswertung'}: "
            f"{len(jobs)} Treffer beruecksichtigt, {len(analyse_jobs)} Top-Kandidaten ausgewaehlt. "
            f"{self.echte_bewertungen} echte {client.model}-Bewertungen, "
            f"{self.technische_bewertungen} technische Vorbewertungen."
        )
        return jobs

    def dubletten_pruefen(self, paare: list[dict[str, object]], abbruch_event=None) -> list[tuple[int, int]]:
        abbruch_pruefen(abbruch_event)
        if not self.enabled or not paare:
            return []
        kandidaten = paare[:max(0, LOCAL_AI_DEDUPLICATION_MAX_PAIRS)]
        if not kandidaten:
            return []

        client = self.client or OllamaAnalysisClient()
        self.client = client
        prompt = _dubletten_prompt(kandidaten)
        logging.info(
            "Lokale KI-Dublettenpruefung gestartet: Modell=%s, Paare=%s.",
            getattr(client, "model", LOCAL_AI_ANALYSIS_MODEL),
            len(kandidaten),
        )
        daten = (
            client.generate_json(prompt, abbruch_event=abbruch_event)
            if abbruch_event is not None
            else client.generate_json(prompt)
        )
        abbruch_pruefen(abbruch_event)
        if not isinstance(daten, dict):
            logging.info("Lokale KI-Dublettenpruefung nicht verfuegbar; Grenzfaelle bleiben getrennt.")
            return []

        kandidaten_nach_id = {int(paar["paar_id"]): paar for paar in kandidaten}
        bestaetigt = []
        for entscheidung in daten.get("pairs", []):
            if not isinstance(entscheidung, dict) or entscheidung.get("same_job") is not True:
                continue
            try:
                paar_id = int(entscheidung.get("pair_id"))
                confidence = int(entscheidung.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            paar = kandidaten_nach_id.get(paar_id)
            if paar is None or confidence < 90 or int(paar.get("vorpruefung", 0)) < 72:
                continue
            bestaetigt.append((int(paar["index_a"]), int(paar["index_b"])))
        logging.info(
            "Lokale KI-Dublettenpruefung abgeschlossen: %s von %s Paaren bestaetigt.",
            len(bestaetigt),
            len(kandidaten),
        )
        return bestaetigt

    def abbrechen(self) -> None:
        abbrechen = getattr(self.client, "abbrechen", None)
        if callable(abbrechen):
            abbrechen()


def _dubletten_prompt(paare: list[dict[str, object]]) -> str:
    return f"""Du pruefst moegliche Dubletten fuer die lokale App JobScout AI.

Entscheide sehr konservativ, ob zwei Eintraege dieselbe konkrete Stellenausschreibung beschreiben.
Gleicher Beruf, gleiche Firma oder gleicher Ort allein reichen nicht. Verschiedene Standorte, Fachbereiche,
Arbeitszeiten, Referenznummern oder erkennbar unterschiedliche Aufgaben bedeuten: nicht zusammenfuehren.
Titelvarianten, gekuerzte Texte und verschiedene Jobportale duerfen dieselbe Stelle sein.
Bei Unsicherheit antworte mit same_job=false. Erfinde keine Informationen.

Kandidatenpaare:
{json.dumps(paare, ensure_ascii=False)}

Antworte ausschliesslich als JSON-Objekt:
{{
  "pairs": [
    {{
      "pair_id": 0,
      "same_job": false,
      "confidence": 0,
      "reason": "kurzer, konkret pruefbarer Grund"
    }}
  ]
}}
"""


def _analyse_prompt(jobs: list[Job], suchanfrage: SearchRequest, gesamt_treffer: int | None = None) -> str:
    job_daten = [
        {
            "index": index,
            "titel": job.titel,
            "firma": job.firma,
            "ort": job.ort,
            "quelle": job.quelle,
            "beschreibung": _kuerzen(job.kurzbeschreibung, 650),
            "beschreibung_ist_moeglicherweise_gekuerzt": _beschreibung_wirkt_gekuerzt(job.kurzbeschreibung),
            "veroeffentlichungsdatum": job.veroeffentlichungsdatum,
            "gehalt_min": job.gehalt_min,
            "gehalt_max": job.gehalt_max,
            "kategorie": job.kategorie,
        }
        for index, job in enumerate(jobs)
    ]
    kontext = {
        "suchbegriff": suchanfrage.suchbegriff,
        "ort": suchanfrage.ort,
        "umkreis": suchanfrage.umkreis,
        "ki_kriterien": _ki_kriterien_promptdaten(suchanfrage.ki_kriterien),
        "nutzerprofil": _nutzerprofil_promptdaten(suchanfrage.ki_kriterien),
        "gesamt_treffer_vor_ki_screening": gesamt_treffer if gesamt_treffer is not None else len(jobs),
        "detailliert_analysierte_top_kandidaten": len(job_daten),
        "jobs": job_daten,
    }
    return f"""Du bist die lokale KI-Auswertung fuer JobScout AI.

Bewerte nur die gelieferten Jobs. Erfinde keine Stellen, Firmen oder Links.
Wichtig: Die gelieferten Jobs sind Top-Kandidaten aus allen Suchtreffern. Die Gesamtanzahl steht in gesamt_treffer_vor_ki_screening.
Nutze Deutsch. Sei kurz und pruefbar.
Wenn Informationen fehlen, sage das knapp statt zu raten.
Nutze die ki_kriterien als verbindliches Bewertungsprofil des Nutzers. Wenn ein Kriterium nicht beurteilbar ist, nenne es als offene Pruefung statt einen Nachteil zu erfinden.
Nutze das nutzerprofil als dauerhafte Wissensbasis zur Person. Bewerte aber nur, was aus Jobdaten und Profil ableitbar ist.
Bewerte die praktische Bewerbungsrelevanz und verlange keine perfekte Profil- oder Titeluebereinstimmung. Uebertragbare Aufgaben, realistische Einstiegschance, Lernpotenzial, Organisation, Verwaltung, Bueroarbeit sowie digitale und technische Kenntnisse sind positive Signale.
Trenne strikt zwischen hard_conflicts und open_questions. Nur ein im Jobtext eindeutig belegter Konflikt mit einem ausdruecklichen Nutzer-Ausschluss ist ein hard_conflict. Fehlende oder unklare Angaben sind open_questions und ziehen keine Punkte ab.
Klare Ausschluesse sind zum Beispiel ausdruecklich unerwuenschte Schicht- oder Wochenendarbeit, klare Vertriebspflicht, ein ausgeschlossener Taetigkeitsbereich, zwingende Fuehrungsverantwortung, eindeutige unpassende Vollzeitpflicht oder ein verbindlich zu weit entfernter Standort.
Remote-Modus "zwingend" bedeutet: Eine ausdrueckliche reine Vor-Ort-Pflicht ist ein klarer Konflikt. Fehlt ein Remote/Homeoffice-Signal nur, ist das eine offene Pruefung ohne automatischen Punktabzug. Remote-Modus "wichtig" bedeutet: Remote/Homeoffice sichtbar positiv gewichten, fehlende Information aber nur als Unsicherheit behandeln.
Teilzeit gewuenscht bedeutet: Teilzeit, Minijob, flexible Stunden oder konkrete passende Arbeitszeit positiv werten; fehlende Angaben als offene Pruefung nennen.
Gehaltswuensche sind Kriterien: Nenne fehlende oder unklare Gehaltsangaben als offene Pruefung. Erfinde kein Gehalt.
Wichtig: Manche Provider liefern nur gekuerzte Stellenbeschreibungen oder Ausschnitte. Werte fehlende Details deshalb nicht automatisch als schlechtes Job-Signal. Fuehre solche Punkte nur als Unsicherheit/offene Pruefung auf.
Nutze diese Score-Skala konsistent:
- 75-100: sehr gute Passung
- 60-74: gute Passung
- 45-59: pruefenswerter Treffer
- 30-44: schwache Passung
- 0-29: eher unpassend
Ein grundsaetzlich interessanter Top-Kandidat mit mindestens einem konkreten positiven Signal und ohne hard_conflict soll in der Regel mindestens 45 Punkte erhalten. Werte von 0-29 sind fuer klar fachfremde Stellen oder eindeutige Ausschluesse reserviert. Eine fehlende Gehalts-, Teilzeit-, Remote-, Arbeitszeit- oder Aufgabenangabe darf den Score nicht senken.
Die globale summary ist Pflicht. Sie soll 2-4 kurze Saetze enthalten: Gesamtpassung, beste Trefferart, wichtigste Einschraenkungen und konkrete naechste Pruefung.
Gib fuer jeden gelieferten Top-Kandidaten genau eine Job-Bewertung zurueck, auch wenn die Empfehlung nur "anschauen" oder "ignorieren" lautet.
Jede Job-summary soll erklaeren, warum die Stelle passt oder nicht passt. strengths, risks und skills muessen konkrete, unterschiedliche Informationen enthalten.

Suchkontext und Jobs:
{json.dumps(kontext, ensure_ascii=False)}

Antworte ausschliesslich als JSON-Objekt:
{{
  "summary": "2-4 kurze Saetze zur gesamten Trefferliste und zu den Nutzerkriterien",
  "jobs": [
    {{
      "index": 0,
      "match_score": 0,
      "recommendation": "anschauen|speichern|ignorieren",
      "summary": "konkretes Kurzfazit zur Stelle mit Bezug auf Suche und Kriterien",
      "strengths": ["maximal drei konkrete Passungsgruende"],
      "hard_conflicts": ["maximal drei eindeutig belegte Konflikte; sonst leer"],
      "open_questions": ["maximal drei fehlende oder unklare Angaben; ohne Punktabzug"],
      "skills": ["erkannte Anforderungen oder Skills"]
    }}
  ]
}}
"""


def _analyse_kandidaten(jobs: list[Job], suchanfrage: SearchRequest, max_jobs: int) -> list[Job]:
    if max_jobs <= 0:
        return []
    bewertete_jobs = [
        (_vorsortier_score(job, suchanfrage), index, job)
        for index, job in enumerate(jobs)
    ]
    bewertete_jobs.sort(key=lambda eintrag: (-eintrag[0], eintrag[1]))
    return [job for _score, _index, job in bewertete_jobs[:max_jobs]]


def _vorsortier_score(job: Job, suchanfrage: SearchRequest) -> int:
    text = " ".join([
        job.titel,
        job.firma,
        job.ort,
        job.quelle,
        job.kurzbeschreibung,
        job.kategorie,
    ]).lower()
    titel = str(job.titel or "").lower()
    score = 0

    for begriff in _suchwoerter(suchanfrage.suchbegriff):
        if begriff in titel:
            score += 12
        elif begriff in text:
            score += 6

    ort = str(suchanfrage.ort or "").strip().lower()
    if ort and ort in str(job.ort or "").lower():
        score += 10

    kriterien = suchanfrage.ki_kriterien if isinstance(suchanfrage.ki_kriterien, dict) else {}
    if kriterien.get("homeoffice") or kriterien.get("remote_modus") in ("wichtig", "zwingend"):
        if any(wort in text for wort in ("remote", "homeoffice", "home office", "mobil", "hybrid")):
            score += 14
        elif kriterien.get("remote_modus") == "zwingend":
            score -= 8

    if kriterien.get("teilzeit") and any(wort in text for wort in ("teilzeit", "minijob", "aushilfe")):
        score += 10
    if kriterien.get("vollzeit") and "vollzeit" in text:
        score += 8
    if kriterien.get("wohnortnaehe") and ort and ort in str(job.ort or "").lower():
        score += 8

    for kriterium in (
        "freitext",
        "arbeitszeit",
        "gewuenschte_taetigkeiten",
        "ausschlusskriterien",
    ):
        for begriff in _suchwoerter(str(kriterien.get(kriterium, ""))):
            if begriff in text:
                score += 4

    profil = kriterien.get("nutzerprofil") if isinstance(kriterien.get("nutzerprofil"), dict) else {}
    for kriterium in ("staerken", "kenntnisse", "wunschrolle", "berufserfahrung"):
        for begriff in _suchwoerter(str(profil.get(kriterium, ""))):
            if begriff in text:
                score += 3

    for begriff in _suchwoerter(str(kriterien.get("ausschlusskriterien", ""))):
        if begriff in text:
            score -= 8

    if job.kurzbeschreibung:
        score += min(8, len(job.kurzbeschreibung) // 250)
    if job.link:
        score += 2
    if job.gehalt_min or job.gehalt_max:
        score += 3
    return score


def _suchwoerter(text: str) -> list[str]:
    stopwoerter = {"und", "oder", "der", "die", "das", "eine", "einen", "sollte", "sein", "mit", "ohne"}
    woerter = []
    for wort in str(text or "").lower().replace("/", " ").replace(",", " ").replace(".", " ").split():
        if len(wort) < 3 or wort in stopwoerter:
            continue
        woerter.append(wort)
    return woerter


def _ki_kriterien_promptdaten(kriterien: dict[str, Any] | None) -> dict[str, Any]:
    daten = kriterien if isinstance(kriterien, dict) else {}
    ergebnis: dict[str, Any] = {}
    bool_felder = {
        "homeoffice": "homeoffice_wichtig",
        "teilzeit": "teilzeit_passend",
        "vollzeit": "vollzeit_passend",
        "wohnortnaehe": "wohnortnaehe_wichtig",
    }
    for quelle, ziel in bool_felder.items():
        if daten.get(quelle):
            ergebnis[ziel] = True

    remote_modus = _auswahlwert(daten.get("remote_modus"), {"egal", "wichtig", "zwingend"}, "egal")
    if remote_modus != "egal":
        ergebnis["remote_modus"] = remote_modus

    text_felder = {
        "max_pendeln": "max_pendeln_oder_entfernung",
        "arbeitszeit": "arbeitszeit",
        "mindestgehalt": "mindestgehalt",
        "wunschgehalt": "wunschgehalt",
        "gehaltsmodell": "gehaltsmodell",
        "gewuenschte_taetigkeiten": "gewuenschte_taetigkeiten",
        "ausschlusskriterien": "ausschlusskriterien",
        "freitext": "weitere_kriterien",
    }
    for quelle, ziel in text_felder.items():
        wert = str(daten.get(quelle, "") or "").strip()
        if wert:
            ergebnis[ziel] = _kuerzen(wert, 300)

    prioritaet = str(daten.get("prioritaet", "") or "").strip()
    if prioritaet and prioritaet != "Ausgewogen":
        ergebnis["prioritaet"] = prioritaet
    return ergebnis


def _nutzerprofil_promptdaten(kriterien: dict[str, Any] | None) -> dict[str, Any]:
    daten = kriterien if isinstance(kriterien, dict) else {}
    profil = daten.get("nutzerprofil") if isinstance(daten.get("nutzerprofil"), dict) else {}
    return {
        feld: wert
        for feld in (
            "kurzprofil",
            "berufserfahrung",
            "staerken",
            "kenntnisse",
            "wunschrolle",
            "einschraenkungen",
        )
        if (wert := _kuerzen(str(profil.get(feld, "") or "").strip(), 450))
    }


def _auswahlwert(wert: Any, erlaubte_werte: set[str], standard: str) -> str:
    text = str(wert or "").strip()
    return text if text in erlaubte_werte else standard


def _bewertung_uebernehmen(jobs: list[Job], eintrag: Any) -> int | None:
    if not isinstance(eintrag, dict):
        return None
    try:
        index = int(eintrag.get("index"))
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(jobs):
        return None

    job = jobs[index]
    job.ki_match_score = normalisiere_match_score(eintrag.get("match_score"))
    job.ki_bewertungsart = "echt"
    job.ki_empfehlung = str(eintrag.get("recommendation", "") or "").strip()
    job.ki_zusammenfassung = str(eintrag.get("summary", "") or "").strip()
    job.ki_staerken = normalisiere_textliste(eintrag.get("strengths"))
    job.ki_ausschluesse = normalisiere_textliste(eintrag.get("hard_conflicts"))
    job.ki_offene_punkte = normalisiere_textliste(eintrag.get("open_questions"))
    alte_risiken = normalisiere_textliste(eintrag.get("risks"))
    job.ki_risiken = normalisiere_textliste(job.ki_ausschluesse + job.ki_offene_punkte + alte_risiken)
    job.ki_skills = normalisiere_textliste(eintrag.get("skills"))
    if job.ki_staerken and not job.ki_ausschluesse and job.ki_match_score < 45:
        job.ki_match_score = 45
    return index if job.hat_ki_daten() else None


def _fallback_bewertung_uebernehmen(job: Job, vorsortier_score: int, index: int) -> None:
    score = max(35, min(78, 42 + vorsortier_score))
    job.ki_match_score = score
    job.ki_bewertungsart = "technisch"
    job.ki_empfehlung = "anschauen" if score >= 55 else "pruefen"
    job.ki_zusammenfassung = (
        "Technische Vorbewertung: Diese Stelle wurde anhand Suchbegriff, Ort, Kriterien "
        "und Datenqualitaet als Kandidat ausgewaehlt."
    )
    job.ki_staerken = ["Passt zur aktuellen Suche oder zu den Kriterien"]
    job.ki_risiken = ["Lokale KI lieferte keine verwertbare Detailanalyse"]
    job.ki_offene_punkte = list(job.ki_risiken)
    job.ki_ausschluesse = []
    job.ki_skills = [job.kategorie] if job.kategorie else []


def _technische_fallback_zusammenfassung(fehlerart: str) -> str:
    if fehlerart == "timeout":
        ursache = "Die lokale KI hat die Analyse nicht innerhalb des Sicherheitslimits abgeschlossen."
    elif fehlerart in {"connection", "http"}:
        ursache = "Ollama oder das lokale Modell konnte technisch nicht erreicht werden."
    elif fehlerart in {"invalid_json", "invalid_response"}:
        ursache = "Die lokale KI hat keine verwertbare strukturierte Antwort geliefert."
    else:
        ursache = "Die lokale KI hat keine verwertbare Antwort geliefert."
    return f"{ursache} JobScout AI zeigt deshalb klar gekennzeichnete technische Vorbewertungen."


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        daten = json.loads(text)
        return daten if isinstance(daten, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        ende = text.rfind("}")
        if start == -1 or ende == -1 or ende <= start:
            return None
        try:
            daten = json.loads(text[start:ende + 1])
        except json.JSONDecodeError:
            return None
        return daten if isinstance(daten, dict) else None


def _kuerzen(text: str, max_zeichen: int) -> str:
    wert = " ".join(str(text or "").split())
    if len(wert) <= max_zeichen:
        return wert
    return wert[:max_zeichen - 3] + "..."


def _beschreibung_wirkt_gekuerzt(text: str) -> bool:
    wert = " ".join(str(text or "").split()).strip()
    if not wert:
        return True
    return len(wert) < 350 or wert.endswith("...")

