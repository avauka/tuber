"""Zuordnungstabelle und Kennlinie (AP17a §7).

Die Werte selbst sind fachlicher Vorschlag und dürfen sich ändern; was hier
festgehalten wird, sind die Regeln drumherum — dass Kalkstein oben landet,
dass ein unbekannter Wert zu nodata führt und nicht zu 0, und dass die
Kennlinie unterhalb der Schwelle in die unterste Klasse drückt, ohne die
Fläche zu verlieren.
"""

import pytest

from gewichte import KLASSENGRENZEN, klasse
from kalk_zuordnung import (
    DAEMPFUNG_OHNE_AUSSAGE,
    SCHWELLE,
    boden_score,
    kalkscore,
    kennlinie,
    litho_score,
    verknuepft,
)


# ------------------------------------------------------------- Lithologie


def test_reiner_kalkstein_ist_der_hoechste_wert():
    assert litho_score("Kalkstein") == 100


def test_reihenfolge_der_anteile_zaehlt():
    """"Kalkstein, Tonstein" ist kalkgeprägt, "Tonstein, Kalkstein" nicht."""
    kalk_zuerst = litho_score("Kalkstein, Tonstein")
    ton_zuerst = litho_score("Tonstein, Kalkstein")

    assert kalk_zuerst is not None and ton_zuerst is not None
    assert kalk_zuerst > ton_zuerst


@pytest.mark.parametrize(
    "lithologie",
    ["Kalkstein", "Kalkstein, Mergelstein", "Mergelstein", "Dolomitstein", "Kalksandstein"],
)
def test_carbonatgesteine_liegen_ueber_der_schwelle(lithologie):
    wert = litho_score(lithologie)
    assert wert is not None and wert >= SCHWELLE


@pytest.mark.parametrize(
    "lithologie",
    ["Sand", "Sand, Kies", "Quarzit", "Torf", "Tonstein, Schluffstein", "Sandstein"],
)
def test_silikatische_und_saure_gesteine_bleiben_darunter(lithologie):
    wert = litho_score(lithologie)
    assert wert is not None and wert < SCHWELLE


@pytest.mark.parametrize("lithologie", ["Basaltschutt", "Gneis", "irgendwas"])
def test_unbekannte_lithologie_wird_nodata_und_nicht_null(lithologie):
    """Eine Lücke in der Tabelle soll als Lücke in der Karte auffallen.

    Mit 0 ginge sie als schlechter Standort durch, und niemand fände sie
    je wieder.
    """
    assert litho_score(lithologie) is None


def test_ein_unbekannter_anteil_verwirft_die_ganze_angabe():
    assert litho_score("Kalkstein, Gneis") is None


@pytest.mark.parametrize("lithologie", ["Gewässer", "Abraum, Müll, Bergematerial, Erdaushub"])
def test_flaechen_ohne_aussage_bleiben_leer(lithologie):
    assert litho_score(lithologie) is None


def test_leere_angabe_ist_nodata():
    assert litho_score(None) is None
    assert litho_score("") is None


# --------------------------------------------------------------- Bodentyp


def test_rendzina_ist_der_kalkbodentyp():
    assert boden_score("Rendzina") == 100


def test_zusammengesetzter_bodentyp_wird_vom_zweiten_teil_dominiert():
    """Die Quelle führt beide Reihenfolgen — sie trägt also Bedeutung."""
    rendzina_haupt = boden_score("Braunerde-Rendzina")
    braunerde_haupt = boden_score("Rendzina-Braunerde")

    assert rendzina_haupt is not None and braunerde_haupt is not None
    assert rendzina_haupt > braunerde_haupt


def test_auftrags_ist_ein_zusatz_und_kein_eigener_typ():
    assert boden_score("Auftrags-Pararendzina") == boden_score("Pararendzina")


def test_gleichheitszeichen_der_quelle_stoert_nicht():
    assert boden_score("=Pseudogley") == boden_score("Pseudogley")


