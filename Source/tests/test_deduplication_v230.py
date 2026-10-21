import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis import AiAnalysisStep
from app import JobScoutAI
from deduplication import jobs_deduplizieren
from filters import JobFilter
from models import Job, SearchRequest, normalisierte_url
from pipeline import SearchPipeline
from providers.base_provider import JobProvider
from providers.exceptions import ProviderError
from providers.registry import ProviderRegistry
from repositories import JsonJobRepository


class StaticProvider(JobProvider):
    name = "static"
    anzeigename = "Static"
    aktiv = True

    def __init__(self, jobs):
        self.jobs = jobs
        self.aufrufe = 0

    def suchen(self, suchanfrage):
        self.aufrufe += 1
        return [Job.from_dict(job.to_dict()) for job in self.jobs]


class BlockingProvider(JobProvider):
    anzeigename = "Blockiert"
    aktiv = True

    def __init__(self, status_code):
        self.name = f"blockiert_{status_code}"
        self.status_code = status_code
        self.aufrufe = 0

    def suchen(self, suchanfrage):
        self.aufrufe += 1
        raise ProviderError(
            "gesperrt",
            "Quelle temporaer gesperrt.",
            status_code=self.status_code,
            retry_after_seconds=0,
        )


class TermProvider(JobProvider):
    name = "term"
    anzeigename = "Term"
    aktiv = True

    def __init__(self):
        self.aufrufe = 0

    def suchen(self, suchanfrage):
        self.aufrufe += 1
        return [
            Job(
                titel=f"{suchanfrage.suchbegriff} Stelle",
                firma="Firma",
                ort="Ort",
                quelle=self.anzeigename,
                link=f"https://example.test/{self.aufrufe}",
            )
        ]


class DuplicateAiClient:
    model = "qwen3:8b"

    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {"pairs": [{"pair_id": 0, "same_job": True, "confidence": 96, "reason": "Gleiche Stelle"}]}


