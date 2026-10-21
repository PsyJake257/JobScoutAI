import tempfile
import unittest
from pathlib import Path

from models import SearchRequest
from providers.exceptions import ProviderError
from providers.jooble_provider import JoobleProvider


class FakeJoobleClient:
    def __init__(self, antwort=None, fehler=None):
        self.antwort = antwort or {"jobs": []}
        self.fehler = fehler
        self.requests = []

    def post_json(self, url, headers, body):
        self.requests.append((url, headers, body))
        if self.fehler:
            raise self.fehler
        return self.antwort


class JoobleProviderTests(unittest.TestCase):
    def env_datei(self, tmp: str) -> Path:
        datei = Path(tmp) / ".env"
        datei.write_text("JOOBLE_API_KEY=test-key\n", encoding="utf-8")
        return datei

    def test_vollstaendige_antwort_wird_gemappt(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeJoobleClient({
                "jobs": [
                    {
                        "title": "Python Entwickler",
                        "company": "Jooble Test GmbH",
                        "location": "Berlin",
                        "snippet": "Spannende Aufgabe",
                        "link": "https://example.com/job",
                        "updated": "2026-07-23T12:55:35",
                    }
                ]
            })
            provider = JoobleProvider(client, self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Python", "Berlin", "30"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Python Entwickler")
        self.assertEqual(jobs[0].firma, "Jooble Test GmbH")
        self.assertEqual(jobs[0].ort, "Berlin")
        self.assertEqual(jobs[0].quelle, "Jooble")
        self.assertEqual(jobs[0].link, "https://example.com/job")
        self.assertEqual(jobs[0].kurzbeschreibung, "Spannende Aufgabe")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-07-23")

    def test_request_body_nutzt_jooble_radius(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeJoobleClient()
            provider = JoobleProvider(client, self.env_datei(tmp))

            provider.suchen(SearchRequest("Pflege", "Berlin", "30"))

        body = client.requests[0][2]
        self.assertEqual(body["keywords"], "Pflege")
        self.assertEqual(body["location"], "Berlin")
        self.assertEqual(body["radius"], "40")
        self.assertEqual(body["page"], "1")
        self.assertEqual(body["ResultOnPage"], 25)

    def test_mehrere_provider_seiten_werden_geladen(self):
        class MehrseitenClient(FakeJoobleClient):
            def post_json(self, url, headers, body):
                self.requests.append((url, headers, body))
                if body["page"] == "1":
                    return {"jobs": [{"title": f"Job {index}", "company": "Firma"} for index in range(25)]}
                if body["page"] == "2":
                    return {"jobs": [{"title": "Job 26", "company": "Firma"}]}
                return {"jobs": []}

        with tempfile.TemporaryDirectory() as tmp:
            client = MehrseitenClient()
            provider = JoobleProvider(client, self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Job", "Berlin", "30"))

        self.assertEqual(len(jobs), 26)
        self.assertEqual([request[2]["page"] for request in client.requests], ["1", "2"])

    def test_vollstaendige_beschreibung_wird_nicht_gekuerzt(self):
        langer_text = "Snippet " * 90
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeJoobleClient({
                "jobs": [{"title": "Job", "company": "Firma", "snippet": langer_text}]
            })
            provider = JoobleProvider(client, self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Job", "Berlin", "30"))

        self.assertEqual(jobs[0].kurzbeschreibung, langer_text.strip())
        self.assertGreater(len(jobs[0].kurzbeschreibung), 500)

    def test_fehlende_optionale_felder_bleiben_leer(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(FakeJoobleClient({"jobs": [{"title": "Job"}]}), self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("Job", "", "10"))

        self.assertEqual(jobs[0].firma, "")
        self.assertEqual(jobs[0].ort, "")
        self.assertEqual(jobs[0].link, "")
        self.assertEqual(jobs[0].kurzbeschreibung, "")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "")

    def test_ungueltige_url_wird_nicht_uebernommen(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(
                FakeJoobleClient({"jobs": [{"title": "Job", "company": "Firma", "link": "not-a-url"}]}),
                self.env_datei(tmp),
            )

            jobs = provider.suchen(SearchRequest("Job", "", "10"))

        self.assertEqual(jobs[0].link, "")

    def test_leere_jobliste(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(FakeJoobleClient({"jobs": []}), self.env_datei(tmp))

            jobs = provider.suchen(SearchRequest("x", "", "10"))

        self.assertEqual(jobs, [])

    def test_fehlerhafter_datensatz_zwischen_gueltigen_datensaetzen(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(
                FakeJoobleClient({
                    "jobs": [
                        {"title": "A", "company": "Firma A"},
                        "ungueltig",
                        {"title": "B", "company": "Firma B"},
                    ]
                }),
                self.env_datei(tmp),
            )

            jobs = provider.suchen(SearchRequest("x", "", "10"))

        self.assertEqual([job.titel for job in jobs], ["A", "B"])

    def test_fehlender_api_key_wird_provider_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(FakeJoobleClient(), Path(tmp) / ".env")

            with self.assertRaises(ProviderError) as context:
                provider.suchen(SearchRequest("x", "", "10"))

        self.assertIn("Jooble ist nicht konfiguriert", context.exception.benutzer_meldung)

    def test_deaktivierungsgrund_bei_fehlender_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(FakeJoobleClient(), Path(tmp) / ".env")

            self.assertIn(".env", provider.deaktivierungsgrund())

    def test_deaktivierungsgrund_bei_fehlendem_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / ".env"
            datei.write_text("ANDERER_WERT=1\n", encoding="utf-8")
            provider = JoobleProvider(FakeJoobleClient(), datei)

            self.assertIn("JOOBLE_API_KEY", provider.deaktivierungsgrund())

    def test_provider_error_aus_http_client_wird_weitergegeben(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = JoobleProvider(
                FakeJoobleClient(fehler=ProviderError("technisch", "Jooble nicht erreichbar")),
                self.env_datei(tmp),
            )

            with self.assertRaises(ProviderError) as context:
                provider.suchen(SearchRequest("x", "", "10"))

        self.assertEqual(context.exception.benutzer_meldung, "Jooble nicht erreichbar")


if __name__ == "__main__":
    unittest.main()
