import logging
import threading
import time
from copy import deepcopy
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from analysis import AiAnalysisStep
from cancellation import OperationCancelled, abbruch_pruefen
from config import ARBEITNOW_RATE_LIMIT_SECONDS, PROVIDER_429_MAX_WAIT_SECONDS, PROVIDER_429_RETRY_ATTEMPTS
from deduplication import ki_dubletten_zusammenfuehren, mehrdeutige_jobpaare
from filters import JobFilter
from models import Job, SearchRequest
from providers import ProviderError, ProviderRegistry


class SearchPipeline:
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        job_filter: JobFilter,
        ai_analysis: AiAnalysisStep,
    ):
        self.provider_registry = provider_registry
        self.job_filter = job_filter
        self.ai_analysis = ai_analysis
        self.letzte_meldungen = list(self.provider_registry.deaktivierte_meldungen)
        self.letzte_diagnose = self._leere_diagnose()
        self.letzte_diagnose["providerfehler"] = list(self.provider_registry.deaktivierte_meldungen)
        self._provider_letzter_start: dict[str, float] = {}
        self._provider_start_lock = threading.Lock()

    def ausfuehren(self, suchanfrage: SearchRequest, abbruch_event=None) -> list[Job]:
        return self._ausfuehren_einzeln(suchanfrage, ki_dedupe=True, abbruch_event=abbruch_event)

    def _ausfuehren_einzeln(
        self,
        suchanfrage: SearchRequest,
        ausgeschlossene_provider: set[str] | None = None,
        ki_dedupe: bool = False,
        abbruch_event=None,
    ) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        anfrage = suchanfrage.bereinigt()
        provider_gruppen = []
        self.letzte_meldungen = list(self.provider_registry.deaktivierte_meldungen)
        self.letzte_diagnose = self._leere_diagnose()
        for meldung in self.provider_registry.deaktivierte_meldungen:
            self.letzte_diagnose["providerfehler"].append(meldung)

        ausgeschlossen = ausgeschlossene_provider or set()
        provider_liste = [
            provider
            for provider in self.provider_registry.auswahl(anfrage.provider)
            if provider.name not in ausgeschlossen
        ]

        if not provider_liste:
            if ausgeschlossen:
                return []
            self.letzte_meldungen.append("Es ist keine aktive Jobquelle konfiguriert.")
            self.letzte_diagnose["providerfehler"].append("Es ist keine aktive Jobquelle konfiguriert.")
            return []

        self.letzte_diagnose["provider_reihenfolge"] = [
            provider.anzeigename
            for provider in provider_liste
        ]

        suchergebnisse = {}
        executor = ThreadPoolExecutor(max_workers=len(provider_liste))
        for provider in provider_liste:
            logging.info("Provider-Suche gestartet: %s", provider.name)

        future_zu_provider = {
            executor.submit(self._provider_suchen, provider, anfrage, abbruch_event): provider
            for provider in provider_liste
        }
        ausstehend = set(future_zu_provider)
        try:
            while ausstehend:
                abbruch_pruefen(abbruch_event)
                erledigt, ausstehend = wait(ausstehend, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in erledigt:
                    provider = future_zu_provider[future]
                    provider_name = provider.anzeigename
                    try:
                        suchergebnisse[provider.name] = future.result()
                    except OperationCancelled:
                        raise
                    except ProviderError as fehler:
                        logging.exception("Provider-Suche fehlgeschlagen: %s", provider.name)
                        self.letzte_meldungen.append(fehler.benutzer_meldung)
                        self.letzte_diagnose["treffer_vor_filter"][provider_name] = 0
                        self.letzte_diagnose["providerfehler"].append(f"{provider_name}: {fehler.benutzer_meldung}")
                        self.letzte_diagnose["providerfehler_details"].append({
                            "provider_name": provider.name,
                            "anzeigename": provider_name,
                            "status_code": fehler.status_code,
                            "meldung": fehler.benutzer_meldung,
                        })
                    except Exception:
                        logging.exception("Provider-Suche fehlgeschlagen: %s", provider.name)
                        self.letzte_meldungen.append("Eine Jobquelle konnte nicht abgefragt werden.")
                        self.letzte_diagnose["treffer_vor_filter"][provider_name] = 0
                        self.letzte_diagnose["providerfehler"].append(
                            f"{provider_name}: Eine Jobquelle konnte nicht abgefragt werden."
                        )
                        self.letzte_diagnose["providerfehler_details"].append({
                            "provider_name": provider.name,
                            "anzeigename": provider_name,
                            "status_code": None,
                            "meldung": "Eine Jobquelle konnte nicht abgefragt werden.",
                        })
        finally:
            abgebrochen = abbruch_event is not None and abbruch_event.is_set()
            if abgebrochen:
                for future in ausstehend:
                    future.cancel()
            executor.shutdown(wait=not abgebrochen, cancel_futures=abgebrochen)

        abbruch_pruefen(abbruch_event)
        for provider in provider_liste:
            provider_name = provider.anzeigename
            if provider.name not in suchergebnisse:
                continue

            jobs_des_providers = suchergebnisse[provider.name]
            try:
                if isinstance(jobs_des_providers, list):
                    self.letzte_diagnose["treffer_vor_filter"][provider_name] = len(jobs_des_providers)
                    provider_jobs_eintrag = (provider_name, jobs_des_providers)
                    provider_gruppen.append(provider_jobs_eintrag)
                else:
                    logging.error("Provider %s lieferte keinen Listenwert.", provider.name)
                    self.letzte_diagnose["treffer_vor_filter"][provider_name] = 0
            except Exception:
                logging.exception("Provider-Ergebnis konnte nicht verarbeitet werden: %s", provider.name)
                self.letzte_diagnose["treffer_vor_filter"][provider_name] = 0
                self.letzte_diagnose["providerfehler"].append(
                    f"{provider_name}: Provider-Ergebnis konnte nicht verarbeitet werden."
                )

        abbruch_pruefen(abbruch_event)
        gefilterte_jobs = self.job_filter.anwenden_gruppiert(provider_gruppen, anfrage)
        self._dedupe_statistik_uebernehmen(self.job_filter.letzte_deduplizierung)
        if ki_dedupe:
            gefilterte_jobs = self._ki_grenzfaelle_pruefen(gefilterte_jobs, abbruch_event=abbruch_event)
        abbruch_pruefen(abbruch_event)
        self.letzte_diagnose["dubletten_entfernt"] = (
            self.job_filter.letzte_dubletten + self.letzte_diagnose["dubletten_ki"]
        )
        self.letzte_diagnose["treffer_nach_deduplizierung"] = len(gefilterte_jobs)
        self.ai_analysis.letzte_zusammenfassung = ""
        self.ai_analysis.letzte_meldung = "Lokale KI-Auswertung noch nicht gestartet."
        self.ai_analysis.letzter_status = "nicht_gestartet"
        self.ai_analysis.echte_bewertungen = 0
        self.ai_analysis.technische_bewertungen = 0
        return gefilterte_jobs
    def ausfuehren_mehrere(self, suchanfragen: list[SearchRequest], abbruch_event=None) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        anfragen = [anfrage.bereinigt() for anfrage in suchanfragen if str(anfrage.suchbegriff or "").strip()]
        if not anfragen:
            self.letzte_meldungen = ["Keine KI-Suchbegriffe vorhanden."]
            self.letzte_diagnose = self._leere_diagnose()
            self.letzte_diagnose["providerfehler"].append("Keine KI-Suchbegriffe vorhanden.")
            return []

        alle_gruppen = []
        aggregiert = self._leere_diagnose()
        aggregiert["ki_suchbegriffe"] = [anfrage.suchbegriff for anfrage in anfragen]
        provider_reihenfolge = []
        providerfehler = []
        fehler_nach_provider = {}
        pausierte_provider: set[str] = set()
        meldungen = []
        interne_dubletten = 0

        for anfrage in anfragen:
            abbruch_pruefen(abbruch_event)
            jobs = self._ausfuehren_einzeln(
                anfrage,
                ausgeschlossene_provider=pausierte_provider,
                ki_dedupe=False,
                abbruch_event=abbruch_event,
            )
            diagnose = deepcopy(self.letzte_diagnose)
            for job in jobs:
                job.suchbegriffe_hinzufuegen([anfrage.suchbegriff])
            alle_gruppen.append((anfrage.suchbegriff, jobs))
            interne_dubletten += int(diagnose.get("dubletten_entfernt", 0) or 0)
            for feld in (
                "dubletten_url", "dubletten_inhalt", "dubletten_aehnlich", "dubletten_ki", "dubletten_unklar"
            ):
                aggregiert[feld] += int(diagnose.get(feld, 0) or 0)
            for provider_name in diagnose.get("provider_reihenfolge", []):
                if provider_name not in provider_reihenfolge:
                    provider_reihenfolge.append(provider_name)
            for name, anzahl in diagnose.get("treffer_vor_filter", {}).items():
                aggregiert["treffer_vor_filter"][name] = aggregiert["treffer_vor_filter"].get(name, 0) + int(anzahl or 0)
            for detail in diagnose.get("providerfehler_details", []):
                name = str(detail.get("provider_name", ""))
                if detail.get("status_code") in (403, 429) and name:
                    pausierte_provider.add(name)
                eintrag = fehler_nach_provider.setdefault(name or str(detail.get("anzeigename", "")), {
                    "anzeigename": detail.get("anzeigename", name),
                    "meldung": detail.get("meldung", "Providerfehler"),
                    "anzahl": 0,
                    "pausiert": False,
                })
                eintrag["anzahl"] += 1
                eintrag["pausiert"] = eintrag["pausiert"] or detail.get("status_code") in (403, 429)
            for meldung in self.letzte_meldungen:
                if meldung not in meldungen:
                    meldungen.append(meldung)

        abbruch_pruefen(abbruch_event)
        kombinierte_jobs = self.job_filter.anwenden_gruppiert(alle_gruppen, anfragen[0])
        finale_statistik = self.job_filter.letzte_deduplizierung
        aggregiert["dubletten_url"] += finale_statistik.url
        aggregiert["dubletten_inhalt"] += finale_statistik.inhalt
        aggregiert["dubletten_aehnlich"] += finale_statistik.aehnlich
        ki_dubletten_vorher = aggregiert["dubletten_ki"]
        kombinierte_jobs = self._ki_grenzfaelle_pruefen(
            kombinierte_jobs,
            aggregiert,
            abbruch_event=abbruch_event,
        )
        abbruch_pruefen(abbruch_event)
        finale_ki_dubletten = aggregiert["dubletten_ki"] - ki_dubletten_vorher
        providerfehler = [*self.provider_registry.deaktivierte_meldungen, *[
            (
                f"{detail['anzeigename']}: {detail['meldung']}"
                f" ({detail['anzahl']} Fehler; fuer den restlichen Suchlauf pausiert)"
                if detail["pausiert"]
                else f"{detail['anzeigename']}: {detail['meldung']} ({detail['anzahl']} Fehler)"
            )
            for detail in fehler_nach_provider.values()
        ]]
        aggregiert["provider_reihenfolge"] = provider_reihenfolge
        aggregiert["providerfehler"] = providerfehler
        aggregiert["dubletten_entfernt"] = (
            interne_dubletten + finale_statistik.gesamt + finale_ki_dubletten
        )
        aggregiert["treffer_nach_deduplizierung"] = len(kombinierte_jobs)
        self.letzte_diagnose = aggregiert
        self.letzte_meldungen = meldungen
        self.ai_analysis.letzte_zusammenfassung = ""
        self.ai_analysis.letzte_meldung = "Lokale KI-Auswertung noch nicht gestartet."
        self.ai_analysis.letzter_status = "nicht_gestartet"
        self.ai_analysis.echte_bewertungen = 0
        self.ai_analysis.technische_bewertungen = 0
        return kombinierte_jobs

    def _provider_suchen(self, provider, anfrage: SearchRequest, abbruch_event=None) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        self._provider_abstand_einhalten(provider.name, abbruch_event)
        versuch = 0
        while True:
            abbruch_pruefen(abbruch_event)
            try:
                jobs = provider.suchen(anfrage)
                abbruch_pruefen(abbruch_event)
                return jobs
            except ProviderError as fehler:
                if fehler.status_code != 429 or versuch >= PROVIDER_429_RETRY_ATTEMPTS:
                    raise
                wartezeit = fehler.retry_after_seconds if fehler.retry_after_seconds is not None else 2.0 ** (versuch + 1)
                wartezeit = min(max(0.5, wartezeit), PROVIDER_429_MAX_WAIT_SECONDS)
                logging.warning(
                    "Provider %s meldet HTTP 429; neuer Versuch in %.1f Sekunden.",
                    provider.name,
                    wartezeit,
                )
                if abbruch_event is not None:
                    if abbruch_event.wait(wartezeit):
                        raise OperationCancelled("Provider-Suche wurde abgebrochen.")
                else:
                    time.sleep(wartezeit)
                versuch += 1

    def _provider_abstand_einhalten(self, provider_name: str, abbruch_event=None) -> None:
        mindestabstand = ARBEITNOW_RATE_LIMIT_SECONDS if provider_name == "arbeitnow" else 0.0
        if mindestabstand <= 0:
            return
        with self._provider_start_lock:
            jetzt = time.monotonic()
            letzter_start = self._provider_letzter_start.get(provider_name, 0.0)
            wartezeit = mindestabstand - (jetzt - letzter_start)
            if wartezeit > 0:
                if abbruch_event is not None:
                    if abbruch_event.wait(wartezeit):
                        raise OperationCancelled("Provider-Suche wurde abgebrochen.")
                else:
                    time.sleep(wartezeit)
            self._provider_letzter_start[provider_name] = time.monotonic()

    def _dedupe_statistik_uebernehmen(self, statistik) -> None:
        self.letzte_diagnose["dubletten_url"] = statistik.url
        self.letzte_diagnose["dubletten_inhalt"] = statistik.inhalt
        self.letzte_diagnose["dubletten_aehnlich"] = statistik.aehnlich

    def _ki_grenzfaelle_pruefen(
        self,
        jobs: list[Job],
        diagnose: dict | None = None,
        abbruch_event=None,
    ) -> list[Job]:
        abbruch_pruefen(abbruch_event)
        ziel_diagnose = diagnose if diagnose is not None else self.letzte_diagnose
        paare = mehrdeutige_jobpaare(jobs)
        ziel_diagnose["dubletten_unklar"] += len(paare)
        if not paare:
            return jobs
        bestaetigte_paare = self.ai_analysis.dubletten_pruefen(paare, abbruch_event=abbruch_event)
        abbruch_pruefen(abbruch_event)
        ergebnis, entfernt = ki_dubletten_zusammenfuehren(jobs, bestaetigte_paare)
        ziel_diagnose["dubletten_ki"] += entfernt
        return ergebnis

    def ki_analysieren(self, jobs: list[Job], suchanfrage: SearchRequest, abbruch_event=None, fortschritt=None) -> list[Job]:
        return self.ai_analysis.analysieren(jobs, suchanfrage.bereinigt(), abbruch_event=abbruch_event, fortschritt=fortschritt)

    def diagnose_meldung(self) -> str:
        diagnose = self.letzte_diagnose
        teile = []

        if diagnose.get("ki_suchbegriffe"):
            teile.append("KI-Suchbegriffe: " + ", ".join(diagnose["ki_suchbegriffe"]))

        if diagnose["provider_reihenfolge"]:
            teile.append("Aktive Provider: " + ", ".join(diagnose["provider_reihenfolge"]))

        if diagnose["treffer_vor_filter"]:
            provider_teile = [
                f"{name}: {diagnose['treffer_vor_filter'][name]}"
                for name in diagnose["provider_reihenfolge"]
                if name in diagnose["treffer_vor_filter"]
            ]
            teile.append(", ".join(provider_teile))

        treffer_vor_dedupe = sum(diagnose["treffer_vor_filter"].values())
        teile.append(f"Rohresultate: {treffer_vor_dedupe}")
        teile.append(
            "Dubletten entfernt: "
            f"{diagnose['dubletten_entfernt']} "
            f"(URL {diagnose['dubletten_url']}, Inhalt {diagnose['dubletten_inhalt']}, "
            f"aehnlich {diagnose['dubletten_aehnlich']}, KI {diagnose['dubletten_ki']})"
        )
        if diagnose["dubletten_unklar"]:
            teile.append(f"KI-Grenzfaelle geprueft: {diagnose['dubletten_unklar']}")
        teile.append(f"Eindeutige Stellen: {diagnose['treffer_nach_deduplizierung']}")

        if diagnose["providerfehler"]:
            teile.append("Hinweise: " + " ".join(diagnose["providerfehler"]))

        ki_meldung = getattr(self.ai_analysis, "letzte_meldung", "")
        if ki_meldung:
            teile.append(ki_meldung)

        return " | ".join([teil for teil in teile if teil])

    def ki_zusammenfassung(self) -> str:
        return getattr(self.ai_analysis, "letzte_zusammenfassung", "")

    def ki_analyse_status(self) -> str:
        return getattr(self.ai_analysis, "letzter_status", "nicht_gestartet")

    def ki_analyse_anzahlen(self) -> tuple[int, int]:
        return (
            int(getattr(self.ai_analysis, "echte_bewertungen", 0) or 0),
            int(getattr(self.ai_analysis, "technische_bewertungen", 0) or 0),
        )

    def _leere_diagnose(self):
        return {
            "treffer_vor_filter": {},
            "dubletten_entfernt": 0,
            "treffer_nach_deduplizierung": 0,
            "providerfehler": [],
            "providerfehler_details": [],
            "provider_reihenfolge": [],
            "ki_suchbegriffe": [],
            "dubletten_url": 0,
            "dubletten_inhalt": 0,
            "dubletten_aehnlich": 0,
            "dubletten_ki": 0,
            "dubletten_unklar": 0,
        }