class DeduplicationV230Tests(unittest.TestCase):
    def test_jooble_job_id_ignoriert_suchparameter_und_away_desc_variante(self):
        erster = "https://de.jooble.org/away/-123?p=1&ckey=Assistenz&pos=2"
        zweiter = "https://de.jooble.org/desc/-123?p=9&ckey=Buero&pos=17"

        self.assertEqual(normalisierte_url(erster), normalisierte_url(zweiter))
        jobs, statistik = jobs_deduplizieren([
            Job("Assistenz", "Firma A", "Ort A", "Jooble", link=erster),
            Job("Andere Schreibweise", "Firma B", "Ort B", "Jooble", link=zweiter),
        ])

        self.assertEqual(len(jobs), 1)
        self.assertEqual(statistik.url, 1)

    def test_quellenuebergreifende_dublette_behaelt_daten_und_herkunft(self):
        jobs, statistik = jobs_deduplizieren([
            Job(
                "Teamassistenz (m/w/d)",
                "Beispiel GmbH",
                "Bad Nauheim",
                "Jooble",
                link="https://jooble.example/1",
                favorit=True,
                notizen="Bereits angesehen",
                ki_suchbegriffe=["Assistenz"],
            ),
            Job(
                "Teamassistenz",
                "Beispiel GmbH",
                "Bad Nauheim",
                "Karriereseite",
                link="https://beispiel.de/jobs/123",
                kurzbeschreibung="Vollstaendige Stellenbeschreibung " * 20,
                ki_suchbegriffe=["Buerokraft"],
            ),
        ])

        self.assertEqual(len(jobs), 1)
        self.assertEqual(statistik.inhalt, 1)
        self.assertEqual(jobs[0].quelle, "Karriereseite")
        self.assertEqual(jobs[0].quellen, ["Jooble", "Karriereseite"])
        self.assertEqual(jobs[0].ki_suchbegriffe, ["Assistenz", "Buerokraft"])
        self.assertTrue(jobs[0].favorit)
        self.assertEqual(jobs[0].notizen, "Bereits angesehen")
        self.assertGreater(len(jobs[0].kurzbeschreibung), 200)

    def test_unterschiedliche_stellen_bei_gleicher_firma_bleiben_getrennt(self):
        jobs, _statistik = jobs_deduplizieren([
            Job("Sachbearbeiter Personal", "Beispiel GmbH", "Frankfurt", "A"),
            Job("Sachbearbeiter Einkauf", "Beispiel GmbH", "Frankfurt", "B"),
        ])

        self.assertEqual(len(jobs), 2)

    def test_llm_prueft_nur_mehrdeutigen_kandidaten_und_kann_bestaetigen(self):
        beschreibung = "Seminare organisieren, Teilnehmende betreuen und Termine koordinieren. " * 8
        provider = StaticProvider([
            Job("Sachbearbeiter Seminarorganisation", "Bildung Beispiel GmbH", "Frankfurt", "A", kurzbeschreibung=beschreibung),
            Job("Mitarbeiter Seminarabwicklung", "Bildung Beispiel GmbH", "Frankfurt", "B", kurzbeschreibung=beschreibung),
        ])
        client = DuplicateAiClient()
        pipeline = SearchPipeline(
            ProviderRegistry([provider]),
            JobFilter(),
            AiAnalysisStep(client=client, enabled=True),
        )

        jobs = pipeline.ausfuehren(SearchRequest("Seminar", "Frankfurt", "20"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(pipeline.letzte_diagnose["dubletten_ki"], 1)
        self.assertEqual(len(client.prompts), 1)

    def test_403_provider_wird_im_mehrbegriff_lauf_nur_einmal_abgefragt(self):
        blockiert = BlockingProvider(403)
        term = TermProvider()
        pipeline = SearchPipeline(
            ProviderRegistry([blockiert, term]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren_mehrere([
            SearchRequest("A", "Ort", "20"),
            SearchRequest("B", "Ort", "20"),
            SearchRequest("C", "Ort", "20"),
        ])

        self.assertEqual(blockiert.aufrufe, 1)
        self.assertEqual(term.aufrufe, 3)
        self.assertEqual(len(jobs), 3)
        self.assertIn("restlichen Suchlauf pausiert", pipeline.diagnose_meldung())

    def test_429_wird_einmal_wiederholt_und_dann_im_batch_pausiert(self):
        blockiert = BlockingProvider(429)
        pipeline = SearchPipeline(
            ProviderRegistry([blockiert]),
            JobFilter(),
            AiAnalysisStep(),
        )

        with patch("pipeline.search_pipeline.time.sleep"):
            pipeline.ausfuehren_mehrere([
                SearchRequest("A", "Ort", "20"),
                SearchRequest("B", "Ort", "20"),
            ])

        self.assertEqual(blockiert.aufrufe, 2)

    def test_bestandsbereinigung_legt_sicherung_an_und_bewahrt_favorit(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            daten = [
                Job("Teamassistenz (m/w/d)", "Firma GmbH", "Ort", "A", link="https://a.test/1", favorit=True).to_dict(),
                Job("Teamassistenz", "Firma", "Ort", "B", link="https://b.test/2", notizen="Wichtig").to_dict(),
            ]
            datei.write_text(json.dumps(daten), encoding="utf-8")
            repository = JsonJobRepository(datei)

            ergebnis = repository.bestand_bereinigen_mit_sicherung()
            jobs = repository.laden()

            self.assertEqual(ergebnis["entfernt"], 1)
            self.assertEqual(len(jobs), 1)
            self.assertTrue(jobs[0].favorit)
            self.assertEqual(jobs[0].notizen, "Wichtig")
            self.assertTrue(Path(ergebnis["sicherung"]).exists())
            self.assertTrue(datei.with_name("jobs.dedupe-v2.json").exists())

    def test_zerstoerte_ki_widgets_werden_nicht_mehr_konfiguriert(self):
        class ZerstoertesWidget:
            def winfo_exists(self):
                return 0

            def configure(self, **kwargs):
                raise AssertionError("Ein zerstoertes Widget darf nicht aktualisiert werden.")

        app = JobScoutAI.__new__(JobScoutAI)
        app.ansicht = "ki_suche"
        app.suche_laeuft = False
        app.ki_laeuft = False
        app.ki_jobsuche_laeuft = False
        app.ki_suchplan_button = ZerstoertesWidget()
        app.ki_jobsuche_start_button = ZerstoertesWidget()
        app.ki_suchbegriff_hinzufuegen_button = ZerstoertesWidget()

        app._ki_jobsuche_button_status_aktualisieren()


if __name__ == "__main__":
    unittest.main()