@pytest.mark.parametrize("bodentyp", ["Podsol", "Hochmoor", "Braunerde"])
def test_saure_bodentypen_bleiben_unter_der_schwelle(bodentyp):
    wert = boden_score(bodentyp)
    assert wert is not None and wert < SCHWELLE


def test_unbekannter_bodentyp_wird_nodata(bodentyp="Schwarzerde-Sonderfall"):
    assert boden_score(bodentyp) is None


def test_leerer_bodentyp_ist_nodata():
    """In der BK 50 stehen rund 61 000 ha ohne Typ — die bleiben leer."""
    assert boden_score("") is None
    assert boden_score("   ") is None


# --------------------------------------------------------------- Kennlinie


def test_knapp_unter_der_schwelle_landet_in_der_untersten_klasse():
    """ADR 0008 §4: steile Kennlinie statt K.-o.-Kriterium.

    Die Zelle bleibt vorhanden — sie wird nur deutlich abgewertet.
    """
    wert = kennlinie(SCHWELLE - 1)

    assert wert is not None
    assert klasse(wert) == 1
    assert wert > 0


def test_knapp_ueber_der_schwelle_verlaesst_die_unterste_klasse():
    assert klasse(kennlinie(SCHWELLE + 1)) > 1


def test_kennlinie_knickt_an_der_schwelle():
    """Oberhalb der Schwelle steigt der Score deutlich schneller.

    Genau das ist der Ersatz für das verworfene K.-o.-Kriterium: Kalkarme
    Flächen werden zusammengedrückt, kalkreiche gespreizt — ohne dass eine
    Fläche verschwindet (ADR 0008 §4).
    """
    am_knick = kennlinie(SCHWELLE)
    steigung_darunter = (am_knick - kennlinie(SCHWELLE - 10)) / 10
    steigung_darueber = (kennlinie(SCHWELLE + 10) - am_knick) / 10

    assert steigung_darueber > 2.5 * steigung_darunter


def test_kennlinie_bleibt_im_wertebereich():
    assert kennlinie(0) == 0
    assert kennlinie(100) == 100
    assert 0 <= kennlinie(-20) <= 100
    assert 0 <= kennlinie(150) <= 100


def test_klassengrenzen_passen_zur_kennlinie():
    """Die unterste Klasse endet genau dort, wo die Schwelle abbildet."""
    assert kennlinie(SCHWELLE) == KLASSENGRENZEN[0]


# ----------------------------------------------------------- beide Quellen


def test_kalkstein_bleibt_oben_trotz_nichtssagendem_bodentyp():
    """Der Befund aus dem ersten echten Lauf.

    Über den Eifelkalkmulden steht in der BK 50 meist "Braunerde". Ein
    Mittelwert beider Quellen drückte Blankenheim und Nettersheim damit in
    die unterste Klasse — fachlich falsch, das sind die Kalkstandorte der
    Region. Der Bodentyp sagt dort schlicht nichts über Carbonat aus.
    """
    wert = kalkscore("Kalkstein, Mergelstein", "Braunerde")

    assert wert is not None
    # Nicht ">= 3": Genau diese Deckelung nach unten hat den Fehler aus B1
    # durchgelassen, den der Nachtrag korrigiert (57 km² Kalkstein-Mergelstein
    # in der Bbox).
    assert klasse(wert) == 4


def test_kalkbodentyp_bestaetigt_und_traegt_nach():
    """Rendzina auf einer im 1:100.000 nicht erfassten Kalklinse."""
    ohne_boden = kalkscore("Sand, Kies", None)
    mit_rendzina = kalkscore("Sand, Kies", "Rendzina")

    assert ohne_boden is not None and mit_rendzina is not None
    assert klasse(ohne_boden) == 1
    assert klasse(mit_rendzina) == 4


def test_saurer_nasser_boden_ueberschreibt_den_untergrund():
    """Ein Hochmoor über Kalkstein ist kein Kalkstandort."""
    wert = kalkscore("Kalkstein", "Hochmoor")

    assert wert is not None
    assert klasse(wert) == 1


