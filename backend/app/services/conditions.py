"""Bedingungs-Engine (Spec §5).

VERTRAG (durch tests/unit/test_conditions_scoring.py fixiert):
- Vier Teilscores: season (0-30), soil_moisture (0-30), rain (0-25),
  field (0-15). total = Summe, mit vollständiger Aufschlüsselung
  (Invariante 10: keine Blackbox-Zahl).
- Saisonfenster hängen am ÖKOTYP/Zielfenster, nie an der Taxonomie
  (Invariante 7): "sommer" und "burgunder" sind getrennte Fenster
  derselben Art t_aestivum.
- Die Engine gibt NIE "keine Saison" zurück: best_window liefert immer
  das nächstliegende Zielfenster (Spec §5, Ganzjahresabdeckung).
- Open-Meteo ignoriert falsch geschriebene Variablennamen stillschweigend;
  validate_openmeteo_response muss bei fehlenden Feldern HART fehlschlagen.

Alle Kurven sind stückweise linear und über app/core/params.py kalibrierbar.
Bewusst einfach gehalten: kalibriert wird mit echten Felddaten, nicht jetzt.
"""

from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.core import params

MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class SeasonWindow:
    key: str  # z.B. "aestivum_sommer"
    label: str
    start_month: int  # inklusiv
    end_month: int  # inklusiv; end < start = über Jahreswechsel
    plateau_start_month: int | None
    plateau_end_month: int | None
    host_hint: str  # Wirtsbaum-Hinweis fürs UI


# Startwerte nach Spec §5 — im UI editierbar, hier nur Defaults.
DEFAULT_WINDOWS: dict[str, SeasonWindow] = {
    "borchii": SeasonWindow("borchii", "Bianchetto", 1, 4, 2, 3, "Kiefer und Hasel beachten"),
    "aestivum_sommer": SeasonWindow(
        "aestivum_sommer", "Sommer-Ökotyp", 5, 11, 7, 9, "Eiche, Buche, Hainbuche"
    ),
    "aestivum_burgunder": SeasonWindow(
        "aestivum_burgunder",
        "Burgunder-Ökotyp",
        9,
        1,
        10,
        12,
        "Eiche, Buche, Hainbuche; dunklere Gleba",
    ),
    "macrosporum": SeasonWindow(
        "macrosporum", "Knoblauchtrüffel", 9, 12, None, None, "Eiche, Pappel, Weide"
    ),
    "mesentericum": SeasonWindow("mesentericum", "Löwentrüffel", 9, 2, None, None, "Buche"),
    "brumale": SeasonWindow(
        "brumale", "Wintertrüffel", 12, 3, None, None, "geringwertig, Fenster-Füller"
    ),
}


@dataclass(frozen=True)
class ScoreBreakdown:
    season: float
    soil_moisture: float
    rain: float
    field: float
    window_key: str
    total: float


# --- Hilfen ---------------------------------------------------------------


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ramp(value: float, zero_at: float, one_at: float) -> float:
    """Stückweise lineare Rampe: 0 bei zero_at, 1 bei one_at, dazwischen
    linear, ausserhalb geklemmt. Funktioniert in beide Richtungen."""
    if zero_at == one_at:
        return 1.0 if value >= one_at else 0.0
    return _clamp01((value - zero_at) / (one_at - zero_at))


def _month_position(d: date) -> float:
    """Datum als stetige Monatsposition: 1. Januar -> 1.0, 31. Januar -> ~1.97.
    Ohne das springt der Saisonscore am Monatsersten statt weich zu laufen."""
    days_in_month = monthrange(d.year, d.month)[1]
    return d.month + (d.day - 1) / days_in_month


def _window_length(window: SeasonWindow) -> float:
    """Fensterlänge in Monaten. end < start bedeutet über den Jahreswechsel."""
    length = (window.end_month + 1 - window.start_month) % MONTHS_PER_YEAR
    # Rest 0 heisst hier Volljahr, nicht Nulllänge.
    return float(length) if length else float(MONTHS_PER_YEAR)


