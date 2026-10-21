from models import SearchRequest
from service_factory import erstelle_job_search_service


def suche_jobs(suchbegriff, ort, umkreis):
    service = erstelle_job_search_service()
    return service.jobs_suchen(SearchRequest(suchbegriff, ort, umkreis))
