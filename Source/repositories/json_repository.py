import json
import logging
from pathlib import Path
import shutil
from datetime import datetime
from typing import Iterable
from copy import deepcopy
from threading import RLock

from deduplication import DeduplizierungsStatistik, jobs_deduplizieren
from models import Job, SearchTerm, SearchTermSet, UserProfile


class JsonSettingsRepository:
    def __init__(self, datei: Path, standardwerte: dict[str, str]):
        self.datei = datei
        self.standardwerte = standardwerte

    def laden(self) -> dict[str, str]:
        self.datei.parent.mkdir(parents=True, exist_ok=True)

        if not self.datei.exists():
            self.speichern(self.standardwerte)
            return self.standardwerte.copy()

        try:
            with open(self.datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            return {**self.standardwerte, **daten}
        except Exception:
            self.speichern(self.standardwerte)
            return self.standardwerte.copy()

    def speichern(self, settings: dict[str, str]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)

        with open(self.datei, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)


class JsonJobRepository:
    def __init__(self, datei: Path):
        self.datei = datei
        self.letzte_deduplizierung = DeduplizierungsStatistik()
        self._cache_stamp = None
        self._cache_jobs = []
        self._cache_lock = RLock()

    def laden(self) -> list[Job]:
        with self._cache_lock:
            return self._laden_mit_cache()

    def _laden_mit_cache(self) -> list[Job]:
        self.datei.parent.mkdir(parents=True, exist_ok=True)

        if not self.datei.exists():
            self.speichern([])
            return []

        try:
            stat = self.datei.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._cache_stamp:
                return deepcopy(self._cache_jobs)
            with open(self.datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            jobs = [Job.from_dict(eintrag) for eintrag in daten]
            self._cache_jobs = jobs
            self._cache_stamp = stamp
            return deepcopy(jobs)
        except Exception:
            self.speichern([])
            return []

    def speichern(self, jobs: Iterable[Job]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)

        eindeutige_jobs = self._deduplizieren(jobs)
        self._atomar_schreiben([job.to_dict() for job in eindeutige_jobs])

    def _deduplizieren(self, jobs: Iterable[Job]) -> list[Job]:
        eindeutige_jobs, statistik = jobs_deduplizieren(list(jobs))
        self.letzte_deduplizierung = statistik
        return eindeutige_jobs

    def bestand_bereinigen_mit_sicherung(self) -> dict[str, object]:
        marker = self.datei.with_name(f"{self.datei.stem}.dedupe-v2.json")
        if marker.exists() or not self.datei.exists():
            return {"ausgefuehrt": False, "entfernt": 0}

        try:
            with open(self.datei, "r", encoding="utf-8") as f:
                rohdaten = json.load(f)
            if not isinstance(rohdaten, list):
                return {"ausgefuehrt": False, "entfernt": 0}
            jobs = [Job.from_dict(eintrag) for eintrag in rohdaten if isinstance(eintrag, dict)]
        except Exception:
            logging.exception("Jobbestand konnte fuer die Dublettenmigration nicht gelesen werden.")
            return {"ausgefuehrt": False, "entfernt": 0}

        eindeutige_jobs, statistik = jobs_deduplizieren(jobs)
        backup_datei = ""
        if statistik.gesamt:
            backup_ordner = self.datei.parent / "backups"
            backup_ordner.mkdir(parents=True, exist_ok=True)
            zeitstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = backup_ordner / f"{self.datei.stem}_vor_dedupe_v2_{zeitstempel}{self.datei.suffix}"
            shutil.copy2(self.datei, backup)
            backup_datei = str(backup)
            self.letzte_deduplizierung = statistik
            self._atomar_schreiben([job.to_dict() for job in eindeutige_jobs])
            logging.info(
                "Jobbestand bereinigt: %s -> %s Eintraege; Sicherung: %s",
                len(jobs),
                len(eindeutige_jobs),
                backup,
            )

        marker_daten = {
            "version": 2,
            "zeitpunkt": datetime.now().isoformat(timespec="seconds"),
            "vorher": len(jobs),
            "nachher": len(eindeutige_jobs),
            "entfernt": statistik.gesamt,
            "arten": statistik.als_dict(),
            "sicherung": backup_datei,
        }
        marker.write_text(json.dumps(marker_daten, indent=4, ensure_ascii=False), encoding="utf-8")
        return {"ausgefuehrt": True, **marker_daten}

    def _atomar_schreiben(self, daten: list[dict]) -> None:
        with self._cache_lock:
            temporaer = self.datei.with_suffix(f"{self.datei.suffix}.tmp")
            with open(temporaer, "w", encoding="utf-8") as f:
                json.dump(daten, f, indent=4, ensure_ascii=False)
            temporaer.replace(self.datei)
            self._cache_stamp = None


class JsonSearchTermRepository:
    def __init__(self, datei: Path):
        self.datei = datei

    def laden(self) -> list[SearchTerm]:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        if not self.datei.exists():
            self.speichern([])
            return []
        try:
            with open(self.datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            if not isinstance(daten, list):
                return []
            return [SearchTerm.from_dict(eintrag) for eintrag in daten if isinstance(eintrag, dict)]
        except Exception:
            return []

    def speichern(self, suchbegriffe: Iterable[SearchTerm]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        with open(self.datei, "w", encoding="utf-8") as f:
            json.dump([begriff.to_dict() for begriff in suchbegriffe], f, indent=4, ensure_ascii=False)


class JsonSearchTermSetRepository:
    def __init__(self, datei: Path):
        self.datei = datei

    def laden(self) -> list[SearchTermSet]:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        if not self.datei.exists():
            self.speichern([])
            return []
        try:
            with open(self.datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            if not isinstance(daten, list):
                return []
            return [
                SearchTermSet.from_dict(eintrag)
                for eintrag in daten
                if isinstance(eintrag, dict) and str(eintrag.get("name", "")).strip()
            ]
        except Exception:
            logging.exception("Suchbegriff-Sets konnten nicht gelesen werden.")
            return []

    def speichern(self, suchbegriff_sets: Iterable[SearchTermSet]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        temporaer = self.datei.with_suffix(f"{self.datei.suffix}.tmp")
        with open(temporaer, "w", encoding="utf-8") as f:
            json.dump(
                [suchbegriff_set.to_dict() for suchbegriff_set in suchbegriff_sets],
                f,
                indent=4,
                ensure_ascii=False,
            )
        temporaer.replace(self.datei)


class JsonUserProfileRepository:
    def __init__(self, datei: Path):
        self.datei = datei

    def laden(self) -> list[UserProfile]:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        if not self.datei.exists():
            self.speichern([])
            return []
        try:
            with open(self.datei, "r", encoding="utf-8") as f:
                daten = json.load(f)
            if not isinstance(daten, list):
                return []
            return [
                UserProfile.from_dict(eintrag)
                for eintrag in daten
                if isinstance(eintrag, dict) and str(eintrag.get("name", "")).strip()
            ]
        except Exception:
            logging.exception("Nutzerprofile konnten nicht gelesen werden.")
            return []

    def speichern(self, nutzerprofile: Iterable[UserProfile]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        temporaer = self.datei.with_suffix(f"{self.datei.suffix}.tmp")
        with open(temporaer, "w", encoding="utf-8") as f:
            json.dump(
                [profil.to_dict() for profil in nutzerprofile],
                f,
                indent=4,
                ensure_ascii=False,
            )
        temporaer.replace(self.datei)
