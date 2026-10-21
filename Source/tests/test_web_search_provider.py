import tempfile
import unittest
from pathlib import Path

from analysis import AiAnalysisStep
from filters import JobFilter
from models import Job
from models import SearchRequest
from pipeline import SearchPipeline
from providers.base_provider import JobProvider
from providers.exceptions import ProviderError
from providers.registry import ProviderRegistry
from providers.serp_usage_tracker import SerpApiUsageTracker
from providers.web_search_provider import (
    SerpApiWebSearchBackend,
    WebSearchBackend,
    WebSearchProvider,
)


class FakeWebSearchBackend(WebSearchBackend):
    def __init__(self, ergebnisse=None, grund="", fehler=None):
        self.ergebnisse = ergebnisse or []
        self.grund = grund
        self.fehler = fehler
        self.anfragen = []

    def deaktivierungsgrund(self) -> str:
        return self.grund

    def suchen(self, suchanfrage: SearchRequest) -> list[dict]:
        self.anfragen.append(suchanfrage)
        if self.fehler:
            raise self.fehler
        return self.ergebnisse


class FakeSerpClient:
    def __init__(self, antworten):
        self.antworten = list(antworten)
        self.aufrufe = []

    def get_json(self, url, headers, params=None):
        self.aufrufe.append((url, headers, params))
        antwort = self.antworten.pop(0)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


class ExistingProvider(JobProvider):
    name = "bestehend"
    anzeigename = "Bestehend"
    aktiv = True

    def suchen(self, suchanfrage):
        return [Job("Assistenz", "Beispiel GmbH", "Berlin", self.anzeigename)]


