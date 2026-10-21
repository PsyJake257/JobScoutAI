APP_NAME = "JobScout AI"
VERSION = "2.40.2"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820
HTTP_TIMEOUT_SECONDS = 12
SERP_SEARCH_TIMEOUT_SECONDS = 45
MAX_SEARCH_RESULTS = 25
MAX_PROVIDER_PAGES = 4
RESULTS_PER_PAGE = 12
MIN_SEARCH_RADIUS_KM = 1
MAX_SEARCH_RADIUS_KM = 200
ACTIVE_PROVIDER_NAMES = ["arbeitsagentur", "jooble", "adzuna", "websuche", "karriereseiten", "arbeitnow"]
ETHICAL_SCRAPING_USER_AGENT = f"JobScoutAI/{VERSION} (private local job search; ethical crawler)"
ETHICAL_SCRAPING_USER_AGENT_TOKEN = "JobScoutAI"
ETHICAL_REQUEST_DELAY_SECONDS = 1.0
SERP_SEARCH_MONTHLY_LIMIT = 250
SERP_SEARCH_MAX_PAGES = 2
SERP_SEARCH_RATE_LIMIT_SECONDS = 1.0
ARBEITNOW_MAX_PAGES = 2
ARBEITNOW_RATE_LIMIT_SECONDS = 1.0
PROVIDER_429_RETRY_ATTEMPTS = 1
PROVIDER_429_MAX_WAIT_SECONDS = 15.0
CAREER_SITE_MAX_PAGES_PER_SITE = 12
LOCAL_AI_ANALYSIS_ENABLED = True
LOCAL_AI_ANALYSIS_MODEL = "qwen3:4b"
LOCAL_AI_ANALYSIS_MAX_JOBS = 12
LOCAL_AI_ANALYSIS_TIMEOUT_SECONDS = 240
LOCAL_AI_ANALYSIS_CONTEXT_TOKENS = 8192
LOCAL_AI_ANALYSIS_MAX_OUTPUT_TOKENS = 2048
LOCAL_AI_ANALYSIS_KEEP_ALIVE = "10m"
LOCAL_AI_DEDUPLICATION_MAX_PAIRS = 12
LOCAL_AI_ANALYSIS_BEST_MATCH_DISPLAY_LIMIT = 0
LOCAL_AI_JOB_SEARCH_MAX_TERMS = 8
GOOD_MATCH_SCORE_THRESHOLD = 60

STANDARD_SETTINGS = {
    "einleitung_abgeschlossen": False,
    "suchbegriff": "",
    "ort": "",
    "umkreis": "30",
    "provider": ACTIVE_PROVIDER_NAMES,
    "ki_ort": "",
    "ki_umkreis": "30",
    "ki_provider": ACTIVE_PROVIDER_NAMES,
    "darstellung": "system",
    "ki_kriterien": {
        "homeoffice": False,
        "teilzeit": False,
        "vollzeit": False,
        "wohnortnaehe": False,
        "remote_modus": "egal",
        "max_pendeln": "",
        "arbeitszeit": "",
        "mindestgehalt": "",
        "wunschgehalt": "",
        "gehaltsmodell": "",
        "gewuenschte_taetigkeiten": "",
        "ausschlusskriterien": "",
        "prioritaet": "Ausgewogen",
        "freitext": "",
    },
    "nutzerprofil": {
        "kurzprofil": "",
        "berufserfahrung": "",
        "staerken": "",
        "kenntnisse": "",
        "wunschrolle": "",
        "einschraenkungen": "",
    },
    "nutzerprofil_auswahl": "",
}

