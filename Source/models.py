from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Optional
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

JOB_STATUS_VALUES = [
    "Neu",
    "Gespeichert",
    "Bewerbung geplant",
    "Beworben",
    "Gespraech",
    "Angebot",
    "Absage",
    "Erledigt",
]
JOB_STATUS_SELECTABLE_VALUES = [
    "Neu",
    "Gespeichert",
    "Bewerbung geplant",
    "Beworben",
    "Gespraech",
    "Erledigt",
]

SEARCH_TERM_STATUS_VALUES = ["aktiv", "pausiert", "geloescht"]
SEARCH_TERM_SOURCE_VALUES = ["manuell", "KI"]
USER_PROFILE_FIELDS = (
    "kurzprofil",
    "berufserfahrung",
    "staerken",
    "kenntnisse",
    "wunschrolle",
    "einschraenkungen",
)


def _sauberer_text(wert) -> str:
    if wert is None:
        return ""
    return str(wert).strip()


def normalisiere_status(wert) -> str:
    status = _sauberer_text(wert)
    if status in JOB_STATUS_VALUES:
        return status
    return "Neu"


def status_fuer_anzeige(wert) -> str:
    status = normalisiere_status(wert)
    if status in ("Angebot", "Absage"):
        return "Erledigt"
    return status


def normalisiere_eigene_bewertung(wert) -> int:
    try:
        bewertung = int(wert)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, bewertung))


def normalisiere_match_score(wert) -> int:
    try:
        score = int(wert)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def normalisiere_textliste(wert) -> list[str]:
    if not isinstance(wert, list):
        return []
    return [str(eintrag).strip() for eintrag in wert if str(eintrag or "").strip()]


def normalisiere_statusverlauf(wert) -> list[dict[str, str]]:
    if not isinstance(wert, list):
        return []

    eintraege = []
    for index, eintrag in enumerate(wert):
        if not isinstance(eintrag, dict):
            continue
        status = normalisiere_status(eintrag.get("status"))
        if status == "Neu":
            continue
        datum = _sauberer_text(eintrag.get("datum"))
        uhrzeit = _sauberer_text(eintrag.get("uhrzeit"))
        if not datum or not uhrzeit:
            zeitpunkt = _sauberer_text(eintrag.get("zeitpunkt"))
            if zeitpunkt:
                datum, uhrzeit = _datum_und_uhrzeit_aus_zeitpunkt(zeitpunkt)
        if not datum:
            datum = _sauberer_text(eintrag.get("date"))
        if not uhrzeit:
            uhrzeit = _sauberer_text(eintrag.get("time"))
        if not datum:
            datum = "1970-01-01"
        if not uhrzeit:
            uhrzeit = "00:00"
        eintraege.append({
            "id": _sauberer_text(eintrag.get("id")) or f"legacy-{index + 1}",
            "datum": datum,
            "uhrzeit": uhrzeit[:5],
            "status": status,
        })
    return sorted(eintraege, key=statusverlauf_sortierschluessel)


def statusverlauf_sortierschluessel(eintrag: dict[str, str]):
    datum = _sauberer_text(eintrag.get("datum"))
    uhrzeit = _sauberer_text(eintrag.get("uhrzeit"))
    eintrag_id = _sauberer_text(eintrag.get("id"))
    id_zeitstempel = eintrag_id.split("-", 1)[0]
    if len(id_zeitstempel) == 20 and id_zeitstempel.isdigit():
        try:
            return (datetime.strptime(id_zeitstempel, "%Y%m%d%H%M%S%f"), eintrag_id)
        except ValueError:
            pass
    for formatierung in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M"):
        try:
            return (datetime.strptime(f"{datum} {uhrzeit}", formatierung), eintrag_id)
        except ValueError:
            pass
    return (datetime.min, eintrag_id)


