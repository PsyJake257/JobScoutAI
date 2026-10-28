# CHANGELOG

## Version 2.44.0 - Gemma, Top-Kandidaten und Glas-Look - 2026-10-28

- Gemma 4 E2B IT (Q4_K_M) und llama.cpp vollständig enthalten; GPU/Vulkan bevorzugt, CPU-Fallback bei Startproblemen. Hintergrund-Vorwärmen beim Programmstart, ohne das Fenster zu blockieren.
- Die KI prüft alle ausgewählten Stellen in kleinen Gruppen und bewertet danach bis zu 15 Top-Kandidaten einzeln mit Kurzfazit, konkreten Passungsgründen und offenen Fragen. Bei höchstens 15 Stellen werden alle direkt ausführlich bewertet.
- Laufender Fortschritt aktualisiert vorhandene Widgets, neue Fazits werden einmal ergänzt. Die Ansicht wird nicht nach jeder Stelle neu aufgebaut. Fehlerhafte Detailantworten erhalten keinen erfundenen Match-Wert.
- Matte Glasflächen, sanfte Reflexe, schwebende Navigation und kontrastreiche Bedienelemente. Statische, begrenzt gecachte Kanteneffekte ohne Live-Blur beim Scrollen.
- Lizenzinformationen, Modellherkunft, portable Build-Werkzeuge und Entwicklerhinweise auf Gemma/llama.cpp umgestellt. Downloads werden aus einem frischen Ordner ohne private Daten oder API-Schlüssel erstellt.

## Version 2.40.2 - Scrollen und Reaktionszeit - 2026-10-21

- Scroll-Ereignisse und Scrollbar-Ziehen werden pro Zeichenintervall gebündelt; keine erzwungene Verarbeitung aller GUI-Leerlaufaufgaben bei jedem Scrollschritt.
- Scrollregion wird nur bei Größenänderungen aktualisiert. Globale Eingabebindungen und geplante Scroll-Callbacks werden beim Schließen aufgeräumt.
- Dateiabhaengiger Cache für Stellendaten vermeidet wiederholtes JSON-Lesen; Aufrufer erhalten weiterhin unabhängige Kopien und externe Änderungen werden erkannt.
- KI-Analyse baut höchstens eine Ergebnisseite gleichzeitig auf. Alle Treffer bleiben über die Seitennavigation erreichbar; Gesamtauswertung umfasst weiterhin alle Treffer.
- Mehr/Weniger aktualisiert nur die jeweilige Beschreibung statt der ganzen Ansicht. Quellenfilter werden nur in der Bewerbungsverwaltung neu geladen.

## Version 2.40.1 - Umlaute, Kontrast und KI-Vorschlaege - 2026-10-21

- Die Oberflaeche zeigt deutsche Umlaute und ss als scharfes s an, wo sprachlich erforderlich. Interne Statuswerte, Filter und gespeicherte Daten behalten ihre bisherigen Bezeichnungen.
- Buttons waehlen zur Hintergrundfarbe passende dunkle oder weisse Schrift. Deaktivierte Buttons verwenden eine neutrale Flaeche mit lesbarer Beschriftung.
- Die portable KI-Laufzeit wird vor KI-Aktionen geprueft und bei Bedarf neu gestartet. Fehler werden in `data/logs/ollama.log` nachvollziehbar.
- Die Vorschlagsplanung fordert ein festes Antwortschema an und verwirft Platzhalter. Ein eingetragener Berufsbegriff dient als Ausgangspunkt.
- Fehlermeldungen der Vorschlagsplanung werden direkt im Vorschlagsbereich angezeigt; Fehler aus Hintergrundthreads behalten ihre Ausnahme bis zur Anzeige.
- Der aktuell benutzte PublicBuild-Testordner wird samt Nutzerdaten erhalten. Die Paketierung verweigert das Weitergeben bereits benutzter Ordner.

## Version 2.40.0 - Gefuehrte Einfuehrung direkt in der App - 2026-10-21

- Jeder Einfuehrungsschritt oeffnet die passende Kategorie und hebt den erklaerten Bereich mit einem goldenen Rahmen hervor.
- Eine kompakte Erklaerung bleibt im App-Fenster und waehlt die Ecke mit der geringsten Ueberdeckung des Ziels. Markierungen folgen dem Scrollen und der Fenstergroesse.
- Jobsuche, Sortierung, KI-Suchbegriffe und Vorschlaege, Nutzerprofil, Analyse, Bewerbungen und API-Einrichtung haben eigene Schritte.
- Vorwaerts, Zurueck und Beenden bleiben jederzeit erreichbar. Beim Beenden werden Ausgangsansicht, Seite, Status-Reiter, Scrollposition und vorherige ungespeicherte Formulartexte wiederhergestellt.
- Das Tutorial startet selbst keine Suche oder KI-Analyse und erzeugt keine Beispieldaten.

## Version 2.39.0 - Einfuehrung und Suchquellen einrichten - 2026-10-21

- Die Einfuehrung beim ersten Start erklaert Jobsuche, Suchbegriff-Sammlungen, Nutzerprofile, KI-Analyse und Bewerbungen. Sie kann uebersprungen und in den Einstellungen erneut geoeffnet werden.
- Eigene API-Zugangsdaten und Karriereseiten lassen sich in den Einstellungen eintragen, verdeckt anzeigen und direkt in die lokale `.env` speichern. Die Datei kann dort geoeffnet und neu geladen werden.
- Geaenderte Suchquellen stehen ohne Neustart in beiden Suchansichten bereit. Leere Schluesselfelder deaktivieren den jeweiligen Anbieter.
- `.env` wird atomar aktualisiert; Kommentare und fremde Einstellungen bleiben erhalten. Gleichzeitige externe Aenderungen werden vor einem Ueberschreiben bestaetigt.
- Der oeffentliche Build wird automatisch gegen die persoenlichen Zugangswerte geprueft. Die Vorgaengerversion 2.38.0 wurde einschliesslich der EXE im verteilten Archiv ohne Fund geprueft.
- Die Paketierung liest die Version zentral aus config.py und erzeugt zwei gleich grosse Archivteile.

