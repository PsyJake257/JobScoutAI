from dataclasses import dataclass
from difflib import SequenceMatcher

from models import (
    JOB_STATUS_VALUES,
    Job,
    normalisierte_url,
    normalisiere_jobtext,
    normalisiere_statusverlauf,
    statusverlauf_sortierschluessel,
)


@dataclass
class DeduplizierungsStatistik:
    url: int = 0
    inhalt: int = 0
    aehnlich: int = 0
    ki: int = 0

    @property
    def gesamt(self) -> int:
        return self.url + self.inhalt + self.aehnlich + self.ki

    def als_dict(self) -> dict[str, int]:
        return {
            "url": self.url,
            "inhalt": self.inhalt,
            "aehnlich": self.aehnlich,
            "ki": self.ki,
            "gesamt": self.gesamt,
        }


def job_url_schluessel(job: Job) -> str:
    return normalisierte_url(job.link)


def job_inhaltsschluessel(job: Job) -> tuple[str, str, str] | None:
    schluessel = (
        normalisiere_jobtext(job.titel, "titel"),
        normalisiere_jobtext(job.firma, "firma"),
        normalisiere_jobtext(job.ort, "ort"),
    )
    return schluessel if all(schluessel) else None


def dubletten_art(erster: Job, zweiter: Job, aehnlich_erlaubt: bool = True) -> str:
    erster_link = job_url_schluessel(erster)
    zweiter_link = job_url_schluessel(zweiter)
    if erster_link and erster_link == zweiter_link:
        return "url"

    erster_inhalt = job_inhaltsschluessel(erster)
    zweiter_inhalt = job_inhaltsschluessel(zweiter)
    if erster_inhalt and erster_inhalt == zweiter_inhalt:
        return "inhalt"

    if not aehnlich_erlaubt or not erster_inhalt or not zweiter_inhalt:
        return ""

    titel = _aehnlichkeit(erster_inhalt[0], zweiter_inhalt[0])
    firma = _aehnlichkeit(erster_inhalt[1], zweiter_inhalt[1])
    ort_passt = _orte_sind_kompatibel(erster_inhalt[2], zweiter_inhalt[2])
    if not ort_passt:
        return ""

    beschreibung = _beschreibungsaehnlichkeit(erster, zweiter)
    if titel >= 0.94 and firma >= 0.92:
        return "aehnlich"
    if titel >= 0.90 and firma >= 0.97 and beschreibung >= 0.72:
        return "aehnlich"
    if titel >= 0.97 and firma >= 0.86 and beschreibung >= 0.82:
        return "aehnlich"
    return ""


def jobs_deduplizieren(jobs: list[Job]) -> tuple[list[Job], DeduplizierungsStatistik]:
    deduplizierer = JobDeduplizierer()
    for job in jobs:
        deduplizierer.hinzufuegen(job)
    return deduplizierer.jobs, deduplizierer.statistik


