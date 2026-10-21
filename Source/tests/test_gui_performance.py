import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app import JobScoutAI
from models import Job
from repositories.json_repository import JsonJobRepository
from scroll_widgets import IdleScrollbar, ResponsiveScrollableFrame


class GuiPerformanceTests(unittest.TestCase):
    def test_repository_reads_once_and_returns_isolated_values(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / "Backups") as folder:
            file = Path(folder) / "jobs.json"
            file.write_text(json.dumps([{"titel": "Test", "quellen": ["Testquelle"]}]), encoding="utf-8")
            repository = JsonJobRepository(file)
            with patch("repositories.json_repository.json.load", wraps=json.load) as read:
                jobs = repository.laden()
                jobs[0].titel = "Nicht gespeichert"
                jobs[0].quellen.append("Andere Quelle")
                second = repository.laden()
                self.assertEqual(read.call_count, 1)
                self.assertEqual(second[0].titel, "Test")
                self.assertNotIn("Andere Quelle", second[0].quellen)

    def test_repository_notices_external_changes_and_saved_changes(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / "Backups") as folder:
            file = Path(folder) / "jobs.json"
            file.write_text('[{"titel":"Alt"}]', encoding="utf-8")
            repository = JsonJobRepository(file)
            self.assertEqual(repository.laden()[0].titel, "Alt")
            file.write_text('[{"titel":"Extern geaendert"}]', encoding="utf-8")
            self.assertEqual(repository.laden()[0].titel, "Extern geaendert")
            repository.speichern([])
            self.assertEqual(repository.laden(), [])

    def _frame(self):
        frame = ResponsiveScrollableFrame.__new__(ResponsiveScrollableFrame)
        frame._parent_canvas = Mock()
        frame._parent_canvas.yview.return_value = (0.1, 0.5)
        frame._check_if_valid_scroll = Mock(return_value=True)
        frame._apply_widget_scaling = lambda value: value
        frame.after = Mock(return_value="timer")
        frame._wheel_pending = None
        frame._wheel_amount = {"x": 0.0, "y": 0.0}
        return frame

    def test_wheel_burst_is_combined_without_losing_distance(self):
        frame = self._frame()
        with patch("scroll_widgets.sys.platform", "win32"):
            for _ in range(10):
                frame._mouse_wheel_all(SimpleNamespace(widget=Mock(), state=0, delta=-120))
        frame.after.assert_called_once()
        frame._parent_canvas.yview_scroll.assert_not_called()
        frame._flush_wheel()
        frame._parent_canvas.yview_scroll.assert_called_once_with(480, "units")

    def test_textbox_wheel_is_not_intercepted(self):
        frame = self._frame()
        frame._check_if_valid_scroll.return_value = False
        frame._mouse_wheel_all(SimpleNamespace(widget=Mock()))
        frame.after.assert_not_called()

    def test_scroll_position_events_do_not_recompute_region(self):
        frame = self._frame()
        frame._content_size = (800, 2000)
        frame.after_idle = Mock()
        frame._content_configured(SimpleNamespace(width=800, height=2000))
        frame.after_idle.assert_not_called()

    def test_drag_uses_latest_position_with_one_scheduled_draw(self):
        frame = self._frame()
        frame._drag_pending = None
        frame._orientation = "vertical"
        frame._scrollbar_command("moveto", 0.2)
        frame._scrollbar_command("moveto", 0.8)
        frame.after.assert_called_once()
        frame._flush_drag()
        frame._parent_canvas.yview.assert_called_once_with("moveto", 0.8)

    def test_scrollbar_does_not_flush_gui_or_redraw_unchanged_position(self):
        bar = IdleScrollbar.__new__(IdleScrollbar)
        bar._start_value, bar._end_value = 0.0, 0.5
        bar._get_scrollbar_values_for_minimum_pixel_size = lambda: (bar._start_value, bar._end_value)
        bar._current_width, bar._current_height = 16, 500
        bar._corner_radius, bar._border_spacing = 4, 2
        bar._orientation = "vertical"
        bar._apply_widget_scaling = lambda value: value
        bar._draw_engine = Mock()
        bar._draw_engine.draw_rounded_scrollbar.return_value = False
        bar._canvas = Mock()
        bar.set(0.0, 0.5)
        bar._draw_engine.draw_rounded_scrollbar.assert_not_called()
        bar.set(0.1, 0.6)
        bar._canvas.update_idletasks.assert_not_called()

    def test_more_text_updates_only_its_own_card(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.beschreibung_status = Mock()
        app.beschreibung_status.ist_aufgeklappt.return_value = True
        label, button = Mock(), Mock()
        app._beschreibungs_widgets = {"job": [(label, button, "Text " * 100)]}
        app.zeige_jobs = Mock()
        app.beschreibung_umschalten("job")
        app.zeige_jobs.assert_not_called()
        label.configure.assert_called_once()
        button.configure.assert_called_once_with(text="Weniger anzeigen")

    def test_analysis_page_is_bounded_to_result_page_size(self):
        app = JobScoutAI.__new__(JobScoutAI)
        app.aktuelle_seite = 1
        jobs = list(range(30))
        self.assertEqual(app._jobs_der_seite(jobs), list(range(12, 24)))


if __name__ == "__main__":
    unittest.main()