Pruefung: 48 gezielte Tests erfolgreich. Technischer Startcheck und Build-Ergebnis siehe Release-Bericht.

## Version 2.38.0 - Standalone-KI und Weitergabe - 2026-10-05

- Der separate oeffentliche Windows-Build enthaelt Qwen3 4B und eine lokale CPU-kompatible Ollama-Laufzeit vollstaendig im App-Ordner.
- JobScout AI startet die eigene KI-Laufzeit ohne Konsolenfenster auf einem isolierten lokalen Port und beendet nur den selbst gestarteten Prozess.
- Lizenzinformationen fuer JobScout AI, Qwen3, Ollama, Python, Tcl/Tk und die verwendeten Python-Bibliotheken werden im Build mitgeliefert und sind in den Einstellungen erreichbar.
- `Tools/PublicBuild_erstellen.ps1` erzeugt den neuen, nutzerneutralen Build unter `PublicBuild/JobScoutAI-Portable`; bestehende App-Daten und API-Schluessel werden nicht uebernommen.

Pruefung: gezielte Release- und Ollama-Client-Tests sowie ein technischer Startcheck des separaten Standalone-Builds.

## Version 2.37.0 - Getrennte KI-Suchvorschlaege - 2026-08-31

- Gespeicherte Suchbegriffe und neue KI-Vorschlaege werden nebeneinander in getrennten Spalten angezeigt.
- Vorschlaege lassen sich einzeln bearbeiten, uebernehmen oder verwerfen sowie gesammelt uebernehmen oder verwerfen.
- Das Erzeugen und Verwerfen von Vorschlaegen veraendert keine gespeicherten Suchbegriffe. Erst eine bewusste Uebernahme ergaenzt den Pool; nahezu identische Begriffe bleiben ausgeschlossen.

Tests: Syntaxpruefung und zwei gezielte Persistenztests erfolgreich.

- Portabler GUI-Build nach `App/JobScoutAI.exe` uebernommen; Sicherung: `Backups/App_before_build_2.37.0_20260831_172654`. Lokale Konfiguration, Nutzerdaten und Startdateien wurden erhalten.

## Version 2.36.1 - Farblogik fuer Bewerbungsstatus - 2026-08-31

- Die Status-Reiter verwenden eigene Prozessfarben: neutral, hellblau, hellgelb, gruen, goldorange und hellrot.
- Der aktive Reiter besitzt eine kraeftigere Flaeche und einen staerkeren Rahmen, sodass die Auswahl nicht allein ueber Farbe erkennbar ist.

Tests: Drei gezielte Status-, Filter- und Sortiertests erfolgreich.

- Portabler GUI-Build nach `App/JobScoutAI.exe` uebernommen; Sicherung: `Backups/App_before_build_2.36.1_20260831_171429`. `.env`, Nutzerdaten und Startdateien wurden erhalten.

## Version 2.36.0 - Uebersichtliche Bewerbungsstatus - 2026-08-31

- Die Bewerbungsverwaltung besitzt Status-Reiter mit aktuellen Trefferzahlen.
- Der Status kann direkt auf der Stellenkarte geaendert werden. Danach oeffnet sich der Ziel-Reiter und die zuletzt geaenderte Stelle steht oben.
- `Angebot` und `Absage` sind nicht mehr auswaehlbar. Bestehende Eintraege bleiben im Verlauf erhalten und werden in der Uebersicht unter `Erledigt` zusammengefasst.

Tests: Drei gezielte Status-, Filter- und Sortiertests erfolgreich.

- Portabler GUI-Build nach `App/JobScoutAI.exe` uebernommen; Sicherung: `Backups/App_before_build_2.36.0_20260831_165349`. `.env`, Nutzerdaten und Startdateien wurden erhalten.

## Version 2.35.1 - Start ohne Eingabeaufforderung - 2026-08-31

- Der portable Windows-Build verwendet jetzt eine echte GUI-EXE (`console=False`) statt eines auszublendenden Konsolen-Bootloaders. Die Eingabeaufforderung wird beim regulären Start nicht mehr erzeugt.
- Startfehler bleiben über `data/logs/jobscout.log` und den vorhandenen Fehlerdialog nachvollziehbar.

## Version 2.35.0 - Sortierbare Such- und Analyseergebnisse - 2026-08-31

- Normale Jobsuche und KI-Jobsuche besitzen eine kompakte Sortierleiste direkt oberhalb der Pagination. Standard ist `Neueste zuerst`; weitere Optionen sind aelteste Stellen, Stellenname, Unternehmen und Ort jeweils auf- und absteigend.
- Die besten Treffer der KI-Analyse lassen sich nach KI-Match, Datum, Stellenname, Unternehmen oder Ort sortieren. Die bisherige Rangfolge nach hoechstem Match bleibt dort der Standard.
- Die gemeinsame Service-Logik normalisiert ISO-Zeitpunkte, deutsche und englische relative Datumsangaben. Stellen ohne verwertbares Veroeffentlichungsdatum bleiben bei beiden Datumsrichtungen am Ende.
- Ein Sortierwechsel setzt paginierte Suchlisten auf die erste Seite zurueck; die KI-Analyse behaelt ihre Scrollposition beim Neurendern bei.

Tests: 180 unittest-Tests erfolgreich. Die normale Jobsuche und der eigene Ergebnisreiter der KI-Jobsuche wurden zusaetzlich mit einer isolierten portablen QA-Ausgabe visuell geprueft; die abschliessende Sichtpruefung des Releases uebernimmt der Nutzer.

