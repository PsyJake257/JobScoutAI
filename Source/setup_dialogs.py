import os
import subprocess
import webbrowser
from copy import deepcopy
import tkinter as tk
from ui_text import messagebox

import ui_widgets as ctk

from paths import BASIS_ORDNER
from providers.env_loader import lade_env_wert, speichere_env_werte


ZUGANGSFELDER = (
    ("JOOBLE_API_KEY", "Jooble: API-Schluessel", "https://de.jooble.org/api/about", True),
    ("ADZUNA_APP_ID", "Adzuna: App-ID", "https://developer.adzuna.com/", False),
    ("ADZUNA_API_KEY", "Adzuna: API-Schluessel", "https://developer.adzuna.com/", True),
    ("SERP_SEARCH_API_KEY", "SerpApi: API-Schluessel", "https://serpapi.com/manage-api-key", True),
    ("CAREER_SITE_URLS", "Karriereseiten: URLs (mit Semikolon trennen)", "https://schema.org/JobPosting", False),
)

EINLEITUNG = (
    ("dashboard", "kennzahlen", "Deine Uebersicht",
     "Das Dashboard zeigt Treffer, gespeicherte Stellen und laufende Bewerbungen. Weiter unten findest du deine zuletzt gespeicherten Angebote mit ihrem aktuellen Status."),
    ("suche", "such_panel", "Stellen suchen",
     "Trage Beruf, Ort und Umkreis ein und waehle deine Suchquellen. Jobs suchen startet die Abfrage. Arbeitsagentur und Arbeitnow funktionieren ohne persoenlichen Schluessel."),
    ("suche", "treffer_sortierleiste", "Aktuelle Angebote zuerst",
     "Hier sortierst du deine Suchergebnisse, etwa nach Datum, Name oder Unternehmen. Neueste zuerst bringt aktuelle Angebote nach oben. Ohne Suchlauf ist die Liste noch leer."),
    ("ki_suche", "ki_such_panel", "Mit mehreren Begriffen suchen",
     "Die KI-Jobsuche durchsucht die gewaehlten Quellen mit allen aktiven Begriffen. Ort und Umkreis gelten fuer diesen Suchlauf. Neue Vorschlaege erzeugen sammelt erst einmal Ideen."),
    ("ki_suche", "begriffe", "Deine Suchbegriffe",
     "Links stehen deine gespeicherten Begriffe. Der Switch aktiviert oder pausiert sie. Mit Speichern unter und Laden wechselst du zwischen Sammlungen, zum Beispiel Buero und Handwerk."),
    ("ki_suche", "vorschlaege", "Vorschlaege selbst uebernehmen",
     "Neue KI-Vorschlaege erscheinen hier rechts. Du kannst sie bearbeiten, uebernehmen oder verwerfen. Deine gespeicherten Begriffe werden dabei nicht automatisch ersetzt. Ohne erzeugte Vorschlaege bleibt dieser Bereich leer."),
    ("profil", "profil_werkzeuge", "Dein persoenliches Profil",
     "Speichere unterschiedliche Profile mit Erfahrung, Staerken und Wunschrollen. Laden oeffnet ein Profil; Speichern unter legt eine benannte Sammlung deiner Angaben an."),
    ("ki", "analyse_setup", "Angebote persoenlich bewerten",
     "Waehle hier die Trefferquellen und das passende Nutzerprofil. Gemma prüft zuerst alle ausgewählten Stellen und bewertet danach bis zu 15 Top-Kandidaten ausführlich. Fertige Kurzfazits erscheinen bereits während der Analyse. Ohne echte KI-Auswertung wird keine Match-Punktzahl angezeigt. Das Modell wärmt beim Programmstart im Hintergrund vor."),
    ("bewerbungen", "bewerbung_status_tabs", "Bewerbungen im Blick",
     "Das Herz auf einer Stellenkarte speichert das Angebot. Diese Reiter ordnen deine Bewerbungen nach Fortschritt. Den Status aenderst du direkt auf der Karte; Details bieten weitere Notizen."),
    ("einstellungen", "zugangsdaten", "Weitere Suchquellen hinzufuegen",
     "Hier oeffnest du die Anbieter und traegst eigene Zugangsdaten fuer Jooble, Adzuna und SerpApi oder Karriereseiten ein. Speichern legt die lokale .env an; die Quellen sind ohne Neustart nutzbar. Profile und KI-Auswertungen bleiben lokal, Suchanfragen gehen an die gewaehlten Anbieter."),
)


