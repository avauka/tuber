"""Stufe 2 — Faktorlayer gewichten und Kacheln schreiben (ADR 0008 §7).

    python3 stufe2_tiles.py

Billig und oft: liest die vorhandenen Faktorlayer aus `work/`, gewichtet
sie, klassifiziert in vier Stufen und schreibt `out/suitability.pmtiles`.
**Läuft ohne Stufe 1**, das ist der Kern von ADR 0008 §7 — eine
Gewichtsänderung kostet Minuten, keinen Tag.

Warum Vektorkacheln und nicht Rasterkacheln: Invariante 10 verlangt, dass
sich jeder Score aufschlüsseln lässt. Ein Rasterbild kann beim Antippen
nichts über sich sagen; ein Polygon trägt seine Werte als Attribute mit.

Fehlt ein Faktor, wird sein Gewicht proportional auf die vorhandenen
umgelegt (ADR 0008 §5). Bei einem einzigen Faktor heisst das: Er trägt
100 %. Das steht so in `suitability.meta.json` und muss im UI erklärt
werden.
"""

import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

from gewichte import KLASSENGRENZEN, VERSION, umgelegt
from raster import ZIELRASTER

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

WURZEL = Path(__file__).parent
WORK = WURZEL / "work"
OUT = WURZEL / "out"

PMTILES = OUT / "suitability.pmtiles"
META = OUT / "suitability.meta.json"
MBTILES = WORK / "suitability.mbtiles"
POLYGONE = WORK / "suitability_flaechen.gpkg"

NODATA = 255

# Faktorname -> Dateiname des Layers aus Stufe 1. Wächst mit AP17b; was
# nicht existiert, gilt als nicht vorhanden und wird umgelegt.
FAKTOR_DATEIEN = {
    "kalk": "kalk_score.tif",
    "wasser": "wasser_score.tif",
    "exposition": "exposition_score.tif",
    "wirtsbaum": "wirtsbaum_score.tif",
    "struktur": "struktur_score.tif",
    "klima": "klima_score.tif",
}

STUFEN_DATEI = "kalk_stufe.tif"

# Der Score wird auf 5 Punkte gerundet, bevor Flächen gebildet werden.
# Ohne diese Stufung entstünde je Wert eine eigene Fläche.
#
# Gemessen am Stand vom 2026-08-13 (AP17a-Nachtrag A3), beide Gründe:
#
# 1. **Grösse.** 7,67 MB mit Rundung gegen 11,26 MB ohne, bei 7934 statt
#    14 664 Flächen — 3,59 MB Unterschied.
# 2. **Auflösung.** Ohne Rundung meldet GDAL beim Kachelschreiben "at least
#    one tile exceeded the default maximum tile size of 500000 bytes and was
#    encoded at lower resolution"; mit Rundung nicht. Ungerundet würde also
#    ausgerechnet die dichteste Kachel stillschweigend vergröbert.
#
# "Ohne Rundung" und "auf ganze Zahlen gerundet" sind hier dasselbe: Der
# Faktorlayer ist ein Byte-Raster, der Score also ohnehin ganzzahlig. Die
# beiden Archive waren byte-identisch.
#
# **Die Klasse wird trotzdem aus dem ungerundeten Wert abgeleitet** (B2) —
# siehe _klassen_raster.
SCORE_SCHRITT = 5

# Flächen unter dieser Zellzahl werden dem Nachbarn zugeschlagen. 25 Zellen
# sind bei 20 m genau ein Hektar — unterhalb davon behauptet eine Quelle im
# Massstab 1:50.000 ohnehin nichts.
MINDESTFLAECHE_ZELLEN = 25

# z13 entspricht bei uns rund 19 m je Pixel und damit der Rasterweite.
# Darüber hinaus zeichnet MapLibre per Overzoom weiter.
MIN_ZOOM = 6
MAX_ZOOM = 13

