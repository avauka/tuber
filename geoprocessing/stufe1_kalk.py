"""Stufe 1 — Faktorlayer Kalk aus IS GK 100 und IS BK 50 (ADR 0008 §7).

    python3 stufe1_kalk.py

Teuer und selten: Quellen lesen, auf das gemeinsame 20-m-Raster brennen, je
Zelle einen Score 0-100 und die verwendete Kaskadenstufe schreiben. Läuft
nur, wenn eine Quelle neu ist.

Ergebnis in `work/`, zwei deckungsgleiche GeoTIFFs:

    kalk_score.tif   Byte, 0-100, 255 = keine Datenlage
    kalk_stufe.tif   Byte, 2 = Kaskadenstufe 2 (GK 100 + BK 50), 0 = keine

Die beiden Dateien sind zugleich die von Invariante 10 geforderte
Aufschlüsselung: Der Teilscore je Faktor bleibt als eigener Layer erhalten
und wird nicht in den Gesamtscore hineingerechnet und vergessen.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

from kalk_zuordnung import (
    BODEN_BESTAETIGT_AB,
    BODEN_UEBERSCHREIBT_BIS,
    DAEMPFUNG_OHNE_AUSSAGE,
    SCHWELLE,
    boden_score,
    litho_score,
)
from raster import ZIELRASTER

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

WURZEL = Path(__file__).parent
RAW = WURZEL / "raw"
WORK = WURZEL / "work"

# Wo die entpackten Quellen liegen. Das Entpacken steht im README; hier wird
# nur gelesen, damit ein Lauf nicht stillschweigend Rohdaten anfasst.
GK100_SHAPE = RAW / "gk100_entpackt" / "shape" / "Basismodul" / "GK100_Hauptschichten.shp"
BK50_GPKG = RAW / "bk50_entpackt" / "BK50_GPKG" / "BK50_A.gpkg"

LITHOLOGIE_FELD = "LITHOLOG_1"
BODENTYP_FELD = "TYP_TEXT"

SCORE_TIF = WORK / "kalk_score.tif"
STUFE_TIF = WORK / "kalk_stufe.tif"
# Name laut AP17a-Nachtrag B4: Der Bericht ist die Metadatei des
# Faktorlayers und trägt dessen Namen.
BERICHT = WORK / "kalk.meta.json"

# 255 als nodata, weil der Score selbst nur 0-100 belegt.
NODATA = 255
KASKADENSTUFE = 2


class PipelineFehler(RuntimeError):
    """Abbruchgrund, der dem Nutzer etwas sagt."""


def _bbox_geometrie() -> ogr.Geometry:
    """Der Kartenausschnitt als Polygon — zum Zuschneiden der Flächen."""
    min_x, min_y, max_x, max_y = ZIELRASTER.bbox
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y), (min_x, min_y)):
        ring.AddPoint_2D(float(x), float(y))
    flaeche = ogr.Geometry(ogr.wkbPolygon)
    flaeche.AddGeometry(ring)
    return flaeche


def _flaeche_km2(geometrie: ogr.Geometry | None, ausschnitt: ogr.Geometry) -> float:
    """Fläche innerhalb des Ausschnitts, in km². Robust gegen kaputte Ringe."""
    if geometrie is None:
        return 0.0
    try:
        if ausschnitt.Contains(geometrie):
            return geometrie.GetArea() / 1e6
        return geometrie.Intersection(ausschnitt).GetArea() / 1e6
    except RuntimeError:
        try:
            return geometrie.MakeValid().Intersection(ausschnitt).GetArea() / 1e6
        except RuntimeError:
            return 0.0


def _zielraster(pfad: Path, dtype: int = gdal.GDT_Byte) -> gdal.Dataset:
    treiber = gdal.GetDriverByName("GTiff")
    datensatz = treiber.Create(
        str(pfad),
        ZIELRASTER.spalten,
        ZIELRASTER.zeilen,
        1,
        dtype,
        options=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    datensatz.SetGeoTransform(ZIELRASTER.geotransform)
    bezug = osr.SpatialReference()
    bezug.ImportFromEPSG(ZIELRASTER.epsg)
    datensatz.SetProjection(bezug.ExportToWkt())
    band = datensatz.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    band.Fill(NODATA)
    return datensatz


def _scores_brennen(
    quelle: Path,
    layername: str | None,
    feld: str,
    bewerten,
    ziel: Path,
) -> dict:
    """Ein Vektorlayer -> Rasterlayer mit dem Score der Zuordnungstabelle.

    Die Bewertung passiert einmal je **Attributwert**, nicht je Objekt:
    115 Lithologien und 136 Bodentypen gegen 191 000 Flächen — und wer
    Werte ohne Zuordnung hat, sieht sie im Bericht statt sie als Loch in
    der Karte zu suchen.
    """
    datenquelle = ogr.Open(str(quelle))
    if datenquelle is None:
        raise PipelineFehler(f"Quelle nicht lesbar: {quelle}")
    layer = datenquelle.GetLayerByName(layername) if layername else datenquelle.GetLayer(0)
    if layer is None:
        raise PipelineFehler(f"Layer {layername!r} fehlt in {quelle.name}.")
    if layer.FindFieldIndex(feld, True) < 0:
        raise PipelineFehler(f"Feld {feld!r} fehlt in {quelle.name}.")

    layer.SetSpatialFilterRect(*ZIELRASTER.bbox)

    # Zwischenlayer im Speicher: Geometrie plus der fertige Score. gdal
    # rastert danach in einem Zug über das Attribut.
    speicher = ogr.GetDriverByName("MEM").CreateDataSource("bewertet")
    bezug = osr.SpatialReference()
    bezug.ImportFromEPSG(ZIELRASTER.epsg)
    ziel_layer = speicher.CreateLayer("bewertet", bezug, ogr.wkbMultiPolygon)
    ziel_layer.CreateField(ogr.FieldDefn("score", ogr.OFTInteger))

    zwischenspeicher: dict[str, float | None] = {}
    ohne_zuordnung: dict[str, dict[str, float]] = {}
    ausschnitt = _bbox_geometrie()
    gezaehlt = 0
    uebernommen = 0

    definition = ziel_layer.GetLayerDefn()
    for objekt in layer:
        gezaehlt += 1
        rohwert = objekt.GetField(feld)
        schluessel = rohwert or ""
        if schluessel not in zwischenspeicher:
            zwischenspeicher[schluessel] = bewerten(rohwert)
        wert = zwischenspeicher[schluessel]
        geometrie = objekt.GetGeometryRef()
        if wert is None:
            # Nicht nur zählen, sondern die Fläche mitnehmen: Ob ein
            # unbekannter Wert 0,4 km² oder 250 km² gross ist, entscheidet,
            # ob er die Karte betrifft (AP17a-Nachtrag B4).
            eintrag = ohne_zuordnung.setdefault(schluessel, {"objekte": 0, "km2": 0.0})
            eintrag["objekte"] += 1
            eintrag["km2"] += _flaeche_km2(geometrie, ausschnitt)
            continue
        if geometrie is None:
            continue
        neu = ogr.Feature(definition)
        neu.SetField("score", int(round(wert)))
        neu.SetGeometry(geometrie.Clone())
        ziel_layer.CreateFeature(neu)
        uebernommen += 1

    raster = _zielraster(ziel)
    gdal.RasterizeLayer(raster, [1], ziel_layer, options=["ATTRIBUTE=score", "ALL_TOUCHED=FALSE"])
    raster.FlushCache()
    raster = None

    sortiert = sorted(ohne_zuordnung.items(), key=lambda p: -p[1]["km2"])
    return {
        "quelle": quelle.name,
        "feld": feld,
        "objekte_in_bbox": gezaehlt,
        "gerastert": uebernommen,
        "werte_ohne_zuordnung": [
            {"wert": wert, "objekte": int(zahlen["objekte"]), "km2": round(zahlen["km2"], 3)}
            for wert, zahlen in sortiert
        ],
    }


def _lesen(pfad: Path) -> np.ndarray:
    datensatz = gdal.Open(str(pfad))
    if not ZIELRASTER.passt_zu(
        datensatz.GetGeoTransform(), datensatz.RasterXSize, datensatz.RasterYSize
    ):
        raise PipelineFehler(f"{pfad.name} passt nicht auf das Zielraster.")
    return datensatz.GetRasterBand(1).ReadAsArray()


def _schreiben(pfad: Path, daten: np.ndarray) -> None:
    datensatz = _zielraster(pfad)
    datensatz.GetRasterBand(1).WriteArray(daten)
    datensatz.FlushCache()
    datensatz = None


def main() -> int:
    beginn = time.monotonic()
    WORK.mkdir(parents=True, exist_ok=True)

    for pfad in (GK100_SHAPE, BK50_GPKG):
        if not pfad.exists():
            print(
                f"FEHLER: {pfad} fehlt. Rohdaten herunterladen und entpacken — "
                "siehe geoprocessing/README.md.",
                file=sys.stderr,
            )
            return 1

    print(f"Zielraster: {ZIELRASTER.spalten} x {ZIELRASTER.zeilen} Zellen "
          f"à {ZIELRASTER.zellgroesse} m, EPSG:{ZIELRASTER.epsg}")

    print("Lithologie (IS GK 100) …")
    litho_bericht = _scores_brennen(
        GK100_SHAPE, None, LITHOLOGIE_FELD, litho_score, WORK / "kalk_litho.tif"
    )
    print(f"   {litho_bericht['gerastert']} von {litho_bericht['objekte_in_bbox']} Flächen")

    print("Bodentyp (IS BK 50) …")
    boden_bericht = _scores_brennen(
        BK50_GPKG, "BK50", BODENTYP_FELD, boden_score, WORK / "kalk_boden.tif"
    )
    print(f"   {boden_bericht['gerastert']} von {boden_bericht['objekte_in_bbox']} Flächen")

    print("Kaskade zusammenführen …")
    litho = _lesen(WORK / "kalk_litho.tif")
    boden = _lesen(WORK / "kalk_boden.tif")

    hat_litho = litho != NODATA
    hat_boden = boden != NODATA
    hat_daten = hat_litho | hat_boden

    # Verknüpfung wie in kalk_zuordnung.verknuepft, nur vektorisiert: Der
    # Bodentyp bestätigt, überschreibt oder schweigt — gemittelt wird nicht.
    # Der Rohwert bleibt hier ungedämpft; gedämpft wird unten hinter der
    # Kennlinie (AP17a-Nachtrag B1).
    roh = np.zeros(litho.shape, dtype=np.float32)
    beide = hat_litho & hat_boden
    l_f = litho.astype(np.float32)
    b_f = boden.astype(np.float32)
    schweigt = beide & (b_f > BODEN_UEBERSCHREIBT_BIS) & (b_f < BODEN_BESTAETIGT_AB)
    roh[beide] = np.where(
        b_f[beide] >= BODEN_BESTAETIGT_AB,
        np.maximum(l_f[beide], b_f[beide]),
        np.where(
            b_f[beide] <= BODEN_UEBERSCHREIBT_BIS,
            np.minimum(l_f[beide], b_f[beide]),
            np.maximum(l_f[beide], b_f[beide]),
        ),
    )
    nur_litho = hat_litho & ~hat_boden
    roh[nur_litho] = litho[nur_litho]
    nur_boden = hat_boden & ~hat_litho
    roh[nur_boden] = boden[nur_boden]

    # Steile Kennlinie (ADR 0008 §4), vektorisiert — dieselbe Formel wie
    # kalk_zuordnung.kennlinie, die der Test gegen Einzelwerte prüft.
    score = np.where(
        roh < SCHWELLE,
        roh * (25.0 / SCHWELLE),
        25.0 + (roh - SCHWELLE) * (75.0 / (100.0 - SCHWELLE)),
    )
    # Dämpfung erst hier, und nur im Schweige-Zweig.
    score = np.where(schweigt, score * DAEMPFUNG_OHNE_AUSSAGE, score)
    ergebnis = np.full(litho.shape, NODATA, dtype=np.uint8)
    ergebnis[hat_daten] = np.clip(np.round(score[hat_daten]), 0, 100).astype(np.uint8)

    stufe = np.zeros(litho.shape, dtype=np.uint8)
    stufe[hat_daten] = KASKADENSTUFE

    _schreiben(SCORE_TIF, ergebnis)
    _schreiben(STUFE_TIF, stufe)

    dauer = time.monotonic() - beginn
    abdeckung = float(hat_daten.mean() * 100)
    bericht = {
        "faktor": "kalk",
        "kaskadenstufe": KASKADENSTUFE,
        "zellen": int(litho.size),
        "zellen_mit_daten": int(hat_daten.sum()),
        "abdeckung_prozent": round(abdeckung, 2),
        "nur_lithologie": int(nur_litho.sum()),
        "nur_bodentyp": int(nur_boden.sum()),
        "beide_quellen": int(beide.sum()),
        "sekunden": round(dauer, 1),
        "lithologie": litho_bericht,
        "bodentyp": boden_bericht,
    }
    BERICHT.write_text(json.dumps(bericht, indent=2, ensure_ascii=False) + "\n")

    print(
        f"\n{SCORE_TIF.name} und {STUFE_TIF.name} geschrieben.\n"
        f"Abdeckung {abdeckung:.1f} % der Zellen, davon {int(beide.sum())} aus beiden Quellen.\n"
        f"Laufzeit {dauer:.0f} s. Einzelheiten: {BERICHT.name}"
    )
    # Laut, nicht still: Ein GK-100-Download mit neuer Nomenklatur soll hier
    # auffallen und nicht als Loch in der Karte gesucht werden (Nachtrag B4).
    # Die Fläche steht dabei, weil sie entscheidet, ob der Wert die Karte
    # überhaupt betrifft.
    for name, bericht_teil in (("Lithologie", litho_bericht), ("Bodentyp", boden_bericht)):
        fehlend = bericht_teil["werte_ohne_zuordnung"]
        if fehlend:
            summe = sum(eintrag["km2"] for eintrag in fehlend)
            print(
                f"\n{name}: {len(fehlend)} Werte ohne Zuordnung, zusammen "
                f"{summe:.2f} km² (bleiben leer):"
            )
            for eintrag in fehlend[:10]:
                print(
                    f"   {eintrag['km2']:9.2f} km²  {eintrag['objekte']:5d} Objekte  "
                    f"{eintrag['wert']!r}"
                )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PipelineFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        sys.exit(1)
