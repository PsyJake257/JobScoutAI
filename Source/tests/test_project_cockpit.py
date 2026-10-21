import tempfile
import unittest
from pathlib import Path

from developer_tools.project_cockpit import collect_project_data, write_project_cockpit


class ProjectCockpitTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        source = root / "Source"
        knowledge = source / "knowledge"
        tests = source / "tests"
        app = root / "App"
        backups = root / "Backups"
        knowledge.mkdir(parents=True)
        tests.mkdir()
        app.mkdir()
        (backups / "manual_test").mkdir(parents=True)
        (app / "JobScoutAI.exe").write_bytes(b"test")
        (tests / "test_example.py").write_text("pass\n", encoding="utf-8")
        (knowledge / "CHANGELOG.md").write_text(
            "# CHANGELOG\n\n## Version 9.9 - Teststand\n\n- Sichtbare Verbesserung.\n",
            encoding="utf-8",
        )
        (knowledge / "PROJECT_STATE.md").write_text(
            "# PROJECT STATE\n\n"
            "## Bekannte Einschraenkungen\n\n- Testgrenze.\n\n"
            "## Offene Technische Punkte\n\n- Naechstes Ziel.\n",
            encoding="utf-8",
        )
        return source

    def test_collect_project_data_uses_project_documents_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._project(Path(tmp))
            data = collect_project_data(source)

        self.assertEqual(data["development_owner"], "Codex")
        self.assertEqual(data["runtime_ai"], "qwen3:4b")
        self.assertEqual(data["test_files"], 1)
        self.assertIn("Version 9.9 - Teststand", data["release"])
        self.assertIn("Naechstes Ziel.", data["goals"])
        self.assertIn("Testgrenze.", data["limits"])
        self.assertTrue(any("manual_test" in item for item in data["backups"]))

    def test_cockpit_is_neutral_and_contains_runtime_ai_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._project(Path(tmp))
            cockpit_path = write_project_cockpit(source)
            cockpit = cockpit_path.read_text(encoding="utf-8")

        self.assertIn("JobScout AI - Projektcockpit", cockpit)
        self.assertIn("Codex-only Entwicklung", cockpit)
        self.assertIn("qwen3:4b bleibt App-Laufzeit-KI", cockpit)
        self.assertIn("Sichtbare Verbesserung.", cockpit)
        self.assertNotIn("Delegierte Ollama-Aufgaben", cockpit)
        self.assertNotIn("Protokollierte Worker-Aufgaben", cockpit)


if __name__ == "__main__":
    unittest.main()
