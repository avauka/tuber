"""Saisonzustand: Rechenschicht (AP-Saisonzustand, ADR 0007 „Rückweg").

**Nicht die Bedingungs-Engine.** Die beantwortet „ist jetzt ein guter
Zeitpunkt" über 14 Tage Rückschau aus der Forecast-API und lebt in
`app/services/area_conditions.py`. Hier geht es um sechs Monate gegen eine
30-Jahres-Normale aus dem ERA5-Archiv — die Frage ist „ist dieses Jahr
eins". Zwei Größen, zwei Quellen, zwei Tabellen; die Trennung ist
beabsichtigt und in ADR 0007 begründet.

Alles hier ist reine Arithmetik über Tageswerten. Der Abruf steckt im Job
(`app/jobs/season_backfill.py`), damit die Kennzahlen ohne Netz prüfbar
bleiben — CLAUDE.md verlangt für Bedingungs-Scoring Tests vor dem Code.

Zwei Entscheidungen, die den Zahlen ihre Bedeutung geben:

* **Kalenderfenster statt Jahresdurchschnitt.** Die 90-Tage-Summe wird
  gegen die Normale genau derselben Kalendertage verglichen. Sonst liesse
  ein trockener Sommer sich dadurch normalisieren, dass die nassen
  Wintermonate in die Referenz rutschen.
* **Lücken bleiben sichtbar.** Ein Fenster mit fehlenden Tagen liefert
  seinen Wert weiter, trägt aber mit, auf wie vielen Tagen er beruht. Eine
  stille Teilsumme wäre eine Zahl, der man ihre Unvollständigkeit nicht
  ansieht.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.core import params

# Schlüssel der Normale: Kalendertag ohne Jahr, damit der 29.02. ein
# eigener Eintrag bleibt und nicht auf den 28.02. fällt.
KALENDERSCHLUESSEL = "%m-%d"


@dataclass(frozen=True)
class Fensterwert:
    """Ein Fensterwert samt seiner Datenlage."""

    wert: float | None
    tage: int
    fehlende_tage: int

    @property
    def vollstaendig(self) -> bool:
        return self.fehlende_tage == 0


@dataclass(frozen=True)
class Saisonkennzahlen:
    """Die Kennzahlen aus §3 — einzeln, ohne verdichtete Gesamtnote.

    Eine Gesamtnote wäre nicht kalibrierbar, solange keine Funddaten
    existieren, und Invariante 10 verlangt Aufschlüsselbarkeit ohnehin.
    """

    stichtag: date
    niederschlag_30d: Fensterwert
    niederschlag_90d: Fensterwert
    niederschlag_180d: Fensterwert
    niederschlag_30d_prozent: float | None
    niederschlag_90d_prozent: float | None
    niederschlag_180d_prozent: float | None
    bodenfeuchte_90d: Fensterwert
    bodenfeuchte_90d_prozent: float | None
    trockenperiode_180d_tage: int
    fehlende_tage: int

    @property
    def vollstaendig(self) -> bool:
        return self.fehlende_tage == 0


def kalendertage(ende: date, tage: int) -> list[date]:
    """Die `tage` Kalendertage bis einschliesslich `ende`, aufsteigend."""
    return [ende - timedelta(days=abstand) for abstand in reversed(range(tage))]


def normale_je_kalendertag(werte: dict[date, float | None]) -> dict[str, float]:
    """Mittelwert je Kalendertag über alle Jahre der Reihe.

    Fehlende Tage werden übergangen, nicht als Null gezählt — sonst zöge
    eine Lücke im Archiv den Normalwert nach unten und die Anomalie
    fälschlich nach oben.
    """
    summen: dict[str, float] = {}
    zaehler: dict[str, int] = {}
    for tag, wert in werte.items():
        if wert is None:
            continue
        schluessel = tag.strftime(KALENDERSCHLUESSEL)
        summen[schluessel] = summen.get(schluessel, 0.0) + float(wert)
        zaehler[schluessel] = zaehler.get(schluessel, 0) + 1
    return {
        schluessel: summen[schluessel] / zaehler[schluessel]
        for schluessel in summen
        if zaehler[schluessel]
    }


def fenster_normal(normale: dict[str, float], ende: date, tage: int) -> float | None:
    """Erwartungswert des Fensters aus der Normale derselben Kalendertage.

    Fehlt auch nur ein Kalendertag, gibt es keinen Erwartungswert: Eine
    Summe, der ein Tag fehlt, wäre als Vergleichsgrösse falsch — und die
    Anomalie darauf sähe aus wie ein Wettersignal.
    """
    gesamt = 0.0
    for tag in kalendertage(ende, tage):
        schluessel = tag.strftime(KALENDERSCHLUESSEL)
        if schluessel not in normale:
            return None
        gesamt += normale[schluessel]
    return gesamt


def fenster_ist(
    werte: dict[date, float | None],
    ende: date,
    tage: int,
    art: Literal["summe", "mittel"],
) -> Fensterwert:
    """Summe oder Mittel über das Fenster, mit der Zahl der Lücken."""
    vorhanden: list[float] = []
    fehlend = 0
    for tag in kalendertage(ende, tage):
        wert = werte.get(tag)
        if wert is None:
            fehlend += 1
            continue
        vorhanden.append(float(wert))

    if not vorhanden:
        return Fensterwert(wert=None, tage=tage, fehlende_tage=fehlend)
    wert = sum(vorhanden) if art == "summe" else sum(vorhanden) / len(vorhanden)
    return Fensterwert(wert=wert, tage=tage, fehlende_tage=fehlend)


def anomalie_prozent(ist: float | None, normal: float | None) -> float | None:
    """Ist-Wert als Prozent der Normale.

    Der Saisonzustand ist eine Abweichung, keine Absolutzahl: „180 mm in
    sechs Monaten" sagt nichts, „41 % des Normalwerts" sagt alles.
    """
    if ist is None or normal is None or normal == 0:
        return None
    return ist / normal * 100.0


def laengste_trockenperiode(
    werte: dict[date, float | None],
    ende: date,
    tage: int,
    schwelle_mm: float | None = None,
) -> int:
    """Längste zusammenhängende Folge trockener Tage im Fenster.

    Absolut, ohne Normalbezug (§3) — eine sechswöchige Trockenphase im
    Frühsommer ist unabhängig davon bemerkenswert, wie das langjährige
    Mittel aussieht.

    Ein fehlender Tag beendet die Folge, statt sie stillschweigend
    fortzuschreiben: Ob es an ihm geregnet hat, ist unbekannt.
    """
    grenze = params.SEASON_DRY_DAY_MAX_MM if schwelle_mm is None else schwelle_mm
    laengste = 0
    laufend = 0
    for tag in kalendertage(ende, tage):
        wert = werte.get(tag)
        if wert is None or float(wert) >= grenze:
            laufend = 0
            continue
        laufend += 1
        laengste = max(laengste, laufend)
    return laengste


def saisonkennzahlen(
    stichtag: date,
    niederschlag: dict[date, float | None],
    bodenfeuchte: dict[date, float | None],
    normale_niederschlag: dict[str, float],
    normale_bodenfeuchte: dict[str, float],
) -> Saisonkennzahlen:
    """Alle Kennzahlen aus §3 für einen Stichtag."""
    kurz, mittel, lang = params.SEASON_WINDOWS_DAYS
    boden_fenster = params.SEASON_SOIL_WINDOW_DAYS

    n30 = fenster_ist(niederschlag, stichtag, kurz, art="summe")
    n90 = fenster_ist(niederschlag, stichtag, mittel, art="summe")
    n180 = fenster_ist(niederschlag, stichtag, lang, art="summe")
    feuchte = fenster_ist(bodenfeuchte, stichtag, boden_fenster, art="mittel")

    # Die Normale der Bodenfeuchte ist ein Mittel, keine Summe: durch die
    # Zahl der Tage teilen, sonst verglichen wir Äpfel mit Birnen.
    normal_feuchte_summe = fenster_normal(normale_bodenfeuchte, stichtag, boden_fenster)
    normal_feuchte = None if normal_feuchte_summe is None else normal_feuchte_summe / boden_fenster

    return Saisonkennzahlen(
        stichtag=stichtag,
        niederschlag_30d=n30,
        niederschlag_90d=n90,
        niederschlag_180d=n180,
        niederschlag_30d_prozent=anomalie_prozent(
            n30.wert, fenster_normal(normale_niederschlag, stichtag, kurz)
        ),
        niederschlag_90d_prozent=anomalie_prozent(
            n90.wert, fenster_normal(normale_niederschlag, stichtag, mittel)
        ),
        niederschlag_180d_prozent=anomalie_prozent(
            n180.wert, fenster_normal(normale_niederschlag, stichtag, lang)
        ),
        bodenfeuchte_90d=feuchte,
        bodenfeuchte_90d_prozent=anomalie_prozent(feuchte.wert, normal_feuchte),
        trockenperiode_180d_tage=laengste_trockenperiode(niederschlag, stichtag, lang),
        # Das längste Fenster kennt die meisten Lücken; die kürzeren sind
        # darin enthalten.
        fehlende_tage=max(n180.fehlende_tage, feuchte.fehlende_tage),
    )
