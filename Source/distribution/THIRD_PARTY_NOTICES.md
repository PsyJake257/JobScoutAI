# JobScout AI - Lizenzinformationen

Gilt für die portable Windows-Ausgabe; Komponentenstand siehe `COMPONENTS.md`.

JobScout AI wird unter der MIT-Lizenz weitergegeben. Der vollstaendige Text
liegt unter `licenses/LICENSE-JOBSCOUT-AI.txt`.

## Lokale KI

- Modell: Gemma 4 E2B IT, GGUF Q4_K_M
- Urheber/Projekt: Google DeepMind; GGUF-Quantisierung von Unsloth
- Lizenz: Apache License 2.0
- Modellinformation: https://ai.google.dev/gemma/docs/core/model_card_4
- Artefakt: https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF
- Vollständiger Lizenztext: `licenses/GEMMA4_E2B_LICENSE.txt`
- Exakte Revision, Dateigröße und SHA-256: `MODEL-PROVENANCE.json`

Das Modell arbeitet lokal. Stellenanzeigen, Nutzerprofile und
Bewertungskriterien werden fuer die KI-Auswertung nicht an einen externen
KI-Dienst gesendet.

## KI-Laufzeit

- Komponente: llama.cpp / ggml mit CPU- und Vulkan-Backend
- Lizenz: MIT License
- Projekt: https://github.com/ggml-org/llama.cpp
- Vollständiger Lizenztext: `licenses/LLAMA_CPP_LICENSE.txt`
- Weitere Laufzeittexte: `licenses/CPP_HTTPLIB_LICENSE.txt`, `licenses/LLVM-LICENSE.txt`

Der portable Build bevorzugt Vulkan/GPU und versucht bei Startproblemen die
CPU-Laufzeit. Der Server läuft ausschließlich auf `127.0.0.1` an einem zufälligen
Port mit temporärem Zugriffsschlüssel im Offline-Modus. Er wird beim Beenden
von JobScout AI geschlossen. Ollama ist nicht enthalten.

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

Gemma 4 E2B wird als unverändertes Q4_K_M-Artefakt der dokumentierten Unsloth-
Revision weitergegeben, nicht als eigene Modellkreation. Hersteller und Markeninhaber
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
