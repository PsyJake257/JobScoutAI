import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from analysis.ai_analysis import OllamaAnalysisClient
from analysis.job_search_planner import AiJobSearchPlanner, suchbegriffe_aus_antwort
from app import JobScoutAI
from models import SearchRequest
from ui_text import anzeigetext
from ui_widgets import kontrastfarbe


class UiLanguageAndAiTests(unittest.TestCase):
    def test_german_display_without_false_replacements(self):
        self.assertEqual(anzeigetext("Gespraech: Naechste Vorschlaege fuer Buero uebernehmen"), "Gespräch: Nächste Vorschläge für Büro übernehmen")
        self.assertEqual(anzeigetext("Neue Quellen: Jooble, Segoe UI, JOBSCOUT_API_KEY"), "Neue Quellen: Jooble, Segoe UI, JOBSCOUT_API_KEY")
        self.assertEqual(anzeigetext("Schließen und zurück"), "Schließen und zurück")

    def test_light_buttons_get_dark_text(self):
        self.assertEqual(kontrastfarbe("#62B2FF"), "#071522")
        self.assertEqual(kontrastfarbe("#176DB3"), "#FFFFFF")

    def test_client_reads_portable_endpoint_at_creation(self):
        with patch.dict(os.environ, {"JOBSCOUT_OLLAMA_URL": "http://127.0.0.1:11435"}):
            self.assertEqual(OllamaAnalysisClient().base_url, "http://127.0.0.1:11435")
            self.assertEqual(OllamaAnalysisClient(base_url="http://example.test").base_url, "http://example.test")

    def test_ai_action_recovers_embedded_runtime(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.portable_ai = Mock()
        app.portable_ai.ollama_exe.is_file.return_value = True
        app.portable_ai.starten.return_value = True
        app._lokale_ki_bereitstellen()
        app.portable_ai.starten.assert_called_once()
        app.portable_ai.starten.return_value = False
        with self.assertRaises(RuntimeError):
            app._lokale_ki_bereitstellen()

    def test_planner_explains_connection_failure(self):
        client = SimpleNamespace(model="test", generate_json=lambda _: None, last_error_kind="connection")
        planner = AiJobSearchPlanner(client=client)
        self.assertEqual(planner.suchbegriffe_generieren(SearchRequest("", "", "30")), [])
        self.assertIn("nicht erreichbar", planner.letzte_meldung)

    def test_planner_rejects_placeholder_professions(self):
        data = {"search_terms": ["Berufsbezeichnung 1", "Suchbegriff", "Sachbearbeiter"]}
        self.assertEqual(suchbegriffe_aus_antwort(data, SearchRequest("Buero", "", "30"), 3), ["Sachbearbeiter"])

    def test_background_error_callback_keeps_exception(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app._lokale_ki_bereitstellen = Mock(side_effect=RuntimeError("test failure"))
        event = Mock()
        event.is_set.return_value = False
        callbacks = []
        app._gui_ausfuehren = callbacks.append
        app._ki_jobsuche_fehlgeschlagen = Mock()
        app._ki_suchbegriffe_im_hintergrund(None, event)
        callbacks[0]()
        self.assertEqual(str(app._ki_jobsuche_fehlgeschlagen.call_args.args[0]), "test failure")