def erklaerung_position(flaeche, groesse, ziel):
    """Choose an in-window corner with the least overlap with the highlighted area."""
    links, oben, rechts, unten = flaeche
    breite, hoehe = groesse
    kandidaten = [(max(links, rechts - breite), max(oben, unten - hoehe)),
                  (max(links, rechts - breite), oben), (links, max(oben, unten - hoehe)), (links, oben)]

    def ueberlappung(position):
        x, y = position
        return max(0, min(x + breite, ziel[2]) - max(x, ziel[0])) * max(0, min(y + hoehe, ziel[3]) - max(y, ziel[1]))

    return min(kandidaten, key=ueberlappung)


class GefuehrteEinleitung:
    def __init__(self, owner, abgeschlossen):
        self.owner = owner
        self.app = owner.app
        self.abgeschlossen = abgeschlossen
        self.index = 0
        self.timer = None
        owner._ansichts_zustand_sichern()
        self.ausgang = owner.ansicht
        self.zustaende = deepcopy(owner.ansichts_zustaende)
        self.suchbereich = owner.ki_suchbereich.get()
        self.bewerbungsstatus = owner.bewerbung_status_auswahl
        self.entwurf = owner._einleitungs_entwurf_sichern()
        owner.einleitung_aktiv = True
        self.panel = ctk.CTkFrame(self.app, width=360, corner_radius=8, border_width=2,
                                  border_color="#F5B557", fg_color=("#FFFFFF", "#1D2936"))
        self.schritt = ctk.CTkLabel(self.panel, text="", anchor="w", text_color=("#76500E", "#F5B557"))
        self.schritt.pack(fill="x", padx=18, pady=(14, 4))
        self.titel = ctk.CTkLabel(self.panel, text="", font=("Segoe UI", 18, "bold"), anchor="w", justify="left", wraplength=320)
        self.titel.pack(fill="x", padx=18)
        self.text = ctk.CTkLabel(self.panel, text="", font=("Segoe UI", 14), anchor="w", justify="left", wraplength=320)
        self.text.pack(fill="x", padx=18, pady=(8, 16))
        unten = ctk.CTkFrame(self.panel, fg_color="transparent")
        unten.pack(fill="x", padx=18, pady=(0, 16))
        self.zurueck = ctk.CTkButton(unten, text="Zurueck", width=85, command=lambda: self.anzeigen(self.index - 1))
        self.zurueck.pack(side="left")
        self.weiter = ctk.CTkButton(unten, text="Weiter", width=95, command=self.naechster_schritt)
        self.weiter.pack(side="right")
        ctk.CTkButton(unten, text="Beenden", width=80, fg_color="transparent", border_width=1,
                      text_color=("#263544", "#EDF3F9"), command=self.schliessen).pack(side="right", padx=6)
        self.raender = [tk.Frame(self.app, background="#F5B557", borderwidth=0) for _ in range(4)]
        self.anzeigen(0)

    def winfo_exists(self):
        return self.panel.winfo_exists()

    def lift(self):
        self.panel.lift()

    def naechster_schritt(self):
        if self.index == len(EINLEITUNG) - 1:
            self.schliessen()
        else:
            self.anzeigen(self.index + 1)

    def anzeigen(self, index):
        if self.timer is not None:
            self.app.after_cancel(self.timer)
            self.timer = None
        self.index = max(0, min(index, len(EINLEITUNG) - 1))
        ansicht, ziel, titel, text = EINLEITUNG[self.index]
        self.schritt.configure(text=f"Einfuehrung  {self.index + 1} / {len(EINLEITUNG)}")
        self.titel.configure(text=titel)
        self.text.configure(text=text)
        self.zurueck.configure(state="normal" if self.index else "disabled")
        self.weiter.configure(text="Fertig" if self.index == len(EINLEITUNG) - 1 else "Weiter")
        self.owner._einleitungs_ansicht_oeffnen(ansicht)
        self.app.update_idletasks()
        widget = self.owner._einleitungs_ziel(ziel)
        if widget is not None and self._in_liste(widget):
            canvas = self.owner.liste._parent_canvas
            y = widget.winfo_rooty() - self.owner.liste.winfo_rooty()
            canvas.yview_moveto(max(0, y - 12) / max(1, self.owner.liste.winfo_height()))
        self.positionieren()

    def _in_liste(self, widget):
        while widget is not None:
            if widget is self.owner.liste:
                return True
            widget = getattr(widget, "master", None)
        return False

    def positionieren(self):
        if not self.winfo_exists():
            return
        self.app.update_idletasks()
        ziel = self.owner._einleitungs_ziel(EINLEITUNG[self.index][1])
        breite, hoehe = self.app.winfo_width(), self.app.winfo_height()
        rect = (0, 0, 0, 0)
        if ziel is not None and ziel.winfo_exists() and ziel.winfo_viewable():
            x = ziel.winfo_rootx() - self.app.winfo_rootx()
            y = ziel.winfo_rooty() - self.app.winfo_rooty()
            rect = (max(0, x - 4), max(0, y - 4), min(breite, x + ziel.winfo_width() + 4), min(hoehe, y + ziel.winfo_height() + 4))
            if self._in_liste(ziel):
                canvas = self.owner.liste._parent_canvas
                cx, cy = canvas.winfo_rootx() - self.app.winfo_rootx(), canvas.winfo_rooty() - self.app.winfo_rooty()
                rect = (max(rect[0], cx), max(rect[1], cy), min(rect[2], cx + canvas.winfo_width()), min(rect[3], cy + canvas.winfo_height()))
        x1, y1, x2, y2 = rect
        for rand in self.raender:
            rand.place_forget()
        if x2 > x1 and y2 > y1:
            for rand, werte in zip(self.raender, ((x1, y1, x2-x1, 3), (x1, y2-3, x2-x1, 3), (x1, y1, 3, y2-y1), (x2-3, y1, 3, y2-y1))):
                x, y, w, h = werte
                rand.place(x=x, y=y, width=w, height=h)
                rand.lift()
        scale = self.panel._get_widget_scaling()
        pw, ph = self.panel.winfo_reqwidth(), self.panel.winfo_reqheight()
        links = self.owner.seitenleiste.winfo_width() + 16
        x, y = erklaerung_position((links, 16, breite-16, hoehe-16), (pw, ph), rect)
        self.panel.place(x=x / scale, y=y / scale)
        self.panel.lift()
        self.timer = self.app.after(180, self.positionieren)

    def schliessen(self, speichern=True):
        try:
            if speichern:
                self.abgeschlossen()
        except OSError:
            messagebox.showerror("Einleitung", "Der Einrichtungsstand konnte nicht gespeichert werden. Bitte Schreibrechte im App-Ordner pruefen.", parent=self.app)
            return
        self.destroy()
        owner = self.owner
        owner.einleitung_aktiv = False
        owner.ki_suchbereich.set(self.suchbereich)
        owner.bewerbung_status_auswahl = self.bewerbungsstatus
        owner.ansichts_zustaende = deepcopy(self.zustaende)
        owner.ansicht = self.ausgang
        owner._ansicht_wechseln(self.ausgang)
        owner._einleitungs_entwurf_wiederherstellen(self.entwurf)
        position = self.zustaende.get(self.ausgang, {}).get("scrollposition", 0.0)
        self.app.after_idle(lambda: owner.liste._parent_canvas.yview_moveto(position))

    def destroy(self):
        if self.timer is not None:
            self.app.after_cancel(self.timer)
            self.timer = None
        for rand in self.raender:
            rand.destroy()
        self.panel.destroy()


