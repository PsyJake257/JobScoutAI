import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from socket import timeout as SocketTimeout
from unittest.mock import patch
from urllib.error import HTTPError

from app import (
    BeschreibungAnzeigeStatus,
    JobScoutAI,
    analyse_treffer_auswaehlen,
    beschreibung_hat_mehr,
    beschreibung_lesbar,
    beschreibung_vorschau,
    darstellung_normalisieren,
    favoriten_button_text,
    haeufigkeiten,
    ist_detailfeld_schreibgeschuetzt,
    ki_aktionszustand,
    ki_beste_treffer,
    match_score_verteilung,
    scrollbare_liste_nach_oben,
    status_badge_farben,
    suchstatus_daten,
)
from analysis import AiAnalysisStep, AiJobSearchPlanner
from analysis.ai_analysis import (
    OllamaAnalysisClient,
    _analyse_kandidaten,
    _analyse_prompt,
    _beschreibung_wirkt_gekuerzt,
)
from analysis.job_search_planner import suchbegriffe_aus_antwort
from application.job_search_service import JobSearchService
from cancellation import OperationCancelled
from filters import JobFilter
from models import JOB_STATUS_VALUES, Job, SearchRequest
from pipeline.search_pipeline import SearchPipeline
from providers.base_provider import JobProvider
from providers.exceptions import ProviderError
from providers.http_client import JsonHttpClient
from providers.registry import ProviderRegistry
from repositories.json_repository import (
    JsonJobRepository,
    JsonSearchTermRepository,
    JsonSearchTermSetRepository,
    JsonUserProfileRepository,
)
from repositories.json_repository import JsonSettingsRepository


class MemorySettingsRepository:
    def laden(self):
        return {}

    def speichern(self, settings):
        self.settings = settings


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class FakeLabel:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def pack(self, *args, **kwargs):
        return None


class FakeTextbox:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.state = "normal"
        self.text = ""
        self.bindings = {}

    def insert(self, index, text):
        if self.state != "disabled":
            self.text += text

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def bind(self, event, callback):
        self.bindings[event] = callback

    def pack(self, *args, **kwargs):
        return None


class FakeValue:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class GoodProvider(JobProvider):
    name = "good"
    anzeigename = "Good"
    aktiv = True

    def suchen(self, suchanfrage):
        return [Job(titel="Job", firma="Firma", ort="Ort", quelle=self.anzeigename, link="https://x.test")]


class BlockingProvider(JobProvider):
    name = "blocking"
    anzeigename = "Blocking"
    aktiv = True

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def suchen(self, suchanfrage):
        self.started.set()
        self.release.wait(3)
        return [Job(titel="Verspaetet", firma="Firma", ort="Ort", quelle=self.anzeigename)]


class ManyProvider(JobProvider):
    def __init__(self, name, anzeigename, titel_prefix, anzahl):
        self.name = name
        self.anzeigename = anzeigename
        self.aktiv = True
        self.titel_prefix = titel_prefix
        self.anzahl = anzahl

    def suchen(self, suchanfrage):
        return [
            Job(titel=f"{self.titel_prefix} {index}", firma=self.anzeigename, ort="Ort", quelle=self.anzeigename)
            for index in range(self.anzahl)
        ]


class DuplicateProvider(JobProvider):
    def __init__(self, name, anzeigename, link):
        self.name = name
        self.anzeigename = anzeigename
        self.aktiv = True
        self.link = link

    def suchen(self, suchanfrage):
        return [Job(titel="Gleicher Job", firma="Firma", ort="Ort", quelle=self.anzeigename, link=self.link)]


class DisabledProvider(JobProvider):
    name = "disabled"
    anzeigename = "Disabled"
    aktiv = True

    def deaktivierungsgrund(self):
        return "Disabled wurde beim Start deaktiviert."

    def suchen(self, suchanfrage):
        raise AssertionError("Deaktivierte Provider duerfen nicht gesucht werden.")


class BrokenProvider(JobProvider):
    name = "broken"
    anzeigename = "Broken"
    aktiv = True

    def suchen(self, suchanfrage):
        raise ProviderError("technisch", "Benutzerhinweis")

class EchoProvider(JobProvider):
    name = "echo"
    anzeigename = "Echo"
    aktiv = True

    def __init__(self):
        self.suchbegriffe = []

    def suchen(self, suchanfrage):
        self.suchbegriffe.append(suchanfrage.suchbegriff)
        return [
            Job(
                titel=f"{suchanfrage.suchbegriff} Stelle",
                firma="Firma",
                ort=suchanfrage.ort or "Ort",
                quelle=self.anzeigename,
                link=f"https://jobs.test/{suchanfrage.suchbegriff.lower().replace(' ', '-')}",
            )
        ]


class DuplicateEchoProvider(JobProvider):
    name = "duplicate_echo"
    anzeigename = "Duplicate Echo"
    aktiv = True

    def suchen(self, suchanfrage):
        return [
            Job(
                titel="Gleicher KI-Job",
                firma="Firma",
                ort="Ort",
                quelle=self.anzeigename,
                link="https://jobs.test/gleich",
            )
        ]


class FakeAnalysisClient:
    model = "qwen3:8b"

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return self.response


class BlockingAnalysisClient:
    model = "qwen3:8b"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def generate_json(self, prompt, abbruch_event=None):
        self.started.set()
        self.release.wait(3)
        return {"summary": "Verspaetete Auswertung", "jobs": []}

    def abbrechen(self):
        self.release.set()


