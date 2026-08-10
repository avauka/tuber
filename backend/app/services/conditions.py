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
"""

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence


@dataclass(frozen=True)
class SeasonWindow:
    key: str            # z.B. "aestivum_sommer"
    label: str
    start_month: int    # inklusiv
    end_month: int      # inklusiv; end < start = über Jahreswechsel
    plateau_start_month: int | None
    plateau_end_month: int | None
    host_hint: str      # Wirtsbaum-Hinweis fürs UI


# Startwerte nach Spec §5 — im UI editierbar, hier nur Defaults.
DEFAULT_WINDOWS: dict[str, SeasonWindow] = {
    "borchii": SeasonWindow("borchii", "Bianchetto", 1, 4, 2, 3,
                            "Kiefer und Hasel beachten"),
    "aestivum_sommer": SeasonWindow("aestivum_sommer", "Sommer-Ökotyp", 5, 11, 7, 9,
                                    "Eiche, Buche, Hainbuche"),
    "aestivum_burgunder": SeasonWindow("aestivum_burgunder", "Burgunder-Ökotyp", 9, 1, 10, 12,
                                       "Eiche, Buche, Hainbuche; dunklere Gleba"),
    "macrosporum": SeasonWindow("macrosporum", "Knoblauchtrüffel", 9, 12, None, None,
                                "Eiche, Pappel, Weide"),
    "mesentericum": SeasonWindow("mesentericum", "Löwentrüffel", 9, 2, None, None,
                                 "Buche"),
    "brumale": SeasonWindow("brumale", "Wintertrüffel", 12, 3, None, None,
                            "geringwertig, Fenster-Füller"),
}


@dataclass(frozen=True)
class ScoreBreakdown:
    season: float
    soil_moisture: float
    rain: float
    field: float
    window_key: str
    total: float


def season_score(d: date, window: SeasonWindow) -> float:
    """0-30, weiche Kurve übers Jahr (kein harter Schalter)."""
    raise NotImplementedError


def best_window(d: date, windows: Mapping[str, SeasonWindow] | None = None
                ) -> tuple[SeasonWindow, float]:
    """Höchstbewertetes Fenster für das Datum. Gibt IMMER ein Fenster zurück."""
    raise NotImplementedError


def soil_moisture_score(moisture_7_28_m3m3: float) -> float:
    """0-30, Glockenkurve um den Zielbereich in 7-28 cm Tiefe."""
    raise NotImplementedError


def rain_score(precip_daily_mm: Sequence[float]) -> float:
    """0-25. Index 0 = heute, rückwärts 14 Tage. Ideal: ergiebiger Regen
    vor 3-7 Tagen; gewichtet nach Abstand."""
    raise NotImplementedError


def field_score(temp_c: float, wind_kmh: float, soil_temp_c: float) -> float:
    """0-15. Gefrorener Boden => 0. Hitze und starker Wind mindern."""
    raise NotImplementedError


def total_score(d: date, moisture: float, precip_daily_mm: Sequence[float],
                temp_c: float, wind_kmh: float, soil_temp_c: float,
                window: SeasonWindow | None = None) -> ScoreBreakdown:
    """Gesamtscore 0-100 mit vollständiger Aufschlüsselung (Invariante 10).
    Ohne explizites Fenster wird best_window verwendet."""
    raise NotImplementedError


def validate_openmeteo_response(requested_hourly: Sequence[str],
                                response: Mapping) -> None:
    """Wirft ValueError, wenn angeforderte hourly-Variablen in der Antwort
    fehlen (Open-Meteo ignoriert Tippfehler stillschweigend, Spec §5)."""
    raise NotImplementedError