- Finaler portabler Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260831_083632`. Alle elf nutzerspezifischen Dateien wurden mit identischen SHA-256-Pruefsummen erhalten. Der installierte Build startet und reagiert; die eingebettete `config` bestaetigt Version `2.35.0`.

## Version 2.34.0 - Einheitliches App-Branding - 2026-08-25

- Das neue JobScout-AI-Logo wird als kompakte Marke in der Seitenleiste angezeigt; der bisherige Produktname und Untertitel bleiben lesbar erhalten.
- Fenster, Taskleiste, Desktop-Verknuepfung und portable EXE verwenden ein eigenes Windows-Icon mit sieben Aufloesungen von 16 bis 256 Pixeln.
- PyInstaller buendelt PNG und ICO als Laufzeitressourcen. `paths.py` trennt weiterhin beschreibbare Nutzerdaten neben der EXE von gebuendelten, schreibgeschuetzten Marken-Assets.
- `developer_tools/build_brand_assets.py` erzeugt die transparenten PNG- und ICO-Dateien reproduzierbar aus der gelieferten quadratischen Logoquelle.
- Ein Text-Fallback verhindert Startfehler, falls ein Branding-Asset in einer Entwicklungsumgebung fehlt.

Tests: 177 unittest-Tests erfolgreich.

- Native GUI-Pruefung bei 1280 x 820 Pixeln bestaetigte den kompakten Logo-Schriftzug, das Titelleisten-Icon, die vollstaendige Navigation und ein ueberlappungsfreies Layout.
- Finaler portabler Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260825_233036`. Der installierte EXE-Smoke-Test bestaetigte Version `2.34.0`, neues Fenster- und Sidebar-Branding, erhaltene Nutzerdaten mit null Hash-Abweichungen, kein sichtbares Konsolenfenster und normales vollstaendiges Beenden. Die Desktop-Verknuepfung verwendet explizit das eingebettete EXE-Icon.

## Version 2.33.0 - Benannte Nutzerprofile und Profilauswahl - 2026-08-24

- Beliebig viele Nutzerprofile lassen sich unter einem Namen speichern, laden, aktualisieren und loeschen. Die Profile liegen getrennt in `data/user_profiles.json`.
- Das bisherige Einzelprofil wird beim ersten Start verlustfrei als `Standardprofil` uebernommen; die aktive Auswahl bleibt in den Einstellungen erhalten.
- Ueberschreiben und Loeschen erfordern eine Bestaetigung. Beim Laden eines anderen Profils warnt die Anwendung vor ungespeicherten Formulardaten.
- Die KI-Analyse bietet neben der Profilfreigabe ein Dropdown fuer das konkrete Profil. Ohne ausgefuelltes Profil wird der Start klar blockiert und die Profilverwaltung direkt angeboten.
- Analyse-Snapshots und Ergebnisstatus enthalten den Namen des verwendeten Profils, sodass ein Profilwechsel ein vorhandenes Ergebnis korrekt als veraltet markiert.

Tests: 175 unittest-Tests erfolgreich.

- Native GUI-Pruefung bei 1280 x 820 Pixeln bestaetigte die Profilwerkzeugleiste, das vollstaendig migrierte `Standardprofil`, das Profil-Dropdown der KI-Analyse und ein ueberlappungsfreies Layout.
- Finaler portabler Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260824_182113`. Der installierte EXE-Smoke-Test bestaetigte Version `2.33.0`, alle sechs unveraendert migrierten Profilfelder, erhaltene Nutzerdaten, kein sichtbares Konsolenfenster und normales vollstaendiges Beenden.

## Version 2.32.0 - Suchbegriff-Sets und klare Aktiv-Switches - 2026-08-24

- Aktivieren und Pausieren einzelner KI-Suchbegriffe erfolgt ueber echte Switches. Rote beziehungsweise gruene Spur, farbiger Rand und die Texte `Pausiert` oder `Aktiv` machen den Zustand auch ohne reine Farberkennung eindeutig.
- Komplette Suchbegriff-Pools lassen sich unter frei waehlbaren Namen speichern, laden und loeschen. Ein Set enthaelt Bezeichnung, Aktivstatus und Herkunft jedes Begriffs.
- Vor dem Ueberschreiben eines vorhandenen Sets fragt die Anwendung explizit nach. Beim Laden warnt sie ebenfalls, dass der aktuelle Pool ersetzt wird.
- Benannte Sets liegen getrennt vom aktiven Pool in `data/search_term_sets.json`. Beim Laden bleiben vorhandene Begriffsstatistiken erhalten beziehungsweise werden aus dem gespeicherten Jobbestand neu berechnet.
- Die KI-Jobsuche zeigt oberhalb des Pools eine kompakte Set-Auswahl sowie die Anzahl aktiver und gesamter Begriffe.

Tests: 172 unittest-Tests erfolgreich. Die native GUI-Pruefung bestaetigte die kompakte Set-Leiste, klare rote und gruene Switch-Zustaende, den deutsch beschrifteten Speichern-Dialog und die korrekte Aktiv-Zaehlung bei 1280 x 820 Pixeln.

- Finaler portabler Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260824_174652`. Der installierte EXE-Smoke-Test bestaetigte Version `2.32.0`, erhaltene Nutzerdaten, kein sichtbares Konsolenfenster und normales vollstaendiges Beenden.

## Version 2.31.2 - Arbeitsagentur v6 und robuste SerpApi-Suche - 2026-08-24

- Arbeitsagentur-Suche auf die aktuelle Route `/pc/v6/jobs` und deren Felder `ergebnisliste`, `stellenlokationen` sowie `datumErsteVeroeffentlichung` aktualisiert. Der kompatible v4-Detailabruf bleibt erhalten.
- SerpApi verwendet einen eigenen 45-Sekunden-Timeout. Voruebergehende Konto- oder Suchfehler deaktivieren die Quelle nicht mehr dauerhaft; ein erfolgreicher Status- oder Suchabruf stellt sie wieder her.
- Konkrete Bewerbungslinks werden aus `jobs_results.apply_options` gelesen; `share_link` bleibt der eindeutige Google-Jobs-Rueckfall. Eine leere Ergebnislage gilt nicht mehr als Providerstoerung.

Tests: 169 unittest-Tests erfolgreich.

## Version 2.31.1 - Letzte gespeicherte Stellen und sichtbarer Status - 2026-08-20