# --- Teilscores -----------------------------------------------------------


def season_score(d: date, window: SeasonWindow) -> float:
    """0-30, weiche Kurve übers Jahr (kein harter Schalter)."""
    length = _window_length(window)
    # Alles auf eine fensterrelative Achse 0..length drehen. Damit ist ein
    # Fenster über den Jahreswechsel derselbe Fall wie jedes andere.
    offset = (_month_position(d) - window.start_month) % MONTHS_PER_YEAR
    if offset >= length:
        return 0.0

    if window.plateau_start_month is not None and window.plateau_end_month is not None:
        plateau_from = float((window.plateau_start_month - window.start_month) % MONTHS_PER_YEAR)
        plateau_to = float((window.plateau_end_month + 1 - window.start_month) % MONTHS_PER_YEAR)
        if plateau_to <= plateau_from:
            plateau_to += MONTHS_PER_YEAR
        plateau_from = min(plateau_from, length)
        plateau_to = min(plateau_to, length)

        if offset < plateau_from:
            shape = _ramp(offset, 0.0, plateau_from)
        elif offset <= plateau_to:
            shape = 1.0
        else:
            shape = _ramp(offset, length, plateau_to)
    else:
        # Ohne Plateau: Dreieck mit Peak in Fenstermitte. Das trennt
        # überlappende Fenster ohne Sonderregel — im Februar liegt das
        # borchii-Plateau über der brumale-Flanke.
        peak = length / 2
        shape = 1.0 - abs(offset - peak) / peak

    return params.SCORE_MAX_SEASON * _clamp01(shape)


def best_window(
    d: date, windows: Mapping[str, SeasonWindow] | None = None
) -> tuple[SeasonWindow, float]:
    """Höchstbewertetes Fenster für das Datum. Gibt IMMER ein Fenster zurück."""
    candidates = windows if windows is not None else DEFAULT_WINDOWS
    if not candidates:
        raise ValueError("Keine Saisonfenster konfiguriert.")
    # max() liefert auch bei lauter Nullscores ein Fenster — die Engine kennt
    # kein "keine Saison" (Spec §5).
    best = max(candidates.values(), key=lambda w: season_score(d, w))
    return best, season_score(d, best)


def soil_moisture_score(moisture_7_28_m3m3: float) -> float:
    """0-30, Glockenkurve um den Zielbereich in 7-28 cm Tiefe."""
    optimum = params.SOIL_MOISTURE_OPTIMUM_M3M3
    if moisture_7_28_m3m3 <= optimum:
        shape = _ramp(moisture_7_28_m3m3, params.SOIL_MOISTURE_DRY_ZERO_M3M3, optimum)
    else:
        shape = _ramp(moisture_7_28_m3m3, params.SOIL_MOISTURE_WET_ZERO_M3M3, optimum)
    return params.SCORE_MAX_SOIL_MOISTURE * shape


def _rain_lag_weight(lag_days: int) -> float:
    """Gewicht eines Regentages nach Abstand zu heute."""
    if lag_days <= params.RAIN_LAG_IDEAL_FROM_DAYS:
        # Frischer Regen zählt, aber gedämpft: der Boden hat noch nicht reagiert.
        return params.RAIN_WEIGHT_TODAY + (1.0 - params.RAIN_WEIGHT_TODAY) * _ramp(
            lag_days, 0.0, params.RAIN_LAG_IDEAL_FROM_DAYS
        )
    if lag_days <= params.RAIN_LAG_IDEAL_TO_DAYS:
        return 1.0
    return params.RAIN_WEIGHT_OLDEST + (1.0 - params.RAIN_WEIGHT_OLDEST) * _ramp(
        lag_days, params.RAIN_LAG_MAX_DAYS, params.RAIN_LAG_IDEAL_TO_DAYS
    )


