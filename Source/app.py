import logging
import os
import threading
import webbrowser
from copy import deepcopy
from ui_text import messagebox, anzeigetext

import ui_widgets as ctk
from PIL import Image, ImageTk

from config import (
    APP_NAME,
    GOOD_MATCH_SCORE_THRESHOLD,
    LOCAL_AI_ANALYSIS_BEST_MATCH_DISPLAY_LIMIT,
    LOCAL_AI_ANALYSIS_MODEL,
    LOCAL_AI_JOB_SEARCH_MAX_TERMS,
    RESULTS_PER_PAGE,
    VERSION,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from logging_config import log_pfad, richte_logging_ein
from cancellation import OperationCancelled
from models import SearchRequest, job_schluessel
from paths import APP_ICON_DATEI, APP_LOGO_DATEI, THIRD_PARTY_NOTICES_DATEI
from service_factory import erstelle_job_search_service
from providers import standard_provider_registry
from setup_dialogs import suchquellen_editor, zeige_einleitung


SORTIERUNGEN = [
    "Letzte Statusaenderung",
    "Naechstes Follow-up",
    "Bewerbungsdatum",
    "Veroeffentlichungsdatum",
    "Eigene Bewertung",
]
TREFFER_SORTIERUNGEN = [
    "Neueste zuerst",
    "Aelteste zuerst",
    "Stellenname A-Z",
    "Stellenname Z-A",
    "Unternehmen A-Z",
    "Unternehmen Z-A",
    "Ort A-Z",
    "Ort Z-A",
]
ANALYSE_TREFFER_SORTIERUNGEN = [
    "KI-Match: hoch nach niedrig",
    "KI-Match: niedrig nach hoch",
    *TREFFER_SORTIERUNGEN,
]
FOLLOWUP_FILTER = ["Alle", "Offene Follow-ups", "Heute", "Ueberfaellig", "Ohne Follow-up"]
BEWERBUNGSSTATUS_TABS = ["Alle", "Gespeichert", "Bewerbung geplant", "Beworben", "Gespraech", "Erledigt"]
BEWERBUNGSSTATUS_TAB_FARBEN = {
    "Alle": (("#EDF1F5", "#485A6B"), ("#718091", "#63778B")),
    "Gespeichert": (("#DDF1FF", "#25618A"), ("#64B5EE", "#3B8FC3")),
    "Bewerbung geplant": (("#FFF4C7", "#80651B"), ("#E1AD22", "#D0A62A")),
    "Beworben": (("#DDF7EB", "#287A5D"), ("#2AAC7B", "#34B98A")),
    "Gespraech": (("#FFE8C6", "#8B5717"), ("#F5B557", "#F1A642")),
    "Erledigt": (("#F9DDE1", "#4A252B"), ("#DF6B78", "#A94755")),
}
FAVORIT_SYMBOL_GESPEICHERT = "\u2665"
FAVORIT_SYMBOL_NICHT_GESPEICHERT = "\u2661"
KARTEN_BESCHREIBUNG_MAX_ZEICHEN = 280
SCHREIBGESCHUETZTE_DETAIL_FELDER = {"kurzbeschreibung"}
DARSTELLUNG_NAMEN = {
    "system": "System",
    "light": "Hell",
    "dark": "Dunkel",
}
FARBE_HINTERGRUND = ("#F3F6F9", "#0B1119")
FARBE_SEITENLEISTE = ("#FFFFFF", "#0E1621")
FARBE_KARTE = ("#FFFFFF", "#151E29")
FARBE_KARTE_ZWEI = ("#EDF2F7", "#101923")
FARBE_RAND = ("#D7E0E8", "#273444")
FARBE_TEXT_SEKUNDAER = ("#526170", "#9AA9BA")
FARBE_PRIMAER = ("#176DB3", "#62B2FF")
FARBE_PRIMAER_HOVER = ("#125A94", "#3B9CF0")
FARBE_PRIMAER_TEXT = ("#FFFFFF", "#071522")
FARBE_ERFOLG = ("#16865C", "#25A978")
FARBE_WARNUNG = ("#B86E00", "#F0A43C")
FARBE_FEHLER = ("#C43E4F", "#E45D6D")
KEIN_NUTZERPROFIL = "Keine Profile gespeichert"
STATUS_BADGE_FARBEN = {
    "Neu": (("#E8EEF4", "#263341"), ("#405366", "#B8C5D2")),
    "Gespeichert": (("#E8EEF4", "#263341"), ("#405366", "#B8C5D2")),
    "Bewerbung geplant": (("#E4EFFB", "#173753"), FARBE_PRIMAER),
    "Beworben": (("#E1ECFB", "#17365F"), FARBE_PRIMAER),
    "Gespraech": (("#E0F3EE", "#153B35"), FARBE_ERFOLG),
    "Angebot": (("#DDF3E8", "#143C2C"), FARBE_ERFOLG),
    "Absage": (("#FBE5E8", "#48232A"), FARBE_FEHLER),
    "Erledigt": (("#E8ECEF", "#2A323A"), FARBE_TEXT_SEKUNDAER),
}
PROVIDER_EINSTELLUNGEN = (
    {
        "name": "arbeitsagentur",
        "label": "Bundesagentur fuer Arbeit",
        "beschreibung": "Oeffentliche deutsche Jobsuche mit Ort- und Umkreissuche; kein eigener API-Key erforderlich.",
        "url": "https://www.arbeitsagentur.de/jobsuche/",
        "link_text": "Jobsuche oeffnen",
    },
    {
        "name": "jooble",
        "label": "Jooble",
        "beschreibung": "Internationale Stellen-API; benoetigt JOOBLE_API_KEY in der lokalen .env-Datei.",
        "url": "https://de.jooble.org/api/about",
        "link_text": "API-Info oeffnen",
    },
    {
        "name": "adzuna",
        "label": "Adzuna",
        "beschreibung": "Stellen-API fuer Deutschland; benoetigt ADZUNA_APP_ID und ADZUNA_API_KEY.",
        "url": "https://developer.adzuna.com/",
        "link_text": "API-Info oeffnen",
    },
    {
        "name": "websuche",
        "label": "SerpApi-Websuche",
        "beschreibung": "Strukturierte Google-Jobs-Ergebnisse mit konkreten Stellenlinks und monatlichem Kontingent.",
        "url": "https://serpapi.com/google-jobs-api",
        "link_text": "API-Info oeffnen",
    },
    {
        "name": "karriereseiten",
        "label": "Karriereseiten",
        "beschreibung": "Liest konfigurierte Unternehmensseiten aus CAREER_SITE_URLS und bevorzugt JobPosting-Strukturdaten.",
        "url": "https://schema.org/JobPosting",
        "link_text": "Format ansehen",
    },
    {
        "name": "arbeitnow",
        "label": "Arbeitnow",
        "beschreibung": "Kostenlose oeffentliche Stellen-API ohne eigenen Key; der Radius wird nachgelagert gefiltert.",
        "url": "https://www.arbeitnow.com/api/job-board-api",
        "link_text": "API-Info oeffnen",
    },
)


def beschreibung_lesbar(text):
    return str(text or "").replace("**", "").strip()


def beschreibung_vorschau(text, aufgeklappt=False, max_zeichen=KARTEN_BESCHREIBUNG_MAX_ZEICHEN):
    beschreibung = " ".join(beschreibung_lesbar(text).split())
    if aufgeklappt or len(beschreibung) <= max_zeichen:
        return beschreibung
    return f"{beschreibung[:max_zeichen - 3]}..."


def beschreibung_hat_mehr(text, max_zeichen=KARTEN_BESCHREIBUNG_MAX_ZEICHEN):
    return len(" ".join(beschreibung_lesbar(text).split())) > max_zeichen


def favoriten_button_text(job):
    return FAVORIT_SYMBOL_GESPEICHERT if job.favorit else FAVORIT_SYMBOL_NICHT_GESPEICHERT


def status_badge_farben(status):
    return STATUS_BADGE_FARBEN.get(str(status or "Neu"), STATUS_BADGE_FARBEN["Neu"])


def ist_detailfeld_schreibgeschuetzt(name):
    return name in SCHREIBGESCHUETZTE_DETAIL_FELDER


def textfeld_schreibgeschuetzt_machen(textfeld):
    def eingabe_blockieren(event=None):
        return "break"

    for ereignis in ("<Key>", "<<Paste>>", "<<Cut>>"):
        textfeld.bind(ereignis, eingabe_blockieren)
    return textfeld


def darstellung_normalisieren(wert):
    text = str(wert or "system").strip().lower()
    rueckwaerts = {name.lower(): schluessel for schluessel, name in DARSTELLUNG_NAMEN.items()}
    return text if text in DARSTELLUNG_NAMEN else rueckwaerts.get(text, "system")


def aktionsfarbthema_anwenden():
    button_thema = ctk.ThemeManager.theme["CTkButton"]
    button_thema["fg_color"] = list(FARBE_PRIMAER)
    button_thema["hover_color"] = list(FARBE_PRIMAER_HOVER)
    button_thema["text_color"] = list(FARBE_PRIMAER_TEXT)


def ki_aktionszustand(suche_laeuft, analyse_laeuft, hat_jobs, analyse_status, hat_ki_daten):
    if suche_laeuft:
        analyse_button = ("disabled", "Erst Suche abwarten")
    elif analyse_laeuft:
        analyse_button = ("normal", "Analyse abbrechen")
    elif not hat_jobs:
        analyse_button = ("disabled", "Treffer auswaehlen")
    else:
        analyse_button = ("normal", "Analyse starten")

    if analyse_laeuft:
        return analyse_button, ("disabled", "Analyse laeuft...", "neutral")
    if analyse_status == "echt":
        return analyse_button, ("normal", "Zur KI-Analyse", "erfolg")
    if analyse_status == "teilweise":
        return analyse_button, ("normal", "Zur KI-Analyse", "warnung")
    if analyse_status == "technisch":
        return analyse_button, ("normal", "Zur KI-Analyse", "neutral")
    return analyse_button, ("normal", "Zur KI-Analyse", "erfolg" if hat_jobs else "neutral")


def suchstatus_daten(
    ansicht,
    normale_anzahl=0,
    ki_anzahl=0,
    normale_laeuft=False,
    ki_laeuft=False,
    normale_meldung="",
    ki_meldung="",
):
    if ansicht == "suche":
        if normale_laeuft:
            return "Jobsuche laeuft...", "normal", False
        if str(normale_meldung or "").startswith(("Fehler", "Jobsuche abgebrochen")):
            return str(normale_meldung), "normal", False
        return f"{max(0, int(normale_anzahl or 0))} Treffer aus der Jobsuche", "normal", normale_anzahl > 0

    if ansicht == "ki_suche":
        if ki_laeuft:
            return "KI-Jobsuche laeuft...", "ki", False
        if str(ki_meldung or "").startswith(("Fehler", "Bitte", "KI-Jobsuche abgebrochen", "KI-Suchplanung abgebrochen")):
            return str(ki_meldung), "ki", False
        return f"{max(0, int(ki_anzahl or 0))} Treffer aus der KI-Jobsuche", "ki", ki_anzahl > 0

    return "", "", False


def scrollbare_liste_nach_oben(liste):
    canvas = getattr(liste, "_parent_canvas", None)
    if canvas is not None and hasattr(canvas, "yview_moveto"):
        canvas.yview_moveto(0)
        return True
    if hasattr(liste, "yview_moveto"):
        liste.yview_moveto(0)
        return True
    return False


def match_score_verteilung(jobs):
    verteilung = {
        "Sehr gute Passung (75-100)": 0,
        "Gute Passung (60-74)": 0,
        "Pruefenswert (45-59)": 0,
        "Schwach (30-44)": 0,
        "Eher unpassend (0-29)": 0,
    }
    for job in jobs:
        score = max(0, min(100, int(getattr(job, "ki_match_score", 0) or 0)))
        if score >= 75:
            verteilung["Sehr gute Passung (75-100)"] += 1
        elif score >= 60:
            verteilung["Gute Passung (60-74)"] += 1
        elif score >= 45:
            verteilung["Pruefenswert (45-59)"] += 1
        elif score >= 30:
            verteilung["Schwach (30-44)"] += 1
        else:
            verteilung["Eher unpassend (0-29)"] += 1
    return verteilung


def ki_beste_treffer(jobs, limit=LOCAL_AI_ANALYSIS_BEST_MATCH_DISPLAY_LIMIT):
    bewertete_jobs = [job for job in jobs if job.hat_ki_daten()]
    sortierte_jobs = sorted(bewertete_jobs, key=lambda eintrag: eintrag.ki_match_score, reverse=True)
    if limit and limit > 0:
        return sortierte_jobs[:limit]
    return sortierte_jobs


def analyse_treffer_auswaehlen(normale_jobs, ki_jobs, normale_aktiv=True, ki_aktiv=True):
    ausgewaehlt = []
    gesehen = set()
    quellen = []
    if normale_aktiv:
        quellen.append(normale_jobs or [])
    if ki_aktiv:
        quellen.append(ki_jobs or [])
    for jobs in quellen:
        for job in jobs:
            schluessel = job_schluessel(job)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            ausgewaehlt.append(job)
    return ausgewaehlt


def haeufigkeiten(werte, limit=6):
    zaehler = {}
    for wert in werte:
        text = str(wert or "").strip()
        if text:
            zaehler[text] = zaehler.get(text, 0) + 1
    return sorted(zaehler.items(), key=lambda eintrag: (-eintrag[1], eintrag[0].lower()))[:limit]


class BeschreibungAnzeigeStatus:
    def __init__(self):
        self.aufgeklappte_schluessel = set()

    def ist_aufgeklappt(self, schluessel):
        return schluessel in self.aufgeklappte_schluessel

    def umschalten(self, schluessel):
        if schluessel in self.aufgeklappte_schluessel:
            self.aufgeklappte_schluessel.remove(schluessel)
            return False
        self.aufgeklappte_schluessel.add(schluessel)
        return True


class JobScoutAI:

    def __init__(self):
        richte_logging_ein()
        logging.info("JobScout AI gestartet")

        self.job_service = erstelle_job_search_service()
        self.settings = self.job_service.settings_laden()
        self.geladenes_nutzerprofil_name = self.job_service.nutzerprofile_initialisieren(
            self.settings.get("nutzerprofil"),
            self.settings.get("nutzerprofil_auswahl", ""),
        )
        geladenes_profil = self.job_service.nutzerprofil_laden(self.geladenes_nutzerprofil_name)
        if geladenes_profil is not None:
            self.settings["nutzerprofil_auswahl"] = geladenes_profil.name
            self.settings["nutzerprofil"] = geladenes_profil.daten()
            self.job_service.settings_speichern(self.settings)
        self.jobs = []
        self.normale_suchergebnisse = []
        self.ki_suchergebnisse = []
        self.analyse_jobs = []
        self.ansicht = "dashboard"
        self.aktuelle_seite = 0
        self.ansichts_zustaende = {}
        self.beschreibung_status = BeschreibungAnzeigeStatus()
        self.undo_timer_id = None
        self.provider_variablen = {}
        self.ki_provider_variablen = {}
        self.ki_kriterien_variablen = {}
        self.nutzerprofil_widgets = {}
        self.suche_laeuft = False
        self.ki_laeuft = False
        self.ki_jobsuche_laeuft = False
        self.normaler_such_abbruch = None
        self.ki_jobsuche_abbruch = None
        self.ki_analyse_abbruch = None
        self.ki_analyse_zustand_snapshot = None
        self.ki_kriterien_snapshot = None
        self.ki_zusammenfassung_veraltet = False
        self.ki_jobsuche_begriffe = []
        self.ki_jobsuche_widgets = []
        self.ki_suchbegriff_pool_widgets = {}
        self.ki_jobsuche_meldung = "KI-Jobsuche bereit. Suchbegriffe verwalten oder einen Suchlauf starten."
        self.normaler_suchmeldung = ""
        self.letzter_suchkontext = None
        self.normaler_suchkontext = None
        self.ki_suchkontext = None
        self.aktuelle_ergebnisquelle = "normal"
        self.normale_treffer_sortierung = "Neueste zuerst"
        self.ki_treffer_sortierung = "Neueste zuerst"
        self.analyse_treffer_sortierung = "KI-Match: hoch nach niedrig"
        self.analyse_quellen_snapshot = set()
        self.analyse_profil_snapshot = ""
        self.analyse_hinweis = ""
        self.wird_beendet = False
        self.nav_buttons = {}
        self.darstellung_modus = darstellung_normalisieren(self.settings.get("darstellung"))

        ctk.set_appearance_mode(self.darstellung_modus)
        ctk.set_default_color_theme("blue")
        aktionsfarbthema_anwenden()
        self.app = ctk.CTk()
        self.app.title(f"{APP_NAME} v{VERSION}")
        self.app.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.app.minsize(1040, 700)
        self.app.configure(fg_color=FARBE_HINTERGRUND)
        self.app.grid_columnconfigure(1, weight=1)
        self.app.grid_rowconfigure(0, weight=1)
        self.branding_bild = None
        self.fenster_icon_bild = None
        self.seitenleisten_logo_bild = None
        self._branding_laden()
        self.analyse_normale_jobs = ctk.BooleanVar(value=False)
        self.analyse_ki_jobs = ctk.BooleanVar(value=False)
        self.analyse_mit_nutzerprofil = ctk.BooleanVar(value=True)
        profil_auswahl = self.geladenes_nutzerprofil_name or KEIN_NUTZERPROFIL
        self.nutzerprofil_editor_auswahl = ctk.StringVar(value=profil_auswahl)
        self.analyse_nutzerprofil_auswahl = ctk.StringVar(value=profil_auswahl)
        self.ki_suchbereich = ctk.StringVar(value="Suchbegriffe")
        self.ki_suchbegriff_set_auswahl = ctk.StringVar(value="")

        self._seitenleiste_erstellen()

        self.hauptbereich = ctk.CTkFrame(self.app, fg_color="transparent", corner_radius=0)
        self.hauptbereich.grid(row=0, column=1, sticky="nsew")
        self.hauptbereich.grid_columnconfigure(0, weight=1)
        self.hauptbereich.grid_rowconfigure(1, weight=1)

        self._kopfzeile_erstellen()

        self.arbeitsbereich = ctk.CTkFrame(self.hauptbereich, fg_color="transparent", corner_radius=0)
        self.arbeitsbereich.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))

        self.such_panel = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.such_panel.grid_columnconfigure(0, weight=4)
        self.such_panel.grid_columnconfigure(1, weight=3)
        self.such_panel.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            self.such_panel,
            text="Neue Jobsuche",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            self.such_panel,
            text="Suchbegriff, Region und Quellen festlegen",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 14))

        suchfeld = ctk.CTkFrame(self.such_panel, fg_color="transparent")
        suchfeld.grid(row=2, column=0, sticky="ew", padx=(18, 8))
        ctk.CTkLabel(suchfeld, text="Berufsbezeichnung", anchor="w").pack(fill="x")
        self.such = ctk.CTkEntry(
            suchfeld,
            placeholder_text="z. B. Buerokraft, Sachbearbeitung, Online-Lernbegleitung",
            height=38,
        )
        self.such.pack(fill="x", pady=(4, 0))
        self.such.insert(0, self.settings.get("suchbegriff", ""))

        ortsfeld = ctk.CTkFrame(self.such_panel, fg_color="transparent")
        ortsfeld.grid(row=2, column=1, sticky="ew", padx=8)
        ctk.CTkLabel(ortsfeld, text="Ort", anchor="w").pack(fill="x")
        self.ort = ctk.CTkEntry(ortsfeld, placeholder_text="z. B. Bad Nauheim", height=38)
        self.ort.pack(fill="x", pady=(4, 0))
        self.ort.insert(0, self.settings.get("ort", ""))

        radiusfeld = ctk.CTkFrame(self.such_panel, fg_color="transparent")
        radiusfeld.grid(row=2, column=2, sticky="ew", padx=(8, 18))
        ctk.CTkLabel(radiusfeld, text="Suchradius", anchor="w").pack(fill="x")
        self.umkreis = ctk.CTkComboBox(
            radiusfeld,
            values=["10 km", "20 km", "30 km", "50 km", "100 km"],
            height=38,
        )
        self.umkreis.pack(fill="x", pady=(4, 0))
        self.umkreis.set(self._umkreis_anzeige(self.settings.get("umkreis", "30")))

        self.provider_frame = ctk.CTkFrame(self.such_panel, fg_color="transparent")
        self.provider_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 18))
        self._provider_checkboxes_erstellen()

        self.such_button = ctk.CTkButton(
            self.such_panel,
            text="Jobs suchen",
            command=self.suchen,
            height=40,
            font=("Segoe UI", 13, "bold"),
        )
        self.such_button.grid(row=3, column=2, sticky="ew", padx=(8, 18), pady=(16, 18))

        self.ki_such_panel = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.ki_such_panel.grid_columnconfigure(0, weight=3)
        self.ki_such_panel.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.ki_such_panel,
            text="KI-Suchlauf konfigurieren",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            self.ki_such_panel,
            text="Eigener Suchraum fuer alle aktiven KI-Suchbegriffe",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

        ki_region = ctk.CTkFrame(self.ki_such_panel, fg_color="transparent")
        ki_region.grid(row=2, column=0, sticky="ew", padx=(18, 10))
        ki_region.grid_columnconfigure(0, weight=3)
        ki_region.grid_columnconfigure(1, weight=1)
        ki_ortsfeld = ctk.CTkFrame(ki_region, fg_color="transparent")
        ki_ortsfeld.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(ki_ortsfeld, text="Ort", anchor="w").pack(fill="x")
        self.ki_ort = ctk.CTkEntry(ki_ortsfeld, placeholder_text="z. B. Bad Nauheim", height=38)
        self.ki_ort.pack(fill="x", pady=(4, 0))
        self.ki_ort.insert(0, self.settings.get("ki_ort", self.settings.get("ort", "")))

        ki_radiusfeld = ctk.CTkFrame(ki_region, fg_color="transparent")
        ki_radiusfeld.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ctk.CTkLabel(ki_radiusfeld, text="Suchradius", anchor="w").pack(fill="x")
        self.ki_umkreis = ctk.CTkComboBox(
            ki_radiusfeld,
            values=["10 km", "20 km", "30 km", "50 km", "100 km"],
            height=38,
        )
        self.ki_umkreis.pack(fill="x", pady=(4, 0))
        self.ki_umkreis.set(self._umkreis_anzeige(self.settings.get("ki_umkreis", self.settings.get("umkreis", "30"))))

        ki_aktionen = ctk.CTkFrame(self.ki_such_panel, fg_color="transparent")
        ki_aktionen.grid(row=2, column=1, sticky="nsew", padx=(10, 18))
        self.ki_suchplan_button = ctk.CTkButton(
            ki_aktionen,
            text="Neue Vorschlaege erzeugen",
            command=self.ki_suchbegriffe_erzeugen,
            height=38,
        )
        self.ki_suchplan_button.pack(fill="x", pady=(0, 6))
        self.ki_jobsuche_start_button = ctk.CTkButton(
            ki_aktionen,
            text="Mit aktiven Begriffen suchen",
            command=self.ki_jobsuche_starten,
            height=38,
            font=("Segoe UI", 13, "bold"),
            fg_color=FARBE_ERFOLG,
            hover_color=("#11734E", "#1D8C64"),
        )
        self.ki_jobsuche_start_button.pack(fill="x")

        self.ki_provider_frame = ctk.CTkFrame(self.ki_such_panel, fg_color="transparent")
        self.ki_provider_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 10))
        self._ki_provider_checkboxes_erstellen()

        self.ki_bereichsumschalter = ctk.CTkSegmentedButton(
            self.ki_such_panel,
            values=["Suchbegriffe", "Ergebnisse"],
            variable=self.ki_suchbereich,
            command=self._ki_suchbereich_wechseln,
            height=36,
        )
        self.ki_bereichsumschalter.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 16))

        self.ki_kriterien_fenster = ctk.CTkToplevel(self.app)
        self.ki_kriterien_fenster.withdraw()
        self.ki_kriterien_fenster.title("Bewertungskriterien")
        self.ki_kriterien_fenster.geometry("1120x650")
        self.ki_kriterien_fenster.minsize(900, 590)
        self.ki_kriterien_fenster.transient(self.app)
        self.ki_kriterien_fenster.protocol("WM_DELETE_WINDOW", self._ki_kriterien_speichern_und_schliessen)
        self.ki_panel = ctk.CTkFrame(
            self.ki_kriterien_fenster,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.ki_panel.pack(fill="both", expand=True, padx=18, pady=18)
        self._ki_kriterien_erstellen(self.ki_panel)

        self.filter_frame = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.filter_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.filter_frame,
            text="Bewerbungen filtern",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=5, sticky="ew", padx=16, pady=(14, 10))

        self.bewerbung_status_auswahl = "Alle"
        self.bewerbung_status_tabs = ctk.CTkFrame(self.filter_frame, fg_color="transparent")
        self.bewerbung_status_tab_buttons = {}
        for index, status in enumerate(BEWERBUNGSSTATUS_TABS):
            self.bewerbung_status_tabs.grid_columnconfigure(index, weight=1, uniform="bewerbungsstatus")
            button = ctk.CTkButton(
                self.bewerbung_status_tabs,
                text=status,
                command=lambda status=status: self._bewerbungsstatus_tab_gewechselt(status),
                height=36,
                corner_radius=5,
                border_width=1,
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 2 if index < len(BEWERBUNGSSTATUS_TABS) - 1 else 0))
            self.bewerbung_status_tab_buttons[status] = button
        self.bewerbung_status_tabs.grid(row=1, column=0, columnspan=5, sticky="ew", padx=16, pady=(0, 10))

        self.bewerbung_suche = ctk.CTkEntry(
            self.filter_frame,
            placeholder_text="Titel, Firma oder Notiz durchsuchen",
            height=36,
        )
        self.bewerbung_suche.grid(row=2, column=0, sticky="ew", padx=(16, 6), pady=(0, 14))

        self.quellen_filter = ctk.CTkComboBox(self.filter_frame, values=["Alle"])
        self.quellen_filter.set("Alle")
        self.quellen_filter.grid(row=2, column=1, padx=6, pady=(0, 14))

        self.followup_filter = ctk.CTkComboBox(self.filter_frame, values=FOLLOWUP_FILTER)
        self.followup_filter.set("Alle")
        self.followup_filter.grid(row=2, column=2, padx=6, pady=(0, 14))

        self.sortierung = ctk.CTkComboBox(self.filter_frame, values=SORTIERUNGEN)
        self.sortierung.set("Letzte Statusaenderung")
        self.sortierung.grid(row=2, column=3, padx=6, pady=(0, 14))

        ctk.CTkButton(
            self.filter_frame,
            text="Anwenden",
            command=self.filter_anwenden,
            width=96,
            height=36,
        ).grid(row=2, column=4, padx=(6, 16), pady=(0, 14))

        self.status_panel = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.status = ctk.CTkLabel(
            self.status_panel,
            text="",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        )
        self.status.pack(fill="x", padx=16, pady=(10, 2))

        self.diagnose = ctk.CTkLabel(
            self.status_panel,
            text="",
            font=("Segoe UI", 11),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
            wraplength=930,
        )
        self.diagnose.pack(fill="x", padx=16, pady=2)

        self.ki_status = ctk.CTkLabel(
            self.status_panel,
            text="",
            font=("Segoe UI", 12),
            anchor="w",
            justify="left",
            wraplength=930,
        )
        self.ki_status.pack(fill="x", padx=16, pady=(2, 10))

        self.ki_button_suche = None

        self.suchstatus_panel = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
            height=52,
        )
        self.suchstatus_panel.grid_columnconfigure(0, weight=1)
        self.suchstatus_label = ctk.CTkLabel(
            self.suchstatus_panel,
            text="",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        self.suchstatus_label.grid(row=0, column=0, sticky="ew", padx=(16, 12), pady=9)
        self.ki_anzeigen_button = ctk.CTkButton(
            self.suchstatus_panel,
            text="Zur KI-Analyse",
            command=lambda: self.zur_ki_analyse("normal"),
            width=170,
            height=34,
            fg_color=FARBE_ERFOLG,
            hover_color=("#11734E", "#1D8C64"),
            text_color=("white", "white"),
        )
        self.ki_anzeigen_button.grid(row=0, column=1, padx=(0, 10), pady=9)

        self.treffer_sortierleiste = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color="transparent",
            corner_radius=0,
        )
        ctk.CTkLabel(
            self.treffer_sortierleiste,
            text="Sortieren nach",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(side="left")
        self.treffer_sortierung_combo = ctk.CTkComboBox(
            self.treffer_sortierleiste,
            values=TREFFER_SORTIERUNGEN,
            command=self._treffer_sortierung_geaendert,
            state="readonly",
            width=250,
            height=34,
        )
        self.treffer_sortierung_combo.pack(side="right")

        self.navigation = ctk.CTkFrame(self.arbeitsbereich, fg_color="transparent")

        self.zurueck_button = ctk.CTkButton(
            self.navigation,
            text="< Zurueck",
            command=self.vorherige_seite,
            width=110,
        )
        self.zurueck_button.pack(side="left")

        self.seiten_label = ctk.CTkLabel(self.navigation, text="Seite 1 / 1")
        self.seiten_label.pack(side="left", expand=True)

        self.weiter_button = ctk.CTkButton(
            self.navigation,
            text="Weiter >",
            command=self.naechste_seite,
            width=110,
        )
        self.weiter_button.pack(side="right")

        self.liste = ctk.CTkScrollableFrame(
            self.arbeitsbereich,
            fg_color="transparent",
            corner_radius=0,
        )
        self.liste.pack(fill="both", expand=True)

        self.undo_frame = ctk.CTkFrame(
            self.arbeitsbereich,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        self.undo_text = ctk.CTkLabel(self.undo_frame, text="Stelle entfernt")
        self.undo_text.pack(side="left", padx=(12, 8), pady=8)
        ctk.CTkButton(self.undo_frame, text="Rueckgaengig", command=self.entfernung_rueckgaengig, width=120).pack(
            side="left", pady=8
        )

        self.zeige_jobs()
        self.diagnose.configure(text=self.job_service.diagnose_meldung())
        self.app.protocol("WM_DELETE_WINDOW", self.beenden)
        if not self.settings.get("einleitung_abgeschlossen", False):
            self.app.after(400, self._einleitung_oeffnen)

    def _branding_laden(self):
        try:
            if APP_LOGO_DATEI.exists():
                with Image.open(APP_LOGO_DATEI) as logo:
                    self.branding_bild = logo.convert("RGBA")
                self.fenster_icon_bild = ImageTk.PhotoImage(
                    self.branding_bild.resize((64, 64), Image.Resampling.LANCZOS)
                )
                self.app.iconphoto(True, self.fenster_icon_bild)
            if APP_ICON_DATEI.exists():
                self.app.iconbitmap(default=str(APP_ICON_DATEI))
        except Exception:
            logging.warning("App-Branding konnte nicht vollstaendig geladen werden.", exc_info=True)

    def _seitenleiste_erstellen(self):
        self.seitenleiste = ctk.CTkFrame(
            self.app,
            width=220,
            fg_color=FARBE_SEITENLEISTE,
            corner_radius=0,
        )
        self.seitenleiste.grid(row=0, column=0, sticky="nsew")
        self.seitenleiste.grid_propagate(False)
        self.seitenleiste.grid_rowconfigure(9, weight=1)

        marke = ctk.CTkFrame(self.seitenleiste, fg_color="transparent", corner_radius=0)
        marke.grid(row=0, column=0, rowspan=2, sticky="ew", padx=18, pady=(20, 18))
        marke.grid_columnconfigure(1, weight=1)

        text_spalte = 0
        if self.branding_bild is not None:
            self.seitenleisten_logo_bild = ctk.CTkImage(
                light_image=self.branding_bild,
                dark_image=self.branding_bild,
                size=(56, 56),
            )
            ctk.CTkLabel(
                marke,
                text="",
                image=self.seitenleisten_logo_bild,
                width=56,
                height=56,
            ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
            text_spalte = 1

        ctk.CTkLabel(
            marke,
            text="JobScout AI",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=text_spalte, sticky="sew", pady=(2, 1))
        ctk.CTkLabel(
            marke,
            text="Intelligente Jobsuche",
            font=("Segoe UI", 10),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).grid(row=1, column=text_spalte, sticky="new", pady=(1, 2))

        navigation = [
            ("dashboard", "Dashboard", self.zeige_dashboard),
            ("suche", "Jobs suchen", self.zeige_suchergebnisse),
            ("ki_suche", "KI-Jobsuche", self.zeige_ki_jobsuche),
            ("bewerbungen", "Bewerbungen", self.zeige_bewerbungen),
            ("ki", "KI-Analyse", self.zeige_ki_zusammenfassung),
            ("profil", "Nutzerprofil", self.zeige_nutzerprofil),
            ("einstellungen", "Einstellungen", self.zeige_einstellungen),
        ]
        for zeile, (name, text, befehl) in enumerate(navigation, start=2):
            button = ctk.CTkButton(
                self.seitenleiste,
                text=text,
                command=befehl,
                anchor="w",
                height=40,
                corner_radius=7,
                fg_color="transparent",
                hover_color=FARBE_KARTE_ZWEI,
                text_color=("gray15", "gray90"),
                font=("Segoe UI", 13),
            )
            button.grid(row=zeile, column=0, sticky="ew", padx=12, pady=3)
            self.nav_buttons[name] = button

        ctk.CTkLabel(
            self.seitenleiste,
            text="Lokale Verarbeitung aktiv",
            font=("Segoe UI", 11),
            text_color=FARBE_ERFOLG,
            anchor="w",
        ).grid(row=10, column=0, sticky="sew", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            self.seitenleiste,
            text=f"Version {VERSION}",
            font=("Segoe UI", 10),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).grid(row=11, column=0, sticky="ew", padx=20, pady=(0, 20))

    def _kopfzeile_erstellen(self):
        kopf = ctk.CTkFrame(self.hauptbereich, fg_color="transparent", corner_radius=0)
        kopf.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 14))
        kopf.grid_columnconfigure(0, weight=1)

        self.seiten_titel = ctk.CTkLabel(
            kopf,
            text="Dashboard",
            font=("Segoe UI", 26, "bold"),
            anchor="w",
        )
        self.seiten_titel.grid(row=0, column=0, sticky="ew")
        self.seiten_untertitel = ctk.CTkLabel(
            kopf,
            text="Aktueller Stand Ihrer Jobsuche",
            font=("Segoe UI", 12),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        )
        self.seiten_untertitel.grid(row=1, column=0, sticky="ew", pady=(2, 0))

    def _ansicht_layout_aktualisieren(self):
        self.liste.cancel_pending_scroll()
        for panel in (
            self.such_panel,
            self.ki_such_panel,
            self.filter_frame,
            self.status_panel,
            self.suchstatus_panel,
            self.treffer_sortierleiste,
            self.navigation,
        ):
            panel.pack_forget()
        self.liste.pack_forget()

        titel = {
            "dashboard": ("Dashboard", "Aktueller Stand Ihrer Jobsuche"),
            "suche": ("Jobs suchen", "Neue Stellen finden und Ergebnisse vergleichen"),
            "ki_suche": ("KI-Jobsuche", "Suchbegriffe lokal planen und automatisch suchen"),
            "bewerbungen": ("Bewerbungen", "Gespeicherte Stellen und naechste Schritte"),
            "ki": ("KI-Analyse", "Treffer nach Ihren persoenlichen Kriterien bewerten"),
            "profil": ("Nutzerprofil", "Lebenslauf, Staerken und Suchpraeferenzen fuer die lokale KI"),
            "einstellungen": ("Einstellungen", "Darstellung und lokale Komponenten"),
        }
        seitentitel, untertitel = titel.get(self.ansicht, titel["dashboard"])
        self.seiten_titel.configure(text=seitentitel)
        self.seiten_untertitel.configure(text=untertitel)

        if self.ansicht == "suche":
            self.such_panel.pack(fill="x", pady=(0, 12))
        elif self.ansicht == "ki_suche":
            self.ki_such_panel.pack(fill="x", pady=(0, 12))
        elif self.ansicht == "bewerbungen":
            self.filter_frame.pack(fill="x", pady=(0, 12))

        ki_ergebnisse = self.ansicht == "ki_suche" and self.ki_suchbereich.get() == "Ergebnisse"
        if self.ansicht in ("suche", "ki_suche"):
            self._suchstatusleiste_aktualisieren()
            self.suchstatus_panel.pack(fill="x", pady=(0, 10))
        elif self.ansicht == "bewerbungen":
            self.status_panel.pack(fill="x", pady=(0, 10))
        if (
            (self.ansicht == "suche" and self.normale_suchergebnisse)
            or self.ansicht == "bewerbungen"
            or (ki_ergebnisse and self.ki_suchergebnisse)
        ):
            if self.ansicht in ("suche", "ki_suche"):
                self._treffer_sortierleiste_aktualisieren()
                self.treffer_sortierleiste.pack(fill="x", pady=(0, 8))
            self.navigation.pack(fill="x", pady=(0, 8))
        self.liste.pack(fill="both", expand=True)

        for name, button in self.nav_buttons.items():
            aktiv = name == self.ansicht
            button.configure(
                fg_color=FARBE_PRIMAER if aktiv else "transparent",
                text_color=FARBE_PRIMAER_TEXT if aktiv else ("gray15", "gray90"),
            )

    def suchen(self):
        if self.suche_laeuft or self.ki_laeuft or self.ki_jobsuche_laeuft:
            return
        try:
            self.status.configure(text="Suche laeuft...")
            self.normaler_suchmeldung = "Jobsuche laeuft..."
            suchanfrage = self._basis_suchanfrage()
            self.letzter_suchkontext = suchanfrage
            abbruch_event = threading.Event()
            self.normaler_such_abbruch = abbruch_event
            self.suche_laeuft = True
            self._normaler_suchbutton_status_aktualisieren()
            self.diagnose.configure(text="Provider-Suche laeuft im Hintergrund. KI-Auswertung startet erst auf Wunsch.")
            self.ki_status.configure(text="KI-Zusammenfassung noch nicht gestartet.")
            self._ki_button_status_aktualisieren()
            threading.Thread(
                target=self._suche_im_hintergrund,
                args=(suchanfrage, abbruch_event),
                daemon=True,
            ).start()
        except Exception as fehler:
            logging.exception("Fehler bei der Jobsuche")
            self.normaler_suchmeldung = f"Fehler bei der Suche: {fehler}"
            self.status.configure(text=self.normaler_suchmeldung)
            self._such_button_freigeben()

    def _suche_im_hintergrund(self, suchanfrage, abbruch_event):
        try:
            jobs = self.job_service.search_jobs(suchanfrage, abbruch_event=abbruch_event)
            self._gui_ausfuehren(lambda: self._suche_abgeschlossen(jobs, suchanfrage, abbruch_event))
        except OperationCancelled:
            logging.info("Jobsuche wurde abgebrochen.")
            self._gui_ausfuehren(lambda: self._suche_abbruch_abgeschlossen(abbruch_event))
        except Exception as fehler:
            if abbruch_event.is_set():
                logging.info("Jobsuche wurde waehrend einer Provider-Antwort abgebrochen.")
                self._gui_ausfuehren(lambda: self._suche_abbruch_abgeschlossen(abbruch_event))
                return
            logging.exception("Fehler bei der Jobsuche")
            self._gui_ausfuehren(lambda fehler=fehler: self._suche_fehlgeschlagen(fehler, abbruch_event))

    def _suche_abgeschlossen(self, jobs, suchanfrage, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("normaler_such_abbruch", abbruch_event):
            return
        self.normaler_such_abbruch = None
        self.jobs = jobs
        self.normale_suchergebnisse = list(jobs)
        self.analyse_jobs = []
        self._ki_daten_der_aktuellen_suche_loeschen()
        self.ki_kriterien_snapshot = None
        self.ki_zusammenfassung_veraltet = False
        self.ki_jobsuche_begriffe = []
        self.ki_jobsuche_widgets = []
        self.letzter_suchkontext = suchanfrage
        self.normaler_suchkontext = suchanfrage
        self.aktuelle_ergebnisquelle = "normal"
        self.analyse_normale_jobs.set(bool(jobs))
        self.analyse_ki_jobs.set(False)
        self.analyse_hinweis = ""
        self.normaler_suchmeldung = ""
        self.ansicht = "suche"
        self.aktuelle_seite = 0
        self._ansichts_zustand_zuruecksetzen("suche")
        self.zeige_jobs()
        self.status.configure(text=self.job_service.status_meldung())
        self.diagnose.configure(text=self.job_service.diagnose_meldung())
        self.ki_status.configure(text=self._ki_zusammenfassung_text())
        self._such_button_freigeben()
        self._ki_button_status_aktualisieren()

    def _suche_fehlgeschlagen(self, fehler, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("normaler_such_abbruch", abbruch_event):
            return
        self.normaler_such_abbruch = None
        self.normaler_suchmeldung = f"Fehler bei der Suche: {fehler}"
        self.status.configure(text=self.normaler_suchmeldung)
        self._such_button_freigeben()

    def _such_button_freigeben(self):
        self.suche_laeuft = False
        self.normaler_such_abbruch = None
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()

    def normale_suche_abbrechen(self):
        abbruch_event = self.normaler_such_abbruch
        if not self.suche_laeuft or self.ki_jobsuche_laeuft or abbruch_event is None:
            return
        abbruch_event.set()
        self.normaler_suchmeldung = "Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten."
        self.status.configure(text=self.normaler_suchmeldung)
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        self._suchstatusleiste_aktualisieren()

    def _suche_abbruch_abgeschlossen(self, abbruch_event):
        if self.normaler_such_abbruch is not abbruch_event:
            return
        self.normaler_such_abbruch = None
        self.suche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        self._suchstatusleiste_aktualisieren()

    def _normaler_suchbutton_status_aktualisieren(self):
        button = getattr(self, "such_button", None)
        if not self._widget_existiert(button):
            return
        if self.suche_laeuft and not self.ki_jobsuche_laeuft:
            if self._abbruch_angefordert("normaler_such_abbruch"):
                button.configure(
                    state="disabled",
                    text="Suche wird beendet...",
                    command=self.normale_suche_abbrechen,
                    fg_color=FARBE_FEHLER,
                    hover_color=("#A72F40", "#C94A5A"),
                )
                return
            button.configure(
                state="normal",
                text="Suche abbrechen",
                command=self.normale_suche_abbrechen,
                fg_color=FARBE_FEHLER,
                hover_color=("#A72F40", "#C94A5A"),
            )
            return
        if self.ki_laeuft:
            text = "Analyse abwarten"
        elif self.ki_jobsuche_laeuft:
            text = "KI-Jobsuche abwarten"
        else:
            button.configure(
                state="normal",
                text="Jobs suchen",
                command=self.suchen,
                fg_color=FARBE_PRIMAER,
                hover_color=FARBE_PRIMAER_HOVER,
            )
            return
        button.configure(
            state="disabled",
            text=text,
            command=self.suchen,
            fg_color=FARBE_PRIMAER,
            hover_color=FARBE_PRIMAER_HOVER,
        )

    def _suchstatusleiste_aktualisieren(self):
        label = getattr(self, "suchstatus_label", None)
        button = getattr(self, "ki_anzeigen_button", None)
        if not self._widget_existiert(label) or not self._widget_existiert(button):
            return

        text, quelle, hat_treffer = suchstatus_daten(
            self.ansicht,
            len(self.normale_suchergebnisse),
            len(self.ki_suchergebnisse),
            self.suche_laeuft
            and not self.ki_jobsuche_laeuft
            and not self._abbruch_angefordert("normaler_such_abbruch"),
            self.ki_jobsuche_laeuft and not self._abbruch_angefordert("ki_jobsuche_abbruch"),
            self.normaler_suchmeldung,
            self.ki_jobsuche_meldung,
        )
        gesperrt = self.suche_laeuft or self.ki_laeuft or self.ki_jobsuche_laeuft
        label.configure(text=text)
        button.configure(
            state="normal" if hat_treffer and not gesperrt else "disabled",
            text="Zur KI-Analyse",
            command=lambda ausgang=quelle: self.zur_ki_analyse(ausgang),
            fg_color=FARBE_ERFOLG if hat_treffer and not gesperrt else FARBE_KARTE,
            hover_color=("#11734E", "#1D8C64") if hat_treffer and not gesperrt else FARBE_KARTE_ZWEI,
            border_width=0 if hat_treffer and not gesperrt else 1,
            border_color=FARBE_RAND,
            text_color=("white", "white") if hat_treffer and not gesperrt else ("gray45", "gray60"),
        )

    def ki_zusammenfassung_aktualisieren(self):
        if self.ki_laeuft or self.suche_laeuft or self.ki_jobsuche_laeuft:
            return
        jobs = self._ausgewaehlte_analyse_jobs()
        if not jobs:
            if self.normale_suchergebnisse or self.ki_suchergebnisse:
                self.analyse_hinweis = "Bitte mindestens eine Trefferquelle fuer die Analyse auswaehlen."
            else:
                self.analyse_hinweis = "Es liegen noch keine Treffer fuer eine KI-Analyse vor."
            self.ki_status.configure(text=self.analyse_hinweis)
            self.zeige_ki_zusammenfassung()
            return

        if self.analyse_mit_nutzerprofil.get():
            profil_name = self._analyseprofil_name()
            profil = self._nutzerprofil()
            if not profil_name or not any(str(wert or "").strip() for wert in profil.values()):
                self.analyse_hinweis = "Bitte ein ausgefuelltes Nutzerprofil auswaehlen oder die Profilnutzung deaktivieren."
                self.ki_status.configure(text=self.analyse_hinweis)
                self.zeige_ki_zusammenfassung()
                return

        suchanfrage = self._analyse_suchanfrage()
        abbruch_event = threading.Event()
        self.ki_analyse_abbruch = abbruch_event
        self.ki_analyse_zustand_snapshot = self.job_service.ki_analysezustand_sichern()
        self.ki_laeuft = True
        self.ki_zusammenfassung_veraltet = False
        self.analyse_hinweis = "Die lokale KI analysiert die ausgewaehlten Treffer."
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        self.ki_status.configure(text="KI-Analyse laeuft mit den aktuellen Kriterien...")
        self.diagnose.configure(text=self.job_service.diagnose_meldung())
        if self.ansicht == "ki":
            self.zeige_jobs()
        threading.Thread(
            target=self._ki_analyse_im_hintergrund,
            args=(deepcopy(jobs), suchanfrage, abbruch_event),
            daemon=True,
        ).start()

    def _ki_analyse_im_hintergrund(self, jobs, suchanfrage, abbruch_event):
        try:
            self._lokale_ki_bereitstellen()
            analysierte_jobs = self.job_service.ki_analyse_ausfuehren(
                jobs,
                suchanfrage,
                abbruch_event=abbruch_event,
            )
            self._gui_ausfuehren(
                lambda: self._ki_analyse_abgeschlossen(
                    analysierte_jobs,
                    suchanfrage.ki_kriterien,
                    abbruch_event,
                )
            )
        except OperationCancelled:
            logging.info("KI-Analyse wurde abgebrochen.")
            self._gui_ausfuehren(lambda: self._ki_analyse_abbruch_abgeschlossen(abbruch_event))
        except Exception as fehler:
            if abbruch_event.is_set():
                logging.info("KI-Analyse wurde waehrend einer Modellantwort abgebrochen.")
                self._gui_ausfuehren(lambda: self._ki_analyse_abbruch_abgeschlossen(abbruch_event))
                return
            logging.exception("Fehler bei der KI-Auswertung")
            self._gui_ausfuehren(lambda fehler=fehler: self._ki_analyse_fehlgeschlagen(fehler, abbruch_event))

    def _ki_analyse_abgeschlossen(self, jobs, kriterien, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("ki_analyse_abbruch", abbruch_event):
            return
        self.ki_analyse_abbruch = None
        self.ki_analyse_zustand_snapshot = None
        self.analyse_jobs = list(jobs)
        self._ki_analysedaten_synchronisieren(self.analyse_jobs)
        self.ki_laeuft = False
        self.ki_jobsuche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self.ki_kriterien_snapshot = dict(kriterien or {})
        self.analyse_quellen_snapshot = self._aktive_analyse_quellen()
        self.analyse_profil_snapshot = (
            self._analyseprofil_name() if self.analyse_mit_nutzerprofil.get() else ""
        )
        self.ki_zusammenfassung_veraltet = self._analyse_einstellungen_geaendert()
        bewertete = sum(1 for job in self.analyse_jobs if job.hat_ki_daten())
        self.analyse_hinweis = f"Analyse abgeschlossen: {bewertete} Top-Kandidaten wurden bewertet."
        self.status.configure(text=self.analyse_hinweis)
        self.diagnose.configure(text=self.job_service.diagnose_meldung())
        self.ki_status.configure(text=self._ki_zusammenfassung_text())
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki":
            self.zeige_ki_zusammenfassung()
        else:
            self.zeige_jobs()

    def _ki_analyse_fehlgeschlagen(self, fehler, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("ki_analyse_abbruch", abbruch_event):
            return
        self.ki_analyse_abbruch = None
        self.ki_analyse_zustand_snapshot = None
        self.ki_laeuft = False
        self.ki_jobsuche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self.analyse_hinweis = f"Fehler bei der KI-Auswertung: {fehler}"
        self.ki_status.configure(text=self.analyse_hinweis)
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki":
            self.zeige_jobs()

    def ki_analyse_abbrechen(self):
        abbruch_event = self.ki_analyse_abbruch
        if not self.ki_laeuft or abbruch_event is None or abbruch_event.is_set():
            return
        abbruch_event.set()
        self.job_service.ki_analyse_abbrechen()
        self.job_service.ki_analysezustand_wiederherstellen(self.ki_analyse_zustand_snapshot)
        self.analyse_hinweis = "KI-Analyse abgebrochen. Die letzte abgeschlossene Auswertung bleibt erhalten."
        self.status.configure(text=self.analyse_hinweis)
        self.ki_status.configure(text=self.analyse_hinweis)
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki":
            self.zeige_jobs()

    def _ki_analyse_abbruch_abgeschlossen(self, abbruch_event):
        if self.ki_analyse_abbruch is not abbruch_event:
            return
        self.job_service.ki_analysezustand_wiederherstellen(self.ki_analyse_zustand_snapshot)
        self.ki_analyse_abbruch = None
        self.ki_analyse_zustand_snapshot = None
        self.ki_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki":
            self.zeige_jobs()

    def _ki_analysedaten_synchronisieren(self, analysierte_jobs):
        nach_schluessel = {job_schluessel(job): job for job in analysierte_jobs}
        for sammlung in (self.jobs, self.normale_suchergebnisse, self.ki_suchergebnisse):
            for job in sammlung:
                analysierter_job = nach_schluessel.get(job_schluessel(job))
                if analysierter_job is not None:
                    job.ki_daten_aus(analysierter_job)

    def _ki_daten_der_aktuellen_suche_loeschen(self, jobs=None):
        for job in self.jobs if jobs is None else jobs:
            job.ki_daten_loeschen()

    def _gui_ausfuehren(self, funktion):
        if self.wird_beendet:
            return
        try:
            self.app.after(0, funktion)
        except Exception:
            logging.debug("GUI-Callback konnte nicht mehr geplant werden.", exc_info=True)

    def _abbruch_angefordert(self, attribut):
        abbruch_event = getattr(self, attribut, None)
        return abbruch_event is not None and abbruch_event.is_set()

    def _abbruchlauf_ist_aktuell(self, attribut, abbruch_event):
        if abbruch_event is None:
            return True
        return getattr(self, attribut, None) is abbruch_event and not abbruch_event.is_set()

    def zeige_jobs(self):
        self.einleitung_ziele = {}
        self._beschreibungs_widgets = {}
        self._ansicht_layout_aktualisieren()
        if self.ansicht == "bewerbungen":
            self._quellen_filter_aktualisieren()
        if self.ansicht != "ki_suche":
            self.ki_suchbegriff_hinzufuegen_button = None
            self.ki_neuer_suchbegriff = None
            self.ki_jobsuche_widgets = []
            self.ki_suchbegriff_pool_widgets = {}
        for element in self.liste.winfo_children():
            element.destroy()

        if self.ansicht == "dashboard":
            self._zeige_dashboard()
            return
        if self.ansicht == "einstellungen":
            self._zeige_einstellungen()
            return
        if self.ansicht == "profil":
            self._zeige_nutzerprofil()
            return
        if self.ansicht == "ki_suche":
            self._zeige_ki_jobsuche()
            return
        if self.ansicht == "bewerbungen":
            self._zeige_bewerbungsgruppen()
            return
        if self.ansicht == "ki":
            self._zeige_ki_zusammenfassung()
            return

        jobs = self._aktuelle_jobs()
        if not jobs:
            self._navigation_aktualisieren(0)
            self._suchstatusleiste_aktualisieren()
            return

        gesamt = len(jobs)
        self._navigation_aktualisieren(gesamt)
        self._suchstatusleiste_aktualisieren()

        for job in self._jobs_der_seite(jobs):
            self._job_karte(job, kompakt=True)

    def _zeige_ki_jobsuche(self):
        self.ki_jobsuche_widgets = []
        self.ki_suchbegriff_pool_widgets = {}
        if self.ki_suchbereich.get() == "Ergebnisse":
            self._zeige_ki_jobsuche_ergebnisse()
            return

        self.status.configure(text=self.ki_jobsuche_meldung)
        self.diagnose.configure(
            text="Suchvorschlaege und Provider-Suche verwenden ausschliesslich Ort, Radius und Quellen dieser Seite."
        )
        self.ki_status.configure(text="Die Treffer werden erst im Bereich KI-Analyse bewertet.")
        self._navigation_aktualisieren(0)

        gespeicherte_begriffe = self.job_service.suchbegriffe_laden()
        spalten = ctk.CTkFrame(self.liste, fg_color="transparent")
        spalten.pack(fill="both", expand=True, padx=2, pady=(4, 2))
        spalten.grid_columnconfigure(0, weight=3)
        spalten.grid_columnconfigure(1, weight=2)

        gespeicherte_spalte = ctk.CTkFrame(spalten, fg_color="transparent")
        gespeicherte_spalte.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        vorschlaege_spalte = ctk.CTkFrame(spalten, fg_color="transparent")
        vorschlaege_spalte.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.einleitung_ziele.update(begriffe=gespeicherte_spalte, vorschlaege=vorschlaege_spalte)

        self._suchbegriff_set_leiste_anzeigen(gespeicherte_spalte, gespeicherte_begriffe)
        if not gespeicherte_begriffe:
            leer = ctk.CTkFrame(gespeicherte_spalte, fg_color=FARBE_KARTE, border_width=1, border_color=FARBE_RAND, corner_radius=8)
            leer.pack(fill="x", padx=6, pady=6)
            ctk.CTkLabel(
                leer,
                text="Noch keine Suchbegriffe gespeichert.",
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
            ).pack(fill="x", padx=16, pady=16)
        else:
            for begriff in gespeicherte_begriffe:
                self._gespeicherten_suchbegriff_anzeigen(gespeicherte_spalte, begriff)

        aktionen = ctk.CTkFrame(gespeicherte_spalte, fg_color="transparent")
        aktionen.pack(fill="x", padx=6, pady=(8, 2))
        self.ki_neuer_suchbegriff = ctk.CTkEntry(
            aktionen,
            placeholder_text="Berufs- oder Taetigkeitsbezeichnung",
            height=36,
        )
        self.ki_neuer_suchbegriff.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ki_suchbegriff_hinzufuegen_button = ctk.CTkButton(
            aktionen,
            text="Begriff hinzufuegen",
            command=self._ki_suchbegriff_hinzufuegen,
            width=170,
        )
        self.ki_suchbegriff_hinzufuegen_button.pack(side="left")

        vorschlag_kopf = ctk.CTkFrame(vorschlaege_spalte, fg_color="transparent")
        vorschlag_kopf.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            vorschlag_kopf,
            text="Neue KI-Vorschlaege",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            vorschlag_kopf,
            text=f"{len(self.ki_jobsuche_begriffe or [])} offen",
            text_color=FARBE_TEXT_SEKUNDAER,
        ).pack(side="right")

        vorschlaege = self.ki_jobsuche_begriffe or []
        if not vorschlaege:
            leer = ctk.CTkFrame(vorschlaege_spalte, fg_color=FARBE_KARTE, border_width=1, border_color=FARBE_RAND, corner_radius=8)
            leer.pack(fill="x", padx=6, pady=6)
            ctk.CTkLabel(
                leer,
                text=(self.ki_jobsuche_meldung if self.ki_jobsuche_meldung != "KI-Jobsuche bereit. Suchbegriffe verwalten oder einen Suchlauf starten."
                      else "Noch keine neuen Vorschlaege erzeugt.\nGespeicherte Begriffe bleiben dabei unveraendert."),
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=16, pady=16)
        else:
            for index, vorschlag in enumerate(vorschlaege):
                self._ki_vorschlag_anzeigen(vorschlaege_spalte, index, vorschlag)
            vorschlag_aktionen = ctk.CTkFrame(vorschlaege_spalte, fg_color="transparent")
            vorschlag_aktionen.pack(fill="x", padx=6, pady=(8, 2))
            ctk.CTkButton(
                vorschlag_aktionen,
                text="Alle uebernehmen",
                command=self._ki_vorschlaege_alle_uebernehmen,
                width=150,
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                vorschlag_aktionen,
                text="Alle verwerfen",
                command=self._ki_vorschlaege_alle_verwerfen,
                width=135,
                fg_color=FARBE_KARTE_ZWEI,
                border_width=1,
                border_color=FARBE_RAND,
                text_color=("gray15", "gray90"),
                hover_color=FARBE_KARTE,
            ).pack(side="left")

        if self.ki_suchergebnisse:
            analyse_weiter = ctk.CTkFrame(
                self.liste,
                fg_color=FARBE_KARTE_ZWEI,
                border_width=1,
                border_color=FARBE_RAND,
                corner_radius=8,
            )
            analyse_weiter.pack(fill="x", padx=6, pady=(10, 2))
            ctk.CTkLabel(
                analyse_weiter,
                text=f"{len(self.ki_suchergebnisse)} Treffer aus dem letzten KI-Suchlauf",
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=14, pady=12)
            ctk.CTkButton(
                analyse_weiter,
                text="Ergebnisse anzeigen",
                command=lambda: self._ki_suchbereich_wechseln("Ergebnisse"),
                width=160,
            ).pack(side="right", padx=12, pady=10)

        self._ki_jobsuche_button_status_aktualisieren()

    def _suchbegriff_set_leiste_anzeigen(self, parent, gespeicherte_begriffe):
        kopf = ctk.CTkFrame(parent, fg_color="transparent")
        kopf.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            kopf,
            text="Gespeicherte Suchbegriffe",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        aktive_anzahl = sum(begriff.status == "aktiv" for begriff in gespeicherte_begriffe)
        ctk.CTkLabel(
            kopf,
            text=f"{aktive_anzahl} aktiv | {len(gespeicherte_begriffe)} gesamt",
            text_color=FARBE_TEXT_SEKUNDAER,
        ).pack(side="right")

        leiste = ctk.CTkFrame(parent, fg_color="transparent")
        leiste.pack(fill="x", padx=6, pady=(0, 8))
        set_namen = [eintrag.name for eintrag in self.job_service.suchbegriff_sets_laden()]
        aktuelle_auswahl = self.ki_suchbegriff_set_auswahl.get()
        if aktuelle_auswahl not in set_namen:
            self.ki_suchbegriff_set_auswahl.set(set_namen[0] if set_namen else "Keine Sets gespeichert")
        self.ki_suchbegriff_set_combo = ctk.CTkComboBox(
            leiste,
            values=set_namen or ["Keine Sets gespeichert"],
            variable=self.ki_suchbegriff_set_auswahl,
            state="readonly" if set_namen else "disabled",
            height=36,
        )
        self.ki_suchbegriff_set_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ki_suchbegriff_set_laden_button = ctk.CTkButton(
            leiste,
            text="Laden",
            command=self._ki_suchbegriff_set_laden,
            width=90,
            height=36,
            state="normal" if set_namen else "disabled",
        )
        self.ki_suchbegriff_set_laden_button.pack(side="left", padx=4)
        self.ki_suchbegriff_set_speichern_button = ctk.CTkButton(
            leiste,
            text="Speichern unter",
            command=self._ki_suchbegriff_set_speichern_unter,
            width=145,
            height=36,
            state="normal" if gespeicherte_begriffe else "disabled",
            fg_color=FARBE_ERFOLG,
            hover_color=("#11734E", "#1D8C64"),
        )
        self.ki_suchbegriff_set_speichern_button.pack(side="left", padx=4)
        self.ki_suchbegriff_set_loeschen_button = ctk.CTkButton(
            leiste,
            text="Set loeschen",
            command=self._ki_suchbegriff_set_loeschen,
            width=110,
            height=36,
            state="normal" if set_namen else "disabled",
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_KARTE,
        )
        self.ki_suchbegriff_set_loeschen_button.pack(side="left", padx=(4, 0))

    def _zeige_ki_jobsuche_ergebnisse(self):
        jobs = self._aktuelle_jobs()
        gesamt = len(jobs)
        self.aktuelle_ergebnisquelle = "ki"
        self.status.configure(
            text=f"{gesamt} Jobs aus der KI-Jobsuche" if jobs else "Noch keine Ergebnisse aus der KI-Jobsuche."
        )
        self.diagnose.configure(
            text=self.job_service.diagnose_meldung()
            if self.ki_suchkontext is not None
            else "Noch kein KI-Suchlauf ausgefuehrt."
        )
        self.ki_status.configure(
            text="Treffer bereit fuer die KI-Analyse." if jobs else "Starten Sie zuerst einen Suchlauf mit aktiven Begriffen."
        )
        self._navigation_aktualisieren(gesamt)

        kontext = self.ki_suchkontext or self._ki_basis_suchanfrage()
        kopf = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        kopf.pack(fill="x", padx=6, pady=(0, 8))
        ctk.CTkLabel(
            kopf,
            text="Ergebnisse der KI-Jobsuche",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 2))
        provider_text = self._provider_anzeigenamen(kontext.provider)
        ctk.CTkLabel(
            kopf,
            text=f"{kontext.ort or 'Ohne Ortsangabe'} | {kontext.umkreis} km | Quellen: {provider_text}",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            wraplength=920,
        ).pack(fill="x", padx=16, pady=(0, 14))

        if not jobs:
            ctk.CTkLabel(
                self.liste,
                text="Im letzten KI-Suchlauf wurden keine Stellen gefunden.",
                text_color=FARBE_TEXT_SEKUNDAER,
            ).pack(pady=(24, 8))
            ctk.CTkButton(
                self.liste,
                text="Suchbegriffe verwalten",
                command=lambda: self._ki_suchbereich_wechseln("Suchbegriffe"),
                width=180,
            ).pack()
            return

        for job in self._jobs_der_seite(jobs):
            self._job_karte(job, kompakt=True)

    def _ki_suchbereich_wechseln(self, bereich):
        self.ki_suchbereich.set(bereich)
        self.aktuelle_seite = 0
        if self.ansicht == "ki_suche":
            self.zeige_jobs()
            scrollbare_liste_nach_oben(self.liste)

    def _gespeicherten_suchbegriff_anzeigen(self, parent, begriff):
        zeile = ctk.CTkFrame(parent, fg_color=FARBE_KARTE, border_width=1, border_color=FARBE_RAND, corner_radius=8)
        zeile.pack(fill="x", padx=6, pady=4)
        zeile.grid_columnconfigure(0, weight=1)
        feld = ctk.CTkEntry(zeile, height=36)
        feld.insert(0, begriff.bezeichnung)
        feld.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=(10, 4))
        self.ki_suchbegriff_pool_widgets[begriff.id] = feld
        ctk.CTkLabel(
            zeile,
            text=begriff.quelle,
            text_color=FARBE_TEXT_SEKUNDAER,
            width=70,
        ).grid(row=0, column=1, padx=4, pady=(10, 4))
        ctk.CTkButton(
            zeile,
            text="Speichern",
            command=lambda: self._ki_suchbegriff_bearbeiten(begriff.id, feld),
            width=90,
            height=34,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_KARTE,
        ).grid(row=0, column=2, padx=4, pady=(10, 4))
        status_variable = ctk.StringVar(value=begriff.status)
        ctk.CTkSwitch(
            zeile,
            text="Aktiv" if begriff.status == "aktiv" else "Pausiert",
            variable=status_variable,
            onvalue="aktiv",
            offvalue="pausiert",
            command=lambda suchbegriff_id=begriff.id, variable=status_variable: (
                self._ki_suchbegriff_status_vom_switch(suchbegriff_id, variable.get())
            ),
            width=130,
            switch_width=48,
            switch_height=24,
            button_length=0,
            border_width=2,
            border_color=FARBE_ERFOLG if begriff.status == "aktiv" else FARBE_FEHLER,
            fg_color=FARBE_FEHLER,
            progress_color=FARBE_ERFOLG,
            button_color=("#FFFFFF", "#F1F5F9"),
            button_hover_color=("#E8EEF4", "#D7E0E8"),
            text_color=FARBE_ERFOLG if begriff.status == "aktiv" else FARBE_FEHLER,
        ).grid(row=0, column=3, padx=(10, 4), pady=(10, 4))
        ctk.CTkButton(
            zeile,
            text="Loeschen",
            command=lambda: self._ki_suchbegriff_loeschen(begriff.id),
            width=80,
            height=34,
            fg_color=FARBE_FEHLER,
            hover_color=("#A62F40", "#C94758"),
        ).grid(row=0, column=4, padx=(4, 12), pady=(10, 4))
        letzte_suche = begriff.letzte_suche or "noch nie"
        metadaten = (
            f"Treffer: {begriff.treffer_anzahl} | KI-bewertet: {begriff.ki_bewertet_anzahl} | "
            f"Gut ab {GOOD_MATCH_SCORE_THRESHOLD}: {begriff.gute_treffer_anzahl} | "
            f"Durchschnitt: {begriff.durchschnitt_score}/100 | Bester: {begriff.bester_score}/100 | "
            f"Letzte Suche: {letzte_suche}"
        )
        hinweis = self.job_service.suchbegriff_behalten_hinweis(begriff)
        if hinweis:
            metadaten += f" | {hinweis}"
        ctk.CTkLabel(
            zeile,
            text=metadaten,
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
            wraplength=980,
        ).grid(row=1, column=0, columnspan=5, sticky="ew", padx=12, pady=(2, 10))

    def _ki_vorschlag_anzeigen(self, parent, index, vorschlag):
        zeile = ctk.CTkFrame(parent, fg_color=FARBE_KARTE, border_width=1, border_color=FARBE_RAND, corner_radius=8)
        zeile.pack(fill="x", padx=6, pady=4)
        zeile.grid_columnconfigure(0, weight=1)
        feld = ctk.CTkEntry(zeile, height=36)
        feld.insert(0, vorschlag)
        feld.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=10)
        feld.bind("<KeyRelease>", lambda _event: self._ki_jobsuche_begriff_geaendert(index, feld.get()))
        self.ki_jobsuche_widgets.append(feld)
        ctk.CTkButton(
            zeile,
            text="Uebernehmen",
            command=lambda: self._ki_vorschlag_uebernehmen(index),
            width=105,
            height=34,
        ).grid(row=0, column=1, padx=4, pady=10)
        ctk.CTkButton(
            zeile,
            text="Verwerfen",
            command=lambda: self._ki_vorschlag_verwerfen(index),
            width=90,
            height=34,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_KARTE,
        ).grid(row=0, column=2, padx=(4, 12), pady=10)

    def _basis_suchanfrage(self, mit_kriterien=False):
        return SearchRequest(
            self.such.get(),
            self.ort.get(),
            self._umkreis_wert(),
            self._ausgewaehlte_provider(),
            self._ki_kriterien() if mit_kriterien else {},
        )

    def _ki_basis_suchanfrage(self, mit_kriterien=False):
        return SearchRequest(
            "",
            self.ki_ort.get(),
            self._ki_umkreis_wert(),
            self._ausgewaehlte_ki_provider(),
            self._ki_kriterien() if mit_kriterien else {},
        )

    def _analyse_suchanfrage(self):
        kontexte = []
        if self.analyse_normale_jobs.get() and self.normaler_suchkontext is not None:
            kontexte.append(self.normaler_suchkontext)
        if self.analyse_ki_jobs.get() and self.ki_suchkontext is not None:
            kontexte.append(self.ki_suchkontext)
        basis = kontexte[-1] if kontexte else (self.letzter_suchkontext or self._basis_suchanfrage())
        suchbegriffe = []
        for kontext in kontexte or [basis]:
            wert = str(kontext.suchbegriff or "").strip()
            if wert and wert not in suchbegriffe:
                suchbegriffe.append(wert)
        kriterien = self._ki_kriterien()
        if not self.analyse_mit_nutzerprofil.get():
            kriterien.pop("nutzerprofil", None)
        return SearchRequest(
            " | ".join(suchbegriffe),
            basis.ort,
            basis.umkreis,
            basis.provider,
            kriterien,
        )

    def _aktive_analyse_quellen(self):
        quellen = set()
        if self.analyse_normale_jobs.get() and self.normale_suchergebnisse:
            quellen.add("normal")
        if self.analyse_ki_jobs.get() and self.ki_suchergebnisse:
            quellen.add("ki")
        return quellen

    def _ausgewaehlte_analyse_jobs(self):
        return analyse_treffer_auswaehlen(
            self.normale_suchergebnisse,
            self.ki_suchergebnisse,
            self.analyse_normale_jobs.get(),
            self.analyse_ki_jobs.get(),
        )

    def _analyse_einstellungen_geaendert(self):
        if self.ki_kriterien_snapshot is None:
            return False
        aktuelle_kriterien = self._ki_kriterien()
        if not self.analyse_mit_nutzerprofil.get():
            aktuelle_kriterien.pop("nutzerprofil", None)
        return (
            aktuelle_kriterien != self.ki_kriterien_snapshot
            or self._aktive_analyse_quellen() != self.analyse_quellen_snapshot
            or (
                self._analyseprofil_name() if self.analyse_mit_nutzerprofil.get() else ""
            )
            != self.analyse_profil_snapshot
        )

    def _analyseprofil_option_geaendert(self):
        self._analyseauswahl_geaendert()

    def _analyseprofil_geaendert(self, auswahl=None):
        profil_name = str(auswahl or self.analyse_nutzerprofil_auswahl.get() or "").strip()
        if not self.job_service.nutzerprofil_existiert(profil_name):
            profil_name = ""
        self.analyse_nutzerprofil_auswahl.set(profil_name or KEIN_NUTZERPROFIL)
        self.settings["nutzerprofil_auswahl"] = profil_name
        profil_objekt = self.job_service.nutzerprofil_laden(profil_name)
        self.settings["nutzerprofil"] = profil_objekt.daten() if profil_objekt is not None else {}
        self.job_service.settings_speichern(self._aktuelle_settings())
        self._analyseauswahl_geaendert()

    def _analyseauswahl_geaendert(self):
        self.analyse_hinweis = ""
        if self.analyse_jobs:
            self.ki_zusammenfassung_veraltet = self._analyse_einstellungen_geaendert()
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki":
            self.zeige_jobs()

    def ki_suchbegriffe_erzeugen(self):
        if self.suche_laeuft or self.ki_laeuft or self.ki_jobsuche_laeuft:
            return
        abbruch_event = threading.Event()
        self.ki_jobsuche_abbruch = abbruch_event
        self.ki_jobsuche_laeuft = True
        self._ki_jobsuche_status_setzen("KI-Suchplanung laeuft...")
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_jobsuche_button_status_aktualisieren()
        suchanfrage = self._ki_basis_suchanfrage(mit_kriterien=True)
        eingabe = getattr(self, "ki_neuer_suchbegriff", None)
        startbegriff = (eingabe.get().strip() if eingabe is not None else "") or self.such.get().strip()
        suchanfrage = SearchRequest(startbegriff, suchanfrage.ort, suchanfrage.umkreis, suchanfrage.provider, suchanfrage.ki_kriterien)
        self.job_service.settings_speichern(self._aktuelle_settings())
        threading.Thread(
            target=self._ki_suchbegriffe_im_hintergrund,
            args=(suchanfrage, abbruch_event),
            daemon=True,
        ).start()

    def _ki_suchbegriffe_im_hintergrund(self, suchanfrage, abbruch_event):
        try:
            self._lokale_ki_bereitstellen()
            begriffe = self.job_service.ki_suchbegriffe_generieren(
                suchanfrage,
                abbruch_event=abbruch_event,
            )
            self._gui_ausfuehren(lambda: self._ki_suchbegriffe_abgeschlossen(begriffe, abbruch_event))
        except OperationCancelled:
            logging.info("KI-Suchplanung wurde abgebrochen.")
            self._gui_ausfuehren(lambda: self._ki_jobsuche_abbruch_abgeschlossen(abbruch_event))
        except Exception as fehler:
            if abbruch_event.is_set():
                logging.info("KI-Suchplanung wurde waehrend einer Modellantwort abgebrochen.")
                self._gui_ausfuehren(lambda: self._ki_jobsuche_abbruch_abgeschlossen(abbruch_event))
                return
            logging.exception("Fehler bei der KI-Suchplanung")
            self._gui_ausfuehren(lambda fehler=fehler: self._ki_jobsuche_fehlgeschlagen(fehler, abbruch_event))

    def _ki_suchbegriffe_abgeschlossen(self, begriffe, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("ki_jobsuche_abbruch", abbruch_event):
            return
        self.ki_jobsuche_abbruch = None
        self.ki_jobsuche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self.ki_jobsuche_begriffe = [anzeigetext(begriff) for begriff in (begriffe or [])]
        self._ki_jobsuche_status_setzen(
            getattr(self.job_service.ai_search_planner, "letzte_meldung", "KI-Suchplanung abgeschlossen.")
        )
        self._ki_jobsuche_button_status_aktualisieren()
        if self.ansicht == "ki_suche":
            self.zeige_jobs()

    def ki_jobsuche_starten(self):
        if self.suche_laeuft or self.ki_laeuft or self.ki_jobsuche_laeuft:
            return
        begriffe = self.job_service.aktive_suchbegriffe()
        if not begriffe:
            self._ki_jobsuche_status_setzen("Bitte mindestens einen gespeicherten Suchbegriff aktivieren.")
            return
        basis = self._ki_basis_suchanfrage(mit_kriterien=True)
        suchkontext = SearchRequest("; ".join(begriffe), basis.ort, basis.umkreis, basis.provider, basis.ki_kriterien)
        self.job_service.settings_speichern(self._aktuelle_settings())
        abbruch_event = threading.Event()
        self.ki_jobsuche_abbruch = abbruch_event
        self.ki_jobsuche_laeuft = True
        self.suche_laeuft = True
        self.letzter_suchkontext = suchkontext
        self._ki_jobsuche_status_setzen("KI-Jobsuche laeuft...")
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_jobsuche_button_status_aktualisieren()
        threading.Thread(
            target=self._ki_jobsuche_im_hintergrund,
            args=(begriffe, suchkontext, abbruch_event),
            daemon=True,
        ).start()

    def _ki_jobsuche_im_hintergrund(self, begriffe, suchanfrage, abbruch_event):
        try:
            self._lokale_ki_bereitstellen()
            jobs = self.job_service.ki_jobsuche_ausfuehren(
                begriffe,
                suchanfrage,
                abbruch_event=abbruch_event,
            )
            self._gui_ausfuehren(lambda: self._ki_jobsuche_abgeschlossen(jobs, suchanfrage, abbruch_event))
        except OperationCancelled:
            logging.info("KI-Jobsuche wurde abgebrochen.")
            self._gui_ausfuehren(lambda: self._ki_jobsuche_abbruch_abgeschlossen(abbruch_event))
        except Exception as fehler:
            if abbruch_event.is_set():
                logging.info("KI-Jobsuche wurde waehrend einer Provider-Antwort abgebrochen.")
                self._gui_ausfuehren(lambda: self._ki_jobsuche_abbruch_abgeschlossen(abbruch_event))
                return
            logging.exception("Fehler bei der KI-Jobsuche")
            self._gui_ausfuehren(lambda fehler=fehler: self._ki_jobsuche_fehlgeschlagen(fehler, abbruch_event))

    def _ki_jobsuche_abgeschlossen(self, jobs, suchanfrage, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("ki_jobsuche_abbruch", abbruch_event):
            return
        self.ki_jobsuche_abbruch = None
        self.ki_suchergebnisse = list(jobs)
        self.analyse_jobs = []
        self._ki_daten_der_aktuellen_suche_loeschen(self.ki_suchergebnisse)
        self.ki_kriterien_snapshot = None
        self.ki_zusammenfassung_veraltet = False
        self.letzter_suchkontext = suchanfrage
        self.ki_suchkontext = suchanfrage
        self.aktuelle_ergebnisquelle = "ki"
        self.analyse_normale_jobs.set(False)
        self.analyse_ki_jobs.set(bool(jobs))
        self.analyse_hinweis = ""
        self.ki_jobsuche_laeuft = False
        self.suche_laeuft = False
        self.ansicht = "ki_suche"
        self.ki_suchbereich.set("Ergebnisse")
        self.aktuelle_seite = 0
        self._ansichts_zustand_zuruecksetzen("ki_suche")
        self._normaler_suchbutton_status_aktualisieren()
        self.zeige_jobs()
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.diagnose.configure(text=self.job_service.diagnose_meldung())
        self.ki_status.configure(text=self._ki_zusammenfassung_text())
        self._ki_button_status_aktualisieren()
        self._ki_jobsuche_button_status_aktualisieren()

    def _ki_jobsuche_fehlgeschlagen(self, fehler, abbruch_event=None):
        if not self._abbruchlauf_ist_aktuell("ki_jobsuche_abbruch", abbruch_event):
            return
        self.ki_jobsuche_abbruch = None
        self.ki_jobsuche_laeuft = False
        self.suche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_jobsuche_status_setzen(f"Fehler bei der KI-Jobsuche: {fehler}")
        self._ki_jobsuche_button_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        if self.ansicht == "ki_suche":
            self.zeige_jobs()

    def _lokale_ki_bereitstellen(self):
        runtime = getattr(self, "portable_ai", None)
        if runtime is not None and runtime.ollama_exe.is_file() and not runtime.starten():
            raise RuntimeError("Die lokale KI konnte nicht gestartet werden. Details stehen in data/logs/ollama.log.")

    def ki_jobsuche_abbrechen(self):
        abbruch_event = self.ki_jobsuche_abbruch
        if not self.ki_jobsuche_laeuft or abbruch_event is None or abbruch_event.is_set():
            return
        ist_suchplanung = not self.suche_laeuft
        abbruch_event.set()
        if ist_suchplanung:
            self.job_service.ki_suchplanung_abbrechen()
            meldung = "KI-Suchplanung abgebrochen. Vorhandene Vorschlaege bleiben erhalten."
        else:
            meldung = "KI-Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten."
        self._ki_jobsuche_status_setzen(meldung)
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_jobsuche_button_status_aktualisieren()
        self._ki_button_status_aktualisieren()

    def _ki_jobsuche_abbruch_abgeschlossen(self, abbruch_event):
        if self.ki_jobsuche_abbruch is not abbruch_event:
            return
        self.ki_jobsuche_abbruch = None
        self.ki_jobsuche_laeuft = False
        self.suche_laeuft = False
        self._normaler_suchbutton_status_aktualisieren()
        self._ki_jobsuche_button_status_aktualisieren()
        self._ki_button_status_aktualisieren()
        self._suchstatusleiste_aktualisieren()

    def _ki_jobsuche_begriffe_aus_widgets(self):
        werte = [widget.get() for widget in getattr(self, "ki_jobsuche_widgets", [])]
        if not werte:
            werte = self.ki_jobsuche_begriffe
        bereinigt = []
        gesehen = set()
        for wert in werte:
            text = str(wert or "").strip()
            if not text:
                continue
            schluessel = text.lower()
            if schluessel in gesehen:
                continue
            bereinigt.append(text)
            gesehen.add(schluessel)
            if len(bereinigt) >= LOCAL_AI_JOB_SEARCH_MAX_TERMS:
                break
        self.ki_jobsuche_begriffe = bereinigt
        return bereinigt

    def _ki_jobsuche_begriff_geaendert(self, index, wert):
        while len(self.ki_jobsuche_begriffe) <= index:
            self.ki_jobsuche_begriffe.append("")
        self.ki_jobsuche_begriffe[index] = str(wert or "").strip()
        self._ki_jobsuche_button_status_aktualisieren()

    def _ki_suchbegriff_hinzufuegen(self):
        wert = self.ki_neuer_suchbegriff.get() if getattr(self, "ki_neuer_suchbegriff", None) else ""
        self.job_service.suchbegriff_hinzufuegen(wert, "manuell")
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_suchbegriff_bearbeiten(self, suchbegriff_id, widget):
        self.job_service.suchbegriff_bearbeiten(suchbegriff_id, widget.get())
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_suchbegriff_status_vom_switch(self, suchbegriff_id, neuer_status):
        self.job_service.suchbegriff_status_setzen(suchbegriff_id, neuer_status)
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _texteingabe_dialog(self, titel, hinweis, bestaetigen_text="Speichern"):
        dialog = ctk.CTkToplevel(self.app)
        dialog.title(titel)
        dialog.geometry("430x190")
        dialog.resizable(False, False)
        dialog.transient(self.app)
        dialog.grid_columnconfigure(0, weight=1)

        ergebnis = {"wert": None}

        def bestaetigen():
            ergebnis["wert"] = eingabe.get().strip()
            dialog.destroy()

        def abbrechen():
            dialog.destroy()

        ctk.CTkLabel(
            dialog,
            text=hinweis,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 8))
        eingabe = ctk.CTkEntry(dialog, height=36)
        eingabe.grid(row=1, column=0, sticky="ew", padx=20)

        aktionen = ctk.CTkFrame(dialog, fg_color="transparent")
        aktionen.grid(row=2, column=0, sticky="e", padx=16, pady=20)
        ctk.CTkButton(
            aktionen,
            text="Abbrechen",
            command=abbrechen,
            width=100,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_KARTE,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            aktionen,
            text=bestaetigen_text,
            command=bestaetigen,
            width=100,
        ).pack(side="left", padx=4)

        eingabe.bind("<Return>", lambda _event: bestaetigen())
        dialog.bind("<Escape>", lambda _event: abbrechen())
        dialog.protocol("WM_DELETE_WINDOW", abbrechen)
        dialog.update_idletasks()
        x = self.app.winfo_rootx() + max(0, (self.app.winfo_width() - dialog.winfo_width()) // 2)
        y = self.app.winfo_rooty() + max(0, (self.app.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        eingabe.focus_set()
        self.app.wait_window(dialog)
        return ergebnis["wert"]

    def _ki_suchbegriff_set_speichern_unter(self):
        name = self._texteingabe_dialog(
            "Suchbegriff-Set speichern",
            "Name fuer das aktuelle Suchbegriff-Set:",
        )
        name = str(name or "").strip()
        if not name:
            return
        ueberschreiben = self.job_service.suchbegriff_set_existiert(name)
        if ueberschreiben and not messagebox.askyesno(
            "Suchbegriff-Set ueberschreiben",
            f"Das Set '{name}' existiert bereits. Soll es mit dem aktuellen Pool ueberschrieben werden?",
            parent=self.app,
        ):
            return
        eintrag = self.job_service.suchbegriff_set_speichern(name, ueberschreiben=ueberschreiben)
        if eintrag is not None:
            self.ki_suchbegriff_set_auswahl.set(eintrag.name)
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_suchbegriff_set_laden(self):
        name = self.ki_suchbegriff_set_auswahl.get()
        aktuelle_begriffe = self.job_service.suchbegriffe_laden()
        if aktuelle_begriffe and not messagebox.askyesno(
            "Suchbegriff-Set laden",
            (
                f"Beim Laden von '{name}' werden die {len(aktuelle_begriffe)} aktuellen "
                "Suchbegriffe ersetzt. Fortfahren?"
            ),
            parent=self.app,
        ):
            return
        eintrag = self.job_service.suchbegriff_set_laden(name)
        if eintrag is not None:
            self.ki_suchbegriff_set_auswahl.set(eintrag.name)
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_suchbegriff_set_loeschen(self):
        name = self.ki_suchbegriff_set_auswahl.get()
        if not messagebox.askyesno(
            "Suchbegriff-Set loeschen",
            f"Soll das gespeicherte Set '{name}' wirklich geloescht werden?",
            parent=self.app,
        ):
            return
        self.job_service.suchbegriff_set_loeschen(name)
        self.ki_suchbegriff_set_auswahl.set("")
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_suchbegriff_loeschen(self, suchbegriff_id):
        self.job_service.suchbegriff_status_setzen(suchbegriff_id, "geloescht")
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_vorschlag_uebernehmen(self, index):
        begriffe = [widget.get().strip() for widget in self.ki_jobsuche_widgets]
        if not 0 <= index < len(begriffe) or not begriffe[index]:
            return
        gespeichert = self.job_service.suchbegriff_hinzufuegen(begriffe[index], "KI")
        if gespeichert:
            del begriffe[index]
        self.ki_jobsuche_begriffe = [begriff for begriff in begriffe if begriff]
        self._ki_jobsuche_status_setzen(self.job_service.status_meldung())
        self.zeige_jobs()

    def _ki_vorschlag_verwerfen(self, index):
        begriffe = [widget.get().strip() for widget in self.ki_jobsuche_widgets]
        if 0 <= index < len(begriffe):
            del begriffe[index]
        self.ki_jobsuche_begriffe = [begriff for begriff in begriffe if begriff]
        self.zeige_jobs()

    def _ki_vorschlaege_alle_uebernehmen(self):
        begriffe = self._ki_jobsuche_begriffe_aus_widgets()
        nicht_uebernommen = []
        for begriff in begriffe:
            if not self.job_service.suchbegriff_hinzufuegen(begriff, "KI"):
                nicht_uebernommen.append(begriff)
        self.ki_jobsuche_begriffe = nicht_uebernommen
        if nicht_uebernommen:
            self._ki_jobsuche_status_setzen("Einige nahezu identische Vorschlaege wurden nicht uebernommen.")
        else:
            self._ki_jobsuche_status_setzen("Alle Vorschlaege wurden gespeichert.")
        self.zeige_jobs()

    def _ki_vorschlaege_alle_verwerfen(self):
        self.ki_jobsuche_begriffe = []
        self._ki_jobsuche_status_setzen("Alle neuen Vorschlaege wurden verworfen. Gespeicherte Suchbegriffe bleiben unveraendert.")
        self.zeige_jobs()

    def _ki_jobsuche_status_setzen(self, text):
        self.ki_jobsuche_meldung = str(text or "").strip()
        self.status.configure(text=self.ki_jobsuche_meldung)
        self._suchstatusleiste_aktualisieren()

    def _ki_jobsuche_button_status_aktualisieren(self):
        if getattr(self, "ansicht", "") != "ki_suche":
            return
        plan_button = getattr(self, "ki_suchplan_button", None)
        start_button = getattr(self, "ki_jobsuche_start_button", None)
        add_button = getattr(self, "ki_suchbegriff_hinzufuegen_button", None)
        gesperrt = self.suche_laeuft or self.ki_laeuft or self.ki_jobsuche_laeuft
        suchplanung_laeuft = self.ki_jobsuche_laeuft and not self.suche_laeuft
        jobsuche_laeuft = self.ki_jobsuche_laeuft and self.suche_laeuft
        abbruch_angefordert = self._abbruch_angefordert("ki_jobsuche_abbruch")
        if self._widget_existiert(plan_button):
            if suchplanung_laeuft:
                plan_button.configure(
                    state="disabled" if abbruch_angefordert else "normal",
                    text="Planung wird beendet..." if abbruch_angefordert else "Vorschlaege abbrechen",
                    command=self.ki_jobsuche_abbrechen,
                    fg_color=FARBE_FEHLER,
                    hover_color=("#A72F40", "#C94A5A"),
                )
            else:
                plan_button.configure(
                    state="disabled" if gesperrt else "normal",
                    text="Neue Vorschlaege erzeugen",
                    command=self.ki_suchbegriffe_erzeugen,
                    fg_color=FARBE_PRIMAER,
                    hover_color=FARBE_PRIMAER_HOVER,
                )
        if self._widget_existiert(start_button):
            hat_begriffe = bool(self.job_service.aktive_suchbegriffe())
            if jobsuche_laeuft:
                start_button.configure(
                    state="disabled" if abbruch_angefordert else "normal",
                    text="Suche wird beendet..." if abbruch_angefordert else "KI-Jobsuche abbrechen",
                    command=self.ki_jobsuche_abbrechen,
                    fg_color=FARBE_FEHLER,
                    hover_color=("#A72F40", "#C94A5A"),
                )
            else:
                start_button.configure(
                    state="disabled" if gesperrt or not hat_begriffe else "normal",
                    text="Mit aktiven Begriffen suchen",
                    command=self.ki_jobsuche_starten,
                    fg_color=FARBE_ERFOLG,
                    hover_color=("#11734E", "#1D8C64"),
                )
        if self._widget_existiert(add_button):
            add_button.configure(state="disabled" if gesperrt else "normal")

    def _widget_existiert(self, widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except Exception:
            return False
    def _zeige_dashboard(self):
        gespeicherte_daten = self.job_service.jobs_laden()
        gespeicherte_jobs = [job for job in gespeicherte_daten if job.ist_gespeichert()]
        bewerbungen = [
            job
            for job in gespeicherte_jobs
            if job.status not in ("Neu", "Gespeichert")
        ]
        ki_jobs = [job for job in (self.analyse_jobs or self.jobs or gespeicherte_daten) if job.hat_ki_daten()]
        durchschnitt = (
            round(sum(job.ki_match_score for job in ki_jobs) / len(ki_jobs))
            if ki_jobs
            else 0
        )

        kennzahlen = ctk.CTkFrame(self.liste, fg_color="transparent")
        self.einleitung_ziele["kennzahlen"] = kennzahlen
        kennzahlen.pack(fill="x", pady=(0, 14))
        for spalte in range(4):
            kennzahlen.grid_columnconfigure(spalte, weight=1, uniform="kennzahlen")

        self._kennzahl_karte(
            kennzahlen,
            0,
            "Aktuelle Treffer",
            str(len(self.jobs)),
            "Letzter Suchlauf",
            FARBE_PRIMAER,
        )
        self._kennzahl_karte(
            kennzahlen,
            1,
            "Gespeichert",
            str(len(gespeicherte_jobs)),
            "Merkliste und Vorgemerktes",
            FARBE_ERFOLG,
        )
        self._kennzahl_karte(
            kennzahlen,
            2,
            "Bewerbungen",
            str(len(bewerbungen)),
            "Aktive Prozesse",
            FARBE_WARNUNG,
        )
        self._kennzahl_karte(
            kennzahlen,
            3,
            "KI-Match",
            f"{durchschnitt}%" if ki_jobs else "-",
            f"{len(ki_jobs)} Kandidaten bewertet",
            FARBE_PRIMAER,
        )

        diagramme = ctk.CTkFrame(self.liste, fg_color="transparent")
        diagramme.pack(fill="x", pady=(0, 16))
        diagramme.grid_columnconfigure(0, weight=1, uniform="diagramme")
        diagramme.grid_columnconfigure(1, weight=1, uniform="diagramme")

        quellen = haeufigkeiten(
            [job.quelle for job in (self.jobs or gespeicherte_daten)],
            limit=5,
        )
        skills = haeufigkeiten(
            [skill for job in ki_jobs for skill in job.ki_skills],
            limit=5,
        )
        self._balkendiagramm(
            diagramme,
            0,
            "Jobs nach Quelle",
            quellen,
            FARBE_PRIMAER,
            "Noch keine Suchtreffer vorhanden.",
        )
        self._balkendiagramm(
            diagramme,
            1,
            "Haeufige Anforderungen",
            skills,
            FARBE_ERFOLG,
            "Nach der KI-Auswertung erscheinen hier gefragte Skills.",
        )

        ctk.CTkLabel(
            self.liste,
            text="Zuletzt gespeicherte Stellen",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 8))
        letzte_jobs = self.job_service.zuletzt_gespeicherte_jobs(limit=5)
        if not letzte_jobs:
            leer = ctk.CTkFrame(
                self.liste,
                fg_color=FARBE_KARTE,
                border_width=1,
                border_color=FARBE_RAND,
                corner_radius=8,
            )
            leer.pack(fill="x")
            ctk.CTkLabel(
                leer,
                text="Speichern Sie interessante Stellen mit dem Herzsymbol.",
                text_color=FARBE_TEXT_SEKUNDAER,
            ).pack(anchor="w", padx=16, pady=18)
            return

        for job in letzte_jobs:
            zeile = ctk.CTkFrame(
                self.liste,
                fg_color=FARBE_KARTE,
                border_width=1,
                border_color=FARBE_RAND,
                corner_radius=8,
            )
            zeile.pack(fill="x", pady=4)
            zeile.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                zeile,
                text=self._anzeigetext(job.titel, "Stellentitel nicht angegeben"),
                font=("Segoe UI", 14, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
            ctk.CTkLabel(
                zeile,
                text=(
                    f"{self._anzeigetext(job.firma, 'Firma nicht angegeben')}  |  "
                    f"{self._anzeigetext(job.ort, 'Ort nicht angegeben')}  |  "
                    f"{self._anzeigetext(job.quelle, 'Quelle unbekannt')}"
                ),
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
            self._status_badge(zeile, job.status).grid(row=0, column=1, rowspan=2, padx=10)
            if job.ki_match_score:
                ctk.CTkLabel(
                    zeile,
                    text=f"{job.ki_match_score}% Match",
                    text_color=FARBE_ERFOLG if job.ki_match_score >= 70 else FARBE_WARNUNG,
                    font=("Segoe UI", 12, "bold"),
                ).grid(row=0, column=2, rowspan=2, padx=(0, 10))
            ctk.CTkButton(
                zeile,
                text="Details",
                width=82,
                command=lambda aktueller_job=job: self.detailansicht_oeffnen(aktueller_job),
            ).grid(row=0, column=3, rowspan=2, padx=(0, 12))

    def _kennzahl_karte(self, parent, spalte, titel, wert, hinweis, farbe):
        karte = ctk.CTkFrame(
            parent,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.grid(row=0, column=spalte, sticky="nsew", padx=(0 if spalte == 0 else 5, 5 if spalte < 3 else 0))
        ctk.CTkLabel(
            karte,
            text=titel,
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(13, 2))
        ctk.CTkLabel(
            karte,
            text=wert,
            font=("Segoe UI", 26, "bold"),
            text_color=farbe,
            anchor="w",
        ).pack(fill="x", padx=14)
        ctk.CTkLabel(
            karte,
            text=hinweis,
            font=("Segoe UI", 10),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(2, 13))

    def _balkendiagramm(self, parent, spalte, titel, daten, farbe, leertext):
        karte = ctk.CTkFrame(
            parent,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.grid(row=0, column=spalte, sticky="nsew", padx=(0 if spalte == 0 else 6, 6 if spalte == 0 else 0))
        ctk.CTkLabel(
            karte,
            text=titel,
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 12))

        if not daten:
            ctk.CTkLabel(
                karte,
                text=leertext,
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
                justify="left",
                wraplength=380,
            ).pack(fill="x", padx=16, pady=(0, 18))
            return

        maximum = max(anzahl for _name, anzahl in daten) or 1
        for name, anzahl in daten:
            kopf = ctk.CTkFrame(karte, fg_color="transparent")
            kopf.pack(fill="x", padx=16)
            ctk.CTkLabel(kopf, text=name, font=("Segoe UI", 11), anchor="w").pack(side="left")
            ctk.CTkLabel(
                kopf,
                text=str(anzahl),
                font=("Segoe UI", 11, "bold"),
                text_color=farbe,
            ).pack(side="right")
            balken = ctk.CTkProgressBar(karte, height=7, progress_color=farbe)
            balken.pack(fill="x", padx=16, pady=(2, 9))
            balken.set(anzahl / maximum)
        ctk.CTkLabel(karte, text="", height=3).pack()

    def _zeige_nutzerprofil(self):
        self.nutzerprofil_widgets = {}
        self.status.configure(text="Nutzerprofile fuer die lokale KI")
        self.diagnose.configure(text="Profile getrennt verwalten und in der KI-Analyse gezielt auswaehlen.")
        self.ki_status.configure(text="")
        self._navigation_aktualisieren(0)

        profil_objekt = self.job_service.nutzerprofil_laden(self.geladenes_nutzerprofil_name)
        profil = profil_objekt.daten() if profil_objekt is not None else {}
        profil_namen = self._nutzerprofil_namen()
        auswahlwerte = profil_namen or [KEIN_NUTZERPROFIL]
        if self.nutzerprofil_editor_auswahl.get() not in auswahlwerte:
            self.nutzerprofil_editor_auswahl.set(self.geladenes_nutzerprofil_name or KEIN_NUTZERPROFIL)

        karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.pack(fill="both", expand=True, pady=(0, 12))
        ctk.CTkLabel(
            karte,
            text="Persoenliche Profile",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            karte,
            text="Die lokale KI nutzt diese Angaben, um Treffer besser mit Erfahrung, Staerken und Wuenschen abzugleichen.",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
            wraplength=900,
        ).pack(fill="x", padx=18, pady=(0, 12))

        werkzeuge = ctk.CTkFrame(karte, fg_color="transparent")
        self.einleitung_ziele["profil_werkzeuge"] = werkzeuge
        werkzeuge.pack(fill="x", padx=18, pady=(0, 10))
        werkzeuge.grid_columnconfigure(0, weight=1)
        profil_auswahl = ctk.CTkComboBox(
            werkzeuge,
            values=auswahlwerte,
            variable=self.nutzerprofil_editor_auswahl,
            state="readonly" if profil_namen else "disabled",
            height=38,
        )
        profil_auswahl.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            werkzeuge,
            text="Laden",
            command=self._nutzerprofil_auswahl_laden,
            width=95,
            height=38,
            state="normal" if profil_namen else "disabled",
        ).grid(row=0, column=1, padx=4)
        ctk.CTkButton(
            werkzeuge,
            text="Speichern unter",
            command=self._nutzerprofil_speichern_unter,
            width=145,
            height=38,
            fg_color=FARBE_ERFOLG,
            hover_color=("#11734E", "#1D8C64"),
        ).grid(row=0, column=2, padx=4)
        ctk.CTkButton(
            werkzeuge,
            text="Profil loeschen",
            command=self._nutzerprofil_loeschen,
            width=125,
            height=38,
            state="normal" if profil_namen else "disabled",
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_FEHLER,
            text_color=FARBE_FEHLER,
            hover_color=FARBE_RAND,
        ).grid(row=0, column=3, padx=(4, 0))

        ctk.CTkLabel(
            karte,
            text=(
                f"Geladen: {self.geladenes_nutzerprofil_name}"
                if self.geladenes_nutzerprofil_name
                else "Noch kein Profil gespeichert"
            ),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 4))

        felder = [
            ("kurzprofil", "Kurzprofil", "z. B. kaufmaennischer Hintergrund, Organisation, Quereinstieg moeglich"),
            ("berufserfahrung", "Berufserfahrung", "Stationen, Branchen, relevante Aufgaben"),
            ("staerken", "Staerken", "z. B. strukturiert, ruhig, zuverlaessig, kundenorientiert"),
            ("kenntnisse", "Kenntnisse", "Software, Sprachen, Zertifikate, Fachwissen"),
            ("wunschrolle", "Wunschrolle", "Welche Arbeit soll die KI besonders positiv bewerten?"),
            ("einschraenkungen", "Einschraenkungen", "Was soll die KI vorsichtig bewerten oder meiden?"),
        ]
        for name, label, platzhalter in felder:
            self._profil_textfeld(karte, name, label, platzhalter, str(profil.get(name, "") or ""))

        ctk.CTkButton(
            karte,
            text="Ausgewaehltes Profil speichern",
            command=self.nutzerprofil_speichern,
            width=230,
            height=38,
            font=("Segoe UI", 13, "bold"),
            state="normal" if self.geladenes_nutzerprofil_name else "disabled",
        ).pack(anchor="e", padx=18, pady=(4, 18))

    def _profil_textfeld(self, parent, name, label, platzhalter, wert):
        platzhalter = anzeigetext(platzhalter)
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=18, pady=(8, 2))
        feld = ctk.CTkTextbox(parent, height=74, wrap="word")
        feld.pack(fill="x", padx=18, pady=(0, 4))
        feld.insert("1.0", wert or platzhalter)
        if not wert:
            feld.configure(text_color=FARBE_TEXT_SEKUNDAER)
            feld.bind("<FocusIn>", lambda _event, widget=feld, text=platzhalter: self._platzhalter_entfernen(widget, text))
        feld.bind("<KeyRelease>", lambda _event: self._nutzerprofil_geaendert())
        self.nutzerprofil_widgets[name] = (feld, platzhalter)

    def _platzhalter_entfernen(self, widget, platzhalter):
        if widget.get("1.0", "end").strip() == platzhalter:
            widget.delete("1.0", "end")
            widget.configure(text_color=("gray15", "gray90"))

    def _profilformular_daten(self):
        profil = {}
        nutzerprofil_widgets = getattr(self, "nutzerprofil_widgets", {})
        if nutzerprofil_widgets:
            try:
                for name, (widget, platzhalter) in nutzerprofil_widgets.items():
                    wert = widget.get("1.0", "end").strip()
                    profil[name] = "" if wert == platzhalter else wert
                return profil
            except Exception:
                self.nutzerprofil_widgets = {}
        profil_objekt = self.job_service.nutzerprofil_laden(getattr(self, "geladenes_nutzerprofil_name", ""))
        if profil_objekt is not None:
            return profil_objekt.daten()
        settings = getattr(self, "settings", {})
        gespeichertes_profil = settings.get("nutzerprofil") if isinstance(settings, dict) else {}
        return dict(gespeichertes_profil) if isinstance(gespeichertes_profil, dict) else {}

    def _nutzerprofil_namen(self):
        return [profil.name for profil in self.job_service.nutzerprofile_laden()]

    def _analyseprofil_name(self):
        variable = getattr(self, "analyse_nutzerprofil_auswahl", None)
        settings = getattr(self, "settings", {})
        auswahl = variable.get() if variable is not None else settings.get("nutzerprofil_auswahl", "")
        auswahl = str(auswahl or "").strip()
        if not auswahl or auswahl == KEIN_NUTZERPROFIL:
            return ""
        job_service = getattr(self, "job_service", None)
        if job_service is None or not hasattr(job_service, "nutzerprofil_existiert"):
            return ""
        return auswahl if job_service.nutzerprofil_existiert(auswahl) else ""

    def _nutzerprofil(self):
        job_service = getattr(self, "job_service", None)
        profil_objekt = (
            job_service.nutzerprofil_laden(self._analyseprofil_name())
            if job_service is not None and hasattr(job_service, "nutzerprofil_laden")
            else None
        )
        if profil_objekt is not None:
            return profil_objekt.daten()
        settings = getattr(self, "settings", {})
        gespeichertes_profil = settings.get("nutzerprofil") if isinstance(settings, dict) else {}
        return dict(gespeichertes_profil) if isinstance(gespeichertes_profil, dict) else {}

    def _nutzerprofil_geaendert(self):
        if self.ki_kriterien_snapshot is not None:
            self.ki_zusammenfassung_veraltet = True

    def _nutzerprofil_hat_ungespeicherte_aenderungen(self):
        if not self.nutzerprofil_widgets:
            return False
        profil_objekt = self.job_service.nutzerprofil_laden(self.geladenes_nutzerprofil_name)
        gespeichert = profil_objekt.daten() if profil_objekt is not None else {}
        return self._profilformular_daten() != gespeichert

    def _nutzerprofil_aktivieren(self, name):
        profil_objekt = self.job_service.nutzerprofil_laden(name)
        if profil_objekt is None:
            return False
        self.geladenes_nutzerprofil_name = profil_objekt.name
        self.nutzerprofil_editor_auswahl.set(profil_objekt.name)
        self.analyse_nutzerprofil_auswahl.set(profil_objekt.name)
        self.settings["nutzerprofil_auswahl"] = profil_objekt.name
        self.settings["nutzerprofil"] = profil_objekt.daten()
        self.job_service.settings_speichern(self._aktuelle_settings())
        if self.ki_kriterien_snapshot is not None:
            self.ki_zusammenfassung_veraltet = True
        return True

    def _nutzerprofil_auswahl_laden(self):
        name = self.nutzerprofil_editor_auswahl.get()
        if not name or name == KEIN_NUTZERPROFIL:
            return
        if self._nutzerprofil_hat_ungespeicherte_aenderungen() and not messagebox.askyesno(
            "Ungespeicherte Aenderungen",
            "Die aktuellen Eingaben wurden noch nicht gespeichert. Trotzdem ein anderes Profil laden?",
            parent=self.app,
        ):
            self.nutzerprofil_editor_auswahl.set(self.geladenes_nutzerprofil_name or KEIN_NUTZERPROFIL)
            return
        if self._nutzerprofil_aktivieren(name):
            self.zeige_jobs()
            self.status.configure(text=f"Nutzerprofil '{name}' geladen.")

    def _nutzerprofil_speichern_unter(self):
        name = self._texteingabe_dialog(
            "Nutzerprofil speichern unter",
            "Name fuer dieses Nutzerprofil:",
            self.geladenes_nutzerprofil_name,
        )
        if name is None:
            return
        name = str(name).strip()
        if not name:
            messagebox.showwarning("Name fehlt", "Bitte einen Namen fuer das Nutzerprofil eingeben.", parent=self.app)
            return
        ueberschreiben = self.job_service.nutzerprofil_existiert(name)
        if ueberschreiben and not messagebox.askyesno(
            "Nutzerprofil ueberschreiben",
            f"Das Profil '{name}' existiert bereits. Wirklich ueberschreiben?",
            parent=self.app,
        ):
            return
        try:
            profil = self.job_service.nutzerprofil_speichern(
                name,
                self._profilformular_daten(),
                ueberschreiben=ueberschreiben,
            )
        except ValueError as fehler:
            messagebox.showwarning("Profil nicht gespeichert", str(fehler), parent=self.app)
            return
        self._nutzerprofil_aktivieren(profil.name)
        self.zeige_jobs()
        self.status.configure(text=f"Nutzerprofil '{profil.name}' gespeichert.")

    def _nutzerprofil_loeschen(self):
        name = self.nutzerprofil_editor_auswahl.get()
        if not name or name == KEIN_NUTZERPROFIL:
            return
        if not messagebox.askyesno(
            "Nutzerprofil loeschen",
            f"Das Nutzerprofil '{name}' wirklich loeschen?",
            parent=self.app,
        ):
            return
        if not self.job_service.nutzerprofil_loeschen(name):
            return
        profil_namen = self._nutzerprofil_namen()
        if profil_namen:
            self._nutzerprofil_aktivieren(profil_namen[0])
        else:
            self.geladenes_nutzerprofil_name = ""
            self.nutzerprofil_editor_auswahl.set(KEIN_NUTZERPROFIL)
            self.analyse_nutzerprofil_auswahl.set(KEIN_NUTZERPROFIL)
            self.settings["nutzerprofil_auswahl"] = ""
            self.settings["nutzerprofil"] = {}
            self.job_service.settings_speichern(self._aktuelle_settings())
        self.zeige_jobs()
        self.status.configure(text=f"Nutzerprofil '{name}' geloescht.")

    def nutzerprofil_speichern(self):
        name = self.geladenes_nutzerprofil_name
        if not name:
            self._nutzerprofil_speichern_unter()
            return
        if not messagebox.askyesno(
            "Nutzerprofil aktualisieren",
            f"Die gespeicherten Daten von '{name}' mit den aktuellen Eingaben ueberschreiben?",
            parent=self.app,
        ):
            return
        try:
            self.job_service.nutzerprofil_speichern(
                name,
                self._profilformular_daten(),
                ueberschreiben=True,
            )
        except ValueError as fehler:
            messagebox.showwarning("Profil nicht gespeichert", str(fehler), parent=self.app)
            return
        self._nutzerprofil_aktivieren(name)
        self.zeige_jobs()
        self.status.configure(text=f"Nutzerprofil '{name}' aktualisiert.")

    def _zeige_einstellungen(self):
        darstellung = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        darstellung.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            darstellung,
            text="Darstellung",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            darstellung,
            text="Das Farbschema wird sofort angewendet und fuer den naechsten Start gespeichert.",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 12))
        auswahl = ctk.CTkSegmentedButton(
            darstellung,
            values=["System", "Hell", "Dunkel"],
            command=self._darstellung_geaendert,
            height=38,
        )
        auswahl.pack(anchor="w", padx=18, pady=(0, 18))
        auswahl.set(DARSTELLUNG_NAMEN[self.darstellung_modus])

        ki_karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        ki_karte.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            ki_karte,
            text="Lokale KI",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 8))
        self._einstellungszeile(ki_karte, "Modell", LOCAL_AI_ANALYSIS_MODEL)
        self._einstellungszeile(ki_karte, "Verarbeitung", "Lokal im portablen App-Ordner")
        self._einstellungszeile(ki_karte, "Start", "Manuell nach der Jobsuche")
        ctk.CTkLabel(ki_karte, text="", height=5).pack()

        provider_karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        provider_karte.pack(fill="x", pady=(0, 12))
        provider_kopf = ctk.CTkFrame(provider_karte, fg_color="transparent")
        provider_kopf.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(
            provider_kopf,
            text="API und Suchquellen",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            provider_kopf,
            text="Status aktualisieren",
            command=self._provider_status_aktualisieren,
            width=150,
            height=32,
        ).pack(side="right")
        statuszeilen = {}
        for index, info in enumerate(PROVIDER_EINSTELLUNGEN):
            name = info["name"]
            zeile = ctk.CTkFrame(provider_karte, fg_color="transparent")
            zeile.pack(fill="x", padx=18, pady=8)
            ctk.CTkLabel(
                zeile,
                text=info["label"],
                font=("Segoe UI", 13, "bold"),
                width=205,
                anchor="w",
            ).pack(side="left", anchor="n", pady=(1, 0))
            inhalt = ctk.CTkFrame(zeile, fg_color="transparent")
            inhalt.pack(side="left", fill="x", expand=True)
            wert = ctk.CTkLabel(
                inhalt,
                text="Status wird geladen...",
                anchor="w",
                justify="left",
                wraplength=900,
            )
            wert.pack(fill="x")
            ctk.CTkLabel(
                inhalt,
                text=info["beschreibung"],
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
                justify="left",
                wraplength=900,
            ).pack(fill="x", pady=(2, 0))
            ctk.CTkButton(
                zeile,
                text=info["link_text"],
                command=lambda url=info["url"]: webbrowser.open(url),
                width=145,
                height=30,
                fg_color=FARBE_KARTE_ZWEI,
                border_width=1,
                border_color=FARBE_RAND,
                text_color=("gray15", "gray90"),
            ).pack(side="right", padx=(14, 0), anchor="n")
            statuszeilen[name] = wert
            if index < len(PROVIDER_EINSTELLUNGEN) - 1:
                ctk.CTkFrame(
                    provider_karte,
                    height=1,
                    fg_color=FARBE_RAND,
                    corner_radius=0,
                ).pack(fill="x", padx=18)
        ctk.CTkLabel(provider_karte, text="", height=5).pack()
        self.provider_statuszeilen = statuszeilen
        self._provider_status_anzeigen(self.job_service.provider_status())
        zugangsdaten = ctk.CTkFrame(provider_karte, fg_color="transparent")
        zugangsdaten.pack(fill="x")
        self.einleitung_ziele["zugangsdaten"] = zugangsdaten
        self.zugangsfelder = suchquellen_editor(zugangsdaten, self._zugangsdaten_bearbeitbar, self._suchquellen_neu_laden)
        if not getattr(self, "provider_status_laeuft", False) and not getattr(self, "einleitung_aktiv", False):
            self._provider_status_aktualisieren()

        system_karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        system_karte.pack(fill="x")
        ctk.CTkLabel(
            system_karte,
            text="Anwendung",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 8))
        self._einstellungszeile(system_karte, "Version", VERSION)
        self._einstellungszeile(system_karte, "Logdatei", str(log_pfad()))
        ctk.CTkButton(system_karte, text="Einfuehrung erneut anzeigen", command=self._einleitung_oeffnen, width=220).pack(anchor="w", padx=18, pady=10)
        ctk.CTkLabel(system_karte, text="", height=5).pack()

        lizenz_karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        lizenz_karte.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(
            lizenz_karte,
            text="Lizenzen und Weitergabe",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 8))
        self._einstellungszeile(lizenz_karte, "JobScout AI", "MIT-Lizenz")
        self._einstellungszeile(lizenz_karte, "Lokale KI", "Qwen3 4B - Apache License 2.0")
        self._einstellungszeile(lizenz_karte, "KI-Laufzeit", "Ollama - MIT-Lizenz")
        ctk.CTkButton(
            lizenz_karte,
            text="Lizenzinformationen oeffnen",
            command=self._lizenzinformationen_oeffnen,
            width=210,
            height=34,
        ).pack(anchor="w", padx=18, pady=(8, 18))

    def _einleitung_oeffnen(self):
        fenster = getattr(self, "einleitung_fenster", None)
        if fenster is not None and fenster.winfo_exists():
            fenster.lift()
            return

        def abgeschlossen():
            settings = self._aktuelle_settings()
            settings["einleitung_abgeschlossen"] = True
            self.job_service.settings_speichern(settings)
            self.settings["einleitung_abgeschlossen"] = True

        self.einleitung_fenster = zeige_einleitung(self, abgeschlossen)

    def _einleitungs_ansicht_oeffnen(self, ansicht):
        if ansicht == "ki_suche":
            self.ansichts_zustaende.setdefault(ansicht, {})["suchbereich"] = "Suchbegriffe"
        self._ansicht_wechseln(ansicht)
        if ansicht == "suche" and not self.treffer_sortierleiste.winfo_manager():
            self.treffer_sortierleiste.pack(before=self.liste._parent_frame, fill="x", pady=(0, 8))

    def _einleitungs_ziel(self, name):
        widget = self.einleitung_ziele.get(name)
        if widget is None:
            widget = getattr(self, name, None)
        return widget if widget is not None and widget.winfo_exists() else None

    def _einleitungs_entwurf_sichern(self):
        if self.ansicht == "profil":
            return {"profil": {name: feld.get("1.0", "end-1c") for name, (feld, _) in self.nutzerprofil_widgets.items()}}
        if self.ansicht == "ki_suche" and self.ki_suchbereich.get() == "Suchbegriffe":
            return {"begriffe": {name: feld.get() for name, feld in self.ki_suchbegriff_pool_widgets.items()},
                    "neuer_begriff": self.ki_neuer_suchbegriff.get() if self.ki_neuer_suchbegriff is not None else ""}
        if self.ansicht == "einstellungen":
            return {"zugangsdaten": {name: feld.get() for name, feld in getattr(self, "zugangsfelder", {}).items()}}
        return {}

    def _einleitungs_entwurf_wiederherstellen(self, entwurf):
        for name, text in entwurf.get("profil", {}).items():
            feld = self.nutzerprofil_widgets[name][0]
            feld.delete("1.0", "end")
            feld.insert("1.0", text)
        for name, text in entwurf.get("begriffe", {}).items():
            feld = self.ki_suchbegriff_pool_widgets.get(name)
            if feld is not None:
                feld.delete(0, "end")
                feld.insert(0, text)
        if "neuer_begriff" in entwurf:
            self.ki_neuer_suchbegriff.insert(0, entwurf["neuer_begriff"])
        for name, text in entwurf.get("zugangsdaten", {}).items():
            feld = self.zugangsfelder[name]
            feld.delete(0, "end")
            feld.insert(0, text)

    def _zugangsdaten_bearbeitbar(self):
        if self.suche_laeuft or self.ki_jobsuche_laeuft or self.ki_laeuft or getattr(self, "provider_status_laeuft", False):
            messagebox.showinfo("Suchquellen", "Bitte die laufende Suche, Analyse oder Statusabfrage abwarten.")
            return False
        return True

    def _suchquellen_neu_laden(self):
        vorher = set(self.job_service.verfuegbare_provider_namen())
        ausgewaehlt = self._ausgewaehlte_provider()
        ki_ausgewaehlt = self._ausgewaehlte_ki_provider()
        self.job_service.pipeline.provider_registry = standard_provider_registry()
        neue = set(self.job_service.verfuegbare_provider_namen()) - vorher
        self.settings["provider"] = ausgewaehlt + sorted(neue)
        self.settings["ki_provider"] = ki_ausgewaehlt + sorted(neue)
        for frame in (self.provider_frame, self.ki_provider_frame):
            for widget in frame.winfo_children():
                widget.destroy()
        self.provider_variablen.clear()
        self.ki_provider_variablen.clear()
        self._provider_checkboxes_erstellen()
        self._ki_provider_checkboxes_erstellen()
        self.job_service.settings_speichern(self._aktuelle_settings())
        self._provider_status_anzeigen(self.job_service.provider_status())
        self._provider_status_aktualisieren()

    def _lizenzinformationen_oeffnen(self):
        if not THIRD_PARTY_NOTICES_DATEI.is_file():
            messagebox.showwarning(
                "Lizenzinformationen",
                "Die Lizenzinformationen wurden in diesem Entwicklungsstand nicht gefunden.",
            )
            return
        os.startfile(THIRD_PARTY_NOTICES_DATEI)

    def _provider_status_aktualisieren(self):
        if getattr(self, "provider_status_laeuft", False):
            return
        self.provider_status_laeuft = True
        for label in getattr(self, "provider_statuszeilen", {}).values():
            label.configure(text="Status wird aktualisiert...")
        threading.Thread(
            target=self._provider_status_im_hintergrund,
            daemon=True,
        ).start()

    def _provider_status_im_hintergrund(self):
        try:
            status = self.job_service.provider_status(aktualisieren=True)
        except Exception:
            logging.exception("Provider-Status konnte nicht aktualisiert werden.")
            status = self.job_service.provider_status()
        self._gui_ausfuehren(lambda: self._provider_status_abgeschlossen(status))

    def _provider_status_abgeschlossen(self, status):
        self.provider_status_laeuft = False
        self._provider_status_anzeigen(status)

    def _provider_status_anzeigen(self, status):
        status_nach_name = {
            eintrag.get("name"): eintrag
            for eintrag in status
            if isinstance(eintrag, dict)
        }
        for name, label in getattr(self, "provider_statuszeilen", {}).items():
            if not label.winfo_exists():
                continue
            eintrag = status_nach_name.get(name, {})
            details = eintrag.get("statusdetails") if isinstance(eintrag, dict) else {}
            details = details if isinstance(details, dict) else {}
            if name == "websuche":
                if not details.get("konfiguriert"):
                    text = "Deaktiviert - SERP_SEARCH_API_KEY fehlt."
                elif details.get("statusfehler"):
                    text = str(details["statusfehler"])
                else:
                    verbleibend = int(details.get("verbleibend", 0) or 0)
                    limit = int(details.get("limit", 0) or 0)
                    konto = str(details.get("provider_status") or "Konfiguriert")
                    text = f"{konto} - {verbleibend} / {limit} Suchanfragen verbleibend"
                    if details.get("limit_erreicht"):
                        text = "Monatslimit erreicht - Websuche ist deaktiviert."
            else:
                text = str(
                    details.get("provider_status")
                    or eintrag.get("deaktivierungsgrund")
                    or ("Aktiv" if eintrag.get("aktiv") else "Deaktiviert")
                )
            aktiv = bool(eintrag.get("aktiv")) and not str(text).casefold().startswith(
                ("deaktiviert", "monatslimit", "fehler")
            )
            label.configure(text=text, text_color=FARBE_ERFOLG if aktiv else FARBE_FEHLER)

    def _einstellungszeile(self, parent, label, wert):
        zeile = ctk.CTkFrame(parent, fg_color="transparent")
        zeile.pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(
            zeile,
            text=label,
            text_color=FARBE_TEXT_SEKUNDAER,
            width=130,
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            zeile,
            text=wert,
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(side="left", fill="x", expand=True)

    def _darstellung_geaendert(self, wert):
        self.darstellung_modus = darstellung_normalisieren(wert)
        ctk.set_appearance_mode(self.darstellung_modus)
        self.settings["darstellung"] = self.darstellung_modus
        self.job_service.settings_speichern(self._aktuelle_settings())

    def _zeige_bewerbungsgruppen(self):
        gruppen = self.job_service.bewerbungen_nach_status(
            self.bewerbung_suche.get(),
            self.bewerbung_status_auswahl,
            self.quellen_filter.get(),
            self.sortierung.get(),
            self.followup_filter.get(),
        )
        anzahl = self.job_service.status_anzahlen()
        self._bewerbungsstatus_tabs_aktualisieren(anzahl)
        jobs = [job for status in self.job_service.status_werte() for job in gruppen.get(status, [])]
        gesamt = len(jobs)

        self.status.configure(text=f"{gesamt} Bewerbungen in der aktuellen Ansicht")
        self.diagnose.configure(text=self._status_uebersicht(anzahl))
        self.ki_status.configure(text="")
        self._navigation_aktualisieren(gesamt)

        if not jobs:
            ctk.CTkLabel(self.liste, text="Keine Bewerbungen gefunden.").pack(pady=20)
            return

        seiten_jobs = set(id(job) for job in self._jobs_der_seite(jobs))
        for status in self.job_service.status_werte():
            jobs_in_gruppe = [job for job in gruppen.get(status, []) if id(job) in seiten_jobs]
            if not jobs_in_gruppe:
                continue
            if self.bewerbung_status_auswahl == "Alle":
                ctk.CTkLabel(
                    self.liste,
                    text=f"{status} ({anzahl.get(status, 0)})",
                    font=("Arial", 17, "bold"),
                    anchor="w",
                ).pack(fill="x", padx=6, pady=(14, 4))
            for job in jobs_in_gruppe:
                self._job_karte(job, kompakt=False)

    def _bewerbungsstatus_tabs_aktualisieren(self, anzahl):
        gesamt = sum(anzahl.get(status, 0) for status in self.job_service.status_werte() if status != "Neu")
        for status in BEWERBUNGSSTATUS_TABS:
            wert = gesamt if status == "Alle" else anzahl.get(status, 0)
            passiv, aktiv = BEWERBUNGSSTATUS_TAB_FARBEN[status]
            ausgewaehlt = status == self.bewerbung_status_auswahl
            self.bewerbung_status_tab_buttons[status].configure(
                text=f"{status} ({wert})",
                fg_color=aktiv if ausgewaehlt else passiv,
                hover_color=aktiv,
                text_color=("#18232D", "#F5F7FA"),
                border_color=aktiv if ausgewaehlt else FARBE_RAND,
                border_width=2 if ausgewaehlt else 1,
            )

    def _bewerbungsstatus_tab_gewechselt(self, status):
        self.bewerbung_status_auswahl = status if status in BEWERBUNGSSTATUS_TABS else "Alle"
        self.aktuelle_seite = 0
        self.zeige_jobs()
        scrollbare_liste_nach_oben(self.liste)

    def _zeige_ki_zusammenfassung(self):
        jobs = [job for job in self.analyse_jobs if job.hat_ki_daten()]
        self.status.configure(text=self._ki_zusammenfassung_text())
        self._ki_analyse_setup_anzeigen()

        if self.ki_laeuft:
            laufend = ctk.CTkFrame(
                self.liste,
                fg_color=FARBE_KARTE_ZWEI,
                border_width=1,
                border_color=FARBE_PRIMAER,
                corner_radius=8,
            )
            laufend.pack(fill="x", padx=8, pady=(2, 12))
            ctk.CTkLabel(
                laufend,
                text="Lokale KI-Analyse laeuft",
                font=("Segoe UI", 16, "bold"),
                anchor="w",
            ).pack(fill="x", padx=16, pady=(14, 2))
            ctk.CTkLabel(
                laufend,
                text="Die ausgewaehlten Treffer werden mit Ihren Bewertungskriterien abgeglichen.",
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
            ).pack(fill="x", padx=16, pady=(0, 8))
            fortschritt = ctk.CTkProgressBar(laufend, mode="indeterminate", height=7)
            fortschritt.pack(fill="x", padx=16, pady=(0, 16))
            fortschritt.start()
            if not jobs:
                return

        if not self.normale_suchergebnisse and not self.ki_suchergebnisse:
            self._ki_analyse_leerzustand()
            return

        if not jobs:
            bereit = ctk.CTkFrame(
                self.liste,
                fg_color=FARBE_KARTE,
                border_width=1,
                border_color=FARBE_RAND,
                corner_radius=8,
            )
            bereit.pack(fill="x", padx=8, pady=(2, 12))
            ctk.CTkLabel(
                bereit,
                text="Bereit fuer Ihre erste Auswertung",
                font=("Segoe UI", 18, "bold"),
                anchor="w",
            ).pack(fill="x", padx=18, pady=(16, 4))
            ctk.CTkLabel(
                bereit,
                text=(
                    "Waehlen Sie oben die Trefferquellen und optional das Nutzerprofil aus. "
                    "Die Analyse startet ausschliesslich ueber den Button Analyse starten."
                ),
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
                justify="left",
                wraplength=920,
            ).pack(fill="x", padx=18, pady=(0, 16))
            return

        self._ki_ergebnis_status_anzeigen(jobs)
        self._ki_visuelle_uebersicht(jobs)

        zusammenfassung = self._ki_gesamtfazit(jobs)
        self._ki_abschnitt("Einordnung der lokalen KI")
        fazit = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_PRIMAER,
            corner_radius=8,
        )
        fazit.pack(fill="x", padx=8, pady=(2, 10))
        ctk.CTkLabel(
            fazit,
            text=zusammenfassung,
            anchor="w",
            justify="left",
            wraplength=900,
            font=("Segoe UI", 13),
        ).pack(fill="x", padx=18, pady=16)

        details = ctk.CTkFrame(self.liste, fg_color="transparent")
        details.pack(fill="x", padx=8, pady=(4, 8))
        details.grid_columnconfigure(0, weight=1, uniform="ki_details")
        details.grid_columnconfigure(1, weight=1, uniform="ki_details")
        skill_daten = haeufigkeiten([skill for job in jobs for skill in job.ki_skills], limit=6)
        offene_daten = haeufigkeiten(
            [punkt for job in jobs for punkt in (job.ki_offene_punkte or job.ki_risiken)],
            limit=6,
        )
        self._balkendiagramm(
            details,
            0,
            "Haeufige Anforderungen",
            skill_daten,
            FARBE_ERFOLG,
            "Keine wiederkehrenden Anforderungen erkannt.",
        )
        self._balkendiagramm(
            details,
            1,
            "Offene Pruefpunkte",
            offene_daten,
            FARBE_WARNUNG,
            "Keine offenen Pruefpunkte erkannt.",
        )

        beste_treffer = ki_beste_treffer(jobs)
        self._navigation_aktualisieren(len(beste_treffer))
        self._ki_abschnitt("Beste Treffer")
        self._ki_treffer_sortierleiste_anzeigen(len(beste_treffer))
        for job in self._jobs_der_seite(self.job_service.suchergebnisse_sortieren(beste_treffer, self.analyse_treffer_sortierung)):
            self._ki_treffer_karte(job)

        self._ki_abschnitt("Hinweis zur Datenqualitaet")
        ctk.CTkLabel(
            self.liste,
            text=(
                "Einige Provider liefern nur gekuerzte Stellenbeschreibungen. "
                "Die KI-Auswertung behandelt fehlende Details deshalb als offene Punkte, nicht automatisch als schlechte Stelle."
            ),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", padx=12, pady=(2, 10))

    def _ki_analyse_setup_anzeigen(self):
        if not self.normale_suchergebnisse:
            self.analyse_normale_jobs.set(False)
        if not self.ki_suchergebnisse:
            self.analyse_ki_jobs.set(False)

        karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.pack(fill="x", padx=8, pady=(0, 12))
        self.einleitung_ziele["analyse_setup"] = karte
        karte.grid_columnconfigure(0, weight=1)
        karte.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            karte,
            text="Analyse zusammenstellen",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            karte,
            text="Trefferquellen auswaehlen und festlegen, welche persoenlichen Daten die lokale KI verwenden darf.",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
            wraplength=940,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

        normale_checkbox = ctk.CTkCheckBox(
            karte,
            text=f"Normale Jobsuche  ({len(self.normale_suchergebnisse)} Treffer)",
            variable=self.analyse_normale_jobs,
            command=self._analyseauswahl_geaendert,
        )
        normale_checkbox.grid(row=2, column=0, sticky="w", padx=18, pady=6)
        if not self.normale_suchergebnisse:
            normale_checkbox.configure(state="disabled")

        ki_checkbox = ctk.CTkCheckBox(
            karte,
            text=f"KI-Jobsuche  ({len(self.ki_suchergebnisse)} Treffer)",
            variable=self.analyse_ki_jobs,
            command=self._analyseauswahl_geaendert,
        )
        ki_checkbox.grid(row=2, column=1, sticky="w", padx=18, pady=6)
        if not self.ki_suchergebnisse:
            ki_checkbox.configure(state="disabled")

        profil_namen = self._nutzerprofil_namen()
        profil_auswahl = self._analyseprofil_name()
        if not profil_auswahl and profil_namen:
            profil_auswahl = profil_namen[0]
            self.analyse_nutzerprofil_auswahl.set(profil_auswahl)
        profil_objekt = self.job_service.nutzerprofil_laden(profil_auswahl)
        profil = profil_objekt.daten() if profil_objekt is not None else {}
        profil_ausgefuellt = any(str(wert or "").strip() for wert in profil.values())
        ctk.CTkCheckBox(
            karte,
            text="Nutzerprofil in die Bewertung einbeziehen",
            variable=self.analyse_mit_nutzerprofil,
            command=self._analyseprofil_option_geaendert,
        ).grid(row=3, column=0, sticky="w", padx=18, pady=(10, 4))

        profilwahl = ctk.CTkFrame(karte, fg_color="transparent")
        profilwahl.grid(row=3, column=1, sticky="ew", padx=18, pady=(8, 4))
        profilwahl.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            profilwahl,
            text="Nutzerprofil fuer diese Analyse",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkComboBox(
            profilwahl,
            values=profil_namen or [KEIN_NUTZERPROFIL],
            variable=self.analyse_nutzerprofil_auswahl,
            command=self._analyseprofil_geaendert,
            state="readonly" if self.analyse_mit_nutzerprofil.get() and profil_namen else "disabled",
            height=36,
        ).grid(row=1, column=0, sticky="ew")

        profil_status = (
            f"Ausgewaehlt: {profil_auswahl} | Profil ist ausgefuellt"
            if profil_ausgefuellt
            else "Kein ausgefuelltes Profil ausgewaehlt."
        )
        ctk.CTkLabel(
            karte,
            text=profil_status,
            text_color=FARBE_ERFOLG if profil_ausgefuellt else FARBE_WARNUNG,
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 6))
        if not profil_ausgefuellt:
            ctk.CTkButton(
                karte,
                text="Nutzerprofil verwalten",
                command=self.zeige_nutzerprofil,
                width=180,
                height=34,
                fg_color=FARBE_KARTE_ZWEI,
                border_width=1,
                border_color=FARBE_RAND,
                text_color=("gray15", "gray90"),
                hover_color=FARBE_RAND,
            ).grid(row=4, column=1, sticky="e", padx=18, pady=(4, 6))

        ctk.CTkLabel(
            karte,
            text=self._ki_kriterien_kurztext(),
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
            wraplength=700,
        ).grid(row=5, column=0, sticky="ew", padx=18, pady=(10, 16))
        ctk.CTkButton(
            karte,
            text="Kriterien bearbeiten",
            command=self._ki_kriterien_fenster_anzeigen,
            width=170,
            height=36,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_RAND,
        ).grid(row=5, column=1, sticky="e", padx=18, pady=(10, 16))

        aktionsleiste = ctk.CTkFrame(karte, fg_color=FARBE_KARTE_ZWEI, corner_radius=0)
        aktionsleiste.grid(row=6, column=0, columnspan=2, sticky="ew")
        aktionsleiste.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            aktionsleiste,
            text=f"{len(self._ausgewaehlte_analyse_jobs())} eindeutige Treffer ausgewaehlt",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=14)
        self.ki_button = ctk.CTkButton(
            aktionsleiste,
            text="Analyse starten",
            command=self.ki_zusammenfassung_aktualisieren,
            width=180,
            height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color=FARBE_ERFOLG,
            hover_color=("#11734E", "#1D8C64"),
        )
        self.ki_button.grid(row=0, column=1, sticky="e", padx=18, pady=10)
        self._ki_button_status_aktualisieren()

        if self.analyse_hinweis:
            hinweis_farbe = FARBE_FEHLER if self.analyse_hinweis.startswith(("Fehler", "Bitte", "Es liegen")) else FARBE_TEXT_SEKUNDAER
            ctk.CTkLabel(
                karte,
                text=self.analyse_hinweis,
                text_color=hinweis_farbe,
                anchor="w",
                justify="left",
                wraplength=920,
            ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 12))

    def _ki_analyse_leerzustand(self):
        leer = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_WARNUNG,
            corner_radius=8,
        )
        leer.pack(fill="x", padx=8, pady=(2, 12))
        ctk.CTkLabel(
            leer,
            text="Keine Treffer fuer die Analyse vorhanden",
            font=("Segoe UI", 18, "bold"),
            text_color=FARBE_WARNUNG,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            leer,
            text="Starten Sie zuerst mindestens eine Suche. Danach stehen die Treffer hier getrennt zur Auswahl.",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=18, pady=(0, 12))
        aktionen = ctk.CTkFrame(leer, fg_color="transparent")
        aktionen.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(aktionen, text="Zur Jobsuche", command=self.zeige_suchergebnisse, width=150).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            aktionen,
            text="Zur KI-Jobsuche",
            command=self.zeige_ki_jobsuche,
            width=160,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            text_color=("gray15", "gray90"),
            hover_color=FARBE_RAND,
        ).pack(side="left")

    def _ki_ergebnis_status_anzeigen(self, jobs):
        status = self.job_service.ki_analyse_status()
        status_text = {
            "echt": "Lokale KI-Analyse abgeschlossen",
            "teilweise": "Teilweise lokale KI-Analyse",
            "technisch": "Technische Vorbewertung",
        }.get(status, "Analyseergebnis")
        quellen = []
        if "normal" in self.analyse_quellen_snapshot:
            quellen.append("normale Jobsuche")
        if "ki" in self.analyse_quellen_snapshot:
            quellen.append("KI-Jobsuche")
        basis = " + ".join(quellen) or "ausgewaehlte Treffer"
        profiltext = (
            f"mit Nutzerprofil: {self.analyse_profil_snapshot}"
            if self.analyse_profil_snapshot
            else "ohne Nutzerprofil"
        )
        text = f"{status_text} | {len(self.analyse_jobs)} Treffer beruecksichtigt | {len(jobs)} Top-Kandidaten | {basis} | {profiltext}"
        band = ctk.CTkFrame(self.liste, fg_color=FARBE_KARTE_ZWEI, corner_radius=6)
        band.pack(fill="x", padx=8, pady=(0, 12))
        ctk.CTkLabel(
            band,
            text=text,
            text_color=FARBE_ERFOLG if status == "echt" else FARBE_WARNUNG,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=940,
        ).pack(fill="x", padx=14, pady=10)

    def _ki_visuelle_uebersicht(self, jobs):
        durchschnitt = round(sum(job.ki_match_score for job in jobs) / len(jobs))
        top_score = max(job.ki_match_score for job in jobs)
        sehr_passend = sum(1 for job in jobs if job.ki_match_score >= 75)
        offene_punkte = sum(len(job.ki_offene_punkte or job.ki_risiken) for job in jobs)

        kennzahlen = ctk.CTkFrame(self.liste, fg_color="transparent")
        kennzahlen.pack(fill="x", padx=8, pady=(2, 12))
        for spalte in range(4):
            kennzahlen.grid_columnconfigure(spalte, weight=1, uniform="ki_kennzahlen")
        self._kennzahl_karte(kennzahlen, 0, "Durchschnitt", f"{durchschnitt}%", "KI-Match", FARBE_PRIMAER)
        self._kennzahl_karte(kennzahlen, 1, "Bester Treffer", f"{top_score}%", "Hoechster Match", FARBE_ERFOLG)
        self._kennzahl_karte(kennzahlen, 2, "Sehr passend", str(sehr_passend), "Ab 75 Prozent", FARBE_ERFOLG)
        self._kennzahl_karte(kennzahlen, 3, "Offene Punkte", str(offene_punkte), "Vor Bewerbung pruefen", FARBE_WARNUNG)

        verteilung = list(match_score_verteilung(jobs).items())
        diagramm = ctk.CTkFrame(self.liste, fg_color="transparent")
        diagramm.pack(fill="x", padx=8, pady=(0, 8))
        diagramm.grid_columnconfigure(0, weight=1, uniform="ki_diagramme")
        diagramm.grid_columnconfigure(1, weight=1, uniform="ki_diagramme")
        self._balkendiagramm(
            diagramm,
            0,
            "Match-Verteilung",
            verteilung,
            FARBE_PRIMAER,
            "Noch keine bewerteten Kandidaten.",
        )
        empfehlungen = haeufigkeiten([job.ki_empfehlung or "offen" for job in jobs], limit=5)
        self._balkendiagramm(
            diagramm,
            1,
            "Empfehlungen",
            empfehlungen,
            FARBE_ERFOLG,
            "Noch keine Empfehlungen vorhanden.",
        )

    def _ki_abschnitt(self, text):
        ctk.CTkLabel(self.liste, text=text, font=("Segoe UI", 18, "bold"), anchor="w").pack(
            fill="x", padx=8, pady=(14, 4)
        )

    def _ki_treffer_sortierleiste_anzeigen(self, anzahl):
        leiste = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE_ZWEI,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        leiste.pack(fill="x", padx=8, pady=(2, 8))
        ctk.CTkLabel(
            leiste,
            text=f"{anzahl} analysierte Treffer",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=14, pady=10)
        auswahl = ctk.CTkComboBox(
            leiste,
            values=ANALYSE_TREFFER_SORTIERUNGEN,
            command=self._analyse_treffer_sortierung_geaendert,
            state="readonly",
            width=270,
            height=34,
        )
        auswahl.set(self.analyse_treffer_sortierung)
        auswahl.pack(side="right", padx=10, pady=8)

        seitenleiste = ctk.CTkFrame(self.liste, fg_color="transparent")
        seitenleiste.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(seitenleiste, text="< Zurueck", width=110, command=self.vorherige_seite,
                      state="normal" if self.aktuelle_seite > 0 else "disabled").pack(side="left")
        ctk.CTkLabel(seitenleiste, text=f"Seite {self.aktuelle_seite + 1} / {max(1, self._seitenanzahl(anzahl))}").pack(side="left", expand=True)
        ctk.CTkButton(seitenleiste, text="Weiter >", width=110, command=self.naechste_seite,
                      state="normal" if self.aktuelle_seite + 1 < self._seitenanzahl(anzahl) else "disabled").pack(side="right")

    def _ki_treffer_karte(self, job):
        karte = ctk.CTkFrame(
            self.liste,
            fg_color=FARBE_KARTE,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.pack(fill="x", padx=8, pady=6)
        titel = self._anzeigetext(job.titel, "Stellentitel nicht angegeben")
        firma = self._anzeigetext(job.firma, "Firma nicht angegeben")
        ort = self._anzeigetext(job.ort, "Ort nicht angegeben")
        quelle = self._anzeigetext(job.quellen_text(), "Quelle unbekannt")
        ctk.CTkLabel(
            karte,
            text=f"{job.ki_match_score}/100 - {titel}",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
            wraplength=880,
        ).pack(fill="x", padx=12, pady=(10, 2))
        fortschritt = ctk.CTkProgressBar(
            karte,
            height=7,
            progress_color=self._match_farbe(job.ki_match_score),
        )
        fortschritt.pack(fill="x", padx=12, pady=(2, 6))
        fortschritt.set(max(0, min(100, job.ki_match_score)) / 100)
        ctk.CTkLabel(
            karte,
            text=f"{firma} | {ort} | Quelle: {quelle} | Empfehlung: {job.ki_empfehlung or 'offen'}",
            anchor="w",
            wraplength=900,
        ).pack(fill="x", padx=12, pady=2)
        for label, text in self._ki_treffer_textteile(job):
            ctk.CTkLabel(
                karte,
                text=f"{label}: {text}",
                anchor="w",
                justify="left",
                wraplength=880,
            ).pack(fill="x", padx=12, pady=2)

        self._job_beschreibung_anzeigen(karte, job)
        self._job_aktionen_anzeigen(karte, job)

    def _match_farbe(self, score):
        if score >= 75:
            return FARBE_ERFOLG
        if score >= 60:
            return FARBE_PRIMAER
        if score >= 30:
            return FARBE_WARNUNG
        return FARBE_FEHLER

    def _ki_gesamtfazit(self, jobs):
        zusammenfassung = self.job_service.ki_zusammenfassung()
        if zusammenfassung:
            return zusammenfassung
        return self._ki_fallback_gesamtfazit(jobs)

    def _ki_fallback_gesamtfazit(self, jobs):
        if not jobs:
            return "Noch keine KI-bewerteten Jobs vorhanden."

        bewertete_jobs = [job for job in jobs if job.hat_ki_daten()]
        if not bewertete_jobs:
            return "Noch keine KI-bewerteten Jobs vorhanden."

        top_jobs = sorted(bewertete_jobs, key=lambda job: job.ki_match_score, reverse=True)
        top = top_jobs[0]
        durchschnitt = round(sum(job.ki_match_score for job in bewertete_jobs) / len(bewertete_jobs))
        empfehlungen = {}
        for job in bewertete_jobs:
            empfehlung = (job.ki_empfehlung or "offen").strip()
            empfehlungen[empfehlung] = empfehlungen.get(empfehlung, 0) + 1

        haeufige_risiken = self._haeufige_ki_punkte([punkt for job in bewertete_jobs for punkt in job.ki_risiken])
        haeufige_skills = self._haeufige_ki_punkte([skill for job in bewertete_jobs for skill in job.ki_skills])
        empfehlungstext = ", ".join(f"{anzahl}x {name}" for name, anzahl in empfehlungen.items())
        saetze = [
            f"Die lokale KI hat {len(bewertete_jobs)} Treffer bewertet; der durchschnittliche Match liegt bei {durchschnitt}/100.",
            f"Der staerkste Treffer ist \"{top.titel}\" mit {top.ki_match_score}/100 und Empfehlung \"{top.ki_empfehlung or 'offen'}\".",
        ]
        if empfehlungstext:
            saetze.append(f"Empfehlungen: {empfehlungstext}.")
        if haeufige_risiken:
            saetze.append("Wichtigste offene Punkte: " + ", ".join(haeufige_risiken[:3]) + ".")
        if haeufige_skills:
            saetze.append("Haeufige Anforderungen: " + ", ".join(haeufige_skills[:5]) + ".")
        return " ".join(saetze)

    def _haeufige_ki_punkte(self, punkte):
        zaehler = {}
        reihenfolge = []
        for punkt in punkte:
            text = str(punkt or "").strip()
            if not text:
                continue
            if text not in zaehler:
                reihenfolge.append(text)
                zaehler[text] = 0
            zaehler[text] += 1
        return sorted(reihenfolge, key=lambda eintrag: (-zaehler[eintrag], reihenfolge.index(eintrag)))

    def _ki_treffer_textteile(self, job):
        teile = []
        if job.ki_zusammenfassung:
            teile.append(("Kurzfazit", job.ki_zusammenfassung))
        if job.ki_staerken:
            teile.append(("Warum interessant", ", ".join(job.ki_staerken[:3])))
        if job.ki_ausschluesse:
            teile.append(("Klare Ausschluesse", ", ".join(job.ki_ausschluesse[:3])))
        if job.ki_offene_punkte:
            teile.append(("Offene Pruefpunkte", ", ".join(job.ki_offene_punkte[:3])))
        elif job.ki_risiken:
            teile.append(("Offene Punkte", ", ".join(job.ki_risiken[:3])))
        if job.ki_skills:
            teile.append(("Anforderungen", ", ".join(job.ki_skills[:6])))
        if not teile:
            teile.append(("Kurzfazit", "Die lokale KI hat fuer diese Stelle keine Detailauswertung geliefert."))
        return teile

    def _ki_risiko_jobs(self, jobs):
        return [job for job in jobs if job.ki_risiken or job.ki_match_score < 45]

    def _ki_skill_uebersicht(self, jobs):
        gesehen = []
        for job in jobs:
            for skill in job.ki_skills:
                if skill not in gesehen:
                    gesehen.append(skill)
        return gesehen
    def _job_karte(self, job, kompakt):
        kartenfarbe = ("#FFF4F4", "#332029") if self.job_service.followup_status(job) == "ueberfaellig" else FARBE_KARTE
        karte = ctk.CTkFrame(
            self.liste,
            fg_color=kartenfarbe,
            border_width=1,
            border_color=FARBE_RAND,
            corner_radius=8,
        )
        karte.pack(fill="x", padx=5, pady=6)

        titel_text = self._anzeigetext(job.titel, "Stellentitel nicht angegeben")
        kopf = ctk.CTkFrame(karte, fg_color="transparent")
        kopf.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(kopf, text=titel_text, font=("Segoe UI", 18, "bold"), anchor="w", wraplength=760).pack(
            side="left", fill="x", expand=True
        )
        if not kompakt and self.ansicht == "bewerbungen":
            status_auswahl = ctk.CTkComboBox(
                kopf,
                values=[wert for wert in self.job_service.status_werte() if wert != "Neu"],
                command=lambda status, aktueller_job=job: self._bewerbungsstatus_direkt_aendern(aktueller_job, status),
                width=175,
                height=30,
            )
            status_auswahl.set(self.job_service.status_fuer_anzeige(job.status))
            status_auswahl.pack(side="right", padx=(12, 0))
        elif not kompakt:
            self._status_badge(kopf, self.job_service.status_fuer_anzeige(job.status)).pack(side="right", padx=(12, 0))

        firma = self._anzeigetext(job.firma, "Firma nicht angegeben")
        ort = self._anzeigetext(job.ort, "Ort nicht angegeben")
        quelle = self._anzeigetext(job.quellen_text(), "Quelle unbekannt")
        ctk.CTkLabel(
            karte,
            text=f"{firma}  |  {ort}  |  Quelle: {quelle}",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", padx=12, pady=2)
        if job.ki_suchbegriffe:
            ctk.CTkLabel(
                karte,
                text="KI-Suchbegriff: " + ", ".join(job.ki_suchbegriffe[:4]),
                text_color=FARBE_TEXT_SEKUNDAER,
                anchor="w",
                wraplength=900,
            ).pack(fill="x", padx=12, pady=(0, 2))

        infos = []
        if job.veroeffentlichungsdatum:
            infos.append(f"Veroeffentlicht: {job.veroeffentlichungsdatum}")
        if job.status and kompakt:
            infos.append(f"Status: {job.status}")
        if job.bewerbungsdatum:
            infos.append(f"Bewerbungsdatum: {job.bewerbungsdatum}")
        if job.eigene_bewertung:
            infos.append(f"Bewertung: {job.eigene_bewertung}/5")
        letzte_aenderung = self.job_service.letzte_statusaenderung_text(job)
        if letzte_aenderung and not kompakt:
            infos.append(f"Letzte Aenderung: {letzte_aenderung}")
        if infos:
            ctk.CTkLabel(karte, text=" | ".join(infos), anchor="w").pack(fill="x", padx=12, pady=2)

        ki_text = self._ki_job_text(job)
        if ki_text:
            ctk.CTkLabel(
                karte,
                text=ki_text,
                text_color=self._match_farbe(job.ki_match_score),
                anchor="w",
                wraplength=900,
            ).pack(fill="x", padx=12, pady=2)
            ki_balken = ctk.CTkProgressBar(
                karte,
                height=6,
                progress_color=self._match_farbe(job.ki_match_score),
            )
            ki_balken.pack(fill="x", padx=12, pady=(2, 5))
            ki_balken.set(max(0, min(100, job.ki_match_score)) / 100)

        followup_text = self.job_service.followup_text(job)
        if followup_text and not kompakt:
            ctk.CTkLabel(karte, text=followup_text, anchor="w", wraplength=760).pack(fill="x", padx=12, pady=2)

        self._job_beschreibung_anzeigen(karte, job)
        self._job_aktionen_anzeigen(karte, job)

    def _status_badge(self, parent, status):
        hintergrund, textfarbe = status_badge_farben(status)
        return ctk.CTkLabel(
            parent,
            text=str(status or "Neu"),
            fg_color=hintergrund,
            text_color=textfarbe,
            corner_radius=6,
            height=28,
            font=("Segoe UI", 11, "bold"),
        )

    def _bewerbungsstatus_direkt_aendern(self, job, status):
        status = self.job_service.status_fuer_anzeige(status)
        if status == self.job_service.status_fuer_anzeige(job.status):
            return
        aktualisiert = self.job_service.job_status_aendern(job, status)
        self._ergebnislisten_synchronisieren(aktualisiert)
        self.bewerbung_status_auswahl = status
        self.aktuelle_seite = 0
        logging.info("Bewerbungsstatus direkt geaendert: %s - %s", job.titel, status)
        self.zeige_jobs()
        scrollbare_liste_nach_oben(self.liste)

    def _job_beschreibung_anzeigen(self, karte, job):
        if not job.kurzbeschreibung:
            return
        beschreibung_schluessel = self._beschreibung_schluessel(job)
        aufgeklappt = self.beschreibung_status.ist_aufgeklappt(beschreibung_schluessel)
        label = ctk.CTkLabel(
            karte,
            text=beschreibung_vorschau(job.kurzbeschreibung, aufgeklappt),
            anchor="w",
            justify="left",
            wraplength=900,
        )
        label.pack(fill="x", padx=12, pady=2)
        if beschreibung_hat_mehr(job.kurzbeschreibung):
            button = ctk.CTkButton(
                karte,
                text="Weniger anzeigen" if aufgeklappt else "Mehr anzeigen",
                command=lambda schluessel=beschreibung_schluessel: self.beschreibung_umschalten(schluessel),
                width=140,
            )
            button.pack(anchor="w", padx=12, pady=(2, 0))
            self._beschreibungs_widgets.setdefault(beschreibung_schluessel, []).append((label, button, job.kurzbeschreibung))

    def _job_aktionen_anzeigen(self, karte, job):
        aktionen = ctk.CTkFrame(karte, fg_color="transparent")
        aktionen.pack(fill="x", padx=12, pady=(6, 10))
        ctk.CTkButton(
            aktionen,
            text="Details",
            command=lambda aktueller_job=job: self.detailansicht_oeffnen(aktueller_job),
            width=110,
        ).pack(side="left", padx=(0, 8))

        if job.link:
            ctk.CTkButton(
                aktionen,
                text="Link oeffnen",
                command=lambda url=job.link: self.link_oeffnen(url),
                width=120,
            ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            aktionen,
            text=favoriten_button_text(job),
            command=lambda aktueller_job=job: self.favorit_umschalten(aktueller_job),
            width=46,
        ).pack(side="left")

    def detailansicht_oeffnen(self, job):
        fenster = ctk.CTkToplevel(self.app)
        fenster.title("Stellendetails")
        fenster.geometry("760x720")
        fenster.transient(self.app)
        self._detailansicht_rendern(fenster, job)

    def _detailansicht_rendern(self, fenster, job):
        for element in fenster.winfo_children():
            element.destroy()
        inhalt = ctk.CTkScrollableFrame(fenster)
        inhalt.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(inhalt, text="Stellendetails", font=("Arial", 22, "bold"), anchor="w").pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(inhalt, text=f"Aktueller Status: {self.job_service.status_fuer_anzeige(job.status)}", font=("Arial", 15, "bold"), anchor="w").pack(
            fill="x", pady=(0, 8)
        )

        felder = {}
        self._detail_abschnitt(inhalt, "Stelle")
        for name, wert in [
            ("titel", job.titel),
            ("firma", job.firma),
            ("ort", job.ort),
            ("quelle", job.quelle),
            ("link", job.link),
            ("entfernung", job.entfernung),
            ("veroeffentlichungsdatum", job.veroeffentlichungsdatum),
            ("gehalt_min", job.gehalt_min),
            ("gehalt_max", job.gehalt_max),
            ("kategorie", job.kategorie),
        ]:
            felder[name] = self._detail_eingabe(inhalt, name, wert)

        felder["kurzbeschreibung"] = self._detail_text(
            inhalt,
            "kurzbeschreibung",
            beschreibung_lesbar(job.kurzbeschreibung),
            180,
        )

        self._detail_abschnitt(inhalt, "Bewerbung")
        for name, wert in [
            ("bewerbungsdatum", job.bewerbungsdatum),
            ("ansprechpartner", job.ansprechpartner),
            ("email", job.email),
            ("telefon", job.telefon),
            ("naechste_aktion", job.naechste_aktion),
            ("followup_datum", job.followup_datum),
            ("followup_uhrzeit", job.followup_uhrzeit),
        ]:
            felder[name] = self._detail_eingabe(inhalt, name, wert)

        felder["status"] = self._detail_auswahl(
            inhalt,
            "status",
            self.job_service.status_werte(),
            self.job_service.status_fuer_anzeige(job.status),
        )
        felder["eigene_bewertung"] = self._detail_auswahl(
            inhalt,
            "eigene_bewertung",
            ["0", "1", "2", "3", "4", "5"],
            str(job.eigene_bewertung),
        )
        felder["notizen"] = self._detail_text(inhalt, "notizen", job.notizen, 120)
        felder["gehaltsnotizen"] = self._detail_text(inhalt, "gehaltsnotizen", job.gehaltsnotizen, 80)
        felder["followup_erledigt"] = self._detail_auswahl(
            inhalt,
            "followup_erledigt",
            ["offen", "erledigt"],
            "erledigt" if job.followup_erledigt else "offen",
        )

        if job.hat_ki_daten():
            self._detail_abschnitt(inhalt, "Lokale KI-Auswertung")
            ctk.CTkLabel(
                inhalt,
                text=self._ki_detail_text(job),
                anchor="w",
                justify="left",
                wraplength=690,
            ).pack(fill="x", pady=(2, 8))

        self._detail_abschnitt(inhalt, "Bewerbungsverlauf")
        self._statusverlauf_anzeigen(inhalt, job, fenster)

        aktionen = ctk.CTkFrame(inhalt, fg_color="transparent")
        aktionen.pack(fill="x", pady=(14, 0))

        ctk.CTkButton(
            aktionen,
            text="Speichern",
            command=lambda: self.details_speichern(job, felder, fenster),
            width=120,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            aktionen,
            text="Aus Bewerbungen entfernen",
            command=lambda: self.bewerbung_entfernen(job, fenster),
            width=190,
        ).pack(side="left", padx=(0, 8))

        if job.link:
            ctk.CTkButton(
                aktionen,
                text="Link oeffnen",
                command=lambda url=job.link: self.link_oeffnen(url),
                width=120,
            ).pack(side="left")

    def _detail_abschnitt(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Arial", 17, "bold"), anchor="w").pack(fill="x", pady=(16, 4))

    def _statusverlauf_anzeigen(self, parent, job, fenster):
        if not job.statusverlauf:
            ctk.CTkLabel(parent, text="Noch keine Statusaenderungen gespeichert.", anchor="w").pack(
                fill="x", pady=(2, 6)
            )
            return

        for eintrag in job.statusverlauf:
            zeile = ctk.CTkFrame(parent, fg_color="transparent")
            zeile.pack(fill="x", pady=3)

            datum = ctk.CTkEntry(zeile, width=105)
            datum.insert(0, eintrag.get("datum", ""))
            datum.pack(side="left", padx=(0, 6))

            uhrzeit = ctk.CTkEntry(zeile, width=70)
            uhrzeit.insert(0, eintrag.get("uhrzeit", ""))
            uhrzeit.pack(side="left", padx=(0, 6))

            status = ctk.CTkComboBox(zeile, values=[wert for wert in self.job_service.status_werte() if wert != "Neu"], width=160)
            status.set(self.job_service.status_fuer_anzeige(eintrag.get("status", "Gespeichert")))
            status.pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                zeile,
                text="Aendern",
                command=lambda eintrag_id=eintrag.get("id", ""), datum=datum, uhrzeit=uhrzeit, status=status: (
                    self.statusverlauf_bearbeiten(job, eintrag_id, datum.get(), uhrzeit.get(), status.get(), fenster)
                ),
                width=85,
            ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                zeile,
                text="Loeschen",
                command=lambda eintrag_id=eintrag.get("id", ""): self.statusverlauf_loeschen(job, eintrag_id, fenster),
                width=85,
            ).pack(side="left")

    def _detail_eingabe(self, parent, label, wert):
        ctk.CTkLabel(parent, text=self._feld_label(label), anchor="w").pack(fill="x", pady=(8, 2))
        eingabe = ctk.CTkEntry(parent)
        eingabe.insert(0, wert or "")
        eingabe.pack(fill="x")
        return eingabe

    def _detail_auswahl(self, parent, label, werte, wert):
        ctk.CTkLabel(parent, text=self._feld_label(label), anchor="w").pack(fill="x", pady=(8, 2))
        auswahl = ctk.CTkComboBox(parent, values=werte)
        auswahl.set(wert if wert in werte else werte[0])
        auswahl.pack(fill="x")
        return auswahl

    def _detail_text(self, parent, label, wert, hoehe):
        ctk.CTkLabel(parent, text=self._feld_label(label), anchor="w").pack(fill="x", pady=(8, 2))
        textfeld = ctk.CTkTextbox(parent, height=hoehe)
        textfeld.insert("1.0", wert or "")
        if ist_detailfeld_schreibgeschuetzt(label):
            textfeld_schreibgeschuetzt_machen(textfeld)
        textfeld.pack(fill="x")
        return textfeld

    def details_speichern(self, job, felder, fenster):
        alter_schluessel = job_schluessel(job)
        details = {}
        for name, feld in felder.items():
            if ist_detailfeld_schreibgeschuetzt(name):
                continue
            if isinstance(feld, ctk.CTkTextbox):
                details[name] = feld.get("1.0", "end").strip()
            else:
                details[name] = feld.get()
        details["followup_erledigt"] = details.get("followup_erledigt") == "erledigt"
        aktualisiert = self.job_service.job_details_speichern(job, details)
        self._ergebnislisten_synchronisieren(aktualisiert, alter_schluessel)
        logging.info("Jobdetails gespeichert: %s", job.titel)
        self.zeige_jobs()
        self._detailansicht_rendern(fenster, job)

    def statusverlauf_bearbeiten(self, job, eintrag_id, datum, uhrzeit, status, fenster):
        aktualisiert = self.job_service.statusverlauf_bearbeiten(job, eintrag_id, datum, uhrzeit, status)
        self._ergebnislisten_synchronisieren(aktualisiert)
        logging.info("Statusverlauf bearbeitet: %s", job.titel)
        self.zeige_jobs()
        self._detailansicht_rendern(fenster, job)

    def statusverlauf_loeschen(self, job, eintrag_id, fenster):
        aktualisiert = self.job_service.statusverlauf_loeschen(job, eintrag_id)
        self._ergebnislisten_synchronisieren(aktualisiert)
        logging.info("Statusverlauf geloescht: %s", job.titel)
        self.zeige_jobs()
        self._detailansicht_rendern(fenster, job)

    def favorit_umschalten(self, job):
        war_favorit = job.favorit
        aktualisiert = self.job_service.favorit_umschalten(job)
        self._ergebnislisten_synchronisieren(aktualisiert)
        logging.info("Favorit umgeschaltet: %s", job.titel)
        self.zeige_jobs()
        if war_favorit:
            self.entfernung_meldung_anzeigen()

    def bewerbung_entfernen(self, job, fenster):
        aktualisiert = self.job_service.job_entfernen(job)
        self._ergebnislisten_synchronisieren(aktualisiert)
        logging.info("Job aus Bewerbungen entfernt: %s", job.titel)
        self.zeige_jobs()
        self._detailansicht_rendern(fenster, job)
        self.entfernung_meldung_anzeigen()

    def entfernung_meldung_anzeigen(self):
        if self.undo_timer_id:
            self.app.after_cancel(self.undo_timer_id)
        if not self.undo_frame.winfo_ismapped():
            self.undo_frame.pack(fill="x", padx=20, pady=(0, 8))
        self.undo_text.configure(text="Stelle entfernt -")
        self.undo_timer_id = self.app.after(8000, self.entfernung_meldung_ausblenden)

    def entfernung_meldung_ausblenden(self):
        self.undo_timer_id = None
        self.undo_frame.pack_forget()

    def entfernung_rueckgaengig(self):
        job = self.job_service.entfernung_rueckgaengig()
        if job:
            self._ergebnislisten_synchronisieren(job)
            logging.info("Entfernung rueckgaengig gemacht: %s", job.titel)
        self.entfernung_meldung_ausblenden()
        self.zeige_jobs()

    def _ergebnislisten_synchronisieren(self, aktualisierter_job, alter_schluessel=None):
        if aktualisierter_job is None:
            return
        schluessel = job_schluessel(aktualisierter_job)
        alter_schluessel = alter_schluessel or schluessel
        gesehen = set()
        for sammlung in (self.jobs, self.normale_suchergebnisse, self.ki_suchergebnisse, self.analyse_jobs):
            for job in sammlung:
                if id(job) in gesehen:
                    continue
                gesehen.add(id(job))
                if job_schluessel(job) not in (schluessel, alter_schluessel):
                    continue
                if job is aktualisierter_job:
                    continue
                for feld in (
                    "titel", "firma", "ort", "quelle", "link", "entfernung", "kurzbeschreibung",
                    "veroeffentlichungsdatum", "quellen", "gehalt_min", "gehalt_max", "kategorie",
                ):
                    wert = getattr(aktualisierter_job, feld)
                    setattr(job, feld, list(wert) if isinstance(wert, list) else wert)
                job.verwaltungsdaten_aus(aktualisierter_job)

    def _scrollposition_lesen(self):
        canvas = getattr(getattr(self, "liste", None), "_parent_canvas", None)
        if canvas is None:
            return 0.0
        try:
            return float(canvas.yview()[0])
        except Exception:
            return 0.0

    def _ansichts_zustand_sichern(self, scrollposition=None):
        if not hasattr(self, "liste"):
            return
        zustand = {
            "seite": self.aktuelle_seite,
            "scrollposition": self._scrollposition_lesen() if scrollposition is None else scrollposition,
        }
        if self.ansicht == "ki_suche":
            zustand["suchbereich"] = self.ki_suchbereich.get()
        elif self.ansicht == "bewerbungen":
            zustand["status"] = self.bewerbung_status_auswahl
        self.ansichts_zustaende[self.ansicht] = zustand

    def _ansicht_wechseln(self, ansicht):
        if ansicht != self.ansicht:
            self._ansichts_zustand_sichern()
        zustand = self.ansichts_zustaende.get(ansicht, {})
        self.ansicht = ansicht
        self.aktuelle_seite = max(0, int(zustand.get("seite", 0) or 0))
        if ansicht == "ki_suche":
            self.ki_suchbereich.set(zustand.get("suchbereich", self.ki_suchbereich.get()))
        elif ansicht == "bewerbungen":
            self.bewerbung_status_auswahl = zustand.get("status", self.bewerbung_status_auswahl)
        self.zeige_jobs()
        scrollposition = float(zustand.get("scrollposition", 0.0) or 0.0)
        if scrollposition:
            canvas = getattr(self.liste, "_parent_canvas", None)
            if canvas is not None:
                self.app.after_idle(lambda: canvas.yview_moveto(scrollposition))

    def _ansichts_zustand_zuruecksetzen(self, ansicht):
        self.ansichts_zustaende.pop(ansicht, None)

    def zeige_dashboard(self):
        self._ansicht_wechseln("dashboard")

    def zeige_suchergebnisse(self):
        self._ansicht_wechseln("suche")

    def zeige_ki_jobsuche(self):
        self._ansicht_wechseln("ki_suche")

    def zeige_bewerbungen(self):
        self._ansicht_wechseln("bewerbungen")

    def zeige_ki_zusammenfassung(self):
        self._ansicht_wechseln("ki")

    def zur_ki_analyse(self, quelle=None):
        ausgang = quelle or self.aktuelle_ergebnisquelle
        if ausgang == "ki" and self.ki_suchergebnisse:
            self.analyse_normale_jobs.set(False)
            self.analyse_ki_jobs.set(True)
        elif ausgang == "normal" and self.normale_suchergebnisse:
            self.analyse_normale_jobs.set(True)
            self.analyse_ki_jobs.set(False)
        self.analyse_hinweis = ""
        self.zeige_ki_zusammenfassung()

    def zeige_nutzerprofil(self):
        self._ansicht_wechseln("profil")

    def zeige_einstellungen(self):
        self._ansicht_wechseln("einstellungen")

    def zeige_gespeicherte_stellen(self):
        self.zeige_bewerbungen()

    def filter_anwenden(self):
        self.ansicht = "bewerbungen"
        self.aktuelle_seite = 0
        self._ansichts_zustand_zuruecksetzen("bewerbungen")
        self.zeige_jobs()

    def _treffer_sortierleiste_aktualisieren(self):
        wert = self.ki_treffer_sortierung if self.ansicht == "ki_suche" else self.normale_treffer_sortierung
        self.treffer_sortierung_combo.configure(values=TREFFER_SORTIERUNGEN)
        self.treffer_sortierung_combo.set(wert)

    def _treffer_sortierung_geaendert(self, wert):
        if wert not in TREFFER_SORTIERUNGEN:
            return
        if self.ansicht == "ki_suche":
            self.ki_treffer_sortierung = wert
        else:
            self.normale_treffer_sortierung = wert
        self.aktuelle_seite = 0
        self._ansichts_zustand_zuruecksetzen(self.ansicht)
        self.zeige_jobs()
        scrollbare_liste_nach_oben(self.liste)

    def _analyse_treffer_sortierung_geaendert(self, wert):
        if wert not in ANALYSE_TREFFER_SORTIERUNGEN:
            return
        canvas = getattr(self.liste, "_parent_canvas", None)
        scrollposition = canvas.yview()[0] if canvas is not None else 0.0
        self.analyse_treffer_sortierung = wert
        self.aktuelle_seite = 0
        self.zeige_jobs()
        if canvas is not None:
            self.app.after_idle(lambda: canvas.yview_moveto(scrollposition))

    def _quellen_filter_aktualisieren(self):
        aktuelle_auswahl = self.quellen_filter.get()
        werte = ["Alle"] + self.job_service.quellen_werte()
        self.quellen_filter.configure(values=werte)
        self.quellen_filter.set(aktuelle_auswahl if aktuelle_auswahl in werte else "Alle")

    def _anzeigetext(self, wert, fallback):
        text = str(wert).strip() if wert is not None else ""
        if not text or text.lower() == "none":
            return fallback
        return text

    def _beschreibung_kuerzen(self, text):
        beschreibung = " ".join(str(text).split())
        if len(beschreibung) <= 280:
            return beschreibung
        return f"{beschreibung[:277]}..."

    def _beschreibung_schluessel(self, job):
        return repr(job_schluessel(job))

    def beschreibung_umschalten(self, schluessel):
        self.beschreibung_status.umschalten(schluessel)
        aufgeklappt = self.beschreibung_status.ist_aufgeklappt(schluessel)
        for label, button, text in self._beschreibungs_widgets.get(schluessel, []):
            label.configure(text=beschreibung_vorschau(text, aufgeklappt))
            button.configure(text="Weniger anzeigen" if aufgeklappt else "Mehr anzeigen")

    def _feld_label(self, name):
        labels = {
            "titel": "Titel",
            "firma": "Firma",
            "ort": "Ort",
            "quelle": "Quelle",
            "link": "Link zur Stelle",
            "entfernung": "Entfernung",
            "veroeffentlichungsdatum": "Veroeffentlichungsdatum",
            "bewerbungsdatum": "Bewerbungsdatum",
            "ansprechpartner": "Ansprechpartner",
            "email": "E-Mail",
            "telefon": "Telefon",
            "naechste_aktion": "Naechste Aktion",
            "followup_datum": "Follow-up-Datum",
            "followup_uhrzeit": "Follow-up-Uhrzeit",
            "followup_erledigt": "Follow-up-Status",
            "status": "Status",
            "eigene_bewertung": "Eigene Bewertung (0-5)",
            "kurzbeschreibung": "Vollstaendige Stelleninformationen",
            "notizen": "Notizen",
            "gehaltsnotizen": "Gehaltsnotizen",
            "gehalt_min": "Gehaltsuntergrenze",
            "gehalt_max": "Gehaltsobergrenze",
            "kategorie": "Kategorie",
        }
        return labels.get(name, name)

    def _ki_kriterien_fenster_anzeigen(self):
        self.ki_kriterien_fenster.deiconify()
        self.ki_kriterien_fenster.lift()
        self.ki_kriterien_fenster.focus_force()

    def _ki_kriterien_speichern_und_schliessen(self):
        self.settings["ki_kriterien"] = self._ki_kriterien()
        self.job_service.settings_speichern(self._aktuelle_settings())
        self.ki_kriterien_fenster.withdraw()
        if self.ki_kriterien_snapshot is not None:
            self.ki_zusammenfassung_veraltet = self._analyse_einstellungen_geaendert()
        if self.ansicht == "ki":
            self.zeige_jobs()

    def _ki_kriterien_kurztext(self):
        kriterien = self._ki_kriterien()
        beschreibungen = []
        bool_labels = {
            "homeoffice": "Homeoffice wichtig",
            "teilzeit": "Teilzeit",
            "vollzeit": "Vollzeit",
            "wohnortnaehe": "Wohnortnaehe",
        }
        for name, label in bool_labels.items():
            if kriterien.get(name):
                beschreibungen.append(label)
        remote = str(kriterien.get("remote_modus", "egal") or "egal")
        if remote != "egal":
            beschreibungen.append(f"Remote: {remote}")
        text_labels = {
            "max_pendeln": "Pendeln",
            "arbeitszeit": "Arbeitszeit",
            "mindestgehalt": "Mindestgehalt",
            "wunschgehalt": "Wunschgehalt",
            "gehaltsmodell": "Gehaltsmodell",
            "gewuenschte_taetigkeiten": "Taetigkeiten",
            "ausschlusskriterien": "Ausschluesse",
            "freitext": "weitere Kriterien",
            "prioritaet": "Prioritaet",
        }
        for name, label in text_labels.items():
            if str(kriterien.get(name, "") or "").strip():
                beschreibungen.append(label)
        if not beschreibungen:
            return "Bewertungskriterien: keine zusaetzlichen Kriterien festgelegt"
        sichtbar = ", ".join(beschreibungen[:7])
        rest = len(beschreibungen) - 7
        return f"Bewertungskriterien: {sichtbar}" + (f" und {rest} weitere" if rest > 0 else "")

    def _ki_kriterien_erstellen(self, parent):
        gespeicherte_kriterien = self.settings.get("ki_kriterien")
        if not isinstance(gespeicherte_kriterien, dict):
            gespeicherte_kriterien = {}

        rahmen = ctk.CTkFrame(parent, fg_color="transparent")
        rahmen.pack(fill="x", padx=18, pady=16)

        ctk.CTkLabel(
            rahmen,
            text="Bewertungskriterien",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            rahmen,
            text="Diese Kriterien gelten fuer den naechsten manuellen Analyselauf.",
            text_color=FARBE_TEXT_SEKUNDAER,
            anchor="w",
        ).pack(fill="x", pady=(2, 12))

        optionen = ctk.CTkFrame(rahmen, fg_color="transparent")
        optionen.pack(fill="x", pady=(0, 12))
        optionen.grid_columnconfigure(0, weight=1)
        optionen.grid_columnconfigure(1, weight=1)

        for index, (name, text) in enumerate([
            ("homeoffice", "Homeoffice/Remote wichtig"),
            ("teilzeit", "Teilzeit passend"),
            ("vollzeit", "Vollzeit passend"),
            ("wohnortnaehe", "Wohnortnaehe wichtig"),
        ]):
            variable = ctk.BooleanVar(value=bool(gespeicherte_kriterien.get(name, False)))
            self.ki_kriterien_variablen[name] = variable
            ctk.CTkCheckBox(
                optionen,
                text=text,
                variable=variable,
                command=self._ki_kriterien_geaendert,
            ).grid(row=index // 2, column=index % 2, sticky="w", pady=5)

        details = ctk.CTkFrame(rahmen, fg_color="transparent")
        details.pack(fill="x")
        for spalte in range(4):
            details.grid_columnconfigure(spalte, weight=1)

        ctk.CTkLabel(details, text="Remote-Modus", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.ki_remote_modus = ctk.CTkComboBox(
            details,
            values=["egal", "wichtig", "zwingend"],
            width=130,
            height=36,
            command=lambda _wert: self._ki_kriterien_geaendert(),
        )
        remote_modus = str(gespeicherte_kriterien.get("remote_modus", "egal") or "egal")
        self.ki_remote_modus.set(remote_modus if remote_modus in ["egal", "wichtig", "zwingend"] else "egal")
        self.ki_remote_modus.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))

        ctk.CTkLabel(details, text="Maximales Pendeln", anchor="w").grid(
            row=0, column=1, sticky="w", padx=(0, 10)
        )
        self.ki_max_pendeln = ctk.CTkEntry(
            details,
            placeholder_text="z. B. 30 Minuten",
            width=170,
            height=36,
        )
        self.ki_max_pendeln.insert(0, str(gespeicherte_kriterien.get("max_pendeln", "") or ""))
        self.ki_max_pendeln.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_max_pendeln.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Arbeitszeit", anchor="w").grid(
            row=0, column=2, sticky="w", padx=(0, 10)
        )
        self.ki_arbeitszeit = ctk.CTkEntry(
            details,
            placeholder_text="z. B. vormittags, max. 30 Stunden, keine Schicht",
            height=36,
        )
        self.ki_arbeitszeit.insert(0, str(gespeicherte_kriterien.get("arbeitszeit", "") or ""))
        self.ki_arbeitszeit.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_arbeitszeit.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Prioritaet", anchor="w").grid(
            row=0, column=3, sticky="w"
        )
        self.ki_prioritaet = ctk.CTkComboBox(
            details,
            values=["Ausgewogen", "Gehalt wichtiger", "Wohnort wichtiger", "Remote/Teilzeit wichtiger", "Aufgabeninhalt wichtiger"],
            height=36,
            command=lambda _wert: self._ki_kriterien_geaendert(),
        )
        prioritaet = str(gespeicherte_kriterien.get("prioritaet", "Ausgewogen") or "Ausgewogen")
        if prioritaet not in ["Ausgewogen", "Gehalt wichtiger", "Wohnort wichtiger", "Remote/Teilzeit wichtiger", "Aufgabeninhalt wichtiger"]:
            prioritaet = "Ausgewogen"
        self.ki_prioritaet.set(prioritaet)
        self.ki_prioritaet.grid(row=1, column=3, sticky="ew", pady=(4, 0))

        ctk.CTkLabel(details, text="Mindestgehalt", anchor="w").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        self.ki_mindestgehalt = ctk.CTkEntry(details, placeholder_text="z. B. 30000 EUR/Jahr", height=36)
        self.ki_mindestgehalt.insert(0, str(gespeicherte_kriterien.get("mindestgehalt", "") or ""))
        self.ki_mindestgehalt.grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_mindestgehalt.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Wunschgehalt", anchor="w").grid(
            row=2, column=1, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        self.ki_wunschgehalt = ctk.CTkEntry(details, placeholder_text="optional", height=36)
        self.ki_wunschgehalt.insert(0, str(gespeicherte_kriterien.get("wunschgehalt", "") or ""))
        self.ki_wunschgehalt.grid(row=3, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_wunschgehalt.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Gehaltsmodell", anchor="w").grid(
            row=2, column=2, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        self.ki_gehaltsmodell = ctk.CTkEntry(details, placeholder_text="z. B. brutto/Jahr, Stundenlohn", height=36)
        self.ki_gehaltsmodell.insert(0, str(gespeicherte_kriterien.get("gehaltsmodell", "") or ""))
        self.ki_gehaltsmodell.grid(row=3, column=2, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_gehaltsmodell.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Gewuenschte Taetigkeiten", anchor="w").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=(0, 10), pady=(12, 0)
        )
        self.ki_gewuenschte_taetigkeiten = ctk.CTkEntry(
            details,
            placeholder_text="z. B. Verwaltung, Organisation, Weiterbildung, Kundenkontakt",
            height=36,
        )
        self.ki_gewuenschte_taetigkeiten.insert(0, str(gespeicherte_kriterien.get("gewuenschte_taetigkeiten", "") or ""))
        self.ki_gewuenschte_taetigkeiten.grid(row=5, column=0, columnspan=2, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.ki_gewuenschte_taetigkeiten.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Ausschlusskriterien", anchor="w").grid(
            row=4, column=2, columnspan=2, sticky="w", pady=(12, 0)
        )
        self.ki_ausschlusskriterien = ctk.CTkEntry(
            details,
            placeholder_text="z. B. kein Vertrieb, keine Schichtarbeit, kein Aussendienst",
            height=36,
        )
        self.ki_ausschlusskriterien.insert(0, str(gespeicherte_kriterien.get("ausschlusskriterien", "") or ""))
        self.ki_ausschlusskriterien.grid(row=5, column=2, columnspan=2, sticky="ew", pady=(4, 0))
        self.ki_ausschlusskriterien.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkLabel(details, text="Weitere persoenliche Kriterien", anchor="w").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(12, 0)
        )
        self.ki_kriterien_freitext = ctk.CTkEntry(
            details,
            placeholder_text="Weitere Kriterien, z. B. ruhiges Buero, wenig Telefon, Weiterbildung",
            height=36,
        )
        self.ki_kriterien_freitext.insert(0, str(gespeicherte_kriterien.get("freitext", "") or ""))
        self.ki_kriterien_freitext.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.ki_kriterien_freitext.bind("<KeyRelease>", lambda _event: self._ki_kriterien_geaendert())

        ctk.CTkButton(
            rahmen,
            text="Kriterien uebernehmen",
            command=self._ki_kriterien_speichern_und_schliessen,
            width=190,
            height=40,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="e", pady=(14, 0))

    def _ki_kriterien(self):
        kriterien = {
            "homeoffice": self._ki_bool_kriterium("homeoffice"),
            "teilzeit": self._ki_bool_kriterium("teilzeit"),
            "vollzeit": self._ki_bool_kriterium("vollzeit"),
            "wohnortnaehe": self._ki_bool_kriterium("wohnortnaehe"),
            "remote_modus": self._widget_text("ki_remote_modus", "egal"),
            "max_pendeln": self._widget_text("ki_max_pendeln"),
            "freitext": self._widget_text("ki_kriterien_freitext"),
        }
        optionale_felder = {
            "arbeitszeit": self._widget_text("ki_arbeitszeit"),
            "mindestgehalt": self._widget_text("ki_mindestgehalt"),
            "wunschgehalt": self._widget_text("ki_wunschgehalt"),
            "gehaltsmodell": self._widget_text("ki_gehaltsmodell"),
            "gewuenschte_taetigkeiten": self._widget_text("ki_gewuenschte_taetigkeiten"),
            "ausschlusskriterien": self._widget_text("ki_ausschlusskriterien"),
        }
        for name, wert in optionale_felder.items():
            if wert:
                kriterien[name] = wert
        prioritaet = self._widget_text("ki_prioritaet", "Ausgewogen")
        if prioritaet and prioritaet != "Ausgewogen":
            kriterien["prioritaet"] = prioritaet
        profil = self._nutzerprofil()
        if any(str(wert or "").strip() for wert in profil.values()):
            kriterien["nutzerprofil"] = profil
        return kriterien

    def _ki_bool_kriterium(self, name):
        variable = self.ki_kriterien_variablen.get(name)
        return bool(variable.get()) if variable is not None else False

    def _widget_text(self, attribut, standard=""):
        widget = getattr(self, attribut, None)
        if widget is None:
            return standard
        return str(widget.get() or "").strip()

    def _ki_kriterien_geaendert(self):
        if self.ki_kriterien_snapshot is not None:
            self.ki_zusammenfassung_veraltet = self._analyse_einstellungen_geaendert()
        self.ki_status.configure(text=self._ki_zusammenfassung_text())
        self._ki_button_status_aktualisieren()

    def _ki_button_status_aktualisieren(self):
        analyse_status = self.job_service.ki_analyse_status()
        ausgewaehlte_jobs = self._ausgewaehlte_analyse_jobs()
        hat_ki_daten = any(job.hat_ki_daten() for job in self.analyse_jobs)
        status, _anzeigen_status = ki_aktionszustand(
            self.suche_laeuft,
            self.ki_laeuft,
            bool(ausgewaehlte_jobs),
            analyse_status,
            hat_ki_daten,
        )

        button = getattr(self, "ki_button", None)
        if self._widget_existiert(button):
            if self.ki_laeuft and self._abbruch_angefordert("ki_analyse_abbruch"):
                button.configure(
                    state="disabled",
                    text="Analyse wird beendet...",
                    command=self.ki_analyse_abbrechen,
                    fg_color=FARBE_FEHLER,
                    hover_color=("#A72F40", "#C94A5A"),
                )
            elif self.ki_laeuft:
                button.configure(
                    state="normal",
                    text="Analyse abbrechen",
                    command=self.ki_analyse_abbrechen,
                    fg_color=FARBE_FEHLER,
                    hover_color=("#A72F40", "#C94A5A"),
                )
            else:
                button.configure(
                    state=status[0],
                    text=status[1],
                    command=self.ki_zusammenfassung_aktualisieren,
                    fg_color=FARBE_ERFOLG,
                    hover_color=("#11734E", "#1D8C64"),
                )
        self._suchstatusleiste_aktualisieren()


    def _provider_checkboxes_erstellen(self):
        gespeicherte_provider = self.settings.get("provider")
        if not isinstance(gespeicherte_provider, list):
            gespeicherte_provider = self.job_service.verfuegbare_provider_namen()
        else:
            gespeicherte_provider = list(gespeicherte_provider)
        try:
            provider_katalog_version = int(self.settings.get("provider_katalog_version", 1))
        except (TypeError, ValueError):
            provider_katalog_version = 1
        if provider_katalog_version < 3:
            for neuer_provider in ("websuche", "karriereseiten", "arbeitnow"):
                if neuer_provider not in gespeicherte_provider:
                    gespeicherte_provider.append(neuer_provider)
        self.settings["provider_katalog_version"] = 3

        verfuegbare_namen = set(self.job_service.verfuegbare_provider_namen())
        for provider in self.job_service.provider_status():
            name = provider["name"]
            if name not in ("arbeitsagentur", "jooble", "adzuna", "websuche", "karriereseiten", "arbeitnow"):
                continue
            aktiv = bool(provider["aktiv"])
            variable = ctk.BooleanVar(value=aktiv and name in gespeicherte_provider)
            self.provider_variablen[name] = variable
            checkbox = ctk.CTkCheckBox(
                self.provider_frame,
                text=provider["anzeigename"],
                variable=variable,
                command=self._provider_auswahl_validieren,
            )
            checkbox.pack(side="left", padx=(0, 12))
            if name not in verfuegbare_namen:
                checkbox.configure(state="disabled")

        self._provider_auswahl_validieren()

    def _ki_provider_checkboxes_erstellen(self):
        gespeicherte_provider = self.settings.get("ki_provider")
        if not isinstance(gespeicherte_provider, list):
            gespeicherte_provider = self.job_service.verfuegbare_provider_namen()

        verfuegbare_namen = set(self.job_service.verfuegbare_provider_namen())
        sichtbare_provider = [
            provider
            for provider in self.job_service.provider_status()
            if provider["name"] in ("arbeitsagentur", "jooble", "adzuna", "websuche", "karriereseiten", "arbeitnow")
        ]
        for spalte in range(3):
            self.ki_provider_frame.grid_columnconfigure(spalte, weight=1)
        for index, provider in enumerate(sichtbare_provider):
            name = provider["name"]
            aktiv = bool(provider["aktiv"])
            variable = ctk.BooleanVar(value=aktiv and name in gespeicherte_provider)
            self.ki_provider_variablen[name] = variable
            checkbox = ctk.CTkCheckBox(
                self.ki_provider_frame,
                text=provider["anzeigename"],
                variable=variable,
                command=self._ki_provider_auswahl_validieren,
            )
            checkbox.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 12), pady=4)
            if name not in verfuegbare_namen:
                checkbox.configure(state="disabled")

        self._ki_provider_auswahl_validieren()

    def _provider_auswahl_validieren(self):
        aktive_auswahl = self._ausgewaehlte_provider()
        if aktive_auswahl:
            return

        for name in self.job_service.verfuegbare_provider_namen():
            variable = self.provider_variablen.get(name)
            if variable is not None:
                variable.set(True)
                return

    def _ausgewaehlte_provider(self):
        verfuegbare_namen = set(self.job_service.verfuegbare_provider_namen())
        return [
            name
            for name, variable in self.provider_variablen.items()
            if name in verfuegbare_namen and variable.get()
        ]

    def _ki_provider_auswahl_validieren(self):
        if self._ausgewaehlte_ki_provider():
            return
        for name in self.job_service.verfuegbare_provider_namen():
            variable = self.ki_provider_variablen.get(name)
            if variable is not None:
                variable.set(True)
                return

    def _ausgewaehlte_ki_provider(self):
        verfuegbare_namen = set(self.job_service.verfuegbare_provider_namen())
        return [
            name
            for name, variable in self.ki_provider_variablen.items()
            if name in verfuegbare_namen and variable.get()
        ]

    def _provider_anzeigenamen(self, namen):
        namen = list(namen or [])
        anzeigenamen = {provider["name"]: provider["anzeigename"] for provider in self.job_service.provider_status()}
        return ", ".join(anzeigenamen.get(name, name) for name in namen) or "keine"

    def _umkreis_wert(self):
        return str(self.umkreis.get() or "").replace("km", "").strip()

    def _ki_umkreis_wert(self):
        return str(self.ki_umkreis.get() or "").replace("km", "").strip()

    def _umkreis_anzeige(self, wert):
        text = self._umkreis_wert_aus_text(wert)
        return f"{text or '30'} km"

    def _umkreis_wert_aus_text(self, wert):
        return str(wert or "").replace("km", "").strip()

    def naechste_seite(self):
        if self.aktuelle_seite + 1 < self._seitenanzahl(len(self._aktuelle_jobs())):
            self.aktuelle_seite += 1
            self._ansichts_zustand_sichern(scrollposition=0.0)
            self.zeige_jobs()
            scrollbare_liste_nach_oben(self.liste)

    def vorherige_seite(self):
        if self.aktuelle_seite > 0:
            self.aktuelle_seite -= 1
            self._ansichts_zustand_sichern(scrollposition=0.0)
            self.zeige_jobs()
            scrollbare_liste_nach_oben(self.liste)

    def _navigation_aktualisieren(self, gesamt):
        seiten = self._seitenanzahl(gesamt)
        if gesamt == 0:
            self.aktuelle_seite = 0
            self.seiten_label.configure(text="Seite 0 / 0")
            self.zurueck_button.configure(state="disabled")
            self.weiter_button.configure(state="disabled")
            return

        if self.aktuelle_seite >= seiten:
            self.aktuelle_seite = seiten - 1

        self.seiten_label.configure(text=f"Seite {self.aktuelle_seite + 1} / {seiten}")
        self.zurueck_button.configure(state="normal" if self.aktuelle_seite > 0 else "disabled")
        self.weiter_button.configure(state="normal" if self.aktuelle_seite + 1 < seiten else "disabled")

    def _seitenanzahl(self, gesamt):
        if gesamt <= 0:
            return 0
        return (gesamt + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

    def _jobs_der_seite(self, jobs):
        start = self.aktuelle_seite * RESULTS_PER_PAGE
        ende = min(start + RESULTS_PER_PAGE, len(jobs))
        return jobs[start:ende]

    def _aktuelle_jobs(self):
        if self.ansicht == "bewerbungen":
            gruppen = self.job_service.bewerbungen_nach_status(
                self.bewerbung_suche.get(),
                self.bewerbung_status_auswahl,
                self.quellen_filter.get(),
                self.sortierung.get(),
                self.followup_filter.get(),
            )
            return [job for status in self.job_service.status_werte() for job in gruppen.get(status, [])]
        if self.ansicht == "ki":
            return self.job_service.suchergebnisse_sortieren(
                [job for job in self.analyse_jobs if job.hat_ki_daten()],
                self.analyse_treffer_sortierung,
            )
        if self.ansicht == "ki_suche":
            return self.job_service.suchergebnisse_sortieren(
                self.ki_suchergebnisse,
                self.ki_treffer_sortierung,
            )
        if self.ansicht == "suche":
            return self.job_service.suchergebnisse_sortieren(
                self.normale_suchergebnisse,
                self.normale_treffer_sortierung,
            )
        return self.jobs

    def _status_uebersicht(self, anzahl):
        teile = [f"{status}: {anzahl.get(status, 0)}" for status in self.job_service.status_werte()]
        return " | ".join(teile)

    def _ki_zusammenfassung_text(self):
        zusammenfassung = self.job_service.ki_zusammenfassung()
        analyse_status = self.job_service.ki_analyse_status()
        if self.ki_laeuft:
            return "KI-Analyse laeuft mit den aktuellen Kriterien..."
        if not self.normale_suchergebnisse and not self.ki_suchergebnisse:
            return ""
        if not any(job.hat_ki_daten() for job in self.analyse_jobs):
            return "Noch keine KI-Analyse gestartet. Trefferquellen auswaehlen und Analyse starten."
        if not zusammenfassung:
            zusammenfassung = self._ki_fallback_gesamtfazit([job for job in self.analyse_jobs if job.hat_ki_daten()])
        if self.ki_zusammenfassung_veraltet:
            return f"Analyse nicht aktuell: Auswahl oder Kriterien wurden geaendert. Letztes Fazit: {zusammenfassung}"
        if analyse_status == "technisch":
            return f"Nur technische Vorbewertung, keine echte Ollama-Analyse: {zusammenfassung}"
        if analyse_status == "teilweise":
            return f"Teilweise echte Ollama-Analyse: {zusammenfassung}"
        return f"KI-Analyse aktuell: {zusammenfassung}"

    def _ki_job_text(self, job):
        teile = []
        if job.ki_match_score:
            teile.append(f"KI-Match: {job.ki_match_score}/100")
        if job.ki_empfehlung:
            teile.append(f"Empfehlung: {job.ki_empfehlung}")
        if job.ki_zusammenfassung:
            teile.append(job.ki_zusammenfassung)
        if job.ki_skills:
            teile.append("Skills: " + ", ".join(job.ki_skills[:5]))
        return " | ".join(teile)

    def _ki_detail_text(self, job):
        zeilen = []
        if job.ki_match_score:
            zeilen.append(f"Match: {job.ki_match_score}/100")
        if job.ki_empfehlung:
            zeilen.append(f"Empfehlung: {job.ki_empfehlung}")
        if job.ki_zusammenfassung:
            zeilen.append(f"Zusammenfassung: {job.ki_zusammenfassung}")
        if job.ki_staerken:
            zeilen.append("Staerken: " + ", ".join(job.ki_staerken))
        if job.ki_risiken:
            zeilen.append("Risiken/offene Punkte: " + ", ".join(job.ki_risiken))
        if job.ki_skills:
            zeilen.append("Skills: " + ", ".join(job.ki_skills))
        return "\n".join(zeilen)

    def link_oeffnen(self, url):
        logging.info("Joblink geoeffnet: %s", url)
        webbrowser.open(url)

    def _aktuelle_settings(self):
        profil_name = self._analyseprofil_name()
        return {
            "einleitung_abgeschlossen": bool(self.settings.get("einleitung_abgeschlossen", False)),
            "suchbegriff": self.such.get(),
            "ort": self.ort.get(),
            "umkreis": self._umkreis_wert(),
            "provider": self._ausgewaehlte_provider(),
            "provider_katalog_version": 3,
            "ki_ort": self.ki_ort.get(),
            "ki_umkreis": self._ki_umkreis_wert(),
            "ki_provider": self._ausgewaehlte_ki_provider(),
            "darstellung": self.darstellung_modus,
            "ki_kriterien": self._ki_kriterien(),
            "nutzerprofil": self._nutzerprofil(),
            "nutzerprofil_auswahl": profil_name,
        }

    def beenden(self):
        self.wird_beendet = True
        for attribut in ("normaler_such_abbruch", "ki_jobsuche_abbruch", "ki_analyse_abbruch"):
            abbruch_event = getattr(self, attribut, None)
            if abbruch_event is not None:
                abbruch_event.set()
        self.job_service.ki_analyse_abbrechen()
        self.job_service.ki_suchplanung_abbrechen()
        try:
            self.job_service.settings_speichern(self._aktuelle_settings())
            logging.info("JobScout AI beendet")
        finally:
            logging.shutdown()
            self.app.destroy()

    def starten(self):
        self.app.mainloop()


def starten():
    JobScoutAI().starten()