QUELLEN = [
    {
        "name": "IS GK 100 — Lithologische Zusammensetzung",
        "herausgeber": "Geologischer Dienst NRW",
        "lizenz": "dl-de/by-2-0",
        "stand": "2020-04-22",
        "abgerufen": "2026-08-13",
    },
    {
        "name": "IS BK 50 — Bodenkarte 1:50.000",
        "herausgeber": "Geologischer Dienst NRW",
        "lizenz": "dl-de/by-2-0",
        "stand": "2026-03-11",
        "abgerufen": "2026-08-13",
    },
]


class PipelineFehler(RuntimeError):
    """Abbruchgrund, der dem Nutzer etwas sagt."""


def _lesen(pfad: Path) -> np.ndarray:
    datensatz = gdal.Open(str(pfad))
    if not ZIELRASTER.passt_zu(
        datensatz.GetGeoTransform(), datensatz.RasterXSize, datensatz.RasterYSize
    ):
        raise PipelineFehler(
            f"{pfad.name} passt nicht auf das Zielraster — Stufe 1 mit derselben "
            "Rastergeometrie wiederholen."
        )
    return datensatz.GetRasterBand(1).ReadAsArray()


def _vorhandene_faktoren() -> dict[str, np.ndarray]:
    gefunden: dict[str, np.ndarray] = {}
    for name, datei in FAKTOR_DATEIEN.items():
        pfad = WORK / datei
        if pfad.exists():
            gefunden[name] = _lesen(pfad)
    if not gefunden:
        raise PipelineFehler(
            "Kein einziger Faktorlayer in work/. Erst Stufe 1 laufen lassen "
            "(python3 stufe1_kalk.py)."
        )
    return gefunden


