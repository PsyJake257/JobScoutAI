# JobScout AI

Kostenloser Windows-Assistent für Stellensuche, Bewerbungsorganisation und
lokale KI-Auswertung. Portable App ohne Installation, mit vollständig
enthaltenem Gemma-4-E2B-Modell. Public Preview: **2.44.0**.

## Fertige App herunterladen

Unter [Releases](https://github.com/PsyJake257/JobScoutAI/releases/tag/v2.44.0)
beide Dateien herunterladen:

- `JobScoutAI-Portable-2.44.0.7z.001`
- `JobScoutAI-Portable-2.44.0.7z.002`

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
- KI-Vorprüfung aller ausgewählten Stellen, danach ausführliche Kurzfazits,
  Passungsgründe und offene Fragen für bis zu 15 Top-Kandidaten
- schrittweise Ergebnisse ohne kompletten Seitenaufbau nach jeder Stelle
- matte Glasoptik mit klaren Kontrasten und statischen Lichtreflexen
- geführte Einführung und API-Einrichtung direkt in den Einstellungen
- Profile, Einstellungen und Bewerbungsdaten lokal im App-Ordner speichern

## Voraussetzungen

Windows 10/11 x64, mindestens 8 GB RAM empfohlen. Für Archiv und entpackte App
etwa 10 GB freien Speicher einplanen. 16 GB RAM bieten mehr Spielraum.
Vulkan/GPU wird bevorzugt; bei Startproblemen wird die CPU-Laufzeit versucht.
Das Modell wärmt beim Programmstart im Hintergrund vor. Laden und Rechnen
können je nach Computer Zeit benötigen. Für Stellenquellen ist Internet erforderlich.

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

Für KI im Quellcode-Modus die Ordner `runtime/` und `models/` aus dem
portablen Download neben `Source/main.py` bereitstellen. Die App startet die
lokale llama.cpp-Laufzeit selbst. Das große Modell wird nur im Download
mitgeliefert, nicht in Git gespeichert. Optionale API-Werte sind in
`.env.example` dokumentiert; die App legt `Source/.env` über die Einstellungen an.

Gezielte Tests, vom Ordner `Source` aus: `python -m unittest discover -s tests`.
GUI-Build: in `Source` mit dem Python der virtuellen Umgebung
`python -m PyInstaller --noconfirm JobScoutAI.spec`. Dieser GUI-Build allein
enthält noch nicht llama.cpp und das Modell. Einen frischen vollständigen
Download erstellt `Tools/PublicBuild_erstellen.ps1 -AiAssets <Ordner>`.
Der Ordner muss `runtime/cpu`, `runtime/vulkan` und das dokumentierte GGUF
unter `models/` enthalten. Die Modell-Prüfsumme wird vor dem Kopieren geprüft;
Lizenztexte werden aus `Source/distribution` beigefügt. Danach
`Tools/PublicBuild_paketieren.ps1 -BuildPath <frischer Buildordner>` ausführen.
Die Version wird ausschließlich in `Source/config.py` gepflegt.

## Lizenzen und Weitergabe

Gemma 4 E2B: Apache-2.0; llama.cpp: MIT. Andere Komponenten behalten ihre Lizenzen.
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
