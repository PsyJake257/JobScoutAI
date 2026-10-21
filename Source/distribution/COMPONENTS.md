# Komponenten und Herkunft

Bestand der Windows-x64-Ausgabe, geprüft am 21.10.2026. Die App-Version steht
in `BUILD-INFO.txt`; im Quellcode ist ausschließlich `Source/config.py`
maßgeblich. Die unten genannten Komponenten wurden nicht für JobScout AI
inhaltlich verändert; Verpackung und Auswahl von CPU-Dateien sind angepasst.

| Komponente | Version/Artefakt | Lizenz / Originalquelle |
| --- | --- | --- |
| JobScout AI | siehe BUILD-INFO | MIT, https://github.com/PsyJake257/JobScoutAI |
| Qwen3-4B | qwen3:4b, Q4_K_M | Apache-2.0, https://huggingface.co/Qwen/Qwen3-4B ; https://ollama.com/library/qwen3:4b |
| Ollama | 0.40.6, CPU-Dateien | MIT, https://github.com/ollama/ollama |
| Python | 3.12.14, x64 | PSF und enthaltene Fremdhinweise, https://www.python.org/ ; https://docs.python.org/3.12/license.html |
| Tcl/Tk | 8.6 | mitgelieferte license.terms, https://www.tcl-lang.org/ |
| CustomTkinter | 6.0.0 | MIT, https://github.com/TomSchimansky/CustomTkinter |
| darkdetect | 0.8.0 | BSD-3-Clause, https://github.com/albertosottile/darkdetect |
| packaging | 26.2 | Apache-2.0 oder BSD-2-Clause, https://github.com/pypa/packaging |
| Pillow | 12.3.0 | MIT-CMU und Sammellizenzen für eingebundene Bildbibliotheken, https://github.com/python-pillow/Pillow |
| Roboto | mit CustomTkinter gelieferte statische Fonts | Apache-2.0, Copyright 2011 Google Inc., https://github.com/googlefonts/roboto |
| OpenSSL | 3.5.8 | Apache-2.0, https://github.com/openssl/openssl/tree/openssl-3.5.8 |
| libffi, Expat, zlib, XZ/liblzma | mit Python gelieferte Bibliotheken | Originaltexte in licenses und Python-Fremdhinweisen |
| LLVM libc++, libunwind, OpenMP | mit Ollama gelieferte DLLs | Apache-2.0 mit LLVM-Ausnahmen, https://github.com/llvm/llvm-project |
| MinGW-w64/winpthreads | mit Ollama gelieferte libwinpthread-1.dll | Originaltext WINPTHREADS-LICENSE.txt, https://github.com/mingw-w64/mingw-w64 |
| llama.cpp, ggml und weitere Ollama-Abhängigkeiten | mit Ollama ausgeliefert | vollständige Originalhinweise unter licenses/ollama-vendor |
| Microsoft C-Laufzeit | mit Python gelieferte Windows-DLLs | zusätzliche Bedingungen in PYTHON-LICENSE.txt und REDISTRIBUTION_TERMS.md |
| PyInstaller-Bootloader | 6.21.0 | GPL-2.0 mit Bootloader-Ausnahme, https://pyinstaller.org/en/stable/license.html |

Die jeweiligen Unterversionen der nativen Fremdbibliotheken sind, soweit vom
Lieferanten angegeben, in dessen Lizenzsammlungen dokumentiert; nicht aus
Dateinamen abgeleitete Versionsnummern werden hier nicht behauptet.
`CHECKSUMS-SHA256.txt` identifiziert EXE, Ollama und die konkreten Modell-Blobs.
Supplementäre Lizenztexte stammen aus den offiziellen Projekten; die
Python-Sammelhinweise liegen zusätzlich als lokal lesbare HTML-Datei vor.

App-Symbole: KI-gestützt für dieses Projekt erstelltes Logo/Icon; keine
Behauptung exklusiver Markenrechte oder rechtlichen Urheberrechtsschutzes.
CustomTkinter_shapes_font gehört zu CustomTkinter und dessen MIT-Lizenz.

## Suchdienste

Die Software-Lizenzen gelten nicht für die externen Suchdienste oder Anzeigen.
Arbeitsagentur: https://www.arbeitsagentur.de/ ; Arbeitnow:
https://www.arbeitnow.com/ ; Jooble: https://jooble.org/api/about ; Adzuna:
https://developer.adzuna.com/ ; SerpApi: https://serpapi.com/ .
Es gelten die jeweils aktuellen Vertrags-, Datenschutz- und Zugangsbedingungen.
Verwendete Zugänge müssen vom Nutzer selbst rechtmäßig beschafft werden.

## Weiterentwicklung

Quellcode, Anleitung und Sicherheitshinweise stehen im GitHub-Repository.
Die Lizenztexte müssen auch bei eigener Weitergabe der Binärdateien erhalten
bleiben. Unveränderte Fremdkomponenten dürfen nicht als Eigenentwicklung
ausgegeben werden. Neue Abhängigkeiten erfordern eine erneute Lizenzprüfung.
