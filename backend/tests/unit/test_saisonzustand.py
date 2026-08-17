"""Saisonzustand: Anomalie gegen die eigene Normale (AP-Saisonzustand §5).

Test-First nach CLAUDE.md — diese Datei entstand vor
`app/services/saisonzustand.py`. Geprüft wird die Rechenschicht, nicht der
Abruf: Die Kennzahlen sind reine Funktionen über Tageswerten, und genau
das macht sie prüfbar.

**Der Saisonzustand ist nicht die Bedingungs-Engine.** Die Engine beantwortet
"ist jetzt ein guter Zeitpunkt" über 14 Tage Rückschau aus der Forecast-API;
hier geht es über sechs Monate gegen eine 30-Jahres-Normale aus dem Archiv.
Zwei Größen, zwei Quellen, bewusst getrennt (ADR 0007).
"""

from datetime import date

import pytest

from app.core import params
from app.services.saisonzustand import (
    Fensterwert,
    anomalie_prozent,
    fenster_ist,
    fenster_normal,
    kalendertage,
    laengste_trockenperiode,
    normale_je_kalendertag,
    saisonkennzahlen,
)


def reihe(start: date, werte: list[float | None]) -> dict[date, float | None]:
    """Tageswerte ab `start`, ein Wert je Tag."""
    from datetime import timedelta

    return {start + timedelta(days=i): wert for i, wert in enumerate(werte)}


# ------------------------------------------------------------- Kalenderfenster


def test_kalendertage_laeuft_rueckwaerts_und_schliesst_das_ende_ein():
    tage = kalendertage(date(2026, 3, 3), 3)

    assert tage == [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]


def test_kalendertage_ueberschreitet_den_jahreswechsel():
    tage = kalendertage(date(2026, 1, 2), 3)

    assert tage == [date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]


# ------------------------------------------------------------------- Normale


def test_normale_mittelt_je_kalendertag_ueber_die_jahre():
    """Der 1. Juni wird über alle Jahre gemittelt, nicht über das Jahr."""
    werte = {
        date(1991, 6, 1): 10.0,
        date(1992, 6, 1): 20.0,
        date(1993, 6, 1): 30.0,
        date(1991, 6, 2): 0.0,
    }

    normale = normale_je_kalendertag(werte)

    assert normale["06-01"] == pytest.approx(20.0)
    assert normale["06-02"] == pytest.approx(0.0)


def test_normale_uebergeht_luecken_statt_sie_als_null_zu_zaehlen():
    """Ein fehlender Tag darf den Mittelwert nicht nach unten ziehen."""
    werte = {date(1991, 6, 1): 10.0, date(1992, 6, 1): None, date(1993, 6, 1): 30.0}

    normale = normale_je_kalendertag(werte)

    assert normale["06-01"] == pytest.approx(20.0)


def test_normale_kennt_den_schalttag():
    werte = {date(1992, 2, 29): 4.0, date(1996, 2, 29): 6.0}

    normale = normale_je_kalendertag(werte)

    assert normale["02-29"] == pytest.approx(5.0)


# ---------------------------------------------------- Fenster gegen Normale


def test_neunzig_tage_werden_gegen_dasselbe_kalenderfenster_verglichen():
    """Kein Jahresdurchschnitt.

    Ein trockener Sommer darf nicht dadurch normal aussehen, dass die
    nassen Wintermonate in die Referenz gerechnet werden.
    """
    # Normale: im Fenster täglich 2 mm, ausserhalb 10 mm.
    normale = {f"{monat:02d}-{tag:02d}": 10.0 for monat in range(1, 13) for tag in range(1, 32)}
    for tag in kalendertage(date(2026, 8, 31), 90):
        normale[tag.strftime("%m-%d")] = 2.0

    erwartet = fenster_normal(normale, date(2026, 8, 31), 90)

    assert erwartet == pytest.approx(180.0)