def rain_score(precip_daily_mm: Sequence[float]) -> float:
    """0-25. Index 0 = heute, rückwärts 14 Tage. Ideal: ergiebiger Regen
    vor 3-7 Tagen; gewichtet nach Abstand."""
    weighted_mm = 0.0
    for lag_days, millimetres in enumerate(precip_daily_mm[: params.RAIN_LAG_MAX_DAYS]):
        # Negativwerte sind Messfehler, keine Trockenheit.
        weighted_mm += max(0.0, millimetres) * _rain_lag_weight(lag_days)
    return params.SCORE_MAX_RAIN * _clamp01(weighted_mm / params.RAIN_SATURATION_MM)


def field_score(temp_c: float, wind_kmh: float, soil_temp_c: float) -> float:
    """0-15. Gefrorener Boden => 0. Hitze und starker Wind mindern."""
    if soil_temp_c <= params.FIELD_SOIL_FROZEN_C:
        # Kein Teilscore, sondern ein K.-o.-Kriterium: im gefrorenen Boden
        # findet der Hund nichts, egal wie gut der Rest aussieht.
        return 0.0

    if temp_c < params.FIELD_TEMP_IDEAL_FROM_C:
        temp_factor = _ramp(temp_c, params.FIELD_TEMP_COLD_ZERO_C, params.FIELD_TEMP_IDEAL_FROM_C)
    elif temp_c > params.FIELD_TEMP_IDEAL_TO_C:
        temp_factor = _ramp(temp_c, params.FIELD_TEMP_HEAT_ZERO_C, params.FIELD_TEMP_IDEAL_TO_C)
    else:
        temp_factor = 1.0

    wind_factor = _ramp(wind_kmh, params.FIELD_WIND_ZERO_KMH, params.FIELD_WIND_CALM_KMH)
    return params.SCORE_MAX_FIELD * temp_factor * wind_factor


def total_score(
    d: date,
    moisture: float,
    precip_daily_mm: Sequence[float],
    temp_c: float,
    wind_kmh: float,
    soil_temp_c: float,
    window: SeasonWindow | None = None,
) -> ScoreBreakdown:
    """Gesamtscore 0-100 mit vollständiger Aufschlüsselung (Invariante 10).
    Ohne explizites Fenster wird best_window verwendet."""
    if window is None:
        window, season = best_window(d)
    else:
        season = season_score(d, window)

    soil = soil_moisture_score(moisture)
    rain = rain_score(precip_daily_mm)
    field = field_score(temp_c, wind_kmh, soil_temp_c)

    return ScoreBreakdown(
        season=season,
        soil_moisture=soil,
        rain=rain,
        field=field,
        window_key=window.key,
        # Summe statt eigener Formel: der Gesamtscore muss aus den vier
        # sichtbaren Teilen nachrechenbar bleiben.
        total=season + soil + rain + field,
    )


def validate_openmeteo_response(requested_hourly: Sequence[str], response: Mapping) -> None:
    """Wirft ValueError, wenn angeforderte hourly-Variablen in der Antwort
    fehlen (Open-Meteo ignoriert Tippfehler stillschweigend, Spec §5)."""
    hourly = response.get("hourly")
    # Fehlender oder kaputter hourly-Block heisst: nichts ist angekommen.
    # Damit faellt er unter dieselbe Prüfung statt in einen Sonderzweig.
    available: Mapping = hourly if isinstance(hourly, Mapping) else {}

    # Ein vorhandener Schlüssel mit None ist genauso unbrauchbar wie ein
    # fehlender; beides darf nicht stillschweigend durchrutschen.
    missing = [name for name in requested_hourly if available.get(name) is None]
    if missing:
        raise ValueError(
            "Open-Meteo-Antwort ohne angeforderte hourly-Variablen: "
            f"{', '.join(sorted(missing))}. Variablennamen prüfen — die API "
            "ignoriert Tippfehler stillschweigend."
        )
