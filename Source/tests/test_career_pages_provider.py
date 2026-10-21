import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from analysis import AiAnalysisStep
from filters import JobFilter
from models import Job, SearchRequest
from pipeline import SearchPipeline
from providers.base_provider import JobProvider
from providers.career_pages_provider import CareerPagesProvider
from providers.ethical_http_client import EthicalHttpClient, RobotsDeniedError
from providers.registry import ProviderRegistry


class FakeCareerClient:
    def __init__(self, seiten=None, gesperrt=None):
        self.seiten = seiten or {}
        self.gesperrt = set(gesperrt or [])
        self.aufrufe = []

    def get_public_html(self, url):
        self.aufrufe.append(url)
        if url in self.gesperrt:
            raise RobotsDeniedError("gesperrt")
        return self.seiten.get(url, "")


class ExistingProvider(JobProvider):
    name = "bestehend"
    anzeigename = "Bestehend"
    aktiv = True

    def suchen(self, suchanfrage):
        return [
            Job(
                "Assistenz",
                "Beispiel GmbH",
                "Bad Nauheim",
                self.anzeigename,
                link="https://firma.example/jobs/assistenz",
            )
        ]


class CareerPagesProviderTests(unittest.TestCase):
    START_URL = "https://firma.example/karriere"
    JOB_URL = "https://firma.example/jobs/assistenz"

    def _job_html(self):
        return """
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Assistenz Verwaltung (m/w/d)",
          "description": "<p>Organisation, Termine und Verwaltung.</p>",
          "datePosted": "2026-07-28",
          "employmentType": "PART_TIME",
          "hiringOrganization": {"@type": "Organization", "name": "Beispiel GmbH"},
          "jobLocation": {
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "postalCode": "61231",
              "addressLocality": "Bad Nauheim",
              "addressRegion": "Hessen"
            }
          },
          "baseSalary": {
            "@type": "MonetaryAmount",
            "value": {"@type": "QuantitativeValue", "minValue": 32000, "maxValue": 38000}
          },
          "url": "https://firma.example/jobs/assistenz"
        }
        </script></head><body></body></html>
        """

    def test_provider_folgt_relevanten_links_und_mappt_json_ld(self):
        client = FakeCareerClient({
            self.START_URL: '<a href="/jobs/assistenz">Offene Stelle Assistenz</a>',
            self.JOB_URL: self._job_html(),
        })
        provider = CareerPagesProvider(client, start_urls=[self.START_URL])

        jobs = provider.suchen(SearchRequest("Assistenz", "Bad Nauheim", "30"))

        self.assertEqual(client.aufrufe, [self.START_URL, self.JOB_URL])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].quelle, "Karriereseite")
        self.assertEqual(jobs[0].firma, "Beispiel GmbH")
        self.assertEqual(jobs[0].ort, "61231 Bad Nauheim Hessen")
        self.assertEqual(jobs[0].gehalt_min, "32000")
        self.assertEqual(jobs[0].gehalt_max, "38000")
        self.assertIn("Organisation", jobs[0].kurzbeschreibung)

    def test_unpassende_stelle_wird_nicht_uebernommen(self):
        provider = CareerPagesProvider(
            FakeCareerClient({self.JOB_URL: self._job_html()}),
            start_urls=[self.JOB_URL],
        )
        self.assertEqual(provider.suchen(SearchRequest("Softwareentwickler", "", "30")), [])

    def test_html_fallback_erkennt_greenhouse_titel_und_firma(self):
        html = """
        <html><head>
          <title>Job Application for Administrative Assistant at Asset Living</title>
          <meta name="description" content="Administrative office support">
        </head><body></body></html>
        """
        url = "https://job-boards.greenhouse.io/assetliving/jobs/6103182004"
        provider = CareerPagesProvider(FakeCareerClient({url: html}), start_urls=[url])

        jobs = provider.suchen(SearchRequest("Administrative Assistant", "", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Administrative Assistant")
        self.assertEqual(jobs[0].firma, "Asset Living")

    def test_robots_sperre_wird_uebersprungen(self):
        provider = CareerPagesProvider(
            FakeCareerClient(gesperrt=[self.START_URL]),
            start_urls=[self.START_URL],
        )
        self.assertEqual(provider.suchen(SearchRequest("Assistenz", "", "30")), [])

    def test_fehlende_konfiguration_deaktiviert_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = CareerPagesProvider(
                FakeCareerClient(),
                env_datei=Path(tmp) / ".env",
            )
            self.assertIn("CAREER_SITE_URLS", provider.deaktivierungsgrund())

    def test_ethical_client_respektiert_robots_disallow(self):
        client = EthicalHttpClient(request_delay_seconds=0)
        client._fetch = Mock(return_value=(200, "User-agent: *\nDisallow: /jobs", "text/plain"))
        with self.assertRaises(RobotsDeniedError):
            client.get_public_html("https://firma.example/jobs/assistenz")
        self.assertEqual(client._fetch.call_count, 1)

    def test_ethical_client_laesst_erlaubte_seite_zu(self):
        client = EthicalHttpClient(request_delay_seconds=0)
        client._fetch = Mock(side_effect=[
            (200, "User-agent: *\nDisallow: /intern", "text/plain"),
            (200, "<html>ok</html>", "text/html; charset=utf-8"),
        ])
        html = client.get_public_html("https://firma.example/jobs/assistenz")
        self.assertEqual(html, "<html>ok</html>")
        self.assertEqual(client._fetch.call_count, 2)

    def test_deduplizierung_mit_bestehendem_provider(self):
        career = CareerPagesProvider(
            FakeCareerClient({self.JOB_URL: self._job_html()}),
            start_urls=[self.JOB_URL],
        )
        pipeline = SearchPipeline(
            ProviderRegistry([ExistingProvider(), career]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("Assistenz", "Bad Nauheim", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(pipeline.letzte_diagnose["dubletten_entfernt"], 1)
        self.assertEqual(jobs[0].quelle, "Karriereseite")


if __name__ == "__main__":
    unittest.main()
