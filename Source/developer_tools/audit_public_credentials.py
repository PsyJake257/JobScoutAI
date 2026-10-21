"""Check distribution files and frozen Python modules without printing secrets."""

import marshal
from pathlib import Path
import sys

from PyInstaller.archive.readers import CArchiveReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providers.env_loader import lade_env_wert


KEYS = ("JOOBLE_API_KEY", "ADZUNA_APP_ID", "ADZUNA_API_KEY", "SERP_SEARCH_API_KEY")


def audit(target, personal_folders):
    secrets = {
        value.encode()
        for folder in personal_folders
        for key in KEYS
        if (value := lade_env_wert(folder / ".env", key))
    }
    findings = []
    checked = 0
    for file in target.rglob("*"):
        if not file.is_file() or "models" in file.relative_to(target).parts:
            continue
        if file.suffix.lower() in (".dll", ".pyd") or "runtime" in file.relative_to(target).parts:
            continue
        data = file.read_bytes()
        checked += 1
        if any(secret in data for secret in secrets):
            findings.append(str(file.relative_to(target)))
        if file.name == "JobScoutAI.exe":
            archive = CArchiveReader(str(file))
            pyz = archive.open_embedded_archive("PYZ.pyz")
            for name in pyz.toc:
                code = pyz.extract(name)
                raw = marshal.dumps(code)
                if any(secret in raw for secret in secrets):
                    findings.append(f"JobScoutAI.exe:{name}")
            for name, entry in archive.toc.items():
                if entry[-1] in ("s", "m", "M", "x"):
                    if any(secret in archive.extract(name) for secret in secrets):
                        findings.append(f"JobScoutAI.exe:{name}")
        if file.name == ".env":
            if any(lade_env_wert(file, key) for key in KEYS):
                findings.append("Personal API configuration present")
    print(f"Checked {checked} files plus frozen Python modules; {len(secrets)} personal values compared.")
    print("Findings: " + (", ".join(findings) if findings else "NONE"))
    return bool(findings)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "PublicBuild" / "JobScoutAI-Portable"
    raise SystemExit(audit(target, (root / "Source", root / "App")))
