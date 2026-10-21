import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from setup_dialogs import EINLEITUNG, GefuehrteEinleitung, erklaerung_position


class GuidedTourTests(unittest.TestCase):
    def test_panel_moves_away_from_bottom_right_target(self):
        position = erklaerung_position((220, 16, 1264, 804), (360, 280), (850, 500, 1260, 800))
        self.assertEqual(position, (904, 16))

    def test_panel_stays_inside_small_window(self):
        x, y = erklaerung_position((235, 16, 1024, 684), (420, 350), (235, 16, 1024, 200))
        self.assertGreaterEqual(x, 235)
        self.assertGreaterEqual(y, 16)
        self.assertLessEqual(x + 420, 1024)
        self.assertLessEqual(y + 350, 684)

    def test_close_restores_pagination_tab_and_zero_scroll(self):
        owner = SimpleNamespace(
            ki_suchbereich=Mock(), liste=SimpleNamespace(_parent_canvas=Mock()),
            _ansicht_wechseln=Mock(), _einleitungs_entwurf_wiederherstellen=Mock(),
        )
        tour = GefuehrteEinleitung.__new__(GefuehrteEinleitung)
        tour.owner = owner
        tour.app = Mock()
        tour.app.after_idle.side_effect = lambda action: action()
        tour.abgeschlossen = Mock()
        tour.destroy = Mock()
        tour.ausgang = "bewerbungen"
        tour.zustaende = {"bewerbungen": {"seite": 2, "status": "Beworben", "scrollposition": 0.0}}
        tour.suchbereich = "Ergebnisse"
        tour.bewerbungsstatus = "Beworben"
        tour.entwurf = {"neuer_begriff": "unsaved"}

        tour.schliessen(speichern=False)

        self.assertFalse(owner.einleitung_aktiv)
        self.assertEqual(owner.ansichts_zustaende, tour.zustaende)
        self.assertIsNot(owner.ansichts_zustaende, tour.zustaende)
        owner.ki_suchbereich.set.assert_called_once_with("Ergebnisse")
        owner._ansicht_wechseln.assert_called_once_with("bewerbungen")
        owner._einleitungs_entwurf_wiederherstellen.assert_called_once_with(tour.entwurf)
        owner.liste._parent_canvas.yview_moveto.assert_called_once_with(0.0)
        tour.abgeschlossen.assert_not_called()

    def test_tour_covers_all_categories_with_separate_ai_terms_and_suggestions(self):
        self.assertEqual({step[0] for step in EINLEITUNG}, {"dashboard", "suche", "ki_suche", "profil", "ki", "bewerbungen", "einstellungen"})
        self.assertIn(("ki_suche", "begriffe"), [step[:2] for step in EINLEITUNG])
        self.assertIn(("ki_suche", "vorschlaege"), [step[:2] for step in EINLEITUNG])