- Das Dashboard verwendet nicht mehr die letzten zufaelligen Treffer des Suchlaufs, sondern ausschliesslich die fuenf zuletzt gespeicherten Stellen.
- Ein eigener persistenter Speicherzeitpunkt `gespeichert_am` bildet die Reihenfolge verlaesslich ab. Bestehende Stellen ohne das neue Feld leiten den Zeitpunkt kompatibel aus ihrem ersten Statusereignis ab.
- Dashboard-Zeilen zeigen den aktuellen Bewerbungsstatus als kompakten farbigen Badge. Match-Wert und Detailaktion bleiben separat erkennbar.
- Bewerbungskarten zeigen ihren Status ebenfalls direkt im Kartenkopf. Die bisherige kleine Statusangabe in der Metadatenzeile wird dort nicht mehr doppelt dargestellt.

Tests: 166 unittest-Tests erfolgreich. Die native GUI-Pruefung mit dem vorhandenen Stellenbestand bestaetigte genau fuenf chronologisch korrekte Dashboard-Eintraege sowie lesbare Status-Badges fuer `Gespeichert`, `Bewerbung geplant` und `Beworben`.

- Finaler Release-Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_release_2.31.1_20260820_225212`. Der installierte EXE-Smoke-Test bestaetigte vorhandene Nutzerdaten, Fenstertitel `JobScout AI v2.31.1`, normales Schliessen und kein sichtbares Konsolenfenster.

## Version 2.31.0 - Verlaessliche Websuche und Desktop-Release - 2026-08-20

- Websuche von allgemeinen Google-Ergebnissen auf strukturierte SerpApi-Google-Jobs-Treffer umgestellt. Konkrete Bewerbungslinks werden bevorzugt; eindeutige Google-Jobs-Detailseiten dienen als Rueckfall.
- Such-, Kategorie- und Sammelseiten werden defensiv verworfen. Ort, Radius, Unternehmen, Trefferort und tokenbasierte Pagination werden aus der strukturierten Antwort uebernommen.
- Normale Jobsuche, KI-Jobsuche und KI-Analyse koennen waehrend des laufenden Vorgangs ueber ihren jeweiligen Startbutton abgebrochen werden.
- Die Einstellungen zeigen alle sechs produktiven Quellen mit Laufzeitstatus, Konfigurationshinweis und passendem Informationslink.
- Der redundante Einstellungen-Button in der Seitenkopfzeile wurde entfernt; die linke Navigation ist der eindeutige Zugang.
- Die portable Windows-App startet ohne Konsolenfenster. Fatale Startfehler werden protokolliert und in einem Dialog mit Zugriff auf die Logdatei angezeigt.
- Versionierung auf Semantic Versioning umgestellt. `config.VERSION` steuert Fenstertitel, Seitenleiste, Einstellungen und HTTP-User-Agent zentral; der Release-Ablauf ist in `AGENTS.md` festgehalten.

Tests: 163 unittest-Tests erfolgreich. Der native Release-Smoke-Test bestaetigte Fenstertitel und Versionsanzeige `2.31.0`, alle sechs Suchquellen, die bereinigte Kopfzeile, erhaltene Nutzerdaten sowie den Start ohne sichtbares Konsolenfenster.

- Finaler Release-Build nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_release_2.31.0_20260820_222156`.

## Version 2.30 - Zentraler KI-Analyse-Workflow - 2026-08-20

- Die grossen technischen Statusflaechen auf normaler Jobsuche und KI-Jobsuche wurden durch kompakte Trefferleisten ersetzt. Sichtbar bleiben nur quellengebundene Trefferzahl, kurze Lauf-/Fehlermeldungen und `Zur KI-Analyse`.
- Trefferstatus, Analyse-Einstieg und Pagination sind nun strikt an die jeweilige Suchart gebunden. Eine KI-Jobsuche kann deshalb keine Trefferzahl oder leere Seitennavigation mehr in der normalen Jobsuche anzeigen.
- Normale Jobsuche und KI-Jobsuche halten ihre letzten Treffer getrennt vor. Auf `KI-Analyse` koennen beide Quellen einzeln oder gemeinsam ausgewaehlt werden; Dubletten werden fuer den Analyselauf entfernt.
- Der separate Button `Treffer mit KI bewerten` wurde aus der Suchansicht entfernt. `Zur KI-Analyse` wechselt nur die Ansicht, und die lokale KI startet ausschliesslich ueber `Analyse starten` auf der Analyse-Seite.
- Das Nutzerprofil kann pro Analyselauf ein- oder ausgeschlossen werden. Die gespeicherten Bewertungskriterien bleiben unabhaengig davon erhalten und werden in einem eigenen kompakten Dialog bearbeitet.
- Ein leerer Zustand erklaert fehlende Treffer und fuehrt direkt zu `Jobs suchen` oder `KI-Jobsuche`. Fehlende Quellenauswahl wird als klare Validierung angezeigt.
- Die KI-Ergebnisse nutzen die volle scrollbare Seite mit Statusband, vier Kennzahlen, Match- und Empfehlungsverteilung, grafischen Anforderungen und offenen Pruefpunkten, Gesamtfazit und ausfuehrlichen Trefferkarten.
- Die KI-Jobsuche besitzt eigene persistente Einstellungen fuer Ort, Radius und Provider. Suchplanung und Mehrbegriff-Suche verwenden ausschliesslich diesen Suchraum.
- Nach Abschluss bleibt die KI-Jobsuche in ihrem eigenen Ergebnisreiter. Die normale Trefferliste wird nicht ueberschrieben; beide Sucharten besitzen getrennte paginierte Ergebnisstaende.
- KI-Jobsuche und KI-Analyse verwenden dieselben Kartenaktionen wie die normale Suche: Beschreibung aufklappen, Details, Link oeffnen und Favorit. Verwaltungsdaten werden zwischen geladenen Ansichten synchronisiert.
- Seiten- und Reiterwechsel beginnen oben, damit insbesondere der Analyseaufbau nicht mit einer alten Scrollposition geoeffnet wird.

Tests: 152 unittest-Tests erfolgreich. Native GUI-Pruefung bestaetigte eigenstaendige KI-Suchparameter, kompakte quellengebundene Trefferleisten, ausgeblendete Leernavigation, Ergebnisreiter, Pagination, Ergebnisdiagramme sowie vollstaendige Kartenaktionen ohne Ueberlappungen.

## Version 2.29 - Suchbegriff-Pool und realistischere KI-Bewertung - 2026-08-02

