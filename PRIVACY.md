# Datenschutz bei der portablen Nutzung

JobScout AI speichert Einstellungen, Nutzerprofile, Suchbegriffe,
Stellenangebote und Bewerbungsstatus lokal im Ordner `data`.

Die KI-Auswertung mit Qwen3 4B erfolgt lokal auf dem Computer. Die dabei
verwendeten Stellen- und Profildaten werden nicht an einen externen KI-Dienst
gesendet.

Bei einer Stellensuche werden Suchbegriff, Ort, Radius und technisch
erforderliche Anfragedaten an die vom Nutzer aktivierten externen Suchquellen
uebertragen. Fuer diese Dienste gelten deren eigene Datenschutzbestimmungen.

Der verteilte Build enthaelt keine API-Schluessel und keine persoenlichen
Nutzerdaten. Nutzer sollten den Ordner `data` nicht an Dritte weitergeben.

Eigene API-Zugangsdaten werden auf Wunsch in der lokalen Datei `.env` neben
`JobScoutAI.exe` gespeichert. Die Eingabefelder sind standardmaessig verdeckt;
die Datei selbst ist eine unverschluesselte Textdatei. Sie wird nur fuer die
Verbindung zum jeweiligen Anbieter verwendet und darf nicht weitergegeben
werden. Das Leeren eines Zugangsfelds und Speichern entfernt den Zugang.

Auch IP-Adresse und technische Verbindungsdaten werden bei externen Anfragen
dem jeweiligen Dienst bekannt. Bei Karriereseiten und dem Öffnen von Links
entstehen Verbindungen zur jeweiligen Website. Es gibt keinen eigenen
JobScout-Cloudspeicher und keine eingebaute Nutzungsanalyse/Telemetrie.

Nicht alle Quellen senden dieselben Daten: Arbeitnow lädt öffentliche
Angebote und filtert lokal; andere APIs erhalten Suchparameter. Niemals
Geheimnisse oder Lebensläufe als
Suchbegriff verwenden.

Zum Löschen lokaler Daten die App schließen und `data/` sowie gegebenenfalls
`.env` entfernen. Eigene Sicherungen, entpackte alte Versionen und den
Papierkorb ebenfalls berücksichtigen. Logs können Suchbegriffe, Ortsangaben,
Dateipfade und Fehlermeldungen enthalten; vor Weitergabe prüfen.

Der GitHub-Download und die Nutzung der Anbieter-Websites unterliegen deren
Datenschutzregeln, nicht einer Zusage vollständiger Offline-Nutzung.
