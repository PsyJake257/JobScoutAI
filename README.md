# JobScout AI

Kostenloser Windows-Assistent für Stellensuche, Bewerbungsorganisation und
lokale KI-Auswertung. Portable App ohne Installation, mit vollständig
enthaltenem Qwen3-4B-Modell. Public Preview: **2.40.2**.

## Fertige App herunterladen

Unter [Releases](https://github.com/PsyJake257/JobScoutAI/releases/tag/v2.40.2)
beide Dateien herunterladen:

- `JobScoutAI-Portable-2.40.2.7z.001`
- `JobScoutAI-Portable-2.40.2.7z.002`

Beide im selben Ordner lassen. `.001` mit [7-Zip](https://www.7-zip.org/)
entpacken; der zweite Teil wird automatisch verwendet. Danach
`JobScoutAI.exe` starten. **„Source code (zip)“ enthält nur den Quellcode,
nicht die fertige App und das KI-Modell.**

Solange das Repository privat ist, können nur eingeladene Personen auf
Quellcode und Downloads zugreifen.

## Funktionen

- Stellen aus mehreren wählbaren Suchquellen finden und sortieren
- normale Jobsuche und KI-Vorschläge für passende Berufsbezeichnungen
- Suchbegriffe und mehrere persönliche Profile speichern und laden
- Stellen speichern, nach Bewerbungsstatus filtern und Status direkt ändern
- lokale KI-Analyse mit Match-Wert, Stärken und offenen Punkten
- geführte Einführung und API-Einrichtung direkt in den Einstellungen
- Profile, Einstellungen und Bewerbungsdaten lokal im App-Ordner speichern

## Voraussetzungen

Windows 10/11 x64, mindestens 8 GB RAM empfohlen. Für Archiv und entpackte App
etwa 8 GB freien Speicher einplanen. Die CPU-KI kann beim Laden und Rechnen
Zeit benötigen. Für Stellenquellen ist Internet erforderlich.

Arbeitsagentur und Arbeitnow benötigen keinen persönlichen Schlüssel.
Weitere Quellen erfordern eigene, rechtmäßig bezogene API-Zugänge und können
Gebühren oder Limits haben. Einrichtung unter Einstellungen. Keine privaten
API-Schlüssel oder Nutzerprofile sind Bestandteil des Downloads.

## Datenschutz und Grenzen

KI-Auswertung und Profile bleiben bei der mitgelieferten lokalen Laufzeit auf
dem Computer. Suchanfragen verbinden sich mit den ausgewählten Anbietern;
diese erhalten Anfrage- und technische Verbindungsdaten. `.env`, `data/`
und Logs sind unverschlüsselte lokale Dateien. Nicht weitergeben.
Siehe [Datenschutzhinweise](PRIVACY.md).

KI-Vorschläge können falsch sein. Die App unterstützt die eigene Jobsuche,
nicht die automatisierte Personalauswahl. Keine Garantie für Verfügbarkeit,
Richtigkeit oder Erfolg. Keine Verbindung zu den Stellenanbietern und keine
Zusage einer offiziellen oder dauerhaft unterstützten API.

## Quellcode und Entwicklung

Der eigene Quellcode steht unter [MIT](LICENSE). Python 3.12 verwenden:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Source/requirements.txt
.\.venv\Scripts\python.exe Source/main.py
```

Für KI im Quellcode-Modus muss eine eigene lokale Ollama-Laufzeit mit
`qwen3:4b` vorhanden sein. Das große Modell wird nur im portablen Download
mitgeliefert, nicht in Git gespeichert. Optionale API-Werte sind in
`.env.example` dokumentiert; die App legt `Source/.env` über die Einstellungen an.

Gezielte Tests, vom Ordner `Source` aus: `python -m unittest discover -s tests`.
GUI-Build: in `Source` mit dem Python der virtuellen Umgebung
`python -m PyInstaller --noconfirm JobScoutAI.spec`. Dieser GUI-Build allein
enthält noch nicht Ollama und das Modell; Lizenztexte und externe Laufzeit
müssen für eine Weitergabe ebenfalls vollständig beigefügt werden.
Die Version wird ausschließlich in `Source/config.py` gepflegt.

## Lizenzen und Weitergabe

Qwen3-4B: Apache-2.0; Ollama: MIT. Andere Komponenten behalten ihre Lizenzen.
Die MIT-Lizenz des eigenen Codes ersetzt nicht die Lizenzen fremder
Bibliotheken, Windows-Laufzeitdateien, Schriften oder Anzeigeninhalte.

- [Komponenten und Quellen](Source/distribution/COMPONENTS.md)
- [Lizenzübersicht](Source/distribution/THIRD_PARTY_NOTICES.md)
- [Originaltexte](Source/distribution/licenses/)
- [Nutzung und Weitergabe](REDISTRIBUTION_TERMS.md)
- [Sicherheitsmeldungen](SECURITY.md)

Alle Hinweise liegen auch im App-Paket; die Einstellungen öffnen die
Lizenzübersicht. Das Projekt wird kostenlos und nichtkommerziell angeboten;
dies schränkt die MIT-Rechte für andere nicht zusätzlich ein. Keine
anwaltliche Zusicherung vollständiger rechtlicher Konformität.