def _datum_und_uhrzeit_aus_zeitpunkt(zeitpunkt: str) -> tuple[str, str]:
    text = zeitpunkt.strip()
    for formatierung in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            wert = datetime.strptime(text[:19], formatierung)
            return wert.strftime("%Y-%m-%d"), wert.strftime("%H:%M")
        except ValueError:
            pass
    return "", ""


def normalisiere_zeitpunkt(wert) -> str:
    text = _sauberer_text(wert)
    if not text:
        return ""
    for formatierung, laenge in (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M", 16),
        ("%Y-%m-%d %H:%M", 16),
    ):
        try:
            zeitpunkt = datetime.strptime(text[:laenge], formatierung)
            return zeitpunkt.isoformat(timespec="seconds")
        except ValueError:
            pass
    return ""


TRACKING_PARAMETER_PREFIXE = ("utm_",)
TRACKING_PARAMETER_NAMEN = {
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "source",
}

JOOBLE_JOB_PFAD = re.compile(r"^/(?:away|desc)/(-?\d+)(?:/|$)", re.IGNORECASE)
JOBTITEL_ZUSAETZE = (
    re.compile(r"\(?\b(?:m|w|d|f|x|gn)(?:\s*[/|,\-]\s*(?:m|w|d|f|x|gn)){1,4}\b\)?", re.IGNORECASE),
    re.compile(r"\((?:all genders|alle geschlechter|gn)\)", re.IGNORECASE),
)
FIRMEN_RECHTSFORMEN = re.compile(
    r"\b(?:gmbh|mbh|ag|kg|kgaa|ug|se|gbr|ohg|e\s*v|inc|ltd|llc|corp|co)\b",
    re.IGNORECASE,
)


