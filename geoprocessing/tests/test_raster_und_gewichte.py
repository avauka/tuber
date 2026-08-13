"""Rastergeometrie und Gewichtsumlage (AP17a §7).

Beides ohne GDAL prüfbar und deshalb hier: Die Rastergeometrie ist reine
Arithmetik, die Umlage-Regel auch. Was die Pipeline daraus macht, prüft der
echte Lauf.
"""

import pytest

from gewichte import GEWICHTE, klasse, umgelegt
from raster import ZIELRASTER, Rasterbezug


# ---------------------------------------------------------- Rastergeometrie


def test_zwei_laeufe_ergeben_dasselbe_raster():
    """Die Ausdehnung steht fest im Code und wird nicht neu transformiert.

    Sonst verschöbe eine neue PROJ-Version das Raster um Zentimeter und
    alle bestehenden Faktorlayer passten nicht mehr aufeinander.
    """
    erst = Rasterbezug()
    zweit = Rasterbezug()

    assert erst == zweit
    assert erst.geotransform == zweit.geotransform
    assert (erst.spalten, erst.zeilen) == (zweit.spalten, zweit.zeilen)


def test_ausdehnung_liegt_auf_ganzen_zellen():
    for wert in ZIELRASTER.bbox:
        assert wert % ZIELRASTER.zellgroesse == 0


def test_zellgroesse_ist_zwanzig_meter():
    """ADR 0008 §2 — bewusst nicht die 10 m aus Spec §6."""
    assert ZIELRASTER.zellgroesse == 20
    assert ZIELRASTER.epsg == 25832


def test_geotransform_zeigt_nach_unten():
    ursprung_x, breite, dreh_x, ursprung_y, dreh_y, hoehe = ZIELRASTER.geotransform

    assert (ursprung_x, ursprung_y) == (ZIELRASTER.min_x, ZIELRASTER.max_y)
    assert breite == ZIELRASTER.zellgroesse
    assert hoehe == -ZIELRASTER.zellgroesse
    assert dreh_x == dreh_y == 0.0


def test_abmessungen_passen_zur_ausdehnung():
    assert ZIELRASTER.spalten * ZIELRASTER.zellgroesse == ZIELRASTER.max_x - ZIELRASTER.min_x
    assert ZIELRASTER.zeilen * ZIELRASTER.zellgroesse == ZIELRASTER.max_y - ZIELRASTER.min_y


def test_fremdes_raster_wird_erkannt():
    """Stufe 2 addiert nur Layer, die dieselben Zellen meinen."""
    assert ZIELRASTER.passt_zu(ZIELRASTER.geotransform, ZIELRASTER.spalten, ZIELRASTER.zeilen)

    verschoben = list(ZIELRASTER.geotransform)
    verschoben[0] += 10
    assert not ZIELRASTER.passt_zu(tuple(verschoben), ZIELRASTER.spalten, ZIELRASTER.zeilen)
    assert not ZIELRASTER.passt_zu(ZIELRASTER.geotransform, ZIELRASTER.spalten + 1, ZIELRASTER.zeilen)


# ------------------------------------------------------------------ Umlage


def test_vollstaendiger_satz_bleibt_unveraendert():
    anteile = umgelegt(list(GEWICHTE))

    assert anteile == pytest.approx(GEWICHTE)
    assert sum(anteile.values()) == pytest.approx(100.0)


def test_fehlender_faktor_wird_proportional_umgelegt():
    """ADR 0008 §5: kein Ersatzwert, kein Auffüllen mit Mittelwerten."""
    anteile = umgelegt(["kalk", "wasser", "exposition", "wirtsbaum", "struktur"])

    assert sum(anteile.values()) == pytest.approx(100.0)
    # Das Klima-Gewicht (10) verteilt sich nach Verhältnis, die Rangfolge
    # der übrigen bleibt.
    assert anteile["kalk"] > anteile["wasser"] > anteile["exposition"]
    assert anteile["kalk"] == pytest.approx(30.0 * 100.0 / 90.0)


def test_ein_einziger_faktor_traegt_hundert_prozent():
    """Genau der Stand von AP17a — und im UI zu erklären."""
    anteile = umgelegt(["kalk"])

    assert anteile == {"kalk": pytest.approx(100.0)}


def test_ohne_faktoren_gibt_es_keinen_score():
    with pytest.raises(ValueError, match="Ohne Faktoren"):
        umgelegt([])


def test_unbekannter_faktor_faellt_auf():
    with pytest.raises(ValueError, match="Unbekannte Faktoren"):
        umgelegt(["kalk", "mondphase"])


# ------------------------------------------------------------------ Klassen


@pytest.mark.parametrize(
    ("score", "erwartet"),
    [(0, 1), (24.9, 1), (25, 2), (49.9, 2), (50, 3), (74.9, 3), (75, 4), (100, 4)],
)
def test_vier_klassen_ohne_verlauf(score, erwartet):
    assert klasse(score) == erwartet