- Dauerhaften `SearchTerm`-Pool mit eigener JSON-Persistenz in `data/search_terms.json` eingefuehrt. Begriffe besitzen Quelle, Status, letzte Suche, Trefferzahl, bewertete und gute Treffer, Durchschnitt sowie besten Score.
- KI-Jobsuche in gespeicherte Begriffe und getrennte Vorschlaege gegliedert. Vorschlaege entstehen nur nach Klick, koennen bearbeitet, einzeln verworfen oder einzeln beziehungsweise gesammelt uebernommen werden und ersetzen keine gespeicherten Begriffe.
- Nur aktive gespeicherte Begriffe werden gesucht; pausierte Begriffe bleiben erhalten. Das Acht-Begriffe-Limit gilt nur fuer einen Vorschlagslauf, nicht fuer Pool oder aktive Suche.
- Bereits gespeicherte und nahezu identische Vorschlaege werden promptseitig und lokal gefiltert. Umbenennen aktualisiert auch die Herkunft vorhandener Jobs.
- Mehrfachherkunft deduplizierter Jobs bleibt in `ki_suchbegriffe` erhalten; Statistiken zaehlen denselben Job pro Begriff nur einmal. Gute Treffer beginnen zentral bei `GOOD_MATCH_SCORE_THRESHOLD = 60`.
- Ursache der zu niedrigen Scores behoben: Der alte Prompt kannte keine verbindliche Score-Skala und trennte offene Angaben nicht strukturell von Ausschluessen. Der neue Prompt bewertet praktische Bewerbungsrelevanz nach 75/60/45/30, gewichtet uebertragbare Aufgaben und Lernpotenzial positiv und behandelt fehlende Angaben ohne Punktabzug.
- Jobmodell um `ki_ausschluesse` und `ki_offene_punkte` erweitert. Positive Kandidaten ohne klaren Konflikt werden defensiv auf mindestens 45 kalibriert, falls das Modell dennoch einen zu niedrigen Score liefert.
- Bewertungsart pro Job als `echt` oder `technisch` gekennzeichnet; technische Ollama-Fallbacks zaehlen nicht als echte KI-Bewertungen in Pool-Statistiken.
- Reale lokale `qwen3:8b`-Pruefung: realistische Projektassistenz `85/100` mit fehlenden Angaben nur als offene Punkte; klare Sales-/Fuehrungs-/Wochenendarbeitskonflikte `0/100`.

Tests: 137 unittest-Tests erfolgreich, inklusive Persistenz, Statuswechsel, Dubletten, mehr als acht aktive Begriffe, Mehrfachherkunft, Statistiken, Ollama-Fehlerfallback und Score-Kalibrierung.

- Finaler Release-Build erfolgreich nach `App/JobScoutAI.exe` uebernommen; vorherige App unter `Backups/App_before_build_20260802_201817` gesichert.
- GUI-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.29`, korrekt getrennte Pool-/Vorschlagsbereiche, deaktivierten Suchbutton ohne aktive Begriffe, normales Schliessen und keinen verbleibenden Prozess.

## Version 2.28 - SerpApi-Kontingent und Arbeitnow - 2026-07-29

- Brave aus dem aktiven Code entfernt und `WebSearchProvider` auf die offizielle SerpApi Google Search API umgestellt.
- Kostenlosen SerpApi-Account-Endpunkt fuer Status, Tarif und verbleibende Monatsanfragen angebunden.
- Lokalen Ersatzzaehler `data/serp_api_usage.json` mit automatischem Monatswechsel ergaenzt, falls SerpApi keine Kontingentfelder liefert.
- Fehlender oder ungueltiger Key, Netzwerkfehler und Monatslimit deaktivieren nur die Websuche; alle uebrigen Provider laufen weiter.
- Einstellungen zeigen SerpApi-Status und verbleibende Anfragen ohne den GUI-Thread zu blockieren.
- `ArbeitnowProvider` als normaler Provider integriert; kostenlose oeffentliche API, kein Key, begrenzte sequenzielle Seitenabrufe und lokale Filterung.
- Arbeitnow liefert reale aktuelle deutsche Stellen, unterstuetzt aber keine exakte Radius-Suche. Die Nutzungsbedingungen verlangen einen Link zur Quelle; dieser ist in den Einstellungen vorhanden.
- SerpApi und Arbeitnow wurden real erreicht. Relevanzfilter wurden nach dem Live-Test verschaerft, damit reine Produktseiten und fachfremde Feed-Treffer nicht als Stellen erscheinen.
- Positiver Live-Test fuer `Software Engineer` in Berlin: 9 relevante SerpApi-Webfundstellen und 6 Arbeitnow-Stellen; offizieller SerpApi-Stand danach 248 / 250.
- Einmalige Provider-Katalogmigration aktiviert konfigurierte Websuche, Karriereseiten und Arbeitnow auch in bestehenden Nutzer-Settings; spaetere manuelle Abwahlen bleiben erhalten.

Tests: 131 unittest-Tests erfolgreich.

- Release-Build erfolgreich nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260729_215021`.
- EXE-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.28`, reagierendes Fenster, normales Schliessen und Exitcode 0.

## Version 2.27 - Websuche und Karriereseiten - 2026-07-29

- `WebSearchProvider` als normaler Provider mit austauschbarem `WebSearchBackend` integriert; erste Implementierung ist die offizielle Brave Search API.
- `CareerPagesProvider` fuer explizit konfigurierte oeffentliche Karriereseiten integriert.
- Neuer `EthicalHttpClient` respektiert `robots.txt`, eindeutigen User-Agent, Timeouts, Host-Rate-Limits und auswertbares `Crawl-delay`.
- Karriereseiten werden ohne Browserautomation sequenziell gelesen; primaer wird standardisiertes `JobPosting`-JSON-LD genutzt, ergaenzt durch einen begrenzten HTML-Fallback fuer direkte Stellenunterseiten.
- Beide Provider liefern das bestehende `Job`-Modell und verwenden unveraendert Pipeline, Diagnose, Deduplizierung, faire Mischung, Pagination, Persistenz, KI-Jobsuche und KI-Analyse.
- Neue Konfiguration: `BRAVE_SEARCH_API_KEY` und semikolongetrennte `CAREER_SITE_URLS`.
- Reale Karriereseiten-Pruefung erfolgreich: eine oeffentliche Greenhouse-Stelle wurde nach robots.txt-Pruefung als `Karriereseite` mit Titel und Firma erkannt.
- Websuche im realen Projekt sauber als nicht konfiguriert erkannt, da kein `BRAVE_SEARCH_API_KEY` vorhanden ist; es erfolgte kein inoffizielles Suchmaschinen-Scraping.
- Release-Build erfolgreich erstellt; die vorherige App liegt unter `Backups/App_before_build_20260729_205503`.
- EXE-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.27`, normales Schliessen ohne erzwungenes Beenden und Exitcode 0.

