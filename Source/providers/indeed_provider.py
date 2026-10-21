from models import Job, SearchRequest
from providers.base_provider import JobProvider


class IndeedProvider(JobProvider):
    name = "indeed"
    anzeigename = "Indeed"
    aktiv = False

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        return []
