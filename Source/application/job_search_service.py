import logging
import re
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta

from config import GOOD_MATCH_SCORE_THRESHOLD, MAX_SEARCH_RADIUS_KM, MIN_SEARCH_RADIUS_KM
from deduplication import JobDeduplizierer, jobs_deduplizieren, jobs_zusammenfuehren
from models import (
    JOB_STATUS_SELECTABLE_VALUES,
    USER_PROFILE_FIELDS,
    Job,
    SearchTerm,
    SearchTermSet,
    SearchTermSetEntry,
    SearchRequest,
    UserProfile,
    job_schluessel,
    normalisiere_eigene_bewertung,
    normalisiere_jobtext,
    normalisiere_status,
    normalisiere_statusverlauf,
    status_fuer_anzeige,
    statusverlauf_sortierschluessel,
)
from pipeline import SearchPipeline
from analysis import AiJobSearchPlanner
from analysis.job_search_planner import normalisiere_suchbegriff, suchbegriffe_sind_aehnlich
from cancellation import OperationCancelled, abbruch_pruefen
from repositories import (
    JsonJobRepository,
    JsonSearchTermRepository,
    JsonSearchTermSetRepository,
    JsonSettingsRepository,
    JsonUserProfileRepository,
)


class JobSearchService:
    def __init__(
        self,
        pipeline: SearchPipeline,
        job_repository: JsonJobRepository,
        settings_repository: JsonSettingsRepository,
        ai_search_planner: AiJobSearchPlanner | None = None,
        search_term_repository: JsonSearchTermRepository | None = None,
        search_term_set_repository: JsonSearchTermSetRepository | None = None,
        user_profile_repository: JsonUserProfileRepository | None = None,
    ):
        self.pipeline = pipeline
        self.job_repository = job_repository
        self.settings_repository = settings_repository
        self.letzte_meldung = ""
        self.letzter_entfernter_job: Job | None = None
        self.ai_search_planner = ai_search_planner or AiJobSearchPlanner()
        self.search_term_repository = search_term_repository
        self.search_term_set_repository = search_term_set_repository
        self.user_profile_repository = user_profile_repository

    def settings_laden(self) -> dict[str, str]:
        return self.settings_repository.laden()

    def settings_speichern(self, settings: dict[str, str]) -> None:
        self.settings_repository.speichern(settings)
        logging.info("Einstellungen gespeichert")

    def nutzerprofile_initialisieren(self, legacy_profil=None, auswahl: str = "") -> str:
        profile = self.nutzerprofile_laden()
        legacy_daten = self._nutzerprofil_daten(legacy_profil)
        if not profile and any(legacy_daten.values()) and self.user_profile_repository is not None:
            standardprofil = UserProfile(
                name="Standardprofil",
                **legacy_daten,
                aktualisiert_am=datetime.now().isoformat(timespec="seconds"),
            )
            self.user_profile_repository.speichern([standardprofil])
            profile = [standardprofil]
            logging.info("Bestehendes Nutzerprofil als Standardprofil migriert.")

        ausgewaehlt = self.nutzerprofil_laden(auswahl)
        if ausgewaehlt is not None:
            return ausgewaehlt.name
        return profile[0].name if profile else ""

    def nutzerprofile_laden(self) -> list[UserProfile]:
        if self.user_profile_repository is None:
            return []
        return sorted(self.user_profile_repository.laden(), key=lambda profil: profil.name.casefold())

    def nutzerprofil_laden(self, name: str) -> UserProfile | None:
        profil_name = self._nutzerprofil_name(name)
        return next(
            (
                profil
                for profil in self.nutzerprofile_laden()
                if profil.name.casefold() == profil_name.casefold()
            ),
            None,
        )

    def nutzerprofil_existiert(self, name: str) -> bool:
        return self.nutzerprofil_laden(name) is not None

    def nutzerprofil_speichern(
        self,
        name: str,
        daten,
        ueberschreiben: bool = False,
    ) -> UserProfile:
        if self.user_profile_repository is None:
            self.letzte_meldung = "Nutzerprofile sind nicht verfuegbar."
            raise ValueError(self.letzte_meldung)
        profil_name = self._nutzerprofil_name(name)
        if not profil_name:
            self.letzte_meldung = "Bitte einen Namen fuer das Nutzerprofil eingeben."
            raise ValueError(self.letzte_meldung)
        profil_daten = self._nutzerprofil_daten(daten)
        if not any(profil_daten.values()):
            self.letzte_meldung = "Bitte mindestens ein Profilfeld ausfuellen."
            raise ValueError(self.letzte_meldung)

        profile = self.user_profile_repository.laden()
        vorhandener_index = next(
            (
                index
                for index, profil in enumerate(profile)
                if profil.name.casefold() == profil_name.casefold()
            ),
            None,
        )
        if vorhandener_index is not None and not ueberschreiben:
            self.letzte_meldung = f"Das Nutzerprofil '{profile[vorhandener_index].name}' existiert bereits."
            raise ValueError(self.letzte_meldung)

        profil = UserProfile(
            name=profil_name,
            **profil_daten,
            aktualisiert_am=datetime.now().isoformat(timespec="seconds"),
        )
        if vorhandener_index is None:
            profile.append(profil)
        else:
            profile[vorhandener_index] = profil
        self.user_profile_repository.speichern(profile)
        self.letzte_meldung = f"Nutzerprofil '{profil.name}' gespeichert."
        return profil

    def nutzerprofil_loeschen(self, name: str) -> bool:
        if self.user_profile_repository is None:
            self.letzte_meldung = "Nutzerprofile sind nicht verfuegbar."
            return False
        profil_name = self._nutzerprofil_name(name)
        profile = self.user_profile_repository.laden()
        verbleibend = [profil for profil in profile if profil.name.casefold() != profil_name.casefold()]
        if len(verbleibend) == len(profile):
            self.letzte_meldung = "Das ausgewaehlte Nutzerprofil wurde nicht gefunden."
            return False
        self.user_profile_repository.speichern(verbleibend)
        self.letzte_meldung = f"Nutzerprofil '{profil_name}' geloescht."
        return True

    def _nutzerprofil_daten(self, daten) -> dict[str, str]:
        if isinstance(daten, UserProfile):
            daten = daten.daten()
        if not isinstance(daten, dict):
            daten = {}
        return {feld: str(daten.get(feld, "") or "").strip() for feld in USER_PROFILE_FIELDS}

    def _nutzerprofil_name(self, name: str) -> str:
        return " ".join(str(name or "").strip().split())[:80]

    def jobs_laden(self) -> list[Job]:
        return self.job_repository.laden()

    def jobs_speichern(self, jobs: list[Job]) -> None:
        self.job_repository.speichern(jobs)
        logging.info("Jobs gespeichert: %s", len(jobs))

    def search_jobs(self, suchanfrage: SearchRequest, abbruch_event=None) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        suchanfrage = suchanfrage.bereinigt()
        meldung = self._validiere_suchanfrage(suchanfrage)
        if meldung:
            self.letzte_meldung = meldung
            return []

        logging.info(
            "Suche gestartet: %s | %s | %s km",
            suchanfrage.suchbegriff,
            suchanfrage.ort,
            suchanfrage.umkreis,
        )
        analyse_snapshot = self._analysezustand_snapshot()
        meldung_snapshot = self.letzte_meldung
        try:
            jobs = self.pipeline.ausfuehren(suchanfrage, abbruch_event=abbruch_event)
            abbruch_pruefen(abbruch_event)
            jobs = self._mit_gespeicherten_daten_abgleichen(jobs)
            if jobs:
                self.letzte_meldung = f"{len(jobs)} Jobs gefunden"
            elif self.pipeline.letzte_meldungen:
                self.letzte_meldung = " ".join(self.pipeline.letzte_meldungen)
            else:
                self.letzte_meldung = (
                    "Fuer diese Kombination wurden keine Stellen gefunden. "
                    "Bitte Suchbegriff allgemeiner formulieren oder Ort/Umkreis anpassen."
                )

            abbruch_pruefen(abbruch_event)
            self.jobs_speichern(self._vereinige_jobs(self.job_repository.laden(), jobs))
            return jobs
        except OperationCancelled:
            self.letzte_meldung = meldung_snapshot
            self._analysezustand_wiederherstellen(analyse_snapshot)
            raise

    def jobs_suchen(self, suchanfrage: SearchRequest, abbruch_event=None) -> list[Job]:
        return self.search_jobs(suchanfrage, abbruch_event=abbruch_event)

    def suchbegriffe_laden(self, geloeschte_einschliessen: bool = False) -> list[SearchTerm]:
        if self.search_term_repository is None:
            return []
        begriffe = self.search_term_repository.laden()
        if geloeschte_einschliessen:
            return begriffe
        return [begriff for begriff in begriffe if begriff.status != "geloescht"]

    def aktive_suchbegriffe(self) -> list[str]:
        return [begriff.bezeichnung for begriff in self.suchbegriffe_laden() if begriff.status == "aktiv"]

    def suchbegriff_sets_laden(self) -> list[SearchTermSet]:
        if self.search_term_set_repository is None:
            return []
        return sorted(self.search_term_set_repository.laden(), key=lambda eintrag: eintrag.name.casefold())

    def suchbegriff_set_existiert(self, name: str) -> bool:
        schluessel = self._suchbegriff_set_name(name).casefold()
        return bool(schluessel) and any(
            eintrag.name.casefold() == schluessel for eintrag in self.suchbegriff_sets_laden()
        )

    def suchbegriff_set_speichern(self, name: str, ueberschreiben: bool = False) -> SearchTermSet | None:
        if self.search_term_set_repository is None:
            self.letzte_meldung = "Suchbegriff-Sets sind nicht verfuegbar."
            return None
        set_name = self._suchbegriff_set_name(name)
        if not set_name:
            self.letzte_meldung = "Bitte einen Namen fuer das Suchbegriff-Set eingeben."
            return None

        begriffe = self.suchbegriffe_laden()
        if not begriffe:
            self.letzte_meldung = "Es sind keine Suchbegriffe zum Speichern vorhanden."
            return None

        suchbegriff_sets = self.search_term_set_repository.laden()
        vorhandener_index = next(
            (
                index
                for index, eintrag in enumerate(suchbegriff_sets)
                if eintrag.name.casefold() == set_name.casefold()
            ),
            None,
        )
        if vorhandener_index is not None and not ueberschreiben:
            self.letzte_meldung = f"Das Suchbegriff-Set '{suchbegriff_sets[vorhandener_index].name}' existiert bereits."
            return None

        eintrag = SearchTermSet(
            name=set_name,
            suchbegriffe=[
                SearchTermSetEntry(
                    bezeichnung=begriff.bezeichnung,
                    status=begriff.status,
                    quelle=begriff.quelle,
                )
                for begriff in begriffe
            ],
            aktualisiert_am=datetime.now().isoformat(timespec="seconds"),
        )
        if vorhandener_index is None:
            suchbegriff_sets.append(eintrag)
        else:
            suchbegriff_sets[vorhandener_index] = eintrag
        self.search_term_set_repository.speichern(suchbegriff_sets)
        self.letzte_meldung = f"Suchbegriff-Set '{set_name}' gespeichert."
        return eintrag

    def suchbegriff_set_laden(self, name: str) -> SearchTermSet | None:
        if self.search_term_repository is None or self.search_term_set_repository is None:
            self.letzte_meldung = "Suchbegriff-Sets sind nicht verfuegbar."
            return None
        set_name = self._suchbegriff_set_name(name)
        eintrag = next(
            (
                kandidat
                for kandidat in self.search_term_set_repository.laden()
                if kandidat.name.casefold() == set_name.casefold()
            ),
            None,
        )
        if eintrag is None:
            self.letzte_meldung = "Das ausgewaehlte Suchbegriff-Set wurde nicht gefunden."
            return None

        vorhandene = {
            normalisiere_suchbegriff(begriff.bezeichnung).casefold(): begriff
            for begriff in self.search_term_repository.laden()
        }
        neue_begriffe = []
        for set_begriff in eintrag.suchbegriffe:
            schluessel = normalisiere_suchbegriff(set_begriff.bezeichnung).casefold()
            begriff = deepcopy(vorhandene.get(schluessel))
            if begriff is None:
                begriff = SearchTerm(
                    id=uuid.uuid4().hex,
                    bezeichnung=set_begriff.bezeichnung,
                    quelle=set_begriff.quelle,
                )
            begriff.bezeichnung = set_begriff.bezeichnung
            begriff.status = set_begriff.status
            begriff.quelle = set_begriff.quelle
            neue_begriffe.append(begriff)
        self.search_term_repository.speichern(neue_begriffe)
        self._suchbegriff_statistiken_aktualisieren()
        self.letzte_meldung = (
            f"Suchbegriff-Set '{eintrag.name}' mit {len(neue_begriffe)} Begriffen geladen."
        )
        return eintrag

    def suchbegriff_set_loeschen(self, name: str) -> bool:
        if self.search_term_set_repository is None:
            self.letzte_meldung = "Suchbegriff-Sets sind nicht verfuegbar."
            return False
        set_name = self._suchbegriff_set_name(name)
        suchbegriff_sets = self.search_term_set_repository.laden()
        verbleibend = [
            eintrag for eintrag in suchbegriff_sets if eintrag.name.casefold() != set_name.casefold()
        ]
        if len(verbleibend) == len(suchbegriff_sets):
            self.letzte_meldung = "Das ausgewaehlte Suchbegriff-Set wurde nicht gefunden."
            return False
        self.search_term_set_repository.speichern(verbleibend)
        self.letzte_meldung = f"Suchbegriff-Set '{set_name}' geloescht."
        return True

    def suchbegriff_hinzufuegen(self, bezeichnung: str, quelle: str = "manuell") -> SearchTerm | None:
        if self.search_term_repository is None:
            return None
        name = normalisiere_suchbegriff(bezeichnung)
        if not name:
            self.letzte_meldung = "Bitte eine Berufs- oder Taetigkeitsbezeichnung eingeben."
            return None

        begriffe = self.search_term_repository.laden()
        for begriff in begriffe:
            if suchbegriffe_sind_aehnlich(name, begriff.bezeichnung):
                if begriff.status == "geloescht":
                    begriff.status = "aktiv"
                    begriff.bezeichnung = name
                    self.search_term_repository.speichern(begriffe)
                    self.letzte_meldung = f"Suchbegriff '{name}' wieder aktiviert."
                    return begriff
                self.letzte_meldung = f"Ein nahezu identischer Suchbegriff ist bereits gespeichert: {begriff.bezeichnung}"
                return None

        suchbegriff = SearchTerm(id=uuid.uuid4().hex, bezeichnung=name, quelle="KI" if quelle == "KI" else "manuell")
        begriffe.append(suchbegriff)
        self.search_term_repository.speichern(begriffe)
        self.letzte_meldung = f"Suchbegriff '{name}' gespeichert."
        return suchbegriff

    def suchbegriff_bearbeiten(self, suchbegriff_id: str, bezeichnung: str) -> SearchTerm | None:
        if self.search_term_repository is None:
            return None
        name = normalisiere_suchbegriff(bezeichnung)
        if not name:
            self.letzte_meldung = "Ein Suchbegriff darf nicht leer sein."
            return None
        begriffe = self.search_term_repository.laden()
        for anderer in begriffe:
            if anderer.id != suchbegriff_id and anderer.status != "geloescht" and suchbegriffe_sind_aehnlich(name, anderer.bezeichnung):
                self.letzte_meldung = f"Ein nahezu identischer Suchbegriff ist bereits gespeichert: {anderer.bezeichnung}"
                return None
        for begriff in begriffe:
            if begriff.id == suchbegriff_id and begriff.status != "geloescht":
                alte_bezeichnung = begriff.bezeichnung
                begriff.bezeichnung = name
                self.search_term_repository.speichern(begriffe)
                self._job_suchbegriff_umbenennen(alte_bezeichnung, name)
                self._suchbegriff_statistiken_aktualisieren()
                self.letzte_meldung = f"Suchbegriff in '{name}' geaendert."
                return begriff
        self.letzte_meldung = "Suchbegriff wurde nicht gefunden."
        return None

    def suchbegriff_status_setzen(self, suchbegriff_id: str, status: str) -> SearchTerm | None:
        if self.search_term_repository is None or status not in ("aktiv", "pausiert", "geloescht"):
            return None
        begriffe = self.search_term_repository.laden()
        for begriff in begriffe:
            if begriff.id == suchbegriff_id:
                begriff.status = status
                self.search_term_repository.speichern(begriffe)
                self.letzte_meldung = f"Suchbegriff '{begriff.bezeichnung}' ist jetzt {status}."
                return begriff
        self.letzte_meldung = "Suchbegriff wurde nicht gefunden."
        return None

    def suchbegriff_behalten_hinweis(self, suchbegriff: SearchTerm) -> str:
        if suchbegriff.gute_treffer_anzahl >= 2:
            return "Mehrfach gute Treffer - Behalten lohnt sich."
        if suchbegriff.bester_score >= GOOD_MATCH_SCORE_THRESHOLD:
            return "Mindestens ein guter Treffer."
        return ""

    def ki_suchbegriffe_generieren(self, suchanfrage: SearchRequest, abbruch_event=None) -> list[str]:
        vorhandene = [begriff.bezeichnung for begriff in self.suchbegriffe_laden()]
        return self.ai_search_planner.suchbegriffe_generieren(
            suchanfrage.bereinigt(),
            vorhandene,
            abbruch_event=abbruch_event,
        )

    def ki_jobsuche_ausfuehren(
        self,
        suchbegriffe: list[str],
        basisanfrage: SearchRequest,
        abbruch_event=None,
    ) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        basisanfrage = basisanfrage.bereinigt()
        begriffe = self._suchbegriffe_bereinigen(suchbegriffe)
        if not begriffe:
            self.letzte_meldung = "Keine gueltigen KI-Suchbegriffe vorhanden."
            return []

        meldung = self._validiere_suchanfrage(
            SearchRequest(begriffe[0], basisanfrage.ort, basisanfrage.umkreis, basisanfrage.provider, basisanfrage.ki_kriterien)
        )
        if meldung:
            self.letzte_meldung = meldung
            return []

        anfragen = [
            SearchRequest(begriff, basisanfrage.ort, basisanfrage.umkreis, basisanfrage.provider, basisanfrage.ki_kriterien)
            for begriff in begriffe
        ]
        logging.info("KI-Jobsuche gestartet: %s Suchbegriffe.", len(anfragen))
        analyse_snapshot = self._analysezustand_snapshot()
        meldung_snapshot = self.letzte_meldung
        try:
            jobs = self.pipeline.ausfuehren_mehrere(anfragen, abbruch_event=abbruch_event)
            abbruch_pruefen(abbruch_event)
            jobs = self._mit_gespeicherten_daten_abgleichen(jobs)
            if jobs:
                self.letzte_meldung = f"{len(jobs)} Jobs mit KI-Jobsuche gefunden ({len(anfragen)} Suchbegriffe)"
            elif self.pipeline.letzte_meldungen:
                self.letzte_meldung = " ".join(self.pipeline.letzte_meldungen)
            else:
                self.letzte_meldung = "KI-Jobsuche abgeschlossen, aber keine passenden Stellen gefunden."
            abbruch_pruefen(abbruch_event)
            self.jobs_speichern(self._vereinige_jobs(self.job_repository.laden(), jobs))
            self._suchbegriffe_als_gesucht_markieren(begriffe)
            self._suchbegriff_statistiken_aktualisieren()
            return jobs
        except OperationCancelled:
            self.letzte_meldung = meldung_snapshot
            self._analysezustand_wiederherstellen(analyse_snapshot)
            raise

    def ki_analyse_ausfuehren(self, jobs: list[Job], suchanfrage: SearchRequest, abbruch_event=None, fortschritt=None) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        if not jobs:
            self.pipeline.ki_analysieren([], suchanfrage, abbruch_event=abbruch_event)
            self.letzte_meldung = "Keine Suchergebnisse fuer die KI-Auswertung vorhanden."
            return jobs

        analyse_snapshot = self._analysezustand_snapshot()
        meldung_snapshot = self.letzte_meldung
        job_snapshots = [deepcopy(job) for job in jobs]
        try:
            for job in jobs:
                job.ki_daten_loeschen()

            analysierte_jobs = self.pipeline.ki_analysieren(
                jobs,
                suchanfrage,
                abbruch_event=abbruch_event,
                fortschritt=fortschritt,
            )
            abbruch_pruefen(abbruch_event)
            self.jobs_speichern(self._vereinige_jobs(self.job_repository.laden(), analysierte_jobs))
            self._suchbegriff_statistiken_aktualisieren()
            self.letzte_meldung = f"{len(jobs)} Jobs gefunden"
            return analysierte_jobs
        except Exception:
            for job, snapshot in zip(jobs, job_snapshots):
                job.ki_daten_aus(snapshot)
            self.letzte_meldung = meldung_snapshot
            self._analysezustand_wiederherstellen(analyse_snapshot)
            raise

    def ki_analyse_abbrechen(self) -> None:
        abbrechen = getattr(self.pipeline.ai_analysis, "abbrechen", None)
        if callable(abbrechen):
            abbrechen()

    def ki_analysezustand_sichern(self) -> dict[str, object]:
        return self._analysezustand_snapshot()

    def ki_analysezustand_wiederherstellen(self, snapshot: dict[str, object] | None) -> None:
        if snapshot is not None:
            self._analysezustand_wiederherstellen(snapshot)

    def ki_suchplanung_abbrechen(self) -> None:
        abbrechen = getattr(self.ai_search_planner, "abbrechen", None)
        if callable(abbrechen):
            abbrechen()

    def _analysezustand_snapshot(self) -> dict[str, object]:
        analyse = self.pipeline.ai_analysis
        return {
            "letzte_zusammenfassung": analyse.letzte_zusammenfassung,
            "letzte_meldung": analyse.letzte_meldung,
            "letzter_status": analyse.letzter_status,
            "echte_bewertungen": analyse.echte_bewertungen,
            "technische_bewertungen": analyse.technische_bewertungen,
        }

    def _analysezustand_wiederherstellen(self, snapshot: dict[str, object]) -> None:
        analyse = self.pipeline.ai_analysis
        analyse.letzte_zusammenfassung = str(snapshot.get("letzte_zusammenfassung", "") or "")
        analyse.letzte_meldung = str(snapshot.get("letzte_meldung", "") or "")
        analyse.letzter_status = str(snapshot.get("letzter_status", "nicht_gestartet") or "nicht_gestartet")
        analyse.echte_bewertungen = int(snapshot.get("echte_bewertungen", 0) or 0)
        analyse.technische_bewertungen = int(snapshot.get("technische_bewertungen", 0) or 0)

    def ki_analyse_status(self) -> str:
        return self.pipeline.ki_analyse_status()

    def ki_analyse_anzahlen(self) -> tuple[int, int]:
        return self.pipeline.ki_analyse_anzahlen()

    def gespeicherte_jobs_laden(
        self,
        suchtext: str = "",
        status: str = "Alle",
        quelle: str = "Alle",
        sortierung: str = "Letzte Statusaenderung",
        followup_filter: str = "Alle",
    ) -> list[Job]:
        suchtext = str(suchtext or "").lower().strip()
        status = str(status or "Alle").strip()
        quelle = str(quelle or "Alle").strip()
        jobs = [job for job in self.job_repository.laden() if job.ist_gespeichert()]

        if status != "Alle":
            jobs = [job for job in jobs if status_fuer_anzeige(job.status) == status]

        if quelle != "Alle":
            jobs = [job for job in jobs if quelle in job.quellen or job.quelle == quelle]

        jobs = self._filtere_followups(jobs, followup_filter)

        if suchtext:
            jobs = [
                job for job in jobs
                if suchtext in self._suchbarer_text(job)
            ]

        return self._sortiere_jobs(jobs, sortierung)

    def zuletzt_gespeicherte_jobs(self, limit: int = 5) -> list[Job]:
        jobs = [job for job in self.job_repository.laden() if job.ist_gespeichert()]
        sortierte_jobs = sorted(
            enumerate(jobs),
            key=lambda eintrag: (self._gespeichert_am_sortierschluessel(eintrag[1]), eintrag[0]),
            reverse=True,
        )
        return [job for _index, job in sortierte_jobs[:max(0, int(limit or 0))]]

    def bewerbungen_nach_status(
        self,
        suchtext: str = "",
        status: str = "Alle",
        quelle: str = "Alle",
        sortierung: str = "Letzte Statusaenderung",
        followup_filter: str = "Alle",
    ) -> dict[str, list[Job]]:
        jobs = self.gespeicherte_jobs_laden(suchtext, status, quelle, sortierung, followup_filter)
        gruppen = {statuswert: [] for statuswert in JOB_STATUS_SELECTABLE_VALUES}
        for job in jobs:
            gruppen.setdefault(status_fuer_anzeige(job.status), []).append(job)
        return gruppen

    def status_anzahlen(self) -> dict[str, int]:
        anzahl = {status: 0 for status in JOB_STATUS_SELECTABLE_VALUES}
        for job in self.job_repository.laden():
            if job.ist_gespeichert():
                status = status_fuer_anzeige(job.status)
                anzahl[status] = anzahl.get(status, 0) + 1
        return anzahl

    def quellen_werte(self) -> list[str]:
        quellen = set()
        for job in self.job_repository.laden():
            if job.ist_gespeichert():
                quellen.update(job.quellen or [job.quelle])
        quellen.discard("")
        return sorted(quellen)

    def job_speichern(self, job: Job) -> Job:
        job.favorit = True
        if job.status == "Neu":
            self._status_setzen(job, "Gespeichert", verlauf_schreiben=True)
        return self._job_aktualisieren(job)

    def favorit_umschalten(self, job: Job) -> Job:
        if job.favorit:
            return self.job_per_herz_entfernen(job)
        return self.job_speichern(job)

    def job_per_herz_entfernen(self, job: Job) -> Job:
        self.letzter_entfernter_job = deepcopy(job)
        return self._verwaltungsdaten_zuruecksetzen(job)

    def entfernung_rueckgaengig(self) -> Job | None:
        if not self.letzter_entfernter_job:
            return None
        wiederhergestellter_job = deepcopy(self.letzter_entfernter_job)
        self.letzter_entfernter_job = None
        return self._job_aktualisieren(wiederhergestellter_job)

    def job_entfernen(self, job: Job) -> Job:
        self.letzter_entfernter_job = deepcopy(job)
        return self._verwaltungsdaten_zuruecksetzen(job)

    def job_status_aendern(self, job: Job, status: str) -> Job:
        self._status_setzen(job, status, verlauf_schreiben=True)
        if job.status != "Neu":
            job.favorit = True
        elif not self._hat_detaildaten(job):
            job.favorit = False
        return self._job_aktualisieren(job)

    def job_notizen_speichern(self, job: Job, notizen: str, bewerbungsdatum: str) -> Job:
        job.notizen = str(notizen or "").strip()
        job.bewerbungsdatum = str(bewerbungsdatum or "").strip()
        if job.notizen or job.bewerbungsdatum:
            job.favorit = True
            if job.status == "Neu":
                job.status = "Gespeichert"
        return self._job_aktualisieren(job)

    def job_details_speichern(self, job: Job, details: dict[str, object]) -> Job:
        alter_schluessel = job_schluessel(job)
        job.titel = str(details.get("titel", job.titel) or "").strip()
        job.firma = str(details.get("firma", job.firma) or "").strip()
        job.ort = str(details.get("ort", job.ort) or "").strip()
        job.quelle = str(details.get("quelle", job.quelle) or "").strip()
        job.link = str(details.get("link", job.link) or "").strip()
        job.entfernung = str(details.get("entfernung", job.entfernung) or "").strip()
        neue_beschreibung = str(details.get("kurzbeschreibung", "") or "").strip()
        if neue_beschreibung and len(neue_beschreibung) >= len(str(job.kurzbeschreibung or "")):
            job.kurzbeschreibung = neue_beschreibung
        job.veroeffentlichungsdatum = str(
            details.get("veroeffentlichungsdatum", job.veroeffentlichungsdatum) or ""
        ).strip()
        neuer_status = normalisiere_status(details.get("status", job.status))
        job.notizen = str(details.get("notizen", job.notizen) or "").strip()
        job.bewerbungsdatum = str(details.get("bewerbungsdatum", job.bewerbungsdatum) or "").strip()
        job.ansprechpartner = str(details.get("ansprechpartner", job.ansprechpartner) or "").strip()
        job.email = str(details.get("email", job.email) or "").strip()
        job.telefon = str(details.get("telefon", job.telefon) or "").strip()
        job.gehaltsnotizen = str(details.get("gehaltsnotizen", job.gehaltsnotizen) or "").strip()
        job.gehalt_min = str(details.get("gehalt_min", job.gehalt_min) or "").strip()
        job.gehalt_max = str(details.get("gehalt_max", job.gehalt_max) or "").strip()
        job.kategorie = str(details.get("kategorie", job.kategorie) or "").strip()
        job.eigene_bewertung = normalisiere_eigene_bewertung(details.get("eigene_bewertung", job.eigene_bewertung))
        self._followup_felder_setzen(job, details)
        self._status_setzen(job, neuer_status, verlauf_schreiben=neuer_status != job.status)
        job.favorit = True
        if job.status == "Neu":
            self._status_setzen(job, "Gespeichert", verlauf_schreiben=True)
        return self._job_aktualisieren(job, alter_schluessel)

    def followup_speichern(
        self,
        job: Job,
        naechste_aktion: str,
        followup_datum: str,
        followup_uhrzeit: str = "",
        followup_erledigt: bool = False,
    ) -> Job:
        self._followup_felder_setzen(job, {
            "naechste_aktion": naechste_aktion,
            "followup_datum": followup_datum,
            "followup_uhrzeit": followup_uhrzeit,
            "followup_erledigt": followup_erledigt,
        })
        if job.naechste_aktion or job.followup_datum:
            job.favorit = True
            if job.status == "Neu":
                self._status_setzen(job, "Gespeichert", verlauf_schreiben=True)
        return self._job_aktualisieren(job)

    def followup_status(self, job: Job) -> str:
        if job.followup_erledigt:
            return "erledigt"
        if not str(job.followup_datum or "").strip():
            return "ohne"
        sortierdatum = self._datum_sortierschluessel(job.followup_datum).date()
        if sortierdatum == datetime.min.date():
            return "offen"
        heute = date.today()
        if sortierdatum < heute:
            return "ueberfaellig"
        if sortierdatum == heute:
            return "heute"
        return "offen"

    def followup_text(self, job: Job) -> str:
        teile = []
        if job.naechste_aktion:
            teile.append(f"Naechste Aktion: {job.naechste_aktion}")
        if job.followup_datum:
            zeit = f" {job.followup_uhrzeit}" if job.followup_uhrzeit else ""
            status = "erledigt" if job.followup_erledigt else self.followup_status(job)
            teile.append(f"Follow-up: {job.followup_datum}{zeit} ({status})")
        return " | ".join(teile)

    def statusverlauf_bearbeiten(
        self,
        job: Job,
        eintrag_id: str,
        datum: str,
        uhrzeit: str,
        status: str,
    ) -> Job:
        eintrag_id = str(eintrag_id or "").strip()
        if not eintrag_id:
            return job

        neuer_status = normalisiere_status(status)
        if neuer_status == "Neu":
            return job

        geaendert = False
        verlauf = []
        for eintrag in normalisiere_statusverlauf(job.statusverlauf):
            if eintrag.get("id") == eintrag_id:
                verlauf.append({
                    "id": eintrag_id,
                    "datum": str(datum or "").strip() or eintrag["datum"],
                    "uhrzeit": (str(uhrzeit or "").strip() or eintrag["uhrzeit"])[:5],
                    "status": neuer_status,
                })
                geaendert = True
            else:
                verlauf.append(eintrag)

        if not geaendert:
            return job

        job.statusverlauf = sorted(normalisiere_statusverlauf(verlauf), key=statusverlauf_sortierschluessel)
        self._status_aus_verlauf_aktualisieren(job)
        return self._job_aktualisieren(job)

    def statusverlauf_loeschen(self, job: Job, eintrag_id: str) -> Job:
        eintrag_id = str(eintrag_id or "").strip()
        job.statusverlauf = [
            eintrag
            for eintrag in normalisiere_statusverlauf(job.statusverlauf)
            if eintrag.get("id") != eintrag_id
        ]
        self._status_aus_verlauf_aktualisieren(job)
        return self._job_aktualisieren(job)

    def letzte_statusaenderung_text(self, job: Job) -> str:
        eintrag = self._letzter_statusverlaufseintrag(job)
        if not eintrag:
            return ""
        return f"{eintrag['datum']} {eintrag['uhrzeit']} - {eintrag['status']}"

    def status_werte(self) -> list[str]:
        return JOB_STATUS_SELECTABLE_VALUES.copy()

    def status_fuer_anzeige(self, status: str) -> str:
        return status_fuer_anzeige(status)

    def status_meldung(self) -> str:
        return self.letzte_meldung

    def diagnose_meldung(self) -> str:
        return self.pipeline.diagnose_meldung()

    def ki_zusammenfassung(self) -> str:
        return self.pipeline.ki_zusammenfassung()

    def provider_status(self, aktualisieren: bool = False) -> list[dict[str, object]]:
        return self.pipeline.provider_registry.provider_status(aktualisieren)

    def verfuegbare_provider_namen(self) -> list[str]:
        return [provider["name"] for provider in self.provider_status() if provider["aktiv"]]

    def _suchbegriffe_bereinigen(self, suchbegriffe: list[str]) -> list[str]:
        bereinigt = []
        gesehen = set()
        for begriff in suchbegriffe or []:
            text = str(begriff or "").strip()
            if not text:
                continue
            schluessel = text.lower()
            if schluessel in gesehen:
                continue
            bereinigt.append(text)
            gesehen.add(schluessel)
        return bereinigt

    def _suchbegriff_set_name(self, name: str) -> str:
        return " ".join(str(name or "").split())[:80]

    def _suchbegriffe_als_gesucht_markieren(self, verwendete_begriffe: list[str]) -> None:
        if self.search_term_repository is None:
            return
        zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M")
        verwendete = {normalisiere_suchbegriff(begriff).lower() for begriff in verwendete_begriffe}
        begriffe = self.search_term_repository.laden()
        for begriff in begriffe:
            if normalisiere_suchbegriff(begriff.bezeichnung).lower() in verwendete:
                begriff.letzte_suche = zeitpunkt
        self.search_term_repository.speichern(begriffe)

    def _suchbegriff_statistiken_aktualisieren(self) -> None:
        if self.search_term_repository is None:
            return
        jobs = self.job_repository.laden()
        begriffe = self.search_term_repository.laden()
        for begriff in begriffe:
            name = normalisiere_suchbegriff(begriff.bezeichnung).lower()
            eindeutige = {}
            for job in jobs:
                herkunft = {normalisiere_suchbegriff(wert).lower() for wert in job.ki_suchbegriffe}
                if name in herkunft:
                    eindeutige[job_schluessel(job)] = job
            treffer = list(eindeutige.values())
            bewertete = [
                job for job in treffer
                if job.hat_ki_daten() and job.ki_bewertungsart != "technisch"
            ]
            scores = [job.ki_match_score for job in bewertete]
            begriff.treffer_anzahl = len(treffer)
            begriff.ki_bewertet_anzahl = len(bewertete)
            begriff.gute_treffer_anzahl = sum(score >= GOOD_MATCH_SCORE_THRESHOLD for score in scores)
            begriff.durchschnitt_score = round(sum(scores) / len(scores)) if scores else 0
            begriff.bester_score = max(scores, default=0)
        self.search_term_repository.speichern(begriffe)

    def _job_suchbegriff_umbenennen(self, alte_bezeichnung: str, neue_bezeichnung: str) -> None:
        alt = normalisiere_suchbegriff(alte_bezeichnung).lower()
        jobs = self.job_repository.laden()
        geaendert = False
        for job in jobs:
            neue_herkunft = []
            for begriff in job.ki_suchbegriffe:
                if normalisiere_suchbegriff(begriff).lower() == alt:
                    neue_herkunft.append(neue_bezeichnung)
                    geaendert = True
                else:
                    neue_herkunft.append(begriff)
            job.ki_suchbegriffe = []
            job.suchbegriffe_hinzufuegen(neue_herkunft)
        if geaendert:
            self.job_repository.speichern(jobs)
    def _validiere_suchanfrage(self, suchanfrage: SearchRequest) -> str:
        if not suchanfrage.suchbegriff and not suchanfrage.ort:
            return "Bitte Suchbegriff oder Ort eingeben."

        try:
            umkreis = int(suchanfrage.umkreis)
        except ValueError:
            return "Bitte einen gueltigen Umkreis in Kilometern auswaehlen."

        if umkreis < MIN_SEARCH_RADIUS_KM or umkreis > MAX_SEARCH_RADIUS_KM:
            return f"Bitte einen Umkreis zwischen {MIN_SEARCH_RADIUS_KM} und {MAX_SEARCH_RADIUS_KM} km waehlen."

        return ""

    def _mit_gespeicherten_daten_abgleichen(self, jobs: list[Job]) -> list[Job]:
        bekannte_jobs = JobDeduplizierer()
        for gespeicherter_job in self.job_repository.laden():
            bekannte_jobs.hinzufuegen(gespeicherter_job)

        for job in jobs:
            vorhandener_job, _art = bekannte_jobs.finden(job)
            if vorhandener_job:
                jobs_zusammenfuehren(job, vorhandener_job)

        return jobs

    def _vereinige_jobs(self, vorhandene_jobs: list[Job], neue_jobs: list[Job]) -> list[Job]:
        zusammengefuehrt, _statistik = jobs_deduplizieren([*vorhandene_jobs, *neue_jobs])
        return zusammengefuehrt

    def _job_aktualisieren(self, job: Job, alter_schluessel=None) -> Job:
        if job.ist_gespeichert() and not job.gespeichert_am:
            job.gespeichert_am = datetime.now().isoformat(timespec="seconds")
        elif not job.ist_gespeichert():
            job.gespeichert_am = ""
        jobs = self.job_repository.laden()
        schluessel = job_schluessel(job)
        alter_schluessel = alter_schluessel or schluessel
        aktualisiert = False
        neue_jobs = []

        for vorhandener_job in jobs:
            if job_schluessel(vorhandener_job) in (schluessel, alter_schluessel):
                neue_jobs.append(job)
                aktualisiert = True
            else:
                neue_jobs.append(vorhandener_job)

        if not aktualisiert:
            neue_jobs.append(job)

        self.jobs_speichern(neue_jobs)
        return job

    def _suchbarer_text(self, job: Job) -> str:
        werte = [
            job.titel,
            job.firma,
            job.ort,
            job.quellen_text(),
            job.kurzbeschreibung,
            job.notizen,
            job.status,
            job.bewerbungsdatum,
            job.ansprechpartner,
            job.email,
            job.telefon,
            job.gehaltsnotizen,
            job.gehalt_min,
            job.gehalt_max,
            job.kategorie,
            str(job.eigene_bewertung),
            job.naechste_aktion,
            job.followup_datum,
            job.followup_uhrzeit,
        ]
        return " ".join(werte).lower()

    def _hat_detaildaten(self, job: Job) -> bool:
        return any([
            job.notizen.strip(),
            job.bewerbungsdatum.strip(),
            job.ansprechpartner.strip(),
            job.email.strip(),
            job.telefon.strip(),
            job.gehaltsnotizen.strip(),
            job.gehalt_min.strip(),
            job.gehalt_max.strip(),
            job.kategorie.strip(),
            job.eigene_bewertung > 0,
            job.naechste_aktion.strip(),
            job.followup_datum.strip(),
            job.followup_uhrzeit.strip(),
        ])

    def _verwaltungsdaten_zuruecksetzen(self, job: Job) -> Job:
        job.favorit = False
        job.beworben = False
        job.status = "Neu"
        job.gespeichert_am = ""
        job.statusverlauf = []
        job.notizen = ""
        job.bewerbungsdatum = ""
        job.ansprechpartner = ""
        job.email = ""
        job.telefon = ""
        job.gehaltsnotizen = ""
        job.eigene_bewertung = 0
        job.naechste_aktion = ""
        job.followup_datum = ""
        job.followup_uhrzeit = ""
        job.followup_erledigt = False
        return self._job_aktualisieren(job)

    def _vollstaendigere_beschreibung_behalten(self, ziel: Job, vorhandener_job: Job) -> None:
        if len(str(vorhandener_job.kurzbeschreibung or "")) > len(str(ziel.kurzbeschreibung or "")):
            ziel.kurzbeschreibung = vorhandener_job.kurzbeschreibung

    def _followup_felder_setzen(self, job: Job, details: dict[str, object]) -> None:
        job.naechste_aktion = str(details.get("naechste_aktion", job.naechste_aktion) or "").strip()
        job.followup_datum = str(details.get("followup_datum", job.followup_datum) or "").strip()
        job.followup_uhrzeit = str(details.get("followup_uhrzeit", job.followup_uhrzeit) or "").strip()[:5]
        job.followup_erledigt = bool(details.get("followup_erledigt", job.followup_erledigt))

    def _filtere_followups(self, jobs: list[Job], followup_filter: str) -> list[Job]:
        filterwert = str(followup_filter or "Alle").strip()
        if filterwert == "Alle":
            return jobs
        if filterwert == "Offene Follow-ups":
            return [job for job in jobs if self.followup_status(job) in ("offen", "heute", "ueberfaellig")]
        if filterwert == "Heute":
            return [job for job in jobs if self.followup_status(job) == "heute"]
        if filterwert == "Ueberfaellig":
            return [job for job in jobs if self.followup_status(job) == "ueberfaellig"]
        if filterwert == "Ohne Follow-up":
            return [job for job in jobs if self.followup_status(job) == "ohne"]
        return jobs

    def _status_setzen(self, job: Job, status: str, verlauf_schreiben: bool) -> None:
        neuer_status = normalisiere_status(status)
        if neuer_status == job.status and not (verlauf_schreiben and not job.statusverlauf and neuer_status != "Neu"):
            job.beworben = job.status == "Beworben"
            return

        job.status = neuer_status
        job.beworben = neuer_status == "Beworben"
        if verlauf_schreiben and neuer_status != "Neu":
            job.statusverlauf = normalisiere_statusverlauf(job.statusverlauf)
            job.statusverlauf.append(self._neuer_statusverlaufseintrag(neuer_status, job.statusverlauf))

    def _neuer_statusverlaufseintrag(self, status: str, vorhandener_verlauf=None) -> dict[str, str]:
        jetzt = datetime.now()
        if vorhandener_verlauf:
            letzter_zeitpunkt = max(
                statusverlauf_sortierschluessel(eintrag)[0]
                for eintrag in normalisiere_statusverlauf(vorhandener_verlauf)
            )
            if letzter_zeitpunkt != datetime.min and jetzt <= letzter_zeitpunkt:
                jetzt = letzter_zeitpunkt + timedelta(microseconds=1)
        return {
            "id": f"{jetzt.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
            "datum": jetzt.strftime("%Y-%m-%d"),
            "uhrzeit": jetzt.strftime("%H:%M"),
            "status": normalisiere_status(status),
        }

    def _letzter_statusverlaufseintrag(self, job: Job):
        verlauf = normalisiere_statusverlauf(job.statusverlauf)
        if not verlauf:
            return None
        return sorted(verlauf, key=statusverlauf_sortierschluessel)[-1]

    def _gespeichert_am_sortierschluessel(self, job: Job) -> datetime:
        text = str(job.gespeichert_am or "").strip()
        if text:
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                pass
        verlauf = normalisiere_statusverlauf(job.statusverlauf)
        if verlauf:
            return statusverlauf_sortierschluessel(verlauf[0])[0]
        return datetime.min

    def _status_aus_verlauf_aktualisieren(self, job: Job) -> None:
        letzter_eintrag = self._letzter_statusverlaufseintrag(job)
        if letzter_eintrag:
            job.status = letzter_eintrag["status"]
            job.favorit = True
        elif job.favorit or self._hat_detaildaten(job):
            job.status = "Gespeichert"
        else:
            job.status = "Neu"
        job.beworben = job.status == "Beworben"

    def _sortiere_jobs(self, jobs: list[Job], sortierung: str) -> list[Job]:
        sortierung = str(sortierung or "").strip()
        if sortierung == "Letzte Statusaenderung":
            return sorted(
                jobs,
                key=lambda job: self._letzte_statusaenderung_sortierschluessel(job),
                reverse=True,
            )
        if sortierung == "Veroeffentlichungsdatum":
            return sorted(
                jobs,
                key=lambda job: self._datum_sortierschluessel(job.veroeffentlichungsdatum),
                reverse=True,
            )
        if sortierung == "Eigene Bewertung":
            return sorted(jobs, key=lambda job: job.eigene_bewertung, reverse=True)
        if sortierung == "Naechstes Follow-up":
            return sorted(
                jobs,
                key=lambda job: (
                    self._followup_sortierdatum(job),
                    self._uhrzeit_sortierschluessel(job.followup_uhrzeit),
                ),
            )
        return sorted(
            jobs,
            key=lambda job: self._datum_sortierschluessel(job.bewerbungsdatum),
            reverse=True,
        )

    def suchergebnisse_sortieren(self, jobs: list[Job], sortierung: str) -> list[Job]:
        jobs = list(jobs or [])
        sortierung = str(sortierung or "Neueste zuerst").strip()
        if sortierung in ("Neueste zuerst", "Aelteste zuerst"):
            mit_datum = [job for job in jobs if self._datum_sortierschluessel(job.veroeffentlichungsdatum) != datetime.min]
            ohne_datum = [job for job in jobs if self._datum_sortierschluessel(job.veroeffentlichungsdatum) == datetime.min]
            mit_datum.sort(
                key=lambda job: self._datum_sortierschluessel(job.veroeffentlichungsdatum),
                reverse=sortierung == "Neueste zuerst",
            )
            ohne_datum.sort(key=lambda job: normalisiere_jobtext(job.titel, "titel"))
            return mit_datum + ohne_datum
        if sortierung in ("Stellenname A-Z", "Stellenname Z-A"):
            return self._suchergebnisse_nach_text_sortieren(
                jobs,
                "titel",
                sortierung == "Stellenname Z-A",
            )
        if sortierung in ("Unternehmen A-Z", "Unternehmen Z-A"):
            return self._suchergebnisse_nach_text_sortieren(
                jobs,
                "firma",
                sortierung == "Unternehmen Z-A",
            )
        if sortierung in ("Ort A-Z", "Ort Z-A"):
            return self._suchergebnisse_nach_text_sortieren(
                jobs,
                "ort",
                sortierung == "Ort Z-A",
            )
        if sortierung == "KI-Match: niedrig nach hoch":
            return sorted(jobs, key=lambda job: (job.ki_match_score, normalisiere_jobtext(job.titel, "titel")))
        nach_titel = sorted(jobs, key=lambda job: normalisiere_jobtext(job.titel, "titel"))
        return sorted(nach_titel, key=lambda job: job.ki_match_score, reverse=True)

    def _suchergebnisse_nach_text_sortieren(self, jobs: list[Job], feld: str, rueckwaerts: bool) -> list[Job]:
        mit_text = [job for job in jobs if str(getattr(job, feld, "") or "").strip()]
        ohne_text = [job for job in jobs if not str(getattr(job, feld, "") or "").strip()]
        mit_text.sort(
            key=lambda job: normalisiere_jobtext(getattr(job, feld, ""), feld),
            reverse=rueckwaerts,
        )
        ohne_text.sort(key=lambda job: normalisiere_jobtext(job.titel, "titel"))
        return mit_text + ohne_text

    def _letzte_statusaenderung_sortierschluessel(self, job: Job):
        eintrag = self._letzter_statusverlaufseintrag(job)
        if eintrag:
            return statusverlauf_sortierschluessel(eintrag)
        return (self._datum_sortierschluessel(job.bewerbungsdatum), "")

    def _uhrzeit_sortierschluessel(self, wert: str):
        text = str(wert or "").strip()
        for formatierung in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(text, formatierung).time()
            except ValueError:
                pass
        return datetime.max.time()

    def _followup_sortierdatum(self, job: Job):
        datum = self._datum_sortierschluessel(job.followup_datum)
        if datum == datetime.min:
            return datetime.max
        return datum

    def _datum_sortierschluessel(self, wert: str):
        text = str(wert or "").strip()
        if not text:
            return datetime.min
        try:
            zeitpunkt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if zeitpunkt.tzinfo is not None:
                zeitpunkt = zeitpunkt.astimezone().replace(tzinfo=None)
            return zeitpunkt
        except ValueError:
            pass
        for formatierung in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(text, formatierung)
            except ValueError:
                pass
        text_klein = text.casefold()
        jetzt = datetime.now()
        if text_klein in ("heute", "today"):
            return jetzt
        if text_klein in ("gestern", "yesterday"):
            return jetzt - timedelta(days=1)
        relativ = re.fullmatch(
            r"vor\s+(\d+)\+?\s+(stunde(?:n)?|tag(?:e|en)?|woche(?:n)?|monat(?:e|en)?)",
            text_klein,
        )
        if relativ:
            anzahl = int(relativ.group(1))
            einheit = relativ.group(2)
            if einheit.startswith("stunde"):
                return jetzt - timedelta(hours=anzahl)
            if einheit.startswith("woche"):
                return jetzt - timedelta(weeks=anzahl)
            if einheit.startswith("monat"):
                return jetzt - timedelta(days=anzahl * 30)
            return jetzt - timedelta(days=anzahl)
        relativ = re.fullmatch(r"(\d+)\+?\s+(hour|hours|day|days|week|weeks|month|months)\s+ago", text_klein)
        if relativ:
            anzahl = int(relativ.group(1))
            einheit = relativ.group(2)
            if einheit.startswith("hour"):
                return jetzt - timedelta(hours=anzahl)
            if einheit.startswith("week"):
                return jetzt - timedelta(weeks=anzahl)
            if einheit.startswith("month"):
                return jetzt - timedelta(days=anzahl * 30)
            return jetzt - timedelta(days=anzahl)
        return datetime.min
