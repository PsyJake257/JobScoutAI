from models import Job, SearchRequest
from providers.base_provider import JobProvider


class LinkedInProvider(JobProvider):
    name = "linkedin"
    anzeigename = "LinkedIn"
    aktiv = False

    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        return []
