from typing import Iterable

from config import STANDARD_SETTINGS
from models import Job
from paths import DATA_ORDNER as DATA
from paths import JOBS_DATEI as JOBS
from paths import SETTINGS_DATEI as SETTINGS
from repositories import JsonJobRepository, JsonSettingsRepository

STANDARD = STANDARD_SETTINGS

_settings_repository = JsonSettingsRepository(SETTINGS, STANDARD)
_job_repository = JsonJobRepository(JOBS)


def lade_settings():
    return _settings_repository.laden()


def speichere_settings(settings):
    _settings_repository.speichern(settings)


def lade_jobs():
    return _job_repository.laden()


def speichere_jobs(jobs: Iterable[Job]):
    _job_repository.speichern(jobs)