class JobDeduplizierer:
    def __init__(self):
        self.jobs: list[Job] = []
        self.statistik = DeduplizierungsStatistik()
        self._url_index: dict[str, int] = {}
        self._inhalt_index: dict[tuple[str, str, str], int] = {}
        self._firma_ort_index: dict[tuple[str, str], set[int]] = {}
        self._titel_ort_index: dict[tuple[str, str], set[int]] = {}
        self._schluessel_nach_position: dict[int, tuple[str, tuple[str, str, str] | None]] = {}

    def hinzufuegen(self, job: Job) -> tuple[Job, str]:
        position, art = self._finden(job)
        if position is not None:
            vorhandener_job = self.jobs[position]
            jobs_zusammenfuehren(vorhandener_job, job)
            setattr(self.statistik, art, getattr(self.statistik, art) + 1)
            self._registrieren(position, vorhandener_job)
            return vorhandener_job, art

        position = len(self.jobs)
        self.jobs.append(job)
        self._registrieren(position, job)
        return job, ""

    def finden(self, job: Job) -> tuple[Job | None, str]:
        position, art = self._finden(job)
        return (self.jobs[position], art) if position is not None else (None, "")

    def _finden(self, job: Job) -> tuple[int | None, str]:
        link = job_url_schluessel(job)
        if link and link in self._url_index:
            return self._url_index[link], "url"

        inhalt = job_inhaltsschluessel(job)
        if inhalt and inhalt in self._inhalt_index:
            return self._inhalt_index[inhalt], "inhalt"

        for position in self._kandidaten(inhalt):
            art = dubletten_art(self.jobs[position], job, aehnlich_erlaubt=True)
            if art:
                return position, art
        return None, ""

    def _kandidaten(self, inhalt: tuple[str, str, str] | None) -> list[int]:
        if not inhalt:
            return []
        titel, firma, ort = inhalt
        ort_kern = _ort_kern(ort)
        kandidaten = set(self._firma_ort_index.get((firma, ort_kern), set()))
        kandidaten.update(self._titel_ort_index.get((titel, ort_kern), set()))
        return sorted(kandidaten)

    def _registrieren(self, position: int, job: Job) -> None:
        alter_link, alter_inhalt = self._schluessel_nach_position.get(position, ("", None))
        if alter_link and self._url_index.get(alter_link) == position:
            self._url_index.pop(alter_link, None)
        if alter_inhalt:
            if self._inhalt_index.get(alter_inhalt) == position:
                self._inhalt_index.pop(alter_inhalt, None)
            alter_titel, alte_firma, alter_ort = alter_inhalt
            alter_ort_kern = _ort_kern(alter_ort)
            self._index_position_entfernen(self._firma_ort_index, (alte_firma, alter_ort_kern), position)
            self._index_position_entfernen(self._titel_ort_index, (alter_titel, alter_ort_kern), position)

        link = job_url_schluessel(job)
        if link:
            self._url_index[link] = position
        inhalt = job_inhaltsschluessel(job)
        self._schluessel_nach_position[position] = (link, inhalt)
        if not inhalt:
            return
        titel, firma, ort = inhalt
        self._inhalt_index[inhalt] = position
        ort_kern = _ort_kern(ort)
        self._firma_ort_index.setdefault((firma, ort_kern), set()).add(position)
        self._titel_ort_index.setdefault((titel, ort_kern), set()).add(position)

    def _index_position_entfernen(self, index: dict, schluessel, position: int) -> None:
        positionen = index.get(schluessel)
        if not positionen:
            return
        positionen.discard(position)
        if not positionen:
            index.pop(schluessel, None)


def mehrdeutige_jobpaare(jobs: list[Job], limit: int = 12) -> list[dict[str, object]]:
    paare = []
    gruppen: dict[str, list[int]] = {}
    for index, job in enumerate(jobs):
        inhalt = job_inhaltsschluessel(job)
        if not inhalt:
            continue
        ort_kern = _ort_kern(inhalt[2])
        for schluessel in (f"f:{inhalt[1]}|{ort_kern}", f"t:{inhalt[0]}|{ort_kern}"):
            gruppen.setdefault(schluessel, []).append(index)

    gesehen = set()
    for indexe in gruppen.values():
        for position, erster_index in enumerate(indexe):
            for zweiter_index in indexe[position + 1:]:
                paar = (min(erster_index, zweiter_index), max(erster_index, zweiter_index))
                if paar in gesehen:
                    continue
                gesehen.add(paar)
                erster = jobs[paar[0]]
                zweiter = jobs[paar[1]]
                if dubletten_art(erster, zweiter):
                    continue
                score = _mehrdeutigkeits_score(erster, zweiter)
                if score < 0.72:
                    continue
                paare.append({
                    "paar_id": len(paare),
                    "index_a": paar[0],
                    "index_b": paar[1],
                    "vorpruefung": round(score * 100),
                    "job_a": _job_promptdaten(erster),
                    "job_b": _job_promptdaten(zweiter),
                })
                if len(paare) >= max(0, limit):
                    return paare
    return paare


def ki_dubletten_zusammenfuehren(jobs: list[Job], paare: list[tuple[int, int]]) -> tuple[list[Job], int]:
    eltern = list(range(len(jobs)))

    def wurzel(index: int) -> int:
        while eltern[index] != index:
            eltern[index] = eltern[eltern[index]]
            index = eltern[index]
        return index

    for erster_index, zweiter_index in paare:
        if not (0 <= erster_index < len(jobs) and 0 <= zweiter_index < len(jobs)):
            continue
        erster = wurzel(erster_index)
        zweiter = wurzel(zweiter_index)
        if erster != zweiter:
            eltern[zweiter] = erster

    ergebnis = []
    position_nach_wurzel = {}
    entfernt = 0
    for index, job in enumerate(jobs):
        gruppe = wurzel(index)
        if gruppe not in position_nach_wurzel:
            position_nach_wurzel[gruppe] = len(ergebnis)
            ergebnis.append(job)
            continue
        jobs_zusammenfuehren(ergebnis[position_nach_wurzel[gruppe]], job)
        entfernt += 1
    return ergebnis, entfernt


