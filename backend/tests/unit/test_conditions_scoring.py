"""Bedingungs-Scoring — Verträge nach Spec §5.

Eigenschafts-Tests statt Magic Numbers: Die Kurvenformen sind kalibrierbar,
die EIGENSCHAFTEN (Monotonie, Bereiche, Aufschlüsselbarkeit) nicht.
"""

from datetime import date

import pytest

from app.services.conditions import (
    DEFAULT_WINDOWS,
    ScoreBreakdown,
    best_window,
    field_score,
    rain_score,
    season_score,
    soil_moisture_score,
    total_score,
    validate_openmeteo_response,
)

JULI = date(2026, 7, 15)  # Plateau Sommer-Ökotyp
NOVEMBER = date(2026, 11, 15)  # Plateau Burgunder-Ökotyp
FEBRUAR = date(2026, 2, 15)  # Bianchetto-Fenster


# ------------------------------------------------- Fenster-Konfiguration


def test_windows_hang_am_oekotyp_nicht_an_der_art():
    """Invariante 7: sommer und burgunder sind GETRENNTE Fenster derselben
    Art. Es darf kein einzelnes 'aestivum'-Fenster geben."""
    assert "aestivum_sommer" in DEFAULT_WINDOWS
    assert "aestivum_burgunder" in DEFAULT_WINDOWS
    assert "aestivum" not in DEFAULT_WINDOWS
    s, b = DEFAULT_WINDOWS["aestivum_sommer"], DEFAULT_WINDOWS["aestivum_burgunder"]
    assert (s.start_month, s.end_month) != (b.start_month, b.end_month)


def test_jedes_fenster_hat_wirtsbaum_hinweis():
    for w in DEFAULT_WINDOWS.values():
        assert w.host_hint.strip()


# ----------------------------------------------------------- Saisonscore


def test_season_score_range_und_plateau():
    w = DEFAULT_WINDOWS["aestivum_sommer"]
    for d in (JULI, NOVEMBER, FEBRUAR):
        assert 0.0 <= season_score(d, w) <= 30.0
    assert season_score(JULI, w) > season_score(FEBRUAR, w)


def test_season_score_weiche_kurve_kein_harter_schalter():
    """An den Fensterrändern > 0, aber unter Plateau-Niveau."""
    w = DEFAULT_WINDOWS["aestivum_sommer"]  # Mai-Nov, Plateau Jul-Sep
    rand = season_score(date(2026, 5, 5), w)
    plateau = season_score(JULI, w)
    assert 0.0 < rand < plateau


def test_season_score_fenster_ueber_jahreswechsel():
    """Burgunder Sep-Jan: Dezember muss hoch bewerten, nicht als 'nach Ende'."""
    w = DEFAULT_WINDOWS["aestivum_burgunder"]
    assert season_score(date(2026, 12, 10), w) > season_score(date(2026, 6, 10), w)


def test_best_window_gibt_immer_ein_fenster_zurueck():
    """Spec §5: Die Engine kennt kein 'keine Saison'."""
    for month in range(1, 13):
        w, _score = best_window(date(2026, month, 15))
        assert w is not None
        assert w.key in DEFAULT_WINDOWS
    # Februar: Bianchetto-Fenster (Beispiel aus dem Spec)
    w, _ = best_window(FEBRUAR)
    assert w.key == "borchii"


# -------------------------------------------------------- Bodenfeuchte


def test_soil_moisture_glockenkurve():
    """Zu trocken UND zu nass sind schlecht; Monotonie weg vom Optimum."""
    scores = {m: soil_moisture_score(m) for m in (0.05, 0.15, 0.28, 0.45, 0.60)}
    for s in scores.values():
        assert 0.0 <= s <= 30.0
    peak = max(scores, key=scores.get)
    assert 0.05 < peak < 0.60  # Optimum liegt innen, nicht am Rand
    assert scores[0.05] < scores[0.15]  # trockener = schlechter
    assert scores[0.60] < scores[0.45]  # nasser = schlechter


# ------------------------------------------------------- Regen-Nachlauf


def _tage(mm_at: dict[int, float]) -> list[float]:
    """14-Tage-Liste, Index 0 = heute."""
    return [mm_at.get(i, 0.0) for i in range(14)]


def test_rain_score_ideal_ist_3_bis_7_tage_nachlauf():
    frisch = rain_score(_tage({1: 22.0}))
    ideal = rain_score(_tage({5: 22.0}))
    alt = rain_score(_tage({13: 22.0}))
    for s in (frisch, ideal, alt):
        assert 0.0 <= s <= 25.0
    assert ideal > frisch
    assert ideal > alt


def test_rain_score_trockenperiode_ist_null_oder_minimal():
    assert rain_score(_tage({})) <= 2.0


# --------------------------------------------------------- Feldfaktoren


def test_field_score_frost_ist_null():
    """Gefrorener Boden macht die Suche sinnlos (Spec §5)."""
    assert field_score(temp_c=2.0, wind_kmh=5.0, soil_temp_c=-1.0) == 0.0


def test_field_score_hitze_und_sturm_mindern():
    mild = field_score(temp_c=14.0, wind_kmh=5.0, soil_temp_c=10.0)
    heiss = field_score(temp_c=32.0, wind_kmh=5.0, soil_temp_c=18.0)
    sturm = field_score(temp_c=14.0, wind_kmh=45.0, soil_temp_c=10.0)
    assert 0.0 <= mild <= 15.0
    assert heiss < mild
    assert sturm < mild


# ---------------------------------------------------------- Gesamtscore


def test_total_score_aufschluesselbar_und_konsistent():
    """Invariante 10: total == Summe der Teilscores, alle sichtbar."""
    b = total_score(
        JULI,
        moisture=0.28,
        precip_daily_mm=_tage({5: 22.0}),
        temp_c=14.0,
        wind_kmh=8.0,
        soil_temp_c=12.0,
    )
    assert isinstance(b, ScoreBreakdown)
    assert 0.0 <= b.total <= 100.0
    assert b.total == pytest.approx(b.season + b.soil_moisture + b.rain + b.field)
    assert b.window_key in DEFAULT_WINDOWS


def test_gute_bedingungen_schlagen_schlechte():
    gut = total_score(JULI, 0.28, _tage({5: 22.0}), 14.0, 8.0, 12.0)
    schlecht = total_score(JULI, 0.05, _tage({}), 33.0, 50.0, 22.0)
    assert gut.total > schlecht.total


# ----------------------------------------------------- Open-Meteo-Ingest


def test_openmeteo_fehlende_variable_schlaegt_hart_fehl():
    """Spec §5: Tippfehler in Variablennamen werden von der API still
    ignoriert — der Ingest muss das erkennen."""
    requested = ["soil_moisture_7_to_28cm", "precipitation"]
    response = {"hourly": {"precipitation": [0.1, 0.0]}}  # Feuchte fehlt!
    with pytest.raises(ValueError):
        validate_openmeteo_response(requested, response)


def test_openmeteo_vollstaendige_antwort_passiert():
    requested = ["precipitation"]
    response = {"hourly": {"precipitation": [0.1, 0.0]}}
    validate_openmeteo_response(requested, response)  # darf nicht werfen