def test_normale_des_fensters_nutzt_den_schalttag_nur_im_schaltjahr():
    """Am Fensterrand entscheidet der Kalender, nicht die Tageszahl."""
    normale = {"02-27": 1.0, "02-28": 1.0, "02-29": 100.0, "03-01": 1.0, "03-02": 1.0}

    im_schaltjahr = fenster_normal(normale, date(2024, 3, 1), 3)  # 28.2., 29.2., 1.3.
    ohne_schaltjahr = fenster_normal(normale, date(2026, 3, 1), 3)  # 27.2., 28.2., 1.3.

    # Dasselbe Fenster von drei Tagen trifft nur im Schaltjahr den 29.2.
    assert im_schaltjahr == pytest.approx(102.0)
    assert ohne_schaltjahr == pytest.approx(3.0)


def test_fehlender_kalendertag_in_der_normale_faellt_auf():
    """Lieber None als eine Summe, der ein Tag fehlt."""
    normale = {"03-01": 1.0}

    assert fenster_normal(normale, date(2026, 3, 2), 2) is None


# ------------------------------------------------------------------ Ist-Wert


def test_fenster_summiert_genau_die_angeforderten_tage():
    werte = reihe(date(2026, 8, 1), [1.0] * 31)

    ergebnis = fenster_ist(werte, date(2026, 8, 31), 30, art="summe")

    assert isinstance(ergebnis, Fensterwert)
    assert ergebnis.wert == pytest.approx(30.0)
    assert ergebnis.fehlende_tage == 0
    assert ergebnis.vollstaendig is True


def test_fenster_bildet_auf_wunsch_den_mittelwert():
    werte = reihe(date(2026, 8, 1), [0.2, 0.4, 0.6])

    ergebnis = fenster_ist(werte, date(2026, 8, 3), 3, art="mittel")

    assert ergebnis.wert == pytest.approx(0.4)


def test_luecke_ergibt_ein_unvollstaendiges_ergebnis_und_keine_stille_teilsumme():
    """§5: Eine lückenhafte Archivantwort darf nicht als Zahl durchgehen.

    Der Wert wird trotzdem berechnet — aber er trägt sichtbar, auf wie
    wenigen Tagen er beruht.
    """
    werte = reihe(date(2026, 8, 1), [1.0, None, 1.0, 1.0])

    ergebnis = fenster_ist(werte, date(2026, 8, 4), 4, art="summe")

    assert ergebnis.vollstaendig is False
    assert ergebnis.fehlende_tage == 1
    assert ergebnis.wert == pytest.approx(3.0)


def test_fehlender_tag_am_rand_zaehlt_ebenfalls_als_luecke():
    werte = reihe(date(2026, 8, 2), [1.0, 1.0])

    ergebnis = fenster_ist(werte, date(2026, 8, 3), 3, art="summe")

    assert ergebnis.fehlende_tage == 1
    assert ergebnis.vollstaendig is False


# ----------------------------------------------------------------- Anomalie


def test_anomalie_ist_prozent_der_normale():
    assert anomalie_prozent(74.0, 180.0) == pytest.approx(41.1, abs=0.05)


def test_anomalie_ueber_hundert_bei_nassem_jahr():
    assert anomalie_prozent(240.0, 180.0) == pytest.approx(133.3, abs=0.05)


def test_anomalie_ohne_normale_ist_keine_zahl():
    """Ohne Referenz gibt es keine Aussage — und keine erfundene."""
    assert anomalie_prozent(74.0, None) is None
    assert anomalie_prozent(None, 180.0) is None


def test_anomalie_bei_normale_null_ist_keine_zahl():
    """Wüstenfall: Division durch null erzeugt keine Prozentzahl."""
    assert anomalie_prozent(5.0, 0.0) is None


# -------------------------------------------------------- Trockenperiode


def test_laengste_trockenperiode_zaehlt_zusammenhaengende_tage():
    werte = reihe(date(2026, 8, 1), [5.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0])

    assert laengste_trockenperiode(werte, date(2026, 8, 7), 7) == 3


