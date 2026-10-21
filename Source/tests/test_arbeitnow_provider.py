import unittest

from analysis import AiAnalysisStep
from filters import JobFilter
from models import Job, SearchRequest
from pipeline import SearchPipeline
from providers.arbeitnow_provider import ArbeitnowProvider
from providers.base_provider import JobProvider
from providers.registry import ProviderRegistry


class FakeArbeitnowClient:
    def __init__(self, antworten):
        self.antworten = list(antworten)
        self.aufrufe = []

    def get_json(self, url, headers, params=None):
        self.aufrufe.append((url, headers, params))
        return self.antworten.pop(0)


class ExistingProvider(JobProvider):
    name = "bestehend"
    anzeigename = "Bestehend"
    aktiv = True

    def suchen(self, suchanfrage):
        return [
            Job(
                "Office Manager (m/w/d)",
                "Beispiel GmbH",
                "Berlin",
                self.anzeigename,
                link="https://example.org/jobs/office-manager",
            )
        ]


class ArbeitnowProviderTests(unittest.TestCase):
    def _antwort(self, next_link=None):
        return {
            "data": [
                {
                    "slug": "office-manager",
                    "company_name": "Beispiel GmbH",
                    "title": "Office Manager (m/w/d)",
                    "description": "<p>Organisation und administrative Aufgaben</p>",
                    "remote": False,
                    "url": "https://example.org/jobs/office-manager",
                    "tags": ["Administration"],
                    "job_types": ["Full-time"],
                    "location": "Berlin, Germany",
                    "created_at": 1785283200,
                },
                {
                    "company_name": "Andere GmbH",
                    "title": "Software Engineer",
                    "description": "<p>Python</p>",
                    "remote": False,
                    "url": "https://example.org/jobs/software",
                    "location": "Munich, Germany",
                    "created_at": 1785283200,
                },
            ],
            "links": {"next": next_link},
        }

    def test_mappt_und_filtert_deutsche_stellen(self):
        client = FakeArbeitnowClient([self._antwort()])
        provider = ArbeitnowProvider(client)

        jobs = provider.suchen(SearchRequest("Office Manager", "Berlin", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].quelle, "Arbeitnow")
        self.assertEqual(jobs[0].firma, "Beispiel GmbH")
        self.assertIn("Organisation", jobs[0].kurzbeschreibung)
        self.assertIn("Full-time", jobs[0].kategorie)
        self.assertEqual(client.aufrufe[0][2]["page"], "1")

    def test_remote_stelle_bleibt_trotz_abweichendem_ort_relevant(self):
        antwort = self._antwort()
        antwort["data"][0]["remote"] = True
        antwort["data"][0]["location"] = "Germany"
        provider = ArbeitnowProvider(FakeArbeitnowClient([antwort]))

        jobs = provider.suchen(SearchRequest("Office", "Bad Nauheim", "30"))

        self.assertEqual(len(jobs), 1)

    def test_deduplizierung_mit_bestehendem_provider(self):
        arbeitnow = ArbeitnowProvider(FakeArbeitnowClient([self._antwort()]))
        pipeline = SearchPipeline(
            ProviderRegistry([ExistingProvider(), arbeitnow]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("Office Manager", "Berlin", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(pipeline.letzte_diagnose["dubletten_entfernt"], 1)


if __name__ == "__main__":
    unittest.main()