def test_eine_fehlende_quelle_traegt_die_andere_allein():
    assert kalkscore("Kalkstein", None) == kennlinie(100)
    assert kalkscore(None, "Rendzina") == kennlinie(100)


def test_ohne_jede_quelle_bleibt_die_zelle_leer():
    assert kalkscore(None, None) is None
    assert kalkscore("Gewässer", "") is None


# ------------------------------- Dämpfung hinter der Kennlinie (Nachtrag B1)


def test_flaeche_knapp_ueber_der_schwelle_bleibt_darueber():
    """Der Regressionstest des Nachtrags.

    Vorher wurde die Dämpfung auf den Rohwert angewandt: 56,7 wurde zu 48,2
    und fiel unter die Schwelle, obwohl die Lithologie carbonathaltig ist.
    Ein K.-o.-Kriterium durch die Hintertür, das ADR 0008 §4 ausdrücklich
    verworfen hat.
    """
    roh, schweigt = verknuepft(litho_score("Mergelstein, Sandstein"), boden_score("Braunerde"))

    assert schweigt is True
    assert roh is not None and roh > SCHWELLE

    wert = kalkscore("Mergelstein, Sandstein", "Braunerde")
    assert wert is not None
    assert klasse(wert) > 1


def test_verknuepft_liefert_ungedaempft_und_meldet_den_zweig():
    """Die Dämpfung gehört nicht mehr in den Rohwert."""
    roh, schweigt = verknuepft(100.0, 25.0)

    assert roh == 100.0
    assert schweigt is True


@pytest.mark.parametrize(
    ("boden", "erwartet"),
    [(100.0, False), (60.0, False), (10.0, False), (0.0, False), (25.0, True), (59.0, True)],
)
def test_daempfung_greift_nur_im_schweige_zweig(boden, erwartet):
    """Bestätigender und überschreibender Zweig bleiben ungedämpft."""
    _, schweigt = verknuepft(80.0, boden)

    assert schweigt is erwartet


def test_daempfung_wirkt_wie_ihr_wert():
    """0,85 soll 0,85 bedeuten — der Grund für den Umbau.

    Vor der Kennlinie angewandt wirkte die Konstante oberhalb der Schwelle
    wie gemessen 0,743 bis 0,775, je nach Rohwert.
    """
    ungedaempft = kalkscore("Kalkstein", "Rendzina")  # bestätigender Zweig
    gedaempft = kalkscore("Kalkstein", "Braunerde")  # Schweige-Zweig

    assert ungedaempft is not None and gedaempft is not None
    assert gedaempft == pytest.approx(ungedaempft * DAEMPFUNG_OHNE_AUSSAGE)


def test_unterhalb_der_schwelle_aendert_die_reihenfolge_nichts():
    """Dort ist die Kennlinie linear durch den Ursprung.

    Beide Reihenfolgen sind gleichwertig — deshalb wechselt unterhalb der
    Schwelle keine Fläche die Klasse.
    """
    wert = kalkscore("Sand, Kies", "Braunerde")
    roh, _ = verknuepft(litho_score("Sand, Kies"), boden_score("Braunerde"))

    assert wert is not None and roh is not None
    assert wert == pytest.approx(kennlinie(roh * DAEMPFUNG_OHNE_AUSSAGE))


# ---------------------------------- Zusammengesetzte Typen ohne Aussage (B3)


@pytest.mark.parametrize(
    "bodentyp", ["Niedermoor-Deckkulturboden", "Abtrags-Hochmoor-Deckkulturboden"]
)
def test_deckkulturboden_macht_den_ganzen_typ_zu_nodata(bodentyp):
    """Geprüft und so belassen: 2,37 km² in der Bbox.

    Aufgetragenes Material unbekannter Herkunft steht oben; aus dem
    verschütteten Untergrund einen Kalkwert abzuleiten hiesse, über den
    heutigen Wurzelraum etwas zu behaupten.
    """
    assert boden_score(bodentyp) is None