def test_trockenperiode_zaehlt_leichten_regen_als_trocken():
    """Unterhalb der Schwelle aus params.py bleibt der Boden trocken."""
    knapp_drunter = params.SEASON_DRY_DAY_MAX_MM - 0.1
    werte = reihe(date(2026, 8, 1), [knapp_drunter, knapp_drunter, 10.0])

    assert laengste_trockenperiode(werte, date(2026, 8, 3), 3) == 2


def test_trockenperiode_am_fensterende():
    werte = reihe(date(2026, 8, 1), [10.0, 0.0, 0.0])

    assert laengste_trockenperiode(werte, date(2026, 8, 3), 3) == 2


def test_trockenperiode_ohne_regen_ist_das_ganze_fenster():
    werte = reihe(date(2026, 8, 1), [0.0] * 5)

    assert laengste_trockenperiode(werte, date(2026, 8, 5), 5) == 5


def test_fehlender_tag_unterbricht_die_trockenperiode_nicht_stillschweigend():
    """Ein Loch ist kein Regen — aber auch kein belegter Trockentag."""
    werte = reihe(date(2026, 8, 1), [0.0, None, 0.0])

    assert laengste_trockenperiode(werte, date(2026, 8, 3), 3) == 1


# ------------------------------------------------------- Kennzahlen gesamt


def test_saisonkennzahlen_liefert_alle_vier_groessen():
    """§3: drei Niederschlagsfenster, eine Bodenfeuchte, eine Trockenperiode.

    Keine Gesamtnote — die Kennzahlen stehen einzeln (Invariante 10).
    """
    ende = date(2026, 8, 31)
    niederschlag = {tag: 1.0 for tag in kalendertage(ende, 180)}
    feuchte = {tag: 0.20 for tag in kalendertage(ende, 180)}
    normale_niederschlag = {tag.strftime("%m-%d"): 2.0 for tag in kalendertage(ende, 366)}
    normale_feuchte = {tag.strftime("%m-%d"): 0.25 for tag in kalendertage(ende, 366)}

    kennzahlen = saisonkennzahlen(
        ende, niederschlag, feuchte, normale_niederschlag, normale_feuchte
    )

    assert kennzahlen.niederschlag_30d.wert == pytest.approx(30.0)
    assert kennzahlen.niederschlag_90d.wert == pytest.approx(90.0)
    assert kennzahlen.niederschlag_180d.wert == pytest.approx(180.0)
    # Jeweils die Hälfte der Normale.
    assert kennzahlen.niederschlag_30d_prozent == pytest.approx(50.0)
    assert kennzahlen.niederschlag_90d_prozent == pytest.approx(50.0)
    assert kennzahlen.niederschlag_180d_prozent == pytest.approx(50.0)
    assert kennzahlen.bodenfeuchte_90d.wert == pytest.approx(0.20)
    assert kennzahlen.bodenfeuchte_90d_prozent == pytest.approx(80.0)
    assert kennzahlen.trockenperiode_180d_tage == 0
    assert kennzahlen.vollstaendig is True

    # Es gibt bewusst keine verdichtete Gesamtnote.
    assert not hasattr(kennzahlen, "score")
    assert not hasattr(kennzahlen, "note")


def test_unvollstaendige_reihe_macht_das_ganze_ergebnis_unvollstaendig():
    ende = date(2026, 8, 31)
    niederschlag = {tag: 1.0 for tag in kalendertage(ende, 180)}
    niederschlag[ende] = None
    feuchte = {tag: 0.20 for tag in kalendertage(ende, 180)}
    normale_niederschlag = {tag.strftime("%m-%d"): 2.0 for tag in kalendertage(ende, 366)}
    normale_feuchte = {tag.strftime("%m-%d"): 0.25 for tag in kalendertage(ende, 366)}

    kennzahlen = saisonkennzahlen(
        ende, niederschlag, feuchte, normale_niederschlag, normale_feuchte
    )

    assert kennzahlen.vollstaendig is False
    assert kennzahlen.fehlende_tage >= 1