def jobs_zusammenfuehren(ziel: Job, quelle: Job) -> Job:
    ziel.quellen_hinzufuegen([ziel.quelle, quelle.quelle, *quelle.quellen])
    ziel.suchbegriffe_aus(quelle)

    quelle_ist_vollstaendiger = _datenqualitaet(quelle) > _datenqualitaet(ziel)
    if quelle_ist_vollstaendiger and quelle.quelle:
        ziel.quelle = quelle.quelle

    if _link_qualitaet(quelle.link) > _link_qualitaet(ziel.link) or (
        quelle_ist_vollstaendiger and quelle.link
    ):
        ziel.link = quelle.link
        if quelle.quelle:
            ziel.quelle = quelle.quelle

    for feld in ("titel", "firma", "ort", "entfernung", "gehalt_min", "gehalt_max", "kategorie"):
        aktueller_wert = str(getattr(ziel, feld, "") or "").strip()
        neuer_wert = str(getattr(quelle, feld, "") or "").strip()
        if neuer_wert and (not aktueller_wert or quelle_ist_vollstaendiger):
            setattr(ziel, feld, neuer_wert)

    if len(str(quelle.kurzbeschreibung or "").strip()) > len(str(ziel.kurzbeschreibung or "").strip()):
        ziel.kurzbeschreibung = quelle.kurzbeschreibung
    if quelle.veroeffentlichungsdatum and (
        not ziel.veroeffentlichungsdatum or quelle.veroeffentlichungsdatum > ziel.veroeffentlichungsdatum
    ):
        ziel.veroeffentlichungsdatum = quelle.veroeffentlichungsdatum

    _verwaltungsdaten_zusammenfuehren(ziel, quelle)
    _ki_daten_zusammenfuehren(ziel, quelle)
    ziel.quellen_hinzufuegen([ziel.quelle])
    return ziel


def _verwaltungsdaten_zusammenfuehren(ziel: Job, quelle: Job) -> None:
    ziel.favorit = ziel.favorit or quelle.favorit
    ziel.beworben = ziel.beworben or quelle.beworben
    if ziel.bewertung is None and quelle.bewertung is not None:
        ziel.bewertung = quelle.bewertung
    ziel.eigene_bewertung = max(ziel.eigene_bewertung, quelle.eigene_bewertung)
    speicherzeitpunkte = [
        zeitpunkt
        for zeitpunkt in (ziel.gespeichert_am, quelle.gespeichert_am)
        if zeitpunkt
    ]
    ziel.gespeichert_am = min(speicherzeitpunkte) if speicherzeitpunkte else ""

    for feld in (
        "notizen", "ansprechpartner", "email", "telefon", "gehaltsnotizen", "naechste_aktion"
    ):
        setattr(ziel, feld, _texte_verbinden(getattr(ziel, feld), getattr(quelle, feld)))

    for feld in ("bewerbungsdatum", "followup_datum", "followup_uhrzeit"):
        if not str(getattr(ziel, feld, "") or "").strip() and str(getattr(quelle, feld, "") or "").strip():
            setattr(ziel, feld, getattr(quelle, feld))
    ziel.followup_erledigt = ziel.followup_erledigt or quelle.followup_erledigt

    verlauf = normalisiere_statusverlauf([*ziel.statusverlauf, *quelle.statusverlauf])
    eindeutig = {}
    for eintrag in verlauf:
        schluessel = (
            eintrag.get("id"), eintrag.get("datum"), eintrag.get("uhrzeit"), eintrag.get("status")
        )
        eindeutig[schluessel] = eintrag
    ziel.statusverlauf = sorted(eindeutig.values(), key=statusverlauf_sortierschluessel)
    if ziel.statusverlauf:
        ziel.status = ziel.statusverlauf[-1]["status"]
    else:
        rang = {status: index for index, status in enumerate(JOB_STATUS_VALUES)}
        ziel.status = max((ziel.status, quelle.status), key=lambda status: rang.get(status, 0))
    ziel.beworben = ziel.beworben or ziel.status == "Beworben"


def _ki_daten_zusammenfuehren(ziel: Job, quelle: Job) -> None:
    vorherige_werte = {
        feld: list(getattr(ziel, feld))
        for feld in ("ki_staerken", "ki_risiken", "ki_skills", "ki_ausschluesse", "ki_offene_punkte")
    }
    if _ki_qualitaet(quelle) > _ki_qualitaet(ziel):
        ziel.ki_daten_aus(quelle)
    for feld in ("ki_staerken", "ki_risiken", "ki_skills", "ki_ausschluesse", "ki_offene_punkte"):
        werte = []
        gesehen = set()
        for wert in [*vorherige_werte[feld], *getattr(ziel, feld), *getattr(quelle, feld)]:
            text = str(wert or "").strip()
            if text and text.casefold() not in gesehen:
                werte.append(text)
                gesehen.add(text.casefold())
        setattr(ziel, feld, werte)


