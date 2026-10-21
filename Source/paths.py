import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASIS_ORDNER = Path(sys.executable).resolve().parent
    RESSOURCEN_ORDNER = Path(getattr(sys, "_MEIPASS", BASIS_ORDNER)).resolve()
else:
    BASIS_ORDNER = Path(__file__).resolve().parent
    RESSOURCEN_ORDNER = BASIS_ORDNER

DATA_ORDNER = BASIS_ORDNER / "data"
ASSET_ORDNER = RESSOURCEN_ORDNER / "assets"
APP_LOGO_DATEI = ASSET_ORDNER / "jobscout_logo.png"
APP_ICON_DATEI = ASSET_ORDNER / "jobscout_icon.ico"
SETTINGS_DATEI = DATA_ORDNER / "settings.json"
JOBS_DATEI = DATA_ORDNER / "jobs.json"
SUCHBEGRIFFE_DATEI = DATA_ORDNER / "search_terms.json"
SUCHBEGRIFF_SETS_DATEI = DATA_ORDNER / "search_term_sets.json"
NUTZERPROFILE_DATEI = DATA_ORDNER / "user_profiles.json"
LOG_ORDNER = DATA_ORDNER / "logs"
LOG_DATEI = LOG_ORDNER / "jobscout.log"
SERP_NUTZUNG_DATEI = DATA_ORDNER / "serp_api_usage.json"
THIRD_PARTY_NOTICES_DATEI = BASIS_ORDNER / "THIRD_PARTY_NOTICES.md"
if not THIRD_PARTY_NOTICES_DATEI.exists() and not getattr(sys, "frozen", False):
    THIRD_PARTY_NOTICES_DATEI = BASIS_ORDNER / "distribution" / "THIRD_PARTY_NOTICES.md"
