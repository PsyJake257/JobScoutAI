import json
import logging
from typing import Any

from config import LOCAL_AI_JOB_SEARCH_MAX_TERMS
from cancellation import abbruch_pruefen
from models import SearchRequest
from analysis.ai_analysis import (
    OllamaAnalysisClient,
    _ki_kriterien_promptdaten,
    _kuerzen,
    _nutzerprofil_promptdaten,
    _parse_json_object,
)


BEDINGUNGSBEGRIFFE = {
    "teilzeit",
    "vollzeit",
    "homeoffice",
    "home office",
    "remote",
    "hybrid",
    "quereinsteiger",
    "stunden",
    "stunde",
    "km",
    "ohne",
    "ruhig",
    "ruhiges",
    "buerojob",
}


class AiJobSearchPlanner:
    def __init__(self, client: OllamaAnalysisClient | None = None, max_terms: int = LOCAL_AI_JOB_SEARCH_MAX_TERMS):
        self.client = client
        self.max_terms = max(1, int(max_terms or 1))
        self.letzte_meldung = "KI-Jobsuche noch nicht gestartet."
        self.letzter_status = "nicht_gestartet"

    def suchbegriffe_generieren(
        self,
        suchanfrage: SearchRequest,
        vorhandene_suchbegriffe: list[str] | None = None,
        abbruch_event=None,
    ) -> list[str]:
        abbruch_pruefen(abbruch_event)
        anfrage = suchanfrage.bereinigt()
        vorhandene_suchbegriffe = [str(begriff or "").strip() for begriff in (vorhandene_suchbegriffe or [])]
        client = self.client or OllamaAnalysisClient(response_schema={
            "type": "object",
            "properties": {"search_terms": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": self.max_terms}},
            "required": ["search_terms"],
            "additionalProperties": False,
        })
        self.client = client
        prompt = _suchplan_prompt(anfrage, self.max_terms, vorhandene_suchbegriffe)
        logging.info(
            "KI-Suchplan gestartet: Modell=%s, MaxBegriffe=%s, Prompt-Zeichen=%s.",
            client.model,
            self.max_terms,
            len(prompt),
        )
        daten = (
            client.generate_json(prompt, abbruch_event=abbruch_event)
            if abbruch_event is not None
            else client.generate_json(prompt)
        )
        abbruch_pruefen(abbruch_event)
        if not daten:
            self.letzter_status = "fehler"
            grund = getattr(client, "last_error_kind", "")
            if grund in {"connection", "http"}:
                self.letzte_meldung = "Die lokale KI ist nicht erreichbar. Bitte erneut versuchen; die Laufzeit wird automatisch neu gestartet."
            elif grund == "timeout":
                self.letzte_meldung = "Die lokale KI hat zu lange gebraucht. Bitte erneut versuchen oder das Nutzerprofil kuerzen."
            else:
                self.letzte_meldung = "Die lokale KI lieferte keine verwertbare Antwort. Bitte erneut Vorschlaege erzeugen."
            return []

        begriffe = suchbegriffe_aus_antwort(daten, anfrage, self.max_terms, vorhandene_suchbegriffe)
        if not begriffe:
            self.letzter_status = "keine_daten"
            self.letzte_meldung = "Lokale KI lieferte keine verwendbaren Jobbezeichnungen."
            return []

        self.letzter_status = "echt"
        self.letzte_meldung = f"Lokale KI hat {len(begriffe)} Suchbegriffe vorgeschlagen."
        logging.info("KI-Suchplan abgeschlossen: %s Begriffe.", len(begriffe))
        return begriffe

    def abbrechen(self) -> None:
        abbrechen = getattr(self.client, "abbrechen", None)
        if callable(abbrechen):
            abbrechen()


def _suchplan_prompt(
    suchanfrage: SearchRequest,
    max_terms: int,
    vorhandene_suchbegriffe: list[str] | None = None,
) -> str:
    kriterien = suchanfrage.ki_kriterien if isinstance(suchanfrage.ki_kriterien, dict) else {}
    kontext = {
        "bisheriger_suchbegriff": _kuerzen(suchanfrage.suchbegriff, 160),
        "ort": _kuerzen(suchanfrage.ort, 120),
        "umkreis": suchanfrage.umkreis,
        "ki_kriterien": _ki_kriterien_promptdaten(kriterien),
        "nutzerprofil": _nutzerprofil_promptdaten(kriterien),
        "bereits_gespeicherte_suchbegriffe": [
            _kuerzen(begriff, 80)
            for begriff in (vorhandene_suchbegriffe or [])
            if str(begriff or "").strip()
        ],
        "max_suchbegriffe": max_terms,
    }
    return f"""Du bist die lokale KI-Suchplanung fuer JobScout AI.

Erzeuge bis zu {max_terms} unterschiedliche Suchbegriffe fuer eine Jobsuche.
Die Suchbegriffe werden direkt als Berufsbezeichnung an Jobprovider geschickt.
Nutze Deutsch mit korrekten Umlauten. Liefere nur sinnvolle Berufs- oder Taetigkeitsbezeichnungen.
Leite aus Nutzerprofil und Kriterien verschiedene passende Berufsfelder ab, nicht nur Synonyme.
Vermeide nahezu identische Begriffe und Begriffe, die voraussichtlich kaum Treffer liefern.
Schlage keinen Begriff vor, der bereits in bereits_gespeicherte_suchbegriffe steht oder nahezu identisch dazu ist.

Wichtige Regel: Keine Arbeitsbedingungen, Orte oder Filter als Suchbegriffe verwenden.
Nicht erlaubte Suchbegriffe oder Begriffsteile: Teilzeit, Vollzeit, Homeoffice, Remote, Hybrid, Quereinsteiger, Stunden, Kilometer, Orte, ohne Vertrieb, ruhiges Buero.
Diese Informationen dienen nur spaeter zur Bewertung, nicht zur Provider-Suche.
Wenn der bisherige Suchbegriff selbst nur eine Bedingung ist, nutze ihn nicht als Suchbegriff.

Kontext:
{json.dumps(kontext, ensure_ascii=False)}

Antworte ausschliesslich als JSON-Objekt mit dem Feld search_terms.
Dieses Feld muss eine Liste konkreter, realer Berufsnamen enthalten, zum Beispiel
Sachbearbeiter, Bürokaufmann, Lagerist oder Elektroniker, jeweils passend zum Kontext.
Wenn noch kein Nutzerprofil angegeben ist, orientiere dich am bisherigen Suchbegriff.
Fehlt auch dieser, schlage verschiedene verbreitete Berufe vor.
Keine Platzhalter wie Berufsbezeichnung oder Suchbegriff ausgeben. Gib nicht den Kontext zurueck.
"""


def suchbegriffe_aus_antwort(
    daten: dict[str, Any],
    suchanfrage: SearchRequest,
    max_terms: int,
    vorhandene_suchbegriffe: list[str] | None = None,
) -> list[str]:
    if not isinstance(daten, dict):
        return []
    roh = daten.get("search_terms") or daten.get("suchbegriffe") or daten.get("terms")
    if isinstance(roh, str):
        parsed = _parse_json_object(roh)
        if isinstance(parsed, dict):
            roh = parsed.get("search_terms") or parsed.get("suchbegriffe") or parsed.get("terms")
    if not isinstance(roh, list):
        return []

    ergebnis = []
    gesehen = [
        normalisiere_suchbegriff(begriff)
        for begriff in (vorhandene_suchbegriffe or [])
        if normalisiere_suchbegriff(begriff)
    ]
    for eintrag in roh:
        begriff = normalisiere_suchbegriff(eintrag)
        if not begriff or any(suchbegriffe_sind_aehnlich(begriff, bekannt) for bekannt in gesehen):
            continue
        if not ist_erlaubter_job_suchbegriff(begriff, suchanfrage):
            continue
        ergebnis.append(begriff)
        gesehen.append(begriff)
        if len(ergebnis) >= max_terms:
            break
    return ergebnis


def normalisiere_suchbegriff(wert: object) -> str:
    text = str(wert or "").strip()
    text = text.strip("-•*0123456789. )(")
    text = " ".join(text.replace("/", " ").split())
    if len(text) > 60:
        text = text[:60].rsplit(" ", 1)[0].strip()
    return text


def suchbegriff_aehnlichkeitsschluessel(begriff: str) -> str:
    text = normalisiere_suchbegriff(begriff).lower()
    zusammensetzungen = {
        "verwaltungsassistenz": "verwaltung assistenz",
        "projektassistenz": "projekt assistenz",
        "teamassistenz": "team assistenz",
        "office-manager": "office manager",
    }
    for quelle, ziel in zusammensetzungen.items():
        text = text.replace(quelle, ziel)
    ersetzungen = {
        "kauffrau": "kaufleute",
        "kaufmann": "kaufleute",
        "mitarbeiterin": "mitarbeiter",
        "assistentin": "assistenz",
        "assistent": "assistenz",
        "referentin": "referent",
        "angestellte": "angestellter",
    }
    for quelle, ziel in ersetzungen.items():
        text = text.replace(quelle, ziel)
    return " ".join(sorted(text.replace("-", " ").split()))


def suchbegriffe_sind_aehnlich(erster: str, zweiter: str) -> bool:
    erster_schluessel = suchbegriff_aehnlichkeitsschluessel(erster)
    zweiter_schluessel = suchbegriff_aehnlichkeitsschluessel(zweiter)
    if not erster_schluessel or not zweiter_schluessel:
        return False
    if erster_schluessel == zweiter_schluessel:
        return True

    erste_woerter = set(erster_schluessel.split())
    zweite_woerter = set(zweiter_schluessel.split())
    gemeinsam = erste_woerter & zweite_woerter
    vereinigt = erste_woerter | zweite_woerter
    return bool(gemeinsam) and len(gemeinsam) / len(vereinigt) >= 0.75

def ist_erlaubter_job_suchbegriff(begriff: str, suchanfrage: SearchRequest) -> bool:
    text = normalisiere_suchbegriff(begriff)
    if len(text) < 4:
        return False
    klein = text.lower()
    if klein.startswith(("berufsbezeichnung", "suchbegriff")) or klein in {"beruf", "bezeichnung", "stelle"}:
        return False
    if any(zeichen.isdigit() for zeichen in klein):
        return False
    if any(bedingung in klein for bedingung in BEDINGUNGSBEGRIFFE):
        return False

    ort_teile = [teil for teil in suchanfrage.ort.lower().replace(",", " ").split() if len(teil) >= 4]
    if any(teil in klein for teil in ort_teile):
        return False

    woerter = [wort for wort in klein.replace("-", " ").split() if len(wort) >= 3]
    if len(woerter) > 5:
        return False
    return True