def _gesamtscore(faktoren: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    anteile = umgelegt(list(faktoren))

    summe = np.zeros(next(iter(faktoren.values())).shape, dtype=np.float32)
    gueltig = np.ones(summe.shape, dtype=bool)
    for name, daten in faktoren.items():
        hat_wert = daten != NODATA
        # Eine Zelle bekommt nur einen Gesamtscore, wenn jeder beteiligte
        # Faktor dort etwas zu sagen hat. Sonst entstünde ein Score, der
        # heimlich auf weniger Faktoren beruht als angegeben.
        gueltig &= hat_wert
        summe += np.where(hat_wert, daten, 0).astype(np.float32) * (anteile[name] / 100.0)

    return summe, gueltig, anteile


def _klassen_raster(scores: np.ndarray) -> np.ndarray:
    """Klasse je Zelle — dieselben Grenzen wie gewichte.klasse, vektorisiert."""
    ergebnis = np.ones(scores.shape, dtype=np.uint16)
    for grenze in KLASSENGRENZEN:
        ergebnis += (scores >= grenze).astype(np.uint16)
    return ergebnis


def _gerundet_und_geklemmt(summe: np.ndarray, klassen: np.ndarray) -> np.ndarray:
    """Score auf SCORE_SCHRITT runden, ohne die Klassengrenze zu überschreiten.

    Ohne die Klemmung stünde in der Aufschlüsselung ein Score, der über der
    Grenze seiner eigenen Klasse liegt: 48,2 rundet auf 50, die Klasse ist
    aber aus 48,2 abgeleitet und damit 2. Score 50 neben Klasse 2 wäre für
    den Leser ein Widerspruch — und gegen den Geist von Invariante 10, die
    verlangt, dass die Zahlen sich erklären.

    Da alle Klassengrenzen Vielfache von SCORE_SCHRITT sind, kann die
    Rundung nur nach oben über eine Grenze schieben; ein Schritt zurück
    genügt. Die Schleife ist nur die Absicherung gegen andere Grenzen.
    """
    gerundet = np.round(summe / SCORE_SCHRITT) * SCORE_SCHRITT
    for _ in range(3):
        zu_hoch = _klassen_raster(gerundet) > klassen
        if not zu_hoch.any():
            break
        gerundet = np.where(zu_hoch, gerundet - SCORE_SCHRITT, gerundet)
    return np.clip(gerundet, 0, 100)


def _flaechen_schreiben(schluessel: np.ndarray, gueltig: np.ndarray) -> int:
    """Schlüsselraster in Polygone überführen.

    Der Schlüssel trägt drei Werte zugleich:
    `((gerundeter Score + 1) * 10 + Klasse) * 10 + Datenstufe`.

    Die Klasse reist mit, weil sie aus dem **ungerundeten** Score stammt und
    sich nach der Rundung nicht mehr rekonstruieren liesse (B2).
    Polygonisiert wird einmal; die Attribute entstehen beim Zerlegen. Mit
    weiteren Faktoren (AP17b) wächst der Schlüssel um deren Klassen.
    """
    treiber = gdal.GetDriverByName("MEM")
    quelle = treiber.Create("", ZIELRASTER.spalten, ZIELRASTER.zeilen, 1, gdal.GDT_UInt16)
    quelle.SetGeoTransform(ZIELRASTER.geotransform)
    bezug = osr.SpatialReference()
    bezug.ImportFromEPSG(ZIELRASTER.epsg)
    quelle.SetProjection(bezug.ExportToWkt())
    band = quelle.GetRasterBand(1)
    band.WriteArray(schluessel)
    band.SetNoDataValue(0)

    maske_ds = treiber.Create("", ZIELRASTER.spalten, ZIELRASTER.zeilen, 1, gdal.GDT_Byte)
    maske_ds.SetGeoTransform(ZIELRASTER.geotransform)
    maske_ds.SetProjection(bezug.ExportToWkt())
    maske_ds.GetRasterBand(1).WriteArray(gueltig.astype(np.uint8) * 255)
    maske = maske_ds.GetRasterBand(1)

    # Splitter wegräumen, bevor daraus Polygone werden.
    gdal.SieveFilter(band, maske, band, threshold=MINDESTFLAECHE_ZELLEN, connectedness=4)

    if POLYGONE.exists():
        POLYGONE.unlink()
    ziel = ogr.GetDriverByName("GPKG").CreateDataSource(str(POLYGONE))
    layer = ziel.CreateLayer("suitability", bezug, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("schluessel", ogr.OFTInteger))
    gdal.Polygonize(band, maske, layer, 0)

    anzahl = layer.GetFeatureCount()
    ziel = None
    return anzahl


def _attribute_ergaenzen(anteile: dict[str, float]) -> int:
    """Aus dem Schlüssel die lesbaren Attribute machen.

    Score, Teilscore je Faktor und Datenstufe stehen danach an jedem
    Polygon — das ist die Aufschlüsselung, die Invariante 10 verlangt, und
    genau das, was der Planer beim Antippen zeigt.
    """
    quelle = ogr.Open(str(POLYGONE), update=1)
    layer = quelle.GetLayer(0)
    layer.CreateField(ogr.FieldDefn("score", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("klasse", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("stufe", ogr.OFTInteger))
    for name in anteile:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTInteger))

    anzahl = 0
    layer.StartTransaction()
    for objekt in layer:
        schluessel = objekt.GetField("schluessel")
        # Der Schlüssel trägt den um eins erhöhten Score, damit Score 0 mit
        # Stufe 0 nicht auf den reservierten Schlüssel 0 fällt.
        stufe = schluessel % 10
        rest = schluessel // 10
        klassennummer = rest % 10
        score = rest // 10 - 1
        objekt.SetField("score", int(score))
        # Aus dem Schlüssel, nicht aus dem gerundeten Score neu berechnet:
        # Die Klasse gehört zum ungerundeten Wert (B2).
        objekt.SetField("klasse", int(klassennummer))
        objekt.SetField("stufe", int(stufe))
        # Solange nur ein Faktor existiert, ist sein Teilscore der
        # Gesamtscore — er trägt 100 %. Mit mehreren Faktoren kommen die
        # Teilwerte aus dem erweiterten Schlüssel.
        for name in anteile:
            objekt.SetField(name, int(score))
        layer.SetFeature(objekt)
        anzahl += 1
    layer.CommitTransaction()
    quelle = None
    return anzahl


def _kacheln_schreiben() -> None:
    if MBTILES.exists():
        MBTILES.unlink()
    gdal.VectorTranslate(
        str(MBTILES),
        str(POLYGONE),
        options=gdal.VectorTranslateOptions(
            format="MBTiles",
            dstSRS="EPSG:4326",
            reproject=True,
            layerName="suitability",
            datasetCreationOptions=[
                f"MINZOOM={MIN_ZOOM}",
                f"MAXZOOM={MAX_ZOOM}",
                "NAME=TUBER Eignung",
                "DESCRIPTION=Eignungskarte, vorberechnet (ADR 0008)",
                "TYPE=overlay",
            ],
        ),
    )
    if PMTILES.exists():
        PMTILES.unlink()
    ergebnis = subprocess.run(
        ["pmtiles", "convert", str(MBTILES), str(PMTILES)],
        capture_output=True,
        text=True,
    )
    if ergebnis.returncode != 0:
        print(ergebnis.stdout + ergebnis.stderr, file=sys.stderr)
        raise PipelineFehler(f"pmtiles convert endete mit Code {ergebnis.returncode}.")


def _sha256(pfad: Path) -> str:
    digest = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    beginn = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    faktoren = _vorhandene_faktoren()
    fehlend = [name for name in FAKTOR_DATEIEN if name not in faktoren]
    print(f"Faktoren vorhanden: {', '.join(faktoren)}")
    if fehlend:
        print(f"Faktoren fehlen:    {', '.join(fehlend)} — Gewichte werden umgelegt")

    summe, gueltig, anteile = _gesamtscore(faktoren)
    for name, anteil in anteile.items():
        print(f"   {name:<12} {anteil:5.1f} %")

    stufen_pfad = WORK / STUFEN_DATEI
    stufen = _lesen(stufen_pfad) if stufen_pfad.exists() else np.full(summe.shape, 0, np.uint8)

    # Klasse aus dem ungerundeten Wert, Score gerundet und in die Klasse
    # geklemmt (B2).
    klassen = _klassen_raster(summe)
    gerundet = _gerundet_und_geklemmt(summe, klassen).astype(np.uint16)
    # Schlüssel 0 ist reserviert für "keine Daten"; deshalb +1 auf den
    # Score, damit auch Score 0 mit Stufe 0 unterscheidbar bleibt.
    schluessel = np.where(
        gueltig,
        ((gerundet + 1) * 10 + klassen) * 10 + stufen.astype(np.uint16),
        0,
    )

    print("Flächen bilden …")
    polygone = _flaechen_schreiben(schluessel.astype(np.uint16), gueltig)
    print(f"   {polygone} Flächen")

    beschriftet = _attribute_ergaenzen(anteile)

    print("Kacheln schreiben …")
    _kacheln_schreiben()

    dauer = time.monotonic() - beginn
    meta = {
        "gewichtssatz_version": VERSION,
        "faktoren": {name: round(anteil, 2) for name, anteil in anteile.items()},
        "faktoren_fehlend": fehlend,
        "rasterweite_m": ZIELRASTER.zellgroesse,
        "epsg_verarbeitung": ZIELRASTER.epsg,
        "bbox": list(ZIELRASTER.bbox),
        "bbox_wgs84": [5.4, 49.7, 7.2, 51.1],
        "klassengrenzen": list(KLASSENGRENZEN),
        "min_zoom": MIN_ZOOM,
        "max_zoom": MAX_ZOOM,
        "flaechen": beschriftet,
        "quellen": QUELLEN,
        "bytes": PMTILES.stat().st_size,
        "sha256": _sha256(PMTILES),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    print(
        f"\n{PMTILES.name}: {meta['bytes'] / 1_000_000:.1f} MB, {beschriftet} Flächen\n"
        f"{META.name} geschrieben. Laufzeit {dauer:.0f} s."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PipelineFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        sys.exit(1)