def normalisiere_jobtext(wert, feld: str = "allgemein") -> str:
    text = _sauberer_text(wert).casefold().replace("ß", "ss")
    if feld == "titel":
        for muster in JOBTITEL_ZUSAETZE:
            text = muster.sub(" ", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    if feld == "firma":
        text = FIRMEN_RECHTSFORMEN.sub(" ", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def normalisierte_url(url: str) -> str:
    text = _sauberer_text(url)
    if not text:
        return ""

    try:
        teile = urlsplit(text)
    except ValueError:
        return text.lower().rstrip("/")

    if not teile.scheme or not teile.netloc:
        return text.lower().rstrip("/")

    scheme = teile.scheme.lower()
    host = teile.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    pfad = teile.path.rstrip("/") or ""
    if host == "jooble.org" or host.endswith(".jooble.org"):
        treffer = JOOBLE_JOB_PFAD.match(pfad)
        if treffer:
            return urlunsplit((scheme, host, f"/job/{treffer.group(1)}", "", ""))

    query_parameter = []
    for name, wert in parse_qsl(teile.query, keep_blank_values=True):
        name_klein = name.lower()
        if name_klein in TRACKING_PARAMETER_NAMEN:
            continue
        if any(name_klein.startswith(prefix) for prefix in TRACKING_PARAMETER_PREFIXE):
            continue
        query_parameter.append((name, wert))

    query = urlencode(sorted(query_parameter), doseq=True)
    return urlunsplit((scheme, host, pfad, query, ""))


def job_schluessel(job: "Job"):
    inhalt = (
        normalisiere_jobtext(job.titel, "titel"),
        normalisiere_jobtext(job.firma, "firma"),
        normalisiere_jobtext(job.ort, "ort"),
    )
    if all(inhalt):
        return ("inhalt", *inhalt)

    normalisierter_link = normalisierte_url(job.link)
    if normalisierter_link:
        return ("link", normalisierter_link)

    return ("unvollstaendig", *inhalt)


@dataclass
class Job:
    titel: str
    firma: str
    ort: str
    quelle: str
    link: str = ""
    entfernung: str = ""
    kurzbeschreibung: str = ""
    veroeffentlichungsdatum: str = ""
    quellen: list[str] = field(default_factory=list)
    favorit: bool = False
    beworben: bool = False
    bewertung: Optional[str] = None
    status: str = "Neu"
    gespeichert_am: str = ""
    notizen: str = ""
    bewerbungsdatum: str = ""
    ansprechpartner: str = ""
    email: str = ""
    telefon: str = ""
    gehaltsnotizen: str = ""
    gehalt_min: str = ""
    gehalt_max: str = ""
    kategorie: str = ""
    eigene_bewertung: int = 0
    statusverlauf: list[dict[str, str]] = field(default_factory=list)
    naechste_aktion: str = ""
    followup_datum: str = ""
    followup_uhrzeit: str = ""
    followup_erledigt: bool = False
    ki_zusammenfassung: str = ""
    ki_match_score: int = 0
    ki_bewertungsart: str = ""
    ki_empfehlung: str = ""
    ki_staerken: list[str] = field(default_factory=list)
    ki_risiken: list[str] = field(default_factory=list)
    ki_skills: list[str] = field(default_factory=list)
    ki_ausschluesse: list[str] = field(default_factory=list)
    ki_offene_punkte: list[str] = field(default_factory=list)
    ki_suchbegriffe: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.status = normalisiere_status(self.status)
        self.gespeichert_am = normalisiere_zeitpunkt(self.gespeichert_am)
        self.eigene_bewertung = normalisiere_eigene_bewertung(self.eigene_bewertung)
        self.statusverlauf = normalisiere_statusverlauf(self.statusverlauf)
        self.ki_match_score = normalisiere_match_score(self.ki_match_score)
        self.ki_bewertungsart = self.ki_bewertungsart if self.ki_bewertungsart in ("echt", "technisch") else ""
        self.ki_staerken = normalisiere_textliste(self.ki_staerken)
        self.ki_risiken = normalisiere_textliste(self.ki_risiken)
        self.ki_skills = normalisiere_textliste(self.ki_skills)
        self.ki_ausschluesse = normalisiere_textliste(self.ki_ausschluesse)
        self.ki_offene_punkte = normalisiere_textliste(self.ki_offene_punkte)
        self.ki_suchbegriffe = normalisiere_textliste(self.ki_suchbegriffe)
        vorhandene_quellen = normalisiere_textliste(self.quellen)
        self.quellen = []
        self.quellen_hinzufuegen([self.quelle, *vorhandene_quellen])
        if self.beworben and self.status == "Neu":
            self.status = "Beworben"
        elif self.favorit and self.status == "Neu":
            self.status = "Gespeichert"
        if self.statusverlauf:
            self.status = self.statusverlauf[-1]["status"]
            self.beworben = self.status == "Beworben"
            if not self.gespeichert_am:
                erster_zeitpunkt = statusverlauf_sortierschluessel(self.statusverlauf[0])[0]
                if erster_zeitpunkt != datetime.min:
                    self.gespeichert_am = erster_zeitpunkt.isoformat(timespec="seconds")

    def ist_gespeichert(self) -> bool:
        return (
            self.favorit
            or self.status != "Neu"
            or bool(self.notizen.strip())
            or bool(self.bewerbungsdatum.strip())
            or bool(self.ansprechpartner.strip())
            or bool(self.email.strip())
            or bool(self.telefon.strip())
            or bool(self.gehaltsnotizen.strip())
            or self.eigene_bewertung > 0
            or bool(self.statusverlauf)
            or bool(self.naechste_aktion.strip())
            or bool(self.followup_datum.strip())
            or bool(self.followup_uhrzeit.strip())
        )

    def verwaltungsdaten_aus(self, anderer: "Job") -> None:
        self.favorit = anderer.favorit
        self.beworben = anderer.beworben
        self.bewertung = anderer.bewertung
        self.status = normalisiere_status(anderer.status)
        self.gespeichert_am = normalisiere_zeitpunkt(anderer.gespeichert_am)
        self.notizen = anderer.notizen
        self.bewerbungsdatum = anderer.bewerbungsdatum
        self.ansprechpartner = anderer.ansprechpartner
        self.email = anderer.email
        self.telefon = anderer.telefon
        self.gehaltsnotizen = anderer.gehaltsnotizen
        self.eigene_bewertung = normalisiere_eigene_bewertung(anderer.eigene_bewertung)
        self.statusverlauf = normalisiere_statusverlauf(anderer.statusverlauf)
        self.naechste_aktion = anderer.naechste_aktion
        self.followup_datum = anderer.followup_datum
        self.followup_uhrzeit = anderer.followup_uhrzeit
        self.followup_erledigt = anderer.followup_erledigt

    def ki_daten_aus(self, anderer: "Job") -> None:
        self.ki_zusammenfassung = anderer.ki_zusammenfassung
        self.ki_match_score = normalisiere_match_score(anderer.ki_match_score)
        self.ki_bewertungsart = anderer.ki_bewertungsart
        self.ki_empfehlung = anderer.ki_empfehlung
        self.ki_staerken = normalisiere_textliste(anderer.ki_staerken)
        self.ki_risiken = normalisiere_textliste(anderer.ki_risiken)
        self.ki_skills = normalisiere_textliste(anderer.ki_skills)
        self.ki_ausschluesse = normalisiere_textliste(anderer.ki_ausschluesse)
        self.ki_offene_punkte = normalisiere_textliste(anderer.ki_offene_punkte)

    def suchbegriffe_hinzufuegen(self, begriffe: list[str]) -> None:
        vorhandene = normalisiere_textliste(self.ki_suchbegriffe)
        gesehen = {eintrag.lower() for eintrag in vorhandene}
        for begriff in normalisiere_textliste(begriffe):
            schluessel = begriff.lower()
            if schluessel not in gesehen:
                vorhandene.append(begriff)
                gesehen.add(schluessel)
        self.ki_suchbegriffe = vorhandene

    def suchbegriffe_aus(self, anderer: "Job") -> None:
        self.suchbegriffe_hinzufuegen(anderer.ki_suchbegriffe)

    def quellen_hinzufuegen(self, quellen: list[str]) -> None:
        vorhandene = normalisiere_textliste(self.quellen)
        gesehen = {eintrag.casefold() for eintrag in vorhandene}
        for quelle in normalisiere_textliste(quellen):
            schluessel = quelle.casefold()
            if schluessel not in gesehen:
                vorhandene.append(quelle)
                gesehen.add(schluessel)
        self.quellen = vorhandene
        if not self.quelle and vorhandene:
            self.quelle = vorhandene[0]

    def quellen_text(self) -> str:
        self.quellen_hinzufuegen([self.quelle])
        return ", ".join(self.quellen)

    def ki_daten_loeschen(self) -> None:
        self.ki_zusammenfassung = ""
        self.ki_match_score = 0
        self.ki_bewertungsart = ""
        self.ki_empfehlung = ""
        self.ki_staerken = []
        self.ki_risiken = []
        self.ki_skills = []
        self.ki_ausschluesse = []
        self.ki_offene_punkte = []

    def hat_ki_daten(self) -> bool:
        return any([
            self.ki_zusammenfassung.strip(),
            self.ki_match_score > 0,
            self.ki_bewertungsart,
            self.ki_empfehlung.strip(),
            self.ki_staerken,
            self.ki_risiken,
            self.ki_skills,
            self.ki_ausschluesse,
            self.ki_offene_punkte,
        ])

    def to_dict(self):
        return {
            "titel": self.titel,
            "firma": self.firma,
            "ort": self.ort,
            "quelle": self.quelle,
            "link": self.link,
            "url": self.link,
            "entfernung": self.entfernung,
            "kurzbeschreibung": self.kurzbeschreibung,
            "veroeffentlichungsdatum": self.veroeffentlichungsdatum,
            "quellen": normalisiere_textliste(self.quellen),
            "favorit": self.favorit,
            "beworben": self.beworben,
            "bewertung": self.bewertung,
            "status": self.status,
            "gespeichert_am": self.gespeichert_am,
            "notizen": self.notizen,
            "bewerbungsdatum": self.bewerbungsdatum,
            "ansprechpartner": self.ansprechpartner,
            "email": self.email,
            "telefon": self.telefon,
            "gehaltsnotizen": self.gehaltsnotizen,
            "gehalt_min": self.gehalt_min,
            "gehalt_max": self.gehalt_max,
            "kategorie": self.kategorie,
            "eigene_bewertung": self.eigene_bewertung,
            "statusverlauf": normalisiere_statusverlauf(self.statusverlauf),
            "naechste_aktion": self.naechste_aktion,
            "followup_datum": self.followup_datum,
            "followup_uhrzeit": self.followup_uhrzeit,
            "followup_erledigt": self.followup_erledigt,
            "ki_zusammenfassung": self.ki_zusammenfassung,
            "ki_match_score": self.ki_match_score,
            "ki_bewertungsart": self.ki_bewertungsart,
            "ki_empfehlung": self.ki_empfehlung,
            "ki_staerken": normalisiere_textliste(self.ki_staerken),
            "ki_risiken": normalisiere_textliste(self.ki_risiken),
            "ki_skills": normalisiere_textliste(self.ki_skills),
            "ki_ausschluesse": normalisiere_textliste(self.ki_ausschluesse),
            "ki_offene_punkte": normalisiere_textliste(self.ki_offene_punkte),
            "ki_suchbegriffe": normalisiere_textliste(self.ki_suchbegriffe),
        }

    @classmethod
    def from_dict(cls, daten):
        if not isinstance(daten, dict):
            daten = {}

        status = normalisiere_status(daten.get("status"))
        beworben = bool(daten.get("beworben", False))
        favorit = bool(daten.get("favorit", False))
        if status == "Neu" and beworben:
            status = "Beworben"
        elif status == "Neu" and favorit:
            status = "Gespeichert"

        return cls(
            titel=_sauberer_text(daten.get("titel")),
            firma=_sauberer_text(daten.get("firma")),
            ort=_sauberer_text(daten.get("ort")),
            quelle=_sauberer_text(daten.get("quelle")),
            link=_sauberer_text(daten.get("link") or daten.get("url")),
            entfernung=_sauberer_text(daten.get("entfernung")),
            kurzbeschreibung=_sauberer_text(daten.get("kurzbeschreibung")),
            veroeffentlichungsdatum=_sauberer_text(daten.get("veroeffentlichungsdatum")),
            quellen=normalisiere_textliste(daten.get("quellen")),
            favorit=favorit,
            beworben=beworben,
            bewertung=daten.get("bewertung"),
            status=status,
            gespeichert_am=normalisiere_zeitpunkt(daten.get("gespeichert_am")),
            notizen=_sauberer_text(daten.get("notizen")),
            bewerbungsdatum=_sauberer_text(daten.get("bewerbungsdatum")),
            ansprechpartner=_sauberer_text(daten.get("ansprechpartner")),
            email=_sauberer_text(daten.get("email")),
            telefon=_sauberer_text(daten.get("telefon")),
            gehaltsnotizen=_sauberer_text(daten.get("gehaltsnotizen")),
            gehalt_min=_sauberer_text(daten.get("gehalt_min") or daten.get("gehaltsuntergrenze")),
            gehalt_max=_sauberer_text(daten.get("gehalt_max") or daten.get("gehaltsobergrenze")),
            kategorie=_sauberer_text(daten.get("kategorie")),
            eigene_bewertung=normalisiere_eigene_bewertung(daten.get("eigene_bewertung")),
            statusverlauf=normalisiere_statusverlauf(daten.get("statusverlauf")),
            naechste_aktion=_sauberer_text(daten.get("naechste_aktion")),
            followup_datum=_sauberer_text(daten.get("followup_datum")),
            followup_uhrzeit=_sauberer_text(daten.get("followup_uhrzeit"))[:5],
            followup_erledigt=bool(daten.get("followup_erledigt", False)),
            ki_zusammenfassung=_sauberer_text(daten.get("ki_zusammenfassung")),
            ki_match_score=normalisiere_match_score(daten.get("ki_match_score")),
            ki_bewertungsart=_sauberer_text(daten.get("ki_bewertungsart")),
            ki_empfehlung=_sauberer_text(daten.get("ki_empfehlung")),
            ki_staerken=normalisiere_textliste(daten.get("ki_staerken")),
            ki_risiken=normalisiere_textliste(daten.get("ki_risiken")),
            ki_skills=normalisiere_textliste(daten.get("ki_skills")),
            ki_ausschluesse=normalisiere_textliste(daten.get("ki_ausschluesse")),
            ki_offene_punkte=normalisiere_textliste(daten.get("ki_offene_punkte")),
            ki_suchbegriffe=normalisiere_textliste(daten.get("ki_suchbegriffe")),
        )


@dataclass
class SearchTerm:
    id: str
    bezeichnung: str
    quelle: str = "manuell"
    status: str = "aktiv"
    letzte_suche: str = ""
    treffer_anzahl: int = 0
    ki_bewertet_anzahl: int = 0
    gute_treffer_anzahl: int = 0
    durchschnitt_score: int = 0
    bester_score: int = 0

    def __post_init__(self):
        self.id = _sauberer_text(self.id)
        self.bezeichnung = _sauberer_text(self.bezeichnung)
        self.quelle = self.quelle if self.quelle in SEARCH_TERM_SOURCE_VALUES else "manuell"
        self.status = self.status if self.status in SEARCH_TERM_STATUS_VALUES else "aktiv"
        self.letzte_suche = _sauberer_text(self.letzte_suche)
        self.treffer_anzahl = _nicht_negative_ganzzahl(self.treffer_anzahl)
        self.ki_bewertet_anzahl = _nicht_negative_ganzzahl(self.ki_bewertet_anzahl)
        self.gute_treffer_anzahl = _nicht_negative_ganzzahl(self.gute_treffer_anzahl)
        self.durchschnitt_score = normalisiere_match_score(self.durchschnitt_score)
        self.bester_score = normalisiere_match_score(self.bester_score)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "bezeichnung": self.bezeichnung,
            "quelle": self.quelle,
            "status": self.status,
            "letzte_suche": self.letzte_suche,
            "treffer_anzahl": self.treffer_anzahl,
            "ki_bewertet_anzahl": self.ki_bewertet_anzahl,
            "gute_treffer_anzahl": self.gute_treffer_anzahl,
            "durchschnitt_score": self.durchschnitt_score,
            "bester_score": self.bester_score,
        }

    @classmethod
    def from_dict(cls, daten):
        if not isinstance(daten, dict):
            daten = {}
        return cls(
            id=daten.get("id", ""),
            bezeichnung=daten.get("bezeichnung") or daten.get("name", ""),
            quelle=daten.get("quelle", "manuell"),
            status=daten.get("status", "aktiv"),
            letzte_suche=daten.get("letzte_suche", ""),
            treffer_anzahl=daten.get("treffer_anzahl", 0),
            ki_bewertet_anzahl=daten.get("ki_bewertet_anzahl", 0),
            gute_treffer_anzahl=daten.get("gute_treffer_anzahl", 0),
            durchschnitt_score=daten.get("durchschnitt_score", 0),
            bester_score=daten.get("bester_score", 0),
        )


@dataclass(frozen=True)
class SearchTermSetEntry:
    bezeichnung: str
    status: str = "aktiv"
    quelle: str = "manuell"

    def __post_init__(self):
        object.__setattr__(self, "bezeichnung", _sauberer_text(self.bezeichnung))
        status = self.status if self.status in ("aktiv", "pausiert") else "aktiv"
        quelle = self.quelle if self.quelle in SEARCH_TERM_SOURCE_VALUES else "manuell"
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "quelle", quelle)

    def to_dict(self) -> dict[str, str]:
        return {
            "bezeichnung": self.bezeichnung,
            "status": self.status,
            "quelle": self.quelle,
        }

    @classmethod
    def from_dict(cls, daten):
        if not isinstance(daten, dict):
            daten = {}
        return cls(
            bezeichnung=daten.get("bezeichnung") or daten.get("name", ""),
            status=daten.get("status", "aktiv"),
            quelle=daten.get("quelle", "manuell"),
        )


