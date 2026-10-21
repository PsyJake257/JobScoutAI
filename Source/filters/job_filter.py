from deduplication import DeduplizierungsStatistik, JobDeduplizierer
from models import Job, SearchRequest


class JobFilter:
    def __init__(self):
        self.letzte_dubletten = 0
        self.letzte_deduplizierung = DeduplizierungsStatistik()

    def anwenden(self, jobs: list[Job], suchanfrage: SearchRequest) -> list[Job]:
        return self.anwenden_gruppiert([("alle", jobs)], suchanfrage)

    def anwenden_gruppiert(self, provider_jobs: list[tuple[str, list[Job]]], suchanfrage: SearchRequest) -> list[Job]:
        eindeutige_gruppen = []
        deduplizierer = JobDeduplizierer()
        self.letzte_dubletten = 0

        for provider_name, jobs in provider_jobs:
            eindeutige_jobs = []
            eindeutige_gruppen.append((provider_name, eindeutige_jobs))
            for job in jobs:
                _job, art = deduplizierer.hinzufuegen(job)
                if art:
                    continue
                eindeutige_jobs.append(job)

        self.letzte_deduplizierung = deduplizierer.statistik
        self.letzte_dubletten = deduplizierer.statistik.gesamt
        return self._fair_mischen(eindeutige_gruppen)

    def _fair_mischen(self, provider_jobs: list[tuple[str, list[Job]]]) -> list[Job]:
        gemischt = []
        position = 0

        while True:
            hinzugefuegt = False
            for provider_name, jobs in provider_jobs:
                if position < len(jobs):
                    gemischt.append(jobs[position])
                    hinzugefuegt = True

            if not hinzugefuegt:
                break

            position += 1

        return gemischt
