"""GPX-Parsing und -Bereinigung — Verträge nach Spec §9 und ADR 0006.

Diese Tests existieren VOR der Implementierung (CLAUDE.md, Test-First).
Sie dürfen nie gelöscht oder aufgeweicht werden, um grün zu werden.
"""

from datetime import UTC

import pytest

from app.core import params
from app.services.gpx import CleanResult, ParsedTrack, clean_track, parse_gpx


def _load(gpx_fixture_dir, name: str) -> bytes:
    return (gpx_fixture_dir / name).read_bytes()


# ---------------------------------------------------------------- Parsing

def test_parse_returns_all_points_with_utc_times(gpx_fixture_dir):
    track = parse_gpx(_load(gpx_fixture_dir, "track_no_accuracy.gpx"))
    assert isinstance(track, ParsedTrack)
    assert len(track.points) == 60
    for p in track.points:
        assert p.time.tzinfo is not None
        assert p.time.utcoffset() == UTC.utcoffset(None)


def test_parse_accuracy_meters_from_extension(gpx_fixture_dir):
    """Fall 1 (ADR 0006): Extension-Element mit 'accuracy' im Namen = Meter."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_accuracy_meters.gpx"))
    assert all(p.accuracy_source == "meters" for p in track.points)
    assert track.points[0].accuracy_m == pytest.approx(4.0)
    assert max(p.accuracy_m for p in track.points) <= 9.0


def test_parse_hdop_converted_and_flagged_as_estimate(gpx_fixture_dir):
    """Fall 2: nur <hdop> -> Meter-Schätzung über HDOP_TO_M_FACTOR."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_hdop_only.gpx"))
    assert all(p.accuracy_source == "hdop" for p in track.points)
    assert track.points[0].accuracy_m == pytest.approx(1.5 * params.HDOP_TO_M_FACTOR)
    assert track.points[20].accuracy_m == pytest.approx(8.0 * params.HDOP_TO_M_FACTOR)


def test_parse_without_accuracy_reports_none(gpx_fixture_dir):
    """Fall 3: keine Angabe -> None + source 'none'. NIE Werte erfinden."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_no_accuracy.gpx"))
    assert all(p.accuracy_m is None for p in track.points)
    assert all(p.accuracy_source == "none" for p in track.points)


# ------------------------------------------------------------- Bereinigung

def test_clean_drops_points_above_accuracy_threshold(gpx_fixture_dir):
    """hdop 8.0 -> 40 m Schätzung -> über TRACK_ACCURACY_MAX_M -> raus."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_hdop_only.gpx"))
    result = clean_track(track.points)
    assert isinstance(result, CleanResult)
    assert result.dropped_accuracy == 2
    assert len(result.kept) == 58
    assert result.all_accuracy_missing is False
    # Mittel nur über behaltene Punkte -> 1.5 * Faktor
    assert result.mean_accuracy_m == pytest.approx(1.5 * params.HDOP_TO_M_FACTOR)


def test_clean_drops_speed_outlier(gpx_fixture_dir):
    """200-m-Sprung in 1 s (Kronendach-Sprung) muss rausfliegen."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_speed_outlier.gpx"))
    result = clean_track(track.points)
    assert result.dropped_speed >= 1
    # Der Ausreisser lag quer zur Linie: kein behaltener Punkt weit weg
    lats = [p.lat for p in result.kept]
    assert max(lats) - min(lats) < 0.0005  # ~55 m Toleranz statt 200 m Sprung


def test_clean_without_accuracy_data_keeps_points_and_flags(gpx_fixture_dir):
    """Ohne Genauigkeitsdaten: kein Genauigkeitsfilter möglich, aber Flag
    für Confidence 'niedrig' downstream (ADR 0006)."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_no_accuracy.gpx"))
    result = clean_track(track.points)
    assert result.dropped_accuracy == 0
    assert result.all_accuracy_missing is True
    assert result.mean_accuracy_m is None


def test_clean_never_mutates_input(gpx_fixture_dir):
    """Invariante 5: der Rohtrack bleibt unverändert erhalten."""
    track = parse_gpx(_load(gpx_fixture_dir, "track_speed_outlier.gpx"))
    before = tuple(track.points)
    clean_track(track.points)
    assert tuple(track.points) == before