@dataclass
class SearchTermSet:
    name: str
    suchbegriffe: list[SearchTermSetEntry] = field(default_factory=list)
    aktualisiert_am: str = ""

    def __post_init__(self):
        self.name = " ".join(_sauberer_text(self.name).split())
        self.aktualisiert_am = _sauberer_text(self.aktualisiert_am)
        eindeutige = []
        gesehen = set()
        for eintrag in self.suchbegriffe or []:
            if not isinstance(eintrag, SearchTermSetEntry):
                eintrag = SearchTermSetEntry.from_dict(eintrag)
            schluessel = eintrag.bezeichnung.casefold()
            if not schluessel or schluessel in gesehen:
                continue
            eindeutige.append(eintrag)
            gesehen.add(schluessel)
        self.suchbegriffe = eindeutige

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "suchbegriffe": [eintrag.to_dict() for eintrag in self.suchbegriffe],
            "aktualisiert_am": self.aktualisiert_am,
        }

    @classmethod
    def from_dict(cls, daten):
        if not isinstance(daten, dict):
            daten = {}
        rohbegriffe = daten.get("suchbegriffe") or daten.get("terms") or []
        return cls(
            name=daten.get("name", ""),
            suchbegriffe=[
                SearchTermSetEntry.from_dict(eintrag)
                for eintrag in rohbegriffe
                if isinstance(eintrag, dict)
            ],
            aktualisiert_am=daten.get("aktualisiert_am", ""),
        )


