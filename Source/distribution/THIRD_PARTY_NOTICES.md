# JobScout AI - Lizenzinformationen

Gilt für die portable Windows-Ausgabe; Komponentenstand siehe `COMPONENTS.md`.

JobScout AI wird unter der MIT-Lizenz weitergegeben. Der vollstaendige Text
liegt unter `licenses/LICENSE-JOBSCOUT-AI.txt`.

## Lokale KI

- Modell: Qwen3 4B, Ollama-Tag `qwen3:4b`, Q4_K_M
- Urheber/Projekt: Qwen Team / Alibaba Cloud
- Lizenz: Apache License 2.0
- Projekt: https://github.com/QwenLM/Qwen3
- Modellinformation: https://ollama.com/library/qwen3:4b
- Vollstaendiger Lizenztext: `licenses/QWEN3-APACHE-2.0.txt`

Das Modell arbeitet lokal. Stellenanzeigen, Nutzerprofile und
Bewertungskriterien werden fuer die KI-Auswertung nicht an einen externen
KI-Dienst gesendet.

## KI-Laufzeit

- Komponente: Ollama
- Lizenz: MIT License
- Projekt: https://github.com/ollama/ollama
- Vollstaendiger Lizenztext: `licenses/OLLAMA-LICENSE.txt`
- Weitere Bibliothekshinweise der Laufzeit: `licenses/ollama-vendor/`

Der portable Build enthaelt die CPU-Laufzeit. Ollama wird ausschliesslich
lokal auf `127.0.0.1` gestartet und beim Beenden von JobScout AI geschlossen.

## Anwendungsbibliotheken

- Python: Python Software Foundation License
- Tcl/Tk: BSD-aehnliche Tcl/Tk-Lizenz
- CustomTkinter: MIT License
- darkdetect: BSD 3-Clause License
- Pillow: MIT-CMU License sowie die im Pillow-Lizenztext aufgefuehrten
  Bibliothekslizenzen
- PyInstaller-Bootloader: GPLv2 mit besonderer Ausnahme fuer gebaute Programme

Die vollstaendigen mitgelieferten Lizenztexte befinden sich im Ordner
`licenses/`.

Zusätzlich enthalten: packaging (Apache-2.0 oder BSD-2-Clause), Roboto
(Apache-2.0), OpenSSL (Apache-2.0), libffi (MIT), Expat (MIT), zlib,
XZ/liblzma sowie LLVM libc++, libunwind und OpenMP (Apache-2.0 mit
LLVM-Ausnahmen) und MinGW-w64/winpthreads. Originaltexte und Quellen sind
unter `licenses/` und `COMPONENTS.md` aufgeführt. Die in Pillow enthaltenen
Bildbibliotheken sind in dessen vollständiger Sammellizenz aufgeführt.

Qwen3-4B wird als unverändertes, von Ollama bereitgestelltes Q4_K_M-Artefakt
weitergegeben, nicht als eigene Modellkreation. Hersteller und Markeninhaber
unterstützen oder zertifizieren JobScout AI damit nicht. Roboto wird
unverändert mit CustomTkinter weitergegeben. App-Logo und Icon wurden für
dieses Projekt KI-gestützt erstellt; fremde Markenrechte werden nicht gewährt.

Der MIT-Lizenztext gilt für den eigenen JobScout-AI-Quellcode, nicht pauschal
für alle enthaltenen Fremdkomponenten. Für Microsoft-Laufzeitbestandteile
gelten zusätzlich die Bedingungen in `licenses/PYTHON-LICENSE.txt` und
`REDISTRIBUTION_TERMS.md`. PyInstaller und 7-Zip sind Build-Werkzeuge;
7-Zip ist nicht Bestandteil des Downloads.

## Externe Suchdienste

JobScout AI ist nicht mit der Bundesagentur fuer Arbeit, Jooble, Adzuna,
SerpApi, Arbeitnow oder den ausgelesenen Unternehmen verbunden. Fuer externe
Suchdienste gelten deren eigene Bedingungen. Suchbegriffe und Ortsangaben
werden nur an die vom Nutzer aktivierten Quellen uebertragen. API-Schluessel
sind nicht Bestandteil dieses Builds.

Die MIT-Lizenz gewährt keine Rechte an Stellenanzeigen, Firmennamen oder
Inhalten externer Anbieter. API-Zugang, Kontingente, Gebühren und erlaubte
Nutzung richten sich nach dem jeweiligen Anbieter. Öffentliche Erreichbarkeit
eines Endpunkts ersetzt keine Nutzungsberechtigung. Keine Zusage dauerhafter
Verfügbarkeit oder offizieller Unterstützung der Suchschnittstellen.
