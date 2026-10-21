import tempfile
import unittest
from pathlib import Path

from models import SearchRequest
from providers.adzuna_provider import AdzunaProvider
from providers.exceptions import ProviderError


class FakeAdzunaClient:
    def __init__(self, antwort=None, fehler=None):
        self.antwort = antwort or {"results": []}
        self.fehler = fehler
        self.requests = []

    def get_json(self, url, headers, params=None):
        self.requests.append((url, headers, params or {}))
        if self.fehler:
            raise self.fehler
        return self.antwort


class AdzunaProviderTests(unittest.TestCase):
    def env_datei(self, tmp: str, app_id="app-id", api_key="api-key") -> Path:
        datei = Path(tmp) / ".env"
        datei.write_text(f"ADZUNA_APP_ID={app_id}\nADZUNA_API_KEY={api_key}\n", encoding="utf-8")
        return datei

    def test_provider_ist_nur_mit_app_id_und_api_key_aktiv(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = AdzunaProvider(FakeAdzunaClient(), self.env_datei(tmp))

            self.assertEqual(provider.deaktivierungsgrund(), "")

    def test_fehlende_app_id_deaktiviert_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / ".env"
            datei.write_text("ADZUNA_API_KEY=secret\n", encoding="utf-8")
            provider = AdzunaProvider(FakeAdzunaClient(), datei)

            self.assertIn("ADZUNA_APP_ID", provider.deaktivierungsgrund())

    def test_fehlender_api_key_deaktiviert_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / ".env"
            datei.write_text("ADZUNA_APP_ID=app\n", encoding="utf-8")
            provider = AdzunaProvider(FakeAdzunaClient(), datei)

            self.assertIn("ADZUNA_API_KEY", provider.deaktivierungsgrund())

    def test_secret_maskierung_in_konfigurationsfehler(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / ".env"
            datei.write_text("ADZUNA_APP_ID=super-geheime-app\n", encoding="utf-8")
            provider = AdzunaProvider(FakeAdzunaClient(), datei)

            grund = provider.deaktivierungsgrund()

        self.assertNotIn("super-geheime-app", grund)

    def test_request_nutzt_deutsche_suche_und_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeAdzunaClient()
            provider = AdzunaProvider(client, self.env_datei(tmp))

            provider.suchen(SearchRequest("Pflege", "Berlin", "30"))

        url, headers, params = client.requests[0]
        self.assertIn("/jobs/de/search/1", url)
        self.assertEqual(params["what"], "Pflege")
        self.assertEqual(params["where"], "Berlin")
        self.assertEqual(params["distance"], "30")
        self.assertEqual(params["results_per_page"], "25")
        self.assertEqual(params["app_id"], "app-id")
        self.assertEqual(params["app_key"], "api-key")

    def test_mehrere_provider_seiten_werden_geladen(self):
        class MehrseitenClient(FakeAdzunaClient):
            def get_json(self, url, headers, params=None):
                self.requests.append((url, headers, params or {}))
                if "/search/1" in url:
                    return {"results": [{"title": f"Job {index}", "company": {"display_name": "Firma"}} for index in range(25)]}
                if "/search/2" in url:
                    return {"results": [{"title": "Job 26", "company": {"display_name": "Firma"}}]}
                return {"results": []}

        with tempfile.TemporaryDirectory() as tmp:
            client = MehrseitenClient()
            provider = AdzunaProvider(client, self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Job", "Berlin", "30"))

        self.assertEqual(len(jobs), 26)
        self.assertEqual([request[0].rsplit("/", 1)[-1] for request in client.requests], ["1", "2"])

    def test_vollstaendige_antwort_wird_gemappt_und_html_bereinigt(self):
        langer_text = "<p>Start &amp; Mitte</p><div>" + ("Beschreibung " * 70) + "</div>"
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeAdzunaClient({
                "results": [{
                    "title": "Python Entwickler",
                    "company": {"display_name": "Adzuna Test GmbH"},
                    "location": {"area": ["Deutschland", "Hessen", "Bad Nauheim"], "display_name": "Bad Nauheim"},
                    "description": langer_text,
                    "created": "2026-07-24T10:00:00Z",
                    "redirect_url": "https://example.com/job?utm_source=x",
                    "salary_min": 42000,
                    "salary_max": 55000.0,
                    "category": {"label": "IT Jobs", "tag": "it-jobs"},
                }]
            })
            provider = AdzunaProvider(client, self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Python", "Bad Nauheim", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Python Entwickler")
        self.assertEqual(jobs[0].firma, "Adzuna Test GmbH")
        self.assertEqual(jobs[0].ort, "Hessen, Bad Nauheim")
        self.assertEqual(jobs[0].quelle, "Adzuna")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-07-24")
        self.assertEqual(jobs[0].gehalt_min, "42000")
        self.assertEqual(jobs[0].gehalt_max, "55000")
        self.assertEqual(jobs[0].kategorie, "IT Jobs")
        self.assertIn("Start & Mitte", jobs[0].kurzbeschreibung)
        self.assertNotIn("<p>", jobs[0].kurzbeschreibung)
        self.assertGreater(len(jobs[0].kurzbeschreibung), 500)

    def test_fehlende_optionale_felder_bleiben_leer(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = AdzunaProvider(FakeAdzunaClient({"results": [{"title": "Job"}]}), self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Job", "", "10"))

        self.assertEqual(jobs[0].firma, "")
        self.assertEqual(jobs[0].ort, "")
        self.assertEqual(jobs[0].link, "")
        self.assertEqual(jobs[0].gehalt_min, "")
        self.assertEqual(jobs[0].kategorie, "")

    def test_unerwartete_jobliste_wird_provider_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = AdzunaProvider(FakeAdzunaClient({"results": "kaputt"}), self.env_datei(tmp))

            with self.assertRaises(ProviderError):
                provider.suchen(SearchRequest("x", "", "10"))

    def test_provider_error_aus_http_client_wird_weitergegeben(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = AdzunaProvider(
                FakeAdzunaClient(fehler=ProviderError("timeout", "Adzuna nicht erreichbar")),
                self.env_datei(tmp),
            )

            with self.assertRaises(ProviderError) as context:
                provider.suchen(SearchRequest("x", "", "10"))

        self.assertEqual(context.exception.benutzer_meldung, "Adzuna nicht erreichbar")


if __name__ == "__main__":
    unittest.main()