def zeige_einleitung(owner, abgeschlossen):
    return GefuehrteEinleitung(owner, abgeschlossen)


def suchquellen_editor(parent, bereit, aktualisiert):
    env_datei = BASIS_ORDNER / ".env"
    felder = {}
    ctk.CTkLabel(parent, text="Zugangsdaten verwalten", font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 10))
    for name, label, url, geheim in ZUGANGSFELDER:
        zeile = ctk.CTkFrame(parent, fg_color="transparent")
        zeile.pack(fill="x", padx=18, pady=5)
        zeile.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(zeile, text=label, anchor="w").grid(row=0, column=0, sticky="ew")
        feld = ctk.CTkEntry(zeile, show="*" if geheim else "", height=34)
        feld.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        feld.insert(0, lade_env_wert(env_datei, name))
        felder[name] = feld
        ctk.CTkButton(zeile, text="Anbieter oeffnen", width=145, command=lambda link=url: webbrowser.open(link)).grid(row=1, column=1)

    def laden():
        for name, feld in felder.items():
            feld.delete(0, "end")
            feld.insert(0, lade_env_wert(env_datei, name))

    # Compare with the displayed snapshot so external edits are not overwritten.
    snapshot = {name: feld.get() for name, feld in felder.items()}

    def speichern():
        if not bereit():
            return
        werte = {name: feld.get() for name, feld in felder.items() if feld.get() != snapshot[name]}
        try:
            if any(lade_env_wert(env_datei, name) != snapshot[name] for name in werte):
                if not messagebox.askyesno("Zugangsdaten geaendert", "Die Datei wurde zwischenzeitlich bearbeitet. Deine Eingaben trotzdem uebernehmen?", parent=parent):
                    return
            speichere_env_werte(env_datei, werte)
        except (OSError, ValueError, UnicodeError) as fehler:
            hinweis = str(fehler) if isinstance(fehler, ValueError) else "Die .env konnte nicht gespeichert werden. Bitte Schreibrechte im App-Ordner pruefen."
            messagebox.showerror("Zugangsdaten", hinweis, parent=parent)
            return
        snapshot.update({name: feld.get() for name, feld in felder.items()})
        aktualisiert()
        messagebox.showinfo("Suchquellen", "Gespeichert. Konfigurierte Suchquellen sind jetzt ohne Neustart verfuegbar. Ein leeres Schluesselfeld deaktiviert die zugehoerige Quelle.", parent=parent)

    def datei_oeffnen():
        try:
            if not env_datei.exists():
                speichere_env_werte(env_datei, {name: "" for name, *_ in ZUGANGSFELDER})
            if os.name == "nt":
                subprocess.Popen(["notepad.exe", str(env_datei)])
            else:
                webbrowser.open(env_datei.as_uri())
        except OSError:
            messagebox.showerror("Zugangsdaten", "Die .env konnte nicht geoeffnet werden.", parent=parent)

    def neu_laden():
        if any(feld.get() != snapshot[name] for name, feld in felder.items()):
            if not messagebox.askyesno("Eingaben verwerfen?", "Ungespeicherte Eingaben durch den Dateiinhalt ersetzen?", parent=parent):
                return
        if not bereit():
            return
        laden()
        snapshot.update({name: feld.get() for name, feld in felder.items()})
        aktualisiert()

    def sichtbar():
        for name, _, _, geheim in ZUGANGSFELDER:
            if geheim:
                felder[name].configure(show="" if anzeigen.get() else "*")

    anzeigen = ctk.BooleanVar(value=False)
    ctk.CTkSwitch(parent, text="Schluessel anzeigen", variable=anzeigen, command=sichtbar).pack(anchor="w", padx=18, pady=10)
    aktionen = ctk.CTkFrame(parent, fg_color="transparent")
    aktionen.pack(fill="x", padx=18, pady=(2, 18))
    ctk.CTkButton(aktionen, text="Zugangsdaten speichern", command=speichern, width=185).pack(side="left")
    ctk.CTkButton(aktionen, text=".env oeffnen", command=datei_oeffnen, width=125).pack(side="left", padx=8)
    ctk.CTkButton(aktionen, text="Aus Datei neu laden", command=neu_laden, width=155).pack(side="left")
    return felder