Tests: 124 unittest-Tests erfolgreich.

## Version 2.26 - KI-Analyse zeigt alle besten Treffer - 2026-07-29

- Darstellungsfehler in `KI-Analyse` behoben: Der Abschnitt `Beste Treffer` war versehentlich per Slice auf 5 Karten begrenzt.
- Die Anzeige nutzt jetzt zentral `LOCAL_AI_ANALYSIS_BEST_MATCH_DISPLAY_LIMIT`; Standard `0` bedeutet unbegrenzt.
- Statistik und sichtbare Trefferkarten bleiben damit konsistent: 16 KI-bewertete Kandidaten erzeugen 16 Karten.
- Release-Build erfolgreich erstellt; Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.26`, normales Schliessen und Exitcode 0.

## Version 2.25 - KI-Jobsuche - 2026-07-29

- Neue Hauptseite `KI-Jobsuche`: `qwen3:8b` erzeugt aus Nutzerprofil und KI-Bewertungskriterien bis zu 8 editierbare Jobbezeichnungen.
- Die KI darf keine Arbeitsbedingungen, Orte oder Filter als Suchbegriffe verwenden; solche Angaben bleiben Kriterien fuer die spaetere Stellenbewertung.
- Jeder bestaetigte Suchbegriff startet einen eigenen vollstaendigen Suchlauf ueber die vorhandene SearchPipeline und alle aktiven Provider.
- Nach Abschluss werden alle Ergebnisse gemeinsam dedupliziert, gespeichert und in der normalen Trefferliste angezeigt.
- Treffer behalten transparent `ki_suchbegriffe`, damit sichtbar bleibt, ueber welchen KI-Suchbegriff ein Job gefunden wurde; Dubletten fuehren mehrere Begriffe zusammen.
- Reale qwen3:8b-Suchplanung erfolgreich getestet; Varianten-Dubletten wie Kaufmann/Kauffrau werden nachbereinigt.
- Release-Build erfolgreich erstellt; Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.25`, normales Schliessen und Exitcode 0.

Tests: 111 unittest-Tests und Cockpit-Tests erfolgreich.

## Version 2.24 - KI-Buttons und Pagination nachgebessert - 2026-07-29

- Laufende KI-Analysen zeigen nur noch auf dem Startbutton `Analyse laeuft...`; der Folgeschritt-Button bleibt als `KI-Analyse ansehen` sichtbar, ist aber deaktiviert.
- Nach vollstaendig echter Ollama-Auswertung wird `Zur KI-Analyse` aktiv und gruen hervorgehoben. Technische Vorbewertungen bleiben neutral und werden nicht als erfolgreicher KI-Folgeschritt dargestellt.
- Die Buttontexte, Aktivierungszustaende und Farben werden weiterhin zentral aus `ki_aktionszustand` abgeleitet.
- Beim Wechsel mit `Weiter` oder `Zurueck` springt die scrollbare Ergebnisliste automatisch an den Seitenanfang.

## Version 2.23 - Stabile lokale KI-Analyse - 2026-07-29

- Ursache der bisherigen Ollama-Ausfaelle reproduziert: Der 16K-Kontext lagerte Teile der Berechnung auf die CPU aus; `qwen3:8b` rechnete beim 90-Sekunden-Abbruch noch und wurde durch den Client-Abbruch beendet.
- Ollama-Aufruf auf strukturiertes JSON, deaktivierten Denkmodus, 8K-Kontext, maximal 2.048 Ausgabetoken und zehn Minuten Modellvorhaltung umgestellt.
- Sicherheitslimit auf 240 Sekunden gesetzt; die kuerzeren Laufzeiten entstehen primaer durch das passendere Inferenzprofil, nicht durch pauschales Warten.
- Diagnose protokolliert Modell, Laufzeit, Prompt- und Ausgabetoken sowie Abschlussgrund, aber keine Prompt-, Profil- oder Stellendaten.
- Analyseergebnisse unterscheiden jetzt `echt`, `teilweise` und `technisch`; fehlende Einzelantworten werden separat und sichtbar technisch vorbewertet.
- Leere Bewertungs- und Nutzerprofilfelder werden nicht an Ollama uebergeben; lange Freitexte werden fuer den stabilen 8K-Kontext begrenzt.
- Suche und KI-Analyse sperren sich gegenseitig. Der Startbutton zeigt waehrend des Laufs `Analyse laeuft...`; der Folgeschritt bleibt sichtbar und deaktiviert.
- Nach einer vollstaendigen echten Ollama-Auswertung erscheint `KI-Analyse ansehen` als gruen hervorgehobener Folgeschritt. Technische Vorbewertungen bleiben neutral und werden nicht als KI-Erfolg dargestellt.
- Realer Integrationstest mit dem installierten `qwen3:8b`: 2.161 Treffer lokal gescreent, 12 Top-Kandidaten in 61,5 Sekunden echt bewertet, 0 technische Fallbacks, Gesamtfazit vorhanden.
- Portabler Build erfolgreich nach `App/JobScoutAI.exe` uebernommen; die vorherige App liegt unter `Backups/App_before_build_20260729_173616`.
- Release-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.23`, reagierendes Fenster, normales Schliessen und Exitcode 0.

Tests: 106 unittest-Tests erfolgreich.

## Version 2.22 - Codex-only Entwicklung und neutrales Projektcockpit - 2026-07-29

- Lokale Ollama-Worker fuer Coding, Reviews und Dokumentationsaufgaben aus dem aktiven Entwicklungsstand entfernt.
- Entwicklung, Dateianderungen, Tests, Build und Dokumentationspflege liegen wieder vollstaendig bei Codex.
- `qwen3:8b` bleibt unveraendert als lokale Laufzeit-KI fuer die Stellenanalyse in JobScout AI erhalten.
- Das Projektcockpit wurde aus der Delegationslogik geloest und wird nun netzwerkfrei durch `developer_tools/project_cockpit.py` erzeugt.
- Die Startdatei `App/JobScoutAI_Projektuebersicht_anzeigen.bat` bleibt der eindeutige visuelle Einstieg und zeigt Version, Build, Projektverlauf, Ziele, Grenzen und Backups.
- Historische Delegationsprotokolle wurden aus dem aktiven Source-Stand entfernt und bleiben im Backup `Backups/manual_20260729_162634` wiederherstellbar.
- Tests fuer die neutrale Cockpit-Erzeugung und die klare Grenze zwischen Codex-Entwicklung und App-Laufzeit-KI ergaenzt.
- Portable EXE erfolgreich gebaut; Release-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.22`, reagierendes Fenster, normales Schliessen und Exitcode 0.