@dataclass
class UserProfile:
    name: str
    kurzprofil: str = ""
    berufserfahrung: str = ""
    staerken: str = ""
    kenntnisse: str = ""
    wunschrolle: str = ""
    einschraenkungen: str = ""
    aktualisiert_am: str = ""

    def __post_init__(self):
        self.name = " ".join(_sauberer_text(self.name).split())
        self.aktualisiert_am = _sauberer_text(self.aktualisiert_am)
        for feld in USER_PROFILE_FIELDS:
            setattr(self, feld, _sauberer_text(getattr(self, feld)))

    def daten(self) -> dict[str, str]:
        return {feld: getattr(self, feld) for feld in USER_PROFILE_FIELDS}

    def ist_ausgefuellt(self) -> bool:
        return any(self.daten().values())

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            **self.daten(),
            "aktualisiert_am": self.aktualisiert_am,
        }

    @classmethod
    def from_dict(cls, daten):
        if not isinstance(daten, dict):
            daten = {}
        profil_daten = daten.get("daten") if isinstance(daten.get("daten"), dict) else daten
        return cls(
            name=daten.get("name", ""),
            **{feld: profil_daten.get(feld, "") for feld in USER_PROFILE_FIELDS},
            aktualisiert_am=daten.get("aktualisiert_am", ""),
        )


def _nicht_negative_ganzzahl(wert) -> int:
    try:
        return max(0, int(wert))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class SearchRequest:
    suchbegriff: str
    ort: str
    umkreis: str
    provider: list[str] = field(default_factory=list)
    ki_kriterien: dict[str, object] = field(default_factory=dict)

    def bereinigt(self):
        return SearchRequest(
            suchbegriff=_sauberer_text(self.suchbegriff),
            ort=_sauberer_text(self.ort),
            umkreis=_sauberer_text(self.umkreis),
            provider=list(self.provider or []),
            ki_kriterien=dict(self.ki_kriterien or {}),
        )

