from abc import ABC, abstractmethod

from models import Job, SearchRequest


class JobProvider(ABC):
    name: str
    anzeigename: str
    aktiv: bool = False

    def deaktivierungsgrund(self) -> str:
        return ""

    def statusdetails(self, aktualisieren: bool = False) -> dict[str, object]:
        return {}

    @abstractmethod
    def suchen(self, suchanfrage: SearchRequest) -> list[Job]:
        raise NotImplementedError
