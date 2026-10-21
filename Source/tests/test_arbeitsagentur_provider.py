import unittest

from models import SearchRequest
from providers.arbeitsagentur_provider import ArbeitsagenturProvider


class FakeArbeitsagenturClient:
    def __init__(self, suchantwort, detailantworten=None):
        self.suchantwort = suchantwort
        self.detailantworten = detailantworten or {}
        self.requests = []

    def get_json(self, url, headers, params=None):
        if "jobdetails" in url:
            return self.detailantworten.get(url, {})
        self.requests.append((url, headers, params or {}))
        return self.suchantwort


class ArbeitsagenturProviderMappingTests(unittest.TestCase):
    def provider(self, stellenangebote, detailantwort=None):
        return ArbeitsagenturProvider(
            FakeArbeitsagenturClient(
                {"ergebnisliste": stellenangebote},
                detailantworten=detailantwort or {},
            )
        )

    def test_vollstaendige_antwort_wird_gemappt(self):
        provider = self.provider([
            {
                "beruf": "Pflegefachkraft",
                "arbeitgeber": "Klinik Test",
                "arbeitsort": {"plz": "10115", "ort": "Berlin"},
                "entfernung": 12,
                "beschreibung": "<p>Gute Stelle</p>",
                "aktuelleVeroeffentlichungsdatum": "2026-07-23T10:00:00",
                "externeUrl": "https://example.com/job",
            }
        ])

        jobs = provider.suchen(SearchRequest("Pflege", "Berlin", "20"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Pflegefachkraft")
        self.assertEqual(jobs[0].firma, "Klinik Test")
        self.assertEqual(jobs[0].ort, "10115 Berlin")
        self.assertEqual(jobs[0].entfernung, "12 km")
        self.assertEqual(jobs[0].kurzbeschreibung, "Gute Stelle")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-07-23")
        self.assertEqual(jobs[0].link, "https://example.com/job")

    def test_v6_suchroute_und_v6_felder_werden_gemappt(self):
        provider = self.provider([{
            "stellenangebotsTitel": "Teamassistenz (m/w/d)",
            "firma": "Muster GmbH",
            "stellenlokationen": [{
                "adresse": {"plz": "61231", "ort": "Bad Nauheim", "region": "HESSEN"}
            }],
            "datumErsteVeroeffentlichung": "2026-08-24",
            "referenznummer": "10000-12345-S",
        }])

        jobs = provider.suchen(SearchRequest("Teamassistenz", "Bad Nauheim", "30"))

        self.assertIn("/pc/v6/jobs", provider.http_client.requests[0][0])
        self.assertEqual(jobs[0].titel, "Teamassistenz (m/w/d)")
        self.assertEqual(jobs[0].firma, "Muster GmbH")
        self.assertEqual(jobs[0].ort, "61231 Bad Nauheim HESSEN")
        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-08-24")

    def test_fehlende_beschreibung_bleibt_leer(self):
        jobs = self.provider([{"beruf": "Assistenz", "arbeitgeber": "Firma"}]).suchen(
            SearchRequest("Assistenz", "Berlin", "20")
        )

        self.assertEqual(jobs[0].kurzbeschreibung, "")

    def test_vollstaendige_beschreibung_wird_nicht_gekuerzt(self):
        langer_text = "Beschreibung " * 80
        jobs = self.provider([{
            "beruf": "Assistenz",
            "arbeitgeber": "Firma",
            "beschreibung": f"<p>{langer_text}</p>",
        }]).suchen(SearchRequest("Assistenz", "Berlin", "20"))

        self.assertEqual(jobs[0].kurzbeschreibung, langer_text.strip())
        self.assertGreater(len(jobs[0].kurzbeschreibung), 500)

    def test_fehlende_entfernung_bleibt_leer(self):
        jobs = self.provider([{"beruf": "Assistenz", "arbeitgeber": "Firma"}]).suchen(
            SearchRequest("Assistenz", "Berlin", "20")
        )

        self.assertEqual(jobs[0].entfernung, "")

    def test_fehlendes_veroeffentlichungsdatum_bleibt_leer(self):
        jobs = self.provider([{"beruf": "Assistenz", "arbeitgeber": "Firma"}]).suchen(
            SearchRequest("Assistenz", "Berlin", "20")
        )

        self.assertEqual(jobs[0].veroeffentlichungsdatum, "")

    def test_fehlende_firma_oder_ort_bricht_nicht_ab(self):
        jobs = self.provider([{"beruf": "Assistenz"}]).suchen(SearchRequest("Assistenz", "", "20"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].firma, "")
        self.assertEqual(jobs[0].ort, "")

    def test_leere_ergebnisliste(self):
        jobs = self.provider([]).suchen(SearchRequest("xyz", "Berlin", "20"))

        self.assertEqual(jobs, [])

    def test_mehrere_provider_seiten_werden_geladen(self):
        class MehrseitenClient(FakeArbeitsagenturClient):
            def get_json(self, url, headers, params=None):
                if "jobdetails" in url:
                    return {}
                self.requests.append((url, headers, params or {}))
                seite = params.get("page")
                if seite == "1":
                    return {"stellenangebote": [{"beruf": f"Job {index}", "arbeitgeber": "Firma"} for index in range(25)]}
                if seite == "2":
                    return {"stellenangebote": [{"beruf": "Job 26", "arbeitgeber": "Firma"}]}
                return {"stellenangebote": []}

        client = MehrseitenClient({})
        provider = ArbeitsagenturProvider(client)

        jobs = provider.suchen(SearchRequest("Job", "Berlin", "20"))

        self.assertEqual(len(jobs), 26)
        self.assertEqual([request[2]["page"] for request in client.requests], ["1", "2"])

    def test_fehlerhafter_datensatz_zwischen_gueltigen_datensaetzen(self):
        jobs = self.provider([
            {"beruf": "Erste Stelle", "arbeitgeber": "A"},
            "ungueltig",
            {"beruf": "Zweite Stelle", "arbeitgeber": "B"},
        ]).suchen(SearchRequest("Stelle", "Berlin", "20"))

        self.assertEqual([job.titel for job in jobs], ["Erste Stelle", "Zweite Stelle"])

    def test_unerwartete_feldtypen_werden_defensiv_behandelt(self):
        jobs = self.provider([
            {
                "beruf": 123,
                "arbeitgeber": {"name": "Firma Objekt"},
                "arbeitsort": [{"ort": "Hamburg"}],
                "entfernung": 7.5,
                "beschreibung": ["Listenbeschreibung"],
            }
        ]).suchen(SearchRequest("123", "Hamburg", "20"))

        self.assertEqual(jobs[0].titel, "123")
        self.assertEqual(jobs[0].firma, "Firma Objekt")
        self.assertEqual(jobs[0].ort, "Hamburg")
        self.assertEqual(jobs[0].entfernung, "7.5 km")
        self.assertEqual(jobs[0].kurzbeschreibung, "Listenbeschreibung")

    def test_datumsmapping(self):
        jobs = self.provider([
            {"beruf": "Job", "arbeitgeber": "Firma", "veroeffentlichtAm": "2026-08-01"}
        ]).suchen(SearchRequest("Job", "Berlin", "20"))

        self.assertEqual(jobs[0].veroeffentlichungsdatum, "2026-08-01")

    def test_url_mapping_fallback_bei_ungueltiger_url(self):
        jobs = self.provider([
            {"beruf": "Job", "arbeitgeber": "Firma", "refnr": "10000-12345-S", "externeUrl": "not-a-url"}
        ]).suchen(SearchRequest("Job", "Berlin", "20"))

        self.assertTrue(jobs[0].link.startswith("https://www.arbeitsagentur.de/jobsuche/jobdetail/"))


if __name__ == "__main__":
    unittest.main()