Tests: 102 unittest-Tests erfolgreich. AST-Syntaxcheck fuer 40 Python-Dateien erfolgreich.

## Version 2.21 - Nutzerprofil und besserer KI-Workflow - 2026-07-29

- Neue Hauptseite `Nutzerprofil` ergaenzt. Dort koennen Kurzprofil, Berufserfahrung, Staerken, Kenntnisse, Wunschrolle und Einschraenkungen fuer die lokale KI gespeichert werden.
- KI-Bewertungskriterien erweitert um Arbeitszeit, Mindestgehalt, Wunschgehalt, Gehaltsmodell, gewuenschte Taetigkeiten, Ausschlusskriterien und Prioritaet.
- Jobsuche zeigt direkt nach dem Suchlauf den Button `Treffer mit KI bewerten`; der Wechsel zur KI-Analyse erfolgt danach bewusst ueber `Zur KI-Analyse`.
- KI-Auswertung springt nach Abschluss nicht mehr ungefragt aus der aktuellen Ansicht.
- Ergebnis-Pagination von 25 auf 12 Karten pro Seite reduziert, damit das Scrollen in der CustomTkinter-Liste fluessiger bleibt.
- Ollama-Prompt nutzt jetzt Kriterien und Nutzerprofil gemeinsam als Bewertungsbasis.
- Wenn Ollama keine verwertbaren Einzelbewertungen liefert, erzeugt JobScout AI eine klar gekennzeichnete technische Vorbewertung statt leerer KI-Ergebnisse.
- Echter Ollama-Test mit `qwen3:8b`: zweiter Lauf mit 90 Sekunden bewertete zwei Teststellen erfolgreich; erster Kaltstart-Test mit 45 Sekunden lief in Timeout.
- Portable EXE erfolgreich gebaut; Release-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.21`, reagierendes Fenster und vollstaendiges Beenden.

Tests: 106 unittest-Tests erfolgreich.

## Version 2.20 - Moderne Arbeitsoberflaeche - 2026-07-28

- Hauptfenster als klar gegliederte Desktop-Arbeitsoberflaeche mit fester Seitenleiste und Kopfzeile neu aufgebaut.
- Neue Hauptseiten `Dashboard`, `Jobs suchen`, `Bewerbungen`, `KI-Analyse` und `Einstellungen`.
- Dashboard zeigt aktuelle Treffer, gespeicherte Stellen, aktive Bewerbungen, durchschnittlichen KI-Match sowie Diagramme fuer Quellen und haeufige Anforderungen.
- KI-Analyse zeigt Kennzahlen, Match-Verteilung, farbige Bewertungsbalken, Gesamtfazit und ausfuehrliche Top-Kandidaten.
- Jobsuche, Bewerbungsfilter und KI-Kriterien sind visuell und funktional getrennt; die Provider-Suche bleibt von der manuellen Ollama-Auswertung entkoppelt.
- Darstellung `System`, `Hell` oder `Dunkel` kann ueber Einstellungen gewaehlt werden und wird in `settings.json` gespeichert.
- Fensterstandard auf `1280 x 820` angehoben und Mindestgroesse `1040 x 700` ergaenzt.
- Karten, Statusbereiche, Typografie, Abstaende und Farbhierarchie fuer schnelleres Erfassen ueberarbeitet.
- GUI-Smoke-Test rendert alle neuen Seiten sowie Dashboard-, KI- und Jobkarten mit Beispieldaten fehlerfrei.
- Ein begrenzter UI-Review mit lokalem `qwen3:8b` wurde angefordert, lief jedoch in einen Timeout und lieferte keine verwertbaren Befunde; Codex hat die Umsetzung und Pruefung vollstaendig uebernommen.
- Portable EXE erfolgreich gebaut; Release-Smoke-Test bestaetigte Fenstertitel `JobScout AI v2.20`, reagierendes Fenster und vollstaendiges Beenden.

Tests: 106 unittest-Tests erfolgreich.

## Version 2.17 - Mehr Provider-Seiten - 2026-07-27

- Bundesagentur, Jooble und Adzuna laden bis zu 4 Ergebnisseiten pro Suchlauf statt nur Seite 1.
- `MAX_PROVIDER_PAGES = 4` als Schutzgrenze ergaenzt, damit breite Suchen mehr Treffer liefern, aber nicht endlos API-Seiten abrufen.
- Provider stoppen frueh, wenn eine Quelle weniger als `MAX_SEARCH_RESULTS` Treffer auf einer Seite liefert.
- KI-Screening beruecksichtigt dadurch einen groesseren deduplizierten Trefferpool und waehlt daraus Top-Kandidaten.
- KI-Prompt verlangt fuer jeden gelieferten Top-Kandidaten eine Bewertung, auch wenn die Empfehlung nur `anschauen` oder `ignorieren` ist.
- Tests fuer mehrseitige Providerabrufe bei Bundesagentur, Jooble und Adzuna ergaenzt.

Tests: 104 unittest-Tests erfolgreich.
## Version 2.16 - KI-Screening aller Treffer - 2026-07-27

- Lokales Vorscreening bewertet alle aktuellen Suchtreffer anhand Suchbegriff, Ort, Kriterien und Datenqualitaet.
- Ollama bekommt danach die besten Top-Kandidaten zur Detailanalyse, statt nur die ersten Treffer der Ergebnisliste.
- Standardlimit fuer detaillierte lokale KI-Analyse von 5 auf 12 Top-Kandidaten erhoeht.
- Ollama-Kontext und Timeout fuer groessere Kandidatenlisten angehoben.
- Statusmeldung zeigt jetzt, wie viele Treffer insgesamt beruecksichtigt und wie viele Top-Kandidaten analysiert wurden.
- Tests fuer Vorsortierung ueber alle Treffer und neue Analyse-Meldung ergaenzt.

Tests: 101 unittest-Tests erfolgreich.
## Version 2.15 - Bessere KI-Zusammenfassung - 2026-07-27

- KI-Prompt fordert eine verpflichtende Gesamtzusammenfassung mit Gesamtpassung, Trefferart, Einschraenkungen und naechster Pruefung.
- KI-Reiter nutzt ein lokales Fallback-Gesamtfazit, wenn Ollama zwar Jobs bewertet, aber keine globale `summary` liefert.
- Beste-Treffer-Karten zeigen jetzt Kurzfazit, Passungsgruende, offene Punkte und Anforderungen statt nur Staerken.
- Tests fuer Promptvorgaben, Fallback-Gesamtfazit und Trefferkarten-Texte ergaenzt.

Tests: 99 unittest-Tests erfolgreich.
## Version 2.14 - Projektcockpit fuer Delegationen und Verlauf - 2026-07-27

- `Ollama_Delegationen_anzeigen.bat` erzeugt weiterhin die HTML-Uebersicht, diese zeigt nun aber mehr als reine Worker-Delegationen.
- HTML-Cockpit ergaenzt um aktuellen Projektstand, Changelog-Verlauf, naechste Ziele, bekannte Grenzen und aktuelle Backups.
- Echte Ollama-Delegationen bleiben separat nachvollziehbar, Codex-Aenderungen ohne Worker erscheinen ueber den Projektverlauf.
- Tests fuer die erweiterten Cockpit-Inhalte ergaenzt.
- `JobScoutAI_Projektuebersicht_anzeigen.bat` liegt nun direkt im `App`-Ordner neben der EXE und erzeugt die Projektuebersicht aus `Source` neu.

Tests: 97 unittest-Tests erfolgreich.
## Version 2.13 - Manuelle KI-Zusammenfassung - 2026-07-27

- Provider-Suche und lokale Ollama-Auswertung getrennt, damit Suchergebnisse schneller sichtbar werden.
- Neuer Ablauf: erst Jobs suchen, dann `KI-Zusammenfassung aktualisieren` mit den aktuell gesetzten Kriterien starten.
- Kriterienaenderungen markieren vorhandene KI-Zusammenfassungen als nicht aktuell.
- KI-Auswertung kann dieselben aktuellen Treffer mit geaenderten Kriterien erneut bewerten und speichert die neuen KI-Daten.
- Tests fuer getrennte Pipeline-Suche und separate Service-KI-Auswertung ergaenzt.

Tests: 97 unittest-Tests erfolgreich.
## Version 2.12 - KI-Bewertungskriterien - 2026-07-27

- Suchmaske um gespeicherte KI-Bewertungskriterien erweitert: Homeoffice/Remote, Teilzeit, Vollzeit, Wohnortnaehe, Remote-Modus, Pendel-/Entfernungsgrenze und Freitext.
- `SearchRequest` transportiert das Kriterienprofil bis zur lokalen Ollama-Auswertung.
- KI-Prompt nutzt die Kriterien als Bewertungsprofil und behandelt nicht beurteilbare Punkte als offene Pruefung.
- Tests fuer Kriterienfluss, Promptinhalt und UI-Helfer ergaenzt.

Tests: 96 unittest-Tests erfolgreich.
## Version 2.11 - KI-Zusammenfassung und Hintergrundsuche - 2026-07-26

- Jobsuche aus dem GUI-Thread geloest: Provider-Suche und lokale Ollama-Auswertung laufen im Hintergrund.
- Neuer Reiter `KI-Zusammenfassung` mit Gesamtfazit, besten Treffern, offenen Punkten, haeufigen Anforderungen und Hinweis zur Datenqualitaet.
- KI-Prompt beruecksichtigt gekuerzte Provider-Beschreibungen und wertet fehlende Details nicht automatisch negativ.
- Tests erweitert fuer KI-Prompt und KI-Uebersichtshelfer.

Tests: 93 unittest-Tests erfolgreich.

## Version 2.10 - Lokale KI-Auswertung Stufe 1 - 2026-07-26

- Lokale Ollama-Auswertung fuer Suchergebnisse eingebunden.
- `qwen3:8b` als Analysemodell fuer Jobbewertungen genutzt.
- Jobmodell um KI-Felder erweitert: Zusammenfassung, Match-Score, Empfehlung, Staerken, Risiken und Skills.
- GUI zeigt KI-Hinweise auf Jobkarten und in Details.
- Codex-Ollama-Delegationswerkzeuge und HTML-Uebersicht dokumentiert.

Tests: 91 unittest-Tests erfolgreich.

## Version 2.9.1 - Stabilisierte Providersuche - 2026-07-25

- Providerstruktur fuer Bundesagentur fuer Arbeit, Jooble und Adzuna stabilisiert.
- Persistenz, Deduplizierung, Filterung und Bewerbungsverwaltung ausgebaut.
- Portable Buildstruktur fuer Windows vorbereitet.

## Historische Vorversionen

- Fruehe Prototypen, alte Buildordner und Vorversionen wurden im Zuge der Primaerordner-Struktur nach `Backups` archiviert.
- Aktive Entwicklung findet seit der Umstrukturierung nur noch in `Source` statt.












