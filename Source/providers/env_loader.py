from pathlib import Path
import os
import re
import tempfile


def lade_env_wert(datei: Path, schluessel: str) -> str:
    if not datei.exists():
        return ""

    try:
        zeilen = datei.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return ""

    for zeile in zeilen:
        eintrag = zeile.strip()
        if not eintrag or eintrag.startswith("#") or "=" not in eintrag:
            continue

        name, wert = eintrag.split("=", 1)
        if name.strip() == schluessel:
            return wert.strip().strip('"').strip("'")

    return ""


def speichere_env_werte(datei: Path, werte: dict[str, str]) -> None:
    """Replace edited keys atomically, preserving unrelated settings and comments."""
    for name, wert in werte.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or any(
            zeichen in wert for zeichen in ("\r", "\n", "\0", '"', "'")
        ):
            raise ValueError("Bitte einen einzelnen Zugangswert ohne Zeilenumbruch oder Anfuehrungszeichen eingeben.")
    vorhanden = datei.read_text(encoding="utf-8-sig") if datei.exists() else ""
    zeilen = []
    bearbeitet = set()
    for zeile in vorhanden.splitlines():
        name = zeile.split("=", 1)[0].strip() if "=" in zeile else ""
        if name in werte:
            if name not in bearbeitet:
                zeilen.append(f"{name}={werte[name].strip()}")
                bearbeitet.add(name)
        else:
            zeilen.append(zeile)
    zeilen.extend(f"{name}={wert.strip()}" for name, wert in werte.items() if name not in bearbeitet)
    datei.parent.mkdir(parents=True, exist_ok=True)
    temp_pfad = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=datei.parent, delete=False) as datei_temp:
            temp_pfad = Path(datei_temp.name)
            datei_temp.write("\n".join(zeilen) + "\n")
        os.replace(temp_pfad, datei)
    finally:
        if temp_pfad is not None:
            temp_pfad.unlink(missing_ok=True)
