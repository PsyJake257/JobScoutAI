import io
import json
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from analysis.ai_analysis import AiAnalysisStep
from analysis.llama_client import LlamaAnalysisClient
from analysis.single_job_analysis import gueltige_bewertung
from application.job_search_service import JobSearchService
from app import JobScoutAI
from cancellation import OperationCancelled
from config import LOCAL_AI_ANALYSIS_MODEL
from models import Job, SearchRequest
from portable_ai import PortableAiRuntime


GOOD = {"match_score": 75, "recommendation": "anschauen",
        "summary": "Die Stelle umfasst Datenpflege. Die vorhandene Erfahrung in der Büroorganisation passt dazu.",
        "strengths": ["Datenpflege"], "hard_conflicts": [], "open_questions": [], "skills": ["Word"]}


class Client:
    model = LOCAL_AI_ANALYSIS_MODEL
    last_error_kind = "timeout"

    def __init__(self, answers):
        self.answers, self.prompts = iter(answers), []

    def generate_json(self, prompt, abbruch_event=None):
        self.prompts.append(prompt)
        return deepcopy(next(self.answers))


def jobs():
    return [Job(f"Büro {i}", f"Firma{i}", "Ort", "Test") for i in range(3)]


class E2bVariantTests(unittest.TestCase):
    def test_single_requests_and_incremental_independent_snapshots(self):
        client, progress = Client([GOOD, GOOD, GOOD]), []
        data = jobs()
        step = AiAnalysisStep(client, enabled=True)
        step.analysieren(data, SearchRequest("Büro", "Ort", "20"), fortschritt=lambda *args: progress.append(args))
        progress = [item for item in progress if item[2] is not None and item[0] > 0]
        self.assertEqual([item[0] for item in progress], [1, 2, 3])
        self.assertEqual(step.echte_bewertungen, 3)
        for index, prompt in enumerate(client.prompts):
            self.assertIn(f"Firma{index}", prompt)
            self.assertTrue(all(f"Firma{other}" not in prompt for other in range(3) if other != index))
        progress[0][2][0].ki_zusammenfassung = "Geändert"
        self.assertNotEqual(data[0].ki_zusammenfassung, "Geändert")
        self.assertEqual(step.letzter_status, "echt")

    def test_timeout_only_affects_its_job_and_does_not_invent_score(self):
        data = jobs()
        step = AiAnalysisStep(Client([GOOD, None, GOOD]), enabled=True)
        step.analysieren(data, SearchRequest("Büro", "Ort", "20"))
        self.assertEqual(step.echte_bewertungen, 2)
        self.assertEqual(step.technische_bewertungen, 1)
        self.assertEqual(data[1].ki_bewertungsart, "technisch")
        self.assertEqual(data[1].ki_match_score, 0)
        self.assertFalse(data[1].ki_staerken)
        self.assertIn("Zeitlimit", data[1].ki_zusammenfassung)
        app = JobScoutAI.__new__(JobScoutAI)
        self.assertNotIn("/100", app._ki_job_text(data[1]))

    def test_missing_or_invalid_detail_response_is_rejected(self):
        self.assertFalse(gueltige_bewertung({"index": 0, "match_score": 99}))
        self.assertFalse(gueltige_bewertung({**GOOD, "summary": ""}))
        self.assertFalse(gueltige_bewertung({**GOOD, "match_score": True}))
        self.assertTrue(gueltige_bewertung(GOOD))

    def test_confirmed_conflicts_cannot_be_recommended_and_unknown_experience_is_not_claimed(self):
        data = jobs()[:1]
        answer = {**GOOD, "match_score": 90, "hard_conflicts": ["Personalführung ausgeschlossen"]}
        step = AiAnalysisStep(Client([answer]), enabled=True)
        step.analysieren(data, SearchRequest("Büro", "Ort", "20"))
        self.assertEqual(data[0].ki_empfehlung, "ignorieren")
        self.assertLess(data[0].ki_match_score, 45)
        self.assertEqual(data[0].ki_staerken, [])

    def test_cancel_between_jobs_stops_without_next_request(self):
        event, client = Event(), Client([GOOD, GOOD])
        step = AiAnalysisStep(client, enabled=True)
        with self.assertRaises(OperationCancelled):
            step.analysieren(jobs(), SearchRequest("Büro", "Ort", "20"), event,
                             fortschritt=lambda done, total, partial: event.set() if done and partial is not None else None)
        self.assertEqual(len(client.prompts), 1)

    def test_service_cancellation_restores_previous_ratings_without_save(self):
        event = Event()
        data = jobs()
        for job in data:
            job.ki_match_score, job.ki_zusammenfassung = 85, "Vorheriges Fazit"
        step = AiAnalysisStep(Client([GOOD, GOOD]), enabled=True)
        service = JobSearchService.__new__(JobSearchService)
        service.pipeline = SimpleNamespace(ai_analysis=step, ki_analysieren=step.analysieren)
        service.letzte_meldung = "Vorher"
        service.jobs_speichern = Mock()
        with self.assertRaises(OperationCancelled):
            service.ki_analyse_ausfuehren(data, SearchRequest("Büro", "Ort", "20"), event,
                                        fortschritt=lambda done, total, partial: event.set() if done and partial is not None else None)
        self.assertEqual([job.ki_match_score for job in data], [85, 85, 85])
        self.assertTrue(all(job.ki_zusammenfassung == "Vorheriges Fazit" for job in data))
        service.jobs_speichern.assert_not_called()

    def _stream(self, finish="stop"):
        events = [{"choices": [{"delta": {"content": json.dumps(GOOD)}, "finish_reason": None}]},
                  {"choices": [{"delta": {}, "finish_reason": finish}]}]
        return io.BytesIO(b"".join(b"data: " + json.dumps(item).encode() + b"\n\n" for item in events) + b"data: [DONE]\n\n")

    def test_local_chat_uses_json_schema_and_disables_thinking(self):
        client = LlamaAnalysisClient(response_schema={"type": "object"})
        with patch("analysis.llama_client.urlopen", return_value=self._stream()) as open_:
            self.assertEqual(client.generate_json("Test"), GOOD)
        payload = json.loads(open_.call_args.args[0].data)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["max_tokens"], 512)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["response_format"]["type"], "json_schema")

    def test_truncated_answer_is_never_a_real_rating(self):
        client = LlamaAnalysisClient()
        with patch("analysis.llama_client.urlopen", return_value=self._stream("length")):
            self.assertIsNone(client.generate_json("Test"))
        self.assertEqual(client.last_error_kind, "output_limit")

    def test_stale_progress_cannot_replace_cancelled_results(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.analyse_jobs = ["Vorher"]
        app._abbruchlauf_ist_aktuell = lambda *_: False
        app._ki_analyse_fortschritt(1, 2, ["Neu"], Event())
        self.assertEqual(app.analyse_jobs, ["Vorher"])

    def test_all_jobs_screened_before_best_fifteen_receive_detail(self):
        data = [Job(f"Titel{i}", f"Firma{i}", "Ort", "Test") for i in range(19)]
        screens = [{f"job_{i}": offset + i for i in range(min(4, 19 - offset))}
                   for offset in range(0, 19, 4)]
        client = Client(screens + [GOOD] * 15)
        progress = []
        step = AiAnalysisStep(client, enabled=True)
        step.analysieren(data, SearchRequest("Büro", "Ort", "20"),
                         fortschritt=lambda *args: progress.append(args))
        self.assertEqual(len(client.prompts), 5 + 15)
        for i, job in enumerate(data):
            self.assertIn(f'"Firma{i}"', client.prompts[i // 4])
            self.assertEqual(job.hat_ki_daten(), i >= 4)
        self.assertIn('"Firma18"', client.prompts[5])
        self.assertEqual(progress[5], (19, 19, None))
        self.assertEqual(progress[-1][:2], (15, 15))
        self.assertIn("Alle 19", step.letzte_zusammenfassung)

    def test_incomplete_screening_aborts_instead_of_silently_skipping_jobs(self):
        data = jobs()
        client = Client([{"job_0": 80}])
        with self.assertRaisesRegex(RuntimeError, "nicht alle Stellen"):
            AiAnalysisStep(client, enabled=True, max_jobs=2).analysieren(data, SearchRequest("Büro", "Ort", "20"))
        self.assertFalse(any(job.hat_ki_daten() for job in data))

    def test_cancel_during_screening_prevents_detail_requests(self):
        event = Event()
        client = Client([{"job_0": 80, "job_1": 60, "job_2": 40}])
        with self.assertRaises(OperationCancelled):
            AiAnalysisStep(client, enabled=True, max_jobs=2).analysieren(
                jobs(), SearchRequest("Büro", "Ort", "20"), event,
                fortschritt=lambda done, *_: event.set() if done else None)
        self.assertEqual(len(client.prompts), 1)

    def test_progress_updates_existing_widgets_and_appends_each_card_once(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.ansicht = "ki"
        app._abbruchlauf_ist_aktuell = lambda *_: True
        app._ki_live_container = object()
        app._ki_live_label, app._ki_live_balken, app._ki_setup_hinweis = Mock(), Mock(), Mock()
        app._ki_live_schluessel = set()
        app._ki_treffer_karte, app.zeige_jobs = Mock(), Mock()
        data = jobs()
        for job in data:
            job.ki_zusammenfassung = "Fazit"
        app.analyse_jobs = []
        app._ki_analyse_fortschritt(4, 19, None, Event())
        self.assertEqual(app.analyse_jobs, [])
        app._ki_live_balken.set.assert_called_with(4 / 19)
        app._ki_analyse_fortschritt(1, 3, data[:1], Event())
        app._ki_analyse_fortschritt(2, 3, deepcopy(data[:2]), Event())
        app._ki_analyse_fortschritt(2, 3, deepcopy(data[:2]), Event())
        self.assertEqual(app._ki_treffer_karte.call_count, 2)
        app._ki_live_balken.set.assert_called_with(2 / 3)
        app.zeige_jobs.assert_not_called()
        app.ansicht = "suche"
        app._ki_analyse_fortschritt(3, 3, data, Event())
        self.assertEqual(app._ki_treffer_karte.call_count, 2)
        self.assertEqual(app.analyse_jobs, data)

    def test_warmup_runs_once_and_uses_small_answer(self):
        runtime = PortableAiRuntime()
        runtime.starten = Mock(return_value=True)
        client = Mock()
        client.generate_json.return_value = {"bereit": True}
        with patch("analysis.llama_client.LlamaAnalysisClient", return_value=client) as create:
            runtime.vorwaermen()
            runtime.vorwaermen()
        client.generate_json.assert_called_once()
        self.assertEqual(create.call_args.kwargs["max_output_tokens"], 16)
        self.assertEqual(runtime.vorwaerm_status, "Bereit")

    def test_closing_during_warmup_prevents_any_late_process_start(self):
        runtime = PortableAiRuntime()
        runtime.beenden()
        with patch("portable_ai.subprocess.Popen") as start:
            self.assertFalse(runtime.starten())
            runtime.vorwaermen()
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
