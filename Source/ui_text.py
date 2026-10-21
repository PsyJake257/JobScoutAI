"""German presentation text; persisted identifiers keep their existing spelling."""

import re
from tkinter import messagebox as _messagebox


_PAARE = """
aelteste älteste
aendern ändern
aenderung änderung
aenderst änderst
aenderungen änderungen
anfuehrungszeichen anführungszeichen
ausfuellen ausfüllen
ausgefuehrt ausgeführt
ausgefuelltes ausgefülltes
ausgefuellt ausgefüllt
ausgewaehlt ausgewählt
ausgewaehlte ausgewählte
ausgewaehlten ausgewählten
ausgewaehltes ausgewähltes
ausschliesslich ausschließlich
ausschluesse ausschlüsse
aussendienst außendienst
auswaehlen auswählen
benoetigt benötigt
bestaetigt bestätigt
bestaetigen bestätigen
buero büro
buerojob bürojob
buerokraft bürokraft
datenqualitaet datenqualität
dublettenpruefung dublettenprüfung
einfuehrung einführung
einschraenkungen einschränkungen
enthaelt enthält
erhaeltst erhältst
ergaenzen ergänzen
ergaenzt ergänzt
europaeischer europäischer
fuer für
geaendert geändert
gekuerzt gekürzt
gekuerzte gekürzte
geloescht gelöscht
geoeffnet geöffnet
gespraech gespräch
groesse größe
gross groß
gewaehlten gewählten
gewuenschte gewünschte
gueltige gültige
gueltigen gültigen
haeufige häufige
hinzufuegen hinzufügen
hoechster höchster
kaufmaennischer kaufmännischer
kuerzen kürzen
laedt lädt
laeuft läuft
loeschen löschen
moeglich möglich
moeglicherweise möglicherweise
naechste nächste
naechsten nächsten
naechstes nächstes
oeffentliche öffentliche
oeffentlich öffentlich
oeffentlichen öffentlichen
oeffentlicher öffentlicher
oeffnen öffnen
oeffnest öffnest
oeffnet öffnet
persoenlich persönlich
persoenliche persönliche
persoenlichen persönlichen
persoenliches persönliches
prioritaet priorität
pruefen prüfen
pruefenswert prüfenswert
pruefpunkte prüfpunkte
rueckgaengig rückgängig
schluessel schlüssel
schluesselfeld schlüsselfeld
schluesselfelder schlüsselfelder
schliessen schließen
spaeter später
staerken stärken
statusaenderung statusänderung
statusaenderungen statusänderungen
suchpraeferenzen suchpräferenzen
suchvorschlaege suchvorschläge
taetigkeiten tätigkeiten
taetigkeitsbezeichnung tätigkeitsbezeichnung
traegst trägst
ueber über
ueberfaellig überfällig
uebernehmen übernehmen
uebernommen übernommen
ueberschreiben überschreiben
ueberschrieben überschrieben
uebersicht übersicht
uebersprungen übersprungen
uebrigen übrigen
ungueltig ungültig
ungueltige ungültige
ungueltiges ungültiges
unveraendert unverändert
unvollstaendig unvollständig
verfuegbar verfügbar
veroeffentlichungsdatum veröffentlichungsdatum
veroeffentlicht veröffentlicht
vollstaendig vollständig
vollstaendige vollständige
vorpruefung vorprüfung
vorschlaege vorschläge
voruebergehend vorübergehend
waehle wähle
waehlen wählen
waehrend während
wohnortnaehe wohnortnähe
wuensche wünsche
wuenschen wünschen
zugehoerige zugehörige
zurueck zurück
zuruecksetzen zurücksetzen
zusaetzlich zusätzlich
zusaetzlichen zusätzlichen
zuverlaessig zuverlässig
"""
_WOERTER = dict(zeile.split() for zeile in _PAARE.splitlines() if zeile.strip())


def anzeigetext(text):
    if not isinstance(text, str):
        return text

    def ersetzen(treffer):
        wort = treffer.group()
        neu = _WOERTER.get(wort.lower(), wort)
        if wort.isupper():
            return neu.upper()
        return neu[:1].upper() + neu[1:] if wort[:1].isupper() else neu

    return re.sub(r"[^\W\d_]+", ersetzen, text)


class _Messagebox:
    def __getattr__(self, name):
        original = getattr(_messagebox, name)

        def anzeigen(*args, **kwargs):
            args = tuple(anzeigetext(wert) for wert in args)
            for schluessel in ("title", "message", "detail"):
                if schluessel in kwargs:
                    kwargs[schluessel] = anzeigetext(kwargs[schluessel])
            return original(*args, **kwargs)

        return anzeigen


messagebox = _Messagebox()