def _ki_qualitaet(job: Job) -> tuple[int, int, int]:
    art = 2 if job.ki_bewertungsart == "echt" else 1 if job.hat_ki_daten() else 0
    details = sum(len(getattr(job, feld)) for feld in (
        "ki_staerken", "ki_risiken", "ki_skills", "ki_ausschluesse", "ki_offene_punkte"
    ))
    return art, details, len(str(job.ki_zusammenfassung or ""))


def _link_qualitaet(link: str) -> tuple[int, int]:
    text = normalisierte_url(link)
    if not text:
        return 0, 0
    aggregator = any(host in text for host in ("jooble.org", "adzuna."))
    return (1 if aggregator else 2, len(text))


def _datenqualitaet(job: Job) -> tuple[int, int, tuple[int, int]]:
    beschreibung_laenge = len(str(job.kurzbeschreibung or "").strip())
    gefuellte_felder = sum(
        bool(str(getattr(job, feld, "") or "").strip())
        for feld in (
            "titel", "firma", "ort", "link", "entfernung", "veroeffentlichungsdatum",
            "gehalt_min", "gehalt_max", "kategorie",
        )
    )
    return beschreibung_laenge, gefuellte_felder, _link_qualitaet(job.link)


def _texte_verbinden(erster, zweiter) -> str:
    erster_text = str(erster or "").strip()
    zweiter_text = str(zweiter or "").strip()
    if not erster_text:
        return zweiter_text
    if not zweiter_text or zweiter_text.casefold() in erster_text.casefold():
        return erster_text
    if erster_text.casefold() in zweiter_text.casefold():
        return zweiter_text
    return f"{erster_text}\n\n{zweiter_text}"


def _aehnlichkeit(erster: str, zweiter: str) -> float:
    if not erster or not zweiter:
        return 0.0
    if erster == zweiter:
        return 1.0
    return SequenceMatcher(None, erster, zweiter).ratio()


def _ort_kern(ort: str) -> str:
    tokens = [
        token for token in ort.split()
        if not token.isdigit() and token not in {"deutschland", "germany", "hessen", "bayern", "nrw"}
    ]
    return " ".join(tokens) or ort


def _orte_sind_kompatibel(erster: str, zweiter: str) -> bool:
    erster_kern = _ort_kern(erster)
    zweiter_kern = _ort_kern(zweiter)
    if erster_kern == zweiter_kern:
        return True
    erster_tokens = set(erster_kern.split())
    zweiter_tokens = set(zweiter_kern.split())
    if erster_tokens and zweiter_tokens and (erster_tokens <= zweiter_tokens or zweiter_tokens <= erster_tokens):
        return True
    return _aehnlichkeit(erster_kern, zweiter_kern) >= 0.90


def _beschreibungsaehnlichkeit(erster: Job, zweiter: Job) -> float:
    erster_text = normalisiere_jobtext(erster.kurzbeschreibung)[:700]
    zweiter_text = normalisiere_jobtext(zweiter.kurzbeschreibung)[:700]
    if len(erster_text) < 60 or len(zweiter_text) < 60:
        return 0.0
    return _aehnlichkeit(erster_text, zweiter_text)


def _mehrdeutigkeits_score(erster: Job, zweiter: Job) -> float:
    erster_inhalt = job_inhaltsschluessel(erster)
    zweiter_inhalt = job_inhaltsschluessel(zweiter)
    if not erster_inhalt or not zweiter_inhalt or not _orte_sind_kompatibel(erster_inhalt[2], zweiter_inhalt[2]):
        return 0.0
    titel = _aehnlichkeit(erster_inhalt[0], zweiter_inhalt[0])
    firma = _aehnlichkeit(erster_inhalt[1], zweiter_inhalt[1])
    beschreibung = _beschreibungsaehnlichkeit(erster, zweiter)
    return 0.48 * titel + 0.37 * firma + 0.15 * beschreibung


def _job_promptdaten(job: Job) -> dict[str, str]:
    return {
        "titel": job.titel,
        "firma": job.firma,
        "ort": job.ort,
        "quelle": job.quelle,
        "datum": job.veroeffentlichungsdatum,
        "beschreibung": " ".join(str(job.kurzbeschreibung or "").split())[:500],
    }
