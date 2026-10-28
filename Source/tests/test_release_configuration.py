import re
import unittest
from pathlib import Path

from PIL import Image

from app import PROVIDER_EINSTELLUNGEN
from config import ACTIVE_PROVIDER_NAMES, ETHICAL_SCRAPING_USER_AGENT, LOCAL_AI_ANALYSIS_MODEL, VERSION


class ReleaseConfigurationTests(unittest.TestCase):
    def test_version_ist_semver_und_steuert_user_agent(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"JobScoutAI/{VERSION}", ETHICAL_SCRAPING_USER_AGENT)

    def test_einstellungen_decken_alle_produktiven_provider_ab(self):
        namen = [eintrag["name"] for eintrag in PROVIDER_EINSTELLUNGEN]

        self.assertEqual(namen, ACTIVE_PROVIDER_NAMES)
        self.assertTrue(all(eintrag["url"].startswith("https://") for eintrag in PROVIDER_EINSTELLUNGEN))
        self.assertTrue(all(eintrag["beschreibung"] for eintrag in PROVIDER_EINSTELLUNGEN))

    def test_portabler_build_versteckt_eigenes_konsolenfenster(self):
        source = Path(__file__).resolve().parents[1]
        spec = (source / "JobScoutAI.spec").read_text(encoding="utf-8")

        self.assertIn("console=False", spec)

    def test_branding_assets_sind_fuer_ui_und_windows_build_vorhanden(self):
        source = Path(__file__).resolve().parents[1]
        logo_pfad = source / "assets" / "jobscout_logo.png"
        icon_pfad = source / "assets" / "jobscout_icon.ico"

        self.assertTrue(logo_pfad.is_file())
        self.assertTrue(icon_pfad.is_file())
        with Image.open(logo_pfad) as logo:
            self.assertEqual(logo.size, (512, 512))
            self.assertEqual(logo.mode, "RGBA")
            self.assertEqual(logo.getchannel("A").getextrema(), (0, 255))
        with Image.open(icon_pfad) as icon:
            self.assertEqual(icon.format, "ICO")
            self.assertIn((256, 256), icon.info.get("sizes", set()))

    def test_portabler_build_buendelt_und_verwendet_das_app_icon(self):
        source = Path(__file__).resolve().parents[1]
        spec = (source / "JobScoutAI.spec").read_text(encoding="utf-8")

        self.assertIn("branding_datas", spec)
        self.assertIn('icon=str(Path("assets") / "jobscout_icon.ico")', spec)

    def test_oeffentlicher_build_verwendet_portables_gemma_e2b(self):
        source = Path(__file__).resolve().parents[1]
        runtime = (source / "portable_ai.py").read_text(encoding="utf-8")
        build_script = (source.parent / "Tools" / "PublicBuild_erstellen.ps1").read_text(encoding="utf-8")

        self.assertEqual(LOCAL_AI_ANALYSIS_MODEL, "gemma-4-E2B")
        self.assertIn('"--host", "127.0.0.1"', runtime)
        self.assertIn('"--offline"', runtime)
        self.assertIn('"--api-key", key', runtime)
        self.assertIn("MODEL-PROVENANCE.json", build_script)
        self.assertIn("GEMMA4_E2B_LICENSE.txt", build_script)


if __name__ == "__main__":
    unittest.main()