class HttpPipelineRepositoryTests(unittest.TestCase):
    def service_mit_repository(self, datei, provider=None, analyse=None):
        return JobSearchService(
            SearchPipeline(ProviderRegistry([provider or GoodProvider()]), JobFilter(), analyse or AiAnalysisStep()),
            JsonJobRepository(datei),
            MemorySettingsRepository(),
            search_term_repository=JsonSearchTermRepository(datei.with_name("search_terms.json")),
            search_term_set_repository=JsonSearchTermSetRepository(datei.with_name("search_term_sets.json")),
            user_profile_repository=JsonUserProfileRepository(datei.with_name("user_profiles.json")),
        )

    def test_timeout_wird_provider_error(self):
        client = JsonHttpClient(timeout_seconds=1)

        with patch("providers.http_client.urlopen", side_effect=SocketTimeout("timeout")):
            with self.assertRaises(ProviderError) as context:
                client.get_json("https://example.com", headers={})

        self.assertIn("Keine Verbindung", context.exception.benutzer_meldung)

    def test_ungueltiges_json_wird_provider_error(self):
        client = JsonHttpClient(timeout_seconds=1)

        with patch("providers.http_client.urlopen", return_value=FakeResponse(b"kein json")):
            with self.assertRaises(ProviderError) as context:
                client.get_json("https://example.com", headers={})

        self.assertIn("ungueltige Antwort", context.exception.benutzer_meldung)

    def test_post_json_maskiert_api_key_in_fehler(self):
        client = JsonHttpClient(timeout_seconds=1)

        with patch("providers.http_client.urlopen", side_effect=SocketTimeout("timeout")):
            with self.assertRaises(ProviderError) as context:
                client.post_json("https://jooble.org/api/geheimer-key", headers={}, body={"keywords": "x"})

        self.assertNotIn("geheimer-key", str(context.exception))

    def test_http_fehler_wird_provider_error(self):
        client = JsonHttpClient(timeout_seconds=1)
        fehler = HTTPError("https://example.com", 500, "Serverfehler", hdrs=None, fp=None)

        with patch("providers.http_client.urlopen", side_effect=fehler):
            with self.assertRaises(ProviderError):
                client.get_json("https://example.com", headers={})

    def test_pipeline_sammelt_benutzerhinweise(self):
        pipeline = SearchPipeline(ProviderRegistry([BrokenProvider()]), JobFilter(), AiAnalysisStep())

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(jobs, [])
        self.assertEqual(pipeline.letzte_meldungen, ["Benutzerhinweis"])

    def test_provider_fehler_verhindert_nicht_andere_ergebnisse(self):
        pipeline = SearchPipeline(ProviderRegistry([BrokenProvider(), GoodProvider()]), JobFilter(), AiAnalysisStep())

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Job")
        self.assertEqual(pipeline.letzte_meldungen, ["Benutzerhinweis"])
        self.assertIn("Broken: 0, Good: 1", pipeline.diagnose_meldung())

    def test_pipeline_suche_kann_waehrend_eines_blockierenden_providers_abbrechen(self):
        provider = BlockingProvider()
        pipeline = SearchPipeline(ProviderRegistry([provider]), JobFilter(), AiAnalysisStep())
        abbruch_event = threading.Event()
        fehler = []
        abgeschlossen = threading.Event()

        def ausfuehren():
            try:
                pipeline.ausfuehren(SearchRequest("x", "y", "10"), abbruch_event=abbruch_event)
            except Exception as ausnahme:
                fehler.append(ausnahme)
            finally:
                abgeschlossen.set()

        thread = threading.Thread(target=ausfuehren)
        thread.start()
        try:
            self.assertTrue(provider.started.wait(1))
            abbruch_event.set()
            self.assertTrue(abgeschlossen.wait(1))
            self.assertIsInstance(fehler[0], OperationCancelled)
        finally:
            provider.release.set()
            thread.join(1)

    def test_pipeline_diagnose_zaehlt_provider_und_deduplizierung(self):
        pipeline = SearchPipeline(
            ProviderRegistry([ManyProvider("a", "A", "A", 2), ManyProvider("b", "B", "B", 1)]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(len(jobs), 3)
        self.assertEqual(pipeline.letzte_diagnose["treffer_vor_filter"], {"A": 2, "B": 1})
        self.assertEqual(pipeline.letzte_diagnose["treffer_nach_deduplizierung"], 3)
        self.assertIn("A: 2, B: 1", pipeline.diagnose_meldung())

    def test_pipeline_suche_startet_lokale_ki_nicht_automatisch(self):
        client = FakeAnalysisClient({
            "summary": "Ein guter Treffer.",
            "jobs": [{
                "index": 0,
                "match_score": 82,
                "recommendation": "anschauen",
                "summary": "Passt gut zur Suche.",
                "strengths": ["Remote"],
                "risks": ["Gehalt fehlt"],
                "skills": ["Python"],
            }],
        })
        analyse = AiAnalysisStep(client=client, enabled=True, max_jobs=1)
        pipeline = SearchPipeline(ProviderRegistry([GoodProvider()]), JobFilter(), analyse)

        jobs = pipeline.ausfuehren(SearchRequest("Python", "Berlin", "10"))

        self.assertFalse(jobs[0].hat_ki_daten())
        self.assertEqual(client.prompts, [])
        self.assertEqual(pipeline.ki_zusammenfassung(), "")
        self.assertIn("Lokale KI-Auswertung noch nicht gestartet.", pipeline.diagnose_meldung())

        pipeline.ki_analysieren(jobs, SearchRequest("Python", "Berlin", "10"))

        self.assertEqual(jobs[0].ki_match_score, 82)
        self.assertEqual(jobs[0].ki_bewertungsart, "echt")
        self.assertEqual(jobs[0].ki_empfehlung, "anschauen")
        self.assertEqual(jobs[0].ki_zusammenfassung, "Passt gut zur Suche.")
        self.assertEqual(jobs[0].ki_staerken, ["Remote"])
        self.assertEqual(jobs[0].ki_risiken, ["Gehalt fehlt"])
        self.assertEqual(jobs[0].ki_skills, ["Python"])
        self.assertEqual(pipeline.ki_zusammenfassung(), "Ein guter Treffer.")
        self.assertIn("1 Treffer beruecksichtigt, 1 Top-Kandidaten ausgewaehlt.", pipeline.diagnose_meldung())
        self.assertEqual(pipeline.ki_analyse_status(), "echt")
        self.assertEqual(pipeline.ki_analyse_anzahlen(), (1, 0))
        self.assertIn("Python", client.prompts[0])

    def test_service_ki_analyse_bewertet_aktuelle_jobs_mit_kriterien(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeAnalysisClient({
                "summary": "Remote ist entscheidend.",
                "jobs": [{
                    "index": 0,
                    "match_score": 91,
                    "recommendation": "speichern",
                    "summary": "Passt zum Remote-Profil.",
                    "strengths": ["Remote"],
                    "risks": [],
                    "skills": ["Office"],
                }],
            })
            analyse = AiAnalysisStep(client=client, enabled=True, max_jobs=1)
            service = self.service_mit_repository(Path(tmp) / "jobs.json", analyse=analyse)
            jobs = service.search_jobs(SearchRequest("Teamassistenz", "Bad Nauheim", "30"))

            self.assertFalse(jobs[0].hat_ki_daten())

            service.ki_analyse_ausfuehren(
                jobs,
                SearchRequest(
                    "Teamassistenz",
                    "Bad Nauheim",
                    "30",
                    ki_kriterien={"homeoffice": True, "remote_modus": "zwingend"},
                ),
            )

            self.assertEqual(jobs[0].ki_match_score, 91)
            self.assertEqual(jobs[0].ki_empfehlung, "speichern")
            self.assertIn('"remote_modus": "zwingend"', client.prompts[0])
            self.assertEqual(service.job_repository.laden()[0].ki_zusammenfassung, "Passt zum Remote-Profil.")

    def test_abgebrochene_suche_speichert_keine_verspaeteten_treffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = BlockingProvider()
            datei = Path(tmp) / "jobs.json"
            repository = JsonJobRepository(datei)
            repository.speichern([Job(titel="Vorhanden", firma="A", ort="Ort", quelle="Test")])
            service = self.service_mit_repository(datei, provider=provider)
            abbruch_event = threading.Event()
            fehler = []
            abgeschlossen = threading.Event()

            def suchen():
                try:
                    service.search_jobs(SearchRequest("x", "y", "10"), abbruch_event=abbruch_event)
                except Exception as ausnahme:
                    fehler.append(ausnahme)
                finally:
                    abgeschlossen.set()

            thread = threading.Thread(target=suchen)
            thread.start()
            try:
                self.assertTrue(provider.started.wait(1))
                abbruch_event.set()
                self.assertTrue(abgeschlossen.wait(1))
                self.assertIsInstance(fehler[0], OperationCancelled)
                self.assertEqual([job.titel for job in repository.laden()], ["Vorhanden"])
            finally:
                provider.release.set()
                thread.join(1)

    def test_abgebrochene_ki_analyse_stellt_letzte_auswertung_wieder_her(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = BlockingAnalysisClient()
            analyse = AiAnalysisStep(client=client, enabled=True, max_jobs=1)
            analyse.letzte_zusammenfassung = "Vorheriges Fazit"
            analyse.letzte_meldung = "Vorherige Analyse abgeschlossen"
            analyse.letzter_status = "echt"
            analyse.echte_bewertungen = 1
            service = self.service_mit_repository(Path(tmp) / "jobs.json", analyse=analyse)
            job = Job(
                titel="Bestehende Analyse",
                firma="Firma",
                ort="Ort",
                quelle="Test",
                ki_match_score=84,
                ki_bewertungsart="echt",
                ki_zusammenfassung="Vorherige Bewertung",
            )
            abbruch_event = threading.Event()
            fehler = []
            abgeschlossen = threading.Event()

            def analysieren():
                try:
                    service.ki_analyse_ausfuehren(
                        [job],
                        SearchRequest("x", "y", "10"),
                        abbruch_event=abbruch_event,
                    )
                except Exception as ausnahme:
                    fehler.append(ausnahme)
                finally:
                    abgeschlossen.set()

            thread = threading.Thread(target=analysieren)
            thread.start()
            self.assertTrue(client.started.wait(1))
            abbruch_event.set()
            service.ki_analyse_abbrechen()
            self.assertTrue(abgeschlossen.wait(1))
            thread.join(1)

            self.assertIsInstance(fehler[0], OperationCancelled)
            self.assertEqual(job.ki_match_score, 84)
            self.assertEqual(job.ki_zusammenfassung, "Vorherige Bewertung")
            self.assertEqual(service.ki_analyse_status(), "echt")
            self.assertEqual(service.ki_zusammenfassung(), "Vorheriges Fazit")

    def test_lokale_ki_analyse_bleibt_bei_fehler_defensiv(self):
        analyse = AiAnalysisStep(client=FakeAnalysisClient(None), enabled=True, max_jobs=1)
        job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test")

        jobs = analyse.analysieren([job], SearchRequest("x", "y", "10"))

        self.assertIs(jobs[0], job)
        self.assertTrue(jobs[0].hat_ki_daten())
        self.assertEqual(jobs[0].ki_bewertungsart, "technisch")
        self.assertIn("Nur technische Vorbewertung", analyse.letzte_meldung)
        self.assertIn("keine verwertbare Antwort", analyse.letzte_zusammenfassung)
        self.assertEqual(analyse.letzter_status, "technisch")
        self.assertEqual((analyse.echte_bewertungen, analyse.technische_bewertungen), (0, 1))

    def test_ollama_client_nutzt_stabiles_json_profil(self):
        ollama_antwort = {
            "response": json.dumps({"summary": "Fazit", "jobs": []}),
            "done_reason": "stop",
            "prompt_eval_count": 123,
            "eval_count": 45,
            "load_duration": 2_000_000_000,
        }
        client = OllamaAnalysisClient(timeout_seconds=17)

        with patch(
            "analysis.ai_analysis.urlopen",
            return_value=FakeResponse(json.dumps(ollama_antwort).encode("utf-8")),
        ) as urlopen_mock:
            ergebnis = client.generate_json("Testprompt")

        request = urlopen_mock.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(ergebnis["summary"], "Fazit")
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertEqual(payload["format"], "json")
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 2048)
        self.assertEqual(urlopen_mock.call_args.kwargs["timeout"], 17)
        self.assertEqual(client.last_metrics["prompt_tokens"], 123)
        self.assertEqual(client.last_metrics["output_tokens"], 45)

    def test_ollama_client_bricht_auch_im_verbindungsaufbau_sofort_ab(self):
        gestartet = threading.Event()
        freigeben = threading.Event()
        abgeschlossen = threading.Event()
        abbruch_event = threading.Event()
        fehler = []
        antwort = {
            "response": json.dumps({"summary": "Zu spaet", "jobs": []}),
            "done_reason": "stop",
        }

        def langsames_urlopen(_request, timeout):
            gestartet.set()
            freigeben.wait(3)
            return FakeResponse(json.dumps(antwort).encode("utf-8"))

        client = OllamaAnalysisClient(timeout_seconds=17)

        def ausfuehren():
            try:
                client.generate_json("Testprompt", abbruch_event=abbruch_event)
            except Exception as ausnahme:
                fehler.append(ausnahme)
            finally:
                abgeschlossen.set()

        with patch("analysis.ai_analysis.urlopen", side_effect=langsames_urlopen):
            thread = threading.Thread(target=ausfuehren)
            thread.start()
            try:
                self.assertTrue(gestartet.wait(1))
                abbruch_event.set()
                self.assertTrue(abgeschlossen.wait(1))
                self.assertIsInstance(fehler[0], OperationCancelled)
            finally:
                freigeben.set()
                thread.join(1)

    def test_teilantwort_wird_nicht_als_vollstaendige_ki_analyse_ausgegeben(self):
        response = {
            "summary": "Ein Kandidat wurde bewertet.",
            "jobs": [{
                "index": 0,
                "match_score": 88,
                "recommendation": "anschauen",
                "summary": "Gute Passung.",
                "strengths": ["Office"],
                "risks": [],
                "skills": ["Organisation"],
            }],
        }
        analyse = AiAnalysisStep(client=FakeAnalysisClient(response), enabled=True, max_jobs=2)
        jobs = [
            Job(titel="Assistenz", firma="A", ort="Bad Nauheim", quelle="Test"),
            Job(titel="Buerokraft", firma="B", ort="Bad Nauheim", quelle="Test"),
        ]

        analyse.analysieren(jobs, SearchRequest("Buero", "Bad Nauheim", "20"))

        self.assertEqual(analyse.letzter_status, "teilweise")
        self.assertEqual((analyse.echte_bewertungen, analyse.technische_bewertungen), (1, 1))
        self.assertIn("fehlende Kandidaten", analyse.letzte_zusammenfassung)
        self.assertEqual(
            sum("Technische Vorbewertung" in job.ki_zusammenfassung for job in jobs),
            1,
        )

    def test_leere_kriterien_und_profilfelder_werden_im_prompt_ignoriert(self):
        prompt = _analyse_prompt(
            [Job(titel="Assistenz", firma="A", ort="Bad Nauheim", quelle="Test")],
            SearchRequest(
                "Assistenz",
                "Bad Nauheim",
                "20",
                ki_kriterien={
                    "remote_modus": "egal",
                    "prioritaet": "Ausgewogen",
                    "arbeitszeit": "",
                    "nutzerprofil": {"staerken": "", "kenntnisse": "Office"},
                },
            ),
        )

        self.assertIn('"ki_kriterien": {}', prompt)
        self.assertIn('"nutzerprofil": {"kenntnisse": "Office"}', prompt)
        self.assertNotIn('"arbeitszeit": ""', prompt)

    def test_ki_aktionszustand_kennzeichnet_nur_echte_analyse_gruen(self):
        analyse, weiter = ki_aktionszustand(False, False, True, "echt", True)
        self.assertEqual(analyse, ("normal", "Analyse starten"))
        self.assertEqual(weiter, ("normal", "Zur KI-Analyse", "erfolg"))

        _analyse, technisch = ki_aktionszustand(False, False, True, "technisch", True)
        self.assertEqual(technisch, ("normal", "Zur KI-Analyse", "neutral"))

        laufend, weiter_laufend = ki_aktionszustand(False, True, True, "nicht_gestartet", False)
        self.assertEqual(laufend, ("normal", "Analyse abbrechen"))
        self.assertEqual(weiter_laufend, ("disabled", "Analyse laeuft...", "neutral"))

        _analyse, ohne_daten = ki_aktionszustand(False, False, True, "nicht_gestartet", False)
        self.assertEqual(ohne_daten, ("normal", "Zur KI-Analyse", "erfolg"))

    def test_analyse_treffer_auswahl_kombiniert_quellen_ohne_dubletten(self):
        normal = [
            Job(titel="Assistenz", firma="A", ort="Bad Nauheim", quelle="Test"),
            Job(titel="Sachbearbeitung", firma="B", ort="Friedberg", quelle="Test"),
        ]
        ki = [
            Job(titel="Assistenz", firma="A", ort="Bad Nauheim", quelle="Andere Quelle"),
            Job(titel="Office Manager", firma="C", ort="Frankfurt", quelle="Test"),
        ]

        kombiniert = analyse_treffer_auswaehlen(normal, ki, True, True)
        nur_ki = analyse_treffer_auswaehlen(normal, ki, False, True)

        self.assertEqual([job.titel for job in kombiniert], ["Assistenz", "Sachbearbeitung", "Office Manager"])
        self.assertEqual([job.titel for job in nur_ki], ["Assistenz", "Office Manager"])

    def test_ki_basis_suchanfrage_nutzt_eigene_region_und_provider(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.ki_ort = FakeValue("Friedberg")
        app.ki_umkreis = FakeValue("50 km")
        app._ausgewaehlte_ki_provider = lambda: ["jooble", "arbeitnow"]
        app._ki_kriterien = lambda: {"teilzeit": True}

        anfrage = app._ki_basis_suchanfrage(mit_kriterien=True)

        self.assertEqual(anfrage.suchbegriff, "")
        self.assertEqual(anfrage.ort, "Friedberg")
        self.assertEqual(anfrage.umkreis, "50")
        self.assertEqual(anfrage.provider, ["jooble", "arbeitnow"])
        self.assertEqual(anfrage.ki_kriterien, {"teilzeit": True})

    def test_aktuelle_jobs_bleiben_nach_suchart_getrennt(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = JobScoutAI.__new__(JobScoutAI)
            normal = [
                Job(titel="Normal alt", firma="A", ort="Ort", quelle="Test", veroeffentlichungsdatum="2026-08-20"),
                Job(titel="Normal neu", firma="A", ort="Ort", quelle="Test", veroeffentlichungsdatum="2026-08-29"),
            ]
            ki = [
                Job(titel="KI alt", firma="B", ort="Ort", quelle="Test", veroeffentlichungsdatum="2026-08-21"),
                Job(titel="KI neu", firma="B", ort="Ort", quelle="Test", veroeffentlichungsdatum="2026-08-30"),
            ]
            app.job_service = self.service_mit_repository(Path(tmp) / "jobs.json")
            app.normale_treffer_sortierung = "Neueste zuerst"
            app.ki_treffer_sortierung = "Neueste zuerst"
            app.jobs = normal
            app.normale_suchergebnisse = normal
            app.ki_suchergebnisse = ki

            app.ansicht = "suche"
            self.assertEqual([job.titel for job in app._aktuelle_jobs()], ["Normal neu", "Normal alt"])
            app.ansicht = "ki_suche"
            self.assertEqual([job.titel for job in app._aktuelle_jobs()], ["KI neu", "KI alt"])

    def test_suchstatus_haelt_trefferquellen_strikt_getrennt(self):
        normal = suchstatus_daten("suche", normale_anzahl=0, ki_anzahl=509)
        ki = suchstatus_daten("ki_suche", normale_anzahl=0, ki_anzahl=509)

        self.assertEqual(normal, ("0 Treffer aus der Jobsuche", "normal", False))
        self.assertEqual(ki, ("509 Treffer aus der KI-Jobsuche", "ki", True))

    def test_suchstatus_zeigt_nur_kurze_lauf_und_fehlermeldungen(self):
        laufend = suchstatus_daten("ki_suche", ki_anzahl=509, ki_laeuft=True)
        fehler = suchstatus_daten(
            "suche",
            normale_anzahl=12,
            normale_meldung="Fehler bei der Suche: Zeitueberschreitung",
        )

        self.assertEqual(laufend, ("KI-Jobsuche laeuft...", "ki", False))
        self.assertEqual(fehler, ("Fehler bei der Suche: Zeitueberschreitung", "normal", False))

    def test_suchstatus_zeigt_abbruch_ohne_alte_treffer_zu_vermischen(self):
        normal = suchstatus_daten(
            "suche",
            normale_anzahl=12,
            normale_meldung="Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten.",
        )
        ki = suchstatus_daten(
            "ki_suche",
            ki_anzahl=509,
            ki_meldung="KI-Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten.",
        )

        self.assertEqual(normal[0], "Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten.")
        self.assertEqual(normal[1:], ("normal", False))
        self.assertEqual(ki[0], "KI-Jobsuche abgebrochen. Vorherige Treffer bleiben erhalten.")
        self.assertEqual(ki[1:], ("ki", False))

    def test_ki_jobsuche_bleibt_nach_abschluss_in_eigener_ergebnisansicht(self):
        class Widget:
            def configure(self, **_kwargs):
                return None

        class Service:
            def status_meldung(self):
                return "2 Jobs gefunden"

            def diagnose_meldung(self):
                return "Diagnose"

        app = JobScoutAI.__new__(JobScoutAI)
        normal = [Job(titel="Normal", firma="A", ort="Ort", quelle="Test")]
        ki = [Job(titel="KI", firma="B", ort="Ort", quelle="Test", ki_match_score=75)]
        app.jobs = normal
        app.normale_suchergebnisse = normal
        app.ki_suchergebnisse = []
        app.analyse_jobs = normal.copy()
        app.ki_kriterien_snapshot = {}
        app.ki_zusammenfassung_veraltet = True
        app.analyse_normale_jobs = FakeValue(True)
        app.analyse_ki_jobs = FakeValue(False)
        app.ki_suchbereich = FakeValue("Suchbegriffe")
        app.such_button = Widget()
        app.status = Widget()
        app.diagnose = Widget()
        app.ki_status = Widget()
        app.job_service = Service()
        app.zeige_jobs = lambda: None
        app._ki_zusammenfassung_text = lambda: ""
        app._ki_button_status_aktualisieren = lambda: None
        app._ki_jobsuche_button_status_aktualisieren = lambda: None

        app._ki_jobsuche_abgeschlossen(ki, SearchRequest("KI", "Friedberg", "50", ["jooble"]))

        self.assertEqual(app.ansicht, "ki_suche")
        self.assertEqual(app.ki_suchbereich.get(), "Ergebnisse")
        self.assertIs(app.jobs, normal)
        self.assertEqual(app.ki_suchergebnisse, ki)

    def test_verwaltungsdaten_werden_zwischen_ergebnislisten_synchronisiert(self):
        app = JobScoutAI.__new__(JobScoutAI)
        normal = Job(titel="Assistenz", firma="A", ort="Ort", quelle="Test")
        ki = Job(titel="Assistenz", firma="A", ort="Ort", quelle="Andere Quelle")
        app.jobs = [normal]
        app.normale_suchergebnisse = [normal]
        app.ki_suchergebnisse = [ki]
        app.analyse_jobs = [ki]
        ki.favorit = True
        ki.status = "Gespeichert"
        ki.notizen = "Interessant"

        app._ergebnislisten_synchronisieren(ki)

        self.assertTrue(normal.favorit)
        self.assertEqual(normal.status, "Gespeichert")
        self.assertEqual(normal.notizen, "Interessant")

    def test_scrollbare_liste_springt_nach_oben(self):
        class Canvas:
            def __init__(self):
                self.position = None

            def yview_moveto(self, position):
                self.position = position

        class Liste:
            def __init__(self):
                self._parent_canvas = Canvas()

        liste = Liste()

        self.assertTrue(scrollbare_liste_nach_oben(liste))
        self.assertEqual(liste._parent_canvas.position, 0)
    def test_ki_suchplan_filtert_bedingungen_und_begrenzt_auf_acht(self):
        anfrage = SearchRequest("", "Bad Nauheim", "30")
        begriffe = suchbegriffe_aus_antwort(
            {
                "search_terms": [
                    "Remote",
                    "Teilzeit",
                    "Sachbearbeiter Verwaltung",
                    "Bad Nauheim",
                    "Buerokraft",
                    "Assistenz Verwaltung",
                    "Kaufmaennischer Mitarbeiter",
                    "Weiterbildungskoordination",
                    "Seminarorganisation",
                    "Office Manager",
                    "Empfangsmitarbeiter",
                    "Datenerfassung",
                    "Projektassistenz",
                ]
            },
            anfrage,
            8,
        )

        self.assertEqual(len(begriffe), 8)
        self.assertNotIn("Remote", begriffe)
        self.assertNotIn("Teilzeit", begriffe)
        self.assertNotIn("Bad Nauheim", begriffe)
        self.assertEqual(begriffe[0], "Sachbearbeiter Verwaltung")

    def test_ki_suchplaner_nutzt_lokales_ollama_json(self):
        client = FakeAnalysisClient({"search_terms": ["Buerokraft", "Assistenz", "Homeoffice"]})
        planner = AiJobSearchPlanner(client=client, max_terms=8)

        begriffe = planner.suchbegriffe_generieren(
            SearchRequest(
                "",
                "Bad Nauheim",
                "30",
                ki_kriterien={"teilzeit": True, "nutzerprofil": {"kenntnisse": "Office"}},
            )
        )

        self.assertEqual(begriffe, ["Buerokraft", "Assistenz"])
        self.assertEqual(planner.letzter_status, "echt")
        self.assertIn("Office", client.prompts[0])

    def test_ki_suchplan_filtert_bereits_gespeicherte_und_nahezu_identische_begriffe(self):
        client = FakeAnalysisClient({
            "search_terms": ["Assistenz Verwaltung", "Verwaltung Assistenz", "Projektassistenz"]
        })
        planner = AiJobSearchPlanner(client=client, max_terms=8)

        begriffe = planner.suchbegriffe_generieren(
            SearchRequest("", "Bad Nauheim", "30"),
            ["Verwaltungsassistenz", "Assistenz Verwaltung"],
        )

        self.assertEqual(begriffe, ["Projektassistenz"])
        self.assertIn("bereits_gespeicherte_suchbegriffe", client.prompts[0])

    def test_suchbegriff_pool_bleibt_persistent_und_unterstuetzt_statuswechsel(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)

            begriff = service.suchbegriff_hinzufuegen("Buerokraft", "manuell")
            self.assertIsNotNone(begriff)
            self.assertIsNone(service.suchbegriff_hinzufuegen("Buerokraft", "KI"))

            service.suchbegriff_status_setzen(begriff.id, "pausiert")
            self.assertEqual(service.aktive_suchbegriffe(), [])
            service.suchbegriff_status_setzen(begriff.id, "aktiv")

            neu_geladen = self.service_mit_repository(datei)
            self.assertEqual(neu_geladen.aktive_suchbegriffe(), ["Buerokraft"])
            neu_geladen.suchbegriff_status_setzen(begriff.id, "geloescht")
            self.assertEqual(neu_geladen.suchbegriffe_laden(), [])
            self.assertEqual(neu_geladen.suchbegriffe_laden(True)[0].status, "geloescht")

    def test_suchbegriff_set_speichert_pool_und_aktivstatus_und_ersetzt_beim_laden(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            datenpflege = service.suchbegriff_hinzufuegen("Datenpflege", "manuell")
            service.suchbegriff_hinzufuegen("Projektassistenz", "KI")
            service.suchbegriff_status_setzen(datenpflege.id, "pausiert")

            gespeichert = service.suchbegriff_set_speichern("Buero-Jobs")

            self.assertIsNotNone(gespeichert)
            self.assertEqual(
                [(eintrag.bezeichnung, eintrag.status) for eintrag in gespeichert.suchbegriffe],
                [("Datenpflege", "pausiert"), ("Projektassistenz", "aktiv")],
            )

            for begriff in service.suchbegriffe_laden():
                service.suchbegriff_status_setzen(begriff.id, "geloescht")
            service.suchbegriff_hinzufuegen("Elektriker", "manuell")

            neu_geladen = self.service_mit_repository(datei)
            neu_geladen.suchbegriff_set_laden("Buero-Jobs")
            pool = neu_geladen.suchbegriffe_laden()

            self.assertEqual([begriff.bezeichnung for begriff in pool], ["Datenpflege", "Projektassistenz"])
            self.assertEqual([begriff.status for begriff in pool], ["pausiert", "aktiv"])
            self.assertEqual([begriff.quelle for begriff in pool], ["manuell", "KI"])
            self.assertNotIn("Elektriker", [begriff.bezeichnung for begriff in pool])

    def test_suchbegriff_set_verlangt_explizites_ueberschreiben_und_kann_geloescht_werden(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            service.suchbegriff_hinzufuegen("Buerokraft", "manuell")
            service.suchbegriff_set_speichern("Buero-Jobs")
            service.suchbegriff_hinzufuegen("Office Manager", "manuell")

            self.assertIsNone(service.suchbegriff_set_speichern("buero-jobs"))
            self.assertIn("existiert bereits", service.status_meldung())
            self.assertEqual(len(service.suchbegriff_sets_laden()[0].suchbegriffe), 1)

            ueberschrieben = service.suchbegriff_set_speichern("Buero-Jobs", ueberschreiben=True)
            self.assertEqual(len(ueberschrieben.suchbegriffe), 2)
            self.assertTrue(service.suchbegriff_set_loeschen("BUERO-JOBS"))
            self.assertEqual(service.suchbegriff_sets_laden(), [])

    def test_bisheriges_nutzerprofil_wird_einmalig_als_standardprofil_migriert(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            legacy_profil = {
                "kurzprofil": "Organisation und Verwaltung",
                "berufserfahrung": "Mehrjaehrige Sachbearbeitung",
                "staerken": "Strukturiert",
                "kenntnisse": "MS Office",
                "wunschrolle": "Backoffice",
                "einschraenkungen": "Kein Schichtdienst",
            }

            auswahl = service.nutzerprofile_initialisieren(legacy_profil)
            erneut = service.nutzerprofile_initialisieren({"kurzprofil": "Nicht uebernehmen"})

            self.assertEqual(auswahl, "Standardprofil")
            self.assertEqual(erneut, "Standardprofil")
            self.assertEqual(service.nutzerprofil_laden("standardprofil").daten(), legacy_profil)
            self.assertEqual(len(service.nutzerprofile_laden()), 1)

    def test_nutzerprofile_speichern_laden_und_schuetzen_vor_versehentlichem_ueberschreiben(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            service.nutzerprofil_speichern("Buero-Profil", {"kurzprofil": "Verwaltung"})

            with self.assertRaisesRegex(ValueError, "existiert bereits"):
                service.nutzerprofil_speichern("buero-profil", {"kurzprofil": "Handwerk"})

            profil = service.nutzerprofil_speichern(
                "Buero-Profil",
                {"kurzprofil": "Digitale Sachbearbeitung", "kenntnisse": "Excel"},
                ueberschreiben=True,
            )
            neu_geladen = self.service_mit_repository(Path(tmp) / "jobs.json")

            self.assertEqual(profil.kurzprofil, "Digitale Sachbearbeitung")
            self.assertEqual(neu_geladen.nutzerprofil_laden("BUERO-PROFIL").kenntnisse, "Excel")

    def test_nutzerprofil_kann_geloescht_werden(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            service.nutzerprofil_speichern("Buero", {"kurzprofil": "Sachbearbeitung"})
            service.nutzerprofil_speichern("Handwerk", {"kurzprofil": "Montage"})

            self.assertTrue(service.nutzerprofil_loeschen("buero"))
            self.assertFalse(service.nutzerprofil_existiert("Buero"))
            self.assertEqual([profil.name for profil in service.nutzerprofile_laden()], ["Handwerk"])

    def test_suchbegriff_umbenennen_erhaelt_jobherkunft_und_statistik(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            begriff = service.suchbegriff_hinzufuegen("Buerokraft", "manuell")
            service.jobs_speichern([
                Job(
                    titel="Buerokraft",
                    firma="A",
                    ort="Ort",
                    quelle="Test",
                    ki_suchbegriffe=["Buerokraft"],
                    ki_match_score=72,
                    ki_zusammenfassung="Gute Passung.",
                )
            ])

            service.suchbegriff_bearbeiten(begriff.id, "Mitarbeiter Buero")

            self.assertEqual(service.jobs_laden()[0].ki_suchbegriffe, ["Mitarbeiter Buero"])
            statistik = service.suchbegriffe_laden()[0]
            self.assertEqual(statistik.treffer_anzahl, 1)
            self.assertEqual(statistik.bester_score, 72)

    def test_ki_jobsuche_verwendet_alle_aktiven_poolbegriffe_auch_ueber_acht(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = EchoProvider()
            service = self.service_mit_repository(Path(tmp) / "jobs.json", provider=provider)
            begriffe = [f"Taetigkeit {buchstabe}" for buchstabe in "ABCDEFGHI"]
            for begriff in begriffe:
                service.suchbegriff_hinzufuegen(begriff, "manuell")

            service.ki_jobsuche_ausfuehren(
                service.aktive_suchbegriffe(),
                SearchRequest("", "Bad Nauheim", "30", ["echo"]),
            )

            self.assertEqual(provider.suchbegriffe, begriffe)

    def test_ki_jobsuche_startet_eigenen_suchlauf_pro_begriff(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = EchoProvider()
            service = self.service_mit_repository(Path(tmp) / "jobs.json", provider=provider)

            jobs = service.ki_jobsuche_ausfuehren(
                ["Buerokraft", "Assistenz"],
                SearchRequest("", "Bad Nauheim", "30", ["echo"]),
            )

            self.assertEqual(provider.suchbegriffe, ["Buerokraft", "Assistenz"])
            self.assertEqual(len(jobs), 2)
            self.assertEqual(jobs[0].ki_suchbegriffe, ["Buerokraft"])
            self.assertIn("KI-Suchbegriffe: Buerokraft, Assistenz", service.diagnose_meldung())

    def test_ki_jobsuche_erhaelt_mehrere_suchbegriffe_bei_dubletten(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json", provider=DuplicateEchoProvider())

            jobs = service.ki_jobsuche_ausfuehren(
                ["Buerokraft", "Assistenz"],
                SearchRequest("", "Bad Nauheim", "30", ["duplicate_echo"]),
            )

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].ki_suchbegriffe, ["Buerokraft", "Assistenz"])
            gespeicherte_jobs = service.jobs_laden()
            self.assertEqual(gespeicherte_jobs[0].ki_suchbegriffe, ["Buerokraft", "Assistenz"])

    def test_suchbegriff_statistiken_zaehlen_deduplizierte_jobs_je_begriff(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeAnalysisClient({
                "summary": "Guter gemeinsamer Treffer.",
                "jobs": [{
                    "index": 0,
                    "match_score": 70,
                    "recommendation": "anschauen",
                    "summary": "Uebertragbare Verwaltungsaufgaben.",
                    "strengths": ["Organisation"],
                    "hard_conflicts": [],
                    "open_questions": ["Arbeitszeit offen"],
                    "skills": ["Office"],
                }],
            })
            analyse = AiAnalysisStep(client=client, enabled=True, max_jobs=1)
            service = self.service_mit_repository(
                Path(tmp) / "jobs.json",
                provider=DuplicateEchoProvider(),
                analyse=analyse,
            )
            service.suchbegriff_hinzufuegen("Buerokraft", "manuell")
            service.suchbegriff_hinzufuegen("Assistenz", "KI")

            jobs = service.ki_jobsuche_ausfuehren(
                service.aktive_suchbegriffe(),
                SearchRequest("", "Bad Nauheim", "30", ["duplicate_echo"]),
            )
            service.ki_analyse_ausfuehren(jobs, SearchRequest("Buerokraft; Assistenz", "Bad Nauheim", "30"))

            statistik = {begriff.bezeichnung: begriff for begriff in service.suchbegriffe_laden()}
            for name in ("Buerokraft", "Assistenz"):
                self.assertEqual(statistik[name].treffer_anzahl, 1)
                self.assertEqual(statistik[name].ki_bewertet_anzahl, 1)
                self.assertEqual(statistik[name].gute_treffer_anzahl, 1)
                self.assertEqual(statistik[name].durchschnitt_score, 70)
                self.assertEqual(statistik[name].bester_score, 70)
                self.assertTrue(statistik[name].letzte_suche)

    def test_ki_score_wird_ohne_harten_konflikt_praxisnah_nachkalibriert(self):
        response = {
            "summary": "Zwei unterschiedliche Kandidaten.",
            "jobs": [
                {
                    "index": 0,
                    "match_score": 24,
                    "recommendation": "anschauen",
                    "summary": "Aufgaben sind uebertragbar.",
                    "strengths": ["Organisation"],
                    "hard_conflicts": [],
                    "open_questions": ["Teilzeit nicht genannt", "Gehalt fehlt"],
                    "skills": ["Office"],
                },
                {
                    "index": 1,
                    "match_score": 24,
                    "recommendation": "ignorieren",
                    "summary": "Vertrieb ist zwingend.",
                    "strengths": ["Digitale Kenntnisse"],
                    "hard_conflicts": ["Zwingende Vertriebspflicht"],
                    "open_questions": [],
                    "skills": ["Vertrieb"],
                },
            ],
        }
        analyse = AiAnalysisStep(client=FakeAnalysisClient(response), enabled=True, max_jobs=2)
        jobs = [
            Job(titel="Projektassistenz", firma="A", ort="Ort", quelle="Test"),
            Job(titel="Vertriebsleitung", firma="B", ort="Ort", quelle="Test"),
        ]

        analyse.analysieren(jobs, SearchRequest("Assistenz", "Ort", "30"))

        self.assertEqual(jobs[0].ki_match_score, 45)
        self.assertEqual(jobs[0].ki_offene_punkte, ["Teilzeit nicht genannt", "Gehalt fehlt"])
        self.assertEqual(jobs[1].ki_match_score, 24)
        self.assertEqual(jobs[1].ki_ausschluesse, ["Zwingende Vertriebspflicht"])
        self.assertIn("75-100: sehr gute Passung", analyse.client.prompts[0])
    def test_lokale_ki_vorsortierung_beruecksichtigt_alle_treffer(self):
        jobs = [
            Job(titel="Lagerhilfe", firma="Firma", ort="Giessen", quelle="Test", kurzbeschreibung="Schichtarbeit"),
            Job(
                titel="Buerokraft Teilzeit",
                firma="Firma",
                ort="Bad Nauheim",
                quelle="Test",
                kurzbeschreibung="Teilzeit Office Organisation ruhiges Buero Homeoffice moeglich",
            ),
            Job(titel="Verkauf", firma="Firma", ort="Usingen", quelle="Test", kurzbeschreibung="Kasse Verkauf"),
        ]
        suchanfrage = SearchRequest(
            "Buero",
            "Bad Nauheim",
            "30",
            ki_kriterien={"teilzeit": True, "homeoffice": True, "freitext": "ruhiges Buero"},
        )

        kandidaten = _analyse_kandidaten(jobs, suchanfrage, 1)

        self.assertEqual(kandidaten, [jobs[1]])

    def test_lokale_ki_analyse_meldet_beruecksichtigte_treffer_und_top_kandidaten(self):
        response = {
            "summary": "Top-Kandidat passt.",
            "jobs": [{
                "index": 0,
                "match_score": 90,
                "recommendation": "speichern",
                "summary": "Gute Passung.",
                "strengths": ["Teilzeit"],
                "risks": [],
                "skills": ["Office"],
            }],
        }
        client = FakeAnalysisClient(response)
        analyse = AiAnalysisStep(client=client, enabled=True, max_jobs=1)
        jobs = [
            Job(titel="Lagerhilfe", firma="Firma", ort="Giessen", quelle="Test", kurzbeschreibung="Schichtarbeit"),
            Job(titel="Buerokraft Teilzeit", firma="Firma", ort="Bad Nauheim", quelle="Test", kurzbeschreibung="Teilzeit Office"),
        ]

        analyse.analysieren(jobs, SearchRequest("Buero", "Bad Nauheim", "30"))

        self.assertIn("2 Treffer beruecksichtigt", analyse.letzte_meldung)
        self.assertIn("1 Top-Kandidaten", analyse.letzte_meldung)
        self.assertIn('"gesamt_treffer_vor_ki_screening": 2', client.prompts[0])
        self.assertTrue(jobs[1].hat_ki_daten())

    def test_faire_mischung_ergaenzt_provider_mit_wenigen_treffern(self):
        pipeline = SearchPipeline(
            ProviderRegistry([ManyProvider("a", "A", "A", 3), ManyProvider("b", "B", "B", 1)]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual([job.quelle for job in jobs], ["A", "B", "A", "A"])

    def test_faire_mischung_mit_drei_providern(self):
        pipeline = SearchPipeline(
            ProviderRegistry([
                ManyProvider("arbeitsagentur", "Bundesagentur fuer Arbeit", "A", 2),
                ManyProvider("jooble", "Jooble", "J", 2),
                ManyProvider("adzuna", "Adzuna", "Z", 2),
            ]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(
            [job.quelle for job in jobs],
            ["Bundesagentur fuer Arbeit", "Jooble", "Adzuna", "Bundesagentur fuer Arbeit", "Jooble", "Adzuna"],
        )

    def test_deduplizierung_ueber_provider_links(self):
        pipeline = SearchPipeline(
            ProviderRegistry([
                DuplicateProvider("a", "A", "https://example.com/job"),
                DuplicateProvider("b", "B", "https://example.com/job"),
            ]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(len(jobs), 1)

    def test_deduplizierung_normalisiert_trackingparameter_fragmente_und_host(self):
        pipeline = SearchPipeline(
            ProviderRegistry([
                DuplicateProvider("a", "A", "https://www.example.com/job/?utm_source=mail#oben"),
                DuplicateProvider("b", "B", "https://example.com/job"),
            ]),
            JobFilter(),
            AiAnalysisStep(),
        )

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(pipeline.letzte_diagnose["dubletten_entfernt"], 1)

    def test_deduplizierung_behaelt_vollstaendigere_daten(self):
        kurzer_provider = ManyProvider("a", "A", "A", 0)
        langer_provider = ManyProvider("b", "B", "B", 0)
        kurzer_provider.suchen = lambda suchanfrage: [
            Job(titel="Gleicher Job", firma="Firma", ort="Ort", quelle="A", kurzbeschreibung="kurz")
        ]
        langer_provider.suchen = lambda suchanfrage: [
            Job(titel="Gleicher Job", firma="Firma", ort="Ort", quelle="B", kurzbeschreibung="lang " * 200)
        ]
        pipeline = SearchPipeline(ProviderRegistry([kurzer_provider, langer_provider]), JobFilter(), AiAnalysisStep())

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(len(jobs), 1)
        self.assertGreater(len(jobs[0].kurzbeschreibung), 500)
        self.assertEqual(jobs[0].quelle, "B")

    def test_registry_deaktiviert_provider_mit_startproblem(self):
        registry = ProviderRegistry([DisabledProvider()])
        pipeline = SearchPipeline(registry, JobFilter(), AiAnalysisStep())

        jobs = pipeline.ausfuehren(SearchRequest("x", "y", "10"))

        self.assertEqual(jobs, [])
        self.assertEqual(registry.aktive(), [])
        self.assertIn("Disabled wurde beim Start deaktiviert.", pipeline.diagnose_meldung())

    def test_service_erklaert_leere_suchanfrage(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = JobSearchService(
                SearchPipeline(ProviderRegistry([GoodProvider()]), JobFilter(), AiAnalysisStep()),
                JsonJobRepository(Path(tmp) / "jobs.json"),
                MemorySettingsRepository(),
            )

            jobs = service.search_jobs(SearchRequest("   ", "   ", "30"))

        self.assertEqual(jobs, [])
        self.assertIn("Bitte Suchbegriff oder Ort", service.status_meldung())

    def test_service_erklaert_ungueltigen_umkreis(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = JobSearchService(
                SearchPipeline(ProviderRegistry([GoodProvider()]), JobFilter(), AiAnalysisStep()),
                JsonJobRepository(Path(tmp) / "jobs.json"),
                MemorySettingsRepository(),
            )

            jobs = service.search_jobs(SearchRequest("Pflege", "Berlin", "abc"))

        self.assertEqual(jobs, [])
        self.assertIn("gueltigen Umkreis", service.status_meldung())

    def test_jobs_speichern_und_laden(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            repository = JsonJobRepository(datei)
            repository.speichern([Job(titel="Job", firma="Firma", ort="Ort", quelle="Test")])

            jobs = repository.laden()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Job")

    def test_gespeicherter_job_wird_dauerhaft_geladen(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)

            service.job_speichern(Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test"))
            neue_service_instanz = self.service_mit_repository(datei)
            jobs = neue_service_instanz.gespeicherte_jobs_laden()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "Gespeichert")
        self.assertTrue(jobs[0].favorit)
        self.assertRegex(jobs[0].gespeichert_am, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_dashboard_liefert_die_fuenf_zuletzt_gespeicherten_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            repository = JsonJobRepository(datei)
            repository.speichern([
                Job(
                    titel=f"Job {index}",
                    firma="Firma",
                    ort="Ort",
                    quelle="Test",
                    favorit=True,
                    status="Gespeichert",
                    gespeichert_am=f"2026-08-{index + 1:02d}T09:00:00",
                )
                for index in range(7)
            ])
            service = self.service_mit_repository(datei)

            jobs = service.zuletzt_gespeicherte_jobs()

        self.assertEqual([job.titel for job in jobs], ["Job 6", "Job 5", "Job 4", "Job 3", "Job 2"])

    def test_legacy_job_leitet_speicherzeitpunkt_aus_erstem_status_ab(self):
        job = Job.from_dict({
            "titel": "Legacy Job",
            "firma": "Firma",
            "ort": "Ort",
            "quelle": "Test",
            "favorit": True,
            "statusverlauf": [
                {"id": "1", "datum": "2026-08-03", "uhrzeit": "10:15", "status": "Gespeichert"},
                {"id": "2", "datum": "2026-08-04", "uhrzeit": "11:30", "status": "Beworben"},
            ],
        })

        self.assertEqual(job.gespeichert_am, "2026-08-03T10:15:00")
        self.assertEqual(job.status, "Beworben")

    def test_status_badges_decken_alle_bewerbungsstatus_ab(self):
        farben = {status: status_badge_farben(status) for status in JOB_STATUS_VALUES}

        self.assertEqual(set(farben), set(JOB_STATUS_VALUES))
        self.assertNotEqual(farben["Beworben"], farben["Absage"])
        self.assertEqual(status_badge_farben("Unbekannt"), farben["Neu"])

    def test_favorit_kann_umgeschaltet_werden(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.favorit_umschalten(job)
            gespeicherter_job = service.gespeicherte_jobs_laden()[0]
            service.favorit_umschalten(gespeicherter_job)
            jobs = service.gespeicherte_jobs_laden()

        self.assertEqual(jobs, [])
        self.assertEqual(gespeicherter_job.gespeichert_am, "")

    def test_favoriten_symbol_ohne_herz_text(self):
        nicht_gespeichert = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test")
        gespeichert = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", favorit=True)

        self.assertEqual(favoriten_button_text(nicht_gespeichert), "\u2661")
        self.assertEqual(favoriten_button_text(gespeichert), "\u2665")
        self.assertNotIn("Herz:", favoriten_button_text(nicht_gespeichert))
        self.assertNotIn("Herz:", favoriten_button_text(gespeichert))

    def test_favoriten_toggle_aktualisiert_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://toggle.test")

            service.favorit_umschalten(job)
            symbol_gespeichert = favoriten_button_text(job)
            service.favorit_umschalten(job)
            symbol_entfernt = favoriten_button_text(job)

        self.assertEqual(symbol_gespeichert, "\u2665")
        self.assertEqual(symbol_entfernt, "\u2661")

    def test_entfernen_und_rueckgaengig_stellt_alle_verwaltungsdaten_wieder_her(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")
            service.job_details_speichern(job, {
                "status": "Beworben",
                "notizen": "Notiz",
                "bewerbungsdatum": "2026-08-01",
                "ansprechpartner": "Max",
                "email": "max@example.com",
                "telefon": "123",
                "gehaltsnotizen": "60k",
                "eigene_bewertung": "4",
                "naechste_aktion": "Nachfassen",
                "followup_datum": "2026-08-03",
                "followup_uhrzeit": "09:30",
                "followup_erledigt": False,
            })
            service.job_status_aendern(job, "Gespraech")

            service.favorit_umschalten(job)
            entfernte_jobs = service.gespeicherte_jobs_laden()
            wiederhergestellt = service.entfernung_rueckgaengig()
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden(status="Gespraech")

        self.assertEqual(entfernte_jobs, [])
        self.assertIsNotNone(wiederhergestellt)
        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].favorit)
        self.assertEqual(jobs[0].status, "Gespraech")
        self.assertEqual([eintrag["status"] for eintrag in jobs[0].statusverlauf], ["Beworben", "Gespraech"])
        self.assertEqual(jobs[0].notizen, "Notiz")
        self.assertEqual(jobs[0].bewerbungsdatum, "2026-08-01")
        self.assertEqual(jobs[0].ansprechpartner, "Max")
        self.assertEqual(jobs[0].email, "max@example.com")
        self.assertEqual(jobs[0].telefon, "123")
        self.assertEqual(jobs[0].gehaltsnotizen, "60k")
        self.assertEqual(jobs[0].eigene_bewertung, 4)
        self.assertEqual(jobs[0].naechste_aktion, "Nachfassen")
        self.assertEqual(jobs[0].followup_datum, "2026-08-03")
        self.assertEqual(jobs[0].followup_uhrzeit, "09:30")
        self.assertFalse(jobs[0].followup_erledigt)

    def test_status_notizen_und_bewerbungsdatum_werden_gespeichert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_status_aendern(job, "Bewerbung geplant")
            service.job_notizen_speichern(job, "Rueckfrage klaeren", "2026-08-01")
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden("rueckfrage", "Bewerbung geplant")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].notizen, "Rueckfrage klaeren")
        self.assertEqual(jobs[0].bewerbungsdatum, "2026-08-01")
        self.assertEqual(jobs[0].status, "Bewerbung geplant")

    def test_statuswechsel_erzeugt_verlauf(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_status_aendern(job, "Beworben")
            service.job_status_aendern(job, "Gespraech")
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden(status="Gespraech")

        self.assertEqual(len(jobs), 1)
        self.assertEqual([eintrag["status"] for eintrag in jobs[0].statusverlauf], ["Beworben", "Gespraech"])
        self.assertRegex(jobs[0].statusverlauf[0]["datum"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(jobs[0].statusverlauf[0]["uhrzeit"], r"^\d{2}:\d{2}$")

    def test_statusverlauf_bearbeiten_aktualisiert_aktuellen_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_status_aendern(job, "Beworben")
            service.job_status_aendern(job, "Gespraech")
            letzter_eintrag = job.statusverlauf[-1]
            service.statusverlauf_bearbeiten(job, letzter_eintrag["id"], "2026-08-03", "10:30", "Angebot")
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden(status="Angebot")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "Angebot")
        self.assertEqual(jobs[0].statusverlauf[-1]["datum"], "2026-08-03")
        self.assertEqual(jobs[0].statusverlauf[-1]["uhrzeit"], "10:30")

    def test_statusverlauf_loeschen_faellt_auf_vorherigen_status_zurueck(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_status_aendern(job, "Beworben")
            service.job_status_aendern(job, "Absage")
            service.statusverlauf_loeschen(job, job.statusverlauf[-1]["id"])
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden(status="Beworben")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "Beworben")
        self.assertEqual([eintrag["status"] for eintrag in jobs[0].statusverlauf], ["Beworben"])

    def test_detaildaten_werden_gespeichert_und_job_bleibt_kompatibel(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_details_speichern(job, {
                "titel": "Senior Job",
                "firma": "Neue Firma",
                "ort": "Berlin",
                "quelle": "Karriereseite",
                "link": "https://x.test/neu",
                "kurzbeschreibung": "Vollstaendige Beschreibung",
                "status": "Gespraech",
                "notizen": "Portfolio senden",
                "bewerbungsdatum": "2026-08-02",
                "ansprechpartner": "Max Muster",
                "email": "max@example.com",
                "telefon": "+49 30 123",
                "gehaltsnotizen": "60k bis 65k",
                "eigene_bewertung": "5",
            })
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden("portfolio", "Gespraech", "Karriereseite")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].titel, "Senior Job")
        self.assertEqual(jobs[0].link, "https://x.test/neu")
        self.assertEqual(jobs[0].ansprechpartner, "Max Muster")
        self.assertEqual(jobs[0].eigene_bewertung, 5)
        self.assertTrue(jobs[0].favorit)

    def test_detailworkflow_speichert_followup_ohne_zusatzlogik(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            aktualisiert = service.job_details_speichern(job, {
                "status": "Bewerbung geplant",
                "naechste_aktion": "Unterlagen pruefen",
                "followup_datum": "2026-08-04",
                "followup_uhrzeit": "11:15",
                "followup_erledigt": True,
            })
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden("unterlagen")

        self.assertIs(aktualisiert, job)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].naechste_aktion, "Unterlagen pruefen")
        self.assertEqual(jobs[0].followup_datum, "2026-08-04")
        self.assertEqual(jobs[0].followup_uhrzeit, "11:15")
        self.assertTrue(jobs[0].followup_erledigt)

    def test_statuswechsel_aktualisiert_beworben_flag_und_zaehlung(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Test", link="https://x.test")

            service.job_status_aendern(job, "Beworben")
            service.job_status_aendern(job, "Angebot")
            jobs = service.gespeicherte_jobs_laden(status="Erledigt")
            anzahl = service.status_anzahlen()
            status_werte = service.status_werte()

        self.assertEqual(len(jobs), 1)
        self.assertFalse(jobs[0].beworben)
        self.assertEqual(anzahl["Erledigt"], 1)
        self.assertEqual(anzahl["Beworben"], 0)
        self.assertNotIn("Angebot", status_werte)
        self.assertNotIn("Absage", status_werte)

    def test_schnelle_statuswechsel_bleiben_chronologisch(self):
        job = Job(
            titel="Job",
            firma="Firma",
            ort="Ort",
            quelle="Test",
            statusverlauf=[
                {"id": "20260725142551037159-a", "datum": "2026-07-25", "uhrzeit": "14:25", "status": "Angebot"},
                {"id": "20260725142551037158-b", "datum": "2026-07-25", "uhrzeit": "14:25", "status": "Beworben"},
            ],
        )

        self.assertEqual([eintrag["status"] for eintrag in job.statusverlauf], ["Beworben", "Angebot"])
        self.assertEqual(job.status, "Angebot")

    def test_alte_daten_ohne_verlauf_bleiben_kompatibel(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            datei.write_text(json.dumps([{
                "titel": "Legacy",
                "firma": "Firma",
                "ort": "Ort",
                "quelle": "Alt",
                "link": "https://legacy.test",
                "favorit": True,
                "status": "Beworben",
            }]), encoding="utf-8")
            service = self.service_mit_repository(datei)
            jobs = service.gespeicherte_jobs_laden(status="Beworben")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "Beworben")
        self.assertEqual(jobs[0].statusverlauf, [])
        self.assertTrue(jobs[0].favorit)

    def test_alte_daten_ohne_followup_bleiben_kompatibel(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            datei.write_text(json.dumps([{
                "titel": "Legacy",
                "firma": "Firma",
                "ort": "Ort",
                "quelle": "Alt",
                "favorit": True,
                "status": "Gespeichert",
            }]), encoding="utf-8")
            jobs = self.service_mit_repository(datei).gespeicherte_jobs_laden()

        self.assertEqual(jobs[0].naechste_aktion, "")
        self.assertEqual(jobs[0].followup_datum, "")
        self.assertEqual(jobs[0].followup_uhrzeit, "")
        self.assertFalse(jobs[0].followup_erledigt)

    def test_bewerbungen_werden_nach_status_und_quelle_gefiltert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            service.job_details_speichern(
                Job(titel="Python Entwickler", firma="A", ort="Berlin", quelle="Quelle A", link="https://a.test"),
                {"status": "Beworben", "notizen": "Remote moeglich"},
            )
            service.job_details_speichern(
                Job(titel="Assistenz", firma="B", ort="Hamburg", quelle="Quelle B", link="https://b.test"),
                {"status": "Gespraech", "notizen": "Vor Ort"},
            )

            jobs = service.gespeicherte_jobs_laden("remote", "Beworben", "Quelle A")
            gruppen = service.bewerbungen_nach_status("remote", "Alle", "Quelle A")

        self.assertEqual([job.titel for job in jobs], ["Python Entwickler"])
        self.assertEqual([job.titel for job in gruppen["Beworben"]], ["Python Entwickler"])
        self.assertEqual(gruppen["Gespraech"], [])

    def test_bewerbungen_werden_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            service.job_details_speichern(
                Job(
                    titel="Alt",
                    firma="A",
                    ort="Berlin",
                    quelle="Test",
                    link="https://alt.test",
                    veroeffentlichungsdatum="2026-01-01",
                ),
                {"bewerbungsdatum": "2026-08-01", "eigene_bewertung": "2"},
            )
            service.job_details_speichern(
                Job(
                    titel="Neu",
                    firma="B",
                    ort="Berlin",
                    quelle="Test",
                    link="https://neu.test",
                    veroeffentlichungsdatum="2026-07-01",
                ),
                {"bewerbungsdatum": "2026-07-01", "eigene_bewertung": "5"},
            )

            nach_bewerbung = service.gespeicherte_jobs_laden(sortierung="Bewerbungsdatum")
            nach_veroeffentlichung = service.gespeicherte_jobs_laden(sortierung="Veroeffentlichungsdatum")
            nach_bewertung = service.gespeicherte_jobs_laden(sortierung="Eigene Bewertung")

        self.assertEqual([job.titel for job in nach_bewerbung], ["Alt", "Neu"])
        self.assertEqual([job.titel for job in nach_veroeffentlichung], ["Neu", "Alt"])
        self.assertEqual([job.titel for job in nach_bewertung], ["Neu", "Alt"])

    def test_suchergebnisse_werden_nach_veroeffentlichung_sortiert_und_lassen_fehlende_daten_hinten(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            jobs = [
                Job("Ohne Datum", "D", "Berlin", "Test"),
                Job("Vor zwei Tagen", "C", "Berlin", "Test", veroeffentlichungsdatum="vor 2 Tagen"),
                Job("Gestern", "B", "Berlin", "Test", veroeffentlichungsdatum="gestern"),
                Job("Heute", "A", "Berlin", "Test", veroeffentlichungsdatum="heute"),
            ]

            neueste = service.suchergebnisse_sortieren(jobs, "Neueste zuerst")
            aelteste = service.suchergebnisse_sortieren(jobs, "Aelteste zuerst")

        self.assertEqual([job.titel for job in neueste], ["Heute", "Gestern", "Vor zwei Tagen", "Ohne Datum"])
        self.assertEqual([job.titel for job in aelteste], ["Vor zwei Tagen", "Gestern", "Heute", "Ohne Datum"])
        self.assertEqual([job.titel for job in jobs], ["Ohne Datum", "Vor zwei Tagen", "Gestern", "Heute"])

    def test_suchergebnisse_verstehen_iso_zeitpunkte_und_englische_relative_daten(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            jobs = [
                Job("Englisch alt", "A", "Berlin", "Test", veroeffentlichungsdatum="3 days ago"),
                Job("Englisch neu", "B", "Berlin", "Test", veroeffentlichungsdatum="today"),
                Job("ISO alt", "C", "Berlin", "Test", veroeffentlichungsdatum="2026-01-01T08:30:00Z"),
                Job("ISO neu", "D", "Berlin", "Test", veroeffentlichungsdatum="2026-02-01T09:30:00+01:00"),
            ]

            sortiert = service.suchergebnisse_sortieren(jobs, "Neueste zuerst")

        self.assertEqual(
            [job.titel for job in sortiert],
            ["Englisch neu", "Englisch alt", "ISO neu", "ISO alt"],
        )

    def test_suchergebnisse_werden_nach_textfeldern_und_ki_match_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service_mit_repository(Path(tmp) / "jobs.json")
            jobs = [
                Job("Beta", "Zeta GmbH", "Wiesbaden", "Test", ki_match_score=40),
                Job("Alpha", "Mitte AG", "Frankfurt", "Test", ki_match_score=80),
                Job("Gamma", "Alpha KG", "Bad Nauheim", "Test", ki_match_score=60),
            ]

            titel = service.suchergebnisse_sortieren(jobs, "Stellenname A-Z")
            firmen = service.suchergebnisse_sortieren(jobs, "Unternehmen Z-A")
            orte = service.suchergebnisse_sortieren(jobs, "Ort A-Z")
            match_ab = service.suchergebnisse_sortieren(jobs, "KI-Match: hoch nach niedrig")
            match_auf = service.suchergebnisse_sortieren(jobs, "KI-Match: niedrig nach hoch")

        self.assertEqual([job.titel for job in titel], ["Alpha", "Beta", "Gamma"])
        self.assertEqual([job.titel for job in firmen], ["Beta", "Alpha", "Gamma"])
        self.assertEqual([job.titel for job in orte], ["Gamma", "Alpha", "Beta"])
        self.assertEqual([job.ki_match_score for job in match_ab], [80, 60, 40])
        self.assertEqual([job.ki_match_score for job in match_auf], [40, 60, 80])

    def test_bewerbungen_werden_nach_letzter_statusaenderung_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            repository = JsonJobRepository(datei)
            repository.speichern([
                Job(
                    titel="Alt",
                    firma="A",
                    ort="Berlin",
                    quelle="Test",
                    link="https://alt.test",
                    favorit=True,
                    statusverlauf=[{"id": "1", "datum": "2026-08-01", "uhrzeit": "09:00", "status": "Beworben"}],
                ),
                Job(
                    titel="Neu",
                    firma="B",
                    ort="Berlin",
                    quelle="Test",
                    link="https://neu.test",
                    favorit=True,
                    statusverlauf=[{"id": "2", "datum": "2026-08-02", "uhrzeit": "09:00", "status": "Beworben"}],
                ),
            ])
            service = self.service_mit_repository(datei)

            jobs = service.gespeicherte_jobs_laden(sortierung="Letzte Statusaenderung")

        self.assertEqual([job.titel for job in jobs], ["Neu", "Alt"])

    def test_followups_werden_gespeichert_geaendert_gefiltert_und_sortiert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            heute = date.today().strftime("%Y-%m-%d")
            service.followup_speichern(
                Job(titel="Heute", firma="A", ort="Berlin", quelle="Test", link="https://heute.test"),
                "Anrufen",
                heute,
                "09:00",
            )
            service.followup_speichern(
                Job(titel="Spaeter", firma="B", ort="Berlin", quelle="Test", link="https://spaeter.test"),
                "Mail",
                "2099-01-01",
                "10:00",
            )
            service.job_speichern(Job(titel="Ohne", firma="C", ort="Berlin", quelle="Test", link="https://ohne.test"))
            spaeter = service.gespeicherte_jobs_laden("Spaeter")[0]
            service.followup_speichern(spaeter, "Mail aktualisiert", "2099-01-02", "12:00", True)

            heute_jobs = service.gespeicherte_jobs_laden(followup_filter="Heute")
            offene_jobs = service.gespeicherte_jobs_laden(followup_filter="Offene Follow-ups")
            ohne_jobs = service.gespeicherte_jobs_laden(followup_filter="Ohne Follow-up")
            sortiert = service.gespeicherte_jobs_laden(sortierung="Naechstes Follow-up")

        self.assertEqual([job.titel for job in heute_jobs], ["Heute"])
        self.assertEqual([job.titel for job in offene_jobs], ["Heute"])
        self.assertEqual([job.titel for job in ohne_jobs], ["Ohne"])
        self.assertEqual(sortiert[0].titel, "Heute")
        self.assertEqual(spaeter.naechste_aktion, "Mail aktualisiert")
        self.assertTrue(spaeter.followup_erledigt)

    def test_ueberfaellige_followups_werden_gefiltert(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            service.followup_speichern(
                Job(titel="Alt", firma="A", ort="Berlin", quelle="Test", link="https://alt-followup.test"),
                "Nachfassen",
                "2000-01-01",
            )

            jobs = service.gespeicherte_jobs_laden(followup_filter="Ueberfaellig")

        self.assertEqual([job.titel for job in jobs], ["Alt"])
        self.assertEqual(service.followup_status(jobs[0]), "ueberfaellig")

    def test_vollstaendige_beschreibung_wird_nicht_beim_zusammenfuehren_gekuerzt(self):
        with tempfile.TemporaryDirectory() as tmp:
            langer_text = "A" * 800
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            service.job_speichern(Job(
                titel="Job",
                firma="Firma",
                ort="Ort",
                quelle="Alt",
                link="https://x.test",
                kurzbeschreibung=langer_text,
            ))

            jobs = service.search_jobs(SearchRequest("Job", "Ort", "10"))

        self.assertEqual(jobs[0].kurzbeschreibung, langer_text)

    def test_mehr_weniger_anzeigezustand_und_markdown_lesbarkeit(self):
        status = BeschreibungAnzeigeStatus()
        schluessel = ("link", "https://x.test")
        langer_text = "**Wichtig** " + ("Beschreibung " * 40)

        vorschau = beschreibung_vorschau(langer_text)
        aufgeklappt = status.umschalten(schluessel)
        voller_text = beschreibung_vorschau(langer_text, status.ist_aufgeklappt(schluessel))
        wieder_zu = status.umschalten(schluessel)

        self.assertNotIn("**", beschreibung_lesbar(langer_text))
        self.assertTrue(vorschau.endswith("..."))
        self.assertTrue(aufgeklappt)
        self.assertIn("Wichtig", voller_text)
        self.assertFalse(wieder_zu)

    def test_mehr_button_nur_bei_langer_beschreibung(self):
        self.assertFalse(beschreibung_hat_mehr("Kurzer Text"))
        self.assertTrue(beschreibung_hat_mehr("Beschreibung " * 40))

    def test_mehr_weniger_mehrere_karten_behalten_zustand(self):
        status = BeschreibungAnzeigeStatus()
        erster = ("link", "https://eins.test")
        zweiter = ("link", "https://zwei.test")

        status.umschalten(erster)
        status.umschalten(zweiter)
        status.umschalten(erster)

        self.assertFalse(status.ist_aufgeklappt(erster))
        self.assertTrue(status.ist_aufgeklappt(zweiter))

    def test_detailbeschreibung_ist_schreibgeschuetzt_andere_textfelder_editierbar(self):
        app = JobScoutAI.__new__(JobScoutAI)
        with patch("app.ctk.CTkLabel", FakeLabel), patch("app.ctk.CTkTextbox", FakeTextbox):
            detail_beschreibung = JobScoutAI._detail_text(app, None, "kurzbeschreibung", "Volltext", 120)
            notizen = JobScoutAI._detail_text(app, None, "notizen", "Notiz", 120)

        self.assertTrue(ist_detailfeld_schreibgeschuetzt("kurzbeschreibung"))
        self.assertFalse(ist_detailfeld_schreibgeschuetzt("notizen"))
        self.assertEqual(detail_beschreibung.state, "normal")
        self.assertEqual(detail_beschreibung.bindings["<Key>"](), "break")
        self.assertEqual(detail_beschreibung.bindings["<<Paste>>"](), "break")
        self.assertEqual(detail_beschreibung.bindings["<<Cut>>"](), "break")
        self.assertEqual(notizen.state, "normal")
        self.assertEqual(notizen.bindings, {})

    def test_ki_prompt_behandelt_gekuerzte_provider_beschreibung_als_unsicherheit(self):
        job = Job(
            titel="Teamassistenz",
            firma="Firma",
            ort="Bad Nauheim",
            quelle="Provider",
            kurzbeschreibung="Kurzer Ausschnitt der Stellenbeschreibung",
        )

        prompt = _analyse_prompt([job], SearchRequest("Teamassistenz", "Bad Nauheim", "30"))

        self.assertIn("gekuerzte Stellenbeschreibungen", prompt)
        self.assertIn("nicht automatisch als schlechtes Job-Signal", prompt)
        self.assertTrue(_beschreibung_wirkt_gekuerzt(job.kurzbeschreibung))

    def test_ki_prompt_enthaelt_bewertungskriterien_des_nutzers(self):
        job = Job(
            titel="Remote Teamassistenz",
            firma="Firma",
            ort="Remote",
            quelle="Provider",
            kurzbeschreibung="Remote moeglich. Teilzeit ist nach Absprache denkbar.",
        )
        suchanfrage = SearchRequest(
            "Teamassistenz",
            "Bad Nauheim",
            "30",
            ki_kriterien={
                "homeoffice": True,
                "teilzeit": True,
                "wohnortnaehe": True,
                "remote_modus": "zwingend",
                "max_pendeln": "30 Minuten",
                "freitext": "wenig Telefon, strukturierte Aufgaben",
            },
        )

        prompt = _analyse_prompt([job], suchanfrage)

        self.assertIn("ki_kriterien", prompt)
        self.assertIn("Remote-Modus \"zwingend\"", prompt)
        self.assertIn('"remote_modus": "zwingend"', prompt)
        self.assertIn('"max_pendeln_oder_entfernung": "30 Minuten"', prompt)
        self.assertIn("wenig Telefon, strukturierte Aufgaben", prompt)
        self.assertIn("Die globale summary ist Pflicht", prompt)
        self.assertIn("fuer jeden gelieferten Top-Kandidaten genau eine Job-Bewertung", prompt)
        self.assertIn("Jede Job-summary soll erklaeren", prompt)

    def test_search_request_bereinigt_behaelt_ki_kriterien(self):
        suchanfrage = SearchRequest(
            "  Assistenz  ",
            "  Bad Nauheim  ",
            "30",
            ki_kriterien={"homeoffice": True, "remote_modus": "wichtig"},
        )

        bereinigt = suchanfrage.bereinigt()

        self.assertEqual(bereinigt.suchbegriff, "Assistenz")
        self.assertEqual(bereinigt.ort, "Bad Nauheim")
        self.assertEqual(bereinigt.ki_kriterien, {"homeoffice": True, "remote_modus": "wichtig"})
        self.assertIsNot(bereinigt.ki_kriterien, suchanfrage.ki_kriterien)

    def test_ki_kriterien_helfer_liefert_ui_profil(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.ki_kriterien_variablen = {
            "homeoffice": FakeValue(True),
            "teilzeit": FakeValue(False),
            "vollzeit": FakeValue(True),
            "wohnortnaehe": FakeValue(True),
        }
        app.ki_remote_modus = FakeValue("wichtig")
        app.ki_max_pendeln = FakeValue("30 Minuten")
        app.ki_kriterien_freitext = FakeValue("ruhiges Buero")

        self.assertEqual(
            app._ki_kriterien(),
            {
                "homeoffice": True,
                "teilzeit": False,
                "vollzeit": True,
                "wohnortnaehe": True,
                "remote_modus": "wichtig",
                "max_pendeln": "30 Minuten",
                "freitext": "ruhiges Buero",
            },
        )

    def test_ki_uebersicht_helfer_sortieren_risiken_und_skills(self):
        app = JobScoutAI.__new__(JobScoutAI)
        guter_job = Job(titel="A", firma="Firma", ort="Ort", quelle="Test", ki_match_score=80, ki_skills=["Office", "Kommunikation"])
        risiko_job = Job(titel="B", firma="Firma", ort="Ort", quelle="Test", ki_match_score=35, ki_risiken=["Entfernung pruefen"], ki_skills=["Office"])

        self.assertEqual(app._ki_risiko_jobs([guter_job, risiko_job]), [risiko_job])
        self.assertEqual(app._ki_skill_uebersicht([guter_job, risiko_job]), ["Office", "Kommunikation"])

    def test_darstellung_normalisieren_akzeptiert_gespeicherte_und_deutsche_werte(self):
        self.assertEqual(darstellung_normalisieren("system"), "system")
        self.assertEqual(darstellung_normalisieren("Hell"), "light")
        self.assertEqual(darstellung_normalisieren("Dunkel"), "dark")
        self.assertEqual(darstellung_normalisieren("unbekannt"), "system")

    def test_match_score_verteilung_und_haeufigkeiten_liefern_dashboard_daten(self):
        jobs = [
            Job(titel="A", firma="Firma", ort="Ort", quelle="A", ki_match_score=92),
            Job(titel="B", firma="Firma", ort="Ort", quelle="A", ki_match_score=68),
            Job(titel="C", firma="Firma", ort="Ort", quelle="B", ki_match_score=45),
            Job(titel="D", firma="Firma", ort="Ort", quelle="B", ki_match_score=20),
        ]

        self.assertEqual(
            match_score_verteilung(jobs),
            {
                "Sehr gute Passung (75-100)": 1,
                "Gute Passung (60-74)": 1,
                "Pruefenswert (45-59)": 1,
                "Schwach (30-44)": 0,
                "Eher unpassend (0-29)": 1,
            },
        )
        self.assertEqual(haeufigkeiten(["Office", "Python", "Office"]), [("Office", 2), ("Python", 1)])

    def test_ki_beste_treffer_zeigt_alle_bewerteten_kandidaten_sortiert(self):
        jobs = [
            Job(titel=f"Job {index}", firma="Firma", ort="Ort", quelle="Test", ki_match_score=50 + index)
            for index in range(16)
        ]
        jobs.append(Job(titel="Ohne KI", firma="Firma", ort="Ort", quelle="Test"))

        beste_treffer = ki_beste_treffer(jobs)

        self.assertEqual(len(beste_treffer), 16)
        self.assertEqual([job.titel for job in beste_treffer[:3]], ["Job 15", "Job 14", "Job 13"])
        self.assertEqual([job.titel for job in ki_beste_treffer(jobs, limit=5)], ["Job 15", "Job 14", "Job 13", "Job 12", "Job 11"])

    def test_repository_speichert_statusverlauf(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            repository.speichern([
                Job(
                    titel="Job",
                    firma="Firma",
                    ort="Ort",
                    quelle="Test",
                    statusverlauf=[{"id": "1", "datum": "2026-08-01", "uhrzeit": "09:00", "status": "Beworben"}],
                )
            ])

            jobs = repository.laden()

        self.assertEqual(jobs[0].status, "Beworben")
        self.assertEqual(jobs[0].statusverlauf[0]["status"], "Beworben")

    def test_settings_repository_laedt_provider_auswahl_kompatibel(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "settings.json"
            repository = JsonSettingsRepository(datei, {"suchbegriff": "", "ort": "", "umkreis": "30", "provider": []})
            repository.speichern({"suchbegriff": "Pflege", "provider": ["arbeitsagentur", "adzuna"]})

            settings = repository.laden()

        self.assertEqual(settings["suchbegriff"], "Pflege")
        self.assertEqual(settings["provider"], ["arbeitsagentur", "adzuna"])


    def test_erneut_gefundener_job_behaelt_verwaltungsdaten(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            service = self.service_mit_repository(datei)
            gespeicherter_job = Job(titel="Job", firma="Firma", ort="Ort", quelle="Alt", link="https://x.test")
            service.job_status_aendern(gespeicherter_job, "Gespraech")
            service.job_notizen_speichern(gespeicherter_job, "Termin Dienstag", "")

            jobs = service.search_jobs(SearchRequest("Job", "Ort", "10"))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].status, "Gespraech")
        self.assertEqual(jobs[0].notizen, "Termin Dienstag")

    def test_gespeicherte_jobs_werden_dedupliziert(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            repository.speichern([
                Job(titel="Job", firma="Firma", ort="Ort", quelle="A", link="https://x.test"),
                Job(titel="Job", firma="Firma", ort="Ort", quelle="B", link="https://x.test"),
            ])

            jobs = repository.laden()

        self.assertEqual(len(jobs), 1)

    def test_repository_speichert_und_laesst_vollstaendige_beschreibung(self):
        with tempfile.TemporaryDirectory() as tmp:
            langer_text = "Volltext " * 120
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            repository.speichern([
                Job(
                    titel="Job",
                    firma="Firma",
                    ort="Ort",
                    quelle="Test",
                    link="https://voll.test",
                    kurzbeschreibung=langer_text,
                )
            ])

            jobs = repository.laden()

        self.assertEqual(jobs[0].kurzbeschreibung, langer_text.strip())
        self.assertGreater(len(jobs[0].kurzbeschreibung), 500)

    def test_repository_speichert_ki_auswertung(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            repository.speichern([
                Job(
                    titel="Job",
                    firma="Firma",
                    ort="Ort",
                    quelle="Test",
                    ki_zusammenfassung="Guter Treffer",
                    ki_match_score=88,
                    ki_empfehlung="speichern",
                    ki_staerken=["Remote"],
                    ki_risiken=["Gehalt unklar"],
                    ki_skills=["Python"],
                )
            ])

            jobs = repository.laden()

        self.assertEqual(jobs[0].ki_zusammenfassung, "Guter Treffer")
        self.assertEqual(jobs[0].ki_match_score, 88)
        self.assertEqual(jobs[0].ki_empfehlung, "speichern")
        self.assertEqual(jobs[0].ki_staerken, ["Remote"])
        self.assertEqual(jobs[0].ki_risiken, ["Gehalt unklar"])
        self.assertEqual(jobs[0].ki_skills, ["Python"])

    def test_ki_kartentext_und_detailtext_sind_lesbar(self):
        app = JobScoutAI.__new__(JobScoutAI)
        job = Job(
            titel="Job",
            firma="Firma",
            ort="Ort",
            quelle="Test",
            ki_zusammenfassung="Passt gut.",
            ki_match_score=75,
            ki_empfehlung="anschauen",
            ki_staerken=["Remote"],
            ki_risiken=["Gehalt fehlt"],
            ki_skills=["Python", "SQL"],
        )

        kartentext = JobScoutAI._ki_job_text(app, job)
        detailtext = JobScoutAI._ki_detail_text(app, job)

        self.assertIn("KI-Match: 75/100", kartentext)
        self.assertIn("Empfehlung: anschauen", kartentext)
        self.assertIn("Skills: Python, SQL", kartentext)
        self.assertIn("Staerken: Remote", detailtext)
        self.assertIn("Risiken/offene Punkte: Gehalt fehlt", detailtext)

    def test_ki_fallback_gesamtfazit_nutzt_jobbewertungen(self):
        app = JobScoutAI.__new__(JobScoutAI)
        jobs = [
            Job(
                titel="Aushilfe Buero",
                firma="Firma",
                ort="Ort",
                quelle="Test",
                ki_match_score=80,
                ki_empfehlung="anschauen",
                ki_risiken=["Gehalt fehlt"],
                ki_skills=["Organisation"],
            ),
            Job(
                titel="Lagerjob",
                firma="Firma",
                ort="Ort",
                quelle="Test",
                ki_match_score=40,
                ki_empfehlung="ignorieren",
                ki_risiken=["Kein Remote"],
                ki_skills=["Zuverlaessigkeit"],
            ),
        ]

        fazit = JobScoutAI._ki_fallback_gesamtfazit(app, jobs)

        self.assertIn("2 Treffer bewertet", fazit)
        self.assertIn("Aushilfe Buero", fazit)
        self.assertIn("Gehalt fehlt", fazit)
        self.assertIn("Organisation", fazit)

    def test_ki_treffer_textteile_zeigen_fazit_staerken_risiken_und_skills(self):
        app = JobScoutAI.__new__(JobScoutAI)
        job = Job(
            titel="Job",
            firma="Firma",
            ort="Ort",
            quelle="Test",
            ki_zusammenfassung="Passt wegen Naehe, aber Remote fehlt.",
            ki_staerken=["Naehe", "Teilzeit"],
            ki_risiken=["Kein Remote"],
            ki_skills=["Office", "Kommunikation"],
        )

        teile = JobScoutAI._ki_treffer_textteile(app, job)

        self.assertIn(("Kurzfazit", "Passt wegen Naehe, aber Remote fehlt."), teile)
        self.assertIn(("Warum interessant", "Naehe, Teilzeit"), teile)
        self.assertIn(("Offene Punkte", "Kein Remote"), teile)
        self.assertIn(("Anforderungen", "Office, Kommunikation"), teile)

    def test_repository_behaelt_laengeren_text_bei_dubletten(self):
        with tempfile.TemporaryDirectory() as tmp:
            kurzer_text = "kurz"
            langer_text = "lang " * 200
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            repository.speichern([
                Job(
                    titel="Job",
                    firma="Firma",
                    ort="Ort",
                    quelle="Kurz",
                    link="https://dup.test",
                    kurzbeschreibung=kurzer_text,
                ),
                Job(
                    titel="Job",
                    firma="Firma",
                    ort="Ort",
                    quelle="Lang",
                    link="https://dup.test",
                    kurzbeschreibung=langer_text,
                ),
            ])

            jobs = repository.laden()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].kurzbeschreibung, langer_text.strip())

    def test_fehlende_json_datei_wird_sauber_behandelt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = JsonJobRepository(Path(tmp) / "jobs.json")
            jobs = repository.laden()

        self.assertEqual(jobs, [])

    def test_leere_json_datei_wird_sauber_behandelt(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            datei.write_text("", encoding="utf-8")
            repository = JsonJobRepository(datei)
            jobs = repository.laden()

        self.assertEqual(jobs, [])

    def test_beschaedigte_json_datei_wird_sauber_behandelt(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "jobs.json"
            datei.write_text("{ kaputt", encoding="utf-8")
            repository = JsonJobRepository(datei)
            jobs = repository.laden()
            self.assertEqual(json.loads(datei.read_text(encoding="utf-8")), [])

        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()