class WebSearchProviderTests(unittest.TestCase):
    def test_provider_mappt_serp_ergebnisse_auf_jobmodell(self):
        backend = FakeWebSearchBackend([
            {
                "title": "Sachbearbeiter (m/w/d)",
                "url": "https://firma.example/karriere/sachbearbeiter",
                "description": "Organisation und Verwaltung",
                "source": "Beispiel GmbH",
                "date": "2026-07-28",
            },
            {"title": "Ohne Link", "url": "", "description": "wird ignoriert"},
        ])
        provider = WebSearchProvider(backend)

        jobs = provider.suchen(SearchRequest("Sachbearbeiter", "Bad Nauheim", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].quelle, "Websuche")
        self.assertEqual(jobs[0].firma, "Beispiel GmbH")
        self.assertEqual(jobs[0].ort, "Bad Nauheim")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-07-28")

    def test_serp_backend_nutzt_offizielle_api_und_kontostand(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            tracker = SerpApiUsageTracker(Path(tmp) / "usage.json")
            client = FakeSerpClient([
                {
                    "account_status": "Active",
                    "plan_name": "Free",
                    "searches_per_month": 250,
                    "plan_searches_left": 187,
                    "this_month_usage": 63,
                },
                {
                    "search_metadata": {"status": "Success"},
                    "jobs_results": [{
                        "title": "Teamassistenz (m/w/d)",
                        "company_name": "Example GmbH",
                        "location": "Bad Nauheim",
                        "description": "Beschreibung",
                        "via": "Example Jobs",
                        "detected_extensions": {"posted_at": "vor 2 Tagen"},
                        "apply_options": [{
                            "title": "Example Jobs",
                            "link": "https://example.org/job/teamassistenz-123",
                        }],
                        "job_id": "job-123",
                    }],
                },
                {
                    "account_status": "Active",
                    "plan_name": "Free",
                    "searches_per_month": 250,
                    "plan_searches_left": 187,
                    "this_month_usage": 63,
                },
            ])
            backend = SerpApiWebSearchBackend(client, env_datei, tracker)

            ergebnisse = backend.suchen(SearchRequest("Assistenz", "Bad Nauheim", "30"))
            status = backend.statusdetails()

        self.assertEqual(len(ergebnisse), 1)
        self.assertEqual(client.aufrufe[0][0], backend.ACCOUNT_URL)
        _url, headers, params = client.aufrufe[1]
        self.assertNotIn("X-Subscription-Token", headers)
        self.assertEqual(params["engine"], "google_jobs")
        self.assertEqual(params["google_domain"], "google.de")
        self.assertEqual(params["api_key"], "test-key")
        self.assertIn("Assistenz", params["q"])
        self.assertNotIn("Bad Nauheim", params["q"])
        self.assertEqual(params["lrad"], "30")
        self.assertEqual(ergebnisse[0]["url"], "https://example.org/job/teamassistenz-123")
        self.assertEqual(ergebnisse[0]["company"], "Example GmbH")
        self.assertEqual(status["verbleibend"], 187)

    def test_serp_backend_stoppt_beim_monatslimit(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            client = FakeSerpClient([{
                "account_status": "Active",
                "searches_per_month": 250,
                "plan_searches_left": 0,
                "this_month_usage": 250,
            }])
            backend = SerpApiWebSearchBackend(
                client,
                env_datei,
                SerpApiUsageTracker(Path(tmp) / "usage.json"),
            )

            with self.assertRaises(ProviderError) as context:
                backend.suchen(SearchRequest("Assistenz", "", "30"))

        self.assertIn("monatliche", context.exception.benutzer_meldung)
        self.assertEqual(len(client.aufrufe), 1)

    def test_fehlender_key_deaktiviert_websuche(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("", encoding="utf-8")
            backend = SerpApiWebSearchBackend(
                FakeSerpClient([]),
                env_datei,
                SerpApiUsageTracker(Path(tmp) / "usage.json"),
            )
            self.assertIn("SERP_SEARCH_API_KEY", backend.deaktivierungsgrund())

    def test_serp_ohne_kontingentfelder_zaehlt_lokal(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            tracker = SerpApiUsageTracker(Path(tmp) / "usage.json")
            backend = SerpApiWebSearchBackend(
                FakeSerpClient([
                    {"account_status": "Active"},
                    {
                        "search_metadata": {"status": "Success"},
                        "jobs_results": [{
                            "title": "Assistenz Job",
                            "company_name": "Example GmbH",
                            "location": "Berlin",
                            "description": "Assistenz gesucht",
                            "share_link": "https://www.google.de/search?htidocid=123",
                        }],
                    },
                ]),
                env_datei,
                tracker,
            )

            backend.suchen(SearchRequest("Assistenz", "", "30"))

            self.assertEqual(tracker.status()["verbleibend"], 249)
            self.assertEqual(tracker.status()["quelle"], "lokal")

    def test_serp_backend_nutzt_naechste_seite_und_google_detail_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            client = FakeSerpClient([
                {"account_status": "Active"},
                {
                    "search_metadata": {"status": "Success"},
                    "jobs_results": [{
                        "title": "Assistenz (m/w/d)",
                        "company_name": "Firma Eins",
                        "share_link": "https://www.google.de/search?htidocid=eins",
                    }],
                    "serpapi_pagination": {"next_page_token": "seite-zwei"},
                },
                {
                    "search_metadata": {"status": "Success"},
                    "jobs_results": [{
                        "title": "Office Assistenz (m/w/d)",
                        "company_name": "Firma Zwei",
                        "share_link": "https://www.google.de/search?htidocid=zwei",
                    }],
                },
            ])
            backend = SerpApiWebSearchBackend(
                client,
                env_datei,
                SerpApiUsageTracker(Path(tmp) / "usage.json"),
            )

            ergebnisse = backend.suchen(SearchRequest("Assistenz", "Berlin", "20 km"))

        self.assertEqual(len(ergebnisse), 2)
        self.assertNotIn("next_page_token", client.aufrufe[1][2])
        self.assertEqual(client.aufrufe[2][2]["next_page_token"], "seite-zwei")
        self.assertEqual(client.aufrufe[2][2]["lrad"], "20")

    def test_provider_verwirft_such_und_kategorieseiten(self):
        backend = FakeWebSearchBackend([
            {
                "title": "Assistenz Jobs in Hessen | Jetzt 3.000 offene Stellen finden",
                "url": "https://de.indeed.com/q-assistenz-l-hessen-jobs.html?vjk=abc123",
                "description": "Viele Assistenzstellen in Hessen",
                "source": "Indeed",
            },
            {
                "title": "Projektassistent (m/w/d), Bad Nauheim, Hessen",
                "url": "https://fox8.jobs/job/projektassistent-987",
                "description": "Konkrete Stellenanzeige",
                "source": "FOX8 Jobs",
            },
        ])
        provider = WebSearchProvider(backend)

        jobs = provider.suchen(SearchRequest("Projektassistent", "Bad Nauheim", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Projektassistent (m/w/d), Bad Nauheim, Hessen")

    def test_provider_mappt_strukturierte_firma_und_trefferort(self):
        backend = FakeWebSearchBackend([{
            "title": "Teamassistenz (m/w/d)",
            "url": "https://de.indeed.com/viewjob?jk=abc123",
            "description": "Konkrete Stelle",
            "company": "Muster GmbH",
            "location": "Friedberg (Hessen)",
            "source": "Indeed",
            "is_detail": True,
        }])
        provider = WebSearchProvider(backend)

        jobs = provider.suchen(SearchRequest("Teamassistenz", "Bad Nauheim", "30"))

        self.assertEqual(jobs[0].firma, "Muster GmbH")
        self.assertEqual(jobs[0].ort, "Friedberg (Hessen)")

    def test_provider_bleibt_nach_voruebergehendem_serp_fehler_aktiv(self):
        provider = WebSearchProvider(FakeWebSearchBackend(
            fehler=ProviderError("technisch", "Websuche nicht erreichbar"),
        ))
        with self.assertRaises(ProviderError):
            provider.suchen(SearchRequest("Assistenz", "", "30"))
        self.assertTrue(provider.aktiv)

    def test_nicht_erreichbarer_kontostand_blockiert_suche_nicht(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            tracker = SerpApiUsageTracker(Path(tmp) / "usage.json")
            client = FakeSerpClient([
                ProviderError("Kontostand nicht erreichbar", "Kontostand nicht erreichbar"),
                {
                    "search_metadata": {"status": "Success"},
                    "jobs_results": [{
                        "title": "Assistenz (m/w/d)",
                        "company_name": "Muster GmbH",
                        "apply_options": [{"link": "https://example.org/jobs/123"}],
                    }],
                },
            ])
            backend = SerpApiWebSearchBackend(client, env_datei, tracker)

            ergebnisse = backend.suchen(SearchRequest("Assistenz", "Berlin", "30"))
            verbraucht = tracker.status()["verbraucht"]

        self.assertEqual(len(ergebnisse), 1)
        self.assertEqual(verbraucht, 1)

    def test_statusaktualisierung_erholt_sich_nach_transientem_fehler(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            client = FakeSerpClient([
                ProviderError("Timeout", "SerpApi-Kontostatus ist nicht erreichbar."),
                {
                    "account_status": "Active",
                    "searches_per_month": 250,
                    "plan_searches_left": 200,
                    "this_month_usage": 50,
                },
            ])
            backend = SerpApiWebSearchBackend(
                client,
                env_datei,
                SerpApiUsageTracker(Path(tmp) / "usage.json"),
            )

            fehlerstatus = backend.statusdetails(aktualisieren=True)
            erholter_status = backend.statusdetails(aktualisieren=True)
            deaktivierungsgrund = backend.deaktivierungsgrund()

        self.assertIn("statusfehler", fehlerstatus)
        self.assertNotIn("statusfehler", erholter_status)
        self.assertEqual(erholter_status["provider_status"], "Active")
        self.assertEqual(deaktivierungsgrund, "")

    def test_serp_meldung_ohne_ergebnisse_ist_keine_providerstoerung(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_datei = Path(tmp) / ".env"
            env_datei.write_text("SERP_SEARCH_API_KEY=test-key\n", encoding="utf-8")
            client = FakeSerpClient([
                {"account_status": "Active"},
                {"error": "Google hasn't returned any results for this query."},
            ])
            backend = SerpApiWebSearchBackend(
                client,
                env_datei,
                SerpApiUsageTracker(Path(tmp) / "usage.json"),
            )

            ergebnisse = backend.suchen(SearchRequest("Sehr seltene Rolle", "Berlin", "30"))
            deaktivierungsgrund = backend.deaktivierungsgrund()

        self.assertEqual(ergebnisse, [])
        self.assertEqual(deaktivierungsgrund, "")

    def test_serp_fehler_blockiert_anderen_provider_nicht(self):
        web = WebSearchProvider(FakeWebSearchBackend(
            fehler=ProviderError("technisch", "Websuche nicht erreichbar"),
        ))
        pipeline = SearchPipeline(
            ProviderRegistry([ExistingProvider(), web]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("Assistenz", "Berlin", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertIn("Websuche nicht erreichbar", pipeline.diagnose_meldung())

    def test_lokaler_zaehler_setzt_sich_im_neuen_monat_zurueck(self):
        class Uhr:
            monat = "2026-07"

            @classmethod
            def now(cls):
                from datetime import datetime
                return datetime.strptime(cls.monat, "%Y-%m")

        with tempfile.TemporaryDirectory() as tmp:
            tracker = SerpApiUsageTracker(Path(tmp) / "usage.json", now=Uhr.now)
            tracker.verbrauch_erhoehen(12)
            self.assertEqual(tracker.status()["verbleibend"], 238)
            Uhr.monat = "2026-08"
            self.assertEqual(tracker.status()["verbleibend"], 250)


if __name__ == "__main__":
    unittest.main()
