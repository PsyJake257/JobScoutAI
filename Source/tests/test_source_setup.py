import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from providers.env_loader import lade_env_wert, speichere_env_werte
from providers.jooble_provider import JoobleProvider
from providers.registry import ProviderRegistry


class SourceSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = Path(self.tmp.name) / ".env"

    def test_create_read_and_clear(self):
        speichere_env_werte(self.env, {"JOOBLE_API_KEY": "test-key"})
        self.assertEqual(lade_env_wert(self.env, "JOOBLE_API_KEY"), "test-key")
        speichere_env_werte(self.env, {"JOOBLE_API_KEY": ""})
        self.assertEqual(lade_env_wert(self.env, "JOOBLE_API_KEY"), "")

    def test_preserve_comments_other_values_and_normalize_duplicates(self):
        self.env.write_text("# existing\nOTHER=leave-me\nJOOBLE_API_KEY=old\nJOOBLE_API_KEY=duplicate\n", encoding="utf-8")
        speichere_env_werte(self.env, {"JOOBLE_API_KEY": "replacement"})
        self.assertEqual(self.env.read_text(encoding="utf-8"), "# existing\nOTHER=leave-me\nJOOBLE_API_KEY=replacement\n")

    def test_windows_bom_and_urls(self):
        self.env.write_text("JOOBLE_API_KEY=old\n", encoding="utf-8-sig")
        self.assertEqual(lade_env_wert(self.env, "JOOBLE_API_KEY"), "old")
        urls = "https://example.org/jobs?a=1;https://example.com/careers"
        speichere_env_werte(self.env, {"CAREER_SITE_URLS": urls})
        self.assertEqual(lade_env_wert(self.env, "JOOBLE_API_KEY"), "old")
        self.assertEqual(lade_env_wert(self.env, "CAREER_SITE_URLS"), urls)

    def test_injection_rejected_before_write(self):
        self.env.write_text("OTHER=keep\n", encoding="utf-8")
        for value in ("bad\nOTHER=changed", "bad\rvalue", "bad\0value", '"quoted"'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                speichere_env_werte(self.env, {"JOOBLE_API_KEY": value})
        self.assertEqual(self.env.read_text(), "OTHER=keep\n")

    def test_failed_replace_preserves_original_and_cleans_temp(self):
        self.env.write_text("OTHER=keep\n", encoding="utf-8")
        with patch("providers.env_loader.os.replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                speichere_env_werte(self.env, {"JOOBLE_API_KEY": "not-committed"})
        self.assertEqual(self.env.read_text(), "OTHER=keep\n")
        self.assertEqual(list(self.env.parent.iterdir()), [self.env])

    def test_provider_availability_updates_after_save_and_clear(self):
        def registry():
            return ProviderRegistry([JoobleProvider(env_datei=self.env)], ["jooble"])

        self.assertEqual(registry().aktive(), [])
        speichere_env_werte(self.env, {"JOOBLE_API_KEY": "test-key"})
        self.assertEqual([provider.name for provider in registry().aktive()], ["jooble"])
        speichere_env_werte(self.env, {"JOOBLE_API_KEY": ""})
        self.assertEqual(registry().aktive(), [])
