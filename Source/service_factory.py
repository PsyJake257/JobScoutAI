from analysis import AiAnalysisStep
from application import JobSearchService
from config import LOCAL_AI_ANALYSIS_ENABLED, LOCAL_AI_ANALYSIS_MAX_JOBS, STANDARD_SETTINGS
from filters import JobFilter
from paths import JOBS_DATEI, NUTZERPROFILE_DATEI, SETTINGS_DATEI, SUCHBEGRIFFE_DATEI, SUCHBEGRIFF_SETS_DATEI
from pipeline import SearchPipeline
from providers import standard_provider_registry
from repositories import (
    JsonJobRepository,
    JsonSearchTermRepository,
    JsonSearchTermSetRepository,
    JsonSettingsRepository,
    JsonUserProfileRepository,
)


def erstelle_job_search_service() -> JobSearchService:
    pipeline = SearchPipeline(
        provider_registry=standard_provider_registry(),
        job_filter=JobFilter(),
        ai_analysis=AiAnalysisStep(
            enabled=LOCAL_AI_ANALYSIS_ENABLED,
            max_jobs=LOCAL_AI_ANALYSIS_MAX_JOBS,
        ),
    )

    job_repository = JsonJobRepository(JOBS_DATEI)
    job_repository.bestand_bereinigen_mit_sicherung()

    return JobSearchService(
        pipeline=pipeline,
        job_repository=job_repository,
        settings_repository=JsonSettingsRepository(SETTINGS_DATEI, STANDARD_SETTINGS),
        search_term_repository=JsonSearchTermRepository(SUCHBEGRIFFE_DATEI),
        search_term_set_repository=JsonSearchTermSetRepository(SUCHBEGRIFF_SETS_DATEI),
        user_profile_repository=JsonUserProfileRepository(NUTZERPROFILE_DATEI),
    )
